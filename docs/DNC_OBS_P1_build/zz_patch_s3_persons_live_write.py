#!/usr/bin/env python3
"""S3 persons write path goes live (Nik's 2026-09-15 follow-up GO). Same discipline as the earlier
S3-persons-extension patch: preserves live CONFIG.FIRE_S3 (already permanently true for the leads
path) while merging in the local CONFIG's new FIRE_S3_PERSONS field (defaults false -- flipped
separately after one supervised verify window)."""
import json
import os
import ssl
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(HERE), ".env")
for line in open(ENV_PATH, encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v)
BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
ctx = ssl._create_unverified_context()


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


LIVE_ID = "QM21Vd7VId7PBdqh"
NEW_NODE_NAMES = {"FIRE_S3_PERSONS?", "S3 Persons Build Upsert Input", "S3 Persons Call UpsertLedger",
                  "S3 Persons Has Identity?", "S3 Persons Log No Identity", "S3 Persons Split Matches"}
EXPECTED_CHANGED = {"CONFIG", "S3 Classify Persons", "S3 Persons Report"}

if __name__ == "__main__":
    apply_it = "--apply" in sys.argv
    local = json.load(open("workflows/dnc_s3_creation_watcher/dnc_s3_creation_watcher.json", encoding="utf-8"))
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    local_by_name = {n["name"]: n for n in local["nodes"]}
    live_by_name = {n["name"]: n for n in live["nodes"]}

    to_add = set(local_by_name) - set(live_by_name)
    to_remove = set(live_by_name) - set(local_by_name)
    if to_add != NEW_NODE_NAMES:
        raise SystemExit(f"ABORT: to_add {sorted(to_add)} != expected {sorted(NEW_NODE_NAMES)}")
    if to_remove:
        raise SystemExit(f"ABORT: unexpected nodes to remove: {sorted(to_remove)}")

    def comparable(n):
        return {k: v for k, v in n.items() if k != "position"}
    changed = {n for n in local_by_name if n in live_by_name and comparable(local_by_name[n]) != comparable(live_by_name[n])}
    if changed != EXPECTED_CHANGED:
        raise SystemExit(f"ABORT: unexpected changed-node set {sorted(changed)}, expected {sorted(EXPECTED_CHANGED)}")

    if not apply_it:
        print("DRY RUN (pass --apply to actually patch).")
        print(f"to_add={sorted(to_add)} changed(will use LOCAL except CONFIG's FIRE_S3)={sorted(changed)}")
        sys.exit(0)

    # merge CONFIG: take LOCAL's field set (adds FIRE_S3_PERSONS) but preserve LIVE's current
    # FIRE_S3 value (permanently true) instead of the generator's safe-default false.
    local_cfg = local_by_name["CONFIG"]
    live_cfg = live_by_name["CONFIG"]
    live_fire_s3 = next(a["value"] for a in live_cfg["parameters"]["assignments"]["assignments"] if a["name"] == "FIRE_S3")
    for a in local_cfg["parameters"]["assignments"]["assignments"]:
        if a["name"] == "FIRE_S3":
            a["value"] = live_fire_s3

    new_nodes = list(live["nodes"]) + [local_by_name[name] for name in sorted(NEW_NODE_NAMES)]
    new_nodes = [local_by_name[n["name"]] if n["name"] in EXPECTED_CHANGED else n for n in new_nodes]

    new_connections = dict(live["connections"])
    new_connections["CONFIG"] = local["connections"]["CONFIG"]
    new_connections["S3 Persons Any New?"] = local["connections"]["S3 Persons Any New?"]
    for name in NEW_NODE_NAMES:
        if name in local["connections"]:
            new_connections[name] = local["connections"][name]

    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{LIVE_ID}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{LIVE_ID}", "PUT",
        {"name": live["name"], "nodes": new_nodes, "connections": new_connections, "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{LIVE_ID}/activate", "POST", {})

    verify = n8n(f"/api/v1/workflows/{LIVE_ID}")
    verify_names = sorted(n["name"] for n in verify["nodes"])
    expected_names = sorted(set(live_by_name) | NEW_NODE_NAMES)
    ok = verify_names == expected_names
    vcfg = next(n for n in verify["nodes"] if n["name"] == "CONFIG")
    vassigns = {a["name"]: a["value"] for a in vcfg["parameters"]["assignments"]["assignments"]}
    print(f"post-patch active={verify.get('active')} node_count={len(verify['nodes'])} names_match={ok} "
          f"FIRE_S3_preserved={vassigns.get('FIRE_S3') is True} FIRE_S3_PERSONS={vassigns.get('FIRE_S3_PERSONS')}")
    if not ok or vassigns.get("FIRE_S3") is not True or vassigns.get("FIRE_S3_PERSONS") is not False:
        raise SystemExit("POST-PATCH VERIFY FAILED")
