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
  const _exp = [foreign, CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];
  assert.equal(out.label_ids.length, _exp.length, 'W1.0.7 union set: ' + out.label_ids);
  _exp.forEach((x) => assert(out.label_ids.includes(x), 'missing ' + x));
  assert.equal(out.changed, true);
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
  const currentPerson = person('Replied', { [F.connected_at]: '2026-07-10', [F.campaign]: 'HR Test Campaign', [F.company]: 'HR Test Company', [F.position]: 'Test Engineer', [F.li_url]: 'u', [F.public_id]: 'p', [F.member_id]: 1 });
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

test('W1.0.4 M7 Build alert_text: escaped user parts, NO reply text, NO InMail, deep link vs search', () => {
  const norm = normalize(makeWebhookBody({
    recent_messages: [{ message: 'secret reply body', is_reply: true, message_type: 'REGULAR' }],
    campaign: { id: 'c', name: 'Camp & <1>' }, sender: { id: 's', full_name: 'Send<er>' }, is_inmail: true,
    lead: { id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'A<b>&c', company_name: 'C&C', position: 'Eng<x>', summary: 's', email_address: '' },
  }));
  const build = (leadData) => runCodeNode('M7 Build', { outputs: { CONFIG: CFG, Normalize: norm, 'M7 Person Get': { data: person('Accepted') }, 'M7 Lead Get': { success: true, data: leadData } } }).json;
  let o = build(leads());  // lead exists
  assert(o.alert_text.includes('/leads/inbox/lead-new'), 'deep link to selected lead: ' + o.alert_text);
  assert(o.alert_text.includes('&amp;') && o.alert_text.includes('&lt;'), 'user parts escaped');
  assert(!o.alert_text.includes('secret reply body'), 'NO reply text in alert');
  assert(!/InMail/.test(o.alert_text), 'NO InMail marker');
  assert(!/\{\{/.test(o.alert_text), 'no unrendered braces');
  o = build([]);  // no lead
  assert(o.alert_text.includes('/person/') && o.alert_text.includes('|Open person>') && o.alert_text.includes('no lead'), 'W1.0.5 person deep link when no lead');
  assert(!o.alert_text.includes('search?term'), 'no search link');
  assert(o.reply_text === 'secret reply body', 'reply_text still emitted (for the reply activity)');
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

test('W1.0.4 alert wiring: Switch[3]->IF Email Present; M7 Build->Critical Slack->IF Patch; =-prefix; continue-on-fail; no writes before slack', () => {
  assert.equal(workflow.connections['Switch'].main[3][0].node, 'M7 IF Email Present');
  assert(!workflow.connections['M7 Reply Context'] && !nodes.has('M7 Reply Context'), 'M7 Reply Context removed');
  assert.equal(workflow.connections['M7 Build'].main[0][0].node, 'M7 Critical Slack');
  assert.equal(workflow.connections['M7 Critical Slack'].main[0][0].node, 'M7 IF Patch');
  assert.equal(getNode('M7 Critical Slack').parameters.text.trim(), '={{ $json.alert_text }}');
  assert.equal(getNode('M7 Critical Slack').onError, 'continueRegularOutput');
  // no PATCH/POST precedes M7 Critical Slack on the reply path
  const seen = new Set(); const stack = ['M7 IF Email Present'];
  while (stack.length) {
    const u = stack.pop(); if (u === 'M7 Critical Slack') continue;
    for (const br of (workflow.connections[u]?.main || [])) for (const e of br) {
      if (e.node === 'M7 Critical Slack' || seen.has(e.node)) continue;
      seen.add(e.node);
      const nd = getNode(e.node);
      assert(!(nd.type === 'n8n-nodes-base.httpRequest' && ['PATCH', 'POST'].includes(nd.parameters.method)), 'write ' + e.node + ' precedes Critical Slack');
      stack.push(e.node);
    }
  }
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

// ===================== W1.0.3 additions (R1-R5) =====================
function pget(cfObj, extra) { return { data: { id: 7, custom_fields: Object.assign({}, cfObj || {}), ...(extra || {}) } }; }

test('R1 Person Create sets Source enum from CONFIG (create-only); absent from patch/build bodies', () => {
  if (!F.source) { assert.fail('CONFIG.fields.source missing'); }
  assert.equal(CFG.source_value, 446);
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent' }));
  const body = JSON.parse(evalExpression(getNode('Person Create').parameters.jsonBody, { outputs: { CONFIG: CFG, Normalize: norm } }));
  assert.equal(body.custom_fields[F.source], CFG.source_value);
  for (const nm of ['Person Patch Invited', 'M5 Person Patch Accepted']) {
    assert(!getNode(nm).parameters.jsonBody.includes('f.source'), nm + ' must not set source');
  }
  assert(!getNode('M7 Build').parameters.jsCode.includes('source_value'));
  assert(!getNode('M6 Build').parameters.jsCode.includes('source_value'));
});

test('R2 Person Patch Invited fills empty fields, never overwrites non-empty', () => {
  const raw = getNode('Person Patch Invited').parameters.jsonBody;
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: { id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'X', company_name: 'NewCo', position: 'NewPos', summary: 's', email_address: '' }, campaign: { id: 'c', name: 'NewCamp' } }));
  let cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': pget({ [F.stage]: 'Accepted' }) } })).custom_fields;
  assert.equal(cf[F.company], 'NewCo');
  assert.equal(cf[F.position], 'NewPos');
  assert.equal(cf[F.campaign], 'NewCamp');
  assert(!(F.stage in cf), 'stage not advanced when already past Invited');
  cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': pget({ [F.stage]: 'Accepted', [F.company]: 'OldCo', [F.position]: 'OldPos', [F.campaign]: 'OldCamp' }) } })).custom_fields;
  assert(!(F.company in cf) && !(F.position in cf) && !(F.campaign in cf), 'non-empty values not overwritten');
});

test('R2 IF Rank Allows Invited gate is composite (fillable-only fires; all-present is false)', () => {
  const raw = getNode('IF Rank Allows Invited').parameters.conditions.conditions[0].leftValue;
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: { id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'X', company_name: 'NewCo', position: '', summary: '', email_address: '' }, campaign: { id: 'c', name: '' } }));
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { [F.stage]: 'Accepted' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), true);
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { [F.stage]: 'Accepted', [F.company]: 'C', [F.position]: 'P', [F.li_url]: 'u', [F.public_id]: 's', [F.member_id]: 1, [F.campaign]: 'K' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), false);
});

