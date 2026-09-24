#!/usr/bin/env python3
"""What does the existing claims dataTable look like, and how does WF-1 already talk to it?
The alert registry has to live in the SAME table - dataTable creation is UI-only, there is no REST
endpoint for it (verified previously). READ ONLY."""
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


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
print("=== WF-1 dataTable nodes ===")
for n in wf["nodes"]:
    if "dataTable" in n["type"] or "datatable" in n["type"].lower():
        print(f"\n--- {n['name']}  ({n['type']} v{n.get('typeVersion')}) ---")
        print(f"  onError={n.get('onError')}")
        print(json.dumps(n.get("parameters"), ensure_ascii=False, indent=1)[:1400])

print("\n=== M7 Alert Gate: the block that must move ===")
js = N["M7 Alert Gate"]["parameters"]["jsCode"]
for i, l in enumerate(js.splitlines(), 1):
    if any(t in l for t in ("sd", "reg", "key", "should", "reason", "prune")):
        print(f"  {i:>3}| {l.rstrip()[:110]}")

print("\n=== M7 Labels Compute: the registry WRITE that must move ===")
js2 = N["M7 Labels Compute"]["parameters"]["jsCode"]
started = False
for i, l in enumerate(js2.splitlines(), 1):
    if "Records alert DELIVERY" in l:
        started = True
    if started:
        print(f"  {i:>3}| {l.rstrip()[:110]}")

print("\n=== WF-2 equivalents (same class, 1 overlap observed) ===")
wf2 = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
for n in wf2["nodes"]:
    if "dataTable" in n["type"]:
        p = n.get("parameters") or {}
        print(f"  {n['name']:<24} op={p.get('operation')} table="
              f"{json.dumps(p.get('dataTableId'), ensure_ascii=False)[:80]}")
