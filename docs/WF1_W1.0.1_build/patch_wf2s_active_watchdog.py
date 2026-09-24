"""Step 1 + recovery setup for WF-2S, in one deploy.

(1) WATCHDOG: alarm when WF-2 is not ACTIVE.
    `WF-2 Mode Read` already GETs the whole workflow object, so `active` was in the response all
    along and `WF-2 Mode Eval` simply never looked at it. That is why WF-2 could sit deactivated for
    15 hours while the watchdog cheerfully reported WRITE_MODE=shadow: reading CONFIG works fine on
    an inactive workflow. Code-only change in two nodes; the graph is untouched.
    (WF-2H needs no change - it reads Smartlead stats and Pipedrive leads, never WF-2's state.)

(2) RECOVERY: raise lookback_minutes so the SENT events stranded by the outage fall back inside the
    window. Original values are saved to disk for the restore.

Deploy protocol: deactivate -> PUT -> activate -> RE-READ and verify active===true. That verification
is the whole point: an unverified activate is exactly what caused this incident.
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
SAVED = os.path.join(HERE, "wf2s_config_before_recovery.json")
LOOKBACK_RECOVERY = int(os.environ.get("RECOVERY_LOOKBACK", "1200"))   # ~20h, covers from 10:50Z
MAX_PER_RUN = os.environ.get("RECOVERY_MAX_PER_RUN")                  # None = leave as-is
SETTINGS_OK = {"executionOrder", "saveManualExecutions", "callerPolicy", "errorWorkflow",
               "saveDataErrorExecution", "saveDataSuccessExecution", "saveExecutionProgress",
               "executionTimeout", "timezone"}

ACTIVE_BLOCK = """
// W1.0.16-ops: WF-2 sat DEACTIVATED for ~15h on 2026-08-04 (PUT at 14:30:52Z left it off) and
// nothing noticed. This watchdog read WF-2's CONFIG - which works perfectly well on an INACTIVE
// workflow - and never asked whether WF-2 was actually RUNNING. Meanwhile every `Replay Into WF-2`
// got 404 "Active version not found" and the whole SENT pipeline was dead in the water.
// An inactive receiver is a total outage in shadow AND in live, so alarm on it unconditionally.
// `active` was in this very response all along; the check cost nothing but was never asked for.
const activeKnown = (typeof wf.active === 'boolean');
const isActive = (wf.active === true);
"""


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


st, wf = api(f"/api/v1/workflows/{WF2S}")
if st >= 300:
    sys.exit(f"cannot read WF-2S: {st} {wf}")
N = {n["name"]: n for n in wf["nodes"]}
print(f"WF-2S version={wf.get('versionId')} nodes={len(wf['nodes'])} active={wf.get('active')}")

# ---------------------------------------------------------------- 1. Mode Eval
ev = N["WF-2 Mode Eval"]
code = ev["parameters"]["jsCode"]
if "activeKnown" in code:
    sys.exit("already patched - refusing to double-patch")
anchor = "const sd = $getWorkflowStaticData('global');"
if anchor not in code:
    sys.exit("anchor not found in WF-2 Mode Eval - inspect before patching")
code = code.replace(anchor, ACTIVE_BLOCK.strip() + "\n" + anchor, 1)

old_ret = "__mode_overdue: (mode === 'live' && hours !== null && hours >= limit) || mode === null,"
if old_ret not in code:
    sys.exit("return-shape anchor not found - inspect before patching")
new_ret = (
    "// __mode_overdue is the single alarm flag this graph already routes on, so inactivity joins it\n"
    "    // rather than adding nodes to a live workflow; the distinct fields below carry the REASON.\n"
    "    __wf2_active: activeKnown ? isActive : null,\n"
    "    __wf2_inactive: (!activeKnown) || (!isActive),\n"
    "    __mode_overdue: (mode === 'live' && hours !== null && hours >= limit) || mode === null"
    " || (!activeKnown) || (!isActive),"
)
code = code.replace(old_ret, new_ret, 1)
ev["parameters"]["jsCode"] = code
print("  patched WF-2 Mode Eval")

# ---------------------------------------------------------------- 2. the Slack text
warn = N["Ops Warn Mode Overdue"]
q = chr(39)
new_text = (
    "={{ (() => { const j=$json;"
    " if (j.__wf2_inactive === true) {"
    "   return " + json.dumps(":rotating_light: *WF-2 IS NOT ACTIVE* - every SENT replay is being "
                             "rejected with 404 \"Active version not found\", so the SENT pipeline "
                             "is dead. This is a total outage in shadow and in live. Re-activate "
                             "WF-2, then verify by re-reading `active` AND probing its webhook - a "
                             "200 from /activate is not proof. Cause on 2026-08-04: a PUT left it "
                             "deactivated and the activate step was never verified.") + ";"
    " }"
    " if (j.__mode === null) {"
    "   return " + json.dumps(":warning: *WF-2S cannot read WF-2's WRITE_MODE* - the live-window "
                             "expiry check is blind right now.") + ";"
    " }"
    " return " + json.dumps(":rotating_light: *WF-2 has been in WRITE_MODE=live for ") + " + "
    "j.__mode_hours + " + json.dumps("h*") + " + " + json.dumps(" (limit ") + " + j.__mode_limit"
    " + " + json.dumps("h, live since ") + " + j.__mode_live_since + " + json.dumps("). A live "
    "window is supposed to last minutes. Revert to shadow or say why it is still open.") + ";"
    " })() }}"
)
warn["parameters"]["text"] = new_text
print("  patched Ops Warn Mode Overdue (adds the inactive branch)")

# ---------------------------------------------------------------- 3. CONFIG for recovery
cfg_node = N["CONFIG"]
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
before = {"lookback_minutes": cfg.get("lookback_minutes"), "max_per_run": cfg.get("max_per_run")}
json.dump(before, open(SAVED, "w", encoding="utf-8"), indent=2)
print(f"  saved originals to {SAVED}: {before}")
cfg["lookback_minutes"] = LOOKBACK_RECOVERY
if MAX_PER_RUN:
    cfg["max_per_run"] = int(MAX_PER_RUN)
cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)
print(f"  CONFIG lookback_minutes {before['lookback_minutes']} -> {cfg['lookback_minutes']}"
      f"   max_per_run {before['max_per_run']} -> {cfg['max_per_run']}")

# ---------------------------------------------------------------- deploy
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
           "settings": settings}
print("\ndeploying...")
st, r = api(f"/api/v1/workflows/{WF2S}/deactivate", "POST")
print(f"  deactivate -> {st}")
st, r = api(f"/api/v1/workflows/{WF2S}", "PUT", payload)
print(f"  PUT        -> {st}")
if st >= 300:
    print(f"  FAILED: {r}")
    st2, _ = api(f"/api/v1/workflows/{WF2S}/activate", "POST")
    print(f"  re-activated original -> {st2}")
    sys.exit(1)
st, r = api(f"/api/v1/workflows/{WF2S}/activate", "POST")
print(f"  activate   -> {st}")

# the lesson from this very incident: verify, never trust the 200
ok = False
for i in range(1, 6):
    time.sleep(4)
    st, after = api(f"/api/v1/workflows/{WF2S}")
    print(f"  re-read #{i}: active={after.get('active')} version={after.get('versionId')}")
    if after.get("active") is True:
        ok = True
        break
if not ok:
    sys.exit("ABORT: WF-2S did not come back ACTIVE - fix before the next cycle")

st, after = api(f"/api/v1/workflows/{WF2S}")
N2 = {n["name"]: n for n in after["nodes"]}
c2 = json.loads(N2["CONFIG"]["parameters"]["jsonOutput"])
print(f"\nverified: nodes={len(after['nodes'])} active={after.get('active')}")
print(f"  lookback_minutes={c2.get('lookback_minutes')} max_per_run={c2.get('max_per_run')}")
print(f"  Mode Eval has active check: {'activeKnown' in N2['WF-2 Mode Eval']['parameters']['jsCode']}")
print(f"  Slack has inactive branch : {'__wf2_inactive' in N2['Ops Warn Mode Overdue']['parameters']['text']}")
print(f"\nnew versionId: {after.get('versionId')}")
