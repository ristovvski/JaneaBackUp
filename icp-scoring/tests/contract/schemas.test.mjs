// tests/contract/schemas.test.mjs — the boundaries hold.
//
// Three schemas guard three boundaries: Clay -> classifier (facts),
// classifier -> Clay (one component), Clay -> n8n (the scored event). This
// file asserts every fixture sits on the right side of its boundary, and that
// the per-component `value` discriminator actually discriminates.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import Ajv from 'ajv';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...p) => JSON.parse(readFileSync(join(ROOT, ...p), 'utf8'));

const RUBRIC = read('config', 'rubric_v6.json');
const eventSchema = read('engine', 'schemas', 'icp_scored_event.schema.json');
const classifierSchema = read('engine', 'schemas', 'classifier_output.schema.json');
const factsSchema = read('engine', 'schemas', 'enrichment_facts.schema.json');

const ajv = new Ajv({ strict: false, allErrors: true });
const validateEvent = ajv.compile(eventSchema);
const validateClassifier = ajv.compile(classifierSchema);
const validateFacts = ajv.compile(factsSchema);

const CLAY_DIR = join(ROOT, 'tests', 'fixtures', 'clay');
const clayFiles = readdirSync(CLAY_DIR).filter((f) => f.endsWith('.json')).sort();

const errs = (v) => (v.errors || []).map((e) => `${e.instancePath || '/'} ${e.message}`).join('; ');

describe('icp_scored_event.schema.json', () => {
  test('the fixture set is the one §3 asks for', () => {
    assert.deepEqual(clayFiles, [
      'icp_scored_A.json',
      'icp_scored_B_stable.json',
      'icp_scored_contracting.json',
      'icp_scored_insufficient.json',
      'icp_scored_malformed.json',
      'icp_scored_tier2.json',
    ]);
  });

  for (const file of clayFiles.filter((f) => !f.includes('malformed'))) {
    test(`${file} validates`, () => {
      const ok = validateEvent(read('tests', 'fixtures', 'clay', file));
      assert.ok(ok, `${file} must validate but did not: ${errs(validateEvent)}`);
    });
  }

  test('icp_scored_malformed.json FAILS, and for the reasons it was built to fail for', () => {
    const malformed = read('tests', 'fixtures', 'clay', 'icp_scored_malformed.json');
    assert.equal(validateEvent(malformed), false, 'the malformed fixture must not validate');

    const paths = (validateEvent.errors || []).map((e) => e.instancePath);
    const messages = errs(validateEvent);
    assert.ok(messages.includes('additionalProperties') || paths.includes(''), 'extra top-level key');
    assert.ok(paths.some((p) => p.startsWith('/jobs')), 'missing required jobs key');
    assert.ok(paths.some((p) => p.startsWith('/score')), 'invalid score block');
  });

  test('a valid event turns invalid when any single required key is removed', () => {
    const base = read('tests', 'fixtures', 'clay', 'icp_scored_A.json');
    for (const key of eventSchema.required) {
      const mutated = structuredClone(base);
      delete mutated[key];
      assert.equal(validateEvent(mutated), false, `removing "${key}" should have failed validation`);
    }
  });

  test('an unknown top-level key is rejected (Clay drift must be loud)', () => {
    const mutated = read('tests', 'fixtures', 'clay', 'icp_scored_A.json');
    mutated.brand_new_clay_column = 'surprise';
    assert.equal(validateEvent(mutated), false);
  });

  test('status insufficient_data and a non-null grade cannot coexist', () => {
    const mutated = read('tests', 'fixtures', 'clay', 'icp_scored_insufficient.json');
    assert.equal(mutated.score.status, 'insufficient_data');
    assert.equal(mutated.score.grade, null);
    mutated.score.grade = 'A';
    assert.equal(validateEvent(mutated), false, 'insufficient_data with a grade must fail');
  });

  test('status scored requires a grade', () => {
    const mutated = read('tests', 'fixtures', 'clay', 'icp_scored_A.json');
    mutated.score.grade = null;
    assert.equal(validateEvent(mutated), false);
  });

  test('only the three rubric multipliers are accepted', () => {
    const base = read('tests', 'fixtures', 'clay', 'icp_scored_A.json');
    for (const m of Object.values(RUBRIC.activation_multipliers)) {
      const ok = structuredClone(base);
      ok.score.multiplier = m;
      // The rest of the score block still has to agree, so only check the enum
      // by asserting the multiplier is not itself the cause of a failure.
      validateEvent(ok);
      const multErrors = (validateEvent.errors || []).filter((e) => e.instancePath === '/score/multiplier');
      assert.equal(multErrors.length, 0, `multiplier ${m} must be allowed`);
    }
    const bad = structuredClone(base);
    bad.score.multiplier = 0.5;
    assert.equal(validateEvent(bad), false);
  });

  test('a level outside 0/3/7/10 is rejected wherever it appears', () => {
    for (const key of ['industries', 'geography', 'stage_maturity']) {
      const mutated = read('tests', 'fixtures', 'clay', 'icp_scored_A.json');
      mutated.score.levels[key] = 5;
      assert.equal(validateEvent(mutated), false, `score.levels.${key}`);
    }
    for (const component of ['company_type', 'stage_maturity']) {
      const mutated = read('tests', 'fixtures', 'clay', 'icp_scored_A.json');
      mutated.cls_all[component].level = 5;
      assert.equal(validateEvent(mutated), false, `cls_all.${component}.level`);
    }
  });
});

