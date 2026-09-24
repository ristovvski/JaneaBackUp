'use strict';
// Static + fixture tests for smartlead_observability_readonly (Build 5, R1+R4).
// Run: node workflows/smartlead_observability_readonly/tests/obs_tests.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const R = path.join(__dirname, '..', '..', '..');
const { parseLeadsStatisticsV1, evaluateR1R4V1, obsIsDeduped } =
  require(path.join(R, 'subworkflows', 'lib', 'obs_v1.js'));
const fx = (p) => JSON.parse(fs.readFileSync(path.join(R, 'fixtures', p), 'utf8'));

let pass = 0, fail = 0, deferred = 0;
function t(n, fn) { try { fn(); pass++; console.log('  ok  - ' + n); }
  catch (e) { fail++; console.log('  FAIL- ' + n + '\n        ' + e.message); } }
function def(n, why) { deferred++; console.log('  DEFER- ' + n + '  (' + why + ')'); }

const NOW = '2026-07-23T10:00:00.000Z';
const SINCE = '2026-07-23T08:00:00.000Z';
const FWD = { interested: true, not_interested: true, information_request: true };
const CFG = (o) => Object.assign({ campaign_id: '512995', r1_stall_hours: 6, r4_delta_threshold: 25 }, o || {});

console.log('parse leads-statistics:');
t('counts replies + categorizations after watermark', () => {
  const m = parseLeadsStatisticsV1(fx('smartlead/leads_statistics_page.json'), SINCE, FWD);
  assert.equal(m.replies, 3);       // leads 1,2,3 replied after 08:00
  assert.equal(m.categorized, 1);   // lead 1 categorized after 08:00 (lead 4's cat is before)
  assert.equal(m.forwardable_new, 1);
});

console.log('R1 (categories stalled):');
t('stalled_categories_fire_R1 once stall persists', () => {
  const m = parseLeadsStatisticsV1(fx('smartlead/leads_statistics_stalled.json'), SINCE, FWD);
  assert.equal(m.categorized, 0);
  // stall started 7h ago -> exceeds 6h threshold -> fires
  const ev = evaluateR1R4V1({ metrics: m, config: CFG(), now: NOW, r1_since: '2026-07-23T03:00:00.000Z' });
  assert.ok(ev.alerts.some((a) => a.rule === 'R1'));
});
t('R1 does NOT fire before stall threshold', () => {
  const m = parseLeadsStatisticsV1(fx('smartlead/leads_statistics_stalled.json'), SINCE, FWD);
  const ev = evaluateR1R4V1({ metrics: m, config: CFG(), now: NOW, r1_since: '2026-07-23T09:00:00.000Z' });
  assert.ok(!ev.alerts.some((a) => a.rule === 'R1'));   // only 1h elapsed
  assert.equal(ev.r1_since_next, '2026-07-23T09:00:00.000Z'); // clock kept
});
t('R1 clears when categorization resumes (no alert, clock reset)', () => {
  const m = parseLeadsStatisticsV1(fx('smartlead/leads_statistics_page.json'), SINCE, FWD); // categorized=1
  const ev = evaluateR1R4V1({ metrics: m, config: CFG(), now: NOW, r1_since: '2026-07-23T01:00:00.000Z' });
  assert.ok(!ev.alerts.some((a) => a.rule === 'R1'));
  assert.equal(ev.r1_since_next, null);
});

console.log('R4 (pipeline delta):');
t('unbalanced replies vs categories fires R4', () => {
  const m = { replies: 40, categorized: 3, forwardable_new: 3, max_event_time: NOW };
  const ev = evaluateR1R4V1({ metrics: m, config: CFG({ r4_delta_threshold: 25 }), now: NOW, r1_since: null });
  assert.ok(ev.alerts.some((a) => a.rule === 'R4' && a.delta === 37));
});
t('forwarded_reply_matches_no_alert (balanced pipeline)', () => {
  const m = { replies: 5, categorized: 5, forwardable_new: 4, max_event_time: NOW };
  const ev = evaluateR1R4V1({ metrics: m, config: CFG(), now: NOW, r1_since: null });
  assert.equal(ev.alerts.length, 0);
});

console.log('dedupe:');
t('alert_dedupe_suppresses_repeat (active window)', () => {
  const row = { state_key: 'alert_dedupe:R1:512995', expires_at: '2026-07-23T13:00:00.000Z' };
  assert.equal(obsIsDeduped(row, NOW), true);    // expires 13:00 > now 10:00 -> suppressed
});
t('dedupe expired -> fires again', () => {
  const row = { state_key: 'alert_dedupe:R1:512995', expires_at: '2026-07-23T09:00:00.000Z' };
  assert.equal(obsIsDeduped(row, NOW), false);
});
t('no dedupe row -> fires', () => assert.equal(obsIsDeduped(null, NOW), false));

console.log('read-only + backoff + drift (workflow JSON):');
const wf = JSON.parse(fs.readFileSync(path.join(R, 'workflows', 'smartlead_observability_readonly',
  'smartlead_observability_readonly.json'), 'utf8'));
t('smartlead_429_backs_off (retryOnFail on the HTTP node)', () => {
  const http = wf.nodes.find((n) => n.type === 'n8n-nodes-base.httpRequest');
  assert.equal(http.parameters.method, 'GET');
  assert.equal(http.retryOnFail, true);
  assert.ok(http.maxTries >= 3);
});
t('ZERO writes to Smartlead (only GET + obs_state + slack)', () => {
  wf.nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest')
    .forEach((n) => assert.equal(n.parameters.method, 'GET', 'non-GET Smartlead call!'));
  // data table writes must target obs_state only, never a Smartlead endpoint
  wf.nodes.filter((n) => n.type === 'n8n-nodes-base.dataTable' && ['insert','update','upsert'].includes(n.parameters.operation))
    .forEach((n) => assert.equal(n.parameters.dataTableId.value, 'obs_state'));
});
t('Evaluate node embeds obs_v1 verbatim', () => {
  const block = fs.readFileSync(path.join(R, 'subworkflows', 'lib', 'obs_v1.js'), 'utf8')
    .match(/\/\/\s*>>> obs_v1 >>>\n([\s\S]*?)\n\/\/\s*<<< obs_v1 <<</)[1];
  const code = wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code').map((n) => n.parameters.jsCode).join('\n');
  assert.ok(code.includes(block));
});

console.log('\nDEFERRED (need per-lead message-history endpoint, undocumented 2026-07-23):');
def('unmatched_interested_reply_fires_R2', 'R2 needs reply content + per-reply category');
def('wrong_person_lands_in_digest_only (R3)', 'R3 needs per-reply category content');

console.log('\n%d passed, %d failed, %d deferred', pass, fail, deferred);
process.exit(fail ? 1 : 0);
