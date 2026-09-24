#!/usr/bin/env python3
"""Apply W1.0.4 (compact reply alert + Pipedrive deep link) to the W1.0.3 patched export.

- Remove M7 Reply Context (front Slack hop); restore Switch[3] -> M7 IF Email Present.
- Build compact alert_text inside M7 Build (lead deep-link when lead_id, search fallback else).
- Move M7 Critical Slack to M7 Build -> M7 Critical Slack -> M7 IF Patch (after GETs, before writes).
- Rewrite M7 Slack Warn (unknown person) to compact "not in Pipedrive" (single message; Normalize-only).
- CONFIG += pipedrive_base. No reply_text / no InMail in any alert.
Input: W1.0.3 patched JSON. Deterministic, no network.
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

PDBASE = "https://janeasystems.pipedrive.com"

ALERT_BLOCK = (
    "\n// ===== W1.0.4 compact reply alert (lead_id known here; posts after GETs, before writes) =====\n"
    "function escapeSlack(v){ return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }\n"
    "const pdBase = CFG.pipedrive_base;\n"
    "const aName = (norm.lead && norm.lead.full_name) || '';\n"
    "const aPos = (norm.lead && norm.lead.position) || '';\n"
    "const aCo = (norm.lead && norm.lead.company_name) || '';\n"
    "const aCamp = (norm.campaign && typeof norm.campaign === 'object') ? (norm.campaign.name || norm.campaign.id || '') : (norm.campaign || '');\n"
    "const aSnd = (norm.sender && typeof norm.sender === 'object') ? (norm.sender.name || norm.sender.full_name || norm.sender.id || '') : (norm.sender || '');\n"
    "const aLi = (norm.lead && (norm.lead.url || norm.lead.profile_url)) || '';\n"
    "let aParen = '';\n"
    "if (aPos && aCo) aParen = ' (' + escapeSlack(aPos) + ' @ ' + escapeSlack(aCo) + ')';\n"
    "else if (aPos) aParen = ' (' + escapeSlack(aPos) + ')';\n"
    "else if (aCo) aParen = ' (@ ' + escapeSlack(aCo) + ')';\n"
    "const aMeta = [];\n"
    "if (aCamp) aMeta.push(escapeSlack(aCamp));\n"
    "if (aSnd) aMeta.push('via ' + escapeSlack(aSnd));\n"
    "const aMetaStr = aMeta.length ? ' \\u00b7 ' + aMeta.join(' \\u00b7 ') : '';\n"
    "const aLead = (selectedLead && selectedLead.id)\n"
    "  ? '<' + pdBase + '/leads/inbox/' + selectedLead.id + '|Open lead>'\n"
    "  : 'no lead \\u00b7 <' + pdBase + '/search?term=' + encodeURIComponent(aName) + '|Search Pipedrive>';\n"
    "const aLiLink = aLi ? ' \\u00b7 <' + aLi + '|LinkedIn>' : '';\n"
    "const alert_text = '\\ud83d\\udcac ' + escapeSlack(aName) + aParen + aMetaStr + ' \\u2014 ' + aLead + aLiLink;\n"
)

M7_SLACK_WARN_TEXT = (
    "={{ (() => { function escapeSlack(v){ return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }\n"
    "  const n = $('Normalize').item.json; const cfg = $('CONFIG').item.json; const lead = n.lead || {};\n"
    "  const name = lead.full_name || ''; const pos = lead.position || ''; const co = lead.company_name || '';\n"
    "  const camp = (n.campaign && typeof n.campaign === 'object') ? (n.campaign.name || n.campaign.id || '') : (n.campaign || '');\n"
    "  const snd = (n.sender && typeof n.sender === 'object') ? (n.sender.name || n.sender.full_name || n.sender.id || '') : (n.sender || '');\n"
    "  const li = lead.url || lead.profile_url || '';\n"
    "  let paren = ''; if (pos && co) paren = ' (' + escapeSlack(pos) + ' @ ' + escapeSlack(co) + ')'; else if (pos) paren = ' (' + escapeSlack(pos) + ')'; else if (co) paren = ' (@ ' + escapeSlack(co) + ')';\n"
    "  const meta = []; if (camp) meta.push(escapeSlack(camp)); if (snd) meta.push('via ' + escapeSlack(snd));\n"
    "  const metaStr = meta.length ? ' \\u00b7 ' + meta.join(' \\u00b7 ') : '';\n"
    "  const search = '<' + cfg.pipedrive_base + '/search?term=' + encodeURIComponent(name) + '|Search Pipedrive>';\n"
    "  const liLink = li ? ' \\u00b7 <' + li + '|LinkedIn>' : '';\n"
    "  return '\\ud83d\\udcac ' + escapeSlack(name) + paren + metaStr + ' \\u2014 \\u26a0\\ufe0f not in Pipedrive \\u00b7 ' + search + liLink;\n"
    "})() }}"
)


def edge(n, i=0):
    return {"node": n, "type": "main", "index": i}


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}
    if "M7 Reply Context" not in bn:
        raise ValueError("M7 Reply Context absent — already W1.0.4-patched or drifted")

    # CONFIG += pipedrive_base
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if "pipedrive_base" in cfg:
        raise ValueError("CONFIG.pipedrive_base already present")
    cfg["pipedrive_base"] = PDBASE
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)

    # M7 Build: insert alert block + add alert_text to return
    mb = bn["M7 Build"]["parameters"]
    a1 = "const patchBody = { custom_fields };\n\nreturn {"
    if a1 not in mb["jsCode"]:
        raise ValueError("M7 Build return anchor not found")
    mb["jsCode"] = mb["jsCode"].replace(a1, "const patchBody = { custom_fields };\n" + ALERT_BLOCK + "\nreturn {")
    a2 = "    conversation_id: conversationValue,\n    activityType: CFG.activity_type_msg,"
    if a2 not in mb["jsCode"]:
        raise ValueError("M7 Build json anchor not found")
    mb["jsCode"] = mb["jsCode"].replace(a2, "    conversation_id: conversationValue,\n    alert_text,\n    activityType: CFG.activity_type_msg,")

    # M7 Slack Warn -> compact "not in Pipedrive"
    bn["M7 Slack Warn"]["parameters"]["text"] = M7_SLACK_WARN_TEXT

    # M7 Critical Slack: keep text/onError; tidy position near M7 Build
    bn["M7 Critical Slack"]["position"] = [2600, 1840]
    # text stays "={{ $json.alert_text }}" (now reads M7 Build output)

    # Remove M7 Reply Context node
    w["nodes"] = [n for n in w["nodes"] if n["name"] != "M7 Reply Context"]

    # Rewire
    conns = w["connections"]
    sw = conns["Switch"]["main"]
    sw[3] = [edge("M7 IF Email Present")]              # restore direct front connection
    conns.pop("M7 Reply Context", None)
    conns["M7 Build"] = {"main": [[edge("M7 Critical Slack")]]}   # was -> M7 IF Patch
    conns["M7 Critical Slack"] = {"main": [[edge("M7 IF Patch")]]}  # was -> M7 IF Email Present

    w.pop("pinData", None)
    w["active"] = False
    return w


def _has_cycle(conns, names):
    color = {n: 0 for n in names}; bad = []
    def dfs(u):
        color[u] = 1
        for br in conns.get(u, {}).get("main", []):
            for e in br:
                v = e["node"]
                if color.get(v, 2) == 1: bad.append(f"{u}->{v}")
                elif color.get(v, 2) == 0: dfs(v)
        color[u] = 2
    for n in names:
        if color.get(n, 2) == 0: dfs(n)
    return bad


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    names = set(bn); conns = w["connections"]
    if "M7 Reply Context" in bn:
        e.append("M7 Reply Context should be removed")
    # front restored
    if conns["Switch"]["main"][3] != [edge("M7 IF Email Present")]:
        e.append("Switch[3] must go direct to M7 IF Email Present")
    # moved critical slack
    if conns.get("M7 Build", {}).get("main") != [[edge("M7 Critical Slack")]]:
        e.append("M7 Build must feed M7 Critical Slack")
    if conns.get("M7 Critical Slack", {}).get("main") != [[edge("M7 IF Patch")]]:
        e.append("M7 Critical Slack must feed M7 IF Patch")
    cs = bn["M7 Critical Slack"]
    if cs["parameters"]["text"].strip() != "={{ $json.alert_text }}":
        e.append("M7 Critical Slack text must be ={{ $json.alert_text }} (= prefix)")
    if cs.get("onError") != "continueRegularOutput":
        e.append("M7 Critical Slack must keep onError=continueRegularOutput")
    # M7 Build alert_text
    mb = bn["M7 Build"]["parameters"]["jsCode"]
    if "const alert_text" not in mb or "alert_text," not in mb:
        e.append("M7 Build must build+return alert_text")
    if "/leads/inbox/" not in mb or "/search?term=" not in mb:
        e.append("M7 Build alert_text must have deep link + search fallback")
    alert_line = mb.split("const alert_text =")[1].split(";")[0] if "const alert_text =" in mb else ""
    if "reply_text" in alert_line:
        e.append("alert_text assembly must not reference reply_text")
    # alert must not contain InMail marker literal
    for nm in ("M7 Build", "M7 Slack Warn"):
        blob = bn[nm]["parameters"].get("jsCode", bn[nm]["parameters"].get("text", ""))
        if "InMail" in blob:
            e.append(f"{nm} alert must not contain InMail marker")
    # M7 Slack Warn compact, Normalize-only (no M7 Build)
    warn = bn["M7 Slack Warn"]["parameters"]["text"]
    if "not in Pipedrive" not in warn:
        e.append("M7 Slack Warn must use compact 'not in Pipedrive' format")
    if "M7 Build" in warn:
        e.append("F10.6: M7 Slack Warn must not reference M7 Build")
    if conns.get("M7 Slack Warn"):
        e.append("M7 Slack Warn must be a terminal leaf")
    # CONFIG
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("pipedrive_base") != PDBASE:
        e.append("CONFIG.pipedrive_base missing")
    # graph
    cyc = _has_cycle(conns, names)
    if cyc: e.append(f"cycle(s): {cyc}")
    for s, cc in conns.items():
        for br in cc.get("main", []):
            for x in br:
                if x["node"] not in names: e.append(f"dangling {s}->{x['node']}")
    # NEW invariant: no PATCH/POST precedes M7 Critical Slack on the reply path
    # walk from M7 IF Email Present forward until M7 Critical Slack; assert intermediates aren't PATCH/POST
    def method(n):
        return (bn.get(n, {}).get("parameters") or {}).get("method")
    seen, stack = set(), ["M7 IF Email Present"]
    while stack:
        u = stack.pop()
        if u == "M7 Critical Slack":
            continue
        for br in conns.get(u, {}).get("main", []):
            for x in br:
                v = x["node"]
                if v == "M7 Critical Slack":
                    continue
                if v not in seen:
                    seen.add(v)
                    if bn.get(v, {}).get("type") == "n8n-nodes-base.httpRequest" and method(v) in ("PATCH", "POST"):
                        e.append(f"write node {v} precedes M7 Critical Slack on reply path")
                    stack.append(v)
    # ancestry: M7 Lead Get -> ... -> M7 Critical Slack -> ... -> M7 Person Patch
    if conns.get("M7 Lead Get", {}).get("main") != [[edge("M7 Build")]]:
        e.append("M7 Lead Get must feed M7 Build (Critical Slack downstream of reads)")
    if w.get("active") is not False: e.append("not inactive")
    if "pinData" in w: e.append("pinData present")
    if len(w["nodes"]) != 90: e.append(f"expected 90 nodes, got {len(w['nodes'])}")
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
    print(f"W1.0.4 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
