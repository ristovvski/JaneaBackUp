#!/usr/bin/env node
// n8n/patch/patch.mjs — deterministic build of WF-ICP-Score.dev.json.
//
// The golden example's release protocol requires a patcher whose second run is
// byte-identical and whose validate() refuses to emit a bad workflow. For
// release 1 there is no previous patched.json to anchor-replace against, so
// this builds the whole graph from its sources instead — which is strictly
// stronger: there is no hand-edited surface for a patch to drift away from.
//
//   sources: n8n/nodes/*.js       (Code-node jsCode, spliced in byte-identical)
//            n8n/nodes/CONFIG.json (the Set node's static payload)
//   output:  n8n/workflows/WF-ICP-Score.dev.json
//            n8n/workflows/api-payload.json   ({name,nodes,connections,settings})
//
// From release 2 on, switch to anchor-based replaces over the previous
// patched.json if a hand edit in the n8n editor ever needs preserving. Until
// then, regenerating is safer.
//
//   node n8n/patch/patch.mjs            build + validate
//   node n8n/patch/patch.mjs --check    validate only; fail if a rebuild would differ

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { validate } from './validate.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const NODES = join(ROOT, 'n8n', 'nodes');
const OUT = join(ROOT, 'n8n', 'workflows', 'WF-ICP-Score.dev.json');
const API_OUT = join(ROOT, 'n8n', 'workflows', 'api-payload.json');
const IMPORT_OUT = join(ROOT, 'n8n', 'workflows', 'import-dev-no-credentials.json');

const code = (name) => readFileSync(join(NODES, `${name}.js`), 'utf8');
const CONFIG_STATIC = JSON.parse(readFileSync(join(NODES, 'CONFIG.json'), 'utf8'));

// The four values that must never sit in a file: a Clay webhook URL is an
// unguessable endpoint, so it is a secret. Spliced from $env at runtime.
export const ENV_BINDINGS = {
  clay_webhook_url: 'ICP_CLAY_WEBHOOK_URL',
  clay_callback_url: 'ICP_CLAY_CALLBACK_URL',
  audit_sheet_id: 'ICP_AUDIT_SHEET_ID',
  slack_channel_ops: 'ICP_SLACK_CHANNEL',
};

/**
 * The CONFIG Set node's jsonOutput: the static payload, plus the env-sourced
 * values, plus now_iso. now_iso is in CONFIG rather than read as $now inside
 * each node so that every node in one execution agrees on "now" — a run that
 * straddles midnight must not write one date and gate on another — and so the
 * node tests can pin it.
 */
function configExpression() {
  const envPairs = Object.entries(ENV_BINDINGS)
    .map(([key, envKey]) => `${key}: $env.${envKey}`)
    .join(', ');
  return `={{ JSON.stringify(Object.assign({}, ${JSON.stringify(CONFIG_STATIC)}, ` +
         `{ ${envPairs}, now_iso: $now.toISO() })) }}`;
}

// ---------------------------------------------------------------------------
// Node factories. Every id/key/option comes from CONFIG at runtime; nothing
// provider-specific is a literal below.
// ---------------------------------------------------------------------------

const PIPEDRIVE_V2 = 'https://api.pipedrive.com/api/v2';
const PIPEDRIVE_V1 = 'https://api.pipedrive.com/v1';

// ---------------------------------------------------------------------------
// Webhook paths.
//
// SECURITY.md is explicit: "an n8n webhook path is the only authentication
// those endpoints have ... The path IS the credential." So the committed
// source carries a PLACEHOLDER, never a live path. Set these when building an
// export you intend to import:
//
//   ICP_WEBHOOK_PATH_A=<unguessable> ICP_WEBHOOK_PATH_B=<unguessable> \
//     node n8n/patch/patch.mjs
//
// The generated export is gitignored, so the real path never reaches git. A
// build with the variables unset produces the placeholder, which n8n will
// happily register and which you must not use for anything real.
// ---------------------------------------------------------------------------
export const PLACEHOLDER_PATH_A = 'REPLACE-ME-icp-score-pipedrive';
export const PLACEHOLDER_PATH_B = 'REPLACE-ME-icp-scored-clay';

