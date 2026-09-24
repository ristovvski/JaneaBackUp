#!/usr/bin/env python3
"""S2 rebuild, Nik's 2026-09-15 GO: full replacement of dnc_s2_meeting_to_dnc's frozen-snapshot
design with a live daily poll. See ARTIFACT_prefire_s2_rebuild.md for the reasoning."""
import json
import os
import ssl
import sys

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

import urllib.request


def n8n(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, method=method, data=data,
                                headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json",
                                         "accept": "application/json"})
    with urllib.request.urlopen(r, timeout=180, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


LIVE_ID = "E0oTTvHHQ0hVTNDD"

if __name__ == "__main__":
    apply_it = "--apply" in sys.argv
    if not apply_it:
        local = json.load(open("workflows/dnc_s2_meeting_to_dnc/dnc_s2_meeting_to_dnc.json", encoding="utf-8"))
        live = n8n(f"/api/v1/workflows/{LIVE_ID}")
        local_names = {n["name"] for n in local["nodes"]}
        live_names = {n["name"] for n in live["nodes"]}
        print("DRY RUN (pass --apply to actually patch).")
        print("to_add:", sorted(local_names - live_names))
        print("to_remove:", sorted(live_names - local_names))
        sys.exit(0)

    safe_patch_workflow(
        n8n, live_id=LIVE_ID, local_path="workflows/dnc_s2_meeting_to_dnc/dnc_s2_meeting_to_dnc.json",
        label="dnc_s2_meeting_to_dnc-rebuild",
        expected_to_add={"Daily Timer", "S2 Get Recent Label Leads", "S2 Classify Label Signals",
                          "S2 Get Recent Stage Deals", "S2 Classify Stage Signals",
                          "S2 Aggregate Candidates", "S2 Split Candidates"},
        expected_to_remove={"S2 Classify", "S2 Limit Chunk", "S2 Merge Identity Paths", "S2 Write Barrier"},
        expected_param_diffs={"CONFIG", "S2 Build Upsert Input", "S2 Combine", "S2 Send Guard"},
    )
