#!/usr/bin/env python3
"""Throwaway probe: fresh live counts + a handful of real rows from the two n8n Data Tables that
Phase 2's initial load will read FROM (dnc_registry_dev, dnc_domains) -- for the §9f.2 pre-post
artifact. Read-only (dataTable "get", never write). Deploys, fires, deletes."""
import json
import os
import ssl
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

REGISTRY_TABLE = "UOgKwlGsL28lX61O"
DOMAINS_TABLE = "ai4ZiOGqzuJHRYLB"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def build():
    report_js = (
        "const reg = $('Get Registry').all().map(i => i.json);\n"
        "const dom = $('Get Domains').all().map(i => i.json);\n"
        "const active = reg.filter(r => r.status === 'active');\n"
        "const removed = reg.filter(r => r.status === 'removed');\n"
        "return [{ json: {\n"
        "  registry_total: reg.length, registry_active: active.length, registry_removed: removed.length,\n"
        "  registry_examples: reg.slice(0, 5),\n"
        "  domains_total: dom.length, domains_examples: dom.slice(0, 5),\n"
        "} }];\n"
    )
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": "probe-source-counts",
                         "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-600, 300], "webhookId": "probesourcecounts01"},
        {"parameters": {"resource": "row", "operation": "get", "dataTableId": {"__rl": True, "mode": "id", "value": REGISTRY_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_registry", "name": "Get Registry", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 200], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"resource": "row", "operation": "get", "dataTableId": {"__rl": True, "mode": "id", "value": DOMAINS_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_domains", "name": "Get Domains", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 400], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"jsCode": report_js, "mode": "runOnceForAllItems"},
         "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [-200, 300]},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Get Registry", "type": "main", "index": 0},
                               {"node": "Get Domains", "type": "main", "index": 0}]]},
        "Get Registry": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
        "Get Domains": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
        "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return {"name": "ZZ_PROBE_source_counts_DELETE_ME", "nodes": nodes,
            "connections": connections, "settings": {}}


def fire(path):
    url = BASE.replace("/api/v1", "") + "/webhook/" + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (raw.decode() if raw else None)


def main():
    wf_json = build()
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    print(f"deployed probe workflow id={wid}")
    time.sleep(1)
    try:
        status, body = fire("probe-source-counts")
        print(f"HTTP {status}")
        with open(os.path.join(HERE, "source_counts_probe.json"), "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
        print("wrote source_counts_probe.json")
        if isinstance(body, dict):
            print("registry_total:", body.get("registry_total"), "active:", body.get("registry_active"),
                  "removed:", body.get("registry_removed"))
            print("domains_total:", body.get("domains_total"))
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"probe workflow {wid} deactivated + deleted.")


if __name__ == "__main__":
    main()
