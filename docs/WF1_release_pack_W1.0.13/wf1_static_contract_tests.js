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
  const out = runCodeNode('Normalize', { input: body, outputs: { CONFIG: CFG } });
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

function leads(labelIds = [CFG.labels.connected], campaignName = 'HR Test Campaign') {
  const _CK = CFG.fields.lead_campaign;
  return [
    { id: 'lead-old', add_time: '2026-01-01T00:00:00Z', is_archived: false, label_ids: labelIds, [_CK]: 'Some Other Campaign' },
    { id: 'lead-archived-newest', add_time: '2026-12-01T00:00:00Z', is_archived: true, label_ids: labelIds, [_CK]: campaignName },
    { id: 'lead-new', add_time: '2026-07-01T00:00:00Z', is_archived: false, label_ids: labelIds, [_CK]: campaignName },
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
    input: { success: true, data: leads([foreign, CFG.labels.responded], 'HR Test Campaign') },
    outputs: {
      CONFIG: CFG,
      Normalize: normalize(makeWebhookBody({})),
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

test('acceptance correction: late accepted fills connected_at, stage forward-only, campaign ALWAYS-overwrites (W1.0.11.1)', () => {
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
  assert(!Object.prototype.hasOwnProperty.call(body.custom_fields, F.stage), 'stage forward-only (no rollback)');
  assert.equal(body.custom_fields[F.campaign], 'Older Campaign', 'W1.0.11.1: campaign always-overwrites incoming, even a late/older event (Newer -> Older)');
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

test('F2 existing-lead path selects the campaign-matching lead (W1.0.11)', () => {
  const out = runCodeNode('Select Existing Lead', {
    input: { success: true, data: leads() },
    outputs: { CONFIG: CFG, Normalize: normalize(makeWebhookBody({})), 'PID Resolved': { person_id: 80354 } },
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
  let o = build(leads([CFG.labels.connected], 'Camp & <1>'));  // lead exists (campaign-matched for W1.0.11 selectLead)
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
  assert(!(F.company in cf) && !(F.position in cf), 'company/position (fill-if-empty) not overwritten');
  assert.equal(cf[F.campaign], 'NewCamp', 'W1.0.11.1: campaign ALWAYS-overwrites a differing value (OldCamp -> NewCamp)');
  // W1.0.11.1 idempotent: same incoming campaign as current -> no redundant campaign write
  cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': pget({ [F.stage]: 'Accepted', [F.campaign]: 'NewCamp' }) } })).custom_fields;
  assert(!(F.campaign in cf), 'W1.0.11.1: same-campaign is idempotent (no redundant PATCH field)');
});

test('R2 IF Rank Allows Invited gate is composite (fillable-only fires; all-present is false)', () => {
  const raw = getNode('IF Rank Allows Invited').parameters.conditions.conditions[0].leftValue;
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: { id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'X', company_name: 'NewCo', position: '', summary: '', email_address: '' }, campaign: { id: 'c', name: '' } }));
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { [F.stage]: 'Accepted' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), true);
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { [F.stage]: 'Accepted', [F.company]: 'C', [F.position]: 'P', [F.li_url]: 'u', [F.public_id]: 's', [F.member_id]: 1, [F.campaign]: 'K', [CFG.fields.person_medium]: 'x' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), false);
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
  assert.equal(body.title, 'camp-001 - HR Test Campaign - Lule Salihu');  // W1.0.11 title convention: id - name - person
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
  const mk = (v) => JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'M7 Build': { person_id: 7, lead_id: 'lead-1', reply_note: v } } }));  // W1.0.8: note source is reply_note
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
    Normalize: normalize(makeWebhookBody({ campaign: { id: 'c', name: 'HR Test Campaign' } })),
    'M7 Person Get': { data: { id: 7, custom_fields: stage ? { [F.stage]: stage } : {} } },
    'M7 Build': { targetStage: incomingStage },
    'M7 Lead Get': { data: [{ id: 'lead-1', is_archived: false, add_time: '2026-07-01', label_ids: existingLabels, [CFG.fields.lead_campaign]: 'HR Test Campaign' }] },
  } }).json;
}
function m5labels(stage, existingLabels) {
  return runCodeNode('M5 Labels Compute', {
    input: { data: [{ id: 'lead-1', is_archived: false, add_time: '2026-07-01', label_ids: existingLabels, [CFG.fields.lead_campaign]: 'HR Test Campaign' }] },
    outputs: { CONFIG: CFG, Normalize: normalize(makeWebhookBody({ campaign: { id: 'c', name: 'HR Test Campaign' } })), 'M5 Person Get': { data: { id: 7, custom_fields: stage ? { [F.stage]: stage } : {} } } },
  }).json;
}
function eqSet(a, b) { return a.length === b.length && a.every((x) => b.includes(x)); }

