'use strict';
// Fixture-replay tests for the WF-1 reply tee (Build 3). Mirrors the workflow's data path:
// map -> normalize_v1 -> two eq Gets (linkedin/email) -> merge_v1. No n8n runtime.
// Run: node workflows/heyreach_reply_to_dnc_ledger/tests/tee_tests.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const R = path.join(__dirname, '..', '..', '..');
const { normalizeIdentityV1 } = require(path.join(R, 'subworkflows', 'lib', 'normalize_v1.js'));
const { dncMergeDecisionV1 } = require(path.join(R, 'subworkflows', 'lib', 'merge_v1.js'));
const fx = (p) => JSON.parse(fs.readFileSync(path.join(R, 'fixtures', p), 'utf8'));

const NOW = '2026-07-23T00:00:00.000Z';
const CFG = { ttlMonths: 6, now: NOW };
let pass = 0, fail = 0;
function t(n, fn) { try { fn(); pass++; console.log('  ok  - ' + n); }
  catch (e) { fail++; console.log('  FAIL- ' + n + '\n        ' + e.message); } }

// The tee's Map node contract:
function mapToUpsert(ev) {
  if (!ev.reply_event_id) throw new Error('reply_event_id required');
  if (!ev.linkedin_url && !ev.email) throw new Error('need linkedin_url or email');
  return { linkedin_url: ev.linkedin_url || null, email: ev.email || null,
    full_name: ev.full_name || null, pipedrive_person_id: ev.pipedrive_person_id != null ? ev.pipedrive_person_id : null,
    entry_type: 'replied', source: 'heyreach_reply',
    reply_category: ev.reply_category != null ? ev.reply_category : null,
    correlation_id: ev.correlation_id || null,
    idempotency_key: 'heyreach:' + ev.reply_event_id + ':dnc' };
}
// The two eq Gets, mirrored against an in-memory ledger:
function getsFor(norm, ledger) {
  const li = norm.linkedin_url_norm ? ledger.filter(r => r.linkedin_url_norm === norm.linkedin_url_norm) : [];
  const em = norm.email_lc ? ledger.filter(r => r.email_lc === norm.email_lc) : [];
  return { byLi: li, byEm: em };
}
function run(ev, ledger) {
  const inp = mapToUpsert(ev);
  const norm = normalizeIdentityV1(inp);
  const g = getsFor(norm, ledger);
  return dncMergeDecisionV1({ norm, incoming: inp, config: CFG, matchedByLinkedin: g.byLi, matchedByEmail: g.byEm });
}
function applied(rec) { // shape an inserted/updated row as it would land in the ledger
  return Object.assign({}, rec);
}

console.log('heyreach reply tee:');

t('reply_with_linkedin_only_creates_entry', () => {
  const d = run(fx('heyreach/reply_received_linkedin_only.json'), []);
  assert.equal(d.action, 'insert');
  assert.equal(d.record.identity_key, 'mario-rossi');
  assert.equal(d.record.entry_type, 'replied');
  assert.equal(d.record.source, 'heyreach_reply');
  assert.equal(d.record.expires_at, '2027-01-23T00:00:00.000Z');
});

t('reply_with_both_ids_matching_same_row_upserts', () => {
  const seedRow = applied(run(fx('heyreach/reply_received_linkedin_only.json'), []).record);
  const d = run(fx('heyreach/reply_received_both_ids.json'), [seedRow]);
  assert.equal(d.action, 'update');              // adds email + reply_category to same identity
  assert.equal(d.record.identity_key, 'mario-rossi');
  assert.equal(d.record.email_lc, 'pii-b2774afe@example.invalid');
});

t('conflicting_identifiers_alert_no_write', () => {
  const marioRow = applied(run(fx('heyreach/reply_received_linkedin_only.json'), []).record);
  const seeds = fx('ledger_seeds.json').rows.filter(r => r.identity_key === 'pii-5fb991e9@example.invalid');
  const d = run(fx('heyreach/reply_received_conflict.json'), [marioRow].concat(seeds));
  assert.equal(d.action, 'conflict');
});

t('duplicate_webhook_replay_is_ignored', () => {
  const seedRow = applied(run(fx('heyreach/reply_received_linkedin_only.json'), []).record); // added_at=NOW
  const d = run(fx('heyreach/reply_received_replay.json'), [seedRow]);
  assert.equal(d.action, 'noop');
});

t('existing_explicit_opt_out_not_downgraded', () => {
  const optout = { id: 9, identity_key: 'mario-rossi', linkedin_url_norm: 'https://www.linkedin.com/in/pii-31379a93',
    entry_type: 'explicit_opt_out', source: 'smartlead_category', status: 'active',
    added_at: '2026-02-01T00:00:00.000Z', expires_at: null, norm_v: 'v1' };
  const d = run(fx('heyreach/reply_received_linkedin_only.json'), [optout]);
  assert.equal(d.record.entry_type, 'explicit_opt_out');
  assert.equal(d.record.expires_at, null);
});

console.log('\n%d passed, %d failed', pass, fail);
process.exit(fail ? 1 : 0);
