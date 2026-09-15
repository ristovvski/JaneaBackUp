// n8n/patch/validate.mjs — refuse to emit a bad workflow.
//
// This is the patcher's own gate, run before anything is written. It overlaps
// tests/static/workflow_review.test.mjs on purpose: the test tells a developer
// the export is wrong, this stops a wrong export existing in the first place.
//
// Returns an array of human-readable findings. Empty means clean.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const HASH_40_HEX = /\b[0-9a-f]{40}\b/;
// A Slack channel id is C + 8-10 uppercase alphanumerics. Inside JS source an
// ordinary identifier (COMPONENTS, CONFIDENCE_RANK) matches that shape, so
// jsCode is checked for the QUOTED form only.
const SLACK_CHANNEL_ID = /\bC[A-Z0-9]{8,10}\b/;
const SLACK_CHANNEL_ID_QUOTED = /['"`]C[A-Z0-9]{8,10}['"`]/;
const SECRET_SHAPES = [
  { pattern: /api_token=/, why: 'a token in a query string' },
  { pattern: /Bearer\s+[A-Za-z0-9._-]{8,}/, why: 'a bearer token' },
  { pattern: /\bsk-[A-Za-z0-9]{8,}/, why: 'an API key' },
  { pattern: /\bxox[baprs]-[A-Za-z0-9-]{8,}/, why: 'a Slack token' },
  { pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/, why: 'a private key' },
];

// The one node allowed to swallow its own failure: the error-branch Slack
// alert, posted BEFORE the writes so a failing CRM write cannot silence the
// human ping. Anything else with continueOnFail is hiding an error.
export const CONTINUE_ON_FAIL_ALLOWLIST = ['Slack alert error'];

// Creators. A retried create is a duplicate.
export const MUST_NOT_RETRY = ['POST note', 'POST note error', 'POST Clay', 'Append audit row'];

export function validate(workflow, { nodesDir } = {}) {
  const findings = [];
  const push = (msg) => findings.push(msg);

  // --- shape ------------------------------------------------------------
  for (const key of ['name', 'nodes', 'connections', 'settings']) {
    if (!(key in workflow)) push(`workflow is missing "${key}"`);
  }
  if (!Array.isArray(workflow.nodes) || workflow.nodes.length === 0) {
    push('workflow has no nodes');
    return findings;
  }

  // --- hard invariants ---------------------------------------------------
  if (workflow.active !== false) push(`active must be false, got ${JSON.stringify(workflow.active)}`);
  if ('pinData' in workflow) push('pinData must not be present in an exported workflow');
  if (!workflow.settings || !workflow.settings.errorWorkflow) {
    push('settings.errorWorkflow must be set so terminal errors are observable');
  }

  const names = workflow.nodes.map((n) => n.name);
  const duplicates = names.filter((n, i) => names.indexOf(n) !== i);
  if (duplicates.length > 0) push(`duplicate node names: ${[...new Set(duplicates)].join(', ')}`);

  const byName = new Map(workflow.nodes.map((n) => [n.name, n]));

  // --- connections reference real nodes ---------------------------------
  for (const [source, outputs] of Object.entries(workflow.connections)) {
    if (!byName.has(source)) push(`connections references unknown source node "${source}"`);
    // n8n requires { main: [...] }. A bare array imports as NO connections at
    // all, silently, so this is a hard fail rather than a tolerated variant.
    if (!outputs || !Array.isArray(outputs.main)) {
      push(`connections["${source}"] must be an object with a "main" array`);
      continue;
    }
    for (const output of outputs.main) {
      if (!Array.isArray(output)) {
        push(`connections["${source}"].main must be an array of arrays`);
        continue;
      }
      for (const target of output) {
        if (!target || typeof target.node !== 'string') {
          push(`connections["${source}"] has a malformed target`);
        } else if (!byName.has(target.node)) {
          push(`connection ${source} -> unknown node "${target.node}"`);
        }
      }
    }
  }

  // --- a trigger exists --------------------------------------------------
  const triggers = workflow.nodes.filter((n) => /webhook|trigger/i.test(n.type));
  if (triggers.length === 0) push('no trigger node');

  // --- every webhook is authenticated -----------------------------------
  for (const node of workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.webhook')) {
    const auth = node.parameters && node.parameters.authentication;
    if (!auth || auth === 'none') {
      push(`webhook "${node.name}" has no authentication (got ${JSON.stringify(auth)})`);
    }
    if (!node.credentials || Object.keys(node.credentials).length === 0) {
      push(`webhook "${node.name}" declares authentication but references no credential`);
    }
  }

  // --- CONFIG is first on each path -------------------------------------
  const configNodes = workflow.nodes.filter((n) => /^CONFIG/.test(n.name));
  if (configNodes.length === 0) push('no CONFIG node');
  for (const node of configNodes) {
    if (node.type !== 'n8n-nodes-base.set') {
      push(`"${node.name}" must be a Set node, got ${node.type}`);
    }
  }

  // --- Code nodes are byte-identical to their source files --------------
  if (nodesDir) {
    const sources = new Map(
      readdirSync(nodesDir).filter((f) => f.endsWith('.js'))
        .map((f) => [f.replace(/\.js$/, ''), readFileSync(join(nodesDir, f), 'utf8')])
    );
    const used = new Set();
    for (const node of workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
      // "Dedupe B" deploys Dedupe.js: strip a single-letter path suffix.
      const base = node.name.replace(/ [AB]$/, '');
      const source = sources.get(base);
      if (source === undefined) {
        push(`Code node "${node.name}" has no source file n8n/nodes/${base}.js`);
        continue;
      }
      used.add(base);
      if (node.parameters.jsCode !== source) {
        push(`Code node "${node.name}" jsCode is not byte-identical to n8n/nodes/${base}.js`);
      }
    }
    for (const base of sources.keys()) {
      if (!used.has(base)) push(`n8n/nodes/${base}.js is not deployed by any Code node`);
    }
  }

  // --- no literal ids or secrets outside CONFIG -------------------------
  for (const node of workflow.nodes) {
    const isConfig = /^CONFIG/.test(node.name);
    const serialized = JSON.stringify(node.parameters || {});

    for (const { pattern, why } of SECRET_SHAPES) {
      if (pattern.test(serialized)) push(`node "${node.name}" looks like it contains ${why}`);
    }

    if (!isConfig) {
      if (HASH_40_HEX.test(serialized)) {
        push(`node "${node.name}" contains a literal 40-hex Pipedrive field key — it belongs in CONFIG`);
      }
      const isCode = node.type === 'n8n-nodes-base.code';
      const channelPattern = isCode ? SLACK_CHANNEL_ID_QUOTED : SLACK_CHANNEL_ID;
      if (channelPattern.test(serialized)) {
        push(`node "${node.name}" contains a literal Slack channel id — it belongs in CONFIG`);
      }
    }
  }

  // Credentials are referenced by name, never inlined.
  for (const node of workflow.nodes) {
    for (const [type, credential] of Object.entries(node.credentials || {})) {
      if (!credential || !credential.name) {
        push(`node "${node.name}" has a ${type} credential with no name`);
      }
      for (const key of Object.keys(credential || {})) {
        if (!['id', 'name'].includes(key)) {
          push(`node "${node.name}" credential ${type} carries an unexpected key "${key}"`);
        }
      }
    }
  }

  // --- retry semantics ---------------------------------------------------
  for (const name of MUST_NOT_RETRY) {
    const node = byName.get(name);
    if (!node) { push(`expected a node named "${name}"`); continue; }
    if (node.retryOnFail !== false) {
      push(`"${name}" creates an entity, so retryOnFail must be false (a retried create is a duplicate)`);
    }
  }
  for (const node of workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest')) {
    const method = (node.parameters && node.parameters.method) || 'GET';
    if (['GET', 'PATCH'].includes(method) && node.retryOnFail !== true) {
      push(`"${node.name}" is an idempotent ${method} and should have retry configured`);
    }
  }

  // --- continueOnFail allow-list ----------------------------------------
  for (const node of workflow.nodes) {
    if (node.continueOnFail === true && !CONTINUE_ON_FAIL_ALLOWLIST.includes(node.name)) {
      push(`node "${node.name}" sets continueOnFail — only ${CONTINUE_ON_FAIL_ALLOWLIST.join(', ')} may`);
    }
  }

  // --- Slack alerts carry the ids you need to find the run --------------
  for (const node of workflow.nodes.filter((n) => n.type === 'n8n-nodes-base.slack')) {
    const text = (node.parameters && node.parameters.text) || '';
    if (!text.includes('$execution.id')) push(`Slack node "${node.name}" text omits execution_id`);
    if (!/request_id|_dedupe_key/.test(text)) push(`Slack node "${node.name}" text omits request_id`);
    const channel = JSON.stringify((node.parameters || {}).channelId || '');
    if (!channel.includes("$('CONFIG')")) {
      push(`Slack node "${node.name}" channel must come from a CONFIG expression`);
    }
  }

  // --- expressions ------------------------------------------------------
  // "{{ ... }}" without a leading "=" posts literal braces (a real incident).
  const walk = (value, path) => {
    if (typeof value === 'string') {
      if (value.includes('{{') && !value.startsWith('=')) {
        push(`${path} contains "{{" but does not start with "=" — it would post literal braces`);
      }
      // n8n ends an expression at the FIRST "}}". A nested one — which any
      // embedded JSON object produces — truncates the expression silently: the
      // workflow imports, the editor looks right, and the node fails at run
      // time with an error from the JSON parser, not the expression engine.
      // This cost a live execution to find (CONFIG, "invalid syntax").
      // Only whole-string expressions ("={{ ... }}") are checked. A parameter
      // like "=execution_id={{ a }} request_id={{ b }}" is legal n8n: several
      // expressions interleaved with literal text, and its second "}}" is a
      // closing delimiter, not a nested one.
      //
      // For a whole-string expression the test is exact: the first "}}" after
      // the opening must BE the closing one. If anything follows it, n8n closed
      // the expression early and the remainder is literal text.
      if (value.startsWith('={{') && value.trimEnd().endsWith('}}')) {
        const first = value.indexOf('}}', 3);
        if (first !== -1 && first !== value.trimEnd().length - 2) {
          push(`${path} has "}}" inside the expression body at offset ${first} — n8n closes the `
             + 'expression there and the rest becomes literal text (write "} }" instead)');
        }
      }
    } else if (Array.isArray(value)) {
      value.forEach((v, i) => walk(v, `${path}[${i}]`));
    } else if (value && typeof value === 'object') {
      for (const [k, v] of Object.entries(value)) walk(v, `${path}.${k}`);
    }
  };
  for (const node of workflow.nodes) {
    // jsCode is JavaScript, not an n8n expression: "{{" is legal there.
    const { jsCode, ...expressionParams } = node.parameters || {};
    walk(expressionParams, `node "${node.name}".parameters`);
  }

  // --- ICP Final is never written ---------------------------------------
  const writers = workflow.nodes.filter(
    (n) => n.type === 'n8n-nodes-base.httpRequest' &&
           ['PATCH', 'PUT', 'POST'].includes((n.parameters || {}).method)
  );
  for (const node of writers) {
    const body = JSON.stringify(node.parameters);
    if (/f_icp_final/.test(body)) {
      push(`write node "${node.name}" references f_icp_final — ICP Final must never be written`);
    }
  }

  return findings;
}