test('W1.0.9 event-truth: reply on already-connected lead keeps all three (foreign preserved)', () => {
  // person accepted earlier (lead already has connected), then replies -> union keeps all three
  const o = m7labels('Accepted', 'Replied to invite', [L7.cold, L7.connected, FOREIGN]);
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

// ===================== W1.0.8 additions (org website / person location / multi-reply) =====================
function normLead(extra) {
  return normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: Object.assign({
    id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'X', company_name: 'Acme',
    position: 'Eng', summary: 's', email_address: '' }, extra || {}) }));
}
function m7build(msgs) {
  const norm = normalize(makeWebhookBody({ recent_messages: msgs }));
  return runCodeNode('M7 Build', { outputs: { CONFIG: CFG, Normalize: norm, 'M7 Person Get': { data: person('Accepted') }, 'M7 Lead Get': { success: true, data: leads() } } }).json;
}

test('W1.0.8 B1 Org Create: website from company_url; omitted when empty/null', () => {
  const raw = getNode('Org Create').parameters.jsonBody;
  assert(raw.trim().startsWith('={{ (() =>'), 'Org Create Code-built');
  let b = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: normLead({ company_url: 'https://acme.com' }) } }));
  assert.equal(b.website, 'https://acme.com'); assert.equal(b.name, 'Acme');
  b = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: normLead({ company_url: '' }) } }));
  assert(!('website' in b), 'omit empty');
  b = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: normLead({ company_url: null }) } }));
  assert(!('website' in b), 'omit null');
});

test('W1.0.8 B2 Person Create sets LinkedIn Location from lead.location (R4 omit when empty)', () => {
  const raw = getNode('Person Create').parameters.jsonBody;
  const PL = CFG.fields.person_location;
  assert.equal(PL, 'db219a0b68aa164d0aed1f7791687c5ae788b7ae');
  let b = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: normLead({ location: 'Cracow, Poland' }) } }));
  assert.equal(b.custom_fields[PL], 'Cracow, Poland');
  b = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: normLead({ location: '' }) } }));
  assert(!(PL in b.custom_fields), 'omit empty');
});

test('W1.0.8 B2 Person Patch Invited fills location only when empty; never overwrites', () => {
  const raw = getNode('Person Patch Invited').parameters.jsonBody;
  const PL = CFG.fields.person_location; const norm = normLead({ location: 'NewCity' });
  let cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: { [F.stage]: 'Accepted' } } } } })).custom_fields;
  assert.equal(cf[PL], 'NewCity', 'filled when empty');
  cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: { [F.stage]: 'Accepted', [PL]: 'OldCity' } } } } })).custom_fields;
  assert(!(PL in cf), 'not overwritten when present');
});

test('W1.0.8 B2 IF Rank Allows Invited fires when only location is fillable', () => {
  const raw = getNode('IF Rank Allows Invited').parameters.conditions.conditions[0].leftValue;
  const norm = normLead({ location: 'Kyiv', company_name: 'C', position: 'P' });
  const present = { [F.stage]: 'Accepted', [F.campaign]: 'HR Test Campaign', [F.company]: 'C', [F.position]: 'P', [F.li_url]: 'https://linkedin.com/in/x', [F.public_id]: 'x', [F.member_id]: 990000001 };
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: present } }, outputs: { CONFIG: CFG, Normalize: norm } }), true, 'location fillable -> true');
  const all = Object.assign({}, present, { [CFG.fields.person_location]: 'Kyiv', [CFG.fields.person_medium]: 'x' });
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: all } }, outputs: { CONFIG: CFG, Normalize: norm } }), false, 'all present -> false');
});

