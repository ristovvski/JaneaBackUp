#!/usr/bin/env python3
"""Deterministic builder for the DNC/observability n8n workflow JSON (Phase 1).

House pattern (mirrors patch_wf1_*.py): logic lives in lib/*.js; this builder embeds the
frozen code blocks VERBATIM into Code nodes so tests/dnc_contract_tests.js drift-check passes
by construction. No secrets are emitted (credential NAMES only). Re-runnable / byte-stable.
"""
import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(ROOT, "subworkflows", "lib")

# STAGE 1 migration finding (2026-08-10, via zz_probe_ live verification): Data Table
# dataTableId "mode: name" resolves fine when a workflow is invoked DIRECTLY (its own trigger),
# but throws "Could not find the data table" when that same workflow is invoked as a SUBWORKFLOW
# (Execute Workflow node -> executeWorkflowTrigger). UpsertLedger and CheckLedger are ALWAYS
# invoked as subworkflows in production, so mode:"name" would have broken 100% of real traffic --
# this was never caught before because no static test executes a live n8n instance. Fix: reference
# by immutable id wherever a real id is known; tables not yet created keep mode:"name" (nothing to
# reference yet) with a comment flagging it needs this dict updated once created.
TABLE_IDS = {
    "dnc_registry_dev": "UOgKwlGsL28lX61O",
    "dnc_domain_block_dev": "ADexvtQHc6cT2yJ6",
    # the estate's shared claims/queue table (WF2_STATE_PORT_2026-09-03) -- reused here (2026-09-14)
    # as the Supabase delta-push queue, family="supabase_delta_registry". A row's PRESENCE means
    # "pending push" here (opposite of this table's usual dedup-guard semantics elsewhere, where
    # presence means "already handled" and rows are kept for a retention window) -- the delta
    # pusher deletes its own claim rows immediately on a successful push. This new family is
    # deliberately NOT added to dnc_claims_prune's retention_days_by_family allowlist: a claim that
    # fails to push should be retained loudly (visible, investigable) rather than silently expired.
    "dnc_claims": "euyostwJYfJefItC",
    # Company DNC (1,373 banned domains), created 2026-09-09, id from the table's own UI URL.
    # (first id given, CUkoLQxUxRuS1Lod, was wrong -- confirmed live, genuinely didn't resolve
    # even in total isolation; corrected id below verified live to resolve + read cleanly.)
    "dnc_domains": "ai4ZiOGqzuJHRYLB",
    # "obs_state": None,            # not yet created in n8n -- mode:"name" fallback stays
}

# Same class of bug as TABLE_IDS above, discovered 2026-08-11 while building WF-4: exec_wf's
# placeholder ("REPLACE_<name>_ID" + mode:"list") was NEVER substituted after deploy -- confirmed
# live on both already-deployed callers (heyreach_reply_to_dnc_ledger, dnc_check_service), which
# would fail immediately with "workflow not found" the moment either is ever actually triggered.
# Neither has been activated yet so no real traffic has hit this. Fix: reference by immutable id
# wherever the target subworkflow is already deployed and its id is known.
WORKFLOW_IDS = {
    "DNC__NormalizeIdentity__v1": "K2M1Z0m1gKX6LdFI",
    "DNC__UpsertLedger__v1": "RolYGL3J2CNg6Yp3",
    "DNC__CheckLedger__v1": "kv7reJYAAgsOV33t",
}


def _data_table_ref(table):
    if table in TABLE_IDS:
        return {"__rl": True, "mode": "id", "value": TABLE_IDS[table]}
    return {"__rl": True, "mode": "name", "value": table}


def block(fname, marker):
    src = open(os.path.join(LIB, fname), encoding="utf-8").read()
    m = re.search(r"//\s*>>> %s >>>\n(.*?)\n//\s*<<< %s <<<" % (re.escape(marker), re.escape(marker)),
                  src, re.S)
    if not m:
        raise SystemExit("marker %s not found in %s" % (marker, fname))
    return m.group(1)


NORM = block("normalize_v1.js", "normalize_v1")
MERGE = block("merge_v1.js", "merge_v1")
EXPIRE = block("expire_v1.js", "expire_v1")
OBS = block("obs_v1.js", "obs_v1")
REASON = block("reason_v1.js", "reason_v1")  # STAGE 1 migration addition — additive only

# ---- node factories --------------------------------------------------------
def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_"),
         "name": name, "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def code_node(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code",
                {"jsCode": js, "mode": "runOnceForAllItems"}, x, y, tv=2)


def code_node_per_item(name, js, x, y=300):
    # runOnceForEachItem: required whenever the JS uses $json (the CURRENT item) or a paired-item
    # accessor like $('SomeNode').item.json to correlate back to an upstream node -- those only
    # resolve correctly in per-item mode. Using code_node()'s default runOnceForAllItems here
    # silently collapses N items down to 1 real bug found live 2026-08-11 in the projections
    # sweep's first real execution: "PD Classify" and "SL Classify" each dropped hundreds of items
    # to a single output because $json/.item only ever saw the first item under that mode.
    return node(name, "n8n-nodes-base.code",
                {"jsCode": js, "mode": "runOnceForEachItem"}, x, y, tv=2)


def set_config(assignments, x=-400):
    a = []
    for i, (k, v, t) in enumerate(assignments):
        a.append({"id": str(i + 1), "name": k, "value": v, "type": t})
    return node("CONFIG", "n8n-nodes-base.set",
                {"assignments": {"assignments": a}, "includeOtherFields": True, "options": {}},
                x, tv=3.4)


def trigger(x=-600):
    return node("When Called", "n8n-nodes-base.executeWorkflowTrigger", {}, x, tv=1)


def dt_get(name, keyName, keyValueExpr, x, table="dnc_registry_dev", y=300):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": _data_table_ref(table),
        "matchType": "anyCondition",
        "filters": {"conditions": [{"keyName": keyName, "condition": "eq", "keyValue": keyValueExpr}]},
        "options": {}
    }, x, y, tv=1, extra={"alwaysOutputData": True})


def dt_get_or2(name, keyName1, keyValueExpr1, keyName2, keyValueExpr2, x, table="dnc_registry_dev", y=300):
    # ONE lookup matching EITHER column, verified live 2026-08-26 before use (2 synthetic items,
    # one matching only via the second column, correctly returned exactly that row). Exists
    # specifically to avoid a two-separate-lookups-plus-Merge shape: found live the same day that
    # feeding two parallel single-column dt_get nodes into a Merge("append") node does NOT
    # reliably wait for both branches before firing downstream -- it fired Classify Batch once per
    # branch ARRIVAL, each time with only that branch's partial results, silently misclassifying
    # Dennis (the known-blocked fixture) as CLEAN because the empty LinkedIn-branch firing beat
    # the real Email-branch match to the response. One query, no merge, no barrier to get wrong.
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": _data_table_ref(table),
        "matchType": "anyCondition",
        "filters": {"conditions": [
            {"keyName": keyName1, "condition": "eq", "keyValue": keyValueExpr1},
            {"keyName": keyName2, "condition": "eq", "keyValue": keyValueExpr2},
        ]},
        "options": {}
    }, x, y, tv=1, extra={"alwaysOutputData": True})


def dt_upsert(name, value_map, matching, x, table="dnc_registry_dev"):
    # n8n's upsert operation requires filters.conditions matching `matching` -- NOT optional,
    # NOT inferred from matchingColumns. Missing this throws "At least one condition is required"
    # at actual runtime (caught 2026-08-10 by zz_probe_ live verification; every static test passed
    # anyway because none of them execute a real n8n instance).
    conditions = [{"keyName": col, "condition": "eq", "keyValue": value_map[col]} for col in matching]
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "upsert",
        "dataTableId": _data_table_ref(table),
        "matchType": "allConditions",
        "filters": {"conditions": conditions},
        "columns": {"mappingMode": "defineBelow", "value": value_map,
                    "matchingColumns": matching, "schema": []},
        "options": {}
    }, x, tv=1, extra={"onError": "stopWorkflow", "retryOnFail": False})


def exec_wf(name, sub_name, x, y=300):
    # mode: "each" -- NOT "once". Found live 2026-08-12 (S3 Surfe backfill's real fire): "once"
    # batches every fan-out item reaching this node in one execution into a SINGLE subworkflow
    # call, but DNC__UpsertLedger__v1/DNC__CheckLedger__v1 are both written assuming single-item
    # semantics ($input.first() in prep_js) -- with "once", only the FIRST of N items was ever
    # processed, the rest silently dropped with no error, no warning, execution status "success"
    # throughout. Caught only because a post-fire wire-check ("verify source_signal on the wire")
    # found 1 registry row where 24 were expected. Verified the fix directly: "each" invokes the
    # subworkflow once per item, confirmed via 3 items with distinct emails all appearing correctly
    # in the output (not the same first item's result three times). WF4 sheet intake and
    # heyreach_reply_to_dnc_ledger both only ever call this with 1 item today so they never
    # triggered the bug in practice, but "once" was never correct there either -- fixed at the
    # helper level so no caller can regress into this again.
    if sub_name in WORKFLOW_IDS:
        workflow_id = {"__rl": True, "mode": "id", "value": WORKFLOW_IDS[sub_name]}
    else:
        workflow_id = {"__rl": True, "mode": "list", "value": "REPLACE_" + sub_name + "_ID",
                        "cachedResultName": sub_name}
    return node(name, "n8n-nodes-base.executeWorkflow", {
        "source": "database", "workflowId": workflow_id, "mode": "each", "options": {}
    }, x, y, tv=1.2)


def if_node(name, left_expr, right_val, x, y=300):
    return node(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "strict"},
                       "combinator": "and",
                       "conditions": [{"leftValue": left_expr, "rightValue": right_val,
                                       "operator": {"type": "string", "operation": "equals"}}]}
    }, x, y, tv=2)


def schedule_daily(name, hour, minute, x, y=300):
    return node(name, "n8n-nodes-base.scheduleTrigger", {
        "rule": {"interval": [{"field": "cronExpression",
                               "expression": "%d %d * * *" % (minute, hour)}]}
    }, x, y, tv=1.2)


def schedule_interval(name, minutes, x, y=300):
    return node(name, "n8n-nodes-base.scheduleTrigger", {
        "rule": {"interval": [{"field": "minutes", "minutesInterval": minutes}]}
    }, x, y, tv=1.2)


def dt_get_all_not_empty(name, keyName, x, table="dnc_registry_dev", y=300):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": _data_table_ref(table),
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": keyName, "condition": "isNotEmpty"}]},
        "options": {}
    }, x, y, tv=1, extra={"alwaysOutputData": True})


def dt_get_all(name, keyName, keyValueExpr, x, table="dnc_registry_dev", y=300):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": _data_table_ref(table),
        "returnAll": True, "matchType": "anyCondition",
        "filters": {"conditions": [{"keyName": keyName, "condition": "eq", "keyValue": keyValueExpr}]},
        "options": {}
    }, x, y, tv=1, extra={"alwaysOutputData": True})


def dt_update(name, value_map, conditions, x, table="dnc_registry_dev", y=300):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "update",
        "dataTableId": _data_table_ref(table),
        "matchType": "allConditions",
        "filters": {"conditions": conditions},
        "columns": {"mappingMode": "defineBelow", "value": value_map, "matchingColumns": [], "schema": []},
        "options": {}
    }, x, y, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})


def dt_claim_enqueue(name, claim_key_expr, family, workflow_name, evidence_expr, x, y=300):
    # Supabase delta-push queue entry. onError:continueErrorOutput (NOT dt_upsert's default
    # stopWorkflow) -- a failure to enqueue a sync claim must never block or fail the real DNC
    # write it's chained after; the delta pusher simply won't see this row until the next writer
    # touches it or the nightly reconcile catches it. Both output branches are always wired to the
    # same next node by the caller (success/failure look identical downstream: fire-and-forget).
    value_map = {
        "claim_key": claim_key_expr, "family": family, "workflow": workflow_name,
        "event_time": "={{ $now.toISO() }}", "claimed_at": "={{ $now.toISO() }}",
        "evidence": evidence_expr,
    }
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "upsert",
        "dataTableId": _data_table_ref("dnc_claims"),
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq", "keyValue": claim_key_expr}]},
        "columns": {"mappingMode": "defineBelow", "value": value_map,
                    "matchingColumns": ["claim_key"], "schema": []},
        "options": {}
    }, x, y, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2})


# Claim key for an enqueue chained directly after a dt_update/dt_upsert on dnc_registry_dev: that
# node's own output IS the written row (verified live 2026-09-24 on PD Mark Done: full row incl. id).
REGISTRY_ROW_CLAIM_KEY_EXPR = "={{ 'supabase_delta_registry|' + $json.id }}"
REGISTRY_ROW_CLAIM_EVIDENCE_EXPR = "={{ 'identity_key=' + ($json.identity_key || '') }}"
SWEEP_CLAIM_KEY_EXPR = REGISTRY_ROW_CLAIM_KEY_EXPR
SWEEP_CLAIM_EVIDENCE_EXPR = REGISTRY_ROW_CLAIM_EVIDENCE_EXPR


def dt_upsert_tbl(name, value_map, matching, x, table, y=300):
    n = dt_upsert(name, value_map, matching, x, table)
    n["position"] = [x, y]
    return n


def split_out(name, field, x, y=300):
    return node(name, "n8n-nodes-base.splitOut",
                {"fieldToSplitOut": field, "options": {}}, x, y, tv=1)


def if_bool(name, expr, x, y=300):
    return node(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"},
                       "combinator": "and",
                       "conditions": [{"leftValue": expr, "rightValue": True,
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}
    }, x, y, tv=2)


def http_get_smartlead(name, url_expr, qs_pairs, x, y=300, cred="Smartlead DEV (readonly)"):
    # httpQueryAuth is a GENERIC credential type (genericAuth=true in its own n8n source) -- it
    # is only wired up by the HTTP Request node's execute() when authentication=
    # "genericCredentialType" + genericAuthType="httpQueryAuth". The "predefinedCredentialType" +
    # nodeCredentialType combo (used here since Build 1) is for credential types tied to a real
    # dedicated node implementation and silently does NOT inject the query param for a generic
    # type -- the request goes out unauthenticated. Never caught because every prior user of this
    # helper kept a REPLACE_ME placeholder and was never actually executed with a real credential
    # until the 2026-08-11 projections-sweep build. Live-verified against Pipedrive with a real
    # credential before propagating this fix.
    return node(name, "n8n-nodes-base.httpRequest", {
        "method": "GET", "url": url_expr,
        "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
        "sendQuery": True,
        "queryParameters": {"parameters": [{"name": k, "value": v} for k, v in qs_pairs]},
        "options": {}
    }, x, y, tv=4.2, extra={
        "credentials": {"httpQueryAuth": {"id": "REPLACE_ME", "name": cred}},
        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 4, "waitBetweenTries": 2500})


# Real, working httpQueryAuth credentials created 2026-08-11 via POST /api/v1/credentials for the
# projections sweep -- n8n's public API supports credential creation (unlike listing), so these
# were created directly rather than left as REPLACE_ME placeholders, matching the already-baked-in
# Slack credential pattern once a credential is confirmed real and working.
PIPEDRIVE_CRED = {"id": "DEFM2qykN8B2lqzw", "name": "Pipedrive API (DNC projections)"}
SMARTLEAD_CRED = {"id": "3o6NEljtQ1moYYGp", "name": "Smartlead API (DNC projections)"}
# Routine-vs-final Slack routing, 2026-08-12 (Nik): dry-runs/chunk progress -> #gtm-telemetry;
# ops (OPS_CHANNEL, "C0B8GCVNR5W") gets final results and questions only. Applies to
# dnc_projections_sweep, dnc_s3_creation_watcher, dnc_s3_surfe_backfill -- every other workflow's
# single-channel alert_channel/dev_channel_guard behavior is unaffected.
OPS_CHANNEL = "C0B8GCVNR5W"
TELEMETRY_CHANNEL = "C0BQM1X9ZUY"
# #alerts -- confirmed by Nik 2026-09-14, distinct from OPS_CHANNEL (#niks-channel, his own
# coordination channel). Monitor/drift/health-check lines (gate monitor, Supabase reconcile drift,
# and future additions of that kind) go here, not to ops.
ALERTS_CHANNEL = "C0BTUHSSM3K"


def http_pipedrive(name, method, url_expr, x, y=300, body_expr=None, paginate=False, max_requests=10):
    # No throttle at all caused a real 85% failure rate (1934/2264) hitting Pipedrive's rate
    # limiter live 2026-08-11 -- "Request failed with status code 429" on nearly every call once
    # sent back-to-back with no spacing. n8n's own error message names the fix: batching options.
    params = {
        "method": method, "url": url_expr,
        "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 400}}},
    }
    if paginate:
        # Auditor finding 2026-08-11 (pre-fire review): a v1 list read with a default page size of
        # 100 was being treated as always-one-page BY ASSUMPTION, not proven -- same defect family
        # as WF-2's off-by-one resolver bugs (silent truncation past page 1). Pipedrive's own
        # additional_data.pagination.more_items_in_collection is the authoritative signal; n8n's
        # native pagination (not a hand-rolled loop) follows it until false. maxRequests=10 is a
        # sane upper bound (10 * limit 100 = 1000 leads for one person, far beyond plausible) so a
        # malformed completion expression can't spin forever.
        params["options"]["pagination"] = {"pagination": {
            "paginationMode": "updateAParameterInEachRequest",
            "parameters": {"parameters": [
                {"type": "qs", "name": "start",
                 "value": "={{ $response.body.additional_data.pagination.start + "
                          "$response.body.additional_data.pagination.limit }}"},
            ]},
            "paginationCompleteWhen": "other",
            "completeExpression": "={{ !$response.body.additional_data.pagination.more_items_in_collection }}",
            "limitPagesFetched": True, "maxRequests": max_requests, "requestInterval": 400,
        }}
    if body_expr is not None:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = body_expr
    return node(name, "n8n-nodes-base.httpRequest", params, x, y, tv=4.2, extra={
        "credentials": {"httpQueryAuth": PIPEDRIVE_CRED},
        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 4, "waitBetweenTries": 2500})


def http_smartlead(name, method, url_expr, x, y=300, body_expr=None):
    # Cloudflare (fronting server.smartlead.ai) blocks Python's/n8n's default User-Agent with a
    # 403 "Error 1010: Access denied" -- confirmed live 2026-08-11 while building
    # dnc_smartlead_resolve.py. A browser-shaped UA header clears it.
    params = {
        "method": method, "url": url_expr,
        "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "User-Agent", "value": "Mozilla/5.0 janea-backfill/1.0"}]},
        # same rate-limit lesson as Pipedrive -- 786/987 failed with no throttle live 2026-08-11.
        # The standalone dnc_smartlead_resolve.py script used 0.3s and had zero errors on the same
        # 987 candidates, so 350ms here is consistent with a value already proven to work.
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 350}}},
    }
    if body_expr is not None:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = body_expr
    return node(name, "n8n-nodes-base.httpRequest", params, x, y, tv=4.2, extra={
        "credentials": {"httpQueryAuth": SMARTLEAD_CRED},
        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 4, "waitBetweenTries": 2500})


def slack_post(name, text_expr, x, y=300, channel_expr=None, extra_props=None):
    # channel_expr defaults to the static CONFIG.alert_channel (every pre-2026-08-12 call site) --
    # pass "={{ $json.target_channel }}" for workflows that route per-post between the ops channel
    # (final results) and #gtm-telemetry (routine dry-runs/chunk progress).
    #
    # RETRY/ERROR BEHAVIOR, documented 2026-08-20 (found live via the S3 conflict-alert crash --
    # "channel_not_found" killed the whole parent execution): this helper sets NEITHER
    # `retryOnFail` NOR `onError` -- every Slack post in this project inherits n8n's node defaults
    # (no automatic retry; onError defaults to stopping the whole execution on failure). That is a
    # real, live gap: a transient Slack API blip or a misconfigured channel on ANY of the ~15 posts
    # built from this helper crashes whatever workflow calls it, not just the alert. Only
    # "Slack Conflict Alert" (below, in DNC__UpsertLedger__v1 -- called from every S1-S4/reversal
    # workflow) has been opted out of that default so far, via extra_props, because it's the one
    # that actually crashed live; the other ~14 call sites still share this same exposure and
    # deserve the same fix, not yet done project-wide.
    extra = {"credentials": {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}}}
    if extra_props:
        extra.update(extra_props)
    return node(name, "n8n-nodes-base.slack", {
        "resource": "message", "operation": "post", "select": "channel",
        "channelId": {"__rl": True, "mode": "id",
                      "value": channel_expr or "={{ $('CONFIG').first().json.alert_channel }}"},
        "text": text_expr, "otherOptions": {}
    }, x, y, tv=2.2, extra=extra)


SEND_GUARD_JS = (
    "// Amendment 3: hard-fail unless the target channel is the designated test channel in dev.\n"
    "// The expected channel is configurable per-workflow (cfg.dev_channel_guard) so a workflow\n"
    "// with its own confirmed-correct dev/ops channel isn't forced onto the historical default --\n"
    "// falls back to that default for every workflow that doesn't set it, so this is additive.\n"
    "//\n"
    "// dev_channel_guard_list added 2026-08-12 (Nik's routine-vs-final channel split: dry-runs/\n"
    "// chunk progress -> #gtm-telemetry, final results/questions -> ops) -- a workflow can now be\n"
    "// dev-valid for EITHER of two channels, picked per-post via $json.target_channel, not just one\n"
    "// static alert_channel. Every workflow that doesn't set dev_channel_guard_list keeps the exact\n"
    "// prior single-channel behavior unchanged.\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const ch = ($json && $json.target_channel) || cfg.alert_channel;\n"
    "const allowed = cfg.dev_channel_guard_list\n"
    "  ? JSON.parse(cfg.dev_channel_guard_list)\n"
    # fallback fixed 2026-08-20: C0BFE6KAN8J (#nik-test-channel) is unreachable by the bot
    # credential ("Smartlead Slack") -- confirmed live via the S3 conflict-alert crash
    # ("channel_not_found"). Six workflows relied on this exact literal as BOTH their alert_channel
    # AND (via this fallback) their own dev-mode guard target, so the guard was silently checking
    # "does the post target equal the same dead channel" -- always true, never catching anything,
    # right up until the post itself failed. Now matches the same live, reachable channel
    # (OPS_CHANNEL / niks-channel) those six were pointed at below.\n"
    "  : [cfg.dev_channel_guard || '%s'];\n"
    "if (String(cfg.MODE) === 'dev' && !allowed.includes(ch)) {\n"
    "  throw new Error('SEND-GUARD: MODE=dev but target channel=' + ch + ' (must be one of ' + allowed.join(',') + ')');\n"
    "}\n"
    "return $input.all();\n"
) % OPS_CHANNEL


def conns(pairs):
    c = {}
    for src, dst in pairs:
        c.setdefault(src, {"main": [[]]})
        c[src]["main"][0].append({"node": dst, "type": "main", "index": 0})
    return c


# WF-ERR Error Handler, confirmed active. Found live 2026-08-11 (fix-owner session's audit): 6
# workflows carried the literal unresolved "REPLACE_CORE__ErrorHandler_ID" placeholder and 3 had
# no errorWorkflow at all -- same class of bug as every other never-substituted REPLACE_ placeholder
# found this build. All 9 workflows were inactive so nothing silently failed, but the moment any
# is ever activated, its failures would be invisible. Fixed at the wf() helper so every workflow
# generated from here on gets a real, working error handler by construction.
CORE_ERROR_HANDLER_ID = "BbrXPABgOaaTJjD6"


def wf(name, nodes, connections):
    return {"name": name, "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "errorWorkflow": CORE_ERROR_HANDLER_ID}, "active": False}


def write(path, obj):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    json.load(open(full, encoding="utf-8"))  # parse-validate
    print("wrote", path, "(%d nodes)" % len(obj["nodes"]))


# ===========================================================================
# 1) DNC__NormalizeIdentity__v1
# ===========================================================================
norm_driver = (
    NORM + "\n\n"
    "const s = ($input.first() && $input.first().json) || {};\n"
    "return [{ json: normalizeIdentityV1({linkedin_url: s.linkedin_url, email: s.email,"
    " full_name: s.full_name, pipedrive_person_id: s.pipedrive_person_id}) }];\n"
)
n_t = trigger()
n_c = code_node("Normalize", norm_driver, -300)
write("subworkflows/DNC__NormalizeIdentity__v1.json",
      wf("DNC__NormalizeIdentity__v1", [n_t, n_c], conns([("When Called", "Normalize")])))

# ===========================================================================
# 2) DNC__UpsertLedger__v1
#
# CALLER NOTE (found live 2026-08-28, dnc_archived_responders_import's first real fire): this
# subworkflow has 3 DISCONNECTED terminal paths -- Send Guard->Slack Conflict Alert (split-
# identity conflict, no write), Upsert Ledger Row->Has Tombstone? (the real write), and Noop
# (idempotent) (already exists identically). A caller invoking this via executeWorkflow(mode:each)
# gets each terminal path back as its OWN numbered output branch, not one merged stream -- wiring
# only branch 0 forward silently undercounts a real batch (found as "processed: 1" instead of 315
# on a real fire; no data was lost, only the report was wrong). Any new driver MUST merge all 3
# branches (see dnc_archived_responders_import's "Merge Outcomes" node) before counting outcomes.
# ===========================================================================
prep_js = (
    NORM + "\n\n" + REASON + "\n\n"
    "const s = ($input.first() && $input.first().json) || {};\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const DOM = ['explicit_opt_out','negative_reply','replied','employee_connection','manual'];\n"
    "let entryType = s.entry_type;\n"
    "if (s.reason) {\n"
    "  if (!REASON_TO_ENTRY_TYPE.hasOwnProperty(s.reason)) throw new Error('DNC upsert: invalid reason ' + s.reason);\n"
    "  entryType = reasonEntryType(s.reason);\n"
    "}\n"
    "if (DOM.indexOf(entryType) === -1) throw new Error('DNC upsert: invalid entry_type ' + entryType);\n"
    # Registry hygiene rule, added 2026-08-14 -- direct fallout of the label-reversal incident: 116
    # reply_dnc rows turned out to be unclassifiable (explicit "do not contact" vs a soft "not
    # interested" decline) because reply_category was never captured when they were written, and
    # by the time anyone needed the distinction, the only fix left was a slow re-derivation project
    # against a different provider's raw data. A schema-level assert, not a habit: every
    # reply_dnc-reasoned row must carry its source category from here on, or the write is rejected
    # outright rather than silently creating tomorrow's version of the same gap.
    "if (s.reason === 'reply_dnc' && !s.reply_category) {\n"
    "  throw new Error('DNC upsert: reply_dnc requires reply_category (a reply-sourced reason with "
    "no captured category is exactly the 116-row gap from 2026-08-14 -- never again silently)');\n"
    "}\n"
    "const norm = normalizeIdentityV1({linkedin_url: s.linkedin_url, email: s.email,"
    " full_name: s.full_name, pipedrive_person_id: s.pipedrive_person_id});\n"
    "const incoming = { entry_type: entryType, source: s.source,"
    " reply_category: (s.reply_category != null ? s.reply_category : null),"
    " full_name: norm.full_name, pipedrive_person_id: norm.pipedrive_person_id,"
    " correlation_id: s.correlation_id || null,"
    " reason: s.reason || null, source_ref: s.source_ref || null,"
    " date_precision: s.date_precision || null, expiry_review_pending: !!s.expiry_review_pending,"
    # S3 addition, 2026-08-12: which trigger fired (creator|surfe|both) -- only ever set by S3
    # callers; every other caller omits it and this stays null, exactly like owner_tag.
    " source_signal: s.source_signal || null };\n"
    "if (!norm.identity_key && !norm.linkedin_unmatchable) { /* nothing to match on */ }\n"
    "return [{ json: { norm, incoming,"
    " li_key: norm.linkedin_url_norm || '__DNC_NO_LI__',"
    " em_key: norm.email_lc || '__DNC_NO_EM__',"
    " config: { ttlMonths: Number(cfg.ttl_months || 6), now: cfg.now } } }];\n"
)
decide_js = (
    MERGE + "\n\n" + REASON + "\n\n"
    "const ctx = $('Normalize + Prep').first().json;\n"
    "const rows = (arr) => arr.filter(x => x && x.json && x.json.identity_key).map(x => x.json);\n"
    "const byLi = rows($('Get by LinkedIn').all());\n"
    "const byEm = rows($('Get by Email').all());\n"
    "let d = dncMergeDecisionV1({norm: ctx.norm, incoming: ctx.incoming, config: ctx.config,"
    " matchedByLinkedin: byLi, matchedByEmail: byEm});\n"
    # split-identity corroboration, 2026-08-20 (Person-69cbb908 case): a conflict is sometimes one
    # person split across two half-rows (a LinkedIn-only employee_connection import row + a
    # pid-carrying row some other caller wrote without LinkedIn), not two different people.
    # dncSplitIdentityMergeV1 only upgrades the action when BOTH the exact shape AND the names
    # corroborate -- any other conflict (including a shape match with names that DON'T
    # corroborate) is untouched and still alerts to a human, exactly as before this fix.\n"
    "let splitMerge = null;\n"
    "if (d.action === 'conflict') {\n"
    "  splitMerge = dncSplitIdentityMergeV1(d, { incoming: ctx.incoming, config: ctx.config });\n"
    "  if (splitMerge.corroborated) {\n"
    "    d = { action: 'merge_split_identity', record: splitMerge.record, tombstone: splitMerge.tombstone };\n"
    "  }\n"
    "}\n"
    "const allCandidates = byLi.concat(byEm);\n"
    "const primary = (d.record && d.record.id != null) ? allCandidates.find(r => r.id === d.record.id) : null;\n"
    "if (d.action !== 'conflict' && d.record) {\n"
    # three-way reason consolidation for the split-merge case: the TOMBSTONED row's own reason
    # must not vanish -- pre-fold it into "existing" alongside the survivor's own reason before
    # the normal incoming-merge runs, or Nik's explicit "old row's reason -> also_flagged" would
    # silently drop whichever side reasonMergeV1 didn't already know to look at.\n"
    "  let existingSignal = (primary && primary.reason) ? { reason: primary.reason,"
    "    source_ref: primary.source_ref || null, source: primary.source || null,"
    "    also_flagged: primary.also_flagged ? JSON.parse(primary.also_flagged) : [] } : null;\n"
    "  if (splitMerge && splitMerge.corroborated && splitMerge.emp_row && splitMerge.emp_row.reason) {\n"
    "    const empSignal = { reason: splitMerge.emp_row.reason,"
    "      source_ref: splitMerge.emp_row.source_ref || null, source: splitMerge.emp_row.source || null,"
    "      also_flagged: splitMerge.emp_row.also_flagged ? JSON.parse(splitMerge.emp_row.also_flagged) : [] };\n"
    "    existingSignal = reasonMergeV1(empSignal, existingSignal);\n"
    "  }\n"
    "  const incomingSignal = ctx.incoming.reason ? { reason: ctx.incoming.reason,"
    "    source_ref: ctx.incoming.source_ref || null, source: ctx.incoming.source || null } : null;\n"
    # merged is null iff NEITHER side ever had a reason -- leave the record's reason-family fields
    # untouched (byte-for-byte Phase-1 behavior). Any other case (reason on either side) must
    # recompute and WRITE these fields, or a reason-less caller (e.g. heyreach tee) touching an
    # already-classified row would silently null out its reason/source_ref/also_flagged on the
    # very next merge -- this was a real bug: the old `if (ctx.incoming.reason && ...)` gate
    # skipped this whole block whenever the CALLER had no reason, even when the EXISTING row did.
    "  const merged = reasonMergeV1(existingSignal, incomingSignal);\n"
    "  if (merged) {\n"
    "    d.record.reason = merged.reason;\n"
    "    d.record.source_ref = merged.source_ref;\n"
    "    d.record.also_flagged = JSON.stringify(merged.also_flagged || []);\n"
    "    d.record.offboard_removable = isOffboardRemovable(merged.reason);\n"
    # fill-if-empty, same philosophy as merge_v1's own linkedin_url_norm/email_lc/full_name handling
    "    d.record.date_precision = (ctx.incoming.date_precision != null) ? ctx.incoming.date_precision"
    "      : ((primary && primary.date_precision) || null);\n"
    "    d.record.expiry_review_pending = (ctx.incoming.expiry_review_pending != null)"
    "      ? !!ctx.incoming.expiry_review_pending : !!(primary && primary.expiry_review_pending);\n"
    "    const override = reasonExpiryOverride(merged.reason, d.record.date_precision);\n"
    "    if (override.override) d.record.expires_at = override.expires_at;\n"
    "    d.record.owner_tag = (merged.reason === 'manual_offboard_eligible') ? (merged.source_ref || null) : null;\n"
    "  }\n"
    # S3 addition, 2026-08-12: fill-or-union, never overwritten to a NARROWER value. First hit
    # sets it; a later hit with the SAME signal is a no-op; a later hit with the OTHER signal
    # upgrades to 'both' (e.g. the creator-watch caught it first, a later Surfe backfill pass finds
    # the same row also matches) -- and 'both' never downgrades back to a single signal.
    "  if (ctx.incoming.source_signal) {\n"
    "    const existingSig = (primary && primary.source_signal) || null;\n"
    "    const incSig = ctx.incoming.source_signal;\n"
    "    d.record.source_signal = (!existingSig || existingSig === incSig) ? incSig : 'both';\n"
    "  }\n"
    "}\n"
    # projections_state: initialize the 3-pending default on a true INSERT (no existing row); on
    # an UPDATE/merge, carry the PRIMARY row's existing value forward untouched -- merge_v1's own
    # `merged` record never carries this field at all, so leaving this unguarded would silently
    # null out a projection the Stage-2 sweep already marked done|skipped|failed on the very next
    # live event to touch the row (the same class of bug just fixed above for reason/source_ref).
    "if (d.record && d.record.projections_state == null) {\n"
    "  if (d.action === 'insert') {\n"
    "    d.record.projections_state = JSON.stringify({ pipedrive: 'pending', smartlead: 'pending', heyreach: 'pending' });\n"
    "  } else {\n"
    "    let proj = null;\n"
    "    try { proj = (primary && primary.projections_state) ? JSON.parse(primary.projections_state) : null; } catch (e) {}\n"
    # re-eligibility fix, 2026-08-20: found live -- Person-83a8d74b's Aug-11 onboarding-import row
    # stayed stuck at pipedrive:'skipped:no_person' even after the Aug-19 backfill linked her
    # pipedrive_person_id, because this carry-forward blindly copied the OLD stored value forward
    # without ever re-checking whether the reason it was skipped still holds. A person_id that was
    # unknown at write time but is now known must become 'pending' again, or the Stage-2 sweep's
    # own pending-only filter skips the row forever even though the original skip reason is gone.
    # Scoped to exactly this one transition (skipped:no_person -> pending, person_id now known) --
    # never touches skipped:no_email/failed:*/done, which have their own, unrelated causes.\n"
    "    if (proj && proj.pipedrive === 'skipped:no_person' && d.record.pipedrive_person_id != null) {\n"
    "      proj.pipedrive = 'pending';\n"
    "    }\n"
    "    d.record.projections_state = proj ? JSON.stringify(proj) : null;\n"
    "  }\n"
    "}\n"
    "const dup = Math.max(0, (byLi.length + byEm.length) - 1);\n"
    "return [{ json: Object.assign({}, d, { duplicates_seen: dup,"
    " correlation_id: ctx.incoming.correlation_id, unmatchable: (!ctx.norm.identity_key) }) }];\n"
)
conflict_alert_failed_js = (
    # error-output terminal for "Slack Conflict Alert" (2026-08-20) -- the conflict itself is
    # never lost even when the alert can't send: it's already fully captured in this same
    # execution's "Decide" node output, which n8n retains regardless. This node exists so the
    # branch has a real dead end that SAYS "the human-facing alert failed" instead of either (a)
    # crashing the caller, or (b) silently succeeding with no trace that the alert never arrived.\n"
    "const ctx = $('Decide').first().json;\n"
    "return [{ json: {\n"
    "  alert_failed: true,\n"
    "  correlation_id: ctx.correlation_id,\n"
    "  linkedin_row_id: (ctx.linkedin_row && ctx.linkedin_row.id) || null,\n"
    "  email_row_id: (ctx.email_row && ctx.email_row.id) || null,\n"
    "  note: 'DNC conflict Slack alert failed to send -- see this execution\\'s Decide node for "
    "the full conflict detail. No registry write happened either way (conflicts never write).',\n"
    "} }];\n"
)
# value map for upsert: write every ledger column from the decided record
UP_VALUE = {
    "identity_key": "={{ $json.record.identity_key }}",
    "linkedin_url_norm": "={{ $json.record.linkedin_url_norm }}",
    "email_lc": "={{ $json.record.email_lc }}",
    "full_name": "={{ $json.record.full_name }}",
    "pipedrive_person_id": "={{ $json.record.pipedrive_person_id }}",
    "entry_type": "={{ $json.record.entry_type }}",
    "source": "={{ $json.record.source }}",
    "reply_category": "={{ $json.record.reply_category }}",
    "status": "={{ $json.record.status }}",
    "added_at": "={{ $json.record.added_at }}",
    "expires_at": "={{ $json.record.expires_at }}",
    "removed_at": "={{ $json.record.removed_at }}",
    "removed_reason": "={{ $json.record.removed_reason }}",
    "correlation_id": "={{ $json.record.correlation_id }}",
    "norm_v": "={{ $json.record.norm_v }}",
    # STAGE 1 migration additions — additive, nullable; absent/undefined for old (non-reason) callers
    "reason": "={{ $json.record.reason }}",
    "source_ref": "={{ $json.record.source_ref }}",
    "also_flagged": "={{ $json.record.also_flagged }}",
    "date_precision": "={{ $json.record.date_precision }}",
    "offboard_removable": "={{ $json.record.offboard_removable }}",
    "expiry_review_pending": "={{ $json.record.expiry_review_pending }}",
    "owner_tag": "={{ $json.record.owner_tag }}",
    "projections_state": "={{ $json.record.projections_state }}",
    # S3 addition, 2026-08-12: NOT YET a real Data Table column (UI-only creation, not done yet --
    # see dnc_registry_dev.schema.yaml). Included here so the write is target-correct the moment the
    # column exists; do not activate any S3 workflow before it's confirmed created.
    "source_signal": "={{ $json.record.source_signal }}",
}
u_nodes = [
    trigger(-800),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("ttl_months", 6, "number"), ("now", "={{ $now.toISO() }}", "string"),
                ("module", "DNC__UpsertLedger__v1", "string")], x=-600),
    code_node("Normalize + Prep", prep_js, -380),
    dt_get("Get by LinkedIn", "linkedin_url_norm", "={{ $('Normalize + Prep').first().json.li_key }}", -160),
    dt_get("Get by Email", "email_lc", "={{ $('Normalize + Prep').first().json.em_key }}", 60),
    code_node("Decide", decide_js, 280),
    node("Route", "n8n-nodes-base.switch", {
        "rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict"},
                            "combinator": "and",
                            "conditions": [{"leftValue": "={{ $json.action }}", "rightValue": "conflict",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "outputKey": "conflict"},
            {"conditions": {"options": {"caseSensitive": True, "typeValidation": "strict"},
                            "combinator": "and",
                            "conditions": [{"leftValue": "={{ $json.action }}", "rightValue": "noop",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "outputKey": "noop"}
        ]}, "options": {"fallbackOutput": "extra"}
    }, 500, tv=3),
    code_node("Send Guard", SEND_GUARD_JS, 720, y=140),
    # crashed live 2026-08-20: "channel_not_found" on the (now-fixed) dead alert_channel killed
    # the ENTIRE parent execution -- every S1-S4/reversal caller of this subworkflow inherits this
    # node, so an alert-delivery failure must never be allowed to take down the actual write path.
    # onError:continueErrorOutput + a bounded retry (matching the dt_update/dt_delete precedent
    # elsewhere in this file) -- a real conflict still needs a human to see it, so failure gets
    # logged to a dead-end node instead of silently vanishing, per the OOM-postmortem's
    # "unwired onError is the same bug as no onError" lesson.
    slack_post("Slack Conflict Alert",
               "=:rotating_light: *DNC conflict* — LinkedIn and email resolve to different people; "
               "NO write.\\ncorrelation_id: `{{ $('Decide').first().json.correlation_id }}` · "
               "execution: `{{ $execution.id }}`\\nlinkedin_row: `{{ JSON.stringify($('Decide').first().json.linkedin_row) }}`\\n"
               "email_row: `{{ JSON.stringify($('Decide').first().json.email_row) }}`", 940, y=140,
               extra_props={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3}),
    code_node("Conflict Alert Failed", conflict_alert_failed_js, 1160, y=220),
    node("Noop (idempotent)", "n8n-nodes-base.noOp", {}, 720, y=300),
    dt_upsert_tbl("Upsert Ledger Row", UP_VALUE, ["identity_key"], 720, "dnc_registry_dev", y=460),
    # Supabase Phase 2 delta pusher (2026-09-14): every real ledger write enqueues a claim so the
    # delta pusher knows to push this row's current state to Supabase. Chained directly after the
    # write it's tracking (single-item throughout this subworkflow -- "When Called" always carries
    # exactly 1 item, so no amplification risk chaining a dataTable node here).
    dt_claim_enqueue("Enqueue Supabase Delta",
                      "={{ 'supabase_delta_registry|' + $('Upsert Ledger Row').first().json.id }}",
                      "supabase_delta_registry", "DNC__UpsertLedger__v1",
                      "={{ 'identity_key=' + ($('Decide').first().json.record.identity_key || '') }}",
                      840, y=460),
    # split-identity merge, 2026-08-20: runs after EVERY write (insert/update/merge_split_identity
    # all funnel through "Upsert Ledger Row" via the switch's fallback), and is a true no-op for
    # the first two since $('Decide').first().json.tombstone is only ever set by the corroborated
    # split-merge path. Soft-remove only -- never a hard delete, matching this table's own
    # deletion_policy (dnc_registry_dev.schema.yaml).
    if_bool("Has Tombstone?", "={{ !!$('Decide').first().json.tombstone }}", 960, y=460),
    dt_update("Tombstone Split-Identity Row",
              {"status": "removed",
               "removed_at": "={{ $now.toISO() }}",
               "removed_reason": "={{ 'merged_into:' + $('Decide').first().json.record.id }}"},
              [{"keyName": "id", "condition": "eq", "keyValue": "={{ $('Decide').first().json.tombstone.id }}"}],
              1180, y=460),
    # the LOSING identity's row also changed (soft-removed) and needs its own Supabase push --
    # different row id than the primary enqueue above ($('Decide').first().json.tombstone.id, not
    # $('Upsert Ledger Row')'s own id).
    dt_claim_enqueue("Enqueue Supabase Delta (Tombstone)",
                      "={{ 'supabase_delta_registry|' + $('Decide').first().json.tombstone.id }}",
                      "supabase_delta_registry", "DNC__UpsertLedger__v1",
                      "={{ 'tombstone merged_into:' + $('Decide').first().json.record.identity_key }}",
                      1400, y=460),
]
u_conn = conns([
    ("When Called", "CONFIG"), ("CONFIG", "Normalize + Prep"),
    ("Normalize + Prep", "Get by LinkedIn"), ("Get by LinkedIn", "Get by Email"),
    ("Get by Email", "Decide"), ("Decide", "Route"),
])
# Switch outputs: index 0 conflict, 1 noop, 2 fallback(extra=write -- insert/update/merge_split_identity)
u_conn["Route"] = {"main": [
    [{"node": "Send Guard", "type": "main", "index": 0}],
    [{"node": "Noop (idempotent)", "type": "main", "index": 0}],
    [{"node": "Upsert Ledger Row", "type": "main", "index": 0}],
]}
u_conn.update(conns([("Send Guard", "Slack Conflict Alert"),
                      ("Upsert Ledger Row", "Enqueue Supabase Delta"),
                      ("Tombstone Split-Identity Row", "Enqueue Supabase Delta (Tombstone)")]))
