#!/usr/bin/env python3
"""#26 STEP 1 — migrate the 53 alert-registry keys into the claims dataTable.

There is no REST endpoint for dataTable rows (re-probed: 404 on all seven shapes), so the write has
to happen INSIDE n8n. This builds a throwaway workflow, fires it once, reads the result back from
the execution, and deactivates it again.

Shape: Webhook -> Rows (53 items) -> DT Upsert -> Collapse -> DT Read Back -> Respond
The read-back is a separate dataTable query filtered on family, so the verification is a fresh read
of the table rather than a count of what we think we sent.
"""
import argparse, json, os, ssl, sys, time, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
TID = "euyostwJYfJefItC"
PATH = "{{WEBHOOK_ZZ_MIG_WF1_ALERT_REGISTRY}}"

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
a = ap.parse_args()


def n8n(path, method="GET", body=None, att=0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and att < 5:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise SystemExit(f"n8n {method} {path}: HTTP {e.code} {e.read()[:250]}")
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


ROWS = json.load(open(os.path.join(HERE, "alert_registry_migration.json"),
                      encoding="utf-8"))["rows"]
print(f"rows to migrate: {len(ROWS)}")
print(f"  forms: L={sum(1 for r in ROWS if r['form']=='L')} "
      f"P={sum(1 for r in ROWS if r['form']=='P')}")

CODE = ("// Migration payload, embedded so the run is reproducible and auditable.\n"
        "const ROWS = " + json.dumps(ROWS, ensure_ascii=False) + ";\n"
        "return ROWS.map(r => ({ json: r }));\n")

wf = {
    "name": "zz_migrate_wf1_alert_registry (throwaway, deactivate after use)",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": PATH,
                        "responseMode": "lastNode", "options": {}},
         "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
         "id": "mig-hook", "name": "Webhook", "webhookId": PATH},
        {"parameters": {"jsCode": CODE},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0],
         "id": "mig-rows", "name": "Rows"},
        {"parameters": {"resource": "row", "operation": "upsert",
                        "dataTableId": {"__rl": True, "mode": "id", "value": TID},
                        "matchType": "allConditions",
                        "filters": {"conditions": [
                            {"keyName": "claim_key", "condition": "eq",
                             "keyValue": "={{ $json.claim_key }}"}]},
                        "columns": {"mappingMode": "defineBelow", "value": {
                            "claim_key": "={{ $json.claim_key }}",
                            "family": "wf1_alert",
                            "workflow": "WF-1",
                            "event_time": "={{ $json.claimed_at }}",
                            "claimed_at": "={{ $json.claimed_at }}",
                            "evidence": "={{ 'migrated:staticData __alerted_v1 exec:' + $execution.id }}"}},
                        "options": {}},
         "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [440, 0],
         "id": "mig-upsert", "name": "DT Upsert"},
        {"parameters": {"jsCode": "return [{ json: { upserted: $input.all().length } }];"},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 0],
         "id": "mig-collapse", "name": "Collapse"},
        {"parameters": {"resource": "row", "operation": "get",
                        "dataTableId": {"__rl": True, "mode": "id", "value": TID},
                        "matchType": "allConditions",
                        "filters": {"conditions": [
                            {"keyName": "family", "condition": "eq",
                             "keyValue": "wf1_alert"}]},
                        "options": {}},
         "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [880, 0],
         "id": "mig-read", "name": "DT Read Back"},
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Rows", "type": "main", "index": 0}]]},
        "Rows": {"main": [[{"node": "DT Upsert", "type": "main", "index": 0}]]},
        "DT Upsert": {"main": [[{"node": "Collapse", "type": "main", "index": 0}]]},
        "Collapse": {"main": [[{"node": "DT Read Back", "type": "main", "index": 0}]]},
    },
    "settings": {"executionOrder": "v1"},
}

if not a.live:
    print("\n--live not given. Would create the throwaway workflow and POST once.")
    print(f"  webhook path: /{PATH}")
    print(f"  first row: {json.dumps(ROWS[0], ensure_ascii=False)[:130]}")
    sys.exit(0)

existing = [w for w in (n8n("/api/v1/workflows?limit=250") or {}).get("data", [])
            if w["name"].startswith("zz_migrate_wf1_alert_registry")]
if existing:
    wid = existing[0]["id"]
    print(f"reusing existing throwaway workflow {wid}")
    n8n(f"/api/v1/workflows/{wid}", "PUT", wf)
else:
    created = n8n("/api/v1/workflows", "POST", wf)
    wid = created.get("id")
    print(f"created throwaway workflow {wid}")

n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
print("activated; firing once...")
time.sleep(3)
url = BASE.replace("/api/v1", "") + f"/webhook/{PATH}"
req = urllib.request.Request(url, method="POST", data=b"{}",
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=300, context=ctx) as x:
        print(f"  webhook responded {x.status}: {x.read()[:200].decode('utf-8','replace')}")
except Exception as e:
    print(f"  webhook call: {str(e)[:160]}")

time.sleep(4)
ex = (n8n(f"/api/v1/executions?workflowId={wid}&limit=3") or {}).get("data") or []
if ex:
    det = n8n(f"/api/v1/executions/{ex[0]['id']}?includeData=true")
    rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
    print(f"\nexecution {ex[0]['id']} status={ex[0].get('status')} nodes={sorted(rd.keys())}")
    for nm in ("DT Upsert", "Collapse", "DT Read Back"):
        try:
            items = rd[nm][0]["data"]["main"][0]
            print(f"  {nm:<14} items={len(items)}  "
                  f"sample={json.dumps(items[0]['json'], ensure_ascii=False)[:120]}")
        except Exception as e:
            print(f"  {nm:<14} n/a ({str(e)[:60]})")
    err = ((det.get("data") or {}).get("resultData") or {}).get("error") or {}
    if err:
        print(f"  ERROR: {str(err.get('message'))[:160]}")

n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
print(f"\ndeactivated {wid} — throwaway left in place for audit, not deleted")
