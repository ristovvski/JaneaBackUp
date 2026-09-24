#!/usr/bin/env python3
"""READ-ONLY: full export (every column) of the exact 7,450 rows that will be deleted --
status='removed' AND removed_reason='rule_change_2026-08-26_melisa' AND id in the confirmed
still-tombstoned subset of the original 7,486 (the 36 reactivated ones are correctly excluded --
they are no longer tombstones, they're active rows now). Writes to audit-artifacts/ before any
delete -- this IS the history once the rows are gone."""
import csv, json, os, ssl, time, urllib.request

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
AUDIT_DIR = os.path.join(os.path.dirname(HERE), "audit-artifacts")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-export-target-rows", "responseMode": "lastNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-400, 300], "webhookId": "zzexporttargetrows01"},
    {"parameters": {"resource": "row", "operation": "get",
                     "dataTableId": {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"},
                     "returnAll": True, "matchType": "allConditions",
                     "filters": {"conditions": [
                         {"keyName": "status", "condition": "eq", "keyValue": "removed"},
                         {"keyName": "removed_reason", "condition": "eq", "keyValue": "rule_change_2026-08-26_melisa"},
                     ]},
                     "options": {}},
     "id": "get_target", "name": "Get Target", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    # responseMode:lastNode does NOT serialize a multi-item upstream node as a clean JSON array --
    # found live (returned a single flat object / mixed-up fragments instead of all 7,450 rows).
    # Collapse explicitly into ONE item's json field before responding, the same proven pattern
    # used successfully everywhere else this session.
    {"parameters": {"jsCode": "return [{ json: { rows: $input.all().map(i => i.json) } }];",
                     "mode": "runOnceForAllItems"},
     "id": "collapse", "name": "Collapse", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Get Target", "type": "main", "index": 0}]]},
    "Get Target": {"main": [[{"node": "Collapse", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_export_target_rows", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-export-target-rows",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
            rows = json.loads(r.read())["rows"]
        print("rows returned:", len(rows))

        os.makedirs(AUDIT_DIR, exist_ok=True)
        csv_path = os.path.join(AUDIT_DIR, "dnc_registry_tombstones_2026-08-26_melisa_EXPORT_2026-09-09.csv")
        json_path = os.path.join(AUDIT_DIR, "dnc_registry_tombstones_2026-08-26_melisa_EXPORT_2026-09-09.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)
        if rows:
            fieldnames = sorted({k for r in rows for k in r.keys()})
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                for r in rows:
                    w.writerow(r)
        print("wrote", csv_path)
        print("wrote", json_path)

        ids = sorted(r["id"] for r in rows)
        with open(os.path.join(HERE, "delete_target_ids.json"), "w", encoding="utf-8") as f:
            json.dump(ids, f)
        print("delete target ids:", len(ids), "-> saved delete_target_ids.json")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print("cleaned up", wid)


if __name__ == "__main__":
    main()