const WEBHOOK_PATH_A = process.env.ICP_WEBHOOK_PATH_A || PLACEHOLDER_PATH_A;
const WEBHOOK_PATH_B = process.env.ICP_WEBHOOK_PATH_B || PLACEHOLDER_PATH_B;
export const USING_PLACEHOLDER_PATHS =
  WEBHOOK_PATH_A === PLACEHOLDER_PATH_A || WEBHOOK_PATH_B === PLACEHOLDER_PATH_B;

const codeNode = (name, position, source, extra = {}) => ({
  parameters: { jsCode: source },
  id: name,
  name,
  type: 'n8n-nodes-base.code',
  typeVersion: 2,
  position,
  ...extra,
});

const ifNode = (name, position, conditions, extra = {}) => ({
  parameters: {
    conditions: {
      options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
      conditions,
      combinator: 'and',
    },
    looseTypeValidation: false,
    options: {},
  },
  id: name,
  name,
  type: 'n8n-nodes-base.if',
  typeVersion: 2.2,
  position,
  ...extra,
});

const boolCondition = (leftValue, expected) => ({
  id: `${leftValue}-is-${expected}`,
  leftValue: `={{ ${leftValue} }}`,
  rightValue: expected,
  operator: { type: 'boolean', operation: 'equals' },
});

const noOp = (name, position) => ({
  parameters: {},
  id: name,
  name,
  type: 'n8n-nodes-base.noOp',
  typeVersion: 1,
  position,
});

const httpNode = (name, position, params, extra = {}) => ({
  parameters: {
    authentication: 'predefinedCredentialType',
    nodeCredentialType: 'pipedriveApi',
    options: {},
    ...params,
  },
  id: name,
  name,
  type: 'n8n-nodes-base.httpRequest',
  typeVersion: 4.2,
  position,
  credentials: { pipedriveApi: { id: 'pipedrive_main', name: 'pipedrive_main' } },
  ...extra,
});

const slackNode = (name, position, text, extra = {}) => ({
  parameters: {
    resource: 'message',
    operation: 'post',
    select: 'channel',
    // Driven from CONFIG, never a literal channel id.
    channelId: { __rl: true, value: "={{ $('CONFIG').item.json.slack_channel_ops }}", mode: 'id' },
    text,
    otherOptions: {},
  },
  id: name,
  name,
  type: 'n8n-nodes-base.slack',
  typeVersion: 2.2,
  position,
  credentials: { slackApi: { id: 'slack_ops', name: 'slack_ops' } },
  ...extra,
});

const RETRY = { retryOnFail: true, maxTries: 3, waitBetweenTries: 2000 };
// A retried create is a duplicate. Notes, the Clay row and the audit append
// are all creates.
const NO_RETRY = { retryOnFail: false };

// ---------------------------------------------------------------------------
// The graph
// ---------------------------------------------------------------------------

