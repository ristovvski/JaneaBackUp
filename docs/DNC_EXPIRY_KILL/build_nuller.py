# -*- coding: utf-8 -*-
"""One-shot, secret-gated, id-targeted writer: sets expires_at = null on the row ids it is given.

Deliberately dumb. It does NOT read the registry and decide for itself what to null - the caller
supplies the exact id list from the snapshot artifact, so what gets written is exactly what was
recorded as reversible. A writer that re-derives its own target set can drift from the artifact
that is supposed to undo it.

Chunked by construction: one HTTP call = one chunk = one execution. A ~100-item burst is the
documented OOM threshold on this instance, so the caller keeps chunks at or below that.
"""
import json, sys

OUT = sys.argv[1]
LEDGER = "UOgKwlGsL28lX61O"          # real table id, never mode:"name"
SECRET = sys.argv[2]

nodes = [
    {"parameters": {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_EXPIRY_NULL_ONESHOT}}",
                    "responseMode": "responseNode", "options": {}},
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
     "id": "nul-hook", "name": "Webhook", "webhookId": "{{WEBHOOK_DNC_EXPIRY_NULL_ONESHOT}}"},

    {"parameters": {"jsCode":
        "// Secret-gated. This endpoint performs unattended registry writes; it exists for one\n"
        "// afternoon and is deactivated the moment the run completes.\n"
        "const b = $('Webhook').item.json.body || {};\n"
        "if (String(b.secret || '') !== " + json.dumps(SECRET) + ") {\n"
        "  throw new Error('EXPIRY-NULL: bad secret');\n"
        "}\n"
        "const ids = Array.isArray(b.ids) ? b.ids : null;\n"
        "if (!ids || !ids.length) throw new Error('EXPIRY-NULL: no ids supplied');\n"
        "if (ids.length > 150) throw new Error('EXPIRY-NULL: chunk too large: ' + ids.length);\n"
        "return ids.map(function (id) { return { json: { row_id: id } }; });\n",
        "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 0],
     "id": "nul-gate", "name": "Verify And Split"},

    {"parameters": {"resource": "row", "operation": "update",
                    "dataTableId": {"__rl": True, "mode": "id", "value": LEDGER},
                    "matchType": "allConditions",
                    "filters": {"conditions": [
                        {"keyName": "id", "condition": "eq", "keyValue": "={{ $json.row_id }}"}]},
                    "columns": {"mappingMode": "defineBelow",
                                "value": {"expires_at": None},
                                "matchingColumns": [], "schema": []},
                    "options": {}},
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [400, 0],
     "id": "nul-write", "name": "Null Expires At", "onError": "continueRegularOutput"},

    {"parameters": {"jsCode":
        "// POSITIVE success check. A failed dataTable op does not reliably return {error} - some\n"
        "// ops echo the original input with no marker at all - so success is asserted by the real\n"
        "// response shape: a row carrying our identity_key and an expires_at that is now null.\n"
        "const asked = $('Verify And Split').all().map(function (i) { return i.json.row_id; });\n"
        "const out = $input.all().map(function (i) { return i.json; });\n"
        "let ok = 0; const bad = [];\n"
        "out.forEach(function (r, ix) {\n"
        "  const row = (r && r.data) ? r.data : r;\n"
        "  const good = row && typeof row.identity_key === 'string'\n"
        "            && (row.expires_at === null || row.expires_at === undefined || row.expires_at === '');\n"
        "  if (good) ok++; else bad.push({ id: asked[ix], got: JSON.stringify(row).slice(0, 160) });\n"
        "});\n"
        "return [{ json: { asked: asked.length, confirmed_null: ok, failed: bad.length,\n"
        "                  failures: bad.slice(0, 10) } }];\n",
        "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600, 0],
     "id": "nul-tally", "name": "Tally"},

    {"parameters": {"respondWith": "json",
                    "responseBody": "={{ JSON.stringify($json) }}", "options": {}},
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [800, 0],
     "id": "nul-respond", "name": "Respond"},
]

conns = {
    "Webhook": {"main": [[{"node": "Verify And Split", "type": "main", "index": 0}]]},
    "Verify And Split": {"main": [[{"node": "Null Expires At", "type": "main", "index": 0}]]},
    "Null Expires At": {"main": [[{"node": "Tally", "type": "main", "index": 0}]]},
    "Tally": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}

wf = {"name": "dnc_expiry_null_oneshot", "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1", "errorWorkflow": "BbrXPABgOaaTJjD6",
                   "callerPolicy": "workflowsFromSameOwner", "timezone": "Asia/Jerusalem"}}
json.dump(wf, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
prod = {}
for s, v in conns.items():
    for t in v["main"][0]:
        prod.setdefault(t["node"], []).append(s)
print("built", len(nodes), "nodes; fan-in:", {k: v for k, v in prod.items() if len(v) > 1} or "none")
