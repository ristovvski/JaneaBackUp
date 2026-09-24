#!/usr/bin/env python3
"""Partition the 8775 empty-owner_tag rows by ACTUAL backfill source, not entry_type/reason:
(a) correlation_id starts with s4_event_populations: -> derive from campaign sender
(b) has pipedrive_person_id -> derive from Pipedrive current owner
(c) neither -> leave empty, count honestly
Read-only. Also extracts the distinct S4 campaign_ids referenced, for the sender-lookup step."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-owner-tag-partition", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobeownerpart01"},
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
        "const isS4 = (r) => String(r.correlation_id || '').startsWith('s4_event_populations:');\n"
        "const sourceA = empty.filter(isS4);\n"
        "const sourceB = empty.filter(r => !isS4(r) && r.pipedrive_person_id != null);\n"
        "const sourceC = empty.filter(r => !isS4(r) && r.pipedrive_person_id == null);\n"
        "const campaignIds = {};\n"
        "for (const r of sourceA) {\n"
        "  const parts = String(r.correlation_id).split(':'); // s4_event_populations:smartlead:<id>\n"
        "  const provider = parts[1], cid = parts[2];\n"
        "  if (!cid) continue;\n"
        "  const key = provider + ':' + cid;\n"
        "  campaignIds[key] = (campaignIds[key] || 0) + 1;\n"
        "}\n"
        "return [{ json: {\n"
        "  total_empty: empty.length,\n"
        "  source_a_s4_count: sourceA.length,\n"
        "  source_b_has_pid_count: sourceB.length,\n"
        "  source_c_neither_count: sourceC.length,\n"
        "  distinct_s4_campaigns: Object.entries(campaignIds).sort((a,b) => b[1]-a[1]),\n"
        "  source_c_sample: sourceC.slice(0, 10).map(r => ({ id: r.id, identity_key: r.identity_key,\n"
        "    entry_type: r.entry_type, source: r.source, correlation_id: r.correlation_id })),\n"
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
wf_json = {"name": "zz_probe_owner_tag_partition", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-owner-tag-partition",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        with open(os.path.join(HERE, "fixtures", "owner_tag_partition.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(json.dumps({k: v for k, v in result.items() if k != 'distinct_s4_campaigns'}, indent=2))
        print("distinct S4 campaigns:", len(result.get("distinct_s4_campaigns", [])))
        for c, n in result.get("distinct_s4_campaigns", []):
            print(" ", c, n)
        print("wrote fixtures/owner_tag_partition.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
