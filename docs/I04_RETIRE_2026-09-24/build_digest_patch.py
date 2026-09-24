#!/usr/bin/env python3
"""dnc_morning_digest: retire the CRM change-log line, add the data-table size line.

  remove  CRM Changelog 24h, Changelog Count          (their table was deleted 2026-09-24)
  add     DT Domains Rows -> DT Domains Agg -> DT Claims Rows -> DT Size Agg
  change  CONFIG  (event_table_id dropped, data_table_cap_mb + size table ids added, note updated)
          Compose (change-log text and its gap gone; new DATA TABLES line; the 12-line cap can no
                   longer cut the "not measured" footer)
  wiring  Sched Agg -> DT Domains Rows -> ... -> DT Size Agg -> Compose

Writes dnc_morning_digest.post.json from the live backup. Pushes nothing.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
pre = json.load(open(os.path.join(HERE, "backup", "dnc_morning_digest.pre.json"), encoding="utf-8"))
w = copy.deepcopy(pre)
N = {n["name"]: n for n in w["nodes"]}
js = lambda f: open(os.path.join(HERE, f), encoding="utf-8").read()


def must_replace(s, old, new, label):
    if s.count(old) != 1:
        raise SystemExit("ABORT %s: expected exactly 1 occurrence, found %d" % (label, s.count(old)))
    return s.replace(old, new)


# ---------------------------------------------------------------- CONFIG
cfg = json.loads(N["CONFIG"]["parameters"]["jsonOutput"])
assert cfg.pop("event_table_id") == "zAW2IYoO6Dj0vdIt"
cfg["_i04_note"] = ("2026-09-24: the CRM change log (I-04) is retired. Its table i04_event_log was "
                    "deleted (36 MB of the 50 MB data-table cap); dnc_i04_event_receiver and "
                    "dnc_i04_event_log_prune are deactivated and preserved; Pipedrive webhooks "
                    "3163026/3163027 deleted. The digest no longer reports it.")
cfg["data_table_cap_mb"] = 50
cfg["domains_table_id"] = "ai4ZiOGqzuJHRYLB"
cfg["claims_table_id"] = "euyostwJYfJefItC"
N["CONFIG"]["parameters"]["jsonOutput"] = json.dumps(cfg, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------- Compose
c = N["Compose"]["parameters"]["jsCode"]
c = must_replace(c, """  // I-04 became a change log on 2026-09-03: the daily summary and the weekly reconciliation were
  // retired, so there is no reporting job left to be 'ok' or 'FAILING'. What remains is the event
  // receiver, and the honest measure of it is how many CRM changes it actually captured.
""", """  // The CRM change log (I-04) was retired on 2026-09-24 - its table was deleted to free data-table
  // space and its receiver was deactivated - so it is no longer part of HEALTH.
""", "changelog comment")
c = must_replace(c, "(d.__err_readable === false || missed === null || d.__changelog_readable === false)",
                 "(d.__err_readable === false || missed === null)", "health amber condition")
c = must_replace(c, """    + ' · missed schedules ' + num(missed)
    + ' · CRM change log ' + (d.__changelog_readable ? num(d.changelog_24h) + ' events' : 'unreadable');""",
                 """    + ' · missed schedules ' + num(missed);""", "health line")
c = must_replace(c, """// ---------- footer: what was NOT measured. Never a silent gap.""",
                 """// ---------- 6 DATA TABLES - the 50 MB cap every DNC write and every claim depends on.
// '≈': serialized row data, not n8n's own storage figure (UI-only; see DT Size Agg).
{
  const ok = d.__dt_readable === true;
  const pct = d.dt_pct;
  const st = !ok ? 'amber' : pct >= 90 ? 'red' : pct >= 80 ? 'amber' : 'green';
  const p = d.dt_parts || {};
  const g = d.dt_growth_7d_mb;
  L.push(dot(st) + ' *DATA TABLES* ' + (ok ? '≈' + d.dt_total_mb + ' MB' : 'n/a') + ' / ' + num(d.dt_cap_mb)
    + (ok ? ' (' + pct + '%) · ledger ' + p.ledger + ' · domains ' + p.domains + ' · claims ' + p.claims : '')
    + ((g === null || g === undefined) ? '' : ' · ' + (g >= 0 ? '+' : '') + g + ' MB/7d'));
}
// ---------- footer: what was NOT measured. Never a silent gap.""", "data tables section")
c = must_replace(c, "  if (d.__changelog_readable === false) gaps.push('CRM change log unreadable: ' + d.__changelog_error);\n",
                 "  if (d.__dt_readable === false) gaps.push('data-table size unreadable: ' + d.__dt_error);\n",
                 "footer gap")
c = must_replace(c, "const text = [header].concat(L).slice(0, 12).join('\\n');",
                 """// The 12-line cap must never cut the footer: a dropped "not measured" line is a silent gap.
const foot = (L.length && String(L[L.length - 1]).startsWith(':information_source:')) ? [L.pop()] : [];
const text = [header].concat(L).slice(0, 12 - foot.length).concat(foot).join('\\n');""", "line cap")
if "hangelog" in c or "change log " in c.replace("CRM change log (I-04) was retired", ""):
    raise SystemExit("ABORT: a change-log reference survived in Compose")
N["Compose"]["parameters"]["jsCode"] = c

# ---------------------------------------------------------------- nodes
x0, y0 = N["CRM Changelog 24h"]["position"]
w["nodes"] = [n for n in w["nodes"] if n["name"] not in ("CRM Changelog 24h", "Changelog Count")]


def read(name, cfg_key, x):
    return {"parameters": {"resource": "row", "operation": "get", "returnAll": True,
                           "dataTableId": {"__rl": True, "mode": "id", "value": cfg[cfg_key]},
                           "options": {}},
            "id": "dt-" + name.lower().replace(" ", "-"), "name": name,
            "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [x, y0],
            "alwaysOutputData": True, "onError": "continueRegularOutput"}


def code(name, f, x):
    return {"parameters": {"jsCode": js(f)}, "id": "dt-" + name.lower().replace(" ", "-"), "name": name,
            "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [x, y0]}


w["nodes"] += [read("DT Domains Rows", "domains_table_id", x0),
               code("DT Domains Agg", "dt_domains_agg.js", x0 + 220),
               read("DT Claims Rows", "claims_table_id", x0 + 440),
               code("DT Size Agg", "dt_size_agg.js", x0 + 660)]
C = w["connections"]
C.pop("CRM Changelog 24h")
C.pop("Changelog Count")
link = lambda a, b: {"main": [[{"node": b, "type": "main", "index": 0}]]}
C["Sched Agg"] = link("Sched Agg", "DT Domains Rows")
C["DT Domains Rows"] = link("", "DT Domains Agg")
C["DT Domains Agg"] = link("", "DT Claims Rows")
C["DT Claims Rows"] = link("", "DT Size Agg")
C["DT Size Agg"] = link("", "Compose")

names = {n["name"] for n in w["nodes"]}
for s, v in C.items():
    assert s in names, s
    for br in v.get("main", []):
        for t in br:
            assert t["node"] in names, t["node"]
json.dump(w, open(os.path.join(HERE, "dnc_morning_digest.post.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("post: %d nodes (pre %d)  ->  dnc_morning_digest.post.json" % (len(w["nodes"]), len(pre["nodes"])))
