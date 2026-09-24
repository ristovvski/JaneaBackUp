#!/usr/bin/env python3
"""Driver for dnc_supabase_initial_load (NOT YET DEPLOYED -- see deploy_supabase_sync.py, which
does not exist yet either, on purpose: nothing fires before Nik's word per §9f.2).

Reads dnc_registry_dev + dnc_domains fresh from n8n via a read-only probe workflow (deployed,
fired, deleted -- same pattern as probe_source_counts.py), maps each row into the EXACT Supabase
column shape, chunks into groups of CHUNK_SIZE, and POSTs each chunk to the
dnc_supabase_initial_load webhook. dry_run is True by default; pass --live to actually write.
Fires ONE final finalize:true call per table after its chunks succeed, to log the sync-run into
dnc_registry_meta."""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

REGISTRY_TABLE = "UOgKwlGsL28lX61O"
DOMAINS_TABLE = "ai4ZiOGqzuJHRYLB"
CHUNK_SIZE = 500

REGISTRY_COLUMNS = [
    "id", "identity_key", "norm_v", "linkedin_url_norm", "email_lc", "full_name",
    "pipedrive_person_id", "entry_type", "reason", "source", "source_ref", "source_signal",
    "correlation_id", "date_precision", "expiry_review_pending", "offboard_removable",
    "also_flagged", "projections_state", "owner_tag", "status", "added_at", "removed_at",
    "removed_reason", "reply_category", "expires_at", "createdAt", "updatedAt",
]
DOMAINS_COLUMNS = ["domain", "added_at", "source", "reason", "status"]


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def fire_webhook(path, body, timeout=60):
    url = BASE.replace("/api/v1", "") + "/webhook/" + path
    req = urllib.request.Request(url, method="POST", data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (raw.decode() if raw else None)


def deploy_read_probe():
    """Read-only probe: dumps every row from both source Data Tables. Deployed, fired, deleted."""
    nodes = [
        {"parameters": {"httpMethod": "GET", "path": "probe-full-export", "responseMode": "responseNode", "options": {}},
         "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [-600, 300], "webhookId": "probefullexport01"},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": "id", "value": REGISTRY_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_registry", "name": "Get Registry", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 200], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"resource": "row", "operation": "get",
                         "dataTableId": {"__rl": True, "mode": "id", "value": DOMAINS_TABLE},
                         "returnAll": True, "matchType": "allConditions",
                         "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
                         "options": {}},
         "id": "get_domains", "name": "Get Domains", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [-400, 400], "onError": "continueErrorOutput", "alwaysOutputData": True},
        {"parameters": {"jsCode": (
            "return [{ json: {\n"
            "  registry: $('Get Registry').all().map(i => i.json),\n"
            "  domains: $('Get Domains').all().map(i => i.json),\n"
            "} }];\n"), "mode": "runOnceForAllItems"},
         "id": "report", "name": "Report", "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": [-200, 300]},
        {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [0, 300]},
    ]
    connections = {
        "Webhook": {"main": [[{"node": "Get Registry", "type": "main", "index": 0},
                               {"node": "Get Domains", "type": "main", "index": 0}]]},
        "Get Registry": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
        "Get Domains": {"main": [[{"node": "Report", "type": "main", "index": 0}]]},
        "Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }
    wf_json = {"name": "ZZ_PROBE_full_export_DELETE_ME", "nodes": nodes, "connections": connections, "settings": {}}
    created = n8n("/api/v1/workflows", "POST", wf_json)
    wid = created["id"]
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    return wid


def fetch_source_data():
    wid = deploy_read_probe()
    time.sleep(1)
    try:
        url = BASE.replace("/api/v1", "") + "/webhook/probe-full-export"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            return json.loads(r.read())
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")


def project(row, columns):
    return {c: row.get(c) for c in columns}


def run_table(table, rows, columns, live):
    print(f"\n=== {table}: {len(rows)} rows ===")
    total = 0
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = [project(r, columns) for r in rows[i:i + CHUNK_SIZE]]
        status, result = fire_webhook("{{WEBHOOK_DNC_SUPABASE_INITIAL_LOAD}}",
                                       {"table": table, "rows": chunk, "dry_run": not live})
        print(f"  chunk {i}-{i+len(chunk)}: HTTP {status} -> {result}")
        if isinstance(result, dict) and result.get("ok") is False:
            print(f"  ABORTING {table}: chunk reported ok=false")
            return total
        total += len(chunk)
    status, result = fire_webhook("{{WEBHOOK_DNC_SUPABASE_INITIAL_LOAD}}",
                                   {"table": table, "finalize": True, "row_count": total, "dry_run": not live})
    print(f"  finalize: HTTP {status} -> {result}")
    return total


def main():
    live = "--live" in sys.argv
    print("fetching fresh source data from n8n (read-only)...")
    data = fetch_source_data()
    registry_rows = data["registry"]
    domain_rows = data["domains"]
    print(f"registry: {len(registry_rows)} rows, domains: {len(domain_rows)} rows")

    run_table("dnc_registry", registry_rows, REGISTRY_COLUMNS, live)
    run_table("dnc_domains", domain_rows, DOMAINS_COLUMNS, live)

    print("\n" + ("LIVE -- rows written to Supabase" if live else "DRY RUN -- nothing written"))


if __name__ == "__main__":
    main()