export function buildWorkflow() {
  const nodes = [];

  // ===== Path A: Pipedrive deal.create ====================================
  nodes.push({
    parameters: {
      httpMethod: 'POST',
      path: WEBHOOK_PATH_A,
      // Pipedrive supports HTTP basic auth on the subscription
      // (http_auth_user / http_auth_password), so the endpoint is
      // authenticated rather than merely unguessable.
      authentication: 'basicAuth',
      responseMode: 'responseNode',
      options: {},
    },
    id: 'Webhook Pipedrive',
    name: 'Webhook Pipedrive',
    type: 'n8n-nodes-base.webhook',
    typeVersion: 2,
    position: [-260, 200],
    webhookId: WEBHOOK_PATH_A,
    credentials: { httpBasicAuth: { id: 'icp_webhook_basic', name: 'icp_webhook_basic' } },
  });

  nodes.push({
    parameters: { respondWith: 'text', responseBody: 'ok', options: { responseCode: 200 } },
    id: 'Respond 200 A',
    name: 'Respond 200 A',
    type: 'n8n-nodes-base.respondToWebhook',
    typeVersion: 1,
    position: [-60, 200],
  });

  nodes.push({
    parameters: { mode: 'raw', jsonOutput: configExpression(), options: {} },
    id: 'CONFIG',
    name: 'CONFIG',
    type: 'n8n-nodes-base.set',
    typeVersion: 3.4,
    position: [140, 200],
  });

  nodes.push(codeNode('Dedupe', [340, 200], code('Dedupe')));
  nodes.push(codeNode('Normalize', [540, 200], code('Normalize')));

  nodes.push(ifNode('IF deal.create?', [740, 200], [boolCondition("$json.scoreable", true)]));

  nodes.push(httpNode('GET organization', [940, 100], {
    method: 'GET',
    url: `=${PIPEDRIVE_V2}/organizations/{{ $json.org_id }}`,
  }, RETRY));

  nodes.push(codeNode('IdempotencyGate', [1140, 100], code('IdempotencyGate')));

  nodes.push(ifNode('IF fresh score?', [1340, 100], [boolCondition('$json.skip', true)]));

  nodes.push(noOp('Skip fresh score', [1540, 0]));
  nodes.push(noOp('Skip not scoreable', [940, 300]));

  nodes.push(codeNode('BuildClayRequest', [1540, 160], code('BuildClayRequest'), {
    onError: 'continueErrorOutput',
  }));

  nodes.push({
    parameters: {
      method: 'POST',
      url: "={{ $('CONFIG').item.json.clay_webhook_url }}",
      sendBody: true,
      specifyBody: 'json',
      jsonBody: '={{ JSON.stringify($json.body) }}',
      options: {},
    },
    id: 'POST Clay',
    name: 'POST Clay',
    type: 'n8n-nodes-base.httpRequest',
    typeVersion: 4.2,
    position: [1740, 160],
    // A retried POST creates a SECOND Clay row: a second scoring run and a
    // second credit. Never retry it.
    ...NO_RETRY,
  });

  // Non-blocking tee: anomaly gate on trigger volume.
  nodes.push(ifNode('IF rate exceeded?', [540, -100], [boolCondition('$json._rate_exceeded', true)]));
  nodes.push(slackNode(
    'Slack warn rate',
    [740, -100],
    '=:warning: ICP scoring trigger volume is unusually high: ' +
    "{{ $json._rate_this_hour }} events this hour (limit {{ $('CONFIG').item.json.max_events_per_hour }}). " +
    'A bulk import can burn Clay credits fast. ' +
    'execution_id={{ $execution.id }} request_id={{ $json._dedupe_key }}',
    NO_RETRY
  ));

  // ===== Path B: Clay icp.scored ==========================================
  nodes.push({
    parameters: {
      httpMethod: 'POST',
      path: WEBHOOK_PATH_B,
      // Header auth: X-Clay-Secret, held in the clay_webhook_secret credential.
      authentication: 'headerAuth',
      responseMode: 'responseNode',
      options: {},
    },
    id: 'Webhook Clay',
    name: 'Webhook Clay',
    type: 'n8n-nodes-base.webhook',
    typeVersion: 2,
    position: [-260, 700],
    webhookId: WEBHOOK_PATH_B,
    credentials: { httpHeaderAuth: { id: 'clay_webhook_secret', name: 'clay_webhook_secret' } },
  });

  nodes.push({
    parameters: { respondWith: 'text', responseBody: 'ok', options: { responseCode: 200 } },
    id: 'Respond 200 B',
    name: 'Respond 200 B',
    type: 'n8n-nodes-base.respondToWebhook',
    typeVersion: 1,
    position: [-60, 700],
  });

  nodes.push({
    parameters: { mode: 'raw', jsonOutput: configExpression(), options: {} },
    id: 'CONFIG B',
    name: 'CONFIG B',
    type: 'n8n-nodes-base.set',
    typeVersion: 3.4,
    position: [140, 700],
  });

  nodes.push(codeNode('Dedupe B', [340, 700], code('Dedupe')));

  nodes.push(codeNode('ParseScored', [540, 700], code('ParseScored'), {
    onError: 'continueErrorOutput',
  }));

  // A duplicate callback still gets an audit row, but no writes.
  nodes.push(ifNode('IF write allowed?', [740, 700], [boolCondition('$json._duplicate', false)]));

  nodes.push(httpNode('GET organization B', [940, 600], {
    method: 'GET',
    url: `=${PIPEDRIVE_V2}/organizations/{{ $json.org_id }}`,
  }, RETRY));

  nodes.push(codeNode('BuildOrgPatch', [1140, 600], code('BuildOrgPatch')));

  nodes.push(ifNode('IF patch non-empty?', [1340, 600], [boolCondition('$json.patch_is_empty', false)]));

  nodes.push(httpNode('PATCH organization', [1540, 500], {
    method: 'PATCH',
    url: `=${PIPEDRIVE_V2}/organizations/{{ $json.org_id }}`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify($json.patch) }}',
  }, RETRY));

  nodes.push(codeNode('BuildNote', [1740, 500], code('BuildNote')));

  nodes.push(httpNode('POST note', [1940, 500], {
    method: 'POST',
    // Notes are v1: there is no v2 notes endpoint.
    url: `=${PIPEDRIVE_V1}/notes`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify({ org_id: Number($json.org_id), content: $json.note }) }}',
  }, NO_RETRY));

  nodes.push(codeNode('BuildAuditRow', [2140, 600], code('BuildAuditRow')));

  nodes.push({
    parameters: {
      resource: 'sheet',
      operation: 'append',
      documentId: { __rl: true, value: "={{ $('CONFIG').item.json.audit_sheet_id }}", mode: 'id' },
      sheetName: { __rl: true, value: 'ICP_Audit', mode: 'name' },
      // autoMapInputData maps the incoming keys onto the sheet's header row by
      // name, which is why BuildAuditRow emits its keys in §8.4 order.
      columns: { mappingMode: 'autoMapInputData', value: {}, matchingColumns: [], schema: [] },
      options: {},
    },
    id: 'Append audit row',
    name: 'Append audit row',
    type: 'n8n-nodes-base.googleSheets',
    typeVersion: 4.5,
    position: [2340, 600],
    credentials: { googleSheetsOAuth2Api: { id: 'gsheets_audit', name: 'gsheets_audit' } },
    ...NO_RETRY,
  });

  // ===== Error branch =====================================================
  nodes.push(codeNode('BuildErrorPatch', [940, 900], code('BuildErrorPatch')));

  // Alert BEFORE the writes, with continue-on-fail: if marking the org as
  // Errored also fails, the human ping must still have gone out. This is the
  // one allow-listed continueOnFail in the workflow.
  nodes.push(slackNode(
    'Slack alert error',
    [1140, 900],
    '=:rotating_light: ICP scoring failed. ' +
    'org_id={{ $json.org_id }} request_id={{ $json.request_id }} ' +
    'execution_id={{ $execution.id }} ' +
    'error={{ $json.error_name }}: {{ $json.error_message }}',
    { continueOnFail: true, ...NO_RETRY }
  ));

  nodes.push(ifNode('IF error patch non-empty?', [1340, 900], [boolCondition('$json.patch_is_empty', false)]));

  nodes.push(httpNode('PATCH organization error', [1540, 820], {
    method: 'PATCH',
    url: `=${PIPEDRIVE_V2}/organizations/{{ $json.org_id }}`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify($json.patch) }}',
  }, RETRY));

  nodes.push(httpNode('POST note error', [1740, 820], {
    method: 'POST',
    url: `=${PIPEDRIVE_V1}/notes`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody:
      '={{ JSON.stringify({ org_id: Number($json.org_id), content: ' +
      "'ICP ' + $('CONFIG').item.json.model_version + ' — Calculated: ' + " +
      "$('CONFIG').item.json.label_error + '\\n' + " +
      "'Reason: ' + $json.error_name + ': ' + $json.error_message + '\\n' + " +
      "'request_id ' + ($json.request_id || 'n/a') + ' · execution_id ' + $execution.id" +
      ' }) }}',
  }, NO_RETRY));

  nodes.push(noOp('Skip error patch', [1540, 980]));

  // ---------------------------------------------------------------------
  // Connections
  // ---------------------------------------------------------------------
  // n8n's shape is { "Node": { main: [ [targets...], [targets...] ] } }. The
  // outer array is one entry per OUTPUT (an IF has two); the inner array is
  // the targets of that output. Omitting the `main` wrapper produces JSON that
  // n8n silently imports with no connections at all.
  const out = (...targets) => targets.map((node) => ({ node, type: 'main', index: 0 }));
  const main = (...targets) => ({ main: [out(...targets)] });
  const branch = (trueTargets, falseTargets) => ({
    main: [out(...trueTargets), out(...falseTargets)],
  });

  const connections = {
    // Path A
    'Webhook Pipedrive': main('Respond 200 A'),
    'Respond 200 A': main('CONFIG'),
    CONFIG: main('Dedupe'),
    // Two connections: the spine, plus the anomaly tee that dead-ends.
    // Two targets on ONE output: the spine plus the anomaly tee.
    Dedupe: { main: [out('Normalize', 'IF rate exceeded?')] },
    'IF rate exceeded?': branch(['Slack warn rate'], []),
    Normalize: main('IF deal.create?'),
    'IF deal.create?': branch(['GET organization'], ['Skip not scoreable']),
    'GET organization': main('IdempotencyGate'),
    IdempotencyGate: main('IF fresh score?'),
    'IF fresh score?': branch(['Skip fresh score'], ['BuildClayRequest']),
    // Output 0 is success, output 1 is the error output (onError:
    // continueErrorOutput).
    BuildClayRequest: { main: [out('POST Clay'), out('BuildErrorPatch')] },

    // Path B
    'Webhook Clay': main('Respond 200 B'),
    'Respond 200 B': main('CONFIG B'),
    'CONFIG B': main('Dedupe B'),
    'Dedupe B': main('ParseScored'),
    ParseScored: { main: [out('IF write allowed?'), out('BuildErrorPatch')] },
    // A duplicate skips the writes and goes straight to the audit row.
    'IF write allowed?': branch(['GET organization B'], ['BuildAuditRow']),
    'GET organization B': main('BuildOrgPatch'),
    BuildOrgPatch: main('IF patch non-empty?'),
    // An empty patch means nothing changed, so no PATCH and no second note —
    // but still an audit row.
    'IF patch non-empty?': branch(['PATCH organization'], ['BuildAuditRow']),
    'PATCH organization': main('BuildNote'),
    BuildNote: main('POST note'),
    'POST note': main('BuildAuditRow'),
    BuildAuditRow: main('Append audit row'),

    // Error branch: alert first, then write.
    BuildErrorPatch: main('Slack alert error'),
    'Slack alert error': main('IF error patch non-empty?'),
    'IF error patch non-empty?': branch(['PATCH organization error'], ['Skip error patch']),
    'PATCH organization error': main('POST note error'),
  };

  const workflow = {
    name: 'WF-ICP-Score',
    nodes,
    connections,
    settings: {
      executionOrder: 'v1',
      // Anything this workflow's own error branch cannot handle — a failed
      // PATCH cannot mark itself as Errored — reaches WF-ERR, which Slacks.
      errorWorkflow: 'WF-ERR',
      saveManualExecutions: true,
      callerPolicy: 'workflowsFromSameOwner',
    },
    // DEV only, and never armed by the patcher. Arming is a human act.
    active: false,
  };

  return workflow;
}

