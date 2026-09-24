#!/usr/bin/env node
'use strict';

/**
 * Static contract tests for the patched WF-1 export.
 *
 * These tests execute the actual JavaScript stored inside n8n Code nodes and
 * evaluate selected n8n expressions against controlled fixtures. They do not
 * call n8n, HeyReach, Pipedrive, or Slack, so they are not a substitute for the
 * production-mode test double required by W1.0.
 */

const fs = require('fs');
const vm = require('vm');
const path = require('path');
const assert = require('assert/strict');

const workflowPath = process.argv[2] || path.join(__dirname, 'WF-1 HeyReach Receiver - W1.0.1 patched.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
const nodes = new Map(workflow.nodes.map((node) => [node.name, node]));

function getNode(name) {
  const node = nodes.get(name);
  assert(node, `Node not found: ${name}`);
  return node;
}

function lookupFactory(outputs) {
  return function $(name) {
    if (!Object.prototype.hasOwnProperty.call(outputs, name)) {
      throw new Error(`Mock output missing for node: ${name}`);
    }
    return { item: { json: outputs[name] } };
  };
}

function runCodeNode(name, { input = {}, outputs = {}, staticData = null } = {}) {
  const node = getNode(name);
  const code = node.parameters.jsCode;
  const context = {
    $json: input,
    $: lookupFactory(outputs),
    $getWorkflowStaticData: () => {
      if (!staticData) throw new Error('$getWorkflowStaticData was not supplied');
      return staticData;
    },
    require,
    console,
  };
  return vm.runInNewContext(`(function () {\n${code}\n})()`, context, { filename: `${name}.js` });
}

function expressionSource(raw) {
  assert.equal(typeof raw, 'string');
  const trimmed = raw.trim();
  assert(trimmed.startsWith('={{') && trimmed.endsWith('}}'), `Not an n8n expression: ${trimmed.slice(0, 80)}`);
  return trimmed.slice(3, -2).trim();
}

function evalExpression(raw, { input = {}, outputs = {}, now = null } = {}) {
  const source = expressionSource(raw);
  const context = {
    $json: input,
    $: lookupFactory(outputs),
    $now: now || { toFormat: () => '2026-07-12' },
    console,
  };
  return vm.runInNewContext(`(${source})`, context, { filename: 'n8n-expression.js' });
}

function config() {
  return JSON.parse(getNode('CONFIG').parameters.jsonOutput);
}

const CFG = config();
const F = CFG.fields;
let passed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (error) {
    failures.push({ name, error });
    console.error(`FAIL  ${name}`);
    console.error(error.stack || error);
  }
}

function makeWebhookBody(overrides = {}) {
  return {
    event_type: 'every_message_reply_received',
    correlation_id: '00000000-0000-0000-0000-000000000000',
    timestamp: '2026-07-12T10:00:00.000Z',
    conversation_id: 'conv-001',
    campaign: { id: 'camp-001', name: 'HR Test Campaign' },
    sender: { id: 'sender-001', full_name: 'Person-87a2e116' },
    lead: {
      id: 990000001,
      profile_url: 'https://linkedin.com/in/pii-92d458ae/?trk=foo',
      full_name: 'Person-7641cf62',
      company_name: 'HR Test Company',
      position: 'Test Engineer',
      summary: 'Synthetic fixture',
      email_address: '',
    },
    recent_messages: [
      { message: 'Earlier outbound', is_reply: false, message_type: 'REGULAR' },
      { message: 'Actual reply text', is_reply: true, message_type: 'REGULAR' },
    ],
    connection_message: 'Hello',
    is_inmail: false,
    ...overrides,
  };
}

function normalize(body) {
  const out = runCodeNode('Normalize', { input: body });
  assert(Array.isArray(out) && out.length === 1);
  return out[0].json;
}

function person(stage, extras = {}) {
  return {
    id: 80354,
    first_name: 'HR',
    last_name: 'Test Lead',
    name: 'Person-7641cf62',
    custom_fields: {
      [F.stage]: stage,
      [F.conversation]: '',
      [F.campaign]: 'HR Test Campaign',
      ...extras,
    },
  };
}

