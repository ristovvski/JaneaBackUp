#!/usr/bin/env python3
"""Surgical fix: patch ONLY the "WF-2S Watch" node's `parameters.url` field directly on the LIVE
WF-2R definition -- adds &status=success to the unfiltered /executions read (auditor P2 sweep,
2026-08-26). Does NOT regenerate anything from build_wf2r.py -- a bare re-run of that script was
just proven to regenerate ignore_replies_before as TODAY's timestamp instead of the real
2026-08-06T13:50:17Z floor (and drops telemetry_channel/wf2s_workflow_id entirely), which would
have reset the reply-dedup floor and risked exactly the double-forward WF-2R's own deploy script
warns about. Everything else in the live workflow -- CONFIG, every other node, connections --
stays byte-for-byte what's already live. Active state preserved exactly."""
import copy
import json, os, ssl, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from n8n_deploy_util import put_body, stripped_keys  # noqa: E402

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2R = "U8Bb7Pdq7S6nzYPa"
OLD_FRAGMENT = "wf2s_workflow_id || '') + '&limit=1'"
NEW_FRAGMENT = "wf2s_workflow_id || '') + '&status=success&limit=1'"


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

watch = next((n for n in before["nodes"] if n["name"] == "WF-2S Watch"), None)
if not watch:
    print("REFUSING: 'WF-2S Watch' node not found live -- names may have drifted, do not blind-patch")
    sys.exit(2)
url = watch["parameters"].get("url", "")
if OLD_FRAGMENT not in url:
    print(f"REFUSING: expected fragment not found in live url -- got: {url!r}")
    sys.exit(2)
if "status=" in url:
    print(f"Nothing to do: url already has a status= filter: {url!r}")
    sys.exit(0)

merged = copy.deepcopy(before)
merged_watch = next(n for n in merged["nodes"] if n["name"] == "WF-2S Watch")
merged_watch["parameters"]["url"] = url.replace(OLD_FRAGMENT, NEW_FRAGMENT)
print("old url:", url)
print("new url:", merged_watch["parameters"]["url"])

# confirm this is the ONLY change: every other node byte-identical.
other_diffs = []
for n_before, n_after in zip(before["nodes"], merged["nodes"]):
    if n_before["name"] == "WF-2S Watch":
        continue
    if n_before != n_after:
        other_diffs.append(n_before["name"])
if other_diffs:
    print("REFUSING: unexpected diffs outside WF-2S Watch:", other_diffs)
    sys.exit(2)
print("confirmed: only WF-2S Watch's url changes, every other node untouched")

if was_active:
    n8n(f"/api/v1/workflows/{WF2R}/deactivate", "POST", {})
    chk = n8n(f"/api/v1/workflows/{WF2R}")
    if chk.get("active"):
        print("deactivate did not take -- aborting before PUT")
        sys.exit(1)
    print("deactivated for the PUT")

dropped = stripped_keys(merged)
if dropped:
    print(f"stripping UI-only settings keys the API rejects: {dropped}")
n8n(f"/api/v1/workflows/{WF2R}", "PUT", put_body(merged))

if was_active:
    n8n(f"/api/v1/workflows/{WF2R}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2R}")
print(f"\nafter:  active={after.get('active')} versionId={after.get('versionId')} nodes={len(after.get('nodes') or [])}")
if after.get("active") != was_active:
    print(f"WARNING: active flag changed ({was_active} -> {after.get('active')}) -- investigate immediately")

after_watch = next((n for n in (after.get("nodes") or []) if n["name"] == "WF-2S Watch"), None)
after_url = (after_watch or {}).get("parameters", {}).get("url", "")
ok = "status=success" in after_url
print("fix landed:" , ok, "--", after_url)

after_cfg = json.loads(next(n for n in after["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
before_cfg = json.loads(next(n for n in before["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
cfg_ok = after_cfg == before_cfg
print("CONFIG unchanged:", cfg_ok)
sys.exit(0 if (ok and cfg_ok and after.get("active") == was_active) else 1)
