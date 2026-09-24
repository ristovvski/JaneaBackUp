#!/usr/bin/env python3
"""What does WF-2H actually have in hand? The OOO count must come from a source it already reads -
inventing a new data path for a digest line is not worth it, and counting something we cannot
defend is worse than omitting the line."""
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


wf = n8n("/api/v1/workflows/nK3yIOqRcBearV8s")
N = {n["name"]: n for n in wf["nodes"]}
for nm in ("SL Stats", "SL Stats Summary", "WF-2H Digest", "CONFIG"):
    n = N.get(nm)
    print(f"=== {nm} ({n['type'].split('.')[-1]}) ===")
    js = (n.get("parameters") or {}).get("jsCode")
    if js:
        for i, l in enumerate(js.splitlines(), 1):
            print(f"{i:>3}| {l.rstrip()[:112]}")
    else:
        print(json.dumps(n.get("parameters"), ensure_ascii=False)[:2000])
    print()
