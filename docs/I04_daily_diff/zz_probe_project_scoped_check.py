#!/usr/bin/env python3
"""Decisive test: create a probe workflow EXPLICITLY inside project 57BsS5BV36DRX0Cw (the
"Personal" project, visible in Nik's screenshot URL where i04_log lives) and see if IT can
resolve i04_log where my default-project probes couldn't. If yes, this is confirmed as a
project-scoping issue and the fix is deploying the real workflows into that same project."""
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
PROJECT_ID = "57BsS5BV36DRX0Cw"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


TABLE = {"__rl": True, "mode": "name", "value": "i04_log"}
nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-project-scoped", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobeprojscoped01"},
    {"parameters": {"resource": "row", "operation": "upsert", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_id", "condition": "eq", "keyValue": "=zzprobe:proj:test"}]},
                     "columns": {"mappingMode": "defineBelow", "value": {
                         "event_id": "=zzprobe:proj:test", "received_at": "=2026-08-26T07:00:00.000Z",
                         "event_action": "=updated", "object_type": "=lead", "object_id": "=999",
                         "raw_json": "={\"probe\": true}", "top_level_keys": "=probe",
                     }, "matchingColumns": ["event_id"], "schema": []}, "options": {}},
     "id": "insert", "name": "Insert", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_id", "condition": "eq", "keyValue": "=zzprobe:proj:test"}]},
                     "options": {}},
     "id": "cleanup", "name": "Cleanup", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [0, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [200, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Insert", "type": "main", "index": 0}]]},
    "Insert": {"main": [[{"node": "Cleanup", "type": "main", "index": 0}]]},
    "Cleanup": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_project_scoped", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    body = {"name": wf_json["name"], "nodes": wf_json["nodes"],
            "connections": wf_json["connections"], "settings": wf_json["settings"],
            "projectId": PROJECT_ID}
    try:
        created = n8n("/api/v1/workflows", "POST", body)
        wid = created["id"]
        print(f"created id={wid} (project param accepted)")
    except urllib.error.HTTPError as e:
        print("workflow creation with projectId FAILED:", e.code, e.read()[:800])
        return

    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-project-scoped",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print("SUCCESS:", r.status)
    except urllib.error.HTTPError as e:
        print("FAILED:", e.code, e.read()[:800])

    time.sleep(1)
    execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=1")
    for ex in execs.get("data", []):
        print("execution status:", ex.get("status"))

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print("cleaned up", wid)


if __name__ == "__main__":
    main()
