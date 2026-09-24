#!/usr/bin/env python3
"""Verify BEFORE shipping: does an n8n dataTable 'get' node, fed N input items each with its own
expression-evaluated keyValue, actually run the lookup once PER ITEM (returning each item's own
correlated result), or does it only evaluate against the first item? This is the one real
platform-behavior assumption the gate v2 redesign depends on -- test with 3 distinct real
identity_keys from dnc_registry_dev (known real values) fed as 3 separate items."""
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


# feed 3 distinct fake email_lc keys (one real-ish miss, two distinct) via a Set-node splitting
# into 3 items, each carrying its own em_key, then a dataTable get by email_lc keyed per item.
nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-dt-multi", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-600, 300], "webhookId": "zzprobedtmulti01"},
    {"parameters": {"jsCode": (
        "return [\n"
        "  { json: { label: 'a', em_key: 'pii-d50f3785@example.invalid' } },\n"
        "  { json: { label: 'b', em_key: 'nonexistent-probe-xyz-123@example.invalid' } },\n"
        "  { json: { label: 'c', em_key: 'pii-d50f3785@example.invalid' } },\n"
        "];\n"
    ), "mode": "runOnceForAllItems"},
     "id": "build3", "name": "Build 3 Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-400, 300]},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "matchType": "anyCondition",
                     "filters": {"conditions": [{"keyName": "email_lc", "condition": "eq", "keyValue": "={{ $json.em_key }}"}]},
                     "options": {}},
     "id": "get3", "name": "Get by Email x3", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "return [{ json: { output_item_count: $input.all().length,\n"
        "  outputs: $input.all().map(i => ({ email_lc: i.json.email_lc, identity_key: i.json.identity_key,\n"
        "    entry_type: i.json.entry_type, error: i.json.error })) } }];\n"
    ), "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [200, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Build 3 Items", "type": "main", "index": 0}]]},
    "Build 3 Items": {"main": [[{"node": "Get by Email x3", "type": "main", "index": 0}]]},
    "Get by Email x3": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_datatable_multi_item", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-dt-multi",
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
