#!/usr/bin/env node
/**
 * scripts/gen_openai_schemas.mjs — the seven OpenAI strict-mode classifier schemas.
 *
 * `engine/schemas/classifier_output.schema.json` is the canonical contract and
 * stays that way: one schema, `component` discriminates, and the allOf tail
 * closes `value` per component. It is JSON Schema draft-07 and it is not
 * accepted by OpenAI structured outputs in strict mode, which supports a
 * restricted subset:
 *
 *   - no `oneOf` (use `anyOf`), no `if`/`then`, no `allOf`
 *   - no `maxItems`, `maxLength`, `minLength`, `minimum`, `maximum`
 *   - every property must be listed in `required`
 *   - `additionalProperties: false` on every object
 *
 * So each component gets its own derived schema with `value` already closed —
 * which is strictly stronger than the canonical one at the point of generation,
 * because the model cannot even emit a value from another component's domain.
 *
 * What is LOST in the translation is `evidence`'s `maxItems: 6` and
 * `maxLength: 200`. Those are stated in the prompt and enforced in code
 * (clay/code/21_score_handler.py truncates evidence to six items), never
 * assumed. tests/contract/openai_schemas.test.mjs asserts that this is the
 * ONLY difference between the two schemas' accepted sets.
 *
 *   npm run gen:openai
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (...p) => JSON.parse(readFileSync(join(ROOT, ...p), 'utf8'));

const RUBRIC = read('config', 'rubric_v6.json');
const CANONICAL = read('engine', 'schemas', 'classifier_output.schema.json');

export const LEVELS = RUBRIC.levels;
export const VERTICALS = Object.keys(RUBRIC.industry_verticals);
export const ACTIVATION_STATES = Object.keys(RUBRIC.activation_multipliers);

export const COMPONENTS = CANONICAL.properties.component.enum;

/** The closed `value` domain for one component, taken from the rubric. */
export function valueDomainFor(component) {
  if (component === 'industry_vertical') return VERTICALS;
  if (component === 'activation_state') return ACTIVATION_STATES;
  return LEVELS;
}

export function strictSchemaFor(component) {
  const domain = valueDomainFor(component);
  const properties = {
    component: {
      enum: [component],
      description: 'The component this object classifies. Exactly this value.',
    },
    value: {
      anyOf: [{ enum: domain }, { type: 'null' }],
      description:
        `The ${component} value: one of ${JSON.stringify(domain)}, or null when the facts `
        + 'do not support a defensible answer.',
    },
    evidence: {
      type: 'array',
      items: { type: 'string' },
      description:
        'At most 6 items, each "<fact_key>: <value>" and under 200 characters. '
        + 'The limits are not expressible in strict mode; they are still the contract.',
    },
    confidence: {
      enum: ['high', 'medium', 'low'],
      description: 'high when a fact states it or two agree; medium when inferred; low when extrapolating.',
    },
    missing_inputs: {
      type: 'array',
      items: { type: 'string' },
      description: 'Fact keys you needed and did not get. Empty array when none.',
    },
  };

  if (component === 'activation_state') {
    properties.evidence_dated_within_months = {
      anyOf: [{ type: 'integer' }, { type: 'null' }],
      description:
        `Required when value is "Contracting": the age in months of the dated evidence item, `
        + `which must be within ${RUBRIC.activation_contracting_evidence_max_age_months} months. `
        + 'Null otherwise.',
    };
  }

  return {
    name: `icp_v5_${component}`,
    strict: true,
    schema: {
      type: 'object',
      // Strict mode requires EVERY property to be required. A component that
      // genuinely has nothing to say says so with `value: null` and a populated
      // `missing_inputs` — not by omitting a key.
      required: Object.keys(properties),
      additionalProperties: false,
      properties,
    },
  };
}

const isMain = process.argv[1] && process.argv[1].endsWith('gen_openai_schemas.mjs');
if (isMain) {
  const dir = join(ROOT, 'engine', 'schemas', 'openai');
  mkdirSync(dir, { recursive: true });
  for (const component of COMPONENTS) {
    const file = join(dir, `${component}.strict.json`);
    writeFileSync(file, `${JSON.stringify(strictSchemaFor(component), null, 2)}\n`);
    console.log(`engine/schemas/openai/${component}.strict.json`);
  }
  console.log(`${COMPONENTS.length} strict schemas generated from config/rubric_v6.json`);
}
