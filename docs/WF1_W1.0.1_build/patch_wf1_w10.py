#!/usr/bin/env python3
"""Apply the W1.0 fix-pack to an exported WF-1 HeyReach Receiver JSON.

This script patches nodes by name, preserves the workflow as inactive, removes pinData,
and removes stale connection records. It does not call n8n or external APIs.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import uuid
import re
from pathlib import Path
from typing import Any


_UID_COUNTER = 0


def uid() -> str:
    """Return deterministic UUIDs so the same baseline produces the same patch."""
    global _UID_COUNTER
    _UID_COUNTER += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wf1-w10:{_UID_COUNTER}"))


def bool_if_node(name: str, left_value: str, position: list[int]) -> dict[str, Any]:
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 1,
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": left_value,
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                            "singleValue": True,
                        },
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": position,
    }


def email_if_node(name: str, position: list[int]) -> dict[str, Any]:
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "loose",
                },
                "combinator": "and",
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ ($('Normalize').item.json.lead.email_address || '').trim() }}",
                        "rightValue": "",
                        "operator": {
                            "type": "string",
                            "operation": "notEmpty",
                            "singleValue": True,
                        },
                    }
                ],
            },
            "options": {},
        },
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": position,
    }


def edge(node: str, index: int = 0) -> dict[str, Any]:
    return {"node": node, "type": "main", "index": index}


def set_connections(workflow: dict[str, Any], source: str, outputs: list[list[str]]) -> None:
    workflow.setdefault("connections", {})[source] = {
        "main": [[edge(target) for target in targets] for targets in outputs]
    }


def get_node(nodes_by_name: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    try:
        return nodes_by_name[name]
    except KeyError as exc:
        raise KeyError(f"Required node not found: {name}") from exc


SELECT_LEAD_FN = """function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}"""


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    nodes: list[dict[str, Any]] = w["nodes"]
    by_name = {n["name"]: n for n in nodes}
    patch_only_names = {
        "Select Existing Lead", "Lead From Create", "Sent IF Lead ID",
        "M5 IF Lead ID", "M6 IF Lead ID", "M7 IF Lead ID",
        "M7 IF Reply Activity Lead", "M8 IF Lead ID",
        "IF Email Present", "M5 IF Email Present", "M6 IF Email Present",
        "M7 IF Email Present", "M7 Reply Activity",
    }
    already = sorted(patch_only_names.intersection(by_name))
    if already:
        raise ValueError(f"Input already appears patched; refusing to add duplicate nodes: {already}")

    # F1 — Normalize contract in M7 Build; also expose targetStage for label logic.
    m7_build = get_node(by_name, "M7 Build")
    m7_build["parameters"]["jsCode"] = f"""// ===== M7 Build (every_message_reply_received) =====
const CFG = $('CONFIG').item.json;
const norm = $('Normalize').item.json;
const person = $('M7 Person Get').item.json.data || {{}};
const leadResp = $('M7 Lead Get').item.json;

const fields = CFG.fields;
const stageKey = fields.stage;
const convKey = fields.conversation;
const rank = CFG.stageRank || {{}};

{SELECT_LEAD_FN}
const selectedLead = selectLead(leadResp && leadResp.data);

// --- classify reply: first transition or a subsequent reply ---
const curStageVal = (person.custom_fields && person.custom_fields[stageKey]) || null;
const curRank = curStageVal ? (rank[curStageVal] || 0) : 0;
const REPLIED_RANK = 4;
const targetStage = 'Replied';
const targetRank = rank[targetStage] || REPLIED_RANK;
const isTransition = curRank < targetRank;

// --- render reply_text from Normalize.msgs (last reply), with empty-text placeholders ---
const msgs = Array.isArray(norm.msgs) ? norm.msgs : [];
function render(m) {{
  if (!m) return '[empty message]';
  const t = (m.message == null ? '' : String(m.message)).trim();
  if (t) return t;
  const mt = String(m.message_type || '').toLowerCase();
  if (mt.includes('attach')) return '[attachment]';
  if (mt.includes('voice')) return '[voice note]';
  return '[empty message]';
}}
const replies = msgs.filter(m => m && m.is_reply === true);
const lastReply = replies.length ? replies[replies.length - 1] : (msgs.length ? msgs[msgs.length - 1] : null);
const reply_text = render(lastReply);
const is_inmail = !!norm.is_inmail;

