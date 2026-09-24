#!/usr/bin/env python3
"""REGISTRY COMPLIANCE AUDIT vs Melisa's new rule: registry = replied + meetings +
sales-created/Surfe + employee_connections + explicit opt-outs, NOTHING else. Classify every
active row into COMPLIANT / NON-COMPLIANT / UNCLEAR. Read-only. First pass: get the FULL
entry_type x reason distribution so classification is built on real data, not assumption."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-compliance-audit", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobecompliance01"},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "identity_key", "condition": "isNotEmpty"}]},
                     "options": {}},
     "id": "get_all", "name": "Get All", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "const rows = $input.all().map(i => i.json);\n"
        "const active = rows.filter(r => r.status === 'active');\n"
        "const reasonList = (r) => String(r.reason || '').split(',').map(s => s.trim()).filter(Boolean);\n"
        "const dist = {};\n"
        "for (const r of active) {\n"
        "  const key = r.entry_type + ' | ' + reasonList(r).sort().join(',');\n"
        "  (dist[key] = dist[key] || { count: 0, sample: [] }).count++;\n"
        "  if (dist[key].sample.length < 2) dist[key].sample.push({ id: r.id, identity_key: r.identity_key,\n"
        "    full_name: r.full_name, source: r.source, source_ref: r.source_ref, correlation_id: r.correlation_id });\n"
        "}\n"
        "const out = Object.entries(dist).map(([k, v]) => ({ key: k, count: v.count, sample: v.sample }))\n"
        "  .sort((a, b) => b.count - a.count);\n"
        "return [{ json: { total_active: active.length, distinct_combos: out.length, distribution: out } }];\n"
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
wf_json = {"name": "zz_probe_compliance_audit", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-compliance-audit",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        with open(os.path.join(HERE, "fixtures", "compliance_audit_distribution.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        print(f"total_active: {result['total_active']}  distinct_combos: {result['distinct_combos']}")
        for row in result["distribution"]:
            print(f"  {row['count']:6d}  {row['key']}")
        print("wrote fixtures/compliance_audit_distribution.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
