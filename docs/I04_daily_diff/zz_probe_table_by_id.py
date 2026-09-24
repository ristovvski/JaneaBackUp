#!/usr/bin/env python3
"""Try referencing i04_log by its real ID (zAW2IYoO6Dj0vdIt, from the URL Nik shared) instead of
by name -- if mode:'id' resolves where mode:'name' didn't, this is the same class of bug this
project already hit once (TABLE_IDS dict in build_dnc.py: name-mode fails to resolve in some
contexts, id-mode is the reliable fallback)."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-table-by-id", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobetablebyid01"},
    {"parameters": {"resource": "row", "operation": "upsert", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_id", "condition": "eq", "keyValue": "=zzprobe:byid:test"}]},
                     "columns": {"mappingMode": "defineBelow", "value": {
                         "event_id": "=zzprobe:byid:test", "received_at": "=2026-08-26T07:00:00.000Z",
                         "event_action": "=updated", "object_type": "=lead", "object_id": "=999",
                         "raw_json": "={\"probe\": true}", "top_level_keys": "=probe",
                     }, "matchingColumns": ["event_id"], "schema": []}, "options": {}},
     "id": "insert", "name": "Insert", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"resource": "row", "operation": "get", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_id", "condition": "eq", "keyValue": "=zzprobe:byid:test"}]},
                     "options": {}},
     "id": "readback", "name": "Readback", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [0, 300]},
    {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_id", "condition": "eq", "keyValue": "=zzprobe:byid:test"}]},
                     "options": {}},
     "id": "cleanup", "name": "Cleanup", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [200, 300]},
    {"parameters": {"jsCode": "return [{ json: $('Readback').first().json }];", "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [400, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [600, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Insert", "type": "main", "index": 0}]]},
    "Insert": {"main": [[{"node": "Readback", "type": "main", "index": 0}]]},
    "Readback": {"main": [[{"node": "Cleanup", "type": "main", "index": 0}]]},
    "Cleanup": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_table_by_id", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    try:
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-table-by-id",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print("SUCCESS:", json.dumps(json.loads(r.read()), indent=2))
    except urllib.error.HTTPError as e:
        print("FAILED:", e.code, e.read()[:1000])
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
