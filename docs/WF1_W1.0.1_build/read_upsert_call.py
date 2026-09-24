#!/usr/bin/env python3
"""The one existing UpsertLedger call (S4) - copy its node shape and input mapping verbatim so both
receivers speak the sub-workflow's real contract. Also confirm what reply_dnc does to expiry.
READ ONLY."""
import json, os, re, ssl, urllib.request

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


s4 = n8n("/api/v1/workflows/hhdnug5xdFLAxrOg")
N = {n["name"]: n for n in s4["nodes"]}
call = N.get("S4 Call UpsertLedger")
print("=== S4 Call UpsertLedger (the node shape to copy) ===")
print(f"  type={call['type']}  typeVersion={call.get('typeVersion')}  onError={call.get('onError')}")
print(json.dumps(call.get("parameters"), ensure_ascii=False, indent=1)[:900])

print("\n=== what S4 feeds it (the input contract in practice) ===")
bi = N.get("S4 Build Upsert Input")
if bi:
    print(bi["parameters"]["jsCode"][:900])

print("\n=== ledger: trigger + expiry behaviour for reply_dnc ===")
lg = n8n("/api/v1/workflows/RolYGL3J2CNg6Yp3")
print(f"  active={lg.get('active')}  nodes={len(lg['nodes'])}")
for n in lg["nodes"]:
    if "executeWorkflowTrigger" in n["type"]:
        print(f"  TRIGGER {n['name']}: "
              f"{json.dumps(n.get('parameters'), ensure_ascii=False)[:300]}")
for n in lg["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    if "reasonExpiryOverride" in js:
        m = re.search(r"function reasonExpiryOverride[\s\S]{0,420}", js)
        if m:
            print("\n  " + m.group(0).replace("\n", "\n  "))
        m2 = re.search(r"if \(s\.reason === 'reply_dnc'[\s\S]{0,200}", js)
        if m2:
            print("\n  reply_dnc guard:\n  " + m2.group(0).replace("\n", "\n  ")[:300])
        break
print("\n=== what the ledger returns (so the caller can log failure) ===")
for n in lg["nodes"]:
    if n["type"].endswith("code") and "return" in ((n.get("parameters") or {}).get("jsCode") or ""):
        js = n["parameters"]["jsCode"]
        if "ok" in js[-400:] or "status" in js[-400:]:
            print(f"  --- {n['name']} tail ---")
            print("  " + "\n  ".join(js.splitlines()[-12:]))
            break
