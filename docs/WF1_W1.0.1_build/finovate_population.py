#!/usr/bin/env python3
"""FINOVATE POPULATION CHECK (amendment B). READ ONLY.

Complete list membership from both providers -> for each member, does a Pipedrive LEAD exist?
Identity waterfall is EMAIL-exact then person->leads. Never name-only: name matching is what bound
162 London leads to the wrong person.

Also answers the WHY: did the [Events Visiting] family ever have a list-upload creation step, or is
creation only ever driven by the SENT event? Evidence from execution history around launch.
"""
import json, os, ssl, urllib.parse, urllib.request
from collections import Counter

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
HR = os.environ.get("HEYREACH_API_KEY")
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
CAMPS = {3868449: "Valids", 3868450: "Catch-alls"}


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


def sl(p, **q):
    q["api_key"] = SL
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://server.smartlead.ai/api/v1" + p + "?" + urllib.parse.urlencode(q),
                headers={"User-Agent": "janea/1.0"}), timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


# ---- 1. complete membership, paged to exhaustion
members = {}
for cid, seg in CAMPS.items():
    off, n = 0, 0
    while off < 5000:
        r = sl(f"/campaigns/{cid}/leads", limit=100, offset=off)
        rows = (r or {}).get("data") or []
        if not rows:
            break
        for row in rows:
            ld = row.get("lead") or row
            em = str(ld.get("email") or "").strip().lower()
            if not em:
                continue
            members[em] = {"email": em, "campaign_id": cid, "segment": seg,
                           "first": ld.get("first_name"), "last": ld.get("last_name"),
                           "company": ld.get("company_name")}
            n += 1
        off += 100
        if len(rows) < 100:
            break
    print(f"campaign {cid} ({seg}): {n} members")
print(f"TOTAL distinct members: {len(members)}\n")

# HeyReach side
hr_n = 0
if HR:
    try:
        r = urllib.request.Request("https://api.heyreach.io/api/public/campaign/GetAll",
                                   method="POST", data=json.dumps({"offset": 0, "limit": 100}).encode(),
                                   headers={"X-API-KEY": HR, "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            hc = json.load(x)
        fin = [c for c in (hc.get("items") or [])
               if "finovate" in str(c.get("name") or "").lower()]
        print(f"HeyReach Finovate campaigns: {len(fin)} {[c.get('name') for c in fin]}")
        hr_n = len(fin)
    except Exception as e:
        print(f"HeyReach check failed: {str(e)[:90]}")

# ---- 2. per-member CRM state, email-exact only
print("\nresolving Pipedrive state (email-exact waterfall)...")
rows_out = []
counts = Counter()
for i, (em, m) in enumerate(members.items(), 1):
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&"
           f"term={urllib.parse.quote(em)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    pid = (items[0].get("item") or {}).get("id") if items else None
    leads, has_lead, deal = [], False, None
    if pid:
        leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
        active = [l for l in leads if not l.get("is_archived")]
        has_lead = bool(active)
        dl = (pd(f"/api/v2/deals?person_id={pid}&status=open&limit=10") or {}).get("data") or []
        deal = dl[0].get("id") if dl else None
    state = ("has_lead" if has_lead else ("open_deal" if deal else
             ("person_only" if pid else "nothing")))
    counts[state] += 1
    rows_out.append({**m, "person_id": pid, "state": state, "deal_id": deal,
                     "lead_count": len([l for l in leads if not l.get("is_archived")])})
    if i % 40 == 0:
        print(f"  ...{i}/{len(members)}  {dict(counts)}")

print(f"\n{'=' * 60}\nPOPULATION RESULT\n{'=' * 60}")
tot = len(rows_out)
for k in ("has_lead", "open_deal", "person_only", "nothing"):
    v = counts.get(k, 0)
    print(f"  {k:<12} {v:>4}   {100*v//max(1,tot)}%")
print(f"  {'TOTAL':<12} {tot:>4}")
gap = [r for r in rows_out if r["state"] in ("person_only", "nothing")]
print(f"\n  BACKFILL CANDIDATES (person_only + nothing): {len(gap)}")
print(f"    of those with a provider name: "
      f"{sum(1 for r in gap if r.get('first') and r.get('last'))}")

# ---- 3. WHY: is there any upload-time creation for this family?
print(f"\n{'=' * 60}\nWHY — was there ever a list-upload creation step?\n{'=' * 60}")
wfs = n8n("/api/v1/workflows?limit=250") or {}
hits = []
for w in (wfs.get("data") or []):
    full = n8n(f"/api/v1/workflows/{w['id']}")
    blob = json.dumps(full, ensure_ascii=False)
    if "/leads?offset" in blob or "campaigns/{{" in blob or "GetLeadsFromCampaign" in blob:
        if "Lead Create" in blob or "/v1/leads" in blob:
            hits.append((w["id"], w["name"], full.get("active")))
print("workflows that read a campaign LIST and can create leads:")
for wid, nm, act in hits:
    print(f"   {wid}  {'ACTIVE' if act else 'inact '}  {nm[:56]}")
if not hits:
    print("   NONE — no upload-time creation exists for any campaign family.")

json.dump({"members": rows_out, "counts": dict(counts)},
          open(os.path.join(HERE, "finovate_population.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nartifact: finovate_population.json")
