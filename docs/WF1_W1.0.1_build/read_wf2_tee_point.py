#!/usr/bin/env python3
"""Where to hang the reply-class telemetry tee, and what an existing Slack node looks like so the
new one copies its credential/type exactly rather than being invented."""
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
    except Exception:
        if attempt < 4:
            time.sleep(7)
            return n8n(p, attempt + 1)
        raise


wf = n8n("/api/v1/workflows/jp7rum9Z0YDJkQWv")
N = {n["name"]: n for n in wf["nodes"]}
C = wf.get("connections") or {}
print(f"WF-2 versionId={wf.get('versionId')} nodes={len(wf['nodes'])}\n")

for nm in ("First Reply Gate", "Reply Alert", "Body Reply Alert"):
    print(f"{nm} -> {json.dumps((C.get(nm) or {}).get('main'), ensure_ascii=False)[:220]}")
    n = N.get(nm)
    if n:
        print(f"   position={n.get('position')} type={n['type']}")
print()

# an existing Slack node to copy shape from
for n in wf["nodes"]:
    if n["type"].endswith("slack"):
        print(f"=== sample Slack node: {n['name']} ===")
        print(f"   type={n['type']} typeVersion={n.get('typeVersion')}")
        print(f"   credentials={json.dumps(n.get('credentials'), ensure_ascii=False)}")
        print(f"   onError={n.get('onError')} retryOnFail={n.get('retryOnFail')}")
        print(f"   parameters={json.dumps(n.get('parameters'), ensure_ascii=False)[:600]}")
        break

# an existing IF node shape
for n in wf["nodes"]:
    if n["type"].endswith(".if"):
        print(f"\n=== sample IF node: {n['name']} ===")
        print(f"   type={n['type']} typeVersion={n.get('typeVersion')}")
        break

# the reply category on Normalize, for the activity note
print("\n=== Body Reply Activity: note construction lines ===")
js = N["Body Reply Activity"]["parameters"]["jsCode"].splitlines()
for i, l in enumerate(js, 1):
    if 25 <= i <= 36:
        print(f"{i:>3}| {l.rstrip()}")
print("\n=== does Normalize expose reply_category? ===")
nzjs = N["Normalize"]["parameters"]["jsCode"]
for i, l in enumerate(nzjs.splitlines(), 1):
    if "reply_category" in l or "category" in l:
        print(f"{i:>3}| {l.rstrip()[:112]}")
