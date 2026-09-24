#!/usr/bin/env python3
"""READ ONLY. Exact parameters of `IF Auth Warn` and `Ops Warn Bad Secret`, plus positions, so the
insert preserves what they read instead of guessing. Also: does the claims table already hold a
`wf2_auth_notice` row (a prior partial port would change the migration)?"""
import json
import os
import ssl
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2 = "jp7rum9Z0YDJkQWv"


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


wf = n8n("/api/v1/workflows/%s" % WF2)
N = {n["name"]: n for n in wf["nodes"]}
for nm in ("Verify Secret", "IF Authentic", "IF Auth Warn", "Ops Warn Bad Secret",
           "Alert Key", "DT Alert Get"):
    n = N.get(nm)
    if not n:
        print("%s: ABSENT" % nm)
        continue
    print("=" * 72)
    print("=== %s   type=%s tv=%s pos=%s onError=%s ===" % (
        nm, n["type"].split(".")[-1], n.get("typeVersion"), n.get("position"), n.get("onError")))
    p = dict(n.get("parameters") or {})
    p.pop("jsCode", None)
    print(json.dumps(p, ensure_ascii=False, indent=1)[:2200])
