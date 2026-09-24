#!/usr/bin/env python3
"""Route WF-1 reply alerts to the team channel (#lead-processing), per the routing spec.

TWO changes, and the second is why this is not a one-line CONFIG flip:

  1. `M7 Slack Warn` is an OPS warning that reads `slack_channel_replies`. Flipping that key alone
     would push a warning into the team channel, which the spec forbids ("no warnings, ever").
     It is repointed to `slack_channel_ops` FIRST.
  2. `CONFIG.slack_channel_replies` -> C07LTD8UT70.

After this, `slack_channel_replies` feeds exactly one node: `M7 Critical Slack`, the reply alert.

NOT touched: WF-2's `Reply Alert` / `Nurture Alert` also read `slack_channel_replies`, but WF-2
posts as the *Smartlead* Slack app, which is NOT a member of C07LTD8UT70 - flipping it now would
make those posts fail. That switch waits for the app invite.

Deploy-window rule: deactivate -> PUT -> activate -> re-read and verify.
"""
import argparse, json, os, re, ssl, sys, urllib.error, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF1 = "2jdjKM2NJr473GdA"
TEAM = "C07LTD8UT70"
OPS = "C0B8GCVNR5W"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
        raise


ap = argparse.ArgumentParser()
ap.add_argument("--deploy", action="store_true")
a = ap.parse_args()

wf = n8n(f"/api/v1/workflows/{WF1}")
print(f"WF-1 live: versionId={wf.get('versionId')} nodes={len(wf['nodes'])} "
      f"active={wf.get('active')}")

cfg_node = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
print(f"  slack_channel_replies now : {cfg.get('slack_channel_replies')}")
print(f"  slack_channel_ops now     : {cfg.get('slack_channel_ops')}")

warn = next((n for n in wf["nodes"] if n["name"] == "M7 Slack Warn"), None)
if warn is None:
    print("REFUSING: 'M7 Slack Warn' not found - WF-1 has changed, re-read before patching")
    sys.exit(2)
warn_raw = json.dumps(warn["parameters"].get("channelId") or {}, ensure_ascii=False)
print(f"  M7 Slack Warn reads       : {re.search(r'json.(w+)', warn_raw) and ''}"
      f"{re.findall(r'json[.](.w*)', warn_raw)}")

changed = []
# 1. ops warning off the reply key
if "slack_channel_replies" in warn_raw:
    warn["parameters"]["channelId"]["value"] = \
        "={{ $('CONFIG').item.json.slack_channel_ops }}"
    changed.append("M7 Slack Warn -> slack_channel_ops")
elif "slack_channel_ops" in warn_raw:
    print("  M7 Slack Warn already on the ops key")
else:
    print(f"REFUSING: cannot tell which key M7 Slack Warn uses: {warn_raw[:200]}")
    sys.exit(2)

# 2. reply key to the team channel
if cfg.get("slack_channel_replies") != TEAM:
    cfg["slack_channel_replies"] = TEAM
    cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)
    changed.append(f"CONFIG.slack_channel_replies -> {TEAM}")

# safety: ops keys must stay put
for k in ("slack_channel", "slack_channel_ops"):
    if cfg.get(k) != OPS:
        print(f"REFUSING: {k} is {cfg.get(k)!r}, expected {OPS} - ops alerts must not move")
        sys.exit(2)

print("\nplanned changes:")
for c in changed:
    print("  -", c)
if not changed:
    print("  (none - already in the target state)")
    sys.exit(0)

if not a.deploy:
    print("\n--deploy not given: nothing written.")
    sys.exit(0)

backup = f"wf1_backup_before_reply_channel_{int(datetime.now(timezone.utc).timestamp())}.json"
open(backup, "w", encoding="utf-8").write(json.dumps(
    n8n(f"/api/v1/workflows/{WF1}"), indent=2, ensure_ascii=False))
print(f"\nbackup: {backup}")

was_active = wf.get("active")
if was_active:
    n8n(f"/api/v1/workflows/{WF1}/deactivate", "POST", {})
    if n8n(f"/api/v1/workflows/{WF1}").get("active"):
        print("deactivate did not take - aborting before PUT")
        sys.exit(1)
    print("deactivated (deploy window OPEN - HeyReach webhooks 404 until reactivated)")
# PUT rejects UI-only settings keys with a bare 400 (timeSavedMode / callerPolicy /
# availableInMCP are returned by GET but not accepted back). Whitelist what the API takes,
# otherwise the workflow is left DEACTIVATED by the failed deploy - which is what happened on the
# first attempt here.
ALLOWED = ("executionOrder", "errorWorkflow", "saveDataSuccessExecution",
           "saveDataErrorExecution", "saveManualExecutions", "saveExecutionProgress",
           "executionTimeout", "timezone")
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
n8n(f"/api/v1/workflows/{WF1}", "PUT",
    {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
     "settings": settings})
if was_active:
    n8n(f"/api/v1/workflows/{WF1}/activate", "POST", {})
print("deploy window CLOSED")


after = n8n(f"/api/v1/workflows/{WF1}")
acfg = json.loads(next(n for n in after["nodes"]
                       if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
awarn = json.dumps(next(n for n in after["nodes"]
                        if n["name"] == "M7 Slack Warn")["parameters"].get("channelId"),
                   ensure_ascii=False)
problems = []
if after.get("active") is not was_active:
    problems.append(f"active={after.get('active')} (was {was_active})")
if acfg.get("slack_channel_replies") != TEAM:
    problems.append(f"slack_channel_replies={acfg.get('slack_channel_replies')!r}")
if acfg.get("slack_channel_ops") != OPS or acfg.get("slack_channel") != OPS:
    problems.append("an ops channel key moved - must not happen")
if "slack_channel_ops" not in awarn:
    problems.append("M7 Slack Warn is still not on the ops key")
if len(after["nodes"]) != len(wf["nodes"]):
    problems.append("node count changed")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active                : {after.get('active')}")
print(f"  versionId             : {after.get('versionId')}")
print(f"  slack_channel_replies : {acfg.get('slack_channel_replies')}  (team)")
print(f"  slack_channel_ops     : {acfg.get('slack_channel_ops')}  (ops)")
sys.exit(1 if problems else 0)
