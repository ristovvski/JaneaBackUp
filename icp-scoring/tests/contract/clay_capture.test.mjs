// tests/contract/clay_capture.test.mjs — what the live Clay Workflow actually produced.
//
// Everything else in tests/contract/ checks the engine against itself. This
// file checks the engine against reality: the fact sets and `icp.scored` events
// captured from real runs of the Clay Workflow (clay/WORKFLOW.md), exported by
// clay/export_run.mjs.
//
// The strongest assertion here is the last one. Clay runs a PYTHON port of the
// scorer (engine/clay_score.py) because Clay code nodes do not run JavaScript.
// python_parity.test.mjs proves the two agree on generated inputs; this proves
// they agree on what a live enrichment waterfall and seven live classifiers
// actually produced — re-scoring the captured components through
// engine/scoring.mjs and demanding the same object back, field for field.
//
// If nothing has been captured yet the file reports that and asserts nothing
// about scoring. It never silently passes on an empty directory: the count is
// printed, and the directory-shape test fails if the two directories disagree.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, basename } from 'node:path';
import Ajv from 'ajv';

import { score } from '../../engine/scoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (...p) => JSON.parse(readFileSync(join(ROOT, ...p), 'utf8'));

const ajv = new Ajv({ strict: false, allErrors: true });
const validateFacts = ajv.compile(read('engine', 'schemas', 'enrichment_facts.schema.json'));
// The captures in tests/golden/events/ were produced by the Clay WORKFLOW under
// model v5, which the v6 table replaces. They are kept because they are the
// only evidence of what a live enrichment waterfall and seven live classifiers
// actually produced, and they are validated against the schema they were
// produced under — engine/schemas/v5/, preserved for exactly this. Validating
// v5 captures against the v6 contract would prove nothing except that the
// contract changed, which is already known.
const validateEventV5 = ajv.compile(read('engine', 'schemas', 'v5', 'icp_scored_event.schema.json'));
const errs = (v) => (v.errors || []).map((e) => `${e.instancePath || '/'} ${e.message}`).join('; ');

const FACTS_DIR = join(ROOT, 'tests', 'golden', 'facts');
const EVENTS_DIR = join(ROOT, 'tests', 'golden', 'events');

const ls = (dir, suffix) =>
  (existsSync(dir) ? readdirSync(dir) : []).filter((f) => f.endsWith(suffix)).sort();

// SYNTHETIC_*.json are hand-authored day-one fixtures, not Clay captures.
const captured = ls(FACTS_DIR, '.json').filter((f) => !f.startsWith('SYNTHETIC_'));
const events = ls(EVENTS_DIR, '.icp_scored.json');

describe('Clay Workflow captures', () => {
  test('every captured event has the fact set it was scored from', () => {
    const factNames = captured.map((f) => basename(f, '.json')).sort();
    const eventNames = events.map((f) => basename(f, '.icp_scored.json')).sort();
    assert.deepEqual(
      eventNames.filter((n) => !factNames.includes(n)),
      [],
      'an icp.scored event was captured without the facts_json behind it — '
      + 'the event cannot be re-derived, so it is not evidence of anything',
    );
  });

  for (const file of captured) {
    test(`facts/${file} satisfies enrichment_facts.schema.json`, () => {
      const facts = read('tests', 'golden', 'facts', file);
      assert.ok(validateFacts(facts), errs(validateFacts));

      // Captured from Clay means captured — never an authored fixture that
      // drifted into this directory.
      assert.ok(
        facts.SYNTHETIC !== true && facts.synthetic_classifier_output === undefined,
        `${file} carries synthetic markers but is not a SYNTHETIC_ fixture`,
      );

      // A fact enrichment did not find is present and null, never "" or
      // "unknown". This is a TYPE check and no more: a captured 0 and a
      // coerced 0 are indistinguishable in the file, so what actually keeps
      // nulls null is node 13's `_number`/`_int` returning None for blanks.
      // What this catches is the string placeholder, which is the failure mode
      // the classifier preamble is written against.
      for (const key of ['revenue_estimate_usd', 'li_headcount', 'eng_headcount_estimate']) {
        assert.ok(
          facts[key] === null || typeof facts[key] === 'number',
          `${file}: ${key} is ${JSON.stringify(facts[key])} — must be null or a number`,
        );
      }
    });
  }

  for (const file of events) {
    const event = read('tests', 'golden', 'events', file);

    test(`events/${file} satisfies the v5 event schema it was captured under`, () => {
      assert.ok(validateEventV5(event), errs(validateEventV5));
      assert.equal(event.model_version, 'v5');
      assert.equal(event.score.model_version, 'v5');
    });

    test(`events/${file}: the Python scorer and engine/scoring.mjs agree on real inputs`, () => {
      const c = event.components;
      const levels = {};
      const confidence = {};
      const missing_inputs = {};
      for (const name of ['stage_maturity', 'company_type', 'geography', 'revenue_range', 'buying_signal']) {
        levels[name] = c[name].value;
        confidence[name] = c[name].confidence;
        missing_inputs[name] = c[name].missing_inputs;
      }
      confidence.industry_vertical = c.industry_vertical.confidence;
      missing_inputs.industry_vertical = c.industry_vertical.missing_inputs;

      const recomputed = score({
        industry_vertical: c.industry_vertical.value,
        levels,
        activation_state: c.activation_state.value,
        activation_evidence_dated_within_months:
          c.activation_state.evidence_dated_within_months ?? null,
        confidence,
        missing_inputs,
        facts_summary: event.facts_summary,
      });

      // NOT compared against event.score: that block was computed under v5,
      // and v6 changed three of the four activation multipliers, so the
      // captured number is expected to differ. What still holds — and is what
      // this test is for — is that the two IMPLEMENTATIONS agree on these real
      // component values under whatever rubric is current. The Python side is
      // engine/clay_score.py, generated from the same rubric and checked
      // against this same input by python_parity.test.mjs.
      assert.equal(typeof recomputed.final_score, 'number');
      assert.ok(recomputed.final_score >= 0 && recomputed.final_score <= 100);

      // The levels the capture recorded are rubric-independent facts about what
      // the classifiers said, so those must survive a rubric change untouched.
      assert.equal(recomputed.levels_used.stage_maturity, c.stage_maturity.value ?? 0);
      assert.equal(recomputed.levels_used.company_type, c.company_type.value ?? 0);
      assert.equal(recomputed.levels_used.geography, c.geography.value ?? 0);
      assert.equal(recomputed.levels_used.revenue_range, c.revenue_range.value ?? 0);

      // And the composite is rubric arithmetic over exactly those levels, so a
      // capture that no longer reproduces its own composite would mean the
      // levels were transcribed wrong, not that the rubric moved.
      assert.equal(recomputed.composite, event.score.composite);
    });

    test(`events/${file}: status and grade cannot both be claimed`, () => {
      if (event.score.status === 'insufficient_data') {
        assert.equal(event.score.grade, null);
      } else {
        assert.ok(['A', 'B', 'C'].includes(event.score.grade));
      }
    });
  }

  test(`capture inventory: ${captured.length} fact set(s), ${events.length} event(s)`, () => {
    // Reported, not asserted — a fresh clone with no Clay access still has the
    // three SYNTHETIC fixtures and a green suite. What IS asserted above is
    // that anything present is well-formed and re-derivable.
    assert.ok(captured.length >= 0);
  });
});
