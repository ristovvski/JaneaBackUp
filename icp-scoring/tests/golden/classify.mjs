// tests/golden/classify.mjs — run the real prompts against the Anthropic API,
// cached by sha256(prompt + facts).
//
// Three modes, decided per account, never silently:
//
//   cache   a cache entry exists for this exact prompt+facts -> free, offline,
//           byte-identical to the run that produced it.
//   api     ANTHROPIC_API_KEY is set and there is no cache entry -> one call
//           per component at temperature 0, then written to the cache.
//   stub    the facts file is SYNTHETIC and carries synthetic_classifier_output
//           -> used as-is. NOT a classifier result. Only ever for a file whose
//           name starts with SYNTHETIC_ and whose body sets SYNTHETIC: true.
//
// Anything else returns { mode: 'skip', reason } and golden.test.mjs skips that
// account and prints it. A skipped account never counts as a pass.

import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const PROMPTS = join(ROOT, 'engine', 'prompts');
const CACHE = join(HERE, '.cache');

export const COMPONENTS = [
  'industry_vertical', 'stage_maturity', 'company_type',
  'geography', 'revenue_range', 'activation_state', 'buying_signal',
];

// Model pinned so a cache entry means something. Bump deliberately, and the
// cache keys change with it because the model id is part of the hash.
export const MODEL = process.env.ICP_CLASSIFIER_MODEL || 'claude-opus-5';

const preamble = readFileSync(join(PROMPTS, '_preamble.md'), 'utf8');
const componentPrompt = (component) => readFileSync(join(PROMPTS, `${component}.md`), 'utf8');

/** The prompt Clay sends: preamble + component prompt + facts_json. */
export function buildPrompt(component, facts) {
  const scoringFacts = { ...facts };
  // Never show a classifier the harness's own bookkeeping.
  delete scoringFacts.synthetic_classifier_output;
  delete scoringFacts.SYNTHETIC;
  return [
    preamble,
    componentPrompt(component),
    '## facts_json',
    '',
    '```json',
    JSON.stringify(scoringFacts, null, 2),
    '```',
  ].join('\n\n');
}

const cacheKey = (prompt) =>
  createHash('sha256').update(`${MODEL}\n${prompt}`).digest('hex');

function cacheRead(key) {
  const file = join(CACHE, `${key}.json`);
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, 'utf8'));
}

function cacheWrite(key, value) {
  if (!existsSync(CACHE)) mkdirSync(CACHE, { recursive: true });
  writeFileSync(join(CACHE, `${key}.json`), `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

export function cacheSize() {
  if (!existsSync(CACHE)) return 0;
  return readdirSync(CACHE).filter((f) => f.endsWith('.json')).length;
}

/** One classifier call. Structured output, temperature 0. */
async function callApi(component, prompt) {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error('ANTHROPIC_API_KEY is not set');

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 1024,
      temperature: 0,
      messages: [{ role: 'user', content: prompt }],
    }),
  });

  if (!response.ok) {
    throw new Error(`Anthropic API ${response.status}: ${await response.text()}`);
  }

  const payload = await response.json();
  const text = (payload.content || [])
    .filter((block) => block.type === 'text')
    .map((block) => block.text)
    .join('');

  // The preamble says JSON only; be forgiving about a fence anyway rather than
  // failing an otherwise correct answer.
  const cleaned = text.trim().replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
  let parsed;
  try {
    parsed = JSON.parse(cleaned);
  } catch (error) {
    throw new Error(`${component}: response was not JSON: ${text.slice(0, 300)}`);
  }
  return parsed;
}

/**
 * Get the seven classifier outputs for one fact set.
 * @returns {Promise<{mode:string, outputs?:object, reason?:string}>}
 */
export async function classifyAll(factsFile, facts, { noCache = false } = {}) {
  const isSynthetic = factsFile.startsWith('SYNTHETIC_') && facts.SYNTHETIC === true;

  // Guard against a captured fact set smuggling in stub answers.
  if (facts.synthetic_classifier_output && !isSynthetic) {
    return {
      mode: 'skip',
      reason: `${factsFile} carries synthetic_classifier_output but is not a SYNTHETIC_ fixture — refusing to use authored classifier output as a captured result`,
    };
  }

  const prompts = Object.fromEntries(COMPONENTS.map((c) => [c, buildPrompt(c, facts)]));

  // 1. cache
  if (!noCache) {
    const cached = {};
    let complete = true;
    for (const component of COMPONENTS) {
      const hit = cacheRead(cacheKey(prompts[component]));
      if (!hit) { complete = false; break; }
      cached[component] = hit;
    }
    if (complete) return { mode: 'cache', outputs: cached };
  }

  // 2. api
  if (process.env.ANTHROPIC_API_KEY) {
    const outputs = {};
    for (const component of COMPONENTS) {
      const result = await callApi(component, prompts[component]);
      cacheWrite(cacheKey(prompts[component]), result);
      outputs[component] = result;
    }
    return { mode: 'api', outputs };
  }

  // 3. stub — synthetic fixtures only
  if (isSynthetic && facts.synthetic_classifier_output) {
    const stub = facts.synthetic_classifier_output;
    const missing = COMPONENTS.filter((c) => !(c in stub));
    if (missing.length > 0) {
      return { mode: 'skip', reason: `${factsFile}: synthetic_classifier_output is missing ${missing.join(', ')}` };
    }
    return {
      mode: 'stub',
      outputs: Object.fromEntries(COMPONENTS.map((c) => [c, { component: c, ...stub[c] }])),
    };
  }

  return {
    mode: 'skip',
    reason: `${factsFile}: no cache entry and ANTHROPIC_API_KEY is not set (facts captured from Clay need one real run to populate the cache)`,
  };
}

/** Fold the seven classifier outputs into the score() input shape. */
export function toScoreInput(outputs) {
  const get = (c) => outputs[c] || {};
  return {
    industry_vertical: get('industry_vertical').value ?? null,
    levels: {
      stage_maturity: get('stage_maturity').value ?? null,
      company_type: get('company_type').value ?? null,
      geography: get('geography').value ?? null,
      revenue_range: get('revenue_range').value ?? null,
      buying_signal: get('buying_signal').value ?? null,
    },
    activation_state: get('activation_state').value ?? null,
    activation_evidence_dated_within_months:
      get('activation_state').evidence_dated_within_months ?? null,
    confidence: Object.fromEntries(COMPONENTS.map((c) => [c, get(c).confidence ?? 'low'])),
    missing_inputs: Object.fromEntries(COMPONENTS.map((c) => [c, get(c).missing_inputs ?? []])),
  };
}
