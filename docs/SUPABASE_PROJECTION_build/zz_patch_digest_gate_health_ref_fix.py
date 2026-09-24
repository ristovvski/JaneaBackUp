#!/usr/bin/env python3
"""Item 2 of Nik's 2026-09-15 GO: fix dnc_morning_digest's stale named-reference.

Root cause (traced live via execution 55858's actual runData, 2026-09-15T04:00Z, the first real
post-Supabase-mirror-patch run): "Gate Health" -- the node immediately after "Gate Monitor Last" in
the digest's long linear accumulator chain -- reads `$('DNC Removed Agg').first().json` as its
`prev` object (the standard pattern in this workflow: every code node spreads its predecessor's
accumulated object forward, because an HTTP node sits between them and destroys $json). That
reference predates 2026-09-14's Supabase-mirror patch, which spliced three new nodes (Supabase
Mirror Check / Supabase Meta Check / Supabase Mirror Agg) BETWEEN "DNC Removed Agg" and "Gate
Monitor Last" -- so "Gate Health" now silently drops supabase_reachable/supabase_rows/
supabase_age_min the moment it reads the now-stale "DNC Removed Agg" instead of the new true
predecessor, "Supabase Mirror Agg". Every downstream node in the chain (WF Errors Agg -> ... ->
Changelog Count -> No Match Count -> Compose) correctly references ITS OWN immediate predecessor --
Gate Health is the only break, confirmed by walking the full chain's named references.

This is NOT the same bug pattern this session's memory already documents (multi-input node fires
per branch) -- it's a plain stale pointer, but the general lesson is the same one Nik is flagging
project-wide: "prev-read must reference the direct upstream node" (see the new WF_LINTER rule)."""
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
    with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
        return json.load(x) if x.length != 0 else {}


LIVE_ID = "qJKfR602wV9yfFrj"
OLD_REF = "$('DNC Removed Agg')"
NEW_REF = "$('Supabase Mirror Agg')"

if __name__ == "__main__":
    apply_it = "--apply" in sys.argv
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    nodes = live["nodes"]
    gh = next(n for n in nodes if n["name"] == "Gate Health")
    code = gh["parameters"]["jsCode"]
    occurrences = code.count(OLD_REF)
    assert occurrences == 1, f"expected exactly 1 occurrence of {OLD_REF!r}, found {occurrences} -- aborting"
    new_code = code.replace(OLD_REF, NEW_REF)

    if not apply_it:
        print("DRY RUN (pass --apply to actually patch).")
        print(f"Gate Health: {OLD_REF} -> {NEW_REF} (1 occurrence, verified unique)")
        sys.exit(0)

    gh["parameters"]["jsCode"] = new_code
    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{LIVE_ID}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{LIVE_ID}", "PUT",
        {"name": live["name"], "nodes": nodes, "connections": live["connections"], "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{LIVE_ID}/activate", "POST", {})

    verify = n8n(f"/api/v1/workflows/{LIVE_ID}")
    vgh = next(n for n in verify["nodes"] if n["name"] == "Gate Health")
    ok = NEW_REF in vgh["parameters"]["jsCode"] and OLD_REF not in vgh["parameters"]["jsCode"]
    print(f"post-patch active={verify.get('active')} node_count={len(verify['nodes'])} fix_verified={ok}")
    if not ok:
        raise SystemExit("POST-PATCH VERIFY FAILED")
