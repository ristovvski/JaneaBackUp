"""W1.0.13 - event-marker campaign parser: write the person event trio on marker campaigns.

Base: W1.0.11.1 patched.json (93 nodes) -> 95 nodes.
- CONFIG: + fields.person_event_name (ab5540d2), fields.person_hypothesis (8bdae1a9),
  event_marker_canon {"events visiting":"Events Visiting"}.
- Normalize: parse campaign.name -> n.event_trio {marker,event_name,hypothesis,skip,warn_text}.
  Detect first [..] group (contains-rule); canon lookup (lowercased); Event name = name minus the
  bracket group, trimmed of ws + leading/trailing '-'. Guardrail: empty tail / second bracket / >60
  chars -> skip + warn_text. No marker -> fully inert.
- Write sites (event_name + hypothesis, marker+!skip only, always-overwrite-on-differ, medium unchanged):
  Person Create + Person Patch Invited + M5 Person Patch Accepted, and their gates
  (IF Rank Allows Invited, M5 IF Rank Accepted).
- +2 nodes as a NON-BLOCKING TEE off Normalize (Normalize->Switch UNCHANGED):
  IF Event Marker Bad (skip===true) -> Event Marker Warn (Slack -> slack_channel_ops, text=warn_text).
- selectLead / lead title / Campaign field: UNCHANGED (full bracketed campaign.name flows through as-is).
"""
import argparse, json, sys
from pathlib import Path

EVENT_NAME_KEY = "ab5540d2ca45905dfb1434c0fe4971cc5790de3f"
HYP_KEY = "8bdae1a91272e92b335e9e99f668cde659b6daae"
IF_ID = "0e130001-0000-4013-8000-000000000001"
WARN_ID = "0e130002-0000-4013-8000-000000000002"
COND_ID = "0e130003-0000-4013-8000-000000000003"

PARSER_BLOCK = r"""// W1.0.13 event-marker parser
const _canon = ($('CONFIG').item.json.event_marker_canon) || {};
const _campName = (b.campaign && b.campaign.name) ? String(b.campaign.name) : '';
const _mk = _campName.match(/\[([^\]]*)\]/);
let _trio;
if (!_mk) {
  _trio = { marker: false, event_name: null, hypothesis: null, skip: false, warn_text: null };
} else {
  const _content = _mk[1].trim().toLowerCase();
  const _hyp = Object.prototype.hasOwnProperty.call(_canon, _content) ? _canon[_content] : null;
  let _ev = (_campName.slice(0, _mk.index) + _campName.slice(_mk.index + _mk[0].length));
  _ev = _ev.trim().replace(/^[-\s]+/, '').replace(/[-\s]+$/, '').trim();
  const _bad = (_ev === '') || /\[[^\]]*\]/.test(_ev) || (_ev.length > 60);
  _trio = {
    marker: true,
    event_name: _bad ? null : _ev,
    hypothesis: _bad ? null : _hyp,
    skip: _bad,
    warn_text: _bad ? ('⚠️ WF-1: event-marker campaign has a non-canonical name "' + _campName + '" — trio skipped; fix the campaign name') : null
  };
}
"""

CREATE_ADD = """  cf[f.person_medium] = 'LinkedIn';  // W1.0.11 medium (create)
  const _t = n.event_trio || {};  // W1.0.13 event trio (marker campaigns)
  if (_t.marker && !_t.skip) {
    if (_t.event_name) cf[f.person_event_name] = _t.event_name;
    if (_t.hypothesis) cf[f.person_hypothesis] = _t.hypothesis;
  }"""

PATCH_INV_ADD = """  if (!current[f.person_medium]) cf[f.person_medium] = 'LinkedIn';  // W1.0.11 medium fill-if-empty
  const _t = n.event_trio || {};  // W1.0.13 event trio always-overwrite-on-differ (marker campaigns)
  if (_t.marker && !_t.skip) {
    if (_t.event_name && current[f.person_event_name] !== _t.event_name) cf[f.person_event_name] = _t.event_name;
    if (_t.hypothesis && current[f.person_hypothesis] !== _t.hypothesis) cf[f.person_hypothesis] = _t.hypothesis;
  }"""

