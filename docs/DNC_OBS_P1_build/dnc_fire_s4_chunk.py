"""
Structural concurrency guard + multi-campaign cursor driver for dnc_s4_event_populations.

Same discipline as dnc_fire_pipedrive_chunk.py: refuses to fire if anything is already running,
resolves the specific execution id it creates, polls it to terminal. Additionally cycles through
all 6 (source_type, campaign_id) pairs, paging each one to completion before moving to the next.
"""
import os
import sys
import time
import json
import requests

WF_ID = "hhdnug5xdFLAxrOg"
WEBHOOK_PATH = "{{WEBHOOK_DNC_S4_EVENT_POPULATIONS}}"
POLL_INTERVAL_S = 15
POLL_DEADLINE_S = 20 * 60

CAMPAIGNS = [
    ("smartlead", 3686193, "Ai4 2026"),
    ("smartlead", 3686187, "Ai4 2026"),
    ("smartlead", 3686184, "Ai4 2026"),
    ("smartlead", 3686181, "Ai4 2026"),
    ("heyreach", 513000, "Ai4 2026 - Rune - LinkedIn"),
    ("heyreach", 512995, "Ai4 2026 - Mario - LinkedIn"),
]


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
    r = requests.get(
        f"{base_url}/api/v1/executions",
        params={"workflowId": WF_ID, "status": "running"},
        headers=n8n_headers(), timeout=20,
    )
    r.raise_for_status()
    return r.json().get("data", [])


def fire_one_chunk(base_url, source_type, campaign_id, campaign_name, offset):
    running = running_executions(base_url)
    if running:
        print(f"REFUSING TO FIRE: {len(running)} execution(s) already running.")
        sys.exit(1)

    pre_fire_latest_list = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "limit": 1},
                                         headers=n8n_headers(), timeout=20).json().get("data", [])
    pre_fire_latest = pre_fire_latest_list[0]["id"] if pre_fire_latest_list else None

    url = f"{base_url}/webhook/{WEBHOOK_PATH}"
    body = {"source_type": source_type, "campaign_id": campaign_id,
            "campaign_name": campaign_name, "offset": offset}
    try:
        r = requests.post(url, json=body, timeout=90)
        if r.status_code == 200:
            print(f"  response: {r.text[:300]}")
    except requests.exceptions.RequestException as e:
        print(f"  (client-side disconnect, expected: {type(e).__name__})")

    time.sleep(3)
    running = running_executions(base_url)
    if len(running) == 1:
        eid = running[0]["id"]
    elif len(running) == 0:
        # chunk may have finished faster than this check -- same benign race fixed in
        # dnc_fire_reversal_chunk.py: confirm via a NEW execution id, not just "0 running".
        latest_list2 = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "limit": 1},
                                     headers=n8n_headers(), timeout=20).json().get("data", [])
        if not latest_list2 or latest_list2[0]["id"] == pre_fire_latest:
            print("ABORTING: no new execution appeared at all.")
            sys.exit(1)
        eid = latest_list2[0]["id"]
        print(f"  (chunk already finished by the time of the check: {eid})")
    else:
        print(f"ABORTING: expected exactly 1 new running execution, found {len(running)}: {running}")
        sys.exit(1)
    print(f"  execution {eid} confirmed, polling...")

    deadline = time.time() + POLL_DEADLINE_S
    while time.time() < deadline:
        r = requests.get(f"{base_url}/api/v1/executions/{eid}", headers=n8n_headers(), timeout=20)
        status = r.json().get("status")
        if status in ("success", "error", "crashed", "canceled"):
            print(f"  execution {eid} -> {status}")
            if status != "success":
                print("Chunk did NOT complete cleanly. Stopping.")
                sys.exit(1)
            return eid
        time.sleep(POLL_INTERVAL_S)
    print(f"TIMEOUT waiting on {eid}")
    sys.exit(1)


def get_execution_combine_output(base_url, eid):
    r = requests.get(f"{base_url}/api/v1/executions/{eid}", params={"includeData": "true"},
                      headers=n8n_headers(), timeout=30)
    d = r.json()
    run_data = d.get("data", {}).get("resultData", {}).get("runData", {})
    combine = run_data.get("S4 Combine")
    if not combine:
        return None
    return combine[0]["data"]["main"][0][0]["json"]


def main():
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")

    for source_type, campaign_id, campaign_name in CAMPAIGNS:
        print(f"\n=== {source_type} {campaign_id} ({campaign_name}) ===")
        offset = 0
        while True:
            eid = fire_one_chunk(base_url, source_type, campaign_id, campaign_name, offset)
            out = get_execution_combine_output(base_url, eid)
            if out is None:
                print("  no S4 Combine output found -- stopping this campaign, check manually")
                break
            print(f"  matches_this_chunk={out['matches_this_chunk']} done={out['done']} next_offset={out.get('next_offset')}")
            if out["done"]:
                break
            offset = out["next_offset"]


if __name__ == "__main__":
    main()
