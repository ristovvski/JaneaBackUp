"""
S1 fire driver, Pipedrive-label wave (2026-08-14).

Union wave 1 of 2: Pipedrive lead label "3. Responded" (c9d4b550-bcf3-11ef-a843-357f91e826ec),
verified live -- 1,722 leads currently carry it (matches the spec doc's own ~1,715-and-climbing
estimate). Each candidate gets reply_category='unclassified' since a bare Pipedrive label carries
no specific category (Interested/Not Interested/etc.) -- an honest placeholder, never a guess,
never left null (the exact 116-row gap the schema assert exists to close).

Wave 2 (Smartlead any-campaign history REPLY scan + HeyReach reply backfill) is a separate,
larger scan across all ~117 Smartlead campaigns -- run dnc_scan_s1_smartlead_replies.py for that
and fire its output through this SAME webhook as a second wave; upsert-merge makes the two waves
safely idempotent and order-independent (whichever wave finds a person first creates the row,
the other wave's later arrival just enriches/upgrades it, never conflicts).
"""
import os
import sys
import json
import time
import requests

WF_ID = "BxJZmz1HY5AdaQqE"
WEBHOOK_PATH = "{{WEBHOOK_DNC_S1_RESPONDED_TO_DNC}}"
POLL_INTERVAL_S = 10
POLL_DEADLINE_S = 10 * 60
RESPONDED_LABEL_ID = "c9d4b550-bcf3-11ef-a843-357f91e826ec"


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


def scan_pipedrive_responded():
    token = os.environ["PIPEDRIVE_API_TOKEN"]
    start = 0
    person_ids = set()
    while True:
        r = requests.get("https://api.pipedrive.com/v1/leads",
                          params={"api_token": token, "start": start, "limit": 500, "sort": "add_time DESC"},
                          timeout=30)
        d = r.json()
        rows = d.get("data") or []
        for lead in rows:
            if lead.get("label_ids") and RESPONDED_LABEL_ID in lead["label_ids"] and lead.get("person_id"):
                person_ids.add(str(lead["person_id"]))
        pag = (d.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
        if start > 60000:
            print("SAFETY STOP at start > 60000")
            break
    return sorted(person_ids)


def running_executions(base_url):
    r = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "status": "running"},
                      headers=n8n_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("data", [])


def get_combine(base_url, eid):
    r = requests.get(f"{base_url}/api/v1/executions/{eid}", params={"includeData": "true"},
                      headers=n8n_headers(), timeout=30)
    run_data = r.json().get("data", {}).get("resultData", {}).get("runData", {})
    combine = run_data.get("S1 Combine")
    if not combine:
        return None
    return combine[0]["data"]["main"][0][0]["json"]


def main():
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    person_ids = scan_pipedrive_responded()
    print(f"Pipedrive '3. Responded' label scan: {len(person_ids)} person ids.")
    candidates = [{"pipedrive_person_id": pid, "reply_category": "unclassified",
                   "source": "pipedrive_responded_label"} for pid in person_ids]

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
                           json={"offset": offset, "candidates": candidates}, timeout=90)
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
            print("  no S1 Combine output -- stopping, check manually")
            break
        total_matched += out["matches_this_chunk"]
        total_skipped_no_identity += out.get("skipped_no_identity", 0)
        print(f"  matches_this_chunk={out['matches_this_chunk']} skipped_no_identity={out.get('skipped_no_identity', 0)} "
              f"done={out['done']} next_offset={out.get('next_offset')} total_candidates={out['total_candidates']}")
        if out["done"]:
            break
        offset = out["next_offset"]

    print(f"\n=== FINAL: matched={total_matched} skipped_no_identity={total_skipped_no_identity} "
          f"(source population {len(person_ids)}) ===")


if __name__ == "__main__":
    main()
