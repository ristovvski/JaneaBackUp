#!/usr/bin/env python3
"""P1 FIX deploy (2026-09-16, Nik's item 4): removes dnc_projections_sweep's lead-label write
branch entirely -- field write only, never label_ids. See
task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md for the incident this corrects.

FIRE_PIPEDRIVE is already false live (the STOP action, first thing done this incident) so this is a
pure structural patch -- no write risk either way. Uses patch_utils.safe_patch_workflow (mandatory
since the 2026-09-09 incident) which aborts on any diff outside exactly what's expected below; no
"proceed anyway" path.

Expected diff:
  REMOVE (9): the whole label-write path -- PD Get Leads By Person, PD Classify,
    PD Has Open Lead?, PD Get Lead For Labels, PD Label Union, PD Patch Lead Labels,
    PD Mark Done (with lead), PD Merge Write Errors, and PD Mark Done (no lead) (renamed below).
  ADD (1): PD Mark Done -- the rename target for PD Mark Done (no lead), now the only Mark Done
    node since there's no more with-lead/no-lead fork.
  CHANGE (3): CONFIG (pd_label_dnc field removed), PD Aggregate (rewritten -- no more
    with_open_lead/without_open_lead split, one flat rows list), Combine Summaries (Slack text +
    JSON note field: "field write only" phrasing, no more open-lead counts).
"""
import json
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_utils import safe_patch_workflow

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
ctx = ssl._create_unverified_context()


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


LIVE_ID = "8qVXtI2ez5o6a9hc"
LOCAL_PATH = "workflows/dnc_projections_sweep/dnc_projections_sweep.json"

EXPECTED_REMOVE = {
    "PD Get Leads By Person", "PD Classify", "PD Has Open Lead?", "PD Get Lead For Labels",
    "PD Label Union", "PD Patch Lead Labels", "PD Mark Done (with lead)", "PD Merge Write Errors",
    "PD Mark Done (no lead)",
}
EXPECTED_ADD = {"PD Mark Done"}
EXPECTED_CHANGED = {"CONFIG", "PD Aggregate", "Combine Summaries"}

if __name__ == "__main__":
    apply_it = "--apply" in sys.argv

    live_before = n8n(f"/api/v1/workflows/{LIVE_ID}")
    fire_pipedrive = next(
        (a["value"] for a in live_before["nodes"]
         if a["name"] == "CONFIG" for a in a["parameters"]["assignments"]["assignments"]
         if a["name"] == "FIRE_PIPEDRIVE"),
        None,
    )
    print(f"pre-patch live FIRE_PIPEDRIVE={fire_pipedrive} (must be False before proceeding)")
    if fire_pipedrive is not False:
        raise SystemExit("ABORT: FIRE_PIPEDRIVE is not false live -- STOP action may have regressed. Not patching.")

    if not apply_it:
        with open(LOCAL_PATH, encoding="utf-8") as f:
            local = json.load(f)
        local_by_name = {n["name"]: n for n in local["nodes"]}
        live_by_name = {n["name"]: n for n in live_before["nodes"]}
        to_add = set(local_by_name) - set(live_by_name)
        to_remove = set(live_by_name) - set(local_by_name)

        def _comparable(n):
            return {k: v for k, v in n.items() if k != "position"}
        changed = {n for n in local_by_name if n in live_by_name
                   and _comparable(live_by_name[n]) != _comparable(local_by_name[n])}

        print("DRY RUN (pass --apply to actually patch).")
        print(f"to_add={sorted(to_add)}")
        print(f"  matches expected: {to_add == EXPECTED_ADD}")
        print(f"to_remove={sorted(to_remove)}")
        print(f"  matches expected: {to_remove == EXPECTED_REMOVE}")
        print(f"changed={sorted(changed)}")
        print(f"  matches expected: {changed == EXPECTED_CHANGED}")
        sys.exit(0)

    safe_patch_workflow(n8n, live_id=LIVE_ID, local_path=LOCAL_PATH, label="p1-fix",
                         expected_to_add=EXPECTED_ADD, expected_to_remove=EXPECTED_REMOVE,
                         expected_param_diffs=EXPECTED_CHANGED)

    # post-patch: re-confirm FIRE_PIPEDRIVE is STILL false (safe_patch_workflow preserves whatever
    # was live, but this is cheap and this is a P1 -- verify, don't assume).
    live_after = n8n(f"/api/v1/workflows/{LIVE_ID}")
    fire_after = next(
        a["value"] for n in live_after["nodes"] if n["name"] == "CONFIG"
        for a in n["parameters"]["assignments"]["assignments"] if a["name"] == "FIRE_PIPEDRIVE"
    )
    label_ids_anywhere = "label_ids" in json.dumps(live_after["nodes"])
    dnc_label_id_anywhere = "52a7c290-fc73-11f0-ad98-81d4703453f3" in json.dumps(live_after["nodes"])
    print(f"post-patch FIRE_PIPEDRIVE={fire_after} label_ids_anywhere={label_ids_anywhere} "
          f"dnc_label_id_anywhere={dnc_label_id_anywhere}")
    if fire_after is not False or label_ids_anywhere or dnc_label_id_anywhere:
        raise SystemExit("POST-PATCH VERIFY FAILED -- live workflow still capable of writing the label.")
    print("P1 FIX verified live: sweep can no longer touch label_ids, FIRE_PIPEDRIVE still false.")