u_conn["Has Tombstone?"] = {"main": [
    [{"node": "Tombstone Split-Identity Row", "type": "main", "index": 0}],
    [],
]}
# "Enqueue Supabase Delta" is fire-and-forget (onError:continueErrorOutput) but must NOT be a dead
# end -- the real flow (Has Tombstone?) continues regardless of whether the claim write succeeded,
# on BOTH output branches.
u_conn["Enqueue Supabase Delta"] = {"main": [
    [{"node": "Has Tombstone?", "type": "main", "index": 0}],
    [{"node": "Has Tombstone?", "type": "main", "index": 0}],
]}
# "Enqueue Supabase Delta (Tombstone)" IS a true dead end on both branches -- nothing follows
# "Tombstone Split-Identity Row" today either, and this node changes nothing about that.
u_conn["Enqueue Supabase Delta (Tombstone)"] = {"main": [[], []]}
# error output (index 1) of a continueErrorOutput node -- must be wired, or this is the exact
# "unwired onError is the same bug as no onError" class the OOM postmortem already named.
u_conn["Slack Conflict Alert"] = {"main": [
    [], [{"node": "Conflict Alert Failed", "type": "main", "index": 0}],
]}
write("subworkflows/DNC__UpsertLedger__v1.json", wf("DNC__UpsertLedger__v1", u_nodes, u_conn))

# ===========================================================================
# 3) DNC__CheckLedger__v1  (read-only lookup)
# ===========================================================================
check_norm_js = (
    NORM + "\n\n"
    "const s = ($input.first() && $input.first().json) || {};\n"
    "const norm = normalizeIdentityV1({linkedin_url: s.linkedin_url, email: s.email});\n"
    "return [{ json: { norm,"
    " li_key: norm.linkedin_url_norm || '__DNC_NO_LI__',"
    " em_key: norm.email_lc || '__DNC_NO_EM__' } }];\n"
)
report_js = (
    "// Read-only classification. Amendment 2: strongest-entry_type-wins across duplicate rows.\n"
    "const STRENGTH = {explicit_opt_out:5, negative_reply:4, replied:3, employee_connection:2, manual:1};\n"
    "const ctx = $('Normalize').first().json;\n"
    "if (!ctx.norm.identity_key) { return [{ json: { result: 'usage_hint', norm: ctx.norm } }]; }\n"
    "const rows = (arr) => arr.filter(x => x && x.json && x.json.identity_key).map(x => x.json);\n"
    "const seen = {}; const all = [];\n"
    "rows($('Get by LinkedIn').all()).concat(rows($('Get by Email').all())).forEach((r) => {\n"
    "  const k = (r.id != null ? 'id:' + r.id : r.identity_key + '|' + r.added_at);\n"
    "  if (!seen[k]) { seen[k] = true; all.push(r); }\n"
    "});\n"
    "if (all.length === 0) { return [{ json: { result: 'clean', norm: ctx.norm } }]; }\n"
    "const pick = (list) => list.slice().sort((a,b) => (STRENGTH[b.entry_type]||0)-(STRENGTH[a.entry_type]||0)"
    " || String(a.added_at||'').localeCompare(String(b.added_at||'')))[0];\n"
    "const active = all.filter((r) => r.status === 'active');\n"
    "if (active.length) { const p = pick(active); return [{ json: { result: 'on_dnc', row: p,"
    " entry_type: p.entry_type, source: p.source, since: p.added_at, expires_at: p.expires_at,"
    " duplicates_seen: all.length - 1, norm: ctx.norm } }]; }\n"
    "const p = pick(all);\n"
    "return [{ json: { result: 'clean_with_history', row: p, was_type: p.entry_type,"
    " until: (p.removed_at || p.expires_at || null), norm: ctx.norm } }];\n"
)
c_nodes = [
    trigger(-800),
    code_node("Normalize", check_norm_js, -560),
    dt_get("Get by LinkedIn", "linkedin_url_norm", "={{ $('Normalize').first().json.li_key }}", -340),
    dt_get("Get by Email", "email_lc", "={{ $('Normalize').first().json.em_key }}", -120),
    code_node("Report", report_js, 100),
]
c_conn = conns([
    ("When Called", "Normalize"), ("Normalize", "Get by LinkedIn"),
    ("Get by LinkedIn", "Get by Email"), ("Get by Email", "Report"),
])
write("subworkflows/DNC__CheckLedger__v1.json", wf("DNC__CheckLedger__v1", c_nodes, c_conn))

# ===========================================================================
# Build 3) heyreach_reply_to_dnc_ledger  (WF-1 reply tee; standalone, never attached by us)
# ===========================================================================
map_js = (
    "// Map WF-1's canonical reply_received event -> DNC__UpsertLedger__v1 input.\n"
    "// INPUT CONTRACT (what WF-1 passes when the human attaches this tee):\n"
    "//   { reply_event_id, linkedin_url, email?, full_name?, pipedrive_person_id?,\n"
    "//     reply_category?, correlation_id }\n"
    "const s = ($input.first() && $input.first().json) || {};\n"
    "if (!s.reply_event_id) throw new Error('tee: reply_event_id required for idempotency');\n"
    "if (!s.linkedin_url && !s.email) throw new Error('tee: need linkedin_url or email');\n"
    "return [{ json: {\n"
    "  linkedin_url: s.linkedin_url || null,\n"
    "  email: s.email || null,\n"
    "  full_name: s.full_name || null,\n"
    "  pipedrive_person_id: (s.pipedrive_person_id != null ? s.pipedrive_person_id : null),\n"
    "  entry_type: 'replied',\n"
    "  source: 'heyreach_reply',\n"
    "  reply_category: (s.reply_category != null ? s.reply_category : null),\n"
    "  correlation_id: s.correlation_id || null,\n"
    "  // idempotency: UpsertLedger is naturally idempotent (merge is a pure fn of preserved\n"
    "  // added_at => replay yields action:noop). This key is carried for audit/trace only.\n"
    "  idempotency_key: 'heyreach:' + s.reply_event_id + ':dnc'\n"
    "} }];\n"
)
b3 = [
    trigger(-820),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("workflow", "heyreach_reply_to_dnc_ledger", "string")], x=-620),
    code_node("Map to Upsert Input", map_js, -400),
    exec_wf("Call DNC__UpsertLedger__v1", "DNC__UpsertLedger__v1", -180),
    if_node("MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", 40),
    code_node("Send Guard", SEND_GUARD_JS, 260, y=180),
    slack_post("Dev Summary (verbose)",
               "=:white_check_mark: DNC tee (dev): reply -> ledger action "
               "`{{ $json.action || 'n/a' }}` for `{{ $('Map to Upsert Input').first().json.linkedin_url "
               "|| $('Map to Upsert Input').first().json.email }}` · idem "
               "`{{ $('Map to Upsert Input').first().json.idempotency_key }}` · exec `{{ $execution.id }}`", 480),
]
b3[5]["position"] = [260, 180]
b3[6]["position"] = [480, 180]
b3_conn = conns([
    ("When Called", "CONFIG"), ("CONFIG", "Map to Upsert Input"),
    ("Map to Upsert Input", "Call DNC__UpsertLedger__v1"),
    ("Call DNC__UpsertLedger__v1", "MODE == dev?"),
])
b3_conn["MODE == dev?"] = {"main": [
    [{"node": "Send Guard", "type": "main", "index": 0}],  # true -> dev summary
    [],                                                     # false -> silent (prod)
]}
b3_conn.update(conns([("Send Guard", "Dev Summary (verbose)")]))
b3_wf = wf("heyreach_reply_to_dnc_ledger", b3, b3_conn)
write("workflows/heyreach_reply_to_dnc_ledger/heyreach_reply_to_dnc_ledger.json", b3_wf)

# ===========================================================================
# Build 4) dnc_expiry_job  (daily flip + weekly digest + dedup self-heal pass)
# ===========================================================================
plan_js = (
    EXPIRE + "\n\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const rows = $input.all().map((x) => x.json).filter((r) => r && r.identity_key);\n"
    "const plan = planExpiryV1({ rows: rows, now: cfg.now, digest_dow: Number(cfg.digest_dow || 1) });\n"
    "return [{ json: plan }];\n"
)
counter_js = (
    "const plan = $('Plan').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const prevRows = $input.all().map((x) => x.json).filter((r) => r && r.state_key);\n"
    "const prev = prevRows.length ? Number(prevRows[0].num_value || 0) : 0;\n"
    "const total = prev + Number(plan.expired_count || 0);\n"
    "return [{ json: { state_key: 'counter:expired_week:' + plan.week_key, state_type: 'counter',\n"
    "  str_value: plan.week_key, num_value: total, updated_at: cfg.now,\n"
    "  is_digest_day: plan.is_digest_day, expired_count: plan.expired_count, dedup_count: plan.dedup_count } }];\n"
)
COND2 = [{"keyName": "identity_key", "condition": "eq", "keyValue": "={{ $json.identity_key }}"},
         {"keyName": "added_at", "condition": "eq", "keyValue": "={{ $json.added_at }}"}]
b4 = [
    schedule_daily("Every day 06:00", 6, 0, -900),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("now", "={{ $now.toISO() }}", "string"), ("digest_dow", 1, "number"),
                ("workflow", "dnc_expiry_job", "string")], x=-700),
    dt_get_all("Get Active Rows", "status", "active", -480),
    code_node("Plan", plan_js, -260),
    # branch A: expire
    split_out("Split Expire", "to_expire", -40, y=80),
    dt_update("Update -> expired", {"status": "expired"}, COND2, 180, y=80),
    # branch B: dedup self-heal
    split_out("Split Dedup", "to_dedup", -40, y=260),
    dt_update("Update -> removed (dedup)",
              {"status": "removed", "removed_reason": "dedup_self_heal",
               "removed_at": "={{ $('CONFIG').first().json.now }}"}, COND2, 180, y=260),
    # branch C: weekly counter + digest
    dt_get("Get Week Counter", "state_key",
           "={{ 'counter:expired_week:' + $('Plan').first().json.week_key }}", -40, table="obs_state"),
    code_node("Counter", counter_js, 180, y=440),
    dt_upsert_tbl("Upsert Week Counter",
                  {"state_key": "={{ $json.state_key }}", "state_type": "counter",
                   "str_value": "={{ $json.str_value }}", "num_value": "={{ $json.num_value }}",
                   "updated_at": "={{ $json.updated_at }}"}, ["state_key"], 400, table="obs_state", y=440),
    if_bool("Digest day?", "={{ $('Counter').first().json.is_digest_day }}", 620, y=440),
    code_node("Send Guard (digest)", SEND_GUARD_JS, 840, y=380),
    slack_post("Slack Weekly Digest",
               "=:bar_chart: *DNC weekly digest* — {{ $('Counter').first().json.num_value }} rows "
               "expired in week {{ $('Plan').first().json.week_key }}"
               "{{ $('Plan').first().json.skipped_review_pending > 0 ? ' · ' + $('Plan').first().json.skipped_review_pending + ' held for manual review (expiry_review_pending)' : '' }}"
               " · exec `{{ $execution.id }}`", 1060),
    # branch D: dev verbose summary
    if_node("MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", -40, y=620),
    code_node("Send Guard (dev)", SEND_GUARD_JS, 180, y=620),
    slack_post("Dev Summary (verbose)",
               "=:broom: dnc_expiry_job (dev): expired `{{ $('Plan').first().json.expired_count }}`, "
               "dedup `{{ $('Plan').first().json.dedup_count }}`, ambiguous-skipped "
               "`{{ $('Plan').first().json.skipped_ambiguous }}`, review-pending-skipped "
               "`{{ $('Plan').first().json.skipped_review_pending }}` · week {{ $('Plan').first().json.week_key }} "
               "· exec `{{ $execution.id }}`", 400),
]
b4[13]["position"] = [1060, 440]   # Slack Weekly Digest
b4[14]["position"] = [-40, 620]    # MODE == dev?
b4[15]["position"] = [180, 620]    # Send Guard (dev)
b4[16]["position"] = [400, 620]    # Dev Summary (verbose)
# appended (not inserted) so the positional overrides above keep pointing at the right nodes.
# Live workflow is ARCHIVE__dnc_expiry_job / inactive (2026-09-24); this keeps the generator correct
# so a re-deploy can't reintroduce a registry writer that bypasses the Supabase delta queue.
b4 += [
    dt_claim_enqueue("Enqueue Supabase Delta (expired)", REGISTRY_ROW_CLAIM_KEY_EXPR,
                      "supabase_delta_registry", "dnc_expiry_job", REGISTRY_ROW_CLAIM_EVIDENCE_EXPR, 400, y=80),
    dt_claim_enqueue("Enqueue Supabase Delta (dedup)", REGISTRY_ROW_CLAIM_KEY_EXPR,
                      "supabase_delta_registry", "dnc_expiry_job", REGISTRY_ROW_CLAIM_EVIDENCE_EXPR, 400, y=260),
]
b4_conn = conns([
    ("Every day 06:00", "CONFIG"), ("CONFIG", "Get Active Rows"), ("Get Active Rows", "Plan"),
    ("Split Expire", "Update -> expired"), ("Split Dedup", "Update -> removed (dedup)"),
    ("Update -> expired", "Enqueue Supabase Delta (expired)"),
    ("Update -> removed (dedup)", "Enqueue Supabase Delta (dedup)"),
    ("Get Week Counter", "Counter"), ("Counter", "Upsert Week Counter"),
    ("Upsert Week Counter", "Digest day?"),
    ("Send Guard (digest)", "Slack Weekly Digest"),
    ("Send Guard (dev)", "Dev Summary (verbose)"),
])
# Plan fans out to 4 branches
b4_conn["Plan"] = {"main": [[
    {"node": "Split Expire", "type": "main", "index": 0},
    {"node": "Split Dedup", "type": "main", "index": 0},
    {"node": "Get Week Counter", "type": "main", "index": 0},
    {"node": "MODE == dev?", "type": "main", "index": 0},
]]}
b4_conn["Digest day?"] = {"main": [
    [{"node": "Send Guard (digest)", "type": "main", "index": 0}], []]}
b4_conn["MODE == dev?"] = {"main": [
    [{"node": "Send Guard (dev)", "type": "main", "index": 0}], []]}
b4_wf = wf("dnc_expiry_job", b4, b4_conn)
write("workflows/dnc_expiry_job/dnc_expiry_job.json", b4_wf)

# ===========================================================================
# Build 5) smartlead_observability_readonly  (R1 + R4 only; R2/R3 DEFERRED; single-campaign MVP)
# READ-ONLY toward Smartlead. Writes only obs_state + Slack.
# ===========================================================================
prep_poll_js = (
    "const cfg = $('CONFIG').first().json;\n"
    "const wm = $input.all().map((x) => x.json).filter((r) => r && r.state_key);\n"
    "let since = wm.length ? wm[0].str_value : null;\n"
    "if (!since) since = new Date(new Date(cfg.now).getTime() - Number(cfg.default_lookback_hours || 48) * 3600000).toISOString();\n"
    "return [{ json: { campaign_id: cfg.campaign_id, since_iso: since, event_time_gt: String(since).slice(0, 10) } }];\n"
)
parse_js = (
    OBS + "\n\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const prep = $('Prep Poll').first().json;\n"
    "const page = ($input.first() && $input.first().json) || {};\n"
    "const fwd = {}; (cfg.forwardable || []).forEach((c) => { fwd[String(c).toLowerCase()] = true; });\n"
    "const metrics = parseLeadsStatisticsV1(page, prep.since_iso, fwd);\n"
    "return [{ json: { metrics, campaign_id: cfg.campaign_id, since_iso: prep.since_iso } }];\n"
)
eval_js = (
    OBS + "\n\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const parsed = $('Parse leads-statistics').first().json;\n"
    "const r1 = $input.all().map((x) => x.json).filter((r) => r && r.state_key);\n"
    "const ev = evaluateR1R4V1({ metrics: parsed.metrics, r1_since: r1.length ? r1[0].str_value : null,\n"
    "  now: cfg.now, config: { campaign_id: cfg.campaign_id, r1_stall_hours: cfg.r1_stall_hours,\n"
    "  r4_delta_threshold: cfg.r4_delta_threshold } });\n"
    "return [{ json: Object.assign({}, ev, { campaign_id: cfg.campaign_id,\n"
    "  max_event_time: parsed.metrics.max_event_time, now: cfg.now,\n"
    "  alerts: ev.alerts.map((a) => Object.assign({}, a, { dedupe_key: 'alert_dedupe:' + a.key })) }) }];\n"
)
fire_js = (
    OBS + "\n\n"
    "const alert = $('Split Alerts').item.json;\n"
    "const ded = $input.all().map((x) => x.json).filter((r) => r && r.state_key);\n"
    "const now = $('CONFIG').first().json.now;\n"
    "return [{ json: Object.assign({}, alert, { fire: !obsIsDeduped(ded[0] || null, now) }) }];\n"
)
b5 = [
    node("Every 30 min", "n8n-nodes-base.scheduleTrigger",
         {"rule": {"interval": [{"field": "minutes", "minutesInterval": 30}]}}, -1000, tv=1.2),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("smartlead_base", "https://server.smartlead.ai/api/v1", "string"),
                ("campaign_id", "REPLACE_WITH_AI4_CAMPAIGN_ID", "string"),
                ("r1_stall_hours", 6, "number"), ("r4_delta_threshold", 25, "number"),
                ("dedupe_hours", 4, "number"), ("default_lookback_hours", 48, "number"),
                ("forwardable", ["interested", "not_interested", "information_request"], "array"),
                ("now", "={{ $now.toISO() }}", "string"),
                ("workflow", "smartlead_observability_readonly", "string")], x=-800),
    dt_get("Get Watermark", "state_key",
           "={{ 'watermark:leads_stats:' + $('CONFIG').first().json.campaign_id }}", -580, table="obs_state"),
    code_node("Prep Poll", prep_poll_js, -360),
    http_get_smartlead("GET leads-statistics",
                       "={{ $('CONFIG').first().json.smartlead_base }}/campaigns/{{ $('Prep Poll').first().json.campaign_id }}/leads-statistics",
                       [("limit", "100"), ("event_time_gt", "={{ $('Prep Poll').first().json.event_time_gt }}")], -140),
    node("Poll Error (skip)", "n8n-nodes-base.noOp", {}, -140, y=520),
    code_node("Parse leads-statistics", parse_js, 80),
    dt_get("Get R1 State", "state_key",
           "={{ 'r1_since:' + $('CONFIG').first().json.campaign_id }}", 300, table="obs_state"),
    code_node("Evaluate R1+R4", eval_js, 520),
    dt_upsert_tbl("Update Watermark",
                  {"state_key": "={{ 'watermark:leads_stats:' + $json.campaign_id }}",
                   "state_type": "watermark", "campaign_id": "={{ $json.campaign_id }}",
                   "str_value": "={{ $json.max_event_time }}", "updated_at": "={{ $json.now }}"},
                  ["state_key"], 740, table="obs_state", y=120),
    dt_upsert_tbl("Update R1 State",
                  {"state_key": "={{ 'r1_since:' + $json.campaign_id }}", "state_type": "watermark",
                   "campaign_id": "={{ $json.campaign_id }}", "str_value": "={{ $json.r1_since_next }}",
                   "updated_at": "={{ $json.now }}"}, ["state_key"], 740, table="obs_state", y=300),
    split_out("Split Alerts", "alerts", 740, y=520),
    dt_get("Get Dedupe", "state_key", "={{ $json.dedupe_key }}", 960, table="obs_state", y=520),
    code_node("Fire?", fire_js, 1180, y=520),
    if_bool("Fire alert?", "={{ $json.fire }}", 1400, y=520),
    code_node("Send Guard", SEND_GUARD_JS, 1620, y=460),
    slack_post("Slack Anomaly Alert",
               "=:warning: *Smartlead {{ $json.rule }}* — campaign `{{ $json.key }}`: {{ $json.msg }}"
               " (replies={{ $json.replies }} categorized={{ $json.categorized }} delta={{ $json.delta }})"
               "\\ncorrelation_id: `obs:{{ $('CONFIG').first().json.campaign_id }}:{{ $json.rule }}` · exec `{{ $execution.id }}`", 1840),
    dt_upsert_tbl("Upsert Dedupe",
                  {"state_key": "={{ $('Fire?').item.json.dedupe_key }}", "state_type": "alert_dedupe",
                   "str_value": "={{ $('Fire?').item.json.rule }}",
                   "expires_at": "={{ $now.plus({hours: $('CONFIG').first().json.dedupe_hours}).toISO() }}",
                   "updated_at": "={{ $('CONFIG').first().json.now }}"}, ["state_key"], 2060, table="obs_state", y=520),
]
b5_conn = conns([
    ("Every 30 min", "CONFIG"), ("CONFIG", "Get Watermark"), ("Get Watermark", "Prep Poll"),
    ("Prep Poll", "GET leads-statistics"),
    ("Parse leads-statistics", "Get R1 State"), ("Get R1 State", "Evaluate R1+R4"),
    ("Split Alerts", "Get Dedupe"), ("Get Dedupe", "Fire?"), ("Fire?", "Fire alert?"),
    ("Send Guard", "Slack Anomaly Alert"), ("Slack Anomaly Alert", "Upsert Dedupe"),
])
# HTTP node: main output -> Parse; error output -> Poll Error (skip)
b5_conn["GET leads-statistics"] = {"main": [
    [{"node": "Parse leads-statistics", "type": "main", "index": 0}],
    [{"node": "Poll Error (skip)", "type": "main", "index": 0}]]}
# Evaluate fans out to watermark update, r1 state update, and alert split
b5_conn["Evaluate R1+R4"] = {"main": [[
    {"node": "Update Watermark", "type": "main", "index": 0},
    {"node": "Update R1 State", "type": "main", "index": 0},
    {"node": "Split Alerts", "type": "main", "index": 0}]]}
b5_conn["Fire alert?"] = {"main": [
    [{"node": "Send Guard", "type": "main", "index": 0}], []]}
b5_wf = wf("smartlead_observability_readonly", b5, b5_conn)
write("workflows/smartlead_observability_readonly/smartlead_observability_readonly.json", b5_wf)

# ===========================================================================
# Build 6) dnc_check_service  (Slack @mention in OPS_CHANNEL -> read-only DNC lookup; retargeted
# 2026-08-20 from the dead C0BFE6KAN8J -- see the CONFIG-channel sweep note near SEND_GUARD_JS)
# ===========================================================================
parse_input_js = (
    "const s = ($input.first() && $input.first().json) || {};\n"
    "const text = String(s.text || (s.event && s.event.text) || '');\n"
    "const channel = s.channel || (s.event && s.event.channel) || '';\n"
    "const ts = s.ts || (s.event && s.event.ts) || '';\n"
    "const ALLOWED = $('CONFIG').first().json.alert_channel;\n"
    "if (channel && channel !== ALLOWED) { return []; }        // ignore mentions in other channels\n"
    "const cleaned = text.replace(/<@[^>]+>/g, ' ').trim();     // strip the bot mention token(s)\n"
    "const url = cleaned.match(/https?:\\/\\/[^\\s|>]*linkedin\\.com[^\\s|>]*/i);\n"
    "const email = cleaned.match(/[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}/);\n"
    "return [{ json: { linkedin_url: url ? url[0] : null, email: email ? email[0] : null,\n"
    "  _channel: channel || ALLOWED, _thread_ts: ts, _raw: cleaned } }];\n"
)
format_reply_js = (
    "const r = ($input.first() && $input.first().json) || {};\n"
    "const ctx = $('Parse Input').first().json;\n"
    "let msg;\n"
    "if (r.result === 'on_dnc') {\n"
    "  msg = ':no_entry: *ON DNC* — `' + r.entry_type + '` since ' + String(r.since).slice(0, 10) +\n"
    "    (r.expires_at ? ' (expires ' + String(r.expires_at).slice(0, 10) + ')' : ' (permanent)') +\n"
    "    ' · source: ' + (r.source || '?');\n"
    "} else if (r.result === 'clean_with_history') {\n"
    "  msg = ':white_check_mark: clean now — *was* on DNC (' + r.was_type + ') until ' + String(r.until || '').slice(0, 10);\n"
    "} else if (r.result === 'clean') {\n"
    "  msg = ':white_check_mark: clean — not on the DNC ledger';\n"
    "} else {\n"
    "  msg = ':information_source: Usage: mention me with a LinkedIn /in/ URL or an email to check DNC status.';\n"
    "}\n"
    "return [{ json: { reply: msg, channel: ctx._channel, thread_ts: ctx._thread_ts } }];\n"
)
b6 = [
    node("On @mention", "n8n-nodes-base.slackTrigger", {
        "trigger": ["app_mention"], "watchWorkspace": False,
        "channelId": {"__rl": True, "mode": "id", "value": OPS_CHANNEL}, "options": {}
    }, -820, tv=1, extra={"credentials": {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}}}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("now", "={{ $now.toISO() }}", "string"), ("workflow", "dnc_check_service", "string")], x=-620),
    code_node("Parse Input", parse_input_js, -400),
    exec_wf("Call DNC__CheckLedger__v1", "DNC__CheckLedger__v1", -180),
    code_node("Format Reply", format_reply_js, 40),
    code_node("Send Guard", SEND_GUARD_JS, 260),
    slack_post("Slack Reply", "={{ $json.reply }}", 480),
]
b6_conn = conns([
    ("On @mention", "CONFIG"), ("CONFIG", "Parse Input"),
    ("Parse Input", "Call DNC__CheckLedger__v1"),
    ("Call DNC__CheckLedger__v1", "Format Reply"),
    ("Format Reply", "Send Guard"), ("Send Guard", "Slack Reply"),
])
b6_wf = wf("dnc_check_service", b6, b6_conn)
write("workflows/dnc_check_service/dnc_check_service.json", b6_wf)

