# -*- coding: utf-8 -*-
"""Builds `dnc_intent_vs_reality` — the Class 1 effect verification.

Asserts the CONSEQUENCE of a registry row in the systems of record, and compares it against that
row's own `projections_state` claim. It never reads a switch: a switch tells you what was
configured; only the provider tells you what is true.

Read-only by construction - every provider call is a GET.

Chunked on purpose. A ~100-item burst has OOM'd this instance before and left a workflow
deactivated, so the caller drives it with {offset, limit} and the workflow caps its own batch.

Both HTTP nodes use fullResponse, so "we could not look" (5xx, auth, rate limit) stays
distinguishable from "we looked and it is not there". Collapsing those two is the failure this
workflow exists to detect; it must not commit it.

Usage: python build_intent_vs_reality.py <out.json>
"""
import json, sys

OUT = sys.argv[1]

CONFIG = {
    "module": "dnc_intent_vs_reality",
    "ledger_table_id": "UOgKwlGsL28lX61O",
    "pd_api": "https://api.pipedrive.com",
    "sl_api": "https://server.smartlead.ai/api/v1",
    # Read verbatim out of dnc_projections_sweep's own CONFIG so the assertion cannot drift from
    # the projection it is checking.
    "pd_dnc_field": "9c018b7406ebc481b9c108a487f76c4d09f91c9b",
    "pd_dnc_active": 686,
    "max_rows_per_call": 50,
}

SLICE_JS = r"""
// Positive shape check first. An unreadable registry read is NOT "no rows": reporting a clean
// estate off a failed read is the exact class this workflow exists to catch, so it must not
// commit it itself.
const rows = $input.all().map(i => i.json).filter(r => r && typeof r.identity_key === 'string');
if (!rows.length) {
  throw new Error('dnc_intent_vs_reality: registry read returned no usable rows (expected objects '
                + 'with identity_key). Refusing to report a clean estate.');
}
const body = ($('Webhook').first().json.body) || {};
const cfg = $('CONFIG').first().json;
const cap = Number(cfg.max_rows_per_call) || 50;
const active = rows.filter(r => String(r.status || '') === 'active');
const offset = Math.max(0, Number(body.offset) || 0);
const limit = Math.min(cap, Math.max(1, Number(body.limit) || cap));
// SAMPLE MODE. The registry is far larger than a same-day full walk can honestly cover
// (25,653 active rows = ~51k provider GETs), and a burst that size is what OOM'd this instance
// before. `{mode:"sample", target:N}` takes a SYSTEMATIC sample instead: every `stride`-th row
// across the whole table, so the sample spans the entire insertion history rather than the newest
// or oldest page. Sequential mode is still there for a full walk when there is time for one.
const sampled = String(body.mode || '') === 'sample';
const target = Math.max(1, Number(body.target) || 1000);
const stride = sampled ? Math.max(1, Math.floor(active.length / target)) : 1;
const slice = [];
if (sampled) {
  for (let k = 0; k < limit; k++) {
    const idx = (offset + k) * stride;
    if (idx >= active.length) break;
    slice.push(active[idx]);
  }
} else {
  for (const r of active.slice(offset, offset + limit)) slice.push(r);
}
if (!slice.length) {
  return [{ json: { __empty: true, __total_rows: rows.length, __total_active: active.length,
                    __offset: offset, __limit: limit } }];
}
return slice.map((r, i) => {
  let claim = {};
  try { claim = r.projections_state ? JSON.parse(r.projections_state) : {}; }
  catch (e) { claim = { __unparseable: true }; }
  return { json: {
    __i: i, __total_rows: rows.length, __total_active: active.length,
    __offset: offset, __limit: limit, __batch: slice.length,
    __sampled: sampled, __stride: stride, __target: target,
    identity_key: r.identity_key,
    email_lc: r.email_lc || null,
    linkedin_url_norm: r.linkedin_url_norm || null,
    pipedrive_person_id: r.pipedrive_person_id != null ? r.pipedrive_person_id : null,
    entry_type: r.entry_type || null, reason: r.reason || null, added_at: r.added_at || null,
    source: r.source || null,
    claim_pipedrive: claim.pipedrive == null ? null : String(claim.pipedrive),
    claim_smartlead: claim.smartlead == null ? null : String(claim.smartlead),
    claim_raw: r.projections_state || null
  } };
});
"""

