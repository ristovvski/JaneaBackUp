#!/usr/bin/env python3
"""W1.0.11: lead-per-campaign + Melisa title convention + Campaign field + medium.

Change 1 (core): selectLead (Select Existing Lead, M5 Labels Compute, M6 Build, M7 Build) now matches
  the person's non-archived lead whose LEAD custom field Campaign (CONFIG.fields.lead_campaign) ==
  incoming campaign.name (exact). No title parsing. Sent-path Lead Create Gate: create when NO
  campaign-matching lead exists (even if other-campaign leads do); select-existing when one matches.
  Non-sent paths with no campaign lead keep today's no-lead fallback (selectLead -> null).
Change 2: (a) Create Lead title = "{campaign.id} - {campaign.name} - {full name}" (Melisa sprint
  convention; NEW leads only; never rewrites existing). (b) Create Lead writes lead custom field
  Campaign = campaign.name (the machine key for Change 1).
Change 3: person Medium field (CONFIG.fields.person_medium) = static "LinkedIn" on Person Create +
  fill-if-empty (Person Patch Invited + IF Rank gate + M5). Never overwrites.

Input: W1.0.10.1 patched JSON. Deterministic, no network. Node count unchanged (93).
"""
from __future__ import annotations
import argparse, copy, json, sys
from pathlib import Path
from typing import Any

LEAD_CAMPAIGN = "1cd81dfcac8a5583935ff4b60e284d0e580db0b6"   # lead varchar (created for W1.0.11)
PERSON_MEDIUM = "961698945b0329b367da11916a94f10ff7ba71fe"   # person varchar "Medium"

OLD_SELECTLEAD = (
    "function selectLead(leads) {\n"
    "  return (Array.isArray(leads) ? leads : [])\n"
    "    .filter(l => !l.is_archived)\n"
    "    .sort((a,b) => new Date(b.add_time||0) - new Date(a.add_time||0))[0] || null;\n"
    "}"
)
NEW_SELECTLEAD = (
    "function selectLead(leads) {\n"
    "  const _campKey = $('CONFIG').item.json.fields.lead_campaign;\n"
    "  const _want = ($('Normalize').item.json.campaign || {}).name || null;\n"
    "  return (Array.isArray(leads) ? leads : [])\n"
    "    .filter(l => !l.is_archived)\n"
    "    .find(l => (l[_campKey] ?? null) === _want) || null;  // W1.0.11 lead-per-campaign match\n"
    "}"
)

GATE_CREATE_OLD = "={{ $json.success === true && Array.isArray($json.data) && $json.data.length === 0 }}"
GATE_CREATE_NEW = "={{ $json.success === true && Array.isArray($json.data) && !$json.data.some(l => !l.is_archived && (l[$('CONFIG').item.json.fields.lead_campaign] ?? null) === (($('Normalize').item.json.campaign || {}).name || null)) }}"
GATE_EXISTING_OLD = "={{ $json.success === true && Array.isArray($json.data) && $json.data.length > 0 }}"
GATE_EXISTING_NEW = "={{ $json.success === true && Array.isArray($json.data) && $json.data.some(l => !l.is_archived && (l[$('CONFIG').item.json.fields.lead_campaign] ?? null) === (($('Normalize').item.json.campaign || {}).name || null)) }}"

CL_TITLE_OLD = ("  const company = (n.lead && n.lead.company_name) ? n.lead.company_name : '';\n"
                "  const title = company ? (n.lead.full_name + ' \\u2014 ' + company) : n.lead.full_name;\n")
CL_TITLE_NEW = ("  const camp = n.campaign || {};\n"
                "  const title = [camp.id, camp.name, n.lead.full_name].filter(v => v !== null && v !== undefined && v !== '').join(' - ');  // W1.0.11 Melisa sprint convention\n")
CL_ORG_OLD = "  const org = pid.organization_id;"
CL_ORG_NEW = "  if (camp.name) body[cfg.fields.lead_campaign] = camp.name;  // W1.0.11 lead Campaign machine key\n  const org = pid.organization_id;"

