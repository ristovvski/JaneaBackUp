#!/usr/bin/env python3
"""Deploy a webhook-triggered test copy of dnc_i04_daily_diff, fire it once, watch it run
(this is a real full-estate walk -- ~58k leads + persons -- so it will take a while), report the
result, then clean up. Read-only against Pipedrive; writes only to the NEW i04_snapshots table.
"""
import json, os, ssl, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_i04 import build  # noqa: E402

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
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def main():
    wf_json = build("zz_probe_i04_test_fire", test_webhook=True)
    print("Creating test workflow...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}")

    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE -- aborting")
            sys.exit(1)

        webhook_url = BASE + "/webhook/i04-test-fire"
        print(f"Firing {webhook_url} -- this is a full ~58k-lead walk, expect several minutes...")
        time.sleep(2)
        req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                print(f"webhook ack: {r.status} (onReceived mode -- doesn't wait for completion)")
        except urllib.error.HTTPError as e:
            print(f"webhook error: {e.code} {e.read()[:300]}")

        # poll executions until the run completes
        print("polling for execution completion...")
        exec_id = None
        for _ in range(120):  # up to 20 minutes
            time.sleep(10)
            execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=1")
            data = execs.get("data") or []
            if not data:
                continue
            e = data[0]
            exec_id = e["id"]
            status = e.get("status")
            elapsed = time.time() - t0
            print(f"  [{elapsed:.0f}s] execution {exec_id}: {status}")
            if status in ("success", "error", "crashed"):
                break
        else:
            print("TIMED OUT waiting for completion (20 min) -- leaving workflow active for manual inspection")
            print(f"workflow id: {wid}")
            sys.exit(2)

        detail = n8n(f"/api/v1/executions/{exec_id}?includeData=true")
        d = detail.get("data", {})
        err = d.get("resultData", {}).get("error")
        run = d.get("resultData", {}).get("runData", {})
        print(f"\nnodes that ran: {list(run.keys())}")
        if err:
            print(f"\nERROR: {json.dumps(err)[:1500]}")
        if "Combine Report" in run:
            report = run["Combine Report"][0]["data"]["main"][0][0]["json"]
            print(f"\nREPORT: {json.dumps(report, indent=1)[:2000]}")
        if "Compute Prune List" in run:
            prune = run["Compute Prune List"][0]["data"]["main"][0][0]["json"]
            print(f"\nPRUNE: {json.dumps(prune, indent=1)}")

    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"\ncleaned up test workflow {wid}")


if __name__ == "__main__":
    main()
