#!/usr/bin/env python3
"""Apply the W1.0.1 fix-pack (F9-F12) to the W1.0 patched WF-1 export.

Base (input): "WF-1 HeyReach Receiver - W1.0 patched.json" (88 nodes, inactive).
Output: W1.0.1 patched JSON (+ optional api-payload). Deterministic, no network calls.

F9  Restore "Replied to invite" classification (hybrid rule) in M7 Build.
F10 Failure-isolated critical reply alert BEFORE CRM writes; de-duplicate tail
    alert; separate warn terminals (unknown-person vs no-lead).
F11 Remove require('crypto') from Dedupe (import-free deterministic key).
F12 Slack mrkdwn escaping for all user-originated strings.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import uuid
from pathlib import Path
from typing import Any

_UID_COUNTER = 0


def uid() -> str:
    global _UID_COUNTER
    _UID_COUNTER += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wf1-w101:{_UID_COUNTER}"))


def edge(node: str, index: int = 0) -> dict[str, Any]:
    return {"node": node, "type": "main", "index": index}


def get_node(by_name: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    try:
        return by_name[name]
    except KeyError as exc:
        raise KeyError(f"Required node not found: {name}") from exc


SLACK_CRED = {"slackApi": {"id": "Udq1K604RpJqg1cR", "name": "Slack account 3"}}

# Shared escaper used verbatim inside every Slack-building node (F12).
ESCAPE_FN = ("function escapeSlack(v){ return String(v ?? '')"
             ".replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }")

# ---- F10: M7 Reply Context (depends ONLY on CONFIG + Normalize) ----
REPLY_CONTEXT_CODE = (
    "// ===== M7 Reply Context (F10) — reply alert context; depends ONLY on CONFIG + Normalize =====\n"
    "// Runs before any resolver node. Does NOT reference M7 Person Get / M7 Lead Get / M7 Build.\n"
    "const CFG = $('CONFIG').item.json;\n"
    "const norm = $('Normalize').item.json;\n"
    + ESCAPE_FN + "\n"
    "\n"
    "// reply_text: last is_reply===true, with empty-text placeholders (same rules as M7 Build)\n"
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
    "// alert_text — escape every user-originated field (F12); linkedin_url is plain text (escaped)\n"
    "const inMailSuffix = is_inmail ? ' \\u00b7 InMail' : '';\n"
    "const alert_text =\n"
    "  '\\ud83d\\udcac Reply from ' + escapeSlack(full_name) + ' (' + escapeSlack(position) + ' @ ' + escapeSlack(company_name) + ')\\n' +\n"
    "  'Campaign: ' + escapeSlack(campaign_name) + ' \\u00b7 via ' + escapeSlack(sender_name) + inMailSuffix + '\\n' +\n"
    "  '> ' + escapeSlack(reply_text) + '\\n' +\n"
    "  'LinkedIn: ' + escapeSlack(linkedin_url);\n"
    "\n"
    "return { json: { reply_text, is_inmail, campaign_name, sender_name, full_name, position, company_name, linkedin_url, alert_text } };"
)

# ---- F12: unknown-person warn (Normalize-only, NO M7 Build reference) ----
M7_SLACK_WARN_TEXT = (
    "={{ (() => { " + ESCAPE_FN +
    " const n = $('Normalize').item.json;"
    " const profile = (n.lead && (n.lead.url || n.lead.profile_url)) || '';"
    " return '\\u26a0\\ufe0f WF-1: ' + n.event + ' for unknown person ' + escapeSlack(profile) + ' \\u2014 skipped';"
    " })() }}"
)

# ---- F10: no-lead warn (person resolved, no lead; alert already sent) ----
M7_NO_LEAD_WARN_TEXT = (
    "={{ '\\u26a0\\ufe0f WF-1: ' + $('Normalize').item.json.event"
    " + ' \\u2014 person resolved but no lead found for person ' + (($('M7 Build').item.json.person_id) ?? '')"
    " + '; CRM write skipped (reply alert already sent)' }}"
)


def branch_warn_text(get_ref: str) -> str:
    """M5/M6 warn: dual message (resolved-no-lead vs unknown), fixed braces + escaped profile (F12)."""
    return (
        "={{ (() => { " + ESCAPE_FN +
        " const n = $('Normalize').item.json;"
        " let personId = $json.person_id || null;"
        " if (!personId) { try { personId = $('" + get_ref + "').item.json.person_id"
        " || ($('" + get_ref + "').item.json.data && $('" + get_ref + "').item.json.data.id) || null; } catch (e) {} }"
        " if (personId) return '\\u26a0\\ufe0f WF-1: ' + n.event + ' \\u2014 person resolved but no lead found for person ' + personId + '; write skipped';"
        " const profile = (n.lead && (n.lead.url || n.lead.profile_url)) || '';"
        " return '\\u26a0\\ufe0f WF-1: ' + n.event + ' for unknown person ' + escapeSlack(profile) + ' \\u2014 skipped';"
        " })() }}"
    )


def slack_node(name: str, text: str, position: list[int], on_error: str | None = None) -> dict[str, Any]:
    node = {
        "parameters": {
            "select": "channel",
            "channelId": {"__rl": True, "value": "={{ $('CONFIG').item.json.slack_channel }}", "mode": "id"},
            "text": text,
            "otherOptions": {},
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.slack",
        "typeVersion": 2.3,
        "position": position,
        "credentials": copy.deepcopy(SLACK_CRED),
    }
    if on_error:
        node["onError"] = on_error
    return node


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    nodes: list[dict[str, Any]] = w["nodes"]
    by_name = {n["name"]: n for n in nodes}

    if "M7 Reply Context" in by_name or "M7 Critical Slack" in by_name or "M7 No Lead Warn" in by_name:
        raise ValueError("Input already appears to be W1.0.1-patched; refusing to double-apply")
    for required in ("M7 Build", "Dedupe", "M8 Slack", "M8 Slack Text", "M8 Task", "M7 Slack Warn"):
        get_node(by_name, required)

    # ===== F9 — restore "Replied to invite" classification =====
    m7 = get_node(by_name, "M7 Build")
    code = m7["parameters"]["jsCode"]
    old_line = "const targetStage = 'Replied';"
    if code.count(old_line) != 1:
        raise ValueError("F9: expected exactly one hardcoded targetStage line in M7 Build")
    f9_block = (
        "const followUpRank = rank['First follow-up sent'] ?? 3;\n"
        "const hasOutboundMessage = (Array.isArray(norm.msgs) ? norm.msgs : []).some(m => m && m.is_reply === false); "
        "// strict: undefined/null/missing is NOT outbound\n"
        "const repliedToInvite = !norm.is_inmail && curRank < followUpRank && !hasOutboundMessage;\n"
        "const targetStage = repliedToInvite ? 'Replied to invite' : 'Replied';"
    )
    m7["parameters"]["jsCode"] = code.replace(old_line, f9_block)

    # ===== F11 — remove require('crypto') from Dedupe =====
    ded = get_node(by_name, "Dedupe")
    dcode = ded["parameters"]["jsCode"]
    crypto_seg = (
        "const crypto = require('crypto');\n"
        "const key = (body.correlation_id && body.correlation_id !== nil)\n"
        "  ? body.correlation_id\n"
        "  : crypto.createHash('sha256').update(`${body.event_type}|${body.lead?.profile_url}|${body.timestamp}`).digest('hex');"
    )
    if crypto_seg not in dcode:
        raise ValueError("F11: expected crypto fallback block not found in Dedupe")
    new_key = (
        "const key = (body.correlation_id && body.correlation_id !== nil)\n"
        "  ? body.correlation_id\n"
        "  : [body.event_type || '', body.lead?.profile_url || '', body.timestamp || '', body.conversation_id || ''].join('|');"
    )
    ded["parameters"]["jsCode"] = dcode.replace(crypto_seg, new_key)

    # ===== F12 — mrkdwn escaping on existing warn nodes (also fixes single-brace bug) =====
    get_node(by_name, "M5 Slack Warn")["parameters"]["text"] = branch_warn_text("M5 Person Get")
    get_node(by_name, "M6 Slack Warn")["parameters"]["text"] = branch_warn_text("M6 Build")
    # M7 Slack Warn becomes the UNKNOWN-PERSON-only terminal (F10): Normalize-only, no M7 Build ref.
    get_node(by_name, "M7 Slack Warn")["parameters"]["text"] = M7_SLACK_WARN_TEXT
    # Lead Resp Invalid text carries no user-originated string -> nothing to escape (left as-is).

    # ===== F10 — new nodes =====
    reply_context = {
        "parameters": {"mode": "runOnceForEachItem", "jsCode": REPLY_CONTEXT_CODE},
        "id": uid(),
        "name": "M7 Reply Context",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1180, 1720],
    }
    critical_slack = slack_node("M7 Critical Slack", "={{ $json.alert_text }}", [1420, 1720],
                                on_error="continueRegularOutput")
    no_lead_warn = slack_node("M7 No Lead Warn", M7_NO_LEAD_WARN_TEXT, [5264, 2560])
    for n in (reply_context, critical_slack, no_lead_warn):
        nodes.append(n)
        by_name[n["name"]] = n

    # Remove the moved tail alert (M8 Slack Text + M8 Slack).
    removed = {"M8 Slack Text", "M8 Slack"}
    w["nodes"] = [n for n in nodes if n["name"] not in removed]
    nodes = w["nodes"]
    by_name = {n["name"]: n for n in nodes}

    # ===== F10 — rewiring =====
    conns = w["connections"]
    # Front: Switch[3] -> M7 Reply Context -> M7 Critical Slack -> M7 IF Email Present
    conns["Switch"]["main"][3] = [edge("M7 Reply Context")]
    conns["M7 Reply Context"] = {"main": [[edge("M7 Critical Slack")]]}
    conns["M7 Critical Slack"] = {"main": [[edge("M7 IF Email Present")]]}

    # Tail: explicit terminals; no shared warn terminal
    conns["M8 IF Transition"] = {"main": [[edge("M8 IF Lead ID")], []]}      # false = terminal
    conns["M8 IF Lead ID"] = {"main": [[edge("M8 Task")], [edge("M7 No Lead Warn")]]}
    conns.pop("M8 Task", None)          # M8 Task is a branch end now
    conns.pop("M8 Slack Text", None)    # removed node
    conns.pop("M8 Slack", None)         # removed node

    # Separate warn terminals
    conns["M7 IF URL Found"] = {"main": [[edge("M7 PID From URL")], [edge("M7 Slack Warn")]]}      # unknown-person
    conns["M7 IF Lead ID"] = {"main": [[edge("M7 Lead Patch")], [edge("M7 No Lead Warn")]]}
    conns["M7 IF Reply Activity Lead"] = {"main": [[edge("M7 Reply Activity")], [edge("M7 No Lead Warn")]]}
    # M7 Slack Warn / M7 No Lead Warn are terminals (no outgoing edges).

    # Cleanup / invariants carried over from W1.0
    w.pop("pinData", None)
    w["active"] = False
    return w


# ---------------------------------------------------------------------------
# Validation (structural + F9-F12 semantic + F10.6 graph invariants)
# ---------------------------------------------------------------------------
def _reachable(conns: dict[str, Any], start: str) -> set[str]:
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        for branch in conns.get(cur, {}).get("main", []):
            for e in branch:
                if e["node"] not in seen:
                    seen.add(e["node"])
                    stack.append(e["node"])
    return seen


def _has_cycle(conns: dict[str, Any], names: set[str]) -> list[str]:
    color = {n: 0 for n in names}  # 0=white 1=grey 2=black
    bad: list[str] = []

    def dfs(u: str) -> None:
        color[u] = 1
        for branch in conns.get(u, {}).get("main", []):
            for e in branch:
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


def validate(w: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = w.get("nodes", [])
    names = [n["name"] for n in nodes]
    name_set = set(names)
    if len(names) != len(name_set):
        errors.append("Duplicate node names")
    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate node IDs")
    if w.get("active") is not False:
        errors.append("Workflow is not inactive")
    if "pinData" in w:
        errors.append("pinData present")
    by = {n["name"]: n for n in nodes}
    conns = w.get("connections", {})

    for src, c in conns.items():
        if src not in name_set:
            errors.append(f"Connection source missing: {src}")
        for branch in c.get("main", []):
            for e in branch:
                if e["node"] not in name_set:
                    errors.append(f"Connection target missing: {src} -> {e['node']}")

    for req in ("M7 Reply Context", "M7 Critical Slack", "M7 No Lead Warn"):
        if req not in by:
            errors.append(f"Missing new node: {req}")
    for gone in ("M8 Slack", "M8 Slack Text"):
        if gone in by:
            errors.append(f"Node should have been removed: {gone}")

    # F9
    m7 = by.get("M7 Build", {}).get("parameters", {}).get("jsCode", "")
    if "Replied to invite" not in m7 or "repliedToInvite" not in m7:
        errors.append("F9: M7 Build missing hybrid Replied-to-invite classifier")
    if "const targetStage = 'Replied';" in m7:
        errors.append("F9: hardcoded targetStage still present")

    # F11
    ded = by.get("Dedupe", {}).get("parameters", {}).get("jsCode", "")
    if "require(" in ded:
        errors.append("F11: Dedupe still calls require()")
    if "conversation_id" not in ded:
        errors.append("F11: Dedupe key does not include conversation_id")

    # F10 tail
    if "M8 Task" in conns:
        errors.append("F10: M8 Task should be a terminal (no outgoing edges)")
    m8t = by.get("M8 Task", {})
    if m8t.get("parameters", {}).get("method") != "POST" or m8t.get("retryOnFail") is not False:
        errors.append("F10: M8 Task must remain POST with retryOnFail=false")
    cs = by.get("M7 Critical Slack", {})
    if cs.get("onError") != "continueRegularOutput":
        errors.append("F10: M7 Critical Slack must be onError=continueRegularOutput")

    # F12 escaping present where user strings are built
    for nm in ("M7 Reply Context", "M5 Slack Warn", "M6 Slack Warn", "M7 Slack Warn"):
        blob = json.dumps(by.get(nm, {}).get("parameters", {}), ensure_ascii=False)
        if "escapeSlack" not in blob:
            errors.append(f"F12: escapeSlack missing in {nm}")

    # F12.1 — every Slack node text must be a real expression: if it contains {{ it MUST start with ={{.
    for n in nodes:
        if n.get("type") != "n8n-nodes-base.slack":
            continue
        txt = n.get("parameters", {}).get("text")
        if not isinstance(txt, str):
            errors.append(f"F12.1: Slack node {n['name']} has no text parameter")
            continue
        if "{{" in txt and not txt.startswith("={{"):
            errors.append(f"F12.1: Slack node {n['name']} text has {{{{ without leading '=' (would post literal)")
    cs_text = by.get("M7 Critical Slack", {}).get("parameters", {}).get("text", "")
    if not (cs_text.startswith("={{") and "alert_text" in cs_text):
        errors.append("F12.1: M7 Critical Slack text must be ={{ ... alert_text ... }}")

    # F10.6 graph invariants ---------------------------------------------------
    cyc = _has_cycle(conns, name_set)
    if cyc:
        errors.append(f"Graph has cycle(s): {cyc}")

    # unknown-person path (Switch[3] .. M7 Slack Warn) must not reference M7 Build
    warn_blob = json.dumps(by.get("M7 Slack Warn", {}).get("parameters", {}), ensure_ascii=False)
    if "M7 Build" in warn_blob:
        errors.append("F10.6: unknown-person terminal (M7 Slack Warn) references M7 Build")
    # M7 Slack Warn must be reachable from Switch[3] and be an unknown-person terminal
    reach_from_ctx = _reachable(conns, "M7 Reply Context")
    if "M7 Slack Warn" not in reach_from_ctx:
        errors.append("F10.6: M7 Slack Warn not reachable on the reply branch")
    if conns.get("M7 Slack Warn"):
        errors.append("F10.6: M7 Slack Warn must be a terminal (no outgoing)")

    # M7 Critical Slack reachable from Switch output 3 through Normalize-only deps
    sw3 = conns.get("Switch", {}).get("main", [[]] * 4)
    if not (len(sw3) > 3 and sw3[3] and sw3[3][0]["node"] == "M7 Reply Context"):
        errors.append("F10.6: Switch output 3 must enter M7 Reply Context")
    ctx_code = by.get("M7 Reply Context", {}).get("parameters", {}).get("jsCode", "")
    for forbidden in ("M7 Person Get", "M7 Lead Get", "M7 Build"):
        if f"$('{forbidden}')" in ctx_code or f'$("{forbidden}")' in ctx_code:
            errors.append(f"F10.6: M7 Reply Context must not reference {forbidden}")
    if "M7 Critical Slack" not in _reachable(conns, "M7 Reply Context"):
        errors.append("F10.6: M7 Critical Slack not reachable from M7 Reply Context")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--api-payload", type=Path, default=None)
    args = ap.parse_args()

    wf = json.loads(args.input.read_text(encoding="utf-8"))
    patched = apply_patch(wf)
    errors = validate(patched)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    # Write LF explicitly so output is byte-identical across OSes (deterministic rebuild).
    args.output.write_bytes((json.dumps(patched, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    if args.api_payload:
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        args.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"Patched workflow written to {args.output}")
    print(f"Nodes: {len(wf['nodes'])} -> {len(patched['nodes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
