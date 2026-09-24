#!/usr/bin/env python3
"""HELD -- registry data write. Backfills correlation_id + date_precision (both NOT NULL in
Supabase) on the 82 rows dnc_archived_responders_import wrote on 2026-09-15 without them. Once
set, the 82 claims already stuck in the delta-pusher queue succeed on their next 5-minute cycle
(ending the ~984 Postgres errors/hour) and the nightly reconcile has nothing left it cannot heal.

Plan file: audit_out/unhealable_82_backfill_plan.json. Each update is conditioned on
correlation_id still being empty, so a row someone already fixed is never overwritten.
Deploys a throwaway workflow, fires once, deletes it. Refuses to run until CLEARED_TO_FIRE is True.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DNC_OBS_P1_build"))
from zz_patch_projections_sweep_p1_fix import n8n, BASE, ctx

CLEARED_TO_FIRE = False
REGISTRY_TABLE = "UOgKwlGsL28lX61O"
PLAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit_out", "unhealable_82_backfill_plan.json")


def probe_workflow():
    return {"name": "ZZ_BACKFILL_20260924_unhealable_82_DELETE_ME", "settings": {}, "nodes": [
        {"name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 1, "position": [0, 0],
         "webhookId": "zzbackfillunheal82", "parameters": {"httpMethod": "POST", "path": "zz-backfill-unhealable-82",
                                                          "responseMode": "responseNode", "options": {}}},
        {"name": "Split Rows", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 0],
         "parameters": {"mode": "runOnceForAllItems",
                        "jsCode": "return ($json.body.rows || []).map(r => ({ json: r }));"}},
        {"name": "Set Missing Fields", "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [400, 0],
         "onError": "continueRegularOutput", "parameters": {
             "resource": "row", "operation": "update",
             "dataTableId": {"__rl": True, "mode": "id", "value": REGISTRY_TABLE},
             "matchType": "allConditions",
             "filters": {"conditions": [
                 {"keyName": "id", "condition": "eq", "keyValue": "={{ $json.id }}"},
                 {"keyName": "correlation_id", "condition": "isEmpty"}]},
             "columns": {"mappingMode": "defineBelow", "matchingColumns": [], "schema": [], "value": {
                 "correlation_id": "={{ $('Split Rows').item.json.correlation_id }}",
                 "date_precision": "={{ $('Split Rows').item.json.date_precision }}"}},
             "options": {}}},
        {"name": "Respond", "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [600, 0],
         "parameters": {"respondWith": "allIncomingItems", "options": {}}},
    ], "connections": {
        "Webhook": {"main": [[{"node": "Split Rows", "type": "main", "index": 0}]]},
        "Split Rows": {"main": [[{"node": "Set Missing Fields", "type": "main", "index": 0}]]},
        "Set Missing Fields": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
    }}


def main():
    plan = json.load(open(PLAN, encoding="utf-8"))
    assert len(plan) == 82 and all(p["correlation_id"] and p["date_precision"] for p in plan)
    print(f"plan: {len(plan)} rows, e.g. {plan[0]['full_name']} (#{plan[0]['id']}) -> {plan[0]['correlation_id']}")
    if not CLEARED_TO_FIRE:
        print("HOLD: CLEARED_TO_FIRE is False -- registry data write, needs Nik's explicit go.")
        sys.exit(1)
    wid = n8n("/api/v1/workflows", "POST", probe_workflow())["id"]
    try:
        n8n(f"/api/v1/workflows/{wid}/activate", "POST", {})
        time.sleep(1.5)
        body = json.dumps({"rows": [{k: p[k] for k in ("id", "correlation_id", "date_precision")} for p in plan]}).encode()
        req = urllib.request.Request(BASE + "/webhook/zz-backfill-unhealable-82", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300, context=ctx) as r:
            out = json.loads(r.read() or b"[]")
        updated = [o for o in out if isinstance(o, dict) and o.get("id") and o.get("correlation_id")]
        errors = [o for o in out if isinstance(o, dict) and o.get("error")]
        print(f"updated rows returned: {len(updated)} / {len(plan)}; errors: {len(errors)}")
        if len(updated) != len(plan) or errors:
            print("MISMATCH -- inspect before anything else:", json.dumps(errors[:3])[:800])
    finally:
        n8n(f"/api/v1/workflows/{wid}/deactivate", "POST", {})
        n8n(f"/api/v1/workflows/{wid}", "DELETE")
        print(f"probe workflow {wid} deactivated + deleted")


if __name__ == "__main__":
    main()
