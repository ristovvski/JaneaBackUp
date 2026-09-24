"""
Structural concurrency guard for firing dnc_s2_meeting_to_dnc (rebuilt 2026-09-15, Nik's GO --
live daily poll of label "5. Meeting" + deal stage "Qualified Meeting Set", replacing the frozen-
snapshot replay entirely). Same discipline as dnc_fire_pipedrive_chunk.py: refuses to fire if a
previous execution is still running, resolves the exact execution id it created, polls it to
terminal. No payload needed -- POST {} re-runs the same live query the daily schedule would.
"""
import os
import sys
import time
import json
import requests

WF_ID = "E0oTTvHHQ0hVTNDD"
WEBHOOK_PATH = "{{WEBHOOK_DNC_S2_MEETING_TO_DNC}}"
POLL_INTERVAL_S = 15
POLL_DEADLINE_S = 15 * 60


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
    combine = run_data.get("S2 Combine")
    if not combine:
        return None
    return combine[0]["data"]["main"][0][0]["json"]


def main():
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")

    running = running_executions(base_url)
    if running:
        print(f"REFUSING TO FIRE: {len(running)} execution(s) already running for this workflow:")
        for e in running:
            print(f"  {e['id']}  started {e.get('startedAt')}")
        sys.exit(1)

    print("No running executions. Firing (no payload -- live query runs fresh)...")
    r_latest = requests.get(f"{base_url}/api/v1/executions", params={"workflowId": WF_ID, "limit": 1},
                             headers=n8n_headers(), timeout=20)
    latest_list = r_latest.json().get("data", [])
    pre_fire_latest = latest_list[0]["id"] if latest_list else None

    try:
        requests.post(f"{base_url}/webhook/{WEBHOOK_PATH}", json={}, timeout=(10, 30))
    except requests.exceptions.RequestException as e:
        print(f"  (client-side disconnect while firing, expected: {type(e).__name__}) -- resolving execution id now")

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
        print(f"  (already finished by the time of the check: {eid})")
    else:
        print(f"ABORTING: found {len(running)} running executions, expected 0 or 1: {running}")
        sys.exit(1)

    print(f"Confirmed single execution: {eid}. Polling until terminal...")
    deadline = time.time() + POLL_DEADLINE_S
    status = None
    while time.time() < deadline:
        r = requests.get(f"{base_url}/api/v1/executions/{eid}", headers=n8n_headers(), timeout=20)
        status = r.json().get("status")
        print(f"  {time.strftime('%H:%M:%S')} {eid}: {status}")
        if status in ("success", "error", "crashed", "canceled"):
            break
        time.sleep(POLL_INTERVAL_S)

    if status != "success":
        print(f"TERMINAL (not clean): {eid} -> {status}. Investigate before firing again.")
        sys.exit(1)

    out = get_combine(base_url, eid)
    if out is None:
        print("No S2 Combine output found -- check manually.")
        sys.exit(1)
    print(f"\n=== {eid} ===")
    print(f"count={out.get('count')} distinct_people={out.get('distinct_people')} "
          f"both_signal_people={out.get('both_signal_people')} "
          f"skipped_no_identity={out.get('skipped_no_identity')} "
          f"possibly_truncated={out.get('possibly_truncated')}")


if __name__ == "__main__":
    main()
