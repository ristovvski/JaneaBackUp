#!/usr/bin/env python3
"""Surgical live patch: own-domain guard (OWN_TEAM gate_result for @janeasystems.com rows).
Same discipline as zz_patch_wf2r_watch_url_only.py -- fetch live, diff every node, patch ONLY
Classify Batch (both workflows) + Build Report (gate only), verify all other nodes byte-identical
before writing, deactivate -> PUT -> reactivate -> verify."""
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


def patch_one(live_id, local_json_path, patch_node_names, label):
    with open(local_json_path, encoding="utf-8") as f:
        local = json.load(f)
    live = n8n(f"/api/v1/workflows/{live_id}")
    live_by_name = {n["name"]: n for n in live["nodes"]}
    local_by_name = {n["name"]: n for n in local["nodes"]}

    if set(live_by_name.keys()) != set(local_by_name.keys()):
        print(f"[{label}] NODE SET MISMATCH -- live: {sorted(live_by_name)} local: {sorted(local_by_name)}")
        sys.exit(1)

    diffs = []
    for name in live_by_name:
        lv, lo = live_by_name[name], local_by_name[name]
        if lv.get("parameters") != lo.get("parameters"):
            diffs.append(name)

    unexpected = [d for d in diffs if d not in patch_node_names]
    if unexpected:
        print(f"[{label}] UNEXPECTED param diffs beyond {patch_node_names}: {unexpected} -- aborting, investigate.")
        sys.exit(1)
    missing = [n for n in patch_node_names if n not in diffs]
    if missing:
        print(f"[{label}] WARNING: expected diff not found for {missing} (already applied? or edit didn't take)")

    print(f"[{label}] confirmed: only {diffs} differ from live, all other {len(live_by_name)-len(diffs)} nodes byte-identical.")

    new_nodes = []
    for n in live["nodes"]:
        if n["name"] in patch_node_names:
            new_nodes.append(local_by_name[n["name"]])
        else:
            new_nodes.append(n)

    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{live_id}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{live_id}", "PUT",
        {"name": live["name"], "nodes": new_nodes, "connections": live["connections"], "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{live_id}/activate", "POST", {})
    time.sleep(1)
    verify = n8n(f"/api/v1/workflows/{live_id}")
    verify_by_name = {n["name"]: n for n in verify["nodes"]}
    ok = all(verify_by_name[n["name"]].get("parameters") == n.get("parameters") for n in local["nodes"] if n["name"] in patch_node_names)
    print(f"[{label}] post-patch active={verify.get('active')} patch_applied={ok}")
    if not ok:
        print(f"[{label}] PATCH DID NOT VERIFY -- investigate before trusting this workflow.")
        sys.exit(1)


def main():
    # ids per session memory: gate 9aP2dP0jgAPFGDvA. Drainer id must be looked up by name since it
    # wasn't recorded verbatim in the running summary -- resolve it live first.
    GATE_ID = "9aP2dP0jgAPFGDvA"
    all_wf = n8n("/api/v1/workflows?limit=250")
    drainer = next((w for w in all_wf.get("data", []) if w["name"] == "dnc_gate_queue_drainer"), None)
    if not drainer:
        print("dnc_gate_queue_drainer not found live -- listing workflow names containing 'gate' or 'drain':")
        for w in all_wf.get("data", []):
            if "gate" in w["name"].lower() or "drain" in w["name"].lower():
                print(" -", w["name"], w["id"], "active=", w.get("active"))
        sys.exit(1)
    DRAINER_ID = drainer["id"]
    print("resolved drainer id:", DRAINER_ID, "active=", drainer.get("active"))

    patch_one(GATE_ID, os.path.join(HERE, "workflows", "dnc_pre_add_gate", "dnc_pre_add_gate.json"),
               {"Classify Batch", "Build Report"}, "dnc_pre_add_gate")
    patch_one(DRAINER_ID, os.path.join(HERE, "workflows", "dnc_gate_queue_drainer", "dnc_gate_queue_drainer.json"),
               {"Classify Batch"}, "dnc_gate_queue_drainer")


if __name__ == "__main__":
    main()