test('W1.0.8 B3 two trailing replies -> joined oldest->newest note; reply_text=last; alert has neither', () => {
  const o = m7build([{ message: 'Not at all', is_reply: true, message_type: 'REGULAR' }, { message: 'Grat to connect', is_reply: true, message_type: 'REGULAR' }]);
  assert.equal(o.reply_note, 'Not at all\nGrat to connect', 'joined: ' + JSON.stringify(o.reply_note));
  assert.equal(o.reply_text, 'Grat to connect', 'reply_text=last');
  assert(!o.alert_text.includes('Not at all') && !o.alert_text.includes('Grat to connect'), 'alert excludes reply text');
});

test('W1.0.8 B3 reply-after-outbound -> only trailing replies (stop at non-reply)', () => {
  const o = m7build([{ message: 'earlier reply', is_reply: true, message_type: 'REGULAR' }, { message: 'our outbound', is_reply: false, message_type: 'REGULAR' }, { message: 'final reply', is_reply: true, message_type: 'REGULAR' }]);
  assert.equal(o.reply_note, 'final reply', 'only trailing: ' + JSON.stringify(o.reply_note));
});

test('W1.0.8 B3 placeholders render inside the join', () => {
  const o = m7build([{ message: '', is_reply: true, message_type: 'voice' }, { message: 'text', is_reply: true, message_type: 'REGULAR' }]);
  assert.equal(o.reply_note, '[voice note]\ntext');
});

test('W1.0.8 B3 M7 Reply Activity note = joined reply_note (not last-only)', () => {
  const raw = getNode('M7 Reply Activity').parameters.jsonBody;
  const body = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: normalize(makeWebhookBody({ campaign: { name: 'C' } })), 'M7 Build': { person_id: 7, lead_id: 'L', reply_note: 'a\nb', reply_text: 'b' } } }));
  assert.equal(body.note, 'a\nb', 'multi-line note');
});

// ===================== W1.0.9 additions (event-truth labels: reply never implies connected) =====================
test('W1.0.9 M7 targetSet is [cold, responded] only (no connected push); M5 still pushes connected', () => {
  const m7 = getNode('M7 Labels Compute').parameters.jsCode;
  const m5 = getNode('M5 Labels Compute').parameters.jsCode;
  assert(!m7.includes('if (effectiveRank >= 2) targetSet.push(cfg.labels.connected)'), 'M7 must NOT push connected');
  assert(m7.includes('targetSet.push(cfg.labels.cold)') && m7.includes('targetSet.push(cfg.labels.responded)'), 'M7 pushes cold+responded');
  assert(m5.includes('if (effectiveRank >= 2) targetSet.push(cfg.labels.connected)'), 'M5 still pushes connected (unchanged)');
});

test('W1.0.9 reply WITHOUT accept -> [cold, responded], NO connected (foreign preserved)', () => {
  const o = m7labels('Invited', 'Replied to invite', [L7.cold, FOREIGN]);  // sent only, never accepted
  assert(o.label_ids.includes(L7.cold) && o.label_ids.includes(L7.responded), 'cold+responded: ' + o.label_ids);
  assert(!o.label_ids.includes(L7.connected), 'connected NOT implied by reply: ' + o.label_ids);
  assert(o.label_ids.includes(FOREIGN), 'foreign preserved');
  assert.equal(o.changed, true);
});

