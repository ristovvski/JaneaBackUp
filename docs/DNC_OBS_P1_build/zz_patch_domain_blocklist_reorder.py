#!/usr/bin/env python3
"""Surgical live patch: fix the Get Registry Match (Batch) item-count-amplification incident
(2026-09-14). Root cause: Get Domain Blocklist (1,373-row dataTable get) was chained directly into
Get Registry Match (Batch)'s input, and n8n dataTable "get" nodes execute once PER INPUT ITEM --
so Get Registry Match (Batch) ran 1,373x per gate call instead of once per submitted row (28-78s
observed, 459 consecutive 30s-timeout monitor failures over ~5 days). Fix: reorder so Get Domain
Blocklist fires exactly once (fed by a single-item node) and its bulk output is swallowed before
reaching any per-item-executing node. Full discipline: safe_patch_workflow diffs live vs local in
both directions and aborts on any unexpected node add/remove/change."""
import json
import os
import ssl
import sys
import urllib.request

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
    # NOTE (2026-09-14): the live drainer copy is archived (renamed ARCHIVE__dnc_gate_queue_drainer,
    # inactive) -- confirmed via a full paginated workflow search, no workflow named exactly
    # "dnc_gate_queue_drainer" is live. Per this project's own "never delete incident workflow"
    # convention, that archived copy is preserved audit state and is deliberately NOT touched here.
    # The local generator (build_dnc.py) and its regenerated JSON already carry the same fix, so if
    # this workflow is ever un-archived/redeployed from local files, the fix is already in place.
    GATE_ID = "9aP2dP0jgAPFGDvA"

    safe_patch_workflow(
        n8n, live_id=GATE_ID,
        local_path=os.path.join(HERE, "workflows", "dnc_pre_add_gate", "dnc_pre_add_gate.json"),
        label="dnc_pre_add_gate",
        expected_to_add=None, expected_to_remove=None, expected_param_diffs=[],
    )


if __name__ == "__main__":
    main()