COMPARE_JS = r"""
const cfg = $('CONFIG').first().json;
const src = $('Slice Batch').all().map(i => i.json);
if (src.length === 1 && src[0].__empty === true) return [{ json: { ...src[0] } }];

const pd = $('PD Person Get').all().map(i => i.json);
const sl = $('SL Lead Lookup').all().map(i => i.json);
// Index pairing: an n8n HTTP node emits one item per input item, in order - the same assumption
// WF-2S's claim-after-success relies on. Assert it rather than trust it.
if (pd.length !== src.length || sl.length !== src.length) {
  throw new Error('dnc_intent_vs_reality: response/row count mismatch (rows=' + src.length
                + ' pd=' + pd.length + ' sl=' + sl.length + '). Refusing to report a tally.');
}

const FIELD = cfg.pd_dnc_field;
const ACTIVE = cfg.pd_dnc_active;
const parts = (r) => {
  // fullResponse shape; an errored item may arrive without it
  if (r && typeof r === 'object' && ('statusCode' in r || 'body' in r)) {
    return { code: Number(r.statusCode), body: r.body };
  }
  return { code: NaN, body: r };
};

function pdVerdict(row, resp) {
  if (row.pipedrive_person_id == null) return { v: 'unknown', why: 'no_person_id_on_row' };
  const { code, body } = parts(resp);
  if (!Number.isFinite(code)) return { v: 'unknown', why: 'person_read_failed' };
  if (code === 404) return { v: 'unknown', why: 'person_not_found_404' };
  if (code !== 200) return { v: 'unknown', why: 'person_http_' + code };
  const d = body && body.data;
  if (!d || typeof d !== 'object') return { v: 'unknown', why: 'unexpected_person_shape' };
  const cf = d.custom_fields || {};
  const raw = cf[FIELD];
  const val = (raw && typeof raw === 'object') ? (raw.id != null ? raw.id : raw.value) : raw;
  if (val == null || val === '') return { v: 'false', why: 'dnc_field_empty' };
  return String(val) === String(ACTIVE)
    ? { v: 'true', why: 'dnc_field_set' }
    : { v: 'false', why: 'dnc_field_other_value' };
}

function slVerdict(row, resp) {
  if (!row.email_lc) return { v: 'unknown', why: 'no_email_on_row' };
  const { code, body } = parts(resp);
  if (!Number.isFinite(code)) return { v: 'unknown', why: 'lead_read_failed' };
  // Not being in Smartlead at all means nothing there can send to them - that is the desired end
  // state, not an unknown.
  if (code === 404) return { v: 'true', why: 'not_in_smartlead' };
  if (code !== 200) return { v: 'unknown', why: 'lead_http_' + code };
  if (!body || typeof body !== 'object' || !body.id) return { v: 'true', why: 'not_in_smartlead' };
  return body.is_unsubscribed === true
    ? { v: 'true', why: 'unsubscribed' }
    : { v: 'false', why: 'CONTACTABLE_in_smartlead' };
}

const bucket = (claim, verdict) => {
  if (verdict === 'unknown') return 'uncheckable';
  const done = claim === 'done';
  const pending = claim == null || claim === 'pending' || String(claim).indexOf('skipped') === 0;
  if (done && verdict === 'true') return 'claims_done_and_is';
  if (done && verdict === 'false') return 'claims_done_but_ISNT';
  if (pending && verdict === 'true') return 'claims_pending_but_already_done';
  if (pending && verdict === 'false') return 'claims_pending_and_isnt';
  return 'uncheckable';
};

const out = [];
for (let i = 0; i < src.length; i++) {
  const row = src[i];
  const p = pdVerdict(row, pd[i]);
  const s = slVerdict(row, sl[i]);
  out.push({ json: { ...row,
    pd_verdict: p.v, pd_why: p.why, pd_bucket: bucket(row.claim_pipedrive, p.v),
    sl_verdict: s.v, sl_why: s.why, sl_bucket: bucket(row.claim_smartlead, s.v) } });
}
return out;
"""

