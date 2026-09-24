"""
RETIRED 2026-09-15 (Nik's GO -- "replace the frozen-snapshot replay entirely, don't layer on it").
dnc_s2_meeting_to_dnc was rebuilt to poll Pipedrive live every day (label "5. Meeting" + deal stage
"Qualified Meeting Set", each in the last 24h) -- it no longer accepts a person_ids/offset webhook
body at all, so this script's whole contract is gone. Kept on disk for history, not runnable
against the current live workflow. Use dnc_fire_s2_daily.py instead (no payload needed -- the
webhook just re-runs the same live query the daily schedule would).

--- original docstring below, historical only ---

Structural concurrency guard + chunked-fire driver for dnc_s2_meeting_to_dnc.

Same discipline as dnc_fire_reversal_chunk.py: candidate set is the auditor's frozen person-id
union (label "5. Meeting" UNION deal stage "Qualified Meeting Set"), loaded off disk and POSTed
in full on every chunk call -- this driver never re-derives the union itself. Currently BLOCKED:
the auditor's r3_s2_persons.json has not landed on disk yet (checked repeatedly, absent as of
2026-08-14). Re-run `find` for it before invoking main() for real.
"""
import os
import sys
import json
import time
import requests

WF_ID = "E0oTTvHHQ0hVTNDD"
WEBHOOK_PATH = "{{WEBHOOK_DNC_S2_MEETING_TO_DNC}}"
POLL_INTERVAL_S = 10
POLL_DEADLINE_S = 10 * 60

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "audit-artifacts")
PERSON_IDS_PATH = os.path.join(ARTIFACT_DIR, "r3_s2_persons.json")


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


def load_person_ids():
    if not os.path.exists(PERSON_IDS_PATH):
        raise FileNotFoundError(
            f"{PERSON_IDS_PATH} does not exist yet -- waiting on the auditor's r3_s2_persons.json "
            "(union of label '5. Meeting' + deal stage 'Qualified Meeting Set', expected 541 ids)."
        )
    with open(PERSON_IDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # actual shape (found live 2026-08-14): {label_persons, stage_persons, union} -- union is the
    # 541-id list this scenario needs; label_persons/stage_persons are kept in the file for
    # provenance/cross-check, not consumed here.
    if isinstance(data, dict) and "union" in data:
        ids = data["union"]
    elif isinstance(data, dict) and "person_ids" in data:
        ids = data["person_ids"]
    else:
        ids = data
    deduped = sorted(set(str(i) for i in ids))
    assert len(deduped) == 541, f"expected 541 unique person ids in the union, got {len(deduped)}"
    return deduped


def running_executions(base_url):
    r = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "status": "running"},
                      headers=n8n_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


def get_combine(base_url, eid):
    r = requests.get(f"{base_url}/api/v1/executions/{eid}", params={"includeData": "true"},
                      headers=n8n_headers(), timeout=30)
    run_data = r.json().get("data", {}).get("resultData", {}).get("runData", {})
    combine = run_data.get("S2 Combine")
    if not combine:
        return None
    return combine[0]["data"]["main"][0][0]["json"]


def main():
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    person_ids = load_person_ids()
    print(f"Loaded {len(person_ids)} person ids from {PERSON_IDS_PATH}.")
    offset = 0
    total_matched = 0
    total_skipped_no_identity = 0
    chunk_n = 0
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
                           json={"offset": offset, "person_ids": person_ids}, timeout=90)
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
            print("  no S2 Combine output -- stopping, check manually")
            break
        total_matched += out["matches_this_chunk"]
        total_skipped_no_identity += out.get("skipped_no_identity", 0)
        print(f"  matches_this_chunk={out['matches_this_chunk']} skipped_no_identity={out.get('skipped_no_identity', 0)} "
              f"done={out['done']} next_offset={out.get('next_offset')} total_candidates={out['total_candidates']}")
        if out["done"]:
            break
        offset = out["next_offset"]

    print(f"\n=== FINAL: matched={total_matched} skipped_no_identity={total_skipped_no_identity} ===")


if __name__ == "__main__":
    main()