describe('classifier_output.schema.json — the per-component discriminator', () => {
  const base = (component, value, extra = {}) => ({
    component, value, evidence: ['li_industry: X'], confidence: 'high', missing_inputs: [], ...extra,
  });

  const LEVEL_COMPONENTS = ['stage_maturity', 'company_type', 'geography', 'revenue_range', 'buying_signal'];

  test('the component enum is exactly the seven classifiers', () => {
    assert.deepEqual(classifierSchema.properties.component.enum, [
      'industry_vertical', 'stage_maturity', 'company_type', 'geography',
      'revenue_range', 'activation_state', 'buying_signal',
    ]);
  });

  for (const component of LEVEL_COMPONENTS) {
    test(`${component} accepts 0/3/7/10 and null`, () => {
      for (const value of [...RUBRIC.levels, null]) {
        assert.ok(validateClassifier(base(component, value)), `${component}=${value}: ${errs(validateClassifier)}`);
      }
    });

    test(`${component} rejects an off-ladder number and any string`, () => {
      assert.equal(validateClassifier(base(component, 5)), false, '5 is not a level');
      assert.equal(validateClassifier(base(component, '10')), false, 'a stringified level');
      assert.equal(validateClassifier(base(component, 'FinTech')), false, 'a vertical name');
      assert.equal(validateClassifier(base(component, 'Stable')), false, 'an activation state');
    });
  }

  test('industry_vertical accepts all 17 verticals and null, and nothing else', () => {
    const verticals = Object.keys(RUBRIC.industry_verticals);
    assert.equal(verticals.length, 17);
    for (const v of verticals) {
      assert.ok(validateClassifier(base('industry_vertical', v)), `${v}: ${errs(validateClassifier)}`);
    }
    assert.ok(validateClassifier(base('industry_vertical', null)));

    for (const bad of ['fintech', 'FinTech ', 'Fintech', 'SaaS - Other', 'Crypto', 10, 0]) {
      assert.equal(
        validateClassifier(base('industry_vertical', bad)), false,
        `${JSON.stringify(bad)} must be rejected`
      );
    }
  });

  test('the schema enum and the rubric agree on the 17 verticals, byte for byte', () => {
    const branch = classifierSchema.allOf.find(
      (b) => b.if?.properties?.component?.const === 'industry_vertical'
    );
    const schemaVerticals = branch.then.properties.value.oneOf[0].enum;
    assert.deepEqual(schemaVerticals, Object.keys(RUBRIC.industry_verticals));
  });

  test('activation_state accepts the four states and null, and nothing else', () => {
    const states = Object.keys(RUBRIC.activation_multipliers);
    assert.deepEqual(states, ['Accelerating', 'Transitioning', 'Stable', 'Contracting']);
    for (const s of states) {
      const extra = s === 'Contracting' ? { evidence_dated_within_months: 4 } : {};
      assert.ok(validateClassifier(base('activation_state', s, extra)), `${s}: ${errs(validateClassifier)}`);
    }
    assert.ok(validateClassifier(base('activation_state', null)));
    for (const bad of ['stable', 'Declining', 10, 0]) {
      assert.equal(validateClassifier(base('activation_state', bad)), false, JSON.stringify(bad));
    }
  });

  test('the schema enum and the rubric agree on the four activation states', () => {
    const branch = classifierSchema.allOf.find(
      (b) => b.if?.properties?.component?.const === 'activation_state' && !b.if.properties.value
    );
    assert.deepEqual(
      branch.then.properties.value.oneOf[0].enum,
      Object.keys(RUBRIC.component_scales.activation_state)
    );
  });

  test('Contracting must carry evidence_dated_within_months', () => {
    assert.equal(validateClassifier(base('activation_state', 'Contracting')), false);
    assert.ok(validateClassifier(base('activation_state', 'Contracting', { evidence_dated_within_months: 6 })));
  });

  test('evidence is capped at 6 items of 200 characters', () => {
    assert.equal(
      validateClassifier({ ...base('geography', 10), evidence: new Array(7).fill('x: y') }), false
    );
    assert.equal(
      validateClassifier({ ...base('geography', 10), evidence: ['k: ' + 'x'.repeat(200)] }), false
    );
  });

  test('an unknown key is rejected, and each required key is required', () => {
    assert.equal(validateClassifier({ ...base('geography', 10), rationale: 'chatty' }), false);
    for (const key of classifierSchema.required) {
      const mutated = base('geography', 10);
      delete mutated[key];
      assert.equal(validateClassifier(mutated), false, `missing ${key}`);
    }
  });

  test('every cls_all entry of every clay fixture validates as a classifier output', () => {
    // v6 keeps four classifiers; geography, revenue_range and buying_signal are
    // levelled by the table and have no classifier object to validate. The
    // levelled two carry `level` where the classifier schema says `value`, so
    // the key is renamed for the check rather than the schema being loosened.
    // activation_state is deliberately absent. The classifier contract says the
    // evidence age in MONTHS; the v6 event carries the boolean the rubric
    // actually turns that into (`months <= contracting_max_age_months`). Two
    // contracts at two points, with the table doing the conversion — checked
    // one test down rather than by loosening either schema.
    const VALUE_KEY = { industry_vertical: 'value', company_type: 'level', stage_maturity: 'level' };
    for (const file of clayFiles.filter((f) => !f.includes('malformed'))) {
      const event = read('tests', 'fixtures', 'clay', file);
      for (const [component, key] of Object.entries(VALUE_KEY)) {
        const payload = event.cls_all[component];
        const ok = validateClassifier({
          component,
          value: payload[key],
          evidence: payload.evidence,
          confidence: payload.confidence,
          missing_inputs: payload.missing_inputs,
        });
        assert.ok(ok, `${file} / ${component}: ${errs(validateClassifier)}`);
      }
    }
  });

  test('activation_evidence_dated is the classifier month count run through the rubric', () => {
    const rubric = read('config', 'rubric_v6.json');
    const maxAge = rubric.activation_contracting_evidence_max_age_months;

    // The one fixture that claims Contracting dates its evidence 3 months back,
    // inside the window, so the boolean must be true and the multiplier must be
    // Contracting's rather than the downgrade default.
    const contracting = read('tests', 'fixtures', 'clay', 'icp_scored_contracting.json');
    assert.ok(3 <= maxAge);
    assert.equal(contracting.cls_all.activation_state.value, 'Contracting');
    assert.equal(contracting.cls_all.activation_state.activation_evidence_dated, true);
    assert.equal(contracting.score.activation_state_used, 'Contracting');
    assert.equal(contracting.score.multiplier, rubric.activation_multipliers.Contracting);

    // The flag reports whether the activation evidence is dated at all, not
    // whether the state is Contracting: a dated Accelerating call is still
    // dated. So it must be a boolean everywhere, and true wherever the case
    // gives its evidence a date inside the window.
    for (const file of clayFiles.filter((f) => !f.includes('malformed'))) {
      const event = read('tests', 'fixtures', 'clay', file);
      const flag = event.cls_all.activation_state.activation_evidence_dated;
      assert.equal(typeof flag, 'boolean', `${file}: dating flag must be a boolean, never null`);
      const hasDatedEvidence = event.cls_all.activation_state.evidence
        .some((e) => /\d{4}-\d{2}-\d{2}/.test(e));
      if (flag) assert.ok(hasDatedEvidence, `${file}: flag is true but no evidence string carries a date`);
    }
  });
});

