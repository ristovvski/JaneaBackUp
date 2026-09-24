#!/usr/bin/env python3
"""Wait for sweep execution 48563 to leave `running`, then dump its counts. READ ONLY.

Polls `status=running` explicitly: the UNFILTERED /executions list returned 0 for this very
execution while it was live, which is the documented under-reporting defect. Absence from the
default list is not evidence that a run finished, or that it ever started.
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
SWEEP = "8qVXtI2ez5o6a9hc"
EXEC = sys.argv[1] if len(sys.argv) > 1 else "48563"
HERE = os.path.dirname(os.path.abspath(__file__))
DEADLINE = time.time() + 55 * 60


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=120, context=ctx) as x:
            return json.load(x)
    except Exception as e:
        if a < 3:
            time.sleep(5)
            return n8n(p, a + 1)
        return {"__err": str(e)[:120]}


def state():
    for st in ("running", "success", "error", "canceled", "waiting"):
        d = n8n("/api/v1/executions?" + urllib.parse.urlencode(
            {"workflowId": SWEEP, "status": st, "limit": 20}))
        for r in ((d or {}).get("data") or []):
            if str(r.get("id")) == str(EXEC):
                return st, r
    return None, None


last = None
while time.time() < DEADLINE:
    st, row = state()
    if st != last:
        print("[%s] %s -> %s" % (time.strftime("%H:%M:%S"), EXEC, st), flush=True)
        last = st
    if st and st != "running":
        break
    if st is None:
        print("[%s] %s not found under any status - stopping" % (time.strftime("%H:%M:%S"), EXEC),
              flush=True)
        break
    time.sleep(30)

st, row = state()
print("\nfinal status: %s" % st)
if row:
    print("started=%s stopped=%s" % (row.get("startedAt"), row.get("stoppedAt")))

full = n8n("/api/v1/executions/%s?includeData=true" % EXEC)
rd = (((full or {}).get("data") or {}).get("resultData") or {})
run = rd.get("runData") or {}
print("nodes run: %d" % len(run))
if rd.get("error"):
    print("ERROR: %s" % json.dumps(rd["error"], ensure_ascii=False)[:600])
if rd.get("lastNodeExecuted"):
    print("lastNodeExecuted: %s" % rd["lastNodeExecuted"])

WANT = ("PD Get Candidates", "PD Filter Pending", "PD Limit Chunk", "PD Get Leads By Person",
        "PD Classify", "PD Aggregate", "SL Get Candidates", "SL Filter Pending",
        "SL Resolve By Email", "SL Classify", "SL Aggregate", "HR Get Candidates",
        "HR Count Pending", "Combine Summaries", "Send Guard", "Dev Summary", "Respond")
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
        small = {k: (v if not isinstance(v, (list, dict)) or len(json.dumps(v)) < 500
                     else "<%s len=%d>" % (type(v).__name__, len(v)))
                 for k, v in j.items()}
        print("      %s" % json.dumps(small, ensure_ascii=False)[:1600])

with open(os.path.join(HERE, "sweep_dev_counts_%s.json" % EXEC), "w", encoding="utf-8") as f:
    json.dump({"status": st, "row": row, "error": rd.get("error"),
               "last": rd.get("lastNodeExecuted"),
               "nodes": {k: len(((v[0].get("data") or {}).get("main") or [[]])[0] or [])
                         for k, v in run.items() if v},
               "aggregates": {nm: [i.get("json") for i in
                                   (run[nm][0]["data"]["main"][0] or [])[:3]]
                              for nm in ("PD Aggregate", "SL Aggregate", "HR Count Pending",
                                         "Combine Summaries")
                              if nm in run}}, f, ensure_ascii=False, indent=1)
print("\nevidence -> sweep_dev_counts_%s.json" % EXEC)
