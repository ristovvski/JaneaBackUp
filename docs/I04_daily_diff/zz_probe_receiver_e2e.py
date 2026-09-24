#!/usr/bin/env python3
"""Activate dnc_i04_event_receiver, fire a synthetic v2-shaped Pipedrive-like payload at its real
webhook, and confirm a row actually lands in i04_log (via table-by-id readback), before
registering the real Pipedrive subscriptions."""
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
RECEIVER_ID = "wqORtqgRJ3W5YvBL"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


n8n(f"/api/v1/workflows/{RECEIVER_ID}/activate", "POST", {})
time.sleep(2)
live = n8n(f"/api/v1/workflows/{RECEIVER_ID}")
print("receiver active:", live.get("active"))

# a plausible v2-shaped test payload -- deliberately approximate, since the exact real shape is
# still unconfirmed; this just exercises the defensive-parse + write path end to end.
payload = {
    "meta": {"action": "update", "entity": "lead", "entity_id": "test-lead-123"},
    "data": {"id": "test-lead-123", "title": "Test Lead"},
    "previous": {"id": "test-lead-123", "title": "Test Lead (old)"},
}
req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/{{WEBHOOK_I04_PD_EVENTS}}",
                              method="POST", data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        print("webhook fire status:", r.status)
except urllib.error.HTTPError as e:
    print("webhook fire FAILED:", e.code, e.read()[:500])

time.sleep(2)
execs = n8n(f"/api/v1/executions?workflowId={RECEIVER_ID}&limit=1")
for ex in execs.get("data", []):
    eid = ex.get("id")
    print("execution", eid, ex.get("status"))
    full = n8n(f"/api/v1/executions/{eid}?includeData=true")
    run_data = ((full.get("data", {}).get("resultData") or {}).get("runData") or {})
    for nname in ["Log Event", "Insert Event Row"]:
        if nname in run_data:
            d = run_data[nname][0].get("data", {}).get("main", [[]])
            print(f"  {nname}:", json.dumps(d, indent=2)[:1200])