// --- conversation: same canonical format as M6, write only if currently empty ---
const senderId = norm.sender?.id ?? null;
const conversationValue = (senderId && norm.conv) ? `${{senderId}}:${{norm.conv}}` : (norm.conv || '');
const curConv = (person.custom_fields && person.custom_fields[convKey]) || '';
const writeConv = Boolean(!curConv && conversationValue);

// --- build person PATCH custom_fields dynamically ---
const custom_fields = {{}};
let stageChanged = false;
if (isTransition && targetRank > curRank) {{
  custom_fields[stageKey] = targetStage;
  stageChanged = true;
}}
if (writeConv) custom_fields[convKey] = conversationValue;
const __doPatch = Object.keys(custom_fields).length > 0;
const patchBody = {{ custom_fields }};

return {{
  json: {{
    person_id: person.id || null,
    lead_id: selectedLead ? selectedLead.id : null,
    owner_id: CFG.melisa_user_id,
    custom_fields,
    patchBody,
    __doPatch,
    isTransition,
    stageChanged,
    targetStage,
    reply_text,
    is_inmail,
    conversation_id: conversationValue,
    activityType: CFG.activity_type_msg,
    _guard: {{ curStageVal, curRank, targetRank, writeConv }}
  }}
}};"""

    # F2 — Replace Lead Create Gate IF with a 3-output Switch.
    lead_gate = get_node(by_name, "Lead Create Gate")
    lead_gate["type"] = "n8n-nodes-base.switch"
    lead_gate["typeVersion"] = 3
    lead_gate["parameters"] = {
        "rules": {
            "values": [
                {
                    "conditions": {
                        "options": {"caseSensitive": True, "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": uid(),
                                "leftValue": "={{ $json.success === true && Array.isArray($json.data) && $json.data.length === 0 }}",
                                "rightValue": True,
                                "operator": {
                                    "type": "boolean",
                                    "operation": "true",
                                    "singleValue": True,
                                },
                            }
                        ],
                        "combinator": "and",
                    },
                    "renameOutput": True,
                    "outputKey": "create",
                },
                {
                    "conditions": {
                        "options": {"caseSensitive": True, "typeValidation": "loose"},
                        "conditions": [
                            {
                                "id": uid(),
                                "leftValue": "={{ $json.success === true && Array.isArray($json.data) && $json.data.length > 0 }}",
                                "rightValue": True,
                                "operator": {
                                    "type": "boolean",
                                    "operation": "true",
                                    "singleValue": True,
                                },
                            }
                        ],
                        "combinator": "and",
                    },
                    "renameOutput": True,
                    "outputKey": "existing",
                },
            ]
        },
        "options": {"fallbackOutput": "extra", "renameFallbackOutput": "invalid"},
    }

    select_existing = {
        "parameters": {
            "mode": "runOnceForEachItem",
            "jsCode": f"""// F2/F4: choose the newest active lead for the resolved person.
{SELECT_LEAD_FN}
const lead = selectLead($json.data);
return {{
  json: {{
    person_id: $('PID Resolved').item.json.person_id,
    lead_id: lead ? lead.id : null,
    __invalid: !lead,
    reason: lead ? null : 'no active lead in successful non-empty response'
  }}
}};""",
        },
        "id": uid(),
        "name": "Select Existing Lead",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [5152, 32],
    }
    nodes.append(select_existing)
    by_name[select_existing["name"]] = select_existing

    lead_from_create = {
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": uid(),
                        "name": "lead_id",
                        "type": "string",
                        "value": "={{ $json.data?.id ?? null }}",
                    }
                ]
            },
            "includeOtherFields": True,
            "options": {},
        },
        "id": uid(),
        "name": "Lead From Create",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [5376, 96],
    }
    nodes.append(lead_from_create)
    by_name[lead_from_create["name"]] = lead_from_create

    create_activity = get_node(by_name, "Create Activity")
    create_activity["parameters"]["jsonBody"] = """={
  \"subject\": {{ JSON.stringify('LinkedIn invite sent — ' + ($('Normalize').item.json.campaign.name || '')) }},
  \"type\": {{ JSON.stringify($('CONFIG').item.json.activity_type_msg) }},
  \"done\": true,
  \"participants\": [ { \"person_id\": {{ $('PID Resolved').item.json.person_id }}, \"primary\": true } ],
  \"lead_id\": {{ JSON.stringify($json.lead_id) }},
  \"owner_id\": {{ $('CONFIG').item.json.melisa_user_id }},
  \"note\": {{ JSON.stringify($('Normalize').item.json.invite || '') }}
}"""

    # F3/F4 — effective-rank labels + one identical selector everywhere.
    m5_labels = get_node(by_name, "M5 Labels Compute")
    m5_labels["parameters"]["jsCode"] = f"""// M5: effective-rank label read-modify-write.