describe('enrichment_facts.schema.json', () => {
  const minimal = () => {
    const obj = {};
    for (const key of factsSchema.required) obj[key] = null;
    obj.request_id = 'req-1';
    obj.org_id = '10001';
    obj.identifier_kind = 'domain';
    obj.identifier_value = 'acme.io';
    return obj;
  };

  test('a fact set of all nulls validates — "not found" is a legal fact', () => {
    assert.ok(validateFacts(minimal()), errs(validateFacts));
  });

  test('every required key is genuinely required', () => {
    for (const key of factsSchema.required) {
      const mutated = minimal();
      delete mutated[key];
      assert.equal(validateFacts(mutated), false, `missing ${key} should fail`);
    }
  });

  test('identifier_kind is closed to the three resolveIdentifier kinds', () => {
    const f = minimal();
    for (const kind of ['domain', 'linkedin', 'name']) {
      f.identifier_kind = kind;
      assert.ok(validateFacts(f), kind);
    }
    f.identifier_kind = 'email';
    assert.equal(validateFacts(f), false);
  });

  test('a news item must carry a date — Contracting evidence depends on it', () => {
    const f = minimal();
    f.news_last_12mo = [{ headline: 'Layoffs announced' }];
    assert.equal(validateFacts(f), false, 'a headline with no date is not usable evidence');
    f.news_last_12mo = [{ date: '2026-06-11', headline: 'Layoffs announced' }];
    assert.ok(validateFacts(f), errs(validateFacts));
  });

  test('an unknown fact key is rejected', () => {
    const f = minimal();
    f.mystery_provider_column = 'x';
    assert.equal(validateFacts(f), false);
  });

  test('negative headcounts and revenues are rejected', () => {
    const f = minimal();
    f.li_headcount = -1;
    assert.equal(validateFacts(f), false);
    f.li_headcount = 0;
    f.revenue_estimate_usd = -5;
    assert.equal(validateFacts(f), false);
  });

  test('the golden facts fixtures validate', () => {
    const dir = join(ROOT, 'tests', 'golden', 'facts');
    const files = readdirSync(dir).filter((f) => f.endsWith('.json'));
    assert.ok(files.length >= 3, 'at least the three SYNTHETIC day-one fixtures must exist');
    for (const file of files) {
      const facts = read('tests', 'golden', 'facts', file);
      assert.ok(validateFacts(facts), `${file}: ${errs(validateFacts)}`);
    }
  });
});

