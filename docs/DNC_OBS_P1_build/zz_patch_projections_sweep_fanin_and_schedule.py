#!/usr/bin/env python3
"""Item 1 of Nik's 2026-09-15 GO: fix dnc_projections_sweep's PD Merge Write Paths fan-in bug and
add the hourly schedule, BEFORE going live. CONFIG's MODE/FIRE_PIPEDRIVE flip is a SEPARATE patch
(project convention: live-value flips are one-off patches to the deployed instance, never baked
into the generator -- see the comment above CONFIG in build_dnc.py)."""
import json
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patch_utils import safe_patch_workflow

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


LIVE_ID = "8qVXtI2ez5o6a9hc"

if __name__ == "__main__":
    apply_it = "--apply" in sys.argv
    if not apply_it:
        print("DRY RUN (pass --apply to actually patch). Diffing only.")
        local = json.load(open("workflows/dnc_projections_sweep/dnc_projections_sweep.json", encoding="utf-8"))
        live = n8n(f"/api/v1/workflows/{LIVE_ID}")
        local_names = {n["name"] for n in local["nodes"]}
        live_names = {n["name"] for n in live["nodes"]}
        print("to_add:", local_names - live_names)
        print("to_remove:", live_names - local_names)
        sys.exit(0)

    safe_patch_workflow(
        n8n, live_id=LIVE_ID, local_path="workflows/dnc_projections_sweep/dnc_projections_sweep.json",
        label="dnc_projections_sweep-faninfix-schedule",
        expected_to_add={"Sweep Timer"},
        expected_to_remove={"PD Merge Write Paths", "PD Write Barrier"},
        expected_param_diffs={"PD Filter Pending", "Send Guard"},
    )
