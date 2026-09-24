#!/usr/bin/env python3
"""OWNER_TAG GAP census: count registry rows with empty owner_tag, split by entry_type/reason.
Read-only. Also samples a few rows per bucket for the backfill-source design."""
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
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-owner-tag-census", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobeownertag01"},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "identity_key", "condition": "isNotEmpty"}]},
                     "options": {}},
     "id": "get_all", "name": "Get All", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "const rows = $input.all().map(i => i.json);\n"
        "const active = rows.filter(r => r.status === 'active');\n"
        "const empty = active.filter(r => !r.owner_tag || String(r.owner_tag).trim() === '');\n"
        "const filled = active.filter(r => r.owner_tag && String(r.owner_tag).trim() !== '');\n"
        "const byType = {};\n"
        "for (const r of empty) {\n"
        "  const key = (r.entry_type || 'null') + ' / ' + (r.source || 'null');\n"
        "  (byType[key] = byType[key] || []).push(r);\n"
        "}\n"
        "const summary = Object.entries(byType).map(([k, list]) => ({ key: k, count: list.length,\n"
        "  sample: list.slice(0, 3).map(r => ({ id: r.id, identity_key: r.identity_key,\n"
        "    full_name: r.full_name, pipedrive_person_id: r.pipedrive_person_id,\n"
        "    correlation_id: r.correlation_id, source_ref: r.source_ref, added_at: r.added_at })) }))\n"
        "  .sort((a, b) => b.count - a.count);\n"
        "// employee_connection specifically -- expected to be populated already, verify\n"
        "const empConn = active.filter(r => r.entry_type === 'employee_connection');\n"
        "const empConnEmpty = empConn.filter(r => !r.owner_tag || String(r.owner_tag).trim() === '');\n"
        "return [{ json: {\n"
        "  total_active: active.length, total_empty_owner_tag: empty.length, total_filled: filled.length,\n"
        "  by_entry_type_and_reason: summary,\n"
        "  employee_connection_total: empConn.length, employee_connection_empty: empConnEmpty.length,\n"
        "} }];\n"
    ), "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [200, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Get All", "type": "main", "index": 0}]]},
    "Get All": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_owner_tag_census", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-owner-tag-census",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        print(json.dumps(result, indent=2)[:6000])
        with open(os.path.join(HERE, "fixtures", "owner_tag_census.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("wrote fixtures/owner_tag_census.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