# ===========================================================================
# Build 7) dnc_wf4_sheet_intake  (Stage 2 / WF-4: sheet watch -> normalize -> CheckLedger dedupe
# -> UpsertLedger insert -> NO projections. Per owner GO 2026-08-11.)
# Sheet confirmed live 2026-08-11: https://docs.google.com/spreadsheets/d/
#   10qCtWMwx3e_0YuT9AuSjuF_Q15mOj6EAGO-RTKRl2-o (tab "Sheet1", gid=0), header row exactly:
#   linkedin_url, email, full_name, reason, added_by, notes -- confirmed via public CSV export,
#   sheet was empty (0 data rows) at build time. `notes` has no registry column -- surfaced only
#   in the dev-mode Slack summary, never persisted (no schema field exists for free text).
# ===========================================================================
WF4_SHEET_DOC_ID = "10qCtWMwx3e_0YuT9AuSjuF_Q15mOj6EAGO-RTKRl2-o"
WF4_REASON_DOMAIN = ["client", "unsubscribe", "reply_dnc", "manual_offboard_eligible", "manual_sheet", "offboard"]

wf4_normalize_js = (
    "const s = ($input.first() && $input.first().json) || {};\n"
    "const REASON_DOMAIN = " + json.dumps(WF4_REASON_DOMAIN) + ";\n"
    "const clean = (v) => { const t = (v == null ? '' : String(v)).trim(); return t || null; };\n"
    "const linkedin_url = clean(s.linkedin_url);\n"
    "const email = clean(s.email);\n"
    "const full_name = clean(s.full_name);\n"
    "const source_ref = clean(s.added_by);\n"
    "const notes = clean(s.notes);\n"
    "const rawReason = (clean(s.reason) || '').toLowerCase();\n"
    # unrecognized/blank reason defaults to manual_sheet -- the domain's own designated fallback
    # for exactly this case (a human-curated sheet row with no stronger classification given).
    "const reason = REASON_DOMAIN.includes(rawReason) ? rawReason : 'manual_sheet';\n"
    "if (!linkedin_url && !email) {\n"
    "  return [{ json: { skip: true, skip_reason: 'no linkedin_url or email in sheet row',"
    " full_name, source_ref, notes, raw: s } }];\n"
    "}\n"
    "return [{ json: { skip: false, linkedin_url, email, full_name, reason, source_ref, notes,\n"
    "  correlation_id: 'wf4_sheet:' + $execution.id + ':' + (linkedin_url || email) } }];\n"
)
wf4_build_check_input_js = (
    "const s = $('Normalize Sheet Row').first().json;\n"
    "return [{ json: { linkedin_url: s.linkedin_url, email: s.email } }];\n"
)
wf4_interpret_check_js = (
    "const check = $input.first().json;\n"
    "const s = $('Normalize Sheet Row').first().json;\n"
    "return [{ json: Object.assign({}, s, { already_on_dnc: check.result === 'on_dnc',"
    " check_result: check.result }) }];\n"
)
wf4_build_upsert_input_js = (
    "const s = $('Normalize Sheet Row').first().json;\n"
    "return [{ json: {\n"
    "  linkedin_url: s.linkedin_url, email: s.email, full_name: s.full_name,\n"
    "  reason: s.reason, source: 'manual_sheet', source_ref: s.source_ref,\n"
    # sheet rows are live-dated (added_at = now, always fully known) -- 'derived' is correct, not
    # 'unknown' (which exists for legacy/backfilled rows of uncertain date, not this).
    "  date_precision: 'derived', expiry_review_pending: false,\n"
    "  pipedrive_person_id: null, correlation_id: s.correlation_id,\n"
    "} }];\n"
)
wf4_outcome_malformed_js = (
    "const s = $json;\n"
    "return [{ json: { outcome: 'skipped_malformed', linkedin_url: s.linkedin_url || null,\n"
    "  email: s.email || null, full_name: s.full_name || null, source_ref: s.source_ref || null,\n"
    "  notes: s.notes || null, detail: s.skip_reason } }];\n"
)
wf4_outcome_on_dnc_js = (
    "const s = $json;\n"
    "return [{ json: { outcome: 'skipped_already_on_dnc', linkedin_url: s.linkedin_url,\n"
    "  email: s.email, full_name: s.full_name, source_ref: s.source_ref, notes: s.notes,\n"
    "  detail: s.check_result } }];\n"
)
wf4_outcome_processed_js = (
    "const upsertResult = $input.first().json;\n"
    "const s = $('Normalize Sheet Row').first().json;\n"
    # UpsertLedger's Execute-Workflow output shape depends on which internal branch fired:
    # noop -> {action, record, ...}; insert/update -> the flat row itself (no .action); conflict
    # -> the Slack Conflict Alert node's own response. Best-effort label, not load-bearing --
    # this is dev-summary text only, never read back by any downstream logic.
    "const detail = upsertResult.action || (upsertResult.identity_key ? 'insert_or_update' : 'unknown');\n"
    "return [{ json: { outcome: 'processed', linkedin_url: s.linkedin_url, email: s.email,\n"
    "  full_name: s.full_name, reason: s.reason, source_ref: s.source_ref, notes: s.notes,\n"
    "  detail } }];\n"
)

b7 = [
    node("Watch Sheet", "n8n-nodes-base.googleSheetsTrigger", {
        "authentication": "triggerOAuth2",
        "documentId": {"__rl": True, "mode": "id", "value": WF4_SHEET_DOC_ID},
        "sheetName": {"__rl": True, "mode": "id", "value": "0"},
        "event": "rowAdded",
        # NOTE: pollTimes isn't in the node's own `properties` (n8n injects a "Poll Times" UI
        # section for every polling=true trigger at the platform level) -- this default was not
        # independently verified against n8n source the way every dataTable/exec_wf shape in this
        # file was; review/adjust in the n8n UI before relying on it.
        "pollTimes": {"item": [{"mode": "everyMinute"}]},
        "options": {},
    }, -1000, tv=1, extra={"credentials": {"googleSheetsTriggerOAuth2Api":
                                            {"id": "REPLACE_ME", "name": "REPLACE_ME"}}}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("module", "dnc_wf4_sheet_intake", "string")], x=-800),
    code_node("Normalize Sheet Row", wf4_normalize_js, -580),
    if_bool("Skip (malformed)?", "={{ $json.skip }}", -360),
    code_node("Outcome: Malformed", wf4_outcome_malformed_js, -140, y=460),
    code_node("Build CheckLedger Input", wf4_build_check_input_js, -140, y=140),
    exec_wf("Call DNC__CheckLedger__v1", "DNC__CheckLedger__v1", 80, y=140),
    code_node("Interpret CheckLedger", wf4_interpret_check_js, 300, y=140),
    if_bool("Already on DNC?", "={{ $json.already_on_dnc }}", 520, y=140),
    code_node("Outcome: Already On DNC", wf4_outcome_on_dnc_js, 740, y=280),
    code_node("Build UpsertLedger Input", wf4_build_upsert_input_js, 740, y=0),
    exec_wf("Call DNC__UpsertLedger__v1", "DNC__UpsertLedger__v1", 960, y=0),
    code_node("Outcome: Processed", wf4_outcome_processed_js, 1180, y=0),
    if_node("MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", 1400, y=180),
    code_node("Send Guard", SEND_GUARD_JS, 1620, y=180),
    slack_post("Dev Summary",
               "=:inbox_tray: WF-4 sheet intake (dev): *{{ $json.outcome }}* — "
               "`{{ $json.linkedin_url || $json.email || 'n/a' }}` ({{ $json.full_name || 'no name' }}) · "
               "reason `{{ $json.reason || 'n/a' }}` · added_by `{{ $json.source_ref || 'n/a' }}` · "
               "detail `{{ $json.detail || 'n/a' }}`"
               "{{ $json.notes ? ' · notes: ' + $json.notes : '' }} · exec `{{ $execution.id }}`", 1840, ),
]
b7_conn = conns([
    ("Watch Sheet", "CONFIG"), ("CONFIG", "Normalize Sheet Row"),
    ("Normalize Sheet Row", "Skip (malformed)?"),
    ("Build CheckLedger Input", "Call DNC__CheckLedger__v1"),
    ("Call DNC__CheckLedger__v1", "Interpret CheckLedger"),
    ("Interpret CheckLedger", "Already on DNC?"),
    ("Build UpsertLedger Input", "Call DNC__UpsertLedger__v1"),
    ("Call DNC__UpsertLedger__v1", "Outcome: Processed"),
])
b7_conn["Skip (malformed)?"] = {"main": [
    [{"node": "Outcome: Malformed", "type": "main", "index": 0}],   # true -> malformed
    [{"node": "Build CheckLedger Input", "type": "main", "index": 0}],  # false -> continue
]}
b7_conn["Already on DNC?"] = {"main": [
    [{"node": "Outcome: Already On DNC", "type": "main", "index": 0}],   # true -> already suppressed
    [{"node": "Build UpsertLedger Input", "type": "main", "index": 0}],  # false -> clean/history -> insert
]}
b7_conn.update(conns([
    ("Outcome: Malformed", "MODE == dev?"),
    ("Outcome: Already On DNC", "MODE == dev?"),
    ("Outcome: Processed", "MODE == dev?"),
]))
b7_conn["MODE == dev?"] = {"main": [
    [{"node": "Send Guard", "type": "main", "index": 0}],  # true -> dev summary
    [],                                                     # false -> silent (prod)
]}
b7_conn.update(conns([("Send Guard", "Dev Summary")]))
b7_wf = wf("dnc_wf4_sheet_intake", b7, b7_conn)
write("workflows/dnc_wf4_sheet_intake/dnc_wf4_sheet_intake.json", b7_wf)

# ===========================================================================
# Build 8) dnc_projections_sweep  (Projections Pass, per owner GO 2026-08-11)
# Retry-scan sweep, NOT wired inline into UpsertLedger -- matches the schema's own documented
# intent for projections_state. Three branches: Pipedrive (dry-run count + gated live-write),
# Smartlead (dry-run count + gated live-write), HeyReach (dry-run count ONLY -- no live-write
# branch exists at all; the mechanism itself is still unresolved, parked pending a natural
# HeyReach account reactivation, per PROJECTIONS_PASS_PLAN_2026-08-11.md). FIRE_PIPEDRIVE /
# FIRE_SMARTLEAD default false in CONFIG -- flipping either is a manual, explicit, per-channel
# decision the owner makes by editing the deployed workflow, never something a webhook payload
# can trigger.
# ===========================================================================
PD_FIELD_KEY = "9c018b7406ebc481b9c108a487f76c4d09f91c9b"   # "DNC Status" personField, created 2026-08-11
PD_ACTIVE_OPTION = 686                                        # option id for "dnc_active" (Pipedrive stores the id, not the label)
# PD_LABEL_DNC REMOVED 2026-09-16 (P1 incident) -- this sweep must never write Pipedrive lead
# labels, only the person-level DNC Status field above. See the note above pd_aggregate_js.

pd_filter_js = (
    "const rows = $input.all().map(i => i.json);\n"
    "const out = rows.filter(r => {\n"
    "  if (r.status !== 'active') return false;\n"
    "  let proj = {};\n"
    "  try { proj = r.projections_state ? JSON.parse(r.projections_state) : {}; } catch (e) {}\n"
    "  return proj.pipedrive == null || proj.pipedrive === 'pending';\n"
    "});\n"
    "return out.map(r => ({ json: { identity_key: r.identity_key, pipedrive_person_id: r.pipedrive_person_id,\n"
    "  projections_state: r.projections_state || null } }));\n"
)
pd_limit_chunk_js = (
    # OOM fix, 2026-08-12: three concurrent live-fire executions each holding the full ~2,264-row
    # pending set (read phase + write phase) in memory crashed all three with
    # "Workflow did not finish, possible out-of-memory issue". This node caps EVERY execution's
    # downstream work (both the read/classify phase below AND the write phase, when
    # FIRE_PIPEDRIVE=true) to a bounded chunk. Resumability needs no separate cursor: rows already
    # marked projections_state.pipedrive='done' drop out of PD Filter Pending on the next fire, so
    # re-firing after a chunk completes naturally continues from where the previous one stopped.
    "const rows = $input.all().map(i => i.json);\n"
    "const totalPending = rows.length;\n"
    "const chunkSize = $('CONFIG').first().json.pd_chunk_size || 250;\n"
    "const chunk = rows.slice(0, chunkSize);\n"
    "return chunk.map(r => ({ json: Object.assign({}, r, {\n"
    "  total_pending_before_chunk: totalPending, chunk_size: chunk.length }) }));\n"
)
# pd_classify_js and pd_label_union_js REMOVED 2026-09-16 (P1 incident): this whole classification
# step existed only to gate the label-write branch (has_open_lead / lead_id) -- see the P1 incident
# log (task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md) for the full story: this
# workflow was writing the "DO NOT CONTACT" LEAD LABEL (pd_label_dnc) via PD Patch Lead Labels,
# which was NEVER the sanctioned mechanism -- the field-only ruling (write ONLY the person-level
# DNC Status custom field, never touch label_ids) predates this workflow's build but the label
# branch was built anyway and went live at scale, mislabeling 600 real leads since 2026-09-08
# (including 425 positive repliers, silently withheld from Melisa's handover automation, which
# fires on label "3. Responded" only when "DO NOT CONTACT" is absent). Removed entirely, not
# gated behind a flag -- there is no scenario where this workflow should ever write a lead label
# again. The field write (PD Write DNC Field) is unaffected and remains the sole write this
# workflow performs. One fewer per-candidate Pipedrive API call as a side effect (no more
# /v1/leads?person_id= lookup needed at all).
pd_aggregate_js = (
    # now fed DIRECTLY by "PD Limit Chunk" (no more PD Classify in between) -- rows already carry
    # total_pending_before_chunk/chunk_size from that node.
    "const rows = $input.all().map(i => i.json);\n"
    "const totalPending = rows.length ? rows[0].total_pending_before_chunk : 0;\n"
    "const chunkProcessed = rows.length;\n"
    "return [{ json: { channel: 'pipedrive', eligible: totalPending, chunk_processed: chunkProcessed,\n"
    "  remaining_after_chunk: Math.max(totalPending - chunkProcessed, 0), rows } }];\n"
)
pd_mark_done_expr = (
    "={{ JSON.stringify(Object.assign(JSON.parse($('PD Split Rows').item.json.projections_state || '{}'), "
    "{ pipedrive: 'done' })) }}"
)

# Silent-failure fix, 2026-08-12: every write-phase HTTP node (PD Write DNC Field, PD Get Lead For
# Labels, PD Patch Lead Labels) has n8n's own default onError: 'continueErrorOutput' -- a failed
# item, after exhausting retryOnFail's 4 tries, gets routed to a SECOND output instead of throwing.
# That second output was never wired to anything, so failures vanished silently: the execution
# still reported "success", the Slack digest still said "0 errors", and the row's
# projections_state stayed 'pending' forever -- meaning every future sweep would re-attempt it and
# fail the exact same way, forever, with zero visibility. Caught live: 2 persons deleted from
# Pipedrive (403 "Cannot update a deleted person") silently retried across 3 chunks before a
# read-back sample happened to catch them. Fix: merge all three error outputs into one path,
# classify the failure, and persist a distinguishable marker so the row stops being retried and the
# failure is actually counted.
pd_write_error_classify_js = (
    "const upstream = $json;\n"
    "const errMsg = (upstream.error && upstream.error.message) || '';\n"
    "const isDeleted = /Cannot update a deleted person/i.test(errMsg);\n"
    "const marker = isDeleted ? 'skipped:deleted_person' : 'failed:pipedrive_write_error';\n"
    "return { json: { identity_key: upstream.identity_key, projections_state: upstream.projections_state,\n"
    "  error_marker: marker, error_summary: errMsg.slice(0, 200) } };\n"
)
pd_mark_write_error_expr = (
    "={{ JSON.stringify(Object.assign(JSON.parse($('PD Classify Write Error').item.json.projections_state || '{}'), "
    "{ pipedrive: $('PD Classify Write Error').item.json.error_marker })) }}"
)

sl_filter_js = (
    "const rows = $input.all().map(i => i.json);\n"
    "const out = rows.filter(r => {\n"
    "  if (!r.pipedrive_person_id) return false;\n"
    "  let proj = {};\n"
    "  try { proj = r.projections_state ? JSON.parse(r.projections_state) : {}; } catch (e) {}\n"
    "  return proj.smartlead == null || proj.smartlead === 'pending';\n"
    "});\n"
    "return out.map(r => ({ json: { identity_key: r.identity_key, email_lc: r.email_lc,\n"
    "  projections_state: r.projections_state || null } }));\n"
)
sl_classify_js = (
    "const resp = $json;\n"
    "const upstream = $('SL Filter Pending').item.json;\n"
    "const found = !!(resp && resp.id);\n"
    "const alreadyUnsub = found && resp.is_unsubscribed === true;\n"
    "return { json: { identity_key: upstream.identity_key, email_lc: upstream.email_lc,\n"
    "  projections_state: upstream.projections_state,\n"
    "  resolved: found && !alreadyUnsub, already_unsub: alreadyUnsub, not_found: !found,\n"
    "  lead_id: found ? resp.id : null } };\n"
)
sl_aggregate_js = (
    "const rows = $input.all().map(i => i.json);\n"
    "const resolved = rows.filter(r => r.resolved);\n"
    "const unsub = rows.filter(r => r.already_unsub);\n"
    "const notfound = rows.filter(r => r.not_found);\n"
    "return [{ json: { channel: 'smartlead', eligible: rows.length, resolved_pending_action: resolved.length,\n"
    "  already_unsubscribed: unsub.length, not_found: notfound.length, rows } }];\n"
)
sl_filter_resolved_js = (
    "return $input.all().filter(i => i.json.resolved);\n"
)
sl_mark_done_expr = (
    # PROJECTION RULE (Nik, 2026-08-12): a performed IRREVERSIBLE projection makes the row
    # permanent. Smartlead's global unsubscribe is explicitly "cannot be undone via API" per their
    # own docs -- so a successful unsubscribe write must force this row permanent regardless of its
    # own reason/entry_type's normal TTL (covers the 38 reply_dnc-with-TTL rows inside the 623;
    # without this, the registry would show a person expiring in months while Smartlead itself
    # refuses to ever re-contact them, permanently). Encoded as a 'done:permanent' compound status
    # within the existing projections_state JSON rather than a new top-level column -- avoids the
    # multi-day UI-only Data Table column creation process for a signal that's really just a
    # richer status value for the smartlead key, not new dimension.
    "={{ JSON.stringify(Object.assign(JSON.parse($('SL Filter Resolved Only').item.json.projections_state || '{}'), "
    "{ smartlead: 'done:permanent' })) }}"
)

hr_count_js = (
    "const rows = $input.all().map(i => i.json);\n"
    "const pending = rows.filter(r => {\n"
    "  let proj = {};\n"
    "  try { proj = r.projections_state ? JSON.parse(r.projections_state) : {}; } catch (e) {}\n"
    "  return proj.heyreach == null || proj.heyreach === 'pending';\n"
    "});\n"
    "return [{ json: { channel: 'heyreach', eligible: pending.length,\n"
    "  note: 'PARKED pending natural retest -- see PROJECTIONS_PASS_PLAN_2026-08-11.md. "
    "No API calls made, no live-write branch exists for this channel.' } }];\n"
)

combine_js = (
    # Auditor finding 2026-08-11 (pre-fire review): pipedrive.eligible is a FLOOR, not the
    # population -- it's the count of matched persons from the Pass-1 resolve. This only fixes how
    # the number is REPORTED, so nobody downstream mistakes a floor for an exact population.
    #
    # Lead-label reporting (with_open_lead/without_open_lead) REMOVED 2026-09-16 -- this workflow
    # no longer writes lead labels at all (P1 incident, see the note above pd_aggregate_js).
    #
    # Slack format rewrite, 2026-08-12 (Nik's verdict on the chunked digest: unreadable). Rules
    # applied: multi-line, not one brick paragraph; chunk N/M so a glance shows position; HeyReach's
    # PARKED line dropped from every recurring post (static state, not news -- stated once, only on
    # the final chunk); no internal file references in Slack text ever (build-doc language stays in
    # the JSON note field for anyone reading raw execution data, never in slack_text); Smartlead line
    # only when its snapshot actually changed since the last post; errors suffix always present.
    # All formatting logic lives here in JS -- the Slack node's text parameter is just
    # {{ $json.slack_text }} -- because conditional multi-line strings are unreadable as n8n
    # expressions and this avoids ever hand-editing that expression again for a wording tweak.
    "const pd = $('PD Aggregate').first().json;\n"
    "const sl = $('SL Aggregate').first().json;\n"
    "const hr = $('HR Count Pending').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "\n"
    "const totalFloor = $('PD Get Candidates').all().length;\n"
    "const chunkSize = cfg.pd_chunk_size || 250;\n"
    "const alreadyDoneBeforeChunk = Math.max(totalFloor - pd.eligible, 0);\n"
    "const chunkNumber = Math.floor(alreadyDoneBeforeChunk / chunkSize) + 1;\n"
    "const totalChunks = Math.ceil(totalFloor / chunkSize);\n"
    "const isFinalChunk = pd.remaining_after_chunk === 0;\n"
    "\n"
    # Correction, 2026-08-12 (same day, caught by a read-back sample): "errors is always 0 because
    # a failure would halt the execution" was WRONG. n8n's own default for these HTTP nodes is
    # onError:'continueErrorOutput' -- a failed item does NOT halt anything, it silently routes to
    # a second output. PD Write Error Classify/Mark Write Error (added the same day) now catch and
    # persist those failures instead of losing them; this reads the real count, guarded because the
    # error-handling nodes don't run at all when there are zero errors (n8n skips a node whose only
    # input connection carried zero items), so an unguarded $('...').first() would throw on the
    # normal, error-free path.
    "let errors = 0;\n"
    "try { errors = $('PD Count Write Errors').first().json.count; } catch (e) { errors = 0; }\n"
    "\n"
    "const staticData = $getWorkflowStaticData('global');\n"
    "const curSl = { resolved: sl.resolved_pending_action, unsub: sl.already_unsubscribed, notfound: sl.not_found };\n"
    "const lastSl = staticData.lastSmartleadSnapshot;\n"
    "const slChanged = !lastSl || lastSl.resolved !== curSl.resolved || lastSl.unsub !== curSl.unsub "
    "|| lastSl.notfound !== curSl.notfound;\n"
    "staticData.lastSmartleadSnapshot = curSl;\n"
    "\n"
    "const slLine = `Smartlead: ${sl.resolved_pending_action} pending, ${sl.already_unsubscribed} "
    "already unsub, ${sl.not_found} not found`;\n"
    "const errLine = errors > 0 ? `${errors} errors` : '0 errors';\n"
    "\n"
    "let lines;\n"
    "if (isFinalChunk) {\n"
    "  lines = [\n"
    "    `:white_check_mark: DNC \\u2192 Pipedrive: sweep complete (chunk ${chunkNumber}/${totalChunks})`,\n"
    "    `${pd.chunk_processed} processed this chunk (field write only) \\u00b7 0 remaining \\u00b7 ${errLine}`,\n"
    "    `Total: ${totalFloor} eligible persons covered`,\n"
    "  ];\n"
    "  if (slChanged) lines.push(slLine);\n"
    "  lines.push(`HeyReach: read-only count, no live-write branch (${hr.eligible} eligible)`);\n"
    "} else {\n"
    "  lines = [\n"
    "    `:arrows_counterclockwise: DNC \\u2192 Pipedrive: chunk ${chunkNumber}/${totalChunks} done`,\n"
    "    `${pd.chunk_processed} processed (field write only) \\u00b7 ${pd.remaining_after_chunk} "
    "remaining \\u00b7 ${errLine}`,\n"
    "  ];\n"
    "  if (slChanged) lines.push(slLine);\n"
    "}\n"
    "\n"
    "// DRY RUN MARKER. On 2026-09-08 a MODE=\"dev\" run posted \"chunk 10/12 done · 250 processed\"\n"
    "// to #gtm-telemetry having written nothing at all - a report claiming success for work that never\n"
    "// happened, which is this estate's most expensive recurring failure. EVERY line is prefixed, not\n"
    "// just the first: Slack truncates long messages and people quote single lines out of them.\n"
    "const __live = String(cfg.MODE) === 'live';\n"
    "if (!__live) lines = lines.map(l => 'DRY RUN \\u2014 ' + l);\n"
    "\n"
    # routine chunk progress -> telemetry; the final chunk's post (real results) -> ops.
    "const targetChannel = isFinalChunk ? cfg.alert_channel : cfg.telemetry_channel;\n"
    "\n"
    "return [{ json: {\n"
    "  slack_text: lines.join('\\n'), is_final_chunk: isFinalChunk,\n"
    "  mode: String(cfg.MODE), dry_run: !__live, target_channel: targetChannel,\n"
    "  chunk_number: chunkNumber, total_chunks: totalChunks,\n"
    "  pipedrive: { eligible: pd.eligible, eligible_label: '>=' + pd.eligible,\n"
    "               chunk_processed: pd.chunk_processed, remaining_after_chunk: pd.remaining_after_chunk,\n"
    "               note: 'eligible is a floor (Pass-1 matched persons only); field write only, "
    "never touches Pipedrive lead labels. chunk_processed is this execution only -- "
    "remaining_after_chunk tells you whether another fire is needed.' },\n"
    "  smartlead: { eligible: sl.eligible, resolved_pending_action: sl.resolved_pending_action,\n"
    "               already_unsubscribed: sl.already_unsubscribed, not_found: sl.not_found },\n"
    "  heyreach: { eligible: hr.eligible, note: hr.note },\n"
    "} }];\n"
)

b8 = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}", "responseMode": "responseNode",
          "options": {}}, -1400, tv=2, extra={"webhookId": "dncprojsweep"}),
    # Added 2026-09-15, Nik's GO: this workflow existed since 2026-08-11 with only the webhook
    # above -- nothing in the estate ever called it, so it only ever ran twice (manual test fires,
    # both 2026-09-08). Hourly schedule closes that gap; the webhook stays for
    # dnc_fire_pipedrive_chunk.py's sanctioned supervised-fire path (unchanged).
    schedule_interval("Sweep Timer", 60, -1400, y=-250),
    # alert_channel is the real ops channel (C0B8GCVNR5W), not the historical C0BFE6KAN8J default --
    # found live 2026-08-11 when this sweep became the first workflow in the whole project to ever
    # actually post a real Slack message ("channel_not_found" on the old default). dev_channel_guard
    # tells Amendment 3's Send Guard this channel is confirmed correct for THIS workflow specifically;
    # every other workflow is untouched and keeps validating against the historical default.
    #
    # telemetry_channel added 2026-08-12 (Nik): intermediate chunk-progress posts go to
    # #gtm-telemetry, only the FINAL chunk's post goes to ops (alert_channel) -- computed per-post
    # in combine_js as target_channel, not a static choice. dev_channel_guard_list makes both
    # channels dev-valid for this workflow specifically.
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                # Both default false by construction -- flipping either for a real fire is done as a
                # one-off PATCH to the deployed instance (see dnc_fire_pipedrive.py), never by
                # changing this default, so any future regeneration/redeploy reverts to safe.
                ("FIRE_PIPEDRIVE", False, "boolean"), ("FIRE_SMARTLEAD", False, "boolean"),
                ("pd_field_key", PD_FIELD_KEY, "string"), ("pd_active_option", PD_ACTIVE_OPTION, "number"),
                # OOM fix, 2026-08-12: bounds every execution (read phase + write phase) to a chunk
                # of the pending population instead of the full ~2,264-row set. 200-300 range per
                # the owner's post-incident direction.
                ("pd_chunk_size", 250, "number"),
                ("module", "dnc_projections_sweep", "string")], x=-1200),

    # --- Pipedrive branch ---
    dt_get_all_not_empty("PD Get Candidates", "pipedrive_person_id", -1000, y=-400),
    code_node("PD Filter Pending", pd_filter_js, -800, y=-400),
    code_node("PD Limit Chunk", pd_limit_chunk_js, -700, y=-400),
    # PD Get Leads By Person / PD Classify / PD Has Open Lead? / PD Get Lead For Labels /
    # PD Label Union / PD Patch Lead Labels / PD Mark Done (with lead) / PD Merge Write Errors --
    # ALL REMOVED 2026-09-16 (P1 incident, see the note above pd_aggregate_js). "PD Aggregate" is
    # now fed directly by "PD Limit Chunk"; the field write goes straight to a single "PD Mark
    # Done" for every row, with-lead-or-not no longer being a distinction this workflow makes.
    code_node("PD Aggregate", pd_aggregate_js, -200, y=-400),
    if_bool("FIRE_PIPEDRIVE?", "={{ $('CONFIG').first().json.FIRE_PIPEDRIVE }}", 0, y=-400),
    split_out("PD Split Rows", "rows", 200, y=-500),
    http_pipedrive("PD Write DNC Field", "PATCH",
                   "=https://api.pipedrive.com/api/v2/persons/{{ $json.pipedrive_person_id }}",
                   400, y=-500,
                   body_expr="={{ { custom_fields: { [$('CONFIG').first().json.pd_field_key]: "
                             "$('CONFIG').first().json.pd_active_option } } }}"),
    dt_update("PD Mark Done", {"projections_state": pd_mark_done_expr},
              [{"keyName": "identity_key", "condition": "eq",
                "keyValue": "={{ $('PD Split Rows').item.json.identity_key }}"}], 600, y=-500),
    # Direct registry writes bypass UpsertLedger's own enqueue, so each one enqueues its own
    # Supabase delta claim, keyed on the id of the row the update actually returned (1:1, no
    # amplification). Without this every Mark Done drifts the Supabase mirror until the nightly
    # reconcile (2026-09-24: 416 of 500 drifted rows were projections_state from these nodes).
    dt_claim_enqueue("PD Enqueue Supabase Delta", SWEEP_CLAIM_KEY_EXPR, "supabase_delta_registry",
                      "dnc_projections_sweep", SWEEP_CLAIM_EVIDENCE_EXPR, 800, y=-500),

    # Silent-failure fix, 2026-08-12, simplified 2026-09-16: PD Write DNC Field is now the ONLY
    # write-phase HTTP node in this workflow (labels removed), so its error (2nd) output feeds
    # PD Classify Write Error directly -- no Merge needed for a single source.
    code_node_per_item("PD Classify Write Error", pd_write_error_classify_js, 800, y=-620),
    dt_update("PD Mark Write Error", {"projections_state": pd_mark_write_error_expr},
              [{"keyName": "identity_key", "condition": "eq",
                "keyValue": "={{ $('PD Classify Write Error').item.json.identity_key }}"}], 1000, y=-620),
    code_node("PD Count Write Errors", "return [{ json: { count: $input.all().length } }];", 1200, y=-620),
    dt_claim_enqueue("PD Enqueue Supabase Delta (Write Error)", SWEEP_CLAIM_KEY_EXPR, "supabase_delta_registry",
                      "dnc_projections_sweep", SWEEP_CLAIM_EVIDENCE_EXPR, 1200, y=-740),

    # --- Smartlead branch ---
    dt_get_all_not_empty("SL Get Candidates", "email_lc", -1000, y=-100),
    code_node("SL Filter Pending", sl_filter_js, -800, y=-100),
    http_smartlead("SL Resolve By Email", "GET",
                   "=https://server.smartlead.ai/api/v1/leads?email={{ encodeURIComponent($json.email_lc) }}",
                   -600, y=-100),
    code_node_per_item("SL Classify", sl_classify_js, -400, y=-100),
    code_node("SL Aggregate", sl_aggregate_js, -200, y=-100),
    if_bool("FIRE_SMARTLEAD?", "={{ $('CONFIG').first().json.FIRE_SMARTLEAD }}", 0, y=-100),
    split_out("SL Split Rows", "rows", 200, y=-40),
    code_node("SL Filter Resolved Only", sl_filter_resolved_js, 400, y=-40),
    http_smartlead("SL Unsubscribe", "POST",
                   "=https://server.smartlead.ai/api/v1/leads/{{ $('SL Filter Resolved Only').item.json.lead_id }}/unsubscribe",
                   600, y=-40, body_expr="={{ {} }}"),
    dt_update("SL Mark Done", {"projections_state": sl_mark_done_expr, "expires_at": None},
              [{"keyName": "identity_key", "condition": "eq",
                "keyValue": "={{ $('SL Filter Resolved Only').item.json.identity_key }}"}], 800, y=-40),
    dt_claim_enqueue("SL Enqueue Supabase Delta", SWEEP_CLAIM_KEY_EXPR, "supabase_delta_registry",
                      "dnc_projections_sweep", SWEEP_CLAIM_EVIDENCE_EXPR, 1000, y=60),

    # --- HeyReach branch: dry-run count only, zero external API calls, no live-write branch ---
    dt_get_all_not_empty("HR Get Candidates", "linkedin_url_norm", -1000, y=200),
    code_node("HR Count Pending", hr_count_js, -800, y=200),

    # barriers: the write branches fan out to N items (one per row via Split Out); without
    # collapsing back to 1 before starting the NEXT channel's branch, that channel would run once
    # PER ROW instead of once overall the moment FIRE_PIPEDRIVE/FIRE_SMARTLEAD is ever flipped true.
    #
    # PD Merge Write Paths / PD Write Barrier, REMOVED 2026-09-15 (Nik's GO, pre-schedule fix).
    # Added 2026-08-12 to fix a real duplicate-post bug (two direct wires into one barrier fire
    # once per branch), it was itself the SAME "n8n multi-input node fires per branch" trap one
    # level up: Merge(append, numberInputs=3) only reliably fires when MULTIPLE of its 3 declared
    # inputs actually receive items in a given execution -- proven live this session
    # (dnc_supabase_delta_pusher, 2026-09-14) where a Merge that passed a mixed-batch test silently
    # never fired the moment only ONE branch was populated. PD Count Write Errors is empty on
    # nearly every real chunk (write errors are rare), so most executions land on exactly 2-of-3
    # populated -- fine per that same finding -- but a chunk where every row happens to land on
    # only ONE of {with-lead, no-lead} (plausible for a small/homogeneous tail chunk, e.g. the
    # sweep's own remaining-136-row chunk once scheduled) would silently never barrier, which would
    # silently stop the Smartlead branch AND Combine Summaries/Dev Summary from ever running for
    # that execution -- exactly the operational blindness an unattended hourly schedule cannot
    # tolerate. Fix (matching the delta pusher's proven fix): fan the next phase OUT from a single
    # always-executes upstream source instead of fanning IN from the per-item outcome branches --
    # "PD Aggregate" already runs exactly once per execution (before the with-lead/no-lead fork),
    # so it now feeds "SL Get Candidates" directly, alongside its existing "FIRE_PIPEDRIVE?" wire
    # (plain fan-out, not the risky fan-in shape). "PD Mark Done (with lead)"/"PD Mark Done (no
    # lead)" become clean dead ends (their data table writes are what mattered, same as the delta
    # pusher's per-claim push/skip branches) -- Combine Summaries already reads pd/sl/hr/error
    # counts via $() named references, never via this barrier's own (always-empty, {done:true})
    # payload, so nothing downstream loses any data.
    code_node("SL Write Barrier", "return [{ json: { done: true } }];", 800, y=-40),

    # --- combine + report ---
    code_node("Combine Summaries", combine_js, -200, y=460),
    if_node("MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", 20, y=460),
    code_node("Send Guard", SEND_GUARD_JS, 240, y=460),
    slack_post("Dev Summary", "={{ $json.slack_text }}", 460, channel_expr="={{ $json.target_channel }}"),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 680, y=460, tv=1),
]
b8_conn = conns([
    ("Webhook", "CONFIG"), ("Sweep Timer", "CONFIG"), ("CONFIG", "PD Get Candidates"),
    ("PD Get Candidates", "PD Filter Pending"), ("PD Filter Pending", "PD Limit Chunk"),
    ("PD Limit Chunk", "PD Aggregate"),
    ("PD Split Rows", "PD Write DNC Field"),

    ("SL Get Candidates", "SL Filter Pending"), ("SL Filter Pending", "SL Resolve By Email"),
    ("SL Resolve By Email", "SL Classify"), ("SL Classify", "SL Aggregate"),
    ("SL Aggregate", "FIRE_SMARTLEAD?"),
    ("SL Split Rows", "SL Filter Resolved Only"), ("SL Filter Resolved Only", "SL Unsubscribe"),
    ("SL Unsubscribe", "SL Mark Done"),

    ("HR Get Candidates", "HR Count Pending"),

    ("Combine Summaries", "MODE == dev?"),
    ("Send Guard", "Dev Summary"), ("Dev Summary", "Respond"),
])
# PD Aggregate runs exactly once per execution (before the with-lead/no-lead fork) -- fans out to
# BOTH the write-gate AND directly to the Smartlead branch's entry point, so "SL Get Candidates"
# no longer depends on the per-item write outcomes converging (see the removed-Merge comment
# above). Plain fan-out (one source, two targets), not the risky multi-source fan-in shape.
b8_conn["PD Aggregate"] = {"main": [
    [{"node": "FIRE_PIPEDRIVE?", "type": "main", "index": 0},
     {"node": "SL Get Candidates", "type": "main", "index": 0}],
]}
# FIRE_PIPEDRIVE? true -> split+write; false branch has no target now (PD Aggregate already
# unconditionally feeds SL Get Candidates above -- a second wire here would reintroduce the same
# fan-in risk on FIRE_PIPEDRIVE=false dev/test runs).
b8_conn["FIRE_PIPEDRIVE?"] = {"main": [
    [{"node": "PD Split Rows", "type": "main", "index": 0}],
    [],
]}
# Silent-failure fix, 2026-08-12, simplified 2026-09-16 (labels removed -- PD Write DNC Field is
# now the only write-phase HTTP node here): its SECOND output (index 1, n8n's own
# onError:'continueErrorOutput' error branch) routes directly to PD Classify Write Error, no Merge
# needed for a single source.
b8_conn["PD Write DNC Field"] = {"main": [
    [{"node": "PD Mark Done", "type": "main", "index": 0}],
    [{"node": "PD Classify Write Error", "type": "main", "index": 0}],
]}
# "PD Mark Done" is now a clean dead end -- its data table write is what mattered (same pattern as
# the delta pusher's per-claim push/skip branches); nothing downstream reads their output.
b8_conn.update(conns([
    ("PD Classify Write Error", "PD Mark Write Error"),
    ("PD Mark Done", "PD Enqueue Supabase Delta"),
]))
# success output only (index 0): an update that errored changed nothing, so there is nothing to push.
b8_conn["PD Mark Write Error"] = {"main": [
    [{"node": "PD Count Write Errors", "type": "main", "index": 0},
     {"node": "PD Enqueue Supabase Delta (Write Error)", "type": "main", "index": 0}],
]}
# PD Count Write Errors is also now a clean dead end -- Combine Summaries reads its count via a
# try/catch'd $() named reference (already tolerant of this node not having run at all, which is
# the common 0-errors case), never via a wired connection.
# FIRE_SMARTLEAD? true -> split+unsubscribe, false -> straight into the HeyReach branch
b8_conn["FIRE_SMARTLEAD?"] = {"main": [
    [{"node": "SL Split Rows", "type": "main", "index": 0}],
    [{"node": "HR Get Candidates", "type": "main", "index": 0}],
]}
b8_conn["SL Mark Done"] = {"main": [
    [{"node": "SL Write Barrier", "type": "main", "index": 0},
     {"node": "SL Enqueue Supabase Delta", "type": "main", "index": 0}],
]}
b8_conn.update(conns([("SL Write Barrier", "HR Get Candidates")]))
b8_conn.update(conns([("HR Count Pending", "Combine Summaries")]))
b8_conn["MODE == dev?"] = {"main": [
    [{"node": "Send Guard", "type": "main", "index": 0}],
    [{"node": "Respond", "type": "main", "index": 0}],
]}
b8_wf = wf("dnc_projections_sweep", b8, b8_conn)
write("workflows/dnc_projections_sweep/dnc_projections_sweep.json", b8_wf)

