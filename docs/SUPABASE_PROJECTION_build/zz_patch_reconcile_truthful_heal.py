#!/usr/bin/env python3
"""Nightly reconcile: set aside rows that violate a Supabase NOT NULL constraint (they poisoned the
whole 500-row upsert chunk every night since 2026-09-16), report the upsert's real outcome instead
of asserting "healed", and name drifted rows by changed-column signature (2026-09-24 health-check
item 1). Pass --apply to patch; default is a dry run that only checks the diff.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DNC_OBS_P1_build"))
from patch_utils import safe_patch_workflow
from zz_patch_projections_sweep_p1_fix import n8n

LIVE_ID = "GgZCHdTt1Mr4sT9Y"
LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "workflows", "dnc_supabase_nightly_reconcile", "dnc_supabase_nightly_reconcile.json")
EXPECTED_ADD = {"Tally Upsert Registry", "Tally Upsert Domains"}
EXPECTED_CHANGED = {f"{n} {t}" for t in ("Registry", "Domains")
                    for n in ("Diff", "Chunk Drift", "Upsert Corrections", "Report")} | {"Build Alert Text"}

if __name__ == "__main__":
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    local = json.load(open(LOCAL, encoding="utf-8"))
    lb = {n["name"]: n for n in live["nodes"]}
    lo = {n["name"]: n for n in local["nodes"]}
    cmp = lambda n: {k: v for k, v in n.items() if k != "position"}
    add, remove = set(lo) - set(lb), set(lb) - set(lo)
    changed = {k for k in lo if k in lb and cmp(lo[k]) != cmp(lb[k])}
    print(f"add={sorted(add)}\nremove={sorted(remove)}\nchanged={sorted(changed)}")
    if add != EXPECTED_ADD or remove or changed != EXPECTED_CHANGED:
        raise SystemExit(f"ABORT: unexpected diff. unexpected changed={sorted(changed ^ EXPECTED_CHANGED)}")
    if "--apply" not in sys.argv:
        print("DRY RUN only -- diff matches expectation. Pass --apply to patch.")
        sys.exit(0)
    safe_patch_workflow(n8n, live_id=LIVE_ID, local_path=LOCAL, label="reconcile",
                         expected_to_add=EXPECTED_ADD, expected_param_diffs=EXPECTED_CHANGED)
    after = n8n(f"/api/v1/workflows/{LIVE_ID}")
    up = next(n for n in after["nodes"] if n["name"] == "Upsert Corrections Registry")
    print(f"post-patch active={after.get('active')} Upsert Corrections Registry onError={up.get('onError')}")
    if up.get("onError") != "continueRegularOutput" or not after.get("active"):
        raise SystemExit("POST-PATCH VERIFY FAILED")
