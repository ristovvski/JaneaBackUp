// tests/unit/validate_event.test.mjs — the Path B boundary, rule by rule.
//
// Every case here is a payload that could arrive from the Clay table, and the
// question is only ever one thing: would this be WRITTEN to a rep's CRM? The
// contract is small on purpose — the table scores — so what is left is the set
// of things that must not reach Pipedrive.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
  validateEvent, REQUIRED_TOP, OPTIONAL_TOP, ALLOWED_TOP, LEVEL_KEYS, GRADES, STATUSES,
} from '../../engine/validate_event.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const CLAY = join(ROOT, 'tests', 'fixtures', 'clay');
const read = (name) => JSON.parse(readFileSync(join(CLAY, name), 'utf8'));
const cfg = { levels: [0, 3, 7, 10], model_version: 'v6' };

/** Mutate a copy of the good fixture and return the problems. */
const problemsFor = (mutate) => {
  const event = read('icp_scored_A.json');
  if (mutate) mutate(event);
  return validateEvent(event, cfg);
};

/** Assert the mutation is rejected, and rejected for the stated reason. */
const one = (mutate, pattern) => {
  const problems = problemsFor(mutate);
  assert.ok(problems.length > 0, 'expected at least one problem');
  assert.ok(
    problems.some((p) => pattern.test(p)),
    `expected a problem matching ${pattern}, got: ${problems.join('; ')}`
  );
};

describe('what the table is supposed to send', () => {
  test('every generated fixture that should pass, passes', () => {
    const shouldPass = readdirSync(CLAY)
      .filter((f) => f.endsWith('.json'))
      .filter((f) => !f.includes('malformed') && !f.includes('v60_shape'));
    assert.ok(shouldPass.length >= 6, 'the fixture set must not quietly shrink');
    for (const file of shouldPass) {
      assert.deepEqual(validateEvent(read(file), cfg), [], file);
    }
  });

  test('the LIVE capture passes — the contract is written against the wire', () => {
    // tests/fixtures/clay/icp_scored_live_intellistack.json is the body Clay
    // actually posted on 2026-09-17 (execution 60629), kept verbatim. If this
    // ever fails, the contract has drifted away from what the table sends and
    // the contract is what is wrong.
    assert.deepEqual(validateEvent(read('icp_scored_live_intellistack.json'), cfg), []);
  });

  test('the eight required keys alone are enough', () => {
    const bare = read('icp_scored_bare.json');
    assert.deepEqual(Object.keys(bare).sort(), [...REQUIRED_TOP].sort());
    assert.deepEqual(validateEvent(bare, cfg), []);
  });

  test('the working is optional, every field of it', () => {
    for (const key of OPTIONAL_TOP) {
      assert.deepEqual(problemsFor((e) => { delete e[key]; }), [], `${key} must be optional`);
    }
  });
});

describe('the old contract is rejected, loudly', () => {
  test('a v6.0 event — classifiers, no grade — names every missing key', () => {
    // This is the regression that started the rewrite: Path B answered 200,
    // wrote nothing, and told nobody. It must now be rejected by name.
    const problems = validateEvent(read('icp_scored_v60_shape.json'), cfg);
    for (const key of ['final', 'grade', 'status', 'note']) {
      assert.ok(problems.some((p) => p === `missing "${key}"`), `must name missing ${key}: ${problems.join('; ')}`);
    }
    for (const key of ['domain', 'resolved', 'cls_all', 'apollo_summary', 'model_version']) {
      assert.ok(
        problems.some((p) => p === `unknown top-level key "${key}"`),
        `must reject the v6.0 key ${key}: ${problems.join('; ')}`
      );
    }
  });

  test('every problem is listed at once, not the first one', () => {
    const problems = validateEvent(read('icp_scored_v60_shape.json'), cfg);
    assert.ok(problems.length >= 9,
      `a table wrong in nine places is fixed in one pass, got ${problems.length}`);
  });
});

describe('identity', () => {
  test('a missing required key is named', () => {
    for (const key of REQUIRED_TOP) {
      one((e) => { delete e[key]; }, new RegExp(`missing "${key}"`));
    }
  });

  test('ids are numbers, not quoted numbers', () => {
    one((e) => { e.org_id = '10001'; }, /org_id must be a positive integer/);
    one((e) => { e.org_id = 0; }, /org_id must be a positive integer/);
    one((e) => { e.deal_id = '55001'; }, /deal_id must be an integer or null/);
  });

  test('deal_id may be null — a re-score can happen outside a deal', () => {
    assert.deepEqual(problemsFor((e) => { e.deal_id = null; }), []);
  });

  test('request_id must be there and non-empty — it is the dedupe key', () => {
    one((e) => { e.request_id = ''; }, /request_id must be a non-empty string/);
    one((e) => { e.request_id = 12345; }, /request_id must be a non-empty string/);
  });

  test('an unknown key is rejected — a table change must be loud', () => {
    one((e) => { e.brand_new_column = 1; }, /unknown top-level key "brand_new_column"/);
    one((e) => { e.what_they_sell = 'software'; }, /unknown top-level key "what_they_sell"/);
  });
});

