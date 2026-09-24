#!/usr/bin/env python3
"""exec 16703 is WF-1, not WF-2, so my WF-2 node-name probe proved nothing. List what ACTUALLY ran,
and read WF-1's reply path to see whether person/lead creation exists on it at all."""
import json, os, ssl, urllib.request

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
    except Exception as e:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


d = n8n("/api/v1/executions/16703?includeData=true")
rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
print(f"nodes that RAN in exec 16703 ({len(rd)}):")
for nm in rd:
    try:
        j = rd[nm][0]["data"]["main"][0][0]["json"]
    except Exception:
        j = {}
    keys = [k for k in j if k.startswith("__")][:6]
    print(f"   {nm:<34} {json.dumps({k: j[k] for k in keys}, ensure_ascii=False)[:74]}")

for nm in ("Normalize", "Dedupe", "Route Event", "Event Router"):
    if nm in rd:
        try:
            j = rd[nm][0]["data"]["main"][0][0]["json"]
        except Exception:
            continue
        print(f"\n--- {nm} output (trimmed) ---")
        print(json.dumps(j, ensure_ascii=False, indent=1)[:1400])

wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
print(f"\nWF-1 versionId={wf.get('versionId')} nodes={len(wf['nodes'])}")
names = [n["name"] for n in wf["nodes"]]
print("\nWF-1 nodes mentioning person/lead/create/reply:")
for n in names:
    if any(k in n.lower() for k in ("person", "lead", "create", "reply", "activity", "label")):
        print("   -", n)

# which branch does a reply event take? find the switch/if that routes on event
for n in wf["nodes"]:
    if n["type"].endswith(("switch", "if")) and any(
            k in n["name"].lower() for k in ("event", "route", "kind", "type")):
        print(f"\n=== router node: {n['name']} ({n['type'].split('.')[-1]}) ===")
        print(json.dumps(n.get("parameters"), ensure_ascii=False)[:1500])
