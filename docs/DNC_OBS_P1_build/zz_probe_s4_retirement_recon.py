#!/usr/bin/env python3
"""S4 RETIREMENT recon (Melisa's ruling, Nik confirmed): classify every active registry row by
whether event_contacted is its ONLY active reason (pure S4 -> remove) vs coexists with a
stronger reason (overlap -> keep, demote). Read-only. Builds the artifact for §9f.2."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-s4-retire-recon", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobes4retire01"},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "identity_key", "condition": "isNotEmpty"}]},
                     "options": {}},
     "id": "get_all", "name": "Get All", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"jsCode": (
        "const rows = $input.all().map(i => i.json);\n"
        "const active = rows.filter(r => r.status === 'active');\n"
        "// reason is comma-unioned like source (verified pattern elsewhere in this project) --\n"
        "// split, check membership, don't substring-match (no-substring-blob-checks lesson).\n"
        "const reasonList = (r) => String(r.reason || '').split(',').map(s => s.trim()).filter(Boolean);\n"
        "const hasEC = (r) => reasonList(r).includes('event_contacted');\n"
        "const touched = active.filter(hasEC);\n"
        "const pureS4 = touched.filter(r => reasonList(r).length === 1);\n"
        "const overlap = touched.filter(r => reasonList(r).length > 1);\n"
        "// sanity: what OTHER reasons show up alongside event_contacted in overlap rows?\n"
        "const otherReasonCounts = {};\n"
        "for (const r of overlap) {\n"
        "  for (const rs of reasonList(r)) {\n"
        "    if (rs === 'event_contacted') continue;\n"
        "    otherReasonCounts[rs] = (otherReasonCounts[rs] || 0) + 1;\n"
        "  }\n"
        "}\n"
        "const bySourceRef = {};\n"
        "for (const r of pureS4) {\n"
        "  const k = r.source_ref || '(none)';\n"
        "  bySourceRef[k] = (bySourceRef[k] || 0) + 1;\n"
        "}\n"
        "return [{ json: {\n"
        "  total_active: active.length, touched_by_s4: touched.length,\n"
        "  pure_s4_count: pureS4.length, overlap_count: overlap.length,\n"
        "  other_reasons_in_overlap: Object.entries(otherReasonCounts).sort((a,b)=>b[1]-a[1]),\n"
        "  pure_s4_by_source_ref: Object.entries(bySourceRef).sort((a,b)=>b[1]-a[1]),\n"
        "  pure_s4_sample: pureS4.slice(0, 8).map(r => ({ id: r.id, identity_key: r.identity_key,\n"
        "    full_name: r.full_name, reason: r.reason, source: r.source, source_ref: r.source_ref,\n"
        "    correlation_id: r.correlation_id, also_flagged: r.also_flagged, added_at: r.added_at })),\n"
        "  overlap_sample: overlap.slice(0, 8).map(r => ({ id: r.id, identity_key: r.identity_key,\n"
        "    full_name: r.full_name, entry_type: r.entry_type, reason: r.reason, source: r.source,\n"
        "    also_flagged: r.also_flagged })),\n"
        "  pure_s4_ids: pureS4.map(r => r.id),\n"
        "  overlap_ids: overlap.map(r => r.id),\n"
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
wf_json = {"name": "zz_probe_s4_retirement_recon", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-s4-retire-recon",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        with open(os.path.join(HERE, "fixtures", "s4_retirement_recon.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        summary = {k: v for k, v in result.items() if k not in ("pure_s4_ids", "overlap_ids")}
        print(json.dumps(summary, indent=2)[:6000])
        print("wrote fixtures/s4_retirement_recon.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
