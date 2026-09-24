"""W1.0.15 - ONE reply alert per lead, ever.

Base: W1.0.13.1 patched.json (95 nodes) -> 98 nodes.

DIAGNOSIS (not the premise we started from)
The alert was never gated at all. The chain was:
    M7 Build -> M7 Critical Slack -> M7 IF Patch
`M7 Critical Slack` sits INLINE, posts `$json.alert_text` unconditionally, and HeyReach emits one
`every_message_reply_received` per message. So N messages produced N identical alerts, deterministically.
Person-ec2fedcf, 2026-08-02: execs 12894 (17:14:43Z), 12896 (17:17:40Z), 12898 (17:35:26Z) - three
messages, three posts. There was no label read on the alert path and therefore no read-before-write
race; the 18-minute gap was simply a later message, which a race could never explain.

THE FIX
    M7 Build -> M7 Alert Gate -> M7 IF Should Alert -> [true] M7 Critical Slack -> M7 IF Patch
                                                       [false] M7 Alert Suppressed -> M7 IF Patch
* PRIMARY gate: an alerted-leads registry in workflow staticData, check-and-set inside one
  synchronous block, keyed lead-or-person-or-member + campaign, age-rotated at 90 days.
* SECONDARY gate: the persisted `responded` label already on the lead. staticData is per-workflow and
  is persisted at execution END, so two genuinely concurrent executions can each read a registry that
  does not yet contain the other's key - the label lives in Pipedrive and closes that hole.
* FAIL DIRECTION, per the owner's rule (better a missed duplicate than a duplicate):
    registry hit                        -> SUPPRESS, always, whatever the label read says
    label readable and responded set    -> SUPPRESS (and register)
    label unreadable, registry silent   -> ALERT ONCE and register (a first reply must never be lost)
* BOTH IF branches continue to `M7 IF Patch`: suppressing an alert must never skip the CRM update.
  That is the B20 lesson - a dead-ended false branch silently drops the real work.
"""
import argparse
import json
import sys
from pathlib import Path

ALERT_GATE = r"""// W1.0.15: ONE alert per lead, ever. See the module docstring for why this node exists.
const CFG = $('CONFIG').item.json;
const b = $json;                                  // M7 Build output (carries alert_text)
const n = $('Normalize').item.json;
const sd = $getWorkflowStaticData('global');
const reg = sd.__alerted_v1 = sd.__alerted_v1 || {};

// ---- identity. Lead first, then person, then the LinkedIn identifiers. Never a campaign-only key:
// that would collide across people and suppress everyone after the first.
const camp = String((n.campaign && (n.campaign.id ?? n.campaign.name)) ?? 'nocamp');
const li = (n.lead && (n.lead.member_id || n.lead.public_id || n.lead.li_url)) || null;
const who = b.lead_id ? ('L' + b.lead_id)
          : (b.person_id ? ('P' + b.person_id)
          : (li ? ('M' + li) : null));
const key = who ? (who + '|' + camp) : null;

// ---- prune: a key older than 90 days cannot suppress anything we care about, and an unbounded
// registry in staticData is the same slow leak we fixed in the reconciler.
const now = Date.now();
let pruned = 0;
for (const k of Object.keys(reg)) {
  const t = Date.parse(reg[k]);
  if (Number.isFinite(t) && (now - t) > 90 * 86400000) { delete reg[k]; pruned++; }
}

// ---- SECONDARY: the responded label already persisted on the lead. staticData is written at
// execution end, so concurrent executions cannot see each other's keys; Pipedrive can.
const respondedId = (CFG.labels || {}).responded || null;
let labelSaysRepeat = null;                       // null = could not read
try {
  const resp = $('M7 Lead Get').item.json;
  const leads = (resp && resp.data) || null;
  if (Array.isArray(leads)) {
    const campKey = CFG.fields.lead_campaign;
    const want = (n.campaign || {}).name || null;
    const lead = leads.filter(l => !l.is_archived)
                      .find(l => (l[campKey] ?? null) === want)
                 || (b.lead_id ? leads.find(l => String(l.id) === String(b.lead_id)) : null);
    if (lead && Array.isArray(lead.label_ids)) {
      labelSaysRepeat = respondedId ? lead.label_ids.includes(respondedId) : null;
    }
  }
} catch (e) { labelSaysRepeat = null; }

// ---- decide
let should, reason;
if (!key) {
  // no stable identity at all: we cannot dedupe this one. A first reply must never be lost, so it
  // alerts - and the reason names it, because this is the ONLY path that can still duplicate.
  should = true; reason = 'no_identity';
} else if (reg[key]) {
  should = false; reason = 'already_alerted';
} else if (labelSaysRepeat === true) {
  reg[key] = new Date(now).toISOString();
  should = false; reason = 'responded_label';
} else {
  // check-and-set in the same synchronous block: two items in ONE execution cannot both pass
  reg[key] = new Date(now).toISOString();
  should = true; reason = (labelSaysRepeat === null) ? 'first_alert_label_unreadable' : 'first_alert';
}

return [{ json: { ...b, __alert_key: key, __should_alert: should, __alert_reason: reason,
                  __alert_label_repeat: labelSaysRepeat, __alert_registry_size: Object.keys(reg).length,
                  __alert_pruned: pruned } }];
"""

SUPPRESSED = ("// W1.0.15: the alert was suppressed, but the CRM update must still happen - a "
              "dead-ended\n// false branch would silently drop the person/label/activity work "
              "(the B20 lesson).\nreturn [{ json: $json }];")