function leads(labelIds = [CFG.labels.connected]) {
  return [
    { id: 'lead-old', add_time: '2026-01-01T00:00:00Z', is_archived: false, label_ids: labelIds },
    { id: 'lead-archived-newest', add_time: '2026-12-01T00:00:00Z', is_archived: true, label_ids: labelIds },
    { id: 'lead-new', add_time: '2026-07-01T00:00:00Z', is_archived: false, label_ids: labelIds },
  ];
}

test('workflow remains inactive and contains no pinData/stale connection sources', () => {
  assert.equal(workflow.active, false);
  assert(!Object.prototype.hasOwnProperty.call(workflow, 'pinData'));
  assert(!Object.prototype.hasOwnProperty.call(workflow.connections, 'IF Lead Found'));
  assert(!Object.prototype.hasOwnProperty.call(workflow.connections, 'Lead Resp Guard'));
});

test('all creating POST nodes have retryOnFail=false', () => {
  for (const name of ['Org Create', 'Person Create', 'Create Lead', 'Create Activity', 'M6 Activity', 'M8 Task', 'M7 Reply Activity']) {
    assert.equal(getNode(name).parameters.method, 'POST', `${name} is not POST`);
    assert.equal(getNode(name).retryOnFail, false, `${name} retries POST`);
  }
});

test('Normalize emits the documented internal contract', () => {
  const norm = normalize(makeWebhookBody());
  assert.equal(norm.event, 'every_message_reply_received');
  assert.equal(norm.conv, 'conv-001');
  assert.equal(norm.msgs[1].message, 'Actual reply text');
  assert.equal(norm.lead.url, 'https://www.linkedin.com/in/pii-92d458ae');
  assert.equal(norm.lead.slug, 'hr-test-lead');
  assert(!Object.prototype.hasOwnProperty.call(norm, 'recent_messages'));
  assert(!Object.prototype.hasOwnProperty.call(norm, 'conversation_id'));
});

test('F1/F4 M7 reads msgs+conv, renders reply, canonicalizes conversation, selects newest active lead', () => {
  const norm = normalize(makeWebhookBody());
  const out = runCodeNode('M7 Build', {
    outputs: {
      CONFIG: CFG,
      Normalize: norm,
      'M7 Person Get': { data: person('Accepted') },
      'M7 Lead Get': { success: true, data: leads() },
    },
  }).json;
  assert.equal(out.reply_text, 'Actual reply text');
  assert.equal(out.conversation_id, 'sender-001:conv-001');
  assert.equal(out.custom_fields[F.conversation], 'sender-001:conv-001');
  assert.equal(out.lead_id, 'lead-new');
  assert.equal(out.targetStage, 'Replied');
  assert.equal(out.isTransition, true);
});

test('M7 reply placeholders cover attachment and voice note', () => {
  for (const [messageType, expected] of [['ATTACHMENT', '[attachment]'], ['VOICE_NOTE', '[voice note]']]) {
    const norm = normalize(makeWebhookBody({ recent_messages: [{ message: '', is_reply: true, message_type: messageType }] }));
    const out = runCodeNode('M7 Build', {
      outputs: {
        CONFIG: CFG,
        Normalize: norm,
        'M7 Person Get': { data: person('Accepted') },
        'M7 Lead Get': { success: true, data: leads() },
      },
    }).json;
    assert.equal(out.reply_text, expected);
  }
});

test('F3 late accepted cannot downgrade responded label and preserves foreign labels', () => {
  const foreign = 'foreign-label-id';
  const out = runCodeNode('M5 Labels Compute', {
    input: { success: true, data: leads([foreign, CFG.labels.responded]) },
    outputs: {
      CONFIG: CFG,
      'M5 Person Get': { data: person('Replied') },
    },
  }).json;
  assert.equal(out.targetLabel, CFG.labels.responded);
  assert.deepEqual(Array.from(out.label_ids), [foreign, CFG.labels.responded]);
  assert.equal(out.effectiveRank, 4);
});

