#!/usr/bin/env python3
"""Finovate first replies — Person-a9a7d542 / Person-8bb29b7c. READ ONLY.

Q1 what creates leads for [Events Visiting] campaigns
Q2 Lara: which node emitted 'no lead · not in CRM yet', and why didn't the OOO gate stop it
Q3 Kyle: does Smartlead have him at all; where did the trigger event come from
"""
import json, os, re, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
SL = os.environ["SMARTLEAD_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
KYLE = "pii-febd7426@example.invalid"
LARA = "pii-c7524b7a@example.invalid"


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


print("=" * 78)
print("Q0. the Finovate campaign(s)")
print("=" * 78)
camps = sl("/campaigns")
camps = camps if isinstance(camps, list) else []
fin = [c for c in camps if "finovate" in str(c.get("name") or "").lower()]
for c in fin:
    print(f"  {c.get('id')}  {c.get('name')!r}  status={c.get('status')} "
          f"created={c.get('created_at')}")
FIDS = [c.get("id") for c in fin]

print("\n" + "=" * 78)
print("Q3. do Kyle / Lara exist in Smartlead at all?")
print("=" * 78)
for label, em in (("Kyle", KYLE), ("Lara", LARA)):
    g = sl("/leads/", email=em)
    if isinstance(g, dict) and not g.get("__err") and g.get("id"):
        print(f"  {label:<5} GLOBAL lead id={g.get('id')} name="
              f"{(str(g.get('first_name'))+' '+str(g.get('last_name')))!r} "
              f"company={str(g.get('company_name'))[:26]!r}")
        lcd = g.get("lead_campaign_data") or []
        print(f"        campaigns: {[(c.get('campaign_id'), c.get('lead_category_id'), c.get('status')) for c in lcd]}")
    else:
        print(f"  {label:<5} GLOBAL lookup: {g.get('__err') or 'NOT FOUND'}")

print("\n  per-campaign presence + history:")
for cid in FIDS:
    off = 0
    seen = {}
    while off < 3000:
        r = sl(f"/campaigns/{cid}/leads-statistics", limit=100, offset=off)
        rows = (r or {}).get("data") or []
        if not rows:
            break
        for row in rows:
            to = str(row.get("to") or "").lower()
            if to in (KYLE, LARA):
                seen[to] = row
        if not r.get("hasMore"):
            break
        off += 100
    print(f"    campaign {cid}: matched {len(seen)}")
    for em, row in seen.items():
        hist = row.get("history") or []
        types = [str(h.get("type")) for h in hist]
        print(f"      {em}: history={types}")
        for h in hist:
            if str(h.get("type")).upper() == "REPLY":
                body = re.sub(r"(?s)<[^>]+>", " ", str(h.get("email_body") or ""))[:150]
                print(f"         REPLY {h.get('time')}  {body.strip()[:120]!r}")

print("\n" + "=" * 78)
print("Q2/Q3. WF-2 executions for these two")
print("=" * 78)
cur, pages, hits = None, 0, []
while pages < 8:
    q = {"workflowId": "jp7rum9Z0YDJkQWv", "limit": 250}
    if cur:
        q["cursor"] = cur
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q)) or {}
    rows = d.get("data") or []
    if not rows:
        break
    for r in rows:
        det = n8n(f"/api/v1/executions/{r['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        if not rd:
            continue
        blob = json.dumps(rd).lower()
        if "strougo" in blob or "lyberg" in blob:
            hits.append((r, rd))
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break
print(f"  pages walked {pages}   executions: {len(hits)}")
for r, rd in sorted(hits, key=lambda t: str(t[0].get("startedAt"))):
    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return None
    nz = o("Normalize") or {}
    raw = o("Webhook") or {}
    raw = raw.get("body", raw)
    gate = o("First Reply Gate") or {}
    al = o("Reply Alert") or {}
    print(f"\n  exec {r['id']} {r.get('startedAt')} status={r.get('status')}")
    print(f"     lead.email      : {(nz.get('lead') or {}).get('email')!r}")
    print(f"     event/campaign  : {nz.get('event')!r} / {str(nz.get('campaign_name'))[:46]!r}")
    print(f"     reply_category  : {nz.get('reply_category')!r}   raw={raw.get('reply_category')!r}")
    print(f"     __reply_class   : {nz.get('__reply_class')!r}")
    print(f"     gate: should={gate.get('__should_alert')} reason={gate.get('__alert_reason')!r} "
          f"ooo={gate.get('__ooo')!r}")
    print(f"     alert posted    : ok={al.get('ok')} ch={al.get('channel')}")
    txt = ((al.get("message") or {}).get("text")) or ""
    if txt:
        print(f"     headline        : {txt.splitlines()[0][:120]}")
    print(f"     lead resolved   : {(o('Lead Resolve') or {}).get('__lead_id')!r}")
    print(f"     person          : {(o('R Person Pick') or {}).get('__person_id')!r}")
    ran = [n for n in ("Body Lead Create", "Gate Lead Create", "Lead Create",
                       "Skip Lead Create", "Body Person Create", "Person Create") if n in rd]
    print(f"     creation nodes  : {ran or 'NONE RAN'}")

print("\n" + "=" * 78)
print("Q1. Pipedrive state")
print("=" * 78)
for label, em in (("Kyle", KYLE), ("Lara", LARA)):
    s = pd(f"/api/v2/persons/search?fields=email&exact_match=true&limit=5&term={urllib.parse.quote(em)}")
    items = ((s or {}).get("data") or {}).get("items") or []
    pid = (items[0].get("item") or {}).get("id") if items else None
    print(f"  {label}: person={pid}")
    if pid:
        leads = (pd(f"/v1/leads?limit=50&person_id={pid}") or {}).get("data") or []
        print(f"      leads={len(leads)} {[str(l.get('title'))[:44] for l in leads]}")
