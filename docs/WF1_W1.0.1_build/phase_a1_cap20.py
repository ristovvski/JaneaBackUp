"""Phase A1 — WF-2S max_per_run=20, PERMANENT. Deploy-window rule: quiet check -> deactivate -> PUT
-> activate -> READ-BACK verify. lookback_minutes is left untouched (currently 180) - A2 says no
recovery now; the drain (and any lookback widening it needs) is a Phase C action, not this one.
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
KEY = os.environ["N8N_API_KEY"]
WF2S = "6Y92ryBwYoy6z0Jx"
EXPECT_BASE_VERSION = "719bde15-b6b1-4dae-8111-28f4a52aef1f"
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
print("QUIET-WINDOW PRE-CHECK")
print("=" * 92)
st, live = api(f"/api/v1/workflows/{WF2S}")
print(f"  live versionId={live.get('versionId')}  active={live.get('active')}")
if live.get("versionId") != EXPECT_BASE_VERSION:
    sys.exit(f"ABORT: live version is {live.get('versionId')}, expected {EXPECT_BASE_VERSION} "
             f"(read moments ago) - someone else changed WF-2S mid-flight. Re-diff before deploying.")

st, ex = api(f"/api/v1/executions?workflowId={WF2S}&limit=10")
rows = (ex or {}).get("data") or []
now = datetime.now(timezone.utc)
recent = [r for r in rows if r.get("startedAt")
          and (now - datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00"))
               ).total_seconds() < QUIET_MIN * 60]
running = [r for r in rows if not r.get("stoppedAt")]
print(f"  retained={len(rows)} running={len(running)} started<{QUIET_MIN}min ago={len(recent)}")
if running or recent:
    sys.exit("ABORT: not a quiet window. Retry shortly.")

N = {n["name"]: n for n in live["nodes"]}
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
before = dict(cfg)
print(f"\n  before: max_per_run={cfg.get('max_per_run')} lookback_minutes={cfg.get('lookback_minutes')}")
cfg["max_per_run"] = 20
N["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)
print(f"  after : max_per_run={cfg.get('max_per_run')} lookback_minutes={cfg.get('lookback_minutes')}"
      f"  (lookback UNCHANGED per A2)")

backup = os.path.join(HERE, f"wf2s_backup_before_a1_cap20_{int(time.time())}.json")
json.dump(live, open(backup, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"  backup written: {backup}")

settings = {k: v for k, v in (live.get("settings") or {}).items() if k in SETTINGS_OK}
payload = {"name": live["name"], "nodes": live["nodes"], "connections": live["connections"],
           "settings": settings}

print("\n" + "=" * 92)
print("DEPLOY")
print("=" * 92)
st, r = api(f"/api/v1/workflows/{WF2S}/deactivate", "POST")
print(f"  deactivate -> {st}")
if st >= 300:
    sys.exit(f"ABORT before PUT: {r}")
st, r = api(f"/api/v1/workflows/{WF2S}", "PUT", payload)
print(f"  PUT        -> {st}")
if st >= 300:
    print(f"  FAILED: {r}")
    st2, _ = api(f"/api/v1/workflows/{WF2S}/activate", "POST")
    print(f"  re-activated original -> {st2}")
    sys.exit(1)
st, r = api(f"/api/v1/workflows/{WF2S}/activate", "POST")
print(f"  activate   -> {st}")

print("\n" + "=" * 92)
print("READ-BACK VERIFY (never trust the 200 - this exact class caused the WF-2 outage)")
print("=" * 92)
ok = False
for i in range(1, 6):
    time.sleep(4)
    st, after = api(f"/api/v1/workflows/{WF2S}")
    print(f"  re-read #{i}: active={after.get('active')} version={after.get('versionId')}")
    if after.get("active") is True:
        ok = True
        break
if not ok:
    sys.exit("ABORT: WF-2S did not come back ACTIVE.")

N2 = {n["name"]: n for n in after["nodes"]}
c2 = json.loads(N2["CONFIG"]["parameters"]["jsonOutput"])
print(f"\nverified live CONFIG: max_per_run={c2.get('max_per_run')} "
      f"lookback_minutes={c2.get('lookback_minutes')}")
assert c2.get("max_per_run") == 20, "max_per_run did not take"
assert c2.get("lookback_minutes") == before.get("lookback_minutes"), "lookback changed unexpectedly"
print(f"new versionId: {after.get('versionId')}")
print("PHASE A1 COMPLETE AND VERIFIED.")
