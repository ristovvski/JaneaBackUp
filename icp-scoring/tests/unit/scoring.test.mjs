// tests/unit/scoring.test.mjs — S1..S12 from §5 of the build task.
//
// Every test here maps to exactly one numbered rule. If a rule is deleted from
// engine/scoring.mjs, the test named after it must go red — that is the
// discriminating-test requirement (§9.6), checked once for real in REPORT.md.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, copyFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { score, gradeFor, gradeLabel, roundHalfUp, industryLevelFor, RUBRIC } from '../../engine/scoring.mjs';

const ROOT = new URL('../../', import.meta.url).pathname;

/** A fully-evidenced, all-high-confidence input. Tests vary one thing from it. */
function baseInput(overrides = {}) {
  return {
    industry_vertical: 'FinTech',
    levels: { stage_maturity: 10, company_type: 10, geography: 10, revenue_range: 10, buying_signal: 3 },
    activation_state: 'Accelerating',
    confidence: {
      industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
      geography: 'high', revenue_range: 'high', buying_signal: 'high',
    },
    missing_inputs: {},
    facts_summary: { revenue_usd: 60000000, headcount_total: 300, headcount_eng: 90 },
    ...overrides,
  };
}

/** Solve for the component levels that land the composite on a target value. */
function inputWithComposite(target, overrides = {}) {
  // Only geography (weight 10) and revenue (weight 25) are moved; the rest are
  // pinned, so a target is reached by choosing levels rather than by fudging.
  const base = baseInput(overrides);
  const combos = [];
  for (const stage of RUBRIC.levels) {
    for (const type of RUBRIC.levels) {
      for (const geo of RUBRIC.levels) {
        for (const rev of RUBRIC.levels) {
          for (const vertical of Object.keys(RUBRIC.industry_verticals)) {
            const ind = industryLevelFor(vertical).level;
            const c = (15 * ind + 25 * stage + 25 * rev + 25 * type + 10 * geo) / 10;
            combos.push({ c: Number(c.toFixed(10)), vertical, stage, type, geo, rev });
          }
        }
      }
    }
  }
  const hit = combos.find((x) => x.c === target);
  if (!hit) throw new Error(`no level combination yields composite ${target}`);
  return {
    ...base,
    industry_vertical: hit.vertical,
    levels: { ...base.levels, stage_maturity: hit.stage, company_type: hit.type, geography: hit.geo, revenue_range: hit.rev },
  };
}

describe('S1 industry vertical -> tier -> level', () => {
  test('each of the 17 verticals maps through its tier to a rubric level', () => {
    const verticals = Object.keys(RUBRIC.industry_verticals);
    assert.equal(verticals.length, 17);
    for (const vertical of verticals) {
      const row = RUBRIC.industry_verticals[vertical];
      const expected = RUBRIC.industry_vertical_map[row.tier];
      const result = score(baseInput({ industry_vertical: vertical }));
      assert.equal(result.industry_level, expected, `${vertical} (${row.tier})`);
      assert.equal(result.industry_tier, row.tier);
      assert.ok(!result.flags.includes('unknown_vertical'), `${vertical} must be known`);
    }
  });

  test('the four tiers map to the four rubric levels', () => {
    assert.deepEqual(
      ['Anchor', 'Watch', 'Opportunistic', 'Out'].map((t) => RUBRIC.industry_vertical_map[t]),
      [10, 7, 3, 0]
    );
  });

  test('unknown vertical -> level 0, unknown_vertical flag, confidence low', () => {
    const result = score(baseInput({ industry_vertical: 'Crypto Casinos' }));
    assert.equal(result.industry_level, 0);
    assert.ok(result.flags.includes('unknown_vertical'));
    assert.equal(result.confidence_overall, 'low');
  });

  test('null vertical is treated as unknown, not as an error', () => {
    const result = score(baseInput({ industry_vertical: null }));
    assert.equal(result.industry_level, 0);
    assert.ok(result.flags.includes('unknown_vertical'));
  });
});

