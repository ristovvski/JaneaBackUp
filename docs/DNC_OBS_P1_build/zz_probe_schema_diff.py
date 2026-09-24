#!/usr/bin/env python3
"""Direct schema-diff probe: one Data Table Update node attempting to set ALL 23 expected columns
at once (against a non-matching filter, so nothing is actually written) -- purely to see which
column names n8n's validation rejects. Iterates: on 'unknown column name X', drop X, retry, until
either success (no more unknown-column errors) or no more progress. Reports the full missing list
in one pass instead of one-at-a-time trial and error. Read-only in effect: no row ever matches the
filter (identity_key = a value that can't exist), so nothing is written even on success."""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"
WEBHOOK_PATH = "zz-probe-schema-diff"

EXPECTED_COLUMNS = {
    "identity_key": "string", "linkedin_url_norm": "string", "email_lc": "string",
    "full_name": "string", "pipedrive_person_id": 1, "entry_type": "string", "source": "string",
    "owner_tag": "string", "reply_category": "string", "status": "string",
    "added_at": "2026-01-01T00:00:00.000Z", "expires_at": "2026-01-01T00:00:00.000Z",
    "removed_at": "2026-01-01T00:00:00.000Z", "removed_reason": "string",
    "correlation_id": "string", "norm_v": "string", "reason": "string", "source_ref": "string",
    "also_flagged": "string", "date_precision": "string", "offboard_removable": True,
    "expiry_review_pending": True, "projections_state": "string",
}


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
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x)


def build_wf(columns_to_test):
    value_map = {c: EXPECTED_COLUMNS[c] for c in columns_to_test}
    return {
        "name": "zz_probe_schema_diff",
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
             "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": "zzprobeschemadiff1"},
            {"parameters": {
                "resource": "row", "operation": "update",
                "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
                "matchType": "allConditions",
                "filters": {"conditions": [{"keyName": "identity_key", "condition": "eq",
                                             "keyValue": "zz_probe_this_never_matches_any_row"}]},
                "columns": {"mappingMode": "defineBelow", "value": value_map, "matchingColumns": [], "schema": []},
                "options": {}},
             "id": "update_probe", "name": "Update Probe", "type": "n8n-nodes-base.dataTable",
             "typeVersion": 1, "position": [200, 0]},
            {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
             "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [400, 0]},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Update Probe", "type": "main", "index": 0}]]},
            "Update Probe": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }


def run_once(columns_to_test):
    wf = build_wf(columns_to_test)
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": wf["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    webhook_url = BASE + "/webhook/" + WEBHOOK_PATH
    req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx):
            pass
    except urllib.error.HTTPError:
        pass

    # Always check execution status directly -- a 200 with an empty body does NOT mean success
    # (respondToWebhook never fires if an upstream node errored; the webhook call itself still
    # returns 200 in that case). Give indexing generous time; do NOT delete until resolved --
    # deleting a workflow before its execution is queryable destroys the evidence (learned the
    # hard way earlier this session).
    error_msg = None
    status = None
    for _ in range(15):
        time.sleep(2)
        exres = n8n(f"/api/v1/executions?workflowId={wid}&limit=1&includeData=true")
        rows = exres.get("data", [])
        if rows and rows[0].get("status") in ("success", "error", "crashed"):
            status = rows[0].get("status")
            err = rows[0].get("resultData", {}).get("error")
            if err:
                error_msg = err.get("message") or (err.get("errorResponse") or {}).get("message")
            break

    if status is None:
        print(f"  WARNING: execution status never resolved for workflow {wid} -- leaving it "
              f"undeleted for manual inspection.")
        return None, None, wid

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    return (status == "success"), error_msg, None


def main():
    remaining = list(EXPECTED_COLUMNS.keys())
    missing = []
    mistyped_or_other = []
    for attempt in range(30):
        print(f"\n--- attempt {attempt+1}: testing {len(remaining)} columns ---")
        success, err, undeleted_wid = run_once(remaining)
        if undeleted_wid:
            print(f"stopping -- workflow {undeleted_wid} needs manual cleanup after inspection")
            break
        if success:
            print("SUCCESS -- all remaining columns accepted by n8n's validation.")
            break
        print("error:", err)
        m = None
        if err and "unknown column name" in err:
            import re
            match = re.search(r"unknown column name '([^']+)'", err)
            if match:
                m = match.group(1)
        if m and m in remaining:
            print(f"  -> confirmed missing: {m}")
            missing.append(m)
            remaining.remove(m)
        else:
            print(f"  -> unrecognized error shape, stopping iteration here: {err}")
            mistyped_or_other.append(err)
            break
    else:
        print("hit attempt cap without resolving")

    print("\n=== SCHEMA DIFF RESULT ===")
    print("confirmed MISSING columns:", missing)
    print("columns that validated OK:", remaining)
    if mistyped_or_other:
        print("other/unresolved errors:", mistyped_or_other)


if __name__ == "__main__":
    main()
