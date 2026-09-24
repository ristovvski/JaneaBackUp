#!/usr/bin/env python3
"""Check what's actually inside also_flagged across all 7138 pure-S4 (reason=event_contacted)
rows -- need to know if any of them carry a genuinely STRONGER prior signal (a real reply/
meeting/creation basis, matching the entry_type strength tiers) vs just other weak manual-tier
noise, before classifying which rows are safe to fully tombstone vs must be kept+demoted (the
'Lucas pattern' -- never erase a real reply signal). Read-only."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-s4-also-flagged", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobes4alsoflag01"},
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
        "const pureS4 = active.filter(r => reasonList(r).length === 1 && reasonList(r)[0] === 'event_contacted');\n"
        "// STRENGTH tiers as used elsewhere in this project's merge logic -- a real protective\n"
        "// signal, not just another manual-tier import label.\n"
        "const PROTECTIVE_REASONS = new Set([\n"
        "  'pipedrive_responded_label', 'meeting_sweep', 'pipedrive_surfe', 'pipedrive_personal',\n"
        "  'sales_personal_outreach', 'smartlead_category',\n"
        "]);\n"
        "const withFlags = pureS4.filter(r => {\n"
        "  try { const af = JSON.parse(r.also_flagged || '[]'); return Array.isArray(af) && af.length > 0; }\n"
        "  catch (e) { return false; }\n"
        "});\n"
        "const reasonCounts = {};\n"
        "const protectiveHits = [];\n"
        "for (const r of withFlags) {\n"
        "  let af = [];\n"
        "  try { af = JSON.parse(r.also_flagged || '[]'); } catch (e) {}\n"
        "  for (const entry of af) {\n"
        "    const rs = entry.reason || '(none)';\n"
        "    reasonCounts[rs] = (reasonCounts[rs] || 0) + 1;\n"
        "    if (PROTECTIVE_REASONS.has(rs)) {\n"
        "      protectiveHits.push({ id: r.id, identity_key: r.identity_key, full_name: r.full_name,\n"
        "        also_flagged: af, source_ref: r.source_ref });\n"
        "    }\n"
        "  }\n"
        "}\n"
        "return [{ json: {\n"
        "  pure_s4_total: pureS4.length,\n"
        "  pure_s4_with_also_flagged: withFlags.length,\n"
        "  also_flagged_reason_distribution: Object.entries(reasonCounts).sort((a,b) => b[1]-a[1]),\n"
        "  protective_hits_count: protectiveHits.length,\n"
        "  protective_hits_sample: protectiveHits.slice(0, 10),\n"
        "  protective_hits_all_ids: protectiveHits.map(h => h.id),\n"
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
wf_json = {"name": "zz_probe_s4_also_flagged", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-s4-also-flagged",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        with open(os.path.join(HERE, "fixtures", "s4_also_flagged_check.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        summary = {k: v for k, v in result.items() if k != "protective_hits_all_ids"}
        print(json.dumps(summary, indent=2)[:4000])
        print("wrote fixtures/s4_also_flagged_check.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
