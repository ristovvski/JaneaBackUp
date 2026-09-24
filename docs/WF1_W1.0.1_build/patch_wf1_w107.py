#!/usr/bin/env python3
"""W1.0.7: cumulative (union) label model + assignment-task kill-switch.

Change 1 — union label semantics in M5/M7 Labels Compute:
  replace `existing MINUS ourLabels PLUS [targetLabel]` (replace-semantics) with
  `union(existing, milestoneSet-up-to-effectiveRank)` — never removes anything (foreign
  labels preserved; union-compatible with parallel automation user 25112064). Emits a
  `changed` flag; a new `M{5,7} IF Labels Changed` gate skips the PATCH when the set is
  unchanged (avoids empty PATCHes on replays). The existing `IF Lead ID` gate can't double
  as this skip: its false branch posts a "no lead" warn, and M7's reads $('M7 Build'), not
  the compute output.

Change 2 — task kill-switch:
  CONFIG.create_assignment_task=false; new `M8 IF Task Enabled` gate between
  `M8 IF Lead ID(true)` and `M8 Task`. Flag false => no task (Melisa's automation owns it);
  M8 Task node retained for W1.1 auto-assign. Sent-path Create Lead [cold] verified unchanged.

Input: W1.0.6 patched JSON. Deterministic, no network. 90 -> 93 nodes.
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

TARGETLABEL_OLD = (
    "const targetLabel = effectiveRank >= 4 ? cfg.labels.responded\n"
    "                  : effectiveRank >= 2 ? cfg.labels.connected\n"
    "                  : cfg.labels.cold;"
)
TARGETLABEL_NEW = TARGETLABEL_OLD + (
    "\nconst targetSet = [];\n"
    "if (effectiveRank >= 1) targetSet.push(cfg.labels.cold);\n"
    "if (effectiveRank >= 2) targetSet.push(cfg.labels.connected);\n"
    "if (effectiveRank >= 4) targetSet.push(cfg.labels.responded);"
)
LABELIDS_OLD = "const label_ids = Array.from(new Set(existing.filter(id => !cfg.ourLabels.includes(id)).concat([targetLabel])));"
LABELIDS_NEW = (
    "const label_ids = Array.from(new Set([...existing, ...targetSet]));\n"
    "const changed = !(existing.length === label_ids.length && existing.every(id => label_ids.includes(id)));"
)


def if_node(name: str, node_id: str, left_expr: str, pos: list[int]) -> dict[str, Any]:
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 1},
                "conditions": [{
                    "id": node_id + "-c",
                    "leftValue": left_expr,
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "id": node_id, "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2, "position": pos,
    }


def conn(node): return {"node": node, "type": "main", "index": 0}


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}
    conns = w["connections"]

    # --- Change 2a: CONFIG flag ---
    cfg_raw = bn["CONFIG"]["parameters"]["jsonOutput"]
    cfg_obj = json.loads(cfg_raw)
    if "create_assignment_task" in cfg_obj:
        raise ValueError("CONFIG already has create_assignment_task")
    cfg_obj["create_assignment_task"] = False
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg_obj, indent=2)

    # --- Change 1: union semantics + changed flag in both compute nodes ---
    for nm, out_anchor in (("M5 Labels Compute", "    label_ids,\n    currentStage,"),
                           ("M7 Labels Compute", "    label_ids,\n    label_ids_before: existing,")):
        code = bn[nm]["parameters"]["jsCode"]
        if TARGETLABEL_OLD not in code or LABELIDS_OLD not in code:
            raise ValueError(f"{nm}: expected W1.0.6 replace-semantics not found")
        code = code.replace(TARGETLABEL_OLD, TARGETLABEL_NEW).replace(LABELIDS_OLD, LABELIDS_NEW)
        add = "    label_ids,\n    changed,\n" + out_anchor.split("\n", 1)[1]
        code = code.replace(out_anchor, add)
        if "changed," not in code:
            raise ValueError(f"{nm}: failed to add changed to output")
        bn[nm]["parameters"]["jsCode"] = code

    # --- new gate nodes ---
    n_m5 = if_node("M5 IF Labels Changed", "w107a-m5-labels-changed", "={{ $json.changed === true }}", [3872, 864])
    n_m7 = if_node("M7 IF Labels Changed", "w107b-m7-labels-changed", "={{ $json.changed === true }}", [3616, 1936])
    n_m8 = if_node("M8 IF Task Enabled", "w107c-m8-task-enabled",
                   "={{ $('CONFIG').item.json.create_assignment_task === true }}", [4448, 1840])
    w["nodes"].extend([n_m5, n_m7, n_m8])

    # --- rewire ---
    # M5: IF Lead ID(true) -> IF Labels Changed -> [Lead Patch(leaf), (skip=leaf)]
    conns["M5 IF Lead ID"]["main"][0] = [conn("M5 IF Labels Changed")]
    conns["M5 IF Labels Changed"] = {"main": [[conn("M5 Lead Patch")], []]}
    # M7: IF Lead ID(true) -> IF Labels Changed -> [Lead Patch, (skip)->IF Reply Activity Lead]; both converge
    conns["M7 IF Lead ID"]["main"][0] = [conn("M7 IF Labels Changed")]
    conns["M7 IF Labels Changed"] = {"main": [[conn("M7 Lead Patch")], [conn("M7 IF Reply Activity Lead")]]}
    # M8: IF Lead ID(true) -> IF Task Enabled -> [Task, (disabled=leaf)]
    conns["M8 IF Lead ID"]["main"][0] = [conn("M8 IF Task Enabled")]
    conns["M8 IF Task Enabled"] = {"main": [[conn("M8 Task")], []]}

    w.pop("pinData", None)
    w["active"] = False
    return w


def _cycle(w) -> list[str]:
    conns = w["connections"]; names = [n["name"] for n in w["nodes"]]
    color = {n: 0 for n in names}; bad = []
    def dfs(u):
        color[u] = 1
        for br in (conns.get(u, {}).get("main") or []):
            for e in br or []:
                v = e["node"]
                if color.get(v, 2) == 1: bad.append(f"{u}->{v}")
                elif color.get(v, 2) == 0: dfs(v)
        color[u] = 2
    for n in names:
        if color[n] == 0: dfs(n)
    return bad


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    conns = w["connections"]
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("create_assignment_task") is not False:
        e.append("CONFIG.create_assignment_task must be False")
    for nm in ("M5 Labels Compute", "M7 Labels Compute"):
        c = bn[nm]["parameters"]["jsCode"]
        if "[...existing, ...targetSet]" not in c: e.append(f"{nm}: union not applied")
        if "ourLabels.includes(id)).concat" in c: e.append(f"{nm}: old replace-semantics still present")
        if "const changed =" not in c or "changed," not in c: e.append(f"{nm}: changed flag missing")
    for nm in ("M5 IF Labels Changed", "M7 IF Labels Changed", "M8 IF Task Enabled", "M8 Task"):
        if nm not in bn: e.append(f"missing node {nm}")
    # wiring
    def tgt(nm, br): return [x["node"] for x in (conns.get(nm, {}).get("main") or [[], []])[br]]
    if tgt("M5 IF Lead ID", 0) != ["M5 IF Labels Changed"]: e.append("M5 IF Lead ID(true) not rewired")
    if tgt("M5 IF Labels Changed", 0) != ["M5 Lead Patch"] or tgt("M5 IF Labels Changed", 1) != []: e.append("M5 IF Labels Changed wiring")
    if tgt("M7 IF Lead ID", 0) != ["M7 IF Labels Changed"]: e.append("M7 IF Lead ID(true) not rewired")
    if tgt("M7 IF Labels Changed", 0) != ["M7 Lead Patch"] or tgt("M7 IF Labels Changed", 1) != ["M7 IF Reply Activity Lead"]: e.append("M7 IF Labels Changed wiring")
    if tgt("M8 IF Lead ID", 0) != ["M8 IF Task Enabled"]: e.append("M8 IF Lead ID(true) not rewired")
    if tgt("M8 IF Task Enabled", 0) != ["M8 Task"] or tgt("M8 IF Task Enabled", 1) != []: e.append("M8 IF Task Enabled wiring")
    # sent-path Create Lead cold unchanged
    cl = bn["Create Lead"]["parameters"]["jsonBody"]
    if "[cfg.labels.cold]" not in cl: e.append("Create Lead [cold] changed/absent")
    # no cycle
    cyc = _cycle(w)
    if cyc: e.append(f"cycle(s): {cyc}")
    if w.get("active") is not False: e.append("not inactive")
    if "pinData" in w: e.append("pinData present")
    if len(w["nodes"]) != 93: e.append(f"expected 93 nodes, got {len(w['nodes'])}")
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
    print(f"W1.0.7 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