describe('S2 composite = sum(weight_i * level_i / 10)', () => {
  test('weights sum to 100', () => {
    assert.equal(Object.values(RUBRIC.weights).reduce((a, b) => a + b, 0), 100);
  });

  test('all levels 10 on an Anchor vertical -> composite 100', () => {
    const result = score(baseInput({
      industry_vertical: 'FinTech',
      levels: { stage_maturity: 10, company_type: 10, geography: 10, revenue_range: 10, buying_signal: 10 },
    }));
    assert.equal(result.composite, 100);
  });

  test('all levels 0 -> composite 0', () => {
    const result = score(baseInput({
      industry_vertical: 'Government / Public Sector',
      levels: { stage_maturity: 0, company_type: 0, geography: 0, revenue_range: 0, buying_signal: 0 },
    }));
    assert.equal(result.composite, 0);
  });

  test('composite is arithmetically the weighted sum, computed independently', () => {
    const input = baseInput({
      industry_vertical: 'Pharma / Life Sciences', // Watch -> 7
      levels: { stage_maturity: 3, company_type: 7, geography: 10, revenue_range: 0, buying_signal: 10 },
    });
    const expected = (15 * 7 + 25 * 3 + 25 * 0 + 25 * 7 + 10 * 10) / 10;
    assert.equal(score(input).composite, expected);
    assert.equal(expected, 45.5);
  });
});

describe('S3 activation state defaulting', () => {
  test('a provided state is used as given', () => {
    for (const state of Object.keys(RUBRIC.activation_multipliers)) {
      const extra = state === 'Contracting' ? { activation_evidence_dated_within_months: 3 } : {};
      const result = score(baseInput({ activation_state: state, ...extra }));
      assert.equal(result.activation_state_used, state);
      assert.equal(result.multiplier, RUBRIC.activation_multipliers[state]);
    }
  });

  test('null state falls back to the configured default', () => {
    const result = score(baseInput({ activation_state: null }));
    assert.equal(result.activation_state_used, RUBRIC.activation_default_when_no_evidence);
    assert.equal(result.activation_state_used, 'Stable');
    assert.equal(result.multiplier, 0.8);
  });
});

describe('S4 final scores', () => {
  test('final = round_half_up(composite * multiplier)', () => {
    const input = baseInput({ activation_state: 'Stable' }); // composite 100 * 0.80
    const result = score(input);
    assert.equal(result.composite, 100);
    assert.equal(result.final_score, 80);
  });

  test('final_without_activation = round_half_up(composite), multiplier ignored', () => {
    const input = inputWithComposite(92.5, { activation_state: 'Stable' });
    const result = score(input);
    assert.equal(result.composite, 92.5);
    assert.equal(result.final_score_without_activation, 93);
    assert.equal(result.final_score, 74); // 92.5 * 0.80 = 74.0 -> 74
  });

  test('Contracting multiplier 0 zeroes the final but not the without-activation score', () => {
    const result = score(baseInput({
      activation_state: 'Contracting',
      activation_evidence_dated_within_months: 2,
    }));
    assert.equal(result.multiplier, 0);
    assert.equal(result.final_score, 0);
    assert.equal(result.final_score_without_activation, 100);
  });

  test('roundHalfUp rounds .5 up and .4 down, at the grade boundaries', () => {
    assert.equal(roundHalfUp(74.5), 75);
    assert.equal(roundHalfUp(74.4), 74);
    assert.equal(roundHalfUp(54.5), 55);
    assert.equal(roundHalfUp(54.4), 54);
    assert.equal(roundHalfUp(0), 0);
  });

  test('roundHalfUp is immune to float representation of exact halves', () => {
    // 87.65 * 0.85 is 74.5025 in exact arithmetic but 74.50249999999998 in float.
    assert.equal(roundHalfUp(87.65 * 0.85), 75);
    // 0.1+0.2 style drift must not push a .5 boundary the wrong way.
    assert.equal(roundHalfUp(Number((74.5).toFixed(10))), 75);
  });
});

