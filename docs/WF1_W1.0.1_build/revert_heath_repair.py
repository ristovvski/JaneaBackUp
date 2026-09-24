#!/usr/bin/env python3
"""REVERT the Person-8768306e repair. He is a real responder - an attachment with no text.

Restores exactly what `heath_repair_baseline.json` recorded before the repair:
  1. registry row 33166 -> status active, removed_at null, removed_reason null
  2. lead 987d0600 -> the original label set (3. Responded back)
  3. activity 46415 -> the original note, prefix removed
  4. task 46416 -> untouched (it was already closed BEFORE the repair; the repair did not change it,
     so restoring it to "done" is restoring it to what it was)

The registry row is un-tombstoned through a one-shot driver, because the retirement workflow only
removes - there is no reactivate path, which is worth noting as its own gap.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request

PDT = os.environ["PIPEDRIVE_API_TOKEN"]
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HOST = BASE.split("/api/")[0].rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
REG = "UOgKwlGsL28lX61O"
ROW_ID = 33166
LEAD = "987d0600-ac44-11f1-926c-6949d156b78a"
ACTIVITY = 46415
PATH = "{{WEBHOOK_ZZ_UNTOMBSTONE_HEATH}}"

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
a = ap.parse_args()
print("MODE: %s" % ("LIVE" if a.live else "DRY RUN"))

bl = json.load(open(os.path.join(HERE, "heath_repair_baseline.json"), encoding="utf-8"))
print("baseline: labels=%s  note_len=%d  task_done=%r"
      % (bl.get("lead_label_ids"), len(str(bl.get("activity_note") or "")), bl.get("task_done")))


def pd(p, method="GET", body=None, att=0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request("https://api.pipedrive.com" + p, method=method, data=data,
                               headers={"x-api-token": PDT, "Content-Type": "application/json",
                                        "User-Agent": "janea/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and att < 4:
            time.sleep(4)
            return pd(p, method, body, att + 1)
        return {"__err": "HTTP %s %s" % (e.code, e.read()[:200].decode("utf-8", "replace"))}
    except Exception as e:
        return {"__err": str(e)[:140]}


def n8n(path, method="GET", body=None, att=0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (429, 500, 502, 503, 504) and att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:300]))
    except Exception:
        if att < 3:
            time.sleep(6)
            return n8n(path, method, body, att + 1)
        raise


# ---------------------------------------------------------------- 1. registry
READBACK = r"""
const rows = $input.all().map(i => i.json).filter(r => r && r.id !== undefined);
return [{ json: { found: rows.length, rows: rows.map(r => ({
  id: r.id, status: r.status, reason: r.reason, removed_at: r.removed_at,
  removed_reason: r.removed_reason, expires_at: r.expires_at,
  identity_key: r.identity_key, correlation_id: r.correlation_id })) } }];
