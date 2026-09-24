#!/usr/bin/env python3
"""FIRE_PIPEDRIVE — window 1 of 3. Nik confirmed on the measured count (580 pending, 250 this run).

  MODE dev -> live, FIRE_PIPEDRIVE false -> true, FIRE_SMARTLEAD stays FALSE (explicitly ruled),
  fire the webhook, wait for the execution, then put CONFIG BACK - in a finally, so a crash or a
  timeout in this script cannot leave the sweep armed. Nothing else can trigger it (webhook-only,
  no schedule), but an armed live config is not a state to leave lying around.

Pre-write baseline: `baseline_686_before_window1.json`, 580/580 persons captured, **none already
686** - so the expected delta is exactly the number of successful writes, and rollback is a replay
of that file.

Guard rails on this script itself:
  * refuses to run unless the baseline file is complete (580 rows, 0 read errors)
  * refuses to run unless the DRY RUN marker and the label-union shape guard are live
  * asserts FIRE_SMARTLEAD is false in the body it PUTs, not merely in the body it read
"""
import copy
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from n8n_deploy_util import put_body, stripped_keys

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
HOST = BASE.split("/api/")[0].rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
SWEEP = "8qVXtI2ez5o6a9hc"


def n8n(path, method="GET", body=None, att=0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=300, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        if e.code in (401, 429, 500, 502, 503, 504) and att < 6:
            time.sleep(10)
            return n8n(path, method, body, att + 1)
        raise SystemExit("n8n %s %s: HTTP %s %s" % (method, path, e.code, e.read()[:200]))
    except Exception:
        if att < 4:
            time.sleep(8)
            return n8n(path, method, body, att + 1)
        raise


def code_only(js):
    return "\n".join(re.sub(r"//.*$", "", l) for l in js.splitlines()
                     if not l.strip().startswith("//"))


# ---------------------------------------------------------------- guard rails
bl_path = os.path.join(HERE, "baseline_686_before_window1.json")
bl = json.load(open(bl_path, encoding="utf-8"))
if len(bl["rows"]) != len(bl["pending_ids"]) or bl["read_errors"]:
    sys.exit("baseline incomplete (%d/%d rows, %d errors) - refusing to fire"
             % (len(bl["rows"]), len(bl["pending_ids"]), len(bl["read_errors"])))
print("baseline: %d/%d persons, already-686=%d, chunk1=%d"
      % (len(bl["rows"]), len(bl["pending_ids"]), bl["already_686"], len(bl["chunk1_ids"])))

wf = n8n("/api/v1/workflows/%s" % SWEEP)
ORIG = copy.deepcopy(wf)
N = {n["name"]: n for n in wf["nodes"]}
if "DRY RUN" not in code_only(N["Combine Summaries"]["parameters"]["jsCode"]):
    sys.exit("dry-run marker not live - Nik required it BEFORE this fire")
if "unrecognised" not in code_only(N["PD Label Union"]["parameters"]["jsCode"]):
    sys.exit("label-union shape guard not live - refusing to write labels without it")

asg = N["CONFIG"]["parameters"]["assignments"]["assignments"]
by = {a["name"]: a for a in asg}
print("CONFIG before: MODE=%r FIRE_PIPEDRIVE=%r FIRE_SMARTLEAD=%r"
      % (by["MODE"]["value"], by["FIRE_PIPEDRIVE"]["value"], by["FIRE_SMARTLEAD"]["value"]))


def set_cfg(mode, fire_pd):
    by["MODE"]["value"] = mode
    by["FIRE_PIPEDRIVE"]["value"] = fire_pd
    by["FIRE_SMARTLEAD"]["value"] = False          # ruled: stays false
    if by["FIRE_SMARTLEAD"]["value"] is not False:
        raise SystemExit("refusing: FIRE_SMARTLEAD would not be false")
    n8n("/api/v1/workflows/%s" % SWEEP, "PUT", put_body(wf))
    after = n8n("/api/v1/workflows/%s" % SWEEP)
    a2 = {a["name"]: a["value"] for a in
          next(n for n in after["nodes"] if n["name"] == "CONFIG")
          ["parameters"]["assignments"]["assignments"]}
    print("  CONFIG now: MODE=%r FIRE_PIPEDRIVE=%r FIRE_SMARTLEAD=%r  active=%s version=%s"
          % (a2.get("MODE"), a2.get("FIRE_PIPEDRIVE"), a2.get("FIRE_SMARTLEAD"),
             after.get("active"), str(after.get("versionId"))[:8]))
    if a2.get("FIRE_SMARTLEAD") is not False:
        raise SystemExit("FIRE_SMARTLEAD is not false after the PUT - ABORT")
    if not after.get("active"):
        raise SystemExit("sweep went INACTIVE after the PUT - ABORT")
    return a2


stamp = int(datetime.now(timezone.utc).timestamp())
with open(os.path.join(HERE, "sweep_backup_before_window1_%d.json" % stamp), "w",
          encoding="utf-8") as f:
    f.write(json.dumps(ORIG, indent=2, ensure_ascii=False))
print("workflow backup: sweep_backup_before_window1_%d.json" % stamp)
sk = stripped_keys(wf)
if sk:
    print("stripped UI-only settings keys: %s" % sk)

before_ids = set()
for st in ("success", "error", "running", "canceled", "waiting"):
    d = n8n("/api/v1/executions?" + urllib.parse.urlencode(
        {"workflowId": SWEEP, "status": st, "limit": 40}))
    before_ids |= {str(r["id"]) for r in ((d or {}).get("data") or [])}

exec_id = None
try:
    print("\n--- ARMING ---")
    set_cfg("live", True)

    print("\n--- FIRING ---")
    url = HOST + "/webhook/{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}"
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url, method="POST", data=json.dumps({"source": "window1-live"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "janea/1.0"})
        with urllib.request.urlopen(req, timeout=130, context=ctx) as x:
            print("  HTTP %s in %.0fs" % (x.status, time.time() - t0))
    except Exception as e:
        # a 524 is the edge giving up on the response; the run continues server-side
        print("  edge returned %s after %.0fs (expected - Respond is the last node)"
              % (str(e)[:60], time.time() - t0))

    print("\n--- WAITING for the execution ---")
    deadline = time.time() + 50 * 60
    last = None
    while time.time() < deadline:
        cur = {}
        for st in ("running", "success", "error", "canceled", "waiting"):
            d = n8n("/api/v1/executions?" + urllib.parse.urlencode(
                {"workflowId": SWEEP, "status": st, "limit": 40}))
            for r in ((d or {}).get("data") or []):
                if str(r["id"]) not in before_ids:
                    cur[str(r["id"])] = (st, r)
        if cur:
            eid, (st, row) = sorted(cur.items())[-1]
            exec_id = eid
            if st != last:
                print("  [%s] exec %s -> %s" % (time.strftime("%H:%M:%S"), eid, st), flush=True)
                last = st
            if st != "running":
                break
        time.sleep(30)
    print("  final: exec %s status=%s" % (exec_id, last))
finally:
    print("\n--- DISARMING (always) ---")
    try:
        set_cfg("dev", False)
    except SystemExit as e:
        print("  !! DISARM FAILED: %s" % e)
        print("  !! restore by PUTting sweep_backup_before_window1_%d.json" % stamp)
        raise

if not exec_id:
    sys.exit("no execution appeared - nothing to verify")

full = n8n("/api/v1/executions/%s?includeData=true" % exec_id)
rd = (((full or {}).get("data") or {}).get("resultData") or {})
run = rd.get("runData") or {}
print("\n=== execution %s: %d nodes ran ===" % (exec_id, len(run)))
if rd.get("error"):
    print("ERROR: %s" % json.dumps(rd["error"], ensure_ascii=False)[:500])
if rd.get("lastNodeExecuted"):
    print("lastNodeExecuted: %s" % rd["lastNodeExecuted"])


def items(nm):
    try:
        return [i.get("json") or {} for i in (run[nm][0]["data"]["main"][0] or [])]
    except Exception:
        return []


for nm in ("PD Filter Pending", "PD Limit Chunk", "PD Write DNC Field", "PD Get Lead For Labels",
           "PD Label Union", "PD Patch Lead Labels", "PD Mark Done (with lead)",
           "PD Mark Done (no lead)", "PD Mark Write Error", "PD Count Write Errors",
           "PD Aggregate", "Combine Summaries", "Dev Summary"):
    its = items(nm)
    print("  %-28s items=%d%s" % (nm[:28], len(its), "" if nm in run else "   (did not run)"))

written = [r for r in items("PD Write DNC Field")]
print("\nPD Write DNC Field responses: %d" % len(written))
ok_w = sum(1 for r in written if r.get("success") is True or (r.get("data") or {}).get("id"))
print("  looked successful: %d" % ok_w)
cs = items("Combine Summaries")
if cs:
    print("\nsummary posted:\n  " + str(cs[0].get("slack_text", "")).replace("\n", "\n  "))
    print("  mode=%r dry_run=%r" % (cs[0].get("mode"), cs[0].get("dry_run")))

out = os.path.join(HERE, "window1_exec_%s.json" % exec_id)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"exec": exec_id, "status": last, "error": rd.get("error"),
               "nodes": {k: len(items(k)) for k in run},
               "write_responses": written[:400],
               "summary": cs[0] if cs else None}, f, ensure_ascii=False, indent=1)
print("\n-> %s" % os.path.basename(out))
