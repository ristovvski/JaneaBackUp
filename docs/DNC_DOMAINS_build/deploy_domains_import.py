#!/usr/bin/env python3
"""Deploy dnc_domains_import -- a generic domain-batch upsert driver, same dry_run-default-true
safety as every other batch driver this project uses. BLOCKED until Nik creates the dnc_domains
table and shares its real id (mode:"name" has proven unreliable from API-created workflows on this
instance every time it's been tried -- i04_snapshots, dnc_gate_queue, and others). Substitute
DOMAINS_TABLE_ID below before running.
"""
import json, os, ssl, sys, urllib.request

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

DOMAINS_TABLE_ID = "ai4ZiOGqzuJHRYLB"  # verified live 2026-09-09 (the id first given was wrong)


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def build(table_id):
    domains_table = {"__rl": True, "mode": "id", "value": table_id}
    build_items_js = (
        "const body = $('Webhook').first().json.body || {};\n"
        "const rows = Array.isArray(body.rows) ? body.rows : [];\n"
        "if (!rows.length) throw new Error('dnc_domains_import: body.rows must be a non-empty array');\n"
        "const dryRun = body.dry_run !== false;\n"
        "const errors = [];\n"
        "rows.forEach((r, i) => {\n"
        "  if (!r.domain || typeof r.domain !== 'string' || r.domain !== r.domain.toLowerCase() || r.domain.startsWith('www.')) {\n"
        "    errors.push('row ' + i + ': domain must be a lowercased, www-stripped string, got ' + JSON.stringify(r.domain));\n"
        "  }\n"
        "});\n"
        "if (errors.length) throw new Error('dnc_domains_import: ' + errors.length + ' invalid row(s): ' + errors.slice(0, 10).join('; '));\n"
        "return rows.map(r => ({ json: Object.assign({}, r, { dry_run: dryRun }) }));\n"
    )
    report_js = (
        "const rows = $input.all().map(i => i.json);\n"
        "const dryRun = $('Build Items').all().length ? $('Build Items').first().json.dry_run : true;\n"
        "return [{ json: { processed: rows.length, dry_run: dryRun,\n"
        "  note: dryRun ? 'DRY RUN -- nothing written' : 'WRITTEN -- domains upserted' } }];\n"
    )
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": "dnc-domains-import", "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-600, 300], "webhookId": "dncdomainsimport01"},
        {"parameters": {"jsCode": build_items_js, "mode": "runOnceForAllItems"},
         "id": "build_items", "name": "Build Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [-400, 300]},
        {"parameters": {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"},
                                        "combinator": "and",
                                        "conditions": [{"leftValue": "={{ $json.dry_run === true }}", "rightValue": True,
                                                        "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         "id": "dry_run", "name": "Dry Run?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [-200, 300]},
        {"parameters": {"jsCode": "return $input.all();\n", "mode": "runOnceForAllItems"},
         "id": "report_dry", "name": "Report Dry Run", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [0, 460]},
        {"parameters": {"resource": "row", "operation": "upsert", "dataTableId": domains_table,
                         "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "domain", "condition": "eq", "keyValue": "={{ $json.domain }}"}]},
                         "columns": {"mappingMode": "defineBelow",
                                     "value": {"domain": "={{ $json.domain }}", "added_at": "={{ $json.added_at }}",
                                               "source": "={{ $json.source }}", "reason": "={{ $json.reason }}",
                                               "status": "={{ $json.status }}"},
                                     "matchingColumns": ["domain"], "schema": []},
                         "options": {}},
         "id": "upsert", "name": "Upsert Domain", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [0, 300], "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3},
        {"parameters": {"jsCode": report_js, "mode": "runOnceForAllItems"},
         "id": "build_report", "name": "Build Report", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 300]},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [400, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Build Items", "type": "main", "index": 0}]]},
        "Build Items": {"main": [[{"node": "Dry Run?", "type": "main", "index": 0}]]},
        "Dry Run?": {"main": [[{"node": "Report Dry Run", "type": "main", "index": 0}],
                               [{"node": "Upsert Domain", "type": "main", "index": 0}]]},
        "Report Dry Run": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        "Upsert Domain": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        "Build Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    return {"name": "dnc_domains_import", "nodes": nodes, "connections": connections, "settings": {}}


def main():
    if not DOMAINS_TABLE_ID:
        print("BLOCKED: set DOMAINS_TABLE_ID at the top of this script once Nik creates dnc_domains "
              "and shares its real id (from the table's own UI URL). Nothing deployed.")
        sys.exit(1)
    wf_json = build(DOMAINS_TABLE_ID)
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    print(f"deployed dnc_domains_import, id={wid}")
    print("next: run fire_domains_import.py --dry-run first, then --live")


if __name__ == "__main__":
    main()