describe('S5 grade thresholds, boundaries inclusive', () => {
  test('gradeFor at and around each threshold', () => {
    assert.equal(gradeFor(75), 'A');
    assert.equal(gradeFor(74), 'B');
    assert.equal(gradeFor(55), 'B');
    assert.equal(gradeFor(54), 'C');
    assert.equal(gradeFor(0), 'C');
    assert.equal(gradeFor(100), 'A');
  });

  test('74.5 -> 75 -> A', () => {
    // composite 87.5 (Anchor 10 / stage 10 / type 10 / geo 0 / revenue 7)
    // -> 87.5 * 0.85 = 74.375. Drive the boundary through roundHalfUp instead.
    assert.equal(gradeFor(roundHalfUp(74.5)), 'A');
  });

  test('74.4 -> 74 -> B', () => {
    assert.equal(gradeFor(roundHalfUp(74.4)), 'B');
  });

  test('55 -> B and 54.5 -> 55 -> B and 54.4 -> C', () => {
    assert.equal(gradeFor(55), 'B');
    assert.equal(gradeFor(roundHalfUp(54.5)), 'B');
    assert.equal(gradeFor(roundHalfUp(54.4)), 'C');
  });

  test('the boundary runs through score(), not only through gradeFor()', () => {
    // composite 100, Stable -> 85 -> A. composite 85, Stable -> 72.25 -> 72 -> B.
    assert.equal(score(baseInput({ activation_state: 'Stable' })).grade, 'A');
    assert.equal(score(inputWithComposite(85, { activation_state: 'Stable' })).grade, 'B');
  });

  test('gradeLabel maps grades to the Pipedrive option labels', () => {
    assert.equal(gradeLabel('A'), 'ICP A');
    assert.equal(gradeLabel('B'), 'ICP B');
    assert.equal(gradeLabel('C'), 'ICP C');
    assert.equal(gradeLabel(null), null);
  });
});

describe('S6 insufficient_data', () => {
  const gating = RUBRIC.insufficient_data_rule.components;

  test('the rule gates on stage_maturity, revenue_range and company_type', () => {
    assert.deepEqual(gating, ['stage_maturity', 'revenue_range', 'company_type']);
  });

  for (const component of gating) {
    test(`${component} level null -> insufficient_data, grade null, composite still reported`, () => {
      const input = baseInput();
      input.levels[component] = null;
      const result = score(input);
      assert.equal(result.status, 'insufficient_data');
      assert.equal(result.grade, null);
      assert.equal(result.levels_used[component], 0, 'null is treated as 0 in the composite');
      assert.equal(typeof result.composite, 'number');
      assert.ok(result.composite > 0, 'composite is still computed and reported');
    });

    test(`${component} low confidence with missing inputs -> insufficient_data`, () => {
      const input = baseInput();
      input.confidence[component] = 'low';
      input.missing_inputs[component] = ['revenue_estimate_usd'];
      assert.equal(score(input).status, 'insufficient_data');
    });

    test(`${component} low confidence with NO missing inputs -> still scored`, () => {
      const input = baseInput();
      input.confidence[component] = 'low';
      input.missing_inputs[component] = [];
      assert.equal(score(input).status, 'scored');
    });
  }

  test('a null level on a non-gating component does not trigger insufficient_data', () => {
    const input = baseInput();
    input.levels.geography = null;
    input.levels.buying_signal = null;
    const result = score(input);
    assert.equal(result.status, 'scored');
    assert.notEqual(result.grade, null);
  });

  test('the flag names which components triggered it', () => {
    const input = baseInput();
    input.levels.revenue_range = null;
    const result = score(input);
    assert.ok(result.flags.some((f) => f.startsWith('insufficient:') && f.includes('revenue_range')));
  });
});

