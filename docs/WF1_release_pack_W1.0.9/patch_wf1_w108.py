#!/usr/bin/env python3
"""W1.0.8: org website (create-only), person location (create + fill-if-empty), multi-reply note.

B1  Org Create: company_url -> standard `website` field (CONFIG.org_website_field), R4-omit when empty.
B2  Person location -> custom LinkedIn Location (CONFIG.fields.person_location): Person Create +
    fill-if-empty in Person Patch Invited (+ its IF Rank Allows Invited composite gate) + M5 patch.
B3  M7 Build: reply_note = ALL trailing consecutive is_reply messages joined oldest->newest with \\n
    (placeholders applied); M7 Reply Activity note uses reply_note. Alert unchanged (last reply only).

Input: W1.0.7 patched JSON. Deterministic, no network. Node count unchanged (93).
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

PERSON_LOCATION = "db219a0b68aa164d0aed1f7791687c5ae788b7ae"
ORG_WEBSITE = "website"

ORG_CREATE_OLD = "={{ JSON.stringify({ name: $('Normalize').item.json.lead.company_name }) }}"
ORG_CREATE_NEW = (
    "={{ (() => {\n"
    "  const n = $('Normalize').item.json;\n"
    "  const cfg = $('CONFIG').item.json;\n"
    "  const body = { name: n.lead.company_name };\n"
    "  const site = (n.lead && n.lead.company_url) ? String(n.lead.company_url) : '';\n"
    "  if (site !== '') body[cfg.org_website_field] = site;  // B1 create-only, R4-omit\n"
    "  return JSON.stringify(body);\n"
    "})() }}"
)

PC_OLD = "  cf[f.summary] = n.lead.summary;\n  cf[f.source] = $('CONFIG').item.json.source_value;  // R1 create-only"
PC_NEW = "  cf[f.summary] = n.lead.summary;\n  cf[f.person_location] = n.lead.location;  // B2\n  cf[f.source] = $('CONFIG').item.json.source_value;  // R1 create-only"

PPI_OLD = "  if (!current[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid)) cf[f.member_id] = mid;\n  for (const k of Object.keys(cf))"
PPI_NEW = "  if (!current[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid)) cf[f.member_id] = mid;\n  if (!current[f.person_location] && n.lead.location) cf[f.person_location] = n.lead.location;  // B2 fill-if-empty\n  for (const k of Object.keys(cf))"

M5_OLD = "  if (!current[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid2)) custom_fields[f.member_id] = mid2;\n  for (const k of Object.keys(custom_fields))"
M5_NEW = "  if (!current[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid2)) custom_fields[f.member_id] = mid2;\n  if (!current[f.person_location] && n.lead.location) custom_fields[f.person_location] = n.lead.location;  // B2 fill-if-empty\n  for (const k of Object.keys(custom_fields))"

GATE_OLD = "    (!cf[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid));\n  return stageAdvance || fillable;"
GATE_NEW = "    (!cf[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid)) ||\n    (!cf[f.person_location] && !!n.lead.location);\n  return stageAdvance || fillable;"

M7_REPLY_OLD = "const reply_text = render(lastReply);"
M7_REPLY_NEW = (
    "const reply_text = render(lastReply);\n"
    "// B3: collect ALL trailing consecutive is_reply messages (end -> first non-reply), oldest->newest\n"
    "const trailingReplies = [];\n"
    "for (let i = msgs.length - 1; i >= 0; i--) {\n"
    "  const tm = msgs[i];\n"
    "  if (tm && tm.is_reply === true) trailingReplies.unshift(tm); else break;\n"
    "}\n"
    "const reply_note = trailingReplies.length ? trailingReplies.map(render).join('\\n') : reply_text;"
)
M7_OUT_OLD = "    reply_text,\n    is_inmail,"
M7_OUT_NEW = "    reply_text,\n    reply_note,\n    is_inmail,"

RA_OLD = "  const note = b.reply_text || '';"
RA_NEW = "  const note = b.reply_note || '';"


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}

    # CONFIG
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if "person_location" in cfg.get("fields", {}) or "org_website_field" in cfg:
        raise ValueError("CONFIG already has W1.0.8 keys")
    cfg["fields"]["person_location"] = PERSON_LOCATION
    cfg["org_website_field"] = ORG_WEBSITE
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2)

    def rep(nm, field, old, new):
        node = bn[nm]["parameters"]
        if old not in node[field]:
            raise ValueError(f"{nm}.{field}: anchor not found")
        node[field] = node[field].replace(old, new)

    rep("Org Create", "jsonBody", ORG_CREATE_OLD, ORG_CREATE_NEW)
    rep("Person Create", "jsonBody", PC_OLD, PC_NEW)
    rep("Person Patch Invited", "jsonBody", PPI_OLD, PPI_NEW)
    rep("M5 Person Patch Accepted", "jsonBody", M5_OLD, M5_NEW)
    # IF Rank Allows Invited condition leftValue
    cond = bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]
    if GATE_OLD not in cond["leftValue"]:
        raise ValueError("IF Rank Allows Invited: gate anchor not found")
    cond["leftValue"] = cond["leftValue"].replace(GATE_OLD, GATE_NEW)
    # M7 Build
    rep("M7 Build", "jsCode", M7_REPLY_OLD, M7_REPLY_NEW)
    rep("M7 Build", "jsCode", M7_OUT_OLD, M7_OUT_NEW)
    # M7 Reply Activity note source
    rep("M7 Reply Activity", "jsonBody", RA_OLD, RA_NEW)

    w.pop("pinData", None)
    w["active"] = False
    return w


def _cycle(w):
    conns = w["connections"]; color = {n["name"]: 0 for n in w["nodes"]}; bad = []
    def dfs(u):
        color[u] = 1
        for br in (conns.get(u, {}).get("main") or []):
            for e in br or []:
                v = e["node"]
                if color.get(v, 2) == 1: bad.append(f"{u}->{v}")
                elif color.get(v, 2) == 0: dfs(v)
        color[u] = 2
    for n in list(color):
        if color[n] == 0: dfs(n)
    return bad


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("fields", {}).get("person_location") != PERSON_LOCATION: e.append("CONFIG.fields.person_location missing")
    if cfg.get("org_website_field") != ORG_WEBSITE: e.append("CONFIG.org_website_field missing")
    if cfg.get("create_assignment_task") is not False: e.append("create_assignment_task must remain False")
    oc = bn["Org Create"]["parameters"]["jsonBody"]
    if "org_website_field" not in oc or "company_url" not in oc or not oc.strip().startswith("={{ (() =>"): e.append("Org Create website not applied")
    if "f.person_location] = n.lead.location" not in bn["Person Create"]["parameters"]["jsonBody"]: e.append("Person Create location missing")
    for nm, tok in (("Person Patch Invited", "cf[f.person_location] = n.lead.location"),
                    ("M5 Person Patch Accepted", "custom_fields[f.person_location] = n.lead.location")):
        if tok not in bn[nm]["parameters"]["jsonBody"]: e.append(f"{nm} location fill-if-empty missing")
    if "person_location" not in bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]["leftValue"]:
        e.append("IF Rank gate location clause missing")
    mb = bn["M7 Build"]["parameters"]["jsCode"]
    if "trailingReplies" not in mb or "reply_note" not in mb or "reply_note," not in mb: e.append("M7 Build reply_note missing")
    if "b.reply_note || ''" not in bn["M7 Reply Activity"]["parameters"]["jsonBody"]: e.append("M7 Reply Activity not using reply_note")
    if "b.reply_text" in bn["M7 Reply Activity"]["parameters"]["jsonBody"]: e.append("M7 Reply Activity still uses reply_text for note")
    cyc = _cycle(w)
    if cyc: e.append(f"cycle: {cyc}")
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
    print(f"W1.0.8 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
