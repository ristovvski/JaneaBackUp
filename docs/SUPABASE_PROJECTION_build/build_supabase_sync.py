#!/usr/bin/env python3
"""Generator for Phase 2's Supabase-writing n8n workflows. FILES ONLY -- nothing here deploys or
fires anything; see deploy_supabase_sync.py (not yet run) for that, gated behind Nik's word per
§9f.2. Confirmed live 2026-09-14: the "Supabase account" credential (id u6wyGnYC71Sr1KgT) is a
native n8n Supabase credential (type supabaseApi) -- HTTP Request nodes must use
authentication=predefinedCredentialType + nodeCredentialType=supabaseApi (NOT
genericCredentialType -- that's only for genuinely generic auth types like httpHeaderAuth/
httpQueryAuth; using predefinedCredentialType for an actual predefined type like supabaseApi is
the correct, intended mechanism, confirmed working via a live read-only probe).

dnc_registry_meta is reused as the sync-run log for BOTH tables (not just dnc_registry) --
its `source` column is free text, so domains syncs are logged with a distinguishing prefix
(e.g. "initial_load:dnc_domains") rather than standing up a second, near-identical meta table.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "workflows")

SUPABASE_URL = "https://icxrjwccqitqmpypwhie.supabase.co"
SUPABASE_CRED = {"id": "u6wyGnYC71Sr1KgT", "name": "Supabase account"}

# on_conflict target per table -- the column PostgREST upserts against (matches each table's PK).
TABLE_PK = {"dnc_registry": "id", "dnc_domains": "domain"}


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_"),
         "name": name, "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def code_node(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code", {"jsCode": js, "mode": "runOnceForAllItems"}, x, y, tv=2)


def code_node_per_item(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code", {"jsCode": js, "mode": "runOnceForEachItem"}, x, y, tv=2)


def supabase_http(name, x, y, method, url_expr, extra_headers=None, prefer=None, full_response=True):
    header_params = list(extra_headers or [])
    if prefer:
        header_params.append({"name": "Prefer", "value": prefer})
    params = {
        "method": method,
        "url": url_expr,
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendBody": method in ("POST", "PATCH"),
        "specifyBody": "json",
        "jsonBody": "={{ $json.__body }}" if method in ("POST", "PATCH") else undefined_marker(),
        "sendHeaders": bool(header_params),
        "headerParameters": {"parameters": header_params} if header_params else {"parameters": []},
        # NOTE: the flat "options.fullResponse" key used in the FIRST version of this generator
        # (still live today in dnc_supabase_initial_load's Upsert Chunk / Insert Meta Row nodes) is
        # silently ignored by httpRequest typeVersion 4.2 -- confirmed live 2026-09-14 while
        # building the post-verify script. Harmless there (Build Report never reads
        # statusCode/headers, only checks .error via continueErrorOutput's own branching, which
        # works independently of fullResponse), but the correct nested path is used here so new
        # code doesn't inherit a known-wrong pattern. See memory: n8n-http-fullresponse-nested-path.
        # full_response=False is deliberate for a paginated row-fetch: a plain JSON-array body
        # auto-splits into one output item per row, which is exactly what a downstream diff join
        # wants -- wrapping it would just require unwrapping again.
        "options": {"response": {"response": {"fullResponse": True}}} if full_response else {},
    }
    if method not in ("POST", "PATCH"):
        params.pop("jsonBody", None)
        params.pop("specifyBody", None)
    return node(name, "n8n-nodes-base.httpRequest", params, x, y, tv=4.2,
                extra={"credentials": {"supabaseApi": SUPABASE_CRED},
                       "onError": "continueErrorOutput"})


def undefined_marker():
    # placeholder never actually reaches the JSON (popped when method isn't POST/PATCH); exists
    # only so supabase_http()'s single dict literal above doesn't KeyError building it.
    return None


def write(rel_path, wf_json):
    full = os.path.join(HERE, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(wf_json, f, indent=2, ensure_ascii=False)
    print(f"wrote {rel_path} ({len(wf_json['nodes'])} nodes)")


def wf(name, nodes, connections, error_workflow=None):
    settings = {}
    if error_workflow:
        settings["errorWorkflow"] = error_workflow
    return {"name": name, "nodes": nodes, "connections": connections, "settings": settings}


# ===========================================================================
# dnc_supabase_initial_load -- ONE CHUNK per webhook call, dry_run-default true, same shape as
# every other batch driver in this project (dnc_domains_import, dnc_archived_responders_import,
# dnc_tombstone_hard_delete). The caller (fire_supabase_initial_load.py) does the chunking client
# side and calls this once per chunk of <=500 rows, then ONE final call with finalize:true to log
# the sync-run summary into dnc_registry_meta.
# ===========================================================================
build_items_js = (
    "const body = $('Webhook').first().json.body || {};\n"
    "const table = body.table;\n"
    "if (!['dnc_registry', 'dnc_domains'].includes(table)) {\n"
    "  throw new Error('dnc_supabase_initial_load: table must be dnc_registry or dnc_domains, got ' + JSON.stringify(table));\n"
    "}\n"
    "const dryRun = body.dry_run !== false;\n"
    "if (body.finalize === true) {\n"
    "  return [{ json: { finalize: true, table, row_count: body.row_count, dry_run: dryRun } }];\n"
    "}\n"
    "const rows = Array.isArray(body.rows) ? body.rows : [];\n"
    "if (!rows.length) throw new Error('dnc_supabase_initial_load: body.rows must be a non-empty array (or pass finalize:true)');\n"
    "const pk = table === 'dnc_registry' ? 'id' : 'domain';\n"
    "const errors = [];\n"
    "rows.forEach((r, i) => {\n"
    "  if (r[pk] === undefined || r[pk] === null || r[pk] === '') errors.push('row ' + i + ': missing PK column ' + pk);\n"
    "});\n"
    "if (errors.length) throw new Error('dnc_supabase_initial_load: ' + errors.length + ' invalid row(s): ' + errors.slice(0, 10).join('; '));\n"
    "return [{ json: { finalize: false, table, dry_run: dryRun, row_count: rows.length, __body: rows } }];\n"
)

route_finalize_expr = "={{ $json.finalize === true }}"
route_dry_run_expr = "={{ $json.dry_run === true }}"

upsert_url_expr = (
    "={{ '" + SUPABASE_URL + "/rest/v1/' + $json.table + '?on_conflict=' + "
    "($json.table === 'dnc_registry' ? 'id' : 'domain') }}"
)

meta_insert_url_expr = "={{ '" + SUPABASE_URL + "/rest/v1/dnc_registry_meta' }}"

build_meta_row_js = (
    "const j = $input.first().json;\n"
    "return [{ json: { __body: [{\n"
    "  last_sync_at: new Date().toISOString(),\n"
    "  row_count: j.row_count,\n"
    "  source: 'initial_load:' + j.table,\n"
    "}] } }];\n"
)

report_js = (
    # reads the ORIGINAL context via a named reference to Build Items (a true ancestor on every
    # path into this node), not its own $input -- the upstream Upsert Chunk / Insert Meta Row HTTP
    # nodes use fullResponse:true, which replaces $json with {statusCode, headers, body} entirely,
    # losing table/row_count/dry_run/finalize. $input is still checked, but only to see whether
    # the HTTP call errored (continueErrorOutput attaches an .error field to the passed-through
    # item on failure).\n"
    "const ctx = $('Build Items').first().json;\n"
    "const input = $input.first().json;\n"
    "const failed = !!(input && input.error);\n"
    "return [{ json: {\n"
    "  table: ctx.table, dry_run: ctx.dry_run, row_count: ctx.row_count, finalize: !!ctx.finalize, ok: !failed,\n"
    "  note: failed ? ('ERROR: ' + JSON.stringify(input.error))\n"
    "        : ctx.finalize ? 'sync-run logged to dnc_registry_meta'\n"
    "        : (ctx.dry_run ? 'DRY RUN -- nothing written to Supabase' : 'WRITTEN -- chunk upserted to Supabase'),\n"
    "} }];\n"
)

il_nodes = [
    node("Webhook", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_SUPABASE_INITIAL_LOAD}}", "responseMode": "responseNode", "options": {}},
         -1200, extra={"webhookId": "dncsupabaseinitload01"}),
    code_node("Build Items", build_items_js, -1000),
    # dry_run is checked FIRST, before the finalize/chunk split -- a dry-run finalize call must not
    # write the meta-log row either; both real-write branches (finalize -> meta insert, chunk ->
    # upsert) only exist past this gate.
    node("Is Dry Run?", "n8n-nodes-base.if",
         {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"}, "combinator": "and",
                         "conditions": [{"leftValue": route_dry_run_expr, "rightValue": True,
                                         "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         -800, tv=2),
    node("Is Finalize?", "n8n-nodes-base.if",
         {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"}, "combinator": "and",
                         "conditions": [{"leftValue": route_finalize_expr, "rightValue": True,
                                         "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         -600, y=140, tv=2),
    code_node("Build Meta Row", build_meta_row_js, -400, y=60),
    supabase_http("Insert Meta Row", -200, 60, "POST", meta_insert_url_expr,
                  prefer="resolution=merge-duplicates,return=minimal"),
    supabase_http("Upsert Chunk", -400, 220, "POST", upsert_url_expr,
                  prefer="resolution=merge-duplicates,return=minimal"),
    code_node("Build Report", report_js, 0),
    node("Respond", "n8n-nodes-base.respondToWebhook", {"options": {}}, 200),
]
il_conn = {
    "Webhook": {"main": [[{"node": "Build Items", "type": "main", "index": 0}]]},
    "Build Items": {"main": [[{"node": "Is Dry Run?", "type": "main", "index": 0}]]},
    "Is Dry Run?": {"main": [
        [{"node": "Build Report", "type": "main", "index": 0}],
        [{"node": "Is Finalize?", "type": "main", "index": 0}],
    ]},
    "Is Finalize?": {"main": [
        [{"node": "Build Meta Row", "type": "main", "index": 0}],
        [{"node": "Upsert Chunk", "type": "main", "index": 0}],
    ]},
    "Build Meta Row": {"main": [[{"node": "Insert Meta Row", "type": "main", "index": 0}]]},
    "Insert Meta Row": {"main": [[{"node": "Build Report", "type": "main", "index": 0}],
                                  [{"node": "Build Report", "type": "main", "index": 0}]]},
    "Upsert Chunk": {"main": [[{"node": "Build Report", "type": "main", "index": 0}],
                               [{"node": "Build Report", "type": "main", "index": 0}]]},
    "Build Report": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}
write("workflows/dnc_supabase_initial_load/dnc_supabase_initial_load.json",
      wf("dnc_supabase_initial_load", il_nodes, il_conn))

# ===========================================================================
# dnc_supabase_delta_pusher -- drains the shared claims table (euyostwJYfJefItC, family
# "supabase_delta_registry") enqueued by DNC__UpsertLedger__v1, pushing each changed row's CURRENT
# state to Supabase's dnc_registry and deleting the claim on success. Cron + manual webhook, same
# dual-trigger convention as dnc_claims_prune (webhook uses responseMode:onReceived -- an
# immediate ack, so a schedule-triggered run never needs a respondToWebhook node that would error
# with no webhook context).
# ===========================================================================
CLAIMS_TABLE = {"__rl": True, "mode": "id", "value": "euyostwJYfJefItC"}
REGISTRY_TABLE = {"__rl": True, "mode": "id", "value": "UOgKwlGsL28lX61O"}
# 5, not 10 -- Nik's stated SLA is "registry write -> Supabase row <=6 min"; a 10-minute cron
# can't structurally guarantee that (worst case a claim lands right after a tick), a 5-minute one can.
DELTA_PUSH_INTERVAL_MINUTES = 5
CLAIM_FAMILY = "supabase_delta_registry"

REGISTRY_COLUMNS = [
    "id", "identity_key", "norm_v", "linkedin_url_norm", "email_lc", "full_name",
    "pipedrive_person_id", "entry_type", "reason", "source", "source_ref", "source_signal",
    "correlation_id", "date_precision", "expiry_review_pending", "offboard_removable",
    "also_flagged", "projections_state", "owner_tag", "status", "added_at", "removed_at",
    "removed_reason", "reply_category", "expires_at", "createdAt", "updatedAt",
]

parse_claim_id_js = (
    # claim_key shape: "supabase_delta_registry|<row id>" (see dt_claim_enqueue in build_dnc.py).
    # A malformed/foreign claim_key (wrong prefix, non-numeric id) still gets a registry_id of
    # null, which "Get Current Row" will simply never match (id eq null finds nothing) -- it falls
    # into the same found:false bucket as a genuinely-missing row, staying in the queue
    # (undeleted) for manual investigation rather than being silently dropped.
    "const key = $json.claim_key || '';\n"
    "const prefix = '" + CLAIM_FAMILY + "|';\n"
    "const idStr = key.startsWith(prefix) ? key.slice(prefix.length) : null;\n"
    "const registryId = idStr && /^\\d+$/.test(idStr) ? Number(idStr) : null;\n"
    # runOnceForEachItem: MUST return a bare object, not an array -- an array wrap here is
    # silently mishandled by n8n ("A 'json' property isn't an object"). Same class of bug as the
    # 2026-08-11 PD Classify incident (330-in/1-out) -- caught this time before deploy via a live
    # isolated probe, not in production.\n"
    "return { json: { claim_key: key, registry_id: registryId } };\n"
)

build_push_item_js = (
    # runOnceForAllItems, NOT per-item -- deliberately. "Get Current Row" is invoked once per
    # claim (correct: each claim needs a DIFFERENT row), but its combined output across all those
    # invocations can have anywhere from 0 to N items depending on how many rows were actually
    # found, so it no longer lines up 1:1 with the N claims. This node restores exact
    # N-claims-in/N-items-out cardinality by explicitly joining $('Parse Claim Id').all() (every
    # claim) against $input.all() (every row actually found) by id, rather than relying on
    # pairedItem inference across a cardinality-changing join -- the same class of fix as
    # dnc_pre_add_gate's Get Registry Match (Batch) incident, applied on the READ side this time.
    "const claims = $('Parse Claim Id').all().map(i => i.json);\n"
    "const rows = $input.all().map(i => i.json)\n"
    "  .filter(r => r && typeof r.id === 'number' && typeof r.identity_key === 'string');\n"
    "const byId = {}; rows.forEach(r => { byId[r.id] = r; });\n"
    "const cols = " + json.dumps(REGISTRY_COLUMNS) + ";\n"
    "return claims.map(claim => {\n"
    "  const row = claim.registry_id !== null ? byId[claim.registry_id] : undefined;\n"
    "  if (!row) return { json: { claim_key: claim.claim_key, registry_id: claim.registry_id, found: false } };\n"
    "  const projected = {}; cols.forEach(c => { projected[c] = row[c] !== undefined ? row[c] : null; });\n"
    "  return { json: { claim_key: claim.claim_key, registry_id: claim.registry_id, found: true, __body: [projected] } };\n"
    "});\n"
)

count_claims_seen_js = (
    # Fed DIRECTLY and ONLY by "Fetch Pending Claims" -- a single, always-reliable source, never
    # converging with the per-claim push/delete branches below. Found live 2026-09-14 on the FIRST
    # real organic write (Ben Leeds): a Merge("append", numberInputs:3) collapsing the three
    # per-claim outcomes (skipped/pushed/failed) works fine when a batch happens to populate
    # MULTIPLE of those branches in the same run (proven with a synthetic 2-claim mixed batch), but
    # never fires at all when only ONE outcome is populated -- which is the NORMAL case (0 or 1
    # pending claim per 5-minute cycle in steady state). The claim's actual push+delete is
    # unaffected either way (that part never depended on Merge), but the report/meta-log tail
    # silently never ran for the single-claim case -- confirmed reproducible in isolation, and
    # `alwaysOutputData` on the branching nodes (Has Row?, Upsert To Supabase) did NOT fix it. This
    # redesign trades a precise pushed/failed/skipped breakdown (never persisted anywhere anyway --
    # dnc_registry_meta only has last_sync_at/row_count/source) for a meta-log that reliably fires:
    # row_count now means "claims seen this cycle", not "claims successfully pushed".
    "return [{ json: { claims_seen: $input.all().length } }];\n"
)

build_delta_meta_row_js = (
    "const j = $input.first().json;\n"
    "return [{ json: { __body: [{\n"
    "  last_sync_at: new Date().toISOString(), row_count: j.claims_seen,\n"
    "  source: 'delta_push:dnc_registry',\n"
    "}] } }];\n"
)

dp_nodes = [
    node("Drain Timer", "n8n-nodes-base.scheduleTrigger",
         {"rule": {"interval": [{"field": "minutes", "minutesInterval": DELTA_PUSH_INTERVAL_MINUTES}]}},
         -1600, y=0, tv=1.2),
    node("Manual Trigger", "n8n-nodes-base.webhook",
         {"httpMethod": "GET", "path": "{{WEBHOOK_DNC_SUPABASE_DELTA_PUSHER}}", "responseMode": "onReceived", "options": {}},
         -1600, y=180, extra={"webhookId": "dncsupabasedeltapusher01"}),
    node("Fetch Pending Claims", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get", "dataTableId": CLAIMS_TABLE,
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "family", "condition": "eq", "keyValue": CLAIM_FAMILY}]},
        "options": {}
    }, -1400, y=90, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2,
                     # a genuinely-empty queue (the common case -- nothing pending) must not be
                     # mistaken for a table-read failure and must not silently kill the report step.
                     "alwaysOutputData": True}),
    code_node_per_item("Parse Claim Id", parse_claim_id_js, -1200, y=90),
    node("Get Current Row", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get", "dataTableId": REGISTRY_TABLE,
        "returnAll": True, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "id", "condition": "eq", "keyValue": "={{ $json.registry_id }}"}]},
        "options": {}
    }, -1000, y=90, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2,
                     "alwaysOutputData": True}),
    code_node("Build Push Item", build_push_item_js, -800, y=90),
    node("Has Row?", "n8n-nodes-base.if",
         {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"}, "combinator": "and",
                         "conditions": [{"leftValue": "={{ $json.found }}", "rightValue": True,
                                         "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         -600, y=90, tv=2),
    supabase_http("Upsert To Supabase", -400, 40, "POST",
                  "={{ '" + SUPABASE_URL + "/rest/v1/dnc_registry?on_conflict=id' }}",
                  prefer="resolution=merge-duplicates,return=minimal"),
    # claim_key is read via a named reference to "Build Push Item" (a true ancestor, single
    # linear per-item chain from here -- no fan-in/merge in between to break pairing), NOT via
    # $json -- "Upsert To Supabase" is an HTTP node and its own output REPLACES $json with the
    # response shape ({statusCode,headers,body} or {error}), the same context-loss class fixed in
    # dnc_supabase_initial_load's Build Report.
    node("Delete Claim", "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "deleteRows", "dataTableId": CLAIMS_TABLE,
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "claim_key", "condition": "eq",
                                     "keyValue": "={{ $('Build Push Item').item.json.claim_key }}"}]},
        "options": {}
    }, -200, y=0, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2}),
    # Reporting is a SEPARATE, single-source branch fed directly off "Fetch Pending Claims" (fan-
    # OUT from one reliable source, not fan-IN from several) -- deliberately independent of the
    # per-claim push/delete branches above, which never converge back into anything. See the
    # count_claims_seen_js comment for why.
    code_node("Count Claims Seen", count_claims_seen_js, -1200, y=250),
    node("Any Claims?", "n8n-nodes-base.if",
         {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"}, "combinator": "and",
                         "conditions": [{"leftValue": "={{ $json.claims_seen > 0 }}", "rightValue": True,
                                         "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         -1000, y=250, tv=2),
    code_node("Build Delta Meta Row", build_delta_meta_row_js, -800, y=250),
    supabase_http("Insert Delta Meta Row", -600, 250, "POST", meta_insert_url_expr,
                  prefer="resolution=merge-duplicates,return=minimal"),
]
dp_conn = {
    "Drain Timer": {"main": [[{"node": "Fetch Pending Claims", "type": "main", "index": 0}]]},
    "Manual Trigger": {"main": [[{"node": "Fetch Pending Claims", "type": "main", "index": 0}]]},
    "Fetch Pending Claims": {"main": [
        [{"node": "Parse Claim Id", "type": "main", "index": 0}, {"node": "Count Claims Seen", "type": "main", "index": 0}],
        [{"node": "Parse Claim Id", "type": "main", "index": 0}, {"node": "Count Claims Seen", "type": "main", "index": 0}],
    ]},
    "Parse Claim Id": {"main": [[{"node": "Get Current Row", "type": "main", "index": 0}]]},
    "Get Current Row": {"main": [[{"node": "Build Push Item", "type": "main", "index": 0}],
                                  [{"node": "Build Push Item", "type": "main", "index": 0}]]},
    "Build Push Item": {"main": [[{"node": "Has Row?", "type": "main", "index": 0}]]},
    "Has Row?": {"main": [
        [{"node": "Upsert To Supabase", "type": "main", "index": 0}],
        [],
    ]},
    "Upsert To Supabase": {"main": [
        [{"node": "Delete Claim", "type": "main", "index": 0}],
        [],
    ]},
    "Delete Claim": {"main": [[], []]},
    "Count Claims Seen": {"main": [[{"node": "Any Claims?", "type": "main", "index": 0}]]},
    "Any Claims?": {"main": [
        [{"node": "Build Delta Meta Row", "type": "main", "index": 0}],
        [],
    ]},
    "Build Delta Meta Row": {"main": [[{"node": "Insert Delta Meta Row", "type": "main", "index": 0}]]},
    "Insert Delta Meta Row": {"main": [[], []]},
}
write("workflows/dnc_supabase_delta_pusher/dnc_supabase_delta_pusher.json",
      wf("dnc_supabase_delta_pusher", dp_nodes, dp_conn))

# ===========================================================================
# dnc_supabase_nightly_reconcile -- full field-level compare of BOTH tables, n8n (source of truth)
# vs Supabase, healing any drift by upserting FROM n8n. Cron (nightly) + manual webhook, same dual-
# trigger convention as dnc_claims_prune / dnc_supabase_delta_pusher.
#
# "Never a full pull in one execution" (Nik, citing today's 502 from a DIFFERENT bug -- returning
# the full 25,729-row registry TWICE through a webhook HTTP response): the actual n8n dataTable
# read (returnAll) has been done many times this session with no issue -- the 502 was specifically
# from round-tripping a huge payload through an HTTP response body twice, which a scheduled job
# with a small acknowledgement response never does. What IS genuinely chunked here, and load-
# bearing: the SUPABASE-side read is paginated (offset/limit, required anyway -- PostgREST's own
# max-rows caps any single response at 1000 regardless of ?limit=, confirmed live 2026-09-14, see
# memory: supabase-postgrest-max-rows-cap) and the write-back of any drifted rows is chunked at 500
# (matching every other bulk write in this project). Flagged explicitly in the pre-post artifact
# for Nik to correct if a stricter n8n-side SplitInBatches chunking is wanted instead.
# ===========================================================================
DOMAINS_COLUMNS = ["domain", "added_at", "source", "reason", "status"]
RECONCILE_PAGE_SIZE = 1000
RECONCILE_CHUNK_SIZE = 500
# #alerts -- confirmed by Nik 2026-09-14 (distinct from OPS_CHANNEL/#niks-channel, his own
# coordination channel; monitor/drift lines go here). Also added to build_dnc.py's shared channel
# constants (ALERTS_CHANNEL) so the next builder doesn't have to ask again.
ALERTS_CHANNEL = "C0BTUHSSM3K"
SLACK_CRED = {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}


def slack_post(name, text_expr, x, y=300, channel_id=None):
    return node(name, "n8n-nodes-base.slack", {
        "resource": "message", "operation": "post", "select": "channel",
        "channelId": {"__rl": True, "mode": "id", "value": channel_id or ALERTS_CHANNEL},
        "text": text_expr, "otherOptions": {}
    }, x, y, tv=2.2, extra={"credentials": {"slackApi": SLACK_CRED},
                            # unlike most of this project's ~15 other Slack posts (a documented,
                            # still-open gap -- see build_dnc.py's slack_post comment), THIS one is
                            # explicitly given continueErrorOutput: a Slack outage must never
                            # prevent the reconcile's actual healing work or its meta-log from
                            # completing, matching the one precedent that already got this fix
                            # ("Slack Conflict Alert" in DNC__UpsertLedger__v1).
                            "onError": "continueErrorOutput"})


# Columns declared NOT NULL in the Supabase table (dnc_registry_phase1.sql). A drifted row with a
# null in any of these can never be upserted, and PostgREST array inserts are atomic -- one such
# row fails its whole 500-row chunk. 2026-09-24: 82 rows with null correlation_id/date_precision
# silently blocked the heal of 418 valid rows for 9 nights while the alert said "healed".
REGISTRY_NOT_NULL = [
    "id", "identity_key", "norm_v", "entry_type", "reason", "source", "correlation_id",
    "date_precision", "expiry_review_pending", "offboard_removable", "also_flagged",
    "projections_state", "status", "added_at", "createdAt", "updatedAt",
]
DOMAINS_NOT_NULL = ["domain", "added_at", "source", "status"]
REPORT_EXAMPLES_PER_GROUP = 8


def build_reconcile_table(table_key, source_table_ref, source_pk, supabase_table, supabase_pk,
                           columns, not_null, x0, y0):
    """Returns (nodes, connections_dict, diff_node_name, get_n8n_node_name) for one table's full
    reconcile cluster. x0/y0 offset the whole cluster so two instances (registry, domains) don't
    overlap on the canvas.

    STRICTLY LINEAR, single-incoming-wire chain throughout -- no node here has more than one
    direct predecessor. Found live 2026-09-14: a runOnceForAllItems code node with TWO separate
    incoming wires does NOT wait for both and merge -- it fires ONCE PER ARRIVING BRANCH, the
    exact same "Merge append not a barrier" behavior already documented in this project's memory
    for literal Merge nodes, just generalized to any multi-input node. The original version wired
    both get_n8n_name AND fetch_page_name directly into diff_name, which fired it TWICE per table
    (once misreading get_n8n_name's own bulk output as if it were $input, once correctly) and
    cascaded into Combine Reports firing 4 times total, quadruple-inserting meta rows. Fixed by
    keeping every data source a NAMED-REFERENCE read from a true ancestor, never a second wired
    input -- get_n8n_name now chains through a swallow node before the rest of this table's
    per-page pipeline, so it only ever contributes via $('...').all(), never as a competing wire.
    """
    get_n8n_name = f"Get N8N {table_key}"
    swallow_name = f"Swallow N8N Read {table_key}"
    count_name = f"Count Supabase {table_key}"
    pages_name = f"Compute Pages {table_key}"
    fetch_page_name = f"Fetch Page {table_key}"
    diff_name = f"Diff {table_key}"
    chunk_name = f"Chunk Drift {table_key}"
    upsert_name = f"Upsert Corrections {table_key}"
    tally_name = f"Tally Upsert {table_key}"
    report_name = f"Report {table_key}"

    compute_pages_js = (
        "const header = $('" + count_name + "').first().json.headers['content-range'];\n"
        "const total = header ? parseInt(header.split('/')[1], 10) || 0 : 0;\n"
        "const pageSize = " + str(RECONCILE_PAGE_SIZE) + ";\n"
        "const pages = [];\n"
        "for (let offset = 0; offset < Math.max(total, 1); offset += pageSize) {\n"
        "  pages.push({ json: { offset, limit: pageSize } });\n"
        "}\n"
        "return pages;\n"
    )

    diff_js = (
        "function normTs(v) { return (v === null || v === undefined) ? null : new Date(v).toISOString(); }\n"
        "const TS_COLS = new Set(['added_at', 'removed_at', 'expires_at', 'createdAt', 'updatedAt']);\n"
        "const cols = " + json.dumps(columns) + ";\n"
        "const pk = " + json.dumps(source_pk) + ";\n"
        "const n8nRows = $('" + get_n8n_name + "').all().map(i => i.json);\n"
        "const supabaseRows = $input.all().map(i => i.json).filter(r => r && r[pk] !== undefined);\n"
        "const byPk = {}; supabaseRows.forEach(r => { byPk[r[pk]] = r; });\n"
        "const NOT_NULL = " + json.dumps(not_null) + ";\n"
        # drifted = the healable rows (the upsert body); drift_meta/unhealable = per-row evidence of
        # WHAT changed, so the alert can name rows and the changed-column signature points at the
        # writer path (e.g. projections_state-only = the projections sweep's Mark Done).
        "const drifted = [], driftMeta = [], unhealable = []; let matched = 0;\n"
        "n8nRows.forEach(row => {\n"
        "  const sup = byPk[row[pk]];\n"
        "  const projected = {}; cols.forEach(c => { projected[c] = row[c] !== undefined ? row[c] : null; });\n"
        "  let changed;\n"
        "  if (!sup) changed = ['new_row'];\n"
        "  else {\n"
        "    changed = [];\n"
        "    for (const c of cols) {\n"
        "      let nv = row[c] !== undefined ? row[c] : null, sv = sup[c] !== undefined ? sup[c] : null;\n"
        "      if (TS_COLS.has(c)) { nv = normTs(nv); sv = normTs(sv); }\n"
        "      if (nv !== sv) changed.push(c);\n"
        "    }\n"
        "    if (!changed.length) { matched++; return; }\n"
        "  }\n"
        "  const sig = changed.filter(c => c !== 'updatedAt');\n"
        "  const meta = { key: row[pk], name: row.full_name || String(row[pk]),\n"
        "    changed: sig.length ? sig : ['updatedAt'],\n"
        "    origin: (typeof row.correlation_id === 'string' && row.correlation_id.split(':')[0]) || null };\n"
        "  const nulls = NOT_NULL.filter(c => projected[c] === null);\n"
        "  if (nulls.length) { meta.null_cols = nulls; unhealable.push(meta); return; }\n"
        "  drifted.push(projected); driftMeta.push(meta);\n"
        "});\n"
        "const n8nKeys = new Set(n8nRows.map(r => r[pk]));\n"
        "const extraInSupabase = supabaseRows.filter(r => !n8nKeys.has(r[pk])).length;\n"
        "return [{ json: { table: " + json.dumps(table_key) + ", n8n_total: n8nRows.length,\n"
        "  supabase_total: supabaseRows.length, matched, drifted_count: drifted.length + unhealable.length,\n"
        "  healable_count: drifted.length, extra_in_supabase: extraInSupabase,\n"
        "  drift_meta: driftMeta, unhealable, drifted } }];\n"
    )

    # ALWAYS emits at least one item: a clean night emits a single 0-row sentinel, so the upsert ->
    # tally -> report chain stays strictly linear (no IF branch fanning back in) and still runs.
    chunk_js = (
        "const diff = $('" + diff_name + "').first().json;\n"
        "const size = " + str(RECONCILE_CHUNK_SIZE) + ";\n"
        "const chunks = [];\n"
        "for (let i = 0; i < diff.drifted.length; i += size) {\n"
        "  const rows = diff.drifted.slice(i, i + size);\n"
        "  chunks.push({ json: { __body: rows, __n: rows.length } });\n"
        "}\n"
        "if (!chunks.length) chunks.push({ json: { __body: [], __n: 0 } });\n"
        "return chunks;\n"
    )

    # onError:continueRegularOutput on the upsert puts success and failure items on ONE output, in
    # chunk order, so this single-predecessor node sees every chunk's outcome exactly once.
    tally_js = (
        "const chunks = $('" + chunk_name + "').all().map(i => i.json);\n"
        "const results = $input.all().map(i => i.json);\n"
        "let healed = 0, failed = 0; const errors = [];\n"
        "results.forEach((r, i) => {\n"
        "  const n = (chunks[i] && chunks[i].__n) || 0;\n"
        "  if (!n) return;\n"
        "  if (r && r.error) { failed += n; errors.push(String(r.error.description || r.error.message || 'unknown error').slice(0, 200)); }\n"
        "  else healed += n;\n"
        "});\n"
        "return [{ json: { healed, failed, errors: [...new Set(errors)] } }];\n"
    )

    report_js = (
        "const d = $('" + diff_name + "').first().json;\n"
        "const t = $input.first().json;\n"
        "const MAX = " + str(REPORT_EXAMPLES_PER_GROUP) + ";\n"
        "function group(rows, sigOf) {\n"
        "  const g = {};\n"
        "  rows.forEach(m => { const s = sigOf(m); (g[s] = g[s] || []).push(m); });\n"
        "  return Object.entries(g).sort((a, b) => b[1].length - a[1].length).map(([sig, ms]) => ({ sig, count: ms.length,\n"
        "    examples: ms.slice(0, MAX).map(m => m.name + ' (#' + m.key + (m.origin ? ', ' + m.origin : '') + ')') }));\n"
        "}\n"
        "return [{ json: { table: d.table, n8n_total: d.n8n_total, supabase_total: d.supabase_total,\n"
        "  matched: d.matched, drifted_count: d.drifted_count, extra_in_supabase: d.extra_in_supabase,\n"
        "  healed: t.healed, heal_failed: t.failed, heal_errors: t.errors, unhealable_count: d.unhealable.length,\n"
        "  groups: group(d.drift_meta, m => m.changed.join('+')),\n"
        "  unhealable_groups: group(d.unhealable, m => 'null ' + m.null_cols.join('+')) } }];\n"
    )

    upsert_node = supabase_http(upsert_name, x0 + 1000, y0, "POST",
                                "={{ '" + SUPABASE_URL + "/rest/v1/" + supabase_table + "?on_conflict=" + supabase_pk + "' }}",
                                prefer="resolution=merge-duplicates,return=minimal")
    upsert_node["onError"] = "continueRegularOutput"

    nodes = [
        node(get_n8n_name, "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get", "dataTableId": source_table_ref,
            "returnAll": True, "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "status", "condition": "isNotEmpty"}]},
            "options": {}
        }, x0, y0, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 2,
                                 "alwaysOutputData": True}),
        # swallows get_n8n_name's N-row bulk output back down to exactly 1 item, runOnceForAllItems,
        # completely ignoring its own input -- same "Reset After Domains" pattern already proven in
        # the drainer fix. get_n8n_name stays a true ancestor of diff_name (safe for the named-ref
        # read) without its bulk output ever becoming count_name/fetch_page_name's actual input.
        code_node(swallow_name, "return [{ json: {} }];\n", x0 + 100, y0),
        supabase_http(count_name, x0, y0 + 120, "GET",
                      "={{ '" + SUPABASE_URL + "/rest/v1/" + supabase_table + "?select=" + supabase_pk + "&limit=1' }}",
                      extra_headers=[{"name": "Prefer", "value": "count=exact"}]),
        code_node(pages_name, compute_pages_js, x0 + 200, y0 + 120),
        supabase_http(fetch_page_name, x0 + 400, y0 + 120, "GET",
                      "={{ '" + SUPABASE_URL + "/rest/v1/" + supabase_table + "?select=*&offset=' + $json.offset + '&limit=' + $json.limit }}",
                      full_response=False),
        code_node(diff_name, diff_js, x0 + 600, y0),
        code_node(chunk_name, chunk_js, x0 + 800, y0),
        upsert_node,
        code_node(tally_name, tally_js, x0 + 1100, y0),
        code_node(report_name, report_js, x0 + 1200, y0),
    ]
    conn = {
        get_n8n_name: {"main": [[{"node": swallow_name, "type": "main", "index": 0}]]},
        swallow_name: {"main": [[{"node": count_name, "type": "main", "index": 0}]]},
        count_name: {"main": [[{"node": pages_name, "type": "main", "index": 0}],
                               [{"node": pages_name, "type": "main", "index": 0}]]},
        pages_name: {"main": [[{"node": fetch_page_name, "type": "main", "index": 0}]]},
        fetch_page_name: {"main": [[{"node": diff_name, "type": "main", "index": 0}],
                                    [{"node": diff_name, "type": "main", "index": 0}]]},
        # Strictly linear through the upsert (2026-09-24). It used to be a fire-and-forget dead end
        # with Report wired straight off Diff, because a clean night emitted zero chunks and the
        # upsert never ran (2026-09-14). That kept the report alive but made heal failures
        # invisible: the alert said "healed by upsert" for 9 nights while every heal was rejected.
        # Chunk Drift now always emits >=1 item (a 0-row sentinel on a clean night), so the upsert
        # always runs and its outcome reaches the report through a single wire.
        diff_name: {"main": [[{"node": chunk_name, "type": "main", "index": 0}]]},
        chunk_name: {"main": [[{"node": upsert_name, "type": "main", "index": 0}]]},
        upsert_name: {"main": [[{"node": tally_name, "type": "main", "index": 0}]]},
        tally_name: {"main": [[{"node": report_name, "type": "main", "index": 0}]]},
    }
    return nodes, conn, report_name, get_n8n_name, count_name


reg_nodes, reg_conn, reg_report, reg_get, reg_count = build_reconcile_table(
    "Registry", REGISTRY_TABLE, "id", "dnc_registry", "id", REGISTRY_COLUMNS, REGISTRY_NOT_NULL, -1600, 0)
dom_nodes, dom_conn, dom_report, dom_get, dom_count = build_reconcile_table(
    "Domains", {"__rl": True, "mode": "id", "value": "ai4ZiOGqzuJHRYLB"}, "domain",
    "dnc_domains", "domain", DOMAINS_COLUMNS, DOMAINS_NOT_NULL, -1600, 500)

combine_reports_js = (
    "const reg = $('" + reg_report + "').first().json;\n"
    "const dom = $('" + dom_report + "').first().json;\n"
    "const total_drift = reg.drifted_count + dom.drifted_count;\n"
    "return [{ json: { reg, dom, total_drift } }];\n"
)

# "healed" is only ever claimed for rows the upsert actually accepted -- the old text asserted it
# unconditionally and was false for 9 straight nights (2026-09-16 -> 09-24).
build_alert_text_js = (
    "const j = $input.first().json;\n"
    "const lines = []; let bad = false;\n"
    "for (const [label, r] of [['dnc_registry', j.reg], ['dnc_domains', j.dom]]) {\n"
    "  if (!r || !(r.drifted_count > 0)) continue;\n"
    "  if (r.heal_failed > 0 || r.unhealable_count > 0) bad = true;\n"
    "  lines.push('*' + label + '*: ' + r.drifted_count + ' drifted / ' + r.n8n_total + ' -- healed ' + r.healed\n"
    "    + (r.heal_failed ? ', FAILED ' + r.heal_failed : '') + (r.unhealable_count ? ', unhealable ' + r.unhealable_count : '')\n"
    "    + (r.extra_in_supabase ? ', extra_in_supabase ' + r.extra_in_supabase : ''));\n"
    "  (r.heal_errors || []).forEach(e => lines.push('    upsert error: `' + e + '`'));\n"
    "  (r.unhealable_groups || []).forEach(g => lines.push('    NOT HEALED, ' + g.sig + ' (' + g.count + '): ' + g.examples.join(', ') + (g.count > g.examples.length ? ', ...' : '')));\n"
    "  (r.groups || []).forEach(g => lines.push('    ' + g.sig + ' (' + g.count + '): ' + g.examples.join(', ') + (g.count > g.examples.length ? ', ...' : '')));\n"
    "}\n"
    "const head = bad ? ':rotating_light: *Supabase nightly reconcile* -- drift NOT fully healed:'\n"
    "                 : ':warning: *Supabase nightly reconcile* found drift, healed from n8n (source of truth):';\n"
    "lines.push('_changed-column signature points at the writer: projections_state = projections sweep; new_row = a write that never enqueued a claim_');\n"
    "return [{ json: { text: '=' + head + '\\n' + lines.join('\\n') } }];\n"
)

build_meta_rows_js = (
    "const c = $input.first().json;\n"
    "return [{ json: { __body: [\n"
    "  { last_sync_at: new Date().toISOString(), row_count: c.reg.n8n_total, source: 'nightly_reconcile:dnc_registry' },\n"
    "] } }, { json: { __body: [\n"
    "  { last_sync_at: new Date().toISOString(), row_count: c.dom.n8n_total, source: 'nightly_reconcile:dnc_domains' },\n"
    "] } }];\n"
)

rc_nodes = [
    node("Reconcile Timer", "n8n-nodes-base.scheduleTrigger",
         {"rule": {"interval": [{"field": "cronExpression", "expression": "20 6 * * *"}]}},
         -1800, y=0, tv=1.2),
    node("Manual Trigger", "n8n-nodes-base.webhook",
         {"httpMethod": "GET", "path": "{{WEBHOOK_DNC_SUPABASE_NIGHTLY_RECONCILE}}", "responseMode": "onReceived", "options": {}},
         -1800, y=180, extra={"webhookId": "dncsupabasereconcile01"}),
] + reg_nodes + dom_nodes + [
    code_node("Combine Reports", combine_reports_js, 200, y=250),
    node("Any Drift?", "n8n-nodes-base.if",
         {"conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"}, "combinator": "and",
                         "conditions": [{"leftValue": "={{ $json.total_drift > 0 }}", "rightValue": True,
                                         "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}},
         400, y=250, tv=2),
    code_node("Build Alert Text", build_alert_text_js, 600, y=140),
    slack_post("Slack Drift Alert", "={{ $json.text }}", 800, y=140),
    code_node("Build Meta Rows", build_meta_rows_js, 600, y=350),
    supabase_http("Insert Meta Rows", 800, 350, "POST",
                  "={{ '" + SUPABASE_URL + "/rest/v1/dnc_registry_meta' }}",
                  prefer="resolution=merge-duplicates,return=minimal"),
]
rc_conn = {
    # STRICTLY SEQUENTIAL: trigger -> Registry's whole pipeline -> Domains' whole pipeline ->
    # Combine Reports. Found live 2026-09-14: running both tables in parallel (trigger fanning out
    # to both, both Report nodes wired directly into Combine Reports) fired Combine Reports 4
    # times in one execution (2x2, compounding each table's own multi-wire bug) and quadruple-
    # inserted meta rows. Combine Reports now has exactly ONE direct predecessor (Report Domains)
    # and reads Report Registry via a named reference -- safe because Report Registry is now a
    # true ancestor (single chain), not a parallel sibling.
    "Reconcile Timer": {"main": [[{"node": reg_get, "type": "main", "index": 0}]]},
    "Manual Trigger": {"main": [[{"node": reg_get, "type": "main", "index": 0}]]},
}
rc_conn.update(reg_conn)
rc_conn.update(dom_conn)
rc_conn[reg_report] = {"main": [[{"node": dom_get, "type": "main", "index": 0}]]}
rc_conn[dom_report] = {"main": [[{"node": "Combine Reports", "type": "main", "index": 0}]]}
rc_conn["Combine Reports"] = {"main": [[{"node": "Any Drift?", "type": "main", "index": 0}]]}
rc_conn["Any Drift?"] = {"main": [
    [{"node": "Build Alert Text", "type": "main", "index": 0}, {"node": "Build Meta Rows", "type": "main", "index": 0}],
    [{"node": "Build Meta Rows", "type": "main", "index": 0}],
]}
rc_conn["Build Alert Text"] = {"main": [[{"node": "Slack Drift Alert", "type": "main", "index": 0}]]}
rc_conn["Slack Drift Alert"] = {"main": [[], []]}
rc_conn["Build Meta Rows"] = {"main": [[{"node": "Insert Meta Rows", "type": "main", "index": 0}]]}
rc_conn["Insert Meta Rows"] = {"main": [[], []]}

write("workflows/dnc_supabase_nightly_reconcile/dnc_supabase_nightly_reconcile.json",
      wf("dnc_supabase_nightly_reconcile", rc_nodes, rc_conn))

print("OK")
