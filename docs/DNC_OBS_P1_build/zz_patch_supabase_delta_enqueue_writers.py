#!/usr/bin/env python3
"""Every direct registry writer enqueues its own Supabase delta claim (2026-09-24 health-check
item 1). Structural only: adds dnc_claims enqueue nodes after the registry writes that bypassed
UpsertLedger, and defaults correlation_id/date_precision in the archived-responders import driver.
dnc_projections_sweep's live CONFIG is kept as-is (FIRE_PIPEDRIVE is true live, false in the
generator). Pass --apply to patch; default is a dry run that only checks the diff.
"""
import copy
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_utils import safe_patch_workflow
from zz_patch_projections_sweep_p1_fix import n8n

PATCHES = [
    {"name": "dnc_projections_sweep", "id": "8qVXtI2ez5o6a9hc", "keep_live": {"CONFIG"},
     "add": {"PD Enqueue Supabase Delta", "PD Enqueue Supabase Delta (Write Error)", "SL Enqueue Supabase Delta"},
     "changed": set()},
    {"name": "dnc_s4_retirement_removal", "id": "DYb9jArdS7xKs3nA", "keep_live": set(),
     "add": {"Enqueue Supabase Delta"}, "changed": set()},
    {"name": "dnc_archived_responders_import", "id": "07sGtABZiqLrBChX", "keep_live": set(),
     "add": set(), "changed": {"Build Items"}},
]


def staged_local(p, live):
    with open(f"workflows/{p['name']}/{p['name']}.json", encoding="utf-8") as f:
        local = json.load(f)
    live_by_name = {n["name"]: n for n in live["nodes"]}
    local["nodes"] = [copy.deepcopy(live_by_name[n["name"]]) if n["name"] in p["keep_live"] else n
                      for n in local["nodes"]]
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(local, f)
    return local, path


def main():
    apply_it = "--apply" in sys.argv
    for p in PATCHES:
        live = n8n(f"/api/v1/workflows/{p['id']}")
        local, path = staged_local(p, live)
        lb = {n["name"]: n for n in live["nodes"]}
        lo = {n["name"]: n for n in local["nodes"]}
        cmp = lambda n: {k: v for k, v in n.items() if k != "position"}
        add, remove = set(lo) - set(lb), set(lb) - set(lo)
        changed = {k for k in lo if k in lb and cmp(lo[k]) != cmp(lb[k])}
        ok = add == p["add"] and not remove and changed == p["changed"]
        print(f"{p['name']}: add={sorted(add)} remove={sorted(remove)} changed={sorted(changed)} -> "
              f"{'as expected' if ok else 'UNEXPECTED'}")
        if not ok:
            raise SystemExit("ABORT: diff does not match expectation")
        if apply_it:
            safe_patch_workflow(n8n, live_id=p["id"], local_path=path, label=p["name"],
                                 expected_to_add=p["add"], expected_param_diffs=p["changed"])
            after = n8n(f"/api/v1/workflows/{p['id']}")
            if p["keep_live"]:
                cfg_b = next(n for n in live["nodes"] if n["name"] == "CONFIG")
                cfg_a = next(n for n in after["nodes"] if n["name"] == "CONFIG")
                if cfg_a["parameters"] != cfg_b["parameters"]:
                    raise SystemExit(f"{p['name']}: POST-PATCH CONFIG CHANGED -- investigate immediately")
                print(f"  CONFIG preserved byte-identical (FIRE_PIPEDRIVE live value kept)")
            print(f"  active={after.get('active')} (was {live.get('active')})")
        os.remove(path)
    print("DRY RUN only -- pass --apply to patch." if not apply_it else "all patches applied and verified.")


if __name__ == "__main__":
    main()
