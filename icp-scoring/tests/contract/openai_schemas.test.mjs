// tests/contract/openai_schemas.test.mjs — the strict-mode translation is faithful.
//
// engine/schemas/classifier_output.schema.json is the contract. OpenAI strict
// structured outputs cannot express it, so scripts/gen_openai_schemas.mjs
// derives one strict schema per component. A derivation that quietly widened
// or narrowed what a classifier may return would move the rubric without
// anyone editing the rubric, so this file pins the translation down:
//
//   1. each derived schema is legal strict mode;
//   2. it is generated, not hand-edited (byte staleness);
//   3. every instance the strict schema accepts, the canonical schema accepts
//      for that component — and vice versa — with exactly ONE documented
//      exception: the `evidence` size limits, which strict mode cannot carry.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import Ajv from 'ajv';

import {
  strictSchemaFor, valueDomainFor, COMPONENTS, LEVELS, VERTICALS, ACTIVATION_STATES,
} from '../../scripts/gen_openai_schemas.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...p) => JSON.parse(readFileSync(join(ROOT, ...p), 'utf8'));
const readRaw = (...p) => readFileSync(join(ROOT, ...p), 'utf8');

const ajv = new Ajv({ strict: false, allErrors: true });
const validateCanonical = ajv.compile(read('engine', 'schemas', 'classifier_output.schema.json'));

// Keywords OpenAI strict mode rejects. If one of these reaches a schema, the
// API call 400s at run time — which is a build-time bug found in production.
const FORBIDDEN = [
  'oneOf', 'allOf', 'not', 'if', 'then', 'else',
  'maxItems', 'minItems', 'maxLength', 'minLength',
  'maximum', 'minimum', 'exclusiveMaximum', 'exclusiveMinimum',
  'pattern', 'format', 'default', 'multipleOf', 'uniqueItems',
  'patternProperties', 'dependencies', 'propertyNames', 'contains',
];

function walk(node, path, visit) {
  if (Array.isArray(node)) {
    node.forEach((v, i) => walk(v, `${path}[${i}]`, visit));
    return;
  }
  if (node && typeof node === 'object') {
    visit(node, path);
    for (const [k, v] of Object.entries(node)) walk(v, `${path}.${k}`, visit);
  }
}