test('R3 M6 Build flags message_first only when person has no stage', () => {
  const norm = normalize(makeWebhookBody({ event_type: 'message_sent', recent_messages: [{ message: 'hi', is_reply: false, message_type: 'REGULAR' }] }));
  const noStage = runCodeNode('M6 Build', { outputs: { CONFIG: CFG, Normalize: norm, 'M6 Person Get': { data: { id: 7, custom_fields: {} } }, 'M6 Lead Get': { success: true, data: leads() } } });
  assert.equal(noStage.message_first, true);
  const withStage = runCodeNode('M6 Build', { outputs: { CONFIG: CFG, Normalize: norm, 'M6 Person Get': { data: person('Accepted') }, 'M6 Lead Get': { success: true, data: leads() } } });
  assert.equal(withStage.message_first, false);
});

test('R3 message-first warn is a non-blocking tee with no cycle', () => {
  const c = workflow.connections;
  assert.equal(c['M6 Build'].main[0][0].node, 'M6 IF Message First');
  const t = c['M6 IF Message First'].main;
  const trueTargets = t[0].map((x) => x.node);
  assert(trueTargets.includes('M6 Message First Warn') && trueTargets.includes('M6 IF Lead ID'), 'true output tees to warn AND continue');
  assert.deepEqual(t[1].map((x) => x.node), ['M6 IF Lead ID'], 'false output continues only');
  assert(!c['M6 Message First Warn'], 'warn node is a leaf');
  const color = new Map([...nodes.keys()].map((n) => [n, 0])); const cyc = [];
  function dfs(u) { color.set(u, 1); for (const br of (c[u]?.main || [])) for (const e of br) { const v = e.node; if (color.get(v) === 1) cyc.push(u + '->' + v); else if ((color.get(v) ?? 2) === 0) dfs(v); } color.set(u, 2); }
  for (const n of nodes.keys()) if (color.get(n) === 0) dfs(n);
  assert.deepEqual(cyc, []);
});

