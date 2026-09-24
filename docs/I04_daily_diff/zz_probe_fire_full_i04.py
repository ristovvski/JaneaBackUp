#!/usr/bin/env python3
"""Fire the FULL dnc_i04_daily_diff pipeline (walk -> store -> diff -> report -> prune) as a
webhook-triggered test copy, now that i04_snapshots exists. onReceived + poll (a synchronous
wait would hit Cloudflare's ~100-120s front-end timeout on a multi-minute run -- confirmed
live earlier). This is the FIRST real snapshot -- expect the diff step to report "no previous
snapshot" (first run), which is itself a real, correct behavior to verify.
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
    wf_json = build("zz_probe_i04_full_fire", test_webhook=True)
    print("Creating full-pipeline test workflow...")
    created = n8n("/api/v1/workflows", "POST",
                  {"name": wf_json["name"], "nodes": wf_json["nodes"],
                   "connections": wf_json["connections"], "settings": wf_json["settings"]})
    wid = created["id"]
    print(f"created id={wid}", flush=True)

    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        live = n8n(f"/api/v1/workflows/{wid}")
        if live.get("active") is not True:
            print("ACTIVATION DID NOT TAKE -- aborting")
            sys.exit(1)
        time.sleep(2)

        webhook_url = BASE + "/webhook/i04-test-fire"
        print(f"Firing {webhook_url} ...", flush=True)
        t0 = time.time()
        req = urllib.request.Request(webhook_url, method="POST", data=b"{}",
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                print(f"webhook ack: {r.status}", flush=True)
        except urllib.error.HTTPError as e:
            print(f"webhook error: {e.code} {e.read()[:300]}", flush=True)
            print("(continuing to poll anyway -- an ack error doesn't always mean the run didn't start)")

        print("polling for execution (checking every 10s, up to 20 min)...", flush=True)
        exec_id = None
        for i in range(120):
            time.sleep(10)
            execs = n8n(f"/api/v1/executions?workflowId={wid}&limit=1")
            data = execs.get("data") or []
            elapsed = time.time() - t0
            if not data:
                print(f"  [{elapsed:.0f}s] no execution recorded yet", flush=True)
                continue
            e = data[0]
            exec_id = e["id"]
            status = e.get("status")
            print(f"  [{elapsed:.0f}s] execution {exec_id}: {status}", flush=True)
            if status in ("success", "error", "crashed"):
                break
        else:
            print("TIMED OUT after 20 min -- leaving workflow active for manual inspection")
            print(f"workflow id: {wid} (NOT deleted)")
            return

        detail = n8n(f"/api/v1/executions/{exec_id}?includeData=true")
        d = detail.get("data", {})
        err = d.get("resultData", {}).get("error")
        run = d.get("resultData", {}).get("runData", {})
        print(f"\nnodes that ran: {list(run.keys())}")
        if err:
            print(f"\nERROR: {json.dumps(err)[:2000]}")
        for key in ("Walk Leads Reduce", "Walk Persons Reduce", "Build Snapshot", "Diff",
                    "Combine Report", "Compute Prune List"):
            if key in run:
                item = run[key][0]["data"]["main"][0][0]["json"]
                # avoid dumping the full leads_json/persons_json blobs -- just the shape
                trimmed = {k: (v if not (isinstance(v, str) and len(v) > 300) else f"<{len(v)} chars>")
                           for k, v in item.items()}
                print(f"\n{key}: {json.dumps(trimmed, indent=1)}")
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"\ncleaned up {wid}")


if __name__ == "__main__":
    main()
