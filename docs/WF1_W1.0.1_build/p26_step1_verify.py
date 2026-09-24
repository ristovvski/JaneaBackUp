#!/usr/bin/env python3
"""Read-back said 50 where 53 were upserted. 50 is exactly the shape of a default page cap, but
"looks like a cap" is not evidence. Verify by KEY, not by count: ask the table for each of the 53
keys explicitly and report which are actually absent.

Runs inside n8n (no dataTable REST). Reuses the throwaway workflow, replacing its body with a
per-key lookup.
"""
import json, os, ssl, sys, time, urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HERE = os.path.dirname(os.path.abspath(__file__))
TID = "euyostwJYfJefItC"
PATH = "{{WEBHOOK_ZZ_VERIFY_WF1_ALERT_REGISTRY}}"


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
KEYS = [r["claim_key"] for r in ROWS]

CODE = ("const KEYS = " + json.dumps(KEYS, ensure_ascii=False) + ";\n"
        "return KEYS.map(k => ({ json: { claim_key: k } }));\n")
TALLY = (
    "// one item per key, each carrying whatever the table returned for it\n"
    "const all = $input.all().map(i => i.json);\n"
    "const found = all.filter(r => r && r.claim_key && r.family === 'wf1_alert');\n"
    "const keys = new Set(found.map(r => r.claim_key));\n"
    "const KEYS = " + json.dumps(KEYS, ensure_ascii=False) + ";\n"
    "const missing = KEYS.filter(k => !keys.has(k));\n"
    "return [{ json: { asked: KEYS.length, rows_returned: all.length,\n"
    "                  distinct_found: keys.size, missing_count: missing.length,\n"
    "                  missing } }];\n")

wf = {
    "name": "zz_verify_wf1_alert_registry (throwaway)",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": PATH,
                        "responseMode": "lastNode", "options": {}},
         "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
         "id": "vf-hook", "name": "Webhook", "webhookId": PATH},
        {"parameters": {"jsCode": CODE},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [220, 0],
         "id": "vf-keys", "name": "Keys"},
        {"parameters": {"resource": "row", "operation": "get",
                        "dataTableId": {"__rl": True, "mode": "id", "value": TID},
                        "matchType": "allConditions",
                        "filters": {"conditions": [
                            {"keyName": "claim_key", "condition": "eq",
                             "keyValue": "={{ $json.claim_key }}"}]},
                        "options": {}},
         "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [440, 0],
         "id": "vf-get", "name": "DT Get One", "alwaysOutputData": True,
         "onError": "continueRegularOutput"},
        {"parameters": {"jsCode": TALLY},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 0],
         "id": "vf-tally", "name": "Tally"},
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Keys", "type": "main", "index": 0}]]},
        "Keys": {"main": [[{"node": "DT Get One", "type": "main", "index": 0}]]},
        "DT Get One": {"main": [[{"node": "Tally", "type": "main", "index": 0}]]},
    },
    "settings": {"executionOrder": "v1"},
}

existing = [w for w in (n8n("/api/v1/workflows?limit=250") or {}).get("data", [])
            if w["name"].startswith("zz_verify_wf1_alert_registry")]
if existing:
    wid = existing[0]["id"]
    n8n(f"/api/v1/workflows/{wid}", "PUT", wf)
    print(f"reusing {wid}")
else:
    wid = (n8n("/api/v1/workflows", "POST", wf) or {}).get("id")
    print(f"created {wid}")
n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
time.sleep(3)
url = BASE.replace("/api/v1", "") + f"/webhook/{PATH}"
try:
    with urllib.request.urlopen(urllib.request.Request(
            url, method="POST", data=b"{}",
            headers={"Content-Type": "application/json"}), timeout=300, context=ctx) as x:
        print(f"webhook {x.status}")
except Exception as e:
    print(f"webhook: {str(e)[:140]}")
time.sleep(4)
ex = (n8n(f"/api/v1/executions?workflowId={wid}&limit=2") or {}).get("data") or []
if ex:
    det = n8n(f"/api/v1/executions/{ex[0]['id']}?includeData=true")
    rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
    try:
        t = rd["Tally"][0]["data"]["main"][0][0]["json"]
        print("\n=== PER-KEY VERIFICATION ===")
        print(f"  keys asked      : {t['asked']}")
        print(f"  rows returned   : {t['rows_returned']}")
        print(f"  distinct found  : {t['distinct_found']}")
        print(f"  MISSING         : {t['missing_count']}")
        for m in (t.get("missing") or [])[:10]:
            print(f"     {m}")
    except Exception as e:
        print(f"tally unavailable: {str(e)[:90]}")
        print(f"nodes: {sorted(rd.keys())}")
n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
print(f"\ndeactivated {wid}")