test('R4 body builders strip empty-string custom fields', () => {
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: { id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'X', company_name: '', position: '', summary: '', email_address: '' } }));
  const pc = JSON.parse(evalExpression(getNode('Person Create').parameters.jsonBody, { outputs: { CONFIG: CFG, Normalize: norm } }));
  for (const k of Object.keys(pc.custom_fields)) assert.notEqual(pc.custom_fields[k], '', 'no empty string survives in Person Create');
  assert(!(F.company in pc.custom_fields), 'empty company stripped');
  assert.equal(pc.custom_fields[F.source], 446, 'source (non-empty) kept');
  // R4 line present in all five builders
  for (const nm of ['Person Create', 'Person Patch Invited', 'M5 Person Patch Accepted']) assert(getNode(nm).parameters.jsonBody.includes("=== ''"), nm + ' strips');
  for (const nm of ['M6 Build', 'M7 Build']) assert(getNode(nm).parameters.jsCode.includes("=== ''"), nm + ' strips');
});

test('W1.0.4 R5 alert parenthetical (in M7 Build): omit empty ( @ ); partials render', () => {
  const mk = (pos, comp) => normalize(makeWebhookBody({ recent_messages: [{ message: 'hi', is_reply: true, message_type: 'REGULAR' }], campaign: { id: 'c', name: 'TEST' }, sender: { id: 's', full_name: 'Sergey' }, lead: { id: 1, profile_url: 'https://linkedin.com/in/x', full_name: 'Lule', company_name: comp, position: pos, summary: '', email_address: '' } }));
  const run = (n) => runCodeNode('M7 Build', { outputs: { CONFIG: CFG, Normalize: n, 'M7 Person Get': { data: person('Accepted') }, 'M7 Lead Get': { success: true, data: leads() } } }).json.alert_text;
  const a0 = run(mk('', ''));
  assert(!/\(\s*@?\s*\)/.test(a0), 'no empty parens: ' + a0);
  assert(a0.includes('💬 Lule ·'), 'no paren when neither part: ' + a0);
  assert(run(mk('CEO', '')).includes('(CEO)'), 'position-only');
  assert(run(mk('CEO', 'Acme')).includes('(CEO @ Acme)'), 'both');
});