# ===========================================================================
# Build 9) dnc_s3_creation_watcher  (S3, per owner GO 2026-08-12)
# The only genuinely NEW live automation among S1-S4 (the others are one-time backfill sweeps) --
# a poll-based watcher, chosen over a Pipedrive webhook per the spec's explicit "your call": no
# webhook registration/auth surface to build and test, and this project already has a proven
# poll-reconciler pattern (WF-2S) to follow. Serves BOTH S3 signals with union semantics:
#   Signal A (creator/owner in the five-person sales/BDR set) -- as originally specced.
#   Signal B (lead.channel_id === 'Surfe') -- added 2026-08-12 after Melisa flagged that Surfe
#   creations may attribute to the integration rather than the user, so creator-only would miss
#   exactly the personal-outreach adds this scenario exists to catch. Confirmed via live recon
#   (fixtures/s3_surfe_recon.json): the marker lives on the LEAD (channel_id), not the person --
#   the spec's original person-level framing was corrected before any code shipped.
# Idempotent by construction (DNC__UpsertLedger__v1's own merge semantics: same identity + same
# source = no-op) -- re-scanning the same recent leads every poll cycle is safe and cheap, so no
# separate cursor/lock is needed the way the OOM-fixed Pipedrive sweep needed one for its much
# larger, registry-driven population.
# ===========================================================================
# Widened 2026-08-19 (Nik's ruling on the Person-ea6fcf66 case): "any lead created by a
# sales-team user -> registry," Surfe demoted from the definition to just one more signal within
# it. Roster = old 5 (Toby, Jim, Mario, Noah, Araks) UNION Nik's named set (Rune, Slava, Melisa) --
# Jim explicitly KEPT (he was missing from Nik's list only because that list was LinkedIn proxies,
# not the sales roster; Jim is GetSales phase 2 and his creations must enter S3 once they start).
# Iulia: NO Pipedrive user exists under any spelling (checked live) -- she's HeyReach/BDR-side only
# (onboarded with Araks), never creates Pipedrive records. Left OUT of the roster on purpose, not
# an oversight -- add her id here the day one appears.
S3_SALES_USER_IDS = [17703023, 24721201, 16029123, 25733113, 24902545, 25151686, 25035678, 16340280]
S3_USER_NAMES = {17703023: "Toby", 24721201: "Jim Ash", 16029123: "Mario Stalder",
                 25733113: "Noah Keimach", 24902545: "Araks Grigoryan", 25151686: "Rune Jensen",
                 25035678: "Slava Kraievskyi", 16340280: "Melisa Bahonjic"}
# Automation-write exclusion: Mykyta's own Pipedrive user is the identity behind every n8n/API
# write this project makes -- confirmed live (2026-08-19): 100% of a 1,692-lead sample created by
# this id carries origin:'API', 0% 'ManuallyCreated'. A lead HE creates by hand in the UI would
# still show creator_id===this AND origin:'ManuallyCreated' and correctly stays IN scope; only the
# origin:'API' combination is excluded -- this is deliberately narrower than "exclude this id
# outright" so a genuine future manual action by this account isn't silently dropped too.
S3_AUTOMATION_CREATOR_ID = 25112064
# legacy/website-form token exclusion, found live 2026-08-20 (Melisa's report): creator 13015123
# is Marci Csomor's Pipedrive user -- the identity every Make.com scenario's Pipedrive writes go
# out under (confirmed live earlier this project: Make's own /users/me for this workspace's
# connection returns "Marci Csomor"), covering multiple UNRELATED automations (the old London
# Sales Sprint, and whatever handles website-form/webform intake). NOT a sales-team creation by
# any of those paths -- excluded outright, matching the predicate fix below (creator-only match,
# no owner fallback), same file this constant lives in as S3_SALES_USER_IDS for one source of truth.
S3_WEBFORM_LEGACY_CREATOR_ID = 13015123
# "lh_linkedin_profile_url" -- SAME field key WF-1's resolver and dnc_pull_pipedrive_persons.py
# already use (LI_URL_FIELD_KEY there). Do not swap for a different LinkedIn-shaped field --
# verified live: v1 persons carry LinkedIn only as this custom field, never a standard top-level one.
S3_LI_FIELD_KEY = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
# person extraction, shared by both S3 workflows -- verified live against the Surfe fixture person
# (85760): email is an ARRAY of {label, value, primary}, never a bare string; LinkedIn is a custom
# field, never a standard top-level one.
S3_PERSON_EXTRACT_JS = (
    "const person = $json.data || {};\n"
    # BUG found live 2026-08-20 (Person-1a7d5710/Person-b0fb1597/Vibhooti Dev re-appearing as
    # "no_identity" every poll despite each having a real LinkedIn URL): a v1 GET /persons/{id}
    # puts custom fields at the TOP LEVEL of the person object (person[hash] directly) -- there is
    # no nested person.custom_fields sub-object at all on this endpoint (confirmed live against all
    # three; that key is simply absent). `person.custom_fields && ...` was therefore always
    # undefined, so li was always null regardless of what Pipedrive actually had -- this was never
    # caught before because every prior caller of this shared block supplied linkedin_url/email
    # manually from a separate direct fetch rather than exercising this extraction live.\n"
    "const li = person['%s'] || null;\n"
    "const emailArr = Array.isArray(person.email) ? person.email : [];\n"
    "const emailObj = emailArr.find(e => e.primary) || emailArr[0] || null;\n"
    # found live 2026-08-19 (Person-b0fb1597, one of the two Surfe-signal leads missing from the
    # registry): Pipedrive can store email as {value: '', primary: true} -- a real object, so
    # `emailObj ? ... : null` stays truthy and yields an EMPTY STRING, not null. Never proven as
    # the actual cause of his miss (his LinkedIn alone should have passed the identity gate
    # either way), but a real latent inconsistency regardless -- normalize blank to null so every
    # downstream check (identity gate, normalizeIdentityV1) sees the same "no email" signal a
    # missing field would give, not a falsy-but-present empty string.\n"
    "const email = (emailObj && emailObj.value) ? emailObj.value : null;\n"
) % S3_LI_FIELD_KEY

# Identity-less skip+log, per Nik's GO ruling on the 27-candidate review: a match with NEITHER
# email NOR LinkedIn must never reach UpsertLedger (it would compute a null identity_key and the
# row would vanish silently) -- skipped explicitly and named in the report instead, so a human can
# manually enrich these specific records later. Shared by both S3 workflows.
s3_log_no_identity_js = (
    "return { json: Object.assign({}, $json, { skip_reason: 'no_identity' }) };\n"
)

s3_classify_js = (
    # Aggregates to ONE item (not N raw matches) deliberately: "S3 Any Matches?" needs a single
    # clean boolean gate (count > 0), and "S3 Combine" needs to report accurately on the
    # zero-matches path too (the far more common case, every 15 minutes) -- matching the exact
    # aggregate-then-split-out shape already proven in dnc_projections_sweep (PD Aggregate -> PD
    # Split Rows), not the raw-per-item-output shape that would make the IF gate evaluate
    # per-item instead of once overall.\n"
    # BUG found live 2026-08-20: http_pipedrive() never enables n8n's "split into items" option,
    # so "S3 Get Recent Leads" (no pagination) returns the WHOLE Pipedrive envelope
    # {success, data, additional_data} as ONE item -- not one item per lead. The old
    # `$input.all().map(i => i.json)` therefore built a "leads" array containing exactly one fake
    # lead (the envelope itself, with creator_id/channel_id/owner_id all undefined), so every
    # single poll classified 0 matches by construction, regardless of what was actually in Pipedrive
    # -- confirmed live: the poll right before this fix had 10 real channel_id==='Surfe' leads
    # sitting in the envelope's own .data (including Person-1a7d5710, Person-83a8d74b, Person-b0fb1597)
    # and still reported count:0. S3B's backfill sibling already knew this and correctly
    # flatMaps through .data (see s3_backfill_filter_js above) -- that fix was never back-ported
    # here. Every "0 matches this poll" telemetry post since deploy was reporting "the code never
    # looked," not "nothing qualified."\n"
    "const leads = $input.first().json.data || [];\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const salesIds = JSON.parse(cfg.sales_user_ids);\n"
    "const names = JSON.parse(cfg.user_names);\n"
    "const automationId = cfg.automation_creator_id;\n"
    "const matches = [];\n"
    "for (const lead of leads) {\n"
    # scope-widened 2026-08-19 (Nik's ruling): "any lead created by a sales-team user ->
    # registry" -- Surfe is now one signal among several, not the definition. But our own
    # automation writes leads via the API under Nik's user id too, and those must NOT enter S3
    # as if they were a personal sales creation -- narrowly excluded (id AND origin==='API'),
    # not the id outright, so a genuine manual UI action by that same account still counts.
    "  const isAutomationWrite = lead.creator_id === automationId && lead.origin === 'API';\n"
    "  if (isAutomationWrite) continue;\n"
    # predicate bug found live 2026-08-20 (Melisa's report, website-form/Memurai leads): CREATED
    # BY was the ruling's actual wording, but the code matched on creator OR owner -- meaning a
    # lead created by ANY non-roster source (legacy website-form/webform token, Memurai's own
    # pipeline, any future automation) would still be swept in the moment it got ASSIGNED to a
    # roster member as owner, which routinely happens post-creation and has nothing to do with
    # who actually personally reached out. Owner-only membership is no longer sufficient on its
    # own -- the CREATOR must be a genuine roster member (this is the actual "personal outreach"
    # signal the reason exists to capture); owner is now used only to break a tie/attribution
    # label when picking whose name to credit, never to admit a lead the creator alone wouldn't.\n"
    "  const legacyWebformCreator = lead.creator_id === cfg.webform_legacy_creator_id;\n"
    "  const isWebform = legacyWebformCreator || String(lead.origin || '').toLowerCase() === 'webforms';\n"
    "  if (isWebform) continue;\n"
    # Memurai pipeline exclusion, explicit, per Nik's standing ruling that pipeline is OUT of
    # scope entirely. Matches on the lead's own channel_id/title -- verified live against every
    # real Memurai lead found in the estate (all 20: "[Memurai Chatbot] ..." / channel_id
    # "Memurai Chatbot", or "[Webform] Memurai"). NOT matched on organization name: the list
    # endpoint S3 actually polls returns organization_id as a bare numeric id, never an expanded
    # {name} object (verified live) -- a lead.org_name field would silently never fire.\n"
    "  const isMemurai = String(lead.channel_id || '').toLowerCase().includes('memurai')"
    " || /\\bmemurai\\b/i.test(String(lead.title || ''));\n"
    "  if (isMemurai) continue;\n"
    "  const creatorMatch = salesIds.includes(lead.creator_id);\n"
    "  const surfeMatch = lead.channel_id === 'Surfe';\n"
    "  if (!creatorMatch && !surfeMatch) continue;\n"
    "  const signal = (creatorMatch && surfeMatch) ? 'both' : (creatorMatch ? 'creator' : 'surfe');\n"
    "  const matchedUserId = salesIds.includes(lead.creator_id) ? lead.creator_id"
    "    : (salesIds.includes(lead.owner_id) ? lead.owner_id : null);\n"
    "  const sourceRef = matchedUserId ? names[String(matchedUserId)] : 'Surfe';\n"
    "  matches.push({ lead_id: lead.id, person_id: lead.person_id, source_signal: signal, source_ref: sourceRef });\n"
    "}\n"
    "const bySignal = { creator: 0, surfe: 0, both: 0 };\n"
    "for (const m of matches) bySignal[m.source_signal] = (bySignal[m.source_signal] || 0) + 1;\n"
    "return [{ json: { matches, count: matches.length, by_signal: bySignal } }];\n"
)
s3_filter_new_js = (
    # Loop-spam fix, 2026-08-20: S3 Classify recomputes matches from the CURRENT top-poll_limit
    # snapshot every single poll, with no memory of prior polls -- a lead's creator_id/channel_id
    # never change once created, so once it enters the window it re-matches identically every 15
    # minutes until enough newer leads push it out. Confirmed live: 11 identical lead_ids, same 3
    # no-identity names, 5 polls straight (11:45-12:45), matchesToday inflated to 55 (11x5) before
    # this fix. This was NOT a staticData reset/race -- pollsToday survived two live redeploys
    # today intact (52, continuously accumulating) -- it's a missing feature: no per-lead seen-
    # check was ever built, only the aggregate daily counters.
    #
    # Diff-against-last-poll, not a growing all-time set: a lead's match status is stable once
    # matched (the fields it's keyed on don't change), so once diffed away as "not new" it will
    # keep reappearing in every future raw snapshot until it scrolls out of the poll_limit window
    # entirely -- at which point it stops appearing in `matches` at all, with no repeat-alert risk
    # either way. Last-poll-only diffing is therefore practically equivalent to a full all-time set
    # for this specific shape, at a fraction of the memory, and keeps the store bounded to
    # poll_limit forever instead of growing unbounded.
    #
    # staticData, not a dedicated atomic claims table: WF-1/WF-2's staticData race is a lost-update
    # problem under CONCURRENT overlapping executions (high-frequency webhook triggers). S3 is a
    # single 15-minute schedule trigger with no observed overlap (60 consecutive executions, each
    # sequential, none concurrent) and staticData has already proven durable across two live
    # redeploys today -- the race class this project keeps fixing elsewhere genuinely doesn't apply
    # here. A dedicated Data Table would still be the stronger, platform-atomic choice (this
    # project's own documented policy for exactly this class of state), but table CREATION has no
    # verified API shape (datatables/CREATE_DATATABLES.md) and needs a one-time UI step -- this is
    # the correct interim fix, not a shortcut being passed off as the final one.\n"
    "const agg = $json;\n"
    "const sd = $getWorkflowStaticData('global');\n"
    "const lastSeen = new Set(sd.s3LastPollLeadIds || []);\n"
    "const newMatches = agg.matches.filter(m => !lastSeen.has(m.lead_id));\n"
    "sd.s3LastPollLeadIds = agg.matches.map(m => m.lead_id);\n"
    "const bySignal = { creator: 0, surfe: 0, both: 0 };\n"
    "for (const m of newMatches) bySignal[m.source_signal] = (bySignal[m.source_signal] || 0) + 1;\n"
    "return [{ json: { matches: newMatches, count: newMatches.length, by_signal: bySignal,\n"
    "  all_matches_this_poll: agg.matches.length } }];\n"
)
s3_build_upsert_input_js = (
    "const match = $('S3 Split Matches').item.json;\n"
    + S3_PERSON_EXTRACT_JS +
    "return { json: {\n"
    "  linkedin_url: li, email, full_name: person.name || null,\n"
    "  reason: 'sales_personal_outreach', source: 'pipedrive_personal',\n"
    "  source_ref: match.source_ref, source_signal: match.source_signal,\n"
    "  date_precision: 'derived', expiry_review_pending: false,\n"
    "  pipedrive_person_id: match.person_id,\n"
    "  correlation_id: 's3_creation_watch:' + match.lead_id,\n"
    "} };\n"
)
S3_BURST_THRESHOLD = 5  # tunable: a single poll finding this many-or-more matches escalates to
                        # ops as a possible bulk-import/anomaly signal, not routine activity.

s3_track_poll_stats_js = (
    # Runs on EVERY poll (before the match-count gate) so the daily heartbeat's denominator
    # (polls) is accurate even on the far-more-common 0-match ticks that now post nothing at all.
    # staticData here is a plain day-counter, not a correctness-critical lock (unlike the OOM
    # postmortem's concurrency-guard cursor, which had to be external) -- worst case on a restart
    # is one under/over-counted heartbeat number, not a wrong registry write.
    # `agg.count` is now the NEW-this-poll count (post S3 Filter New) -- before the loop-spam fix
    # this counted the same re-detected matches every poll (55 = 11 x 5 identical polls); now it
    # only counts genuinely new activity, which is what a heartbeat should mean.
    "const agg = $json;\n"
    "const sd = $getWorkflowStaticData('global');\n"
    "const today = new Date().toISOString().slice(0, 10);\n"
    "if (sd.statDate !== today) { sd.statDate = today; sd.pollsToday = 0; sd.matchesToday = 0; }\n"
    "sd.pollsToday += 1;\n"
    "sd.matchesToday += agg.count;\n"
    "return [{ json: agg }];\n"
)
s3_watcher_combine_js = (
    # Only reached when count > 0 now (the 0-match path dead-ends at the gate, no post at all) --
    # no more "0 matches this poll" noise every 15 minutes. Reads from "S3 Filter New", not "S3
    # Classify" directly -- Classify's own count/by_signal is the RAW current-snapshot count
    # (re-includes everything still in the poll window, seen or not); Filter New's is the NEW-
    # this-poll count, which is what the alert and burst threshold must react to (repeats of an
    # already-announced burst must never re-trigger the burst warning).
    "const agg = $('S3 Filter New').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "\n"
    "const noIdentity = $input.all().map(i => i.json).filter(j => j.skip_reason === 'no_identity');\n"
    "const lines = [\n"
    "  `:mag: S3 creation watch: ${agg.count} new match(es) this poll " \
    "(${agg.by_signal.creator} creator, ${agg.by_signal.surfe} surfe, ${agg.by_signal.both} both)`,\n"
    "  cfg.FIRE_S3 ? '(live -- written to registry)' : '(dry-run -- FIRE_S3 is false, nothing written)',\n"
    "];\n"
    "if (noIdentity.length > 0) {\n"
    "  const names = noIdentity.map(n => `${n.full_name} (pid ${n.pipedrive_person_id})`).join(', ');\n"
    "  lines.push(`:warning: ${noIdentity.length} skipped, no email/LinkedIn -- manual enrich needed: ${names}`);\n"
    "}\n"
    # normal match activity -> telemetry (still routine); a burst (>= threshold in one poll) ->
    # ops, since that's a plausible bulk-import/anomaly worth a human noticing promptly rather
    # than scrolling telemetry for.
    "const isBurst = agg.count >= %d;\n"
    "if (isBurst) lines.push(`:rotating_light: burst: ${agg.count} matches in one poll (threshold %d)`);\n"
    "const targetChannel = isBurst ? cfg.alert_channel : cfg.telemetry_channel;\n"
    "\n"
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: targetChannel,\n"
    "  match_count: agg.count, is_burst: isBurst, skipped_no_identity: noIdentity.length, by_signal: agg.by_signal } }];\n"
) % (S3_BURST_THRESHOLD, S3_BURST_THRESHOLD)

# --- Persons extension, 2026-09-15 (Nik's GO, item 5 of the full DNC audit) --------------------
# Root cause found in the audit: S3 only ever polled Pipedrive LEADS (creator_id-matched against
# the sales roster). 144 roster-owned PERSONS created since 2026-09-01 were structurally invisible
# to it -- confirmed live: Pipedrive's Person object (list AND single-GET) has NO creator field at
# all, only owner_id. Originally shipped REPORT-ONLY because the leads path's actual admission rule
# is CREATOR, not owner (Nik's 2026-08-19/08-20 ruling: owner-only membership is insufficient on
# its own -- a bulk event-campaign prospect gets ASSIGNED an owner post-import with no personal
# outreach involved).
#
# SUPERSEDED same day, later GO: "no distinction needed -- Surfe-sourced or personal, roster-owned
# means protected... extend that rule to the S3 persons branch: owner in roster -> registry row, no
# source check -- report-only becomes live." Owner-in-roster is now sufficient on its own; the
# creator/lead-corroboration caution above no longer gates a write, only whether a separate,
# stronger signal (e.g. reply_dnc) already exists -- which DNC__UpsertLedger__v1's own reason-
# strength merge already handles without any extra logic here (sales_personal_outreach never
# downgrades a stronger existing reason; it just appends to also_flagged).
#
# Gated by its OWN flag, FIRE_S3_PERSONS -- deliberately NOT reusing FIRE_S3 (already permanently
# true for the leads path) so this brand-new write path gets its own one supervised verify window
# before going live, matching every other go-live this session, rather than firing for real on
# whatever poll happens to land first after deploy.
s3_persons_classify_js = (
    # same envelope-unwrapping requirement as leads (http_pipedrive returns ONE item, the raw
    # Pipedrive response, never one item per record) -- s3_classify_js's 2026-08-20 fix for this
    # exact bug is not something to silently skip here.
    "const persons = $input.first().json.data || [];\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const salesIds = JSON.parse(cfg.sales_user_ids);\n"
    "const names = JSON.parse(cfg.user_names);\n"
    "const matches = [];\n"
    "for (const p of persons) {\n"
    # person.owner_id is a NESTED OBJECT ({id, name, email, ...}), NOT a bare id like lead.owner_id
    # -- confirmed live 2026-09-15 against real records (pid 86650, 86158).\n"
    "  const ownerId = p.owner_id && typeof p.owner_id === 'object' ? p.owner_id.value : p.owner_id;\n"
    "  if (!salesIds.includes(ownerId)) continue;\n"
    # the LIST response already carries the full LinkedIn custom field + email array per person
    # (confirmed live 2026-09-15) -- no separate per-item Get Person call needed, unlike the leads
    # path (a lead object only carries person_id, not the person's own fields). Same field-access
    # logic as S3_PERSON_EXTRACT_JS, inlined here because that helper expects a {data: person}
    # single-GET envelope, not a raw list item.\n"
    "  const li = p['%s'] || null;\n"
    "  const emailArr = Array.isArray(p.email) ? p.email : [];\n"
    "  const emailObj = emailArr.find((e) => e.primary) || emailArr[0] || null;\n"
    "  const email = (emailObj && emailObj.value) ? emailObj.value : null;\n"
    "  matches.push({ person_id: p.id, owner_id: ownerId, full_name: p.name || null,\n"
    "    linkedin_url: li, email,\n"
    "    source_ref: names[String(ownerId)] || null, org_id: p.org_id || null, add_time: p.add_time || null });\n"
    "}\n"
    "return [{ json: { matches, count: matches.length } }];\n"
) % S3_LI_FIELD_KEY
s3_persons_filter_new_js = (
    # same loop-spam fix as leads (s3_filter_new_js), separate staticData key so it can never
    # collide with or corrupt the leads path's own dedup state.\n"
    "const agg = $json;\n"
    "const sd = $getWorkflowStaticData('global');\n"
    "const lastSeen = new Set(sd.s3LastPollPersonIds || []);\n"
    "const newMatches = agg.matches.filter(m => !lastSeen.has(m.person_id));\n"
    "sd.s3LastPollPersonIds = agg.matches.map(m => m.person_id);\n"
    "return [{ json: { matches: newMatches, count: newMatches.length, all_matches_this_poll: agg.matches.length } }];\n"
)
s3_persons_build_upsert_input_js = (
    "const match = $('S3 Persons Split Matches').item.json;\n"
    "return { json: {\n"
    "  linkedin_url: match.linkedin_url, email: match.email, full_name: match.full_name,\n"
    "  reason: 'sales_personal_outreach', source: 'pipedrive_personal', source_ref: match.source_ref,\n"
    "  date_precision: 'derived', expiry_review_pending: false,\n"
    "  pipedrive_person_id: match.person_id,\n"
    "  correlation_id: 's3_persons_watch:' + match.person_id,\n"
    "} };\n"
)
s3_persons_report_js = (
    # only ever reached via "S3 Persons Any New?"'s true branch (count > 0) -- no zero-count guard
    # needed here. Reads the no-identity skip list via a try/catch'd named reference -- that node
    # may not have run at all this poll (0 skips is the common case) -- found live 2026-09-15 on
    # S2's own rebuild (the exact same unguarded-read mistake), applied here from the start.\n"
    "const agg = $json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "let noIdentity = [];\n"
    "try { noIdentity = $('S3 Persons Log No Identity').all().map((i) => i.json); } catch (e) { noIdentity = []; }\n"
    "const lines = [\n"
    "  `:bust_in_silhouette: S3 persons watch: ${agg.count} new owner-roster-matched person(s) this poll`,\n"
    "  cfg.FIRE_S3_PERSONS ? '(live -- written to registry)' : '(dry-run -- FIRE_S3_PERSONS is false, nothing written)',\n"
    "];\n"
    "if (noIdentity.length > 0) {\n"
    "  const names = noIdentity.map((n) => `${n.full_name} (pid ${n.pipedrive_person_id})`).join(', ');\n"
    "  lines.push(`:warning: ${noIdentity.length} skipped, no email/LinkedIn -- manual enrich needed: ${names}`);\n"
    "}\n"
    "for (const m of agg.matches.slice(0, 25)) {\n"
    "  lines.push(`  - ${m.full_name || '(no name)'} (pid ${m.person_id}, owner ${m.source_ref || m.owner_id}, org ${m.org_id})`);\n"
    "}\n"
    "if (agg.matches.length > 25) lines.push(`  ...and ${agg.matches.length - 25} more`);\n"
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: cfg.telemetry_channel } }];\n"
)

s3_heartbeat_post_js = (
    # Fully independent of CONFIG/Send Guard -- always telemetry, hardcoded, nothing to
    # misconfigure. Reads the SAME staticData s3_track_poll_stats_js maintains, then resets it for
    # the new day (this trigger fires once daily at 00:05, capturing the day that just ended).
    "const sd = $getWorkflowStaticData('global');\n"
    "const polls = sd.pollsToday || 0;\n"
    "const matches = sd.matchesToday || 0;\n"
    "sd.pollsToday = 0; sd.matchesToday = 0; sd.statDate = null;\n"
    "return [{ json: {\n"
    "  slack_text: `:heartbeat: S3 watch alive: ${polls} polls, ${matches} match(es) today`,\n"
    "  target_channel: '%s' } }];\n"
) % TELEMETRY_CHANNEL