TALLY_JS = r"""
const items = $input.all().map(i => i.json);
if (items.length === 1 && items[0].__empty === true) {
  return [{ json: { exhausted: true, checked: 0, offset: items[0].__offset,
                    total_active: items[0].__total_active, total_rows: items[0].__total_rows } }];
}
const B = ['claims_done_and_is', 'claims_done_but_ISNT', 'claims_pending_but_already_done',
           'claims_pending_and_isnt', 'uncheckable'];
const zero = () => B.reduce((a, k) => (a[k] = 0, a), {});
const pd = zero(), sl = zero(), why_pd = {}, why_sl = {};
const liars = [], contactable = [];
const by_reason = {}, ident = { has_pid: 0, has_email: 0, has_both: 0, has_neither: 0 };
for (const it of items) {
  const rk = String(it.reason || it.entry_type || 'unknown');
  by_reason[rk] = (by_reason[rk] || 0) + 1;
  const p = it.pipedrive_person_id != null, e = !!it.email_lc;
  if (p && e) ident.has_both++; else if (p) ident.has_pid++; else if (e) ident.has_email++;
  else ident.has_neither++;
  pd[it.pd_bucket] = (pd[it.pd_bucket] || 0) + 1;
  sl[it.sl_bucket] = (sl[it.sl_bucket] || 0) + 1;
  why_pd[it.pd_why] = (why_pd[it.pd_why] || 0) + 1;
  why_sl[it.sl_why] = (why_sl[it.sl_why] || 0) + 1;
  if (it.pd_bucket === 'claims_done_but_ISNT' || it.sl_bucket === 'claims_done_but_ISNT') {
    liars.push({ identity_key: it.identity_key, pd: it.pd_why, sl: it.sl_why });
  }
  if (it.sl_verdict === 'false') {
    contactable.push({ identity_key: it.identity_key, email: it.email_lc,
                       entry_type: it.entry_type, reason: it.reason, added_at: it.added_at });
  }
}
const f = items[0];
return [{ json: {
  offset: f.__offset, limit: f.__limit, checked: items.length,
  total_rows: f.__total_rows, total_active: f.__total_active,
  next_offset: f.__offset + items.length,
  exhausted: f.__sampled === true
    ? ((f.__offset + items.length) * (f.__stride || 1)) >= f.__total_active
    : (f.__offset + items.length) >= f.__total_active,
  sampled: f.__sampled === true, stride: f.__stride, target: f.__target,
  pipedrive: pd, smartlead: sl, pd_reasons: why_pd, sl_reasons: why_sl,
  by_reason: by_reason, identity_coverage: ident,
  liars_count: liars.length, liars: liars.slice(0, 25),
  still_contactable_count: contactable.length,
  still_contactable_in_smartlead: contactable.slice(0, 25)
} }];
"""

