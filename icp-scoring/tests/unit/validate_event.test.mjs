// tests/unit/validate_event.test.mjs — the v6 boundary check, directly.
//
// This is the rule that decides whether a scored event is written to the CRM
// or refused, and it is spliced verbatim into the ParseScored Code node. A case
// here is a thing the boundary must catch; nodes_execute.test.mjs then proves
// the spliced copy behaves the same way inside n8n.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { validateEvent, roundHalfUp, gradeFor } from '../../engine/validate_event.mjs';
import { roundHalfUp as engineRoundHalfUp, RUBRIC } from '../../engine/scoring.mjs';
import { buildConfig } from '../../scripts/gen_config_node.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const cfg = buildConfig();
const fixture = (name) =>
  JSON.parse(readFileSync(join(ROOT, 'tests', 'fixtures', 'clay', name), 'utf8'));

const valid = () => fixture('icp_scored_A.json');
const problemsFor = (mutate) => {
  const event = valid();
  mutate(event);
  return validateEvent(event, cfg);
};
const one = (mutate, pattern) => {
  const problems = problemsFor(mutate);
  assert.ok(problems.length > 0, 'expected at least one problem');
  assert.ok(
    problems.some((p) => pattern.test(p)),
    `no problem matched ${pattern}:\n  ${problems.join('\n  ')}`
  );
};

describe('validateEvent accepts what the table is supposed to send', () => {
  for (const name of [
    'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting.json',
    'icp_scored_insufficient.json', 'icp_scored_tier2.json',
  ]) {
    test(`${name} is clean`, () => {
      assert.deepEqual(validateEvent(fixture(name), cfg), []);
    });
  }

  test('the provenance keys are optional, both ways', () => {
    assert.deepEqual(validateEvent(valid(), cfg), [], 'absent is fine');
    const withThem = valid();
    withThem.event = 'icp.scored';
    withThem.event_id = 'row-run-1';
    withThem.emitted_at = '2026-09-16T10:00:00Z';
    withThem.clay_table = 'ICP v6';
    withThem.clay_row_url = null;
    assert.deepEqual(validateEvent(withThem, cfg), [], 'present is also fine');
  });

  test('deal_id may be a string, null, or absent entirely', () => {
    for (const mutate of [
      (e) => { e.deal_id = '55001'; },
      (e) => { e.deal_id = null; },
      (e) => { delete e.deal_id; },
    ]) {
      assert.deepEqual(problemsFor(mutate), []);
    }
  });
});

describe('shape', () => {
  test('a missing required key is named', () => {
    for (const key of ['request_id', 'org_id', 'resolved', 'cls_all', 'jobs', 'score', 'apollo_summary', 'model_version']) {
      one((e) => { delete e[key]; }, new RegExp(`missing "${key}"`));
    }
  });

  test('an unknown key anywhere is rejected — a table change must be loud', () => {
    one((e) => { e.brand_new_column = 1; }, /unknown top-level key "brand_new_column"/);
    one((e) => { e.cls_all.geography = {}; }, /cls_all has an unknown key "geography"/);
    one((e) => { e.jobs.eng_closed = 2; }, /jobs has an unknown key "eng_closed"/);
    one((e) => { e.score.industry_level = 10; }, /score has an unknown key "industry_level"/);
    one((e) => { e.resolved.twitter = 'x'; }, /resolved has an unknown key "twitter"/);
    one((e) => { e.apollo_summary.sic_code = '1'; }, /apollo_summary has an unknown key "sic_code"/);
  });

  test('a null where a number belongs is caught, and a null where one is allowed is not', () => {
    one((e) => { e.jobs.eng_open = 'eleven'; }, /jobs\.eng_open has the wrong type/);
    assert.deepEqual(problemsFor((e) => {
      e.jobs.eng_open = null;
      e.jobs.eng_open_60d_plus = null;
      e.jobs.has_eng_leader = null;
    }), [], 'a jobs provider that returned nothing is not a malformed event');
  });

  test('the model version must be the one this workflow holds', () => {
    one((e) => { e.model_version = 'v5'; }, /model_version must be "v6"/);
  });

  test('an off-ladder level is caught in both places it can appear', () => {
    one((e) => { e.score.levels.geography = 5; }, /score\.levels\.geography must be one of/);
    one((e) => { e.cls_all.stage_maturity.level = 5; }, /cls_all\.stage_maturity\.level must be null or one of/);
  });

  test('a shape problem short-circuits the arithmetic, so one fault is not reported twice', () => {
    const problems = problemsFor((e) => { e.score.levels.geography = 5; });
    assert.ok(!problems.some((p) => /composite/.test(p)), `arithmetic noise:\n  ${problems.join('\n  ')}`);
  });
});

