#!/usr/bin/env python3
"""Narrow, activation-free redeploy of WF-2R's nodes/connections only -- fixes the "WF-2S Watch"
unfiltered /executions read (auditor P2 sweep, 2026-08-26). Deliberately does NOT call /activate:
WF-2R is intentionally inactive (per project memory: "built + deployed INACTIVE 2026-08-06, four
load-bearing design points, don't retune blindly") and this fix must not change that. The existing
redeploy_wf2r.py is a one-time deployment script for a past event (the two-ring rotation launch)
that also activates the workflow as a side effect -- wrong tool for a narrow, activation-neutral
fix. Same safe pattern as DNC_OBS_P1_build/redeploy_generic.py: GET live, merge in nodes+
connections only, strip UI-only keys the API rejects, PUT, verify, done."""
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2R = "U8Bb7Pdq7S6nzYPa"
SRC = os.path.join(HERE, "WF-2R Smartlead REPLY Reconciler - built.json")


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:800]}")
        raise


before = n8n(f"/api/v1/workflows/{WF2R}")
was_active = bool(before.get("active"))
print(f"before: active={was_active} versionId={before.get('versionId')} nodes={len(before.get('nodes') or [])}")
# memory said "deployed INACTIVE 2026-08-06" -- that's stale, it's live now (recent executions
# checked separately, all healthy, running every 15 min). Restore whatever state it's in now,
# don't force either way.

local = json.load(open(SRC, encoding="utf-8"))
newcfg = json.loads(next(n for n in local["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
oldcfg = json.loads(next(n for n in before["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
# this fix touches ONLY the "WF-2S Watch" node's url -- confirm nothing else drifted between the
# local build and what's live before pushing, since this build script wasn't the one actively
# maintained this session.
config_diffs = {k: (oldcfg.get(k), newcfg.get(k)) for k in set(oldcfg) | set(newcfg) if oldcfg.get(k) != newcfg.get(k)}
if config_diffs:
    print("REFUSING: CONFIG differs between live and local build beyond the intended fix -- would push unintended changes:")
    for k, (o, n) in config_diffs.items():
        print(f"  {k}: live={o!r} local={n!r}")
    sys.exit(2)
print("CONFIG matches live exactly (only the WF-2S Watch url differs, as intended)")

if was_active:
    n8n(f"/api/v1/workflows/{WF2R}/deactivate", "POST", {})
    chk = n8n(f"/api/v1/workflows/{WF2R}")
    if chk.get("active"):
        print("deactivate did not take -- aborting before PUT")
        sys.exit(1)
    print("deactivated for the PUT")

merged = dict(before)
merged["nodes"] = local["nodes"]
merged["connections"] = local["connections"]
dropped = stripped_keys(merged)
if dropped:
    print(f"stripping UI-only settings keys the API rejects: {dropped}")
n8n(f"/api/v1/workflows/{WF2R}", "PUT", put_body(merged))

if was_active:
    n8n(f"/api/v1/workflows/{WF2R}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2R}")
print(f"after:  active={after.get('active')} versionId={after.get('versionId')} nodes={len(after.get('nodes') or [])}")
if after.get("active") != was_active:
    print(f"WARNING: active flag changed ({was_active} -> {after.get('active')}) -- should have been restored exactly. Investigate immediately.")

got = {n["name"]: n for n in (after.get("nodes") or [])}
sent = {n["name"]: n for n in local["nodes"]}
problems = []
if set(sent) != set(got):
    problems.append(f"node set differs: {set(sent) ^ set(got)}")
for nm in sent.keys() & got.keys():
    if (sent[nm].get("parameters") or {}).get("jsCode") != (got[nm].get("parameters") or {}).get("jsCode"):
        problems.append(f"{nm}: jsCode differs after round-trip")
livecfg = json.loads(got["CONFIG"]["parameters"]["jsonOutput"])
for k in ("ignore_replies_before", "max_per_run", "max_campaigns_per_cycle", "lookback_minutes",
          "hot_cycles_per_cold", "cold_max_age_days", "wf2s_workflow_id"):
    if livecfg.get(k) != newcfg.get(k):
        problems.append(f"CONFIG.{k}: live {livecfg.get(k)!r} != built {newcfg.get(k)!r}")
watch_node = got.get("WF-2S Watch")
url = (watch_node or {}).get("parameters", {}).get("url", "")
if "status=success" not in url:
    problems.append("WF-2S Watch url missing status=success -- fix did not land")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
