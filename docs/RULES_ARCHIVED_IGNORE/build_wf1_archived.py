# -*- coding: utf-8 -*-
"""WF-1: R-A (archived = ignore), R-B (non-campaign = no post), and the channel map.

Scope reasoning, so the change is no bigger than it needs to be:
  * M5/M6/M7's `!is_archived` filters over /v1/leads?person_id= ARE dead code, but they fail in a
    harmless direction - an archived lead yields lead_id null, so `Mx IF Lead ID` is false and no
    label and no activity is written. Those nodes are therefore left alone.
  * The archived-blindness does real damage in exactly two ways:
      1. CREATE: `Lead Create Gate` sees no live lead and creates a DUPLICATE of the archived one.
         This is the live hole - Person-b093030e's next invite event would have done it.
      2. POST: the false branches of the lead-id gates announce "no lead" to Slack.
  * So: one archived-visible probe, one extra condition on the create gate, and one gate per
    person-scoped post.

Channel map (Nik, 2026-08-31):
  #lead-processing  perfect leads only  - a real campaign reply with a working lead link
  #alerts           every system problem, never silenced
  nowhere           personal chats, archived leads, OOO, bounces
"""
import json, sys

SRC, DST, RULES = sys.argv[1], sys.argv[2], sys.argv[3]
rules_js = open(RULES, encoding="utf-8").read().split("if (typeof module !==")[0].rstrip()

w = json.load(open(SRC, encoding="utf-8"))
by = {n["name"]: n for n in w["nodes"]}
conns = w["connections"]
PD_CRED = {"pipedriveApi": {"id": "HnyULgvDdYp0lIkB", "name": "Pipedrive account"}}
ALERTS = "C0BTUHSSM3K"

# ---------------------------------------------------------------- 0. CONFIG: alerts channel
cfg_node = by["CONFIG"]
cfg = json.loads(cfg_node["parameters"]["jsonOutput"])
cfg["slack_channel_alerts"] = ALERTS
cfg_node["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------- 1. archived-visible probe
probe = {
    "parameters": {
        "method": "GET", "url": "=https://api.pipedrive.com/v1/leads/search",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "term", "value": "={{ [ ($('Normalize').item.json.lead || {}).first_name,"
                                      " ($('Normalize').item.json.lead || {}).last_name ]"
                                      ".filter(Boolean).join(' ') || 'zzz-no-name-zzz' }}"},
            {"name": "limit", "value": "100"}]},
        "authentication": "predefinedCredentialType", "nodeCredentialType": "pipedriveApi",
        "options": {}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [-40, -300],
    "id": "wf1-ar-probe", "name": "AR Probe",
    "onError": "continueRegularOutput", "credentials": PD_CRED}

decide = {"parameters": {"jsCode": rules_js + r"""

// ---- AR Decide (WF-1). Runs once, between Normalize and Switch. Spreads Normalize's output
// verbatim so `Switch` still reads $json.event and every $('Normalize') reference is untouched.
const n = $('Normalize').item.json;
const cfg = $('CONFIG').item.json;
const camp = n.campaign || null;
const probe = arParseProbe($input.first().json, (camp || {}).name,
                           (camp || {}).id, (cfg.fields || {}).lead_campaign);
const arch = probe.rows.filter(function (r) { return r.is_archived; });
return [{ json: Object.assign({}, n, { __ar: {
  probe_ok: probe.ok, probe_reason: probe.reason, saturated: probe.saturated, rows: probe.rows,
  archived_person_ids: arch.map(function (r) { return String(r.person_id); }),
  archived_lead_ids: arch.map(function (r) { return r.id; }),
  any_archived: arch.length > 0,
  is_campaign: arIsCampaign(camp),
  campaign_id: (camp || {}).id || null,
} }) }];
""", "mode": "runOnceForAllItems"},
    "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [160, -300],
    "id": "wf1-ar-decide", "name": "AR Decide"}

w["nodes"] += [probe, decide]
old = conns["Normalize"]["main"][0]
assert sorted(t["node"] for t in old) == ["IF Event Marker Bad", "Switch"], \
    "unexpected Normalize fan-out: %r" % [t["node"] for t in old]
conns["Normalize"]["main"][0] = [t for t in old if t["node"] != "Switch"] + \
                                [{"node": "AR Probe", "type": "main", "index": 0}]
conns["AR Probe"] = {"main": [[{"node": "AR Decide", "type": "main", "index": 0}]]}
conns["AR Decide"] = {"main": [[{"node": "Switch", "type": "main", "index": 0}]]}

# ---------------------------------------------------------------- 2. THE LIVE HOLE
gate = by["Lead Create Gate"]
rule0 = gate["parameters"]["rules"]["values"][0]
conds = rule0["conditions"]["conditions"]
assert len(conds) == 1, "Lead Create Gate rule 0 has %d conditions already" % len(conds)
conds.append({
    "id": "wf1-ra-no-archived",
    # deliberately a SHORT expression: a 1,154-char IIFE in an expression is what the parser
    # rejected on WF-2's reply alert (25/25 executions "invalid syntax").
    "leftValue": "={{ ($('AR Decide').first().json.__ar.archived_person_ids || [])"
                 ".indexOf(String($('PID Resolved').item.json.person_id)) === -1 }}",
    "rightValue": True,
    "operator": {"type": "boolean", "operation": "true", "singleValue": True}})