describe('arithmetic — the checks that make this a rejection rather than a warning', () => {
  test('a composite that does not weigh out is rejected', () => {
    one((e) => { e.score.composite = 61; }, /composite is 61, but the posted levels weigh 92\.5/);
  });

  test('a final score that is not the rounded product is rejected', () => {
    one((e) => { e.score.final_score = 90; }, /final_score is 90, but 92\.5 x 1 rounds to 93/);
  });

  test('a without-activation score that is not the rounded composite is rejected', () => {
    one((e) => { e.score.final_score_without_activation = 92; }, /final_score_without_activation is 92/);
  });

  test('a multiplier the rubric does not give that state is rejected', () => {
    // 0.5 is not a rubric multiplier at all — caught in the shape pass.
    one((e) => { e.score.multiplier = 0.5; }, /multiplier must be one of/);
    // 0.95 IS one, just not Accelerating's — caught by the state match, which
    // is the case that actually happens when a table's table of multipliers
    // goes stale.
    one((e) => { e.score.multiplier = 0.95; }, /rubric gives Accelerating a multiplier of 1/);
    const stable = fixture('icp_scored_B_stable.json');
    stable.score.multiplier = 1;
    assert.ok(validateEvent(stable, cfg).some((p) => /rubric gives Stable a multiplier of 0\.8/.test(p)));
  });

  test('a grade the thresholds do not support is rejected', () => {
    one((e) => { e.score.grade = 'B'; }, /grade is "B", but a final score of 93 is A/);
  });

  test('status and grade cannot contradict each other', () => {
    one((e) => { e.score.status = 'insufficient_data'; }, /grade must be null when status is insufficient_data/);
    one((e) => { e.score.grade = null; }, /grade must be A, B or C when status is scored/);
  });

  test('a rubric whose weights do not sum to 100 fails the CONFIG, not the event', () => {
    const broken = { ...cfg, weights: { ...cfg.weights, geography: 40 } };
    const problems = validateEvent(valid(), broken);
    assert.ok(problems.some((p) => /CONFIG\.weights must sum to 100, got 130/.test(p)));
    assert.ok(problems.some((p) => /the rubric in CONFIG is broken, not the event/.test(p)));
  });
});

describe('coherence between the classifiers and the levels', () => {
  test('a level inside score must match the classifier it came from', () => {
    one((e) => { e.cls_all.stage_maturity.level = 3; }, /score\.levels\.stage_maturity is 10, but cls_all\.stage_maturity\.level is 3/);
    one((e) => { e.cls_all.company_type.level = 7; }, /score\.levels\.company_type is 10, but cls_all\.company_type\.level is 7/);
  });

  test('a null classifier level means 0, not "anything goes"', () => {
    const problems = problemsFor((e) => {
      e.cls_all.stage_maturity.level = null;
    });
    assert.ok(problems.some((p) => /score\.levels\.stage_maturity is 10, but cls_all\.stage_maturity\.level is null/.test(p)));
  });

  test('the industry level must match the rubric tier of the vertical', () => {
    // FinTech is Anchor, which is 10. Claiming 7 for it is the stale-vertical-map
    // failure: plausible, invisible, and one grade wrong on every fintech.
    one((e) => {
      e.score.levels.industries = 7;
      e.score.composite = 88;
      e.score.final_score = 88;
      e.score.final_score_without_activation = 88;
    }, /score\.levels\.industries is 7, but the rubric puts "FinTech" at 10/);
  });

  test('an unknown vertical must be levelled 0 and flagged', () => {
    one((e) => { e.cls_all.industry_vertical.value = 'Crypto Casinos'; },
      /is not in the rubric, so score\.levels\.industries must be 0/);
    one((e) => {
      e.cls_all.industry_vertical.value = 'Crypto Casinos';
      e.score.levels.industries = 0;
      e.score.composite = 77.5;
      e.score.final_score = 78;
      e.score.final_score_without_activation = 78;
    }, /so score\.flags must contain "unknown_vertical"/);

    // Levelled 0, flagged, and the arithmetic redone: accepted.
    const honest = valid();
    honest.cls_all.industry_vertical.value = 'Crypto Casinos';
    honest.score.levels.industries = 0;
    honest.score.flags = ['unknown_vertical'];
    honest.score.composite = 77.5;
    honest.score.final_score = 78;
    honest.score.final_score_without_activation = 78;
    assert.deepEqual(validateEvent(honest, cfg), []);
  });

  test('a null vertical is the unknown case, not a free pass', () => {
    one((e) => { e.cls_all.industry_vertical.value = null; },
      /is not in the rubric, so score\.levels\.industries must be 0/);
  });

  test('the activation state used must be the one the rubric allows', () => {
    one((e) => { e.score.activation_state_used = 'Stable'; e.score.multiplier = 0.8; e.score.final_score = 74; },
      /activation_state_used is "Stable", but cls_all\.activation_state gives "Accelerating"/);
  });

  test('an undated Contracting must be downgraded, and say so', () => {
    const event = fixture('icp_scored_contracting.json');
    event.cls_all.activation_state.activation_evidence_dated = false;
    const problems = validateEvent(event, cfg);
    assert.ok(problems.some((p) => /activation_state_used is "Contracting", but cls_all\.activation_state gives "Stable"/.test(p)));

    // Downgraded to the default, flagged, arithmetic redone: accepted.
    const fixed = fixture('icp_scored_contracting.json');
    fixed.cls_all.activation_state.activation_evidence_dated = false;
    fixed.score.activation_state_used = cfg.activation_default;
    fixed.score.multiplier = cfg.activation_multipliers[cfg.activation_default];
    fixed.score.final_score = roundHalfUp(fixed.score.composite * fixed.score.multiplier);
    fixed.score.grade = gradeFor(fixed.score.final_score, cfg.thresholds);
    fixed.score.flags = fixed.score.flags.concat(['contracting_without_dated_evidence']);
    assert.deepEqual(validateEvent(fixed, cfg), []);
  });

  test('a state the classifier could not determine falls back to the default', () => {
    const event = valid();
    event.cls_all.activation_state.value = null;
    const problems = validateEvent(event, cfg);
    assert.ok(problems.some((p) => new RegExp(`gives "${cfg.activation_default}"`).test(p)));
  });
});

