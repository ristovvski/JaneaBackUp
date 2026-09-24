"""
Structural concurrency guard for firing dnc_projections_sweep chunks.

Incident, 2026-08-12: the sweep was fired three times while a previous fire's execution was still
invisible-in-progress (n8n hides running executions from the plain executions list until they
finish), tripling memory use and OOM-crashing all three. Auditor's post-mortem, verbatim: "before
firing any chunk, CHECK no execution of this workflow is running... fire only on previous-terminal.
Chunked batches fired concurrently would reproduce the OOM exactly."

This script is that check, made structural instead of a habit I have to remember under pressure:
refuses to fire if anything is already running, fires exactly once, resolves the exact execution id
it created (never "the newest execution" -- that was the ambiguity that let the incident happen),
and polls that id by id until terminal. Run it again to fire the next chunk; it is the only
sanctioned way to fire this workflow's webhook from now on.
"""
import os
import sys
import time
import json
import requests

WF_ID = "8qVXtI2ez5o6a9hc"
WEBHOOK_PATH = "{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}"
POLL_INTERVAL_S = 30
POLL_DEADLINE_S = 55 * 60


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


def main():
    load_env()
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")

    running = running_executions(base_url)
    if running:
        print(f"REFUSING TO FIRE: {len(running)} execution(s) already running for this workflow:")
        for e in running:
            print(f"  {e['id']}  started {e.get('startedAt')}")
        print("Wait for these to reach a terminal state, then run this script again.")
        sys.exit(1)

    print("No running executions. Firing one chunk...")
    url = f"{base_url}/webhook/{WEBHOOK_PATH}"
    start = time.time()
    try:
        requests.post(url, json={}, timeout=(10, 30))
    except requests.exceptions.RequestException as e:
        # Expected: n8n's responseNode mode / Cloudflare edge times out the client long before the
        # workflow itself finishes. This is NOT a signal to re-fire -- resolve the real execution id
        # below instead of guessing from this.
        print(f"(client-side disconnect while firing, expected: {type(e).__name__}) -- resolving execution id now")

    # Resolve the exact execution this fire created. Must be exactly one; anything else means the
    # guard above raced with something else and this run should stop, not guess.
    time.sleep(3)
    running = running_executions(base_url)
    if len(running) != 1:
        print(f"ABORTING: expected exactly 1 new running execution, found {len(running)}: {running}")
        print("Do not fire again. Investigate manually before proceeding.")
        sys.exit(1)

    eid = running[0]["id"]
    print(f"Confirmed single execution: {eid}. Polling until terminal...")

    deadline = time.time() + POLL_DEADLINE_S
    while time.time() < deadline:
        r = requests.get(f"{base_url}/api/v1/executions/{eid}", headers=n8n_headers(), timeout=20)
        d = r.json()
        status = d.get("status")
        print(f"  {time.strftime('%H:%M:%S')} {eid}: {status}")
        if status in ("success", "error", "crashed", "canceled"):
            print(f"TERMINAL: {eid} -> {status}")
            if status != "success":
                print("Chunk did NOT complete cleanly. Do not fire the next chunk until this is investigated.")
                sys.exit(1)
            sys.exit(0)
        time.sleep(POLL_INTERVAL_S)

    print(f"TIMEOUT: {eid} still not terminal after {POLL_DEADLINE_S}s. Do not fire again -- investigate.")
    sys.exit(1)


if __name__ == "__main__":
    main()