b9 = [
    schedule_interval("Poll Timer", 15, -1400),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                # default false by construction, same discipline as every other FIRE flag in this
                # project -- flipping it for real writes is a one-off live PATCH, never baked in here.
                ("FIRE_S3", False, "boolean"),
                # separate flag from FIRE_S3 on purpose -- the persons write path (2026-09-15,
                # Nik's follow-up GO) is brand new code and gets its own one supervised verify
                # window before going live, not an automatic ride-along with the already-permanent
                # FIRE_S3=true on the leads path.
                ("FIRE_S3_PERSONS", False, "boolean"),
                ("poll_limit", 100, "number"),
                ("sales_user_ids", json.dumps(S3_SALES_USER_IDS), "string"),
                ("user_names", json.dumps({str(k): v for k, v in S3_USER_NAMES.items()}), "string"),
                ("automation_creator_id", S3_AUTOMATION_CREATOR_ID, "number"),
                ("webform_legacy_creator_id", S3_WEBFORM_LEGACY_CREATOR_ID, "number"),
                ("module", "dnc_s3_creation_watcher", "string")], x=-1200),
    http_pipedrive("S3 Get Recent Leads", "GET",
                   "=https://api.pipedrive.com/v1/leads?sort=add_time%20DESC&limit="
                   "{{ $('CONFIG').first().json.poll_limit }}",
                   -1000),
    code_node("S3 Classify", s3_classify_js, -800),
    # loop-spam fix, 2026-08-20: diffs this poll's raw matches against last poll's, so an unchanged
    # estate produces zero "new" matches downstream -- see s3_filter_new_js for the full rationale.
    code_node("S3 Filter New", s3_filter_new_js, -750),
    # runs on every poll, 0-match or not -- the daily heartbeat's poll count must stay accurate
    # even though 0-match polls no longer post anything themselves.
    code_node("S3 Track Poll Stats", s3_track_poll_stats_js, -700),
    if_bool("S3 Any Matches?", "={{ $json.count > 0 }}", -600),
    split_out("S3 Split Matches", "matches", -400, y=100),
    http_pipedrive("S3 Get Person", "GET",
                   "=https://api.pipedrive.com/v1/persons/{{ $json.person_id }}", -200, y=100),
    code_node_per_item("S3 Build Upsert Input", s3_build_upsert_input_js, 0, y=100),
    # skip+log gate, per Nik's GO ruling: an identity-less match (no email, no LinkedIn) must never
    # reach UpsertLedger -- varies per split-item within one execution, so this needs a real Merge
    # before the barrier, same reasoning as the with-lead/no-lead split that caused the
    # OOM-incident's duplicate-post bug.
    if_bool("S3 Has Identity?", "={{ !!($json.linkedin_url || $json.email) }}", 150, y=100),
    code_node_per_item("S3 Log No Identity", s3_log_no_identity_js, 150, y=220),
    if_bool("FIRE_S3?", "={{ $('CONFIG').first().json.FIRE_S3 }}", 200, y=100),
    exec_wf("S3 Call UpsertLedger", "DNC__UpsertLedger__v1", 400, y=60),
    code_node("S3 Write Barrier", "return [{ json: { done: true } }];", 600, y=100),
    node("S3 Merge Identity Paths", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 2, "options": {}}, 800, y=160, tv=3),
    code_node("S3 Combine", s3_watcher_combine_js, -600, y=460),
    if_node("S3 MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", -400, y=460),
    code_node("S3 Send Guard", SEND_GUARD_JS, -200, y=460),
    slack_post("S3 Dev Summary", "={{ $json.slack_text }}", 0, channel_expr="={{ $json.target_channel }}"),
    # Daily heartbeat, per Nik: "0 matches -> no post" makes routine silence indistinguishable
    # from a dead watcher -- one line/day closes that gap. Fully independent of CONFIG/Send Guard
    # (always telemetry, hardcoded, nothing to misconfigure) so it can't be affected by anything
    # going wrong in the poll pipeline above.
    #
    # 23:55, NOT 00:05 -- found live 2026-08-18 (Nik: "1 polls today x3 days"): firing 5 minutes
    # AFTER midnight meant S3 Track Poll Stats had already reset pollsToday for the NEW day and
    # only counted the ONE poll that had happened so far that day (00:00:xx) by the time the
    # heartbeat read it -- correctly reporting "1" every single day, never the real ~96. The 15-min
    # poll schedule and the counter's increment/reset logic were both already correct (confirmed
    # live: staticData mid-day showed pollsToday=30, exactly matching elapsed 15-min polls since
    # midnight) -- only the heartbeat's OWN firing time was wrong relative to the counter it reads.
    # Firing 5 minutes before midnight reports the day's real accumulated total right before the
    # next poll's date-rollover check resets it, not right after.
    schedule_daily("Heartbeat Timer", 23, 55, -1400, y=700),
    code_node("S3 Heartbeat Post", s3_heartbeat_post_js, -1000, y=700),
    slack_post("S3 Heartbeat Slack", "={{ $json.slack_text }}", -600, y=700,
               channel_expr="={{ $json.target_channel }}"),
    # --- Persons extension, 2026-09-15: fully separate parallel branch off CONFIG, never touches
    # the existing (tested, running) leads path at all. LIVE as of the same-day follow-up GO -- see
    # the header comment above s3_persons_classify_js for the policy history.
    http_pipedrive("S3 Get Recent Persons", "GET",
                   "=https://api.pipedrive.com/v1/persons?sort=add_time%20DESC&limit="
                   "{{ $('CONFIG').first().json.poll_limit }}",
                   -1000, y=1000),
    code_node("S3 Classify Persons", s3_persons_classify_js, -800, y=1000),
    code_node("S3 Filter New Persons", s3_persons_filter_new_js, -600, y=1000),
    if_bool("S3 Persons Any New?", "={{ $json.count > 0 }}", -400, y=1000),
    code_node("S3 Persons Report", s3_persons_report_js, -200, y=1000),
    if_node("S3 Persons MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", 0, y=1000),
    code_node("S3 Persons Send Guard", SEND_GUARD_JS, 200, y=1000),
    slack_post("S3 Persons Dev Summary", "={{ $json.slack_text }}", 400, y=1000,
               channel_expr="={{ $json.target_channel }}"),
    # write path, fanned out from "S3 Persons Any New?" alongside the report (plain fan-out, not a
    # second source feeding an existing node). No "Get Person" HTTP call needed here, unlike the
    # leads path -- the list fetch above already carries full identity per person.
    split_out("S3 Persons Split Matches", "matches", -400, y=1150),
    code_node_per_item("S3 Persons Build Upsert Input", s3_persons_build_upsert_input_js, -200, y=1150),
    if_bool("S3 Persons Has Identity?", "={{ !!($json.linkedin_url || $json.email) }}", 0, y=1150),
    code_node_per_item("S3 Persons Log No Identity", s3_log_no_identity_js, 0, y=1250),
    if_bool("FIRE_S3_PERSONS?", "={{ $('CONFIG').first().json.FIRE_S3_PERSONS }}", 200, y=1150),
    exec_wf("S3 Persons Call UpsertLedger", "DNC__UpsertLedger__v1", 400, y=1150),
]
b9_conn = conns([
    ("Poll Timer", "CONFIG"), ("CONFIG", "S3 Get Recent Leads"),
    ("S3 Get Recent Leads", "S3 Classify"), ("S3 Classify", "S3 Filter New"),
    ("S3 Filter New", "S3 Track Poll Stats"),
    ("S3 Track Poll Stats", "S3 Any Matches?"),
    ("S3 Get Person", "S3 Build Upsert Input"),
    # missing edge, found live 2026-08-12: without this, "S3 Build Upsert Input" was a dead end --
    # execution silently stopped there every time, never reaching FIRE_S3?/UpsertLedger/Combine at
    # all. Not an n8n bug (that hunt was real but unrelated) -- a genuine gap in this wiring.
    ("S3 Build Upsert Input", "S3 Has Identity?"),
    ("S3 Call UpsertLedger", "S3 Write Barrier"),
    ("S3 Send Guard", "S3 Dev Summary"),
    ("Heartbeat Timer", "S3 Heartbeat Post"), ("S3 Heartbeat Post", "S3 Heartbeat Slack"),
    ("S3 Get Recent Persons", "S3 Classify Persons"), ("S3 Classify Persons", "S3 Filter New Persons"),
    ("S3 Filter New Persons", "S3 Persons Any New?"),
    ("S3 Persons Send Guard", "S3 Persons Dev Summary"),
])
# per Nik: 0 matches -> NO post at all (was noise every 15 min) -- the false branch simply ends
# here now, no target, instead of feeding "S3 Combine" the way it used to.
b9_conn["S3 Any Matches?"] = {"main": [
    [{"node": "S3 Split Matches", "type": "main", "index": 0}],
    [],
]}
b9_conn.update(conns([("S3 Split Matches", "S3 Get Person")]))
# CONFIG fans OUT to both the (existing, unchanged) leads path and the new persons path -- plain
# fan-out from one source, not the risky multi-source fan-in shape.
b9_conn["CONFIG"] = {"main": [
    [{"node": "S3 Get Recent Leads", "type": "main", "index": 0},
     {"node": "S3 Get Recent Persons", "type": "main", "index": 0}],
]}
# same "0 -> no post" discipline as the leads path. True branch fans OUT to both the report AND
# the write path -- plain fan-out, same shape as CONFIG's own fan-out above.
b9_conn["S3 Persons Any New?"] = {"main": [
    [{"node": "S3 Persons Report", "type": "main", "index": 0},
     {"node": "S3 Persons Split Matches", "type": "main", "index": 0}],
    [],
]}
b9_conn.update(conns([("S3 Persons Report", "S3 Persons MODE == dev?")]))
b9_conn["S3 Persons MODE == dev?"] = {"main": [
    [{"node": "S3 Persons Send Guard", "type": "main", "index": 0}],
    [],
]}
b9_conn.update(conns([
    ("S3 Persons Split Matches", "S3 Persons Build Upsert Input"),
    ("S3 Persons Build Upsert Input", "S3 Persons Has Identity?"),
]))
b9_conn["S3 Persons Has Identity?"] = {"main": [
    [{"node": "FIRE_S3_PERSONS?", "type": "main", "index": 0}],
    [{"node": "S3 Persons Log No Identity", "type": "main", "index": 0}],
]}
# clean dead end -- Combine-equivalent reporting (S3 Persons Report) already reads matches from
# "S3 Filter New Persons" and no-identity skips from "S3 Persons Log No Identity" via named
# references, so nothing needs to converge here.
b9_conn["FIRE_S3_PERSONS?"] = {"main": [
    [{"node": "S3 Persons Call UpsertLedger", "type": "main", "index": 0}],
    [],
]}
# skip+log gate: only identity-bearing rows reach the FIRE decision at all.
b9_conn["S3 Has Identity?"] = {"main": [
    [{"node": "FIRE_S3?", "type": "main", "index": 0}],
    [{"node": "S3 Log No Identity", "type": "main", "index": 0}],
]}
b9_conn["FIRE_S3?"] = {"main": [
    [{"node": "S3 Call UpsertLedger", "type": "main", "index": 0}],
    [{"node": "S3 Write Barrier", "type": "main", "index": 0}],
]}
b9_conn.update(conns([("S3 Write Barrier", "S3 Merge Identity Paths")]))
b9_conn["S3 Log No Identity"] = {"main": [
    [{"node": "S3 Merge Identity Paths", "type": "main", "index": 1}],
]}
b9_conn.update(conns([("S3 Merge Identity Paths", "S3 Combine")]))
# missing edge, found live 2026-08-12 (same class as Build Upsert Input's): without this, S3
# Combine was ALSO a dead end -- it correctly computed slack_text, which happened to surface in
# the lastNode HTTP response, masking that the actual Slack post never fired.
b9_conn.update(conns([("S3 Combine", "S3 MODE == dev?")]))
b9_conn["S3 MODE == dev?"] = {"main": [
    [{"node": "S3 Send Guard", "type": "main", "index": 0}],
    [],
]}
b9_wf = wf("dnc_s3_creation_watcher", b9, b9_conn)
write("workflows/dnc_s3_creation_watcher/dnc_s3_creation_watcher.json", b9_wf)

# ===========================================================================
# Build 10) dnc_s3_surfe_backfill  (S3 Signal B, one-time backfill over EXISTING leads)
# Signal A gets no backfill by original design (S3 was always "catch NEW creations going
# forward," per the spec doc). Signal B needs one because Surfe usage may predate this watcher.
# Chunked + externally-guarded per today's OOM incident: total org lead count is in the
# thousands (confirmed live -- more_items_in_collection still true at a 500-row page), so an
# unfiltered full-population read in one execution is exactly the failure pattern that crashed
# the Pipedrive projections sweep three times today. No registry-side "pending" state exists for
# leads (unlike the sweep's own rows), so THIS backfill genuinely needs an explicit cursor -- kept
# in the caller's own driver script (webhook body start_offset in, next_offset out), not a new
# Data Table (avoids the same UI-only column-creation blocker source_signal is already waiting on).
# Sorted DESC (newest first): Surfe is a recent integration, so real matches surface early rather
# than requiring a full pass to the oldest records before finding any signal.
# ===========================================================================
s3_backfill_filter_js = (
    # With native pagination, http_pipedrive's output is ONE item PER PAGE fetched this chunk
    # (each carrying its own {data: [...], additional_data: {...}}), not one item per lead -- must
    # flatMap through .data first, or this would silently only ever look at however many "pages"
    # happened to arrive as top-level items, never their actual lead contents.
    "const pages = $input.all().map(i => i.json);\n"
    "const leads = pages.flatMap(p => Array.isArray(p.data) ? p.data : []);\n"
    "const matches = leads.filter(l => l.channel_id === 'Surfe')"
    ".map(l => ({ lead_id: l.id, person_id: l.person_id }));\n"
    "return [{ json: { matches, count: matches.length } }];\n"
)
s3_backfill_build_upsert_input_js = (
    "const match = $('S3B Split Matches').item.json;\n"
    + S3_PERSON_EXTRACT_JS +
    "return { json: {\n"
    "  linkedin_url: li, email, full_name: person.name || null,\n"
    "  reason: 'sales_personal_outreach', source: 'pipedrive_surfe', source_ref: 'Surfe',\n"
    "  source_signal: 'surfe', date_precision: 'derived', expiry_review_pending: false,\n"
    "  pipedrive_person_id: match.person_id,\n"
    "  correlation_id: 's3_surfe_backfill:' + match.lead_id,\n"
    "} };\n"
)
s3_backfill_combine_js = (
    # LAST page's pagination block (not the first) is the true continuation point after this
    # chunk's however-many pages were consumed -- each page fetched this chunk arrives as its own
    # item, each with its OWN additional_data.pagination reflecting only that page's position.
    "const pages = $('S3B Get Leads Page').all().map(i => i.json);\n"
    "const lastPage = pages[pages.length - 1] || {};\n"
    "const pg = (lastPage.additional_data && lastPage.additional_data.pagination) || {};\n"
    "const agg = $('S3B Filter Surfe').first().json;\n"
    "const done = !pg.more_items_in_collection;\n"
    "const nextOffset = done ? null : pg.next_start;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "\n"
    "const noIdentity = $input.all().map(i => i.json).filter(j => j.skip_reason === 'no_identity');\n"
    "const lines = [\n"
    "  `:mag: S3 Surfe backfill: ${agg.count} match(es) this chunk (offset " \
    "${cfg.start_offset} -> ${done ? 'DONE' : nextOffset})`,\n"
    "  cfg.FIRE_S3_BACKFILL ? '(live -- written to registry)' : '(dry-run -- FIRE_S3_BACKFILL is false, nothing written)',\n"
    "];\n"
    "if (noIdentity.length > 0) {\n"
    "  const names = noIdentity.map(n => `${n.full_name} (pid ${n.pipedrive_person_id})`).join(', ');\n"
    "  lines.push(`:warning: ${noIdentity.length} skipped, no email/LinkedIn -- manual enrich needed: ${names}`);\n"
    "}\n"
    # routine chunk progress -> telemetry; the final (done=true) chunk's post -> ops.
    "const targetChannel = done ? cfg.alert_channel : cfg.telemetry_channel;\n"
    "\n"
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: targetChannel, matches_this_chunk: agg.count,\n"
    "  skipped_no_identity: noIdentity.length, done, next_offset: nextOffset } }];\n"
)

b10 = [
    # responseMode: "lastNode" -- NOT "responseNode". A dedicated Respond node reproducibly
    # triggered n8n's own "No Respond to Webhook node found in the workflow" validation error live
    # on this specific workflow (WorkflowConfigurationError from
    # Webhook/utils.ts:checkResponseModeConfiguration) despite the Respond node existing and being
    # structurally reachable via every path -- confirmed via a byte-for-byte-correct connections
    # graph, three isolated minimal probes (webhook->respond, webhook->executeWorkflow->respond,
    # webhook->paginated-http->respond, all of which worked standalone), a full delete+recreate,
    # and a fresh never-used path/webhookId -- none of which resolved it. Root cause not
    # conclusively identified; not worth more time chasing given this workflow doesn't need a fast
    # ack anyway (the driver script reads real results via the executions API regardless, same as
    # every projections-sweep chunk fire today). lastNode sidesteps the whole validation path: no
    # dedicated Respond node required at all.
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_S3_SURFE_BACKFILL_V2}}", "responseMode": "lastNode",
          "options": {}}, -1400, tv=2, extra={"webhookId": "dncs3surfebackfillv2"}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                ("FIRE_S3_BACKFILL", False, "boolean"),
                # caller-supplied cursor -- lives in the driver script that fires this webhook, not
                # in any n8n-side table, exactly like the OOM postmortem's guard script pattern but
                # for an offset instead of a running-execution check.
                # $json.body.start_offset, NOT $json.start_offset -- n8n's Webhook node wraps the
                # entire POST body under a `.body` key (alongside `.headers`/`.query`/`.params`),
                # confirmed live 2026-08-14 (S4's first real fire) after this exact mistake made
                # every CONFIG field read null and silently defaulted via `|| 0`/`|| ...`. Never
                # actually exposed here because this backfill's whole population fit in one
                # chunk (offset was always 0 regardless), but the same latent bug either way.
                ("start_offset", "={{ $json.body.start_offset || 0 }}", "number"),
                ("leads_per_page", 500, "number"), ("pages_per_chunk", 3, "number"),
                ("module", "dnc_s3_surfe_backfill", "string")], x=-1200),
    http_pipedrive("S3B Get Leads Page", "GET",
                   "=https://api.pipedrive.com/v1/leads?sort=add_time%20DESC&start="
                   "{{ $('CONFIG').first().json.start_offset }}&limit="
                   "{{ $('CONFIG').first().json.leads_per_page }}",
                   -1000, paginate=True, max_requests=3),
    code_node("S3B Filter Surfe", s3_backfill_filter_js, -800),
    if_bool("S3B Any Matches?", "={{ $json.count > 0 }}", -600),
    split_out("S3B Split Matches", "matches", -400, y=100),
    http_pipedrive("S3B Get Person", "GET",
                   "=https://api.pipedrive.com/v1/persons/{{ $json.person_id }}", -200, y=100),
    code_node_per_item("S3B Build Upsert Input", s3_backfill_build_upsert_input_js, 0, y=100),
    # skip+log gate, per Nik's GO ruling: an identity-less match (no email, no LinkedIn) must never
    # reach UpsertLedger -- varies per split-item within one execution (some rows have an
    # identifier, some don't), so this needs a real Merge before the barrier, same reasoning as the
    # with-lead/no-lead split that caused the OOM-incident's duplicate-post bug.
    if_bool("S3B Has Identity?", "={{ !!($json.linkedin_url || $json.email) }}", 150, y=100),
    code_node_per_item("S3B Log No Identity", s3_log_no_identity_js, 150, y=220),
    if_bool("FIRE_S3_BACKFILL?", "={{ $('CONFIG').first().json.FIRE_S3_BACKFILL }}", 200, y=100),
    exec_wf("S3B Call UpsertLedger", "DNC__UpsertLedger__v1", 400, y=60),
    code_node("S3B Write Barrier", "return [{ json: { done: true } }];", 600, y=100),
    node("S3B Merge Identity Paths", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 2, "options": {}}, 800, y=160, tv=3),
    code_node("S3B Combine", s3_backfill_combine_js, -600, y=460),
    if_node("S3B MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", -400, y=460),
    code_node("S3B Send Guard", SEND_GUARD_JS, -200, y=460),
    slack_post("S3B Dev Summary", "={{ $json.slack_text }}", 0, channel_expr="={{ $json.target_channel }}"),
]
b10_conn = conns([
    ("Webhook", "CONFIG"), ("CONFIG", "S3B Get Leads Page"),
    ("S3B Get Leads Page", "S3B Filter Surfe"), ("S3B Filter Surfe", "S3B Any Matches?"),
    ("S3B Get Person", "S3B Build Upsert Input"),
    # same missing edge as the creation watcher, found live 2026-08-12 -- without this,
    # "S3B Build Upsert Input" was a dead end; execution silently stopped there.
    ("S3B Build Upsert Input", "S3B Has Identity?"),
    ("S3B Call UpsertLedger", "S3B Write Barrier"),
    ("S3B Send Guard", "S3B Dev Summary"),
])
b10_conn["S3B Any Matches?"] = {"main": [
    [{"node": "S3B Split Matches", "type": "main", "index": 0}],
    [{"node": "S3B Combine", "type": "main", "index": 0}],
]}
b10_conn.update(conns([("S3B Split Matches", "S3B Get Person")]))
# skip+log gate: only identity-bearing rows reach the FIRE decision at all.
b10_conn["S3B Has Identity?"] = {"main": [
    [{"node": "FIRE_S3_BACKFILL?", "type": "main", "index": 0}],
    [{"node": "S3B Log No Identity", "type": "main", "index": 0}],
]}
b10_conn["FIRE_S3_BACKFILL?"] = {"main": [
    [{"node": "S3B Call UpsertLedger", "type": "main", "index": 0}],
    [{"node": "S3B Write Barrier", "type": "main", "index": 0}],
]}
b10_conn.update(conns([("S3B Write Barrier", "S3B Merge Identity Paths")]))
b10_conn["S3B Log No Identity"] = {"main": [
    [{"node": "S3B Merge Identity Paths", "type": "main", "index": 1}],
]}
b10_conn.update(conns([("S3B Merge Identity Paths", "S3B Combine")]))
# missing edge, found live 2026-08-12 (same class as Build Upsert Input's): without this, S3B
# Combine was ALSO a dead end -- it correctly computed slack_text, which happened to surface in
# the lastNode HTTP response, masking that the actual Slack post never fired.
b10_conn.update(conns([("S3B Combine", "S3B MODE == dev?")]))
# false branch (MODE != dev) simply ends here -- no Respond node needed under lastNode mode; n8n
# returns whichever node executed last on the actual path taken.
b10_conn["S3B MODE == dev?"] = {"main": [
    [{"node": "S3B Send Guard", "type": "main", "index": 0}],
    [],
]}
b10_wf = wf("dnc_s3_surfe_backfill", b10, b10_conn)
write("workflows/dnc_s3_surfe_backfill/dnc_s3_surfe_backfill.json", b10_wf)

# ===========================================================================
# Build 12) dnc_s4_event_populations  (S4, per owner GO 2026-08-14)
# "Everyone contacted via the four AI4 Smartlead campaigns + both HeyReach campaigns enters with
# reason=event_contacted. One pass over campaign lead lists." -- the most straightforward of the
# four scenarios per the spec doc's own assessment: pure list reads, no Pipedrive dependency, no
# per-item enrichment call needed (unlike S3's person lookup -- email/LinkedIn already ride along
# on the campaign-lead objects themselves for both providers).
#
# Total population confirmed live before writing any code: 892 across the 4 Smartlead campaigns
# (227+205+206+254) + 1,270 across the 2 HeyReach campaigns (657+613) = 2,162 -- comparable in
# scale to the Pipedrive sweep that OOM'd earlier today, so chunked + guarded from the start, not
# retrofitted after a crash. HeyReach's offset pagination verified live to actually advance (zero
# id overlap between offset=0 and offset=3) before relying on it -- the list-ordering trap already
# burned this project once.
#
# Caller-cycled cursor: the driver script iterates (source_type, campaign_id, offset) across all
# 6 campaigns, one HTTP call per execution, same externally-guarded chunking pattern as the S3
# Surfe backfill (webhook body in, next_offset/done out, read via execution data -- lastNode mode,
# not responseNode, given the S3B mystery).
#
# Design call, flagged rather than silently made: HeyReach leads carry a per-lead
# leadCampaignStatus (e.g. "Failed" -- profile unreachable, never actually contacted). Included
# regardless of status -- "everyone... via the campaign" reads as "everyone the campaign targeted,"
# not "everyone who received a message," and DNC's own precedent throughout this project has been
# to prefer the safe superset (S1's union design) over a narrower interpretation that risks missing
# someone who should be protected.
# ===========================================================================
S4_SMARTLEAD_CAMPAIGNS = {3686193: "Ai4 2026", 3686187: "Ai4 2026", 3686184: "Ai4 2026", 3686181: "Ai4 2026"}
S4_HEYREACH_CAMPAIGNS = {513000: "Ai4 2026 - Rune - LinkedIn", 512995: "Ai4 2026 - Mario - LinkedIn"}

s4_normalize_smartlead_js = (
    # GET /campaigns/{id}/leads has a DIFFERENT shape than the global GET /leads?email= lookup
    # used elsewhere in this project (S3's person extraction) -- verified live 2026-08-14 after
    # first assuming they matched: here the real lead object is nested under a `.lead` key, and
    # email/linkedin_profile are plain strings, not the array-of-{label,value,primary} shape the
    # global endpoint uses. Exactly the "verify shapes before fixtures" lesson recurring again.
    "const resp = $json;\n"
    "const rows = Array.isArray(resp.data) ? resp.data : [];\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const matches = rows.map(row => {\n"
    "  const l = row.lead || {};\n"
    "  const fullName = [l.first_name, l.last_name].filter(Boolean).join(' ') || null;\n"
    # found live 2026-08-14 on the Sales Sprint fire's skip report: a STOPPED-status lead (already
    # unsubscribed/bounced out of the campaign) has EVERY `lead.*` field nulled out by Smartlead,
    # including `lead.id` -- `external_id: l.id` alone went null too, and since the skip-report
    # template's only fallback was full_name||external_id, both sides of that `||` were nullish and
    # rendered the literal string "undefined" 48 times across the two biggest sprint campaigns.
    # `row.campaign_lead_map_id` is the one field Smartlead never nulls even on a wiped-PII row --
    # falling back to it keeps the skip report resolvable (a real id to look up) instead of noise.
    "  return { full_name: fullName, email: l.email || null,\n"
    "    linkedin_url: l.linkedin_profile || null, external_id: l.id || row.campaign_lead_map_id || null,\n"
    "    source_ref: cfg.campaign_name || 'Ai4 2026' };\n"
    "});\n"
    "return [{ json: { matches, count: matches.length, total: resp.total_leads || matches.length } }];\n"
)
s4_normalize_heyreach_js = (
    "const resp = $json;\n"
    "const items = Array.isArray(resp.items) ? resp.items : [];\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const matches = items.map(it => {\n"
    "  const p = it.linkedInUserProfile || {};\n"
    "  const email = p.emailAddress || p.enrichedEmailAddress || p.customEmailAddress || null;\n"
    "  const fullName = [p.firstName, p.lastName].filter(Boolean).join(' ') || null;\n"
    "  return { full_name: fullName, email, linkedin_url: p.profileUrl || null, external_id: it.id,\n"
    "    source_ref: cfg.campaign_name || 'Ai4 2026' };\n"
    "});\n"
    "return [{ json: { matches, count: matches.length, total: resp.totalCount || matches.length } }];\n"
)
s4_build_upsert_input_js = (
    "const match = $('S4 Split Matches').item.json;\n"
    "return { json: {\n"
    "  linkedin_url: match.linkedin_url, email: match.email, full_name: match.full_name,\n"
    # external_id must ride along -- found live 2026-08-14: it was used ONLY inline for
    # correlation_id and never copied onto this object, so the skip-report template's fallback
    # (full_name||external_id) always saw external_id as literally undefined, not just null.
    "  external_id: match.external_id,\n"
    "  reason: 'event_contacted', source: 'event_campaign', source_ref: match.source_ref,\n"
    "  date_precision: 'derived', expiry_review_pending: false, pipedrive_person_id: null,\n"
    "  correlation_id: 's4_event_populations:' + $('CONFIG').first().json.source_type + ':' + match.external_id,\n"
    "} };\n"
)
s4_fetch_error_js = (
    # unwired onError:continueErrorOutput on the fetch nodes was exactly the class of bug that
    # cost real time on the Pipedrive sweep -- wired here to a visible report line instead of a
    # silent dead end, even though a single-call-per-execution fetch failure is lower-stakes than
    # the per-item write failures that prompted that fix.
    "return [{ json: { matches: [], count: 0, total: 0, fetch_error: ($json.error && $json.error.message) || 'unknown fetch error' } }];\n"
)
s4_combine_js = (
    "const agg = $('S4 Aggregate').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const noIdentity = $input.all().map(i => i.json).filter(j => j.skip_reason === 'no_identity');\n"
    "const done = (cfg.offset + agg.count) >= agg.total || agg.count === 0;\n"
    "const nextOffset = done ? null : cfg.offset + agg.count;\n"
    "const lines = [\n"
    "  `:mag: S4 event populations (${cfg.source_type} ${cfg.campaign_id}): ${agg.count} lead(s) this chunk, "
    "offset ${cfg.offset} -> ${done ? 'DONE for this campaign' : nextOffset}`,\n"
    "  cfg.FIRE_S4 ? '(live -- written to registry)' : '(dry-run -- FIRE_S4 is false, nothing written)',\n"
    "];\n"
    "if (agg.fetch_error) lines.push(`:warning: fetch error this chunk: ${agg.fetch_error}`);\n"
    "if (noIdentity.length > 0) {\n"
    # a bare numeric fallback id reads as noise without saying WHAT it is -- label it explicitly
    # so "manual enrich needed" stays actionable instead of a list of unexplained numbers.
    "  const names = noIdentity.map(n => n.full_name\n"
    "    || (n.external_id ? `(no name/email/LinkedIn -- Smartlead campaign_lead_map_id ${n.external_id})`\n"
    "                       : '(no identifying info at all)')).join(', ');\n"
    "  lines.push(`:warning: ${noIdentity.length} skipped, no email/LinkedIn -- manual enrich needed: ${names}`);\n"
    "}\n"
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: done ? cfg.alert_channel : cfg.telemetry_channel,\n"
    "  matches_this_chunk: agg.count, done, next_offset: nextOffset } }];\n"
)

b11 = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_S4_EVENT_POPULATIONS}}", "responseMode": "lastNode",
          "options": {}}, -1400, tv=2, extra={"webhookId": "dncs4eventpopulations"}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                ("FIRE_S4", False, "boolean"),
                # caller-supplied cursor, same discipline as the S3 Surfe backfill.
                # $json.body.<field>, NOT $json.<field> -- found live on S4's first real fire: the
                # Webhook node wraps the whole POST body under `.body`, so every one of these was
                # silently reading null, which meant "S4 Is Smartlead?" always evaluated false
                # (routing every call to HeyReach regardless of the requested source_type) and
                # HeyReach's own call then failed on a null campaignId. Fixed here; same class of
                # mistake also fixed in the S3 Surfe backfill's start_offset even though THAT bug
                # never manifested (its whole population fit in one chunk).
                ("source_type", "={{ $json.body.source_type }}", "string"),
                ("campaign_id", "={{ $json.body.campaign_id }}", "number"),
                ("campaign_name", "={{ $json.body.campaign_name }}", "string"),
                ("offset", "={{ $json.body.offset || 0 }}", "number"),
                # 100, not 250 -- Smartlead's campaign/leads endpoint hard-caps limit at 100
                # (confirmed live on S4's second real fire: "limit must be less than or equal to
                # 100"), same cap already known for its other list endpoints. HeyReach accepts 100
                # fine (verified), so one uniform value covers both providers.
                ("chunk_size", 100, "number"),
                ("module", "dnc_s4_event_populations", "string")], x=-1200),
    if_bool("S4 Is Smartlead?", "={{ $('CONFIG').first().json.source_type === 'smartlead' }}", -1000),
    http_smartlead("S4 Get Smartlead Leads", "GET",
                   "=https://server.smartlead.ai/api/v1/campaigns/{{ $('CONFIG').first().json.campaign_id }}"
                   "/leads?offset={{ $('CONFIG').first().json.offset }}&limit={{ $('CONFIG').first().json.chunk_size }}",
                   -800, y=-100),
    code_node("S4 Normalize Smartlead", s4_normalize_smartlead_js, -600, y=-100),
    node("S4 Get HeyReach Leads", "n8n-nodes-base.httpRequest", {
        "method": "POST", "url": "https://api.heyreach.io/api/public/campaign/GetLeadsFromCampaign",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ { campaignId: $('CONFIG').first().json.campaign_id,"
                    " limit: $('CONFIG').first().json.chunk_size, offset: $('CONFIG').first().json.offset } }}",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 350}}},
    }, -800, y=100, tv=4.2, extra={
        # created live 2026-08-14 -- no HeyReach outbound credential existed anywhere in this n8n
        # instance before S4 (the existing HeyReach workflows only ever RECEIVE inbound webhooks
        # from HeyReach; nothing previously called ITS api out). httpHeaderAuth, header name
        # X-API-KEY, matching the auth shape already verified live via the standalone recon calls.
        "credentials": {"httpHeaderAuth": {"id": "pJyex1XdUIZxOpgX", "name": "HeyReach API (DNC S4)"}},
        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 4, "waitBetweenTries": 2500}),
    code_node("S4 Normalize HeyReach", s4_normalize_heyreach_js, -600, y=100),
    code_node("S4 Fetch Error (Smartlead)", s4_fetch_error_js, -600, y=-180),
    code_node("S4 Fetch Error (HeyReach)", s4_fetch_error_js, -600, y=180),
    node("S4 Merge Sources", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 4, "options": {}}, -400, y=0, tv=3),
    code_node("S4 Aggregate", "return [$input.first()];", -200, y=0),
    if_bool("S4 Any Matches?", "={{ $json.count > 0 }}", 0, y=0),
    split_out("S4 Split Matches", "matches", 200, y=100),
    code_node_per_item("S4 Build Upsert Input", s4_build_upsert_input_js, 400, y=100),
    if_bool("S4 Has Identity?", "={{ !!($json.linkedin_url || $json.email) }}", 600, y=100),
    code_node_per_item("S4 Log No Identity", s3_log_no_identity_js, 600, y=220),
    if_bool("FIRE_S4?", "={{ $('CONFIG').first().json.FIRE_S4 }}", 800, y=100),
    exec_wf("S4 Call UpsertLedger", "DNC__UpsertLedger__v1", 1000, y=60),
    code_node("S4 Write Barrier", "return [{ json: { done: true } }];", 1200, y=100),
    node("S4 Merge Identity Paths", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 2, "options": {}}, 1400, y=160, tv=3),
    code_node("S4 Combine", s4_combine_js, -600, y=460),
    if_node("S4 MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", -400, y=460),
    code_node("S4 Send Guard", SEND_GUARD_JS, -200, y=460),
    slack_post("S4 Dev Summary", "={{ $json.slack_text }}", 0, channel_expr="={{ $json.target_channel }}"),
]
b11_conn = conns([
    ("Webhook", "CONFIG"), ("CONFIG", "S4 Is Smartlead?"),
    ("S4 Get Smartlead Leads", "S4 Normalize Smartlead"),
    ("S4 Get HeyReach Leads", "S4 Normalize HeyReach"),
    ("S4 Split Matches", "S4 Build Upsert Input"),
    ("S4 Build Upsert Input", "S4 Has Identity?"),
    ("S4 Call UpsertLedger", "S4 Write Barrier"),
    ("S4 Send Guard", "S4 Dev Summary"),
])
b11_conn["S4 Is Smartlead?"] = {"main": [
    [{"node": "S4 Get Smartlead Leads", "type": "main", "index": 0}],
    [{"node": "S4 Get HeyReach Leads", "type": "main", "index": 0}],
]}
b11_conn["S4 Get Smartlead Leads"] = {"main": [
    [{"node": "S4 Normalize Smartlead", "type": "main", "index": 0}],
    [{"node": "S4 Fetch Error (Smartlead)", "type": "main", "index": 0}],
]}
b11_conn["S4 Get HeyReach Leads"] = {"main": [
    [{"node": "S4 Normalize HeyReach", "type": "main", "index": 0}],
    [{"node": "S4 Fetch Error (HeyReach)", "type": "main", "index": 0}],
]}
b11_conn["S4 Normalize Smartlead"] = {"main": [[{"node": "S4 Merge Sources", "type": "main", "index": 0}]]}
b11_conn["S4 Fetch Error (Smartlead)"] = {"main": [[{"node": "S4 Merge Sources", "type": "main", "index": 1}]]}
b11_conn["S4 Normalize HeyReach"] = {"main": [[{"node": "S4 Merge Sources", "type": "main", "index": 2}]]}
b11_conn["S4 Fetch Error (HeyReach)"] = {"main": [[{"node": "S4 Merge Sources", "type": "main", "index": 3}]]}
b11_conn.update(conns([("S4 Merge Sources", "S4 Aggregate")]))
# found live 2026-08-14 (S4 build resumed): this edge was never wired -- every execution silently
# dead-ended at "S4 Aggregate" (lastNode response mode just returned its raw output), never
# reaching S4 Any Matches?/Split/Combine at all. Same dead-end bug class as S3's
# Build-Upsert-Input/Combine misses earlier this session.
b11_conn.update(conns([("S4 Aggregate", "S4 Any Matches?")]))
b11_conn["S4 Any Matches?"] = {"main": [
    [{"node": "S4 Split Matches", "type": "main", "index": 0}],
    [{"node": "S4 Combine", "type": "main", "index": 0}],
]}
b11_conn["S4 Has Identity?"] = {"main": [
    [{"node": "FIRE_S4?", "type": "main", "index": 0}],
    [{"node": "S4 Log No Identity", "type": "main", "index": 0}],
]}
b11_conn["FIRE_S4?"] = {"main": [
    [{"node": "S4 Call UpsertLedger", "type": "main", "index": 0}],
    [{"node": "S4 Write Barrier", "type": "main", "index": 0}],
]}
b11_conn.update(conns([("S4 Write Barrier", "S4 Merge Identity Paths")]))
b11_conn["S4 Log No Identity"] = {"main": [
    [{"node": "S4 Merge Identity Paths", "type": "main", "index": 1}],
]}
b11_conn.update(conns([("S4 Merge Identity Paths", "S4 Combine")]))
b11_conn.update(conns([("S4 Combine", "S4 MODE == dev?")]))
b11_conn["S4 MODE == dev?"] = {"main": [
    [{"node": "S4 Send Guard", "type": "main", "index": 0}],
    [],
]}
b11_wf = wf("dnc_s4_event_populations", b11, b11_conn)
write("workflows/dnc_s4_event_populations/dnc_s4_event_populations.json", b11_wf)

