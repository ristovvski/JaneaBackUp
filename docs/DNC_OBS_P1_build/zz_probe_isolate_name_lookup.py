#!/usr/bin/env python3
"""Isolate whether n8n's Data Table 'mode: name' resource lookup actually resolves at runtime,
independent of UpsertLedger. Minimal: webhook -> dataTable Get (returnAll, no filter) against
dnc_registry_dev by NAME -> respond with row count. Creates, fires, reports, deletes."""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


WEBHOOK_PATH = "zz-probe-name-lookup"
TABLE_MODE = sys.argv[1] if len(sys.argv) > 1 else "name"   # "name" or "id"
TABLE_VALUE = "dnc_registry_dev" if TABLE_MODE == "name" else "UOgKwlGsL28lX61O"

wf_json = {
    "name": "zz_probe_name_lookup_isolation",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode",
                         "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [0, 0], "webhookId": "zzprobenamelk1"},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": TABLE_MODE, "value": TABLE_VALUE},
                         "returnAll": True, "matchType": "anyCondition",
                         "filters": {"conditions": []}, "options": {}},
         "id": "get_all", "name": "Get All", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [200, 0], "alwaysOutputData": True},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [400, 0]},
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Get All", "type": "main", "index": 0}]]},
        "Get All": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    },
    "settings": {},
}

print(f"Testing dataTableId mode={TABLE_MODE!r} value={TABLE_VALUE!r}")
created = n8n("/api/v1/workflows", "POST",
              {"name": wf_json["name"], "nodes": wf_json["nodes"],
               "connections": wf_json["connections"], "settings": wf_json["settings"]})
wid = created["id"]
print(f"created id={wid}")

try:
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    live = n8n(f"/api/v1/workflows/{wid}")
    if live.get("active") is not True:
        print("activation failed")
        sys.exit(1)
    time.sleep(2)
    webhook_url = BASE + "/webhook/" + WEBHOOK_PATH
    req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    print(f"HTTP {status}, body ({len(raw)} bytes): {raw[:1500]!r}")
finally:
    exres = n8n(f"/api/v1/executions?workflowId={wid}&limit=1&includeData=true")
    for ex in exres.get("data", []):
        rd = ex.get("resultData", {})
        err = rd.get("error")
        if err:
            print("EXECUTION ERROR:", err.get("message"))
    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print(f"deleted workflow {wid}")
