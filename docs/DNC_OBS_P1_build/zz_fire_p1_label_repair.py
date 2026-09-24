#!/usr/bin/env python3
"""P1 REPAIR (2026-09-16, Nik's item 4, second half): strip DO NOT CONTACT from every lead WE
labeled via dnc_projections_sweep's now-removed label branch. See
task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md and
DNC_OBS_P1_build/ARTIFACT_prefire_p1_repair_label_strip.md for full context.

Reuses dnc_label_reversal (live id LQRfmEl4Wv0qpXsI, currently ARCHIVE__dnc_label_reversal /
inactive, preserved not deleted per this project's own "never delete incident workflow" rule) --
built for exactly this shape of operation during the 2026-08-14 incident: chunked, frozen-snapshot-
driven, KEEP/REMOVE classified (client/unsubscribe reasons kept, everything else stripped), unions-
preserving (only the DNC label id is ever removed from label_ids, every other label untouched).
Confirmed live == local, zero drift, no rebuild needed.

frozen_ids here = audit-artifacts/p1_frozen_lead_ids_600.json, the exact 600 lead ids this incident
confirmed WE labeled (sourced from the sweep's own execution history, not a registry re-scan) --
this IS the "only remove ours, never a human's" scoping, by construction. Verified beforehand
(dnc_label_incident_final_live.json): 0 of the 600 have reason client/unsubscribe (so the tool's
own KEEP classification is expected to keep 0), 593 currently still carry the label, 6 already
manually corrected by someone else (will resolve as already_correct, a safe no-op), 1 lead
converted/deleted since (Person-a731ca52, person 84141 -- will resolve as fetch_error, a known,
visible, non-crashing outcome, not silently dropped).

Expected final tally: stripped=593 already_correct=6 no_lead=0 kept_for_reason=0
no_registry_match=0 fetch_error=1 (sum=600).
"""
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
WF_ID = "LQRfmEl4Wv0qpXsI"
WEBHOOK_PATH = "{{WEBHOOK_DNC_LABEL_REVERSAL}}"
POLL_INTERVAL_S = 10
POLL_DEADLINE_S = 10 * 60
FROZEN_IDS_PATH = os.path.join(HERE, "audit-artifacts", "p1_frozen_lead_ids_600.json")

# HOLD -- per Nik's own instruction this incident ("§9f.2 pre-post -> my word -> fire"), and this
# project's established discipline for every prior live write. This script refuses to POST or
# reactivate anything until this is flipped to True, regardless of anything else -- read the
# pre-fire artifact, get Nik's explicit go, THEN flip this constant.
CLEARED_TO_FIRE = True  # Nik, 2026-09-16: "GO on the repair" -- explicit word given, pre-fire
# snapshot taken and matches expected numbers exactly (found=599, has_dnc=593, has_responded=429,
# both=425), firing now.


