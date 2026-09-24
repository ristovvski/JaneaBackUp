#!/usr/bin/env python3
"""W1.0.6 micro-patch: omit empty `note` from activity bodies (F13/R4 idiom).

Root cause (surfaced 2026-07-15, double execs 9992/9995): Pipedrive v2 POST /activities
rejects note:"" with 400 "note: This value is too short." The sent-path Create Activity
built `note: n.invite || ''`, so a connection_request_sent with no connection_message 400s.

- Create Activity (sent path): drop `note` from the object literal; add it back only when
  non-empty (same idiom as the existing lead_id / F13 organization_id guards).
- M7 Reply Activity (reply path): convert the inline `={{ JSON.stringify({...}) }}` to the
  Code-built IIFE idiom and guard `note` (note = reply_text) the same way.

No other field, link, stage-machine or lead-selection behavior changes. Input: W1.0.5 patched JSON.
Deterministic, no network.
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

# --- Create Activity: targeted replace inside the existing IIFE ---
CA_OLD = (
    "    owner_id: cfg.melisa_user_id,\n"
    "    note: n.invite || ''\n"
    "  };\n"
    "  if (lead_id !== null && lead_id !== undefined && lead_id !== '') body.lead_id = lead_id;"
)
CA_NEW = (
    "    owner_id: cfg.melisa_user_id\n"
    "  };\n"
    "  const note = n.invite || '';\n"
    "  if (note !== '') body.note = note;\n"
    "  if (lead_id !== null && lead_id !== undefined && lead_id !== '') body.lead_id = lead_id;"
)

# --- M7 Reply Activity: inline -> Code-built IIFE, note guarded ---
RA_OLD_MARK = "note: $('M7 Build').item.json.reply_text"
RA_NEW = (
    "={{ (() => {\n"
    "  const b = $('M7 Build').item.json;\n"
    "  const cfg = $('CONFIG').item.json;\n"
    "  const body = {\n"
    "    subject: 'LinkedIn reply \\u2014 ' + (($('Normalize').item.json.campaign || {}).name || ''),\n"
    "    type: cfg.activity_type_msg,\n"
    "    done: true,\n"
    "    participants: [{ person_id: b.person_id, primary: true }],\n"
    "    lead_id: b.lead_id,\n"
    "    owner_id: cfg.melisa_user_id\n"
    "  };\n"
    "  const note = b.reply_text || '';\n"
    "  if (note !== '') body.note = note;\n"
    "  return JSON.stringify(body);\n"
    "})() }}"
)


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}

    ca = bn["Create Activity"]["parameters"]
    if CA_OLD not in ca["jsonBody"]:
        raise ValueError("Create Activity: expected W1.0.5 `note: n.invite || ''` block not found (drifted or already patched)")
    ca["jsonBody"] = ca["jsonBody"].replace(CA_OLD, CA_NEW)

    ra = bn["M7 Reply Activity"]["parameters"]
    if RA_OLD_MARK not in ra["jsonBody"]:
        raise ValueError("M7 Reply Activity: expected inline reply_text note not found (drifted or already patched)")
    if not ra["jsonBody"].strip().startswith("={{ JSON.stringify("):
        raise ValueError("M7 Reply Activity: expected inline JSON.stringify body")
    ra["jsonBody"] = RA_NEW

    w.pop("pinData", None)
    w["active"] = False
    return w


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}

    ca = bn["Create Activity"]["parameters"]["jsonBody"]
    if "note: n.invite || ''" in ca:
        e.append("Create Activity still has unconditional note in the literal")
    if "if (note !== '') body.note = note;" not in ca:
        e.append("Create Activity missing guarded note assignment")
    if not ca.strip().startswith("={{ (() =>"):
        e.append("Create Activity must remain a Code-built IIFE")

    ra = bn["M7 Reply Activity"]["parameters"]["jsonBody"]
    if not ra.strip().startswith("={{ (() =>"):
        e.append("M7 Reply Activity must become a Code-built IIFE")
    if "if (note !== '') body.note = note;" not in ra:
        e.append("M7 Reply Activity missing guarded note assignment")
    if RA_OLD_MARK in ra:
        e.append("M7 Reply Activity still has the old inline reply_text note")

    # No activity/task builder may carry an unconditional empty-able note in its object literal.
    for nm in ("Create Activity", "M7 Reply Activity", "M8 Task", "M6 Activity"):
        node = bn.get(nm)
        if not node:
            continue
        jb = node["parameters"].get("jsonBody", "")
        for frag in ("note: n.invite || ''", "note: $('M7 Build').item.json.reply_text"):
            if frag in jb:
                e.append(f"{nm}: residual unconditional empty-able note ({frag})")

    if w.get("active") is not False:
        e.append("not inactive")
    if "pinData" in w:
        e.append("pinData present")
    if len(w["nodes"]) != 90:
        e.append(f"expected 90 nodes, got {len(w['nodes'])}")
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--api-payload", type=Path, default=None)
    a = ap.parse_args()
    wf = json.loads(a.input.read_text(encoding="utf-8"))
    patched = apply_patch(wf)
    errs = validate(patched)
    if errs:
        for x in errs:
            print(f"ERROR: {x}", file=sys.stderr)
        return 1
    a.output.write_bytes((json.dumps(patched, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if a.api_payload:
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        a.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"W1.0.6 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
