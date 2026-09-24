#!/usr/bin/env node
'use strict';
/**
 * WF-2 static contract tests. Executes the REAL code stored in the built workflow and evaluates
 * selected n8n expressions against controlled fixtures. No network, no n8n, no Pipedrive/Smartlead.
 * Usage: node wf2_static_contract_tests.js "WF-2 Smartlead Receiver - built.json"
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');

const wfPath = process.argv[2] || path.join(__dirname, 'WF-2 Smartlead Receiver - built.json');
const workflow = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
const nodes = new Map(workflow.nodes.map((n) => [n.name, n]));
const C = workflow.connections;

function getNode(name) {
  const n = nodes.get(name);
  assert(n, `Node not found: ${name}`);
  return n;
}
function lookupFactory(outputs) {
  return function $(name) {
    if (!Object.prototype.hasOwnProperty.call(outputs, name)) throw new Error(`Mock output missing: ${name}`);
    // n8n exposes .item, .first() and .all(); the stub only had .item, so any node using
    // .first() silently fell into its own catch and behaved as if the node were absent.
    const it = { json: outputs[name] };
    return { item: it, first: () => it, all: () => [it] };
  };
}
function runCode(name, { input = {}, outputs = {}, staticData = null } = {}) {
  const codeStr = getNode(name).parameters.jsCode;
  const ctx = {
    $json: input, $: lookupFactory(outputs), console, require,
    $getWorkflowStaticData: () => { if (!staticData) throw new Error('no staticData'); return staticData; },
  };
  const out = vm.runInNewContext(`(function(){\n${codeStr}\n})()`, ctx, { filename: `${name}.js` });
  return JSON.parse(JSON.stringify(out));  // cross-realm: bring vm values into this realm for strict asserts
}
function exprSource(raw) {
  assert.equal(typeof raw, 'string');
  const t = raw.trim();
  assert(t.startsWith('={{') && t.endsWith('}}'), `not an expression: ${t.slice(0, 60)}`);
  return t.slice(3, -2).trim();
}
function evalExpr(raw, { input = {}, outputs = {} } = {}) {
  return vm.runInNewContext(`(${exprSource(raw)})`, { $json: input, $: lookupFactory(outputs), console });
}
const CFG = JSON.parse(getNode('CONFIG').parameters.jsonOutput);
// The review address is pinned to production by default. A supervised live window redirects it so
// the B25 proof lands somewhere observable, and must DECLARE that via WF2_EXPECT_REVIEW - the same
// pattern as WF2_EXPECT_MODE. Redirecting where human-review replies go is not something a passing
// suite should ever permit silently.
const EXPECT_REVIEW = process.env.WF2_EXPECT_REVIEW || 'melisa@janeasystems.com';
const F = CFG.fields;

let passed = 0; const failures = [];
function test(name, fn) {
  try { fn(); passed += 1; console.log(`PASS  ${name}`); }
  catch (e) { failures.push({ name, e }); console.error(`FAIL  ${name}`); console.error(e.stack || e); }
}

// ---------------------------------------------------------------- fixtures
function payload(over = {}) {
  return Object.assign({
    event_type: 'EMAIL_REPLIED', campaign_id: 3565502,
    campaign_name: '[Sales Sprint] Sales Sprint 2026 - London - Valids',
    lead_id: 777, to_email: 'pii-59e752f7@example.invalid ', to_name: 'Person-fbbb498b', from_email: 'pii-0637c702@example.invalid',
    timestamp: '2026-07-28T10:00:00Z', sequence_number: 1,
    lead_data: { company_name: 'Acme Inc', website: 'https://acme.com', linkedin_profile: 'https://linkedin.com/in/pii-f5c4ebe4',
                 location: 'London', job_title: 'CTO' },
    subject: 'Re: quick question', reply_body: 'Sounds interesting, can we meet next week?',
  }, over);
}
function norm(over = {}) {
  // model the REAL input: Normalize sits after CONFIG, so $json is CONFIG's output and the
  // payload can only come from $('Webhook'). Feeding { body } as $json (as this harness used to)
  // encoded the wrong assumption and hid B11 - an empty payload on every event.
  const out = runCode('Normalize', { input: CFG,
                                     outputs: { Webhook: { body: payload(over) }, CONFIG: CFG } });
  assert(Array.isArray(out) && out.length === 1);
  return out[0].json;
}
const NBSP = ' ', NNBSP = ' ', FIGSP = ' ';

// ================================================================ Normalize / canon
test('N1 nbsp (U+00A0) in campaign name is canonicalized to a plain space', () => {
  const n = norm({ campaign_name: `[Sales${NBSP}Sprint] Sales Sprint 2026` });
  assert.equal(n.campaign_name, '[Sales Sprint] Sales Sprint 2026');
  assert.equal(n.hypothesis, 'Sales Sprint');
});
test('N2 narrow-nbsp (U+202F) and figure-space (U+2007) canonicalized too', () => {
  assert.equal(norm({ campaign_name: `[Sales${NNBSP}Sprint] x` }).hypothesis, 'Sales Sprint');
  assert.equal(norm({ campaign_name: `[Sales${FIGSP}Sprint] x` }).hypothesis, 'Sales Sprint');
});
test('N3 runs of whitespace collapse; raw is preserved for forensics', () => {
  const n = norm({ campaign_name: '[Sales   Sprint]    Sales   Sprint  2026 ' });
  assert.equal(n.campaign_name, '[Sales Sprint] Sales Sprint 2026');
  assert.equal(n.campaign_name_raw, '[Sales   Sprint]    Sales   Sprint  2026 ');
});
test('N4 en-dash is NOT whitespace and survives canonicalization', () => {
  const n = norm({ campaign_name: '[Sales Sprint] Sales Sprint 2026 – London – Valids' });
  assert(n.campaign_name.includes('–'), n.campaign_name);
});
test('N5 email is lower-cased and trimmed', () => {
  assert.equal(norm().lead.email, 'pii-59e752f7@example.invalid');
});
test('N6 company is whitespace-canonicalized', () => {
  assert.equal(norm({ lead_data: { company_name: 'Acme   Inc ' } }).lead.company, 'Acme Inc');
});
test('N7 event discriminator: "First email sent" -> SENT', () => {
  assert.equal(norm({ event_type: 'First email sent' }).event, 'SENT');
  assert.equal(norm({ event_type: 'EMAIL_SENT' }).event, 'SENT');
});
test('N8 EMAIL_REPLIED -> REPLIED', () => assert.equal(norm({ event_type: 'EMAIL_REPLIED' }).event, 'REPLIED'));
test('N9 bounce/unsub discriminated', () => {
  assert.equal(norm({ event_type: 'EMAIL_BOUNCED' }).event, 'BOUNCED');
  assert.equal(norm({ event_type: 'LEAD_UNSUBSCRIBED' }).event, 'UNSUB');
});
test('N10 LEAD_CATEGORY_UPDATED (Make trigger) -> CATEGORY_UPDATED, never a branch event', () => {
  const n = norm({ event_type: 'LEAD_CATEGORY_UPDATED' });
  assert.equal(n.event, 'CATEGORY_UPDATED');
  assert(!['SENT', 'REPLIED', 'BOUNCED', 'UNSUB'].includes(n.event));
});
test('N11 unknown event -> UNKNOWN (routes to ops warn)', () => {
  assert.equal(norm({ event_type: 'SOMETHING_NEW' }).event, 'UNKNOWN');
});
test('N12 every payload field optional: empty body does not throw', () => {
  const out = runCode('Normalize', { input: CFG, outputs: { Webhook: { body: {} }, CONFIG: CFG } });
  const n = out[0].json;
  assert.equal(n.event, 'UNKNOWN');
  assert.equal(n.lead.email, '');
  assert.equal(n.campaign_name, '');
});
test('N13 reply subject/body/received_at mapped defensively across aliases', () => {
  const a = norm({ subject: 'S1', reply_body: 'B1' });
  assert.equal(a.reply.subject, 'S1'); assert.equal(a.reply.body, 'B1');
  const b = norm({ subject: undefined, reply_body: undefined, email_subject: 'S2', body: 'B2' });
  assert.equal(b.reply.subject, 'S2'); assert.equal(b.reply.body, 'B2');
});
test('N14 sender_inbox comes from from_email or email_account', () => {
  assert.equal(norm({ from_email: 'A@B.co' }).sender_inbox, 'a@b.co');
  assert.equal(norm({ from_email: undefined, email_account: 'X@Y.co' }).sender_inbox, 'x@y.co');
});

// ================================================================ marker parser
test('M1 single-bracket sprint -> hypothesis, no event name', () => {
  const n = norm({ campaign_name: '[Sales Sprint] Sales Sprint 2026 - London - Valids' });
  assert.equal(n.hypothesis, 'Sales Sprint'); assert.equal(n.event_name, null);
});
test('M2 two-bracket -> hypothesis + verbatim event name', () => {
  const n = norm({ campaign_name: '[Events Visiting] [Ai4 2026] - Mario' });
  assert.equal(n.hypothesis, 'Events Visiting'); assert.equal(n.event_name, 'Ai4 2026');
});
test('M3 marker case drift is canon-insensitive', () => {
  assert.equal(norm({ campaign_name: '[events visiting] [X 2026]' }).hypothesis, 'Events Visiting');
  assert.equal(norm({ campaign_name: '[TRIGGER-BASED CAMPAIGN] y' }).hypothesis, 'Trigger-based Campaign');
});
test('M4 unknown marker -> marker_unknown set, hypothesis NOT written', () => {
  const n = norm({ campaign_name: '[Totally New Thing] X' });
  assert.equal(n.hypothesis, null); assert.equal(n.marker_unknown, 'Totally New Thing');
});
test('M5 nurture detected via marker', () => {
  const n = norm({ campaign_name: '[Lead Nurturing] Toby' });
  assert.equal(n.is_nurture, true); assert.equal(n.hypothesis, null);
});
test('M6 nurture detected via campaign NAME (Make parity, case-insensitive)', () => {
  assert.equal(norm({ campaign_name: 'Lead nurturing - Rune' }).is_nurture, true);
  assert.equal(norm({ campaign_name: 'LEAD NURTURING x' }).is_nurture, true);
});
test('M7 event name longer than 60 chars is rejected', () => {
  const n = norm({ campaign_name: '[Events Visiting] [' + 'Z'.repeat(61) + ']' });
  assert.equal(n.event_name, null);
});
test('M8 event name containing a nested bracket is rejected', () => {
  const n = norm({ campaign_name: '[Events Visiting] [Ai4 [2026]' });
  assert.equal(n.event_name, null);
});
test('M9 no bracket at all -> fully inert marker fields', () => {
  const n = norm({ campaign_name: 'Ai4 2026 - Mario - LinkedIn' });
  assert.equal(n.hypothesis, null); assert.equal(n.event_name, null);
  assert.equal(n.marker_unknown, null); assert.equal(n.is_nurture, false);
});

// ================================================================ Dedupe
function dedupe(n, staticData) {
  return runCode('Dedupe', { input: n, outputs: { CONFIG: CFG, Normalize: n }, staticData })[0].json;
}
test('D1 dedupe key is event|campaign_id|sl_lead_id|timestamp', () => {
  const n = norm();
  const r = dedupe(n, {});
  assert.equal(r.__dedupe_key, `REPLIED|3565502|777|2026-07-28T10:00:00Z`);
});
test('D2 first delivery not duplicate, second is', () => {
  const n = norm(); const sd = {};
  assert.equal(dedupe(n, sd).__duplicate, false);
  assert.equal(dedupe(n, sd).__duplicate, true);
});
test('D3 age rotation drops entries older than dedupe_max_age_sec', () => {
  const n = norm();
  const old = Math.floor(Date.now() / 1000) - (CFG.dedupe_max_age_sec + 60);
  const sd = { wf2_seen: { 'stale|key|x|y': old } };
  dedupe(n, sd);
  assert(!Object.prototype.hasOwnProperty.call(sd.wf2_seen, 'stale|key|x|y'), 'stale key must be rotated out');
});
test('D4 __first_sent memo is true once, false afterwards (SENT defense)', () => {
  const n = norm({ event_type: 'First email sent' }); const sd = {};
  assert.equal(dedupe(n, sd).__first_sent, true);
  const n2 = norm({ event_type: 'First email sent', timestamp: '2026-07-28T11:00:00Z' });
  assert.equal(dedupe(n2, sd).__first_sent, false);
});

// ================================================================ union labels
function bodyLabels(extra = {}) {
  const n = norm();
  const input = Object.assign({ __lead_id: 'L1', __lead_labels: [], __is_dnc: false }, extra);
  return runCode('Body Lead Labels Union', { input, outputs: { CONFIG: CFG, Normalize: n } })[0].json;
}
test('U1 union adds cold+connected+responded to an empty label set', () => {
  const r = bodyLabels();
  assert.deepEqual(r.__body.label_ids, [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded]);
});
test("U2 union PRESERVES a manual label (Silva) - the fix for Make's absolute PATCH", () => {
  const manual = 'dfbabc50-ea13-11ef-82c9-bb70b5d42474'; // NOT INTERESTED
  const r = bodyLabels({ __lead_labels: [manual] });
  assert(r.__body.label_ids.includes(manual), 'manual label must survive');
  assert.equal(r.__body.label_ids.length, 4);
});
test('U3 union never removes and is idempotent (no change -> __skip)', () => {
  const all = [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];
  const r = bodyLabels({ __lead_labels: all });
  assert.equal(r.__skip, true);
  assert.deepEqual(r.__body.label_ids, all);
});
test('U4 DNC path adds the DO NOT CONTACT label on top of the union', () => {
  const r = bodyLabels({ __dnc_label: true });
  assert(r.__body.label_ids.includes(CFG.labels.dnc));
});

// ================================================================ alert formats
function alertText(over, ctx) {
  const n = norm(over);
  return evalExpr(getNode('Reply Alert').parameters.text, { input: ctx, outputs: { CONFIG: CFG, Normalize: n } });
}
test('A1 normal reply alert is the WF-1 one-liner + email marker', () => {
  const t = alertText({}, { __lead_id: 'L9', __person_id: 5 });
  assert(t.startsWith('\u{1F4AC} '), t);
  assert(t.includes('Person-fbbb498b (CTO @ Acme Inc)'), t);
  assert(t.includes('[Sales Sprint] Sales Sprint 2026 - London - Valids'), t);
  assert(t.includes('via pii-0637c702@example.invalid'), t);
  assert(t.includes(`${CFG.pipedrive_base}/leads/inbox/L9|Open lead`), t);
  assert(t.includes('✉️ pii-59e752f7@example.invalid'), t);
});
test('A2 no-lead variant links the PERSON instead', () => {
  const t = alertText({}, { __lead_id: null, __person_id: 4242 });
  assert(t.includes('no lead'), t);
  assert(t.includes(`${CFG.pipedrive_base}/person/4242|Open person`), t);
});
test('A3 nurture alert carries the nurture suffix and no Pipedrive link', () => {
  const n = norm({ campaign_name: '[Lead Nurturing] Toby' });
  const t = evalExpr(getNode('Nurture Alert').parameters.text, { input: {}, outputs: { CONFIG: CFG, Normalize: n } });
  assert(t.endsWith('· nurture'), t);
  assert(!t.includes('/leads/inbox/'), t);
});
test('A4 user-originated strings are Slack-escaped', () => {
  const t = alertText({ to_name: 'A & B <script>', lead_data: { company_name: 'X > Y' } },
                      { __lead_id: 'L1', __person_id: 1 });
  assert(t.includes('&amp;') && t.includes('&lt;') && t.includes('&gt;'), t);
  assert(!/<script>/.test(t), t);
});
test('A5 every Slack node text is an evaluated expression (F12.1)', () => {
  const slacks = workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.slack');
  assert(slacks.length >= 7, `expected the full Slack catalog, got ${slacks.length}`);
  for (const s of slacks) assert(String(s.parameters.text).startsWith('='), `${s.name} not '='-prefixed`);
});
test('A7 every Slack node posts under the WF-2 app, never the HeyReach one', () => {
  // item E. Gate-proven: this credential posts as app_id A0BLETEHYBF ("Smarlead"), not the
  // HeyReach app A0BFX7C664S. Slack nodes are continueRegularOutput, so a wrong/broken credential
  // would SILENTLY swallow ops warnings rather than fail loudly - hence an explicit assertion.
  const slacks = workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.slack');
  assert(slacks.length >= 9, `expected the full Slack catalog, got ${slacks.length}`);
  for (const s of slacks) {
    assert.equal((s.credentials || {}).slackApi?.id, 'F9CCCbTx8KB5b2OO', `${s.name} credential`);
    assert.notEqual((s.credentials || {}).slackApi?.id, 'Udq1K604RpJqg1cR',
      `${s.name} still on the HeyReach identity`);
  }
});
test('A6 no Slack node carries a literal channel id (all read CONFIG)', () => {
  for (const s of workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.slack')) {
    const v = s.parameters.channelId.value;
    assert(String(v).startsWith('={{'), `${s.name}: ${v}`);
    assert(!/C0[0-9A-Z]{6,}/.test(v), `${s.name} has a literal channel id`);
  }
});

// ================================================================ first-reply gate
function gate(labels, over = {}) {
  const cfg = JSON.parse(JSON.stringify(CFG));
  Object.assign(cfg.flags, over);
  return runCode('First Reply Gate', { input: { __lead_labels: labels }, outputs: { CONFIG: cfg, Normalize: norm() } })[0].json;
}
test('G1 first reply (no responded label) -> alert', () => {
  const r = gate([CFG.labels.cold]);
  assert.equal(r.__should_alert, true); assert.equal(r.__alert_reason, 'first_reply');
});
test('G2 repeat reply (responded present) -> NO alert', () => {
  const r = gate([CFG.labels.cold, CFG.labels.responded]);
  assert.equal(r.__should_alert, false); assert.equal(r.__alert_reason, 'repeat_reply');
});
test('G3 labels unreadable -> alert anyway (fail-open)', () => {
  const r = gate(null);
  assert.equal(r.__should_alert, true); assert.equal(r.__alert_reason, 'fail_open');
});
test('G4 alert_every_reply=true overrides the gate', () => {
  const r = gate([CFG.labels.responded], { alert_every_reply: true });
  assert.equal(r.__should_alert, true); assert.equal(r.__alert_reason, 'alert_every_reply');
});

// ================================================================ classification
function classify(rawText, cfgOver = {}) {
  const cfg = JSON.parse(JSON.stringify(CFG));
  Object.assign(cfg, cfgOver);
  const input = { content: [{ text: rawText }] };
  return runCode('Classify Parse', { input, outputs: { CONFIG: cfg, Normalize: norm() } })[0].json;
}
const MAP = { 'Interested': 1, 'Meeting Request': 2, 'Not Interested': 3, 'Do Not Contact': 4, 'Out Of Office': 5 };
test('L1 valid JSON with known category and sufficient confidence -> ok', () => {
  const r = classify('{"category":"Meeting Request","confidence":0.9,"is_dnc":false,"one_line_summary":"wants a call"}',
                     { category_map: MAP });
  assert.equal(r.__classify_ok, true); assert.equal(r.__category, 'Meeting Request');
  assert.equal(r.__category_id, 2); assert.equal(r.__summary, 'wants a call');
});
test('L2 invalid JSON -> Uncategorized', () => {
  const r = classify('sorry, I cannot do that', { category_map: MAP });
  assert.equal(r.__classify_ok, false); assert.equal(r.__category, 'Uncategorized');
});
test('L3 category outside the vocabulary -> Uncategorized', () => {
  const r = classify('{"category":"Elvis","confidence":0.99}', { category_map: MAP });
  assert.equal(r.__classify_ok, false);
});
test('L4 confidence below min_confidence -> Uncategorized', () => {
  const r = classify('{"category":"Interested","confidence":0.1}', { category_map: MAP });
  assert.equal(r.__classify_ok, false);
});
test('L5 is_dnc propagates; Do Not Contact category implies DNC', () => {
  assert.equal(classify('{"category":"Interested","confidence":0.9,"is_dnc":true}', { category_map: MAP }).__is_dnc, true);
  assert.equal(classify('{"category":"Do Not Contact","confidence":0.9}', { category_map: MAP }).__is_dnc, true);
});
test('L6 forwardable gate follows CONFIG.forwardable_categories', () => {
  assert.equal(classify('{"category":"Meeting Request","confidence":0.9}', { category_map: MAP }).__forwardable, true);
  assert.equal(classify('{"category":"Out Of Office","confidence":0.9}', { category_map: MAP }).__forwardable, false);
});
test('L7 fail-open: Uncategorized still forwards when forward_on_uncategorized=true', () => {
  assert.equal(classify('garbage', { category_map: MAP, forward_on_uncategorized: true }).__forwardable, true);
  assert.equal(classify('garbage', { category_map: MAP, forward_on_uncategorized: false }).__forwardable, false);
});

// ================================================================ category_map fail-safe (Nik's invariant)
function slCategoryBody(cfgOver, parsedOver) {
  const cfg = JSON.parse(JSON.stringify(CFG));
  Object.assign(cfg, cfgOver);
  const input = Object.assign({ __classify_ok: true, __category: 'Meeting Request', __category_id: null, __is_dnc: false }, parsedOver);
  return runCode('Body SL Category', { input, outputs: { CONFIG: cfg, Normalize: norm() } })[0].json;
}
test('K1 EMPTY category_map -> SL Category body sets __skip (necessary, NOT sufficient)', () => {
  // Body-level only. On its own this proved nothing until B14 made the gate read __skip - see SK3,
  // which is the test that actually shows no POST can happen. Kept as the unit-level half.
  // Fixture-driven on purpose, so it keeps holding now that Phase C1 populated the shipped map.
  const r = slCategoryBody({ category_map: {} }, { __category_id: null });
  assert.equal(r.__skip, true, 'with no ids we must never POST a category');
});
test('K1b shipped category_map (Phase C1 pull) is well-formed and covers every writeback name', () => {
  const m = CFG.category_map;
  assert(Object.keys(m).length >= 10, 'expected the 10 live SL categories');
  for (const [name, id] of Object.entries(m))
    assert(Number.isInteger(id) && id > 0, `${name} -> ${id} must be a positive integer id`);
  for (const c of [...CFG.forwardable_categories, 'Do Not Contact'])
    assert(m[c], `writeback target "${c}" has no id in category_map`);
});
test('K2 an Uncategorized classification is always on the SKIP path', () => {
  const r = slCategoryBody({ category_map: MAP }, { __classify_ok: false, __category: 'Uncategorized', __category_id: null });
  assert.equal(r.__skip, true);
});
test('K3 populated map + ok classification -> writes, and pause_lead ONLY for DNC', () => {
  const ok = slCategoryBody({ category_map: MAP }, { __category_id: 2, __is_dnc: false });
  assert.equal(ok.__skip, false); assert.equal(ok.__body.category_id, 2);
  assert(!('pause_lead' in ok.__body), 'non-DNC must not pause the lead');
  const dnc = slCategoryBody({ category_map: MAP }, { __category_id: 4, __is_dnc: true });
  assert.equal(dnc.__body.pause_lead, true);
});

// ================================================================ forward resolution
function fwd(inbox, cfgOver = {}) {
  const cfg = JSON.parse(JSON.stringify(CFG));
  Object.assign(cfg, cfgOver);
  const n = norm({ from_email: inbox });
  // three-way routing reads Classify Parse; ok:true selects the OWNER branch
  return runCode('Forward Resolve', { input: {},
    outputs: { CONFIG: cfg, Normalize: n, 'Classify Parse': { __classify_ok: true } } })[0].json;
}
test('F1 known inbox resolves inbox -> owner NAME -> owner email (sheet-column-1 parity)', () => {
  const r = fwd('pii-661b267e@example.invalid');
  assert.equal(r.__forward_owner, 'Toby');
  assert.equal(r.__forward_to, 'toby@janeasystems.com');
  assert.equal(r.__forward_miss, false);
});
test('F2 unknown inbox -> forward_default + miss flag (drives the ops warn)', () => {
  const r = fwd('pii-4ef8e397@example.invalid');
  assert.equal(r.__forward_miss, true);
  assert.equal(r.__forward_to, CFG.forward_default);
});
test('F3 no owner address in the map carries a trailing/leading space', () => {
  for (const [k, v] of Object.entries(CFG.forward_owner_map)) assert.equal(v, v.trim(), `${k}: ${JSON.stringify(v)}`);
});
test('F4 the "Test" owner row maps to Melisa (explains Make\'s duplicate branch)', () => {
  assert.equal(CFG.forward_owner_map.Test, 'melisa@janeasystems.com');
});
test('F5 every recipient is present in the map (blueprint 14 + Matt from the registry)', () => {
  assert.equal(Object.keys(CFG.forward_owner_map).length, 15,
    'the registry added Matt only - James was already mapped to the same address');
  for (const who of ['Toby', 'Andreas', 'Mario', 'Mirza', 'Melisa', 'Can', 'Test', 'Bill', 'Benedetto',
                     'Sergey', 'James', 'Rune', 'Chrissy', 'Noah', 'Matt'])
    assert(CFG.forward_owner_map[who], `missing ${who}`);
});
test('F6 forward map source is CONFIG and the Sheets path ships disabled', () => {
  assert.equal(CFG.forward_map_source, 'config');
  assert.equal(CFG.sheets.enabled, false);
});

// ================================================================ lead resolve
// B27: the lead read is no longer person-filtered, so the matcher only accepts leads held by an
// email-verified candidate. Fixtures therefore carry person_id, and the harness supplies the
// candidate list the picker would have produced. PERSON is the default owner in these fixtures.
const PERSON = 84882;
function leadResolve(leads, over = {}, candidates = [PERSON]) {
  const n = norm(over);
  const withOwner = leads.map((l) => (l.person_id === undefined ? { ...l, person_id: PERSON } : l));
  return runCode('Lead Resolve', {
    input: { data: withOwner },
    outputs: { CONFIG: CFG, Normalize: n,
               'R Person Pick': { __person_candidates: candidates, __person_id: candidates[0] } },
  })[0].json;
}
test('R1 lead resolved by Campaign field exact (canon) match', () => {
  const leads = [{ id: 'L1', is_archived: false, [F.lead_campaign]: '[Sales Sprint] Sales Sprint 2026 - London - Valids' }];
  const r = leadResolve(leads);
  assert.equal(r.__lead_id, 'L1'); assert.equal(r.__lead_how, 'campaign_field');
});
test('R2 Campaign-field match is nbsp-insensitive on BOTH sides', () => {
  const leads = [{ id: 'L1', is_archived: false, [F.lead_campaign]: `[Sales${NBSP}Sprint] Sales Sprint 2026` }];
  const r = leadResolve(leads, { campaign_name: '[Sales Sprint] Sales Sprint 2026' });
  assert.equal(r.__lead_id, 'L1');
});
test('R3 title-prefix fallback covers pre-convention sprint leads (no backfill needed)', () => {
  const leads = [{ id: 'L2', is_archived: false, title: '3565502 - [Sales Sprint] whatever - Person-fbbb498b' }];
  const r = leadResolve(leads);
  assert.equal(r.__lead_id, 'L2'); assert.equal(r.__lead_how, 'title_prefix');
});
test('R4 archived leads are never selected', () => {
  const leads = [{ id: 'L3', is_archived: true, [F.lead_campaign]: '[Sales Sprint] Sales Sprint 2026 - London - Valids' }];
  const r = leadResolve(leads);
  assert.equal(r.__no_lead, true);
});
test('R5 no match at all -> no-lead path flagged', () => {
  const r = leadResolve([{ id: 'L4', is_archived: false, title: 'unrelated' }]);
  assert.equal(r.__no_lead, true); assert.equal(r.__lead_how, 'none');
});
test('R6 Campaign field wins over the title fallback when both could match', () => {
  const leads = [{ id: 'T', is_archived: false, title: '3565502 - old - Person-fbbb498b' },
                 { id: 'CF', is_archived: false, [F.lead_campaign]: '[Sales Sprint] Sales Sprint 2026 - London - Valids' }];
  assert.equal(leadResolve(leads).__lead_id, 'CF');
});

// ================================================================ builders
function personCreate(over = {}) {
  const n = norm(over);
  return runCode('Body Person Create', { input: { __org_id: 42 }, outputs: { CONFIG: CFG, Normalize: n } })[0].json.__body;
}
test('B1 person create fills all three title mirrors and NOT the standard job_title', () => {
  // was: "fills the STANDARD job_title AND ..." - that asserted a write Pipedrive forbids on this
  // tenant (B17: contact sync disabled -> 403 on job_title). The mirrors carry the title instead.
  const b = personCreate();
  assert.equal(b.job_title, undefined, 'contact-sync field - 403s on this tenant');
  for (const k of [F.position_lh, F.title_std_cf, F.title_linkedin]) assert.equal(b.custom_fields[k], 'CTO', k);
});
test('B2 person create fills LinkedIn into both mirrors, company, location, campaign canon', () => {
  const b = personCreate();
  assert.equal(b.custom_fields[F.linkedin_lh], 'https://linkedin.com/in/pii-f5c4ebe4');
  assert.equal(b.custom_fields[F.linkedin_profile], 'https://linkedin.com/in/pii-f5c4ebe4');
  assert.equal(b.custom_fields[F.company_lh], 'Acme Inc');
  assert.equal(b.custom_fields[F.location_lh], 'London');
  assert.equal(b.custom_fields[F.campaign], '[Sales Sprint] Sales Sprint 2026 - London - Valids');
});
test('B3 person create stamps medium=eMail, hypothesis, source 446, owner', () => {
  const b = personCreate();
  assert.equal(b.custom_fields[F.medium], 'eMail');
  assert.equal(b.custom_fields[F.hypothesis], 'Sales Sprint');
  assert.equal(b.custom_fields[F.source], CFG.source_value);
  assert.equal(b.owner_id, CFG.owner_id);
});
test('B4 person create: empty/absent values are OMITTED (no empty-string writes)', () => {
  const b = personCreate({ lead_data: { company_name: '', job_title: '', linkedin_profile: null, location: '' } });
  for (const k of [F.company_lh, F.position_lh, F.linkedin_lh, F.location_lh])
    assert(!(k in b.custom_fields), `${k} must be omitted`);
  assert(!('job_title' in b), 'standard job_title must be omitted when empty');
});
test('B5 person create sets event name only under the two-bracket convention', () => {
  assert(!(F.event_name in personCreate().custom_fields));
  const b = personCreate({ campaign_name: '[Events Visiting] [Ai4 2026] - Mario' });
  assert.equal(b.custom_fields[F.event_name], 'Ai4 2026');
});
function personPatch(cur, over = {}) {
  const n = norm(over);
  return runCode('Body Person Patch', { input: { __person: cur, __org_id: 42 }, outputs: { CONFIG: CFG, Normalize: n } })[0].json;
}
test('B6 person patch is fill-if-empty: a non-empty medium is NEVER overwritten (cross-channel safety)', () => {
  const r = personPatch({ id: 1, custom_fields: { [F.medium]: 'LinkedIn' } });
  assert(!(F.medium in r.__body.custom_fields), 'LinkedIn medium must survive an email touch');
});
test('B7 person patch ALWAYS-OVERWRITES campaign (W1.0.11.1 semantics)', () => {
  const r = personPatch({ id: 1, custom_fields: { [F.campaign]: 'Some Older Campaign' } });
  assert.equal(r.__body.custom_fields[F.campaign], '[Sales Sprint] Sales Sprint 2026 - London - Valids');
});
test('B8 person patch skips entirely when nothing needs writing', () => {
  const cur = { id: 1, job_title: 'CTO', org_id: 42, custom_fields: {
    [F.position_lh]: 'CTO', [F.title_std_cf]: 'CTO', [F.title_linkedin]: 'CTO', [F.company_lh]: 'Acme Inc',
    [F.linkedin_lh]: 'https://linkedin.com/in/pii-f5c4ebe4', [F.linkedin_profile]: 'https://linkedin.com/in/pii-f5c4ebe4',
    [F.location_lh]: 'London', [F.medium]: 'eMail', [F.hypothesis]: 'Sales Sprint',
    [F.campaign]: '[Sales Sprint] Sales Sprint 2026 - London - Valids' } };
  assert.equal(personPatch(cur).__skip, true);
});
test('B9 person org link is fill-if-empty', () => {
  assert.equal(personPatch({ id: 1, custom_fields: {} }).__body.org_id, 42);
  assert(!('org_id' in personPatch({ id: 1, org_id: 7, custom_fields: {} }).__body));
});
function leadCreate(over = {}, ctx = {}) {
  const n = norm(over);
  return runCode('Body Lead Create', { input: Object.assign({ __person_id: 5, __org_id: 42 }, ctx),
                                       outputs: { CONFIG: CFG, Normalize: n } })[0].json.__body;
}
test('B10 lead title is {campaign_id} - {canon campaign} - {full name}', () => {
  const b = leadCreate({ campaign_name: `[Sales${NBSP}Sprint] Sales Sprint 2026` });
  assert.equal(b.title, '3565502 - [Sales Sprint] Sales Sprint 2026 - Person-fbbb498b');
});
test('B11 lead carries the Campaign custom field (fixes the invisible-email-leads disease)', () => {
  assert.equal(leadCreate()[F.lead_campaign], '[Sales Sprint] Sales Sprint 2026 - London - Valids');
});
test('B12 lead create: union-of-one [1.Cold], channel 578, opportunity type 480, owner, org link', () => {
  const b = leadCreate();
  assert.deepEqual(b.label_ids, [CFG.labels.cold]);
  assert.equal(b.channel, 578);
  assert.equal(b[F.lead_opportunity_type], 480);
  assert.equal(b.owner_id, CFG.owner_id);
  assert.equal(b.organization_id, 42);
});
function orgCreate(over = {}) {
  const n = norm(over);
  return runCode('Body Org Create', { input: {}, outputs: { CONFIG: CFG, Normalize: n } })[0].json.__body;
}
test('B13 org create writes the website into all three parity keys', () => {
  const cf = orgCreate().custom_fields;
  for (const k of [F.org_website_a, F.org_website_b, F.org_website_lh]) assert.equal(cf[k], 'https://acme.com', k);
});
test('B14 a linkedin.com company_url goes to the org LinkedIn field, NOT Website (W1.0.12 guard)', () => {
  const cf = orgCreate({ lead_data: { company_name: 'Acme Inc', website: 'https://www.linkedin.com/company/acme' } }).custom_fields;
  assert.equal(cf[F.org_linkedin_lh], 'https://www.linkedin.com/company/acme');
  for (const k of [F.org_website_a, F.org_website_b, F.org_website_lh]) assert(!(k in cf), `${k} must stay empty`);
});
function replyActivity(over = {}, ctx = {}) {
  const n = norm(over);
  return runCode('Body Reply Activity', { input: Object.assign({ __lead_id: 'L1', __summary: null }, ctx),
                                          outputs: { CONFIG: CFG, Normalize: n } })[0].json;
}
test('B15 reply activity stores subject AND body (email reply text reaches the CRM at last)', () => {
  const r = replyActivity();
  assert(r.__body.note.includes('Subject: Re: quick question'), r.__body.note);
  assert(r.__body.note.includes('Sounds interesting'), r.__body.note);
  assert.equal(r.__body.done, true);
  assert.equal(r.__body.lead_id, 'L1');
});
test('B16 reply activity omits an empty note (W1.0.6 idiom) and skips with no lead', () => {
  const r = replyActivity({ subject: '', reply_body: '' });
  assert(!('note' in r.__body), 'empty note must be omitted');
  assert.equal(replyActivity({}, { __lead_id: null }).__skip, true);
});
test('B17 org resolve: exact canonical name match, ambiguity flagged, domain tiebreak', () => {
  const n = norm();
  const items = [{ item: { id: 1, name: 'Acme Inc' } }, { item: { id: 2, name: 'Acme Inc' } }];
  const r = runCode('Org Resolve', { input: { data: { items } }, outputs: { CONFIG: CFG, Normalize: n } })[0].json;
  assert.equal(r.__org_found, true); assert.equal(r.__org_ambiguous, true);
  const single = runCode('Org Resolve', { input: { data: { items: [{ item: { id: 9, name: 'acme  inc' } }] } },
                                          outputs: { CONFIG: CFG, Normalize: n } })[0].json;
  assert.equal(single.__org_id, 9, 'canonical/case-insensitive name match');
});

// ================================================================ graph invariants
function reach(start, seen = new Set()) {
  for (const out of (C[start]?.main || [])) for (const e of (out || [])) {
    if (!seen.has(e.node)) { seen.add(e.node); reach(e.node, seen); }
  }
  return seen;
}
const REPLIES_NODES = workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.slack' &&
  String(n.parameters.channelId.value).includes('slack_channel_replies')).map((n) => n.name);
test('I1 GRAPH: the DNC path can never reach a replies-channel post (silent by construction)', () => {
  const fromDnc = reach('Mark DNC');
  const leak = REPLIES_NODES.filter((n) => fromDnc.has(n));
  assert.deepEqual(leak, [], `DNC must be silent, leaked: ${leak}`);
  const fromUnsub = reach('U Mark DNC');
  assert.deepEqual(REPLIES_NODES.filter((n) => fromUnsub.has(n)), []);
});
test('I2 GRAPH: alert-before-writes - every reply CRM write is downstream of Reply Alert', () => {
  const after = reach('Reply Alert');
  for (const w of ['SL Category', 'Lead Labels Union', 'Reply Activity']) assert(after.has(w), `${w} must follow the alert`);
});
test('I2b GRAPH: the alert is NEVER downstream of a CRM write (ordering, not just reachability)', () => {
  // F10 idiom: a failed CRM write must never be able to swallow the human notification
  for (const w of ['SL Category', 'Lead Labels Union', 'Reply Activity', 'SL Forward Email']) {
    const after = reach(w);
    for (const alertNode of ['Body Reply Alert', 'Reply Alert', 'Gate Reply Alert'])
      assert(!after.has(alertNode), `${alertNode} must not sit downstream of ${w}`);
  }
});
const feeders = (t) => Object.entries(C).filter(([, c]) => (c.main || []).some((o) => (o || []).some((e) => e.node === t))).map(([s]) => s);
function writeNodes() {
  return workflow.nodes.filter((n) => {
    const isWrite = n.type === 'n8n-nodes-base.slack' || (n.type === 'n8n-nodes-base.httpRequest' &&
      ['POST', 'PATCH', 'PUT', 'DELETE'].includes(String(n.parameters.method).toUpperCase()));
    return isWrite && !n.name.startsWith('Ops Warn') && n.name !== 'LLM Classify';
  });
}
test('I3 GRAPH: EVERY inbound edge of a write node comes from a WRITE_MODE gate', () => {
  // stronger than "has a gate somewhere": a single non-gated path would bypass shadow mode
  const bad = [];
  for (const n of writeNodes()) {
    const fs = feeders(n.name);
    assert(fs.length > 0, `${n.name} is unreachable`);
    const nonGate = fs.filter((f) => !f.startsWith('Gate '));
    if (nonGate.length) bad.push(`${n.name} <- ${nonGate.join(',')}`);
  }
  assert.deepEqual(bad, [], `writes reachable without a gate: ${bad}`);
});
test('I4 GRAPH: every gate routes its false branch to Shadow Log', () => {
  const gates = workflow.nodes.filter((n) => n.name.startsWith('Gate '));
  assert(gates.length >= 12, `expected the full gate set, got ${gates.length}`);
  for (const g of gates) {
    const outs = C[g.name].main;
    assert.equal(outs.length, 2, `${g.name} must have both branches`);
    // B20: the false branch now goes to a Skip node that records AND continues. SH1/SH2 own the
    // detail; here we just assert it still reaches the recorder.
    const skip = outs[1][0].node;
    assert.equal(skip, `Skip ${g.name.slice('Gate '.length)}`, `${g.name} false branch`);
    const rec = ((C[skip]?.main || [])[0] || []).map((e) => e.node);
    assert(rec.includes('Shadow Log'), `${g.name} false branch must record the intended action`);
  }
});
test('I5 GRAPH: gates test WRITE_MODE === live', () => {
  for (const g of workflow.nodes.filter((n) => n.name.startsWith('Gate '))) {
    const left = g.parameters.conditions.conditions[0].leftValue;
    assert(left.includes("WRITE_MODE === 'live'"), `${g.name}: ${left}`);
  }
});
test('I6 GRAPH: ops warns are NOT gated (observability survives shadow)', () => {
  const feeders = (t) => Object.entries(C).filter(([, c]) => (c.main || []).some((o) => (o || []).some((e) => e.node === t))).map(([s]) => s);
  for (const n of workflow.nodes.filter((x) => x.name.startsWith('Ops Warn')))
    assert(!feeders(n.name).some((f) => f.startsWith('Gate ')), `${n.name} must not be gated`);
});
test('I7 GRAPH: no orphan nodes and no dangling connection targets', () => {
  const inbound = new Set();
  for (const [, c] of Object.entries(C)) for (const out of (c.main || [])) for (const e of (out || [])) inbound.add(e.node);
  const orphans = workflow.nodes.map((n) => n.name).filter((n) => n !== 'Webhook' && !inbound.has(n));
  assert.deepEqual(orphans, [], `orphans: ${orphans}`);
  for (const [s, c] of Object.entries(C)) {
    assert(nodes.has(s), `connection source ${s} is not a node`);
    for (const out of (c.main || [])) for (const e of (out || [])) assert(nodes.has(e.node), `${s} -> missing ${e.node}`);
  }
});
test('I8 GRAPH: CATEGORY_UPDATED (Make trigger) reaches no branch - Switch has no such output', () => {
  const rules = getNode('Switch Event').parameters.rules.values.map((v) => v.outputKey);
  assert.deepEqual(rules, ['SENT', 'REPLIED', 'BOUNCED', 'UNSUB']);
  assert(!rules.includes('CATEGORY_UPDATED'));
});
const httpNodes = () => workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest');

const gateExpr = (label) => getNode(`Gate ${label}`).parameters.conditions.conditions[0].leftValue;
const ENRICHED = {
  __enriched: { ...norm({ event_type: 'EMAIL_SENT', lead_data: {} }),
                lead: { email: 'pii-fb41e2f4@example.invalid', full_name: 'E One', company: 'MockEnrich Ltd',
                        title: 'Head of Mock Data', linkedin: 'https://li/x',
                        website: 'https://mockenrich.example', location: 'London' } },
};

// ---------- WS: webhook authenticity (Nik). The endpoint is public and writes to the CRM.
// Rejection must be a silent DROP behind an already-sent 200 - never a 500, because Smartlead
// disables an endpoint after 5 failures.
const SECRET = 'sl-shared-secret-value';
const SECRET_SHA = require('crypto').createHash('sha256').update(SECRET).digest('hex');
function verify(body, cfgOver = {}, headers = {}) {
  const sd = {};
  return runCode('Verify Secret', {
    input: {},
    outputs: { CONFIG: { ...CFG, ...cfgOver }, Webhook: { body, headers } },
    staticData: sd,
  })[0].json;
}
test('WS1 a VALID secret passes and raises no warning', () => {
  const r = verify({ event_type: 'EMAIL_SENT', secret_key: SECRET },
                   { webhook_secret_sha256: SECRET_SHA });
  assert.equal(r.__auth_ok, true);
  assert.equal(r.__auth_mode, 'valid');
  assert.equal(r.__auth_warn, false);
});
test('WS2 a WRONG secret is rejected and warned, with a source hint', () => {
  const r = verify({ event_type: 'EMAIL_SENT', secret_key: 'not-it', campaign_name: 'C' },
                   { webhook_secret_sha256: SECRET_SHA },
                   { 'cf-connecting-ip': '203.0.113.9', 'user-agent': 'curl/8' });
  assert.equal(r.__auth_ok, false);
  assert.equal(r.__auth_mode, 'mismatch');
  assert.equal(r.__auth_warn, true);
  assert(r.__auth_hint.includes('203.0.113.9'), r.__auth_hint);
  assert(r.__auth_hint.includes('curl/8'), r.__auth_hint);
});
test('WS3 a MISSING secret counts as invalid (Nik)', () => {
  for (const body of [{ event_type: 'X' }, { event_type: 'X', secret_key: null }]) {
    const r = verify(body, { webhook_secret_sha256: SECRET_SHA });
    assert.equal(r.__auth_ok, false);
    assert.equal(r.__auth_mode, 'missing');
  }
});
test('WS4 UNCONFIGURED accepts traffic but says so (shipping state)', () => {
  assert.equal(CFG.webhook_secret_sha256, null, 'ships unarmed; arming is a release gate');
  const r = verify({ event_type: 'EMAIL_SENT' });
  assert.equal(r.__auth_ok, true, 'dropping everything would blind the shadow phase');
  assert.equal(r.__auth_mode, 'unconfigured');
  assert.equal(r.__auth_warn, true);
});
test('WS5 no secret VALUE is stored anywhere - only a digest', () => {
  assert(!/webhook_secret"\s*:/.test(JSON.stringify(workflow)), 'no plaintext secret field');
  const js = getNode('Verify Secret').parameters.jsCode;
  assert(/for \(let i = 0;[\s\S]*charCodeAt\(i\) \^/.test(js),
    'constant-time digest compare required (no early return on first differing char)');
  assert(!/=== *want|== *want/.test(js), 'a plain equality compare would be timing-variable');
  assert(js.includes("createHash('sha256')"), js.slice(0, 80));
});
test('WS6 GRAPH: an unauthenticated post can never reach Normalize or any write', () => {
  assert.deepEqual(C['IF Authentic'].main[0].map((e) => e.node), ['Normalize']);
  assert.deepEqual(C['IF Authentic'].main[1].map((e) => e.node), ['NoOp Drop Unauthenticated']);
  const drop = C['NoOp Drop Unauthenticated'];
  assert(!drop || !(drop.main || []).some((o) => (o || []).length), 'the drop path must be terminal');
  // and the 200 is already out the door before any of this runs
  assert.deepEqual(C['Webhook'].main[0].map((e) => e.node), ['Respond to Webhook']);
});
test('WS7 the auth warn is rate-limited so an open endpoint cannot flood Slack', () => {
  const js = getNode('Verify Secret').parameters.jsCode;
  assert(js.includes('$getWorkflowStaticData'), 'needs persistent state to throttle');
  assert(js.includes('__auth_suppressed'), 'suppressed count must be reported');
  const warn = getNode('Ops Warn Bad Secret');
  assert(String(warn.parameters.channelId.value).includes('slack_channel_ops'), 'ops channel only');
});

// ---------- IFC: no branch may decide on context that an HTTP hop has already destroyed (B18).
// General form of the B12 lesson: IF/Switch nodes pass their input through unchanged, so the taint
// travels through chains of them. IF DNC and IF Forwardable both sat behind SL Category and read
// its ack - __forwardable was true and the item still took the false branch, so forwarding and
// classification-derived DNC were BOTH silently dead. Asserted structurally, for every branch.
test('IFC1 no IF condition reads $json.__ when its data origin is an HTTP node', () => {
  const feedersOf = (t) => Object.entries(C)
    .filter(([, c]) => (c.main || []).some((o) => (o || []).some((e) => e.node === t)))
    .map(([s]) => s);
  const PASSTHRU = new Set(['n8n-nodes-base.if', 'n8n-nodes-base.switch']);
  const origins = (name, seen = new Set()) => {
    const out = new Set();
    for (const f of feedersOf(name)) {
      if (seen.has(f)) continue;
      seen.add(f);
      const t = nodes.get(f)?.type;
      if (PASSTHRU.has(t)) for (const o of origins(f, seen)) out.add(o);
      else out.add(f);
    }
    return out;
  };
  const bad = [];
  for (const n of workflow.nodes) {
    if (n.type !== 'n8n-nodes-base.if') continue;
    const expr = String(n.parameters.conditions.conditions[0].leftValue);
    if (!expr.includes('$json.__')) continue;            // named-node reads are always safe
    for (const o of origins(n.name))
      if (nodes.get(o)?.type === 'n8n-nodes-base.httpRequest') bad.push(`${n.name} <- ${o}`);
  }
  assert.deepEqual(bad, [], `branches deciding on destroyed context:\n  ${bad.join('\n  ')}`);
});
test('IFC2 the two reply branches read the classification from Classify Parse by name', () => {
  for (const [node, key] of [['IF DNC', '__is_dnc'], ['IF Forwardable', '__forwardable']]) {
    const e = getNode(node).parameters.conditions.conditions[0].leftValue;
    assert(e.includes("$('Classify Parse')"), `${node}: ${e}`);
    assert(e.includes(key), `${node}: ${e}`);
    assert.equal(evalExpr(e, { input: { ok: true }, outputs: { 'Classify Parse': { [key]: true } } }), true);
    assert.equal(evalExpr(e, { input: { [key]: true }, outputs: { 'Classify Parse': {} } }), false,
      'must ignore $json entirely - that is the ack');
  }
});
test('IFC3 an Interested reply is forwardable end-to-end through the parse contract', () => {
  const parsed = runCode('Classify Parse', {
    input: { content: [{ text: '{"category":"Interested","confidence":0.95,"is_dnc":false}' }] },
    outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json;
  assert.equal(parsed.__forwardable, true);
  assert.equal(evalExpr(getNode('IF Forwardable').parameters.conditions.conditions[0].leftValue,
    { input: { ok: true }, outputs: { 'Classify Parse': parsed } }), true, 'the forward must fire');
});

// ---------- FM: the forward map, after full registry ingestion (699 CSV rows -> 696 unique).
// Resolution is inbox -> owner NAME -> owner email, so a break can hide in either hop. These run
// the REAL Forward Resolve code rather than re-implementing the lookup.
function resolveInbox(inbox) {
  return runCode('Forward Resolve', {
    input: {},
    outputs: { CONFIG: CFG, Normalize: norm({ from_email: inbox }),
               'Classify Parse': { __classify_ok: true } },
  })[0].json;
}
test('FM1 the map loads at the ingested size, with normalised keys', () => {
  const m = CFG.forward_inbox_map;
  assert.equal(Object.keys(m).length, 696, 'unique inboxes after dedupe');
  const bad = Object.keys(m).filter((k) => k !== k.trim().toLowerCase() || !k.includes('@'));
  assert.deepEqual(bad, [], `keys must be trimmed/lowercased addresses: ${bad.slice(0, 5)}`);
});
test('FM2 every owner named by an inbox has a mailbox - nothing silently falls to default', () => {
  const owners = new Set(Object.values(CFG.forward_inbox_map));
  assert.equal(owners.size, 14, 'the registry carries 14 owners');
  const unmapped = [...owners].filter((o) => !CFG.forward_owner_map[o]);
  assert.deepEqual(unmapped, [], `owners with no mailbox: ${unmapped}`);
});
test('FM3 three inboxes per owner resolve end-to-end (inbox -> name -> email)', () => {
  const byOwner = {};
  for (const [inbox, owner] of Object.entries(CFG.forward_inbox_map)) {
    (byOwner[owner] = byOwner[owner] || []).push(inbox);
  }
  const failures = [];
  for (const [owner, inboxes] of Object.entries(byOwner)) {
    // deterministic "random": first, middle, last of the sorted set
    const sorted = inboxes.slice().sort();
    const picks = [sorted[0], sorted[Math.floor(sorted.length / 2)], sorted[sorted.length - 1]];
    for (const inbox of picks) {
      const r = resolveInbox(inbox);
      if (r.__forward_owner !== owner) failures.push(`${inbox}: owner ${r.__forward_owner} != ${owner}`);
      if (r.__forward_to !== CFG.forward_owner_map[owner]) failures.push(`${inbox}: to ${r.__forward_to}`);
      if (r.__forward_miss !== false) failures.push(`${inbox}: flagged as a miss`);
    }
  }
  assert.deepEqual(failures, [], `resolution failures:\n  ${failures.join('\n  ')}`);
});
test('FM4 an unknown inbox still falls to the default AND is flagged as a miss', () => {
  const r = resolveInbox('pii-06fc99a2@example.invalid');
  assert.equal(r.__forward_miss, true, 'the miss flag is what drives Ops Warn Unknown Inbox');
  assert.equal(r.__forward_to, CFG.forward_default);
  assert.equal(r.__forward_owner, null);
  // and the warn is still reachable from the miss
  assert.equal(evalExpr(getNode('IF Inbox Known').parameters.conditions.conditions[0].leftValue,
                        { input: r }), false, 'a miss must take the not-known branch');
});
test('FM5 mailbox addresses live ONLY in CONFIG, never inline in node code', () => {
  const cfgNode = getNode('CONFIG').name;
  const offenders = [];
  for (const n of workflow.nodes) {
    if (n.name === cfgNode) continue;
    const blob = JSON.stringify(n.parameters);
    for (const m of blob.matchAll(/[a-z0-9._%-]+@janea[a-z0-9.-]*\.(com|co)/gi))
      offenders.push(`${n.name}: ${m[0]}`);
  }
  assert.deepEqual(offenders, [], `hardcoded mailboxes outside CONFIG:\n  ${offenders.join('\n  ')}`);
});
test('FM6 the two owners the registry is dominated by resolve to their own mailboxes', () => {
  // Mario (104 inboxes) and Toby (78) are the bulk of the registry - a swap here would misroute most
  assert.equal(resolveInbox('pii-f06d8290@example.invalid').__forward_to, 'mario@janeasystems.com');
  assert.equal(resolveInbox('pii-0637c702@example.invalid').__forward_to, 'toby@janeasystems.com');
  assert.notEqual(CFG.forward_owner_map.Mario, CFG.forward_owner_map.Toby);
});

// ---------- SH: shadow must traverse the WHOLE graph (B20). Proven broken on the real Smartlead
// test (exec 11602): Shadow Log was terminal, so the gate's false branch dead-ended and only the
// FIRST intended write per path was ever recorded. The diff harness had nothing to align.
test('SH1 every gate false branch goes to a Skip node, never straight to Shadow Log', () => {
  const gates = workflow.nodes.filter((n) => n.name.startsWith('Gate '));
  assert.equal(gates.length, 14, 'all 14 write triples');
  const bad = [];
  for (const g of gates) {
    const label = g.name.slice('Gate '.length);
    const f = ((C[g.name]?.main || [])[1] || []).map((e) => e.node);
    if (f.length !== 1 || f[0] !== `Skip ${label}`) bad.push(`${g.name} -> ${f}`);
  }
  assert.deepEqual(bad, [], `gates whose false branch does not pass through:\n  ${bad.join('\n  ')}`);
});
test('SH2 every Skip node RECORDS and then CONTINUES exactly where the live write goes', () => {
  const bad = [];
  for (const n of workflow.nodes.filter((x) => x.name.startsWith('Skip '))) {
    const label = n.name.slice('Skip '.length);
    const out = ((C[n.name]?.main || [])[0] || []).map((e) => e.node);
    if (!out.includes('Shadow Log')) { bad.push(`${n.name}: does not record`); continue; }
    const live = ((C[label]?.main || [])[0] || []).map((e) => e.node);
    const missing = live.filter((t) => !out.includes(t));
    if (missing.length) bad.push(`${n.name}: does not continue to ${missing}`);
  }
  assert.deepEqual(bad, [], `skip paths that truncate the chain:\n  ${bad.join('\n  ')}`);
});
test('SH3 the reply chain is fully reachable in SHADOW, not just in live mode', () => {
  // walk the graph taking ONLY shadow branches (gate false) and assert the whole reply chain runs
  const seen = new Set(['Skip Reply Alert']);
  const stack = ['Skip Reply Alert'];
  while (stack.length) {
    const cur = stack.pop();
    for (const o of (C[cur]?.main || [])) for (const e of (o || [])) {
      if (e.node.startsWith('Gate ')) {                 // in shadow, a gate goes to its Skip
        const skip = `Skip ${e.node.slice('Gate '.length)}`;
        if (!seen.has(skip)) { seen.add(skip); stack.push(skip); }
      } else if (!seen.has(e.node)) { seen.add(e.node); stack.push(e.node); }
    }
  }
  for (const n of ['Classify Body', 'IF Classify Enabled', 'Classify Skipped', 'Classify Parse',
                   'Body SL Category', 'Body Lead Labels Union', 'Body Reply Activity'])
    assert(seen.has(n), `${n} unreachable in shadow mode - the window would not observe it`);
});
test('SH4 Shadow Log stays a terminal recorder (it must not become a chain step)', () => {
  const out = (C['Shadow Log']?.main || []).flat().filter(Boolean);
  assert.deepEqual(out, [], 'Shadow Log must only record; continuation is the Skip node\'s job');
});

// ---------- SRC: provenance of the category, and honest shadow accounting. Both were live gaps:
// the classifier ran with __category_source EMPTY, and Shadow Log recorded skipped writes as if
// they were intended writes.
test('SRC1 a real completion is attributed to the provider', () => {
  const r = runCode('Classify Parse', {
    input: { model: 'gpt-5.2', choices: [{ message: { content: '{"category":"Interested","confidence":0.95}' } }] },
    outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(r.__category_source, 'openai', 'the accuracy report keys off this');
  assert.equal(r.__llm_provider, 'openai');
});
test('SRC2 the native leg keeps its own attribution, not the provider name', () => {
  const skip = runCode('Classify Skipped', {
    outputs: { Normalize: norm({ reply_category: 'Interested' }) } })[0].json;
  const r = runCode('Classify Parse', { input: skip,
    outputs: { CONFIG: CFG, Normalize: norm({ reply_category: 'Interested' }) } })[0].json;
  assert.equal(r.__category_source, 'smartlead-native', 'must not be overwritten by the provider');
});
test('SRC3 Smartlead\'s own category is preserved alongside ours for comparison', () => {
  const n = norm({ reply_category: 'Interested' });
  const r = runCode('Classify Parse', {
    input: { choices: [{ message: { content: '{"category":"Meeting Request","confidence":0.95}' } }] },
    outputs: { CONFIG: CFG, Normalize: n } })[0].json;
  assert.equal(r.__category, 'Meeting Request', 'ours');
  assert.equal(n.reply_category, 'Interested', 'theirs, still on the Normalize output');
  assert.equal(r.__category_source, 'openai');
});
test('SRC4 Shadow Log separates a would-write from a would-skip', () => {
  const base = { CONFIG: CFG, Normalize: norm() };
  const real = runCode('Shadow Log', {
    input: { __intended: { node: 'Reply Activity', method: 'POST', url: '/x', body: {} } },
    outputs: base })[0].json;
  assert.equal(real.would_write, true);
  const skipped = runCode('Shadow Log', {
    input: { __skip: true, __skipped_write: 'SL Category',
             __intended: { node: 'SL Category', method: 'POST', url: '/y', body: {} } },
    outputs: base })[0].json;
  assert.equal(skipped.would_write, false, 'a skipped write must not read as an intended write');
  assert.equal(skipped.skipped_write, 'SL Category');
});

// ---------- RV: three-way forward routing (Nik). An unclassified reply must never be delivered as
// if it were qualified, so it goes to a human reviewer rather than the campaign sender.
function resolveWith(parse, inbox = 'pii-0637c702@example.invalid') {
  return runCode('Forward Resolve', {
    input: {},
    outputs: { CONFIG: CFG, Normalize: norm({ from_email: inbox }), 'Classify Parse': parse },
  })[0].json;
}
test('RV1 branch 1 - a real category forwards to the campaign sender', () => {
  const r = resolveWith({ __classify_ok: true, __category: 'Interested' });
  assert.equal(r.__forward_to, 'toby@janeasystems.com');
  assert.equal(r.__forward_owner, 'Toby');
  assert.equal(r.__forward_review, false);
  assert.equal(r.__forward_reason, 'owner');
});
test('RV2 branch 2 - Uncategorized / low confidence forwards to the REVIEW address', () => {
  for (const parse of [{ __classify_ok: false, __category: 'Uncategorized' },
                       { __classify_ok: false, __category: 'Uncategorized', __confidence: 0.66 },
                       {}]) {
    const r = resolveWith(parse);
    assert.equal(r.__forward_to, CFG.forward_review_address, 'must go to review, not the sender');
    assert.equal(r.__forward_to, EXPECT_REVIEW);
    assert.equal(r.__forward_review, true);
    assert.equal(r.__forward_reason, 'review');
    assert.equal(r.__forward_owner, null, 'no owner is claimed for an unclassified reply');
  }
});
test('RV3 branch 3 - DNC / non-forwardable never reaches the resolver at all', () => {
  const notFwd = runCode('Classify Parse', {
    input: { choices: [{ message: { content: '{"category":"Out Of Office","confidence":0.95,"is_dnc":false}' } }] },
    outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(notFwd.__classify_ok, true);
  assert.equal(notFwd.__forwardable, false, 'Out Of Office is not forwardable');
  assert.equal(evalExpr(getNode('IF Forwardable').parameters.conditions.conditions[0].leftValue,
    { input: {}, outputs: { 'Classify Parse': notFwd } }), false, 'so the forward chain is skipped');
  // and the DNC case likewise diverts before the resolver
  const dnc = runCode('Classify Parse', {
    input: { choices: [{ message: { content: '{"category":"Do Not Contact","confidence":0.98,"is_dnc":true}' } }] },
    outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(evalExpr(getNode('IF DNC').parameters.conditions.conditions[0].leftValue,
    { input: {}, outputs: { 'Classify Parse': dnc } }), true);
});
test('RV4 the review address comes from CONFIG only - never a literal in node code', () => {
  assert.equal(CFG.forward_review_address, EXPECT_REVIEW,
    `review address is ${CFG.forward_review_address}, expected ${EXPECT_REVIEW}`
    + ' - set WF2_EXPECT_REVIEW to declare a window override');
  const js = getNode('Forward Resolve').parameters.jsCode;
  assert(js.includes('CFG.forward_review_address'), 'must read the CONFIG key');
  assert(!/melisa@/.test(js), 'no hardcoded review mailbox');
});
test('RV5 min_confidence 0.70 sends the observed 0.66 garbage case to review', () => {
  assert.equal(CFG.llm.min_confidence, 0.70);
  // the live probe returned exactly this for genuine garbage
  const r = runCode('Classify Parse', {
    input: { choices: [{ message: { content: '{"category":"Uncategorizable by Ai","confidence":0.66,"is_dnc":false}' } }] },
    outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(r.__classify_ok, false, '0.66 < 0.70 -> guardrail');
  assert.equal(r.__category, 'Uncategorized');
  assert.equal(r.__forwardable, true, 'fail-open, so a human still sees it');
  assert.equal(resolveWith(r).__forward_to, CFG.forward_review_address);
  // and at the old threshold it would have been accepted and then NOT forwarded
  const at06 = runCode('Classify Parse', {
    input: { choices: [{ message: { content: '{"category":"Uncategorizable by Ai","confidence":0.66,"is_dnc":false}' } }] },
    outputs: { CONFIG: { ...CFG, llm: { ...CFG.llm, min_confidence: 0.6 } }, Normalize: norm() } })[0].json;
  assert.equal(at06.__classify_ok, true, 'documents exactly what 0.70 fixed');
  assert.equal(at06.__forwardable, false, 'it would have been silently dropped');
});
test('RV6 the review ops-warn carries the reply text and a Smartlead link', () => {
  const t = evalExpr(getNode('Ops Warn Classify').parameters.text, {
    input: {},
    outputs: { CONFIG: CFG,
               Normalize: norm({ app_url: 'https://app.smartlead.ai/app/master-inbox?leadMap=99',
                                 reply_body: 'this   is   the   reply text' }),
               'Classify Parse': { __confidence: 0.66 } } });
  assert(t.includes(EXPECT_REVIEW), 'names where it was routed');
  assert(t.includes('confidence 0.66'), t);
  assert(t.includes('Open in Smartlead'), 'a warn nobody can act on is just noise');
  assert(t.includes('this is the reply text'), 'reply text included, whitespace collapsed');
});

// ---------- OA: OpenAI provider contract. The request/response shape changed wholesale, and the
// old parser would have returned '' for every completion - i.e. silently Uncategorized forever.
test('OA1 CONFIG declares the provider, base and model with no hardcoded host', () => {
  assert.equal(CFG.llm.provider, 'openai');
  assert.equal(CFG.llm.base, 'https://api.openai.com/v1/chat/completions');
  assert.equal(CFG.llm.model, 'gpt-5.2');
  assert.equal(CFG.llm.model_fallback, 'gpt-4o-mini', 'the cost floor stays one line away');
  assert.equal(getNode('LLM Classify').parameters.url, "={{ $('CONFIG').item.json.llm.base }}");
});
test('OA2 the request body is the chat/completions shape', () => {
  const b = runCode('Classify Body', {
    input: {}, outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json.__body;
  assert.equal(b.model, 'gpt-5.2');
  assert.deepEqual(b.response_format, { type: 'json_object' });
  assert.equal(b.max_completion_tokens, 400, 'current flagships renamed max_tokens');
  assert.equal(b.max_tokens, undefined, 'max_tokens would be rejected');
  assert.equal('temperature' in b, false, 'newer flagships accept only the default temperature');
  assert.equal(b.messages.length, 2);
  assert.equal(b.messages[0].role, 'system');
  assert.equal(b.messages[1].role, 'user');
  assert(b.messages[1].content.includes('STRICT JSON'), 'the strict contract stays in the prompt');
  for (const c of Object.keys(CFG.category_map))
    assert(b.messages[1].content.includes(c), `category dictionary must list ${c}`);
});
test('OA3 the parser reads choices[0].message.content', () => {
  const resp = { model: 'gpt-5.2',
    choices: [{ message: { content: '{"category":"Meeting Request","confidence":0.91,"is_dnc":false,"one_line_summary":"wants a call"}' } }],
    usage: { prompt_tokens: 812, completion_tokens: 37, total_tokens: 849 } };
  const r = runCode('Classify Parse', { input: resp, outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(r.__category, 'Meeting Request');
  assert.equal(r.__classify_ok, true);
  assert.equal(r.__category_id, 2);
  assert.equal(r.__summary, 'wants a call');
  assert.equal(r.__llm_provider, 'openai');
  assert.deepEqual(r.__llm_usage, { prompt: 812, completion: 37, total: 849, model: 'gpt-5.2' });
});
test('OA4 every guardrail survives the swap: garbage, unknown category, low confidence', () => {
  const wrap = (content) => ({ choices: [{ message: { content } }] });
  const parse = (input) => runCode('Classify Parse',
    { input, outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  for (const [label, input] of [
    ['garbage', wrap('not json at all')],
    ['empty', wrap('')],
    ['unknown category', wrap('{"category":"Totally Made Up","confidence":0.99}')],
    ['low confidence', wrap('{"category":"Interested","confidence":0.2}')],
    ['no choices', { model: 'x' }],
  ]) {
    const r = parse(input);
    assert.equal(r.__category, 'Uncategorized', `${label} must fall to Uncategorized`);
    assert.equal(r.__classify_ok, false, label);
    assert.equal(r.__category_id, null, `${label} must not carry a writeback id`);
    assert.equal(r.__is_dnc, false, `${label} must never infer DNC`);
  }
});
test('OA5 a DNC-shaped completion drives the DNC path', () => {
  const r = runCode('Classify Parse', {
    input: { choices: [{ message: { content: '{"category":"Do Not Contact","confidence":0.97,"is_dnc":true}' } }] },
    outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(r.__is_dnc, true);
  assert.equal(r.__category_id, 4);
  assert.equal(evalExpr(getNode('IF DNC').parameters.conditions.conditions[0].leftValue,
    { input: {}, outputs: { 'Classify Parse': r } }), true);
});
test('OA6 no Anthropic remnants anywhere in the shipped workflow', () => {
  const blob = JSON.stringify(workflow);
  for (const bad of ['anthropic', 'claude-', 'x-api-key'])
    assert(!blob.toLowerCase().includes(bad), `stale Anthropic reference: ${bad}`);
});

// ---------- NC: Smartlead-native category (F5) + event-alias learning (F1)
test('NC1 Normalize captures Smartlead\'s own reply_category and source', () => {
  const n = norm({ reply_category: 'Interested', reply_source: 'CAMPAIGN' });
  assert.equal(n.reply_category, 'Interested');
  assert.equal(n.reply_source, 'CAMPAIGN');
  assert.equal(norm({ reply_category: undefined, lead_category: { new_name: 'Meeting Request' } })
    .reply_category, 'Meeting Request', 'category-updated shape too');
});
test('NC1b reply_category arrives as a NUMERIC id on organic replies - resolve it to a name', () => {
  // observed live: Smartlead's test payload said "Interested"; real organic replies said 2.
  // Left unresolved, the F5 native fallback would reject it as an unknown category and route
  // every reply to human review, and the accuracy report would compare "Meeting Request" to "2".
  assert.equal(norm({ reply_category: 2 }).reply_category, 'Meeting Request');
  assert.equal(norm({ reply_category: '2' }).reply_category, 'Meeting Request');
  assert.equal(norm({ reply_category: 4 }).reply_category, 'Do Not Contact');
  assert.equal(norm({ reply_category: 'Interested' }).reply_category, 'Interested', 'names still pass');
  assert.equal(norm({ reply_category: 99999 }).reply_category, null, 'an unknown id must not be invented');
  assert.equal(norm({ reply_category: undefined, lead_category: { new_id: 3 } }).reply_category,
               'Not Interested', 'the category-updated shape carries ids too');
});
test('NC1c a numeric native category still drives real gating end-to-end', () => {
  const n = norm({ reply_category: 2 });
  const skip = runCode('Classify Skipped', { outputs: { Normalize: n } })[0].json;
  assert.equal(skip.__category_source, 'smartlead-native');
  const r = runCode('Classify Parse', { input: skip, outputs: { CONFIG: CFG, Normalize: n } })[0].json;
  assert.equal(r.__category, 'Meeting Request');
  assert.equal(r.__classify_ok, true);
  assert.equal(r.__category_id, 2);
});
test('NC2 classifier OFF -> the native category drives REAL gating, marked smartlead-native', () => {
  const skip = runCode('Classify Skipped', {
    outputs: { Normalize: norm({ reply_category: 'Interested' }) },
  })[0].json;
  assert.equal(skip.__category_source, 'smartlead-native');
  const r = runCode('Classify Parse', { input: skip,
    outputs: { CONFIG: CFG, Normalize: norm({ reply_category: 'Interested' }) } })[0].json;
  assert.equal(r.__category, 'Interested', 'not Uncategorized any more');
  assert.equal(r.__classify_ok, true);
  assert.equal(r.__category_id, 1, 'so the SL writeback intent is real, not a placeholder');
  assert.equal(r.__forwardable, true, 'forwardable BECAUSE Interested, not via fail-open');
  assert.equal(r.__category_source, 'smartlead-native', 'source must survive into the parse output');
});
test('NC3 native DNC gates the DNC path for real', () => {
  const skip = runCode('Classify Skipped', {
    outputs: { Normalize: norm({ reply_category: 'Do Not Contact' }) } })[0].json;
  const r = runCode('Classify Parse', { input: skip,
    outputs: { CONFIG: CFG, Normalize: norm({ reply_category: 'Do Not Contact' }) } })[0].json;
  assert.equal(r.__is_dnc, true);
  assert.equal(evalExpr(getNode('IF DNC').parameters.conditions.conditions[0].leftValue,
    { input: {}, outputs: { 'Classify Parse': r } }), true);
});
test('NC4 no native category -> the old fail-open behaviour, unchanged', () => {
  const skip = runCode('Classify Skipped', { outputs: { Normalize: norm({ reply_category: undefined }) } })[0].json;
  assert.equal(skip.__category_source, 'none');
  const r = runCode('Classify Parse', { input: skip,
    outputs: { CONFIG: CFG, Normalize: norm({ reply_category: undefined }) } })[0].json;
  assert.equal(r.__category, 'Uncategorized');
  assert.equal(r.__category_id, null);
  assert.equal(r.__forwardable, true, 'fail-open still reaches a human');
});
test('NC5 an unknown native category cannot smuggle a bad id into the writeback', () => {
  const skip = runCode('Classify Skipped', {
    outputs: { Normalize: norm({ reply_category: 'Totally Made Up' }) } })[0].json;
  const r = runCode('Classify Parse', { input: skip,
    outputs: { CONFIG: CFG, Normalize: norm({ reply_category: 'Totally Made Up' }) } })[0].json;
  assert.equal(r.__classify_ok, false, 'not in category_map -> rejected by the guardrail');
  assert.equal(r.__category_id, null);
});
test('NC6 F1: a raw event string that differs from the canonical one is flagged', () => {
  assert.equal(norm({ event_type: 'EMAIL_REPLY' }).event_alias, null, 'the OBSERVED string is canonical');
  assert.equal(norm({ event_type: 'EMAIL_REPLIED' }).event_alias, 'email_replied',
    'my old assumption would now be reported, not silently absorbed');
  assert.equal(norm({ event_type: 'SOMETHING_ELSE' }).event_alias, null, 'UNKNOWN is not an alias');
  assert.equal(CFG.canonical_events.REPLIED, 'email_reply');
  assert.deepEqual(CFG.canonical_events_observed, ['email_reply'],
    'only the reply event is actually observed - the rest stay declared assumptions');
});
test('NC7 F1: the alias warns ONCE per new string, then is remembered', () => {
  const sd = {};
  const n = norm({ event_type: 'EMAIL_REPLIED' });
  const first = runCode('Event Alias Watch', { outputs: { Normalize: n }, staticData: sd })[0].json;
  assert.equal(first.__alias_warn, true);
  assert.equal(first.__alias_raw, 'email_replied');
  const second = runCode('Event Alias Watch', { outputs: { Normalize: n }, staticData: sd })[0].json;
  assert.equal(second.__alias_warn, false, 'a learned string must not keep warning');
  const other = runCode('Event Alias Watch', {
    outputs: { Normalize: norm({ event_type: 'EMAIL_BOUNCE' }) }, staticData: sd })[0].json;
  assert.equal(other.__alias_warn, true, 'but a different new string still warns');
});
test('NC8 F2: time_replied feeds reply.received_at', () => {
  assert.equal(norm({ time_replied: '2023-04-04T08:31:22+00:00' }).reply.received_at,
               '2023-04-04T08:31:22+00:00');
});

// ---------- DEL: soft-deleted persons (B19). Pipedrive's SEARCH returns them and its payload has
// no is_deleted field - confirmed live with person 84632 after deletion. Patching such a record is
// silent data loss, so each successful resolve is re-read with a GET.
const DELETED_GET = { data: { id: 84632, name: 'E1 Testperson', is_deleted: true } };
const LIVE_GET = { data: { id: 84632, name: 'Real Person', is_deleted: false } };
test('DEL1 SENT: a deleted person becomes NOT FOUND, so the create path runs', () => {
  const r = runCode('Person Verify Apply', {
    input: DELETED_GET,
    outputs: { 'Person Pick': { __person_found: true, __person_id: 84632, __person: { id: 84632 } } },
  })[0].json;
  assert.equal(r.__person_found, false, 'must look exactly like "not found"');
  assert.equal(r.__person_id, null);
  assert.equal(r.__person_deleted, true);
  assert.equal(r.__person_deleted_id, 84632, 'the id is kept for the warn only');
  // and the create/patch fork reads __person_found, so it now takes CREATE
  assert.equal(evalExpr(getNode('IF Person Found').parameters.conditions.conditions[0].leftValue,
                        { input: r }), false);
});
test('DEL2 REPLIED: a deleted person yields the no-lead path', () => {
  const r = runCode('R Person Verify Apply', {
    input: DELETED_GET,
    outputs: { 'R Person Pick': { __person_found: true, __person_id: 84632 } },
  })[0].json;
  assert.equal(r.__person_found, false);
  assert.equal(r.__person_id, null);
});
test('DEL3 a LIVE person passes through untouched', () => {
  const picked = { __person_found: true, __person_id: 84632, __person: { id: 84632 } };
  const r = runCode('Person Verify Apply', { input: LIVE_GET, outputs: { 'Person Pick': picked } })[0].json;
  assert.equal(r.__person_found, true);
  assert.equal(r.__person_id, 84632);
  assert.equal(r.__person_deleted, false);
  assert.equal(r.__person_verified, true);
});
test('DEL4 nothing found -> no verify cost and no false deletion signal', () => {
  const r = runCode('Person Verify Apply', {
    input: {}, outputs: { 'Person Pick': { __person_found: false, __person_id: null } },
  })[0].json;
  assert.equal(r.__person_found, false);
  assert.equal(r.__person_deleted, false, 'absent must never be reported as deleted');
});
test('DEL5 active_flag:false is honoured too, and a failed GET does not invent a deletion', () => {
  const picked = { __person_found: true, __person_id: 5 };
  const byFlag = runCode('Person Verify Apply', {
    input: { data: { id: 5, active_flag: false } }, outputs: { 'Person Pick': picked } })[0].json;
  assert.equal(byFlag.__person_deleted, true);
  // cof=true means a failed GET yields an error-ish item; it must fail SAFE (keep the person)
  const onErr = runCode('Person Verify Apply', {
    input: { error: 'boom' }, outputs: { 'Person Pick': picked } })[0].json;
  assert.equal(onErr.__person_deleted, false, 'an unreachable GET must not delete-by-accident');
  assert.equal(onErr.__person_found, true);
});
test('DEL6 GRAPH: both verifies are wired in, and the warn is ops-only and shared', () => {
  // B22: no resolve -> no verify GET, so the pick now feeds a resolved-check first
  assert.deepEqual(C['Person Pick'].main[0].map((e) => e.node), ['IF Person Resolved']);
  assert.deepEqual(C['IF Person Resolved'].main[0].map((e) => e.node), ['Person Verify']);
  assert.deepEqual(C['IF Person Resolved'].main[1].map((e) => e.node), ['Org Search']);
  assert.deepEqual(C['R Person Pick'].main[0].map((e) => e.node), ['IF R Person Resolved']);
  assert.deepEqual(C['IF R Person Resolved'].main[0].map((e) => e.node), ['R Person Verify']);
  assert.deepEqual(C['IF R Person Resolved'].main[1].map((e) => e.node), ['R Lead List']);
  // one output, two consumers: main chain continues AND the deleted-check tees off
  assert.deepEqual(C['Person Verify Apply'].main[0].map((e) => e.node).sort(),
                   ['IF Person Deleted', 'Org Search']);
  assert.deepEqual(C['R Person Verify Apply'].main[0].map((e) => e.node).sort(),
                   ['IF Person Deleted', 'R Lead List']);
  assert.deepEqual(C['IF Person Deleted'].main[0].map((e) => e.node), ['Ops Warn Deleted Person']);
  const w = getNode('Ops Warn Deleted Person');
  assert(String(w.parameters.channelId.value).includes('slack_channel_ops'), 'ops channel only');
});
test('DEL8 NOTHING may read the unverified pick for person identity (the bypass I missed)', () => {
  // I declared B19 closed while Carry Person Ctx, Merge Reply Ctx and Person Id Final all still read
  // $('Person Pick') / $('R Person Pick') - so the guard was bypassed on both paths, and Person Id
  // Final would have attached a new lead to the DELETED person's id. Same class as B18: the tests
  // checked the guard in isolation and the wiring, never that the DECIDERS consume it.
  const allowed = new Set(['Person Verify Apply', 'R Person Verify Apply']);
  const bad = [];
  for (const n of workflow.nodes) {
    const js = n.parameters.jsCode;
    if (!js || allowed.has(n.name)) continue;
    for (const pick of ["$('Person Pick')", "$('R Person Pick')"]) {
      if (!js.includes(pick)) continue;
      // permitted only as an explicit fallback BEHIND the verified read
      const verified = js.includes("Verify Apply');") || js.includes("Verify Apply').item");
      if (!verified) bad.push(`${n.name} reads ${pick} without consulting the verify first`);
    }
  }
  assert.deepEqual(bad, [], `deleted-person guard bypassed by:\n  ${bad.join('\n  ')}`);
});
test('DEL9 a deleted person cannot become the lead owner (Person Id Final)', () => {
  const r = runCode('Person Id Final', {
    input: { data: { id: 99999 } },                       // the freshly CREATED person
    outputs: { 'Person Verify Apply': { __person_found: false, __person_id: null, __person_deleted: true },
               'Person Pick': { __person_found: true, __person_id: 84632 },   // the stale deleted hit
               'Carry Person Ctx': { __org_id: 7 } },
  })[0].json;
  assert.equal(r.__person_id, 99999, 'must use the new person, never the deleted id');
});
test('DEL10 the reply ctx merge also honours the verify', () => {
  const r = runCode('Merge Reply Ctx', {
    input: { __lead_id: 5, __no_lead: false },
    outputs: { 'R Person Verify Apply': { __person_found: false, __person_id: null, __person_deleted: true },
               'R Person Pick': { __person_found: true, __person_id: 84632 } },
  })[0].json;
  assert.equal(r.__person_id, null);
  assert.equal(r.__person_found, false);
});
test('DEL7 the verify is a GET - it must never itself be a write', () => {
  for (const n of ['Person Verify', 'R Person Verify']) {
    assert.equal(getNode(n).parameters.method, 'GET');
    assert.equal(getNode(n).parameters.sendBody, undefined);
  }
});

// ---------- PD: tenant write constraints (B17). Pipedrive 403s on contact-sync fields when the
// tenant has contact sync disabled - which this one does. It would have killed EVERY person write.
test('PD1 no person body ever sends a contact-sync field', () => {
  const forbidden = CFG.pd_forbidden_std_fields;
  assert(forbidden.includes('job_title'), 'the set must stay recorded in CONFIG');
  for (const node of ['Body Person Create', 'Body Person Patch']) {
    const r = runCode(node, {
      input: { __org_id: 7, __person: { id: 5 }, __person_id: 5 },
      outputs: { CONFIG: CFG, Normalize: norm(), 'Apply Enrich': ENRICHED },
    })[0].json;
    for (const f of forbidden)
      assert(!(f in r.__body), `${node} sends ${f} -> Pipedrive 403 on this tenant`);
  }
});
test('PD2 the title still reaches the CRM via the three custom-field mirrors', () => {
  const r = runCode('Body Person Create', {
    input: { __org_id: 7 },
    outputs: { CONFIG: CFG, Normalize: norm(), 'Apply Enrich': ENRICHED },
  })[0].json;
  for (const k of [F.position_lh, F.title_std_cf, F.title_linkedin])
    assert.equal(r.__body.custom_fields[k], 'Head of Mock Data', `mirror ${k} missing`);
});
test('PD3 std_person_fields stays empty until the tenant setting changes', () => {
  assert.deepEqual(CFG.std_person_fields, {});
});

// ---------- EN: enrichment actually reaches the writes (B16). Apply Enrich published __enriched
// and every body read $('Normalize'), so enrichment was computed and discarded. The real
// EMAIL_SENT payload carries NO lead_data, so this produced Org Create {name:null} -> 400.
test('EN1 the org body uses the ENRICHED company, not the empty one from Normalize', () => {
  const bare = norm({ event_type: 'EMAIL_SENT', lead_data: {} });
  assert.equal(bare.lead.company, null, 'precondition: real SENT payloads carry no company');
  const r = runCode('Body Org Create', {
    input: {}, outputs: { CONFIG: CFG, Normalize: bare, 'Apply Enrich': ENRICHED },
  })[0].json;
  assert.equal(r.__body.name, 'MockEnrich Ltd');
  assert.equal(r.__skip, false);
});
test('EN2 the person body uses the enriched title/company too', () => {
  const r = runCode('Body Person Create', {
    input: { __org_id: 7 },
    outputs: { CONFIG: CFG, Normalize: norm({ event_type: 'EMAIL_SENT', lead_data: {} }),
               'Apply Enrich': ENRICHED },
  })[0].json;
  const cf = r.__body.custom_fields;
  assert.equal(cf[F.position_lh], 'Head of Mock Data');
  assert.equal(cf[F.company_lh], 'MockEnrich Ltd');
});
test('EN3 without enrichment the bodies fall back to Normalize (reply/bounce paths)', () => {
  const r = runCode('Body Org Create', {
    input: {}, outputs: { CONFIG: CFG, Normalize: norm() },   // lead_data present in the fixture
  })[0].json;
  assert.equal(r.__body.name, 'Acme Inc');
});
test('EN4 no company anywhere -> the org write SKIPS instead of POSTing name:null', () => {
  const r = runCode('Body Org Create', {
    input: {}, outputs: { CONFIG: CFG, Normalize: norm({ event_type: 'EMAIL_SENT', lead_data: {} }) },
  })[0].json;
  assert.equal(r.__body.name, null);
  assert.equal(r.__skip, true, 'Pipedrive rejects a nameless org: "name: Missing required field"');
  assert.equal(evalExpr(gateExpr('Org Create'),
    { input: r, outputs: { CONFIG: { ...CFG, WRITE_MODE: 'live' } } }), false);
});
test('EN5 Org Search looks up the enriched company (else it creates a duplicate every time)', () => {
  const url = getNode('Org Search').parameters.url;
  assert(url.includes("Apply Enrich"), 'must consult the enriched value');
  const got = evalUrlTemplate(url, { CONFIG: CFG, 'Apply Enrich': ENRICHED,
                                     Normalize: norm({ event_type: 'EMAIL_SENT', lead_data: {} }) });
  assert(got.includes('term=MockEnrich%20Ltd'), got);
});

// ---------- LK: rendered LINKS (addendum A). B9's lesson applied to Slack text: assert the
// EVALUATED link, never the template - ".../person/" + null renders as a dead link that looks fine
// in source. Nik found this one by clicking it on the live double.
// NOTE: distinct name on purpose - a second `alertText` would hoist over the A-group's helper
function replyAlertRendered(input, outputs) {
  return evalExpr(getNode('Reply Alert').parameters.text,
                  { input, outputs: { CONFIG: CFG, Normalize: norm(), ...outputs } });
}
test('LK1 lead present -> the lead link carries the lead id', () => {
  const t = replyAlertRendered({ __lead_id: 4242 }, {});
  assert(t.includes(`${CFG.pipedrive_base}/leads/inbox/4242|Open lead`), t);
});
test('LK2 no lead but a person -> person link carries the PERSON id, recovered by owner node', () => {
  const t = replyAlertRendered({ ok: true }, { 'Merge Reply Ctx': { __person_id: 777 } });
  assert(t.includes(`${CFG.pipedrive_base}/person/777|Open person`), t);
});
test('LK3 no lead and no person -> NO link at all, never a dangling .../person/', () => {
  const t = replyAlertRendered({ ok: true }, {});
  assert(!/\/person\/[|>]/.test(t), `dead person link rendered: ${t}`);
  assert(!/\/person\/(null|undefined)/.test(t), `null id in link: ${t}`);
  assert(t.includes('not in CRM yet'), t);
});
test('LK4 no rendered link may ever end in a bare id-less path segment', () => {
  for (const [input, outputs] of [[{ __lead_id: 4242 }, {}],
                                  [{ ok: true }, { 'Merge Reply Ctx': { __person_id: 777 } }],
                                  [{ ok: true }, {}]]) {
    for (const m of replyAlertRendered(input, outputs).matchAll(/<([^|>]+)\|/g))
      assert(/\/\d+$/.test(m[1]), `link without a trailing id: ${m[1]}`);
  }
});

// ---------- SLK: the Smartlead deep link (item D, links click-verified by Nik). Same LK family:
// assert the RENDERED link, and no map id must mean no link rather than a 404.
function replyAlertWith(over, input = { __lead_id: 4242 }) {
  return evalExpr(getNode('Reply Alert').parameters.text,
                  { input, outputs: { CONFIG: CFG, Normalize: norm(over) } });
}
test('SLK1 the payload\'s own app_url is used verbatim when present', () => {
  const url = 'https://app.smartlead.ai/app/master-inbox?leadMap=2638146185';
  const t = replyAlertWith({ app_url: url });
  assert(t.includes(`<${url}|Open in Smartlead>`), t);
});
test('SLK2 no app_url but a map id -> the link is constructed from CONFIG.sl_inbox_base', () => {
  const t = replyAlertWith({ app_url: undefined, ui_master_inbox_link: undefined,
                             sl_email_lead_map_id: 9900003001 });
  assert(t.includes(`<${CFG.sl_inbox_base}9900003001|Open in Smartlead>`), t);
  assert.equal(CFG.sl_inbox_base, 'https://app.smartlead.ai/app/master-inbox?leadMap=');
});
test('SLK3 neither available -> NO Smartlead link at all', () => {
  const t = replyAlertWith({ app_url: undefined, ui_master_inbox_link: undefined,
                             sl_email_lead_map_id: undefined });
  assert(!t.includes('Open in Smartlead'), t);
  assert(!t.includes('leadMap='), `never a link with an empty id: ${t}`);
});
test('SLK4 the Smartlead link never replaces the Pipedrive one - both appear', () => {
  const t = replyAlertWith({ app_url: 'https://app.smartlead.ai/app/master-inbox?leadMap=1' });
  assert(t.includes('|Open lead>'), t);
  assert(t.includes('|Open in Smartlead>'), t);
});
test('SLK5 every rendered link in the alert is absolute and carries a non-empty key', () => {
  for (const over of [{ app_url: 'https://app.smartlead.ai/app/master-inbox?leadMap=1' },
                      { app_url: undefined, sl_email_lead_map_id: 55 },
                      { app_url: undefined }]) {
    for (const m of replyAlertWith(over).matchAll(/<([^|>]+)\|/g)) {
      assert(/^https:\/\//.test(m[1]), `not absolute: ${m[1]}`);
      assert(!/[?/=]$/.test(m[1]), `link ends with an empty key: ${m[1]}`);
    }
  }
});

// ---------- PL: real webhook payloads (B15). Recovered from the Make blueprint designer samples -
// these are Smartlead's own payloads, not my guesses. See wf2-webhook-payloads.md.
test('PL1 EMAIL_SENT: sl_email_lead_id populates sl_lead_id', () => {
  const n = norm({ event_type: 'EMAIL_SENT', lead_id: undefined, sl_email_lead_id: '3244145308',
                   sl_email_lead_map_id: 2638146185 });
  assert.equal(n.sl_lead_id, '3244145308', 'null here silently collapses the dedupe key');
  assert.equal(n.sl_lead_map_id, 2638146185);
});
test('PL2 dedupe stays per-lead on real SENT payloads (the collapse this prevents)', () => {
  const a = norm({ event_type: 'EMAIL_SENT', lead_id: undefined, sl_email_lead_id: '111' });
  const b = norm({ event_type: 'EMAIL_SENT', lead_id: undefined, sl_email_lead_id: '222' });
  assert.notEqual(a.sl_lead_id, b.sl_lead_id, 'two leads must not share one dedupe key');
});
test('PL3 the Smartlead UI deep link is taken from the payload, not constructed', () => {
  const url = 'https://app.smartlead.ai/app/master-inbox?leadMap=2638146185';
  assert.equal(norm({ app_url: url }).sl_app_url, url);
  assert.equal(norm({ app_url: undefined, ui_master_inbox_link: url }).sl_app_url, url);
});
test('PL4 reply text also reads the last_reply object shape', () => {
  const n = norm({ subject: undefined, reply_body: undefined,
                   last_reply: { subject: 'Re: hi', email_body: '<div>sure</div>', stats_id: 'st9' } });
  assert.equal(n.reply.subject, 'Re: hi');
  assert.equal(n.reply.body, '<div>sure</div>');
  assert.equal(n.reply.stats_id, 'st9');
});
test('PL5 timestamp accepts event_timestamp / time_sent (real SENT has no `timestamp`)', () => {
  assert.equal(norm({ timestamp: undefined, event_timestamp: '2026-01-28T14:44:39.932+00:00' }).timestamp,
               '2026-01-28T14:44:39.932+00:00');
  assert.equal(norm({ timestamp: undefined, time_sent: '2026-01-28T14:44:39.932+00:00' }).timestamp,
               '2026-01-28T14:44:39.932+00:00');
});

// ---------- SK: __skip ENFORCEMENT (B14). Six bodies computed __skip and nothing read it, so every
// "skip path" was decorative: the category fail-safe would still have POSTed a null id, and a
// no-lead reply would still have PATCHed /v1/leads/undefined. The gate is the enforcement point.
const gateNames = () => workflow.nodes.filter((n) => n.name.startsWith('Gate ')).map((n) => n.name);
test('SK1 EVERY gate tests __skip as well as WRITE_MODE', () => {
  const bad = gateNames().filter((g) => {
    const e = getNode(g).parameters.conditions.conditions[0].leftValue;
    return !e.includes('__skip') || !e.includes('WRITE_MODE');
  });
  assert.deepEqual(bad, [], `gates that cannot stop a skipped write: ${bad}`);
});
test('SK2 a skipped write is blocked even in live mode; a normal one passes', () => {
  const live = { ...CFG, WRITE_MODE: 'live' };
  for (const g of gateNames()) {
    const e = getNode(g).parameters.conditions.conditions[0].leftValue;
    assert.equal(evalExpr(e, { input: { __skip: true }, outputs: { CONFIG: live } }), false, `${g} skip`);
    assert.equal(evalExpr(e, { input: {}, outputs: { CONFIG: live } }), true, `${g} normal`);
    // build the shadow config explicitly: this assertion is about shadow mode, so it must not
    // depend on whatever mode the deployed CONFIG happens to carry (it is 'live' during a window)
    const shadow = { ...CFG, WRITE_MODE: 'shadow' };
    assert.equal(evalExpr(e, { input: {}, outputs: { CONFIG: shadow } }), false, `${g} shadow`);
  }
});
test('SK3 EMPTY category_map -> the SL Category GATE is false, so no POST can happen', () => {
  // the invariant Nik asked to lock. Body-level __skip was never enough on its own.
  const body = runCode('Body SL Category', {
    input: { __classify_ok: true, __category: 'Interested', __category_id: null },
    outputs: { CONFIG: { ...CFG, category_map: {} }, Normalize: norm() },
  })[0].json;
  assert.equal(body.__skip, true);
  assert.equal(evalExpr(gateExpr('SL Category'),
    { input: body, outputs: { CONFIG: { ...CFG, WRITE_MODE: 'live', category_map: {} } } }), false);
});
test('SK4 no resolvable lead -> labels and activity gates are both false', () => {
  const live = { ...CFG, WRITE_MODE: 'live' };
  const lbl = runCode('Body Lead Labels Union', {
    input: { ok: true }, outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json;
  assert.equal(lbl.__skip, true, 'no lead id -> must not PATCH /v1/leads/undefined');
  assert.equal(evalExpr(gateExpr('Lead Labels Union'), { input: lbl, outputs: { CONFIG: live } }), false);
  const act = runCode('Body Reply Activity', {
    input: { ok: true }, outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json;
  assert.equal(act.__skip, true);
  assert.equal(evalExpr(gateExpr('Reply Activity'), { input: act, outputs: { CONFIG: live } }), false);
});
test('SK5 the labels write targets the RECOVERED lead id, not post-HTTP junk', () => {
  const lbl = runCode('Body Lead Labels Union', {
    input: { ok: true, id: 999 },                    // an API ack: it carries no __lead_id
    outputs: { CONFIG: CFG, Normalize: norm(), 'Merge Reply Ctx': { __lead_id: 4242, __lead_labels: [] } },
  })[0].json;
  assert.equal(lbl.__lead_id, 4242, 'the PATCH url interpolates this');
  assert.equal(lbl.__skip, false);
  assert(getNode('Lead Labels Union').parameters.url.includes('$json.__lead_id'));
});

// ---------- UC: context recovery across an HTTP hop (B12). These feed an API-ACK as $json, which
// is what the node really receives after a write - the earlier tests injected __ fields directly and
// therefore agreed with a broken graph.
const SILVA = 'silva-manual-label-0000';
const ACK = { ok: true, id: 999, data: { id: 999 } };            // shaped like an SL/PD response
test('UC1 label union survives the forward hop: fed an API ack, it still preserves a manual label', () => {
  const r = runCode('Body Lead Labels Union', {
    input: ACK,
    outputs: { CONFIG: CFG, Normalize: norm(),
               'Merge Reply Ctx': { __lead_id: 4242, __lead_labels: [SILVA, CFG.labels.cold] } },
  })[0].json;
  assert(r.__label_union.includes(SILVA), 'a manually added label must never be dropped');
  for (const k of ['cold', 'connected', 'responded'])
    assert(r.__label_union.includes(CFG.labels[k]), `${k} missing`);
  assert(!r.__label_union.includes(CFG.labels.dnc), 'no DNC unless the DNC path ran');
  assert.equal(r.__skip, false);
});
test('UC2 DNC path: Mark DNC rebuilds context after the unsubscribe call, union adds DNC', () => {
  const dnc = runCode('Mark DNC', {
    input: ACK,
    outputs: { 'Merge Reply Ctx': { __lead_id: 4242, __lead_labels: [SILVA] },
               'Classify Parse': { __category: 'Do Not Contact', __is_dnc: true } },
  })[0].json;
  assert.deepEqual(dnc.__lead_labels, [SILVA], 'context must survive the HTTP hop');
  assert.equal(dnc.__dnc_label, true);
  assert.equal(dnc.__forwardable, false);
  const r = runCode('Body Lead Labels Union', {
    input: dnc, outputs: { CONFIG: CFG, Normalize: norm(), 'Merge Reply Ctx': { __lead_labels: [SILVA] } },
  })[0].json;
  assert(r.__label_union.includes(CFG.labels.dnc));
  assert(r.__label_union.includes(SILVA));
});
test('UC3 reply activity recovers lead id and summary after the labels PATCH', () => {
  const r = runCode('Body Reply Activity', {
    input: ACK,
    outputs: { CONFIG: CFG, Normalize: norm(),
               'Merge Reply Ctx': { __lead_id: 4242 },
               'Classify Parse': { __summary: 'wants a call next week' } },
  })[0].json;
  assert.equal(r.__skip, false, 'a recoverable lead id must not be treated as missing');
  assert.equal(r.__body.lead_id, 4242);
  assert(JSON.stringify(r.__body).includes('wants a call next week'), 'summary lost');
});
test('UC4 UNSUB path: U Mark DNC rebuilds from U Lead Select, not from the SL ack', () => {
  const r = runCode('U Mark DNC', {
    input: ACK, outputs: { 'U Lead Select': { __lead_id: 77, __lead_labels: [SILVA] } },
  })[0].json;
  assert.deepEqual(r.__lead_labels, [SILVA]);
  assert.equal(r.__lead_id, 77);
  assert.equal(r.__dnc_label, true);
});
test('UC5 with NO recoverable context the union stays inert rather than writing an absolute set', () => {
  const r = runCode('Body Lead Labels Union', {
    input: ACK, outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json;
  assert.equal(r.__body.label_ids.length, 3, 'target labels only');
  assert(!r.__label_union.includes(SILVA));
});

// ---------- NZ: node-input provenance (B11). Live execution proved Normalize's $json is CONFIG's
// output; reading $json.body yielded an empty payload on EVERY event and the suite agreed with it,
// because the harness fed the assumption instead of the topology.
test('NZ1 Normalize takes the payload from the Webhook node, never from $json', () => {
  const js = getNode('Normalize').parameters.jsCode;
  assert(js.includes("$('Webhook')"), 'must name its source node');
  assert(!/const b = \$json/.test(js), '$json here is CONFIG output, not the request body');
  // proof: feed CONFIG as $json (reality) and the payload only via $('Webhook')
  const n = norm({ campaign_name: '[Sales Sprint] X', to_email: 'pii-da50e332@example.invalid' });
  assert.equal(n.campaign_name, '[Sales Sprint] X');
  assert.equal(n.lead.email, 'pii-da50e332@example.invalid');
  assert.equal(n.event, 'REPLIED');
});
test('NZ2 the spine order that forces NZ1 is the one that ships', () => {
  // this test earned its keep: it failed the moment webhook auth was inserted into the spine.
  assert.deepEqual(C['CONFIG'].main[0].map((e) => e.node), ['Verify Secret'],
    'if this changes, re-check every node that reads $json');
  assert.deepEqual(C['IF Authentic'].main[0].map((e) => e.node), ['Normalize']);
});

// ---------- B25: a Body node that spreads $json must decide its OWN __skip.
// Body SL Forward Email spread $json and set nothing, so it inherited __skip from Body SL Category
// (__skip: !__classify_ok). Every Uncategorized reply therefore skipped its forward - the
// human-review routing to forward_review_address was dead in the only case it exists for.
test('B25-1 no Body node inherits __skip from upstream', () => {
  const bad = workflow.nodes
    .filter((n) => n.name.startsWith('Body ') && String(n.parameters.jsCode || '').includes('...$json'))
    .filter((n) => !String(n.parameters.jsCode).includes('__skip'))
    .map((n) => n.name);
  assert.deepEqual(bad, [], 'inheriting __skip is how a write disappears silently');
});
test('B25-2 a review-routed (Uncategorized) reply STILL forwards', () => {
  const out = runCode('Body SL Forward Email', {
    // this is the live shape that failed: category write skipped, forward target = review address
    input: { __skip: true, __skipped_write: 'SL Category', __classify_ok: false,
             __forward_to: 'melisa@janeasystems.com', __forward_reason: 'review',
             __message_id: '<pii-87a5daa0@example.invalid>', __stats_id: 's1', __history: [] },
    outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json;
  assert.equal(out.__skip, false, 'the forward inherited the category write skip - B25');
  assert.equal(out.__body.to_emails, 'melisa@janeasystems.com');
});
test('B25-3 the forward IS skipped when it could not possibly succeed', () => {
  const noTarget = runCode('Body SL Forward Email', {
    input: { __forward_to: null, __message_id: '<a@b>', __stats_id: 's1', __history: [] },
    outputs: { CONFIG: CFG, Normalize: norm() },
  })[0].json;
  assert.equal(noTarget.__skip, true, 'a forward with no recipient must not POST');
  const noMsg = runCode('Body SL Forward Email', {
    input: { __forward_to: 'pii-fd989748@example.invalid', __history: [] },
    outputs: { CONFIG: CFG, Normalize: norm({ message_id: null, stats_id: null }) },
  })[0].json;
  assert.equal(noMsg.__skip, true, 'nothing to forward means no POST');
});

// ---------- SLKX: every Slack message expression must be PARSEABLE JavaScript.
// B26: a bare double quote inside a Python double-quoted string silently terminated it, Python
// concatenated the fragments, and the built expression no longer parsed. Slack answered
// "invalid syntax" and the reply alert never posted - live, for the whole window. Nothing in the
// suite looked at whether these expressions were even syntactically valid.
test('SLKX1 every Slack text expression parses as JavaScript', () => {
  const bad = [];
  for (const n of workflow.nodes.filter((x) => x.type === 'n8n-nodes-base.slack')) {
    const m = String(n.parameters.text || '').match(/^=\{\{([\s\S]*)\}\}$/);
    assert(m, `${n.name}: text is not a single ={{ }} expression`);
    try { new Function('return (' + m[1] + ')'); }
    catch (e) { bad.push(`${n.name}: ${e.message}`); }
  }
  assert.deepEqual(bad, [], 'unparseable Slack expression - this is exactly B26');
});
test('SLKX2 and so does every channel expression', () => {
  for (const n of workflow.nodes.filter((x) => x.type === 'n8n-nodes-base.slack')) {
    const v = String(n.parameters.channelId?.value || '');
    const m = v.match(/^=\{\{([\s\S]*)\}\}$/);
    assert(m, `${n.name}: channel is not an expression`);
    try { new Function('return (' + m[1] + ')'); }
    catch (e) { assert.fail(`${n.name} channel: ${e.message}`); }
  }
});
test('SLKX3 the review warn renders the reply as readable text, not escaped HTML', () => {
  // the real Gmail reply from the live window, verbatim
  const body = '<div dir="ltr"><div class="gmail-gs" style="margin:0px;font-size:16px">'
    + '<div dir="ltr">&nbsp; Sounds good, thanks for reaching out!&nbsp; </div></div></div>'
    + '<br><div class="gmail_quote"><blockquote class="gmail_quote">Hi Nik, WF-2 live window test.'
    + '</blockquote></div>';
  const out = evalExpr(getNode('Ops Warn Classify').parameters.text, {
    input: { __confidence: 0.62 },
    outputs: { CONFIG: CFG, Normalize: norm({ reply_body: body }),
               'Classify Parse': { __confidence: 0.62, __category: 'Uncategorized' } },
  });
  assert(out.includes('Sounds good, thanks for reaching out!'), 'the reply text must be readable');
  assert(!out.includes('&lt;div'), 'escaped HTML tags leaked into the message');
  assert(!out.includes('<div'), 'raw HTML tags leaked into the message');
  assert(!out.includes('Hi Nik, WF-2 live window test'), 'the quoted original was not dropped');
});

// ---------- B24: the SENT branch's existing-lead check matched on the Campaign custom field only.
// Make never populates that field, so live WF-2 created a duplicate of every Make-made lead - proven
// on real data (campaign 3738616: two leads, identical titles, 23 minutes apart).
test('B24-1 an existing lead is matched by the Campaign field when present', () => {
  const out = runCode('Lead Select', {
    input: { data: [{ id: 'L1', title: 'x', person_id: 5, [CFG.fields.lead_campaign]: '[Events Visiting] AI4 - X' }] },
    outputs: { CONFIG: CFG, Normalize: norm({ campaign_name: '[Events Visiting] AI4 - X' }),
               'Person Id Final': { __person_id: 5, __org_id: 6 },
               'Person Pick': { __person_candidates: [5], __person_id: 5 } },
  })[0].json;
  assert.equal(out.__lead_exists, true);
  assert.equal(out.__lead_how, 'campaign_field');
});
test('B24-2 a Make-made lead (EMPTY Campaign field) is matched by the title prefix', () => {
  const out = runCode('Lead Select', {
    input: { data: [{ id: 'L2', title: '3738616 - [Events Visiting] X - Nik Krivosheia', person_id: 5,
                      [CFG.fields.lead_campaign]: '' }] },
    outputs: { CONFIG: CFG,
               Normalize: norm({ campaign_id: 3738616, campaign_name: '[Events Visiting] X' }),
               'Person Id Final': { __person_id: 5, __org_id: 6 },
               'Person Pick': { __person_candidates: [5], __person_id: 5 } },
  })[0].json;
  assert.equal(out.__lead_exists, true, 'this is the duplicate-lead defect: Make fills no Campaign field');
  assert.equal(out.__lead_id, 'L2');
  assert.equal(out.__lead_how, 'title_prefix');
});
test('B24-3 a lead for a DIFFERENT campaign is not matched', () => {
  const out = runCode('Lead Select', {
    input: { data: [{ id: 'L3', title: '9999999 - other - Nik', person_id: 5, [CFG.fields.lead_campaign]: '' }] },
    outputs: { CONFIG: CFG, Normalize: norm({ campaign_id: 3738616, campaign_name: '[X] Y' }),
               'Person Id Final': { __person_id: 5, __org_id: 6 },
               'Person Pick': { __person_candidates: [5], __person_id: 5 } },
  })[0].json;
  assert.equal(out.__lead_exists, false, 'one lead per campaign, so a foreign campaign must not match');
  assert.equal(out.__lead_how, 'none');
});
test('B24-4 archived leads never satisfy the check', () => {
  const out = runCode('Lead Select', {
    input: { data: [{ id: 'L4', title: '3738616 - x - Nik', is_archived: true, person_id: 5,
                      [CFG.fields.lead_campaign]: '' }] },
    outputs: { CONFIG: CFG, Normalize: norm({ campaign_id: 3738616, campaign_name: '[X] Y' }),
               'Person Id Final': { __person_id: 5, __org_id: 6 },
               'Person Pick': { __person_candidates: [5], __person_id: 5 } },
  })[0].json;
  assert.equal(out.__lead_exists, false, 'an archived lead was treated as live');
});
test('B24-4b the prefix separator prevents a shorter campaign id matching a longer one', () => {
  // without " - ", campaign 373 would match a lead titled "3738616 - ..." and suppress a real create
  const out = runCode('Lead Select', {
    input: { data: [{ id: 'L5', title: '3738616 - x - Nik', person_id: 5, [CFG.fields.lead_campaign]: '' }] },
    outputs: { CONFIG: CFG, Normalize: norm({ campaign_id: 373, campaign_name: '[X] Y' }),
               'Person Id Final': { __person_id: 5, __org_id: 6 },
               'Person Pick': { __person_candidates: [5], __person_id: 5 } },
  })[0].json;
  assert.equal(out.__lead_exists, false, 'campaign 373 matched campaign 3738616');
});
test('B24-5 SENT and REPLIED resolve existing leads by the same rule', () => {
  // the asymmetry WAS the bug: one branch had the fallback and the other did not
  for (const n of ['Lead Select', 'Lead Resolve']) {
    const js = getNode(n).parameters.jsCode;
    assert(js.includes("' - '"), `${n}: missing the title-prefix fallback`);
    assert(js.includes('lead_campaign'), `${n}: missing the campaign-field match`);
  }
});

// ---------- B27: duplicate-person selection. THE flip blocker, proven live in the full matrix.
// Pipedrive holds 3 person records for pii-c61c7d08@example.invalid (Make creates one per send, and a
// burst of sends to one address makes duplicates). All four resolvers took the FIRST search hit, the
// lead read was filtered by that one person_id, and when the campaign's lead hung off a DIFFERENT
// duplicate it was invisible: 6 of 7 matrix replies lost their label union and activity, and the
// first-reply gate failed open because it reads labels off the lead.
const DUPES = [84882, 84883, 84884];          // the real shape, oldest first
function pickPerson(items, email = 'pii-c61c7d08@example.invalid') {
  return runCode('R Person Pick', {
    input: { data: { items } },
    outputs: { CONFIG: CFG, Normalize: norm({ to_email: email }) },
  })[0].json;
}
const searchHit = (id) => ({ item: { id, emails: [{ value: 'pii-c61c7d08@example.invalid' }] } });

test('B27-1 every email-verified duplicate is reported, not just the first', () => {
  // deliberately NOT in id order - Pipedrive returns relevance order, which is unstable
  const r = pickPerson([searchHit(84883), searchHit(84884), searchHit(84882)]);
  assert.deepEqual(r.__person_candidates, DUPES, 'candidates must be exposed, oldest first');
  assert.equal(r.__person_dupes, true, 'duplicates must be flagged');
});
test('B27-2 the provisional pick is the OLDEST id, deterministically', () => {
  const a = pickPerson([searchHit(84883), searchHit(84884), searchHit(84882)]);
  const b = pickPerson([searchHit(84884), searchHit(84882), searchHit(84883)]);
  assert.equal(a.__person_id, 84882);
  assert.equal(b.__person_id, 84882, 'search order must not change who we pick');
});
test('B27-3 a non-matching email is never a candidate (B/U took items[0] with no check at all)', () => {
  const r = pickPerson([{ item: { id: 99, emails: [{ value: 'pii-8e71564a@example.invalid' }] } },
                        searchHit(84882)]);
  assert.deepEqual(r.__person_candidates, [84882], 'a fuzzy search hit became the person');
});
test('B27-4 the campaign lead is found even when a DIFFERENT duplicate holds it', () => {
  // this is the exact live failure: we provisionally pick 84882, the lead hangs off 84883
  const leads = [{ id: 'LX', is_archived: false, person_id: 84883,
                   title: '3745477 - [Events Visiting] [WF2 Matrix T8] - Nik - Valids - Nik' }];
  const r = leadResolve(leads, { campaign_id: 3745477, campaign_name: '[Events Visiting] [WF2 Matrix T8] - Nik - Valids' }, DUPES);
  assert.equal(r.__no_lead, false, '6 of 7 matrix replies died exactly here');
  assert.equal(r.__lead_id, 'LX');
  assert.equal(r.__lead_how, 'title_prefix');
});
test('B27-5 the person holding the lead is ADOPTED over the provisional', () => {
  const leads = [{ id: 'LX', is_archived: false, person_id: 84883,
                   title: '3745477 - x - Nik' }];
  const r = leadResolve(leads, { campaign_id: 3745477, campaign_name: '[X] Y' }, DUPES);
  assert.equal(r.__person_id, 84883, 'the lead is the authority, not the first search hit');
  assert.equal(r.__person_adopted, true, 'adoption must be visible in the record');
});
test('B27-6 a stranger\'s lead for the SAME campaign is NOT adopted', () => {
  // the read is no longer person-filtered, so the page contains other people's leads
  const leads = [{ id: 'STRANGER', is_archived: false, person_id: 55555,
                   title: '3745477 - same campaign - Person-66f13945' }];
  const r = leadResolve(leads, { campaign_id: 3745477, campaign_name: '[X] Y' }, DUPES);
  assert.equal(r.__no_lead, true, 'matching on campaign alone attaches us to a stranger');
  assert.equal(r.__person_id, 84882, 'and the provisional must stand');
});
test('B27-7 no lead anywhere -> oldest candidate stands (genuinely new prospect)', () => {
  const r = leadResolve([], { campaign_id: 3745477, campaign_name: '[X] Y' }, DUPES);
  assert.equal(r.__no_lead, true);
  assert.equal(r.__person_id, 84882);
  assert.equal(r.__person_adopted, false);
});
test('B27-8 all four lead reads are unfiltered AND ordered (pagination rule)', () => {
  for (const nm of ['Lead List', 'R Lead List', 'B Lead List', 'U Lead List']) {
    const url = String(getNode(nm).parameters.url);
    assert(!/person_id=/.test(url), `${nm}: still person-filtered - it cannot see a duplicate's lead`);
    assert(/sort=add_time(%20|\+| )DESC/i.test(url), `${nm}: unordered list read used for matching`);
  }
});
test('B27-9 a saturated lead page is reported, never silent', () => {
  const many = [];
  for (let i = 0; i < 500; i++) many.push({ id: 'x' + i, is_archived: false, person_id: 84882 });
  const r = leadResolve(many, { campaign_id: 1, campaign_name: '[X] Y' }, DUPES);
  assert.equal(r.__leads_page_saturated, true, 'an older lead could exist beyond the page');
});
test('B27-10 the SENT branch got the same treatment, not just the reply branch', () => {
  const js = getNode('Person Pick').parameters.jsCode;
  assert(js.includes('__person_candidates'), 'SENT picker still decides on the first hit');
  assert(!/\{ hit = p; break; \}/.test(js), 'first-match-wins still present in SENT');
});
test('B27-11 B/U resolvers verify the email before accepting a person', () => {
  for (const nm of ['B Lead Ctx', 'U Lead Ctx']) {
    const js = getNode(nm).parameters.jsCode;
    assert(js.includes('mails.includes(want)'), `${nm}: still takes items[0] with no email check`);
    assert(js.includes('__person_candidates'), `${nm}: no candidate list`);
  }
});

// ---------- RC: reconciliation provenance. SENT arrives ONLY by WF-2S replay today (Smartlead
// never delivers EMAIL_SENT to our entries), so "which source produced this event" has to survive
// Normalize's whitelist or the diff harness cannot tell replay from real.
test('RC1 a reconciled payload keeps its provenance through Normalize', () => {
  const n = norm({ event_type: 'EMAIL_SENT', campaign_name: '[Events Visiting] AI4 - X',
                   to_email: 'pii-da50e332@example.invalid', __reconciled: true, __reconciled_by: 'WF-2S' });
  assert.equal(n.__reconciled, true, 'provenance dropped by the whitelist');
  assert.equal(n.__reconciled_by, 'WF-2S');
});
test('RC2 a genuine delivery is never labelled reconciled', () => {
  const n = norm({ event_type: 'EMAIL_SENT', campaign_name: '[Events Visiting] AI4 - X',
                   to_email: 'pii-da50e332@example.invalid' });
  assert.equal(n.__reconciled, false, 'a real webhook delivery must not look like a replay');
  assert.equal(n.__reconciled_by, null);
});
test('RC3 the flag cannot be spoofed into naming a source it did not set', () => {
  const n = norm({ event_type: 'EMAIL_SENT', campaign_name: '[Events Visiting] AI4 - X',
                   to_email: 'pii-da50e332@example.invalid', __reconciled_by: 'WF-2S' });
  assert.equal(n.__reconciled, false);
  assert.equal(n.__reconciled_by, null, 'source without the flag must not survive');
});

// ---------- B23: no Pipedrive person -> no lead-list GET. Found by WF-2S replaying real SENT
// events: shadow skips Person Create, so __person_id was null, the URL fabricated person_id=0,
// Pipedrive returned 400, and the SENT execution ABORTED before Shadow Log recorded anything.
test('B23-1 the lead list GET is gated on a real person id', () => {
  assert.deepEqual(C['Person Id Final'].main[0].map((e) => e.node), ['IF Have Person Id'],
    'Person Id Final must not reach Lead List directly');
  const g = getNode('IF Have Person Id');
  const expr = JSON.stringify(g.parameters);
  assert(expr.includes('__person_id !== null'), 'gate must test the id, not truthiness');
});
test('B23-2 both gate branches continue to Lead Select (B20 invariant)', () => {
  assert.deepEqual(C['IF Have Person Id'].main[0].map((e) => e.node), ['Lead List']);
  assert.deepEqual(C['IF Have Person Id'].main[1].map((e) => e.node), ['Lead List Skipped']);
  assert.deepEqual(C['Lead List Skipped'].main[0].map((e) => e.node), ['Lead Select'],
    'a dead-ended false branch loses the create intent entirely');
  assert.deepEqual(C['Lead List'].main[0].map((e) => e.node), ['Lead Select']);
});
test('B23-3 the skip emits an empty list so Lead Select finds no existing lead', () => {
  const js = getNode('Lead List Skipped').parameters.jsCode;
  assert(js.includes('data: []'), 'Lead Select reads $json.data');
  assert(js.includes('pairedItem'), 'Lead Select recovers person/org via a paired lookup');
  assert(js.includes('__no_person: true'), 'the reason must be visible in Shadow Log');
});
test('B23-4 SENT Lead List has the same failure tolerance as its R/B/U siblings', () => {
  for (const n of ['Lead List', 'R Lead List', 'B Lead List', 'U Lead List']) {
    assert.equal(getNode(n).onError, 'continueRegularOutput',
      n + ': a Pipedrive hiccup must degrade, not abort the execution');
  }
});

// ---------- WH: webhook response contract (B10)
test('WH1 responseMode is responseNode whenever a Respond node exists', () => {
  const hook = workflow.nodes.find((n) => n.type === 'n8n-nodes-base.webhook');
  const resp = workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.respondToWebhook');
  assert.equal(resp.length, 1, 'exactly one Respond node');
  // without this n8n aborts EVERY run with "Unused Respond to Webhook node found" -> 500 -> Smartlead
  // disables the endpoint after 5 failures
  assert.equal(hook.parameters.responseMode, 'responseNode');
});
test('WH2 the response is sent BEFORE any processing (Smartlead must not wait on Pipedrive)', () => {
  assert.deepEqual(C['Webhook'].main[0].map((e) => e.node), ['Respond to Webhook']);
  assert.deepEqual(C['Respond to Webhook'].main[0].map((e) => e.node), ['CONFIG']);
});

// ---------- CE: classify_enabled. The Anthropic credential is deferred, so the degraded path is a
// SHIPPING path, not a theoretical one - it gets the same treatment as any other production branch.
test('CE1 classify_enabled is TRUE now that the credential is bound and probed', () => {
  // was "must ship OFF until the credential is bound" - the credential is bound and live-probed,
  // so the classifier runs. Every write is still gated by WRITE_MODE=shadow.
  assert.equal(CFG.classify_enabled, true);
  const expr = getNode('IF Classify Enabled').parameters.conditions.conditions[0].leftValue;
  assert(expr.includes("$('CONFIG').item.json.classify_enabled"), expr);
  assert.equal(evalExpr(expr, { outputs: { CONFIG: CFG } }), true);
  assert.equal(evalExpr(expr, { outputs: { CONFIG: { ...CFG, classify_enabled: false } } }), false);
});
test('CE2 GRAPH: the LLM leg is reachable ONLY through the classify gate', () => {
  const feed = (t) => Object.entries(C).filter(([, c]) => (c.main || []).some((o) => (o || []).some((e) => e.node === t))).map(([s]) => s);
  assert.deepEqual(feed('LLM Classify'), ['IF Classify Enabled']);
  assert.deepEqual(feed('Classify Skipped'), ['IF Classify Enabled']);
  const outs = C['IF Classify Enabled'].main;
  assert.equal(outs[0][0].node, 'LLM Classify', 'true branch = classify');
  assert.equal(outs[1][0].node, 'Classify Skipped', 'false branch = degraded');
  assert.deepEqual(feed('Classify Parse').sort(), ['Classify Skipped', 'LLM Classify']);
});
test('CE3 flag-off outcome: Uncategorized, no category id, no text-DNC, fail-open forward', () => {
  // F5: with no native category this is still the old fail-open path (NC2 covers the native one)
  const skip = runCode('Classify Skipped',
    { outputs: { Normalize: norm({ reply_category: undefined }) } })[0].json;
  assert.equal(skip.__classify_disabled, true);
  const r = runCode('Classify Parse', { input: skip, outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(r.__category, 'Uncategorized');
  assert.equal(r.__classify_ok, false);
  assert.equal(r.__category_id, null, 'no id -> the SL Category write cannot fire');
  assert.equal(r.__is_dnc, false, 'no TEXT-derived DNC while the classifier is off');
  assert.equal(r.__forwardable, true, 'fail-open: replies still reach a human');
  assert.equal(r.__classify_disabled, true, 'the marker must survive into the parse output');
});
test('CE4 flag-off does NOT trip the ops warn (that would fire on every reply for weeks)', () => {
  const cond = getNode('IF Classify Failed').parameters.conditions.conditions[0].leftValue;
  // F5: with no native category this is still the old fail-open path (NC2 covers the native one)
  const skip = runCode('Classify Skipped',
    { outputs: { Normalize: norm({ reply_category: undefined }) } })[0].json;
  const parsed = runCode('Classify Parse', { input: skip, outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(evalExpr(cond, { input: parsed }), false, 'a disabled classifier is expected, not a failure');
  // a REAL classify failure (bad JSON while enabled) must still warn
  const bad = runCode('Classify Parse', { input: { content: [{ text: 'not json' }] },
                                          outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(evalExpr(cond, { input: bad }), true, 'genuine failures must still reach ops');
});
test('CE5 flag-off keeps the SL category write on its skip path', () => {
  // F5: with no native category this is still the old fail-open path (NC2 covers the native one)
  const skip = runCode('Classify Skipped',
    { outputs: { Normalize: norm({ reply_category: undefined }) } })[0].json;
  const parsed = runCode('Classify Parse', { input: skip, outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  const body = runCode('Body SL Category', { input: parsed, outputs: { CONFIG: CFG, Normalize: norm() } })[0].json;
  assert.equal(body.__skip, true, 'never POST a category we could not determine');
});
test('CE6 UNSUBSCRIBED-event DNC is independent of the classifier', () => {
  const reach = (start) => { const seen = new Set(); const st = [start];
    while (st.length) { const cur = st.pop();
      for (const o of (C[cur]?.main || [])) for (const e of (o || [])) if (!seen.has(e.node)) { seen.add(e.node); st.push(e.node); } }
    return seen; };
  const unsubOut = C['Switch Event'].main[3];                       // 4th rule = UNSUB
  const from = new Set();
  for (const e of unsubOut) for (const n of reach(e.node)) from.add(n);
  for (const e of unsubOut) from.add(e.node);
  assert(from.has('U SL Unsubscribe'), 'the event-driven global unsubscribe must still fire');
  for (const n of ['IF Classify Enabled', 'LLM Classify', 'Classify Parse'])
    assert(!from.has(n), `${n} must not sit on the UNSUB path`);
});

// ---------- URL: evaluated request URLs (B9). The raw template read fine; only evaluating it the
// way n8n does exposed a literal '=' welded between the base and the path on 23 of 24 nodes.
function evalUrlTemplate(raw, outputs) {
  assert(raw.startsWith('='), `not an expression field: ${raw.slice(0, 40)}`);
  const parts = raw.slice(1).split(/(\{\{[\s\S]*?\}\})/);
  return parts.map((p) => {
    if (!p.startsWith('{{')) return p;                 // literal text between segments
    const src = p.slice(2, -2).trim();
    return String(vm.runInNewContext(`(${src})`, { $json: {}, $: lookupFactory(outputs) }));
  }).join('');
}
test('URL1 every HTTP node evaluates to a well-formed absolute URL', () => {
  const outputs = {
    CONFIG: CFG,
    Normalize: norm(),
    'Person Pick': { __person_id: 42 },
    'R Person Pick': { __person_id: 42 },
    'Person Id Final': { __person_id: 42, __org_id: 7 },
  };
  const bad = [];
  for (const n of httpNodes()) {
    let u;
    try { u = evalUrlTemplate(String(n.parameters.url), outputs); }
    catch (e) { bad.push(`${n.name}: ${e.message}`); continue; }
    if (!/^https:\/\/[a-z0-9.-]+\//i.test(u)) bad.push(`${n.name}: ${u}`);
    if (/[a-z0-9]=\//i.test(u.split('?')[0])) bad.push(`${n.name}: stray '=' in path -> ${u}`);
  }
  assert.deepEqual(bad, [], `malformed URLs:\n  ${bad.join('\n  ')}`);
});
test('URL2 no raw URL welds two expression segments together with a literal', () => {
  const bad = httpNodes().filter((n) => /\}\}[^{]+\{\{/.test(String(n.parameters.url)))
    .map((n) => `${n.name}: ${n.parameters.url.slice(0, 70)}`);
  assert.deepEqual(bad, [], `literal text between segments:\n  ${bad.join('\n  ')}`);
});

// ---------- SC: Smartlead API contract (B8). Fixtures below are RECORDED live responses
// (2026-07-28), not invented shapes - that is the whole point of the group.
test('SC1 SL Fetch Lead uses the global /leads?email= lookup (the per-campaign one answers 400)', () => {
  const url = getNode('SL Fetch Lead').parameters.url;
  assert(!url.includes('/campaigns/'), 'per-campaign lead lookup is a verified 400');
  assert(url.includes("'/leads?email='"), url);
});
test('SC2 Apply Enrich reads the FLAT /leads?email= response (real shape)', () => {
  const live = {                                    // recorded: pii-9569b1b9@example.invalid
    id: '4086543431', first_name: 'Cheryl', last_name: 'Nagle ', email: 'pii-9569b1b9@example.invalid',
    company_name: 'Perlego', website: null, location: 'London, England, United Kingdom',
    custom_fields: { city: 'London' }, linkedin_profile: 'https://www.linkedin.com/in/pii-e0c6aafb',
    company_url: 'https://perlego.io', is_unsubscribed: false, lead_campaign_data: [],
  };
  const n = norm({ event_type: 'EMAIL_SENT', lead_data: {} });
  const r = runCode('Apply Enrich', { input: live, outputs: { Normalize: n } })[0].json.__enriched;
  assert.equal(r.lead.company, 'Perlego', 'company must come off the flat object');
  assert.equal(r.lead.linkedin, 'https://www.linkedin.com/in/pii-e0c6aafb');
  assert.equal(r.lead.location, 'London, England, United Kingdom');
  assert.equal(r.lead.website, 'https://perlego.io', 'company_url is the website fallback');
});
test('SC3 Apply Enrich still reads the PAGED shape, fields nested under data[0].lead', () => {
  const paged = { total_leads: 1, offset: 0, limit: 1, data: [{
    campaign_lead_map_id: '3318190611', lead_category_id: null, status: 'BLOCKED',
    lead: { id: 1, company_name: 'Perlego', linkedin_profile: 'https://li/x', location: 'London',
            custom_fields: { job_title: 'Head of Data' } } }] };
  const n = norm({ event_type: 'EMAIL_SENT', lead_data: {} });
  const r = runCode('Apply Enrich', { input: paged, outputs: { Normalize: n } })[0].json.__enriched;
  assert.equal(r.lead.company, 'Perlego', 'must descend into data[0].lead, not read data[0]');
  assert.equal(r.lead.title, 'Head of Data', 'titles only ever arrive via custom_fields');
});
test('SC4 Pick Last Message anchors on the last REPLY, not the last entry', () => {
  const hist = { history: [
    { type: 'SENT', message_id: '<s1>', stats_id: 'st1' },
    { type: 'REPLY', message_id: '<r1>', stats_id: 'st1' },
    { type: 'SENT', message_id: '<s2>', stats_id: 'st1' },   // a follow-up after the reply
  ] };
  const r = runCode('Pick Last Message', { input: hist, outputs: { 'Forward Resolve': {} } })[0].json;
  assert.equal(r.__message_id, '<r1>', 'we forward the prospect reply, never our own outbound');
});
test('SC5 Pick Last Message falls back to the last entry when no REPLY exists', () => {
  const hist = { history: [{ type: 'SENT', message_id: '<s1>', stats_id: 'st1' }] };
  const r = runCode('Pick Last Message', { input: hist, outputs: { 'Forward Resolve': {} } })[0].json;
  assert.equal(r.__message_id, '<s1>');
  const empty = runCode('Pick Last Message', { input: {}, outputs: { 'Forward Resolve': {} } })[0].json;
  assert.equal(empty.__message_id, null, 'an empty history must not throw');
});

// ---------- AU: authentication (B7). An unauthenticated HTTP node 401s, and the two ungated
// Smartlead READS plus LLM Classify run even in shadow - so this bites before any write does.
test('AU1 every HTTP node declares an authentication method', () => {
  const bare = httpNodes().filter((n) => !n.parameters.authentication).map((n) => n.name);
  assert.deepEqual(bare, [], `unauthenticated HTTP nodes: ${bare}`);
});
test('AU2 every Pipedrive node is bound to the pipedriveApi credential production WF-1 uses', () => {
  const pd = httpNodes().filter((n) => String(n.parameters.url).includes('pd_api'));
  assert.equal(pd.length, 19, 'exactly 19 (17 + the two B19 person verifies); changes need review');
  for (const n of pd) {
    assert.equal(n.parameters.authentication, 'predefinedCredentialType', n.name);
    assert.equal(n.parameters.nodeCredentialType, 'pipedriveApi', n.name);
    assert.equal((n.credentials || {}).pipedriveApi?.id, 'HnyULgvDdYp0lIkB', `${n.name} credential id`);
  }
});
test('AU3 Smartlead nodes use query auth; the LLM node uses header auth for its provider', () => {
  const sl = httpNodes().filter((x) => String(x.parameters.url).includes('sl_api'));
  assert.equal(sl.length, 6, 'the Smartlead set is exactly 6 nodes');
  for (const n of sl) {
    assert.equal(n.parameters.authentication, 'genericCredentialType', n.name);
    assert.equal(n.parameters.genericAuthType, 'httpQueryAuth', n.name);
    assert.equal((n.credentials || {}).httpQueryAuth?.id, 'YXf5ez4pxDNd2g2B', `${n.name} credential`);
  }
  const llm = getNode('LLM Classify');
  // PROBED: Nik's credential is n8n's native openAiApi type, not httpHeaderAuth. With the predefined
  // type n8n injects Authorization itself, so no auth material can reach the workflow JSON.
  assert.equal(llm.parameters.authentication, 'predefinedCredentialType');
  assert.equal(llm.parameters.nodeCredentialType, 'openAiApi');
  assert.equal((llm.credentials || {}).openAiApi?.id, 'ltWhbdbiCcOBKnLn', 'the single bound credential');
  const hdrs = llm.parameters.headerParameters.parameters.map((h) => h.name);
  // provider switched to OpenAI: the Anthropic version header must be GONE, and Authorization must
  // come from the credential rather than a header literal (AU4 forbids embedded credential values).
  assert(!hdrs.includes('anthropic-version'), 'stale Anthropic header left behind');
  assert(!hdrs.includes('Authorization'), 'Authorization must come from the credential, not the JSON');
});
test('AU4 no credential VALUE is embedded in the workflow - only credential references', () => {
  for (const n of workflow.nodes) {
    for (const c of Object.values(n.credentials || {})) {
      assert.deepEqual(Object.keys(c).sort(), ['id', 'name'], `${n.name} credential must be a reference only`);
    }
  }
});
test('AU5 no HTTP node hardcodes a host - every base comes from CONFIG', () => {
  const bad = httpNodes().filter((n) => /https?:\/\//.test(String(n.parameters.url))).map((n) => n.name);
  assert.deepEqual(bad, [], `hardcoded hosts (untestable, unmockable): ${bad}`);
});
test('I9 SHIP STATE: inactive, expected WRITE_MODE, errorWorkflow bound', () => {
  // Default expectation is shadow. A supervised live window sets WF2_EXPECT_MODE=live, so going
  // live stays a deliberate, visible act rather than something a passing suite quietly permits.
  const expected = process.env.WF2_EXPECT_MODE || 'shadow';
  assert.equal(workflow.active, false);
  assert.equal(CFG.WRITE_MODE, expected,
    `WRITE_MODE is ${CFG.WRITE_MODE}, expected ${expected} - set WF2_EXPECT_MODE to declare intent`);
  assert.equal(workflow.settings.errorWorkflow, 'BbrXPABgOaaTJjD6');
});
test('I10 SECRETS: no api keys, no leaked key, no api_key= param anywhere in the workflow', () => {
  const blob = JSON.stringify(workflow);
  assert(!blob.includes('9f59ef3d'), 'leaked Smartlead key literal present');
  assert(!blob.includes('api_key='), 'api_key= in a URL');
  assert(!/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_[A-Za-z0-9]{6,}/.test(blob), 'SL-key-shaped literal');
});
test('I11 CONFIG: shadow-phase channels, with the flip target kept on record', () => {
  // Phase D routes EVERYTHING to Nik's channel. The team channel is the flip-time value, and the
  // n8n bot was channel_not_found there in W1.0.10, so the flip needs an /invite + a post check.
  assert.equal(CFG.slack_channel_replies, 'C0B8GCVNR5W', 'shadow: replies -> Nik');
  assert.equal(CFG.slack_channel_ops, 'C0B8GCVNR5W');
  assert.equal(CFG.slack_channel_replies_at_flip, 'C07LTD8UT70', 'flip target must stay recorded');
});
test('I12 CONFIG: forwardable categories are exactly Melisa\'s four', () => {
  assert.deepEqual(CFG.forwardable_categories.slice().sort(),
    ['Information Request', 'Interested', 'Meeting Request', 'Not Interested']);
});
test('I13 CONFIG: no assignment task (Melisa\'s automation is the only task source)', () => {
  assert.equal(CFG.flags.create_assignment_task, false);
});
test('I14 GRAPH: SENT branch creates no activity node (2225 emails must not become 2225 activities)', () => {
  const sent = reach('IF Nurture SENT');
  const acts = [...sent].filter((n) => /Activity|Bounce Note/.test(n));
  assert.deepEqual(acts, [], `SENT must not write activities, found: ${acts}`);
});
test('I15 GRAPH: nurture replies reach the replies channel but NO CRM write', () => {
  const fromNurture = reach('Body Nurture Alert');
  assert(fromNurture.has('Nurture Alert'), 'nurture must post');
  const crm = [...fromNurture].filter((n) => ['Lead Labels Union', 'Reply Activity', 'Person Patch', 'Lead Create',
                                              'SL Category', 'SL Forward Email'].includes(n));
  assert.deepEqual(crm, [], `nurture must not touch CRM, found: ${crm}`);
});

console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) process.exit(1);
