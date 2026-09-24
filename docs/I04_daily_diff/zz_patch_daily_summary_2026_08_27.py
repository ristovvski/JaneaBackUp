#!/usr/bin/env python3
"""Surgical live patch for dnc_i04_daily_summary (id 8sT1XjDDVmrz05CA): the 2026-08-27
Load-Watermark-wiring fix + Save-Watermark fail-open + tighter idle-guard cadence. Same discipline
as zz_patch_wf2r_watch_url_only.py / zz_patch_own_domain_guard.py: fetch live, diff every node AND
the connections dict, confirm only the expected surface differs, deactivate -> PUT -> reactivate ->
verify."""
import json, os, ssl, sys, time, urllib.error, urllib.request

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


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


def main():
    LIVE_ID = "8sT1XjDDVmrz05CA"
    EXPECTED_NODE_DIFFS = {"Load Watermark Row", "Save Watermark", "Idle-Guard Trigger",
                            "Check Idle", "Mark Posted Today"}

    with open(os.path.join(HERE, "dnc_i04_daily_summary.json"), encoding="utf-8") as f:
        local = json.load(f)
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    live_by_name = {n["name"]: n for n in live["nodes"]}
    local_by_name = {n["name"]: n for n in local["nodes"]}

    if set(live_by_name.keys()) != set(local_by_name.keys()):
        print("NODE SET MISMATCH -- live:", sorted(live_by_name), "local:", sorted(local_by_name))
        sys.exit(1)

    node_diffs = []
    for name in live_by_name:
        lv, lo = live_by_name[name], local_by_name[name]
        if lv.get("parameters") != lo.get("parameters") or lv.get("onError") != lo.get("onError"):
            node_diffs.append(name)
    unexpected = [d for d in node_diffs if d not in EXPECTED_NODE_DIFFS]
    if unexpected:
        print("UNEXPECTED node param diffs beyond", EXPECTED_NODE_DIFFS, ":", unexpected, "-- aborting.")
        sys.exit(1)
    print("node param diffs (expected set):", node_diffs)

    conn_diffs = [k for k in set(live["connections"]) | set(local["connections"])
                  if live["connections"].get(k) != local["connections"].get(k)]
    unexpected_conn = [d for d in conn_diffs if d not in EXPECTED_NODE_DIFFS]
    if unexpected_conn:
        print("UNEXPECTED connection diffs:", unexpected_conn, "-- aborting.")
        sys.exit(1)
    print("connection diffs (expected set):", conn_diffs)

    new_nodes = [local_by_name[n["name"]] if n["name"] in node_diffs else n for n in live["nodes"]]

    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{LIVE_ID}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{LIVE_ID}", "PUT",
        {"name": live["name"], "nodes": new_nodes, "connections": local["connections"], "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{LIVE_ID}/activate", "POST", {})
    time.sleep(1)
    verify = n8n(f"/api/v1/workflows/{LIVE_ID}")
    verify_by_name = {n["name"]: n for n in verify["nodes"]}
    ok = all(verify_by_name[name].get("parameters") == local_by_name[name].get("parameters") for name in node_diffs)
    conn_ok = all(verify["connections"].get(k) == local["connections"].get(k) for k in conn_diffs)
    print("post-patch active=%s params_applied=%s connections_applied=%s" % (verify.get("active"), ok, conn_ok))
    if not (ok and conn_ok):
        print("PATCH DID NOT VERIFY -- investigate before trusting this workflow.")
        sys.exit(1)


if __name__ == "__main__":
    main()
