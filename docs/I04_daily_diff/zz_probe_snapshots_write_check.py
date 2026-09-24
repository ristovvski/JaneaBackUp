#!/usr/bin/env python3
"""Clean write+readback+cleanup test against i04_snapshots via mode:"name" -- same rigor as the
i04_log investigation, before trusting it for the real staged weekly-walk test. Also re-checks
i04_walk_staging's earlier ambiguous "error" execution status."""
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


TABLE = {"__rl": True, "mode": "name", "value": "i04_snapshots"}
nodes = [
    {"parameters": {"httpMethod": "POST", "path": "zz-probe-snapshots-check", "responseMode": "responseNode", "options": {}},
     "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
     "position": [-600, 300], "webhookId": "zzprobesnapshotschk01"},
    {"parameters": {"resource": "row", "operation": "upsert", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "=_zzprobe_write_check"}]},
                     "columns": {"mappingMode": "defineBelow", "value": {
                         "date": "=_zzprobe_write_check", "captured_at": "=2026-08-26T07:20:00.000Z",
                         "source": "=probe", "counts_json": "={}", "leads_json": "={}",
                         "persons_json": "={}", "dnc_labelled_json": "=[]", "kept_reason": "=probe",
                     }, "matchingColumns": ["date"], "schema": []}, "options": {}},
     "id": "insert", "name": "Insert", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-400, 300]},
    {"parameters": {"resource": "row", "operation": "get", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "=_zzprobe_write_check"}]},
                     "options": {}},
     "id": "readback", "name": "Readback", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-200, 300]},
    {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": TABLE,
                     "matchType": "allConditions",
                     "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "=_zzprobe_write_check"}]},
                     "options": {}},
     "id": "cleanup", "name": "Cleanup", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [0, 300]},
    {"parameters": {"jsCode": "return [{ json: $('Readback').first().json }];", "mode": "runOnceForAllItems"},
     "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 300]},
    {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [400, 300]},
]
connections = {
    "Webhook": {"main": [[{"node": "Insert", "type": "main", "index": 0}]]},
    "Insert": {"main": [[{"node": "Readback", "type": "main", "index": 0}]]},
    "Readback": {"main": [[{"node": "Cleanup", "type": "main", "index": 0}]]},
    "Cleanup": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
    "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
wf_json = {"name": "zz_probe_snapshots_write_check", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    try:
        req = urllib.request.Request(BASE.replace("/api/v1", "") + "/webhook/zz-probe-snapshots-check",
                                      method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            print("SUCCESS:", json.dumps(json.loads(r.read()), indent=2)[:800])
    except urllib.error.HTTPError as e:
        print("FAILED:", e.code, e.read()[:1000])

    time.sleep(1)
    execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=1")
    for ex in execs.get("data", []):
        eid = ex.get("id")
        print("execution status:", ex.get("status"))
        if ex.get("status") != "success":
            full = n8n(f"/api/v1/executions/{eid}?includeData=true")
            err = (full.get("data", {}).get("resultData") or {}).get("error")
            print("error detail:", json.dumps(err, indent=2)[:1500] if err else "(none at top level)")

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print("cleaned up", wid)


if __name__ == "__main__":
    main()