# ===========================================================================
# Build 13) dnc_label_reversal  (Melisa's ruling, 2026-08-14 -- URGENT, same-day)
# The DO NOT CONTACT label must be ONLY on explicit opt-outs (client/unsubscribe reasons), not the
# whole registry -- labels drive team filters and interact with nurture, unlike the person FIELD
# (686), which correctly stays on all 2,262 and is untouched by this reversal.
#
# Precise undo, not a broader relabeling pass: the original projection only ever labeled
# leads[0] (the FIRST lead returned for a person, per PD Classify's own `leads.length ?
# leads[0].id : null`) -- this reversal checks/strips exactly that same lead, matching the actual
# scope of what was written, not inventing new behavior. Union-preserving: only our specific label
# id is ever removed from label_ids; every other label on the lead is left untouched.
#
# Candidate SOURCE (revised 2026-08-14, superseding this workflow's own registry-reason scan):
# the auditor's frozen dnc_projection_labelled_1978.json is authoritative for WHICH ids the
# projection actually labelled -- not a fresh registry query, which could drift from what's
# actually on the wire. Per Nik's explicit ruling: removal set = that 1,978-id artifact MINUS
# person 4538ad40 (Person-d443dfbd -- pre-labelled BEFORE the projection ran, confirmed in
# MANIFEST.json's "already_carried_the_label_pre_run", always out of scope regardless of his
# registry reason). Expected: 1,977. The driver (dnc_fire_reversal_chunk.py) loads the artifact
# off disk and POSTs the full id list as frozen_ids on every chunk call; this workflow never
# re-derives it and never bakes the list into the generator.
#
# IMPORTANT ID-SPACE FIX (found live, first dry-run): the frozen artifact's ids are Pipedrive
# LEAD ids (uuid, e.g. "00144f20-..."), NOT person ids -- registry rows key off the numeric
# pipedrive_person_id (e.g. 43923), a completely different id space. Joining frozen-lead-id
# directly against registry.pipedrive_person_id gave 0 matches out of 1977 on the first live
# dry-run (every single one came back no_registry_match) before this was caught. The correct
# join order is: fetch each frozen LEAD by id first (GET /v1/leads/{id} returns person_id inline),
# THEN look up that person_id in the registry to get its reason -- not the other way around.
#
# Classification (KEEP/REMOVE) still applies ON TOP of the frozen set, per Melisa's ruling --
# the frozen set is "everyone the projection touched", the reason-based filter is "of those, who
# is an explicit opt-out and must stay labelled":
#   KEEP:   reason IN {client, unsubscribe} -- entry_type=explicit_opt_out, unambiguous.
#   REMOVE: everything else (expected to be ~all 1,977).
#   Anomalies (surfaced, never silently auto-stripped): a frozen lead whose person_id has no
#   registry row at all (outcome no_registry_match) -- would mean the projection labelled someone
#   this registry doesn't know about, which should never happen but must be visible if it does.
# ===========================================================================
DNC_LABEL_ID = "52a7c290-fc73-11f0-ad98-81d4703453f3"
LABEL_KEEP_REASONS = {"client", "unsubscribe"}
MARTINETS_PRELABELLED_ID = "4538ad40-4eb7-11f1-9d0a-8ddac4d89290"

r_classify_js = (
    # No registry join here -- the frozen lead-id list IS the candidate set (minus Martinets AND
    # minus any caller-supplied live_exclusion_ids). The reason-based KEEP/REMOVE decision needs
    # each lead's person_id, which only the per-lead fetch downstream (R Get Lead By Id) provides
    # -- see r_check_and_strip_js.
    #
    # live_exclusion_ids added 2026-08-14 (auditor's boundary-check finding): the frozen morning
    # snapshot can drift from live state by fire time -- 9 of the 1,977 had already lost the label
    # by some OTHER actor before this reversal ever touched them, independent of this workflow.
    # Stripping them again would be a no-op (R Check And Strip already reports 'already_correct'
    # for a lead that doesn't carry the label), so this isn't a correctness gap on its own -- but
    # the auditor's re-anchor pass needs a way to tell this workflow "treat these ids as already
    # settled, don't even attempt them" without waiting for a full generator/redeploy cycle each
    # time drift is found. A driver-supplied list, exactly the same frozen-external-list shape as
    # frozen_ids itself, not hardcoded here (the exact ids are still being confirmed).
    "const cfg = $('CONFIG').first().json;\n"
    "const frozenIds = Array.isArray(cfg.frozen_ids) ? cfg.frozen_ids : [];\n"
    "const liveExclusions = new Set(Array.isArray(cfg.live_exclusion_ids) ? cfg.live_exclusion_ids : []);\n"
    "const frozenSet = [...new Set(frozenIds.filter(id => id !== '%s' && !liveExclusions.has(id)))];\n"
    "return [{ json: { matches: frozenSet.map(id => ({ lead_id: id })), count: frozenSet.length,\n"
    "  live_exclusions_applied: liveExclusions.size } }];\n"
) % MARTINETS_PRELABELLED_ID
r_limit_chunk_js = (
    # "R Classify" emits ONE aggregated object with a nested .matches array (same shape as S3's
    # aggregate-then-split pattern), NOT a flat per-item list (the Pipedrive sweep's different
    # pattern) -- found live: $input.all() here was giving exactly 1 item (the wrapper itself),
    # so this node sliced 1 "row" (the wrapper) every single chunk, never advancing past offset 1.
    "const agg = $json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const rows = Array.isArray(agg.matches) ? agg.matches : [];\n"
    "const totalPending = rows.length;\n"
    # cfg.offset, not a hardcoded 0 -- without this the resumable cursor is decorative: every
    # chunk would re-slice the SAME first chunk_size candidates forever, never reaching the rest
    # (idempotent, so no data damage, but the sweep would never actually complete).
    "const chunk = rows.slice(cfg.offset, cfg.offset + cfg.chunk_size);\n"
    "return chunk.map(r => ({ json: Object.assign({}, r, { total_pending_before_chunk: totalPending }) }));\n"
)
r_check_and_strip_js = (
    "const resp = $json;\n"
    "const upstream = $('R Limit Chunk').item.json;\n"
    "const lead = (resp && resp.data && typeof resp.data === 'object' && !Array.isArray(resp.data)) ? resp.data : null;\n"
    "if (!lead) return { json: { lead_id: upstream.lead_id, outcome: 'no_lead' } };\n"
    # join lead.person_id (a plain scalar on the v1 lead object, per PD Classify's own
    # `{ lead_id: lead.id, person_id: lead.person_id }` shape) against the registry to get reason.
    "const registryRows = $('R Get Registry Candidates').all().map(i => i.json);\n"
    "const registryRow = registryRows.find(r => String(r.pipedrive_person_id) === String(lead.person_id));\n"
    "const reason = registryRow ? registryRow.reason : null;\n"
    "const KEEP = %s;\n"
    "if (reason && KEEP.includes(reason)) {\n"
    "  return { json: { lead_id: lead.id, outcome: 'kept_for_reason', reason } };\n"
    "}\n"
    "const hasLabel = Array.isArray(lead.label_ids) && lead.label_ids.includes('%s');\n"
    "if (!hasLabel) return { json: { lead_id: lead.id, outcome: 'already_correct' } };\n"
    "if (!reason) {\n"
    "  return { json: { lead_id: lead.id, person_id: lead.person_id, outcome: 'no_registry_match' } };\n"
    "}\n"
    "const strippedLabels = lead.label_ids.filter(id => id !== '%s');\n"
    "return { json: { lead_id: lead.id, outcome: 'to_strip', reason, stripped_labels: strippedLabels } };\n"
) % (json.dumps(list(LABEL_KEEP_REASONS)), DNC_LABEL_ID, DNC_LABEL_ID)
r_lead_fetch_error_js = (
    # found live 2026-08-14 (auditor's boundary-check re-verification): 5 frozen leads no longer
    # resolve via GET /v1/leads/{id} at all (vanished between this project's own dry-run and the
    # auditor's later re-check -- state genuinely drifting, not a bug in either check). Before this
    # fix, R Get Lead By Id's onError:continueErrorOutput branch was UNWIRED -- exactly the silent-
    # write-failure-gap bug class from the Pipedrive sweep earlier today, just on a read instead of
    # a write. A 404 here would have silently vanished the item entirely: never reaching R Check
    # And Strip, R Merge Outcomes, or R Combine's tally -- outcomes.length would fall short of the
    # chunk's real item count, under-advancing next_offset and eventually reprocessing the same
    # range forever without ever surfacing why. Now visible as its own outcome instead.
    "const upstream = $('R Limit Chunk').item.json;\n"
    "return { json: { lead_id: upstream.lead_id, outcome: 'fetch_error',\n"
    "  error_message: ($json.error && $json.error.message) || 'unknown fetch error' } };\n"
)
r_combine_js = (
    "const agg = $('R Classify').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const outcomes = $input.all().map(i => i.json).filter(j => j.outcome);\n"
    "const stripped = outcomes.filter(o => o.outcome === 'to_strip').length;\n"
    "const alreadyCorrect = outcomes.filter(o => o.outcome === 'already_correct').length;\n"
    "const noLead = outcomes.filter(o => o.outcome === 'no_lead').length;\n"
    "const keptForReason = outcomes.filter(o => o.outcome === 'kept_for_reason').length;\n"
    "const noRegistryMatch = outcomes.filter(o => o.outcome === 'no_registry_match').length;\n"
    "const fetchError = outcomes.filter(o => o.outcome === 'fetch_error').length;\n"
    "const done = (cfg.offset + outcomes.length) >= agg.count || outcomes.length === 0;\n"
    "const nextOffset = done ? null : cfg.offset + outcomes.length;\n"
    "const lines = [\n"
    "  `:label: DNC label reversal: chunk offset ${cfg.offset} -> ${done ? 'DONE' : nextOffset} "
    "(${agg.count} total candidates)`,\n"
    "  `${stripped} stripped this chunk, ${alreadyCorrect} already correct, ${noLead} no lead found`,\n"
    "  cfg.FIRE_REVERSAL ? '(live -- label removed on the wire)' : '(dry-run -- FIRE_REVERSAL is false, nothing written)',\n"
    "];\n"
    "if (keptForReason || noRegistryMatch) {\n"
    "  lines.push(`\\u26a0 this chunk: ${keptForReason} kept for reason (client/unsubscribe), "
    "${noRegistryMatch} frozen leads had no registry row at all`);\n"
    "}\n"
    "if (fetchError) {\n"
    "  const errIds = outcomes.filter(o => o.outcome === 'fetch_error').map(o => o.lead_id).join(', ');\n"
    "  lines.push(`\\u26a0 ${fetchError} frozen lead(s) no longer resolve at all (vanished since the "
    "snapshot this run was fired against): ${errIds}`);\n"
    "}\n"
    "if (agg.live_exclusions_applied) {\n"
    "  lines.push(`(${agg.live_exclusions_applied} live-exclusion id(s) removed from the candidate set before this run)`);\n"
    "}\n"
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: done ? cfg.alert_channel : cfg.telemetry_channel,\n"
    "  stripped_this_chunk: stripped, already_correct_this_chunk: alreadyCorrect, no_lead_this_chunk: noLead,\n"
    "  kept_for_reason_this_chunk: keptForReason, no_registry_match_this_chunk: noRegistryMatch,\n"
    "  fetch_error_this_chunk: fetchError,\n"
    "  total_candidates: agg.count, done, next_offset: nextOffset } }];\n"
)
r_confirm_strip_js = (
    # found live 2026-08-14 on the FIRST real live fire: R Patch Lead Labels is a raw HTTP node --
    # its response REPLACES $json with the Pipedrive PATCH response body ({success, data:{...}}),
    # discarding the {outcome:'to_strip', lead_id, ...} object that was ITS OWN input. R Combine's
    # `.filter(j => j.outcome)` then silently dropped all 100 real successes (no .outcome field on
    # a raw API response), reporting stripped=0 and concluding done=true after exactly one chunk --
    # while the actual PATCH calls had already succeeded correctly (verified: all 100 leads lost
    # ONLY the DNC label, every other label preserved). The underlying writes were never wrong;
    # only this reporting gap was. Restores the outcome context via the paired-item reference,
    # same pattern as R Check And Strip's own $('R Limit Chunk').item.json.
    "const resp = $json;\n"
    "const upstream = $('R Check And Strip').item.json;\n"
    "return { json: Object.assign({}, upstream, { patch_success: !!(resp && resp.success) }) };\n"
)

b13 = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_LABEL_REVERSAL}}", "responseMode": "lastNode",
          "options": {}}, -1400, tv=2, extra={"webhookId": "dnclabelreversal"}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                ("FIRE_REVERSAL", False, "boolean"),
                ("offset", "={{ $json.body.offset || 0 }}", "number"),
                ("chunk_size", 100, "number"),
                ("frozen_ids", "={{ $json.body.frozen_ids || [] }}", "array"),
                ("live_exclusion_ids", "={{ $json.body.live_exclusion_ids || [] }}", "array"),
                ("dnc_label_id", DNC_LABEL_ID, "string"),
                ("module", "dnc_label_reversal", "string")], x=-1200),
    dt_get_all_not_empty("R Get Registry Candidates", "pipedrive_person_id", -1000),
    code_node("R Classify", r_classify_js, -800),
    if_bool("R Any Candidates?", "={{ $json.count > 0 }}", -600),
    code_node("R Limit Chunk", r_limit_chunk_js, -400, y=100),
    http_pipedrive("R Get Lead By Id", "GET",
                   "=https://api.pipedrive.com/v1/leads/{{ $json.lead_id }}",
                   0, y=100, paginate=False),
    code_node_per_item("R Check And Strip", r_check_and_strip_js, 200, y=100),
    if_bool("R Needs Strip?", "={{ $json.outcome === 'to_strip' }}", 400, y=100),
    if_bool("FIRE_REVERSAL?", "={{ $('CONFIG').first().json.FIRE_REVERSAL }}", 600, y=60),
    http_pipedrive("R Patch Lead Labels", "PATCH",
                   "=https://api.pipedrive.com/v1/leads/{{ $json.lead_id }}",
                   800, y=40, body_expr="={{ { label_ids: $json.stripped_labels } }}"),
    code_node_per_item("R Confirm Strip", r_confirm_strip_js, 900, y=40),
    # two SEPARATE passthrough nodes, not one shared -- "R Needs Strip?" false branch (already
    # correct/no lead) and "FIRE_REVERSAL?" false branch (to-strip but dry-run) can BOTH carry real
    # items in the SAME execution (dry-run mode: every to_strip item takes this path too), so a
    # single shared node here would double-fire, same class of bug as every other Merge built
    # today. Three real per-item outcomes now converge on three DISTINCT merge inputs instead.
    # code_node_per_item, NOT code_node -- found live in the first real multi-item dry-run chunk
    # (100 candidates in, only 1 out of "R Merge Outcomes"): code_node()'s default
    # runOnceForAllItems mode + $input.first() is the exact same collapse-N-to-1 bug class as
    # PD Classify/SL Classify (see code_node_per_item's own comment), just on a passthrough node
    # instead of a real transform -- every item past the first was silently dropped before
    # reaching the merge. A per-item passthrough must actually run per item.
    code_node_per_item("R Already Correct/No Lead", "return { json: $json };", 800, y=180),
    code_node_per_item("R To-Strip (dry-run)", "return { json: $json };", 800, y=280),
    code_node_per_item("R Lead Fetch Error", r_lead_fetch_error_js, 200, y=380),
    node("R Merge Outcomes", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 4, "options": {}}, 1000, y=100, tv=3),
    code_node("R Combine", r_combine_js, -600, y=460),
    if_node("R MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", -400, y=460),
    code_node("R Send Guard", SEND_GUARD_JS, -200, y=460),
    slack_post("R Dev Summary", "={{ $json.slack_text }}", 0, channel_expr="={{ $json.target_channel }}"),
]
b13_conn = conns([
    ("Webhook", "CONFIG"), ("CONFIG", "R Get Registry Candidates"),
    ("R Get Registry Candidates", "R Classify"), ("R Classify", "R Any Candidates?"),
    ("R Limit Chunk", "R Get Lead By Id"),
    ("R Check And Strip", "R Needs Strip?"),
    ("R Send Guard", "R Dev Summary"),
])
b13_conn["R Any Candidates?"] = {"main": [
    [{"node": "R Limit Chunk", "type": "main", "index": 0}],
    [{"node": "R Combine", "type": "main", "index": 0}],
]}
b13_conn["R Needs Strip?"] = {"main": [
    [{"node": "FIRE_REVERSAL?", "type": "main", "index": 0}],
    [{"node": "R Already Correct/No Lead", "type": "main", "index": 0}],
]}
b13_conn["FIRE_REVERSAL?"] = {"main": [
    [{"node": "R Patch Lead Labels", "type": "main", "index": 0}],
    [{"node": "R To-Strip (dry-run)", "type": "main", "index": 0}],
]}
# error output (index 1) wired -- found live 2026-08-14 (auditor's boundary-check re-verification,
# 5 frozen leads no longer resolve at all): this was previously unwired, the exact
# silent-write-failure-gap bug class from the Pipedrive sweep, just on a read. See
# r_lead_fetch_error_js's own comment for the mechanism.
b13_conn["R Get Lead By Id"] = {"main": [
    [{"node": "R Check And Strip", "type": "main", "index": 0}],
    [{"node": "R Lead Fetch Error", "type": "main", "index": 0}],
]}
# four genuinely-simultaneous-possible outcomes (a real strip, an already-correct/no-lead skip, a
# to-strip-but-dry-run skip, and now a fetch-error), each on its own merge input -- same shape as
# every other per-item Merge built today, sized for the actual number of distinct outcome paths.
b13_conn.update(conns([("R Patch Lead Labels", "R Confirm Strip")]))
b13_conn["R Confirm Strip"] = {"main": [[{"node": "R Merge Outcomes", "type": "main", "index": 0}]]}
b13_conn["R Already Correct/No Lead"] = {"main": [[{"node": "R Merge Outcomes", "type": "main", "index": 1}]]}
b13_conn["R To-Strip (dry-run)"] = {"main": [[{"node": "R Merge Outcomes", "type": "main", "index": 2}]]}
b13_conn["R Lead Fetch Error"] = {"main": [[{"node": "R Merge Outcomes", "type": "main", "index": 3}]]}
b13_conn.update(conns([("R Merge Outcomes", "R Combine")]))
b13_conn.update(conns([("R Combine", "R MODE == dev?")]))
b13_conn["R MODE == dev?"] = {"main": [
    [{"node": "R Send Guard", "type": "main", "index": 0}],
    [],
]}
b13_wf = wf("dnc_label_reversal", b13, b13_conn)
write("workflows/dnc_label_reversal/dnc_label_reversal.json", b13_wf)

# ===========================================================================
# Build 14) dnc_s2_meeting_to_dnc  -- REBUILT 2026-09-15, Nik's GO ("both" signals, live daily
# poll, replacing the frozen-snapshot replay entirely -- not layered on it).
#
# Source = UNION of (a) Pipedrive leads that got label "5. Meeting" and (b) deals that entered
# stage "Qualified Meeting Set" (Janea Systems Consulting pipeline, id 8/54 -- confirmed live
# 2026-09-15), each within the last `lookback_hours` (24). Meeting ACTIVITIES stay excluded (96.6%
# are internal calendar blocks per the original auditor's recon) -- never keyed on. Memurai stages
# + partner pipeline stay OUT of scope per Nik's standing ruling.
#
# The OLD design (webhook consumes a caller-supplied person_ids list, backed by a frozen
# 2026-08-14 snapshot file that was never recomputed) is GONE, not extended -- confirmed live this
# only ever ran once, real detection needed a genuine live query. This version queries Pipedrive
# directly, every day, on its own.
#
# Fan-in eliminated BY DESIGN, not patched after the fact (Nik: "fix the flagged fan-in before
# scheduling") -- see the aggregate-then-split-out shape below: no Merge node anywhere in this
# workflow. "S2 Aggregate Candidates" runs exactly once per execution (before any per-item split),
# so "S2 Combine" is wired directly off it -- exactly the delta pusher / PD Aggregate fix pattern
# proven this session, applied from the start instead of retrofitted.
#
# Dedup: a person matched by BOTH signals gets TWO entries in the flat candidate list (one per
# signal), not merged into one before writing. This is deliberate, not an oversight -- Decide's own
# merge logic (reason_v1.js's reasonMergeV1) resets also_flagged to [] on a fresh insert regardless
# of what a caller supplies, so a pre-merged single call can never populate also_flagged correctly.
# Two SEQUENTIAL UpsertLedger calls for the same identity (n8n processes a Split Out's items one at
# a time, never concurrently, in this execution model) hit that function's SECOND branch instead --
# existing.reason='meeting_dnc' meets incoming.reason='meeting_dnc' (no downgrade, tie kept as
# existing) but source_ref differs ('5. Meeting label' vs 'Qualified Meeting Set stage'), so the
# second call's evidence correctly lands in also_flagged. Same identity, upsert semantics -> still
# exactly ONE row in the registry either way; this is the proven mechanism (confirmed live earlier
# today: Chirag R Shah's meeting_dnc + S3/Surfe signal, via two separate calls, landed in
# also_flagged correctly on the first try) -- not new/untested logic.
#
# reason=meeting_dnc, entry_type='replied' (see reason_v1.js) -- standard reply-tier TTL, not the
# permanent opt-out tier. Registry-only: no Pipedrive label write (Melisa's label-policy ruling).
# ===========================================================================
S2_MEETING_LABEL_ID = "35edf580-d19e-11ef-935e-7d712003f1b4"   # "5. Meeting", confirmed live 2026-09-15
S2_MEETING_PIPELINE_ID = 8    # "Janea Systems Consulting", confirmed live
S2_MEETING_STAGE_ID = 54      # "Qualified Meeting Set", confirmed live (also the pipeline's own entry stage)

s2r_ts_to_iso_js = (
    # Pipedrive's update_time comes back in TWO different shapes depending on resource: leads use
    # full ISO8601 with a trailing Z ("2026-09-15T14:36:37.264Z"), deals use a bare space-separated
    # UTC string with no timezone marker at all ("2026-09-14 20:26:31") -- confirmed live 2026-09-15
    # against real records from both endpoints in the same session. Both are UTC; normalize once.
    "function tsToIso(v) {\n"
    "  if (!v) return null;\n"
    "  const s = v.includes('T') ? v : v.replace(' ', 'T') + (v.endsWith('Z') ? '' : 'Z');\n"
    "  return new Date(s).toISOString();\n"
    "}\n"
)
s2r_label_classify_js = (
    s2r_ts_to_iso_js +
    "const cfg = $('CONFIG').first().json;\n"
    "const cutoff = new Date(Date.now() - cfg.lookback_hours * 3600 * 1000).toISOString();\n"
    "const resp = $json;\n"
    "const leads = Array.isArray(resp.data) ? resp.data : [];\n"
    # defensive: a single-call, single-page fetch (limit=cfg.fetch_limit, no native pagination --
    # avoids the multi-item-per-page fan-out risk of n8n's own paginate mode) could in principle
    # not reach back far enough on an unusually high-update-volume day. Never silently trust it --
    # flag it in the report instead (same discipline as "Pipedrive list-ordering trap", memory).
    "const oldestIso = leads.length ? tsToIso(leads[leads.length - 1].update_time) : null;\n"
    "const possiblyTruncated = oldestIso ? (oldestIso > cutoff) : false;\n"
    "const matches = [];\n"
    "for (const lead of leads) {\n"
    "  const updIso = tsToIso(lead.update_time);\n"
    "  if (!updIso || updIso < cutoff) continue;\n"
    "  if (!Array.isArray(lead.label_ids) || !lead.label_ids.includes(cfg.meeting_label_id)) continue;\n"
    "  if (!lead.person_id) continue;\n"
    "  matches.push({ person_id: lead.person_id, ref_id: lead.id, kind: 'label', source_ref: '5. Meeting label' });\n"
    "}\n"
    "return [{ json: { matches, count: matches.length, scanned: leads.length, possibly_truncated: possiblyTruncated } }];\n"
)
s2r_stage_classify_js = (
    s2r_ts_to_iso_js +
    "const cfg = $('CONFIG').first().json;\n"
    "const cutoff = new Date(Date.now() - cfg.lookback_hours * 3600 * 1000).toISOString();\n"
    "const resp = $json;\n"
    "const deals = Array.isArray(resp.data) ? resp.data : [];\n"
    "const oldestIso = deals.length ? tsToIso(deals[deals.length - 1].update_time) : null;\n"
    "const possiblyTruncated = oldestIso ? (oldestIso > cutoff) : false;\n"
    "const matches = [];\n"
    "for (const deal of deals) {\n"
    "  const updIso = tsToIso(deal.update_time);\n"
    "  if (!updIso || updIso < cutoff) continue;\n"
    # deal.person_id is a NESTED OBJECT ({value, name, ...}), unlike lead.person_id which is a bare
    # id -- confirmed live 2026-09-15 (deal 2267, Chirag R Shah).\n"
    "  const personId = deal.person_id && typeof deal.person_id === 'object' ? deal.person_id.value : deal.person_id;\n"
    "  if (!personId) continue;\n"
    "  matches.push({ person_id: personId, ref_id: deal.id, kind: 'stage', source_ref: 'Qualified Meeting Set stage' });\n"
    "}\n"
    "return [{ json: { matches, count: matches.length, scanned: deals.length, possibly_truncated: possiblyTruncated } }];\n"
)
s2r_aggregate_js = (
    # Runs exactly once per execution, BEFORE the per-item split -- the single always-executes
    # source both "S2 Split Candidates" and "S2 Combine" hang off, eliminating any need for a
    # Merge node anywhere downstream. This node's own DIRECT wire predecessor is
    # "S2 Classify Stage Signals" (stage runs SECOND in the hand-sequenced chain, see the header
    # comment) -- so $json here is the STAGE aggregate; the label aggregate (which ran earlier)
    # must be read via a named reference instead. Confirmed live 2026-09-15: got these two swapped
    # on the first build (both branches of a real dual-signal candidate came back kind:'stage'),
    # caught by inspecting the actual live output before flipping FIRE_S2, not assumed correct.\n"
    "const stageAgg = $json;\n"
    "const labelAgg = $('S2 Classify Label Signals').first().json;\n"
    "const candidates = [...labelAgg.matches, ...stageAgg.matches];\n"
    # reporting-only grouping -- does NOT affect what gets processed (both entries for a
    # dual-signal person flow through unchanged; see the header comment for why).\n"
    "const bySignalCount = new Map();\n"
    "for (const m of candidates) {\n"
    "  bySignalCount.set(m.person_id, (bySignalCount.get(m.person_id) || 0) + 1);\n"
    "}\n"
    "const distinctPeople = bySignalCount.size;\n"
    "const bothSignalPeople = Array.from(bySignalCount.values()).filter((n) => n > 1).length;\n"
    "return [{ json: {\n"
    "  candidates, count: candidates.length,\n"
    "  label_count: labelAgg.count, stage_count: stageAgg.count,\n"
    "  distinct_people: distinctPeople, both_signal_people: bothSignalPeople,\n"
    "  possibly_truncated: labelAgg.possibly_truncated || stageAgg.possibly_truncated,\n"
    "} }];\n"
)
s2r_build_upsert_input_js = (
    "const match = $('S2 Split Candidates').item.json;\n"
    + S3_PERSON_EXTRACT_JS +
    "return { json: {\n"
    "  linkedin_url: li, email, full_name: person.name || null,\n"
    "  reason: 'meeting_dnc', source: 'meeting_sweep', source_ref: match.source_ref,\n"
    "  date_precision: 'derived', expiry_review_pending: false,\n"
    "  pipedrive_person_id: match.person_id,\n"
    "  correlation_id: 's2_meeting_to_dnc:' + match.person_id + ':' + match.kind + ':' + match.ref_id,\n"
    "} };\n"
)
s2r_combine_js = (
    "const agg = $('S2 Aggregate Candidates').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    # named-ref .all() throws ExpressionError if the target node never ran at all in this
    # execution (not merely "ran with 0 items") -- happens on the (common) 0-candidates poll,
    # where "S2 Any Candidates?" 's false branch means the whole per-item chain, including this
    # node, never executes. Found live 2026-09-15 on the very first dry-run fire against real data.
    # Same defensive shape as PD Aggregate's PD Count Write Errors read -- guard, don't assume.\n"
    "let noIdentity = [];\n"
    "try { noIdentity = $('S2 Log No Identity').all().map((i) => i.json); } catch (e) { noIdentity = []; }\n"
    "const lines = [\n"
    "  `:handshake: S2 meeting-to-DNC: ${agg.count} signal(s) this poll "
    "(${agg.label_count} label, ${agg.stage_count} stage) \\u2192 ${agg.distinct_people} distinct "
    "person(s), ${agg.both_signal_people} matched both signals`,\n"
    "  cfg.FIRE_S2 ? '(live -- written to registry)' : '(dry-run -- FIRE_S2 is false, nothing written)',\n"
    "];\n"
    "if (agg.possibly_truncated) {\n"
    "  lines.push(':warning: fetch window may not fully cover the lookback period today (update "
    "volume outran the single-page fetch limit) -- worth a manual check, not silently trusted.');\n"
    "}\n"
    "if (noIdentity.length > 0) {\n"
    "  const names = noIdentity.map((n) => `${n.full_name} (pid ${n.pipedrive_person_id})`).join(', ');\n"
    "  lines.push(`:warning: ${noIdentity.length} skipped, no email/LinkedIn -- manual enrich needed: ${names}`);\n"
    "}\n"
    "const isBurst = agg.count >= %d;\n"
    "if (isBurst) lines.push(`:rotating_light: burst: ${agg.count} signals in one poll (threshold %d)`);\n"
    "const targetChannel = isBurst ? cfg.alert_channel : cfg.telemetry_channel;\n"
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: targetChannel,\n"
    "  count: agg.count, distinct_people: agg.distinct_people, both_signal_people: agg.both_signal_people,\n"
    "  skipped_no_identity: noIdentity.length, possibly_truncated: agg.possibly_truncated } }];\n"
) % (S3_BURST_THRESHOLD, S3_BURST_THRESHOLD)

