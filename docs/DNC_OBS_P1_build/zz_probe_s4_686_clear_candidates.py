#!/usr/bin/env python3
"""Which persons need field-686 cleared after S4 removal: pipedrive_person_id is set on the
pure-S4 row AND that person has NO OTHER active registry row remaining. Read-only."""
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
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-s4-686-clear", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzprobes4686clear01"},
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
        "const pureS4WithPid = pureS4.filter(r => r.pipedrive_person_id != null);\n"
        "// for each such pid, does the person have any OTHER active row that would survive removal?\n"
        "const byPid = {};\n"
        "for (const r of active) {\n"
        "  if (r.pipedrive_person_id == null) continue;\n"
        "  (byPid[r.pipedrive_person_id] = byPid[r.pipedrive_person_id] || []).push(r);\n"
        "}\n"
        "const clearCandidates = [];\n"
        "const keepPopulated = [];\n"
        "const seenPid = new Set();\n"
        "for (const r of pureS4WithPid) {\n"
        "  const pid = r.pipedrive_person_id;\n"
        "  if (seenPid.has(pid)) continue;\n"
        "  seenPid.add(pid);\n"
        "  const rowsForPid = byPid[pid] || [];\n"
        "  const survivingRows = rowsForPid.filter(x => !(reasonList(x).length === 1 && reasonList(x)[0] === 'event_contacted'));\n"
        "  if (survivingRows.length === 0) {\n"
        "    clearCandidates.push({ pipedrive_person_id: pid, identity_key: r.identity_key, full_name: r.full_name });\n"
        "  } else {\n"
        "    keepPopulated.push({ pipedrive_person_id: pid, surviving_entry_types: survivingRows.map(x => x.entry_type) });\n"
        "  }\n"
        "}\n"
        "return [{ json: {\n"
        "  pure_s4_with_pid_count: pureS4WithPid.length,\n"
        "  distinct_pids_touched: seenPid.size,\n"
        "  clear_686_count: clearCandidates.length,\n"
        "  keep_686_populated_count: keepPopulated.length,\n"
        "  clear_686_sample: clearCandidates.slice(0, 8),\n"
        "  keep_686_sample: keepPopulated.slice(0, 5),\n"
        "  clear_686_all_pids: clearCandidates.map(c => c.pipedrive_person_id),\n"
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
wf_json = {"name": "zz_probe_s4_686_clear", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-s4-686-clear",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            result = json.loads(r.read())
        with open(os.path.join(HERE, "fixtures", "s4_686_clear_candidates.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        summary = {k: v for k, v in result.items() if k != "clear_686_all_pids"}
        print(json.dumps(summary, indent=2)[:3000])
        print("wrote fixtures/s4_686_clear_candidates.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
