"""
dnc_i04_daily_diff -- n8n port of the local I-04 daily snapshot+diff cron (i04_snapshot.py +
i04_diff.py + README, all in this directory). The diff LOGIC is a straight port, verified against
the real 19->20 Aug pair; the WALK is a chunked rebuild (this version) replacing the original
single-execution walk, which crashed the n8n instance (503s, execution status "crashed") when
fired against the real ~58k-lead/person estate -- see the #niks-channel incident post. That
crash's own root-cause line is the standing lesson for every future full-estate operation in this
project: "a small synthetic test proved the LOGIC correct, never the SCALE -- hundreds of real
network round-trips against production Pipedrive is a different risk profile than one in-memory
reduce over 5000 fake records." Any new full-estate walk gets a bounded, staged first run from now
on, not a single-shot fire-and-hope.

CHUNKED-WALK ARCHITECTURE (this version):
  A frequently-firing schedule trigger ("Walk Ticker") checks a persisted walk-state row each
  tick and does AT MOST one bounded unit of work per execution, then stops:
    - state == none (fresh day) + off-peak hour -> start (init state, same as continue_leads)
    - state == none (fresh day) + NOT off-peak  -> noop, wait for the off-peak window
    - status == walking_leads    -> fetch ONE chunk of leads (bounded: 3 pages x 500/page = 1500
                                      records -- S3B's own proven chunk size, reused verbatim per
                                      Nik's explicit instruction), stage each record as its own row
                                      in i04_walk_staging, advance the cursor
    - status == walking_persons  -> same shape, cursor-paginated (v2 API), 3 pages x 100/page
    - status == compacting       -> bulk-read the day's staged rows (one plain Data Table query,
                                      NOT hundreds of HTTP round-trips -- fundamentally cheaper than
                                      the walk itself), build the real i04_snapshots row, purge the
                                      staging rows, mark the walk done, then run the EXISTING
                                      diff/departures/report/retention/idle-guard graph unchanged
    - status == done / circuit_broken -> noop
  Off-peak gate applies ONLY to starting a fresh day's walk; once started, ticks continue at
  whatever cadence the trigger fires, since each tick is already small and bounded regardless of
  hour. Circuit breaker: any 5xx (or other HTTP error) from either chunk fetch flips status to
  circuit_broken and alerts -- by design this does NOT auto-resume ("do not hammer" per the
  explicit spec); resuming requires a human to confirm the underlying issue is clear and manually
  restore status from the saved resume_status field, at which point the NEXT tick picks up from
  the exact cursor position saved just before the break (no data lost, just paused).
  Walk state itself lives as a sentinel row inside i04_snapshots (date="_state_<today>",
  kept_reason="state") rather than a third table -- reuses the existing upsert-by-date plumbing,
  and is explicitly excluded from both the real-snapshot diff query (kept_reason != 'state') and
  the daily-retention prune (which only ever selects kept_reason == 'daily'). A separate light
  prune step below deletes state rows older than a few days so they don't accumulate forever.

  Second table `i04_walk_staging` (see CREATE_I04_WALK_STAGING_TABLE.md): walk_date / resource
  ("lead"|"person") / entity_id / data_json -- one small row per record, written during the walk,
  bulk-read and deleted during compaction. Holds at most one day's in-progress walk at a time.

Storage design decision (verified live, not guessed -- see zz_probe_check_gzip_and_scale.py and
zz_probe_gzip_roundtrip.py, both deleted after use):
  - zlib/gzip is NOT available inside n8n's Code node sandbox ("Module 'zlib' is disallowed").
  - n8n's native Compression node DOES gzip real binary data correctly (round-trip verified on a
    5000-record test payload) -- but the platform stores binary data EXTERNALLY (this instance
    uses "filesystem-v2" mode) and the item's own JSON only carries a mode marker + a reference
    id, not inline base64 -- extracting a plain base64 string from a binary reference for
    Data-Table storage needs one more verified step this build does NOT block on.
  Consequence: this stores each day's FINAL compacted snapshot as UNCOMPRESSED JSON text in one
  i04_snapshots row (same as before). At ~58k leads this runs larger than the original script's
  2.4MB gzip (rough estimate 8-15MB/day uncompressed) -- N8N_DATA_TABLES_MAX_SIZE_BYTES needs
  raising for the intended 30-day-rolling + 6-month-weekly retention (already flagged in
  CREATE_I04_SNAPSHOTS_TABLE.md). Swapping to real gzip via the Compression node remains a
  verified-available, not-yet-wired follow-up.

Table: i04_snapshots (create via n8n UI first -- see CREATE_I04_SNAPSHOTS_TABLE.md)
  date            String    "2026-08-20"  (or "_state_2026-08-20" for a walk-state sentinel row)
  captured_at     Date
  source          String
  counts_json     String    JSON: {leads, persons, dnc_labelled, dnc_field_686} for a real
                             snapshot row, or the walk-state object for a sentinel row
  leads_json      String    JSON: {lead_id: [labels_joined, person_id, add_time]} (empty string on
                             sentinel rows)
  persons_json    String    JSON: {person_id: [add_time, update_time, email_lc, lh_slug, dnc686]}
                             (empty string on sentinel rows)
  dnc_labelled_json String  JSON array of lead ids (empty string on sentinel rows)
  kept_reason     String    "daily" | "weekly" | "state" -- "state" rows are walk-progress
                             sentinels, never touched by the daily-retention prune

Table: i04_walk_staging (create via n8n UI first -- see CREATE_I04_WALK_STAGING_TABLE.md)
  walk_date  String   which day's walk this row belongs to
  resource   String   "lead" | "person"
  entity_id  String   the lead id (uuid) or person id (numeric, as string)
  data_json  String   the minimal per-entity record, same shape as the old in-memory reduce
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

# ---------------------------------------------------------------------------
# minimal self-contained node-builder helpers (deliberately NOT imported from
# DNC_OBS_P1_build/build_dnc.py -- that file executes side-effecting write() calls at import
# time, so importing it would silently regenerate every DNC workflow as a side effect of building
# this one. Matches this project's own established pattern: each major workflow family
# (WF1_W1.0.1_build, DNC_OBS_P1_build) already has its own independent, self-contained builder.)
# ---------------------------------------------------------------------------
OPS_CHANNEL = "C0B8GCVNR5W"
TELEMETRY_CHANNEL = "C0BQM1X9ZUY"
PIPEDRIVE_CRED = {"id": "DEFM2qykN8B2lqzw", "name": "Pipedrive API (DNC projections)"}
CORE_ERROR_HANDLER_ID = "BbrXPABgOaaTJjD6"
I04_TABLE = {"__rl": True, "mode": "name", "value": "i04_snapshots"}
STAGING_TABLE = {"__rl": True, "mode": "name", "value": "i04_walk_staging"}
# mode:"name" ("i04_event_log", later renamed "i04_log") reproducibly failed live --
# "Could not find the data table" on every write, from multiple freshly-created probe workflows,
# across a rename, ruled out column-completeness and (per Nik) project mismatch -- yet writing by
# real ID worked on the first try. Same bug class already documented in build_dnc.py's own
# TABLE_IDS dict (mode:"name" is fragile across invocation/project contexts; mode:"id" is the
# reliable reference). Verified live 2026-08-26 via zz_probe_table_by_id.py before shipping.
EVENT_LOG_TABLE = {"__rl": True, "mode": "id", "value": "zAW2IYoO6Dj0vdIt"}

# S3B's own proven chunk size, reused verbatim per Nik's explicit instruction ("the S3B chunk size
# is the proven reference") -- bounded pages per execution, never a single mega-fetch.
CHUNK_MAX_PAGES = 3
LEADS_PAGE_SIZE = 500
PERSONS_PAGE_SIZE = 100


def node(name, ntype, params, x, y=300, tv=1, extra=None):
    n = {"parameters": params, "id": name.lower().replace(" ", "_").replace("?", "").replace(":", ""),
         "name": name, "type": ntype, "typeVersion": tv, "position": [x, y]}
    if extra:
        n.update(extra)
    return n


def conns(pairs):
    c = {}
    for a, b in pairs:
        c.setdefault(a, {"main": [[]]})
        c[a]["main"][0].append({"node": b, "type": "main", "index": 0})
    return c


def code_node(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code", {"jsCode": js, "mode": "runOnceForAllItems"}, x, y, tv=2)


def code_node_per_item(name, js, x, y=300):
    return node(name, "n8n-nodes-base.code", {"jsCode": js, "mode": "runOnceForEachItem"}, x, y, tv=2)


def set_config(assignments, x=-1200, y=300):
    a = []
    for name_, val, typ in assignments:
        a.append({"id": name_, "name": name_, "value": val, "type": typ})
    return node("CONFIG", "n8n-nodes-base.set",
                {"assignments": {"assignments": a}, "includeOtherFields": True, "options": {}},
                x, y, tv=3.4)


def if_bool(name, expr, x, y=300):
    return node(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "typeValidation": "loose"},
                       "combinator": "and",
                       "conditions": [{"leftValue": expr, "rightValue": True,
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}
    }, x, y, tv=2)


def slack_post(name, text_expr, x, y=300, channel_expr=None, extra_props=None):
    extra = {"credentials": {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Smartlead Slack"}}}
    if extra_props:
        extra.update(extra_props)
    return node(name, "n8n-nodes-base.slack", {
        "resource": "message", "operation": "post", "select": "channel",
        "channelId": {"__rl": True, "mode": "id", "value": channel_expr or OPS_CHANNEL},
        "text": text_expr, "otherOptions": {}
    }, x, y, tv=2.2, extra=extra)


def http_pipedrive_chunk_offset(name, url_expr, x, y=300, max_requests=CHUNK_MAX_PAGES):
    # bounded offset-paginated fetch -- at most `max_requests` pages per execution, never a
    # full-estate mega-fetch. Same completion-signal discipline as before (follow
    # more_items_in_collection), just capped.
    return node(name, "n8n-nodes-base.httpRequest", {
        "method": "GET", "url": url_expr,
        "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
        "options": {
            "batching": {"batch": {"batchSize": 1, "batchInterval": 400}},
            "pagination": {"pagination": {
                "paginationMode": "updateAParameterInEachRequest",
                "parameters": {"parameters": [
                    {"type": "qs", "name": "start",
                     "value": "={{ $response.body.additional_data.pagination.start + "
                              "$response.body.additional_data.pagination.limit }}"},
                ]},
                "paginationCompleteWhen": "other",
                "completeExpression": "={{ !$response.body.additional_data.pagination.more_items_in_collection }}",
                "limitPagesFetched": True, "maxRequests": max_requests, "requestInterval": 400,
            }},
        },
    }, x, y, tv=4.2, extra={
        "credentials": {"httpQueryAuth": PIPEDRIVE_CRED},
        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000})


def http_pipedrive_chunk_cursor(name, url_expr, x, y=300, max_requests=CHUNK_MAX_PAGES):
    return node(name, "n8n-nodes-base.httpRequest", {
        "method": "GET", "url": url_expr,
        "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
        "options": {
            "batching": {"batch": {"batchSize": 1, "batchInterval": 400}},
            "pagination": {"pagination": {
                "paginationMode": "updateAParameterInEachRequest",
                "parameters": {"parameters": [
                    {"type": "qs", "name": "cursor",
                     "value": "={{ $response.body.additional_data.next_cursor }}"},
                ]},
                "paginationCompleteWhen": "other",
                "completeExpression": "={{ !$response.body.additional_data.next_cursor }}",
                "limitPagesFetched": True, "maxRequests": max_requests, "requestInterval": 400,
            }},
        },
    }, x, y, tv=4.2, extra={
        "credentials": {"httpQueryAuth": PIPEDRIVE_CRED},
        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 2000})


def dt_get(name, keyName, keyValueExpr, x, y=300, return_all=False, table=None):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "get",
        "dataTableId": table or I04_TABLE,
        "returnAll": return_all, "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": keyName, "condition": "eq", "keyValue": keyValueExpr}]},
        "options": {}
    }, x, y, tv=1)


def dt_upsert(name, value_map, matching, x, y=300, table=None, guard=True):
    conditions = [{"keyName": col, "condition": "eq", "keyValue": value_map[col]} for col in matching]
    extra = {"onError": "stopWorkflow", "retryOnFail": False} if guard else \
            {"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3}
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "upsert",
        "dataTableId": table or I04_TABLE,
        "matchType": "allConditions",
        "filters": {"conditions": conditions},
        "columns": {"mappingMode": "defineBelow", "value": value_map, "matchingColumns": matching, "schema": []},
        "options": {}
    }, x, y, tv=1, extra=extra)


def dt_delete(name, keyName, keyValueExpr, x, y=300, table=None):
    return node(name, "n8n-nodes-base.dataTable", {
        "resource": "row", "operation": "deleteRows",
        "dataTableId": table or I04_TABLE,
        "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": keyName, "condition": "eq", "keyValue": keyValueExpr}]},
        "options": {}
    }, x, y, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3})


def wf(name, nodes_, connections):
    return {"name": name, "nodes": nodes_, "connections": connections,
            "settings": {"executionOrder": "v1", "errorWorkflow": CORE_ERROR_HANDLER_ID}, "active": False}


def write(path, obj):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    json.load(open(full, encoding="utf-8"))
    print("wrote", path, "(%d nodes)" % len(obj["nodes"]))


# ===========================================================================
# constants ported verbatim from i04_snapshot.py / i04_diff.py
# ===========================================================================
DNC_LABEL = "52a7c290-fc73-11f0-ad98-81d4703453f3"
LH_KEY = "66f0af69bec838dc3f90bb3f16c7d6087d8dbb20"
DNC_FIELD = "9c018b7406ebc481b9c108a487f76c4d09f91c9b"
DNC_ACTIVE = "686"
EXPECTED_DNC = json.load(open(os.path.join(os.path.dirname(HERE), "audit-artifacts",
                                            "prereversal_baseline_FINAL.json"), encoding="utf-8")
                          )["expected_survivors"]


def build(wf_name, test_webhook=False):
    # -------------------- ticker: decide what this tick should do --------------------
    decide_walk_action_js = (
        # 2026-08-26 I-04 REDESIGN (Nik): this chunked walk is no longer the primary detector --
        # dnc_i04_event_receiver + dnc_i04_daily_summary own that job now, near-zero load. This
        # walk is repurposed as the WEEKLY reconciliation safety net (ground-truth catch-all for
        # anything a missed/malformed webhook delivery didn't log). Only the START of a fresh walk
        # is gated by day-of-week -- once a walk is in progress, ticks continue regardless (a
        # multi-day walk that started on the target day must still finish).\n"
        "const cfg = $('CONFIG').first().json;\n"
        "const offpeakStart = parseInt(cfg.offpeak_start_hour, 10);\n"
        "const offpeakEnd = parseInt(cfg.offpeak_end_hour, 10);\n"
        "const reconcileDow = parseInt(cfg.reconcile_day_of_week, 10); // 0=Sunday\n"
        "const today = new Date().toISOString().slice(0, 10);\n"
        "const hour = new Date().getUTCHours();\n"
        "const dow = new Date().getUTCDay();\n"
        "const offPeak = hour >= offpeakStart && hour < offpeakEnd;\n"
        "const isReconcileDay = dow === reconcileDow;\n"
        "const rows = $input.all().map(i => i.json);\n"
        "let state = null;\n"
        "if (rows.length && rows[0].counts_json) {\n"
        "  try { state = JSON.parse(rows[0].counts_json); } catch (e) { state = null; }\n"
        "}\n"
        "let action;\n"
        "if (!state) {\n"
        "  if (!offPeak || !isReconcileDay) { action = 'noop'; }\n"
        "  else {\n"
        "    action = 'continue_leads';\n"
        "    state = { status: 'walking_leads', leads_next_start: 0, persons_cursor: null,\n"
        "      leads_pages_done: 0, persons_pages_done: 0, started_at: new Date().toISOString() };\n"
        "  }\n"
        "} else if (state.status === 'done' || state.status === 'circuit_broken') {\n"
        "  action = 'noop';\n"
        "} else if (state.status === 'walking_leads') { action = 'continue_leads'; }\n"
        "else if (state.status === 'walking_persons') { action = 'continue_persons'; }\n"
        "else if (state.status === 'compacting') { action = 'compact'; }\n"
        "else { action = 'noop'; }\n"
        "return [{ json: { action, today, state } }];\n"
    )

    reduce_leads_chunk_js = (
        "const pages = $input.all().map(i => i.json);\n"
        "const prevState = $('Decide Walk Action').first().json.state;\n"
        "const today = $('Decide Walk Action').first().json.today;\n"
        "const leads = pages.flatMap(p => Array.isArray(p.data) ? p.data : []);\n"
        "const lastPage = pages[pages.length - 1] || {};\n"
        "const pag = (lastPage.additional_data || {}).pagination || {};\n"
        "const morePages = !!pag.more_items_in_collection;\n"
        "const nextStart = (typeof pag.start === 'number' ? pag.start : prevState.leads_next_start) + "
        "(pag.limit || %d);\n"
        "const newState = Object.assign({}, prevState, {\n"
        "  leads_next_start: nextStart,\n"
        "  status: morePages ? 'walking_leads' : 'walking_persons',\n"
        "  leads_pages_done: (prevState.leads_pages_done || 0) + pages.length,\n"
        "});\n"
        "const stagingItems = leads.map(x => ({ json: {\n"
        "  walk_date: today, resource: 'lead', entity_id: String(x.id),\n"
        "  data_json: JSON.stringify([ (x.label_ids || []).slice().sort().join('|'), x.person_id, x.add_time ]),\n"
        "} }));\n"
        "const stateItem = { json: { __state_update: true, date: '_state_' + today, source: 'walk_state',\n"
        "  kept_reason: 'state', captured_at: new Date().toISOString(), counts_json: JSON.stringify(newState),\n"
        "  leads_json: '', persons_json: '', dnc_labelled_json: '' } };\n"
        "return stagingItems.length ? [...stagingItems, stateItem] : [stateItem];\n"
    ) % LEADS_PAGE_SIZE

    reduce_persons_chunk_js = (
        "const pages = $input.all().map(i => i.json);\n"
        "const prevState = $('Decide Walk Action').first().json.state;\n"
        "const today = $('Decide Walk Action').first().json.today;\n"
        "const persons = pages.flatMap(p => Array.isArray(p.data) ? p.data : []);\n"
        "const lastPage = pages[pages.length - 1] || {};\n"
        "const nextCursor = (lastPage.additional_data || {}).next_cursor || null;\n"
        "const newState = Object.assign({}, prevState, {\n"
        "  persons_cursor: nextCursor,\n"
        "  status: nextCursor ? 'walking_persons' : 'compacting',\n"
        "  persons_pages_done: (prevState.persons_pages_done || 0) + pages.length,\n"
        "});\n"
        "const stagingItems = persons.map(p => {\n"
        "  const cf = p.custom_fields || {};\n"
        "  const emails = (p.emails || []).map(e => e.value).filter(Boolean);\n"
        "  const email = emails.length ? emails[0].trim().toLowerCase() : '';\n"
        "  const lh = cf['%s'] || null;\n"
        "  const liMatch = /linkedin\\.com\\/(?:in|pub)\\/([^\\/?#\\s]+)/i.exec(String(lh || '').toLowerCase());\n"
        "  const slug = liMatch ? liMatch[1] : '';\n"
        "  const dnc = cf['%s'];\n"
        "  return { json: { walk_date: today, resource: 'person', entity_id: String(p.id),\n"
        "    data_json: JSON.stringify([ p.add_time, p.update_time, email, slug, (dnc === '%s' ? 1 : 0) ]) } };\n"
        "});\n"
        "const stateItem = { json: { __state_update: true, date: '_state_' + today, source: 'walk_state',\n"
        "  kept_reason: 'state', captured_at: new Date().toISOString(), counts_json: JSON.stringify(newState),\n"
        "  leads_json: '', persons_json: '', dnc_labelled_json: '' } };\n"
        "return stagingItems.length ? [...stagingItems, stateItem] : [stateItem];\n"
    ) % (LH_KEY, DNC_FIELD, DNC_ACTIVE)

    circuit_breaker_js = (
        "const ctx = $('Decide Walk Action').first().json;\n"
        "const prevState = ctx.state || {};\n"
        "const today = ctx.today;\n"
        "const err = ($input.first().json || {}).error || {};\n"
        "const reason = (err.message || err.description || 'unknown error')\n"
        "  + (err.httpCode ? (' (HTTP ' + err.httpCode + ')') : '');\n"
        "const newState = Object.assign({}, prevState, {\n"
        "  status: 'circuit_broken', resume_status: prevState.status,\n"
        "  broken_reason: reason, broken_at: new Date().toISOString(),\n"
        "});\n"
        "return [{ json: { date: '_state_' + today, source: 'walk_state', kept_reason: 'state',\n"
        "  captured_at: new Date().toISOString(), counts_json: JSON.stringify(newState),\n"
        "  leads_json: '', persons_json: '', dnc_labelled_json: '', broken_reason: reason } }];\n"
    )

    mark_walk_done_js = (
        "const ctx = $('Decide Walk Action').first().json;\n"
        "const today = ctx.today;\n"
        "const prevState = ctx.state || {};\n"
        "const newState = Object.assign({}, prevState, { status: 'done', completed_at: new Date().toISOString() });\n"
        "return [{ json: { date: '_state_' + today, source: 'walk_state', kept_reason: 'state',\n"
        "  captured_at: new Date().toISOString(), counts_json: JSON.stringify(newState),\n"
        "  leads_json: '', persons_json: '', dnc_labelled_json: '' } }];\n"
    )

    compact_snapshot_js = (
        "const rows = $input.all().map(i => i.json);\n"
        "const ctx = $('Decide Walk Action').first().json;\n"
        "const today = ctx.today;\n"
        "const L = {}, P = {};\n"
        "for (const r of rows) {\n"
        "  let d; try { d = JSON.parse(r.data_json); } catch (e) { continue; }\n"
        "  if (r.resource === 'lead') L[r.entity_id] = d;\n"
        "  else if (r.resource === 'person') P[r.entity_id] = d;\n"
        "}\n"
        "const dncLabelled = Object.keys(L).filter(id => (L[id][0] || '').split('|').includes('%s')).sort();\n"
        "const counts = {\n"
        "  leads: Object.keys(L).length, persons: Object.keys(P).length,\n"
        "  dnc_labelled: dncLabelled.length,\n"
        "  dnc_field_686: Object.values(P).filter(v => v[4] === 1).length,\n"
        "};\n"
        "const now = new Date().toISOString();\n"
        "return [{ json: {\n"
        "  date: today, captured_at: now, source: 'n8n chunked walk', counts,\n"
        "  leads_json: JSON.stringify(L), persons_json: JSON.stringify(P),\n"
        "  dnc_labelled_json: JSON.stringify(dncLabelled), counts_json: JSON.stringify(counts),\n"
        "} }];\n"
    ) % DNC_LABEL

    # -------------------- DIFF (ported from i04_diff.py, verbatim logic, unchanged) --------------------
    diff_js = (
        "const today = $('Build Snapshot').first().json;\n"
        "const prevRow = $('Pick Previous Snapshot').first().json;\n"
        "if (!prevRow || !prevRow.leads_json) {\n"
        "  return [{ json: { ok: false, reason: 'no previous snapshot -- first run, nothing to diff against yet' } }];\n"
        "}\n"
        "const A = { counts: JSON.parse(prevRow.counts_json), leads: JSON.parse(prevRow.leads_json),\n"
        "  persons: JSON.parse(prevRow.persons_json), dnc_labelled: JSON.parse(prevRow.dnc_labelled_json) };\n"
        "const B = { counts: JSON.parse(today.counts_json), leads: JSON.parse(today.leads_json),\n"
        "  persons: JSON.parse(today.persons_json), dnc_labelled: JSON.parse(today.dnc_labelled_json) };\n"
        "\n"
        "// 1+2: departures / arrivals / reconciliation\n"
        "const la = new Set(Object.keys(A.leads)), lb = new Set(Object.keys(B.leads));\n"
        "const gone = [...la].filter(x => !lb.has(x)).sort();\n"
        "const arrived = [...lb].filter(x => !la.has(x)).sort();\n"
        "const calc = A.counts.leads - gone.length + arrived.length;\n"
        "const reconciles = calc === B.counts.leads;\n"
        "\n"
        "// 3: DNC label set, id-exact\n"
        "const EXPECTED = new Set(%s);\n"
        "const dncSet = new Set(B.dnc_labelled);\n"
        "const dncExact = dncSet.size === EXPECTED.size && [...dncSet].every(x => EXPECTED.has(x));\n"
        "const dncUnexpected = [...dncSet].filter(x => !EXPECTED.has(x)).sort();\n"
        "const dncMissing = [...EXPECTED].filter(x => !dncSet.has(x)).sort();\n"
        "\n"
        "// 4: new persons + duplicate check (same email or same LinkedIn slug)\n"
        "const pa = new Set(Object.keys(A.persons));\n"
        "const newPersons = Object.keys(B.persons).filter(x => !pa.has(x))"
        ".sort((x, y) => (B.persons[x][0] || '').localeCompare(B.persons[y][0] || ''));\n"
        "const byEmail = {}, bySlug = {};\n"
        "for (const [pid, v] of Object.entries(B.persons)) {\n"
        "  if (v[2]) { (byEmail[v[2]] = byEmail[v[2]] || []).push(pid); }\n"
        "  if (v[3]) { (bySlug[v[3]] = bySlug[v[3]] || []).push(pid); }\n"
        "}\n"
        "const dups = [];\n"
        "for (const pid of newPersons) {\n"
        "  const v = B.persons[pid];\n"
        "  const eTwins = (byEmail[v[2]] || []).filter(x => x !== pid);\n"
        "  const sTwins = (bySlug[v[3]] || []).filter(x => x !== pid);\n"
        "  if (eTwins.length || sTwins.length) dups.push({ person: pid, email: v[2], slug: v[3], email_twins: eTwins, slug_twins: sTwins });\n"
        "}\n"
        "\n"
        "// 5a: DNC field-686 delta -- missing is null, never a fake zero\n"
        "const pa686 = A.counts.dnc_field_686, pb686 = B.counts.dnc_field_686;\n"
        "const d686 = (pa686 == null || pb686 == null) ? null : (pb686 - pa686);\n"
        "\n"
        "return [{ json: {\n"
        "  ok: true, prev_date: prevRow.date, curr_date: today.date,\n"
        "  prev_counts: A.counts, curr_counts: B.counts,\n"
        "  departures_count: gone.length, arrivals_count: arrived.length,\n"
        "  departures_sample: gone.slice(0, 12), arrivals_sample: arrived.slice(0, 12),\n"
        "  departures_all: gone, reconciles,\n"
        "  dnc: { labelled: [...dncSet].sort(), exact: dncExact, unexpected: dncUnexpected, missing: dncMissing },\n"
        "  new_persons_count: newPersons.length, new_person_duplicates: dups,\n"
        "  dnc686_prev: pa686, dnc686_curr: pb686, dnc686_delta: d686,\n"
        "} }];\n"
    ) % json.dumps(EXPECTED_DNC)

    classify_departures_js = (
        "return { json: { lead_id: $json } };\n"
    )
    departure_detail_js = (
        "const lid = $('Split Departures').item.json.lead_id;\n"
        "if ($json.error) {\n"
        "  return { json: { lead: lid, deleted_http: $json.error.httpCode || $json.error.status || 'unknown' } };\n"
        "}\n"
        "const d = $json.data || {};\n"
        "return { json: { lead: lid, archived: d.is_archived, archive_time: d.archive_time,\n"
        "  person_id: d.person_id, title: String(d.title || '').slice(0, 70), owner_id: d.owner_id } };\n"
    )
    combine_departures_js = (
        "const dep = $input.all().map(i => i.json);\n"
        "const archived = dep.filter(r => r.archived);\n"
        "const deleted = dep.filter(r => r.deleted_http);\n"
        "return [{ json: { departures_detail: dep, archived_count: archived.length,\n"
        "  deleted_count: deleted.length, undeclared_candidates: archived.length } }];\n"
    )

    idle_guard_js = (
        "const sd = $getWorkflowStaticData('global');\n"
        "const today = new Date().toISOString().slice(0, 10);\n"
        "const lastPosted = sd.lastPostedDate || null;\n"
        "const missed = lastPosted !== today;\n"
        "return [{ json: { missed_today: missed, last_posted_date: lastPosted, today } }];\n"
    )
    mark_posted_js = (
        "const sd = $getWorkflowStaticData('global');\n"
        "sd.lastPostedDate = new Date().toISOString().slice(0, 10);\n"
        "return $input.all();\n"
    )

    combine_report_js = (
        "const cfg = $('CONFIG').first().json;\n"
        "const diff = $('Diff').first().json;\n"
        "const dep = $('Combine Departures').first().json;\n"
        "if (!diff.ok) {\n"
        "  return [{ json: { slack_text: ':mag: I-04: first run -- no previous snapshot to diff against yet. Today\\'s snapshot stored; tomorrow starts the real check.',\n"
        "    green: true } }];\n"
        "}\n"
        "const alerts = [];\n"
        "if (!diff.reconciles) alerts.push('lead count does not reconcile');\n"
        "if (dep.deleted_count) alerts.push(dep.deleted_count + ' lead(s) DELETED, not archived');\n"
        "if (!diff.dnc.exact) alerts.push('DNC label set drifted');\n"
        "if (diff.new_person_duplicates.length) alerts.push(diff.new_person_duplicates.length + ' new person(s) duplicate an existing record');\n"
        "if (diff.dnc686_delta) alerts.push('DNC field-686 population moved by ' + (diff.dnc686_delta > 0 ? '+' : '') + diff.dnc686_delta);\n"
        "if (diff.dnc686_delta === null) alerts.push('DNC field-686 delta unmeasurable (a seeded/incomplete snapshot on one side)');\n"
        "const green = alerts.length === 0;\n"
        "let lines;\n"
        "if (green) {\n"
        "  lines = [\n"
        "    ':white_check_mark: I-04 daily diff (' + diff.prev_date + ' -> ' + diff.curr_date + '): no anomalies',\n"
        "    'departures ' + diff.departures_count + ' (' + dep.archived_count + ' archived, ' + dep.deleted_count + ' deleted) · arrivals ' + diff.arrivals_count + ' · reconciles: ' + diff.reconciles,\n"
        "    'DNC label set exact: ' + diff.dnc.exact + ' · new persons ' + diff.new_persons_count + ' (0 duplicates) · 686 delta ' + (diff.dnc686_delta == null ? 'n/a' : diff.dnc686_delta),\n"
        "  ];\n"
        "} else {\n"
        "  lines = [':rotating_light: I-04 daily diff (' + diff.prev_date + ' -> ' + diff.curr_date + '): ' + alerts.join('; ')];\n"
        "  lines.push('departures ' + diff.departures_count + ' (' + dep.archived_count + ' archived, ' + dep.deleted_count + ' deleted), sample: ' + JSON.stringify(diff.departures_sample));\n"
        "  lines.push('arrivals ' + diff.arrivals_count + ', sample: ' + JSON.stringify(diff.arrivals_sample));\n"
        "  if (!diff.dnc.exact) lines.push('DNC unexpected: ' + JSON.stringify(diff.dnc.unexpected) + ' missing: ' + JSON.stringify(diff.dnc.missing));\n"
        "  if (diff.new_person_duplicates.length) lines.push('duplicate new persons: ' + JSON.stringify(diff.new_person_duplicates.slice(0, 10)));\n"
        "  lines.push('(archived departures are expected only if an operation declared them -- cross-check against the day\\'s #niks-channel §9f.2 posts)');\n"
        "}\n"
        "return [{ json: { slack_text: lines.join('\\n'), green, alerts } }];\n"
    )

    if test_webhook:
        # single-tick fire -- exactly what the staged-rollout test needs (fire N times in a row to
        # exercise ~10 pages before ever wiring the recurring live schedule).
        trig = node("Walk Ticker", "n8n-nodes-base.webhook",
                    {"httpMethod": "POST", "path": "i04-walk-tick-test", "responseMode": "onReceived", "options": {}},
                    -2000, tv=1, extra={"webhookId": "i04walkticktest01"})
    else:
        trig = node("Walk Ticker", "n8n-nodes-base.scheduleTrigger",
                    {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, -2000, tv=1.2)
    heartbeat_trig = node("Idle-Guard Trigger", "n8n-nodes-base.scheduleTrigger",
                          {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]}},
                          -2000, y=1000, tv=1.2)

    nodes = [
        trig,
        set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                    ("telemetry_channel", TELEMETRY_CHANNEL, "string"),
                    ("dev_channel_guard", OPS_CHANNEL, "string"),
                    ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                    ("offpeak_start_hour", "2", "string"), ("offpeak_end_hour", "6", "string"),
                    ("reconcile_day_of_week", "0", "string"),  # 0=Sunday -- weekly reconciliation, not nightly
                    ("module", wf_name, "string")], x=-1800),
        dt_get("Load Walk State", "date", "=_state_{{ $now.toFormat('yyyy-MM-dd') }}", -1600),
        code_node("Decide Walk Action", decide_walk_action_js, -1400),
        if_bool("Is Continue Leads?", "={{ $json.action === 'continue_leads' }}", -1200),
        if_bool("Is Continue Persons?", "={{ $json.action === 'continue_persons' }}", -1200, y=460),
        if_bool("Is Compact?", "={{ $json.action === 'compact' }}", -1200, y=620),
        node("Noop", "n8n-nodes-base.noOp", {}, -1000, y=780),

        # -------- continue_leads: one bounded chunk --------
        http_pipedrive_chunk_offset("HTTP Leads Chunk",
            "=https://api.pipedrive.com/v1/leads?limit=%d&start={{ $json.state.leads_next_start }}"
            % LEADS_PAGE_SIZE, -1000, y=100),
        code_node("Reduce Leads Chunk", reduce_leads_chunk_js, -800, y=100),

        # -------- continue_persons: one bounded chunk --------
        http_pipedrive_chunk_cursor("HTTP Persons Chunk",
            "={{ 'https://api.pipedrive.com/api/v2/persons?limit=%d' + "
            "($json.state.persons_cursor ? ('&cursor=' + $json.state.persons_cursor) : '') }}"
            % PERSONS_PAGE_SIZE, -1000, y=460),
        code_node("Reduce Persons Chunk", reduce_persons_chunk_js, -800, y=460),

        # -------- shared: route chunk output rows to staging vs. state save --------
        if_bool("Is State Marker?", "={{ $json.__state_update === true }}", -600, y=280),
        dt_upsert("Save Walk State", {
            "date": "={{ $json.date }}", "captured_at": "={{ $json.captured_at }}",
            "source": "={{ $json.source }}", "counts_json": "={{ $json.counts_json }}",
            "leads_json": "={{ $json.leads_json }}", "persons_json": "={{ $json.persons_json }}",
            "dnc_labelled_json": "={{ $json.dnc_labelled_json }}", "kept_reason": "={{ $json.kept_reason }}",
        }, ["date"], -400, y=220, guard=False),
        dt_upsert("Insert Staging Row", {
            "walk_date": "={{ $json.walk_date }}", "resource": "={{ $json.resource }}",
            "entity_id": "={{ $json.entity_id }}", "data_json": "={{ $json.data_json }}",
        }, ["walk_date", "resource", "entity_id"], -400, y=340, table=STAGING_TABLE, guard=False),

        # -------- circuit breaker (shared by both chunk fetchers) --------
        code_node("Circuit Breaker: Common", circuit_breaker_js, -800, y=640),
        dt_upsert("Save Walk State (Broken)", {
            "date": "={{ $json.date }}", "captured_at": "={{ $json.captured_at }}",
            "source": "={{ $json.source }}", "counts_json": "={{ $json.counts_json }}",
            "leads_json": "={{ $json.leads_json }}", "persons_json": "={{ $json.persons_json }}",
            "dnc_labelled_json": "={{ $json.dnc_labelled_json }}", "kept_reason": "={{ $json.kept_reason }}",
        }, ["date"], -600, y=700, guard=False),
        slack_post("Alert: Walk Circuit Broken",
                   "=:rotating_light: I-04 chunked walk CIRCUIT BROKEN ({{ $('Decide Walk Action').first().json.today }}): "
                   "{{ $json.broken_reason }}. Halted -- cursor is SAVED, not lost, but this will NOT auto-resume "
                   "(by design, per the no-hammer spec). Resume only after confirming n8n/Pipedrive health, by manually "
                   "restoring the state row's status from its saved resume_status field.",
                   -600, y=820),

        # -------- compact: bulk-read the day's staged rows, build the real snapshot --------
        dt_get("Load All Staging Rows", "walk_date", "={{ $('Decide Walk Action').first().json.today }}",
               -1000, y=620, return_all=True, table=STAGING_TABLE),
        code_node("Build Snapshot", compact_snapshot_js, -800, y=620),
        # matches the ORIGINAL script's own semantic exactly (i04_diff.py: "diff the two NEWEST
        # snapshots") -- the most recent PRIOR *real* snapshot, excluding walk-state sentinel rows
        # (kept_reason == 'state') which would otherwise pollute this query.
        node("Get All Snapshots", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get", "dataTableId": I04_TABLE,
            "returnAll": True, "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "date", "condition": "isNotEmpty"}]},
            "options": {}
        }, -600, y=560, tv=1),
        code_node("Pick Previous Snapshot", (
            "const today = $('Build Snapshot').first().json.date;\n"
            "const rows = $input.all().map(i => i.json)\n"
            "  .filter(r => r.date < today && r.kept_reason !== 'state')\n"
            "  .sort((a, b) => b.date.localeCompare(a.date));\n"
            "return [{ json: rows[0] || {} }];\n"  # {} (not null) -- n8n items require json to be an object
        ), -400, y=560),
        dt_upsert("Store Today's Snapshot", {
            "date": "={{ $('Build Snapshot').first().json.date }}",
            "captured_at": "={{ $('Build Snapshot').first().json.captured_at }}",
            "source": "={{ $('Build Snapshot').first().json.source }}",
            "counts_json": "={{ $('Build Snapshot').first().json.counts_json }}",
            "leads_json": "={{ $('Build Snapshot').first().json.leads_json }}",
            "persons_json": "={{ $('Build Snapshot').first().json.persons_json }}",
            "dnc_labelled_json": "={{ $('Build Snapshot').first().json.dnc_labelled_json }}",
            "kept_reason": "daily",
        }, ["date"], -200, y=520),
        dt_delete("Purge Staging Rows", "walk_date", "={{ $('Decide Walk Action').first().json.today }}",
                  0, y=680, table=STAGING_TABLE),
        code_node("Mark Walk Done", mark_walk_done_js, 0, y=820),

        code_node("Diff", diff_js, 0, y=520),
        if_bool("Has Previous Snapshot?", "={{ $('Diff').first().json.ok }}", 200, y=520),
        node("Split Departures", "n8n-nodes-base.splitOut",
             {"fieldToSplitOut": "departures_all", "options": {}}, 400, y=460),
        code_node_per_item("Prep Departure Lookup", classify_departures_js, 600, y=460),
        node("Get Departure Detail", "n8n-nodes-base.httpRequest", {
            "method": "GET", "url": "=https://api.pipedrive.com/v1/leads/{{ $json.lead_id }}",
            "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
            "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 250}}},
        }, 800, y=460, tv=4.2, extra={"credentials": {"httpQueryAuth": PIPEDRIVE_CRED},
                                     "onError": "continueErrorOutput", "retryOnFail": True,
                                     "maxTries": 3, "waitBetweenTries": 2000}),
        code_node_per_item("Departure Detail", departure_detail_js, 1000, y=460),
        code_node("Combine Departures", combine_departures_js, 1200, y=460),
        node("No Previous -- Skip Departures", "n8n-nodes-base.noOp", {}, 400, y=580),
        node("Merge Departure Paths", "n8n-nodes-base.merge",
             {"mode": "append", "numberInputs": 2, "options": {}}, 1400, y=520, tv=3),
        code_node("Combine Report", combine_report_js, 1600, y=520),
        code_node("Mark Posted Today", mark_posted_js, 1800, y=520),
        node("Report Send Guard", "n8n-nodes-base.code", {"jsCode": (
            "const cfg = $('CONFIG').first().json;\n"
            "const ch = cfg.alert_channel;\n"
            "if (String(cfg.MODE) === 'dev' && !JSON.parse(cfg.dev_channel_guard_list).includes(ch)) {\n"
            "  throw new Error('SEND-GUARD: target channel not in dev allow-list: ' + ch);\n"
            "}\n"
            "return $input.all();\n"
        ), "mode": "runOnceForAllItems"}, 2000, y=520, tv=2),
        slack_post("Post Report", "={{ $json.slack_text }}", 2200, y=520),
        code_node("Alert Post Failed", (
            "return [{ json: { alert_failed: true,\n"
            "  note: 'I-04 daily report failed to post -- see this execution for the diff detail.' } }];\n"
        ), 2200, y=680),

        # -------- retention prune (30 daily rolling / weekly kept 6 months) --------
        dt_get("Get All Snapshots For Prune", "kept_reason", "=daily", 1600, y=820, return_all=True),
        code_node("Compute Prune List", (
            "const rows = $input.all().map(i => i.json).sort((a, b) => b.date.localeCompare(a.date));\n"
            "const keepDaily = rows.slice(0, 30);\n"
            "const rest = rows.slice(30);\n"
            "const toDelete = [];\n"
            "const toRetagWeekly = [];\n"
            "const sixMonthsAgo = new Date(Date.now() - 183 * 86400000).toISOString().slice(0, 10);\n"
            "for (const r of rest) {\n"
            "  const d = new Date(r.date + 'T00:00:00Z');\n"
            "  const isSunday = d.getUTCDay() === 0;\n"
            "  if (isSunday && r.date >= sixMonthsAgo) toRetagWeekly.push(r);\n"
            "  else toDelete.push(r);\n"
            "}\n"
            "return [{ json: { total: rows.length, keep_daily: keepDaily.length,\n"
            "  retag_weekly: toRetagWeekly.map(r => r.date), delete: toDelete.map(r => r.date) } }];\n"
        ), 1800, y=820),
        node("Split Delete List", "n8n-nodes-base.splitOut",
             {"fieldToSplitOut": "delete", "options": {}}, 2000, y=780),
        node("Delete Old Snapshot", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "deleteRows", "dataTableId": I04_TABLE,
            "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "={{ $json.delete }}"}]},
            "options": {}
        }, 2200, y=780, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3}),
        node("Split Retag List", "n8n-nodes-base.splitOut",
             {"fieldToSplitOut": "retag_weekly", "options": {}}, 2000, y=900),
        node("Retag Weekly", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "update", "dataTableId": I04_TABLE,
            "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "={{ $json.retag_weekly }}"}]},
            "columns": {"mappingMode": "defineBelow", "value": {"kept_reason": "weekly"}, "matchingColumns": [], "schema": []},
            "options": {}
        }, 2200, y=900, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3}),
        # old walk-state sentinel rows (kept_reason == 'state') accumulate one-per-day otherwise --
        # prune anything older than 3 days, since only today's/yesterday's state row is ever live.
        dt_get("Get All State Rows", "kept_reason", "=state", 1600, y=980, return_all=True),
        code_node("Compute Old State Rows", (
            "const cutoff = new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10);\n"
            "const rows = $input.all().map(i => i.json)\n"
            "  .filter(r => (r.date || '').replace('_state_', '') < cutoff);\n"
            "return [{ json: { stale_dates: rows.map(r => r.date) } }];\n"
        ), 1800, y=980),
        node("Split Old State Rows", "n8n-nodes-base.splitOut",
             {"fieldToSplitOut": "stale_dates", "options": {}}, 2000, y=1020),
        node("Delete Old State Row", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "deleteRows", "dataTableId": I04_TABLE,
            "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "={{ $json.stale_dates }}"}]},
            "options": {}
        }, 2200, y=1020, tv=1, extra={"onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3}),

        # -------- idle self-guard (separate daily trigger, unchanged) --------
        heartbeat_trig,
        code_node("Check Idle", idle_guard_js, -1800, y=1000),
        if_bool("Missed Today?", "={{ $json.missed_today }}", -1600, y=1000),
        slack_post("Idle Alert",
                   "=:rotating_light: I-04 daily diff did not post today (last post: {{ $json.last_posted_date }}). "
                   "The chunked walk may be stuck, circuit-broken, or n8n never fired the ticker -- check executions "
                   "and today's walk-state row (date=_state_<today>) in i04_snapshots.",
                   -1400, y=960),
    ]

    connections = conns([
        ("Walk Ticker", "CONFIG"), ("CONFIG", "Load Walk State"), ("Load Walk State", "Decide Walk Action"),
        ("Decide Walk Action", "Is Continue Leads?"),
        ("HTTP Leads Chunk", "Reduce Leads Chunk"),
        ("HTTP Persons Chunk", "Reduce Persons Chunk"),
        ("Reduce Leads Chunk", "Is State Marker?"), ("Reduce Persons Chunk", "Is State Marker?"),
        ("Circuit Breaker: Common", "Save Walk State (Broken)"),
        ("Circuit Breaker: Common", "Alert: Walk Circuit Broken"),
        ("Load All Staging Rows", "Build Snapshot"),
        ("Build Snapshot", "Get All Snapshots"),
        ("Get All Snapshots", "Pick Previous Snapshot"),
        ("Pick Previous Snapshot", "Store Today's Snapshot"),
        ("Store Today's Snapshot", "Diff"),
        ("Store Today's Snapshot", "Purge Staging Rows"),
        ("Store Today's Snapshot", "Mark Walk Done"),
        ("Mark Walk Done", "Save Walk State"),
        ("Diff", "Has Previous Snapshot?"),
        ("Split Departures", "Prep Departure Lookup"),
        ("Prep Departure Lookup", "Get Departure Detail"),
        ("Get Departure Detail", "Departure Detail"),
        ("Departure Detail", "Combine Departures"),
        ("Combine Departures", "Merge Departure Paths"),
        ("No Previous -- Skip Departures", "Merge Departure Paths"),
        ("Merge Departure Paths", "Combine Report"),
        ("Combine Report", "Mark Posted Today"),
        ("Mark Posted Today", "Report Send Guard"),
        ("Report Send Guard", "Post Report"),
        ("Store Today's Snapshot", "Get All Snapshots For Prune"),
        ("Get All Snapshots For Prune", "Compute Prune List"),
        ("Compute Prune List", "Split Delete List"), ("Split Delete List", "Delete Old Snapshot"),
        ("Compute Prune List", "Split Retag List"), ("Split Retag List", "Retag Weekly"),
        ("Store Today's Snapshot", "Get All State Rows"),
        ("Get All State Rows", "Compute Old State Rows"),
        ("Compute Old State Rows", "Split Old State Rows"), ("Split Old State Rows", "Delete Old State Row"),
        ("Idle-Guard Trigger", "Check Idle"),
        ("Check Idle", "Missed Today?"),
    ])
    connections["Is Continue Leads?"] = {"main": [
        [{"node": "HTTP Leads Chunk", "type": "main", "index": 0}],
        [{"node": "Is Continue Persons?", "type": "main", "index": 0}],
    ]}
    connections["Is Continue Persons?"] = {"main": [
        [{"node": "HTTP Persons Chunk", "type": "main", "index": 0}],
        [{"node": "Is Compact?", "type": "main", "index": 0}],
    ]}
    connections["Is Compact?"] = {"main": [
        [{"node": "Load All Staging Rows", "type": "main", "index": 0}],
        [{"node": "Noop", "type": "main", "index": 0}],
    ]}
    connections["HTTP Leads Chunk"] = {"main": [
        [{"node": "Reduce Leads Chunk", "type": "main", "index": 0}],
        [{"node": "Circuit Breaker: Common", "type": "main", "index": 0}],
    ]}
    connections["HTTP Persons Chunk"] = {"main": [
        [{"node": "Reduce Persons Chunk", "type": "main", "index": 0}],
        [{"node": "Circuit Breaker: Common", "type": "main", "index": 0}],
    ]}
    connections["Is State Marker?"] = {"main": [
        [{"node": "Save Walk State", "type": "main", "index": 0}],
        [{"node": "Insert Staging Row", "type": "main", "index": 0}],
    ]}
    connections["Has Previous Snapshot?"] = {"main": [
        [{"node": "Split Departures", "type": "main", "index": 0}],
        [{"node": "No Previous -- Skip Departures", "type": "main", "index": 0}],
    ]}
    connections["Missed Today?"] = {"main": [
        [{"node": "Idle Alert", "type": "main", "index": 0}],
        [],
    ]}
    connections["Post Report"] = {"main": [
        [], [{"node": "Alert Post Failed", "type": "main", "index": 0}],
    ]}
    return wf(wf_name, nodes, connections)


# ===========================================================================
# dnc_i04_event_receiver -- 2026-08-26 I-04 REDESIGN (Nik): the nightly full walk above is no
# longer the primary detector. This is: a Pipedrive-native webhook (lead + person changes)
# appends one small row per event to i04_log, near-zero load, always on. Payload shape is
# genuinely unverified (registering a real webhook subscription live confirmed the account is on
# webhook format v2.0, not the classic v1 {meta,current,previous,event} shape this project
# assumed -- no real event arrived in a 90s observation window to confirm the exact v2 field
# layout, and forcing a synthetic mutation on a real production lead just to see one payload
# wasn't worth the footprint). Extraction below is DEFENSIVE (tries v2-shaped fields first,
# falls back to v1-shaped fields) and the raw body is stored UNCONDITIONALLY regardless of which
# path matched -- nothing is ever lost to a wrong guess, and the daily summary (far easier to
# iterate on than a live webhook receiver) does the real interpretation once enough real payloads
# have been logged to get the parsing right.
# ===========================================================================
def build_event_receiver(wf_name, test_webhook=False):
    log_event_js = (
        "const body = $json.body || {};\n"
        "const topKeys = Object.keys(body).join(',');\n"
        "const meta = body.meta || {};\n"
        "// v2-shaped fields first (confirmed live: this account's webhooks are format v2.0),\n"
        "// v1-shaped fields as fallback (meta.action/meta.object/event/current/previous).\n"
        "const action = meta.action || (typeof body.event === 'string' ? body.event.split('.')[0] : null) || 'unknown';\n"
        "const objectType = meta.entity || meta.object"
        " || (typeof body.event === 'string' ? body.event.split('.')[1] : null) || 'unknown';\n"
        "const current = body.data !== undefined ? body.data : body.current;\n"
        "const previous = body.previous;\n"
        "const objectId = (current && current.id != null) ? current.id\n"
        "  : (meta.entity_id != null ? meta.entity_id : (meta.id != null ? meta.id\n"
        "  : ((previous && previous.id != null) ? previous.id : 'unknown')));\n"
        "const receivedAt = new Date().toISOString();\n"
        "return [{ json: {\n"
        "  event_id: objectType + ':' + objectId + ':' + receivedAt,\n"
        "  received_at: receivedAt, event_action: String(action), object_type: String(objectType),\n"
        "  object_id: String(objectId), raw_json: JSON.stringify(body), top_level_keys: topKeys,\n"
        "} }];\n"
    )
    if test_webhook:
        path = "{{WEBHOOK_I04_PD_EVENTS}}-test"
    else:
        path = "{{WEBHOOK_I04_PD_EVENTS}}"
    trig = node("PD Webhook", "n8n-nodes-base.webhook",
                {"httpMethod": "POST", "path": path, "responseMode": "onReceived", "options": {}},
                -800, tv=1, extra={"webhookId": "i04pdevents01" if not test_webhook else "i04pdeventstest01"})
    nodes = [
        trig,
        code_node("Log Event", log_event_js, -600),
        if_bool("Is Lead Or Person?", "={{ ['lead','person'].includes($json.object_type) }}", -400),
        dt_upsert("Insert Event Row", {
            "event_id": "={{ $json.event_id }}", "received_at": "={{ $json.received_at }}",
            "event_action": "={{ $json.event_action }}", "object_type": "={{ $json.object_type }}",
            "object_id": "={{ $json.object_id }}", "raw_json": "={{ $json.raw_json }}",
            "top_level_keys": "={{ $json.top_level_keys }}",
        }, ["event_id"], -200, table=EVENT_LOG_TABLE, guard=False),  # fail-open: a logging hiccup
        # must never make Pipedrive think the endpoint is dead (onReceived already ack'd anyway).
        node("Skip (not lead/person)", "n8n-nodes-base.noOp", {}, -200, y=160),
    ]
    connections = conns([
        ("PD Webhook", "Log Event"), ("Log Event", "Is Lead Or Person?"),
    ])
    connections["Is Lead Or Person?"] = {"main": [
        [{"node": "Insert Event Row", "type": "main", "index": 0}],
        [{"node": "Skip (not lead/person)", "type": "main", "index": 0}],
    ]}
    return wf(wf_name, nodes, connections)


# ===========================================================================
# dnc_i04_daily_summary -- reads i04_log since the last run, computes the same invariant
# the old nightly walk did (departures/arrivals/label-mass-changes/DNC-686 movement/declared vs
# undeclared) from the EVENT LOG instead of a full-estate diff. A watermark (last_summary_at, a
# sentinel row in i04_snapshots, kept_reason='event_watermark') tracks how far the previous run
# got so this one only reads the new slice -- same sentinel-row technique as the weekly walk's
# own _state_ rows, same reason (avoid a third table just for one timestamp).
# ===========================================================================
def build_daily_summary(wf_name, test_webhook=False):
    load_watermark_js = (
        "const rows = $input.all().map(i => i.json);\n"
        "let since = null;\n"
        "if (rows.length && rows[0].counts_json) {\n"
        "  try { since = JSON.parse(rows[0].counts_json).last_summary_at || null; } catch (e) { since = null; }\n"
        "}\n"
        "// first-ever run: look back 24h, not the dawn of time.\n"
        "if (!since) since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();\n"
        "return [{ json: { since, now: new Date().toISOString() } }];\n"
    )
    summarize_js = (
        "const wm = $('Load Watermark').first().json;\n"
        "const all = $('Get New Events').all().map(i => i.json);\n"
        "const events = all.filter(e => e.received_at > wm.since && e.received_at <= wm.now);\n"
        "\n"
        "const leadEvents = events.filter(e => e.object_type === 'lead');\n"
        "const personEvents = events.filter(e => e.object_type === 'person');\n"
        "const departures = leadEvents.filter(e => e.event_action === 'delete' || e.event_action === 'deleted');\n"
        "const arrivals = leadEvents.filter(e => e.event_action === 'add' || e.event_action === 'added'"
        " || e.event_action === 'create' || e.event_action === 'created');\n"
        "const leadUpdates = leadEvents.filter(e => e.event_action === 'update' || e.event_action === 'updated' || e.event_action === 'change');\n"
        "\n"
        "// label-mass-change: many DISTINCT leads updated within a short window (same-minute\n"
        "// clustering) -- a real bulk relabel op, not routine one-off edits trickling in.\n"
        "const byMinute = {};\n"
        "for (const e of leadUpdates) {\n"
        "  const minute = (e.received_at || '').slice(0, 16);\n"
        "  (byMinute[minute] = byMinute[minute] || new Set()).add(e.object_id);\n"
        "}\n"
        "const massChangeMinutes = Object.entries(byMinute)\n"
        "  .filter(([, ids]) => ids.size >= 10)\n"
        "  .map(([minute, ids]) => ({ minute, distinct_leads: ids.size }));\n"
        "\n"
        "// NOT COMPUTABLE, not a fake 0 -- if the event log itself never received anything in\n"
        "// this window (e.g. the Pipedrive subscription silently died), that's a DIFFERENT\n"
        "// finding (zero_events) from 'genuinely zero real changes happened'.\n"
        "const zeroEvents = events.length === 0;\n"
        "\n"
        "return [{ json: {\n"
        "  since: wm.since, until: wm.now,\n"
        "  total_events: events.length, zero_events: zeroEvents,\n"
        "  departures_count: departures.length, departures_ids: departures.map(e => e.object_id),\n"
        "  arrivals_count: arrivals.length, arrivals_ids: arrivals.map(e => e.object_id),\n"
        "  lead_update_count: leadUpdates.length, person_event_count: personEvents.length,\n"
        "  mass_change_minutes: massChangeMinutes,\n"
        "} }];\n"
    )
    combine_summary_js = (
        "const s = $('Summarize').first().json;\n"
        "const sub = $('Check Subscriptions').first().json;\n"
        "const alerts = [];\n"
        "if (s.zero_events) alerts.push('ZERO events logged in this window -- the Pipedrive webhook may be silently dead, not \\'nothing happened\\'');\n"
        "if (s.mass_change_minutes.length) alerts.push(s.mass_change_minutes.length + ' minute(s) with a mass label change (>=10 distinct leads in one minute)');\n"
        "if (!sub.leadActive || !sub.personActive) alerts.push('Pipedrive webhook subscription check failed -- lead_active=' + sub.leadActive + ' person_active=' + sub.personActive);\n"
        "const green = alerts.length === 0;\n"
        "let lines;\n"
        "if (green) {\n"
        "  lines = [\n"
        "    ':white_check_mark: I-04 daily summary (' + s.since + ' -> ' + s.until + '): no anomalies',\n"
        "    'departures ' + s.departures_count + ' · arrivals ' + s.arrivals_count + ' · lead updates ' + s.lead_update_count + ' · person events ' + s.person_event_count,\n"
        "  ];\n"
        "} else {\n"
        "  lines = [':rotating_light: I-04 daily summary (' + s.since + ' -> ' + s.until + '): ' + alerts.join('; ')];\n"
        "  lines.push('departures ' + s.departures_count + ' (' + JSON.stringify(s.departures_ids.slice(0, 12)) + ')');\n"
        "  lines.push('arrivals ' + s.arrivals_count + ' (' + JSON.stringify(s.arrivals_ids.slice(0, 12)) + ')');\n"
        "  if (s.mass_change_minutes.length) lines.push('mass changes: ' + JSON.stringify(s.mass_change_minutes));\n"
        "  lines.push('(cross-check departures/mass-changes against #niks-channel\\'s last 24h §9f.2 posts -- declared ops are expected, undeclared ones are not)');\n"
        "}\n"
        "return [{ json: { slack_text: lines.join('\\n'), green } }];\n"
    )
    check_subscriptions_js = (
        # the weekly reconciliation walk catches a dead subscription EVENTUALLY (as a departures/\n"
        # arrivals mismatch); this checks it DIRECTLY every day instead, matching the standing\n"
        # lesson from the gate incidents: liveness checks must check ACTUAL status, not infer it.\n"
        "const subs = ($input.first().json.data) || [];\n"
        "const active = subs.filter(s => s.is_active);\n"
        "const leadActive = active.some(s => (s.event_objects || [s.event_object]).includes('lead'));\n"
        "const personActive = active.some(s => (s.event_objects || [s.event_object]).includes('person'));\n"
        "return [{ json: { leadActive, personActive, total_active: active.length } }];\n"
    )
    if test_webhook:
        trig = node("Daily Summary Trigger", "n8n-nodes-base.webhook",
                    {"httpMethod": "POST", "path": "i04-summary-test", "responseMode": "onReceived", "options": {}},
                    -1600, tv=1, extra={"webhookId": "i04summarytest01"})
    else:
        trig = node("Daily Summary Trigger", "n8n-nodes-base.scheduleTrigger",
                    {"rule": {"interval": [{"field": "cronExpression", "expression": "30 5 * * *"}]}}, -1600, tv=1.2)
    # 2026-08-27 fix (auditor's "must scream within the hour" spec + kill-test): was 8am once/day,
    # a coarse date-only comparison that could take up to 24h to notice a miss -- today's exec
    # 34078 crash went completely unreported all morning because of it. Now ticks every 15 min so
    # a missed 05:30 UTC slot is caught inside its own 1-hour grace window, same day.
    heartbeat_trig = node("Idle-Guard Trigger", "n8n-nodes-base.scheduleTrigger",
                          {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 * * * *"}]}},
                          -1600, y=700, tv=1.2)
    # slot-aware, real-timestamp based (not "did the date string change"): expected slot is 05:30
    # UTC daily. Re-arms automatically the next day just by comparing against 'today' -- no sticky
    # flag to reset, no manual intervention needed after it fires once. Grace is 45min, not a flat
    # 60 -- with a 15min tick, a 60min grace can miss the "must scream within the hour" bar by up
    # to 15min (grace expires at :60, next tick lands at :75); 45min guarantees the scream lands on
    # the :60 tick at the latest. Verified in zz_killtest_idle_guard.js.
    idle_guard_js = (
        "const sd = $getWorkflowStaticData('global');\n"
        "const now = new Date();\n"
        "const today = now.toISOString().slice(0, 10);\n"
        "const slot = new Date(today + 'T05:30:00.000Z');\n"
        "const graceMs = 45 * 60 * 1000;\n"
        "const pastGrace = now.getTime() > (slot.getTime() + graceMs);\n"
        "const postedToday = sd.lastPostedDate === today;\n"
        "const missed = pastGrace && !postedToday;\n"
        "return [{ json: { missed_today: missed, last_posted_date: sd.lastPostedDate || null,\n"
        "  last_success_at: sd.lastSuccessAt || null, today, checked_at: now.toISOString() } }];\n"
    )
    mark_posted_js = (
        "const sd = $getWorkflowStaticData('global');\n"
        "sd.lastPostedDate = new Date().toISOString().slice(0, 10);\n"
        "sd.lastSuccessAt = new Date().toISOString();\n"
        "return $input.all();\n"
    )

    nodes = [
        trig,
        set_config([("MODE", "dev", "string"), ("alert_channel", OPS_CHANNEL, "string"),
                    ("dev_channel_guard_list", json.dumps([OPS_CHANNEL, TELEMETRY_CHANNEL]), "string"),
                    ("module", wf_name, "string")], x=-1400),
        # 2026-08-27 fix (exec 34078, "Node 'Load Watermark' hasn't been executed"): i04_snapshots
        # does not exist yet (verified live -- "Could not find the data table: 'i04_snapshots'",
        # not a mode:name resolution flake), so this GET always fails. Without onError set, n8n
        # never invokes the downstream code node at all -- not "ran with 0 items", genuinely never
        # scheduled -- so Summarize's unconditional $('Load Watermark') read throws. Fix: wire
        # BOTH this node's outputs (regular AND error) into Load Watermark below, so it always
        # runs regardless of whether the table read succeeds, is empty (first-ever run), or the
        # whole table is missing. Load Watermark's own JS already handles all three shapes
        # gracefully (falls back to a 24h lookback whenever counts_json is absent) -- this was
        # always a wiring gap, not a logic gap.
        node("Load Watermark Row", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get", "dataTableId": I04_TABLE,
            "returnAll": False, "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "date", "condition": "eq", "keyValue": "=_event_watermark"}]},
            "options": {}
        }, -1200, tv=1, extra={"onError": "continueErrorOutput"}),
        code_node("Load Watermark", load_watermark_js, -1000),
        node("Get New Events", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get", "dataTableId": EVENT_LOG_TABLE,
            "returnAll": True, "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "event_id", "condition": "isNotEmpty"}]},
            "options": {}
        }, -1000, y=180, tv=1),
        node("Check Subscriptions HTTP", "n8n-nodes-base.httpRequest", {
            "method": "GET", "url": "=https://api.pipedrive.com/v1/webhooks",
            "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth", "options": {},
        }, -1000, y=340, tv=4.2, extra={"credentials": {"httpQueryAuth": PIPEDRIVE_CRED},
                                        "onError": "continueErrorOutput", "retryOnFail": True, "maxTries": 3}),
        code_node("Check Subscriptions", check_subscriptions_js, -800, y=340),
        code_node("Summarize", summarize_js, -600, y=60),
        code_node("Combine Summary", combine_summary_js, -400, y=60),
        code_node("Mark Posted Today", mark_posted_js, -200, y=60),
        node("Send Guard", "n8n-nodes-base.code", {"jsCode": (
            "const cfg = $('CONFIG').first().json;\n"
            "const ch = cfg.alert_channel;\n"
            "if (String(cfg.MODE) === 'dev' && !JSON.parse(cfg.dev_channel_guard_list).includes(ch)) {\n"
            "  throw new Error('SEND-GUARD: target channel not in dev allow-list: ' + ch);\n"
            "}\n"
            "return $input.all();\n"
        ), "mode": "runOnceForAllItems"}, 0, y=60, tv=2),
        slack_post("Post Summary", "={{ $json.slack_text }}", 200, y=60),
        code_node("Alert Post Failed", (
            "return [{ json: { alert_failed: true,\n"
            "  note: 'I-04 daily summary failed to post -- see this execution for detail.' } }];\n"
        ), 200, y=220),
        # guard=False (fail-open): i04_snapshots not existing must not turn an otherwise-successful
        # daily post (already sent by "Post Summary" upstream) into a red execution -- same 08-27
        # lesson as Load Watermark Row above. Losing the watermark just means tomorrow's run falls
        # back to a 24h lookback again -- self-healing, not silently wrong.
        dt_upsert("Save Watermark", {
            "date": "=_event_watermark", "captured_at": "={{ $('Load Watermark').first().json.now }}",
            "source": "event_watermark", "kept_reason": "event_watermark",
            "counts_json": "={{ JSON.stringify({ last_summary_at: $('Load Watermark').first().json.now }) }}",
            "leads_json": "", "persons_json": "", "dnc_labelled_json": "",
        }, ["date"], 400, y=60, guard=False),
        # prune the event log -- keep 35 days; the weekly reconciliation walk is the long-memory
        # ground truth, the event log only needs to cover "since the last summary" plus slack.
        node("Get Old Events", "n8n-nodes-base.dataTable", {
            "resource": "row", "operation": "get", "dataTableId": EVENT_LOG_TABLE,
            "returnAll": True, "matchType": "allConditions",
            "filters": {"conditions": [{"keyName": "event_id", "condition": "isNotEmpty"}]},
            "options": {}
        }, -1000, y=500, tv=1),
        code_node("Compute Old Events", (
            "const cutoff = new Date(Date.now() - 35 * 86400000).toISOString();\n"
            "const rows = $input.all().map(i => i.json).filter(r => r.received_at < cutoff);\n"
            "return [{ json: { stale_ids: rows.map(r => r.event_id) } }];\n"
        ), -800, y=500),
        node("Split Old Events", "n8n-nodes-base.splitOut",
             {"fieldToSplitOut": "stale_ids", "options": {}}, -600, y=540),
        dt_delete("Delete Old Event", "event_id", "={{ $json.stale_ids }}", -400, y=540, table=EVENT_LOG_TABLE),
        heartbeat_trig,
        code_node("Check Idle", idle_guard_js, -1400, y=700),
        if_bool("Missed Today?", "={{ $json.missed_today }}", -1200, y=700),
        slack_post("Idle Alert",
                   "=:rotating_light: I-04 daily summary did not post today (last post: {{ $json.last_posted_date }}). "
                   "Check whether the trigger fired and whether i04_log is receiving rows at all.",
                   -1000, y=660),
    ]
    connections = conns([
        ("Daily Summary Trigger", "CONFIG"),
        ("CONFIG", "Load Watermark Row"), ("CONFIG", "Get New Events"), ("CONFIG", "Check Subscriptions HTTP"),
        ("CONFIG", "Get Old Events"),
        ("Load Watermark Row", "Load Watermark"),
        ("Check Subscriptions HTTP", "Check Subscriptions"),
        ("Load Watermark", "Summarize"), ("Get New Events", "Summarize"),
        ("Summarize", "Combine Summary"), ("Check Subscriptions", "Combine Summary"),
        ("Combine Summary", "Mark Posted Today"), ("Mark Posted Today", "Send Guard"),
        ("Send Guard", "Post Summary"), ("Post Summary", "Save Watermark"),
        ("Get Old Events", "Compute Old Events"), ("Compute Old Events", "Split Old Events"),
        ("Split Old Events", "Delete Old Event"),
        ("Idle-Guard Trigger", "Check Idle"), ("Check Idle", "Missed Today?"),
    ])
    connections["Post Summary"] = {"main": [
        [{"node": "Save Watermark", "type": "main", "index": 0}],
        [{"node": "Alert Post Failed", "type": "main", "index": 0}],
    ]}
    connections["Missed Today?"] = {"main": [
        [{"node": "Idle Alert", "type": "main", "index": 0}], [],
    ]}
    # both outputs of the watermark read -- success (incl. empty-on-first-run) AND error (incl.
    # "table does not exist") -- must reach Load Watermark. See the node-build comment above.
    connections["Load Watermark Row"] = {"main": [
        [{"node": "Load Watermark", "type": "main", "index": 0}],
        [{"node": "Load Watermark", "type": "main", "index": 0}],
    ]}
    return wf(wf_name, nodes, connections)


if __name__ == "__main__":
    # renamed from dnc_i04_daily_diff -- 2026-08-26 redesign demotes this to the WEEKLY
    # reconciliation safety net (never deployed live under the old name, safe to rename outright).
    write(os.path.join(HERE, "DEV__dnc_i04_weekly_reconciliation.json"), build("DEV__dnc_i04_weekly_reconciliation"))
    write(os.path.join(HERE, "dnc_i04_weekly_reconciliation.json"), build("dnc_i04_weekly_reconciliation"))
    write(os.path.join(HERE, "DEV__dnc_i04_event_receiver.json"), build_event_receiver("DEV__dnc_i04_event_receiver"))
    write(os.path.join(HERE, "dnc_i04_event_receiver.json"), build_event_receiver("dnc_i04_event_receiver"))
    write(os.path.join(HERE, "DEV__dnc_i04_daily_summary.json"), build_daily_summary("DEV__dnc_i04_daily_summary"))
    write(os.path.join(HERE, "dnc_i04_daily_summary.json"), build_daily_summary("dnc_i04_daily_summary"))
    print("OK")