rule0["conditions"]["combinator"] = "and"

# ---------------------------------------------------------------- 3. person-scoped post gates
# One IF per Slack node; every producer is rewired through it. R-A and R-B both land here:
# an archived campaign lead, or no campaign at all, means the post does not happen.
PERSON_POSTS = ["M7 Critical Slack", "M7 No Lead Warn", "M5 Slack Warn", "M6 Slack Warn",
                "M7 Slack Warn", "M6 Message First Warn"]
gate_js = (rules_js + r"""

// ---- R-A + R-B post gate. Person-scoped posts only; system alarms are never gated.
const ar = (function () {
  try { return ($('AR Decide').first().json.__ar) || null; } catch (e) { return null; }
})();
// An unreadable probe FAILS OPEN: a real reply must never be silenced by a failed lookup.
const archivedBlocked = !!(ar && ar.probe_ok === true && ar.any_archived === true);
const noCampaign = !!(ar && ar.is_campaign === false);
const post = !(archivedBlocked || noCampaign);
return $input.all().map(function (i) {
  return { json: Object.assign({}, i.json, {
    __ar_post: post,
    __ar_post_reason: archivedBlocked ? 'archived_lead_ignored'
                    : noCampaign ? 'non_campaign_person' : 'ok',
  }) };
});
""")
newnodes = []
for idx, slack_name in enumerate(PERSON_POSTS):
    sn = by[slack_name]
    gx, gy = sn["position"][0] - 190, sn["position"][1] + 30
    ctx = {"parameters": {"jsCode": gate_js, "mode": "runOnceForAllItems"},
           "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [gx - 190, gy],
           "id": "wf1-arctx-%d" % idx, "name": "AR Ctx %s" % slack_name}
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
                               "conditions": [{"id": "wf1-post-%d" % idx,
                                               "leftValue": "={{ $json.__ar_post === true }}",
                                               "rightValue": True,
                                               "operator": {"type": "boolean",
                                                            "operation": "true",
                                                            "singleValue": True}}]},
                "renameOutput": True, "outputKey": "post"},
               {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict",
                                           "leftValue": "", "version": 1},
                               "combinator": "and",
                               "conditions": [{"id": "wf1-nocamp-%d" % idx,
                                               "leftValue": "={{ $json.__ar_post_reason }}",
                                               "rightValue": "non_campaign_person",
                                               "operator": {"type": "string",
                                                            "operation": "equals"}}]},
                "renameOutput": True, "outputKey": "silent_continue"}]},
           "options": {"fallbackOutput": "extra", "renameFallbackOutput": "archived_stop"}},
           "type": "n8n-nodes-base.switch", "typeVersion": 3,
           "position": [gx, gy], "id": "wf1-arsw-%d" % idx,
           "name": "AR Post? %s" % slack_name}
    newnodes += [ctx, iff]
    # rewire every producer of the Slack node through ctx -> if -> slack
    moved = []
    for src, v in conns.items():
        for br in v.get("main", []):
            if br is None:
                continue
            for t in br:
                if t["node"] == slack_name:
                    t["node"] = ctx["name"]
                    moved.append(src)
    assert moved, "no producer found for %s" % slack_name
    conns[ctx["name"]] = {"main": [[{"node": iff["name"], "type": "main", "index": 0}]]}
    conns[iff["name"]] = {"main": [
        [{"node": slack_name, "type": "main", "index": 0}],
        down,
        []]}
    print("  gated %-24s producers rewired: %s" % (slack_name, moved))
w["nodes"] += newnodes

# ---------------------------------------------------------------- 4. channel map
# system alarms -> #alerts, CONFIG-driven. Never silenced, just relocated.
SYSTEM_POSTS = {"Event Marker Warn", "Lead Resp Invalid"}
ALERT_ROUTED = SYSTEM_POSTS | {"M7 No Lead Warn", "M5 Slack Warn", "M6 Slack Warn",
                              "M7 Slack Warn", "M6 Message First Warn"}
EXPR = "={{ $('CONFIG').item.json.slack_channel_alerts }}"
before_after = []
for n in w["nodes"]:
    if n["type"] != "n8n-nodes-base.slack":
        continue
    ch = n["parameters"].get("channelId") or {}
    old_v = ch.get("value")
    if n["name"] in ALERT_ROUTED:
        ch["value"] = EXPR
        ch["mode"] = "id"
    before_after.append((n["name"], old_v, ch.get("value")))

json.dump({"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
           "settings": {k: v for k, v in (w.get("settings") or {}).items()
                        if k != "timeSavedMode"}},
          open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("\nWF-1: %d nodes (+%d)" % (len(w["nodes"]), 2 + len(newnodes)))
print("channel before -> after:")
for nm, a, b in before_after:
    print("   %-24s %-46s -> %s" % (nm, str(a)[:46], str(b)[:46]))
prod = {}
for s, v in conns.items():
    for br in v.get("main", []):
        for t in (br or []):
            prod.setdefault(t["node"], []).append(s)
multi = {k: v for k, v in prod.items() if len(v) > 1}
print("\nfan-in (expected: the pre-existing merges only):", len(multi), "targets")