PATCH_ACC_ADD = """  if (!current[f.person_medium]) custom_fields[f.person_medium] = 'LinkedIn';  // W1.0.11 medium fill-if-empty
  const _t = n.event_trio || {};  // W1.0.13 event trio always-overwrite-on-differ (marker campaigns)
  if (_t.marker && !_t.skip) {
    if (_t.event_name && current[f.person_event_name] !== _t.event_name) custom_fields[f.person_event_name] = _t.event_name;
    if (_t.hypothesis && current[f.person_hypothesis] !== _t.hypothesis) custom_fields[f.person_hypothesis] = _t.hypothesis;
  }"""

GATE_TRIO = (
    " ||\n"
    "    (!!n.event_trio && n.event_trio.marker && !n.event_trio.skip && !!n.event_trio.event_name && cf[f.person_event_name] !== n.event_trio.event_name) ||\n"
    "    (!!n.event_trio && n.event_trio.marker && !n.event_trio.skip && !!n.event_trio.hypothesis && cf[f.person_hypothesis] !== n.event_trio.hypothesis)")


def r1(s, old, new, where):
    if s.count(old) != 1:
        raise SystemExit(f"ERROR: anchor x{s.count(old)} in {where}")
    return s.replace(old, new)


def apply_patch(w):
    bn = {n["name"]: n for n in w["nodes"]}

    # 1) CONFIG
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    cfg["fields"]["person_event_name"] = EVENT_NAME_KEY
    cfg["fields"]["person_hypothesis"] = HYP_KEY
    cfg["event_marker_canon"] = {"events visiting": "Events Visiting"}
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2)

    # 2) Normalize parser
    nz = bn["Normalize"]["parameters"]
    nz["jsCode"] = r1(nz["jsCode"], "return [{ json: {", PARSER_BLOCK + "return [{ json: {", "Normalize/parser")
    nz["jsCode"] = r1(nz["jsCode"],
                      "  is_inmail: b.is_inmail ?? false\n} }];",
                      "  is_inmail: b.is_inmail ?? false,\n  event_trio: _trio\n} }];", "Normalize/event_trio")

    # 3) write sites
    pc = bn["Person Create"]["parameters"]
    pc["jsonBody"] = r1(pc["jsonBody"], "  cf[f.person_medium] = 'LinkedIn';  // W1.0.11 medium (create)", CREATE_ADD, "Person Create")
    pi = bn["Person Patch Invited"]["parameters"]
    pi["jsonBody"] = r1(pi["jsonBody"], "  if (!current[f.person_medium]) cf[f.person_medium] = 'LinkedIn';  // W1.0.11 medium fill-if-empty", PATCH_INV_ADD, "Person Patch Invited")
    pa = bn["M5 Person Patch Accepted"]["parameters"]
    pa["jsonBody"] = r1(pa["jsonBody"], "  if (!current[f.person_medium]) custom_fields[f.person_medium] = 'LinkedIn';  // W1.0.11 medium fill-if-empty", PATCH_ACC_ADD, "M5 Person Patch Accepted")

    # 4) gates
    g1 = bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]
    g1["leftValue"] = r1(g1["leftValue"], "    (!cf[f.person_medium]);", "    (!cf[f.person_medium])" + GATE_TRIO + ";", "IF Rank Allows Invited")
    g2 = bn["M5 IF Rank Accepted"]["parameters"]["conditions"]["conditions"][0]
    g2["leftValue"] = r1(g2["leftValue"],
                         "    || (!cf[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid));",
                         "    || (!cf[f.member_id] && n.lead.id !== null && n.lead.id !== '' && Number.isFinite(mid))\n"
                         "    || (!!n.event_trio && n.event_trio.marker && !n.event_trio.skip && !!n.event_trio.event_name && cf[f.person_event_name] !== n.event_trio.event_name)\n"
                         "    || (!!n.event_trio && n.event_trio.marker && !n.event_trio.skip && !!n.event_trio.hypothesis && cf[f.person_hypothesis] !== n.event_trio.hypothesis);",
                         "M5 IF Rank Accepted")

    # 5) new nodes (tee off Normalize)
    npos = bn["Normalize"]["position"]
    if_node = {
        "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 1},
            "conditions": [{"id": COND_ID, "leftValue": "={{ $('Normalize').item.json.event_trio.skip === true }}",
                            "rightValue": True, "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and"}, "options": {}},
        "id": IF_ID, "name": "IF Event Marker Bad", "type": "n8n-nodes-base.if", "typeVersion": 2,
        "position": [npos[0], npos[1] + 360]}
    warn_node = {
        "parameters": {"select": "channel",
            "channelId": {"__rl": True, "value": "={{ $('CONFIG').item.json.slack_channel_ops }}", "mode": "id"},
            "text": "={{ $('Normalize').item.json.event_trio.warn_text }}", "otherOptions": {}},
        "id": WARN_ID, "name": "Event Marker Warn", "type": "n8n-nodes-base.slack", "typeVersion": 2.3,
        "position": [npos[0] + 220, npos[1] + 360],
        "credentials": {"slackApi": {"id": "Udq1K604RpJqg1cR", "name": "Slack account 3"}}}
    w["nodes"].append(if_node)
    w["nodes"].append(warn_node)

    # 6) connections: tee Normalize -> IF Event Marker Bad; IF true -> Event Marker Warn
    conns = w["connections"]
    if any(e.get("node") == "IF Event Marker Bad" for e in conns["Normalize"]["main"][0]):
        raise SystemExit("ERROR: Normalize already tees to IF Event Marker Bad")
    conns["Normalize"]["main"][0].append({"node": "IF Event Marker Bad", "type": "main", "index": 0})
    conns["IF Event Marker Bad"] = {"main": [[{"node": "Event Marker Warn", "type": "main", "index": 0}], []]}
    return w