describe('S7 confidence_overall = worst of the weighted components', () => {
  test('all high -> high', () => {
    assert.equal(score(baseInput()).confidence_overall, 'high');
  });

  test('one medium -> medium', () => {
    const input = baseInput();
    input.confidence.geography = 'medium';
    assert.equal(score(input).confidence_overall, 'medium');
  });

  test('one low -> low', () => {
    const input = baseInput();
    input.confidence.company_type = 'low';
    assert.equal(score(input).confidence_overall, 'low');
  });

  test('buying_signal confidence is excluded (weight 0)', () => {
    const input = baseInput();
    input.confidence.buying_signal = 'low';
    assert.equal(score(input).confidence_overall, 'high');
  });

  test('each weighted component can lower the overall confidence on its own', () => {
    const weighted = ['industry_vertical', 'stage_maturity', 'company_type', 'geography', 'revenue_range'];
    for (const component of weighted) {
      const input = baseInput();
      input.confidence[component] = 'low';
      assert.equal(score(input).confidence_overall, 'low', component);
    }
  });

  test('an absent confidence declaration reads as low, never as high', () => {
    const input = baseInput();
    delete input.confidence.stage_maturity;
    assert.equal(score(input).confidence_overall, 'low');
  });
});

describe('S8 tier2_candidate', () => {
  const rule = RUBRIC.tier2_flag_rule;

  test('the rule is revenue > 500M, headcount > 1000, or company_type level == 7', () => {
    assert.deepEqual(rule, { revenue_usd_gt: 500000000, headcount_gt: 1000, company_type_level_eq: 7 });
  });

  test('revenue above the threshold alone sets it', () => {
    const input = baseInput({ facts_summary: { revenue_usd: 500000001, headcount_total: 10, headcount_eng: 3 } });
    assert.equal(score(input).tier2_candidate, true);
  });

  test('revenue exactly at the threshold does not (strict >)', () => {
    const input = baseInput({ facts_summary: { revenue_usd: 500000000, headcount_total: 10, headcount_eng: 3 } });
    assert.equal(score(input).tier2_candidate, false);
  });

  test('headcount above the threshold alone sets it', () => {
    const input = baseInput({ facts_summary: { revenue_usd: 1000, headcount_total: 1001, headcount_eng: 3 } });
    assert.equal(score(input).tier2_candidate, true);
  });

  test('company_type level 7 alone sets it', () => {
    const input = baseInput({ facts_summary: { revenue_usd: 1000, headcount_total: 10, headcount_eng: 3 } });
    input.levels.company_type = 7;
    assert.equal(score(input).tier2_candidate, true);
  });

  test('none of the three -> false, and the flag is absent', () => {
    const input = baseInput({ facts_summary: { revenue_usd: 1000, headcount_total: 10, headcount_eng: 3 } });
    const result = score(input);
    assert.equal(result.tier2_candidate, false);
    assert.ok(!result.flags.includes('tier2_candidate'));
  });

  test('null facts do not set it', () => {
    const input = baseInput({ facts_summary: { revenue_usd: null, headcount_total: null, headcount_eng: null } });
    input.levels.company_type = 10;
    assert.equal(score(input).tier2_candidate, false);
  });
});

describe('S9 Contracting requires dated evidence', () => {
  test('Contracting with evidence inside the window keeps Contracting', () => {
    const result = score(baseInput({
      activation_state: 'Contracting',
      activation_evidence_dated_within_months: 12,
    }));
    assert.equal(result.activation_state_used, 'Contracting');
    assert.equal(result.multiplier, 0);
    assert.ok(!result.flags.includes('contracting_without_dated_evidence'));
  });

  test('Contracting with no evidence date downgrades to Stable and flags it', () => {
    const result = score(baseInput({ activation_state: 'Contracting' }));
    assert.equal(result.activation_state_used, 'Stable');
    assert.equal(result.multiplier, 0.8);
    assert.ok(result.flags.includes('contracting_without_dated_evidence'));
  });

  test('Contracting with stale evidence (13 months) downgrades to Stable', () => {
    const result = score(baseInput({
      activation_state: 'Contracting',
      activation_evidence_dated_within_months: 13,
    }));
    assert.equal(result.activation_state_used, 'Stable');
    assert.ok(result.flags.includes('contracting_without_dated_evidence'));
  });

  test('the window comes from config, not a literal', () => {
    assert.equal(RUBRIC.activation_contracting_evidence_max_age_months, 12);
  });

  test('the downgrade does not touch the other three states', () => {
    for (const state of ['Accelerating', 'Transitioning', 'Stable']) {
      const result = score(baseInput({ activation_state: state }));
      assert.equal(result.activation_state_used, state);
      assert.ok(!result.flags.includes('contracting_without_dated_evidence'));
    }
  });
});

