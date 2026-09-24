#!/usr/bin/env python3
"""Robust iterative schema-diff probe (v2 -- fixes the premature-delete race in v1).
Never deletes a probe workflow until its execution status has actually resolved to
success/error/crashed via polling. One Data Table Update per round, testing all still-unconfirmed
columns at once; drops whichever single column n8n's fail-fast validator names, repeats."""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
TABLE_ID = "UOgKwlGsL28lX61O"

ALL_VALS = {
    "identity_key": "x", "linkedin_url_norm": "x", "email_lc": "x", "full_name": "x",
    "pipedrive_person_id": 1, "entry_type": "x", "source": "x", "owner_tag": "x",
    "reply_category": "x", "status": "x", "added_at": "2026-01-01T00:00:00.000Z",
    "expires_at": "2026-01-01T00:00:00.000Z", "removed_at": "2026-01-01T00:00:00.000Z",
    "removed_reason": "x", "correlation_id": "x", "norm_v": "x", "reason": "x",
    "source_ref": "x", "also_flagged": "x", "date_precision": "x",
    "offboard_removable": True, "expiry_review_pending": True, "projections_state": "x",
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
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x)


def probe_round(vals, tag):
    webhook_path = "zz-probe-diff-" + tag
    wf = {
        "name": "zz_probe_diff_" + tag,
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": webhook_path, "responseMode": "responseNode", "options": {}},
             "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": "zzprobediff" + tag},
            {"parameters": {"resource": "row", "operation": "update",
                             "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
                             "matchType": "allConditions",
                             "filters": {"conditions": [{"keyName": "expires_at", "condition": "eq",
                                                          "keyValue": "2099-01-01T00:00:00.000Z"}]},
                             "columns": {"mappingMode": "defineBelow", "value": vals, "matchingColumns": [], "schema": []},
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
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": wf["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)
    req = urllib.request.Request(BASE + "/webhook/" + webhook_path, method="POST", data=b"{}",
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30, context=ctx)
    except urllib.error.HTTPError:
        pass

    status, msg = None, None
    for _ in range(20):
        time.sleep(2)
        exres = n8n(f"/api/v1/executions?workflowId={wid}&limit=1&includeData=true")
        rows = exres.get("data", [])
        if rows and rows[0].get("status") in ("success", "error", "crashed"):
            status = rows[0]["status"]
            err = rows[0].get("data", {}).get("resultData", {}).get("error")
            msg = err.get("message") if err else None
            if status == "success" or msg:
                break
            # status resolved to error/crashed but the error body hasn't landed yet -- keep polling
            status, msg = None, None

    if status is None:
        print(f"  UNRESOLVED after 40s -- leaving workflow {wid} for manual cleanup")
        return None, wid

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    return (status, msg), None


def main():
    remaining = dict(ALL_VALS)
    confirmed_missing = []
    for i in range(30):
        print(f"\n--- round {i+1}: testing {len(remaining)} columns: {sorted(remaining.keys())} ---")
        result, unresolved_wid = probe_round(remaining, f"r{i}")
        if unresolved_wid:
            print("STOPPING -- manual cleanup needed for", unresolved_wid)
            sys.exit(2)
        status, msg = result
        print(f"  status={status!r} msg={msg!r}")
        if status == "success":
            print("ALL REMAINING COLUMNS VALID.")
            break
        import re
        m = None
        if msg:
            m = re.search(r"unknown column name '([^']+)'", msg) or \
                re.search(r'Column\(s\) "([^"]+)" do not exist', msg)
        if not m:
            print(f"UNEXPECTED (non-column) error, stopping here to avoid misreporting: {msg}")
            break
        if m.group(1) not in remaining:
            print(f"could not parse a known column out of: {msg}")
            break
        col = m.group(1)
        print(f"  CONFIRMED MISSING: {col}")
        confirmed_missing.append(col)
        del remaining[col]
    else:
        print("hit round cap")

    print("\n=== FINAL RESULT ===")
    print("Confirmed MISSING columns:", confirmed_missing)
    print("Confirmed PRESENT (validated) columns:", sorted(remaining.keys()))


if __name__ == "__main__":
    main()