describe('rubric_v6.json is internally consistent (§9.2)', () => {
  test('weights sum to 100', () => {
    assert.equal(Object.values(RUBRIC.weights).reduce((a, b) => a + b, 0), 100);
  });

  test('every vertical total equals the sum of its five sub-rubric dimensions', () => {
    for (const [name, row] of Object.entries(RUBRIC.industry_verticals)) {
      const sum = row.win + row.capability + row.team_domain + row.market + row.engagement;
      assert.equal(row.total, sum, `${name}: total ${row.total} but dimensions sum to ${sum}`);
    }
  });

  test('every vertical tier matches its total against tier_thresholds', () => {
    const t = RUBRIC.industry_vertical_map.tier_thresholds;
    for (const [name, row] of Object.entries(RUBRIC.industry_verticals)) {
      let expected = 'Out';
      if (row.total >= t.Anchor) expected = 'Anchor';
      else if (row.total >= t.Watch) expected = 'Watch';
      else if (row.total >= t.Opportunistic) expected = 'Opportunistic';
      assert.equal(row.tier, expected, `${name}: total ${row.total} implies ${expected}, not ${row.tier}`);
    }
  });

  test('the tier thresholds descend, so the tier ladder is unambiguous', () => {
    const t = RUBRIC.industry_vertical_map.tier_thresholds;
    assert.ok(t.Anchor > t.Watch, 'Anchor must sit above Watch');
    assert.ok(t.Watch > t.Opportunistic, 'Watch must sit above Opportunistic');
  });

  test('every tier named by a vertical has a level in industry_vertical_map', () => {
    for (const [name, row] of Object.entries(RUBRIC.industry_verticals)) {
      assert.equal(
        typeof RUBRIC.industry_vertical_map[row.tier], 'number',
        `${name} has tier "${row.tier}" with no level`
      );
    }
  });

  test('every tier level is one of the four rubric levels', () => {
    for (const tier of ['Anchor', 'Watch', 'Opportunistic', 'Out']) {
      assert.ok(RUBRIC.levels.includes(RUBRIC.industry_vertical_map[tier]), tier);
    }
  });

  test('component_scales cover every level for every level-based component', () => {
    for (const component of ['stage_maturity', 'company_type', 'geography', 'revenue_range', 'buying_signal']) {
      const scale = RUBRIC.component_scales[component];
      assert.deepEqual(Object.keys(scale).sort(), ['0', '10', '3', '7'], component);
      for (const text of Object.values(scale)) {
        assert.ok(typeof text === 'string' && text.length > 5, `${component} has a stub definition`);
      }
    }
  });

  test('activation multipliers and activation component_scales describe the same four states', () => {
    assert.deepEqual(
      Object.keys(RUBRIC.activation_multipliers).sort(),
      Object.keys(RUBRIC.component_scales.activation_state).sort()
    );
  });

  test('the activation default is itself a known state', () => {
    assert.ok(RUBRIC.activation_default_when_no_evidence in RUBRIC.activation_multipliers);
  });

  test('thresholds are ordered and inside the reachable score range', () => {
    assert.ok(RUBRIC.thresholds.A > RUBRIC.thresholds.B);
    assert.ok(RUBRIC.thresholds.A <= 100 && RUBRIC.thresholds.B >= 0);
  });

  test('every insufficient_data component is a real weighted component', () => {
    for (const component of RUBRIC.insufficient_data_rule.components) {
      assert.ok(RUBRIC.weights[component] > 0, `${component} must carry weight`);
    }
  });

  test('grade_labels cover exactly A, B and C', () => {
    assert.deepEqual(Object.keys(RUBRIC.grade_labels).sort(), ['A', 'B', 'C']);
  });

  test('there are exactly 17 verticals and two of them are Tier 2 paths', () => {
    const verticals = Object.entries(RUBRIC.industry_verticals);
    assert.equal(verticals.length, 17);
    const tier2 = verticals.filter(([, r]) => r.tier2_path).map(([n]) => n);
    assert.deepEqual(tier2.sort(), ['Enterprise Tech / Hyperscalers', 'Pharma / Life Sciences']);
  });

  test('the geography deviation from the signed rubric is recorded in config', () => {
    assert.match(RUBRIC.geography_rule_deviation, /NEEDS_DECISION #3/);
  });
});

describe('the rubric in force is v6, and nothing still reads v5', () => {
  test('config/rubric_v6.json is what the engine loads', () => {
    const rubric = read('config', 'rubric_v6.json');
    assert.equal(rubric.model_version, 'v6');
    assert.deepEqual(rubric.activation_multipliers, {
      Accelerating: 1, Transitioning: 0.95, Stable: 0.8, Contracting: 0,
    });
    assert.deepEqual(rubric.unknown_vertical_rule, { level: 0, flag: 'unknown_vertical', confidence: 'low' });
  });

  test('config/rubric_v5.json is kept but marked superseded, and nothing reads it', () => {
    const v5 = read('config', 'rubric_v5.json');
    assert.equal(v5.superseded_by, 'rubric_v6.json');
    assert.equal(v5.model_version, 'v5');

    // A rubric no code reads is history; a rubric some code still reads is a
    // second source of truth. Only the v5 event schema, which exists to
    // validate v5 captures, may still say v5.
    const roots = ['engine', 'scripts', 'clay', 'n8n', 'config'];
    const offenders = [];
    const walk = (dir) => {
      for (const entry of readdirSync(join(ROOT, dir), { withFileTypes: true })) {
        const rel = join(dir, entry.name);
        if (entry.isDirectory()) { walk(rel); continue; }
        if (!/\.(mjs|js|py|json)$/.test(entry.name)) continue;
        if (rel.includes(join('schemas', 'v5'))) continue;
        if (entry.name === 'rubric_v5.json') continue;
        if (readFileSync(join(ROOT, rel), 'utf8').includes('rubric_v5.json')) offenders.push(rel);
      }
    };
    for (const root of roots) walk(root);
    assert.deepEqual(offenders, [], `still reading the superseded rubric:\n  ${offenders.join('\n  ')}`);
  });
});
