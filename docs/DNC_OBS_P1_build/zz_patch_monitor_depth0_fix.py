#!/usr/bin/env python3
"""Surgical live patch: gate-monitor depth-0/positive-shape-check fix. Same discipline as the
other zz_patch_*.py scripts this project -- diff every node, confirm only Track + Report differs,
deactivate -> PUT -> reactivate -> verify."""
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
    LIVE_ID = "g8MUOKFlUaeVrdBx"
    with open(os.path.join(HERE, "workflows", "dnc_pre_add_gate_monitor", "dnc_pre_add_gate_monitor.json"),
              encoding="utf-8") as f:
        local = json.load(f)
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    live_by_name = {n["name"]: n for n in live["nodes"]}
    local_by_name = {n["name"]: n for n in local["nodes"]}

    if set(live_by_name) != set(local_by_name):
        print("NODE SET MISMATCH:", sorted(live_by_name), sorted(local_by_name)); sys.exit(1)

    diffs = [name for name in live_by_name if live_by_name[name].get("parameters") != local_by_name[name].get("parameters")]
    expected = {"Track + Report"}
    unexpected = [d for d in diffs if d not in expected]
    if unexpected:
        print("UNEXPECTED diffs beyond", expected, ":", unexpected, "-- aborting."); sys.exit(1)
    print("confirmed diffs:", diffs, "(", len(live_by_name) - len(diffs), "of", len(live_by_name), "nodes untouched)")

    new_nodes = [local_by_name[n["name"]] if n["name"] in diffs else n for n in live["nodes"]]
    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{LIVE_ID}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{LIVE_ID}", "PUT",
        {"name": live["name"], "nodes": new_nodes, "connections": live["connections"], "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{LIVE_ID}/activate", "POST", {})
    time.sleep(1)
    verify = n8n(f"/api/v1/workflows/{LIVE_ID}")
    verify_by_name = {n["name"]: n for n in verify["nodes"]}
    ok = all(verify_by_name[name].get("parameters") == local_by_name[name].get("parameters") for name in diffs)
    print("post-patch active=%s applied=%s" % (verify.get("active"), ok))
    if not ok:
        print("PATCH DID NOT VERIFY"); sys.exit(1)


if __name__ == "__main__":
    main()
