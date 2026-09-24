# -*- coding: utf-8 -*-
"""Builds `dnc_i04_event_log_prune` — retention for the CRM change log.

Why this exists: `dnc_i04_daily_summary` used to prune the event table as a side effect of
producing its report (35-day cutoff). The summary is being retired, so the table would otherwise
grow forever. Measured 2026-09-03: 1,563 rows over 9 days, mean 215 events/complete day,
~3.4 KB per row → ~19,400 rows / ~62 MB at 90 days.

DESIGN RULE, and the reason this is a separate workflow rather than a step inside the receiver:
  * The receiver is 5 nodes with 1,562 runs and zero errors, on the hot path of every Pipedrive
    event. Nothing goes on that path.
  * The prune NEVER reads the whole table. It filters `received_at < cutoff` server-side, so the
    read is bounded by one day's worth of aged-out rows (~215), not by the table (~62 MB at
    steady state). A full-table read of this table is the OOM shape that has taken this instance
    down before - and it did so again while this change was being built: a probe that chained
    four `returnAll` reads returned 502.
  * `lt` and `gte` were verified to work server-side on `received_at` before being relied on.

Usage:
  python build_event_log_prune.py            # dry run, writes JSON only
  python build_event_log_prune.py --apply    # create/update in n8n
"""
import json, os, sys, time

