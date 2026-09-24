// tests/contract/clay_parity.test.mjs — Clay's formula and engine/scoring.mjs
// must be the same function.
//
// The formula text is generated from the same rubric, so this test is not
// checking arithmetic twice for fun: it is checking that the *generator* has
// been re-run, and that nothing in the portable body depends on a Node API
// that Clay's formula sandbox does not have.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { score, RUBRIC } from '../../engine/scoring.mjs';
import { BEGIN, END } from '../../scripts/gen_clay_formula.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const FORMULA_PATH = join(ROOT, 'engine', 'clay_formula.txt');
const formulaText = readFileSync(FORMULA_PATH, 'utf8');

/** Slice the parity-tested block out of the pasteable instructions around it. */
function portableBody(text) {
  const start = text.indexOf(BEGIN);
  const end = text.indexOf(END);
  assert.ok(start !== -1, 'BEGIN marker missing from engine/clay_formula.txt');
  assert.ok(end > start, 'END marker missing or out of order');
  return text.slice(start + BEGIN.length, end);
}

const clayScore = new Function('inputs', portableBody(formulaText));

describe('the generated file is current', () => {
  test('re-running the generator reproduces engine/clay_formula.txt byte for byte', () => {
    execFileSync(process.execPath, [join(ROOT, 'scripts', 'gen_clay_formula.mjs')], { stdio: 'pipe' });
    assert.equal(
      readFileSync(FORMULA_PATH, 'utf8'),
      formulaText,
      'engine/clay_formula.txt is stale — run `npm run gen:formula` and commit the result'
    );
  });

  test('every rubric number in the formula came from config, not a literal', () => {
    const body = portableBody(formulaText);
    // The rubric is inlined as JSON, so these exact fragments must be present.
    assert.ok(body.includes(JSON.stringify(RUBRIC.weights)), 'weights');
    assert.ok(body.includes(JSON.stringify(RUBRIC.thresholds)), 'thresholds');
    assert.ok(body.includes(JSON.stringify(RUBRIC.activation_multipliers)), 'multipliers');
    assert.ok(body.includes(JSON.stringify(RUBRIC.tier2_flag_rule)), 'tier2 rule');
    assert.ok(
      body.includes(JSON.stringify(RUBRIC.insufficient_data_rule.components)),
      'insufficient-data components'
    );
  });

  test('the portable body uses no Node-only API', () => {
    const body = portableBody(formulaText);
    for (const forbidden of [
      'require(', 'import ', 'process.', 'Buffer', 'structuredClone',
      'readFileSync', 'fetch(', 'Object.entries(', 'Object.fromEntries(',
    ]) {
      assert.ok(!body.includes(forbidden), `portable body must not use ${forbidden}`);
    }
  });
});

