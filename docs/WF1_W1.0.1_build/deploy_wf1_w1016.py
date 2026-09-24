"""Deploy W1.0.16 to WF-1 under the quiet-window rule.

  pre-check: live versionId is still the baseline (nobody else changed it), no execution running,
             nothing in the last QUIET_MIN minutes
  deploy   : deactivate -> PUT -> activate -> verify active + node count + fresh versionId
  PUT sends only {name, nodes, connections, settings}, and `settings` is filtered to the keys the
  API accepts (timeSavedMode / availableInMCP are UI-only and make it 400).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
WF1 = os.environ["WF1_ID"]
KEY = os.environ["N8N_API_KEY"]
PATCHED = os.path.join(HERE, "WF-1 HeyReach Receiver - W1.0.16 patched.json")
EXPECT_BASE_VERSION = "c1292c4b-86dc-426c-8be1-55281515c39f"
EXPECT_NODES = 110
QUIET_MIN = 4
SETTINGS_OK = {"executionOrder", "saveManualExecutions", "callerPolicy", "errorWorkflow",
               "saveDataErrorExecution", "saveDataSuccessExecution", "saveExecutionProgress",
               "executionTimeout", "timezone"}


def api(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"X-N8N-API-KEY": KEY,
                                        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(r, timeout=180) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:600]


print("=" * 92)
print("PRE-CHECK")
print("=" * 92)
st, live = api(f"/api/v1/workflows/{WF1}")
print(f"  live versionId : {live.get('versionId')}")
print(f"  live nodes     : {len(live.get('nodes') or [])}  active={live.get('active')}")
if live.get("versionId") != EXPECT_BASE_VERSION:
    sys.exit(f"ABORT: live version is {live.get('versionId')}, expected the baseline "
             f"{EXPECT_BASE_VERSION}. Someone else changed WF-1 - re-diff before deploying.")

st, ex = api(f"/api/v1/executions?workflowId={WF1}&limit=20")
rows = (ex or {}).get("data") or []
running = [r for r in rows if r.get("status") == "running" or not r.get("stoppedAt")]
now = datetime.now(timezone.utc)
recent = []
for r in rows:
    s = r.get("startedAt")
    if not s:
        continue
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if (now - t).total_seconds() < QUIET_MIN * 60:
        recent.append((r["id"], s, r.get("status")))
print(f"  executions retained: {len(rows)}; running now: {len(running)}")
print(f"  started in the last {QUIET_MIN} min: {len(recent)} {recent[:4]}")
if rows:
    print(f"  newest execution: {rows[0].get('startedAt')} status={rows[0].get('status')}")
if running or recent:
    sys.exit("ABORT: not a quiet window (execution in flight or very recent). Retry shortly.")

backup = os.path.join(HERE, f"wf1_backup_before_w1016_{int(time.time())}.json")
json.dump(live, open(backup, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"  backup written : {backup}")

wf = json.load(open(PATCHED, encoding="utf-8"))
assert len(wf["nodes"]) == EXPECT_NODES, len(wf["nodes"])
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
           "settings": settings}
print(f"  settings sent  : {sorted(settings)}")

print("\n" + "=" * 92)
print("DEPLOY")
print("=" * 92)
st, r = api(f"/api/v1/workflows/{WF1}/deactivate", "POST")
print(f"  deactivate -> {st}")
if st >= 300:
    sys.exit(f"ABORT before PUT: {r}")

st, r = api(f"/api/v1/workflows/{WF1}", "PUT", payload)
print(f"  PUT        -> {st}")
if st >= 300:
    print(f"  PUT FAILED: {r}")
    st2, r2 = api(f"/api/v1/workflows/{WF1}/activate", "POST")
    print(f"  re-activated baseline -> {st2}")
    sys.exit("ABORT: PUT rejected; workflow left on the baseline and re-activated.")

st, r = api(f"/api/v1/workflows/{WF1}/activate", "POST")
print(f"  activate   -> {st}")

print("\n" + "=" * 92)
print("VERIFY")
print("=" * 92)
st, after = api(f"/api/v1/workflows/{WF1}")
names = {n["name"] for n in after.get("nodes") or []}
ok = True
print(f"  versionId : {after.get('versionId')}  (was {EXPECT_BASE_VERSION})")
print(f"  nodes     : {len(after.get('nodes') or [])}  active={after.get('active')}")
for pre in ("", "M5 ", "M6 ", "M7 "):
    for suf in ("Person Search Member", "IF Member Verified", "PID From Member"):
        nm = (pre + suf).strip()
        present = nm in names
        ok &= present
        if not present:
            print(f"    MISSING {nm}")
print(f"  all 12 new nodes present: {ok}")
conn = after.get("connections") or {}
for pre in ("", "M5 ", "M6 ", "M7 "):
    tgt = [t["node"] for t in conn[f"{pre}IF URL Found"]["main"][1]]
    print(f"  {pre}IF URL Found[false] -> {tgt}")
    ok &= tgt == [f"{pre}Person Search Member"]
if not (after.get("active") and len(after.get("nodes") or []) == EXPECT_NODES and ok):
    sys.exit("VERIFY FAILED - inspect before allowing traffic")
print("\nDEPLOYED AND VERIFIED. W1.0.16 live.")
print(f"new versionId: {after.get('versionId')}")

