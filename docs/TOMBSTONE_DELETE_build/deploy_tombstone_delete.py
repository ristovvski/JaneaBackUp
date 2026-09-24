#!/usr/bin/env python3
"""Deploy dnc_tombstone_hard_delete -- a generic, id-agnostic HARD delete driver (not a tombstone
SET -- an actual deleteRows). First real hard-delete this project has ever fired against
dnc_registry_dev (every prior "removal" was a status='removed' SET). dry_run defaults true, same
safety convention as every other batch driver here. Per-item deleteRows (not a single bulk filter)
so a single execution handling up to CHUNK_SIZE ids stays bounded and inspectable."""
import json, os, ssl, urllib.request

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
REGISTRY_TABLE = {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"}


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


build_items_js = (
    "const body = $('Webhook').first().json.body || {};\n"
    "const ids = Array.isArray(body.ids) ? body.ids : [];\n"
    "if (!ids.length) throw new Error('dnc_tombstone_hard_delete: body.ids must be a non-empty array');\n"
    "const dryRun = body.dry_run !== false; // default true -- explicit false required to write\n"
    "// safety: every id must ALREADY be status='removed' AND removed_reason match the expected\n"
    "// tag, checked against the row this node fetches per-item just before deleting (see Verify\n"
    "// Still Tombstoned) -- this node just carries the id + dry_run flag forward.\n"
    "return ids.map(id => ({ json: { id, dry_run: dryRun } }));\n"
)
report_js = (
    "const rows = $input.all().map(i => i.json);\n"
    "const dryRun = $('Build Items').all().length ? $('Build Items').first().json.dry_run : true;\n"
    "const skipped = rows.filter(r => r.skipped_not_tombstoned);\n"
    "return [{ json: { processed: rows.length, skipped_not_tombstoned: skipped.length,\n"
    "  skipped_ids: skipped.map(r => r.id), dry_run: dryRun,\n"
    "  note: dryRun ? 'DRY RUN -- nothing deleted' : 'DELETED -- rows hard-removed' } }];\n"
)


def build():
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": "dnc-tombstone-hard-delete", "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-800, 300], "webhookId": "dnctombstonedelete01"},
        {"parameters": {"jsCode": build_items_js, "mode": "runOnceForAllItems"},
         "id": "build_items", "name": "Build Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-600, 300]},
        # re-verify EACH row is still status=removed with the expected tag right before deleting --
        # a live safety re-check, not trusting the caller-supplied id list alone (the whole point
        # of the earlier reconciliation: some of the original 7486 got reactivated since).
        {"parameters": {"resource": "row", "operation": "get", "dataTableId": REGISTRY_TABLE,
                         "returnAll": False, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "id", "condition": "eq", "keyValue": "={{ $json.id }}"}]},
                         "options": {}},
         "id": "verify_row", "name": "Verify Still Tombstoned", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 300], "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2,
         "alwaysOutputData": True},
        {"parameters": {"jsCode": (
            "const id = $('Build Items').item.json.id;\n"
            "const dryRun = $('Build Items').item.json.dry_run;\n"
            "const row = $json;\n"
            # alwaysOutputData means a genuinely-missing row (0 matches -- already deleted, or
            # never existed) still reaches here as an empty-ish item rather than silently
            # vanishing from the pipeline (n8n-filtered-read-needs-alwaysoutputdata).
            "const stillTombstoned = !!row && row.status === 'removed' && row.removed_reason === 'rule_change_2026-08-26_melisa';\n"
            "return { json: { id, dry_run: dryRun, skip: !stillTombstoned, skipped_not_tombstoned: !stillTombstoned } };\n"
        ), "mode": "runOnceForEachItem"},
         "id": "check_still", "name": "Check Still Tombstoned", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-200, 300]},
        {"parameters": {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"},
                                        "combinator": "and",
                                        "conditions": [{"leftValue": "={{ $json.dry_run === true || $json.skip === true }}", "rightValue": True,
                                                        "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         "id": "skip_delete", "name": "Skip Delete?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [0, 300]},
        {"parameters": {"jsCode": "return $input.all();\n", "mode": "runOnceForAllItems"},
         "id": "report_skip", "name": "Report (skip/dry-run)", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 460]},
        {"parameters": {"resource": "row", "operation": "deleteRows", "dataTableId": REGISTRY_TABLE,
                         "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "id", "condition": "eq", "keyValue": "={{ $json.id }}"}]},
                         "options": {}},
         "id": "delete_row", "name": "Delete Row", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [200, 300], "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2},
        {"parameters": {"jsCode": report_js, "mode": "runOnceForAllItems"},
         "id": "build_report", "name": "Build Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [400, 300]},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [600, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Build Items", "type": "main", "index": 0}]]},
        "Build Items": {"main": [[{"node": "Verify Still Tombstoned", "type": "main", "index": 0}]]},
        "Verify Still Tombstoned": {"main": [[{"node": "Check Still Tombstoned", "type": "main", "index": 0}],
                                              [{"node": "Check Still Tombstoned", "type": "main", "index": 0}]]},
        "Check Still Tombstoned": {"main": [[{"node": "Skip Delete?", "type": "main", "index": 0}]]},
        "Skip Delete?": {"main": [[{"node": "Report (skip/dry-run)", "type": "main", "index": 0}],
                                   [{"node": "Delete Row", "type": "main", "index": 0}]]},
        "Report (skip/dry-run)": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        "Delete Row": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        "Build Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return {"name": "dnc_tombstone_hard_delete", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    wf_json = build()
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    print(f"deployed dnc_tombstone_hard_delete, id={wid}")
    return wid


if __name__ == "__main__":
    main()
