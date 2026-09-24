#!/usr/bin/env python3
"""The WF-2 reply path around 'IF No Lead': what exists today, what it branches to, and which nodes
would have to be reachable to CREATE on a reply. READ ONLY."""
import json, os, ssl, urllib.request
from collections import deque

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
print(f"WF-2 {wf.get('versionId')}  nodes={len(wf['nodes'])}\n")

print("=== IF No Lead ===")
n = N.get("IF No Lead")
print(json.dumps(n.get("parameters"), ensure_ascii=False)[:500])
print(f"  -> {json.dumps((C.get('IF No Lead') or {}).get('main'), ensure_ascii=False)[:240]}")

print("\n=== reply-path chain from Merge Reply Ctx (BFS, 3 hops) ===")
seen, q = {"Merge Reply Ctx"}, deque([("Merge Reply Ctx", 0)])
while q:
    cur, d = q.popleft()
    if d >= 4:
        continue
    for gi, grp in enumerate((C.get(cur) or {}).get("main", []) or []):
        for c in (grp or []):
            nm = c.get("node")
            print(f"   {'  ' * d}{cur} --out{gi}--> {nm}")
            if nm not in seen:
                seen.add(nm)
                q.append((nm, d + 1))

print("\n=== the OOO gate and where the label decision happens ===")
for nm in ("First Reply Gate", "Body Lead Labels Union", "Body Reply Alert"):
    js = N[nm]["parameters"].get("jsCode", "")
    hits = [l.strip()[:104] for l in js.splitlines()
            if "__isOOO" in l or "reply_category" in l or "no lead" in l or "not in CRM" in l]
    print(f"  --- {nm} ---")
    for h in hits[:8]:
        print(f"      {h}")

print("\n=== which nodes are reachable from the REPLY path? (can we reuse the SENT creators?) ===")
reply_reach = set()
q = deque(["Merge Reply Ctx"])
while q:
    cur = q.popleft()
    for grp in (C.get(cur) or {}).get("main", []) or []:
        for c in (grp or []):
            nm = c.get("node")
            if nm and nm not in reply_reach:
                reply_reach.add(nm)
                q.append(nm)
for creator in ("Body Person Create", "Person Create", "Body Lead Create", "Gate Lead Create",
                "Lead Create", "Person Search", "Org Resolve", "Apply Enrich", "SL Fetch Lead"):
    print(f"   {creator:<22} reachable from reply path: {creator in reply_reach}")