describe('the two fields taken on trust are taken on trust', () => {
  test('confidence_overall is not second-guessed', () => {
    // n8n never sees the per-source confidences the table weighed, so any of
    // the three labels is accepted. Saying otherwise would mean inventing a
    // rule the payload cannot support.
    for (const label of ['high', 'medium', 'low']) {
      assert.deepEqual(problemsFor((e) => { e.score.confidence_overall = label; }), []);
    }
    one((e) => { e.score.confidence_overall = 'certain'; }, /confidence_overall must be one of/);
  });

  test('tier2_candidate is not second-guessed either', () => {
    // The rule reads a revenue NUMBER; v6 sends a band string.
    for (const value of [true, false]) {
      assert.deepEqual(problemsFor((e) => { e.score.tier2_candidate = value; }), []);
    }
    one((e) => { e.score.tier2_candidate = 'yes'; }, /tier2_candidate must be a boolean/);
  });
});

describe('the spliced helpers match the engine they were copied from', () => {
  test('roundHalfUp agrees with engine/scoring.mjs across the range', () => {
    for (let i = 0; i <= 100000; i += 1) {
      const x = i / 1000;
      assert.equal(roundHalfUp(x), engineRoundHalfUp(x), `roundHalfUp(${x})`);
    }
    for (const x of [74.5, 74.49999999999999, 87.65 * 0.8, 92.5 * 0.95, 0, 100]) {
      assert.equal(roundHalfUp(x), engineRoundHalfUp(x), `roundHalfUp(${x})`);
    }
    assert.equal(roundHalfUp(null), null);
  });

  test('gradeFor agrees with the rubric thresholds at every boundary', () => {
    const { A, B } = RUBRIC.thresholds;
    assert.equal(gradeFor(A, RUBRIC.thresholds), 'A');
    assert.equal(gradeFor(A - 1, RUBRIC.thresholds), 'B');
    assert.equal(gradeFor(B, RUBRIC.thresholds), 'B');
    assert.equal(gradeFor(B - 1, RUBRIC.thresholds), 'C');
    assert.equal(gradeFor(null, RUBRIC.thresholds), null);
  });

  test('the file has no imports, so it can be spliced into a Code node', () => {
    const source = readFileSync(join(ROOT, 'engine', 'validate_event.mjs'), 'utf8');
    assert.doesNotMatch(source, /^\s*import\s/m);
    assert.doesNotMatch(source, /require\(/);
  });

  test('the ParseScored node carries this file, exports stripped', () => {
    const source = readFileSync(join(ROOT, 'engine', 'validate_event.mjs'), 'utf8');
    const node = readFileSync(join(ROOT, 'n8n', 'nodes', 'ParseScored.js'), 'utf8');
    const body = source.slice(source.indexOf('export const STATES')).replace(/^export /gm, '');
    assert.ok(node.includes(body), 'ParseScored.js is stale — run `npm run gen:nodes`');
  });
});

describe('a body that is not an event at all', () => {
  test('is refused without throwing', () => {
    for (const body of [null, undefined, 'a string', 42, []]) {
      const problems = validateEvent(body, cfg);
      assert.ok(problems.length > 0, JSON.stringify(body));
    }
  });

  test('an empty object names every missing key rather than the first', () => {
    const problems = validateEvent({}, cfg);
    assert.ok(problems.length >= 10, `expected every gap named, got ${problems.length}`);
    assert.ok(problems.some((p) => /missing "request_id"/.test(p)));
    assert.ok(problems.some((p) => /missing "score"/.test(p)));
  });
});