describe('the grade', () => {
  test('status is closed to the two the workflow can act on', () => {
    for (const status of STATUSES) {
      assert.deepEqual(problemsFor((e) => {
        e.status = status;
        if (status === 'insufficient_data') { e.final = null; e.grade = null; }
      }), [], status);
    }
    one((e) => { e.status = 'error'; }, /status must be one of/);
    one((e) => { e.status = 'Scored'; }, /status must be one of/);
  });

  test('grade is A, B, C or null — nothing else', () => {
    for (const grade of GRADES) {
      assert.deepEqual(problemsFor((e) => { e.grade = grade; }), [], grade);
    }
    one((e) => { e.grade = 'D'; }, /grade must be one of/);
    one((e) => { e.grade = 'a'; }, /grade must be one of/);
  });

  test('final is an integer 0-100', () => {
    one((e) => { e.final = 101; }, /final must be an integer 0-100/);
    one((e) => { e.final = -1; }, /final must be an integer 0-100/);
    one((e) => { e.final = 62.5; }, /final must be an integer 0-100/);
    one((e) => { e.final = '62'; }, /final must be an integer 0-100/);
    assert.deepEqual(problemsFor((e) => { e.final = 0; }), []);
    assert.deepEqual(problemsFor((e) => { e.final = 100; }), []);
  });

  test('"scored" with no grade is refused — the worst thing this could write', () => {
    // A grade-shaped blank on a rep's record is worse than a loud failure.
    one((e) => { e.grade = null; }, /status is "scored" but final or grade is null/);
    one((e) => { e.final = null; }, /status is "scored" but final or grade is null/);
  });

  test('insufficient_data with nulls is fine — that is what it means', () => {
    assert.deepEqual(problemsFor((e) => {
      e.status = 'insufficient_data';
      e.final = null;
      e.grade = null;
    }), []);
  });
});

describe('the note', () => {
  test('it must be there, and must say something', () => {
    // It is written to the activity verbatim. An empty note is an activity
    // that looks like the workflow ran and had nothing to say.
    one((e) => { e.note = ''; }, /note must be a non-empty string/);
    one((e) => { e.note = '   \n  '; }, /note must be a non-empty string/);
    one((e) => { e.note = null; }, /note must be a non-empty string/);
    one((e) => { e.note = ['line']; }, /note must be a non-empty string/);
  });

  test('length is not policed — verbatim means verbatim', () => {
    assert.deepEqual(problemsFor((e) => { e.note = 'x'.repeat(5000); }), []);
  });
});

describe('the working, when it travels', () => {
  test('levels are on the ladder or null', () => {
    for (const key of LEVEL_KEYS) {
      one((e) => { e[key] = 5; }, new RegExp(`${key} must be null or one of`));
      one((e) => { e[key] = '7'; }, new RegExp(`${key} must be null or one of`));
      assert.deepEqual(problemsFor((e) => { e[key] = null; }), [], key);
      for (const level of [0, 3, 7, 10]) {
        assert.deepEqual(problemsFor((e) => { e[key] = level; }), [], `${key}=${level}`);
      }
    }
  });

  test('activation_used is one of the four states', () => {
    one((e) => { e.activation_used = 'Growing'; }, /activation_used must be null or one of/);
    assert.deepEqual(problemsFor((e) => { e.activation_used = 'Contracting'; }), []);
  });

  test('confidence_overall is one of the three', () => {
    one((e) => { e.confidence_overall = 'certain'; }, /confidence_overall must be null or one of/);
  });

  test('tier2_candidate is a boolean, flags an array of strings', () => {
    one((e) => { e.tier2_candidate = 'yes'; }, /tier2_candidate must be a boolean/);
    one((e) => { e.flags = 'unknown_vertical'; }, /flags must be an array of strings/);
    one((e) => { e.flags = [1, 2]; }, /flags must be an array of strings/);
    assert.deepEqual(problemsFor((e) => { e.flags = []; }), []);
  });

  test('composite and the multiplier are numbers, and may be fractional', () => {
    assert.deepEqual(problemsFor((e) => { e.composite = 92.5; }), []);
    assert.deepEqual(problemsFor((e) => { e.multiplier = 0.95; }), []);
    one((e) => { e.composite = '78'; }, /composite must be a number/);
    one((e) => { e.multiplier = 'x'; }, /multiplier must be a number/);
  });

  test('ALLOWED_TOP is exactly required + optional, with no overlap', () => {
    assert.deepEqual(ALLOWED_TOP, REQUIRED_TOP.concat(OPTIONAL_TOP));
    assert.equal(new Set(ALLOWED_TOP).size, ALLOWED_TOP.length, 'no key may be in both lists');
  });
});

describe('the spliced copy matches the source', () => {
  test('the file has no imports, so it can be spliced into a Code node', () => {
    const source = readFileSync(join(ROOT, 'engine', 'validate_event.mjs'), 'utf8');
    assert.ok(!/^\s*import\s/m.test(source));
  });

  test('the ParseScored node carries this file, exports stripped', () => {
    const source = readFileSync(join(ROOT, 'engine', 'validate_event.mjs'), 'utf8');
    const node = readFileSync(join(ROOT, 'n8n', 'nodes', 'ParseScored.js'), 'utf8');
    const body = source.slice(source.indexOf('export const GRADES')).replace(/^export /gm, '');
    assert.ok(node.includes(body), 'ParseScored has drifted from engine/validate_event.mjs');
  });
});

describe('a body that is not an event at all', () => {
  test('is refused without throwing', () => {
    for (const body of [null, undefined, 'a string', 42, [], true]) {
      const problems = validateEvent(body, cfg);
      assert.ok(problems.length > 0, JSON.stringify(body));
    }
  });

  test('an empty object names every missing key rather than the first', () => {
    const problems = validateEvent({}, cfg);
    for (const key of REQUIRED_TOP) {
      assert.ok(problems.includes(`missing "${key}"`), `must name ${key}`);
    }
  });
});
