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

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
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

// Prefer the live rendering (real field keys, gitignored) when a create_fields
// run has produced one; fall back to the committed placeholder so a fresh
// clone builds and tests.
const CONFIG_LIVE = join(NODES, 'CONFIG.local.json');
const CONFIG_PATH = existsSync(CONFIG_LIVE) ? CONFIG_LIVE : join(NODES, 'CONFIG.json');
export const CONFIG_IS_LIVE = CONFIG_PATH === CONFIG_LIVE;
const CONFIG_STATIC = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));

// The values that must never sit in a file: a Clay webhook URL is an
// unguessable endpoint, so it is a secret. Spliced from $env at runtime.
export const ENV_BINDINGS = {
  clay_engine_url: 'ICP_CLAY_ENGINE_URL',
  clay_callback_url: 'ICP_CLAY_CALLBACK_URL',
  slack_channel_ops: 'ICP_SLACK_CHANNEL',
};

// The Slack credential to attach, resolved at deploy time against the live
// instance. A credential ID is instance-specific, so it cannot be a literal
// here; scripts/n8n_deploy.mjs resolves it by TYPE against whatever the
// workflow already carries, and this placeholder is what it replaces.
export const SLACK_CREDENTIAL_PLACEHOLDER = 'slack_ops';

/**
 * The CONFIG Set node's jsonOutput: the static payload, plus the four
 * instance-specific values, plus now_iso.
 *
 * now_iso lives here rather than being read as $now inside each node so that
 * every node in one execution agrees on "now" — a run that straddles midnight
 * must not gate on one date and write another — and so the node tests can pin
 * it.
 *
 * The four secrets are resolved from $vars FIRST, then $env. n8n Cloud blocks
 * $env by default (N8N_BLOCK_ENV_ACCESS_IN_NODE) and exposes Variables
 * instead; self-hosted instances usually have $env and may have no Variables
 * at all. Reading a blocked accessor THROWS rather than returning undefined,
 * so each lookup is wrapped — otherwise CONFIG fails the whole execution on
 * the instance type it was not written for. Supporting both removes the guess.
 */
function configExpression() {
  // Third layer: a value baked in at BUILD time from the builder's environment.
  // n8n Cloud blocks $env AND refuses Variable writes over the API (403), so on
  // Cloud the baked value is the only one that arrives. It lands only in the
  // gitignored export — SECURITY.md's "the real values live in n8n" — never in
  // a tracked file.
  const baked = {};
  for (const [key, envKey] of Object.entries(ENV_BINDINGS)) {
    baked[key] = process.env[envKey] || null;
  }

  const pairs = Object.entries(ENV_BINDINGS)
    .map(([key, envKey]) => `${key}: pick('${envKey}', BAKED.${key})`)
    .join(', ');

  const resolver =
    `(() => { const BAKED = ${JSON.stringify(baked)}; const pick = (n, baked) => { ` +
    "try { if (typeof $vars !== 'undefined' && $vars && $vars[n]) return $vars[n]; } catch (e) {} " +
    "try { if (typeof $env !== 'undefined' && $env && $env[n]) return $env[n]; } catch (e) {} " +
    "return baked === undefined ? null : baked; }; " +
    `return { ${pairs}, now_iso: $now.toISO() }; })()`;

  // n8n scans an expression for the FIRST "}}" and ends it there. CONFIG embeds
  // the whole rubric as a JSON literal, and nested objects close with "}}" —
  // e.g. `...investment"}},"vertical_tier":{`. That sequence silently
  // terminated the expression 2749 characters in, so the Set node JSON-parsed a
  // truncated string and the node failed at run time with "invalid syntax".
  // Nothing catches that before a real execution: the workflow imports, the
  // graph validates, and the expression looks right in the editor.
  //
  // Spacing the pair is enough — `} }` is identical JavaScript and no longer a
  // delimiter. validate.mjs now fails the build if any "}}" survives inside an
  // expression body.
  const inner = `JSON.stringify(Object.assign({}, ${JSON.stringify(CONFIG_STATIC)}, ${resolver}))`;
  return `={{ ${inner.replaceAll('}}', '} }')} }}`;
}