test('acceptance correction: late accepted fills connected_at without stage/campaign rollback', () => {
  const currentPerson = person('Replied', { [F.connected_at]: null, [F.campaign]: 'Newer Campaign' });
  const norm = normalize(makeWebhookBody({
    event_type: 'connection_request_accepted',
    timestamp: '2026-07-10T20:15:00Z',
    campaign: { id: 'old', name: 'Older Campaign' },
  }));
  const outputs = { CONFIG: CFG, Normalize: norm, 'M5 Person Get': { data: currentPerson } };
  const condition = getNode('M5 IF Rank Accepted').parameters.conditions.conditions[0];
  assert.equal(condition.operator.type, 'boolean');
  assert.equal(evalExpression(condition.leftValue, { outputs }), true);
  const body = JSON.parse(evalExpression(getNode('M5 Person Patch Accepted').parameters.jsonBody, { outputs }));
  assert.equal(body.custom_fields[F.connected_at], '2026-07-10');
  assert(!Object.prototype.hasOwnProperty.call(body.custom_fields, F.stage));
  assert(!Object.prototype.hasOwnProperty.call(body.custom_fields, F.campaign));
});

test('accepted branch skips Person PATCH when no field needs an update', () => {
  const currentPerson = person('Replied', { [F.connected_at]: '2026-07-10', [F.campaign]: 'HR Test Campaign' });
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_accepted' }));
  const outputs = { CONFIG: CFG, Normalize: norm, 'M5 Person Get': { data: currentPerson } };
  const condition = getNode('M5 IF Rank Accepted').parameters.conditions.conditions[0];
  assert.equal(evalExpression(condition.leftValue, { outputs }), false);
});

test('F4 M6 selects newest active lead and emits null when none exists', () => {
  const norm = normalize(makeWebhookBody({
    event_type: 'message_sent',
    recent_messages: [{ message: 'Follow-up copy', is_reply: false, message_type: 'REGULAR' }],
  }));
  const common = { CONFIG: CFG, Normalize: norm, 'M6 Person Get': { data: person('Accepted') } };
  const selected = runCodeNode('M6 Build', { outputs: { ...common, 'M6 Lead Get': { success: true, data: leads() } } });
  assert.equal(selected.lead_id, 'lead-new');
  assert.equal(selected.sentText, 'Follow-up copy');
  const missing = runCodeNode('M6 Build', { outputs: { ...common, 'M6 Lead Get': { success: true, data: [] } } });
  assert.equal(missing.lead_id, null);
});

test('F2 existing-lead path selects newest active lead', () => {
  const out = runCodeNode('Select Existing Lead', {
    input: { success: true, data: leads() },
    outputs: { 'PID Resolved': { person_id: 80354 } },
  }).json;
  assert.equal(out.person_id, 80354);
  assert.equal(out.lead_id, 'lead-new');
  assert.equal(out.__invalid, false);
});

test('F6 Person Create omits emails for empty email and includes it when present', () => {
  const raw = getNode('Person Create').parameters.jsonBody;
  const baseNorm = normalize(makeWebhookBody({ event_type: 'connection_request_sent' }));
  const emptyBody = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: baseNorm } }));
  assert(!Object.prototype.hasOwnProperty.call(emptyBody, 'emails'));
  const withEmailNorm = { ...baseNorm, lead: { ...baseNorm.lead, email_address: 'hr-test@example.com' } };
  const withEmailBody = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: withEmailNorm } }));
  assert.equal(withEmailBody.emails[0].value, 'hr-test@example.com');
});

test('F6 each email search is entered only through its non-empty guard', () => {
  const expected = {
    'Person Search Email': 'IF Email Present',
    'M5 Person Search Email': 'M5 IF Email Present',
    'M6 Person Search Email': 'M6 IF Email Present',
    'M7 Person Search Email': 'M7 IF Email Present',
  };
  const inbound = new Map([...nodes.keys()].map((name) => [name, []]));
  for (const [source, conn] of Object.entries(workflow.connections)) {
    for (const branch of conn.main || []) for (const edge of branch) inbound.get(edge.node).push(source);
  }
  for (const [search, guard] of Object.entries(expected)) assert.deepEqual(inbound.get(search), [guard]);
});