test('W1.0.9 sent->accepted->reply ends [cold, connected, responded]', () => {
  const afterAccept = m5labels(null, [L7.cold]);                 // accepted: [cold, connected]
  assert(eqSet(afterAccept.label_ids, [L7.cold, L7.connected]), 'after accept: ' + afterAccept.label_ids);
  const afterReply = m7labels('Accepted', 'Replied to invite', afterAccept.label_ids);  // reply unions responded
  assert(eqSet(afterReply.label_ids, [L7.cold, L7.connected, L7.responded]), 'after reply: ' + afterReply.label_ids);
});

test('W1.0.9 reply->late-accepted: after reply [cold,responded], after accept [cold,connected,responded]', () => {
  const afterReply = m7labels('Invited', 'Replied to invite', [L7.cold]);       // reply first, no accept yet
  assert(eqSet(afterReply.label_ids, [L7.cold, L7.responded]), 'after reply: ' + afterReply.label_ids);
  assert(!afterReply.label_ids.includes(L7.connected), 'no connected before accept');
  const afterAccept = m5labels('Replied to invite', afterReply.label_ids);      // late accept adds connected via M5
  assert(eqSet(afterAccept.label_ids, [L7.cold, L7.connected, L7.responded]), 'after late accept: ' + afterAccept.label_ids);
  assert.equal(afterAccept.changed, true);
});

test('W1.0.9 late-accepted no-op replay on full set unchanged (M5 union skip)', () => {
  const o = m5labels('Replied to invite', [L7.cold, L7.connected, L7.responded]);
  assert.equal(o.changed, false);
  assert(eqSet(o.label_ids, [L7.cold, L7.connected, L7.responded]), 'unchanged: ' + o.label_ids);
});

// ===================== W1.0.10 / W1.0.10.1 (split channels; replies temporarily -> ops) =====================
test('W1.0.10.1 channel split intact; replies temporarily routed to ops; no literal channel ids', () => {
  const cfg = JSON.parse(getNode('CONFIG').parameters.jsonOutput);
  // W1.0.10.1: replies flipped back to the ops channel (temporary until the Zap-filter agreement)
  assert.equal(cfg.slack_channel_replies, 'C0B8GCVNR5W', 'CONFIG.slack_channel_replies (temp = ops)');
  assert.equal(cfg.slack_channel_ops, 'C0B8GCVNR5W', 'CONFIG.slack_channel_ops');
  assert.equal(cfg.slack_channel, 'C0B8GCVNR5W', 'slack_channel kept as ops alias');
  const reply = new Set(['M7 Critical Slack', 'M7 Slack Warn']);
  const ops = new Set(['M7 No Lead Warn', 'M5 Slack Warn', 'M6 Slack Warn', 'M6 Message First Warn', 'Lead Resp Invalid', 'Event Marker Warn']);
  let seen = 0;
  for (const n of workflow.nodes) {
    if (n.type !== 'n8n-nodes-base.slack') continue;
    seen++;
    const v = n.parameters.channelId.value;
    assert(typeof v === 'string' && v.startsWith('={{'), n.name + ' channel must be a CONFIG expression: ' + v);
    assert(!/C0[0-9A-Z]{6,}/.test(v), n.name + ' references a literal channel id: ' + v);
    if (reply.has(n.name)) assert(v.includes('slack_channel_replies'), n.name + ' must -> slack_channel_replies (got ' + v + ')');
    else if (ops.has(n.name)) assert(v.includes('slack_channel_ops'), n.name + ' must -> slack_channel_ops (got ' + v + ')');
    else assert.fail('unexpected slack node: ' + n.name);
    assert(!v.endsWith('slack_channel }}'), n.name + ' still on bare slack_channel alias');
  }
  assert.equal(seen, 8, 'expected 8 WF-1 slack nodes (W1.0.13 added Event Marker Warn)');
});

// ===================== W1.0.11 (lead-per-campaign + title + Campaign field + medium) =====================
const CK = CFG.fields.lead_campaign;
const MED = CFG.fields.person_medium;
function m7lead(campaignName, leadArr) {
  const norm = normalize(makeWebhookBody({ campaign: { id: 'c1', name: campaignName }, recent_messages: [{ message: 'hi', is_reply: true, message_type: 'REGULAR' }] }));
  return runCodeNode('M7 Build', { outputs: { CONFIG: CFG, Normalize: norm, 'M7 Person Get': { data: person('Accepted') }, 'M7 Lead Get': { success: true, data: leadArr } } }).json;
}

