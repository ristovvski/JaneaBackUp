#!/usr/bin/env python3
"""Person-b0fb1597 false 'Open lead' alert — which path fired, and which match step missed.

READ ONLY. Person 85761 has existed since ~13 Aug and is in the registry via Surfe/S3, yet a
HeyReach-side alert treated him as new. Find the execution, quote the resolver steps that ran, and
read his actual identity state (the hypothesis is a linkedin-only row with no email).
"""
import json, os, ssl, urllib.parse, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
PDT = os.environ["PIPEDRIVE_API_TOKEN"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


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


print("=" * 78)
print("1. PIPEDRIVE state of person 85761")
print("=" * 78)
p = (pd("/api/v2/persons/85761") or {}).get("data") or {}
print(f"  name={p.get('name')!r}  add_time={p.get('add_time')}  owner={p.get('owner_id')}")
print(f"  emails={[e.get('value') for e in (p.get('emails') or [])]}")
print(f"  phones={[e.get('value') for e in (p.get('phones') or [])]}")
cf = p.get("custom_fields") or {}
LI = {"66f0af69bec838dc3f90bb3f16c7d6087d8dbb20": "linkedin_lh",
      "b59a7d0af178f3149381efd9a8476370b19ca3b5": "linkedin_profile"}
for k, lbl in LI.items():
    print(f"  {lbl:<18} {json.dumps(cf.get(k))[:90]}")
leads = (pd("/v1/leads?limit=50&person_id=85761") or {}).get("data") or []
print(f"  leads: {len(leads)}")
for l in leads:
    print(f"     {l.get('id')} {str(l.get('title'))[:58]!r} labels={len(l.get('label_ids') or [])}")

print("\n" + "=" * 78)
print("2. WF-1 executions mentioning Pickering")
print("=" * 78)
cur, pages, hits = None, 0, []
while pages < 8:
    q = {"workflowId": "2jdjKM2NJr473GdA", "limit": 250}
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
        if "ickering" not in json.dumps(rd):
            continue
        hits.append((r, rd))
    cur = d.get("nextCursor")
    pages += 1
    if not cur:
        break
print(f"  pages walked: {pages}   executions found: {len(hits)}")
for r, rd in sorted(hits, key=lambda t: str(t[0].get("startedAt"))):
    def o(nm):
        try:
            return rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            return None
    nz = o("Normalize") or {}
    raw = o("Webhook") or {}
    raw = raw.get("body", raw)
    print(f"\n  exec {r['id']}  {r.get('startedAt')}  status={r.get('status')}  nodes={len(rd)}")
    print(f"     event   : {nz.get('event')!r}")
    ld = nz.get("lead") or {}
    print(f"     lead    : {ld.get('full_name')!r} slug={ld.get('slug')!r}")
    print(f"     email   : {ld.get('email_address')!r} / enriched={ld.get('enriched_email')!r}")
    print(f"     campaign: {str((nz.get('campaign') or {}).get('name'))[:50]!r}")
    print(f"     nodes ran: {sorted(rd.keys())}")
    for step in ("M7 IF Email Present", "M7 Person Search Email", "M7 Person Search URL",
                 "M7 IF URL Found", "M7 Person Search Member", "M7 IF Member Verified",
                 "M7 Slack Warn", "M7 Critical Slack", "IF Email Present", "Person Search URL",
                 "IF URL Found", "Person Search Member", "PID Resolved", "Lead Search",
                 "Lead Create Gate", "Create Lead"):
        if step in rd:
            j = o(step) or {}
            items = ((j.get("data") or {}) or {}).get("items")
            extra = (f" items={len(items)}" if isinstance(items, list)
                     else f" {json.dumps({k: v for k, v in list(j.items())[:3]}, ensure_ascii=False)[:70]}")
            print(f"       [ran] {step:<26}{extra}")
