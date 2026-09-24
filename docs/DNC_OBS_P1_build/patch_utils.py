#!/usr/bin/env python3
"""Shared, MANDATORY safety helper for every live workflow patch in this project from now on.
Direct consequence of the 2026-09-09 incident: a one-off patch script diffed live vs local, saw 12
"new" nodes instead of the expected 1, and applied the patch anyway -- silently resurrecting a
whole removed subsystem (see task-logs/2026-09-09_gate-domain-block-and-incident.md). Every future
patcher (gate, drainer, or anything else) must use this instead of hand-rolling its own diff.

Usage:
    from zz_patch_utils import safe_patch_workflow
    safe_patch_workflow(n8n, live_id="9aP2dP0jgAPFGDvA", local_path="workflows/.../foo.json",
                         label="gate")

Aborts (raises SystemExit) if the live/local node-name diff, in EITHER direction, doesn't exactly
equal what the caller explicitly expects -- there is no "proceed anyway" path. If a script needs to
add nodes AND you expect that, pass expected_to_add; same for expected_to_remove. Passing nothing
for either means "I expect zero of that kind of diff" -- the strict, safe default.
"""
import json
import time


def safe_patch_workflow(n8n, live_id, local_path, label,
                          expected_to_add=None, expected_to_remove=None,
                          expected_param_diffs=None):
    expected_to_add = set(expected_to_add or [])
    expected_to_remove = set(expected_to_remove or [])

    with open(local_path, encoding="utf-8") as f:
        local = json.load(f)
    live = n8n(f"/api/v1/workflows/{live_id}")
    live_by_name = {n["name"]: n for n in live["nodes"]}
    local_by_name = {n["name"]: n for n in local["nodes"]}

    to_add = set(local_by_name) - set(live_by_name)
    to_remove = set(live_by_name) - set(local_by_name)

    if to_add != expected_to_add:
        raise SystemExit(
            f"[{label}] ABORT: nodes-to-ADD doesn't match expected.\n"
            f"  expected: {sorted(expected_to_add)}\n  actual:   {sorted(to_add)}\n"
            f"  This usually means the live workflow drifted since local was last generated -- "
            f"investigate what the unexpected node(s) do (read their own code/comments) before "
            f"touching anything live.")
    if to_remove != expected_to_remove:
        raise SystemExit(
            f"[{label}] ABORT: nodes-to-REMOVE doesn't match expected.\n"
            f"  expected: {sorted(expected_to_remove)}\n  actual:   {sorted(to_remove)}\n"
            f"  Same warning as above -- do not proceed on a guess.")

    # compare the FULL node (minus "position", which is cosmetic), not just "parameters" -- found
    # live 2026-09-09: onError/alwaysOutputData/retryOnFail/etc. are TOP-LEVEL node fields, not
    # nested inside "parameters", so a parameters-only diff silently misses changes to them. This
    # is exactly the kind of gap this tool exists to prevent -- caught here, before it caused a
    # second incident, because the (correct) alwaysOutputData fix showed as "no diff" and aborted
    # instead of silently deploying nothing.
    def _comparable(n):
        return {k: v for k, v in n.items() if k != "position"}
    param_diffs = [name for name in local_by_name
                   if name in live_by_name
                   and _comparable(live_by_name[name]) != _comparable(local_by_name[name])]
    if expected_param_diffs is not None and set(param_diffs) != set(expected_param_diffs):
        raise SystemExit(
            f"[{label}] ABORT: changed-node set doesn't match expected.\n"
            f"  expected: {sorted(expected_param_diffs)}\n  actual:   {sorted(param_diffs)}")

    print(f"[{label}] diff verified exactly as expected -- add={sorted(to_add)} "
          f"remove={sorted(to_remove)} changed={sorted(param_diffs)}")

    new_nodes = [n for n in live["nodes"] if n["name"] not in to_remove]
    new_nodes = [local_by_name[n["name"]] if n["name"] in param_diffs else n for n in new_nodes]
    new_nodes += [local_by_name[name] for name in to_add]

    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{live_id}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{live_id}", "PUT",
        {"name": live["name"], "nodes": new_nodes, "connections": local["connections"],
         "settings": live["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{live_id}/activate", "POST", {})
    time.sleep(1)

    verify = n8n(f"/api/v1/workflows/{live_id}")
    verify_names = sorted(n["name"] for n in verify["nodes"])
    expected_names = sorted(local_by_name.keys())
    ok = verify_names == expected_names
    print(f"[{label}] post-patch active={verify.get('active')} node_count={len(verify['nodes'])} "
          f"names_match={ok}")
    if not ok:
        raise SystemExit(f"[{label}] POST-PATCH VERIFY FAILED -- live names don't match local exactly.\n"
                          f"  live:   {verify_names}\n  expect: {expected_names}")
    return verify
