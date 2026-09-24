#!/usr/bin/env python3
"""HeyReach Finovate population — the LinkedIn half, done with the right shape and the right
identity key. READ ONLY.

Members live at items[].linkedInUserProfile and carry NO email, so resolution uses the SLUG
waterfall deployed in WF-1 on 14 Aug (search by slug, exact_match=false, then verify the slug
against the person's own LinkedIn field). Never name-only.
"""
import json, os, re, ssl, urllib.parse, urllib.request
from collections import Counter

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
HR = os.environ["HEYREACH_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
CID = 572715
LI_FIELDS = ("66f0af69bec838dc3f90bb3f16c7d6087d8dbb20",
             "b59a7d0af178f3149381efd9a8476370b19ca3b5")


def pd(p):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://api.pipedrive.com" + p,
                headers={"x-api-token": PDT, "User-Agent": "janea/1.0"}),
                timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


def hr(p, b):
    r = urllib.request.Request("https://api.heyreach.io/api/public" + p, method="POST",
                               data=json.dumps(b).encode(),
                               headers={"X-API-KEY": HR, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        return {"__err": str(e)[:130]}


def slug_of(u):
    s = str(u or "").strip().lower()
    m = re.search(r"linkedin\.com/(?:in|pub)/([^/?#\s]+)", s)
    if m:
        try:
            return urllib.parse.unquote(m.group(1))
        except Exception:
            return m.group(1)
    return ""


members, off = [], 0
while off < 3000:
    r = hr("/campaign/GetLeadsFromCampaign", {"campaignId": CID, "offset": off, "limit": 100})
    items = (r or {}).get("items") or []
    if not items:
        break
    for it in items:
        p = it.get("linkedInUserProfile") or {}
        members.append({"profile_url": p.get("profileUrl"),
                        "slug": slug_of(p.get("profileUrl")),
                        "first": p.get("firstName"), "last": p.get("lastName"),
                        "company": p.get("companyName"), "position": p.get("position"),
                        "status": it.get("leadCampaignStatus"),
                        "connection": it.get("leadConnectionStatus"),
                        "message": it.get("leadMessageStatus")})
    off += 100
    if len(items) < 100:
        break
print(f"HeyReach campaign {CID}: {len(members)} members "
      f"(totalCount reported {r.get('totalCount')})")
print(f"  with a resolvable slug: {sum(1 for m in members if m['slug'])}")
print(f"  campaign status mix   : {dict(Counter(str(m['status']) for m in members))}")
print(f"  connection status mix : {dict(Counter(str(m['connection']) for m in members))}")

print("\nresolving against Pipedrive by SLUG (verified, never name-only)...")
counts = Counter()
out = []
for i, m in enumerate(members, 1):
    slug = m["slug"]
    pid = None
    if slug:
        s = pd(f"/api/v2/persons/search?fields=custom_fields&exact_match=false&limit=10&"
               f"term={urllib.parse.quote(slug)}")
        for it in (((s or {}).get("data") or {}).get("items") or []):
            item = it.get("item") or {}
            cfs = item.get("custom_fields")
            vals = cfs if isinstance(cfs, list) else list((cfs or {}).values())
            if any(slug_of(v) == slug for v in vals if isinstance(v, str)):
                pid = item.get("id")
                break
    has_lead = False
    deal = None
    if pid:
        leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
        has_lead = any(not l.get("is_archived") for l in leads)
        dl = (pd(f"/api/v2/deals?person_id={pid}&status=open&limit=10") or {}).get("data") or []
        deal = dl[0].get("id") if dl else None
    state = ("has_lead" if has_lead else ("open_deal" if deal else
             ("person_only" if pid else "nothing")))
    counts[state] += 1
    out.append({**m, "person_id": pid, "state": state, "deal_id": deal})
    if i % 40 == 0:
        print(f"  ...{i}/{len(members)}  {dict(counts)}")

print(f"\n{'=' * 60}\nHEYREACH FINOVATE POPULATION\n{'=' * 60}")
tot = len(out)
for k in ("has_lead", "open_deal", "person_only", "nothing"):
    v = counts.get(k, 0)
    print(f"  {k:<12} {v:>4}   {100*v//max(1,tot)}%")
print(f"  {'TOTAL':<12} {tot:>4}")
gap = [r for r in out if r["state"] in ("person_only", "nothing")]
print(f"\n  no lead: {len(gap)}   of those with a provider name: "
      f"{sum(1 for r in gap if r.get('first') and r.get('last'))}")
contacted = [r for r in gap if str(r.get("status")) not in ("0", "None", "NOT_STARTED")]
print(f"  of the gap, campaign status is not 'not started': {len(contacted)}")
json.dump({"members": out, "counts": dict(counts)},
          open(os.path.join(HERE, "finovate_heyreach_population.json"), "w", encoding="utf-8"),
          indent=1, ensure_ascii=False)
print("\nartifact: finovate_heyreach_population.json")
