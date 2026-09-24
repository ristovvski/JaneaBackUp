#!/usr/bin/env python3
"""Wait for the n8n instance API to recover after the 200-concurrent test's instance-wide 503,
then report gate status + recent execution outcomes. Polls, doesn't hammer."""
import json, os, ssl, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WID = "9aP2dP0jgAPFGDvA"


def n8n(path):
    r = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": KEY, "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=30, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


for attempt in range(10):
    try:
        full = n8n(f"/api/v1/workflows/{WID}")
        print(f"attempt {attempt}: API responded. active={full.get('active')}")
        break
    except Exception as e:
        print(f"attempt {attempt}: API still down ({e}), waiting 15s...")
        time.sleep(15)
else:
    print("API did not recover in time")
    raise SystemExit(1)

execs = n8n(f"/api/v1/executions?workflowId={WID}&limit=30")
rows = execs.get("data", [])
statuses = {}
for e in rows:
    s = e.get("status", "?")
    statuses[s] = statuses.get(s, 0) + 1
print("last 30 executions by status:", statuses)
if rows:
    print("most recent 5:")
    for e in rows[:5]:
        print(" ", e.get("startedAt"), e.get("stoppedAt"), e.get("status"))
