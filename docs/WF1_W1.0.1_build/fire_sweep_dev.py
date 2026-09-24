#!/usr/bin/env python3
"""ITEM 3, step one: a DEV run of `dnc_projections_sweep` to obtain the CURRENT count.

Not a projection. `check_sweep_dev_is_dark.py` proved all seven mutating nodes - both Pipedrive
PATCHes, the Smartlead unsubscribe, and all four `Mark Done` / `Mark Write Error` dataTable writes -
are reachable only through a FIRE_ gate's true branch, and both gates are false. The single side
effect is the workflow's own `Dev Summary` Slack post, into its guarded dev channel.

Why a run and not arithmetic: the ~564 was measured on 2 Sep, the registry is not readable over
REST (404 on every route shape tried), and the DNC-686 population is confirmed only to 27-28 Aug.
A §9f.2 pre-post states the CURRENT count or it is not a pre-post.
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
HOST = BASE.split("/api/")[0].rstrip("/")
SWEEP = "8qVXtI2ez5o6a9hc"
HERE = os.path.dirname(os.path.abspath(__file__))


def n8n(p, a=0):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + p, headers={"X-N8N-API-KEY": KEY}), timeout=300, context=ctx) as x:
            return json.load(x)
    except Exception:
        if a < 4:
            time.sleep(6)
            return n8n(p, a + 1)
        raise


before = (n8n("/api/v1/executions?workflowId=%s&limit=5" % SWEEP) or {}).get("data") or []
print("executions in retention before the run: %d" % len(before))

url = HOST + "/webhook/{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}"
print("POST %s" % url)
t0 = time.time()
req = urllib.request.Request(url, method="POST", data=json.dumps({"source": "dev-count"}).encode(),
                             headers={"Content-Type": "application/json",
                                      "User-Agent": "janea/1.0"})
body, status = None, None
try:
    with urllib.request.urlopen(req, timeout=900, context=ctx) as x:
        status = x.status
        body = x.read().decode("utf-8", "replace")
except urllib.error.HTTPError as e:
    status = e.code
    body = e.read().decode("utf-8", "replace")
except Exception as e:
    status = "ERR"
    body = str(e)
dt = time.time() - t0
print("HTTP %s in %.1fs" % (status, dt))
print("--- response ---")
try:
    print(json.dumps(json.loads(body), ensure_ascii=False, indent=1)[:4000])
except Exception:
    print((body or "")[:4000])

# The response is what the workflow chose to return; the EXECUTION is what it actually computed.
# Read both - a pre-post number that came only from a response body has been wrong here before.
time.sleep(6)
after = (n8n("/api/v1/executions?workflowId=%s&limit=5" % SWEEP) or {}).get("data") or []
print("\nexecutions in retention after: %d" % len(after))
if not after:
    print("no execution recorded - nothing further to read")
    sys.exit(0)
ex = after[0]
print("execution %s  status=%s  started=%s" % (ex.get("id"), ex.get("status"),
                                               ex.get("startedAt")))
full = n8n("/api/v1/executions/%s?includeData=true" % ex["id"])
run = (((full or {}).get("data") or {}).get("resultData") or {}).get("runData") or {}
print("nodes that ran: %d" % len(run))

WANT = ("PD Get Candidates", "PD Filter Pending", "PD Limit Chunk", "PD Classify", "PD Aggregate",
        "SL Get Candidates", "SL Filter Pending", "SL Classify", "SL Aggregate",
        "HR Get Candidates", "HR Count Pending", "Combine Summaries", "Send Guard")
print("\n=== the counts, per node ===")
for nm in WANT:
    if nm not in run:
        print("  %-26s DID NOT RUN" % nm[:26])
        continue
    try:
        items = run[nm][0]["data"]["main"][0] or []
    except Exception:
        print("  %-26s (no output captured)" % nm[:26])
        continue
    print("  %-26s items=%d" % (nm[:26], len(items)))
    if items and len(items) <= 2:
        for it in items:
            j = it.get("json") or {}
            small = {k: v for k, v in j.items()
                     if not isinstance(v, (list, dict)) or len(json.dumps(v)) < 300}
            print("      %s" % json.dumps(small, ensure_ascii=False)[:1200])

out = os.path.join(HERE, "sweep_dev_run_%s.json" % ex["id"])
with open(out, "w", encoding="utf-8") as f:
    json.dump({"execution": ex, "response": body, "runData_nodes": sorted(run)}, f,
              ensure_ascii=False, indent=1)
print("\nevidence -> %s" % os.path.basename(out))
