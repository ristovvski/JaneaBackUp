#!/usr/bin/env python3
"""WF-2H digest: where the counted lines are built, and whether an OOO count is derivable from what
the digest already reads. If it counts from executions, __ooo / __alert_reason='ooo_no_alert' is
already on the wire; if it counts from Smartlead, the category is the source."""
import json, os, re, ssl, urllib.request

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
print(f"WF-2H versionId={wf.get('versionId')} active={wf.get('active')} nodes={len(wf['nodes'])}")
print("nodes:", [n["name"] for n in wf["nodes"]])
print()
for n in wf["nodes"]:
    js = (n.get("parameters") or {}).get("jsCode") or ""
    if not js:
        continue
    if re.search(r"lines|digest|push\(|replies|suppress", js, re.I):
        print(f"=== {n['name']} ({len(js.splitlines())} lines) ===")
        for i, l in enumerate(js.splitlines(), 1):
            if re.search(r"lines\.push|const lines|repl|ooo|OOO|suppress|count|\bn8n\b|"
                         r"executions|alert_reason", l):
                print(f"{i:>3}| {l.rstrip()[:114]}")
        print()
