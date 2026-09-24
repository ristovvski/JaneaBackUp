import glob
import os
import sys
import json
import time
import requests

WF_ID = "LQRfmEl4Wv0qpXsI"
WEBHOOK_PATH = "{{WEBHOOK_DNC_LABEL_REVERSAL}}"
POLL_INTERVAL_S = 10
POLL_DEADLINE_S = 10 * 60

# Authoritative candidate source: the auditor's frozen snapshot of every id the projection
# actually labelled. NOT re-derived from the registry.
ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit-artifacts")
OLD_FROZEN_IDS_PATH = os.path.join(ARTIFACT_DIR, "dnc_projection_labelled_1978.json")
MARTINETS_PRELABELLED_ID = "4538ad40-4eb7-11f1-9d0a-8ddac4d89290"

# Nik's fire-prep final (2026-08-14): the auditor's boundary check found 9 of the 1,977 already
# drifted (label lost by some other actor, unrelated to us) and 5 leads that no longer resolve at
# all -- the corrected strip set is the frozen 1,977 MINUS Person-82f6ebe9's lead (6cff0010-...) and
# Person-b7b67214's lead (b74dbc50-...), both explicit opt-outs whose labels STAY per Melisa's ruling
# (client reason). The auditor is exporting a NEW frozen file with this already applied -- this
# script prefers that fresh export the moment it lands (auditor-authoritative, never re-derived
# here) and only falls back to computing the same 1,975 from the OLD file + these 2 known ids as a
# stopgap so nothing blocks on file-naming uncertainty. Either way this is NOT what actually fires
# without the auditor's fresh baseline + green + Nik's explicit word -- see main()'s hold.
KNOWN_OPT_OUT_LEAD_IDS = ["6cff0010-34a3-11f0-8085-b3a2a921474b", "b74dbc50-e3dc-11ef-8054-5799e8b6d1a7"]


def _looks_like_lead_id(s):
    # Pipedrive v1 lead ids are uuid-shaped ("00144f20-67c3-11f0-9e13-cf00019a48f7").
    return isinstance(s, str) and len(s) >= 30 and s.count("-") >= 3


