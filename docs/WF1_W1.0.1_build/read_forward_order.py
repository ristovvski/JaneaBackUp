#!/usr/bin/env python3
"""Is forward-owner resolution UPSTREAM of First Reply Gate? If yes, the Test-owner note costs zero
new nodes - the telemetry tee can read it. If downstream, it needs its own pair, and I would rather
know that than bolt it somewhere it cannot see."""
import json, os, ssl, urllib.request
from collections import deque

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(p, attempt=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
C = wf.get("connections") or {}
names = [n["name"] for n in wf["nodes"]]
fwd = [n for n in names if "Forward" in n]
print("forward-related nodes:", fwd)

# reachability from a node
def reach(start):
    seen, q = set(), deque([start])
    while q:
        cur = q.popleft()
        for grp in (C.get(cur) or {}).get("main", []) or []:
            for c in grp or []:
                nm = c.get("node")
                if nm and nm not in seen:
                    seen.add(nm)
                    q.append(nm)
    return seen


down_of_gate = reach("First Reply Gate")
print(f"\nnodes downstream of First Reply Gate: {len(down_of_gate)}")
for f in fwd:
    up = "First Reply Gate" in reach(f)
    dn = f in down_of_gate
    print(f"   {f:<26} upstream-of-gate={up}  downstream-of-gate={dn}")

# where does the Test owner get chosen?
N = {n["name"]: n for n in wf["nodes"]}
for f in fwd:
    blob = json.dumps(N[f].get("parameters") or {}, ensure_ascii=False)
    if "forward_owner_map" in blob or "Test" in blob:
        print(f"\n=== {f} mentions the owner map ===")
        js = (N[f].get("parameters") or {}).get("jsCode") or ""
        for i, l in enumerate(js.splitlines(), 1):
            if "owner" in l.lower() or "forward_to" in l.lower() or "Test" in l:
                print(f"{i:>3}| {l.rstrip()[:112]}")