const cfg = $('CONFIG').item.json;
const person = $('M5 Person Get').item.json.data || {{}};
const pcf = person.custom_fields || {{}};
const currentStage = pcf[cfg.fields.stage] || null;
const currentRank = cfg.stageRank[currentStage] || 0;
const incomingRank = cfg.stageRank['Accepted'] || 2;
const effectiveRank = Math.max(currentRank, incomingRank);
const targetLabel = effectiveRank >= 4 ? cfg.labels.responded
                  : effectiveRank >= 2 ? cfg.labels.connected
                  : cfg.labels.cold;

{SELECT_LEAD_FN}
const lead = selectLead($json.data);
if (!lead) {{
  return {{ json: {{ __invalid: true, reason: 'no lead', person_id: person.id || null, lead_id: null }} }};
}}
const existing = Array.isArray(lead.label_ids) ? lead.label_ids : [];
const label_ids = Array.from(new Set(existing.filter(id => !cfg.ourLabels.includes(id)).concat([targetLabel])));
return {{
  json: {{
    person_id: person.id || null,
    lead_id: lead.id,
    label_ids_before: existing,
    label_ids,
    currentStage,
    currentRank,
    incomingRank,
    effectiveRank,
    targetLabel
  }}
}};"""

    m6_build = get_node(by_name, "M6 Build")
    m6_build["parameters"]["jsCode"] = f"""// M6 Build: compute sent text, selected lead and dynamic Person PATCH body.
const cfg = $('CONFIG').item.json;
const f = cfg.fields;
const ranks = cfg.stageRank;
const nz = $('Normalize').item.json;
const person = $('M6 Person Get').item.json.data || {{}};
const pcf = person.custom_fields || {{}};

{SELECT_LEAD_FN}
const lead = selectLead($('M6 Lead Get').item.json.data);
const lead_id = lead ? lead.id : null;
const person_id = person.id || null;

// --- sent text: last Normalize.msgs entry with is_reply === false ---
const msgs = Array.isArray(nz.msgs) ? nz.msgs : [];
let sentEntry = null;
for (const m of msgs) if (m && m.is_reply === false) sentEntry = m;
let sentText;
if (!sentEntry) {{
  sentText = '[empty message]';
}} else {{
  const txt = (sentEntry.message == null ? '' : String(sentEntry.message)).trim();
  if (txt) sentText = txt;
  else {{
    const mt = String(sentEntry.message_type || '').toLowerCase();
    if (mt.includes('attach')) sentText = '[attachment]';
    else if (mt.includes('voice')) sentText = '[voice note]';
    else sentText = '[empty message]';
  }}
}}

// --- forward-only stage ---
const NEW_STAGE = 'First follow-up sent';
const newRank = ranks[NEW_STAGE];
const curStage = pcf[f.stage] != null ? pcf[f.stage] : null;
const curRank = curStage && ranks[curStage] != null ? ranks[curStage] : 0;
const writeStage = curRank < newRank;

// --- conversation: same canonical sender:conversation format, only if empty ---
const conv = nz.conv != null ? nz.conv : null;
const senderId = nz.sender && nz.sender.id != null ? nz.sender.id : null;
const curConv = pcf[f.conversation] != null ? pcf[f.conversation] : null;
const convEmpty = curConv === null || curConv === '';
const convValue = (senderId != null && conv != null) ? (senderId + ':' + conv) : null;
const writeConv = convEmpty && convValue != null;

