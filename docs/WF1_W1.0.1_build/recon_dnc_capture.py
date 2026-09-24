#!/usr/bin/env python3
"""How does WF-2 already write the DNC ledger, and what does DNC__UpsertLedger__v1 expect?
WF-1 must reuse that contract verbatim - one path, one sub-workflow, one identity waterfall.
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


print("=== 1. WF-2 nodes that touch the ledger / UpsertLedger ===")
wf2 = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
C2 = wf2.get("connections") or {}
N2 = {n["name"]: n for n in wf2["nodes"]}
for n in wf2["nodes"]:
    blob = json.dumps(n.get("parameters") or {}, ensure_ascii=False)
    if "UpsertLedger" in blob or "RolYGL3J2CNg6Yp3" in blob or "reply_dnc" in blob \
            or "unsubscrib" in n["name"].lower() or "DNC" in n["name"]:
        print(f"\n--- {n['name']}  ({n['type'].split('.')[-1]}) onError={n.get('onError')} ---")
        js = (n.get("parameters") or {}).get("jsCode")
        if js:
            for i, l in enumerate(js.splitlines(), 1):
                print(f"  {i:>3}| {l.rstrip()[:112]}")
        else:
            print("  " + json.dumps(n.get("parameters"), ensure_ascii=False, indent=1)[:1100])
        print(f"  -> {json.dumps((C2.get(n['name']) or {}).get('main'), ensure_ascii=False)[:160]}")

print("\n=== 2. who feeds those nodes ===")
targets = {n["name"] for n in wf2["nodes"]
           if "UpsertLedger" in json.dumps(n.get("parameters") or {}, ensure_ascii=False)
           or "DNC" in n["name"]}
for src, v in C2.items():
    for gi, grp in enumerate(v.get("main") or []):
        for c in (grp or []):
            if c.get("node") in targets:
                print(f"   {src} --out{gi}--> {c.get('node')}")

print("\n=== 3. DNC__UpsertLedger__v1 — the input contract ===")
lg = n8n("/api/v1/workflows/RolYGL3J2CNg6Yp3")
print(f"  name={lg.get('name')!r} active={lg.get('active')} nodes={len(lg['nodes'])}")
for n in lg["nodes"][:6]:
    print(f"   - {n['name']}  ({n['type'].split('.')[-1]})")
for n in lg["nodes"]:
    if "executeWorkflowTrigger" in n["type"] or n["name"].lower().startswith(("when", "input")):
        print(f"\n  TRIGGER {n['name']}: {json.dumps(n.get('parameters'), ensure_ascii=False)[:500]}")
for n in lg["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    if "reason" in js or "entry_type" in js or "identity" in js.lower():
        print(f"\n  --- {n['name']} (fields it reads) ---")
        for i, l in enumerate(js.splitlines(), 1):
            if re.search(r"reason|entry_type|email|linkedin|person_id|source|correlation|ttl",
                         l):
                print(f"    {i:>3}| {l.rstrip()[:110]}")
        break

print("\n=== 4. WF-1 reply path: where the write must go ===")
wf1 = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
C1 = wf1.get("connections") or {}
for k in ("M7 Build", "M7 Alert Key", "M7 Reply Activity", "M7 IF Reply Activity Lead",
          "M7 Labels Compute", "M7 Lead Patch", "M8 IF Transition"):
    if k in C1:
        print(f"  {k:<28} -> {json.dumps(C1[k].get('main'), ensure_ascii=False)[:140]}")
N1 = {n["name"]: n for n in wf1["nodes"]}
print(f"\n  WF-1 has any UpsertLedger call: "
      f"{'UpsertLedger' in json.dumps(wf1, ensure_ascii=False)}")
print(f"  WF-1 classifier/negative-reply signals: "
      f"{[n['name'] for n in wf1['nodes'] if 'lassif' in n['name'] or 'egative' in n['name']]}")
