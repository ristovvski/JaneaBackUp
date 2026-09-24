#!/usr/bin/env python3
"""dnc_morning_digest: fix the two defects behind its daily n/a lines (2026-09-24 item 2).

1. INTEGRITY n/a -- "PD Campaign Leads" was fed PD Volume's single accumulator item, which has no
   campaign_name, so it searched once with an empty term (Pipedrive 400 "querystring must have
   required property 'term'") and Integrity zipped 1 response against N campaigns. A new
   "Integrity Campaigns" node emits one item per active Smartlead campaign (term = campaign id,
   which matches exactly the '{id} - ...' lead titles Integrity counts), each carrying the
   accumulator forward.
2. no-match n/a -- conversations.history needs channels:history; the bot token has chat:write only.
   A scope change is a Slack-admin app reinstall, so the line is dropped: "Ops Channel History" and
   "No Match Count" are removed, Changelog Count feeds Compose directly, Compose no longer prints it.

Pass --apply to patch; default is a dry run.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DNC_OBS_P1_build"))
from zz_patch_projections_sweep_p1_fix import n8n

LIVE_ID = "qJKfR602wV9yfFrj"
EXPECTED_LIVE_UPDATED_AT = "2026-09-15T13:47:11.826Z"

CAMPAIGNS_FILTER = "$('SL Due Date').all().map(i => i.json).filter(c => c && c.__skip_campaign !== true && c.campaign_id != null)"

INTEGRITY_CAMPAIGNS_JS = (
    "// One item per active Smartlead campaign, so 'PD Campaign Leads' searches each one; every item\n"
    "// carries the accumulator forward because the HTTP node between here and Integrity destroys $json.\n"
    "// With no active campaign a single placeholder keeps the chain alive (Integrity ignores its search).\n"
    "const prev = $('PD Volume').first().json;\n"
    "const camps = " + CAMPAIGNS_FILTER + ";\n"
    "if (!camps.length) return [{ json: { ...prev, __int_term: 'no-active-campaign' } }];\n"
    "return camps.map(c => ({ json: { ...prev, __int_campaign_id: c.campaign_id, __int_term: String(c.campaign_id) } }));"
)

OLD_INTEGRITY_HEAD = (
    "const prev = $('PD Volume').first().json;\n"
    "const camps = $('SL Due Date').all().map(i => i.json);\n"
    "const resp = $input.all().map(i => i.json);\n"
)
NEW_INTEGRITY_HEAD = (
    "const prev = $('Integrity Campaigns').first().json;\n"
    "const camps = " + CAMPAIGNS_FILTER + ";\n"
    "const resp = camps.length ? $input.all().map(i => i.json) : [];\n"
)
OLD_INTEGRITY_RETURN = "return [{ json: { ...prev, __integrity_zip_ok: zip_ok, integrity_per_campaign: per } }];"
NEW_INTEGRITY_RETURN = (
    "const carried = Object.fromEntries(Object.entries(prev).filter(([k]) => !k.startsWith('__int_')));\n"
    "return [{ json: { ...carried, __integrity_zip_ok: zip_ok, integrity_per_campaign: per } }];"
)

OLD_COMPOSE_HEALTH = "\n    + ' · no-match ' + num(d.no_match_24h);"
NEW_COMPOSE_HEALTH = ";"
OLD_COMPOSE_GAP = "  if (d.__nomatch_readable === false) gaps.push('no-match count unreadable: ' + d.__nomatch_error);\n"


def build(live):
    wf = copy.deepcopy(live)
    by = {n["name"]: n for n in wf["nodes"]}

    integ = by["Integrity"]["parameters"]
    assert integ["jsCode"].count(OLD_INTEGRITY_HEAD) == 1, "Integrity head not found verbatim -- live drifted"
    assert integ["jsCode"].count(OLD_INTEGRITY_RETURN) == 1, "Integrity return not found verbatim -- live drifted"
    integ["jsCode"] = (integ["jsCode"].replace(OLD_INTEGRITY_HEAD, NEW_INTEGRITY_HEAD)
                       .replace(OLD_INTEGRITY_RETURN, NEW_INTEGRITY_RETURN))

    term = next(p for p in by["PD Campaign Leads"]["parameters"]["queryParameters"]["parameters"] if p["name"] == "term")
    assert term["value"] == "={{ $json.campaign_name }}", term["value"]
    term["value"] = "={{ $json.__int_term }}"

    comp = by["Compose"]["parameters"]
    for old in (OLD_COMPOSE_HEALTH, OLD_COMPOSE_GAP):
        assert comp["jsCode"].count(old) == 1, f"Compose fragment not found verbatim: {old!r}"
    comp["jsCode"] = comp["jsCode"].replace(OLD_COMPOSE_HEALTH, NEW_COMPOSE_HEALTH).replace(OLD_COMPOSE_GAP, "")
    assert "no_match" not in comp["jsCode"] and "nomatch" not in comp["jsCode"]

    pv = by["PD Volume"]["position"]
    wf["nodes"].append({"parameters": {"jsCode": INTEGRITY_CAMPAIGNS_JS, "mode": "runOnceForAllItems"},
                        "id": "integrity_campaigns", "name": "Integrity Campaigns", "type": "n8n-nodes-base.code",
                        "typeVersion": 2, "position": [pv[0] + 110, pv[1] + 120]})
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in ("Ops Channel History", "No Match Count")]

    c = wf["connections"]
    assert [x["node"] for x in c["PD Volume"]["main"][0]] == ["PD Campaign Leads"]
    assert [x["node"] for x in c["Changelog Count"]["main"][0]] == ["Ops Channel History"]
    c["PD Volume"] = {"main": [[{"node": "Integrity Campaigns", "type": "main", "index": 0}]]}
    c["Integrity Campaigns"] = {"main": [[{"node": "PD Campaign Leads", "type": "main", "index": 0}]]}
    c["Changelog Count"] = {"main": [[{"node": "Compose", "type": "main", "index": 0}]]}
    del c["Ops Channel History"], c["No Match Count"]
    return wf


if __name__ == "__main__":
    live = n8n(f"/api/v1/workflows/{LIVE_ID}")
    if live.get("updatedAt") != EXPECTED_LIVE_UPDATED_AT:
        raise SystemExit(f"ABORT: live digest changed since inspection ({live.get('updatedAt')}) -- re-inspect first")
    new = build(live)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_out", "patched_digest_integrity_nomatch.json")
    json.dump(new, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    before, after = {n["name"] for n in live["nodes"]}, {n["name"] for n in new["nodes"]}
    print(f"add={sorted(after - before)} remove={sorted(before - after)} -> {out}")
    if "--apply" not in sys.argv:
        print("DRY RUN only -- pass --apply to patch.")
        sys.exit(0)
    was_active = live.get("active", False)
    n8n(f"/api/v1/workflows/{LIVE_ID}/deactivate", "POST", {})
    n8n(f"/api/v1/workflows/{LIVE_ID}", "PUT", {"name": new["name"], "nodes": new["nodes"],
                                                "connections": new["connections"], "settings": new["settings"]})
    if was_active:
        n8n(f"/api/v1/workflows/{LIVE_ID}/activate", "POST", {})
    v = n8n(f"/api/v1/workflows/{LIVE_ID}")
    ok = {n["name"] for n in v["nodes"]} == after and v.get("active") == was_active
    print(f"post-patch active={v.get('active')} nodes={len(v['nodes'])} names_match={ok}")
    if not ok:
        raise SystemExit("POST-PATCH VERIFY FAILED")
