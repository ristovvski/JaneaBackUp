# -*- coding: utf-8 -*-
"""WF-2: R-A (archived = ignore), R-B (non-campaign = no post), and the channel map.

Same reasoning as WF-1. The archived-blind sites here are Lead Select / Lead Resolve /
B Lead Select / U Lead Select, all reading /v1/leads?limit=100 which cannot return archived
leads. As in WF-1 the damage is concentrated in the CREATE paths - an archived lead reads as
"no lead", so the gate creates a duplicate - and in the person-scoped posts.
"""
import json, sys

SRC, DST, RULES = sys.argv[1], sys.argv[2], sys.argv[3]
rules_js = open(RULES, encoding="utf-8").read().split("if (typeof module !==")[0].rstrip()

w = json.load(open(SRC, encoding="utf-8"))
by = {n["name"]: n for n in w["nodes"]}
conns = w["connections"]
PD_CRED = {"pipedriveApi": {"id": "HnyULgvDdYp0lIkB", "name": "Pipedrive account"}}
ALERTS = "C0BTUHSSM3K"

# ------------------------------------------------------------------ CONFIG
cfg_node = by["CONFIG"]
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
cfg["slack_channel_alerts"] = ALERTS
cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)

# ------------------------------------------------------------------ probe + decide
probe = {
    "parameters": {
        "method": "GET",
        "url": "={{ $('CONFIG').item.json.pd_api }}/v1/leads/search",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "term", "value":
                "={{ (($('Normalize').item.json.lead || {}).full_name)"
                " || [ ($('Normalize').item.json.lead || {}).first,"
                " ($('Normalize').item.json.lead || {}).last ].filter(Boolean).join(' ')"
                " || (($('Normalize').item.json.lead || {}).email) || 'zzz-no-name-zzz' }}"},
            {"name": "limit", "value": "100"}]},
        "authentication": "predefinedCredentialType", "nodeCredentialType": "pipedriveApi",
        "options": {}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [980, -420],
    "id": "wf2-ar-probe", "name": "AR Probe",
    "onError": "continueRegularOutput", "credentials": PD_CRED}

decide = {"parameters": {"jsCode": rules_js + r"""

// ---- AR Decide (WF-2). Between IF Duplicate and Switch Event. Spreads its input verbatim so
// `Switch Event` still reads $json.event and nothing downstream changes shape.
const n = $('Normalize').item.json;
const cfg = $('CONFIG').item.json;
const camp = { id: n.campaign_id || null, name: n.campaign_name || null };
const probe = arParseProbe($input.first().json, camp.name, camp.id,
                           (cfg.fields || {}).lead_campaign);
const arch = probe.rows.filter(function (r) { return r.is_archived; });
return $input.all().map(function () {
  return { json: Object.assign({}, $('IF Duplicate').first().json, { __ar: {
    probe_ok: probe.ok, probe_reason: probe.reason, saturated: probe.saturated, rows: probe.rows,
    archived_person_ids: arch.map(function (r) { return String(r.person_id); }),
    archived_lead_ids: arch.map(function (r) { return r.id; }),
    any_archived: arch.length > 0,
    is_campaign: arIsCampaign(camp),
    campaign_id: camp.id,
  } }) };
});
""", "mode": "runOnceForAllItems"},
    "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1180, -420],
    "id": "wf2-ar-decide", "name": "AR Decide"}

w["nodes"] += [probe, decide]
dup = conns["IF Duplicate"]["main"]
assert [t["node"] for t in dup[1]] == ["Switch Event"], \
    "unexpected IF Duplicate[1]: %r" % [t["node"] for t in dup[1]]
dup[1] = [{"node": "AR Probe", "type": "main", "index": 0}]
conns["AR Probe"] = {"main": [[{"node": "AR Decide", "type": "main", "index": 0}]]}
conns["AR Decide"] = {"main": [[{"node": "Switch Event", "type": "main", "index": 0}]]}

# ------------------------------------------------------------------ create gates
NO_ARCH = ("={{ ($('AR Decide').first().json.__ar.archived_person_ids || [])"
           ".indexOf(String(%s)) === -1 }}")
for gate_name, person_expr, cid in (
        ("Gate Lead Create", "$('Person Id Final').first().json.__person_id", "wf2-ra-sent"),
        ("R Create Gate", "$('Merge Reply Ctx').first().json.__person_id", "wf2-ra-reply")):
    g = by[gate_name]
    conds = g["parameters"]["conditions"]["conditions"]
    assert len(conds) == 1, "%s already has %d conditions" % (gate_name, len(conds))
    conds.append({"id": cid, "leftValue": NO_ARCH % person_expr, "rightValue": True,
                  "operator": {"type": "boolean", "operation": "true", "singleValue": True}})
    g["parameters"]["conditions"]["combinator"] = "and"
    print("  create gate hardened: %s" % gate_name)