PC_MED_OLD = "  cf[f.person_location] = n.lead.location;  // B2\n  cf[f.source] = $('CONFIG').item.json.source_value;  // R1 create-only"
PC_MED_NEW = "  cf[f.person_location] = n.lead.location;  // B2\n  cf[f.person_medium] = 'LinkedIn';  // W1.0.11 medium (create)\n  cf[f.source] = $('CONFIG').item.json.source_value;  // R1 create-only"
PPI_MED_OLD = "  if (!current[f.person_location] && n.lead.location) cf[f.person_location] = n.lead.location;  // B2 fill-if-empty\n  for (const k of Object.keys(cf))"
PPI_MED_NEW = "  if (!current[f.person_location] && n.lead.location) cf[f.person_location] = n.lead.location;  // B2 fill-if-empty\n  if (!current[f.person_medium]) cf[f.person_medium] = 'LinkedIn';  // W1.0.11 medium fill-if-empty\n  for (const k of Object.keys(cf))"
M5_MED_OLD = "  if (!current[f.person_location] && n.lead.location) custom_fields[f.person_location] = n.lead.location;  // B2 fill-if-empty\n  for (const k of Object.keys(custom_fields))"
M5_MED_NEW = "  if (!current[f.person_location] && n.lead.location) custom_fields[f.person_location] = n.lead.location;  // B2 fill-if-empty\n  if (!current[f.person_medium]) custom_fields[f.person_medium] = 'LinkedIn';  // W1.0.11 medium fill-if-empty\n  for (const k of Object.keys(custom_fields))"
GATE_FILL_OLD = "    (!cf[f.person_location] && !!n.lead.location);\n  return stageAdvance || fillable;"
GATE_FILL_NEW = "    (!cf[f.person_location] && !!n.lead.location) ||\n    (!cf[f.person_medium]);\n  return stageAdvance || fillable;"


def apply_patch(workflow: dict[str, Any]) -> dict[str, Any]:
    w = copy.deepcopy(workflow)
    bn = {n["name"]: n for n in w["nodes"]}

    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    cfg["fields"]["lead_campaign"] = LEAD_CAMPAIGN
    cfg["fields"]["person_medium"] = PERSON_MEDIUM
    bn["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2)

    # Change 1: selectLead in the 4 nodes
    for nm in ("Select Existing Lead", "M5 Labels Compute", "M6 Build", "M7 Build"):
        code = bn[nm]["parameters"]["jsCode"]
        if code.count(OLD_SELECTLEAD) != 1:
            raise ValueError(f"{nm}: expected exactly 1 old selectLead, found {code.count(OLD_SELECTLEAD)}")
        bn[nm]["parameters"]["jsCode"] = code.replace(OLD_SELECTLEAD, NEW_SELECTLEAD)

    # Change 1: Lead Create Gate conditions
    vals = bn["Lead Create Gate"]["parameters"]["rules"]["values"]
    c_create = vals[0]["conditions"]["conditions"][0]
    c_exist = vals[1]["conditions"]["conditions"][0]
    if c_create["leftValue"] != GATE_CREATE_OLD or c_exist["leftValue"] != GATE_EXISTING_OLD:
        raise ValueError("Lead Create Gate: unexpected condition expressions")
    c_create["leftValue"] = GATE_CREATE_NEW
    c_exist["leftValue"] = GATE_EXISTING_NEW

    def rep(nm, field, old, new):
        node = bn[nm]["parameters"]
        if old not in node[field]:
            raise ValueError(f"{nm}.{field}: anchor not found")
        node[field] = node[field].replace(old, new)

    # Change 2: Create Lead title + Campaign field
    rep("Create Lead", "jsonBody", CL_TITLE_OLD, CL_TITLE_NEW)
    rep("Create Lead", "jsonBody", CL_ORG_OLD, CL_ORG_NEW)
    # Change 3: medium
    rep("Person Create", "jsonBody", PC_MED_OLD, PC_MED_NEW)
    rep("Person Patch Invited", "jsonBody", PPI_MED_OLD, PPI_MED_NEW)
    rep("M5 Person Patch Accepted", "jsonBody", M5_MED_OLD, M5_MED_NEW)
    cond = bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]
    if GATE_FILL_OLD not in cond["leftValue"]:
        raise ValueError("IF Rank Allows Invited: fillable anchor not found")
    cond["leftValue"] = cond["leftValue"].replace(GATE_FILL_OLD, GATE_FILL_NEW)

    w.pop("pinData", None)
    w["active"] = False
    return w