def validate(w):
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg["fields"].get("person_event_name") != EVENT_NAME_KEY: e.append("CONFIG person_event_name missing")
    if cfg["fields"].get("person_hypothesis") != HYP_KEY: e.append("CONFIG person_hypothesis missing")
    if cfg.get("event_marker_canon", {}).get("events visiting") != "Events Visiting": e.append("CONFIG event_marker_canon missing")
    nz = bn["Normalize"]["parameters"]["jsCode"]
    if "event_trio: _trio" not in nz or "event-marker parser" not in nz: e.append("Normalize parser missing")
    for nm, key in (("Person Create", "cf[f.person_event_name] = _t.event_name"),
                    ("Person Patch Invited", "current[f.person_event_name] !== _t.event_name"),
                    ("M5 Person Patch Accepted", "current[f.person_event_name] !== _t.event_name")):
        if key not in bn[nm]["parameters"]["jsonBody"]: e.append(f"{nm} event trio write missing")
    for nm in ("IF Rank Allows Invited", "M5 IF Rank Accepted"):
        if "n.event_trio.event_name" not in bn[nm]["parameters"]["conditions"]["conditions"][0]["leftValue"]:
            e.append(f"{nm} gate trio clause missing")
    if "IF Event Marker Bad" not in bn or "Event Marker Warn" not in bn: e.append("new nodes missing")
    conns = w["connections"]
    if not any(x.get("node") == "IF Event Marker Bad" for x in conns["Normalize"]["main"][0]): e.append("tee connection missing")
    if not any(x.get("node") == "Switch" for x in conns["Normalize"]["main"][0]): e.append("Normalize->Switch lost!")
    if conns.get("IF Event Marker Bad", {}).get("main", [[]])[0][0].get("node") != "Event Marker Warn": e.append("IF->Warn connection missing")
    # unchanged assertions
    if "[camp.id, camp.name, n.lead.full_name]" not in bn["Create Lead"]["parameters"]["jsonBody"]: e.append("Create Lead title convention altered!")
    if bn["Event Marker Warn"]["type"] != "n8n-nodes-base.slack": e.append("warn node type wrong")
    if w.get("active") is not False: e.append("not inactive")
    if "pinData" in w: e.append("pinData present")
    if len(w["nodes"]) != 95: e.append(f"expected 95 nodes, got {len(w['nodes'])}")
    return e


def main():
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
    print(f"W1.0.13 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