test('F8 every-reply activity body contains actual reply text and selected lead', () => {
  const norm = normalize(makeWebhookBody());
  const m7 = runCodeNode('M7 Build', {
    outputs: {
      CONFIG: CFG,
      Normalize: norm,
      'M7 Person Get': { data: person('Accepted') },
      'M7 Lead Get': { success: true, data: leads() },
    },
  }).json;
  const body = JSON.parse(evalExpression(getNode('M7 Reply Activity').parameters.jsonBody, {
    outputs: { CONFIG: CFG, Normalize: norm, 'M7 Build': m7 },
  }));
  assert.equal(body.done, true);
  assert.equal(body.lead_id, 'lead-new');
  assert.equal(body.participants[0].person_id, 80354);
  assert.equal(body.note, 'Actual reply text');
});

test('Dedupe code drops the same nil-correlation event within one persisted static-data object', () => {
  const body = makeWebhookBody();
  const staticData = {};
  const outputs = { Webhook: { body } };
  const first = runCodeNode('Dedupe', { outputs, staticData });
  const second = runCodeNode('Dedupe', { outputs, staticData });
  assert.equal(first.length, 1);
  assert.equal(second.length, 0);
  assert.equal(Object.keys(staticData.seen).length, 1);
});


// ===================== W1.0.1 additions (F9-F12) =====================

function buildM7(opts) {
  const stage = opts.stage;
  const msgs = opts.msgs;
  const is_inmail = opts.is_inmail || false;
  const campaign = opts.campaign || { id: 'camp-001', name: 'HR Test Campaign' };
  const norm = normalize(makeWebhookBody({ recent_messages: msgs, is_inmail, campaign }));
  return runCodeNode('M7 Build', {
    outputs: {
      CONFIG: CFG, Normalize: norm,
      'M7 Person Get': { data: person(stage) },
      'M7 Lead Get': { success: true, data: leads() },
    },
  }).json;
}

test('T8a F9 invite-reply (no outbound, not InMail, pre-follow-up) -> Replied to invite', () => {
  const out = buildM7({ stage: 'Accepted', msgs: [{ message: 'Thanks for connecting!', is_reply: true, message_type: 'REGULAR' }] });
  assert.equal(out.targetStage, 'Replied to invite');
  assert.equal(out.isTransition, true);
});

test('T8b F9 person already at First follow-up sent -> Replied', () => {
  const out = buildM7({ stage: 'First follow-up sent', msgs: [{ message: 'Reply after follow-up', is_reply: true, message_type: 'REGULAR' }] });
  assert.equal(out.targetStage, 'Replied');
});

test('T8c F9 InMail reply without outbound -> Replied', () => {
  const out = buildM7({ stage: 'Accepted', is_inmail: true, msgs: [{ message: 'InMail reply', is_reply: true, message_type: 'REGULAR' }] });
  assert.equal(out.targetStage, 'Replied');
});

test('T8d F9 message missing is_reply is NOT outbound -> Replied to invite', () => {
  const out = buildM7({ stage: 'Invited', msgs: [{ message: 'ambiguous', message_type: 'REGULAR' }, { message: 'the reply', is_reply: true, message_type: 'REGULAR' }] });
  assert.equal(out.targetStage, 'Replied to invite');
});

test('F10/F12 M7 Reply Context renders reply text + placeholders and escapes & < >', () => {
  const evil = '<@U123> & <https://x|y>';
  const norm = normalize(makeWebhookBody({
    recent_messages: [{ message: evil, is_reply: true, message_type: 'REGULAR' }],
    campaign: { id: 'c', name: 'Camp & <1>' },
    sender: { id: 's', full_name: 'Send<er>' },
    lead: { id: 990000001, profile_url: 'https://linkedin.com/in/pii-92d458ae/', full_name: 'A<b>&c', company_name: 'C&C', position: 'Eng<x>', summary: 's', email_address: '' },
  }));
  const out = runCodeNode('M7 Reply Context', { input: norm, outputs: { CONFIG: CFG, Normalize: norm } }).json;
  assert.equal(out.reply_text, evil);
  assert(out.alert_text.includes('&amp;'), 'ampersand escaped');
  assert(out.alert_text.includes('&lt;@U123&gt;'), 'mention neutralized');
  assert(!/<@U123>/.test(out.alert_text), 'no live mention token in alert');
  assert(!/<https:\/\/x\|y>/.test(out.alert_text), 'no live link token in alert');
  const att = runCodeNode('M7 Reply Context', { input: norm, outputs: { CONFIG: CFG, Normalize: normalize(makeWebhookBody({ recent_messages: [{ message: '', is_reply: true, message_type: 'ATTACHMENT' }] })) } }).json;
  assert.equal(att.reply_text, '[attachment]');
});

