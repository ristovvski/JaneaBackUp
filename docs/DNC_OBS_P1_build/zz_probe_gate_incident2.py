#!/usr/bin/env python3
"""
Second gate outage (Clay per-row burst caused 502s -> n8n auto-deactivated dnc_pre_add_gate
again). Step 1 of the fix: find the live workflow, inspect its current settings (looking for any
concurrency/queue-mode option), reactivate it, and verify the Barry fixture. Read + reactivate
only -- no destructive action.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")


def load_env():
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


load_env()
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def main():
    print("Listing workflows to find dnc_pre_add_gate...")
    page = n8n("/api/v1/workflows?limit=250")
    items = page.get("data", [])
    gate = next((w for w in items if w.get("name") == "dnc_pre_add_gate"), None)
    if not gate:
        print("NOT FOUND by name 'dnc_pre_add_gate' in first 250 -- widen search")
        sys.exit(1)
    wid = gate["id"]
    print(f"found id={wid} active={gate.get('active')}")

    full = n8n(f"/api/v1/workflows/{wid}")
    print("settings:", json.dumps(full.get("settings", {}), indent=2))

    if not full.get("active"):
        print("Reactivating...")
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(2)
        check = n8n(f"/api/v1/workflows/{wid}")
        print("post-activate active:", check.get("active"))
    else:
        print("already active")

    # recent executions -- how many crashed, roughly when
    execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=50")
    rows = execs.get("data", [])
    statuses = {}
    for e in rows:
        s = e.get("status", "?")
        statuses[s] = statuses.get(s, 0) + 1
    print("last 50 executions by status:", statuses)
    if rows:
        print("most recent:", rows[0].get("startedAt"), rows[0].get("status"))
        print("oldest of these 50:", rows[-1].get("startedAt"), rows[-1].get("status"))


if __name__ == "__main__":
    main()