test('W1.0.11 selectLead picks the Campaign-field match among multiple non-archived (ignores newer foreign)', () => {
  const o = m7lead('Camp X', [
    { id: 'L-foreign', is_archived: false, add_time: '2026-07-01', [CK]: 'Old Camp' },
    { id: 'L-match', is_archived: false, add_time: '2026-06-01', [CK]: 'Camp X' },
  ]);
  assert.equal(o.lead_id, 'L-match', 'campaign match beats newer foreign: ' + o.lead_id);
});

test('W1.0.11 selectLead null when only foreign-campaign leads (no-lead fallback)', () => {
  const o = m7lead('Camp X', [{ id: 'L-foreign', is_archived: false, add_time: '2026-07-01', [CK]: 'Old Camp' }]);
  assert.equal(o.lead_id, null, 'no match -> null: ' + o.lead_id);
});

test('W1.0.11 selectLead appends to same lead on 2nd reply same campaign', () => {
  const o = m7lead('Camp X', [{ id: 'L-match', is_archived: false, add_time: '2026-06-01', [CK]: 'Camp X' }]);
  assert.equal(o.lead_id, 'L-match');
});

test('W1.0.11 selectLead uses the Campaign FIELD, not title parsing', () => {
  const o = m7lead('Camp X', [{ id: 'L-title', is_archived: false, add_time: '2026-07-01', title: '123 - Camp X - John', [CK]: 'Different' }]);
  assert.equal(o.lead_id, null, 'title containing the campaign must NOT match');
});

test('W1.0.11 Lead Create Gate: create on foreign-only/empty, existing on campaign match', () => {
  const vals = getNode('Lead Create Gate').parameters.rules.values;
  const createExpr = vals[0].conditions.conditions[0].leftValue;
  const existExpr = vals[1].conditions.conditions[0].leftValue;
  const norm = normalize(makeWebhookBody({ campaign: { id: 'c1', name: 'Camp X' } }));
  const G = (expr, input) => evalExpression(expr, { input, outputs: { CONFIG: CFG, Normalize: norm } });
  const foreign = { success: true, data: [{ id: 'L1', is_archived: false, [CK]: 'Old Camp' }] };
  const match = { success: true, data: [{ id: 'L2', is_archived: false, [CK]: 'Camp X' }] };
  const empty = { success: true, data: [] };
  assert.equal(G(createExpr, foreign), true, 'foreign-only -> create');
  assert.equal(G(existExpr, foreign), false);
  assert.equal(G(createExpr, match), false);
  assert.equal(G(existExpr, match), true, 'match -> existing');
  assert.equal(G(createExpr, empty), true, 'empty -> create');
});

test('W1.0.11 Create Lead title = "{id} - {name} - {person}" + Campaign field on create', () => {
  const raw = getNode('Create Lead').parameters.jsonBody;
  const norm = normalize(makeWebhookBody({ campaign: { id: '510736', name: 'Ai4 2026 - Rune - LinkedIn' }, lead: { id: 1, profile_url: 'https://linkedin.com/in/x', full_name: 'Person-3426894b', company_name: 'Acme', position: 'Eng', summary: 's', email_address: '' } }));
  const body = JSON.parse(evalExpression(raw, { input: { lead_id: null }, outputs: { CONFIG: CFG, Normalize: norm, 'PID Resolved': { person_id: 7, organization_id: null } } }));
  assert.equal(body.title, '510736 - Ai4 2026 - Rune - LinkedIn - Person-3426894b', 'title: ' + body.title);
  assert.equal(body[CK], 'Ai4 2026 - Rune - LinkedIn', 'Campaign field on create');
  assert.deepEqual(body.label_ids, [CFG.labels.cold]);
});