def _find_fresh_frozen_export():
    # look for anything the auditor may have exported AFTER the original 1978-count artifact and
    # the 1977-count cross-check -- broad glob since the exact filename isn't known yet, newest
    # file wins if more than one candidate matches. Explicitly excludes MANIFEST_* files -- found
    # live 2026-08-14: MANIFEST_reversal_1975.json (a companion doc describing the derivation, NOT
    # the actual id list -- no lead_ids key at all) matched the *1975* glob and got silently
    # treated as if it WERE the id list, iterating its dict keys as "ids" (10 garbage strings).
    # Shape-validated below too, not just name-filtered, so this can't recur under a new filename.
    candidates = []
    for pattern in ("*1975*.json", "reversal_target_*.json", "dnc_projection_labelled_*.json"):
        candidates.extend(glob.glob(os.path.join(ARTIFACT_DIR, pattern)))
    candidates = [c for c in set(candidates)
                  if os.path.basename(c) not in ("dnc_projection_labelled_1978.json", "reversal_target_1977.json")
                  and "manifest" not in os.path.basename(c).lower()]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def load_frozen_ids():
    fresh = _find_fresh_frozen_export()
    if fresh:
        with open(fresh, encoding="utf-8") as f:
            data = json.load(f)
        ids = data["lead_ids"] if isinstance(data, dict) and "lead_ids" in data else data
        if not isinstance(ids, list) or not ids or not all(_looks_like_lead_id(i) for i in ids):
            print(f"REJECTING {fresh}: does not look like a lead_ids list (shape check failed) -- "
                  f"falling back to the known-good stopgap instead of trusting it blindly.")
        else:
            print(f"Using the auditor's fresh export: {fresh}")
            ids = [i for i in ids if i != MARTINETS_PRELABELLED_ID]
            print(f"  {len(ids)} ids after excluding Martinets defensively (file may already exclude him).")
            return ids

    print(f"No fresh auditor export found yet -- falling back to {OLD_FROZEN_IDS_PATH} "
          f"+ the 2 known opt-out exclusions as a stopgap (cross-check against the auditor's own "
          f"export once it lands, do not treat this fallback as authoritative on its own).")
    with open(OLD_FROZEN_IDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    ids = data["lead_ids"]
    assert len(ids) == data["count"] == 1978, f"artifact shape drifted: len={len(ids)} count={data.get('count')}"
    filtered = [i for i in ids if i != MARTINETS_PRELABELLED_ID and i not in KNOWN_OPT_OUT_LEAD_IDS]
    assert len(filtered) == 1975, f"expected 1975 after excluding Martinets + the 2 opt-outs, got {len(filtered)}"
    return filtered


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def n8n_headers():
    return {"X-N8N-API-KEY": os.environ["N8N_API_KEY"], "accept": "application/json"}


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


def load_live_exclusion_ids():
    # last-minute drift the auditor names at re-anchor (e.g. the 5 vanished leads) -- a plain JSON
    # array of lead ids, same frozen-external-list shape as frozen_ids. Optional: absent file =
    # no additional exclusions (the frozen export itself may already be fully current).
    path = os.path.join(ARTIFACT_DIR, "live_exclusion_ids.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ids = data["lead_ids"] if isinstance(data, dict) and "lead_ids" in data else data
    print(f"Loaded {len(ids)} live_exclusion_ids from {path}.")
    return list(ids)


# HOLD -- per Nik (2026-08-14): "Fire on the chain: his fresh baseline -> his green -> Nik's word."
# This script refuses to POST anything live until this is flipped, regardless of FIRE_REVERSAL's
# own state on the deployed workflow -- a second, independent gate on the driver side so a bare
# `python dnc_fire_reversal_chunk.py` can never accidentally fire ahead of that chain completing.
CLEARED_TO_FIRE = True  # Nik, 2026-08-14: auditor's baseline green + bracketed clean (0 leads
# updated during the walk) + Nik's explicit word -- chain complete, FIRE.


def main():
    if not CLEARED_TO_FIRE:
        print("HOLD: CLEARED_TO_FIRE is False. Waiting on the auditor's fresh baseline + his green "
              "+ Nik's explicit word before this driver will POST anything. Flip the constant at "
              "the top of this file only once all three have actually happened.")
        sys.exit(1)
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    frozen_ids = load_frozen_ids()
    live_exclusion_ids = load_live_exclusion_ids()
    print(f"Loaded {len(frozen_ids)} frozen ids (Martinets excluded), "
          f"{len(live_exclusion_ids)} additional live exclusions.")
    # RESUME at 100, not 0 -- the first real chunk (execution 24377) already correctly stripped
    # the DNC label from the first 100 ids in this exact file (verified directly: all 100 patch
    # responses success:true, DNC label id absent afterward, every other label untouched). Only
    # R Combine's reporting was broken for that chunk (fixed now, see r_confirm_strip_js); the
    # underlying writes were never wrong. Re-running offset 0 would just re-verify 100 already-
    # correct leads for no benefit and cost real API calls -- resuming past them instead.
    offset = 100
    total_stripped = 100  # the 100 from execution 24377, verified correct, not re-run
    total_already_correct = 0
    total_no_lead = 0
    total_kept_for_reason = 0
    total_no_registry_match = 0
    total_fetch_error = 0
    chunk_n = 0
    last_out = None
    while True:
        chunk_n += 1
        running = running_executions(base_url)
        if running:
            print(f"REFUSING TO FIRE: running executions present: {running}")
            sys.exit(1)
        print(f"\n--- chunk {chunk_n}, offset={offset} ---")
        pre_fire_latest = None
        r_latest = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "limit": 1},
                                 headers=n8n_headers(), timeout=20)
        latest_list = r_latest.json().get("data", [])
        pre_fire_latest = latest_list[0]["id"] if latest_list else None

        try:
            requests.post(f"{base_url}/webhook/{WEBHOOK_PATH}",
                           json={"offset": offset, "frozen_ids": frozen_ids,
                                 "live_exclusion_ids": live_exclusion_ids}, timeout=90)
        except requests.exceptions.RequestException as e:
            print(f"  (client disconnect, expected: {type(e).__name__})")
        time.sleep(3)
        running = running_executions(base_url)
        if len(running) == 1:
            eid = running[0]["id"]
        elif len(running) == 0:
            # chunk may have finished faster than this check -- confirm by finding a NEW execution
            # (not the one seen before firing), rather than assume "0 running" means "never fired".
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
        last_out = out
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
    print(f"\n=== FINAL: stripped={total_stripped} already_correct={total_already_correct} no_lead={total_no_lead} "
          f"kept_for_reason={total_kept_for_reason} no_registry_match={total_no_registry_match} "
          f"fetch_error={total_fetch_error} (sum={total_all}, expected {len(frozen_ids)}) ===")
    if total_fetch_error:
        print(f"ANOMALY: {total_fetch_error} frozen leads no longer resolve at all (vanished since "
              f"the snapshot this run was fired against) -- cross-check against the auditor's own "
              f"vanished-lead list before treating this as fully reconciled.")
    if total_kept_for_reason or total_no_registry_match:
        print(f"ANOMALY: {total_kept_for_reason} frozen leads kept for reason (client/unsubscribe), "
              f"{total_no_registry_match} frozen leads had no registry row at all.")
    else:
        print("No anomalies: every frozen lead (minus Martinets) matched a registry row and none were client/unsubscribe.")


if __name__ == "__main__":
    main()
