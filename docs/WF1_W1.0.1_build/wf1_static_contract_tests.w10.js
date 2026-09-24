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

const workflowPath = process.argv[2] || path.join(__dirname, 'WF-1 HeyReach Receiver - W1.0 patched.json');
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

console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) process.exitCode = 1;
