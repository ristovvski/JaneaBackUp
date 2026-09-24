#!/usr/bin/env python3
"""The three Person Search URL nodes (M5/M6/M7) and the IFs that judge their results. Need the
exact term expression AND the verification step - normalising to a slug widens the search, so
whatever asserts 'this is really him' matters as much as the term itself."""
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


wf = n8n("/api/v1/workflows/2jdjKM2NJr473GdA")
N = {n["name"]: n for n in wf["nodes"]}
for nm in ("M5 Person Search URL", "M6 Person Search URL", "M7 Person Search URL",
           "Person Search URL", "M7 IF URL Found", "M5 IF URL Found", "M6 IF URL Found",
           "M7 Person Search Member", "M7 IF Member Verified"):
    n = N.get(nm)
    if not n:
        print(f"--- {nm}: ABSENT ---\n")
        continue
    print(f"--- {nm} ({n['type'].split('.')[-1]}) ---")
    print(json.dumps(n.get("parameters"), ensure_ascii=False, indent=1)[:1300])
    print()