describe('parity with engine/scoring.mjs', () => {
  const verticals = [...Object.keys(RUBRIC.industry_verticals), 'Nonexistent Vertical', null];
  const states = [...Object.keys(RUBRIC.activation_multipliers), null];
  const confidences = ['high', 'medium', 'low', undefined];
  const levelChoices = [...RUBRIC.levels, null];

  /** Deterministic case generator; a failure is always reproducible. */
  function* cases(count, seed0) {
    let seed = seed0;
    const next = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
    for (let i = 0; i < count; i += 1) {
      yield {
        industry_vertical: verticals[next(verticals.length)],
        levels: {
          stage_maturity: levelChoices[next(levelChoices.length)],
          company_type: levelChoices[next(levelChoices.length)],
          geography: levelChoices[next(levelChoices.length)],
          revenue_range: levelChoices[next(levelChoices.length)],
          buying_signal: levelChoices[next(levelChoices.length)],
        },
        activation_state: states[next(states.length)],
        activation_evidence_dated_within_months: next(3) === 0 ? next(30) : null,
        confidence: {
          industry_vertical: confidences[next(4)], stage_maturity: confidences[next(4)],
          company_type: confidences[next(4)], geography: confidences[next(4)],
          revenue_range: confidences[next(4)], buying_signal: confidences[next(4)],
        },
        missing_inputs: next(2) === 0
          ? { stage_maturity: ['funding_stage'], revenue_range: ['revenue_estimate_usd'] }
          : {},
        facts_summary: {
          revenue_usd: next(2) === 0 ? next(2000) * 1000000 : null,
          headcount_total: next(2) === 0 ? next(5000) : null,
          headcount_eng: next(2) === 0 ? next(500) : null,
        },
      };
    }
  }

  test('500 generated inputs produce deep-equal output', () => {
    let checked = 0;
    for (const input of cases(500, 20260914)) {
      const engine = score(structuredClone(input));
      const clay = clayScore(structuredClone(input));
      assert.deepEqual(clay, engine, `divergence on ${JSON.stringify(input)}`);
      checked += 1;
    }
    assert.equal(checked, 500);
  });

  test('every vertical agrees', () => {
    for (const vertical of Object.keys(RUBRIC.industry_verticals)) {
      const input = {
        industry_vertical: vertical,
        levels: { stage_maturity: 7, company_type: 10, geography: 10, revenue_range: 10, buying_signal: 3 },
        activation_state: 'Accelerating',
        confidence: {
          industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
          geography: 'high', revenue_range: 'high', buying_signal: 'high',
        },
        missing_inputs: {},
        facts_summary: { revenue_usd: 40000000, headcount_total: 200, headcount_eng: 60 },
      };
      assert.deepEqual(clayScore(structuredClone(input)), score(structuredClone(input)), vertical);
    }
  });

  test('every activation state agrees, including the undated-Contracting downgrade', () => {
    for (const state of [...Object.keys(RUBRIC.activation_multipliers), null]) {
      for (const age of [null, 3, 12, 13, 400]) {
        const input = {
          industry_vertical: 'FinTech',
          levels: { stage_maturity: 10, company_type: 10, geography: 10, revenue_range: 10, buying_signal: 0 },
          activation_state: state,
          activation_evidence_dated_within_months: age,
          confidence: {
            industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
            geography: 'high', revenue_range: 'high', buying_signal: 'high',
          },
          missing_inputs: {},
          facts_summary: { revenue_usd: 100000000, headcount_total: 400, headcount_eng: 120 },
        };
        assert.deepEqual(
          clayScore(structuredClone(input)),
          score(structuredClone(input)),
          `${state} / evidence age ${age}`
        );
      }
    }
  });

  test('both implementations reject an out-of-range level the same way', () => {
    const input = {
      industry_vertical: 'FinTech',
      levels: { stage_maturity: 5, company_type: 10, geography: 10, revenue_range: 10, buying_signal: 0 },
      activation_state: 'Stable',
      confidence: {},
      missing_inputs: {},
      facts_summary: {},
    };
    assert.throws(() => score(structuredClone(input)), /level 5 is not one of/);
    assert.throws(() => clayScore(structuredClone(input)), /level 5 is not one of/);
  });

  test('the grade boundary lands on the same side in both', () => {
    // Walk every reachable composite and check the grade agrees after rounding.
    for (const stage of RUBRIC.levels) {
      for (const rev of RUBRIC.levels) {
        for (const state of ['Accelerating', 'Stable']) {
          const input = {
            industry_vertical: 'HealthTech / MedTech',
            levels: { stage_maturity: stage, company_type: 7, geography: 7, revenue_range: rev, buying_signal: 0 },
            activation_state: state,
            confidence: {
              industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
              geography: 'high', revenue_range: 'high', buying_signal: 'high',
            },
            missing_inputs: {},
            facts_summary: { revenue_usd: 30000000, headcount_total: 150, headcount_eng: 50 },
          };
          const a = score(structuredClone(input));
          const b = clayScore(structuredClone(input));
          assert.equal(b.grade, a.grade, `stage ${stage} / rev ${rev} / ${state}`);
          assert.equal(b.final_score, a.final_score);
        }
      }
    }
  });
});
