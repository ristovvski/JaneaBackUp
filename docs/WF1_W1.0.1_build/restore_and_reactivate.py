"""Stop the crash loop: restore WF-2S lookback to 180, reactivate WF-2, verify everything.

Why urgently: with lookback_minutes=1200 each WF-2S cycle attempts ~100 replays, which OOMs the n8n
instance (WorkflowCrashedError, "possible out-of-memory issue"), crashes WF-2's executions and leaves
WF-2 DEACTIVATED. That is an instance-wide event, so WF-1 (the live LinkedIn receiver) is exposed too.
Restoring the original 180 makes batches empty again - there have been no sends for hours - which
stops the loop. max_per_run is put back to its original 100 rather than changed, because lowering it
is a separate decision for the owner.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF2S = "6Y92ryBwYoy6z0Jx"
WF2 = "jp7rum9Z0YDJkQWv"
WF1 = os.environ["WF1_ID"]
SAVED = os.path.join(HERE, "wf2s_config_before_recovery.json")
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


orig = json.load(open(SAVED, encoding="utf-8"))
print(f"restoring WF-2S CONFIG to {orig}")

st, wf = api(f"/api/v1/workflows/{WF2S}")
N = {n["name"]: n for n in wf["nodes"]}
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
print(f"  current: lookback_minutes={cfg.get('lookback_minutes')} "
      f"max_per_run={cfg.get('max_per_run')}")
cfg["lookback_minutes"] = orig["lookback_minutes"]
cfg["max_per_run"] = orig["max_per_run"]
N["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)
# the watchdog patch stays - it is what caught this
assert "activeKnown" in N["WF-2 Mode Eval"]["parameters"]["jsCode"], "watchdog patch missing"

settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
           "settings": settings}
st, _ = api(f"/api/v1/workflows/{WF2S}/deactivate", "POST")
print(f"  deactivate -> {st}")
st, r = api(f"/api/v1/workflows/{WF2S}", "PUT", payload)
print(f"  PUT        -> {st}")
if st >= 300:
    print(f"  FAILED: {r}")
st, _ = api(f"/api/v1/workflows/{WF2S}/activate", "POST")
print(f"  activate   -> {st}")
for i in range(5):
    time.sleep(4)
    st, after = api(f"/api/v1/workflows/{WF2S}")
    if after.get("active"):
        break
c2 = json.loads({n["name"]: n for n in after["nodes"]}["CONFIG"]["parameters"]["jsonOutput"])
print(f"  verified WF-2S: active={after.get('active')} "
      f"lookback={c2.get('lookback_minutes')} max_per_run={c2.get('max_per_run')} "
      f"version={after.get('versionId')}")

print("\nreactivating WF-2 (shadow)")
st, wf2 = api(f"/api/v1/workflows/{WF2}")
cfg2 = {}
for n in (wf2.get("nodes") or []):
    if n["name"] == "CONFIG":
        cfg2 = json.loads((n.get("parameters") or {}).get("jsonOutput") or "{}")
if cfg2.get("WRITE_MODE") != "shadow":
    sys.exit(f"ABORT: WF-2 WRITE_MODE is {cfg2.get('WRITE_MODE')!r}")
st, _ = api(f"/api/v1/workflows/{WF2}/activate", "POST")
print(f"  activate -> {st}")
for i in range(5):
    time.sleep(4)
    st, a2 = api(f"/api/v1/workflows/{WF2}")
    print(f"  re-read #{i + 1}: active={a2.get('active')}")
    if a2.get("active"):
        break

hook = None
for n in (wf2.get("nodes") or []):
    if n["type"].endswith(".webhook"):
        hook = (n.get("parameters") or {}).get("path")
        break
if hook:
    req = urllib.request.Request(f"{BASE}/webhook/{hook}",
                                 data=json.dumps({"__probe": "restore-check"}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as x:
            print(f"  webhook probe -> {x.status}")
    except urllib.error.HTTPError as e:
        print(f"  webhook probe -> {e.code}")

print("\nWF-1 EXPOSURE CHECK (the OOM is instance-wide)")
st, w1 = api(f"/api/v1/workflows/{WF1}")
print(f"  WF-1 active={w1.get('active')} version={w1.get('versionId')} "
      f"nodes={len(w1.get('nodes') or [])}")
st, ex = api(f"/api/v1/executions?workflowId={WF1}&limit=30")
rows = sorted([r for r in (ex.get("data") or []) if r.get("startedAt")],
              key=lambda r: r["startedAt"], reverse=True)
bad = [r for r in rows if r.get("status") not in ("success", None)]
print(f"  WF-1 retained={len(rows)} non-success={len(bad)} {[(r['id'], r.get('status')) for r in bad[:6]]}")
if rows:
    print(f"  newest WF-1 execution: {rows[0]['startedAt']} status={rows[0].get('status')}")
