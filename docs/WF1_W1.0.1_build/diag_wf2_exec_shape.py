#!/usr/bin/env python3
"""READ-ONLY: inspect real WF-2 execution structure (node names + output item keys) to find the
correct structural field to join Smartlead replies against, instead of a banned substring-blob scan."""
import os, json, ssl
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

N8N_BASE = os.environ["N8N_BASE_URL"].rstrip("/")
N8N_KEY = os.environ["N8N_API_KEY"]
WF2 = "jp7rum9Z0YDJkQWv"
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA else None


def n8n(path, params=None):
    q = urllib.parse.urlencode(params or {})
    url = f"{N8N_BASE}{path}?{q}" if q else f"{N8N_BASE}{path}"
    r = urllib.request.Request(url, headers={"X-N8N-API-KEY": N8N_KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x)


NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(hours=48)
page = n8n("/api/v1/executions", {"workflowId": WF2, "limit": 100})
execs = [e for e in page.get("data", []) if e.get("startedAt") and
         datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00")) >= SINCE]
print(f"{len(execs)} WF-2 executions in window. Listing status + time:")
for e in execs:
    print(" ", e["id"], e.get("startedAt"), e.get("status"), e.get("mode"))

# Find one execution around Ashwin's reply time (2026-08-05T06:08:38Z) - within +/- 40 min
target = datetime.fromisoformat("2026-08-05T06:08:38+00:00")
cand = min(execs, key=lambda e: abs(datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00")) - target))
print(f"\nClosest execution to Ashwin's reply time: {cand['id']} at {cand['startedAt']} (status={cand.get('status')})")

detail = n8n(f"/api/v1/executions/{cand['id']}", {"includeData": "true"})
rd = detail.get("data") or {}
result_data = (rd.get("resultData") or {})
run_data = result_data.get("runData") or {}
print("\nNode names in this execution:", list(run_data.keys()))
for node_name, runs in run_data.items():
    for run in runs[:1]:
        items = (((run.get("data") or {}).get("main") or [[]])[0]) or []
        if items:
            j = items[0].get("json", {})
            print(f"\n  Node '{node_name}' first output item JSON keys:", sorted(j.keys()) if isinstance(j, dict) else type(j))
            snippet = json.dumps(j, default=str)[:400]
            print("    sample:", snippet)
