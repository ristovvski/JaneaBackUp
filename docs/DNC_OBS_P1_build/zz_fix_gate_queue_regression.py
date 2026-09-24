#!/usr/bin/env python3
"""Fix the queue-mode regression I accidentally caused: a routine domain-block patch used a
diffing script that only knew how to ADD nodes, never remove them, so it silently resurrected the
whole dnc_gate_queue apparatus Nik deliberately removed on 2026-09-02 (the queue never drained --
`dnc_gate_queue` doesn't exist, `dnc_gate_queue_drainer` never ran once -- every "queued" response
was a promise that could never be kept).

This replaces the gate's ENTIRE node list and connections with the corrected local build (15
nodes: the honest-410 retrieve path + synchronous-only submit path + the domain-block addition),
dropping the 11 erroneously-resurrected queue nodes. Hard aborts if the live/local diff doesn't
match EXACTLY what's expected -- this must not silently do something different from what was
verified by hand first.
"""
import json, os, ssl, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
CA = os.environ.get("REQUESTS_CA_BUNDLE")
ctx = ssl.create_default_context(cafile=CA) if CA and os.path.exists(CA) else None

LIVE_ID = "9aP2dP0jgAPFGDvA"
EXPECTED_TO_REMOVE = {"Mark Sync Done", "Log Ingress", "Enqueue Rows", "Build Retrieve Items",
                      "Build Retrieve Report", "Is Sync?", "Check Queue Depth", "Build Queue Response",
                      "Decide Sync Or Queue", "Respond Queued", "Lookup Queue By Key"}
EXPECTED_KEPT_COUNT = 15


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def main():
    with open(os.path.join(HERE, "workflows", "dnc_pre_add_gate", "dnc_pre_add_gate.json"), encoding="utf-8") as f:
        local = json.load(f)
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    live_by_name = {n["name"]: n for n in live["nodes"]}
    local_by_name = {n["name"]: n for n in local["nodes"]}

    to_remove = set(live_by_name) - set(local_by_name)
    to_add = set(local_by_name) - set(live_by_name)
    if to_remove != EXPECTED_TO_REMOVE:
        print("ABORT: nodes-to-remove doesn't match expected set.")
        print("  expected:", sorted(EXPECTED_TO_REMOVE))
        print("  actual:  ", sorted(to_remove))
        sys.exit(1)
    if to_add:
        print("ABORT: expected zero new nodes, got:", sorted(to_add))
        sys.exit(1)
    if len(local_by_name) != EXPECTED_KEPT_COUNT:
        print("ABORT: local node count changed unexpectedly:", len(local_by_name))
        sys.exit(1)

    param_diffs = [name for name in local_by_name
                   if name in live_by_name and live_by_name[name].get("parameters") != local_by_name[name].get("parameters")]
    print("nodes being REMOVED (queue-mode regression, confirmed matches expected):", sorted(to_remove))
    print("nodes whose PARAMS differ (will be updated to local's version):", param_diffs)
    print("nodes UNCHANGED:", sorted(set(local_by_name) - set(param_diffs)))

    # final node list = exactly local's 15 nodes (this drops the 11 extras entirely).
    new_nodes = list(local["nodes"])

    was_active = live.get("active", False)
    print(f"\nlive is currently active={was_active}. Proceeding: deactivate -> PUT (15 nodes, "
          f"corrected connections) -> reactivate -> verify.")
    n8n(f"/api/v1/workflows/{LIVE_ID}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{LIVE_ID}", "PUT",
        {"name": live["name"], "nodes": new_nodes, "connections": local["connections"], "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{LIVE_ID}/activate", "POST", {})
    time.sleep(1)

    verify = n8n(f"/api/v1/workflows/{LIVE_ID}")
    verify_names = sorted(n["name"] for n in verify["nodes"])
    expected_names = sorted(local_by_name.keys())
    print(f"\npost-fix: active={verify.get('active')} node_count={len(verify['nodes'])}")
    print("names match expected exactly:", verify_names == expected_names)
    if verify_names != expected_names:
        print("  live: ", verify_names)
        print("  expect:", expected_names)
        sys.exit(1)
    print("connections keys:", sorted(verify["connections"].keys()))
    print("\nFIX VERIFIED.")


if __name__ == "__main__":
    main()
