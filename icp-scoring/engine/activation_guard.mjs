// engine/activation_guard.mjs — the v6 Contracting guard.
//
// v5 asked one question: is the Contracting evidence dated within 12 months?
// It had nothing else to ask with. v6 receives Apollo's headcount trend, so it
// can ask the question that actually matters — did this company shrink? — and
// fall back to the dated-evidence test only when the trend is unavailable or
// inconclusive.
//
// Contracting is a multiplier of ZERO. It takes an account off the board
// entirely, so the bar for applying it is deliberately higher than for any
// other state, and an unbacked claim is downgraded rather than honoured.
//
// Contracting stands if EITHER holds:
//
//   1. apollo_summary.headcount_6mo_growth <= -0.15 — a real, measured
//      contraction over six months.
//   2. `activation_evidence_dated` names a layoff or hiring-freeze item AND
//      carries a date within 12 months of requested_at.
//
// Otherwise the state is downgraded to the rubric default and the run is
// flagged `contracting_without_dated_evidence`.
//
// Test 2 is a keyword match over a citation string, which is a heuristic, and
// it is written as one: the word list is explicit, it is conservative (it does
// not try to infer a layoff from "restructuring" alone appearing anywhere in
// the evidence array), and a miss costs a downgrade — the safe direction. A
// funding round dated last month reads as evidence of the OPPOSITE of
// contraction, so `apollo.funding_events[0].date: 2025-09-01` does not qualify.
//
// NO IMPORTS. Spliced into the Score Code node by scripts/gen_nodes.mjs.

export const HEADCOUNT_CONTRACTION_THRESHOLD = -0.15;
export const EVIDENCE_MAX_AGE_MONTHS = 12;

// Deliberately narrow. Each of these names a workforce reduction or a stop on
// hiring; none of them is a word that shows up in a healthy company's news.
export const CONTRACTION_WORDS = [
  'layoff', 'lay off', 'lay-off', 'laid off', 'redundanc', 'redundant',
  'job cut', 'jobs cut', 'headcount reduc', 'workforce reduc', 'reduction in force',
  'downsiz', 'hiring freeze', 'freeze on hiring', 'hiring pause', 'shed staff',
  'cuts staff', 'cut staff', 'staff cut', 'restructuring with job',
];

/** The date in an evidence citation, as {y, m, d}, or null. ISO or nothing. */
export function dateInCitation(text) {
  if (typeof text !== 'string') return null;
  const match = /(\d{4})-(\d{2})-(\d{2})/.exec(text);
  if (!match) return null;
  const y = Number(match[1]); const m = Number(match[2]); const d = Number(match[3]);
  if (m < 1 || m > 12 || d < 1 || d > 31) return null;
  return { y, m, d };
}

/** Whole months from a {y,m,d} to an ISO instant. Negative means the future. */
export function monthsBefore(date, isoNow) {
  if (!date || typeof isoNow !== 'string') return null;
  const now = dateInCitation(isoNow);
  if (!now) return null;
  let months = (now.y - date.y) * 12 + (now.m - date.m);
  if (now.d < date.d) months -= 1;
  return months;
}

export function namesContraction(text) {
  if (typeof text !== 'string') return false;
  const lower = text.toLowerCase();
  return CONTRACTION_WORDS.some((word) => lower.indexOf(word) !== -1);
}

/**
 * Decide the activation state a score may use.
 *
 * @param {object} activation cls_all.activation_state
 * @param {object} apollo     apollo_summary
 * @param {string} requestedAt ISO instant Path A stamped the request with
 * @param {string} fallback   the rubric's default state
 * @returns {{state, guard_applied, reason, growth, evidence_months}}
 */
export function activationStateFor(activation, apollo, requestedAt, fallback) {
  const claimed = activation && activation.value ? activation.value : null;
  const growth = apollo && typeof apollo.headcount_6mo_growth === 'number'
    ? apollo.headcount_6mo_growth
    : null;

  if (claimed !== 'Contracting') {
    return {
      state: claimed === null ? fallback : claimed,
      guard_applied: false,
      reason: claimed === null ? 'no state determined, rubric default used' : null,
      growth,
      evidence_months: null,
    };
  }

  if (growth !== null && growth <= HEADCOUNT_CONTRACTION_THRESHOLD) {
    return {
      state: 'Contracting',
      guard_applied: false,
      reason: `headcount_6mo_growth ${growth} <= ${HEADCOUNT_CONTRACTION_THRESHOLD}`,
      growth,
      evidence_months: null,
    };
  }

  const citation = activation ? activation.activation_evidence_dated : null;
  const months = monthsBefore(dateInCitation(citation), requestedAt);
  const dated = months !== null && months >= 0 && months <= EVIDENCE_MAX_AGE_MONTHS;
  if (namesContraction(citation) && dated) {
    return {
      state: 'Contracting',
      guard_applied: false,
      reason: `dated contraction evidence ${months} month(s) old`,
      growth,
      evidence_months: months,
    };
  }

  const why = [];
  if (growth === null) why.push('headcount_6mo_growth unavailable');
  else why.push(`headcount_6mo_growth ${growth} > ${HEADCOUNT_CONTRACTION_THRESHOLD}`);
  if (!citation) why.push('no dated evidence cited');
  else if (!namesContraction(citation)) why.push('cited evidence names no layoff or hiring freeze');
  else if (!dated) why.push(months === null ? 'cited evidence carries no date' : `cited evidence is ${months} month(s) old`);

  return {
    state: fallback,
    guard_applied: true,
    reason: why.join('; '),
    growth,
    evidence_months: months,
  };
}
