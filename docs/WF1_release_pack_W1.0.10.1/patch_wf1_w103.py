#!/usr/bin/env python3
"""Apply the W1.0.3 hardening pack (R1-R5) to the W1.0.2 patched WF-1 export.

R1  Person-level Source = enum 446 ("Cold Outreach") on Person Create ONLY (CONFIG source_value).
R2  Fill-missing-only enrichment for existing persons (sent Person Patch Invited + gate; M5 accepted patch).
R3  Message-first warn (known person, no stage) — non-blocking tee in M6.
R4  Strip empty-string custom fields before every POST/PATCH body.
R5  Alert cosmetics: omit empty "( @ )" / graceful campaign·sender line in M7 Reply Context.

Input: "WF-1 HeyReach Receiver - W1.0.2 patched.json". Deterministic, no network.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import uuid
from pathlib import Path
from typing import Any

_UID = 0


def uid() -> str:
    global _UID
    _UID += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wf1-w103:{_UID}"))


SLACK_CRED = {"slackApi": {"id": "Udq1K604RpJqg1cR", "name": "Slack account 3"}}
STRIP = "for (const k of Object.keys(cf)) if (cf[k] === '') delete cf[k];"  # R4 shared 1-liner

# ---- R2: full rewrite of Person Patch Invited (existing-person, sent) ----
PERSON_PATCH_INVITED = (
    "={{ (() => {\n"
    "  const cfg = $('CONFIG').item.json;\n"
    "  const f = cfg.fields;\n"
    "  const n = $('Normalize').item.json;\n"
    "  const person = $('Person Get').item.json.data || {};\n"
    "  const current = person.custom_fields || {};\n"
    "  const curStage = current[f.stage] || null;\n"
    "  const curRank = cfg.stageRank[curStage] || 0;\n"
    "  const invitedRank = cfg.stageRank['Invited'] || 1;\n"
    "  const cf = {};\n"
    "  if (curRank < invitedRank) cf[f.stage] = 'Invited';  // forward-only stage\n"
    "  const campaignName = n.campaign && n.campaign.name ? n.campaign.name : '';\n"
    "  if (!current[f.campaign] && campaignName) cf[f.campaign] = campaignName;\n"
    "  if (!current[f.company] && n.lead.company_name) cf[f.company] = n.lead.company_name;\n"
    "  if (!current[f.position] && n.lead.position) cf[f.position] = n.lead.position;\n"
    "  if (!current[f.li_url] && n.lead.url) cf[f.li_url] = n.lead.url;\n"
    "  if (!current[f.public_id] && n.lead.slug) cf[f.public_id] = n.lead.slug;\n"
    "  const mid = +n.lead.id;\n"
    "  if (!current[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid)) cf[f.member_id] = mid;\n"
    "  " + STRIP + "\n"
    "  return JSON.stringify({ custom_fields: cf });\n"
    "})() }}"
)

# ---- R2: composite gate for IF Rank Allows Invited (stageAdvance || anyFillableEmpty) ----
IF_RANK_INVITED_LEFT = (
    "={{ (() => {\n"
    "  const cfg = $('CONFIG').item.json;\n"
    "  const f = cfg.fields;\n"
    "  const n = $('Normalize').item.json;\n"
    "  const person = $json.data || {};\n"
    "  const cf = person.custom_fields || {};\n"
    "  const curStage = cf[f.stage] || null;\n"
    "  const curRank = cfg.stageRank[curStage] || 0;\n"
    "  const invitedRank = cfg.stageRank['Invited'] || 1;\n"
    "  const stageAdvance = curRank < invitedRank;\n"
    "  const campaignName = n.campaign && n.campaign.name ? n.campaign.name : '';\n"
    "  const mid = +n.lead.id;\n"
    "  const fillable =\n"
    "    (!cf[f.campaign] && !!campaignName) ||\n"
    "    (!cf[f.company] && !!n.lead.company_name) ||\n"
    "    (!cf[f.position] && !!n.lead.position) ||\n"
    "    (!cf[f.li_url] && !!n.lead.url) ||\n"
    "    (!cf[f.public_id] && !!n.lead.slug) ||\n"
    "    (!cf[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid));\n"
    "  return stageAdvance || fillable;\n"
    "})() }}"
)

# ---- R5: full rewrite of M7 Reply Context (graceful parenthetical / campaign·sender line) ----
M7_REPLY_CONTEXT = (
    "// ===== M7 Reply Context (F10 + R5) — depends ONLY on CONFIG + Normalize =====\n"
    "const CFG = $('CONFIG').item.json;\n"
    "const norm = $('Normalize').item.json;\n"
    "function escapeSlack(v){ return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }\n"
    "\n"
    "const msgs = Array.isArray(norm.msgs) ? norm.msgs : [];\n"
    "function render(m){\n"
    "  if (!m) return '[empty message]';\n"
    "  const t = (m.message == null ? '' : String(m.message)).trim();\n"
    "  if (t) return t;\n"
    "  const mt = String(m.message_type || '').toLowerCase();\n"
    "  if (mt.includes('attach')) return '[attachment]';\n"
    "  if (mt.includes('voice')) return '[voice note]';\n"
    "  return '[empty message]';\n"
    "}\n"
    "const replies = msgs.filter(m => m && m.is_reply === true);\n"
    "const lastReply = replies.length ? replies[replies.length - 1] : (msgs.length ? msgs[msgs.length - 1] : null);\n"
    "const reply_text = render(lastReply);\n"
    "\n"
    "const lead = norm.lead || {};\n"
    "const camp = norm.campaign;\n"
    "const campaign_name = (camp && typeof camp === 'object') ? (camp.name || camp.id || '') : (camp || '');\n"
    "const snd = norm.sender;\n"
    "const sender_name = (snd && typeof snd === 'object') ? (snd.name || snd.full_name || snd.id || '') : (snd || '');\n"
    "const full_name = lead.full_name || '';\n"
    "const position = lead.position || '';\n"
    "const company_name = lead.company_name || '';\n"
    "const linkedin_url = lead.url || lead.profile_url || '';\n"
    "const is_inmail = !!norm.is_inmail;\n"
    "\n"
    "// R5: parenthetical only from non-empty parts (no empty '( @ )')\n"
    "let paren = '';\n"
    "if (position && company_name) paren = ' (' + escapeSlack(position) + ' @ ' + escapeSlack(company_name) + ')';\n"
    "else if (position) paren = ' (' + escapeSlack(position) + ')';\n"
    "else if (company_name) paren = ' (@ ' + escapeSlack(company_name) + ')';\n"
    "// R5: campaign / via-sender / InMail line — omit empty parts gracefully\n"
    "const parts = [];\n"
    "if (campaign_name) parts.push('Campaign: ' + escapeSlack(campaign_name));\n"
    "if (sender_name) parts.push('via ' + escapeSlack(sender_name));\n"
    "if (is_inmail) parts.push('InMail');\n"
    "const line2 = parts.join(' \\u00b7 ');\n"
    "\n"
    "const alert_text =\n"
    "  '\\ud83d\\udcac Reply from ' + escapeSlack(full_name) + paren + '\\n' +\n"
    "  (line2 ? line2 + '\\n' : '') +\n"
    "  '> ' + escapeSlack(reply_text) + '\\n' +\n"
    "  'LinkedIn: ' + escapeSlack(linkedin_url);\n"
    "\n"
    "return { json: { reply_text, is_inmail, campaign_name, sender_name, full_name, position, company_name, linkedin_url, alert_text } };"
)

# ---- R3: M6 Message First Warn text ----
M6_MSG_FIRST_WARN_TEXT = (
    "={{ (() => { function escapeSlack(v){ return String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }\n"
    "  const b = $('M6 Build').item.json;\n"
    "  const person = $('M6 Person Get').item.json.data || {};\n"
    "  const name = [person.first_name, person.last_name].filter(Boolean).join(' ') || person.name || ('person ' + b.person_id);\n"
    "  return '\\u26a0\\ufe0f WF-1: message-first flow detected \\u2014 message_sent for person ' + b.person_id + ' (' + escapeSlack(name) + ') with no invite history. Stage semantics may not apply; review campaign type.';\n"
    "})() }}"
)


def edge(n, i=0):
    return {"node": n, "type": "main", "index": i}


def slack_node(name, text, pos):
    return {
        "parameters": {"select": "channel",
                       "channelId": {"__rl": True, "value": "={{ $('CONFIG').item.json.slack_channel }}", "mode": "id"},
                       "text": text, "otherOptions": {}},
        "id": uid(), "name": name, "type": "n8n-nodes-base.slack", "typeVersion": 2.3,
        "position": pos, "credentials": copy.deepcopy(SLACK_CRED),
    }


def if_node(name, left, pos):
    return {
        "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 1},
                                      "conditions": [{"id": uid(), "leftValue": left, "rightValue": True,
                                                      "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                      "combinator": "and"}, "options": {}},
        "id": uid(), "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2, "position": pos,
    }


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}
    if "M6 IF Message First" in bn or "M6 Message First Warn" in bn:
        raise ValueError("already W1.0.3-patched")

    # ---- R0/R1: CONFIG gets fields.source + source_value ----
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if "source" in cfg["fields"]:
        raise ValueError("CONFIG.fields.source already present")
    cfg["fields"]["source"] = "6070ae31f09228f95048b0f68982b1cd4d3a684a"
    cfg["source_value"] = 446  # enum option id for "Cold Outreach"
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)

    # ---- R1 + R4: Person Create — add source (create-only) + strip empties ----
    pc = bn["Person Create"]["parameters"]
    anchor = "  cf[f.summary] = n.lead.summary;\n  const body = {"
    assert anchor in pc["jsonBody"], "Person Create anchor not found"
    pc["jsonBody"] = pc["jsonBody"].replace(
        anchor,
        "  cf[f.summary] = n.lead.summary;\n"
        "  cf[f.source] = $('CONFIG').item.json.source_value;  // R1 create-only\n"
        "  for (const k of Object.keys(cf)) if (cf[k] === '') delete cf[k];  // R4\n"
        "  const body = {")

    # ---- R2: Person Patch Invited body + composite gate ----
    bn["Person Patch Invited"]["parameters"]["jsonBody"] = PERSON_PATCH_INVITED
    cond = bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]
    cond["leftValue"] = IF_RANK_INVITED_LEFT
    cond["rightValue"] = True
    cond["operator"] = {"type": "boolean", "operation": "true", "singleValue": True}

    # ---- R2 + R4: M5 Person Patch Accepted — extend fill-if-empty + strip ----
    m5 = bn["M5 Person Patch Accepted"]["parameters"]
    m5_anchor = ("  const campaignName = n.campaign && n.campaign.name ? n.campaign.name : '';\n"
                 "  if (!current[f.campaign] && campaignName) custom_fields[f.campaign] = campaignName;\n"
                 "  return JSON.stringify({ custom_fields });")
    assert m5_anchor in m5["jsonBody"], "M5 Person Patch Accepted anchor not found"
    m5["jsonBody"] = m5["jsonBody"].replace(m5_anchor,
        "  const campaignName = n.campaign && n.campaign.name ? n.campaign.name : '';\n"
        "  if (!current[f.campaign] && campaignName) custom_fields[f.campaign] = campaignName;\n"
        "  if (!current[f.company] && n.lead.company_name) custom_fields[f.company] = n.lead.company_name;\n"
        "  if (!current[f.position] && n.lead.position) custom_fields[f.position] = n.lead.position;\n"
        "  if (!current[f.li_url] && n.lead.url) custom_fields[f.li_url] = n.lead.url;\n"
        "  if (!current[f.public_id] && n.lead.slug) custom_fields[f.public_id] = n.lead.slug;\n"
        "  const mid2 = +n.lead.id;\n"
        "  if (!current[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid2)) custom_fields[f.member_id] = mid2;\n"
        "  for (const k of Object.keys(custom_fields)) if (custom_fields[k] === '') delete custom_fields[k];\n"
        "  return JSON.stringify({ custom_fields });")

    # M5 IF Rank Accepted — extend gate to fire on fillable-only case
    m5cond = bn["M5 IF Rank Accepted"]["parameters"]["conditions"]["conditions"][0]
    m5_gate_old = "  return curRank < acceptedRank || !cf[f.connected_at] || (!cf[f.campaign] && !!campaignName);"
    assert m5_gate_old in m5cond["leftValue"], "M5 gate anchor not found"
    m5cond["leftValue"] = m5cond["leftValue"].replace(m5_gate_old,
        "  const mid = +n.lead.id;\n"
        "  return curRank < acceptedRank || !cf[f.connected_at] || (!cf[f.campaign] && !!campaignName)\n"
        "    || (!cf[f.company] && !!n.lead.company_name) || (!cf[f.position] && !!n.lead.position)\n"
        "    || (!cf[f.li_url] && !!n.lead.url) || (!cf[f.public_id] && !!n.lead.slug)\n"
        "    || (!cf[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid));")

    # ---- R3 + R4: M6 Build — message_first flag + strip ----
    m6 = bn["M6 Build"]["parameters"]
    a1 = "const curRank = curStage && ranks[curStage] != null ? ranks[curStage] : 0;"
    assert a1 in m6["jsCode"]
    m6["jsCode"] = m6["jsCode"].replace(a1, a1 + "\nconst message_first = !curStage;  // R3: known person, no invite history")
    a2 = "if (writeConv) cf[f.conversation] = convValue;\nconst doPatch = Object.keys(cf).length > 0;"
    assert a2 in m6["jsCode"]
    m6["jsCode"] = m6["jsCode"].replace(a2,
        "if (writeConv) cf[f.conversation] = convValue;\n" + STRIP + "  // R4\nconst doPatch = Object.keys(cf).length > 0;")
    a3 = "  __doPatch: doPatch,\n  patchBody,"
    assert a3 in m6["jsCode"]
    m6["jsCode"] = m6["jsCode"].replace(a3, "  __doPatch: doPatch,\n  patchBody,\n  message_first,")

    # ---- R4: M7 Build — strip custom_fields ----
    m7 = bn["M7 Build"]["parameters"]
    a4 = "const __doPatch = Object.keys(custom_fields).length > 0;"
    assert a4 in m7["jsCode"]
    m7["jsCode"] = m7["jsCode"].replace(a4,
        "for (const k of Object.keys(custom_fields)) if (custom_fields[k] === '') delete custom_fields[k];  // R4\n" + a4)

    # ---- R5: M7 Reply Context full rewrite ----
    bn["M7 Reply Context"]["parameters"]["jsCode"] = M7_REPLY_CONTEXT

    # ---- R3: new nodes + non-blocking tee ----
    if_mf = if_node("M6 IF Message First", "={{ $json.message_first === true }}", [3888, 1200])
    warn = slack_node("M6 Message First Warn", M6_MSG_FIRST_WARN_TEXT, [4160, 1120])
    w["nodes"].extend([if_mf, warn])
    conns = w["connections"]
    conns["M6 Build"] = {"main": [[edge("M6 IF Message First")]]}
    # true -> warn (leaf) AND continue to M6 IF Lead ID ; false -> continue only
    conns["M6 IF Message First"] = {"main": [[edge("M6 Message First Warn"), edge("M6 IF Lead ID")],
                                             [edge("M6 IF Lead ID")]]}
    # M6 Message First Warn is a leaf (no outgoing). M6 IF Lead ID unchanged downstream.

    w.pop("pinData", None)
    w["active"] = False
    return w


def _has_cycle(conns, names):
    color = {n: 0 for n in names}
    bad = []
    def dfs(u):
        color[u] = 1
        for br in conns.get(u, {}).get("main", []):
            for e in br:
                v = e["node"]
                if color.get(v, 2) == 1:
                    bad.append(f"{u}->{v}")
                elif color.get(v, 2) == 0:
                    dfs(v)
        color[u] = 2
    for n in names:
        if color.get(n, 2) == 0:
            dfs(n)
    return bad


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    names = set(bn)
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    # R0/R1
    if cfg.get("fields", {}).get("source") != "6070ae31f09228f95048b0f68982b1cd4d3a684a":
        e.append("R0: CONFIG.fields.source missing/wrong")
    if cfg.get("source_value") != 446:
        e.append("R1: CONFIG.source_value != 446")
    pc = bn["Person Create"]["parameters"]["jsonBody"]
    if "cf[f.source] = $('CONFIG').item.json.source_value" not in pc:
        e.append("R1: Person Create does not set source")
    for nm in ("Person Patch Invited", "M5 Person Patch Accepted", "M7 Build", "M6 Build"):
        body = json.dumps(bn[nm]["parameters"], ensure_ascii=False)
        if "f.source" in body or "source_value" in body:
            e.append(f"R1: {nm} must NOT touch source (create-only)")
    # R2
    if "if (!current[f.company]" not in bn["Person Patch Invited"]["parameters"]["jsonBody"]:
        e.append("R2: Person Patch Invited missing fill-if-empty company")
    if "fillable" not in bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]["leftValue"]:
        e.append("R2: IF Rank Allows Invited gate not composite")
    if "if (!current[f.company]" not in bn["M5 Person Patch Accepted"]["parameters"]["jsonBody"]:
        e.append("R2: M5 patch missing fill-if-empty company")
    # R3
    if "M6 IF Message First" not in bn or "M6 Message First Warn" not in bn:
        e.append("R3: message-first nodes missing")
    if "message_first" not in bn["M6 Build"]["parameters"]["jsCode"]:
        e.append("R3: M6 Build missing message_first flag")
    mf = w["connections"].get("M6 IF Message First", {}).get("main", [])
    t0 = [x["node"] for x in mf[0]] if mf else []
    if "M6 Message First Warn" not in t0 or "M6 IF Lead ID" not in t0:
        e.append("R3: tee true-output must fan to warn AND M6 IF Lead ID")
    if w["connections"].get("M6 Message First Warn"):
        e.append("R3: warn must be a leaf (no outgoing)")
    if w["connections"].get("M6 Build", {}).get("main") != [[{"node": "M6 IF Message First", "type": "main", "index": 0}]]:
        e.append("R3: M6 Build must feed M6 IF Message First")
    # R4
    for nm in ("Person Create", "Person Patch Invited", "M5 Person Patch Accepted", "M6 Build", "M7 Build"):
        if "=== ''" not in bn[nm]["parameters"].get("jsonBody", bn[nm]["parameters"].get("jsCode", "")):
            e.append(f"R4: {nm} does not strip empty strings")
    # R5
    rc = bn["M7 Reply Context"]["parameters"]["jsCode"]
    if "( @ )" in rc or "' @ ' + escapeSlack(company_name) + ')'" in rc.replace("(position && company_name)", ""):
        pass
    if "if (position && company_name)" not in rc or "let paren" not in rc:
        e.append("R5: M7 Reply Context not using conditional parenthetical")
    # graph
    cyc = _has_cycle(w["connections"], names)
    if cyc:
        e.append(f"cycle(s): {cyc}")
    for src, c in w["connections"].items():
        for br in c.get("main", []):
            for x in br:
                if x["node"] not in names:
                    e.append(f"dangling edge {src}->{x['node']}")
    if w.get("active") is not False:
        e.append("not inactive")
    if "pinData" in w:
        e.append("pinData present")
    ids = [n["id"] for n in w["nodes"]]
    if len(ids) != len(set(ids)):
        e.append("dup node ids")
    if len(w["nodes"]) != 91:
        e.append(f"expected 91 nodes, got {len(w['nodes'])}")
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
    print(f"W1.0.3 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
