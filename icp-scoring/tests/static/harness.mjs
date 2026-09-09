// tests/static/harness.mjs — execute the REAL Code-node source.
//
// The point is that the tests run the exact bytes deployed in
// WF-ICP-Score.dev.json. Nothing here reimplements node logic; it only
// provides the scope n8n provides: $input, $('NodeName'), $getWorkflowStaticData,
// $execution, $now, $env.
//
// Code nodes run in "Run Once for All Items" mode, so $json is deliberately
// NOT provided — a node that reaches for it should fail here exactly as it
// would in n8n.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
export const ROOT = join(HERE, '..', '..');
const NODES = join(ROOT, 'n8n', 'nodes');

export const readNode = (name) => readFileSync(join(NODES, `${name}.js`), 'utf8');
export const readJson = (...parts) => JSON.parse(readFileSync(join(ROOT, ...parts), 'utf8'));

/** A fixed clock, so a date-dependent assertion never depends on the wall clock. */
export const NOW_ISO = '2026-09-09T12:00:00.000Z';

/**
 * CONFIG as the Set node produces it: the static payload plus the four
 * env-sourced values plus now_iso.
 */
export function makeConfig(overrides = {}) {
  const staticConfig = readJson('n8n', 'nodes', 'CONFIG.json');
  return {
    ...staticConfig,
    // Deterministic stand-ins for the option ids a live create_fields run
    // supplies. They are numbers because Pipedrive option ids are numbers,
    // which is what BuildOrgPatch writes.
    opt_icp_calculated: {
      'ICP A': 101, 'ICP B': 102, 'ICP C': 103,
      'Insufficient data': 104, 'Error': 105,
    },
    clay_webhook_url: 'https://hooks.clay.test/icp-engine',
    clay_callback_url: 'https://n8n.test/webhook/icp-scored-clay-dev',
    audit_sheet_id: 'sheet-icp-audit-dev',
    slack_channel_ops: 'CDEVOPS001',
    now_iso: NOW_ISO,
    ...overrides,
  };
}

/**
 * Run one Code-node source.
 *
 * @param {string} source        the node's jsCode, read from n8n/nodes/
 * @param {object} opts
 * @param {object[]} opts.input  items on the node's input ($input)
 * @param {object} opts.nodes    { 'NodeName': itemJson } for $('NodeName')
 * @param {object} opts.staticData shared across calls when you pass the same object
 * @param {string} opts.executionId
 * @param {object} opts.env
 * @returns {object[]} the items the node returned
 */
export function runCodeNode(source, opts = {}) {
  const input = opts.input || [];
  const nodeOutputs = opts.nodes || {};
  const staticData = opts.staticData || {};

  const asItem = (json) => ({ json });

  const $input = {
    all: () => input.map(asItem),
    first: () => asItem(input[0]),
    last: () => asItem(input[input.length - 1]),
    get item() { return asItem(input[0]); },
  };

  const $ = (name) => {
    if (!Object.prototype.hasOwnProperty.call(nodeOutputs, name)) {
      // n8n throws when a referenced node has not executed in this run. Code
      // that relies on catching this (Dedupe telling the two paths apart)
      // must see the same behaviour here.
      const error = new Error(`Referenced node "${name}" is unexecuted`);
      error.name = 'NodeOperationError';
      throw error;
    }
    const json = nodeOutputs[name];
    return { item: asItem(json), first: () => asItem(json), all: () => [asItem(json)] };
  };

  const $getWorkflowStaticData = (scope) => {
    staticData[scope] = staticData[scope] || {};
    return staticData[scope];
  };

  const $execution = { id: opts.executionId || 'exec-test-0001', mode: 'test', resumeUrl: null };
  const $now = {
    toISO: () => (opts.nodes && opts.nodes.CONFIG && opts.nodes.CONFIG.now_iso) || NOW_ISO,
  };
  const $env = opts.env || {};
  const $workflow = { id: 'wf-icp-score-dev', name: 'WF-ICP-Score', active: false };

  // eslint-disable-next-line no-new-func
  const fn = new Function(
    '$input', '$', '$getWorkflowStaticData', '$execution', '$now', '$env', '$workflow',
    source
  );
  const result = fn($input, $, $getWorkflowStaticData, $execution, $now, $env, $workflow);
  return result === undefined ? [] : result;
}

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

/** Resolve an "@days_ago:N" marker against the harness clock. */
function resolveMarker(value, nowIso) {
  if (typeof value !== 'string') return value;
  const match = value.match(/^@days_ago:(\d+)$/);
  if (!match) return value;
  const then = new Date(new Date(nowIso).getTime() - Number(match[1]) * 86400000);
  return then.toISOString().slice(0, 10);
}

/**
 * Load a Pipedrive org fixture and expand its symbolic ICP block into hashed
 * custom_fields using CONFIG.
 *
 * Fixtures carry `_icp_symbolic: { icp_calculated: "ICP A", ... }` instead of
 * 40-hex keys, so they stay readable and survive create_fields replacing the
 * placeholder keys with real ones.
 */
export function orgFixture(name, cfg, { nowIso = NOW_ISO } = {}) {
  const fixture = readJson('tests', 'fixtures', 'pipedrive', name);
  const org = structuredClone(fixture.data);
  const symbolic = fixture._icp_symbolic;

  if (symbolic) {
    org.custom_fields = org.custom_fields || {};
    for (const [slug, rawValue] of Object.entries(symbolic)) {
      const key = cfg[`f_${slug}`];
      if (!key) throw new Error(`orgFixture: CONFIG has no key f_${slug}`);
      let value = resolveMarker(rawValue, nowIso);
      // An enum is stored as an option id, which is what Pipedrive returns.
      if (slug === 'icp_calculated' || slug === 'icp_final') {
        const optionId = cfg.opt_icp_calculated[value];
        if (optionId === undefined) throw new Error(`orgFixture: no option id for "${value}"`);
        value = optionId;
      }
      org.custom_fields[key] = value;
    }
  }

  return { fixture, org };
}

export const clayFixture = (name) => readJson('tests', 'fixtures', 'clay', name);
export const pipedriveFixture = (name) => readJson('tests', 'fixtures', 'pipedrive', name);