describe('S10 determinism', () => {
  test('100 pseudo-random inputs score identically on a second call', () => {
    const verticals = [...Object.keys(RUBRIC.industry_verticals), 'Nonexistent Vertical', null];
    const states = [...Object.keys(RUBRIC.activation_multipliers), null];
    const confidences = ['high', 'medium', 'low'];
    const levelChoices = [...RUBRIC.levels, null];

    // A fixed LCG: the case set is identical on every run, so a failure is
    // reproducible rather than a once-in-a-while surprise.
    let seed = 20260909;
    const next = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };

    for (let i = 0; i < 100; i += 1) {
      const input = {
        industry_vertical: verticals[next(verticals.length)],
        levels: {
          stage_maturity: levelChoices[next(levelChoices.length)],
          company_type: levelChoices[next(levelChoices.length)],
          geography: levelChoices[next(levelChoices.length)],
          revenue_range: levelChoices[next(levelChoices.length)],
          buying_signal: levelChoices[next(levelChoices.length)],
        },
        activation_state: states[next(states.length)],
        activation_evidence_dated_within_months: next(3) === 0 ? next(24) : null,
        confidence: {
          industry_vertical: confidences[next(3)], stage_maturity: confidences[next(3)],
          company_type: confidences[next(3)], geography: confidences[next(3)],
          revenue_range: confidences[next(3)], buying_signal: confidences[next(3)],
        },
        missing_inputs: next(2) === 0 ? { stage_maturity: ['funding_stage'] } : {},
        facts_summary: {
          revenue_usd: next(2) === 0 ? next(2000) * 1000000 : null,
          headcount_total: next(2) === 0 ? next(5000) : null,
          headcount_eng: next(2) === 0 ? next(500) : null,
        },
      };
      const a = score(structuredClone(input));
      const b = score(structuredClone(input));
      assert.deepEqual(a, b, `input #${i}: ${JSON.stringify(input)}`);
    }
  });

  test('score() does not mutate its input', () => {
    const input = baseInput();
    const before = structuredClone(input);
    score(input);
    assert.deepEqual(input, before);
  });
});

describe('S11 a rubric whose weights do not sum to 100 cannot load', () => {
  test('module load throws, naming the actual sum', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'icp-badrubric-'));
    mkdirSync(join(dir, 'engine'));
    mkdirSync(join(dir, 'config'));
    copyFileSync(join(ROOT, 'engine', 'scoring.mjs'), join(dir, 'engine', 'scoring.mjs'));

    const bad = structuredClone(RUBRIC);
    bad.weights.geography = 11; // 101 total
    writeFileSync(join(dir, 'config', 'rubric_v6.json'), JSON.stringify(bad));

    await assert.rejects(
      () => import(pathToFileURL(join(dir, 'engine', 'scoring.mjs')).href),
      /weights must sum to 100, got 101/
    );
  });

  test('the real rubric loads without throwing', () => {
    assert.equal(typeof score, 'function');
  });
});

describe('S12 buying_signal carries through and never scores', () => {
  test('weight is 0 in config', () => {
    assert.equal(RUBRIC.weights.buying_signal, 0);
  });

  test('mutating the buying signal level leaves the composite untouched', () => {
    const composites = new Set();
    const finals = new Set();
    for (const level of RUBRIC.levels) {
      const input = baseInput();
      input.levels.buying_signal = level;
      const result = score(input);
      composites.add(result.composite);
      finals.add(result.final_score);
      assert.equal(result.buying_signal_level, level, 'carried through untouched');
      assert.equal(result.levels_used.buying_signal, level);
    }
    assert.equal(composites.size, 1, 'composite must not move with the buying signal');
    assert.equal(finals.size, 1, 'final score must not move with the buying signal');
  });

  test('a null buying signal is carried through as null, not coerced to 0', () => {
    const input = baseInput();
    input.levels.buying_signal = null;
    assert.equal(score(input).buying_signal_level, null);
  });
});

