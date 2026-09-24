#!/usr/bin/env python3
"""Build Report keys the verdict off nz.event. Before making the verdict event-aware, find out what
Normalize actually emits there and with what casing - a mapping keyed on a field that is really
called something else would silently fall through to the blanket 'LOST'."""
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
        if attempt < 3:
            time.sleep(6)
            return n8n(p, attempt + 1)
        raise


ids = (n8n("/api/v1/executions?workflowId=jp7rum9Z0YDJkQWv&limit=40") or {}).get("data") or []
seen = {}
for e in ids:
    try:
        d = n8n(f"/api/v1/executions/{e['id']}?includeData=true")
        rd = ((d.get("data") or {}).get("resultData") or {}).get("runData") or {}
        nz = rd["Normalize"][0]["data"]["main"][0][0]["json"]
    except Exception:
        continue
    key = (repr(nz.get("event")), repr(nz.get("event_type")))
    seen[key] = seen.get(key, 0) + 1
print("Normalize output, (event, event_type) pairs across retained executions:")
for k, v in sorted(seen.items(), key=lambda t: -t[1]):
    print(f"   event={k[0]:<18} event_type={k[1]:<18} x{v}")
