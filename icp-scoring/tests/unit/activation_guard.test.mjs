// tests/unit/activation_guard.test.mjs — the v6 Contracting guard.
//
// Contracting is a multiplier of zero: it takes an account off the board. The
// bar for applying it is therefore higher than for any other state, and these
// cases are the bar.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  activationStateFor, dateInCitation, monthsBefore, namesContraction,
  HEADCOUNT_CONTRACTION_THRESHOLD, EVIDENCE_MAX_AGE_MONTHS, CONTRACTION_WORDS,
} from '../../engine/activation_guard.mjs';

const NOW = '2026-09-18T10:42:00Z';
const guard = (activation, apollo = {}) => activationStateFor(activation, apollo, NOW, 'Stable');
const contracting = (over = {}) => ({ value: 'Contracting', activation_evidence_dated: null, ...over });

describe('states other than Contracting pass through', () => {
  test('a stated state is used as stated', () => {
    for (const state of ['Accelerating', 'Transitioning', 'Stable']) {
      const out = guard({ value: state, activation_evidence_dated: null });
      assert.equal(out.state, state);
      assert.equal(out.guard_applied, false);
    }
  });

  test('no state at all falls back to the rubric default', () => {
    const out = guard({ value: null, activation_evidence_dated: null });
    assert.equal(out.state, 'Stable');
    assert.equal(out.guard_applied, false);
    assert.match(out.reason, /rubric default/);
  });
});

describe('test 1 — measured contraction', () => {
  test('headcount down 18% over six months backs Contracting', () => {
    const out = guard(contracting(), { headcount_6mo_growth: -0.18 });
    assert.equal(out.state, 'Contracting');
    assert.equal(out.guard_applied, false);
    assert.match(out.reason, /headcount_6mo_growth -0\.18/);
  });

  test('the threshold is inclusive at exactly -0.15', () => {
    assert.equal(guard(contracting(), { headcount_6mo_growth: HEADCOUNT_CONTRACTION_THRESHOLD }).state, 'Contracting');
    assert.equal(guard(contracting(), { headcount_6mo_growth: -0.1499 }).state, 'Stable');
  });

  test('growth, however small, does not back Contracting', () => {
    const out = guard(contracting(), { headcount_6mo_growth: 0.05 });
    assert.equal(out.state, 'Stable');
    assert.equal(out.guard_applied, true);
    assert.match(out.reason, /0\.05 > -0\.15/);
  });
});

describe('test 2 — dated layoff or freeze evidence', () => {
  test('a dated layoff item inside the window backs Contracting', () => {
    const out = guard(
      contracting({ activation_evidence_dated: 'news: 2026-06-11 — company lays off 12% in a layoff round' }),
      { headcount_6mo_growth: 0.01 }
    );
    assert.equal(out.state, 'Contracting');
    assert.equal(out.guard_applied, false);
    assert.equal(out.evidence_months, 3);
  });

  test('the same item dated 13 months back does not', () => {
    const out = guard(
      contracting({ activation_evidence_dated: 'news: 2025-08-11 — layoff of 12% of staff' }),
      { headcount_6mo_growth: 0.01 }
    );
    assert.equal(out.state, 'Stable');
    assert.equal(out.guard_applied, true);
    assert.ok(out.evidence_months > EVIDENCE_MAX_AGE_MONTHS);
  });

  test('a funding round is not evidence of contraction, however well dated', () => {
    // This is the case the task names: Sol says Contracting, and the citation
    // it offers is a funding event — which is evidence of the opposite.
    const out = guard(
      contracting({ activation_evidence_dated: 'apollo.funding_events[0].date: 2025-09-01' }),
      { headcount_6mo_growth: 0.05 }
    );
    assert.equal(out.state, 'Stable');
    assert.equal(out.guard_applied, true);
    assert.match(out.reason, /names no layoff or hiring freeze/);
  });

  test('an undated layoff mention does not qualify', () => {
    const out = guard(
      contracting({ activation_evidence_dated: 'a blog post mentions layoffs, no date given' }),
      { headcount_6mo_growth: null }
    );
    assert.equal(out.state, 'Stable');
    assert.equal(out.guard_applied, true);
    assert.match(out.reason, /carries no date/);
  });

  test('no citation at all, and no growth figure, is the weakest case of all', () => {
    const out = guard(contracting(), {});
    assert.equal(out.state, 'Stable');
    assert.equal(out.guard_applied, true);
    assert.match(out.reason, /unavailable/);
    assert.match(out.reason, /no dated evidence cited/);
  });
});

describe('the pieces', () => {
  test('dateInCitation finds an ISO date and rejects nonsense', () => {
    assert.deepEqual(dateInCitation('x 2026-06-11 y'), { y: 2026, m: 6, d: 11 });
    assert.equal(dateInCitation('2026-13-11'), null, 'month 13');
    assert.equal(dateInCitation('June 11 2026'), null, 'not ISO');
    assert.equal(dateInCitation(null), null);
  });

  test('monthsBefore counts whole months and handles the day boundary', () => {
    assert.equal(monthsBefore({ y: 2026, m: 9, d: 18 }, NOW), 0);
    assert.equal(monthsBefore({ y: 2026, m: 9, d: 19 }, NOW), -1, 'tomorrow is the future');
    assert.equal(monthsBefore({ y: 2025, m: 9, d: 18 }, NOW), 12);
    assert.equal(monthsBefore({ y: 2025, m: 9, d: 19 }, NOW), 11);
  });

  test('namesContraction is narrow on purpose', () => {
    for (const word of CONTRACTION_WORDS) {
      assert.ok(namesContraction(`something ${word} something`), word);
    }
    // Words that describe a healthy company must not trip it.
    for (const text of [
      'apollo.funding_events[0].date: 2025-09-01',
      'raised a Series B',
      'hiring 40 engineers',
      'restructuring its product line',
      '',
    ]) {
      assert.equal(namesContraction(text), false, text);
    }
  });

  test('a future-dated citation is not treated as recent', () => {
    const out = guard(
      contracting({ activation_evidence_dated: 'news: 2027-01-01 — layoff announced' }),
      { headcount_6mo_growth: 0 }
    );
    assert.equal(out.state, 'Stable', 'evidence from the future backs nothing');
    assert.equal(out.guard_applied, true);
  });
});
