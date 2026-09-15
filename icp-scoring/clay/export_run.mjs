#!/usr/bin/env node
/**
 * clay/export_run.mjs — pull one Clay Workflow run apart into the artefacts a
 * reviewer and the golden harness need.
 *
 * Writes:
 *   tests/golden/facts/<name>.json               the fact set the classifiers read
 *   tests/golden/events/<name>.icp_scored.json   the event POSTed to n8n Path B
 *   reports/clay-runs/<name>.trace.json          per-node status, inputs, outputs
 *
 * The first two are committed; the trace is NOT. A trace carries every node's
 * raw inputs, and node 01's inputs include `callback_url` — an n8n webhook path,
 * which SECURITY.md treats as a credential. The facts file and the event carry
 * no such field, which is why those two are the ones in the repository.
 *
 * The facts file is the point: it is the exact fact set a live enrichment
 * waterfall produced, so the golden harness can re-score it offline forever
 * without an API key, and a rubric change can be replayed against real data
 * rather than hand-authored fixtures.
 *
 * Usage:
 *   node clay/export_run.mjs --workflow wf_x --run wfr_y --name akuvo [--out DIR]
 */

import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const arg = (n, d = null) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };

const WORKFLOW = arg('workflow');
const RUN = arg('run');
const NAME = arg('name');
const OUT = arg('out', join(ROOT, 'reports', 'clay-runs'));
if (!WORKFLOW || !RUN || !NAME) {
  console.error('usage: node clay/export_run.mjs --workflow wf_x --run wfr_y --name akuvo');
  process.exit(2);
}

const clay = (args) =>
  JSON.parse(execFileSync('clay', args, { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }));

const run = clay(['workflows', 'runs', 'get', WORKFLOW, RUN, '--nodes', '--verbose']);
const graph = clay(['workflows', 'graph', 'get', WORKFLOW]);
const nameOf = Object.fromEntries((graph.summary?.nodes ?? []).map((n) => [n.id, n.name]));

const nodes = (run.nodes ?? []).map((n) => ({
  node: nameOf[n.nodeId] ?? n.nodeId,
  nodeId: n.nodeId,
  status: n.status,
  startedAt: n.startedAt ?? null,
  finishedAt: n.finishedAt ?? null,
  credits: n.credits ?? n.creditsUsed ?? n.metadata?.credits ?? null,
  errors: n.errors ?? null,
  inputs: n.inputs ?? null,
  outputs: n.outputs ?? null,
}));

const byName = (needle) => nodes.find((n) => n.node.includes(needle));

// Clay does not preserve the key order a code node returned, so the fact set is
// re-ordered here against the schema before it is written. A golden file that
// reshuffles between runs cannot be diffed, which is most of what it is for.
const FACT_SCHEMA = JSON.parse(
  readFileSync(join(ROOT, 'engine', 'schemas', 'enrichment_facts.schema.json'), 'utf8'),
);
const FACT_ORDER = Object.keys(FACT_SCHEMA.properties);

function orderFacts(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const out = {};
  for (const key of FACT_ORDER) if (key in raw) out[key] = raw[key];
  for (const key of Object.keys(raw)) if (!(key in out)) out[key] = raw[key];  // never drop
  return out;
}

const facts = orderFacts(byName('Build facts_json')?.outputs?.facts ?? null);
const scored = byName('Build icp.scored event')?.outputs?.event ?? null;

mkdirSync(OUT, { recursive: true });
writeFileSync(
  join(OUT, `${NAME}.trace.json`),
  `${JSON.stringify({ runId: RUN, status: run.status, nodes }, null, 2)}\n`,
);

if (facts) {
  const dir = join(ROOT, 'tests', 'golden', 'facts');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, `${NAME}.json`), `${JSON.stringify(facts, null, 2)}\n`);
  console.log(`tests/golden/facts/${NAME}.json    ${Object.keys(facts).length} keys`);
} else {
  console.error(`no facts_json in run ${RUN} — the Build facts_json node did not produce output`);
}

if (scored) {
  const dir = join(ROOT, 'tests', 'golden', 'events');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, `${NAME}.icp_scored.json`), `${JSON.stringify(scored, null, 2)}\n`);
  console.log(`tests/golden/events/${NAME}.icp_scored.json    grade ${
    scored.score?.grade ?? 'null'} / ${scored.score?.final_score} / ${scored.score?.status}`);
}
console.log(`reports/clay-runs/${NAME}.trace.json    ${nodes.length} nodes, run ${run.status}`);
