#!/usr/bin/env python3
"""Did the dev run actually execute? A 524 is Cloudflare's edge giving up on the RESPONSE, not n8n
aborting the run - and the unfiltered /executions list is known to under-report here, so this asks
per status instead of trusting one page.

READ ONLY."""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
SWEEP = "8qVXtI2ez5o6a9hc"
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, a=0):
    import time
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=180, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {"__err": str(e)[:120]}


found = {}
for st in (None, "success", "error", "waiting", "running", "canceled", "crashed", "new"):
    q = {"workflowId": SWEEP, "limit": 20}
    if st:
        q["status"] = st
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(q))
    rows = (d or {}).get("data")
    if rows is None:
        print("  status=%-9s -> %s" % (st or "(any)", json.dumps(d)[:110]))
        continue
    print("  status=%-9s -> %d" % (st or "(any)", len(rows)))
    for r in rows:
        found[r["id"]] = r

if not found:
    print("\nNO execution exists for the sweep under any status filter.")
    print("The 524 means the edge timed out; with zero executions recorded the run did not start,")
    print("or it was rejected before n8n created an execution record.")
    sys.exit(2)

print("\n=== executions found: %d ===" % len(found))
for r in sorted(found.values(), key=lambda x: str(x.get("startedAt"))):
    print("  id=%-8s status=%-10s started=%s stopped=%s" % (
        r.get("id"), r.get("status"), r.get("startedAt"), r.get("stoppedAt")))

newest = sorted(found.values(), key=lambda x: str(x.get("startedAt")))[-1]
full = n8n("/api/v1/executions/%s?includeData=true" % newest["id"])
rd = (((full or {}).get("data") or {}).get("resultData") or {})
run = rd.get("runData") or {}
print("\nnewest execution %s: status=%s nodes_run=%d" % (newest["id"], newest.get("status"),
                                                         len(run)))
if rd.get("error"):
    print("  ERROR: %s" % json.dumps(rd["error"], ensure_ascii=False)[:400])
if rd.get("lastNodeExecuted"):
    print("  lastNodeExecuted: %s" % rd["lastNodeExecuted"])

WANT = ("PD Get Candidates", "PD Filter Pending", "PD Limit Chunk", "PD Get Leads By Person",
        "PD Classify", "PD Aggregate", "SL Get Candidates", "SL Filter Pending",
        "SL Resolve By Email", "SL Classify", "SL Aggregate", "HR Get Candidates",
        "HR Count Pending", "Combine Summaries", "Send Guard", "Dev Summary")
print("\n=== per-node output ===")
for nm in WANT:
    if nm not in run:
        print("  %-26s did not run" % nm[:26])
        continue
    try:
        items = run[nm][0]["data"]["main"][0] or []
    except Exception:
        print("  %-26s ran, no output captured" % nm[:26])
        continue
    print("  %-26s items=%d" % (nm[:26], len(items)))
    for it in items[:2]:
        j = it.get("json") or {}
        small = {k: (v if not isinstance(v, (list, dict)) or len(json.dumps(v)) < 400
                     else "<%s len=%d>" % (type(v).__name__, len(v)))
                 for k, v in j.items()}
        print("      %s" % json.dumps(small, ensure_ascii=False)[:1400])

with open(os.path.join(HERE, "sweep_dev_exec_%s.json" % newest["id"]), "w",
          encoding="utf-8") as f:
    json.dump({"exec": newest, "nodes": sorted(run),
               "error": rd.get("error"), "last": rd.get("lastNodeExecuted")}, f,
              ensure_ascii=False, indent=1)
print("\nevidence -> sweep_dev_exec_%s.json" % newest["id"])