"""
WF = {
    "name": "zz_untombstone_heath",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": PATH, "responseMode": "responseNode",
                        "options": {}},
         "name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1,
         "position": [0, 0], "webhookId": "zzuntombheath00001"},
        {"parameters": {"resource": "row", "operation": "update",
                        "dataTableId": {"__rl": True, "mode": "id", "value": REG},
                        "matchType": "allConditions",
                        "filters": {"conditions": [
                            {"keyName": "id", "condition": "eq", "keyValue": str(ROW_ID)}]},
                        "columns": {"mappingMode": "defineBelow", "value": {
                            "status": "active",
                            "removed_at": "={{ null }}",
                            "removed_reason": "={{ null }}"}},
                        "options": {}},
         "name": "Reactivate", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [200, 0]},
        {"parameters": {"resource": "row", "operation": "get",
                        "dataTableId": {"__rl": True, "mode": "id", "value": REG},
                        "returnAll": True, "matchType": "allConditions",
                        "filters": {"conditions": [
                            {"keyName": "id", "condition": "eq", "keyValue": str(ROW_ID)}]},
                        "options": {}},
         "name": "Read Back", "type": "n8n-nodes-base.dataTable", "typeVersion": 1,
         "position": [400, 0], "alwaysOutputData": True},
        {"parameters": {"jsCode": READBACK, "mode": "runOnceForAllItems"},
         "name": "Pick", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600, 0]},
        {"parameters": {"options": {}}, "name": "Respond",
         "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [800, 0]},
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Reactivate", "type": "main", "index": 0}]]},
        "Reactivate": {"main": [[{"node": "Read Back", "type": "main", "index": 0}]]},
        "Read Back": {"main": [[{"node": "Pick", "type": "main", "index": 0}]]},
        "Pick": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    },
    "settings": {"executionOrder": "v1"},
}

print("\n--- 1. registry row %d -> active ---" % ROW_ID)
if not a.live:
    print("  would create %r and set status=active, removed_at=null, removed_reason=null"
          % WF["name"])
else:
    existing = [w for w in (n8n("/api/v1/workflows?limit=250") or {}).get("data", [])
                if w["name"] == WF["name"]]
    if existing:
        wid = existing[0]["id"]
        n8n("/api/v1/workflows/%s" % wid, "PUT", WF)
    else:
        wid = n8n("/api/v1/workflows", "POST", WF)["id"]
    print("  driver %s" % wid)
    n8n("/api/v1/workflows/%s/activate" % wid, "POST")
    time.sleep(3)
    try:
        req = urllib.request.Request(HOST + "/webhook/" + PATH, method="POST",
                                     data=json.dumps({}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180, context=ctx) as x:
            out = json.loads(x.read())
        print("  read-back: %s" % json.dumps(out, ensure_ascii=False)[:500])
    finally:
        n8n("/api/v1/workflows/%s/deactivate" % wid, "POST")
        print("  driver deactivated (kept)")

# ---------------------------------------------------------------- 2. label
print("\n--- 2. lead labels ---")
want = bl.get("lead_label_ids") or []
cur = ((pd("/v1/leads/%s" % LEAD) or {}).get("data") or {}).get("label_ids") or []
print("  current=%s\n  baseline=%s" % (cur, want))
if sorted(cur) == sorted(want):
    print("  already matches baseline")
elif not a.live:
    print("  would PATCH label_ids back to the baseline set")
else:
    r = pd("/v1/leads/%s" % LEAD, "PATCH", {"label_ids": want})
    print("  -> %s" % ("ok" if r.get("success") else json.dumps(r)[:200]))

# ---------------------------------------------------------------- 3. activity note
print("\n--- 3. activity %d note ---" % ACTIVITY)
base_note = bl.get("activity_note")
cur_note = str(((pd("/api/v2/activities/%d" % ACTIVITY) or {}).get("data") or {}).get("note") or "")
print("  current  (%d chars): %r" % (len(cur_note), cur_note[:80]))
print("  baseline (%d chars): %r" % (len(str(base_note or "")), str(base_note or "")[:80]))
if cur_note == (base_note or ""):
    print("  already matches baseline")
elif not a.live:
    print("  would PATCH the note back to the baseline value")
else:
    r = pd("/api/v2/activities/%d" % ACTIVITY, "PATCH", {"note": base_note or ""})
    print("  -> %s" % ("ok" if r.get("success") else json.dumps(r)[:200]))

if not a.live:
    print("\nDRY RUN - nothing written. Re-run with --live.")
    sys.exit(0)

print("\n" + "=" * 70)
print("VERIFY")
print("=" * 70)
time.sleep(2)
lead2 = (pd("/v1/leads/%s" % LEAD) or {}).get("data") or {}
act2 = (pd("/api/v2/activities/%d" % ACTIVITY) or {}).get("data") or {}
labels = {x["id"]: x["name"] for x in ((pd("/v1/leadLabels") or {}).get("data") or [])}
checks = [
    ("label set matches baseline",
     sorted(lead2.get("label_ids") or []) == sorted(want)),
    ("`3. Responded` is back",
     "c9d4b550-bcf3-11ef-a843-357f91e826ec" in (lead2.get("label_ids") or [])),
    ("activity note matches baseline", str(act2.get("note") or "") == (base_note or "")),
    ("activity prefix gone", not str(act2.get("note") or "").startswith("[false reply")),
]
allok = True
for lbl, good in checks:
    print("  [%s] %s" % ("ok " if good else "FAIL", lbl))
    allok = allok and good
print("\n  lead labels now: %s" % [labels.get(x, x) for x in (lead2.get("label_ids") or [])])
print("\n=== %s ===" % ("REVERT CLEAN" if allok else "REVERT HAS PROBLEMS"))
sys.exit(0 if allok else 1)