test('W1.0.4 unknown-person warn: compact "not in Pipedrive", Normalize-only, search+LinkedIn links, terminal', () => {
  const warn = getNode('M7 Slack Warn').parameters.text;
  assert(warn.trim().startsWith('={{'), '= prefix');
  assert(!warn.includes('M7 Build'), 'no M7 Build reference on unknown path');
  assert(!workflow.connections['M7 Slack Warn'], 'terminal leaf');
  // render it (Normalize + CONFIG only)
  const n = normalize(makeWebhookBody({ campaign: { id: 'c', name: 'TEST' }, sender: { id: 's', full_name: 'Sergey' }, lead: { id: 1, profile_url: 'https://linkedin.com/in/x', full_name: 'Nobody', company_name: '', position: '', summary: '', email_address: '' } }));
  const txt = evalExpression(warn, { input: n, outputs: { CONFIG: CFG, Normalize: n } });
  assert(txt.includes('not in Pipedrive'), 'compact not-in-Pipedrive: ' + txt);
  assert(!txt.includes('search?term') && !/janeasystems\.pipedrive\.com/.test(txt), 'W1.0.5: no Pipedrive link in unknown warn');
  assert(txt.includes('LinkedIn'), 'LinkedIn link kept');
  assert(!/\{\{/.test(txt) && !/InMail/.test(txt), 'no braces, no InMail');
});

test('W1.0.5 verified link templates only: no search?term anywhere; base only concatenated with /leads/inbox/ or /person/', () => {
  assert.equal(CFG.pipedrive_base, 'https://janeasystems.pipedrive.com');
  const full = JSON.stringify(workflow);
  assert(!full.includes('search?term'), "'search?term' must appear in NO node");
  const mb = getNode('M7 Build').parameters.jsCode;
  assert(mb.includes("/leads/inbox/' + selectedLead.id") && mb.includes("/person/' + (person.id"), 'M7 Build uses both verified templates');
  // every base concatenation must be a verified path template
  const re = /(?:pdBase|pipedrive_base)\s*\+\s*'([^']*)'/g; let m; const bad = [];
  while ((m = re.exec(full)) !== null) if (!(m[1].startsWith('/leads/inbox/') || m[1].startsWith('/person/'))) bad.push(m[1]);
  assert.deepEqual(bad, [], 'non-verified base path literals: ' + JSON.stringify(bad));
  const warn = getNode('M7 Slack Warn').parameters.text;
  assert(!warn.includes('pipedrive_base') && !warn.includes('/person/') && !warn.includes('/leads/'), 'unknown warn has no Pipedrive link');
});

test('W1.0.4 no alert source references reply_text or InMail', () => {
  const mb = getNode('M7 Build').parameters.jsCode;
  const alertAssign = mb.split('const alert_text =')[1].split(';')[0];
  assert(!alertAssign.includes('reply_text') && !/InMail/.test(alertAssign), 'M7 Build alert_text excludes reply_text/InMail');
  assert(!/InMail/.test(getNode('M7 Slack Warn').parameters.text), 'unknown warn excludes InMail');
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
  const seen = new Set(); const stack = ['M7 IF Email Present'];
  while (stack.length) { const u = stack.pop(); for (const branch of (workflow.connections[u]?.main || [])) for (const e of branch) if (!seen.has(e.node)) { seen.add(e.node); stack.push(e.node); } }
  assert(seen.has('M7 Slack Warn'), 'unknown-person warn reachable from Switch[3]');
  assert(!workflow.connections['M7 Slack Warn'], 'M7 Slack Warn is terminal');
  assert(!JSON.stringify(getNode('M7 Slack Warn').parameters).includes('M7 Build'), 'no M7 Build ref on unknown path');
  assert(nodes.has('M7 No Lead Warn'), 'no-lead terminal exists and is distinct');
});

// ===================== W1.0.6 additions (omit empty note) =====================

test('W1.0.6 Create Activity omits note when connection_message empty/absent; keeps it when present', () => {
  const raw = getNode('Create Activity').parameters.jsonBody;
  assert(raw.trim().startsWith('={{ (() =>'), 'Create Activity is a Code-built IIFE');
  const build = (cm, lead_id) => JSON.parse(evalExpression(raw, { input: { lead_id }, outputs: { CONFIG: CFG, Normalize: normalize(makeWebhookBody({ event_type: 'connection_request_sent', connection_message: cm })), 'PID Resolved': { person_id: 81603 } } }));
  let body = build('', 'lead-x');
  assert(!Object.prototype.hasOwnProperty.call(body, 'note'), 'note omitted when connection_message empty');
  assert.equal(body.participants[0].person_id, 81603);
  assert.equal(body.lead_id, 'lead-x');            // other guarded field intact
  assert.equal(body.done, true);
  body = build(null, null);
  assert(!Object.prototype.hasOwnProperty.call(body, 'note'), 'note omitted when connection_message absent (null)');
  assert(!Object.prototype.hasOwnProperty.call(body, 'lead_id'), 'lead_id still omitted when null');
  body = build('Hi there', 'lead-x');
  assert.equal(body.note, 'Hi there', 'note kept when connection_message present');
});

