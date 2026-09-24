"""
SEED WRITE Pass 1 -- read-back verification. Fetches: 100 random rows + 3 collision rows +
paul.gilford (via identity_key OR) + ALL reply_dnc rows + ALL client rows (via reason OR),
in one Data Table get (returnAll) with a big anyCondition filter, then diffs each returned row
against the exact payload that was sent, reporting any mismatch field-by-field.
"""
import json, os, ssl, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
FIX = os.path.join(HERE, "fixtures")
TABLE_ID = "UOgKwlGsL28lX61O"


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


def main():
    with open(os.path.join(FIX, "verify_sample_keys.json"), encoding="utf-8") as f:
        keys = json.load(f)
    with open(os.path.join(FIX, "seed_write_payload_people.json"), encoding="utf-8") as f:
        payload_rows = json.load(f)
    by_key = {r["identity_key"]: r for r in payload_rows}

    conditions = [{"keyName": "identity_key", "condition": "eq", "keyValue": k} for k in keys["all_keys"]]
    conditions.append({"keyName": "reason", "condition": "eq", "keyValue": "reply_dnc"})
    conditions.append({"keyName": "reason", "condition": "eq", "keyValue": "client"})

    webhook_path = "zz-seed-verify-readback"
    wf = {
        "name": "zz_seed_verify_readback",
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": webhook_path, "responseMode": "responseNode",
                             "options": {}},
             "id": "webhook", "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
             "position": [0, 0], "webhookId": webhook_path},
            {"parameters": {"resource": "row", "operation": "get",
                             "dataTableId": {"__rl": True, "mode": "id", "value": TABLE_ID},
                             "matchType": "anyCondition",
                             "filters": {"conditions": conditions},
                             "returnAll": True,
                             "options": {}},
             "id": "get", "name": "Get Verify Set", "type": "n8n-nodes-base.dataTable",
             "typeVersion": 1, "position": [200, 0]},
            {"parameters": {"jsCode": "return [{ json: { count: items.length, rows: items.map(i => i.json) } }];"},
             "id": "agg", "name": "Aggregate", "type": "n8n-nodes-base.code", "typeVersion": 2,
             "position": [400, 0]},
            {"parameters": {"options": {}}, "id": "respond", "name": "Respond",
             "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [600, 0]},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Get Verify Set", "type": "main", "index": 0}]]},
            "Get Verify Set": {"main": [[{"node": "Aggregate", "type": "main", "index": 0}]]},
            "Aggregate": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                   "settings": wf["settings"]})
    wid = created["id"]
    print(f"created verify workflow {wid}")
    n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
    time.sleep(2)

    req = urllib.request.Request(BASE + "/webhook/" + webhook_path, method="POST", data=b"{}",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        print("HTTP ERROR", e.code, raw[:1000])
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        print(f"workflow {wid} left for diagnosis")
        return

    result = json.loads(raw)
    n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{wid}", "DELETE")
    print(f"cleaned up verify workflow {wid}")

    fetched = result["rows"]
    print(f"\nfetched {len(fetched)} rows (expect ~{len(keys['all_keys'])} sample + 142 reply_dnc + 95 client, "
          f"minus overlap since paul.gilford is also reply_dnc)")

    fields_to_check = ["linkedin_url_norm", "email_lc", "full_name", "pipedrive_person_id", "entry_type",
                        "source", "owner_tag", "reply_category", "status", "added_at", "expires_at",
                        "removed_at", "removed_reason", "correlation_id", "norm_v", "reason", "source_ref",
                        "also_flagged", "date_precision", "offboard_removable", "expiry_review_pending",
                        "projections_state"]

    mismatches = []
    seen_keys = set()
    for row in fetched:
        ik = row["identity_key"]
        seen_keys.add(ik)
        expected = by_key.get(ik)
        if expected is None:
            mismatches.append({"identity_key": ik, "issue": "fetched row not found in local payload (unexpected)"})
            continue
        for f in fields_to_check:
            if row.get(f) != expected.get(f):
                mismatches.append({"identity_key": ik, "field": f, "expected": expected.get(f), "actual": row.get(f)})

    reply_dnc_fetched = [r for r in fetched if r["reason"] == "reply_dnc"]
    client_fetched = [r for r in fetched if r["reason"] == "client"]
    print(f"reply_dnc rows fetched: {len(reply_dnc_fetched)} (expect 142, +1 if paul.gilford counted separately -> 143)")
    print(f"client rows fetched: {len(client_fetched)} (expect 95)")

    missing_keys = [k for k in keys["all_keys"] if k not in seen_keys]
    print(f"sample keys requested but NOT found in results: {missing_keys}")

    print(f"\nfield mismatches found: {len(mismatches)}")
    for m in mismatches[:30]:
        print(" ", json.dumps(m))

    out = {
        "fetched_count": len(fetched),
        "reply_dnc_count": len(reply_dnc_fetched),
        "client_count": len(client_fetched),
        "missing_sample_keys": missing_keys,
        "field_mismatches": mismatches,
        "PASS": (len(mismatches) == 0 and not missing_keys
                 and len(reply_dnc_fetched) == 142 and len(client_fetched) == 95),
    }
    with open(os.path.join(FIX, "seed_verify_report.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\nPASS = {out['PASS']}")
    print(f"wrote {os.path.join(FIX, 'seed_verify_report.json')}")


if __name__ == "__main__":
    main()