test('F11 Dedupe uses no require() and conversation_id participates in the key', () => {
  const code = getNode('Dedupe').parameters.jsCode;
  assert(!/require\s*\(/.test(code), 'no require()');
  const staticData = {};
  const a = makeWebhookBody({ correlation_id: '00000000-0000-0000-0000-000000000000', conversation_id: 'conv-A' });
  const b = makeWebhookBody({ correlation_id: '00000000-0000-0000-0000-000000000000', conversation_id: 'conv-B' });
  const r1 = runCodeNode('Dedupe', { outputs: { Webhook: { body: a } }, staticData });
  const r2 = runCodeNode('Dedupe', { outputs: { Webhook: { body: b } }, staticData });
  const r3 = runCodeNode('Dedupe', { outputs: { Webhook: { body: a } }, staticData });
  assert.equal(r1.length, 1);
  assert.equal(r2.length, 1);
  assert.equal(r3.length, 0);
});

test('F10 tail: M8 Slack / M8 Slack Text absent; M8 Task is non-retried POST terminal', () => {
  assert(!nodes.has('M8 Slack'), 'M8 Slack removed');
  assert(!nodes.has('M8 Slack Text'), 'M8 Slack Text removed');
  const t = getNode('M8 Task');
  assert.equal(t.parameters.method, 'POST');
  assert.equal(t.retryOnFail, false);
  assert(!Object.prototype.hasOwnProperty.call(workflow.connections, 'M8 Task'), 'M8 Task terminal');
});

test('F10 critical alert wiring: Switch[3]->Reply Context->Critical Slack->IF Email Present; continue-on-fail', () => {
  assert.equal(workflow.connections['Switch'].main[3][0].node, 'M7 Reply Context');
  assert.equal(workflow.connections['M7 Reply Context'].main[0][0].node, 'M7 Critical Slack');
  assert.equal(workflow.connections['M7 Critical Slack'].main[0][0].node, 'M7 IF Email Present');
  assert.equal(getNode('M7 Critical Slack').onError, 'continueRegularOutput');
  const cc = getNode('M7 Reply Context').parameters.jsCode;
  for (const ref of ["$('M7 Person Get')", "$('M7 Lead Get')", "$('M7 Build')"]) assert(!cc.includes(ref), 'reply context must not reference ' + ref);
});

test('F10.6 graph: no cycles in connections', () => {
  const color = new Map([...nodes.keys()].map((n) => [n, 0]));
  const cyc = [];
  function dfs(u) {
    color.set(u, 1);
    for (const branch of (workflow.connections[u]?.main || [])) for (const e of branch) {
      const v = e.node;
      if (color.get(v) === 1) cyc.push(u + '->' + v);
      else if ((color.get(v) ?? 2) === 0) dfs(v);
    }
    color.set(u, 2);
  }
  for (const n of nodes.keys()) if (color.get(n) === 0) dfs(n);
  assert.deepEqual(cyc, []);
});

test('F13 Create Lead body: valid JSON, org OMITTED when null, cold + channel(number) + channel_id present', () => {
  const raw = getNode('Create Lead').parameters.jsonBody;
  assert(raw.trim().startsWith('={{ (() =>'), 'Create Lead must be a Code-built IIFE body');
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: { id: 990000001, profile_url: 'https://linkedin.com/in/pii-fef550a8', full_name: 'Lule Salihu', company_name: '', position: '', summary: '', email_address: '' } }));
  // org null -> omitted, still valid JSON
  let body = JSON.parse(evalExpression(raw, { input: { lead_id: null }, outputs: { CONFIG: CFG, Normalize: norm, 'PID Resolved': { person_id: 81603, organization_id: null } } }));
  assert(!Object.prototype.hasOwnProperty.call(body, 'organization_id'), 'organization_id omitted when null');
  assert.deepEqual(body.label_ids, [CFG.labels.cold]);
  assert.equal(body.channel, CFG.lead_channel);
  assert.equal(typeof body.channel, 'number');
  assert.equal(body.channel_id, CFG.lead_channel_id_value);
  assert.equal(body.person_id, 81603);
  assert.equal(body.title, 'Lule Salihu');  // no ' — null'
  // org present -> included
  body = JSON.parse(evalExpression(raw, { input: { lead_id: null }, outputs: { CONFIG: CFG, Normalize: norm, 'PID Resolved': { person_id: 81603, organization_id: 20999 } } }));
  assert.equal(body.organization_id, 20999);
});

