# -*- coding: utf-8 -*-
"""Morning digest: stop reporting the retired I-04 summary; report the CRM change log instead.

Before: two nodes asked the n8n API how `dnc_i04_daily_summary` was doing and the HEALTH line said
`I-04 ok | FAILING | unreadable`. That workflow is now deactivated, so the line would report a
component that no longer exists - and it was already reporting FAILING.

After: the same two slots read the event table directly and the line says
`CRM change log N events`. It measures the thing that still exists - events actually captured in
the last 24 hours - rather than whether a reporting job ran.

The read is filtered `received_at >= since` server-side (verified operator), so it is bounded by
one day of events (~215 rows), never the whole table (~62 MB at 90-day steady state).

Usage: python patch_morning_digest.py [--apply]
"""
import json, copy, os, sys

exec(open(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-----------\15a1459d-184a-4069-b4d9-110080844861\scratchpad\s2\lib.py", encoding="utf-8").read())

WID = "qJKfR602wV9yfFrj"
EVENT_TABLE = "zAW2IYoO6Dj0vdIt"
OUT = os.path.dirname(os.path.abspath(sys.argv[0]))

COUNT_JS = r"""
// Replaces the old `I04 Status`. Counts what the CRM change log actually captured in the window.
// Positive shape check, three-state result: a failed read must read as "unreadable", never as 0 -
// zero events and an unreadable table look identical otherwise, and the digest's own rule is that
// a number it could not measure is never printed as a number.
const prev = $('Sched Agg').first().json;
const raw = $input.all().map(i => i.json);
// alwaysOutputData emits one KEYLESS item when the filtered read matched nothing
const placeholder = raw.length === 1 && raw[0] && Object.keys(raw[0]).length === 0;
const items = placeholder ? [] : raw;
const errored = items.filter(r => r && r.error !== undefined);
const rows = items.filter(r => r && typeof r.event_id === 'string');
if (errored.length || (items.length && !rows.length)) {
  // The COUNT ITSELF is null on an unreadable read, not just a sibling flag. `num()` renders null
  // as 'n/a', so the digest can never print a number it did not measure - the estate's own rule.
  return [{ json: { ...prev, __changelog_readable: false, changelog_24h: null,
    __changelog_error: errored.length ? String(errored[0].error).slice(0, 140)
                                      : 'read returned an unrecognised row shape' } }];
}
const byType = {}, byAction = {};
for (const r of rows) {
  const t = String(r.object_type || '?'); byType[t] = (byType[t] || 0) + 1;
  const a = String(r.event_action || '?'); byAction[a] = (byAction[a] || 0) + 1;
}
return [{ json: { ...prev, __changelog_readable: true,
  changelog_24h: rows.length,
  changelog_leads: byType.lead || 0,
  changelog_persons: byType.person || 0,
  changelog_deletes: byAction.delete || 0 } }];
"""

NEW_READ = {
    "parameters": {"resource": "row", "operation": "get",
                   "dataTableId": {"__rl": True, "mode": "id", "value": EVENT_TABLE},
                   "returnAll": True, "matchType": "allConditions",
                   "filters": {"conditions": [{"keyName": "received_at", "condition": "gte",
                                               "keyValue": "={{ $('Window').first().json.since_iso }}"}]},
                   "options": {}},
    "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [4400, 0],
    "id": "digest-changelog-read", "name": "CRM Changelog 24h",
    "onError": "continueRegularOutput", "alwaysOutputData": True,
}
NEW_COUNT = {
    "parameters": {"jsCode": COUNT_JS, "mode": "runOnceForAllItems"},
    "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [4620, 0],
    "id": "digest-changelog-count", "name": "Changelog Count",
}

OLD_HEALTH = """  const i04bad = Number(d.i04_failed_24h) > 0 || d.i04_last_status === 'error';
  const st = (errs > 0 || i04bad || (missed && missed > 0)) ? 'red'
           : (d.__err_readable === false || missed === null) ? 'amber' : 'green';
  let line = dot(st) + ' *HEALTH* failed execs ' + num(d.errors_24h)
    + ' · missed schedules ' + num(missed)
    + ' · I-04 ' + (d.__i04_readable ? (i04bad ? 'FAILING' : 'ok') : 'unreadable')
    + ' · no-match ' + num(d.no_match_24h);
  if (errs > 0) line += ' — <' + base + '/home/executions?status=error|failed executions>';
  else if (i04bad) line += ' — <' + base + '/workflow/' + cfg.i04_workflow_id + '/executions|I-04>';
  else if (missed > 0) line += ' — ' + (d.missed || []).map(m => m.name).slice(0, 3).join(', ');"""

NEW_HEALTH = """  // I-04 became a change log on 2026-09-03: the daily summary and the weekly reconciliation were
  // retired, so there is no reporting job left to be 'ok' or 'FAILING'. What remains is the event
  // receiver, and the honest measure of it is how many CRM changes it actually captured.
  const st = (errs > 0 || (missed && missed > 0)) ? 'red'
           : (d.__err_readable === false || missed === null || d.__changelog_readable === false)
             ? 'amber' : 'green';
  let line = dot(st) + ' *HEALTH* failed execs ' + num(d.errors_24h)
    + ' · missed schedules ' + num(missed)
    + ' · CRM change log ' + (d.__changelog_readable ? num(d.changelog_24h) + ' events' : 'unreadable')
    + ' · no-match ' + num(d.no_match_24h);
  if (errs > 0) line += ' — <' + base + '/home/executions?status=error|failed executions>';
  else if (missed > 0) line += ' — ' + (d.missed || []).map(m => m.name).slice(0, 3).join(', ');"""

OLD_GAP = "  if (d.__nomatch_readable === false) gaps.push('no-match count unreadable: ' + d.__nomatch_error);"
NEW_GAP = ("  if (d.__nomatch_readable === false) gaps.push('no-match count unreadable: ' + d.__nomatch_error);\n"
           "  if (d.__changelog_readable === false) gaps.push('CRM change log unreadable: ' + d.__changelog_error);")


def main():
    live = get_wf(WID)
    json.dump(live, open(os.path.join(OUT, "backups", "dnc_morning_digest__pre_i04_change.json"),
                         "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    wf = copy.deepcopy(live)

    def node(nm):
        for n in wf["nodes"]:
            if n["name"] == nm:
                return n
        raise KeyError(nm)

    # CONFIG: the retired workflow's id is no longer meaningful; the event table is
    cfgn = node("CONFIG")
    cfg = json.loads(cfgn["parameters"]["jsonOutput"])
    removed = cfg.pop("i04_workflow_id", None)
    cfg["event_table_id"] = EVENT_TABLE
    cfg["_i04_note"] = ("2026-09-03: dnc_i04_daily_summary and dnc_i04_weekly_reconciliation were "
                        "retired. I-04 is now a change log only (dnc_i04_event_receiver). This "
                        "digest reports events captured, not whether a reporting job ran.")
    cfgn["parameters"]["jsonOutput"] = json.dumps(cfg, ensure_ascii=False, indent=2)

    # Swap the two I-04 nodes for the two change-log nodes, keeping the chain order.
    # Remove the REPLACEMENTS by name as well as the originals: on a re-run the originals are
    # already gone, and without this the script appends a second copy of each. It did exactly
    # that once (40 -> 42 nodes, two node pairs sharing a name AND an id, with connections
    # resolving by name); repaired the same minute, and this line is why it cannot recur.
    drop = {"I04 Last", "I04 Status", NEW_READ["name"], NEW_COUNT["name"]}
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in drop]
    wf["nodes"] += [NEW_READ, NEW_COUNT]
    for k in ("I04 Last", "I04 Status"):
        wf["connections"].pop(k, None)
    wf["connections"]["Sched Agg"] = {"main": [[{"node": "CRM Changelog 24h", "type": "main", "index": 0}]]}
    wf["connections"]["CRM Changelog 24h"] = {"main": [[{"node": "Changelog Count", "type": "main", "index": 0}]]}
    wf["connections"]["Changelog Count"] = {"main": [[{"node": "Ops Channel History", "type": "main", "index": 0}]]}

    comp = node("Compose")
    js = comp["parameters"]["jsCode"]
    # Re-runnable: accept either the original text or an already-patched Compose, but never a
    # third state - an unrecognised Compose means someone else edited it and patching blind
    # would silently clobber their change.
    already = NEW_HEALTH in js
    if not already:
        assert OLD_HEALTH in js, "Compose HEALTH block is neither the original nor the patched "                                  "version - refusing to patch blind"
        assert OLD_GAP in js, "Compose gap line not found verbatim"
    if not already:
        js = js.replace(OLD_HEALTH, NEW_HEALTH).replace(OLD_GAP, NEW_GAP)
    else:
        print("Compose already patched - leaving it as is")
    assert "i04" not in js and "I-04" not in js.replace("I-04 became a change log", ""), \
        "Compose still references I-04 after patching"
    comp["parameters"]["jsCode"] = js

    # integrity: no dangling edges, no lingering reference to the retired workflow id
    names = {n["name"] for n in wf["nodes"]}
    for s, v in wf["connections"].items():
        assert s in names, "dangling source " + s
        for br in (v.get("main") or []):
            for t in br:
                assert t["node"] in names, "dangling target " + t["node"]
    from collections import Counter
    dupes = [k for k, v in Counter(n["name"] for n in wf["nodes"]).items() if v > 1]
    assert not dupes, "duplicate node names: " + str(dupes)
    blob = json.dumps(wf["nodes"], ensure_ascii=False)
    assert "8sT1XjDDVmrz05CA" not in blob, "digest still references the retired summary"
    assert "gjVZkkvm05jj8CNM" not in blob, "digest still references the weekly"

    json.dump(wf, open(os.path.join(OUT, "patched_dnc_morning_digest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("removed CONFIG.i04_workflow_id =", removed)
    print("nodes %d -> %d  (I04 Last, I04 Status  ->  CRM Changelog 24h, Changelog Count)"
          % (len(live["nodes"]), len(wf["nodes"])))
    print("Compose: HEALTH line now reports 'CRM change log N events'")

    if "--apply" in sys.argv:
        r, dropped = put_wf(WID, wf)
        print("PUT %s  settings-stripped=%s" % (r.status_code, dropped))
        if r.status_code >= 300:
            print(r.text[:500]); sys.exit(1)
        b = get_wf(WID)
        print("readback: active=%s nodes=%d versionId=%s" % (b.get("active"), len(b["nodes"]),
                                                             b.get("versionId")))


if __name__ == "__main__":
    main()
