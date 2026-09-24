#!/usr/bin/env python3
"""W1.0.5 micro-patch: verified Pipedrive link formats only.

- M7 Build no-lead alert: /search?term= (404s) -> /person/{person_id} (verified working).
- M7 Slack Warn (unknown person): drop the Pipedrive link entirely (nothing to open) — LinkedIn only.
- No /search?term= construction anywhere. Lead deep link /leads/inbox/{id} UNCHANGED (Nik-confirmed).
Input: W1.0.4 patched JSON. Deterministic, no network.
"""
from __future__ import annotations
import argparse, copy, json, re, sys
from pathlib import Path
from typing import Any

M7_BUILD_OLD = "'no lead \\u00b7 <' + pdBase + '/search?term=' + encodeURIComponent(aName) + '|Search Pipedrive>'"
M7_BUILD_NEW = "'no lead \\u00b7 <' + pdBase + '/person/' + (person.id || '') + '|Open person>'"

M7_WARN = (
    "={{ (() => { function escapeSlack(v){ return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }\n"
    "  const n = $('Normalize').item.json; const lead = n.lead || {};\n"
    "  const name = lead.full_name || ''; const pos = lead.position || ''; const co = lead.company_name || '';\n"
    "  const camp = (n.campaign && typeof n.campaign === 'object') ? (n.campaign.name || n.campaign.id || '') : (n.campaign || '');\n"
    "  const snd = (n.sender && typeof n.sender === 'object') ? (n.sender.name || n.sender.full_name || n.sender.id || '') : (n.sender || '');\n"
    "  const li = lead.url || lead.profile_url || '';\n"
    "  let paren = ''; if (pos && co) paren = ' (' + escapeSlack(pos) + ' @ ' + escapeSlack(co) + ')'; else if (pos) paren = ' (' + escapeSlack(pos) + ')'; else if (co) paren = ' (@ ' + escapeSlack(co) + ')';\n"
    "  const meta = []; if (camp) meta.push(escapeSlack(camp)); if (snd) meta.push('via ' + escapeSlack(snd));\n"
    "  const metaStr = meta.length ? ' \\u00b7 ' + meta.join(' \\u00b7 ') : '';\n"
    "  const liLink = li ? ' \\u00b7 <' + li + '|LinkedIn>' : '';\n"
    "  return '\\ud83d\\udcac ' + escapeSlack(name) + paren + metaStr + ' \\u2014 \\u26a0\\ufe0f not in Pipedrive' + liLink;\n"
    "})() }}"
)


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}
    mb = bn["M7 Build"]["parameters"]
    if "/search?term=" not in mb["jsCode"]:
        raise ValueError("M7 Build has no /search?term= — already W1.0.5 or drifted")
    if M7_BUILD_OLD not in mb["jsCode"]:
        raise ValueError("M7 Build no-lead search fragment not found")
    mb["jsCode"] = mb["jsCode"].replace(M7_BUILD_OLD, M7_BUILD_NEW)
    bn["M7 Slack Warn"]["parameters"]["text"] = M7_WARN
    w.pop("pinData", None)
    w["active"] = False
    return w


def validate(w) -> list[str]:
    e = []
    blob = json.dumps(w, ensure_ascii=False)
    if "search?term" in blob:
        e.append("R3: 'search?term' still present somewhere")
    bn = {n["name"]: n for n in w["nodes"]}
    mb = bn["M7 Build"]["parameters"]["jsCode"]
    if "/person/' + (person.id" not in mb:
        e.append("M7 Build no-lead must use /person/{person_id}")
    if "/leads/inbox/' + selectedLead.id" not in mb:
        e.append("M7 Build lead deep link /leads/inbox/ must be unchanged")
    warn = bn["M7 Slack Warn"]["parameters"]["text"]
    if "pipedrive_base" in warn or "/person/" in warn or "/leads/" in warn:
        e.append("M7 Slack Warn must have NO Pipedrive link (LinkedIn only)")
    if "not in Pipedrive" not in warn or "LinkedIn" not in warn:
        e.append("M7 Slack Warn must keep 'not in Pipedrive' + LinkedIn")
    # every pdBase/pipedrive_base concatenation must be one of the two verified path templates
    for m in re.finditer(r"(?:pdBase|pipedrive_base)\s*\+\s*'([^']*)'", blob):
        lit = m.group(1)
        if not (lit.startswith("/leads/inbox/") or lit.startswith("/person/")):
            e.append(f"non-verified Pipedrive path literal concatenated to base: {lit!r}")
    if w.get("active") is not False:
        e.append("not inactive")
    if len(w["nodes"]) != 90:
        e.append(f"expected 90 nodes, got {len(w['nodes'])}")
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
    print(f"W1.0.5 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
