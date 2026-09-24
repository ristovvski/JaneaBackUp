'use strict';
// Static tests for dnc_expiry_job (Build 4). Run: node workflows/dnc_expiry_job/tests/expiry_tests.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const R = path.join(__dirname, '..', '..', '..');
const { planExpiryV1, isoWeekKey } = require(path.join(R, 'subworkflows', 'lib', 'expire_v1.js'));

let pass = 0, fail = 0;
function t(n, fn) { try { fn(); pass++; console.log('  ok  - ' + n); }
  catch (e) { fail++; console.log('  FAIL- ' + n + '\n        ' + e.message); } }

const NOW = '2026-07-23T06:00:00.000Z';
const row = (o) => Object.assign({ status: 'active', norm_v: 'v1' }, o);

console.log('dnc_expiry_job:');

t('due_row_expires', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'emma', added_at: '2026-01-24T00:00:00.000Z', entry_type: 'replied', expires_at: '2026-07-22T00:00:00.000Z' })
  ]});
  assert.equal(p.expired_count, 1);
  assert.deepEqual(p.to_expire[0], { identity_key: 'emma', added_at: '2026-01-24T00:00:00.000Z' });
});

t('not_yet_due_row_untouched', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'future', added_at: NOW, entry_type: 'replied', expires_at: '2027-01-01T00:00:00.000Z' })
  ]});
  assert.equal(p.expired_count, 0);
});

t('expiry_review_pending row is skipped, not expired, and counted separately', () => {
  // STAGE 1 addition. Precedent: the 142 reply_dnc Amsterdam-2025 rows were frozen this way,
  // then Nik explicitly unfroze them (HANDOFF_dnc_registry_2026-08-06.md) -- so they seed with
  // this flag FALSE and expire normally. This test proves the guard itself, for the NEXT batch
  // that actually needs freezing.
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'frozen', added_at: '2025-07-01T00:00:00.000Z', entry_type: 'negative_reply',
          expires_at: '2026-01-01T00:00:00.000Z', expiry_review_pending: true })
  ]});
  assert.equal(p.expired_count, 0);
  assert.equal(p.to_expire.length, 0);
  assert.equal(p.skipped_review_pending, 1);
});

t('expiry_review_pending=false (or absent) behaves exactly as before -- e.g. an unfrozen Amsterdam-2025 row', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'unfrozen', added_at: '2025-07-01T00:00:00.000Z', entry_type: 'negative_reply',
          expires_at: '2026-01-01T00:00:00.000Z', expiry_review_pending: false }),
    row({ identity_key: 'no-flag-at-all', added_at: '2025-07-01T00:00:00.000Z', entry_type: 'negative_reply',
          expires_at: '2026-01-01T00:00:00.000Z' })   // field entirely absent -- old-row shape
  ]});
  assert.equal(p.expired_count, 2);
  assert.equal(p.skipped_review_pending, 0);
});

t('permanent_explicit_opt_out_untouchable', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    // even with a (bad) past expires_at, explicit_opt_out is never auto-expired
    row({ identity_key: 'oscar', added_at: '2026-01-01T00:00:00.000Z', entry_type: 'explicit_opt_out', expires_at: '2026-01-02T00:00:00.000Z' })
  ]});
  assert.equal(p.expired_count, 0);
});

t('permanent_null_expiry_untouched', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'perm', added_at: NOW, entry_type: 'employee_connection', expires_at: null })
  ]});
  assert.equal(p.expired_count, 0);
});

t('rerun_same_day_is_noop (no active due rows left)', () => {
  // after a run, due rows are status=expired -> not in the active set fed to plan
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'emma', status: 'expired', added_at: '2026-01-24T00:00:00.000Z', entry_type: 'replied', expires_at: '2026-07-22T00:00:00.000Z' })
  ]});
  assert.equal(p.expired_count, 0);
});

t('dedup: extra active rows for one identity are targeted, primary kept', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'dup', added_at: '2026-01-01T00:00:00.000Z', entry_type: 'replied', expires_at: '2027-01-01T00:00:00.000Z' }),
    row({ identity_key: 'dup', added_at: '2026-02-01T00:00:00.000Z', entry_type: 'explicit_opt_out', expires_at: null })
  ]});
  // strongest = explicit_opt_out (2026-02-01) kept; the replied row removed as dup
  assert.equal(p.dedup_count, 1);
  assert.equal(p.to_dedup[0].identity_key, 'dup');
  assert.equal(p.to_dedup[0].keep_added_at, '2026-02-01T00:00:00.000Z');
});

t('dedup: identical added_at is skipped as ambiguous (not mis-targeted)', () => {
  const p = planExpiryV1({ now: NOW, rows: [
    row({ identity_key: 'z', added_at: NOW, entry_type: 'replied', expires_at: '2027-01-01T00:00:00.000Z' }),
    row({ identity_key: 'z', added_at: NOW, entry_type: 'replied', expires_at: '2027-01-01T00:00:00.000Z' })
  ]});
  assert.equal(p.dedup_count, 0);
  assert.equal(p.skipped_ambiguous, 1);
});

t('is_digest_day true only on configured dow', () => {
  // 2026-07-23 is a Thursday (dow 4)
  assert.equal(planExpiryV1({ now: NOW, rows: [], digest_dow: 4 }).is_digest_day, true);
  assert.equal(planExpiryV1({ now: NOW, rows: [], digest_dow: 1 }).is_digest_day, false);
});

t('isoWeekKey format', () => assert.ok(/^\d{4}-W\d{2}$/.test(isoWeekKey(NOW))));

// drift: JSON Plan node embeds expire_v1 verbatim, uses only eq/allConditions
t('dnc_expiry_job embeds expire_v1 verbatim + eq-only', () => {
  const src = fs.readFileSync(path.join(R, 'subworkflows', 'lib', 'expire_v1.js'), 'utf8');
  const block = src.match(/\/\/\s*>>> expire_v1 >>>\n([\s\S]*?)\n\/\/\s*<<< expire_v1 <<</)[1];
  const wf = JSON.parse(fs.readFileSync(path.join(R, 'workflows', 'dnc_expiry_job', 'dnc_expiry_job.json'), 'utf8'));
  const code = wf.nodes.filter(n => n.type === 'n8n-nodes-base.code').map(n => n.parameters.jsCode).join('\n');
  assert.ok(code.includes(block), 'Plan node missing expire_v1 block');
  (JSON.stringify(wf).match(/"condition":\s*"([^"]+)"/g) || [])
    .forEach(c => assert.ok(c.includes('"eq"'), 'non-eq operator: ' + c));
});

console.log('\n%d passed, %d failed', pass, fail);
process.exit(fail ? 1 : 0);
