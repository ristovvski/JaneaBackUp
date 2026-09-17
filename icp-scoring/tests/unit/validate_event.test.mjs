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

import { validateEvent } from '../../engine/validate_event.mjs';
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
    'icp_scored_A.json', 'icp_scored_B_stable.json', 'icp_scored_contracting_valid.json',
    'icp_scored_contracting_unbacked.json', 'icp_scored_insufficient.json',
    'icp_scored_tier2.json', 'icp_scored_unknown_vertical.json',
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
    withThem.emitted_at = '2026-09-18T10:42:00Z';
    withThem.clay_table = 'ICP v6';
    withThem.clay_row_url = null;
    assert.deepEqual(validateEvent(withThem, cfg), [], 'present is also fine');
  });

  test('deal_id may be an integer, null, or absent entirely', () => {
    for (const mutate of [
      (e) => { e.deal_id = 55001; },
      (e) => { e.deal_id = null; },
      (e) => { delete e.deal_id; },
    ]) {
      assert.deepEqual(problemsFor(mutate), []);
    }
  });

  test('geography and buying_signal are accepted with or without the optional keys', () => {
    // The task shows geography without missing_inputs and buying_signal with
    // neither. Accepting the fuller shape too costs nothing; rejecting a run
    // because a sibling key travelled would cost a score.
    assert.deepEqual(problemsFor((e) => {
      e.cls_all.geography.missing_inputs = ['apollo.country'];
      e.cls_all.buying_signal.confidence = 'medium';
      e.cls_all.buying_signal.missing_inputs = [];
    }), []);
    assert.deepEqual(problemsFor((e) => {
      delete e.cls_all.geography.confidence;
    }), []);
  });

  test('a score block is not part of the v6 contract', () => {
    // The table classifies, n8n scores. An event carrying a score means one of
    // the two is doing the other's job, and that is worth hearing about.
    one((e) => { e.score = { grade: 'A' }; }, /unknown top-level key "score"/);
  });
});

describe('shape', () => {
  test('a missing required key is named', () => {
    for (const key of [
      'request_id', 'org_id', 'requested_at', 'identifier_kind', 'identifier_value',
      'resolved', 'cls_all', 'apollo_summary', 'model_version',
    ]) {
      one((e) => { delete e[key]; }, new RegExp(`missing "${key}"`));
    }
  });

  test('ids are numbers, not quoted numbers', () => {
    one((e) => { e.org_id = '10001'; }, /org_id must be a positive integer/);
    one((e) => { e.deal_id = '55001'; }, /deal_id must be an integer or null/);
  });

  test('an unknown key anywhere is rejected — a table change must be loud', () => {
    one((e) => { e.brand_new_column = 1; }, /unknown top-level key "brand_new_column"/);
    one((e) => { e.cls_all.jobs = {}; }, /cls_all has an unknown key "jobs"/);
    one((e) => { e.cls_all.engineering_hiring.eng_closed = 2; }, /engineering_hiring has an unknown key "eng_closed"/);
    one((e) => { e.cls_all.geography.level_reason = 'x'; }, /cls_all.geography has an unknown key "level_reason"/);
    one((e) => { e.resolved.twitter = 'x'; }, /resolved has an unknown key "twitter"/);
    one((e) => { e.apollo_summary.sic_code = '1'; }, /apollo_summary has an unknown key "sic_code"/);
  });

  test('every hiring count may be null — a provider that found nothing is not malformed', () => {
    assert.deepEqual(problemsFor((e) => {
      e.cls_all.engineering_hiring = {
        total_open: null, eng_open: null, eng_open_60d_plus: null, dates_available: false,
        leader_titles: [], eng_titles_with_days: [], eng_open_ratio: null, eng_headcount: null,
      };
    }), []);
    one((e) => { e.cls_all.engineering_hiring.eng_open = 'three'; }, /engineering_hiring.eng_open has the wrong type/);
    one((e) => { delete e.cls_all.engineering_hiring.dates_available; }, /engineering_hiring.dates_available is missing/);
  });

  test('the model version must be the one this workflow holds', () => {
    one((e) => { e.model_version = 'v5'; }, /model_version must be "v6"/);
  });

  test('an off-ladder level is caught on every component that carries one', () => {
    for (const name of ['company_type', 'stage_maturity', 'geography', 'revenue_range', 'buying_signal']) {
      one((e) => { e.cls_all[name].level = 5; }, new RegExp(`cls_all.${name}.level must be null or one of`));
    }
  });

  test('a null level is allowed — it is how the table says it could not tell', () => {
    assert.deepEqual(problemsFor((e) => {
      e.cls_all.stage_maturity.level = null;
      e.cls_all.revenue_range.level = null;
    }), []);
  });

  test('activation_evidence_dated is a citation string, not a boolean', () => {
    one((e) => { e.cls_all.activation_state.activation_evidence_dated = true; },
      /activation_evidence_dated must be a citation string or null/);
    assert.deepEqual(problemsFor((e) => { e.cls_all.activation_state.activation_evidence_dated = null; }), []);
  });

  test('revenue_range must say where its band came from', () => {
    one((e) => { delete e.cls_all.revenue_range.revenue_source; }, /revenue_range.revenue_source is missing/);
    one((e) => { delete e.cls_all.revenue_range.revenue_band_used; }, /revenue_range.revenue_band_used is missing/);
    // Null is a legitimate answer; absent is not.
    assert.deepEqual(problemsFor((e) => {
      e.cls_all.revenue_range.revenue_band_used = null;
      e.cls_all.revenue_range.revenue_source = null;
    }), []);
  });

  test('apollo_summary carries the growth figures the Contracting guard reads', () => {
    one((e) => { delete e.apollo_summary.headcount_6mo_growth; }, /apollo_summary.headcount_6mo_growth is missing/);
    one((e) => { e.apollo_summary.headcount_6mo_growth = '-0.18'; }, /headcount_6mo_growth has the wrong type/);
    assert.deepEqual(problemsFor((e) => { e.apollo_summary.headcount_6mo_growth = null; }), []);
  });

  test('a confidence outside the three is rejected wherever it appears', () => {
    one((e) => { e.cls_all.revenue_range.confidence = 'certain'; }, /revenue_range.confidence must be one of/);
    one((e) => { e.cls_all.industry_vertical.confidence = null; }, /industry_vertical.confidence must be one of/);
  });
});

describe('the spliced copy matches the source', () => {
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
      assert.ok(validateEvent(body, cfg).length > 0, JSON.stringify(body));
    }
  });

  test('an empty object names every missing key rather than the first', () => {
    const problems = validateEvent({}, cfg);
    assert.ok(problems.length >= 9, `expected every gap named, got ${problems.length}`);
    assert.ok(problems.some((p) => /missing "request_id"/.test(p)));
    assert.ok(problems.some((p) => /missing "cls_all"/.test(p)));
  });
});
