#!/usr/bin/env python3
"""Live function-verify of the 2026-08-11 decide_js fix: a reason-less caller (simulating the
heyreach tee) touching a row that already has reason='manual_offboard_eligible' must NOT wipe
reason/source_ref/owner_tag/also_flagged/offboard_removable/date_precision/expiry_review_pending/
projections_state. Two real UpsertLedger calls (not bypassed), then a read-back, then cleanup.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
UPSERT_LEDGER_ID = "RolYGL3J2CNg6Yp3"
TABLE_ID = "UOgKwlGsL28lX61O"
PROBE_LI_SLUG = "zz-probe-reason-preservation"


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
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
        return json.load(x)


def build_wf(webhook_path, call1_body, call2_body):
    return {
        "name": "zz_probe_reason_preservation",
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": webhook_path, "responseMode": "responseNode",
                             "options": {}},
             "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": webhook_path},
            {"parameters": {"jsCode": f"return [{{ json: {json.dumps(call1_body)} }}];"},
             "id": "build1", "name": "Build Call 1", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [200, 0]},
            {"parameters": {"source": "database",
                             "workflowId": {"__rl": True, "mode": "id", "value": UPSERT_LEDGER_ID},
                             "mode": "once", "options": {}},
             "id": "call1", "name": "Call UpsertLedger 1 (with reason)", "type": "n8n-nodes-base.executeWorkflow",
             "typeVersion": 1.2, "position": [400, 0]},
            {"parameters": {"jsCode": f"return [{{ json: {json.dumps(call2_body)} }}];"},
             "id": "build2", "name": "Build Call 2", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [600, 0]},
            {"parameters": {"source": "database",
                             "workflowId": {"__rl": True, "mode": "id", "value": UPSERT_LEDGER_ID},
                             "mode": "once", "options": {}},
             "id": "call2", "name": "Call UpsertLedger 2 (no reason)", "type": "n8n-nodes-base.executeWorkflow",
             "typeVersion": 1.2, "position": [800, 0]},
            {"parameters": {"resource": "row", "operation": "get",
                             "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
                             "matchType": "allConditions",
                             "filters": {"conditions": [{"keyName": "identity_key", "condition": "eq",
                                                          "keyValue": PROBE_LI_SLUG}]},
                             "options": {}},
             "id": "readback", "name": "Read Back", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
             "position": [1000, 0]},
            {"parameters": {"resource": "row", "operation": "deleteRows",
                             "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
                             "matchType": "allConditions",
                             "filters": {"conditions": [{"keyName": "identity_key", "condition": "eq",
                                                          "keyValue": PROBE_LI_SLUG}]},
                             "options": {}},
             "id": "cleanup", "name": "Cleanup", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
             "position": [1200, 0]},
            {"parameters": {"jsCode": "return [{ json: $('Read Back').first().json }];"},
             "id": "keep", "name": "Keep Readback Payload", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [1400, 0]},
            {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
             "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [1600, 0]},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Build Call 1", "type": "main", "index": 0}]]},
            "Build Call 1": {"main": [[{"node": "Call UpsertLedger 1 (with reason)", "type": "main", "index": 0}]]},
            "Call UpsertLedger 1 (with reason)": {"main": [[{"node": "Build Call 2", "type": "main", "index": 0}]]},
            "Build Call 2": {"main": [[{"node": "Call UpsertLedger 2 (no reason)", "type": "main", "index": 0}]]},
            "Call UpsertLedger 2 (no reason)": {"main": [[{"node": "Read Back", "type": "main", "index": 0}]]},
            "Read Back": {"main": [[{"node": "Cleanup", "type": "main", "index": 0}]]},
            "Cleanup": {"main": [[{"node": "Keep Readback Payload", "type": "main", "index": 0}]]},
            "Keep Readback Payload": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }


def main():
    call1 = {
        "linkedin_url": f"https://www.linkedin.com/in/{PROBE_LI_SLUG}",
        "email": None, "full_name": "ZZ Probe Reason Preservation",
        "reason": "manual_offboard_eligible", "source": None, "source_ref": "zz_probe_owner",
        "date_precision": "unknown", "expiry_review_pending": False,
        "correlation_id": "zz_probe_reason_preservation:call1",
    }
    # simulates a reason-less caller (heyreach tee): entry_type-only, no reason/source_ref at all
    call2 = {
        "linkedin_url": f"https://www.linkedin.com/in/{PROBE_LI_SLUG}",
        "email": None, "full_name": "ZZ Probe Reason Preservation",
        "entry_type": "employee_connection", "source": "heyreach_reply",
        "correlation_id": "zz_probe_reason_preservation:call2",
    }
    webhook_path = "zz-probe-reason-preservation"
    wf = build_wf(webhook_path, call1, call2)
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                   "settings": wf["settings"]})
    wid = created["id"]
    print(f"created probe workflow {wid}")
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)

    req = urllib.request.Request(BASE + "/webhook/" + webhook_path, method="POST", data=b"{}",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        print("HTTP ERROR", e.code, raw[:1500])
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        print(f"workflow {wid} left for diagnosis -- NOT cleaning up probe row either")
        sys.exit(2)

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print(f"cleaned up probe workflow {wid}")

    row = json.loads(raw)
    print("\nrow AFTER call2 (reason-less):")
    print(json.dumps(row, indent=2))

    checks = [
        ("reason preserved", row.get("reason") == "manual_offboard_eligible"),
        ("source_ref preserved", row.get("source_ref") == "zz_probe_owner"),
        ("owner_tag preserved", row.get("owner_tag") == "zz_probe_owner"),
        ("offboard_removable preserved", row.get("offboard_removable") is True),
        ("date_precision preserved", row.get("date_precision") == "unknown"),
        ("expiry_review_pending preserved", row.get("expiry_review_pending") is False),
        ("projections_state preserved across the update (not reset to null)",
         (json.loads(row["projections_state"]) if row.get("projections_state") else None)
         == {"pipedrive": "pending", "smartlead": "pending", "heyreach": "pending"}),
        ("source appended (call1 + call2)", row.get("source") == "heyreach_reply"),
        ("entry_type stayed employee_connection (never downgraded)", row.get("entry_type") == "employee_connection"),
    ]
    print("\n=== CHECKS ===")
    all_ok = True
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_ok = all_ok and ok
    print(f"\nOVERALL: {'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
