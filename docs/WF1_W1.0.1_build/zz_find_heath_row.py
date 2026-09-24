#!/usr/bin/env python3
"""One-shot: find Person-8768306e's row(s) in the DNC registry so they can be tombstoned by id.

The registry data table has no REST API (404 on every route shape tried), so a read has to run
INSIDE n8n. This creates a throwaway workflow, fires it once, reads the answer, and DEACTIVATES it -
the established zz_ pattern. It is registered in ONE_SHOT_TOOLS.md rather than deleted.

READ ONLY against the registry: one dataTable `get`, no writes anywhere.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HOST = BASE.split("/api/")[0].rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
REG = "UOgKwlGsL28lX61O"
PATH = "{{WEBHOOK_ZZ_FIND_HEATH_ROW}}"
PERSON = 86369
LI = "https://www.linkedin.com/in/pii-bffa9d4c"

ap = argparse.ArgumentParser()
ap.add_argument("--run", action="store_true", help="create + fire + deactivate")
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
        if e.code in (429, 500, 502, 503, 504) and att < 5:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:300]))
    except Exception:
        if att < 3:
            time.sleep(6)
            return n8n(path, method, body, att + 1)
        raise


PICK = r"""
// Report every candidate row with the fields that decide whether it is THE row: the identity, the
// reason that was written, and whether it is still active. No filtering by hand - print what the
// table holds and let the operator match it against the execution evidence.
const rows = $input.all().map(i => i.json).filter(r => r && r.id !== undefined);
return [{ json: {
  found: rows.length,
  rows: rows.map(r => ({
    id: r.id, identity_key: r.identity_key, status: r.status,
    reason: r.reason, entry_type: r.entry_type, reply_category: r.reply_category,
    correlation_id: r.correlation_id, pipedrive_person_id: r.pipedrive_person_id,
    linkedin_url_norm: r.linkedin_url_norm, email_lc: r.email_lc,
    added_at: r.added_at, expires_at: r.expires_at,
    removed_at: r.removed_at, removed_reason: r.removed_reason,
    also_flagged: r.also_flagged, source: r.source
  }))
} }];
"""

WF = {
    "name": "zz_find_heath_row",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": PATH, "responseMode": "responseNode",
                        "options": {}},
         "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [0, 0], "webhookId": "zzfindheathrow0001"},
        {"parameters": {"resource": "row", "operation": "get",
                        "dataTableId": {"__rl": True, "mode": "id", "value": REG},
                        "returnAll": True, "matchType": "anyCondition",
                        "filters": {"conditions": [
                            {"keyName": "pipedrive_person_id", "condition": "eq",
                             "keyValue": str(PERSON)},
                            {"keyName": "linkedin_url_norm", "condition": "eq", "keyValue": LI}]},
                        "options": {}},
         "name": "Find Rows", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [200, 0], "alwaysOutputData": True,
         "onError": "continueRegularOutput"},
        {"parameters": {"jsCode": PICK, "mode": "runOnceForAllItems"},
         "name": "Pick", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [400, 0]},
        {"parameters": {"options": {}}, "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [600, 0]},
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Find Rows", "type": "main", "index": 0}]]},
        "Find Rows": {"main": [[{"node": "Pick", "type": "main", "index": 0}]]},
        "Pick": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    },
    "settings": {"executionOrder": "v1"},
}

if not a.run:
    print("dry: would create workflow %r with one dataTable GET on %s" % (WF["name"], REG))
    print("filters: pipedrive_person_id eq %s  OR  linkedin_url_norm eq %s" % (PERSON, LI))
    print("re-run with --run")
    sys.exit(0)

existing = [w for w in (n8n("/api/v1/workflows?limit=250") or {}).get("data", [])
            if w["name"] == WF["name"]]
if existing:
    wid = existing[0]["id"]
    print("reusing %s" % wid)
    n8n("/api/v1/workflows/%s" % wid, "PUT", WF)
else:
    wid = n8n("/api/v1/workflows", "POST", WF)["id"]
    print("created %s" % wid)
n8n("/api/v1/workflows/%s/activate" % wid, "POST")
time.sleep(3)
try:
    req = urllib.request.Request(HOST + "/webhook/" + PATH, method="POST",
                                 data=json.dumps({}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180, context=ctx) as x:
        out = json.loads(x.read())
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
    with open(os.path.join(HERE, "heath_registry_rows.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n-> heath_registry_rows.json")
finally:
    n8n("/api/v1/workflows/%s/deactivate" % wid, "POST")
    print("deactivated %s (kept, registered in ONE_SHOT_TOOLS.md)" % wid)
