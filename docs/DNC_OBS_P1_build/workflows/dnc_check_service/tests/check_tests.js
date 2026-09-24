'use strict';
// Tests for dnc_check_service (Build 6). Run: node workflows/dnc_check_service/tests/check_tests.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const R = path.join(__dirname, '..', '..', '..');
const { normalizeIdentityV1 } = require(path.join(R, 'subworkflows', 'lib', 'normalize_v1.js'));

let pass = 0, fail = 0;
function t(n, fn) { try { fn(); pass++; console.log('  ok  - ' + n); }
  catch (e) { fail++; console.log('  FAIL- ' + n + '\n        ' + e.message); } }

const ALLOWED = 'C0BFE6KAN8J';

// Mirrors the "Parse Input" Code node.
function parseInput(evt) {
  const text = String(evt.text || '');
  const channel = evt.channel || '';
  if (channel && channel !== ALLOWED) return null;             // ignored
  const cleaned = text.replace(/<@[^>]+>/g, ' ').trim();
  const url = cleaned.match(/https?:\/\/[^\s|>]*linkedin\.com[^\s|>]*/i);
  const email = cleaned.match(/[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/);
  return { linkedin_url: url ? url[0] : null, email: email ? email[0] : null };
}
// Mirrors "Format Reply".
function formatReply(r) {
  if (r.result === 'on_dnc') return ':no_entry: *ON DNC* — `' + r.entry_type + '` since ' +
    String(r.since).slice(0, 10) + (r.expires_at ? ' (expires ' + String(r.expires_at).slice(0, 10) + ')' : ' (permanent)');
  if (r.result === 'clean_with_history') return ':white_check_mark: clean now — *was* on DNC (' +
    r.was_type + ') until ' + String(r.until || '').slice(0, 10);
  if (r.result === 'clean') return ':white_check_mark: clean — not on the DNC ledger';
  return ':information_source: Usage: mention me with a LinkedIn /in/ URL or an email';
}

console.log('parse @mention text:');
t('extracts LinkedIn URL from slack-wrapped mention', () => {
  const p = parseInput({ channel: ALLOWED, text: '<@U123> please check <https://www.linkedin.com/in/pii-31379a93|Mario>' });
  assert.equal(p.linkedin_url, 'https://www.linkedin.com/in/pii-31379a93');
  assert.equal(normalizeIdentityV1(p).identity_key, 'mario-rossi');
});
t('extracts email', () => {
  const p = parseInput({ channel: ALLOWED, text: '<@U1> is pii-59e752f7@example.invalid on DNC?' });
  assert.equal(p.email, 'pii-59e752f7@example.invalid');
});
t('mention in another channel is ignored', () => {
  assert.equal(parseInput({ channel: 'C_OTHER', text: '<@U1> x' }), null);
});
t('garbage input -> no identifier (=> usage hint downstream)', () => {
  const p = parseInput({ channel: ALLOWED, text: '<@U1> hello there' });
  assert.equal(p.linkedin_url, null); assert.equal(p.email, null);
  assert.equal(normalizeIdentityV1(p).identity_key, null);
});

console.log('format reply (spec cases):');
t('active_entry_found', () => {
  const m = formatReply({ result: 'on_dnc', entry_type: 'explicit_opt_out', since: '2026-03-01T00:00:00Z', expires_at: null, source: 'smartlead_category' });
  assert.ok(m.includes('ON DNC') && m.includes('explicit_opt_out') && m.includes('permanent'));
});
t('expired_entry_reported_as_clean_with_history', () => {
  const m = formatReply({ result: 'clean_with_history', was_type: 'replied', until: '2026-01-01T00:00:00Z' });
  assert.ok(m.includes('was') && m.includes('until 2026-01-01'));
});
t('clean_person', () => assert.ok(formatReply({ result: 'clean' }).includes('clean')));
t('garbage_input_gets_usage_hint', () => assert.ok(formatReply({ result: 'usage_hint' }).includes('Usage')));

console.log('drift (workflow JSON):');
const wf = JSON.parse(fs.readFileSync(path.join(R, 'workflows', 'dnc_check_service', 'dnc_check_service.json'), 'utf8'));
t('trigger is slackTrigger app_mention on C0BFE6KAN8J', () => {
  const tg = wf.nodes.find((n) => n.type === 'n8n-nodes-base.slackTrigger');
  assert.deepEqual(tg.parameters.trigger, ['app_mention']);
  assert.equal(tg.parameters.channelId.value, 'C0BFE6KAN8J');
});
t('read-only: no Data Table write nodes, no non-Slack HTTP', () => {
  wf.nodes.forEach((n) => {
    if (n.type === 'n8n-nodes-base.dataTable')
      assert.ok(['get', 'rowExists', 'rowNotExists'].includes(n.parameters.operation) || n.parameters.resource !== 'row');
    assert.notEqual(n.type, 'n8n-nodes-base.httpRequest');
  });
});
t('Send Guard present before Slack Reply', () => {
  assert.ok(wf.nodes.some((n) => n.name === 'Send Guard'));
  assert.ok(JSON.stringify(wf.connections['Send Guard']).includes('Slack Reply'));
});

console.log('\n%d passed, %d failed', pass, fail);
process.exit(fail ? 1 : 0);