describe('output contract', () => {
  test('the result carries exactly the documented keys', () => {
    assert.deepEqual(Object.keys(score(baseInput())).sort(), [
      'activation_state_used', 'buying_signal_level', 'composite', 'confidence_overall',
      'final_score', 'final_score_without_activation', 'flags', 'grade', 'industry_level',
      'industry_tier', 'levels_used', 'model_version', 'multiplier', 'status', 'tier2_candidate',
    ]);
  });

  test('model_version comes from config and is v6', () => {
    assert.equal(score(baseInput()).model_version, 'v6');
    assert.equal(RUBRIC.model_version, 'v6');
  });

  test('the v6 activation multipliers are 1.00 / 0.95 / 0.80 / 0.00', () => {
    // v5 gave Transitioning the same 1.00 as Accelerating and Stable 0.85.
    // v6 separates all four, so a Transitioning account is no longer scored as
    // if it were accelerating. Pinned here because these four numbers move
    // every grade on the board.
    assert.deepEqual(RUBRIC.activation_multipliers, {
      Accelerating: 1,
      Transitioning: 0.95,
      Stable: 0.8,
      Contracting: 0,
    });
  });

  test('an unknown vertical scores 0 and says so', () => {
    const result = score(baseInput({ industry_vertical: 'Interplanetary Logistics' }));
    assert.equal(result.industry_level, 0);
    assert.equal(result.levels_used.industry, 0);
    assert.ok(result.flags.includes('unknown_vertical'));
    // The rubric states the rule rather than leaving it to this implementation.
    assert.deepEqual(RUBRIC.unknown_vertical_rule, { level: 0, flag: 'unknown_vertical', confidence: 'low' });
  });

  test('an out-of-range level is rejected rather than silently scored', () => {
    const input = baseInput();
    input.levels.stage_maturity = 5;
    assert.throws(() => score(input), /level 5 is not one of/);
  });
});

describe('acceptance shapes from §9.5 (arithmetic only, facts come from Clay)', () => {
  test('Microsoft-shaped input cannot reach A: Anchor vertical, enterprise revenue', () => {
    const result = score({
      industry_vertical: 'Enterprise Tech / Hyperscalers',
      levels: { stage_maturity: 0, company_type: 10, geography: 10, revenue_range: 0, buying_signal: 10 },
      activation_state: 'Stable',
      confidence: {
        industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
        geography: 'high', revenue_range: 'high',
      },
      missing_inputs: {},
      facts_summary: { revenue_usd: 245000000000, headcount_total: 228000, headcount_eng: 90000 },
    });
    assert.equal(result.industry_level, 10, 'the vertical itself is an Anchor');
    assert.notEqual(result.grade, 'A', 'the composite gates it out');
    assert.equal(result.tier2_candidate, true);
  });

  test('Merck-shaped input cannot reach A: Watch vertical, software-dependent', () => {
    const result = score({
      industry_vertical: 'Pharma / Life Sciences',
      levels: { stage_maturity: 0, company_type: 7, geography: 10, revenue_range: 0, buying_signal: 3 },
      activation_state: 'Stable',
      confidence: {
        industry_vertical: 'high', stage_maturity: 'high', company_type: 'high',
        geography: 'high', revenue_range: 'high',
      },
      missing_inputs: {},
      facts_summary: { revenue_usd: 64000000000, headcount_total: 71000, headcount_eng: 4000 },
    });
    assert.notEqual(result.grade, 'A');
    assert.equal(result.tier2_candidate, true);
  });
});