test('W1.0.6 M7 Reply Activity: Code-built IIFE; omits note when reply_text empty, keeps when present', () => {
  const raw = getNode('M7 Reply Activity').parameters.jsonBody;
  assert(raw.trim().startsWith('={{ (() =>'), 'M7 Reply Activity converted to Code-built IIFE');
  const norm = normalize(makeWebhookBody({ campaign: { id: 'c', name: 'Camp' } }));
  const mk = (reply_text) => JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'M7 Build': { person_id: 7, lead_id: 'lead-1', reply_text } } }));
  let body = mk('');
  assert(!Object.prototype.hasOwnProperty.call(body, 'note'), 'note omitted when reply_text empty');
  assert.equal(body.participants[0].person_id, 7);
  assert.equal(body.lead_id, 'lead-1');
  assert.equal(body.done, true);
  assert.equal(body.type, CFG.activity_type_msg);
  body = mk('Yes, interested');
  assert.equal(body.note, 'Yes, interested', 'note kept when reply_text present');
});

test('W1.0.6 no activity/task body sends an unconditional empty-able note (guarded only)', () => {
  for (const nm of ['Create Activity', 'M7 Reply Activity', 'M6 Activity', 'M8 Task']) {
    const jb = getNode(nm).parameters.jsonBody;
    if (typeof jb !== 'string') continue;
    assert(!jb.includes("note: n.invite || ''"), nm + ' has unconditional invite note');
    assert(!jb.includes("note: $('M7 Build').item.json.reply_text"), nm + ' has unconditional reply_text note');
    if (/\bnote\b/.test(jb)) assert(jb.includes("if (note !== '') body.note = note"), nm + ' sets note without empty-guard');
  }
});

// ===================== W1.0.7 additions (union labels + task kill-switch) =====================
const L7 = CFG.labels;
const FOREIGN = 'zzzz-foreign-label-0000';
function m7labels(stage, incomingStage, existingLabels) {
  return runCodeNode('M7 Labels Compute', { outputs: {
    CONFIG: CFG,
    'M7 Person Get': { data: { id: 7, custom_fields: stage ? { [F.stage]: stage } : {} } },
    'M7 Build': { targetStage: incomingStage },
    'M7 Lead Get': { data: [{ id: 'lead-1', is_archived: false, add_time: '2026-07-01', label_ids: existingLabels }] },
  } }).json;
}
function m5labels(stage, existingLabels) {
  return runCodeNode('M5 Labels Compute', {
    input: { data: [{ id: 'lead-1', is_archived: false, add_time: '2026-07-01', label_ids: existingLabels }] },
    outputs: { CONFIG: CFG, 'M5 Person Get': { data: { id: 7, custom_fields: stage ? { [F.stage]: stage } : {} } } },
  }).json;
}
function eqSet(a, b) { return a.length === b.length && a.every((x) => b.includes(x)); }

test('W1.0.7 union: replied lead ends with cold+connected+responded (+foreign preserved)', () => {
  const o = m7labels('Accepted', 'Replied to invite', [L7.connected, FOREIGN]);
  assert(o.label_ids.includes(L7.cold) && o.label_ids.includes(L7.connected) && o.label_ids.includes(L7.responded), 'all three: ' + o.label_ids);
  assert(o.label_ids.includes(FOREIGN), 'foreign preserved');
  assert.equal(o.changed, true);
});

test('W1.0.7 union: late accepted on responded lead is no-op (changed=false, set unchanged)', () => {
  const o = m5labels('Replied to invite', [L7.cold, L7.connected, L7.responded]);
  assert.equal(o.changed, false);
  assert(eqSet(o.label_ids, [L7.cold, L7.connected, L7.responded]), 'unchanged: ' + o.label_ids);
});

