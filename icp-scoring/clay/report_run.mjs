#!/usr/bin/env node
/**
 * clay/report_run.mjs — the per-row readout for one Clay Workflow run.
 *
 * Prints what a reviewer actually asks for: grade, score, confidence, status,
 * and every classifier's value with the evidence it cited — plus which nodes
 * ran and what each enrichment step cost.
 *
 *   node clay/report_run.mjs --workflow wf_x --run wfr_y --label Akuvo
 */

import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const arg = (n, d = null) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };

const WORKFLOW = arg('workflow');
const RUN = arg('run');
const LABEL = arg('label', RUN);
if (!WORKFLOW || !RUN) {
  console.error('usage: node clay/report_run.mjs --workflow wf_x --run wfr_y [--label Name]');
  process.exit(2);
}

const clay = (args) =>
  JSON.parse(execFileSync('clay', args, { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }));

// Data Credits per provider step, from each action's own
// metadata.upfrontCreditUsage.totalCost. HTTP API is 0 Data Credits and 1
// Action — see clay/WORKFLOW.md, "Credits: two currencies".
const DATA_CREDITS = {
  '03 Enrich company profile': 1,
  '06 Scrape site pages': 4,          // once per page, four pages
  '11 Enrich revenue and headcount': 3,
  '12 Find financing events': 4,
  '13 Find open engineering roles': 1,
  '14 Find recent news': 1,
};
const ACTIONS_PER_NODE = {
  '06 Scrape site pages': 4,
};

const run = clay(['workflows', 'runs', 'get', WORKFLOW, RUN, '--nodes', '--verbose']);
const graph = clay(['workflows', 'graph', 'get', WORKFLOW]);
const nameOf = Object.fromEntries((graph.summary?.nodes ?? []).map((n) => [n.id, n.name]));

const nodes = (run.nodes ?? []).map((n) => ({ name: nameOf[n.nodeId] ?? n.nodeId, ...n }));
const find = (needle) => nodes.find((n) => n.name.includes(needle));

const event = find('Build icp.scored event')?.outputs?.event ?? null;
const facts = find('Build facts_json')?.outputs?.facts ?? null;

const line = (s = '') => console.log(s);
line(`\n${'='.repeat(78)}`);
line(`${LABEL}   run ${RUN}   status ${run.status}`);
line('='.repeat(78));

if (!event) {
  line('\nNo icp.scored event was produced. Nodes:');
  for (const n of nodes) line(`  ${n.status.padEnd(10)} ${n.name}`);
  const failed = nodes.filter((n) => n.status === 'failed');
  for (const n of failed) line(`\n  FAILED ${n.name}:\n    ${(n.errors ?? []).join('\n    ')}`);
} else {
  const s = event.score;
  line(`\n  grade               ${s.grade ?? 'null'}`);
  line(`  final_score         ${s.final_score}   (before activation: ${s.final_score_without_activation})`);
  line(`  status              ${s.status}`);
  line(`  confidence_overall  ${s.confidence_overall}`);
  line(`  activation          ${s.activation_state_used}  x${s.multiplier}`);
  line(`  industry            ${event.components.industry_vertical.value ?? 'null'}`
     + `  tier ${s.industry_tier ?? 'null'}  level ${s.industry_level}`);
  line(`  tier2_candidate     ${s.tier2_candidate}`);
  line(`  flags               ${s.flags.length ? s.flags.join(', ') : '(none)'}`);
  line(`  composite           ${s.composite}`);
  line(`  levels_used         ${JSON.stringify(s.levels_used)}`);

  line('\n  classifiers');
  for (const [name, c] of Object.entries(event.components)) {
    line(`    ${name}  =  ${JSON.stringify(c.value)}   [${c.confidence}]`);
    for (const e of c.evidence) line(`        · ${e}`);
    if (c.missing_inputs.length) line(`        missing: ${c.missing_inputs.join(', ')}`);
  }
}

if (facts) {
  line('\n  facts that carried the score');
  for (const k of ['revenue_estimate_usd', 'revenue_source', 'li_headcount', 'eng_headcount_estimate',
                   'funding_stage', 'last_round_date', 'last_round_usd', 'open_eng_roles_count',
                   'eng_roles_open_60d_plus', 'senior_eng_roles']) {
    line(`    ${k.padEnd(24)} ${JSON.stringify(facts[k])}`);
  }
  line(`    news_last_12mo           ${facts.news_last_12mo === null ? 'null' : `${facts.news_last_12mo.length} item(s)`}`);
}

line('\n  nodes and cost');
let dataCredits = 0;
let actions = 0;
for (const n of nodes) {
  const dc = n.status === 'completed' ? (DATA_CREDITS[n.name] ?? 0) : 0;
  const isAction = n.name.match(/^(0[369]|1[1234]|1[789]|2[0123]|27) /);
  const act = n.status === 'completed' && isAction ? (ACTIONS_PER_NODE[n.name] ?? 1) : 0;
  dataCredits += dc;
  actions += act;
  const cost = dc || act ? `${dc} DC / ${act} Action${act === 1 ? '' : 's'}` : '';
  line(`    ${n.status.padEnd(10)} ${n.name.padEnd(36)} ${cost}`);
}
line(`\n    TOTAL  ${dataCredits} Data Credits + ${actions} Actions (+ OpenAI tokens on the workspace key)`);
line('');
