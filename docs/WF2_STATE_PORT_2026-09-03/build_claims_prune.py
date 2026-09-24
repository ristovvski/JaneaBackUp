# -*- coding: utf-8 -*-
"""dnc_claims_prune - retention for the atomic claims table.

WHY IT EXISTS. The staticData alert registry pruned at 90 days. When that registry was ported to
the claims table this morning the bound did not come with it, and nothing anywhere deletes from
this table. Measured before this build: 565 rows over 27 days, ~21/day, no deletes by any
workflow. Adding WF-2's three stores roughly doubles the fill rate. A fix that quietly drops a
property the old thing had is its own defect class - this closes it on our own work.

Shape is copied from dnc_i04_event_log_prune deliberately: filtered read, positive shape check,
defence-in-depth re-check of the date, capped deletions, outcomes counted rather than assumed.
"""
import json, io, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(os.environ["S2LIB"], "lib.py"), encoding="utf-8").read())
TABLE = "euyostwJYfJefItC"
DRY_DEFAULT = "--live" not in sys.argv


def js(n):
    return io.open(os.path.join(HERE, "nodes", n), encoding="utf-8").read().rstrip("\n")


CONFIG = {
    "dry_run": DRY_DEFAULT,
    "read_cutoff_days": 7,          # the shortest retention; bounds the read so it never scans
    "max_deletes_per_run": 250,
    "retention_days_by_family": {
        "wf1_alert": 90, "wf2_alert": 90,          # the 90 days staticData used to promise
        "wf1_seen": 7, "wf2_seen": 7, "wf2_bounce": 7,   # > the reconcilers' 48h lookback
        "dedupe": 7, "lead_create": 7,
        "probe": 7, "probe_twin": 7,               # rehearsal rows
    },
}

WF = {
    "name": "dnc_claims_prune",
    "nodes": [
        {"parameters": {"rule": {"interval": [{"field": "cronExpression",
                                               "expression": "35 6 * * *"}]}},
         "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [-420, 0],
         "id": "cp-cron", "name": "Daily Prune Trigger"},
        {"parameters": {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_CLAIMS_PRUNE}}",
                        "responseMode": "lastNode", "options": {}},
         "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [-420, 180],
         "id": "cp-hook", "name": "Manual Run",
         "webhookId": "a7f2c934-51b8-4e0d-9c76-8b31de20f4a5"},
        {"parameters": {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=1),
                        "options": {}},
         "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [-220, 80],
         "id": "cp-cfg", "name": "CONFIG"},
        {"parameters": {"resource": "row", "operation": "get",
                        "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
                        "returnAll": True, "matchType": "allConditions",
                        "filters": {"conditions": [
                            {"keyName": "claimed_at", "condition": "lt",
                             "keyValue": "={{ new Date(Date.now() - "
                                         "($json.read_cutoff_days * 86400000)).toISOString() }}"}]},
                        "options": {}},
         "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [-20, 80],
         "id": "cp-read", "name": "Get Stale Claims",
         "onError": "continueRegularOutput", "alwaysOutputData": True},
        {"parameters": {"jsCode": js("prune_plan.js"), "mode": "runOnceForAllItems"},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [180, 80],
         "id": "cp-plan", "name": "Plan"},
        {"parameters": {"conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "combinator": "and",
            "conditions": [{"id": "cp-del", "leftValue": "={{ $json.will_delete > 0 }}",
                            "rightValue": True,
                            "operator": {"type": "boolean", "operation": "true",
                                         "singleValue": True}}]}, "options": {}},
         "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [380, 80],
         "id": "cp-if", "name": "Should Delete?"},
        {"parameters": {"fieldToSplitOut": "keys", "options": {}},
         "type": "n8n-nodes-base.splitOut", "typeVersion": 1, "position": [580, 0],
         "id": "cp-split", "name": "Split Expired"},
        {"parameters": {"resource": "row", "operation": "deleteRows",
                        "dataTableId": {"__rl": True, "mode": "id", "value": TABLE},
                        "matchType": "allConditions",
                        "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq",
                                                    "keyValue": "={{ $json.claim_key }}"}]},
                        "options": {}},
         "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [780, 0],
         "id": "cp-del", "name": "Delete Claim Row",
         "onError": "continueRegularOutput", "retryOnFail": True},
        {"parameters": {"jsCode": js("prune_report_deleted.js"), "mode": "runOnceForAllItems"},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [980, 0],
         "id": "cp-rd", "name": "Report Deleted"},
        {"parameters": {"jsCode": js("prune_report_only.js"), "mode": "runOnceForAllItems"},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [580, 200],
         "id": "cp-ro", "name": "Report Only"},
    ],
    "connections": {
        "Daily Prune Trigger": {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]},
        "Manual Run": {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]},
        "CONFIG": {"main": [[{"node": "Get Stale Claims", "type": "main", "index": 0}]]},
        "Get Stale Claims": {"main": [[{"node": "Plan", "type": "main", "index": 0}]]},
        "Plan": {"main": [[{"node": "Should Delete?", "type": "main", "index": 0}]]},
        "Should Delete?": {"main": [[{"node": "Split Expired", "type": "main", "index": 0}],
                                    [{"node": "Report Only", "type": "main", "index": 0}]]},
        "Split Expired": {"main": [[{"node": "Delete Claim Row", "type": "main", "index": 0}]]},
        "Delete Claim Row": {"main": [[{"node": "Report Deleted", "type": "main", "index": 0}]]},
    },
    "settings": {"executionOrder": "v1", "errorWorkflow": "BbrXPABgOaaTJjD6",
                 "callerPolicy": "workflowsFromSameOwner", "timezone": "Europe/London"},
}


def main():
    existing = [w for w in all_workflows() if w["name"] == "dnc_claims_prune"]
    if existing:
        wid = existing[0]["id"]
        resp, dropped = put_wf(wid, WF)
        print("UPDATED %s -> HTTP %s dropped %s" % (wid, resp.status_code, dropped))
    else:
        r = create_wf(WF)
        if r.status_code >= 300:
            raise SystemExit("create failed %s %s" % (r.status_code, r.text[:400]))
        wid = r.json()["id"]
        print("CREATED dnc_claims_prune id=%s  dry_run=%s" % (wid, CONFIG["dry_run"]))
    print("activate ->", activate(wid).status_code)
    back = get("/api/v1/workflows/%s" % wid)
    print("live: %s nodes=%d active=%s versionId=%s"
          % (back["name"], len(back["nodes"]), back.get("active"), back.get("versionId")))
    return wid


if __name__ == "__main__":
    main()
