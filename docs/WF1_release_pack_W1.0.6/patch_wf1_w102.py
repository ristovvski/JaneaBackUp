#!/usr/bin/env python3
"""Apply W1.0.2 fix F13 to the W1.0.1 patched WF-1 export.

F13 — eliminate the inline-field JSON template pattern (root cause of incidents
E1 and E2): rebuild the `Create Lead` and `Create Activity` bodies with the
established Code-built idiom (like Person Create / M6 Build) — build a JS object
and JSON.stringify it, OMITTING organization_id when null. This guarantees valid
JSON for leads with no company (the common real-lead case).

Input: "WF-1 HeyReach Receiver - W1.0.1 patched.json". Deterministic, no network.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

# Create Lead — Code-built body; org_id omitted when null; cold label; channel 578 (number); channel_id from CONFIG.
CREATE_LEAD_BODY = (
    "={{ (() => {\n"
    "  const n = $('Normalize').item.json;\n"
    "  const pid = $('PID Resolved').item.json;\n"
    "  const cfg = $('CONFIG').item.json;\n"
    "  const company = (n.lead && n.lead.company_name) ? n.lead.company_name : '';\n"
    "  const title = company ? (n.lead.full_name + ' \\u2014 ' + company) : n.lead.full_name;\n"
    "  const body = {\n"
    "    title: title,\n"
    "    person_id: pid.person_id,\n"
    "    owner_id: cfg.melisa_user_id,\n"
    "    label_ids: [cfg.labels.cold],\n"
    "    channel: cfg.lead_channel,\n"
    "    channel_id: cfg.lead_channel_id_value\n"
    "  };\n"
    "  const org = pid.organization_id;\n"
    "  if (org !== null && org !== undefined && org !== '') body.organization_id = org;\n"
    "  return JSON.stringify(body);\n"
    "})() }}"
)

# Create Activity — same idiom; lead_id omitted if absent (always present on this path, kept for safety).
CREATE_ACTIVITY_BODY = (
    "={{ (() => {\n"
    "  const n = $('Normalize').item.json;\n"
    "  const cfg = $('CONFIG').item.json;\n"
    "  const pid = $('PID Resolved').item.json;\n"
    "  const lead_id = $json.lead_id;\n"
    "  const body = {\n"
    "    subject: 'LinkedIn invite sent \\u2014 ' + ((n.campaign && n.campaign.name) || ''),\n"
    "    type: cfg.activity_type_msg,\n"
    "    done: true,\n"
    "    participants: [{ person_id: pid.person_id, primary: true }],\n"
    "    owner_id: cfg.melisa_user_id,\n"
    "    note: n.invite || ''\n"
    "  };\n"
    "  if (lead_id !== null && lead_id !== undefined && lead_id !== '') body.lead_id = lead_id;\n"
    "  return JSON.stringify(body);\n"
    "})() }}"
)


def by_name(w: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["name"]: n for n in w["nodes"]}


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = by_name(w)
    cl = bn["Create Lead"]["parameters"]
    ca = bn["Create Activity"]["parameters"]
    if '"organization_id": {{' not in cl["jsonBody"]:
        raise ValueError("Create Lead does not have the expected inline org template; already patched or drifted?")
    cl["jsonBody"] = CREATE_LEAD_BODY
    ca["jsonBody"] = CREATE_ACTIVITY_BODY
    return w


def _inline_field_template_nodes(w: dict[str, Any]) -> list[str]:
    """Return httpRequest nodes whose jsonBody still uses bare inline {{ }} fields
    (i.e., not a whole-object JSON.stringify / IIFE)."""
    bad = []
    for n in w["nodes"]:
        if n.get("type") != "n8n-nodes-base.httpRequest":
            continue
        jb = (n.get("parameters") or {}).get("jsonBody")
        if not isinstance(jb, str):
            continue
        body = jb.strip()
        if body.startswith("={{ (() =>") or body.startswith("={{ JSON.stringify("):
            continue  # whole-object idiom
        fields = re.findall(r"\{\{\s*(.*?)\s*\}\}", body, re.S)
        bare = [f for f in fields if not f.startswith("JSON.stringify") and not f.startswith("(")]
        if bare:
            bad.append(n["name"])
    return bad


def validate(w: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    bn = by_name(w)
    for nm in ("Create Lead", "Create Activity"):
        jb = bn[nm]["parameters"]["jsonBody"]
        if not jb.strip().startswith("={{ (() =>"):
            errors.append(f"F13: {nm} is not a Code-built IIFE body")
        if "JSON.stringify(body)" not in jb:
            errors.append(f"F13: {nm} does not JSON.stringify a built object")
    cl = bn["Create Lead"]["parameters"]["jsonBody"]
    if '"organization_id": {{' in cl:
        errors.append("F13: Create Lead still has the inline organization_id template")
    if "if (org !== null" not in cl:
        errors.append("F13: Create Lead does not conditionally omit organization_id")
    if "label_ids: [cfg.labels.cold]" not in cl or "channel: cfg.lead_channel" not in cl:
        errors.append("F13: Create Lead missing cold label / channel")
    remaining = _inline_field_template_nodes(w)
    if remaining:
        errors.append(f"F13: inline-field-template jsonBody still present in: {remaining}")
    # unchanged elsewhere: still 89 nodes, inactive, no pinData
    if len(w["nodes"]) != 89:
        errors.append(f"node count changed: {len(w['nodes'])}")
    if w.get("active") is not False:
        errors.append("workflow not inactive")
    if "pinData" in w:
        errors.append("pinData present")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--api-payload", type=Path, default=None)
    args = ap.parse_args()
    wf = json.loads(args.input.read_text(encoding="utf-8"))
    patched = apply_patch(wf)
    errs = validate(patched)
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    args.output.write_bytes((json.dumps(patched, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if args.api_payload:
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        args.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"F13 patched -> {args.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
