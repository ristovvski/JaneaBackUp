"""
SEED WRITE Pass 1 -- the actual bulk write, per owner's explicit 2026-08-11 GO.
Deploys a one-time seed-writer n8n workflow per table (Webhook -> split items -> Data Table
upsert, keyed on identity_key / domain -- idempotent and re-runnable if a batch needs a retry),
drives it in batches, collects per-batch counts, then tears the workflow down.

Usage: python dnc_seed_write.py people   (writes fixtures/seed_write_payload_people.json)
       python dnc_seed_write.py domains  (writes fixtures/seed_write_payload_domains.json)
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
FIX = os.path.join(HERE, "fixtures")

TABLE_IDS = {"dnc_registry_dev": "UOgKwlGsL28lX61O", "dnc_domain_block_dev": "ADexvtQHc6cT2yJ6"}
BATCH_SIZE = 1000


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


def build_workflow(table, matching_col, columns, webhook_path):
    value_map = {c: f"={{{{ $json.{c} }}}}" for c in columns}
    wf = {
        "name": f"zz_seed_writer_{table}",
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": webhook_path, "responseMode": "responseNode",
                             "options": {}},
             "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": webhook_path},
            {"parameters": {"jsCode": "return items[0].json.body.rows.map(r => ({ json: r }));"},
             "id": "split", "name": "Split Rows", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [200, 0]},
            {"parameters": {
                "resource": "row", "operation": "upsert",
                "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_IDS[table]},
                "matchType": "allConditions",
                "filters": {"conditions": [{"keyName": matching_col, "condition": "eq",
                                             "keyValue": f"={{{{ $json.{matching_col} }}}}"}]},
                "columns": {"mappingMode": "defineBelow", "value": value_map,
                            "matchingColumns": [matching_col], "schema": []},
                "options": {}},
             "id": "upsert", "name": "Upsert Batch", "type": "n8n-nodes-base.dataTable",
             "typeVersion": 1, "position": [400, 0]},
            {"parameters": {"jsCode": "return [{ json: { written: $input.all().length } }];"},
             "id": "count", "name": "Count", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [600, 0], "alwaysOutputData": True},
            {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
             "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [800, 0]},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Split Rows", "type": "main", "index": 0}]]},
            "Split Rows": {"main": [[{"node": "Upsert Batch", "type": "main", "index": 0}]]},
            "Upsert Batch": {"main": [[{"node": "Count", "type": "main", "index": 0}]]},
            "Count": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    return wf


def run_batches(table, matching_col, columns, rows, tag):
    webhook_path = f"zz-seed-write-{tag}"
    wf = build_workflow(table, matching_col, columns, webhook_path)
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                   "settings": wf["settings"]})
    wid = created["id"]
    print(f"created seed-writer workflow {wid} for {table}")
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)

    total_written = 0
    batch_reports = []
    webhook_url = BASE + "/webhook/" + webhook_path
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        body = json.dumps({"rows": batch}).encode("utf-8")
        req = urllib.request.Request(webhook_url, method="POST", data=body,
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read()
            print(f"BATCH {i}-{i+len(batch)} HTTP ERROR: {e.code} {raw[:500]}")
            n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
            print(f"STOPPING -- workflow {wid} left for diagnosis, {total_written} rows written so far")
            sys.exit(2)

        try:
            result = json.loads(raw)
            written = result.get("written")
        except json.JSONDecodeError:
            written = None

        batch_no = i // BATCH_SIZE + 1
        print(f"batch {batch_no}: rows {i}-{i+len(batch)-1} ({len(batch)} sent) -> written={written}")
        batch_reports.append({"batch": batch_no, "range": [i, i + len(batch) - 1],
                               "sent": len(batch), "written": written})
        if written != len(batch):
            print(f"  WARNING: written ({written}) != sent ({len(batch)}) for batch {batch_no}")
        total_written += (written or 0)

    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print(f"cleaned up seed-writer workflow {wid}")
    print(f"\nTOTAL rows sent: {len(rows)}, TOTAL written per batch responses: {total_written}")
    return batch_reports, total_written


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which == "people":
        with open(os.path.join(FIX, "seed_write_payload_people.json"), encoding="utf-8") as f:
            rows = json.load(f)
        columns = ["identity_key", "linkedin_url_norm", "email_lc", "full_name", "pipedrive_person_id",
                   "entry_type", "source", "owner_tag", "reply_category", "status", "added_at",
                   "expires_at", "removed_at", "removed_reason", "correlation_id", "norm_v", "reason",
                   "source_ref", "also_flagged", "date_precision", "offboard_removable",
                   "expiry_review_pending", "projections_state"]
        reports, total = run_batches("dnc_registry_dev", "identity_key", columns, rows, "people")
        out = {"table": "dnc_registry_dev", "total_rows": len(rows), "total_written": total,
               "batches": reports}
    elif which == "domains":
        with open(os.path.join(FIX, "seed_write_payload_domains.json"), encoding="utf-8") as f:
            rows = json.load(f)
        columns = ["domain", "source", "status", "added_at", "removed_at", "removed_reason",
                   "correlation_id"]
        reports, total = run_batches("dnc_domain_block_dev", "domain", columns, rows, "domains")
        out = {"table": "dnc_domain_block_dev", "total_rows": len(rows), "total_written": total,
               "batches": reports}
    else:
        print("usage: python dnc_seed_write.py [people|domains]")
        sys.exit(1)

    out_path = os.path.join(FIX, f"seed_write_report_{which}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