b14 = [
    # webhook stays for supervised/on-demand fires (dnc_fire_s2_daily.py) -- no payload contract
    # needed anymore, it just re-runs the same live query the schedule would have run.
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_S2_MEETING_TO_DNC}}", "responseMode": "lastNode",
          "options": {}}, -1400, tv=2, extra={"webhookId": "dncs2meetingtodnc"}),
    schedule_daily("Daily Timer", 8, 0, -1400, y=-150),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                # default false by construction, same discipline as every other FIRE flag in this
                # project -- flipping it for real writes is a one-off live PATCH, never baked in here.
                ("FIRE_S2", False, "boolean"),
                ("meeting_label_id", S2_MEETING_LABEL_ID, "string"),
                ("meeting_pipeline_id", S2_MEETING_PIPELINE_ID, "number"),
                ("meeting_stage_id", S2_MEETING_STAGE_ID, "number"),
                ("lookback_hours", 24, "number"),
                # single-page, single-call fetch (no native n8n pagination -- avoids that mode's
                # own multi-item-per-page fan-out risk entirely). Measured live 2026-09-15: ~400
                # leads sorted by update_time DESC covers 24h of real update volume on this
                # instance -- 500 leaves real headroom. "possibly_truncated" in the report is the
                # safety net if that ever stops being true, not a silent assumption.
                ("fetch_limit", 500, "number"),
                ("module", "dnc_s2_meeting_to_dnc", "string")], x=-1200),
    http_pipedrive("S2 Get Recent Label Leads", "GET",
                   "=https://api.pipedrive.com/v1/leads?sort=update_time%20DESC&limit="
                   "{{ $('CONFIG').first().json.fetch_limit }}",
                   -1000, y=-400),
    code_node("S2 Classify Label Signals", s2r_label_classify_js, -800, y=-400),
    http_pipedrive("S2 Get Recent Stage Deals", "GET",
                   "=https://api.pipedrive.com/v1/deals?stage_id={{ $('CONFIG').first().json.meeting_stage_id }}"
                   "&sort=update_time%20DESC&limit={{ $('CONFIG').first().json.fetch_limit }}",
                   -600, y=-400),
    code_node("S2 Classify Stage Signals", s2r_stage_classify_js, -400, y=-400),
    code_node("S2 Aggregate Candidates", s2r_aggregate_js, -200, y=-400),
    if_bool("S2 Any Candidates?", "={{ $json.count > 0 }}", 0, y=-400),
    split_out("S2 Split Candidates", "candidates", 200, y=-300),
    http_pipedrive("S2 Get Person", "GET",
                   "=https://api.pipedrive.com/v1/persons/{{ $json.person_id }}", 400, y=-300),
    code_node_per_item("S2 Build Upsert Input", s2r_build_upsert_input_js, 600, y=-300),
    if_bool("S2 Has Identity?", "={{ !!($json.linkedin_url || $json.email) }}", 800, y=-300),
    code_node_per_item("S2 Log No Identity", s3_log_no_identity_js, 800, y=-180),
    if_bool("FIRE_S2?", "={{ $('CONFIG').first().json.FIRE_S2 }}", 1000, y=-300),
    exec_wf("S2 Call UpsertLedger", "DNC__UpsertLedger__v1", 1200, y=-340),
    code_node("S2 Combine", s2r_combine_js, -200, y=100),
    if_node("S2 MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", 0, y=100),
    code_node("S2 Send Guard", SEND_GUARD_JS, 200, y=100),
    slack_post("S2 Dev Summary", "={{ $json.slack_text }}", 400, y=100,
               channel_expr="={{ $json.target_channel }}"),
]
b14_conn = conns([
    ("Webhook", "CONFIG"), ("Daily Timer", "CONFIG"),
    ("CONFIG", "S2 Get Recent Label Leads"),
    ("S2 Get Recent Label Leads", "S2 Classify Label Signals"),
    ("S2 Classify Label Signals", "S2 Get Recent Stage Deals"),
    ("S2 Get Recent Stage Deals", "S2 Classify Stage Signals"),
    ("S2 Classify Stage Signals", "S2 Aggregate Candidates"),
    ("S2 Split Candidates", "S2 Get Person"),
    ("S2 Get Person", "S2 Build Upsert Input"),
    ("S2 Build Upsert Input", "S2 Has Identity?"),
    ("S2 Send Guard", "S2 Dev Summary"),
])
# "S2 Aggregate Candidates" fans OUT to both the per-item split AND directly to Combine -- plain
# fan-out (one source, two targets), the same shape used throughout this session's fixes today.
b14_conn["S2 Aggregate Candidates"] = {"main": [
    [{"node": "S2 Any Candidates?", "type": "main", "index": 0},
     {"node": "S2 Combine", "type": "main", "index": 0}],
]}
# false branch (0 candidates) has no target -- Combine already runs unconditionally off Aggregate
# above, so there is nothing left for this branch to feed.
b14_conn["S2 Any Candidates?"] = {"main": [
    [{"node": "S2 Split Candidates", "type": "main", "index": 0}],
    [],
]}
b14_conn["S2 Has Identity?"] = {"main": [
    [{"node": "FIRE_S2?", "type": "main", "index": 0}],
    [{"node": "S2 Log No Identity", "type": "main", "index": 0}],
]}
# both branches are clean dead ends -- Combine reads counts from "S2 Aggregate Candidates" and the
# no-identity list from "S2 Log No Identity" via named references, never from a converged stream.
b14_conn["FIRE_S2?"] = {"main": [
    [{"node": "S2 Call UpsertLedger", "type": "main", "index": 0}],
    [],
]}
b14_conn.update(conns([("S2 Combine", "S2 MODE == dev?")]))
b14_conn["S2 MODE == dev?"] = {"main": [
    [{"node": "S2 Send Guard", "type": "main", "index": 0}],
    [],
]}
b14_wf = wf("dnc_s2_meeting_to_dnc", b14, b14_conn)
write("workflows/dnc_s2_meeting_to_dnc/dnc_s2_meeting_to_dnc.json", b14_wf)

# ===========================================================================
# Build 15) dnc_s1_responded_to_dnc  (S1, union semantics per Nik/the written spec)
# Source = UNION of: Pipedrive lead label "3. Responded" (1,722 leads, verified live 2026-08-14 --
# matches the spec doc's own ~1,715-and-climbing estimate) + Smartlead per-lead history[] (any
# campaign, type==='REPLY', confirmed live via GET /campaigns/{id}/leads-statistics -- history rides
# along inline, no separate per-lead message-history call needed) + HeyReach reply signals.
# Each union member carries whatever reply_category it resolved to; Pipedrive-label-only matches
# (no provider category available) get the honest placeholder 'unclassified', never a guessed
# category and never left null (the exact 116-row gap this session's schema assert exists to close).
#
# Same frozen-external-candidate-list shape as S2/the label reversal: the driver resolves the union
# and hands this workflow a flat (pipedrive_person_id, reply_category, source) list -- this
# workflow never re-derives the union itself.
#
# Registry-only: no Pipedrive label write (Melisa's ruling -- "3. Responded" already exists from
# the original activity and is untouched; only the registry reason=reply_dnc is new here).
#
# Merge-without-weakening: candidates already in the registry via a WEAKER reason (e.g. Andrea
# Tassistro / Owkin, seeded manual_sheet) must be upgraded by UpsertLedger's existing
# never-downgrade reason-merge (reply_dnc outranks manual_sheet), not left at the weaker tier --
# exercised directly by fixtures/s1_poster_case_andrea_tassistro.json.
# ===========================================================================
s1_classify_js = (
    "const cfg = $('CONFIG').first().json;\n"
    "const rows = Array.isArray(cfg.candidates) ? cfg.candidates : [];\n"
    # dedupe by person_id -- if the SAME person surfaced via more than one source (e.g. both the
    # Pipedrive label AND a Smartlead REPLY), keep the richest reply_category rather than an
    # arbitrary one: a real provider category always outranks the 'unclassified' placeholder.
    "const byId = new Map();\n"
    "for (const r of rows) {\n"
    "  const id = String(r.pipedrive_person_id);\n"
    "  const prev = byId.get(id);\n"
    "  if (!prev) { byId.set(id, r); continue; }\n"
    "  if (prev.reply_category === 'unclassified' && r.reply_category !== 'unclassified') byId.set(id, r);\n"
    "}\n"
    "const deduped = [...byId.values()];\n"
    "return [{ json: { matches: deduped, count: deduped.length } }];\n"
)
s1_limit_chunk_js = (
    "const agg = $json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const rows = Array.isArray(agg.matches) ? agg.matches : [];\n"
    "const chunk = rows.slice(cfg.offset, cfg.offset + cfg.chunk_size);\n"
    "return chunk.map(r => ({ json: r }));\n"
)
s1_build_upsert_input_js = (
    "const match = $('S1 Limit Chunk').item.json;\n"
    + S3_PERSON_EXTRACT_JS +
    "return { json: {\n"
    "  linkedin_url: li, email, full_name: person.name || null,\n"
    "  reason: 'reply_dnc', reply_category: match.reply_category, source: match.source || 'reply_sweep',\n"
    "  source_ref: match.source || 'reply_sweep', date_precision: 'derived', expiry_review_pending: false,\n"
    "  pipedrive_person_id: match.pipedrive_person_id,\n"
    "  correlation_id: 's1_responded_to_dnc:' + match.pipedrive_person_id,\n"
    "} };\n"
)
s1_combine_js = (
    "const agg = $('S1 Classify').first().json;\n"
    "const cfg = $('CONFIG').first().json;\n"
    "const outcomes = $input.all().map(i => i.json);\n"
    "const noIdentity = outcomes.filter(j => j.skip_reason === 'no_identity');\n"
    "const done = (cfg.offset + cfg.chunk_size) >= agg.count || agg.count === 0;\n"
    "const nextOffset = done ? null : cfg.offset + cfg.chunk_size;\n"
    "const lines = [\n"
    "  `:speech_balloon: S1 responded-to-DNC: chunk offset ${cfg.offset} -> ${done ? 'DONE' : nextOffset} "
    "(${agg.count} total candidates)`,\n"
    "  cfg.FIRE_S1 ? '(live -- written to registry)' : '(dry-run -- FIRE_S1 is false, nothing written)',\n"
    "];\n"
    "if (noIdentity.length > 0) {\n"
    "  const names = noIdentity.map(n => `${n.full_name} (pid ${n.pipedrive_person_id})`).join(', ');\n"
    "  lines.push(`:warning: ${noIdentity.length} skipped, no email/LinkedIn -- manual enrich needed: ${names}`);\n"
    "}\n"
    # same fix as S2 Combine's matches_this_chunk bug, found live on THIS workflow's own first
    # real dry-run (18*100=1800 reported vs. 1717 real candidates) -- see that comment for detail.
    "return [{ json: { slack_text: lines.join('\\n'), target_channel: done ? cfg.alert_channel : cfg.telemetry_channel,\n"
    "  matches_this_chunk: outcomes.length, skipped_no_identity: noIdentity.length, total_candidates: agg.count,\n"
    "  done, next_offset: nextOffset } }];\n"
)

b15 = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_S1_RESPONDED_TO_DNC}}", "responseMode": "lastNode",
          "options": {}}, -1400, tv=2, extra={"webhookId": "dncs1respondedtodnc"}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                ("FIRE_S1", False, "boolean"),
                ("offset", "={{ $json.body.offset || 0 }}", "number"),
                ("chunk_size", 100, "number"),
                ("candidates", "={{ $json.body.candidates || [] }}", "array"),
                ("module", "dnc_s1_responded_to_dnc", "string")], x=-1200),
    code_node("S1 Classify", s1_classify_js, -1000),
    if_bool("S1 Any Candidates?", "={{ $json.count > 0 }}", -800),
    code_node("S1 Limit Chunk", s1_limit_chunk_js, -600, y=100),
    http_pipedrive("S1 Get Person", "GET",
                   "=https://api.pipedrive.com/v1/persons/{{ $json.pipedrive_person_id }}", -400, y=100),
    code_node_per_item("S1 Build Upsert Input", s1_build_upsert_input_js, -200, y=100),
    if_bool("S1 Has Identity?", "={{ !!($json.linkedin_url || $json.email) }}", 0, y=100),
    code_node_per_item("S1 Log No Identity", s3_log_no_identity_js, 0, y=220),
    if_bool("FIRE_S1?", "={{ $('CONFIG').first().json.FIRE_S1 }}", 200, y=100),
    exec_wf("S1 Call UpsertLedger", "DNC__UpsertLedger__v1", 400, y=60),
    # same fix as S2 Write Barrier's collapse-to-1 bug -- see that comment for the mechanism.
    code_node_per_item("S1 Write Barrier", "return { json: $json };", 600, y=100),
    node("S1 Merge Identity Paths", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 2, "options": {}}, 800, y=160, tv=3),
    code_node("S1 Combine", s1_combine_js, -600, y=460),
    if_node("S1 MODE == dev?", "={{ $('CONFIG').first().json.MODE }}", "dev", -400, y=460),
    code_node("S1 Send Guard", SEND_GUARD_JS, -200, y=460),
    slack_post("S1 Dev Summary", "={{ $json.slack_text }}", 0, channel_expr="={{ $json.target_channel }}"),
]
b15_conn = conns([
    ("Webhook", "CONFIG"), ("CONFIG", "S1 Classify"), ("S1 Classify", "S1 Any Candidates?"),
    ("S1 Limit Chunk", "S1 Get Person"),
    ("S1 Get Person", "S1 Build Upsert Input"),
    ("S1 Build Upsert Input", "S1 Has Identity?"),
    ("S1 Call UpsertLedger", "S1 Write Barrier"),
    ("S1 Send Guard", "S1 Dev Summary"),
])
b15_conn["S1 Any Candidates?"] = {"main": [
    [{"node": "S1 Limit Chunk", "type": "main", "index": 0}],
    [{"node": "S1 Combine", "type": "main", "index": 0}],
]}
b15_conn["S1 Has Identity?"] = {"main": [
    [{"node": "FIRE_S1?", "type": "main", "index": 0}],
    [{"node": "S1 Log No Identity", "type": "main", "index": 0}],
]}
b15_conn["FIRE_S1?"] = {"main": [
    [{"node": "S1 Call UpsertLedger", "type": "main", "index": 0}],
    [{"node": "S1 Write Barrier", "type": "main", "index": 0}],
]}
b15_conn.update(conns([("S1 Write Barrier", "S1 Merge Identity Paths")]))
b15_conn["S1 Log No Identity"] = {"main": [
    [{"node": "S1 Merge Identity Paths", "type": "main", "index": 1}],
]}
b15_conn.update(conns([("S1 Merge Identity Paths", "S1 Combine")]))
b15_conn.update(conns([("S1 Combine", "S1 MODE == dev?")]))
b15_conn["S1 MODE == dev?"] = {"main": [
    [{"node": "S1 Send Guard", "type": "main", "index": 0}],
    [],
]}
b15_wf = wf("dnc_s1_responded_to_dnc", b15, b15_conn)
write("workflows/dnc_s1_responded_to_dnc/dnc_s1_responded_to_dnc.json", b15_wf)

# ===========================================================================
# Build 16) dnc_escalation_detector  (Nik, 2026-08-14 -- alert-only skeleton, auto-pause next week)
# Hourly: registry (active rows) INTERSECT active COLD campaigns' current lead lists. Alert to ops
# if any hit, otherwise fully silent (no telemetry post either) -- a separate daily heartbeat is
# the only always-on signal, same "__idle" lesson as S3's watcher.
#
# NURTURE EXEMPTION (Melisa raised it, Nik promised the patch): a registry person showing up in a
# NURTURE campaign is BY DESIGN (the earlier Gmail experiment already proved global-unsubscribe
# suppresses nurture sends too, so nurture and DNC already interact deliberately) -- never an
# escalation. Nurture campaigns identified live: every campaign whose sender mailbox is
# @janeasystems.com (verified 2026-08-14, 7 campaigns -- team members' own inboxes, not a cold
# lookalike-domain sender). Hardcoded here, not re-derived every run (a campaign's sender doesn't
# change hour to hour; re-scanning email-accounts for all 117 campaigns hourly would be wasteful).
#
# "Active" status, flagged assumption: verified live 2026-08-14 that EVERY one of the 117 current
# Smartlead campaigns is COMPLETED/PAUSED/DRAFTED/STOPPED -- none are currently sending, so there
# is no live campaign to confirm the real "actively sending" status string against. Defined here by
# EXCLUSION (status NOT IN those 4 known-inactive values) rather than inclusion of a guessed
# "ACTIVE" string, so an unseen future status defaults to "treat as active" -- errs toward more
# alerting, never a missed real violation. Confirm against Melisa/Smartlead docs once any campaign
# actually goes active again.
#
# Bounded, not yet paginated: each active-cold campaign's leads are read as a single capped page
# (500, Smartlead's practical per-call ceiling elsewhere in this project). truncated=true surfaces
# if a campaign has more than that -- flagged, not silently dropped -- since there is currently no
# live active campaign large enough to test real pagination against.
# ===========================================================================
NURTURE_CAMPAIGN_IDS = [3721507, 3721506, 3651523, 3092907, 3092906, 3092903, 3092651]
INACTIVE_STATUSES = ["COMPLETED", "PAUSED", "DRAFTED", "STOPPED"]

d_classify_campaigns_js = (
    "const cfg = $('CONFIG').first().json;\n"
    "const nurture = new Set(JSON.parse(cfg.nurture_campaign_ids));\n"
    "const INACTIVE = %s;\n"
    "const camps = $input.all().map(i => i.json);\n"
    "const activeCold = camps.filter(c => !INACTIVE.includes(c.status) && !nurture.has(c.id));\n"
    "return [{ json: { active_cold_campaigns: activeCold.map(c => ({ id: c.id, name: c.name, status: c.status })),\n"
    "  count: activeCold.length, total_campaigns: camps.length } }];\n"
) % json.dumps(INACTIVE_STATUSES)
d_check_intersection_js = (
    "const resp = $json;\n"
    "const campaign = $('Split Active Campaigns').item.json;\n"
    "const leads = Array.isArray(resp.data) ? resp.data : [];\n"
    "const registryRows = $('Get Registry Active Rows').all().map(i => i.json);\n"
    "const emailSet = new Map(registryRows.filter(r => r.email_lc).map(r => [r.email_lc, r]));\n"
    "const liSet = new Map(registryRows.filter(r => r.linkedin_url_norm).map(r => [r.linkedin_url_norm, r]));\n"
    "const hits = [];\n"
    "for (const row of leads) {\n"
    "  const l = row.lead || {};\n"
    "  const email = (l.email || '').toLowerCase();\n"
    "  const li = (l.linkedin_profile || '').toLowerCase();\n"
    "  const reg = (email && emailSet.get(email)) || (li && liSet.get(li));\n"
    "  if (reg) {\n"
    "    hits.push({ full_name: [l.first_name, l.last_name].filter(Boolean).join(' ') || null, email: l.email || null,\n"
    "      campaign_id: campaign.id, campaign_name: campaign.name, entry_type: reg.entry_type, reason: reg.reason });\n"
    "  }\n"
    "}\n"
    "return { json: { hits, campaign_id: campaign.id, campaign_name: campaign.name, leads_checked: leads.length,\n"
    "  truncated: leads.length >= 500 } };\n"
)
d_aggregate_hits_js = (
    "const results = $input.all().map(i => i.json);\n"
    "const hits = results.flatMap(r => r.hits || []);\n"
    "const truncatedCampaigns = results.filter(r => r.truncated).map(r => r.campaign_name);\n"
    "return [{ json: { hits, checked_campaigns: results.length,\n"
    "  leads_checked: results.reduce((s, r) => s + (r.leads_checked || 0), 0),\n"
    "  truncated_campaigns: truncatedCampaigns } }];\n"
)
d_zero_state_js = (
    "return [{ json: { hits: [], checked_campaigns: 0, leads_checked: 0, truncated_campaigns: [] } }];\n"
)
d_combine_js = (
    "const cfg = $('CONFIG').first().json;\n"
    "const classify = $('Classify Active Cold Campaigns').first().json;\n"
    "const agg = $json;\n"
    "const hits = agg.hits || [];\n"
    "const lines = [];\n"
    "if (hits.length > 0) {\n"
    "  lines.push(`:rotating_light: DNC escalation: ${hits.length} registry person(s) found in "
    "${classify.count} active COLD campaign(s)`);\n"
    "  for (const h of hits.slice(0, 20)) {\n"
    "    lines.push(`  - ${h.full_name || h.email} (${h.reason || h.entry_type}) in \"${h.campaign_name}\"`);\n"
    "  }\n"
    "  if (hits.length > 20) lines.push(`  ...and ${hits.length - 20} more`);\n"
    "}\n"
    "if ((agg.truncated_campaigns || []).length > 0) {\n"
    "  lines.push(`:warning: campaign(s) with >=500 leads, only the first page was checked: "
    "${agg.truncated_campaigns.join(', ')} -- pagination not yet built`);\n"
    "}\n"
    "const sd = $getWorkflowStaticData('global');\n"
    "const today = String(cfg.now).slice(0, 10);\n"
    "if (sd.statDate !== today) { sd.statDate = today; sd.runsToday = 0; sd.hitsToday = 0; }\n"
    "sd.runsToday = (sd.runsToday || 0) + 1;\n"
    "sd.hitsToday = (sd.hitsToday || 0) + hits.length;\n"
    "return [{ json: { slack_text: lines.join('\\n'), has_hits: hits.length > 0, hit_count: hits.length,\n"
    "  active_cold_campaign_count: classify.count, total_campaigns: classify.total_campaigns } }];\n"
)
d_heartbeat_js = (
    "const sd = $getWorkflowStaticData('global');\n"
    "const runs = sd.runsToday || 0; const hits = sd.hitsToday || 0;\n"
    "return [{ json: { slack_text: `:mag: DNC escalation detector alive: ${runs} run(s) today, "
    "${hits} hit(s) found`, target_channel: 'C0BQM1X9ZUY' } }];\n"
)

b16 = [
    schedule_interval("Hourly Timer", 60, -1400),
    # manual-test trigger ONLY -- lets the driver fire this on demand for verification (n8n's
    # public API has no "run now" endpoint for a schedule-triggered workflow); the real production
    # path is still Hourly Timer, this is purely so today's zero-active-campaigns path -- the only
    # path actually live-testable right now, since no Smartlead campaign is currently active -- can
    # be verified without waiting up to 60 minutes for the first real tick.
    node("Manual Test Trigger", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_ESCALATION_DETECTOR_TEST}}", "responseMode": "lastNode",
          "options": {}}, -1400, y=-200, tv=2, extra={"webhookId": "dncescalationdetectortest"}),
    set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                ("dev_channel_guard", OPS_CHANNEL, "string"),
                ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                ("nurture_campaign_ids", json.dumps(NURTURE_CAMPAIGN_IDS), "string"),
                ("now", "={{ $now.toISO() }}", "string"),
                ("module", "dnc_escalation_detector", "string")], x=-1200),
    http_smartlead("Get Campaigns", "GET", "https://server.smartlead.ai/api/v1/campaigns", -1000),
    code_node("Classify Active Cold Campaigns", d_classify_campaigns_js, -800),
    if_bool("Any Active Cold Campaigns?", "={{ $json.count > 0 }}", -600),
    # NOT dt_get() -- that helper has no returnAll:True and would silently cap at whatever n8n's
    # default page size is, exactly the kind of undercount this project already burned itself on
    # once (the archived-leads list-read blind spot). Full returnAll scan, matching
    # dt_get_all_not_empty's shape but with an eq condition instead of isNotEmpty.
    node("Get Registry Active Rows", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": _data_table_ref("dnc_registry_dev"),
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "status", "condition": "eq", "keyValue": "active"}]},
        "options": {}
    }, -400, y=100, tv=1, extra={"alwaysOutputData": True}),
    split_out("Split Active Campaigns", "active_cold_campaigns", -400, y=100),
    http_smartlead("Get Campaign Leads", "GET",
                   "=https://server.smartlead.ai/api/v1/campaigns/{{ $json.id }}/leads?offset=0&limit=500",
                   -200, y=100),
    code_node_per_item("Check Intersection", d_check_intersection_js, 0, y=100),
    code_node("Aggregate Hits", d_aggregate_hits_js, 200, y=100),
    code_node("Zero State", d_zero_state_js, -400, y=300),
    node("Merge Campaign Paths", "n8n-nodes-base.merge",
         {"mode": "append", "numberInputs": 2, "options": {}}, 400, y=200, tv=3),
    code_node("Combine", d_combine_js, 600, y=200),
    if_bool("Any Hits?", "={{ $json.has_hits }}", 800, y=200),
    code_node("Send Guard", SEND_GUARD_JS, 1000, y=180),
    slack_post("Escalation Alert", "={{ $json.slack_text }}", 1200, y=180,
               channel_expr="={{ $('CONFIG').first().json.alert_channel }}"),
    schedule_daily("Heartbeat Timer", 6, 10, -1400, y=500),
    code_node("Heartbeat Post", d_heartbeat_js, -1200, y=500),
    slack_post("Heartbeat Slack", "={{ $json.slack_text }}", -1000, y=500,
               channel_expr="={{ $json.target_channel }}"),
]
b16_conn = conns([
    ("Hourly Timer", "CONFIG"), ("Manual Test Trigger", "CONFIG"), ("CONFIG", "Get Campaigns"),
    ("Get Campaigns", "Classify Active Cold Campaigns"),
    ("Classify Active Cold Campaigns", "Any Active Cold Campaigns?"),
    ("Get Registry Active Rows", "Split Active Campaigns"),
    ("Split Active Campaigns", "Get Campaign Leads"),
    ("Get Campaign Leads", "Check Intersection"),
    ("Check Intersection", "Aggregate Hits"),
    ("Send Guard", "Escalation Alert"),
    ("Heartbeat Timer", "Heartbeat Post"), ("Heartbeat Post", "Heartbeat Slack"),
])
# handle zero-active-cold-campaigns cleanly: skip the registry read + lead fetch entirely, go
# straight to a trivial zero-state item -- both paths (real check, zero-skip) converge on the
# SAME 2-input Merge before Combine, same double-fire-safe shape as every other Merge this session.
b16_conn["Any Active Cold Campaigns?"] = {"main": [
    [{"node": "Get Registry Active Rows", "type": "main", "index": 0}],
    [{"node": "Zero State", "type": "main", "index": 0}],
]}
b16_conn["Aggregate Hits"] = {"main": [[{"node": "Merge Campaign Paths", "type": "main", "index": 0}]]}
b16_conn["Zero State"] = {"main": [[{"node": "Merge Campaign Paths", "type": "main", "index": 1}]]}
b16_conn.update(conns([("Merge Campaign Paths", "Combine")]))
b16_conn.update(conns([("Combine", "Any Hits?")]))
# silent-if-zero: the false branch is a true dead end, no post at all -- only a real hit or the
# separate daily heartbeat ever reaches Slack.
b16_conn["Any Hits?"] = {"main": [
    [{"node": "Send Guard", "type": "main", "index": 0}],
    [],
]}
b16_wf = wf("dnc_escalation_detector", b16, b16_conn)
write("workflows/dnc_escalation_detector/dnc_escalation_detector.json", b16_wf)

# ===========================================================================
# Build 17) dnc_pre_add_gate  (Nik, 2026-08-20 -- phase-2 pre-add DNC gate, G-05 candidate)
# Check-list service: a lead list in, CLEAN/BLOCKED/UNRESOLVABLE split out. Read-only against
# dnc_registry_dev -- reuses the ALREADY-EXISTING DNC__CheckLedger__v1 per-row (identity
# normalize + strongest-active-row lookup), the same primitive dnc_check_service's Slack
# @mention path already relies on, rather than re-deriving the matching logic a second time.
# This is THE fix for Stefan's broken pre-rebuild table reference too (2026-08-20 finding) --
# his own check path pointed at a table that no longer exists; this gate becomes his (and
# Melisa's) shared, single, currently-correct read path instead of a private one that can drift.
# ===========================================================================
gate_build_items_js = (
    # webhook-body convention (regression-tested elsewhere in this file): $json.body.*, never
    # bare $json.*. Accepts {rows: [{email?, linkedin_url?, ...any passthrough fields}, ...]} --
    # CSV is a CLIENT-side concern (the wrapper script converts CSV -> this JSON shape before
    # POSTing); the webhook itself only ever speaks JSON, avoiding multipart/binary-upload
    # parsing entirely -- one less unverified n8n node-shape to depend on.
    # Reads via $('Webhook').first().json, NOT bare $json -- this node no longer sits directly
    # after the Webhook trigger (the concurrency guard's bookkeeping nodes sit between them and
    # overwrite $json with their own output), same paired-item-reference class this project hit
    # once already in Classify Row / the R-Patch-Lead-Labels fire. Found live 2026-08-26 when the
    # concurrency guard shipped: every request failed with "body.rows must be a non-empty array"
    # even though real rows were sent, because $json was the concurrency node's output, not the
    # webhook's.\n"
    "const rows = ($('Webhook').first().json.body && $('Webhook').first().json.body.rows) || [];\n"
    "if (!Array.isArray(rows) || rows.length === 0) {\n"
    "  throw new Error('dnc_pre_add_gate: body.rows must be a non-empty array');\n"
    "}\n"
    "return rows.map((r, i) => ({ json: Object.assign({}, r, {\n"
    "  row_index: i,\n"
    "  email: r.email || null,\n"
    "  linkedin_url: r.linkedin_url || r.linkedinUrl || r.li_url || null,\n"
    "}) }));\n"
)
gate_cap_check_js = (
    # hard input cap -- reject BEFORE any lookup work happens (cheap: one code node, nothing
    # touches Pipedrive/the registry). 500 rows/call is the documented ceiling; over that, the
    # caller must split the list rather than the gate silently degrading.\n"
    "const items = $input.all();\n"
    "if (items.length > 500) {\n"
    "  return [{ json: { over_cap: true, count: items.length, error: 'too_many_rows',\n"
    "    message: 'dnc_pre_add_gate: ' + items.length + ' rows exceeds the 500-row cap for one call."
    " Split into multiple calls of <=500 rows each.' } }];\n"
    "}\n"
    "return items.map(i => ({ json: Object.assign({ over_cap: false }, i.json) }));\n"
)
# 2026-08-26 GATE v2 -- Nik's requirement: Clay-direct per-row HTTP must be the SUPPORTED path
# (table -> n8n -> verdicts back, no CSV detours), not a forbidden one. Incident #2's real cause
# wasn't concurrency per se -- it was that EVERY call, including a single-row one, spun up a
# nested DNC__CheckLedger__v1 SUBWORKFLOW execution (its own execution context, its own memory).
# Hundreds of concurrent calls meant hundreds of concurrent nested executions -- that's what
# exhausted the workers. Fixing the shape: the two dataTable lookups CheckLedger already does
# (by linkedin_url_norm, by email_lc) are inlined directly into this workflow's own graph instead
# of being invoked via executeWorkflow -- so ANY call, batch or single-row, is ONE execution with
# ONE or two lightweight Data Table reads, never a subworkflow spin-up. This replaces the
# reject-on-busy concurrency guard shipped a few minutes earlier: that guard treated cheap-to-fix
# expensive requests as something to ration; the real fix makes them cheap in the first place, so
# n8n's own execution queue (not a bespoke 429) is what should absorb a legitimate per-row burst.
# The dnc_gate_concurrency table/guard code is removed here, not left dormant -- it solved a
# problem this redesign eliminates.
#
# Correlation without pairedItem: the LinkedIn/Email lookups are fed ALL rows in the batch at once
# (one dataTable node call each, n8n runs the get per input item internally -- no subworkflow, no
# per-item execution overhead) rather than being chunked into fixed-size groups. Matching each
# found registry row back to the row(s) that should see it is done by VALUE (the found row's own
# linkedin_url_norm/email_lc columns), not by n8n's pairedItem lineage -- deliberately, since a
# lookup can legitimately fan out to 0/1/many rows per input and pairedItem correlation across an
# unpredictable fan-out was the one piece of this design not already proven elsewhere in this
# codebase. Correlating by value is simple, deterministic, and needs no new n8n-node-shape
# assumption. (Registry size checked live before choosing this shape: 32,978 rows / ~28MB JSON --
# too large to bulk-load whole-table per request, which is why targeted lookups, not a full-table
# read, are the right primitive here.)
gate_normalize_batch_js = (
    NORM + "\n\n"
    "const s = $json;\n"
    "const norm = normalizeIdentityV1({ linkedin_url: s.linkedin_url, email: s.email });\n"
    # row_key computed ONCE, here, and carried through every downstream step (ingress log,
    # classify output, enqueue, mark-done) so they all key on the exact same value -- avoids
    # recomputing the unresolvable-row fallback in multiple places and having them drift.\n"
    "const row_key = norm.identity_key || ('unresolvable:' + s.row_index + ':' + Date.now());\n"
    "return { json: Object.assign({}, s, { norm, row_key,\n"
    "  li_key: norm.linkedin_url_norm || '__DNC_NO_LI__', em_key: norm.email_lc || '__DNC_NO_EM__' }) };\n"
)
gate_classify_batch_js = (
    # replicates DNC__CheckLedger__v1's own Report logic (strongest-entry_type-wins,
    # amendment 2) verbatim, plus this gate's own on_dnc/clean/usage_hint -> BLOCKED/CLEAN/
    # UNRESOLVABLE mapping -- folded into one pass now that both lookups and classification run
    # in the SAME execution instead of across N nested subworkflow calls.\n"
    # OWN-DOMAIN GUARD, added 2026-08-26 (Stefan's check caught Noah Keimach -- a Janea employee
    # -- surfacing in his campaign-candidate list). This is deliberately checked BEFORE the
    # registry lookup and wins over every other outcome, including plain CLEAN: an @janeasystems
    # .com row must never enter a campaign list regardless of whether it happens to also carry a
    # registry entry. Distinct from plain employee_connection (which fires on external personal
    # LinkedIn connections a rep imported, and is a normal BLOCKED) -- this is our own team, a
    # different failure mode with a different, self-explaining result the caller can branch on.\n"
    "const OWN_DOMAIN = '@janeasystems.com';\n"
    # COMPANY-DOMAIN BLOCK, added 2026-09-09 (Company DNC, 1,373 banned domains from Clay). Fail-
    # open by the same positive-shape-check discipline as everywhere else in this project: a row
    # only counts as a real domain-block entry if it actually looks like one (status is a string),
    # so a missing/misresolving dnc_domains table degrades to "nothing is blocked", never a crash
    # and never a false BLOCKED. Checked AFTER own-domain (a Janea address must never be treated as
    # a banned company even in the freak case its own domain somehow landed in the import) but
    # BEFORE the person-level registry lookup -- a banned company blocks regardless of whether this
    # specific person has any reply/history of their own.\n"
    "const domainRows = ($('Get Domain Blocklist').all() || []).map(i => i.json);\n"
    "const looksLikeRealDomainRow = (r) => r && typeof r.status === 'string' && typeof r.domain === 'string';\n"
    "const bannedDomains = new Set(domainRows.every(looksLikeRealDomainRow)\n"
    "  ? domainRows.filter((r) => r.status === 'active').map((r) => r.domain) : []);\n"
    "const STRENGTH = { explicit_opt_out: 5, negative_reply: 4, replied: 3, employee_connection: 2, manual: 1 };\n"
    "const originals = $('Normalize Batch').all().map(i => i.json);\n"
    "const found = $input.all().map(i => i.json).filter(r => r && r.identity_key);\n"
    "const byLi = {}, byEm = {};\n"
    "for (const r of found) {\n"
    "  if (r.linkedin_url_norm) (byLi[r.linkedin_url_norm] = byLi[r.linkedin_url_norm] || []).push(r);\n"
    "  if (r.email_lc) (byEm[r.email_lc] = byEm[r.email_lc] || []).push(r);\n"
    "}\n"
    "const pick = (list) => list.slice().sort((a, b) => (STRENGTH[b.entry_type] || 0) - (STRENGTH[a.entry_type] || 0)"
    " || String(a.added_at || '').localeCompare(String(b.added_at || '')))[0];\n"
    "const results = originals.map((s) => {\n"
    "  const norm = s.norm;\n"
    "  let gate_result, reason, registry_row_ref;\n"
    "  const emailDomain = norm.email_lc ? norm.email_lc.slice(norm.email_lc.indexOf('@') + 1) : null;\n"
    "  if (norm.email_lc && norm.email_lc.endsWith(OWN_DOMAIN)) {\n"
    "    gate_result = 'OWN_TEAM'; reason = 'own_team \\u2014 exclude from any campaign list'; registry_row_ref = null;\n"
    "  } else if (emailDomain && bannedDomains.has(emailDomain)) {\n"
    "    gate_result = 'BLOCKED'; reason = 'company_dnc / ' + emailDomain; registry_row_ref = null;\n"
    "  } else if (!norm.identity_key) {\n"
    "    gate_result = 'UNRESOLVABLE'; reason = 'no LinkedIn URL or email to match on'; registry_row_ref = null;\n"
    "  } else {\n"
    "    const seen = {}; const all = [];\n"
    "    (byLi[s.li_key] || []).concat(byEm[s.em_key] || []).forEach((r) => {\n"
    "      const k = (r.id != null ? 'id:' + r.id : r.identity_key + '|' + r.added_at);\n"
    "      if (!seen[k]) { seen[k] = true; all.push(r); }\n"
    "    });\n"
    "    if (all.length === 0) {\n"
    "      gate_result = 'CLEAN'; reason = null; registry_row_ref = null;\n"
    "    } else {\n"
    "      const active = all.filter((r) => r.status === 'active');\n"
    "      if (active.length) {\n"
    "        const p = pick(active);\n"
    "        gate_result = 'BLOCKED';\n"
    "        reason = p.entry_type + (p.source ? (' / ' + p.source) : '');\n"
    "        registry_row_ref = (p.id != null ? p.id : (p.identity_key || null));\n"
    "      } else {\n"
    "        const p = pick(all);\n"
    "        gate_result = 'CLEAN';\n"
    "        reason = 'was ' + p.entry_type + ' until ' + (p.removed_at || p.expires_at || 'unknown') + ', currently clean';\n"
    "        registry_row_ref = null;\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "  const clean = Object.assign({}, s);\n"
    "  delete clean.over_cap; delete clean.norm; delete clean.li_key; delete clean.em_key;\n"
    "  return Object.assign(clean, { gate_result, reason, registry_row_ref, identity_key: norm.identity_key || null });\n"
    "});\n"
    "return results.map(r => ({ json: r }));\n"
)
gate_report_js = (
    # duration_ms/row_count self-reported here (elapsed since "Mark Start", right after Webhook)
    # so the liveness monitor can track real headroom over time instead of guessing at it --
    # Nik's point 5. No new credential/API access needed: purely self-timed within the execution.
    #
    # Found live 2026-08-26 from Stefan's ACTUAL Clay export (Speakers-and-Attendees-Enrichment):
    # 15 rows had really fired (HTTP 200), but only the ONE that came back BLOCKED had its
    # Gate Result/Reason columns populated in Clay -- the other 14 (all CLEAN) came back empty
    # despite a healthy 200 response. The per-classification-bucket response shape (clean[]/
    # blocked[]/unresolvable[]/rows[]) has no single flat field a simple per-row Clay column
    # mapping can point at regardless of outcome -- whatever field Clay's column currently reads
    # (almost certainly something like blocked[0].reason) only exists when the row happens to be
    # blocked. Fix: for the single-row call Clay's per-row column actually makes, ALSO spread
    # that one row's own result at the TOP level of the response (gate_result/reason/
    # registry_row_ref/identity_key) so a flat Clay mapping works no matter which bucket the row
    # landed in. Purely additive -- counts/clean/blocked/unresolvable/rows are unchanged for
    # existing batch-mode consumers.\n"
    "const rows = $input.all().map(i => { const r = Object.assign({}, i.json); delete r.row_key; return r; });\n"
    "const by = { CLEAN: [], BLOCKED: [], UNRESOLVABLE: [], OWN_TEAM: [] };\n"
    "for (const r of rows) (by[r.gate_result] || by.UNRESOLVABLE).push(r);\n"
    "rows.sort((a, b) => a.row_index - b.row_index);\n"
    "const startedAt = $('Mark Start').first().json.started_at;\n"
    "const single = rows.length === 1 ? {\n"
    "  gate_result: rows[0].gate_result, reason: rows[0].reason,\n"
    "  registry_row_ref: rows[0].registry_row_ref, identity_key: rows[0].identity_key,\n"
    "} : {};\n"
    "return [{ json: Object.assign({}, single, {\n"
    "  counts: { total: rows.length, clean: by.CLEAN.length, blocked: by.BLOCKED.length,\n"
    "            unresolvable: by.UNRESOLVABLE.length, own_team: by.OWN_TEAM.length },\n"
    "  clean: by.CLEAN, blocked: by.BLOCKED, unresolvable: by.UNRESOLVABLE, own_team: by.OWN_TEAM,\n"
    "  rows: rows, // full annotated list, original row order, for the launch-post artifact\n"
    "  checked_at: new Date().toISOString(),\n"
    "  duration_ms: Date.now() - startedAt, row_count: rows.length,\n"
    "}) }];\n"
)
# 2026-08-26 GATE v3 -- hybrid queue mode (Nik, confirmed 30-min turnaround acceptable on big
# tables). Sync stays the happy path for the common case (small batch, instance not already
# backlogged); anything bigger, or arriving while a backlog exists, queues instead of piling onto
# a live request -- same lesson as incident #2, generalized: never let load-shape surprise the
# instance, degrade to slower-but-safe instead. dnc_gate_queue does not exist yet -- same
# no-verified-creation-API situation as every table here, AND (2026-08-26 finding, the day's other
# saga) mode:"name" data-table references have proven unreliable from API-created workflows on
# this instance even for tables confirmed to exist with the right columns in the right project --
# once Nik creates this table, GATE_QUEUE_TABLE below needs its real id substituted the same way
# EVENT_LOG_TABLE was fixed in build_i04.py, BEFORE trusting any write to it.
GATE_QUEUE_TABLE_NAME = "dnc_gate_queue"
GATE_QUEUE_TABLE = _data_table_ref(GATE_QUEUE_TABLE_NAME)
GATE_SYNC_MAX_ROWS = 50
GATE_DRAIN_BATCH_SIZE = 50
GATE_DRAIN_INTERVAL_MINUTES = 2

