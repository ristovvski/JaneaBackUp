#!/usr/bin/env python3
"""Differential test: does an UPSERT (the strict, getColumns-validating operation) succeed
against i04_walk_staging (known-working, created earlier this session) from the SAME probe
mechanism that just failed against i04_event_log? If walk_staging succeeds and event_log fails,
the issue is specific to event_log (likely project-scoping: created in a different n8n project
than these API-deployed workflows live in)."""
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


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


TABLE = {"__rl": True, "mode": "name", "value": "i04_walk_staging"}
nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-diff-check", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-600, 300], "webhookId": "zzprobediffcheck01"},
    {"parameters": {"resource": "row", "operation": "upsert", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "walk_date", "condition": "eq", "keyValue": "=zzprobe-diff"}]},
                     "columns": {"mappingMode": "defineBelow", "value": {
                         "walk_date": "=zzprobe-diff", "resource": "=lead", "entity_id": "=999", "data_json": "=[]",
                     }, "matchingColumns": ["walk_date"], "schema": []}, "options": {}},
     "id": "insert", "name": "Insert", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-400, 300]},
    {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "walk_date", "condition": "eq", "keyValue": "=zzprobe-diff"}]},
                     "options": {}},
     "id": "cleanup", "name": "Cleanup", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Insert", "type": "main", "index": 0}]]},
    "Insert": {"main": [[{"node": "Cleanup", "type": "main", "index": 0}]]},
    "Cleanup": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_diff_check", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    try:
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-diff-check",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print("SUCCESS writing to i04_walk_staging:", r.status)
    except urllib.error.HTTPError as e:
        print("FAILED writing to i04_walk_staging:", e.code, e.read()[:500])
    except Exception as e:
        print("other error:", e)

    time.sleep(1)
    execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=1")
    for ex in execs.get("data", []):
        print("execution status:", ex.get("status"))

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print("cleaned up", wid)


if __name__ == "__main__":
    main()
