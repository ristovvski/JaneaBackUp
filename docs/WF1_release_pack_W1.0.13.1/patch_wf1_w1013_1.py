"""W1.0.13.1 - two-bracket event naming: explicit [Event Name] marker.

Base: W1.0.13 patched.json (95 nodes). Normalize-parser-only change (no node/connection/CONFIG/
write-site/gate changes -> stays 95 nodes). New contract:
  [Events Visiting] [Ai4 2026] - {free text, any order}
- group1 (first [..]) -> canon-map hypothesis (unknown -> hypothesis not written).
- group2 (second [..]) -> Event name verbatim (trim surrounding whitespace only; dashes inside legal).
- everything after group2 = ignored free text; a 3rd bracket is ignored (not an error).
- guardrail (ONLY when group1 is canonical, i.e. a recognized event campaign): no 2nd bracket /
  empty 2nd bracket / event_name >60 -> skip trio + ops warn (new text).
- no bracket at all -> inert. unknown group1 -> hypothesis skipped; event_name from group2 if present;
  NO warn (not our vocabulary).
selectLead / lead title / Campaign field: UNCHANGED (full campaign.name flows verbatim).
"""
import argparse, json, sys
from pathlib import Path

ANCHOR_START = "// W1.0.13 event-marker parser"
ANCHOR_END = "return [{ json: {"

NEW_BLOCK = r"""// W1.0.13.1 two-bracket event-marker parser
const _canon = ($('CONFIG').item.json.event_marker_canon) || {};
const _campName = (b.campaign && b.campaign.name) ? String(b.campaign.name) : '';
const _groups = [];
{ const _re = /\[([^\]]*)\]/g; let _m; while ((_m = _re.exec(_campName)) !== null) _groups.push(_m[1]); }
let _trio;
if (_groups.length === 0) {
  _trio = { marker: false, event_name: null, hypothesis: null, skip: false, warn_text: null };
} else {
  const _content = _groups[0].trim().toLowerCase();
  const _isCanon = Object.prototype.hasOwnProperty.call(_canon, _content);
  const _hyp = _isCanon ? _canon[_content] : null;
  const _ev = (_groups.length >= 2) ? _groups[1].trim() : null;
  const _badSecond = (_ev === null) || (_ev === '') || (_ev.length > 60);
  if (_isCanon && _badSecond) {
    _trio = { marker: true, event_name: null, hypothesis: null, skip: true,
      warn_text: ('⚠️ WF-1: event campaign "' + _campName + '" is missing/has an invalid [Event Name] bracket — trio skipped; fix the campaign name') };
  } else {
    _trio = { marker: true, event_name: _ev, hypothesis: _hyp, skip: false, warn_text: null };
  }
}
"""


def apply_patch(w):
    bn = {n["name"]: n for n in w["nodes"]}
    code = bn["Normalize"]["parameters"]["jsCode"]
    if ANCHOR_START not in code or ANCHOR_END not in code:
        raise SystemExit("ERROR: Normalize parser anchors not found (is base W1.0.13?)")
    i = code.index(ANCHOR_START)
    j = code.index(ANCHOR_END)
    if j <= i:
        raise SystemExit("ERROR: anchor order wrong")
    bn["Normalize"]["parameters"]["jsCode"] = code[:i] + NEW_BLOCK + code[j:]
    return w


def validate(w):
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    nz = bn["Normalize"]["parameters"]["jsCode"]
    if "W1.0.13.1 two-bracket event-marker parser" not in nz: e.append("new parser header missing")
    if "_groups" not in nz or "while ((_m = _re.exec(_campName)) !== null)" not in nz: e.append("two-bracket scan missing")
    if "is missing/has an invalid [Event Name] bracket" not in nz: e.append("new warn text missing")
    if "event_trio: _trio" not in nz: e.append("event_trio wiring lost")
    if "// W1.0.13 event-marker parser" in nz: e.append("old single-bracket parser still present")
    # unchanged surfaces (W1.0.13 trio writes + gates + tee + config still intact)
    for nm, key in (("Person Create", "cf[f.person_event_name] = _t.event_name"),
                    ("Person Patch Invited", "current[f.person_event_name] !== _t.event_name"),
                    ("M5 Person Patch Accepted", "current[f.person_event_name] !== _t.event_name")):
        if key not in bn[nm]["parameters"]["jsonBody"]: e.append(f"{nm} trio write lost")
    for nm in ("IF Rank Allows Invited", "M5 IF Rank Accepted"):
        if "n.event_trio.event_name" not in bn[nm]["parameters"]["conditions"]["conditions"][0]["leftValue"]:
            e.append(f"{nm} gate trio clause lost")
    if "Event Marker Warn" not in bn or "IF Event Marker Bad" not in bn: e.append("warn tee lost")
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("event_marker_canon", {}).get("events visiting") != "Events Visiting": e.append("canon map lost")
    if "[camp.id, camp.name, n.lead.full_name]" not in bn["Create Lead"]["parameters"]["jsonBody"]: e.append("Create Lead title convention altered")
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
    print(f"W1.0.13.1 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
