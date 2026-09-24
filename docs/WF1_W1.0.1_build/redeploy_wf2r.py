#!/usr/bin/env python3
"""Update the live WF-2R to the two-ring rotation. n8n refuses a PUT while active, so:
deactivate -> PUT -> activate -> RE-READ and verify. A 200 from /activate is not evidence.

The reply floor is asserted BEFORE and AFTER: if the rebuild lost it, the next cycle would replay
the ten hand-backfilled replies and double-forward hwang to Rune.
"""
import json, os, ssl, sys, urllib.error, urllib.request
from datetime import datetime, timezone

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None
WF2R = "U8Bb7Pdq7S6nzYPa"
SRC = "WF-2R Smartlead REPLY Reconciler - built.json"
NEWEST_BACKFILLED = "2026-08-05T06:08:38+00:00"


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                               headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                        "accept": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
            return json.load(x)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:600]}")
        raise


new = json.load(open(SRC, encoding="utf-8"))
newcfg = json.loads(next(n for n in new["nodes"]
                         if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
floor = newcfg["ignore_replies_before"]
f = datetime.fromisoformat(floor.replace("Z", "+00:00"))
nb = datetime.fromisoformat(NEWEST_BACKFILLED)
if nb >= f:
    print(f"REFUSING: floor {floor} does not clear the newest backfilled reply "
          f"{NEWEST_BACKFILLED} - would risk double-forwarding hwang")
    sys.exit(2)
print(f"floor {floor} clears the backfill by {(f - nb).total_seconds() / 3600:.1f}h")

live = n8n(f"/api/v1/workflows/{WF2R}")
backup = f"wf2r_backup_before_tworing_{int(datetime.now(timezone.utc).timestamp())}.json"
open(backup, "w", encoding="utf-8").write(json.dumps(live, indent=2, ensure_ascii=False))
print(f"backup written: {backup}  (was active={live.get('active')} "
      f"versionId={live.get('versionId')})")

if live.get("active"):
    n8n(f"/api/v1/workflows/{WF2R}/deactivate", "POST", {})
    chk = n8n(f"/api/v1/workflows/{WF2R}")
    if chk.get("active"):
        print("deactivate did not take - aborting before PUT")
        sys.exit(1)
    print("deactivated")

from n8n_deploy_util import put_body, stripped_keys  # noqa: E402
dropped = stripped_keys(new)
if dropped:
    print(f"stripping UI-only settings keys the API rejects: {dropped}")
n8n(f"/api/v1/workflows/{WF2R}", "PUT", put_body(new))
n8n(f"/api/v1/workflows/{WF2R}/activate", "POST", {})

after = n8n(f"/api/v1/workflows/{WF2R}")
got = {n["name"]: n for n in (after.get("nodes") or [])}
sent = {n["name"]: n for n in new["nodes"]}
problems = []
if after.get("active") is not True:
    problems.append(f"active={after.get('active')} after activate")
if set(sent) != set(got):
    problems.append(f"node set differs: {set(sent) ^ set(got)}")
for nm in sent.keys() & got.keys():
    if (sent[nm].get("parameters") or {}).get("jsCode") != \
       (got[nm].get("parameters") or {}).get("jsCode"):
        problems.append(f"{nm}: jsCode differs after round-trip")
livecfg = json.loads(got["CONFIG"]["parameters"]["jsonOutput"])
for k in ("ignore_replies_before", "max_per_run", "max_campaigns_per_cycle", "lookback_minutes",
          "hot_cycles_per_cold", "cold_max_age_days", "wf2s_workflow_id"):
    if livecfg.get(k) != newcfg.get(k):
        problems.append(f"CONFIG.{k}: live {livecfg.get(k)!r} != built {newcfg.get(k)!r}")

print(f"\nlive verification: {'CLEAN' if not problems else 'PROBLEMS'}")
for p in problems:
    print("  -", p)
print(f"  active     : {after.get('active')}")
print(f"  versionId  : {after.get('versionId')}")
print(f"  nodes      : {len(after.get('nodes') or [])}")
print(f"  floor      : {livecfg.get('ignore_replies_before')}")
print(f"  rings      : {livecfg.get('hot_cycles_per_cold')} hot per 1 cold, "
      f"cold cutoff {livecfg.get('cold_max_age_days')}d")
sys.exit(1 if problems else 0)