test('W1.0.11 no runtime path rewrites an existing lead title (only Create Lead sets title)', () => {
  for (const nm of ['M5 Lead Patch', 'M7 Lead Patch']) {
    assert(!getNode(nm).parameters.jsonBody.includes('title'), nm + ' must not touch title');
  }
});

test('W1.0.11 medium=LinkedIn on Person Create + fill-if-empty; never overwrites', () => {
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent' }));
  const pc = JSON.parse(evalExpression(getNode('Person Create').parameters.jsonBody, { outputs: { CONFIG: CFG, Normalize: norm } }));
  assert.equal(pc.custom_fields[MED], 'LinkedIn', 'Person Create medium');
  const ppi = getNode('Person Patch Invited').parameters.jsonBody;
  let cf = JSON.parse(evalExpression(ppi, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: { [F.stage]: 'Accepted' } } } } })).custom_fields;
  assert.equal(cf[MED], 'LinkedIn', 'fills when empty');
  cf = JSON.parse(evalExpression(ppi, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: { [F.stage]: 'Accepted', [MED]: 'Email' } } } } })).custom_fields;
  assert(!(MED in cf), 'does not overwrite existing medium');
});

test('W1.0.11.1 IF Rank Allows Invited gate fires on campaign-differ; idempotent on same-campaign', () => {
  const raw = getNode('IF Rank Allows Invited').parameters.conditions.conditions[0].leftValue;
  const norm = normalize(makeWebhookBody({ event_type: 'connection_request_sent', lead: { id: 990000001, profile_url: 'https://linkedin.com/in/x', full_name: 'X', company_name: 'C', position: 'P', summary: 's', email_address: '' }, campaign: { id: 'c', name: 'NewCamp' } }));
  // everything already filled (stage past Invited) so ONLY the campaign clause can move the gate
  const filled = { [F.stage]: 'Accepted', [F.company]: 'C', [F.position]: 'P', [F.li_url]: 'https://linkedin.com/in/x', [F.public_id]: 's', [F.member_id]: 990000001, [F.person_location]: 'L', [CFG.fields.person_medium]: 'x' };
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { ...filled, [F.campaign]: 'OldCamp' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), true, 'differing campaign fires gate (always-overwrite)');
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { ...filled, [F.campaign]: 'NewCamp' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), false, 'same campaign + nothing else -> gate false (idempotent)');
});

// ===================== W1.0.13 (event-marker campaign parser -> person event trio) =====================
const EVK = CFG.fields.person_event_name;
const HYK = CFG.fields.person_hypothesis;
function trio(campName) {
  return normalize(makeWebhookBody({ event_type: 'connection_request_sent', campaign: { id: 'c', name: campName } })).event_trio;
}
function normMarker(campName, leadOverride) {
  return normalize(makeWebhookBody({ event_type: 'connection_request_sent', campaign: { id: 'c', name: campName }, ...(leadOverride ? { lead: leadOverride } : {}) }));
}

test('W1.0.13 parser: canonical dash / no-dash / case-drift -> Events Visiting + event name', () => {
  for (const nm of ['[Events Visiting] - Ai4 2026', '[Events Visiting] Ai4 2026']) {
    const t = trio(nm);
    assert.equal(t.marker, true); assert.equal(t.skip, false);
    assert.equal(t.event_name, 'Ai4 2026'); assert.equal(t.hypothesis, 'Events Visiting');
  }
  const t = trio('[events visiting] X');
  assert.equal(t.hypothesis, 'Events Visiting'); assert.equal(t.event_name, 'X');
});

test('W1.0.13 parser: unknown bracket -> event name only, hypothesis NOT set', () => {
  const t = trio('[Unknown Thing] X');
  assert.equal(t.marker, true); assert.equal(t.skip, false);
  assert.equal(t.event_name, 'X'); assert.equal(t.hypothesis, null);
});

test('W1.0.13 parser: no marker -> fully inert (nothing derived, no warn)', () => {
  const t = trio('Ai4 2026 - Mario - LinkedIn');
  assert.equal(t.marker, false); assert.equal(t.event_name, null);
  assert.equal(t.hypothesis, null); assert.equal(t.skip, false); assert.equal(t.warn_text, null);
});