// ---------------------------------------------------------------------------
// Emit
// ---------------------------------------------------------------------------

/** Stable JSON: 2-space indent, LF, trailing newline. */
const emit = (value) => `${JSON.stringify(value, null, 2)}\n`.replace(/\r\n/g, '\n');

/**
 * The payload to actually POST when importing into a shared instance.
 *
 * Every `credentials` block is REMOVED. The canonical export keeps them as
 * name placeholders because they document which credential each node needs and
 * the static tests assert that; but an import should attach nothing, so the
 * imported workflow cannot reach Pipedrive, Slack or Sheets even by accident
 * before a human has looked at it. Credentials get attached in the n8n UI, by
 * the person who owns them.
 *
 * `active` stays false and is not settable through this payload anyway.
 */
export function stripCredentials(workflow) {
  return {
    name: `${workflow.name} [DEV]`,
    nodes: workflow.nodes.map((node) => {
      const { credentials, ...rest } = node;
      return rest;
    }),
    connections: workflow.connections,
    settings: workflow.settings,
  };
}

const workflow = buildWorkflow();
const findings = validate(workflow, { nodesDir: NODES });

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (findings.length > 0) {
  process.stderr.write(`validate() found ${findings.length} problem(s):\n`);
  for (const f of findings) process.stderr.write(`  - ${f}\n`);
  process.stderr.write('\nNothing written.\n');
  if (isMain) process.exit(1);
}