test('F13 Create Activity body: valid JSON, participants + type + guarded lead_id', () => {
  const raw = getNode('Create Activity').parameters.jsonBody;
  assert(raw.trim().startsWith('={{ (() =>'), 'Create Activity must be a Code-built IIFE body');
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent' }));
  const body = JSON.parse(evalExpression(raw, { input: { lead_id: 'lead-x' }, outputs: { CONFIG: CFG, Normalize: norm, 'PID Resolved': { person_id: 81603 } } }));
  assert.equal(body.done, true);
  assert.equal(body.participants[0].person_id, 81603);
  assert.equal(body.lead_id, 'lead-x');
  assert.equal(body.type, CFG.activity_type_msg);
});

test('F13 no httpRequest jsonBody uses a bare inline {{ }} field (whole-object idiom only)', () => {
  const offenders = [];
  for (const node of workflow.nodes) {
    if (node.type !== 'n8n-nodes-base.httpRequest') continue;
    const jb = node.parameters && node.parameters.jsonBody;
    if (typeof jb !== 'string') continue;
    const body = jb.trim();
    if (body.startsWith('={{ (() =>') || body.startsWith('={{ JSON.stringify(')) continue;
    const fields = [...body.matchAll(/\{\{\s*([\s\S]*?)\s*\}\}/g)].map((m) => m[1]);
    const bare = fields.filter((f) => !f.startsWith('JSON.stringify') && !f.startsWith('('));
    if (bare.length) offenders.push(node.name + ':' + JSON.stringify(bare));
  }
  assert.deepEqual(offenders, [], 'nodes with bare inline JSON fields: ' + offenders.join(' | '));
});

test('F12.1 every Slack node text is an evaluated expression (no unprefixed {{)', () => {
  for (const node of workflow.nodes) {
    if (node.type !== 'n8n-nodes-base.slack') continue;
    const t = node.parameters && node.parameters.text;
    assert.equal(typeof t, 'string', node.name + ' has no text');
    if (t.includes('{{')) assert(t.startsWith('={{'), node.name + ' text has {{ without leading = : ' + t.slice(0, 24));
  }
  const cs = getNode('M7 Critical Slack').parameters.text;
  assert(cs.startsWith('={{') && cs.includes('alert_text'), 'M7 Critical Slack must evaluate alert_text');
});

test('F10.6 graph: unknown-person terminal is M7 Slack Warn and references no M7 Build', () => {
  const seen = new Set(); const stack = ['M7 Reply Context'];
  while (stack.length) { const u = stack.pop(); for (const branch of (workflow.connections[u]?.main || [])) for (const e of branch) if (!seen.has(e.node)) { seen.add(e.node); stack.push(e.node); } }
  assert(seen.has('M7 Slack Warn'), 'unknown-person warn reachable from Switch[3]');
  assert(!workflow.connections['M7 Slack Warn'], 'M7 Slack Warn is terminal');
  assert(!JSON.stringify(getNode('M7 Slack Warn').parameters).includes('M7 Build'), 'no M7 Build ref on unknown path');
  assert(nodes.has('M7 No Lead Warn'), 'no-lead terminal exists and is distinct');
});


console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) process.exitCode = 1;
