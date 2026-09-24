#!/usr/bin/env python3
"""Is `claim_key` actually unique in wf_claims - and is upsert atomic under CONCURRENCY?

Nik could not find the constraint in the UI and asked me to verify rather than assume. The
data-table REST API is not exposed to our key (404), so the only way to touch the table is through a
dataTable NODE. Hence a throwaway workflow used as a probe, deleted at the end.

TWO questions, and the second is the one that matters:
  A. FUNCTIONAL - two SEQUENTIAL upserts with the same claim_key: 1 row or 2?
  B. ATOMIC     - N CONCURRENT upserts with the same claim_key: still 1 row, or several?

Only B decides the migration. If concurrent upserts each insert, then n8n's upsert is
match-then-write in the client and we have rebuilt the staticData race in a new store - the whole
premise of the atomic-claims table fails and the design must change to insert-only semantics
relying on a DB constraint.

Creates `zz_wf_claims_probe`, uses it, DELETES it. Writes only rows whose claim_key starts with
ZZPROBE- so nothing real is touched.
"""
import argparse, json, os, ssl, sys, threading, time, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
TABLE = "euyostwJYfJefItC"
PATH = "zz-claims-probe-8f21"
TAG = "ZZPROBE-" + datetime.now(timezone.utc).strftime("%H%M%S")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=120, context=ctx) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300].decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)[:200]


def hook(payload, timeout=60):
    url = f"{BASE.replace('/api/v1', '')}/webhook/{PATH}"
    r = urllib.request.Request(url, method="POST", data=json.dumps(payload).encode(),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout, context=ctx) as x:
            return x.status, x.read()[:900].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400].decode("utf-8", "replace")
    except Exception as e:
        return -1, str(e)[:200]


NODES = [
    # `webhookId` is what n8n uses to register the PRODUCTION route. Both working webhooks in this
    # instance (WF-1, WF-2) carry it set equal to `path`; my first probe omitted it and the path
    # never published, which read as "activation is slow" and was actually "never going to happen".
    {"parameters": {"httpMethod": "POST", "path": PATH, "responseMode": "lastNode",
                    "options": {"rawBody": False}},
     "id": "aaaa1111-0000-4000-8000-000000000001", "name": "Webhook",
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "webhookId": PATH,
     "position": [0, 0]},
    {"parameters": {"resource": "row", "operation": "upsert",
                    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
                    "matchType": "allConditions",
                    "filters": {"conditions": [
                        {"keyName": "claim_key", "condition": "eq",
                         "keyValue": "={{ $json.body.k }}"}]},
                    "columns": {"mappingMode": "defineBelow", "value": {
                        "claim_key": "={{ $json.body.k }}",
                        "family": "probe",
                        "workflow": "={{ $json.body.w }}"}},
                    "options": {}},
     "id": "aaaa1111-0000-4000-8000-000000000002", "name": "Upsert",
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [220, 0],
     "onError": "continueRegularOutput"},
    {"parameters": {"resource": "row", "operation": "get",
                    "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
                    "returnAll": True, "matchType": "allConditions",
                    "filters": {"conditions": [
                        {"keyName": "claim_key", "condition": "eq",
                         "keyValue": "={{ $('Webhook').item.json.body.k }}"}]},
                    "options": {}},
     "id": "aaaa1111-0000-4000-8000-000000000003", "name": "Readback",
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [440, 0],
     "onError": "continueRegularOutput"},
    {"parameters": {"jsCode": "const rows = $input.all().map(i => i.json);\n"
                              "return [{ json: { rows: rows.length,\n"
                              "  keys: rows.map(r => r.claim_key || null),\n"
                              "  sample: rows[0] || null } }];"},
     "id": "aaaa1111-0000-4000-8000-000000000004", "name": "Count",
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 0]},
]
CONNS = {"Webhook": {"main": [[{"node": "Upsert", "type": "main", "index": 0}]]},
         "Upsert": {"main": [[{"node": "Readback", "type": "main", "index": 0}]]},
         "Readback": {"main": [[{"node": "Count", "type": "main", "index": 0}]]}}

ap = argparse.ArgumentParser()
ap.add_argument("--run", action="store_true")
a = ap.parse_args()
if not a.run:
    print("probe workflow to be created:", json.dumps([n["name"] for n in NODES]))
    print(f"table={TABLE} path={PATH} tag={TAG}")
    print("\n--run not given: nothing created.")
    sys.exit(0)

print("1. creating throwaway probe workflow")
st, wf = n8n("/api/v1/workflows", "POST", {"name": "zz_wf_claims_probe_DELETE_ME",
                                           "nodes": NODES, "connections": CONNS,
                                           "settings": {"executionOrder": "v1"}})
print(f"   create: HTTP {st} id={wf.get('id') if isinstance(wf, dict) else wf}")
if not isinstance(wf, dict) or not wf.get("id"):
    sys.exit("could not create the probe workflow")
WID = wf["id"]
try:
    st, _ = n8n(f"/api/v1/workflows/{WID}/activate", "POST", {})
    print(f"   activate: HTTP {st}")
    # n8n Cloud publishes the production webhook a few seconds AFTER activate returns 200. A fixed
    # 6s sleep was not enough and every call 404'd - so wait for the path to actually answer rather
    # than assuming a duration. Probe with a harmless payload until it stops 404ing.
    print("   waiting for the webhook path to register...")
    ready = False
    for i in range(20):
        time.sleep(5)
        s, b = hook({"k": TAG + "-WARMUP", "w": "warmup"}, timeout=30)
        if s != 404:
            ready = True
            print(f"   registered after ~{(i + 1) * 5}s (HTTP {s})")
            break
    if not ready:
        raise SystemExit("webhook never registered - aborting before drawing any conclusion")

    print("\n2. FUNCTIONAL - two SEQUENTIAL upserts, same claim_key")
    k1 = TAG + "-SEQ"
    for i in (1, 2):
        st, body = hook({"k": k1, "w": f"seq{i}"})
        print(f"   call {i}: HTTP {st}  {body[:200]}")
        time.sleep(2)

    print("\n3. ATOMIC - 6 CONCURRENT upserts, same claim_key  <-- the decisive test")
    k2 = TAG + "-CONC"
    out = []
    def fire(n):
        out.append(hook({"k": k2, "w": f"conc{n}"}))
    ths = [threading.Thread(target=fire, args=(i,)) for i in range(6)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    for i, (s, b) in enumerate(out):
        print(f"   concurrent {i}: HTTP {s}  {str(b)[:150]}")
    time.sleep(5)
    st, final = hook({"k": k2, "w": "final-readback"})
    print(f"\n   FINAL readback for {k2}: {str(final)[:400]}")
finally:
    print("\n4. cleanup")
    st, _ = n8n(f"/api/v1/workflows/{WID}/deactivate", "POST", {})
    st2, _ = n8n(f"/api/v1/workflows/{WID}", "DELETE")
    print(f"   deactivate HTTP {st}   delete HTTP {st2}")
    print(f"   NOTE: probe rows tagged {TAG} remain in wf_claims - delete them in the UI,")
    print("   or leave them: they are inert and the migration's exclusion list ignores them.")