# ------------------------------------------------------------------ person-scoped post gates
PERSON_POSTS = ["Reply Alert", "Nurture Alert", "Ops Warn No Lead", "Ops Warn Deleted Person"]
gate_js = rules_js + r"""

// ---- R-A + R-B post gate. Person-scoped posts only; system alarms are never gated.
const ar = (function () {
  try { return ($('AR Decide').first().json.__ar) || null; } catch (e) { return null; }
})();
// FAIL OPEN on an unreadable probe: a real reply must never be silenced by a failed lookup.
const archivedBlocked = !!(ar && ar.probe_ok === true && ar.any_archived === true);
const noCampaign = !!(ar && ar.is_campaign === false);
const post = !(archivedBlocked || noCampaign);
return $input.all().map(function (i) {
  return { json: Object.assign({}, i.json, {
    __ar_post: post,
    __ar_post_reason: archivedBlocked ? 'archived_lead_ignored'
                    : noCampaign ? 'non_campaign_person' : 'ok' }) };
});
"""
newnodes = []
for idx, slack_name in enumerate(PERSON_POSTS):
    sn = by[slack_name]
    gx, gy = sn["position"][0] - 200, sn["position"][1] + 40
    ctx = {"parameters": {"jsCode": gate_js, "mode": "runOnceForAllItems"},
           "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [gx - 200, gy],
           "id": "wf2-arctx-%d" % idx, "name": "AR Ctx %s" % slack_name}
    # 3-WAY, not 2: the outcomes are genuinely different.
    #   post                -> the Slack node (which continues to its own downstream)
    #   non-campaign        -> SKIP the post, but CONTINUE downstream. The 2026-08-28 ruling
    #                          stands: a manual thread still gets its silent CRM activity write.
    #   archived (fallback) -> STOP. Rule R-A is zero writes AND zero posts.
    down = [dict(x) for x in (conns.get(slack_name, {}).get("main", [[]])[0] or [])]
    iff = {"parameters": {"rules": {"values": [
               {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict",
                                           "leftValue": "", "version": 1},
                               "combinator": "and",
                               "conditions": [{"id": "wf2-post-%d" % idx,
                                               "leftValue": "={{ $json.__ar_post === true }}",
                                               "rightValue": True,
                                               "operator": {"type": "boolean",
                                                            "operation": "true",
                                                            "singleValue": True}}]},
                "renameOutput": True, "outputKey": "post"},
               {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict",
                                           "leftValue": "", "version": 1},
                               "combinator": "and",
                               "conditions": [{"id": "wf2-nocamp-%d" % idx,
                                               "leftValue": "={{ $json.__ar_post_reason }}",
                                               "rightValue": "non_campaign_person",
                                               "operator": {"type": "string",
                                                            "operation": "equals"}}]},
                "renameOutput": True, "outputKey": "silent_continue"}]},
           "options": {"fallbackOutput": "extra", "renameFallbackOutput": "archived_stop"}},
           "type": "n8n-nodes-base.switch", "typeVersion": 3,
           "position": [gx, gy], "id": "wf2-arsw-%d" % idx,
           "name": "AR Post? %s" % slack_name}
    newnodes += [ctx, iff]
    moved = []
    for src, v in conns.items():
        for br in v.get("main", []):
            if br is None:
                continue
            for tt in br:
                if tt["node"] == slack_name:
                    tt["node"] = ctx["name"]
                    moved.append(src)
    assert moved, "no producer for %s" % slack_name
    # the Slack node's own downstream must survive: re-point the IF's true output at it
    conns[ctx["name"]] = {"main": [[{"node": iff["name"], "type": "main", "index": 0}]]}
    conns[iff["name"]] = {"main": [
        [{"node": slack_name, "type": "main", "index": 0}],
        down,
        []]}
    print("  gated %-24s producers rewired: %s" % (slack_name, moved))
w["nodes"] += newnodes

# ------------------------------------------------------------------ channel map
TO_ALERTS = {"Ops Warn Bad Secret", "Ops Warn Event Alias", "Ops Warn Unknown Event",
             "Ops Warn Unknown Marker", "Ops Warn No Lead", "Ops Warn Classify",
             "Ops Warn Unknown Inbox", "Ops Warn Deleted Person", "Nurture Alert"}
EXPR = "={{ $('CONFIG').item.json.slack_channel_alerts }}"
rows = []
for n in w["nodes"]:
    if n["type"] != "n8n-nodes-base.slack":
        continue
    ch = n["parameters"].get("channelId") or {}
    old = ch.get("value")
    if n["name"] in TO_ALERTS:
        ch["value"] = EXPR
        ch["mode"] = "id"
    rows.append((n["name"], old, ch.get("value")))

json.dump({"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
           "settings": {k: v for k, v in (w.get("settings") or {}).items()
                        if k != "timeSavedMode"}},
          open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nWF-2: %d nodes (+%d)" % (len(w["nodes"]), 2 + len(newnodes)))
for nm, a, b in rows:
    mark = "  ->" if a != b else "    "
    print("  %s %-24s %-44s %s" % (mark, nm, str(a)[:44], str(b)[:44]))