def load_env():
    env_path = os.path.join(os.path.dirname(HERE), ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def n8n_headers():
    return {"X-N8N-API-KEY": os.environ["N8N_API_KEY"], "accept": "application/json"}


def load_frozen_ids():
    with open(FROZEN_IDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    ids = data["lead_ids"]
    assert len(ids) == data["count"] == 600, f"artifact shape drifted: len={len(ids)} count={data.get('count')}"
    return ids


def running_executions(base_url):
    r = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "status": "running"},
                      headers=n8n_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


def get_combine(base_url, eid):
    r = requests.get(f"{base_url}/api/v1/executions/{eid}", params={"includeData": "true"},
                      headers=n8n_headers(), timeout=30)
    run_data = r.json().get("data", {}).get("resultData", {}).get("runData", {})
    combine = run_data.get("R Combine")
    if not combine:
        return None
    return combine[0]["data"]["main"][0][0]["json"]


def get_workflow(base_url, wf_id):
    r = requests.get(f"{base_url}/api/v1/workflows/{wf_id}", headers=n8n_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def set_fire_reversal_and_activate(base_url, wf):
    # flip FIRE_REVERSAL true and reactivate -- the workflow is currently archived/inactive on
    # purpose (preserved after the last incident, per this project's "never delete incident
    # workflow" rule), and a webhook trigger on an inactive workflow never receives production
    # calls, so reactivation is required to fire this at all. Deactivated again in finally().
    cfg = next(n for n in wf["nodes"] if n["name"] == "CONFIG")
    for a in cfg["parameters"]["assignments"]["assignments"]:
        if a["name"] == "FIRE_REVERSAL":
            a["value"] = True
    requests.put(f"{base_url}/api/v1/workflows/{WF_ID}",
                 headers={**n8n_headers(), "Content-Type": "application/json"},
                 json={"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
                       "settings": wf["settings"]}, timeout=60).raise_for_status()
    requests.post(f"{base_url}/api/v1/workflows/{WF_ID}/activate", headers=n8n_headers(), timeout=30).raise_for_status()


def deactivate(base_url):
    requests.post(f"{base_url}/api/v1/workflows/{WF_ID}/deactivate", headers=n8n_headers(), timeout=30).raise_for_status()


def main():
    if not CLEARED_TO_FIRE:
        print("HOLD: CLEARED_TO_FIRE is False. This is the P1 REPAIR -- Nik's own instruction was "
              "'§9f.2 pre-post -> my word -> fire'. Do not flip this constant without his explicit "
              "go on ARTIFACT_prefire_p1_repair_label_strip.md.")
        sys.exit(1)
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    frozen_ids = load_frozen_ids()
    print(f"Loaded {len(frozen_ids)} frozen lead ids (the P1 incident's confirmed 600).")

    wf = get_workflow(base_url, WF_ID)
    was_active = wf.get("active", False)
    set_fire_reversal_and_activate(base_url, wf)
    print(f"Activated dnc_label_reversal, FIRE_REVERSAL=true (was active={was_active}).")

    offset = 0
    total_stripped = 0
    total_already_correct = 0
    total_no_lead = 0
    total_kept_for_reason = 0
    total_no_registry_match = 0
    total_fetch_error = 0
    chunk_n = 0
    try:
        while True:
            chunk_n += 1
            running = running_executions(base_url)
            if running:
                print(f"REFUSING TO FIRE: running executions present: {running}")
                sys.exit(1)
            print(f"\n--- chunk {chunk_n}, offset={offset} ---")
            r_latest = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "limit": 1},
                                     headers=n8n_headers(), timeout=20)
            latest_list = r_latest.json().get("data", [])
            pre_fire_latest = latest_list[0]["id"] if latest_list else None

            try:
                requests.post(f"{base_url}/webhook/{WEBHOOK_PATH}",
                               json={"offset": offset, "frozen_ids": frozen_ids, "live_exclusion_ids": []},
                               timeout=90)
            except requests.exceptions.RequestException as e:
                print(f"  (client disconnect, expected: {type(e).__name__})")
            time.sleep(3)
            running = running_executions(base_url)
            if len(running) == 1:
                eid = running[0]["id"]
            elif len(running) == 0:
                r_latest2 = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "limit": 1},
                                          headers=n8n_headers(), timeout=20)
                latest_list2 = r_latest2.json().get("data", [])
                if not latest_list2 or latest_list2[0]["id"] == pre_fire_latest:
                    print("ABORTING: no new execution appeared at all.")
                    sys.exit(1)
                eid = latest_list2[0]["id"]
                print(f"  (chunk already finished by the time of the check: {eid})")
            else:
                print(f"ABORTING: found {len(running)} running executions, expected 0 or 1: {running}")
                sys.exit(1)
            deadline = time.time() + POLL_DEADLINE_S
            status = None
            while time.time() < deadline:
                r = requests.get(f"{base_url}/api/v1/executions/{eid}", headers=n8n_headers(), timeout=20)
                status = r.json().get("status")
                if status in ("success", "error", "crashed", "canceled"):
                    break
                time.sleep(POLL_INTERVAL_S)
            print(f"  execution {eid} -> {status}")
            if status != "success":
                print("Chunk did not complete cleanly. Stopping.")
                sys.exit(1)
            out = get_combine(base_url, eid)
            if out is None:
                print("  no R Combine output -- stopping, check manually")
                break
            total_stripped += out["stripped_this_chunk"]
            total_already_correct += out["already_correct_this_chunk"]
            total_no_lead += out["no_lead_this_chunk"]
            total_kept_for_reason += out.get("kept_for_reason_this_chunk", 0)
            total_no_registry_match += out.get("no_registry_match_this_chunk", 0)
            total_fetch_error += out.get("fetch_error_this_chunk", 0)
            print(f"  stripped={out['stripped_this_chunk']} already_correct={out['already_correct_this_chunk']} "
                  f"no_lead={out['no_lead_this_chunk']} kept_for_reason={out.get('kept_for_reason_this_chunk', 0)} "
                  f"no_registry_match={out.get('no_registry_match_this_chunk', 0)} "
                  f"fetch_error={out.get('fetch_error_this_chunk', 0)} "
                  f"done={out['done']} next_offset={out.get('next_offset')} total_candidates={out['total_candidates']}")
            if out["done"]:
                break
            offset = out["next_offset"]

        total_all = (total_stripped + total_already_correct + total_no_lead + total_kept_for_reason
                     + total_no_registry_match + total_fetch_error)
        print(f"\n=== FINAL: stripped={total_stripped} already_correct={total_already_correct} "
              f"no_lead={total_no_lead} kept_for_reason={total_kept_for_reason} "
              f"no_registry_match={total_no_registry_match} fetch_error={total_fetch_error} "
              f"(sum={total_all}, expected {len(frozen_ids)}) ===")
        print("Expected: stripped=593 already_correct=6 fetch_error=1, everything else 0.")
    finally:
        deactivate(base_url)
        print("Deactivated dnc_label_reversal again (re-archived, preserved per project convention).")


if __name__ == "__main__":
    main()
