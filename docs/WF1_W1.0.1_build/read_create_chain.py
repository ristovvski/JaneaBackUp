#!/usr/bin/env python3
"""The WF-2 SENT create chain: who feeds Body Lead Create, and what name data was actually
available at Body Person Create time in exec 35110."""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
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


wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}
print("=== who feeds the create nodes ===")
for src, v in C.items():
    for grp in (v.get("main") or []):
        for c in (grp or []):
            if c.get("node") in ("Body Person Create", "Person Create", "Body Lead Create",
                                 "Gate Lead Create", "Lead Create", "IF Lead Exists"):
                print(f"   {src}  ->  {c.get('node')}")
print()
for nm in ("Body Person Create", "Body Lead Create"):
    js = N[nm]["parameters"]["jsCode"]
    print(f"=== {nm} ===")
    for i, l in enumerate(js.splitlines(), 1):
        if any(t in l for t in ("name", "person_id", "__person", "first", "last", "company",
                                "const n =", "$json", "$(")):
            print(f"  {i:>3}| {l.rstrip()[:114]}")
    print()

print("=== exec 35110: what name data existed at that moment ===")
d = n8n("/api/v1/executions/35110?includeData=true")
rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}


def o(nm):
    try:
        return rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception:
        return None


nz = o("Normalize") or {}
ld = nz.get("lead") or {}
print(f"  Normalize lead: full_name={ld.get('full_name')!r} first={ld.get('first')!r} "
      f"last={ld.get('last')!r} company={ld.get('company')!r} email={ld.get('email')!r}")
raw = o("Webhook") or {}
raw = raw.get("body", raw)
print(f"  raw lead_data : {json.dumps(raw.get('lead_data'), ensure_ascii=False)[:220]}")
print(f"  raw to_name   : {raw.get('to_name')!r}")
ae = o("Apply Enrich")
print(f"  Apply Enrich  : {'ran' if ae else 'did NOT run'}")
if ae:
    en = ae.get("__enriched") or {}
    print(f"     __enriched.lead: {json.dumps(en.get('lead'), ensure_ascii=False)[:200]}")
pc = o("Person Create") or {}
print(f"  Person Create response shape: {json.dumps(pc, ensure_ascii=False)[:160]}")
blc = o("Body Lead Create") or {}
print(f"  Body Lead Create saw person_id = {(blc.get('__body') or {}).get('person_id')!r}")
print(f"  nodes in run: {sorted(rd.keys())}")
