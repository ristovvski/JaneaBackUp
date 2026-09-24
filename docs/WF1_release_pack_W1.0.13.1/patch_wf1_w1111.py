"""W1.0.11.1 micro-patch — person campaign field (fields.campaign, lh_campaign_name) becomes
ALWAYS-OVERWRITE (was fill-if-empty). Per Melisa: every event writes the incoming campaign.name
when it differs from the person's current value (same-campaign = idempotent, no redundant PATCH).

ONE-FIELD EXCEPTION: only the person campaign field changes semantics. ALL other enrichment
(company/position/li_url/public_id/member_id/location/medium/source) stays fill-if-empty.
Person Create is unchanged (it already sets campaign unconditionally on create).

Sites changed (sent + accepted paths; no M6/M7 campaign writes exist):
  Person Patch Invited        (jsonBody)   patch builder
  M5 Person Patch Accepted    (jsonBody)   patch builder
  IF Rank Allows Invited      (leftValue)  gate fillable clause
  M5 IF Rank Accepted         (leftValue)  gate fillable clause

Input: W1.0.11 patched.json. Deterministic, LF, node count unchanged (93).
"""
import argparse, json, sys
from pathlib import Path

# fill-if-empty (old)  ->  always-overwrite-on-differ (new)
PATCH_OLD_CF = "if (!current[f.campaign] && campaignName) cf[f.campaign] = campaignName;"
PATCH_NEW_CF = "if (campaignName && current[f.campaign] !== campaignName) cf[f.campaign] = campaignName;  // W1.0.11.1 always-overwrite"
PATCH_OLD_CUSTOM = "if (!current[f.campaign] && campaignName) custom_fields[f.campaign] = campaignName;"
PATCH_NEW_CUSTOM = "if (campaignName && current[f.campaign] !== campaignName) custom_fields[f.campaign] = campaignName;  // W1.0.11.1 always-overwrite"
GATE_OLD = "(!cf[f.campaign] && !!campaignName)"
GATE_NEW = "(!!campaignName && cf[f.campaign] !== campaignName)"


def _replace_once(s, old, new, where):
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"ERROR: expected exactly 1 occurrence of anchor in {where}, found {n}")
    return s.replace(old, new)


def apply_patch(w):
    bn = {n["name"]: n for n in w["nodes"]}
    # 1) Person Patch Invited (sent path) body
    b = bn["Person Patch Invited"]["parameters"]
    b["jsonBody"] = _replace_once(b["jsonBody"], PATCH_OLD_CF, PATCH_NEW_CF, "Person Patch Invited")
    # 2) M5 Person Patch Accepted body
    b = bn["M5 Person Patch Accepted"]["parameters"]
    b["jsonBody"] = _replace_once(b["jsonBody"], PATCH_OLD_CUSTOM, PATCH_NEW_CUSTOM, "M5 Person Patch Accepted")
    # 3) IF Rank Allows Invited gate
    lv = bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]
    lv["leftValue"] = _replace_once(lv["leftValue"], GATE_OLD, GATE_NEW, "IF Rank Allows Invited")
    # 4) M5 IF Rank Accepted gate
    lv = bn["M5 IF Rank Accepted"]["parameters"]["conditions"]["conditions"][0]
    lv["leftValue"] = _replace_once(lv["leftValue"], GATE_OLD, GATE_NEW, "M5 IF Rank Accepted")
    return w


def validate(w):
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    if PATCH_NEW_CF not in bn["Person Patch Invited"]["parameters"]["jsonBody"]:
        e.append("Person Patch Invited always-overwrite missing")
    if PATCH_NEW_CUSTOM not in bn["M5 Person Patch Accepted"]["parameters"]["jsonBody"]:
        e.append("M5 Person Patch Accepted always-overwrite missing")
    for nm in ("IF Rank Allows Invited", "M5 IF Rank Accepted"):
        if GATE_NEW not in bn[nm]["parameters"]["conditions"]["conditions"][0]["leftValue"]:
            e.append(f"{nm} gate clause not updated")
    # the old fill-if-empty campaign form must be gone everywhere
    blob = json.dumps(w)
    if PATCH_OLD_CF in blob or PATCH_OLD_CUSTOM in blob or GATE_OLD in blob:
        e.append("old fill-if-empty campaign form still present somewhere")
    # Person Create still sets campaign unconditionally (unchanged)
    if "cf[f.campaign] = n.campaign.name;" not in bn["Person Create"]["parameters"]["jsonBody"]:
        e.append("Person Create campaign write disappeared (should be unchanged)")
    # other enrichment must remain fill-if-empty (spot-check a couple)
    pi = bn["Person Patch Invited"]["parameters"]["jsonBody"]
    if "if (!current[f.company] && n.lead.company_name)" not in pi:
        e.append("Person Patch Invited company fill-if-empty changed (should be unchanged)")
    if "if (!current[f.person_location] && n.lead.location)" not in pi:
        e.append("Person Patch Invited location fill-if-empty changed (should be unchanged)")
    if w.get("active") is not False:
        e.append("not inactive")
    if "pinData" in w:
        e.append("pinData present")
    if len(w["nodes"]) != 93:
        e.append(f"expected 93 nodes, got {len(w['nodes'])}")
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
        payload = {k: patched[k] for k in ("name", "nodes", "connections", "settings")}
        a.api_payload.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"W1.0.11.1 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