describe('OpenAI strict-mode classifier schemas', () => {
  test('one schema per component, and the component list is the canonical one', () => {
    assert.deepEqual(COMPONENTS.slice().sort(), [
      'activation_state', 'buying_signal', 'company_type', 'geography',
      'industry_vertical', 'revenue_range', 'stage_maturity',
    ]);
  });

  for (const component of COMPONENTS) {
    const generated = strictSchemaFor(component);

    test(`${component}: the file on disk is what the generator produces`, () => {
      const onDisk = readRaw('engine', 'schemas', 'openai', `${component}.strict.json`);
      assert.equal(
        onDisk,
        `${JSON.stringify(generated, null, 2)}\n`,
        `engine/schemas/openai/${component}.strict.json is stale or hand-edited — run \`npm run gen:openai\``,
      );
    });

    test(`${component}: is legal OpenAI strict mode`, () => {
      assert.equal(generated.strict, true);
      assert.equal(generated.schema.type, 'object');

      walk(generated.schema, 'schema', (node, path) => {
        for (const keyword of FORBIDDEN) {
          assert.ok(
            !(keyword in node),
            `${component}: "${keyword}" at ${path} is not supported in strict mode`,
          );
        }
        if (node.type === 'object') {
          assert.equal(node.additionalProperties, false, `${path}: additionalProperties must be false`);
          assert.deepEqual(
            (node.required || []).slice().sort(),
            Object.keys(node.properties || {}).sort(),
            `${path}: strict mode requires EVERY property to be listed in required`,
          );
        }
      });
    });

    test(`${component}: value domain is the rubric's, closed, plus null`, () => {
      const domain = valueDomainFor(component);
      assert.deepEqual(generated.schema.properties.value.anyOf, [{ enum: domain }, { type: 'null' }]);
      if (component === 'industry_vertical') assert.deepEqual(domain, VERTICALS);
      else if (component === 'activation_state') assert.deepEqual(domain, ACTIVATION_STATES);
      else assert.deepEqual(domain, LEVELS);
    });

    test(`${component}: accepts exactly what the canonical schema accepts`, () => {
      const validateStrict = ajv.compile(generated.schema);
      const base = (over = {}) => ({
        component,
        value: valueDomainFor(component)[0],
        evidence: ['li_industry: Software Development'],
        confidence: 'high',
        missing_inputs: [],
        ...(component === 'activation_state' ? { evidence_dated_within_months: null } : {}),
        ...over,
      });

      // Every legal value, plus null, plus one value borrowed from ANOTHER
      // component's domain — which both schemas must reject.
      const foreign = component === 'industry_vertical' ? 10 : 'FinTech';
      const cases = [
        ...valueDomainFor(component).map((v) => [base({ value: v }), true]),
        [base({ value: null }), true],
        [base({ value: foreign }), false],
        ...['high', 'medium', 'low'].map((c) => [base({ confidence: c }), true]),
        [base({ confidence: 'certain' }), false],
        [base({ evidence: [] }), true],
        [base({ missing_inputs: ['revenue_estimate_usd'] }), true],
      ];

      for (const [instance, shouldPass] of cases) {
        const strictOk = validateStrict(instance);
        const canonicalOk = validateCanonical(instance);
        assert.equal(
          strictOk, shouldPass,
          `strict ${component}: ${JSON.stringify(instance.value)} — expected ${shouldPass}`,
        );
        assert.equal(
          canonicalOk, shouldPass,
          `canonical ${component}: ${JSON.stringify(instance.value)} — expected ${shouldPass}`,
        );
      }

      // A missing required key: strict mode requires all of them, canonical
      // requires the five it always required.
      const stripped = base();
      delete stripped.confidence;
      assert.equal(validateStrict(stripped), false);
      assert.equal(validateCanonical(stripped), false);
    });

    test(`${component}: the ONLY looser case is evidence's size limits`, () => {
      const validateStrict = ajv.compile(generated.schema);
      const oversized = {
        component,
        value: valueDomainFor(component)[0],
        evidence: Array.from({ length: 7 }, (_, i) => `k${i}: ${'x'.repeat(250)}`),
        confidence: 'low',
        missing_inputs: [],
        ...(component === 'activation_state' ? { evidence_dated_within_months: null } : {}),
      };
      assert.equal(
        validateStrict(oversized), true,
        'strict mode cannot express maxItems/maxLength, so it must accept this',
      );
      assert.equal(
        validateCanonical(oversized), false,
        'the canonical schema still rejects it — which is why node 21 truncates rather than trusts',
      );
    });
  }

  test('Contracting still demands a dated item, enforced outside the schema', () => {
    // The canonical schema requires `evidence_dated_within_months` when value
    // is Contracting, via if/then. Strict mode has no if/then, so it is always
    // required and may be null — and engine/scoring.mjs (S9) independently
    // downgrades an undated Contracting to the default and flags it. The
    // schema was never the only thing holding this.
    const strict = strictSchemaFor('activation_state');
    assert.ok(strict.schema.required.includes('evidence_dated_within_months'));
    const undatedContracting = {
      component: 'activation_state',
      value: 'Contracting',
      evidence: ['news_last_12mo: layoffs reported'],
      confidence: 'low',
      missing_inputs: [],
      evidence_dated_within_months: null,
    };
    assert.equal(ajv.compile(strict.schema)(undatedContracting), true);
    assert.equal(validateCanonical(undatedContracting), true, 'present-but-null satisfies the canonical if/then too');
  });
});