def _cycle(w):
    conns = w["connections"]; color = {n["name"]: 0 for n in w["nodes"]}; bad = []
    def dfs(u):
        color[u] = 1
        for br in (conns.get(u, {}).get("main") or []):
            for e in br or []:
                v = e["node"]
                if color.get(v, 2) == 1: bad.append(f"{u}->{v}")
                elif color.get(v, 2) == 0: dfs(v)
        color[u] = 2
    for n in list(color):
        if color[n] == 0: dfs(n)
    return bad


def validate(w) -> list[str]:
    e = []
    bn = {n["name"]: n for n in w["nodes"]}
    cfg = json.loads(bn["CONFIG"]["parameters"]["jsonOutput"])
    if cfg.get("fields", {}).get("lead_campaign") != LEAD_CAMPAIGN: e.append("CONFIG.fields.lead_campaign missing")
    if cfg.get("fields", {}).get("person_medium") != PERSON_MEDIUM: e.append("CONFIG.fields.person_medium missing")
    for nm in ("Select Existing Lead", "M5 Labels Compute", "M6 Build", "M7 Build"):
        c = bn[nm]["parameters"]["jsCode"]
        if "find(l => (l[_campKey] ?? null) === _want)" not in c: e.append(f"{nm}: campaign-match selectLead missing")
        if ".sort((a,b) => new Date(b.add_time" in c: e.append(f"{nm}: old newest-lead selectLead still present")
    vals = bn["Lead Create Gate"]["parameters"]["rules"]["values"]
    if "!$json.data.some" not in vals[0]["conditions"]["conditions"][0]["leftValue"]: e.append("gate create not campaign-aware")
    if "$json.data.some" not in vals[1]["conditions"]["conditions"][0]["leftValue"]: e.append("gate existing not campaign-aware")
    cl = bn["Create Lead"]["parameters"]["jsonBody"]
    if "[camp.id, camp.name, n.lead.full_name]" not in cl: e.append("Create Lead title convention missing")
    if "body[cfg.fields.lead_campaign] = camp.name" not in cl: e.append("Create Lead Campaign field write missing")
    if "n.lead.full_name + ' — ' + company" in cl: e.append("Create Lead old title still present")
    if "cf[f.person_medium] = 'LinkedIn'" not in bn["Person Create"]["parameters"]["jsonBody"]: e.append("Person Create medium missing")
    for nm, tok in (("Person Patch Invited", "cf[f.person_medium] = 'LinkedIn'"), ("M5 Person Patch Accepted", "custom_fields[f.person_medium] = 'LinkedIn'")):
        if tok not in bn[nm]["parameters"]["jsonBody"]: e.append(f"{nm} medium fill-if-empty missing")
    if "person_medium" not in bn["IF Rank Allows Invited"]["parameters"]["conditions"]["conditions"][0]["leftValue"]: e.append("IF Rank gate medium clause missing")
    cyc = _cycle(w)
    if cyc: e.append(f"cycle: {cyc}")
    if w.get("active") is not False: e.append("not inactive")
    if "pinData" in w: e.append("pinData present")
    if len(w["nodes"]) != 93: e.append(f"expected 93 nodes, got {len(w['nodes'])}")
    return e


def main() -> int:
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
    print(f"W1.0.11 patched -> {a.output} (nodes: {len(patched['nodes'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