sys.path.insert(0, r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-----------\15a1459d-184a-4069-b4d9-110080844861\scratchpad\s2")
_lib = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "")
exec(open(r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User-Desktop-----------\15a1459d-184a-4069-b4d9-110080844861\scratchpad\s2\lib.py", encoding="utf-8").read())

NAME = "dnc_i04_event_log_prune"
EVENT_TABLE = "zAW2IYoO6Dj0vdIt"

CONFIG = {
    "module": NAME,
    "event_table_id": EVENT_TABLE,
    "retention_days": 90,
    # A cap, not a target. At steady state a day ages out ~215 rows; anything far above that means
    # a backlog, and a backlog should be worked off over several days rather than in one burst.
    "max_deletes_per_run": 500,
    # Armed 2026-09-03. It is a NO-OP until ~2026-11-24: the oldest row is 2026-08-26 and the
    # cutoff is 90 days, so nothing ages out before then. Verified by a dry run the same day.
    "dry_run": False,
    "note": "retention for i04_event_log. Reads only rows older than the cutoff - never the whole "
            "table. Sized 2026-09-03: 215 events/day, 3.4KB/row, ~19.4k rows / ~62MB at 90 days.",
}

PLAN_JS = r"""
const cfg = $('CONFIG').first().json;
const days = Number(cfg.retention_days) || 90;
const cap = Math.max(1, Number(cfg.max_deletes_per_run) || 500);
const dry = cfg.dry_run === true;
const cutoff = new Date(Date.now() - days * 86400000).toISOString();

// POSITIVE shape check. The read is filtered `received_at < cutoff`, so ZERO ROWS IS THE NORMAL,
// HEALTHY ANSWER - it means nothing has aged out yet. That makes "empty" and "unreadable"
// genuinely indistinguishable here unless we look for the failure shape explicitly: on error some
// dataTable ops return {error}, others echo the input items with no marker at all.
const raw = $input.all().map(i => i.json);
// alwaysOutputData gives exactly one KEYLESS item when the filtered read matched nothing. That is
// the healthy answer here and must not be confused with an unreadable table.
const placeholder = raw.length === 1 && raw[0] && Object.keys(raw[0]).length === 0;
const items = placeholder ? [] : raw;
const errored = items.filter(r => r && r.error !== undefined);
const rows = items.filter(r => r && typeof r.event_id === 'string' && typeof r.received_at === 'string');
if (errored.length) {
  throw new Error('i04 prune: the stale-row read failed (' +
    String(errored[0].error).slice(0, 160) + '). Refusing to report "nothing to prune".');
}
// Anything that came back but is not a row is an unrecognised shape - also not "nothing to prune".
if (items.length && !rows.length) {
  throw new Error('i04 prune: read returned ' + items.length + ' item(s) of an unrecognised shape. '
                + 'Refusing to treat that as an empty result.');
}

// Defence in depth: the server-side filter is what bounds the read, but re-check the date here so
// a filter that silently stopped filtering cannot delete live rows.
const stale = rows.filter(r => r.received_at < cutoff);
const mismatched = rows.length - stale.length;
const batch = stale.slice(0, cap);
const oldest = stale.length ? stale.map(r => r.received_at).sort()[0] : null;

return [{ json: {
  cutoff, retention_days: days, dry_run: dry,
  stale_found: stale.length,
  filter_mismatch: mismatched,          // >0 means the server-side filter is not doing its job
  will_delete: dry ? 0 : batch.length,
  planned_delete: batch.length,
  capped: stale.length > cap,
  remaining_after_run: dry ? stale.length : Math.max(0, stale.length - batch.length),
  oldest_stale: oldest,
  stale_ids: dry ? [] : batch.map(r => r.event_id)
} }];
"""

REPORT_ONLY_JS = r"""
const p = $input.first().json;
return [{ json: { ...p, deleted: 0,
  outcome: p.dry_run ? 'DRY RUN - nothing deleted'
         : (p.stale_found === 0 ? 'nothing older than the cutoff' : 'no rows selected'),
  note: p.filter_mismatch > 0
      ? 'WARNING: ' + p.filter_mismatch + ' row(s) came back that are NOT older than the cutoff - '
        + 'the server-side filter is not filtering. Investigate before enabling deletion.'
      : null } }];
"""

REPORT_DELETED_JS = r"""
// Count outcomes, not items. A delete node with continueRegularOutput can hand back an error item;
// reporting "deleted N" off the input count would be a confident, false answer.
const plan = $('Plan').first().json;
const items = $input.all().map(i => i.json);
const failed = items.filter(r => r && r.error !== undefined);
const ok = items.length - failed.length;
return [{ json: {
  cutoff: plan.cutoff, retention_days: plan.retention_days, dry_run: false,
  stale_found: plan.stale_found, attempted: items.length,
  deleted: ok, failed: failed.length,
  first_error: failed.length ? String(failed[0].error).slice(0, 200) : null,
  capped: plan.capped, remaining_after_run: plan.remaining_after_run,
  outcome: failed.length ? 'PARTIAL - ' + failed.length + ' delete(s) failed'
                         : 'deleted ' + ok + ' row(s)'
} }];
"""

nodes = [
    {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "20 6 * * *"}]}},
     "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, -100],
     "id": "i04prune-sched-01", "name": "Daily Prune Trigger"},
    {"parameters": {"httpMethod": "POST", "path": "{{WEBHOOK_I04_EVENT_LOG_PRUNE}}",
                    "responseMode": "lastNode", "options": {}},
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 100],
     "id": "i04prune-hook-01", "name": "Manual Run",
     "webhookId": "f3a8c1d5b7e2409ea6c4d8137b0f5e29"},
    {"parameters": {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2), "options": {}},
     "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [220, 0],
     "id": "i04prune-config-01", "name": "CONFIG"},
    {"parameters": {"resource": "row", "operation": "get",
                    "dataTableId": {"__rl": True, "mode": "id", "value": EVENT_TABLE},
                    "returnAll": True, "matchType": "allConditions",
                    "filters": {"conditions": [{
                        "keyName": "received_at", "condition": "lt",
                        "keyValue": "={{ new Date(Date.now() - ($('CONFIG').first().json.retention_days * 86400000)).toISOString() }}"}]},
                    "options": {}},
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [440, 0],
     "id": "i04prune-read-01", "name": "Get Stale Events",
     # Without this, a zero-row read (the NORMAL healthy answer, since the filter is
     # `received_at < cutoff`) emits no items, every downstream node is skipped, and the run
     # produces no report whatsoever - silence that looks identical to success.
     "alwaysOutputData": True},
    {"parameters": {"jsCode": PLAN_JS, "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [660, 0],
     "id": "i04prune-plan-01", "name": "Plan"},
    {"parameters": {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict",
                                               "leftValue": "", "version": 1},
                                   "combinator": "and",
                                   "conditions": [{"id": "c1", "leftValue": "={{ $json.will_delete > 0 }}",
                                                   "rightValue": True,
                                                   "operator": {"type": "boolean", "operation": "true",
                                                                "singleValue": True}}]},
                    "options": {}},
     "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [880, 0],
     "id": "i04prune-if-01", "name": "Should Delete?"},
    {"parameters": {"fieldToSplitOut": "stale_ids", "options": {}},
     "type": "n8n-nodes-base.splitOut", "typeVersion": 1, "position": [1100, -100],
     "id": "i04prune-split-01", "name": "Split Stale"},
    {"parameters": {"resource": "row", "operation": "deleteRows",
                    "dataTableId": {"__rl": True, "mode": "id", "value": EVENT_TABLE},
                    "matchType": "allConditions",
                    "filters": {"conditions": [{"keyName": "event_id", "condition": "eq",
                                                "keyValue": "={{ $json.stale_ids }}"}]},
                    "options": {}},
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [1320, -100],
     "id": "i04prune-del-01", "name": "Delete Event Row",
     "onError": "continueRegularOutput", "alwaysOutputData": True},
    {"parameters": {"jsCode": REPORT_DELETED_JS, "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1540, -100],
     "id": "i04prune-rep1-01", "name": "Report Deleted"},
    {"parameters": {"jsCode": REPORT_ONLY_JS, "mode": "runOnceForAllItems"},
     "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1100, 100],
     "id": "i04prune-rep2-01", "name": "Report Only"},
]