test('W1.0.7 union: accepted after only-cold -> [cold, connected]', () => {
  const o = m5labels(null, [L7.cold]);
  assert(eqSet(o.label_ids, [L7.cold, L7.connected]), o.label_ids);
  assert.equal(o.changed, true);
});

test('W1.0.7 union: foreign-created lead missing cold -> first touch backfills cold', () => {
  const o = m5labels(null, [FOREIGN]);
  assert(o.label_ids.includes(L7.cold) && o.label_ids.includes(L7.connected), 'cold backfilled: ' + o.label_ids);
  assert(o.label_ids.includes(FOREIGN), 'foreign preserved');
  assert.equal(o.changed, true);
});

test('W1.0.7 union: code uses union, no replace-semantics remain', () => {
  for (const nm of ['M5 Labels Compute', 'M7 Labels Compute']) {
    const c = getNode(nm).parameters.jsCode;
    assert(c.includes('[...existing, ...targetSet]'), nm + ' union');
    assert(!c.includes('ourLabels.includes(id)).concat'), nm + ' old replace gone');
  }
});

test('W1.0.7 kill-switch: CONFIG false; M8 Task gated; both flag values route correctly; node retained', () => {
  assert.equal(JSON.parse(getNode('CONFIG').parameters.jsonOutput).create_assignment_task, false, 'ships false');
  assert.deepEqual(workflow.connections['M8 IF Lead ID'].main[0].map((x) => x.node), ['M8 IF Task Enabled']);
  const en = workflow.connections['M8 IF Task Enabled'].main;
  assert.deepEqual(en[0].map((x) => x.node), ['M8 Task']);
  assert.deepEqual((en[1] || []).map((x) => x.node), []);
  assert(nodes.has('M8 Task'), 'M8 Task retained for W1.1');
  const cond = getNode('M8 IF Task Enabled').parameters.conditions.conditions[0].leftValue;
  assert.equal(evalExpression(cond, { outputs: { CONFIG: { create_assignment_task: false } } }), false, 'false -> unreachable');
  assert.equal(evalExpression(cond, { outputs: { CONFIG: { create_assignment_task: true } } }), true, 'true -> reachable');
});

test('W1.0.7 skip-patch gates wired; no cycle; tail topology intact', () => {
  assert.deepEqual(workflow.connections['M5 IF Lead ID'].main[0].map((x) => x.node), ['M5 IF Labels Changed']);
  assert.deepEqual(workflow.connections['M5 IF Labels Changed'].main[0].map((x) => x.node), ['M5 Lead Patch']);
  assert.deepEqual((workflow.connections['M5 IF Labels Changed'].main[1] || []).map((x) => x.node), []);
  assert.deepEqual(workflow.connections['M7 IF Lead ID'].main[0].map((x) => x.node), ['M7 IF Labels Changed']);
  assert.deepEqual(workflow.connections['M7 IF Labels Changed'].main[0].map((x) => x.node), ['M7 Lead Patch']);
  assert.deepEqual(workflow.connections['M7 IF Labels Changed'].main[1].map((x) => x.node), ['M7 IF Reply Activity Lead']);
  const color = new Map([...nodes.keys()].map((n) => [n, 0])); const cyc = [];
  function dfs(u) { color.set(u, 1); for (const br of (workflow.connections[u]?.main || [])) for (const e of br) { const v = e.node; if (color.get(v) === 1) cyc.push(u + '->' + v); else if ((color.get(v) ?? 2) === 0) dfs(v); } color.set(u, 2); }
  for (const n of nodes.keys()) if (color.get(n) === 0) dfs(n);
  assert.deepEqual(cyc, []);
});

test('W1.0.7 sent-path Create Lead still starts [cold] (unchanged)', () => {
  assert(getNode('Create Lead').parameters.jsonBody.includes('[cfg.labels.cold]'), 'Create Lead cold unchanged');
});


console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) process.exitCode = 1;
