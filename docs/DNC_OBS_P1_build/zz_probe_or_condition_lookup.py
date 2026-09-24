#!/usr/bin/env python3
"""Verify a single dataTable get with matchType=anyCondition and TWO conditions on DIFFERENT
columns (linkedin_url_norm OR email_lc) correctly matches Dennis via the email side, per item,
before rebuilding the gate around this simpler single-lookup shape."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-or-lookup", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-600, 300], "webhookId": "zzprobeorlookup01"},
    {"parameters": {"jsCode": (
        "return [\n"
        "  { json: { label: 'dennis', li_key: '__DNC_NO_LI__', em_key: 'pii-d50f3785@example.invalid' } },\n"
        "  { json: { label: 'clean', li_key: '__DNC_NO_LI__', em_key: 'or-lookup-clean-probe@example.invalid' } },\n"
        "];\n"
    ), "mode": "runOnceForAllItems"},
     "id": "build2", "name": "Build 2 Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-400, 300]},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "matchType": "anyCondition",
                     "filters": {"conditions": [
                         {"keyName": "linkedin_url_norm", "condition": "eq", "keyValue": "={{ $json.li_key }}"},
                         {"keyName": "email_lc", "condition": "eq", "keyValue": "={{ $json.em_key }}"},
                     ]}, "options": {}},
     "id": "lookup", "name": "OR Lookup", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "return [{ json: { output_count: $input.all().length,\n"
        "  outputs: $input.all().map(i => ({ email_lc: i.json.email_lc, identity_key: i.json.identity_key,\n"
        "    entry_type: i.json.entry_type })) } }];\n"
    ), "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [200, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Build 2 Items", "type": "main", "index": 0}]]},
    "Build 2 Items": {"main": [[{"node": "OR Lookup", "type": "main", "index": 0}]]},
    "OR Lookup": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_or_condition_lookup", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-or-lookup",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print(json.dumps(json.loads(r.read()), indent=2))
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
