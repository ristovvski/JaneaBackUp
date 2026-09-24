#!/usr/bin/env python3
"""P3: any object_type=person rows in i04_log after 09:38Z? Closes the person-webhook question --
confirms whether the person subscription (id=3163027) is actually delivering, separate from lead."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-person-events", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobepersonevents01"},
    {"parameters": {"resource": "row", "operation": "get", "dataTableId": TABLE,
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "object_type", "condition": "eq", "keyValue": "=person"}]},
                     "options": {}},
     "id": "get_all", "name": "Get Person Rows", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "const cutoff = '2026-08-26T09:38:00.000Z';\n"
        "const all = $input.all().map(i => i.json);\n"
        "const after = all.filter(r => r.received_at > cutoff);\n"
        "return [{ json: { total_person_rows: all.length, after_cutoff: after.length,\n"
        "  sample: after.slice(0, 5), all_received_ats: all.map(r => r.received_at) } }];\n"
    ), "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [200, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Get Person Rows", "type": "main", "index": 0}]]},
    "Get Person Rows": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_person_events", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-person-events",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print(json.dumps(json.loads(r.read()), indent=2))
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
