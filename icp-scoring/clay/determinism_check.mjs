#!/usr/bin/env node
/**
 * clay/determinism_check.mjs — how deterministic are the classifiers, really?
 *
 * `clay_table_spec.md` §7 calls temperature 0 non-negotiable: "a score that
 * changes between runs cannot be audited or re-derived". The GPT-5.6 family
 * rejects `temperature: 0` outright (HTTP 400, "Only the default (1) value is
 * supported"), so the build pins `seed: 0` behind a closed strict schema
 * instead. A seed is a best-effort hint, not a guarantee.
 *
 * This measures the gap rather than arguing about it: each classifier is sent
 * the SAME request three times, and the three replies are compared field by
 * field. What matters is not byte-identity of the prose — it is whether `value`
 * and `confidence` move, because those are what the score is computed from.
 *
 *   node --env-file=<envfile> clay/determinism_check.mjs [--facts akuvo] [--runs 3]
 *
 * Costs 7 x runs OpenAI calls on the workspace's own key. No Clay credits.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { classifierPrompt, COMPONENTS, STRICT_SCHEMAS, MODELS } from './build_workflow.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const arg = (n, d) => { const i = argv.indexOf(`--${n}`); return i === -1 ? d : argv[i + 1]; };

const FACTS = arg('facts', 'akuvo');
const RUNS = Number(arg('runs', 3));
const KEY = process.env.OPENAI_API_KEY;

if (!KEY) {
  console.error('OPENAI_API_KEY is not set. Run with: node --env-file=<envfile> clay/determinism_check.mjs');
  process.exit(2);
}

const factsPath = join(ROOT, 'tests', 'golden', 'facts', `${FACTS}.json`);
if (!existsSync(factsPath)) {
  console.error(`no captured facts at tests/golden/facts/${FACTS}.json`);
  process.exit(2);
}
const facts = readFileSync(factsPath, 'utf8');

/** The body node 16 builds, reproduced exactly — same prompt, schema, seed. */
const bodyFor = (component) => ({
  model: MODELS.classifier,
  seed: 0,
  response_format: { type: 'json_schema', json_schema: STRICT_SCHEMAS[component] },
  messages: [
    { role: 'system', content: classifierPrompt(component) },
    {
      role: 'user',
      content: `Classify the component \`${component}\` for this company.\n\n`
        + 'This is the complete fact set. Nothing outside it is evidence.\n\n'
        + `\`\`\`json\n${facts}\n\`\`\``,
    },
  ],
});

async function call(component) {
  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(bodyFor(component)),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`${component}: HTTP ${res.status} ${JSON.stringify(err.error ?? {}).slice(0, 200)}`);
  }
  const parsed = await res.json();
  return JSON.parse(parsed.choices[0].message.content);
}

const same = (xs) => xs.every((x) => JSON.stringify(x) === JSON.stringify(xs[0]));

const rows = [];
for (const [component] of COMPONENTS) {
  const replies = [];
  for (let i = 0; i < RUNS; i += 1) replies.push(await call(component));   // eslint-disable-line no-await-in-loop

  const values = replies.map((r) => r.value);
  const confs = replies.map((r) => r.confidence);
  const evidence = replies.map((r) => r.evidence);

  rows.push({
    component,
    valueStable: same(values),
    confStable: same(confs),
    evidenceStable: same(evidence),
    values: [...new Set(values.map((v) => JSON.stringify(v)))],
    confs: [...new Set(confs)],
    evidenceSizes: evidence.map((e) => (e ?? []).length),
  });
  const mark = same(values) && same(confs) ? 'stable' : 'UNSTABLE';
  console.log(`${component.padEnd(18)} ${mark.padEnd(9)} value=${[...new Set(values.map((v) => JSON.stringify(v)))].join(' | ')}  confidence=${[...new Set(confs)].join(' | ')}`);
}

const scoring = rows.filter((r) => !r.valueStable);
const conf = rows.filter((r) => !r.confStable);
const prose = rows.filter((r) => !r.evidenceStable);

console.log('');
console.log(`${RUNS} runs per classifier on tests/golden/facts/${FACTS}.json, model ${MODELS.classifier}, seed 0, no temperature.`);
console.log(`  value drifted:      ${scoring.length} of ${rows.length}${scoring.length ? ' -> ' + scoring.map((r) => r.component).join(', ') : ''}`);
console.log(`  confidence drifted: ${conf.length} of ${rows.length}${conf.length ? ' -> ' + conf.map((r) => r.component).join(', ') : ''}`);
console.log(`  evidence drifted:   ${prose.length} of ${rows.length}${prose.length ? ' -> ' + prose.map((r) => r.component).join(', ') : ''}`);
console.log('');
console.log(scoring.length === 0 && conf.length === 0
  ? 'Every input to the score was identical across all runs. Evidence prose may still vary; it does not enter the score.'
  : 'A scoring input moved between identical requests. The score is not reproducible for this fact set.');

const out = join(ROOT, 'reports', 'determinism.md');
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, [
  '# Classifier determinism — measured, not assumed',
  '',
  `Generated by \`clay/determinism_check.mjs\`. ${RUNS} identical requests per classifier,`,
  `fact set \`tests/golden/facts/${FACTS}.json\`, model \`${MODELS.classifier}\`, \`seed: 0\`,`,
  'no `temperature` (the GPT-5.6 family rejects `temperature: 0` with HTTP 400).',
  '',
  '`value` and `confidence` are what the score is computed from. `evidence` is prose:',
  'it is worth knowing when it moves, but it does not change a grade.',
  '',
  '| Component | value | confidence | evidence | values seen |',
  '|---|---|---|---|---|',
  ...rows.map((r) => `| \`${r.component}\` | ${r.valueStable ? 'stable' : '**drifted**'} | ${r.confStable ? 'stable' : '**drifted**'} | ${r.evidenceStable ? 'stable' : 'drifted'} | ${r.values.join(' · ')} |`),
  '',
  `**${rows.length - scoring.length} of ${rows.length}** classifiers returned an identical \`value\` across ${RUNS} runs;`,
  `**${rows.length - conf.length} of ${rows.length}** returned an identical \`confidence\`.`,
  '',
  scoring.length === 0 && conf.length === 0
    ? 'On this fact set every input to the score was reproducible. That is evidence, not a guarantee: a seed is a hint, and a different fact set may behave differently. Re-run this when the prompts or the model change.'
    : 'At least one scoring input moved between byte-identical requests, so a score on this fact set is not reproducible. This is the cost of `temperature: 0` being unavailable and it should be stated to anyone relying on a grade.',
  '',
].join('\n'));
console.log(`\nreports/determinism.md written`);