connections = {
    "Daily Prune Trigger": {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]},
    "Manual Run": {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]},
    "CONFIG": {"main": [[{"node": "Get Stale Events", "type": "main", "index": 0}]]},
    "Get Stale Events": {"main": [[{"node": "Plan", "type": "main", "index": 0}]]},
    "Plan": {"main": [[{"node": "Should Delete?", "type": "main", "index": 0}]]},
    "Should Delete?": {"main": [[{"node": "Split Stale", "type": "main", "index": 0}],
                                [{"node": "Report Only", "type": "main", "index": 0}]]},
    "Split Stale": {"main": [[{"node": "Delete Event Row", "type": "main", "index": 0}]]},
    "Delete Event Row": {"main": [[{"node": "Report Deleted", "type": "main", "index": 0}]]},
}

wf = {"name": NAME, "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1", "errorWorkflow": "BbrXPABgOaaTJjD6",
                   "callerPolicy": "workflowsFromSameOwner", "timezone": "Asia/Jerusalem"}}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "dnc_i04_event_log_prune.json")
    json.dump(wf, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("built %d nodes -> %s" % (len(nodes), out))
    if "--apply" in sys.argv:
        existing = [w for w in all_workflows() if w["name"] == NAME]
        if existing:
            r, dropped = put_wf(existing[0]["id"], wf)
            print("PUT %s (%s) dropped=%s" % (r.status_code, existing[0]["id"], dropped))
            wid = existing[0]["id"]
        else:
            r = create_wf(wf)
            print("CREATE", r.status_code)
            if r.status_code >= 300:
                print(r.text[:500]); sys.exit(1)
            wid = r.json()["id"]
            print("id:", wid)
        ra = activate(wid)
        print("activate:", ra.status_code)
        back = get_wf(wid)
        print("readback: active=%s nodes=%d versionId=%s" % (back.get("active"), len(back["nodes"]),
                                                             back.get("versionId")))
        open(os.path.join(os.path.dirname(out), "prune_id.txt"), "w").write(wid)
