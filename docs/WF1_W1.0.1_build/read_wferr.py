#!/usr/bin/env python3
"""WF-ERR told the channel a reply was 'LOST - will not be delivered again' while WF-2R replayed it
within the same minute. The wording is not cosmetic: it tells a human whether to go hand-fix
something. Find the IMPACT text and what it keys on."""
import json, os, re, ssl, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

with urllib.request.urlopen(urllib.request.Request(
        BASE + "/api/v1/workflows/BbrXPABgOaaTJjD6",
        headers={"X-N8N-API-KEY": KEY}), timeout=200, context=ctx) as x:
    wf = json.load(x)
print(f"WF-ERR versionId={wf.get('versionId')} active={wf.get('active')} nodes={len(wf['nodes'])}")
print("nodes:", [n["name"] for n in wf["nodes"]])
print()
for n in wf["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    blob = json.dumps(n.get("parameters") or {})
    if re.search(r"LOST|IMPACT|will not be delivered|delivered again", js + blob, re.I):
        print(f"=== {n['name']} ({n['type'].split('.')[-1]}) ===")
        if js:
            for i, l in enumerate(js.splitlines(), 1):
                print(f"{i:>3}| {l.rstrip()[:116]}")
        else:
            print(blob[:1500])
        print()