const cf = {{}};
if (writeStage) cf[f.stage] = NEW_STAGE;
if (writeConv) cf[f.conversation] = convValue;
const doPatch = Object.keys(cf).length > 0;
const patchBody = doPatch ? {{ custom_fields: cf }} : null;
const campaignName = nz.campaign && nz.campaign.name ? nz.campaign.name : '';
const activitySubject = 'LinkedIn message sent — ' + campaignName;
const activityBody = {{
  subject: activitySubject,
  type: cfg.activity_type_msg,
  done: true,
  participants: [{{ person_id, primary: true }}],
  lead_id,
  owner_id: cfg.melisa_user_id,
  note: sentText
}};

return {{
  activityBody,
  person_id,
  lead_id,
  sentText,
  activitySubject,
  activityType: cfg.activity_type_msg,
  owner_id: cfg.melisa_user_id,
  __doPatch: doPatch,
  patchBody,
  _guard: {{ curStage, curRank, newRank, writeStage, curConv, convEmpty, convValue, writeConv }}
}};"""

    m7_labels = get_node(by_name, "M7 Labels Compute")
    m7_labels["parameters"]["jsCode"] = f"""// M7: effective-rank label read-modify-write.
const cfg = $('CONFIG').item.json;
const person = $('M7 Person Get').item.json.data || {{}};
const pcf = person.custom_fields || {{}};
const currentStage = pcf[cfg.fields.stage] || null;
const currentRank = cfg.stageRank[currentStage] || 0;
const incomingStage = $('M7 Build').item.json.targetStage || 'Replied';
const incomingRank = cfg.stageRank[incomingStage] || 4;
const effectiveRank = Math.max(currentRank, incomingRank);
const targetLabel = effectiveRank >= 4 ? cfg.labels.responded
                  : effectiveRank >= 2 ? cfg.labels.connected
                  : cfg.labels.cold;

