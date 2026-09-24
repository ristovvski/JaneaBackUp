#!/usr/bin/env python3
"""Delete the test rows left in i04_log by Nik's manual UI test and my e2e probe."""
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


TABLE = {"__rl": True, "mode": "id", "value": "zAW2IYoO6Dj0vdIt"}
nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-cleanup-test-rows", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzcleanuptestrows01"},
    {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "object_id", "condition": "eq", "keyValue": "=test-lead-123"}]},
                     "options": {}},
     "id": "d1", "name": "Delete e2e test", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 260]},
    {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_action", "condition": "eq", "keyValue": "=no"}]},
                     "options": {}},
     "id": "d2", "name": "Delete manual test", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 340]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Delete e2e test", "type": "main", "index": 0}]]},
    "Delete e2e test": {"main": [[{"node": "Delete manual test", "type": "main", "index": 0}]]},
    "Delete manual test": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_cleanup_test_rows", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    try:
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-cleanup-test-rows",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print("cleanup fired:", r.status)
    except urllib.error.HTTPError as e:
        print("cleanup FAILED:", e.code, e.read()[:500])
    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print("cleaned up probe", wid)


if __name__ == "__main__":
    main()
