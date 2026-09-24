#!/usr/bin/env python3
"""Both Carla alerts used the SAME key P85942|572715 and both read 'first_alert' - so the registry
did not contain it on the second run. Is it there NOW, and does M7 Labels Compute actually reach the
write? (My previous check grepped the key for 'carla', which could never match - the key is
P85942|572715.)"""
import json, os, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
CARLA = "P85942|572715"


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


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
sd = wf.get("staticData") or {}
if isinstance(sd, str):
    sd = json.loads(sd)
reg = ((sd.get("global") or {}).get("__alerted_v1") or {})
print(f"registry size: {len(reg)}")
print(f"  Carla's exact key {CARLA!r} present: {CARLA in reg}")
if CARLA in reg:
    print(f"     stamped {reg[CARLA]}")
print(f"  keys for campaign 572715: {sum(1 for k in reg if k.endswith('|572715'))}")
print(f"  P-prefixed (person-keyed) keys: {sum(1 for k in reg if k.startswith('P'))}")
print(f"  L-prefixed (lead-keyed) keys  : {sum(1 for k in reg if k.startswith('L'))}")

print("\n=== does M7 Labels Compute run AFTER M7 Critical Slack? (graph order) ===")
C = wf.get("connections") or {}
for src, v in C.items():
    for gi, grp in enumerate(v.get("main") or []):
        for c in (grp or []):
            if c.get("node") in ("M7 Labels Compute", "M7 Critical Slack", "M7 IF Patch",
                                 "M7 Alert Suppressed"):
                print(f"   {src} --out{gi}--> {c.get('node')}")

print("\n=== in exec 41222 (the FIRST alert), did the registry write execute? ===")
d = n8n("/api/v1/executions/41222?includeData=true")
rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
print(f"  nodes that ran: {sorted(rd.keys())}")
order = [(nm, rd[nm][0].get("startTime")) for nm in rd if rd[nm] and rd[nm][0].get("startTime")]
order.sort(key=lambda t: t[1] or 0)
print("\n  execution order (startTime):")
for nm, t in order:
    mark = "  <<<" if nm in ("M7 Critical Slack", "M7 Labels Compute", "M7 Alert Gate") else ""
    print(f"     {nm}{mark}")