{SELECT_LEAD_FN}
const lead = selectLead($('M7 Lead Get').item.json.data);
if (!lead) {{
  return {{ json: {{ __invalid: true, reason: 'no lead', person_id: person.id || null, lead_id: null }} }};
}}
const existing = Array.isArray(lead.label_ids) ? lead.label_ids.slice() : [];
const label_ids = Array.from(new Set(existing.filter(id => !cfg.ourLabels.includes(id)).concat([targetLabel])));
return {{
  json: {{
    __invalid: false,
    person_id: person.id || null,
    lead_id: lead.id,
    label_ids,
    label_ids_before: existing,
    currentStage,
    currentRank,
    incomingStage,
    incomingRank,
    effectiveRank,
    targetLabel
  }}
}};"""

    # Acceptance-consistency correction: late accepted must fill connected_at without downgrading stage.
    m5_if_rank = get_node(by_name, "M5 IF Rank Accepted")
    m5_cond = m5_if_rank["parameters"]["conditions"]["conditions"][0]
    m5_cond["leftValue"] = """={{ (() => {
  const cfg = $('CONFIG').item.json;
  const f = cfg.fields;
  const n = $('Normalize').item.json;
  const person = $('M5 Person Get').item.json.data || {};
  const cf = person.custom_fields || {};
  const curStage = cf[f.stage] || null;
  const curRank = cfg.stageRank[curStage] || 0;
  const acceptedRank = cfg.stageRank['Accepted'] || 2;
  const campaignName = n.campaign && n.campaign.name ? n.campaign.name : '';
  return curRank < acceptedRank || !cf[f.connected_at] || (!cf[f.campaign] && !!campaignName);
})() }}"""
    m5_cond["rightValue"] = True
    m5_cond["operator"] = {"type": "boolean", "operation": "true", "singleValue": True}
    m5_patch = get_node(by_name, "M5 Person Patch Accepted")
    m5_patch["parameters"]["jsonBody"] = """={{ (() => {
  const cfg = $('CONFIG').item.json;
  const n = $('Normalize').item.json;
  const f = cfg.fields;
  const person = $('M5 Person Get').item.json.data || {};
  const current = person.custom_fields || {};
  const curStage = current[f.stage] || null;
  const curRank = cfg.stageRank[curStage] || 0;
  const acceptedRank = cfg.stageRank['Accepted'] || 2;
  const custom_fields = {};
  if (curRank < acceptedRank) custom_fields[f.stage] = 'Accepted';
  if (!current[f.connected_at] && n.ts) {
    const d = new Date(n.ts);
    if (!Number.isNaN(d.getTime())) custom_fields[f.connected_at] = d.toISOString().slice(0, 10);
  }
  const campaignName = n.campaign && n.campaign.name ? n.campaign.name : '';
  if (!current[f.campaign] && campaignName) custom_fields[f.campaign] = campaignName;
  return JSON.stringify({ custom_fields });
})() }}"""

    # F5 — lead-id gates before writes.
    new_nodes = [
        bool_if_node("Sent IF Lead ID", "={{ !!$json.lead_id }}", [5488, 96]),
        bool_if_node("M5 IF Lead ID", "={{ !!$json.lead_id }}", [4000, 768]),
        bool_if_node("M6 IF Lead ID", "={{ !!$json.lead_id }}", [3888, 1296]),
        bool_if_node("M7 IF Lead ID", "={{ !!$json.lead_id }}", [3760, 1840]),
        bool_if_node("M7 IF Reply Activity Lead", "={{ !!$('M7 Build').item.json.lead_id }}", [4048, 1840]),
        bool_if_node("M8 IF Lead ID", "={{ !!$('M7 Build').item.json.lead_id }}", [4304, 1760]),
    ]
    for n in new_nodes:
        nodes.append(n)
        by_name[n["name"]] = n

    # F6 — email presence guards in all four resolvers.
    email_nodes = [
        email_if_node("IF Email Present", [2528, 208]),
        email_if_node("M5 IF Email Present", [1328, 912]),
        email_if_node("M6 IF Email Present", [1328, 1424]),
        email_if_node("M7 IF Email Present", [1328, 1984]),
    ]
    for n in email_nodes:
        nodes.append(n)
        by_name[n["name"]] = n

    person_create = get_node(by_name, "Person Create")
    person_create["parameters"]["jsonBody"] = """={{ (() => {
  const n = $('Normalize').item.json;
  const f = $('CONFIG').item.json.fields;
  const org = (() => {
    try { return $('Org From Search').item.json.org_id; } catch (e) {}
    try { return $('Org From Create').item.json.org_id; } catch (e) {}
    return null;
  })();
  const cf = {};
  cf[f.stage] = 'Invited';
  const mid = +n.lead.id;
  if (n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid)) cf[f.member_id] = mid;
  cf[f.public_id] = n.lead.slug;
  cf[f.li_url] = n.lead.url;
  cf[f.company] = n.lead.company_name;
  cf[f.position] = n.lead.position;
  cf[f.campaign] = n.campaign.name;
  cf[f.summary] = n.lead.summary;
  const body = {
    name: n.lead.full_name,
    owner_id: $('CONFIG').item.json.melisa_user_id,
    custom_fields: cf
  };
  if (n.lead.email_address) {
    body.emails = [{ value: n.lead.email_address, primary: true, label: 'work' }];
  }
  if (org != null) body.org_id = org;
  return JSON.stringify(body);
})() }}"""

    # F7 — never blindly retry creating POST requests.
    post_create_nodes = [
        "Org Create",
        "Person Create",
        "Create Lead",
        "Create Activity",
        "M6 Activity",
        "M8 Task",
    ]
    for name in post_create_nodes:
        get_node(by_name, name)["retryOnFail"] = False

    # F8 — completed reply activity on every reply.
    reply_activity = {
        "parameters": {
            "method": "POST",
            "url": "https://api.pipedrive.com/api/v2/activities",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "pipedriveApi",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ subject: 'LinkedIn reply — ' + (($('Normalize').item.json.campaign || {}).name || ''), type: $('CONFIG').item.json.activity_type_msg, done: true, participants: [{ person_id: $('M7 Build').item.json.person_id, primary: true }], lead_id: $('M7 Build').item.json.lead_id, owner_id: $('CONFIG').item.json.melisa_user_id, note: $('M7 Build').item.json.reply_text }) }}",
            "options": {},
        },
        "id": uid(),
        "name": "M7 Reply Activity",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [4304, 1840],
        "retryOnFail": False,
        "maxTries": 2,
        "waitBetweenTries": 2000,
        "credentials": copy.deepcopy(get_node(by_name, "M8 Task")["credentials"]),
    }
    nodes.append(reply_activity)
    by_name[reply_activity["name"]] = reply_activity

    # Dynamic warning text: distinguish unknown person from resolved person with no lead.
    for branch, fallback_node in [
        ("M5", "M5 Person Get"),
        ("M6", "M6 Build"),
        ("M7", "M7 Build"),
    ]:
        warn = get_node(by_name, f"{branch} Slack Warn")
        warn["parameters"]["text"] = f"""={{ (() => {{
  const n = $('Normalize').item.json;
  let personId = $json.person_id || null;
  if (!personId) {{ try {{ personId = $('{fallback_node}').item.json.person_id || $('{fallback_node}').item.json.data?.id || null; }} catch (e) {{}} }}
  if (personId) return `⚠️ WF-1: ${{n.event}} — person resolved but no lead found for person ${{personId}}; write skipped`;
  const profile = n.lead?.url || n.lead?.profile_url || '';
  return `⚠️ WF-1: ${{n.event}} for unknown person ${{profile}} — skipped`;
}})() }}"""

    # Rewire F2.
    set_connections(w, "Lead Create Gate", [["Create Lead"], ["Select Existing Lead"], ["Lead Resp Invalid"]])
    set_connections(w, "Create Lead", [["Lead From Create"]])
    set_connections(w, "Lead From Create", [["Sent IF Lead ID"]])
    set_connections(w, "Select Existing Lead", [["Sent IF Lead ID"]])
    set_connections(w, "Sent IF Lead ID", [["Create Activity"], ["Lead Resp Invalid"]])

    # Rewire F5/F8.
    set_connections(w, "M5 Labels Compute", [["M5 IF Lead ID"]])
    set_connections(w, "M5 IF Lead ID", [["M5 Lead Patch"], ["M5 Slack Warn"]])
    set_connections(w, "M6 Build", [["M6 IF Lead ID"]])
    set_connections(w, "M6 IF Lead ID", [["M6 Activity"], ["M6 Slack Warn"]])
    set_connections(w, "M7 Labels Compute", [["M7 IF Lead ID"]])
    set_connections(w, "M7 IF Lead ID", [["M7 Lead Patch"], ["M7 Slack Warn"]])
    set_connections(w, "M7 Lead Patch", [["M7 IF Reply Activity Lead"]])
    set_connections(w, "M7 IF Reply Activity Lead", [["M7 Reply Activity"], ["M7 Slack Warn"]])
    set_connections(w, "M7 Reply Activity", [["M8 IF Transition"]])
    set_connections(w, "M8 IF Transition", [["M8 IF Lead ID"], ["M8 Slack Text"]])
    set_connections(w, "M8 IF Lead ID", [["M8 Task"], ["M7 Slack Warn"]])

    # Rewire F6 email guards.
    for source in ["Org From Search", "Org From Create", "Org None"]:
        set_connections(w, source, [["IF Email Present"]])
    set_connections(w, "IF Email Present", [["Person Search Email"], ["Person Search URL"]])
    set_connections(w, "M5 IF Email Present", [["M5 Person Search Email"], ["M5 Person Search URL"]])
    set_connections(w, "M6 IF Email Present", [["M6 Person Search Email"], ["M6 Person Search URL"]])
    set_connections(w, "M7 IF Email Present", [["M7 Person Search Email"], ["M7 Person Search URL"]])

    # Switch outputs now enter each branch's email guard.
    switch_main = w["connections"]["Switch"]["main"]
    switch_main[1] = [edge("M5 IF Email Present")]
    switch_main[2] = [edge("M6 IF Email Present")]
    switch_main[3] = [edge("M7 IF Email Present")]

    # Cleanup required by W1.0.
    w.pop("pinData", None)
    w.get("connections", {}).pop("IF Lead Found", None)
    w.get("connections", {}).pop("Lead Resp Guard", None)
    w["active"] = False

    return w


def validate(workflow: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = workflow.get("nodes", [])
    names = [n.get("name") for n in nodes]
    name_set = set(names)
    if len(names) != len(name_set):
        errors.append("Duplicate node names found")
    for source, conn in workflow.get("connections", {}).items():
        if source not in name_set:
            errors.append(f"Connection source does not exist: {source}")
        for output in conn.get("main", []):
            for item in output:
                if item.get("node") not in name_set:
                    errors.append(f"Connection target does not exist: {source} -> {item.get('node')}")
    if workflow.get("active") is not False:
        errors.append("Workflow is not inactive")
    if "pinData" in workflow:
        errors.append("pinData was not removed")

    by_name = {n["name"]: n for n in nodes}
    for required in [
        "Select Existing Lead",
        "Lead From Create",
        "Sent IF Lead ID",
        "M5 IF Lead ID",
        "M6 IF Lead ID",
        "M7 IF Lead ID",
        "M7 IF Reply Activity Lead",
        "M8 IF Lead ID",
        "IF Email Present",
        "M5 IF Email Present",
        "M6 IF Email Present",
        "M7 IF Email Present",
        "M7 Reply Activity",
    ]:
        if required not in by_name:
            errors.append(f"Required patched node missing: {required}")

    for name in ["Org Create", "Person Create", "Create Lead", "Create Activity", "M6 Activity", "M8 Task", "M7 Reply Activity"]:
        if by_name.get(name, {}).get("retryOnFail") is not False:
            errors.append(f"POST retry still enabled: {name}")

    m7_code = by_name.get("M7 Build", {}).get("parameters", {}).get("jsCode", "")
    if "norm.recent_messages" in m7_code or "norm.conversation_id" in m7_code:
        errors.append("M7 Build still references old Normalize keys")
    if "norm.msgs" not in m7_code or "norm.conv" not in m7_code:
        errors.append("M7 Build does not use Normalize msgs/conv")

    stale_sources = {"IF Lead Found", "Lead Resp Guard"}.intersection(workflow.get("connections", {}))
    if stale_sources:
        errors.append(f"Stale connection sources remain: {sorted(stale_sources)}")

    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate node IDs found")

    # Every node reference used by $('Node Name') must resolve. Ignore prose-only sticky notes.
    ref_re = re.compile(r"\$\(['\"]([^'\"]+)['\"]\)")
    for node in nodes:
        if node.get("type") == "n8n-nodes-base.stickyNote":
            continue
        text = json.dumps(node.get("parameters", {}), ensure_ascii=False)
        for ref in ref_re.findall(text):
            if ref not in name_set:
                errors.append(f"Expression in {node.get('name')} references missing node: {ref}")

    select_fn = """function selectLead(leads) {
  return (Array.isArray(leads) ? leads : [])
    .filter(l => !l.is_archived)
    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;
}"""
    for name in ["M5 Labels Compute", "M6 Build", "M7 Build", "M7 Labels Compute", "Select Existing Lead"]:
        code = by_name.get(name, {}).get("parameters", {}).get("jsCode", "")
        if select_fn not in code:
            errors.append(f"Shared selectLead is missing or differs in {name}")

    m5_condition = by_name.get("M5 IF Rank Accepted", {}).get("parameters", {}).get("conditions", {}).get("conditions", [{}])[0]
    if m5_condition.get("operator") != {"type": "boolean", "operation": "true", "singleValue": True}:
        errors.append("M5 IF Rank Accepted must use a boolean true operator")

    # Ensure email guards are the only direct entry points to email searches.
    expected_email_edges = {
        "IF Email Present": "Person Search Email",
        "M5 IF Email Present": "M5 Person Search Email",
        "M6 IF Email Present": "M6 Person Search Email",
        "M7 IF Email Present": "M7 Person Search Email",
    }
    inbound: dict[str, list[str]] = {name: [] for name in name_set}
    for source, conn in workflow.get("connections", {}).items():
        for output in conn.get("main", []):
            for item in output:
                inbound[item["node"]].append(source)
    for guard, search in expected_email_edges.items():
        if inbound.get(search) != [guard]:
            errors.append(f"Email search {search} has unexpected inbound sources: {inbound.get(search)}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--api-payload", type=Path, default=None)
    args = parser.parse_args()

    workflow = json.loads(args.input.read_text(encoding="utf-8"))
    patched = apply_patch(workflow)
    errors = validate(patched)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    args.output.write_text(json.dumps(patched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.api_payload:
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        args.api_payload.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Patched workflow written to {args.output}")
    print(f"Nodes: {len(workflow['nodes'])} -> {len(patched['nodes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