test('W1.0.13 parser guardrails: empty tail / second bracket / >60 chars -> skip + warn text', () => {
  for (const nm of ['[Events Visiting] -', '[Events Visiting] - [Other] X', '[Events Visiting] - ' + 'Z'.repeat(65)]) {
    const t = trio(nm);
    assert.equal(t.skip, true); assert.equal(t.event_name, null); assert.equal(t.hypothesis, null);
    assert(t.warn_text && t.warn_text.includes('non-canonical name') && t.warn_text.includes(nm), 'warn text present: ' + t.warn_text);
  }
});

test('W1.0.13 Person Create writes the trio on a marker campaign', () => {
  const norm = normMarker('[Events Visiting] - Ai4 2026');
  const cf = JSON.parse(evalExpression(getNode('Person Create').parameters.jsonBody, { outputs: { CONFIG: CFG, Normalize: norm } })).custom_fields;
  assert.equal(cf[EVK], 'Ai4 2026'); assert.equal(cf[HYK], 'Events Visiting');
  assert.equal(cf[F.person_medium], 'LinkedIn');
  // unknown bracket: event name written, hypothesis not
  const cf2 = JSON.parse(evalExpression(getNode('Person Create').parameters.jsonBody, { outputs: { CONFIG: CFG, Normalize: normMarker('[Unknown Thing] - Foo 2026') } })).custom_fields;
  assert.equal(cf2[EVK], 'Foo 2026'); assert(!(HYK in cf2), 'unknown bracket -> no hypothesis');
  // guardrail skip: nothing written
  const cf3 = JSON.parse(evalExpression(getNode('Person Create').parameters.jsonBody, { outputs: { CONFIG: CFG, Normalize: normMarker('[Events Visiting] -') } })).custom_fields;
  assert(!(EVK in cf3) && !(HYK in cf3), 'guardrail skip -> no trio');
});

test('W1.0.13 marker campaign OVERWRITES a pre-set trio; person card stays self-consistent', () => {
  const raw = getNode('Person Patch Invited').parameters.jsonBody;
  const norm = normMarker('[Events Visiting] - Ai4 2026');
  const cur = { [F.stage]: 'Accepted', [EVK]: 'Old Event 2024', [HYK]: 'Sales Sprint', [F.campaign]: 'Old Campaign' };
  const cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: cur } } } })).custom_fields;
  assert.equal(cf[EVK], 'Ai4 2026', 'event name overwritten');
  assert.equal(cf[HYK], 'Events Visiting', 'hypothesis overwritten');
  assert.equal(cf[F.campaign], '[Events Visiting] - Ai4 2026', 'campaign field = full bracketed name (W1.0.11.1) -> same campaign as Event name');
});

test('W1.0.13 PLAIN campaign leaves a pre-set trio untouched (parser inert)', () => {
  const raw = getNode('Person Patch Invited').parameters.jsonBody;
  const norm = normMarker('Plain Campaign X');
  const cur = { [F.stage]: 'Accepted', [EVK]: 'Old Event 2024', [HYK]: 'Sales Sprint', [F.campaign]: 'Old Campaign' };
  const cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: cur } } } })).custom_fields;
  assert(!(EVK in cf) && !(HYK in cf), 'plain campaign must not touch event trio');
});

test('W1.0.13 same-campaign repeat -> idempotent (no redundant trio PATCH)', () => {
  const raw = getNode('Person Patch Invited').parameters.jsonBody;
  const norm = normMarker('[Events Visiting] - Ai4 2026');
  const cur = { [F.stage]: 'Accepted', [EVK]: 'Ai4 2026', [HYK]: 'Events Visiting', [F.campaign]: '[Events Visiting] - Ai4 2026' };
  const cf = JSON.parse(evalExpression(raw, { outputs: { CONFIG: CFG, Normalize: norm, 'Person Get': { data: { custom_fields: cur } } } })).custom_fields;
  assert(!(EVK in cf) && !(HYK in cf), 'no redundant event/hyp write when unchanged');
});