def code(name, js, x, y, nid):
    return {"parameters": {"jsCode": js, "mode": "runOnceForAllItems"},
            "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [x, y], "id": nid, "name": name}

HTTP_OPTS = {"batching": {"batch": {"batchSize": 1, "batchInterval": 150}},
             "response": {"response": {"fullResponse": True, "neverError": True}}}
SL_OPTS = {"batching": {"batch": {"batchSize": 1, "batchInterval": 400}},
           "response": {"response": {"fullResponse": True, "neverError": True}}}

nodes = [
    {"parameters": {"httpMethod": "POST", "path": "{{WEBHOOK_DNC_INTENT_VS_REALITY}}",
                    "responseMode": "responseNode", "options": {}},
     "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
     "id": "ivr-webhook-0001", "name": "Webhook",
     "webhookId": "b7f1c3d2e4a54c0f9b8a6d2e1f0c3a45"},
    {"parameters": {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2), "options": {}},
     "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [200, 0],
     "id": "ivr-config-0001", "name": "CONFIG"},
    {"parameters": {"resource": "row", "operation": "get",
                    "dataTableId": {"__rl": True, "mode": "id", "value": CONFIG["ledger_table_id"]},
                    # "allFilters" is rejected ("unexpected match type"); anyCondition is the
                    # value the live gate uses and the only one proven against this node version.
                    "matchType": "anyCondition",
                    "filters": {"conditions": [{"keyName": "status", "condition": "eq",
                                                "keyValue": "=active"}]},
                    # returnAll is REQUIRED: the node silently defaults to limit 50, which would
                    # have capped the whole registry at 50 rows and reported it as the total.
                    "returnAll": True,
                    "options": {}},
     "type": "n8n-nodes-base.dataTable", "typeVersion": 1, "position": [400, 0],
     "id": "ivr-registry-0001", "name": "Get Active Registry Rows"},
    code("Slice Batch", SLICE_JS, 600, 0, "ivr-slice-0001"),
    # B12: after this node $json is the Pipedrive response, so the email for the Smartlead lookup
    # is read from the node that OWNS it, by name.
    {"parameters": {"url": "={{ $('CONFIG').first().json.pd_api }}/api/v2/persons/{{ $json.pipedrive_person_id || 0 }}",
                    "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
                    "options": HTTP_OPTS},
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [800, 0],
     "id": "ivr-pdget-0001", "name": "PD Person Get",
     "credentials": {"httpQueryAuth": {"id": "DEFM2qykN8B2lqzw",
                                       "name": "Pipedrive API (DNC projections)"}},
     "onError": "continueRegularOutput", "alwaysOutputData": True},
    {"parameters": {"url": "={{ $('CONFIG').first().json.sl_api }}/leads?email={{ encodeURIComponent($('Slice Batch').item.json.email_lc || 'no-email-on-row@example.invalid') }}",
                    "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth",
                    "options": SL_OPTS},
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1000, 0],
     "id": "ivr-slget-0001", "name": "SL Lead Lookup",
     "credentials": {"httpQueryAuth": {"id": "3o6NEljtQ1moYYGp",
                                       "name": "Smartlead API (DNC projections)"}},
     "onError": "continueRegularOutput", "alwaysOutputData": True},
    code("Compare", COMPARE_JS, 1200, 0, "ivr-compare-0001"),
    code("Tally", TALLY_JS, 1400, 0, "ivr-tally-0001"),
    {"parameters": {"respondWith": "json", "responseBody": "={{ $json }}", "options": {}},
     "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [1600, 0],
     "id": "ivr-respond-0001", "name": "Respond"},
]

connections = {
    "Webhook": {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]},
    "CONFIG": {"main": [[{"node": "Get Active Registry Rows", "type": "main", "index": 0}]]},
    "Get Active Registry Rows": {"main": [[{"node": "Slice Batch", "type": "main", "index": 0}]]},
    "Slice Batch": {"main": [[{"node": "PD Person Get", "type": "main", "index": 0}]]},
    "PD Person Get": {"main": [[{"node": "SL Lead Lookup", "type": "main", "index": 0}]]},
    "SL Lead Lookup": {"main": [[{"node": "Compare", "type": "main", "index": 0}]]},
    "Compare": {"main": [[{"node": "Tally", "type": "main", "index": 0}]]},
    "Tally": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
}

wf = {"name": "dnc_intent_vs_reality", "nodes": nodes, "connections": connections,
      "settings": {"executionOrder": "v1", "errorWorkflow": "BbrXPABgOaaTJjD6",
                   "callerPolicy": "workflowsFromSameOwner", "timezone": "Asia/Jerusalem"}}

json.dump(wf, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("built %d nodes -> %s" % (len(nodes), OUT))