/** Which of the four instance values this build baked in. Reported, never printed. */
export const BAKED_KEYS = Object.entries(ENV_BINDINGS)
  .filter(([, envKey]) => Boolean(process.env[envKey]))
  .map(([key]) => key);

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
// settings.errorWorkflow must be the error workflow's ID, not its name — n8n
// resolves an id. On this instance WF-ERR is a real workflow with a real id,
// which is instance-specific, so it comes from the environment and defaults to
// the readable placeholder for a fresh clone.
export const PLACEHOLDER_ERROR_WORKFLOW = 'WF-ERR';
const ERROR_WORKFLOW = process.env.ICP_ERROR_WORKFLOW_ID || PLACEHOLDER_ERROR_WORKFLOW;

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

// Which CONFIG node an expression may reference depends on the path the node
// sits on. n8n resolves `$('X')` only when X is CONNECTED upstream of the node
// doing the referencing; Path B's nodes have CONFIG B upstream and CONFIG
// nowhere, so a Path B expression naming CONFIG fails at run time with an
// error whose own message is then lost (see n8n/nodes/Dedupe.js). One helper,
// one argument, no literals.
const cfgRef = (path) => (path === 'B' ? "$('CONFIG B')" : "$('CONFIG')");

const slackNode = (name, position, path, text, extra = {}) => ({
  parameters: {
    resource: 'message',
    operation: 'post',
    select: 'channel',
    // Driven from CONFIG, never a literal channel id.
    channelId: { __rl: true, value: `={{ ${cfgRef(path)}.item.json.slack_channel_ops }}`, mode: 'id' },
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
      // Pipedrive can put HTTP basic auth on the subscription
      // (http_auth_user / http_auth_password), and that is the better control
      // if the pair is ever set. It is not set on subscription 3167529, and an
      // n8n webhook with `authentication` set but no credential attached
      // answers every delivery with 500 "No authentication data defined on
      // node!" — so the node says 'none' and the unguessable path carries it,
      // the same control Path B runs on. Turning it back on means creating the
      // httpBasicAuth credential AND re-registering the subscription with the
      // matching pair; one without the other breaks the trigger silently.
      authentication: 'none',
      responseMode: 'responseNode',
      options: {},
    },
    id: 'Webhook Pipedrive',
    name: 'Webhook Pipedrive',
    type: 'n8n-nodes-base.webhook',
    typeVersion: 2,
    position: [-260, 200],
    webhookId: WEBHOOK_PATH_A,
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

  // The website gate. BuildClayRequest decided; this only routes.
  //
  // True is the ordinary path: a domain was resolved and the table gets asked.
  // False is not an error branch — it is an ordinary outcome with an ordinary
  // result, so it leaves the SAME footprint a scored run leaves: the two
  // organization fields, written together, and one activity.
  nodes.push(ifNode('IF has website?', [1740, 160], [boolCondition('$json.has_website', true)]));

  nodes.push({
    parameters: {
      method: 'POST',
      url: "={{ $('CONFIG').item.json.clay_engine_url }}",
      sendBody: true,
      specifyBody: 'json',
      jsonBody: '={{ JSON.stringify($json.body) }}',
      options: {},
    },
    id: 'POST Clay',
    name: 'POST Clay',
    type: 'n8n-nodes-base.httpRequest',
    typeVersion: 4.2,
    position: [1940, 60],
    // A retried POST creates a SECOND Clay row: a second scoring run and a
    // second credit. Never retry it.
    ...NO_RETRY,
  });

  // ----- no website: write the two fields, post one activity, stop ---------
  nodes.push(codeNode('BuildNoWebsiteWrite', [1940, 280], code('BuildNoWebsiteWrite')));

  // Same no-churn rule as Path B: a second deal on the same day for the same
  // website-less organization changes nothing, so it sends no PATCH — and
  // still posts its activity, because the activity is addressed to whoever
  // created THIS deal.
  nodes.push(ifNode('IF no-website write needed?', [2140, 280], [boolCondition('$json.patch_is_empty', false)]));

  nodes.push(httpNode('PATCH organization (no website)', [2340, 200], {
    method: 'PATCH',
    url: `=${PIPEDRIVE_V2}/organizations/{{ $json.org_id }}`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify($json.patch) }}',
  }, RETRY));

  // Reads BuildNoWebsiteWrite by name, not $json: on the written branch the
  // item arriving here is Pipedrive's PATCH response, and on the unchanged
  // branch it is the builder's own output. One source, both ways.
  nodes.push(httpNode('POST activity (no website)', [2540, 280], {
    method: 'POST',
    url: `=${PIPEDRIVE_V1}/activities`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody:
      '={{ JSON.stringify({ ' +
      "org_id: Number($('BuildNoWebsiteWrite').item.json.org_id), " +
      "subject: $('BuildNoWebsiteWrite').item.json.subject, " +
      "type: $('BuildNoWebsiteWrite').item.json.type, " +
      'done: true, ' +
      "note: $('BuildNoWebsiteWrite').item.json.body }) }}",
  }, NO_RETRY));

  // Non-blocking tee: anomaly gate on trigger volume.
  nodes.push(ifNode('IF rate exceeded?', [540, -100], [boolCondition('$json._rate_exceeded', true)]));
  nodes.push(slackNode(
    'Slack warn rate',
    [740, -100],
    'A',
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
      // No header auth. The owner's ruling: the unguessable path IS the
      // credential, and a shared secret would have had to live as a literal in
      // a Clay node's config, which is a worse place for one than nowhere.
      // n8n treats `authentication` set with no credential attached as a hard
      // 500 on every delivery ("No authentication data defined on node!"), so
      // this has to say 'none' rather than simply be omitted.
      authentication: 'none',
      responseMode: 'responseNode',
      options: {},
    },
    id: 'Webhook Clay',
    name: 'Webhook Clay',
    type: 'n8n-nodes-base.webhook',
    typeVersion: 2,
    position: [-260, 700],
    webhookId: WEBHOOK_PATH_B,
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

  // There is no Score node. The table scores; ParseScored checks that what
  // arrived can be written and hands it on flat. v6.0 held the rubric here and
  // recomputed the grade — two implementations of one rubric, which is exactly
  // the drift this project spent a release removing from Clay.

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

  nodes.push(codeNode('BuildActivity', [1740, 500], code('BuildActivity')));

  // ONE activity per scoring run, marked done so it lands as a record rather
  // than as a task in someone's queue. Activities are v1: the v2 endpoint does
  // not accept `note`, which is where the body goes.
  nodes.push(httpNode('POST activity', [1940, 500], {
    method: 'POST',
    url: `=${PIPEDRIVE_V1}/activities`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify({ org_id: Number($json.org_id), subject: $json.subject, type: $json.type, done: true, note: $json.body }) }}',
  }, NO_RETRY));

  nodes.push(codeNode('BuildRunSummary', [2140, 600], code('BuildRunSummary')));

  // ===== Error branch =====================================================
  //
  // v5 had BuildErrorPatch -> IF patch non-empty? -> PATCH organization error,
  // which set ICP Calculated to "Error" on the organization. All three are
  // gone: a failed run must leave the organization untouched, so the branch is
  // now the Slack alert and one activity, which is the same footprint the
  // happy path leaves.
  nodes.push(codeNode('BuildErrorContext', [940, 900], code('BuildErrorContext')));

  // Alert BEFORE the writes, with continue-on-fail: if marking the org as
  // Errored also fails, the human ping must still have gone out. This is the
  // one allow-listed continueOnFail in the workflow.
  nodes.push(slackNode(
    'Slack alert error',
    [1140, 900],
    'B',
    '=:rotating_light: ICP scoring failed. ' +
    'org_id={{ $json.org_id }} request_id={{ $json.request_id }} ' +
    'execution_id={{ $execution.id }} ' +
    'error={{ $json.error_name }}: {{ $json.error_message }}',
    { continueOnFail: true, ...NO_RETRY }
  ));

  // The error branch posts the SAME one activity the happy path does, so a
  // failed run leaves exactly the same footprint as a successful one: one
  // activity, no field write. v5 also set ICP Calculated to "Error" here; v6
  // does not touch the organization at all when it could not score it, because
  // a field that says "Error" is a field a rep has to learn to ignore.
  // Every field comes from BuildErrorContext BY NAME, never from $json: this
  // node's input is the Slack API response, so $json.org_id was `undefined`
  // and the failure activity landed on no organization at all (activity 46842,
  // execution 60629). A Number(undefined) is NaN, which Pipedrive accepts as
  // "no organization" rather than rejecting.
  const errRef = "$('BuildErrorContext').item.json";
  nodes.push(httpNode('POST activity error', [1740, 820], {
    method: 'POST',
    url: `=${PIPEDRIVE_V1}/activities`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody:
      '={{ JSON.stringify({ ' +
      `org_id: Number(${errRef}.org_id), ` +
      `subject: ${cfgRef('B')}.item.json.activity_subject_failed, ` +
      `type: ${cfgRef('B')}.item.json.activity_type, done: true, note: ` +
      "'Not scored — the run failed before a grade could be produced.' + '\\n\\n' + " +
      `'Reason: ' + ${errRef}.error_message + '\\n\\n' + ` +
      `(${errRef}.problem_count > 0 ? 'What was wrong with the data: ' + ${errRef}.problems.join('; ') + '\\n\\n' : '') + ` +
      "'CHECK: this is a system fault, not a judgement about the company — the run trace has the detail.'" +
      ' }) }}',
  }, NO_RETRY));

  // Wired LAST on the error branch so everything else has already run.
  nodes.push(codeNode('FailLoudly', [1940, 820], code('FailLoudly')));



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
    BuildClayRequest: { main: [out('IF has website?'), out('BuildErrorContext')] },
    'IF has website?': branch(['POST Clay'], ['BuildNoWebsiteWrite']),
    BuildNoWebsiteWrite: main('IF no-website write needed?'),
    // Both branches converge on the activity: exactly one runs, so exactly one
    // activity is posted either way.
    'IF no-website write needed?': branch(
      ['PATCH organization (no website)'],
      ['POST activity (no website)']
    ),
    'PATCH organization (no website)': main('POST activity (no website)'),

    // Path B
    'Webhook Clay': main('Respond 200 B'),
    'Respond 200 B': main('CONFIG B'),
    'CONFIG B': main('Dedupe B'),
    'Dedupe B': main('ParseScored'),
    // ParseScored's second output is its error branch (onError:
    // continueErrorOutput): a malformed event goes straight to the failure
    // branch, which alerts, records, and then THROWS so the execution ends red.
    ParseScored: { main: [out('IF write allowed?'), out('BuildErrorContext')] },
    // A duplicate skips the writes and goes straight to the audit row.
    'IF write allowed?': branch(['GET organization B'], ['BuildRunSummary']),
    'GET organization B': main('BuildOrgPatch'),
    BuildOrgPatch: main('IF patch non-empty?'),
    // An empty patch means nothing changed, so no PATCH and no second note —
    // but still an audit row.
    'IF patch non-empty?': branch(['PATCH organization'], ['BuildRunSummary']),
    'PATCH organization': main('BuildActivity'),
    BuildActivity: main('POST activity'),
    // BuildRunSummary is the end of the line. Its output IS the run's trace:
    // it lands in the n8n execution, which is where a disputed score is read
    // from now that there is no table.
    'POST activity': main('BuildRunSummary'),

    // Error branch: alert a human first — if posting the activity also fails,
    // the ping must still have gone out — then leave the one activity. The
    // organization is not touched at all.
    BuildErrorContext: main('Slack alert error'),
    'Slack alert error': main('POST activity error'),
    // Last, and it throws. The alert and the activity have already happened;
    // the throw is what turns a quietly-successful execution red so
    // settings.errorWorkflow (WF-ERR) fires and the failure reaches Slack.
    'POST activity error': main('FailLoudly'),
  };

  const workflow = {
    name: 'WF-ICP-Score',
    nodes,
    connections,
    settings: {
      executionOrder: 'v1',
      // Anything this workflow's own error branch cannot handle — a failed
      // PATCH cannot mark itself as Errored — reaches WF-ERR, which Slacks.
      errorWorkflow: ERROR_WORKFLOW,
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

  // n8n/workflows/ holds only gitignored build output, so git does not carry
  // the directory and a fresh clone does not have it. Create it rather than
  // requiring a manual mkdir — this is what the fresh-clone check caught.
  mkdirSync(dirname(OUT), { recursive: true });

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
    `  active: ${workflow.active}  errorWorkflow: ${workflow.settings.errorWorkflow}` +
    `${ERROR_WORKFLOW === PLACEHOLDER_ERROR_WORKFLOW ? ' (placeholder — set ICP_ERROR_WORKFLOW_ID)' : ' (from env)'}\n` +
    `  credentials in canonical export: ${credentialled} node(s)\n` +
    `  credentials in import payload:   0 (stripped)\n` +
    `  webhook paths: ${USING_PLACEHOLDER_PATHS ? 'PLACEHOLDER — set ICP_WEBHOOK_PATH_A/B for a real import' : 'from ICP_WEBHOOK_PATH_A/B'}\n` +
    `  CONFIG source: ${CONFIG_IS_LIVE ? 'CONFIG.local.json (LIVE field keys)' : 'CONFIG.json (placeholders)'}\n` +
    `  baked at build: ${BAKED_KEYS.length ? BAKED_KEYS.join(', ') : '(none — runtime $vars/$env only)'}\n` +
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