if (isMain) {
  const text = emit(workflow);
  const apiPayload = emit({
    name: workflow.name,
    nodes: workflow.nodes,
    connections: workflow.connections,
    settings: workflow.settings,
  });

  if (process.argv.includes('--check')) {
    const current = readFileSync(OUT, 'utf8');
    if (current !== text) {
      process.stderr.write(
        'WF-ICP-Score.dev.json differs from a fresh build.\n' +
        'Run `node n8n/patch/patch.mjs` and commit the result.\n'
      );
      process.exit(1);
    }
    process.stdout.write(`--check: WF-ICP-Score.dev.json is byte-identical to a fresh build.\n`);
    process.exit(0);
  }

  const importPayload = emit(stripCredentials(workflow));

  writeFileSync(OUT, text, 'utf8');
  writeFileSync(API_OUT, apiPayload, 'utf8');
  writeFileSync(IMPORT_OUT, importPayload, 'utf8');

  const codeNodes = workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.code');
  const credentialled = workflow.nodes.filter((n) => n.credentials).length;
  process.stdout.write(
    `wrote n8n/workflows/WF-ICP-Score.dev.json (${text.length} bytes)\n` +
    `wrote n8n/workflows/api-payload.json (${apiPayload.length} bytes)\n` +
    `wrote n8n/workflows/import-dev-no-credentials.json (${importPayload.length} bytes)\n` +
    `  nodes: ${workflow.nodes.length} (${codeNodes.length} Code)\n` +
    `  active: ${workflow.active}  errorWorkflow: ${workflow.settings.errorWorkflow}\n` +
    `  credentials in canonical export: ${credentialled} node(s)\n` +
    `  credentials in import payload:   0 (stripped)\n` +
    `  webhook paths: ${USING_PLACEHOLDER_PATHS ? 'PLACEHOLDER — set ICP_WEBHOOK_PATH_A/B for a real import' : 'from ICP_WEBHOOK_PATH_A/B'}\n` +
    `  validate(): clean\n`
  );
  if (USING_PLACEHOLDER_PATHS) {
    process.stdout.write(
      '\n  NOTE: the webhook paths are placeholders. SECURITY.md treats a webhook\n' +
      '        path as a credential, so the committed source cannot hold a real one.\n' +
      '        Rebuild with ICP_WEBHOOK_PATH_A / ICP_WEBHOOK_PATH_B set before importing.\n'
    );
  }
}

export { workflow, emit };