test('W1.0.13 gate (IF Rank Allows Invited) fires on trio-differ, idempotent on same', () => {
  const raw = getNode('IF Rank Allows Invited').parameters.conditions.conditions[0].leftValue;
  const norm = normMarker('[Events Visiting] - Ai4 2026');
  const base = { [F.stage]: 'Accepted', [F.company]: norm.lead.company_name, [F.position]: norm.lead.position, [F.li_url]: norm.lead.url, [F.public_id]: norm.lead.slug, [F.member_id]: 990000001, [F.person_medium]: 'x', [F.campaign]: norm.campaign.name, [HYK]: 'Events Visiting' };
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { ...base, [EVK]: 'Wrong Event' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), true, 'event name differs -> gate fires');
  assert.equal(evalExpression(raw, { input: { data: { custom_fields: { ...base, [EVK]: 'Ai4 2026' } } }, outputs: { CONFIG: CFG, Normalize: norm } }), false, 'trio + all matching -> gate false');
});

test('W1.0.13 lead title + Campaign field carry the FULL bracketed name; campaign-match bracket-safe', () => {
  const rawCL = getNode('Create Lead').parameters.jsonBody;
  const normB = normalize(makeWebhookBody({ event_type: 'connection_request_sent', campaign: { id: 'camp-9', name: '[Events Visiting] - Ai4 2026' }, lead: { id: 5, profile_url: 'https://linkedin.com/in/x', full_name: 'Person-fbbb498b', company_name: '', position: '', summary: '', email_address: '' } }));
  const cl = JSON.parse(evalExpression(rawCL, { input: { lead_id: null }, outputs: { CONFIG: CFG, Normalize: normB, 'PID Resolved': { person_id: 1, organization_id: null } } }));
  assert.equal(cl.title, 'camp-9 - [Events Visiting] - Ai4 2026 - Person-fbbb498b', 'title: ' + cl.title);
  assert.equal(cl[CFG.fields.lead_campaign], '[Events Visiting] - Ai4 2026', 'Campaign field = full bracketed name');
  const o = m7lead('[Events Visiting] - Ai4 2026', [
    { id: 'L-match', is_archived: false, add_time: '2026-07-01', label_ids: [], [CFG.fields.lead_campaign]: '[Events Visiting] - Ai4 2026' },
    { id: 'L-foreign', is_archived: false, add_time: '2026-12-01', label_ids: [], [CFG.fields.lead_campaign]: 'Other' }]);
  assert.equal(o.lead_id, 'L-match', 'bracketed campaign-match works: ' + o.lead_id);
});

test('W1.0.13 warn tee: IF Event Marker Bad + Event Marker Warn wired to ops, main spine intact', () => {
  const ifn = getNode('IF Event Marker Bad');
  assert(ifn.parameters.conditions.conditions[0].leftValue.includes('event_trio.skip === true'), 'IF checks skip');
  const warn = getNode('Event Marker Warn');
  assert.equal(warn.type, 'n8n-nodes-base.slack');
  assert.equal(warn.parameters.channelId.value, "={{ $('CONFIG').item.json.slack_channel_ops }}", 'warn -> ops channel');
  assert(warn.parameters.text.includes('event_trio.warn_text'), 'warn text = warn_text');
  // Normalize tees to IF Event Marker Bad AND still feeds Switch (main spine intact)
  const nz = workflow.connections['Normalize'].main[0].map((e) => e.node);
  assert(nz.includes('Switch'), 'Normalize -> Switch intact');
  assert(nz.includes('IF Event Marker Bad'), 'Normalize tees -> IF Event Marker Bad');
  assert.equal(workflow.connections['IF Event Marker Bad'].main[0][0].node, 'Event Marker Warn', 'IF true -> Warn');
});


console.log(`\n${passed} passed, ${failures.length} failed`);
if (failures.length) process.exitCode = 1;
