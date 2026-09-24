#!/usr/bin/env python3
"""Item 5 of Nik's 2026-09-15 GO: add the report-only Persons-polling extension to
dnc_s3_creation_watcher, without touching the existing (tested, running) leads path or reverting
the live CONFIG.FIRE_S3 value someone already flipped True in an earlier session -- the generator's
own CONFIG default stays False (safe-by-construction philosophy, unchanged), so a plain
safe_patch_workflow would try to revert live's FIRE_S3 back to False as a side effect of adding the
new nodes. This script explicitly keeps live's CONFIG untouched and adds ONLY the 8 new nodes plus
CONFIG's new outgoing wire to "S3 Get Recent Persons"."""
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
NEW_NODE_NAMES = {"S3 Get Recent Persons", "S3 Classify Persons", "S3 Filter New Persons",
                  "S3 Persons Any New?", "S3 Persons Report", "S3 Persons MODE == dev?",
                  "S3 Persons Send Guard", "S3 Persons Dev Summary"}

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
    changed = [n for n in local_by_name if n in live_by_name and comparable(local_by_name[n]) != comparable(live_by_name[n])]
    if changed != ["CONFIG"]:
        raise SystemExit(f"ABORT: unexpected changed-node set {changed}, expected only ['CONFIG']")

    if not apply_it:
        print("DRY RUN (pass --apply to actually patch).")
        print(f"to_add={sorted(to_add)} to_remove={sorted(to_remove)} changed(kept as LIVE)={changed}")
        sys.exit(0)

    # new node list: every live node UNCHANGED (including CONFIG's live values, e.g. FIRE_S3=True)
    # + the 8 new nodes from local.
    new_nodes = list(live["nodes"]) + [local_by_name[name] for name in sorted(NEW_NODE_NAMES)]

    # new connections: live's own connections, PLUS the new persons-path wiring from local, PLUS
    # CONFIG's connection entry replaced with local's (adds the new fan-out target while keeping
    # the existing "S3 Get Recent Leads" target exactly as it already is).
    new_connections = dict(live["connections"])
    new_connections["CONFIG"] = local["connections"]["CONFIG"]
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
    vfire = next(a["value"] for a in vcfg["parameters"]["assignments"]["assignments"] if a["name"] == "FIRE_S3")
    print(f"post-patch active={verify.get('active')} node_count={len(verify['nodes'])} names_match={ok} "
          f"FIRE_S3_preserved={vfire is True}")
    if not ok or vfire is not True:
        raise SystemExit("POST-PATCH VERIFY FAILED")
