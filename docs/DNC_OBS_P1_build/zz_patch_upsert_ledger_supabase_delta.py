#!/usr/bin/env python3
"""Surgical live patch: add Supabase delta-push claim-enqueue to DNC__UpsertLedger__v1
(2026-09-14, Phase 2). Full safe_patch_workflow discipline -- diffs live vs local in both
directions, aborts on any unexpected node add/remove/change."""
import json
import os
import ssl
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
    UPSERT_LEDGER_ID = "RolYGL3J2CNg6Yp3"
    safe_patch_workflow(
        n8n, live_id=UPSERT_LEDGER_ID,
        local_path=os.path.join(HERE, "subworkflows", "DNC__UpsertLedger__v1.json"),
        label="DNC__UpsertLedger__v1",
        expected_to_add={"Enqueue Supabase Delta", "Enqueue Supabase Delta (Tombstone)"},
        expected_to_remove=None,
        expected_param_diffs=[],
    )


if __name__ == "__main__":
    main()
