#!/usr/bin/env python3
"""Verify i04_event_log actually exists before activating anything that depends on it."""
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


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-event-log-check", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobeeventlogchk01"},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "name", "value": "i04_event_log"},
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "event_id", "condition": "eq", "keyValue": "=zzprobe"}]},
                     "options": {}},
     "id": "get_rows", "name": "Get Rows", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
     "position": [-200, 300], "onError": "continueErrorOutput"},
    {"parameters": {"jsCode": "return [{ json: { branch: 'SUCCESS', count: $input.all().length } }];", "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 260]},
    {"parameters": {"jsCode": "return [{ json: { branch: 'ERROR', detail: $input.all().map(i=>i.json) } }];", "mode": "runOnceForAllItems"},
     "id": "report_err", "name": "Report Error", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 380]},
    {"parameters": {"mode": "append", "numberInputs": 2, "options": {}},
     "id": "merge", "name": "Merge", "type": "n8n-nodes-base.merge", "typeVersion": 3, "position": [200, 320]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [400, 320]},
]
connections = {
    "Webhook": {"main": [[{"node": "Get Rows", "type": "main", "index": 0}]]},
    "Get Rows": {"main": [[{"node": "Report", "type": "main", "index": 0}], [{"node": "Report Error", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Merge", "type": "main", "index": 0}]]},
    "Report Error": {"main": [[{"node": "Merge", "type": "main", "index": 1}]]},
    "Merge": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_event_log_check", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-event-log-check",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            result = json.loads(r.read())
        print(json.dumps(result, indent=2))
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
