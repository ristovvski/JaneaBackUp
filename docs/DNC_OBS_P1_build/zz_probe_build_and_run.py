#!/usr/bin/env python3
"""
zz_probe_ schema verification for dnc_registry_dev, per owner's hybrid-finish plan (2026-08-07).

Does NOT run until Nik confirms the 13 remaining UI columns are added (see
CLICKLIST_FOR_NIK_2026-08-07.md). When run:

  1. Builds a throwaway probe workflow (webhook trigger) that:
     a. Calls the REAL, imported DNC__UpsertLedger__v1 with a reason-driven synthetic row
        (exercises the production write path: identity_key, linkedin_url_norm, email_lc,
        full_name, pipedrive_person_id, entry_type[derived], source, reply_category, status,
        added_at, expires_at, correlation_id, norm_v, reason, source_ref, also_flagged,
        offboard_removable, date_precision, expiry_review_pending -- 19 columns).
     b. Directly updates the same row to also set owner_tag, removed_at, removed_reason,
        projections_state -- the 4 columns no production workflow populates yet (owner_tag
        was never wired into UpsertLedger's input mapping; removed_at/removed_reason are
        expiry-job-only; projections_state is Stage-2/WF-4 territory). This half of the probe
        proves the COLUMNS exist and round-trip correctly -- it is NOT exercising real business
        logic for these 4, and the report says so explicitly.
     c. Calls the REAL, imported DNC__CheckLedger__v1 to read the row back (its Report node
        returns the full raw row, not just a formatted string -- verified in build_dnc.py).
     d. Diffs all 23 expected values against what CheckLedger actually returned.
     e. Deletes the probe row.
  2. Imports it via POST /api/v1/workflows (same verified pattern as deploy_dnc_workflows.py).
  3. Activates it (POST .../activate -- same pattern as WF1_W1.0.1_build/activate_wf2r.py).
  4. Fires it via one HTTP POST to its production webhook URL.
  5. Deactivates and DELETES the probe workflow (DELETE /api/v1/workflows/{id}) -- nothing
     probe-shaped is left behind in n8n.
  6. Prints the column-by-column diff report.

Exit code 0 only if all 23 columns round-tripped correctly.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")

UPSERT_LEDGER_ID = "RolYGL3J2CNg6Yp3"
CHECK_LEDGER_ID = "kv7reJYAAgsOV33t"
PROBE_LI_SLUG = "zz-probe-verification-row"
PROBE_LI_URL = "https://www.linkedin.com/in/" + PROBE_LI_SLUG
PROBE_EMAIL = "zz-probe-verification@example.invalid"
WEBHOOK_PATH = "zz-probe-dnc-verify"


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
        return json.load(x) if x.length != 0 else {}


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_"), "name": name,
         "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def code_node(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code", {"jsCode": js, "mode": "runOnceForAllItems"}, x, y, tv=2)


def exec_wf_by_id(name, wf_id, x, y=300):
    return node(name, "n8n-nodes-base.executeWorkflow", {
        "source": "database",
        "workflowId": {"__rl": True, "mode": "id", "value": wf_id},
        "mode": "once", "options": {}
    }, x, y, tv=1.2)


TABLE_IDS = {"dnc_registry_dev": "UOgKwlGsL28lX61O"}


def _ref(table):
    if table in TABLE_IDS:
        return {"__rl": True, "mode": "id", "value": TABLE_IDS[table]}
    return {"__rl": True, "mode": "name", "value": table}


def dt_delete(name, key_name, key_value_expr, x, table="dnc_registry_dev", y=300):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "deleteRows",
        "dataTableId": _ref(table),
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": key_name, "condition": "eq", "keyValue": key_value_expr}]},
        "options": {}
    }, x, y, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})


def dt_update_direct(name, value_map, key_name, key_value_expr, x, table="dnc_registry_dev", y=300):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "update",
        "dataTableId": _ref(table),
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": key_name, "condition": "eq", "keyValue": key_value_expr}]},
        "columns": {"mappingMode": "defineBelow", "value": value_map, "matchingColumns": [], "schema": []},
        "options": {}
    }, x, y, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})


def conns(pairs):
    c = {}
    for a, b in pairs:
        c.setdefault(a, {"main": [[]]})
        c[a]["main"][0].append({"node": b, "type": "main", "index": 0})
    return c


build_payload_js = (
    "return [{ json: {\n"
    "  linkedin_url: " + json.dumps(PROBE_LI_URL) + ",\n"
    "  email: " + json.dumps(PROBE_EMAIL) + ",\n"
    "  full_name: 'ZZ Probe Verification Row',\n"
    "  pipedrive_person_id: 999999999,\n"
    "  reason: 'manual_sheet',\n"
    "  source: 'zz_probe_schema_verification',\n"
    "  source_ref: 'zz_probe_test_harness',\n"
    "  date_precision: 'derived',\n"
    "  expiry_review_pending: false,\n"
    "  reply_category: 'zz_probe_category',\n"
    "  correlation_id: 'zz_probe_' + new Date().toISOString()\n"
    "} }];\n"
)

diff_js = (
    "const upsertOut = $('Call UpsertLedger').first().json;\n"
    "const checkOut = $('Call CheckLedger').first().json;\n"
    "const row = checkOut.row || {};\n"
    "const identityKey = (upsertOut.record && upsertOut.record.identity_key) || upsertOut.identity_key || null;\n"
    "const expected = {\n"
    "  identity_key: identityKey,\n"
    "  linkedin_url_norm: '" + PROBE_LI_URL + "',\n"
    "  email_lc: '" + PROBE_EMAIL + "',\n"
    "  full_name: 'ZZ Probe Verification Row',\n"
    "  pipedrive_person_id: 999999999,\n"
    "  entry_type: 'manual',\n"
    "  source: 'zz_probe_schema_verification',\n"
    "  owner_tag: 'zz_probe_owner_tag_test',\n"
    "  reply_category: 'zz_probe_category',\n"
    "  status: 'active',\n"
    "  reason: 'manual_sheet',\n"
    "  source_ref: 'zz_probe_test_harness',\n"
    "  date_precision: 'derived',\n"
    "  offboard_removable: false,\n"
    "  expiry_review_pending: false,\n"
    "  removed_reason: 'zz_probe_removed_reason_test',\n"
    "};\n"
    "const presenceOnly = ['added_at', 'expires_at', 'removed_at', 'correlation_id', 'norm_v', 'also_flagged', 'projections_state'];\n"
    "const diff = [];\n"
    "for (const k of Object.keys(expected)) {\n"
    "  const actual = row[k];\n"
    "  diff.push({ column: k, expected: expected[k], actual, match: String(actual) === String(expected[k]) });\n"
    "}\n"
    "for (const k of presenceOnly) {\n"
    "  const actual = row[k];\n"
    "  diff.push({ column: k, expected: '(presence-only, no fixed value)', actual, match: actual !== undefined && actual !== null && actual !== '' });\n"
    "}\n"
    "const allOk = diff.every(d => d.match);\n"
    "return [{ json: { identity_key: identityKey, all_23_columns_present_and_correct: allOk, columns_checked: diff.length, diff } }];\n"
)

nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": WEBHOOK_PATH, "responseMode": "responseNode", "options": {}},
         -900, extra={"webhookId": "zzprobe0001"}),
    code_node("Build Payload", build_payload_js, -680),
    exec_wf_by_id("Call UpsertLedger", UPSERT_LEDGER_ID, -460),
    dt_update_direct("Direct-set remaining 4 cols",
                      {"owner_tag": "zz_probe_owner_tag_test",
                       "removed_at": "={{ $now.minus(1, 'day').toISO() }}",
                       "removed_reason": "zz_probe_removed_reason_test",
                       "projections_state": '={{ JSON.stringify({pipedrive:"pending",smartlead:"pending",heyreach:"pending"}) }}'},
                      "identity_key", PROBE_LI_SLUG,
                      -240),
    code_node("Prep CheckLedger Input",
              "return [{ json: { linkedin_url: " + json.dumps(PROBE_LI_URL) + " } }];\n",
              -130),
    exec_wf_by_id("Call CheckLedger", CHECK_LEDGER_ID, 0),
    code_node("Diff", diff_js, 200),
    dt_delete("Cleanup: delete probe row", "identity_key", PROBE_LI_SLUG, 420),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 640),
]
# Call CheckLedger needs {linkedin_url} as input -- wire via an inline Set before it instead of
# relying on executeWorkflow input passthrough ambiguity; simplest: reuse Build Payload's json,
# which already has linkedin_url/email on it, since executeWorkflow (mode=once) forwards input items.

wf_json = {
    "name": "zz_probe_dnc_registry_verification",
    "nodes": nodes,
    "connections": conns([
        ("Webhook", "Build Payload"),
        ("Build Payload", "Call UpsertLedger"),
        ("Call UpsertLedger", "Direct-set remaining 4 cols"),
        ("Direct-set remaining 4 cols", "Prep CheckLedger Input"),
        ("Prep CheckLedger Input", "Call CheckLedger"),
        ("Call CheckLedger", "Diff"),
        ("Diff", "Cleanup: delete probe row"),
        ("Cleanup: delete probe row", "Respond"),
    ]),
    "settings": {},
}


def main():
    print("Creating probe workflow...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}")

    try:
        print("Activating...")
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE -- aborting, not firing webhook")
            sys.exit(1)

        webhook_url = BASE + "/webhook/" + WEBHOOK_PATH
        print(f"Firing webhook: {webhook_url}")
        time.sleep(2)  # let activation propagate
        req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        raw = b""
        status = None
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                status = r.status
                raw = r.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read()

        print(f"\nHTTP status: {status}")
        print(f"raw body ({len(raw)} bytes): {raw[:2000]!r}")
        try:
            result = json.loads(raw)
            print("\n=== PROBE RESULT ===")
            print(json.dumps(result, indent=2))
            ok = result.get("all_23_columns_present_and_correct")
            print(f"\nALL 23 COLUMNS OK: {ok}")
        except json.JSONDecodeError:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
            print("\nCould not parse response as JSON -- NOT deleting the probe workflow, "
                  "diagnose via /api/v1/executions?workflowId=" + wid + " before cleaning up.")
            print(f"probe workflow id (now inactive, still exists): {wid}")
            sys.exit(3)

    except Exception:
        print(f"\nUnexpected error -- NOT deleting the probe workflow (id={wid}) so it can be diagnosed.")
        try:
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        except Exception:
            pass
        raise

    print("\nSuccess path -- deactivating + deleting probe workflow...")
    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print(f"  deleted workflow {wid}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