# 2026-09-09: company-domain block (dnc_domains, 1,373 banned domains). Table created same day,
# real id CUkoLQxUxRuS1Lod (in TABLE_IDS above -- mode:"id" resolves automatically via
# _data_table_ref, never mode:"name", per this instance's proven-unreliable-name-mode history).
# Still fail-open regardless: the lookup node continues on error and the classify code below
# treats "couldn't read the blocklist" as "nothing is blocked", never as a crash or a false block.
GATE_DOMAINS_TABLE_NAME = "dnc_domains"
GATE_DOMAINS_TABLE = _data_table_ref(GATE_DOMAINS_TABLE_NAME)

gate_retrieve_build_js = (
    NORM + "\n\n"
    "const s = $json;\n"
    "const norm = normalizeIdentityV1({ linkedin_url: s.linkedin_url, email: s.email });\n"
    "return { json: Object.assign({}, s, { norm, row_key: norm.identity_key || null }) };\n"
)
gate_retrieve_report_js = (
    # symmetric with submit: the SAME per-row shape Clay already sends comes back in as the
    # retrieve request (Clay just re-submits the row it's waiting on) -- looked up by the same
    # identity_key a submit call would have stored it under.\n"
    "const requested = $('Build Retrieve Items').all().map(i => i.json);\n"
    "const found = $input.all().map(i => i.json).filter(r => r && r.row_key);\n"
    "const byKey = {};\n"
    "for (const r of found) { (byKey[r.row_key] = byKey[r.row_key] || []).push(r); }\n"
    "const pickLatest = (list) => list.slice().sort((a, b) => String(b.submitted_at || '').localeCompare(String(a.submitted_at || '')))[0];\n"
    "const results = requested.map((s) => {\n"
    "  const clean = Object.assign({}, s); delete clean.norm; delete clean.row_key;\n"
    "  const m = pickLatest(byKey[s.row_key] || []);\n"
    "  if (!m) return Object.assign(clean, { retrieve_status: 'not_found' });\n"
    "  if (m.status === 'done') {\n"
    "    let result = {}; try { result = JSON.parse(m.result_json || '{}'); } catch (e) {}\n"
    "    return Object.assign(clean, result, { retrieve_status: 'done' });\n"
    "  }\n"
    "  return Object.assign(clean, { retrieve_status: 'pending' });\n"
    "});\n"
    "const done = results.filter(r => r.retrieve_status === 'done');\n"
    "const pending = results.filter(r => r.retrieve_status !== 'done');\n"
    "const single = results.length === 1 ? Object.assign({ retrieve_status: results[0].retrieve_status },\n"
    "  results[0].retrieve_status === 'done' ? { gate_result: results[0].gate_result, reason: results[0].reason,\n"
    "    registry_row_ref: results[0].registry_row_ref, identity_key: results[0].identity_key } : {}) : {};\n"
    "return [{ json: Object.assign({}, single, { done, pending,\n"
    "  counts: { total: results.length, done: done.length, pending: pending.length } }) }];\n"
)
gate_decide_sync_or_queue_js = (
    # batch-level decision, applied uniformly to every row in the call -- a call either goes
    # sync or it queues as a whole, no per-row mixing (matches the single-call semantics Clay's
    # batch mode and column mode both expect). Fail-open: Check Queue Depth's error branch must
    # read as 'depth unknown', not '1+ pending row'. Found live 2026-08-26 (before this shipped
    # to anyone real): n8n's dataTable error output is NOT uniformly {error:...} -- against a
    # missing table this specific node crashed with an unrelated TypeError and its error branch
    # just PASSED THROUGH THE ORIGINAL INPUT ITEMS unchanged, so filtering on the absence of an
    # .error field caught nothing and every 2-row Barry-fixture call queued instead of going
    # sync. Fixed to a POSITIVE check instead: only count items that actually look like real
    # dnc_gate_queue rows (carry both row_key and status as strings) -- safe regardless of
    # whatever shape a given failure mode happens to produce.\n"
    "const items = $('Normalize Batch').all().map(i => i.json);\n"
    "const depthRows = $input.all().map(i => i.json)\n"
    "  .filter(r => r && typeof r.row_key === 'string' && typeof r.status === 'string');\n"
    "const anyPending = depthRows.length > 0;\n"
    "const sync = items.length <= %d && !anyPending;\n"
    "return items.map(it => ({ json: Object.assign({}, it, { __route: sync ? 'sync' : 'queue' }) }));\n"
) % GATE_SYNC_MAX_ROWS
gate_queue_response_js = (
    "const queuedCount = $('Decide Sync Or Queue').all().length;\n"
    "const priorPending = $('Check Queue Depth').all().length;\n"
    "const totalPending = priorPending + queuedCount;\n"
    "const eta = Math.ceil(totalPending / %d) * %d;\n"
    "return [{ json: { queued: queuedCount, eta_minutes: eta, batch_id: $execution.id,\n"
    "  note: 'retrieve with the same webhook: {\"retrieve\": true, \"rows\": [...]} -- eta is approximate.' } }];\n"
) % (GATE_DRAIN_BATCH_SIZE, GATE_DRAIN_INTERVAL_MINUTES)

g_enqueue_rows = dt_upsert_tbl("Enqueue Rows", {
    # row_key computed once in Normalize Batch, reused everywhere -- this upsert just transitions
    # the SAME ingress row (already written by Log Ingress with status='received') to 'pending'.\n"
    "row_key": "={{ $json.row_key }}",
    "batch_id": "={{ $execution.id }}", "status": "=pending",
    "payload_json": "={{ JSON.stringify($json) }}",
    "submitted_at": "={{ new Date().toISOString() }}",
}, ["row_key"], 400, GATE_QUEUE_TABLE_NAME, y=460)
g_enqueue_rows.update({"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})

g_log_ingress = dt_upsert_tbl("Log Ingress", {
    # P1 auditor fix, 2026-08-26: the crash-safety net itself -- written BEFORE any lookup or
    # classification, so a crash anywhere downstream still leaves an enumerable record of exactly
    # which identities were in the request (closes the "50 crashed executions, zero data
    # recoverable" gap from incident #2). Fail-open on purpose: a logging hiccup must not block a
    # real request, but that means ingress durability is only as good as this write succeeding --
    # flagged, not hidden.\n"
    "row_key": "={{ $json.row_key }}", "batch_id": "={{ $execution.id }}", "status": "=received",
    "payload_json": "={{ JSON.stringify($json) }}",
    "submitted_at": "={{ new Date().toISOString() }}",
}, ["row_key"], -200, GATE_QUEUE_TABLE_NAME, y=-100)
g_log_ingress.update({"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2})

g_mark_sync_done = dt_upsert_tbl("Mark Sync Done", {
    "row_key": "={{ $json.row_key }}", "status": "=done",
    "result_json": "={{ JSON.stringify({ gate_result: $json.gate_result, reason: $json.reason,"
                   " registry_row_ref: $json.registry_row_ref, identity_key: $json.identity_key }) }}",
    "completed_at": "={{ new Date().toISOString() }}",
}, ["row_key"], 900, GATE_QUEUE_TABLE_NAME, y=100)
g_mark_sync_done.update({"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2})

# QUEUE MODE REMOVED 2026-09-02 (Nik's decision, discovered live 2026-09-09 when a routine deploy
# almost silently resurrected it). dnc_gate_queue was never created; dnc_gate_queue_drainer never
# ran a single time; every "queued" response the old v3 gate ever sent was a promise that could
# never be kept. Nik cut the whole apparatus and replaced the retrieve branch with an honest 410.
# This generator now matches that reality byte-for-byte (reconstructed directly from the live
# node's own explanatory comment + a live node-by-node diff, not guessed) -- g_log_ingress,
# g_enqueue_rows, g_mark_sync_done, GATE_QUEUE_TABLE*, gate_decide_sync_or_queue_js,
# gate_queue_response_js, gate_retrieve_build_js/gate_retrieve_report_js are ALL DEAD CODE from
# here on; kept defined above only because dnc_gate_queue_drainer (inactive, orphaned by the same
# ruling) still references some of them, not because the gate needs them. Do not wire any of them
# into g_nodes/g_conn again without checking with Nik first.
gate_retrieve_removed_js = (
    "// QUEUE PATH REMOVED (2026-09-02, Nik's decision). The gate used to park batches over 50 rows in\n"
    "// a `dnc_gate_queue` table and answer {\"queued\": N, \"eta_minutes\": ...}.\n"
    "// `dnc_gate_queue_drainer` has never run and the table does not exist, so that answer was a\n"
    "// confident lie: the caller was promised a verdict that could never arrive.\n"
    "// The queue is gone. The gate answers synchronously up to the 500-row cap and returns an explicit\n"
    "// 413 above it. `retrieve` only ever existed to collect queued verdicts, so the only honest answer\n"
    "// it can give now is an error.\n"
    "return [{ json: {\n"
    "  error: 'retrieve_removed',\n"
    "  message: 'The gate queue was removed on 2026-09-02. There are no queued batches to retrieve. '\n"
    "         + 'POST rows directly (up to 500 per call); the verdicts come back in the same response.',\n"
    "  http_status: 410\n"
    "} }];\n"
)

g_nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_PRE_ADD_GATE}}", "responseMode": "responseNode", "options": {}},
         -1600, extra={"webhookId": "dncpreaddgate01"}),
    if_bool("Is Retrieve?", "={{ $json.body.retrieve === true }}", -1400),
    # -------- retrieval branch: honest 410, see gate_retrieve_removed_js's own comment --------
    node("Retrieve Removed", "n8n-nodes-base.code", {"jsCode": gate_retrieve_removed_js, "mode": "runOnceForAllItems"},
         -1200, y=460, tv=2, extra={"id": "wave0-retrieve-removed-0001"}),
    node("Respond Retrieve", "n8n-nodes-base.respondToWebhook", {"options": {}}, -480, y=460),
    # -------- submit branch: synchronous only, up to the 500-row cap --------
    code_node("Mark Start", "return [{ json: { started_at: Date.now() } }];\n", -1200),
    # small, bounded table (1,373 domains) -- pulled whole rather than per-domain-queried, same
    # rationale as the OWN_DOMAIN static check but for a real, externally-maintained list.
    # POSITION IS LOAD-BEARING, found live 2026-09-14 (real incident, ~5 days undetected): this
    # must sit BEFORE "Build Items" splits the call into one item per submitted row, not after.
    # Two n8n behaviors compound here: (1) a dataTable "get" node runs ONCE PER INPUT ITEM it
    # receives (like an HTTP Request node), not once total; (2) "Build Items" reads the real row
    # list via a NAMED reference ($('Webhook').first().json.body.rows), completely ignoring its
    # own direct input's item count. An EARLIER version of this fix chained
    # Normalize Batch -> Get Domain Blocklist -> Get Registry Match (Batch) to make this node a
    # true ancestor of Classify Batch (closing a DIFFERENT execution-order bug, see below) -- but
    # that fed this node's 1,373-row OUTPUT into Get Registry Match (Batch) as ITS input, so THAT
    # node then ran 1,373 times (once per domain row) instead of once per submitted person. Real
    # production impact: the gate monitor logged 459 consecutive timeouts (>30s) over ~5 days
    # before this was caught. Placing this node right after Mark Start (which always carries
    # exactly ONE item, before the per-row split) means it always runs exactly once per gate call
    # regardless of batch size, and its 1,373-row output harmlessly flows into Build Items, which
    # ignores it. It is STILL a true ancestor of Classify Batch (Mark Start -> here -> Build Items
    # -> ... -> Classify Batch), so the $('Get Domain Blocklist') reference stays reliable.
    node("Get Domain Blocklist", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get", "dataTableId": GATE_DOMAINS_TABLE,
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "status", "condition": "eq", "keyValue": "=active"}]},
        "options": {}
    }, -1000, y=260, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2,
                     # a genuinely-empty-but-working table (0 domains blocked yet, no error)
                     # produces ZERO items -- must not silently kill the rest of the chain.
                     "alwaysOutputData": True}),
    code_node("Build Items", gate_build_items_js, -800),
    code_node("Cap Check", gate_cap_check_js, -600),
    if_bool("Over Cap?", "={{ $json.over_cap === true }}", -400),
    node("Respond Over Cap", "n8n-nodes-base.respondToWebhook",
         {"respondWith": "json", "responseBody": "={{ $json }}", "options": {"responseCode": 413}}, -200, y=680),
    code_node_per_item("Normalize Batch", gate_normalize_batch_js, -200),
    dt_get_or2("Get Registry Match (Batch)", "linkedin_url_norm", "={{ $json.li_key }}",
               "email_lc", "={{ $json.em_key }}", 400, y=100),
    code_node("Classify Batch", gate_classify_batch_js, 800, y=100),
    code_node("Build Report", gate_report_js, 1000, y=100),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 1200, y=100),
]
g_conn = conns([
    ("Webhook", "Is Retrieve?"),
    ("Retrieve Removed", "Respond Retrieve"),
    ("Mark Start", "Get Domain Blocklist"), ("Get Domain Blocklist", "Build Items"),
    ("Build Items", "Cap Check"), ("Cap Check", "Over Cap?"),
    ("Normalize Batch", "Get Registry Match (Batch)"), ("Get Registry Match (Batch)", "Classify Batch"),
    ("Classify Batch", "Build Report"), ("Build Report", "Respond"),
])
g_conn["Is Retrieve?"] = {"main": [
    [{"node": "Retrieve Removed", "type": "main", "index": 0}],
    [{"node": "Mark Start", "type": "main", "index": 0}],
]}
g_conn["Over Cap?"] = {"main": [
    [{"node": "Respond Over Cap", "type": "main", "index": 0}],
    [{"node": "Normalize Batch", "type": "main", "index": 0}],
]}
write("workflows/dnc_pre_add_gate/dnc_pre_add_gate.json", wf("dnc_pre_add_gate", g_nodes, g_conn))
write("workflows/DEV__dnc_pre_add_gate/DEV__dnc_pre_add_gate.json", wf("DEV__dnc_pre_add_gate", g_nodes, g_conn))

# ===========================================================================
# dnc_gate_queue_drainer -- single sequential drainer, batches of GATE_DRAIN_BATCH_SIZE, the
# schedule interval itself IS the breather between batches (no in-execution Wait node needed --
# keeps each execution short, same "keep externally-facing/background work cheap" lesson as v2).
# Reuses gate_normalize_batch_js's SHAPE (payload already normalized at enqueue time, just
# reconstructed from storage) and gate_classify_batch_js VERBATIM, unchanged, by naming this
# workflow's own reconstruction step "Normalize Batch" too -- same matching logic, zero drift risk
# between what the sync path and the drainer decide. No explicit drain-lock: batches are small
# (50 rows, same order of magnitude as the gate's own proven ~200-row/~9.8s throughput) and
# classification is a pure function of stored data, so even a rare overlapping tick just
# reprocesses a few rows harmlessly -- accepted deliberately rather than building lock machinery
# for a self-healing, idempotent operation.
# ===========================================================================
drainer_reconstruct_js = (
    "const rows = $input.all().map(i => i.json).slice(0, %d);\n"
    "return rows.map(r => {\n"
    "  let p = {}; try { p = JSON.parse(r.payload_json || '{}'); } catch (e) {}\n"
    "  return { json: Object.assign({}, p, { __queue_row_id: r.id, __row_key: r.row_key }) };\n"
    "});\n"
) % GATE_DRAIN_BATCH_SIZE

d_write_back = dt_upsert_tbl("Write Back Results", {
    "row_key": "={{ $json.__row_key }}", "status": "=done",
    "result_json": "={{ JSON.stringify({ gate_result: $json.gate_result, reason: $json.reason,"
                   " registry_row_ref: $json.registry_row_ref, identity_key: $json.identity_key }) }}",
    "completed_at": "={{ new Date().toISOString() }}",
}, ["row_key"], 200, GATE_QUEUE_TABLE_NAME, y=0)
d_write_back.update({"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})

d_nodes = [
    node("Drain Timer", "n8n-nodes-base.scheduleTrigger",
        {"rule": {"interval": [{"field": "minutes", "minutesInterval": GATE_DRAIN_INTERVAL_MINUTES}]}}, -1000, tv=1.2),
    # POSITION IS LOAD-BEARING -- same real incident as the gate's own build comment (found live
    # 2026-09-14, ~5 days undetected in dnc_pre_add_gate before this generator-level twin was
    # caught): a dataTable "get" node runs ONCE PER INPUT ITEM (like an HTTP Request node). Drain
    # Timer always carries exactly ONE item, so chaining Get Domain Blocklist directly off it means
    # this node always fires exactly once per drain tick, regardless of pending-queue size.
    # Chaining it any later (e.g. after Fetch Pending Batch, once that has expanded to N pending
    # rows, or after Normalize Batch's per-row expansion) would make THAT per-item node re-run once
    # per DOMAIN (1,373x) instead of once per queue row -- the exact bug that produced 459
    # consecutive 30s-timeout monitor failures in the live gate.
    node("Get Domain Blocklist", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get", "dataTableId": GATE_DOMAINS_TABLE,
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "status", "condition": "eq", "keyValue": "=active"}]},
        "options": {}
    }, -900, y=160, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2,
                     # a genuinely-empty-but-working table (0 domains blocked yet, no error)
                     # produces ZERO items -- must not silently kill the rest of the chain.
                     "alwaysOutputData": True}),
    # Swallows Get Domain Blocklist's 1,373-row output back down to exactly one item before
    # Fetch Pending Batch (itself a per-item-executing dataTable node) runs -- runOnceForAllItems,
    # completely ignores its own input, so it always emits exactly one item regardless of how many
    # domain rows arrived. This is what makes Get Domain Blocklist a true ANCESTOR of Classify
    # Batch (closing the named-reference-needs-ancestor-not-sibling gap) without letting its bulk
    # output become any downstream per-item node's input cardinality.
    code_node("Reset After Domains", "return [{ json: {} }];\n", -800, y=160),
    node("Fetch Pending Batch", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get", "dataTableId": GATE_QUEUE_TABLE,
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "status", "condition": "eq", "keyValue": "=pending"}]},
        "options": {}
    }, -600, tv=1),
    code_node("Normalize Batch", drainer_reconstruct_js, -400),
    dt_get_or2("Get Registry Match (Batch)", "linkedin_url_norm", "={{ $json.li_key }}",
               "email_lc", "={{ $json.em_key }}", -200, y=0),
    code_node("Classify Batch", gate_classify_batch_js, 0, y=0),
    d_write_back,
]
d_conn = conns([
    ("Drain Timer", "Get Domain Blocklist"), ("Get Domain Blocklist", "Reset After Domains"),
    ("Reset After Domains", "Fetch Pending Batch"), ("Fetch Pending Batch", "Normalize Batch"),
    ("Normalize Batch", "Get Registry Match (Batch)"),
    ("Get Registry Match (Batch)", "Classify Batch"), ("Classify Batch", "Write Back Results"),
])
write("workflows/dnc_gate_queue_drainer/dnc_gate_queue_drainer.json", wf("dnc_gate_queue_drainer", d_nodes, d_conn))

# ===========================================================================
# dnc_s4_retirement_removal -- 2026-08-26, Melisa's ruling (Nik confirmed): S4 (event_contacted
# with no other active reason) is retired as a DNC basis. "Our pool of potential customers is
# limited; real case -- Ai4 last-year non-responders were re-contacted this year and some
# replied. Event contact must not block re-approach; only a RESPONSE creates a relationship
# worth protecting." -- Melisa, 2026-08-26.
#
# Tombstone, never delete (reversible, 6-month history stays queryable). Fires against a
# caller-supplied row_ids list (the EXACT set shown in the §9f.2 artifact, not a live recompute
# at fire time -- what gets fired must match what was reviewed). dry_run defaults true --
# writing requires the caller to explicitly pass dry_run:false, on top of Nik's word gating
# whether this ever gets called for real at all. Chunked by the caller (same discipline as S3B/
# S4's own cursor-driven fires) -- 7,138 rows in one execution would repeat the exact OOM class
# this project has hit before.
# ===========================================================================
s4r_build_items_js = (
    "const body = $('Webhook').first().json.body || {};\n"
    "const ids = Array.isArray(body.row_ids) ? body.row_ids : [];\n"
    "if (!ids.length) throw new Error('dnc_s4_retirement_removal: body.row_ids must be a non-empty array');\n"
    "const dryRun = body.dry_run !== false; // default true -- explicit false required to write\n"
    # backported 2026-09-24 from the live node (edited out-of-band 2026-09-11) -- a redeploy from
    # the old generator would have silently reverted caller-supplied removed_reason support.
    "return ids.map(id => ({ json: { id, dry_run: dryRun,\n"
    "  removed_at: new Date().toISOString(), removed_reason: (typeof body.removed_reason === 'string' && body.removed_reason.trim())\n"
    "      ? body.removed_reason.trim().slice(0, 120)\n"
    "      // Default is the original constant, so every existing caller is byte-identical. It was\n"
    "      // hardcoded, which meant a correction could only be filed under someone else's rule change.\n"
    "      : 'rule_change_2026-08-26_melisa' } }));\n"
)
s4r_report_js = (
    # dry_run read from the ORIGINAL Build Items output by name, not from $input -- the real-write
    # branch's $input comes from Update Row, whose own result doesn't carry dry_run at all (it
    # only echoes the columns actually written), so trusting $input here would silently misreport.\n"
    "const rows = $input.all().map(i => i.json);\n"
    "const dryRun = $('Build Items').first().json.dry_run;\n"
    "return [{ json: { processed: rows.length, dry_run: dryRun,\n"
    "  note: dryRun ? 'DRY RUN -- nothing written' : 'WRITTEN -- rows tombstoned' } }];\n"
)
s4r_update = dt_update("Update Row", {
    "status": "=removed", "removed_at": "={{ $json.removed_at }}", "removed_reason": "={{ $json.removed_reason }}",
}, [{"keyName": "id", "condition": "eq", "keyValue": "={{ $json.id }}"}], 400, y=100)

r_nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_S4_RETIREMENT_REMOVAL}}", "responseMode": "responseNode", "options": {}},
         -600, extra={"webhookId": "dncs4retirement01"}),
    code_node("Build Items", s4r_build_items_js, -400),
    if_bool("Dry Run?", "={{ $json.dry_run === true }}", -200),
    code_node("Report Dry Run", "return $input.all();\n", 0, y=200),
    s4r_update,
    code_node("Build Report", s4r_report_js, 600, y=100),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 800, y=100),
    dt_claim_enqueue("Enqueue Supabase Delta", REGISTRY_ROW_CLAIM_KEY_EXPR, "supabase_delta_registry",
                      "dnc_s4_retirement_removal", REGISTRY_ROW_CLAIM_EVIDENCE_EXPR, 600, y=260),
]
r_conn = conns([
    ("Webhook", "Build Items"), ("Build Items", "Dry Run?"),
    ("Build Report", "Respond"),
])
r_conn["Update Row"] = {"main": [
    [{"node": "Build Report", "type": "main", "index": 0},
     {"node": "Enqueue Supabase Delta", "type": "main", "index": 0}],
]}
r_conn["Dry Run?"] = {"main": [
    [{"node": "Report Dry Run", "type": "main", "index": 0}],
    [{"node": "Update Row", "type": "main", "index": 0}],
]}
r_conn["Report Dry Run"] = {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]}
write("workflows/dnc_s4_retirement_removal/dnc_s4_retirement_removal.json",
      wf("dnc_s4_retirement_removal", r_nodes, r_conn))

# ===========================================================================
# dnc_archived_responders_import -- 2026-08-28, Melisa's CSV of ~324 archived leads who responded
# (the API is blind to archived leads; the export is the only complete source). Generic,
# row-agnostic ADDITION driver -- caller-supplied rows, this workflow never re-derives anything.
# Same dry_run-default-true safety as dnc_s4_retirement_removal, same mode:each fan-out via
# exec_wf. Every row must carry a REGISTRY-VALID reason (reason_v1.js's REASON_TO_ENTRY_TYPE keys
# -- 'unsubscribe' for an explicit stop-contact signal, NOT 'explicit_opt_out', which is an
# entry_type value, not a reason -- a mismatch caught here BEFORE firing, not after a rejected
# write). reply_dnc rows must carry reply_category (2026-08-14 schema assert, the 116-row gap).
# ===========================================================================
ari_build_items_js = (
    "const body = $('Webhook').first().json.body || {};\n"
    "const rows = Array.isArray(body.rows) ? body.rows : [];\n"
    "if (!rows.length) throw new Error('dnc_archived_responders_import: body.rows must be a non-empty array');\n"
    "const dryRun = body.dry_run !== false; // default true -- explicit false required to write\n"
    "const VALID_REASONS = ['client','unsubscribe','meeting_dnc','reply_dnc','sales_personal_outreach',"
    "'manual_offboard_eligible','event_contacted','manual_sheet','offboard'];\n"
    "const errors = [];\n"
    "rows.forEach((r, i) => {\n"
    "  if (!VALID_REASONS.includes(r.reason)) errors.push('row ' + i + ': invalid reason ' + r.reason);\n"
    "  if (r.reason === 'reply_dnc' && !r.reply_category) errors.push('row ' + i + ': reply_dnc requires reply_category');\n"
    "  if (!r.email && !r.linkedin_url) errors.push('row ' + i + ': no email/linkedin_url -- cannot resolve an identity');\n"
    "});\n"
    "if (errors.length) throw new Error('dnc_archived_responders_import: ' + errors.length + ' invalid row(s): ' + errors.slice(0, 10).join('; '));\n"
    # correlation_id/date_precision are NOT NULL in Supabase's dnc_registry; this is the only
    # UpsertLedger caller that passes caller rows through verbatim, and the 82 rows it wrote on
    # 2026-09-15 without them have been rejected by every delta push and nightly reconcile since.
    "return rows.map(r => ({ json: Object.assign({}, r, {\n"
    "  correlation_id: r.correlation_id || ('archived_import:' + $execution.id + ':' + (r.linkedin_url || r.email)),\n"
    "  date_precision: r.date_precision || 'unknown',\n"
    "  dry_run: dryRun }) }));\n"
)
ari_report_js = (
    # 2026-08-28 fix, found live on the real fire: DNC__UpsertLedger__v1 has THREE disconnected
    # terminal paths (Send Guard->Slack Conflict Alert, Upsert Ledger Row->Has Tombstone?, Noop
    # (idempotent)) -- executeWorkflow(mode:each) surfaces each as its OWN numbered output branch
    # on the calling node, not one combined stream. Reading only $input.all() here (fed by a
    # single connected branch) silently undercounted a real fire as "processed: 1" instead of 315
    # -- every real write was still correct, but the report was wrong. Fixed by merging all three
    # branches upstream (see Merge Outcomes below) before this node ever runs.\n"
    "const rows = $input.all().map(i => i.json);\n"
    "const dryRun = $('Build Items').all().length ? $('Build Items').first().json.dry_run : true;\n"
    "const conflicts = rows.filter(r => r && r.ok === true && r.channel).length;\n"
    "return [{ json: { processed: rows.length, conflicts_declined: conflicts, dry_run: dryRun,\n"
    "  note: dryRun ? 'DRY RUN -- nothing written' : 'WRITTEN -- rows upserted into the registry' } }];\n"
)

ari_nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_ARCHIVED_RESPONDERS_IMPORT}}", "responseMode": "responseNode", "options": {}},
         -600, extra={"webhookId": "dncarchivedrespimport01"}),
    code_node("Build Items", ari_build_items_js, -400),
    if_bool("Dry Run?", "={{ $json.dry_run === true }}", -200),
    code_node("Report Dry Run", "return $input.all();\n", 0, y=200),
    exec_wf("Call UpsertLedger", "DNC__UpsertLedger__v1", 400, y=100),
    # UpsertLedger's 3 disconnected terminal paths land on 3 separate executeWorkflow output
    # indices -- merge them all before counting, or a real fire silently under-reports (see
    # ari_report_js's comment; found live 2026-08-28).
    node("Merge Outcomes", "n8n-nodes-base.merge", {"mode": "append", "numberInputs": 3, "options": {}},
         550, y=100, tv=3),
    code_node("Build Report", ari_report_js, 700, y=100),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 900, y=100),
]
ari_conn = conns([
    ("Webhook", "Build Items"), ("Build Items", "Dry Run?"),
    ("Build Report", "Respond"),
])
ari_conn["Dry Run?"] = {"main": [
    [{"node": "Report Dry Run", "type": "main", "index": 0}],
    [{"node": "Call UpsertLedger", "type": "main", "index": 0}],
]}
ari_conn["Report Dry Run"] = {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]}
ari_conn["Call UpsertLedger"] = {"main": [
    [{"node": "Merge Outcomes", "type": "main", "index": 0}],
    [{"node": "Merge Outcomes", "type": "main", "index": 1}],
    [{"node": "Merge Outcomes", "type": "main", "index": 2}],
]}
ari_conn["Merge Outcomes"] = {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]}
write("workflows/dnc_archived_responders_import/dnc_archived_responders_import.json",
      wf("dnc_archived_responders_import", ari_nodes, ari_conn))

print("OK")
