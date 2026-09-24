#!/usr/bin/env python3
"""What IS the 24,201-row employee_connection/manual_offboard_eligible bucket? Sample real rows,
check correlation_id/source/source_ref/added_at/pipedrive_person_id patterns before classifying
anything. Read-only."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-offboard-investigate", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobeoffboardinv01"},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "identity_key", "condition": "isNotEmpty"}]},
                     "options": {}},
     "id": "get_all", "name": "Get All", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "const rows = $input.all().map(i => i.json);\n"
        "const active = rows.filter(r => r.status === 'active');\n"
        "const target = active.filter(r => r.entry_type === 'employee_connection' && r.reason === 'manual_offboard_eligible');\n"
        "const bySource = {};\n"
        "const byCorrPrefix = {};\n"
        "const byAddedDate = {};\n"
        "let withPid = 0, withoutPid = 0;\n"
        "for (const r of target) {\n"
        "  const s = r.source || '(none)';\n"
        "  bySource[s] = (bySource[s] || 0) + 1;\n"
        "  const cp = String(r.correlation_id || '').split(':')[0] || '(none)';\n"
        "  byCorrPrefix[cp] = (byCorrPrefix[cp] || 0) + 1;\n"
        "  const d = String(r.added_at || '').slice(0, 10);\n"
        "  byAddedDate[d] = (byAddedDate[d] || 0) + 1;\n"
        "  if (r.pipedrive_person_id != null) withPid++; else withoutPid++;\n"
        "}\n"
        "return [{ json: {\n"
        "  total: target.length, with_pid: withPid, without_pid: withoutPid,\n"
        "  by_source: Object.entries(bySource).sort((a,b)=>b[1]-a[1]).slice(0, 20),\n"
        "  by_correlation_prefix: Object.entries(byCorrPrefix).sort((a,b)=>b[1]-a[1]),\n"
        "  by_added_date: Object.entries(byAddedDate).sort((a,b)=>b[1]-a[1]).slice(0, 20),\n"
        "  sample: target.slice(0, 10).map(r => ({ id: r.id, identity_key: r.identity_key, full_name: r.full_name,\n"
        "    source: r.source, source_ref: r.source_ref, correlation_id: r.correlation_id,\n"
        "    pipedrive_person_id: r.pipedrive_person_id, added_at: r.added_at, also_flagged: r.also_flagged,\n"
        "    owner_tag: r.owner_tag, date_precision: r.date_precision })),\n"
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
wf_json = {"name": "zz_probe_offboard_eligible_investigate", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-offboard-investigate",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        with open(os.path.join(HERE, "fixtures", "offboard_eligible_investigate.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        print(json.dumps(result, indent=2)[:5000])
        print("wrote fixtures/offboard_eligible_investigate.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
