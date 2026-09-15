// tests/contract/python_parity.test.mjs — the Python port and the JS engine
// must be the same function.
//
// Clay Workflow code nodes run Python; engine/scoring.mjs is JavaScript. The
// table design could paste one body into Clay unchanged; the Workflow design
// cannot. So engine/clay_score.py is a GENERATED port, and this test is what
// makes "same behaviour" a fact rather than a hope: both implementations run
// over the same inputs and the results are deep-compared.
//
// Skips (loudly) if python3 is unavailable rather than passing silently.

import { test, describe, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';

import { score, RUBRIC } from '../../engine/scoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const PY = join(ROOT, 'engine', 'clay_score.py');

let pythonAvailable = true;
before(() => {
  try {
    execFileSync('python3', ['--version'], { stdio: 'pipe' });
  } catch {
    pythonAvailable = false;
    process.stdout.write('\n  !! python3 not found — Python parity NOT verified on this machine.\n');
  }
});

/** Run the Python scorer over a batch of inputs; returns the results array. */
function pythonScore(inputs) {
  const runner = join(tmpdir(), `icp-py-parity-${process.pid}.py`);
  writeFileSync(runner, `
import json, sys
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'engine'))})
import clay_score
out = []
for item in json.load(sys.stdin):
    try:
        out.append({"ok": True, "value": clay_score.score(item)})
    except Exception as e:
        out.append({"ok": False, "error": str(e)})
print(json.dumps(out))
`, 'utf8');
  const stdout = execFileSync('python3', [runner], {
    input: JSON.stringify(inputs), encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
  });
  return JSON.parse(stdout);
}

/** Same deterministic generator the JS/Clay parity test uses. */
function* cases(count, seed0) {
  const verticals = [...Object.keys(RUBRIC.industry_verticals), 'Nonexistent Vertical', null];
  const states = [...Object.keys(RUBRIC.activation_multipliers), null];
  const confidences = ['high', 'medium', 'low', undefined];
  const levelChoices = [...RUBRIC.levels, null];
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

describe('engine/clay_score.py is current', () => {
  test('the file exists and is generated from the rubric', () => {
    assert.ok(existsSync(PY), 'run `npm run gen:python`');
    const src = readFileSync(PY, 'utf8');
    assert.ok(src.includes('GENERATED from config/rubric_v5.json'));
    assert.ok(src.includes(JSON.stringify(RUBRIC.weights)), 'weights inlined from config');
    assert.ok(src.includes(JSON.stringify(RUBRIC.thresholds)), 'thresholds inlined from config');
  });

  test('re-running the generator reproduces it byte for byte', () => {
    const before = readFileSync(PY, 'utf8');
    execFileSync(process.execPath, [join(ROOT, 'scripts', 'gen_clay_python.mjs')], { stdio: 'pipe' });
    assert.equal(readFileSync(PY, 'utf8'), before, 'stale — run `npm run gen:python`');
  });

  test('it says out loud that it is a port, not the same bytes', () => {
    assert.match(readFileSync(PY, 'utf8'), /PORT of engine\/clay_formula\.txt/);
  });
});

describe('Python / JavaScript parity', () => {
  test('500 generated inputs produce deep-equal output', (t) => {
    if (!pythonAvailable) return t.skip('python3 unavailable');
    const inputs = [...cases(500, 20260915)];
    const pythonResults = pythonScore(inputs);
    assert.equal(pythonResults.length, inputs.length);

    for (let i = 0; i < inputs.length; i += 1) {
      const py = pythonResults[i];
      let js;
      let jsThrew = null;
      try { js = score(structuredClone(inputs[i])); } catch (error) { jsThrew = error.message; }

      if (jsThrew) {
        assert.equal(py.ok, false, `case ${i}: JS threw but Python did not`);
        continue;
      }
      assert.equal(py.ok, true, `case ${i}: Python threw "${py.error}" but JS did not`);
      assert.deepEqual(py.value, js, `case ${i}: ${JSON.stringify(inputs[i])}`);
    }
  });

  test('every vertical agrees', (t) => {
    if (!pythonAvailable) return t.skip('python3 unavailable');
    const inputs = Object.keys(RUBRIC.industry_verticals).map((vertical) => ({
      industry_vertical: vertical,
      levels: { stage_maturity: 7, company_type: 10, geography: 10, revenue_range: 10, buying_signal: 3 },
      activation_state: 'Accelerating',
      confidence: {
        industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
        geography: 'high', revenue_range: 'high', buying_signal: 'high',
      },
      missing_inputs: {},
      facts_summary: { revenue_usd: 40000000, headcount_total: 200, headcount_eng: 60 },
    }));
    const pythonResults = pythonScore(inputs);
    inputs.forEach((input, i) => {
      assert.deepEqual(pythonResults[i].value, score(structuredClone(input)), input.industry_vertical);
    });
  });

  test('the grade boundary lands on the same side in both languages', (t) => {
    if (!pythonAvailable) return t.skip('python3 unavailable');
    // Python's built-in round() is banker's rounding: round(74.5) == 74, which
    // would silently move a company from A to B. This is the test that catches
    // that if anyone "simplifies" _round_half_up.
    const inputs = [];
    for (const stage of RUBRIC.levels) {
      for (const rev of RUBRIC.levels) {
        for (const state of ['Accelerating', 'Stable']) {
          inputs.push({
            industry_vertical: 'HealthTech / MedTech',
            levels: { stage_maturity: stage, company_type: 7, geography: 7, revenue_range: rev, buying_signal: 0 },
            activation_state: state,
            confidence: {
              industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
              geography: 'high', revenue_range: 'high', buying_signal: 'high',
            },
            missing_inputs: {},
            facts_summary: { revenue_usd: 30000000, headcount_total: 150, headcount_eng: 50 },
          });
        }
      }
    }
    const pythonResults = pythonScore(inputs);
    inputs.forEach((input, i) => {
      const js = score(structuredClone(input));
      assert.equal(pythonResults[i].value.final_score, js.final_score, `case ${i} score`);
      assert.equal(pythonResults[i].value.grade, js.grade, `case ${i} grade`);
    });
  });

  test('every clay fixture agrees', (t) => {
    if (!pythonAvailable) return t.skip('python3 unavailable');
    const names = [
      'icp_scored_A', 'icp_scored_B_stable', 'icp_scored_contracting',
      'icp_scored_insufficient', 'icp_scored_tier2',
    ];
    const inputs = names.map((name) => {
      const event = JSON.parse(readFileSync(join(ROOT, 'tests', 'fixtures', 'clay', `${name}.json`), 'utf8'));
      const c = event.components;
      return {
        industry_vertical: c.industry_vertical.value,
        levels: {
          stage_maturity: c.stage_maturity.value, company_type: c.company_type.value,
          geography: c.geography.value, revenue_range: c.revenue_range.value,
          buying_signal: c.buying_signal.value,
        },
        activation_state: c.activation_state.value,
        activation_evidence_dated_within_months: c.activation_state.evidence_dated_within_months ?? null,
        confidence: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.confidence])),
        missing_inputs: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.missing_inputs])),
        facts_summary: event.facts_summary,
      };
    });
    const pythonResults = pythonScore(inputs);
    names.forEach((name, i) => {
      assert.deepEqual(pythonResults[i].value, score(structuredClone(inputs[i])), name);
    });
  });
});
