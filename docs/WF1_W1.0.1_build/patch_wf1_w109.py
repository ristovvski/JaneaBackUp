#!/usr/bin/env python3
"""W1.0.9 micro-patch: event-truth labels.

Nik's decision: `connected` must mean an ACTUAL accepted connection — never implied by a reply.
Change: M7 Labels Compute targetSet drops the rank>=2 connected push -> reply contributes only
[cold, responded]. M5 Labels Compute UNCHANGED (accepted still yields [cold, connected]).
Union semantics (never remove, preserve foreign, changed/skip-empty-PATCH) untouched. Create Lead
[cold] untouched. Existing leads keep their sets (union never removes; no backfill retro-removal).

Input: W1.0.8 patched JSON. Deterministic, no network. Node count unchanged (93).
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

M7_CONNECTED_LINE = "if (effectiveRank >= 2) targetSet.push(cfg.labels.connected);\n"


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}
    m7 = bn["M7 Labels Compute"]["parameters"]
    code = m7["jsCode"]
    if M7_CONNECTED_LINE not in code:
        raise ValueError("M7 Labels Compute: expected rank>=2 connected push not found (drifted or already W1.0.9)")
    if code.count(M7_CONNECTED_LINE) != 1:
        raise ValueError(f"M7 Labels Compute: expected exactly 1 connected push, found {code.count(M7_CONNECTED_LINE)}")
    m7["jsCode"] = code.replace(M7_CONNECTED_LINE, "")
    w.pop("pinData", None)
    w["active"] = False
    return w


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    m7 = bn["M7 Labels Compute"]["parameters"]["jsCode"]
    m5 = bn["M5 Labels Compute"]["parameters"]["jsCode"]
    # M7: cold + responded, NO connected push
    if "if (effectiveRank >= 2) targetSet.push(cfg.labels.connected);" in m7:
        e.append("M7 still pushes connected (rank>=2)")
    if "targetSet.push(cfg.labels.cold)" not in m7 or "targetSet.push(cfg.labels.responded)" not in m7:
        e.append("M7 must still push cold + responded")
    # M5 unchanged: still pushes connected
    if "if (effectiveRank >= 2) targetSet.push(cfg.labels.connected);" not in m5:
        e.append("M5 connected push must remain (unchanged)")
    for nm, code in (("M7", m7), ("M5", m5)):
        if "[...existing, ...targetSet]" not in code or "const changed =" not in code:
            e.append(f"{nm} union/changed semantics disturbed")
    # Create Lead [cold] untouched
    if "[cfg.labels.cold]" not in bn["Create Lead"]["parameters"]["jsonBody"]:
        e.append("Create Lead [cold] changed/absent")
    if w.get("active") is not False:
        e.append("not inactive")
    if "pinData" in w:
        e.append("pinData present")
    if len(w["nodes"]) != 93:
        e.append(f"expected 93 nodes, got {len(w['nodes'])}")
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path); ap.add_argument("output", type=Path)
    ap.add_argument("--api-payload", type=Path, default=None)
    a = ap.parse_args()
    wf = json.loads(a.input.read_text(encoding="utf-8"))
    patched = apply_patch(wf)
    errs = validate(patched)
    if errs:
        for x in errs: print(f"ERROR: {x}", file=sys.stderr)
        return 1
    a.output.write_bytes((json.dumps(patched, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if a.api_payload:
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        a.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"W1.0.9 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