def apply_patch(w):
    bn = {n["name"]: n for n in w["nodes"]}
    for req in ("M7 Build", "M7 Critical Slack", "M7 IF Patch", "CONFIG", "M7 Lead Get"):
        if req not in bn:
            raise SystemExit(f"ERROR: base is missing {req} (is this W1.0.13.1?)")
    # the chain we are splicing into must be exactly the one we diagnosed
    c = w["connections"]
    if [x["node"] for x in c.get("M7 Build", {}).get("main", [[]])[0]] != ["M7 Critical Slack"]:
        raise SystemExit("ERROR: M7 Build no longer feeds M7 Critical Slack directly")
    if [x["node"] for x in c.get("M7 Critical Slack", {}).get("main", [[]])[0]] != ["M7 IF Patch"]:
        raise SystemExit("ERROR: M7 Critical Slack no longer feeds M7 IF Patch")

    pos = bn["M7 Critical Slack"]["position"]
    w["nodes"].append({"parameters": {"jsCode": ALERT_GATE}, "id": "wf1-w1015-gate",
                       "name": "M7 Alert Gate", "type": "n8n-nodes-base.code",
                       "typeVersion": 2, "position": [pos[0] - 200, pos[1] + 160]})
    w["nodes"].append({
        "parameters": {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict",
                        "version": 1},
            "conditions": [{"id": "wf1-w1015-c1",
                            "leftValue": "={{ $json.__should_alert === true }}",
                            "rightValue": True,
                            "operator": {"type": "boolean", "operation": "true",
                                         "singleValue": True}}],
            "combinator": "and"}, "options": {}},
        "id": "wf1-w1015-if", "name": "M7 IF Should Alert", "type": "n8n-nodes-base.if",
        "typeVersion": 2, "position": [pos[0] - 100, pos[1] + 160]})
    w["nodes"].append({"parameters": {"jsCode": SUPPRESSED}, "id": "wf1-w1015-noop",
                       "name": "M7 Alert Suppressed", "type": "n8n-nodes-base.code",
                       "typeVersion": 2, "position": [pos[0] + 100, pos[1] + 260]})

    m = lambda name: [{"node": name, "type": "main", "index": 0}]
    c["M7 Build"] = {"main": [m("M7 Alert Gate")]}
    c["M7 Alert Gate"] = {"main": [m("M7 IF Should Alert")]}
    c["M7 IF Should Alert"] = {"main": [m("M7 Critical Slack"), m("M7 Alert Suppressed")]}
    c["M7 Critical Slack"] = {"main": [m("M7 IF Patch")]}
    c["M7 Alert Suppressed"] = {"main": [m("M7 IF Patch")]}
    return w


def validate(w):
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    c = w["connections"]
    if len(w["nodes"]) != 98:
        e.append(f"expected 98 nodes, got {len(w['nodes'])}")
    for nm in ("M7 Alert Gate", "M7 IF Should Alert", "M7 Alert Suppressed"):
        if nm not in bn:
            e.append(f"{nm} missing")
    g = bn.get("M7 Alert Gate", {}).get("parameters", {}).get("jsCode", "")
    if "__alerted_v1" not in g:
        e.append("registry key namespace missing")
    if "reg[key] = new Date(now).toISOString();" not in g:
        e.append("check-and-set missing")
    if "already_alerted" not in g:
        e.append("registry-hit suppression missing")
    if "responded_label" not in g:
        e.append("secondary label gate missing")
    if "first_alert_label_unreadable" not in g:
        e.append("fail-open-once path missing (a first reply could be lost)")
    if "90 * 86400000" not in g:
        e.append("registry pruning missing")
    if "'nocamp'" not in g:
        e.append("campaign fallback missing")
    # the alert must be gated, and BOTH branches must reach the CRM work
    if [x["node"] for x in c.get("M7 Build", {}).get("main", [[]])[0]] != ["M7 Alert Gate"]:
        e.append("M7 Build no longer feeds the gate")
    outs = c.get("M7 IF Should Alert", {}).get("main") or []
    if len(outs) != 2:
        e.append("IF Should Alert must have two branches")
    else:
        if [x["node"] for x in outs[0]] != ["M7 Critical Slack"]:
            e.append("true branch must post the alert")
        if [x["node"] for x in outs[1]] != ["M7 Alert Suppressed"]:
            e.append("false branch must go to the NoOp")
    for nm in ("M7 Critical Slack", "M7 Alert Suppressed"):
        if [x["node"] for x in c.get(nm, {}).get("main", [[]])[0]] != ["M7 IF Patch"]:
            e.append(f"{nm} must continue to M7 IF Patch (suppression must not skip the CRM work)")
    # nothing else may have moved
    if w.get("active") is not False:
        e.append("not inactive")
    if "pinData" in w:
        e.append("pinData present")
    nz = bn["Normalize"]["parameters"]["jsCode"]
    if "W1.0.13.1 two-bracket event-marker parser" not in nz:
        e.append("W1.0.13.1 parser lost")
    if "[camp.id, camp.name, n.lead.full_name]" not in bn["Create Lead"]["parameters"]["jsonBody"]:
        e.append("Create Lead title convention altered")
    names = [n["name"] for n in w["nodes"]]
    if len(names) != len(set(names)):
        e.append("duplicate node names")
    targets = {t["node"] for cc in c.values() for o in cc["main"] for t in o}
    for t in targets:
        if t not in names:
            e.append(f"dangling connection target {t}")
    return e


def main():
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
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")
                   if k in patched}
        a.api_payload.write_bytes(
            (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"W1.0.15 -> {a.output} ({len(patched['nodes'])} nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
