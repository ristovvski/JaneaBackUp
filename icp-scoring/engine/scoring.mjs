// engine/scoring.mjs — the deterministic ICP v5 scoring library.
//
// Pure: no network, no CRM, no clock. The rubric JSON is read once at module
// load (the only file read) so that every scoring number has exactly one
// source of truth: config/rubric_v6.json.
//
// This same arithmetic is expressed three more times, all generated from or
// tested against this file:
//   - engine/clay_formula.txt   (Clay formula column; scripts/gen_clay_formula.mjs)
//   - n8n/nodes/ParseScored.js  (independent recompute + drift guard)
//   - tests/unit/scoring.test.mjs
// If you change a number, change config/rubric_v6.json and nothing else.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
export const RUBRIC = JSON.parse(
  readFileSync(join(HERE, '..', 'config', 'rubric_v6.json'), 'utf8')
);

// ---------------------------------------------------------------------------
// Load-time invariants (S11 and friends). A bad rubric must never score.
// ---------------------------------------------------------------------------

const WEIGHT_SUM = Object.values(RUBRIC.weights).reduce((a, b) => a + b, 0);
if (WEIGHT_SUM !== 100) {
  throw new Error(
    `rubric_v6.json: weights must sum to 100, got ${WEIGHT_SUM} ` +
    `(${JSON.stringify(RUBRIC.weights)})`
  );
}

// The composite is Sigma over these. `industries` is the rubric's weight key
// for the industry vertical; the input calls it `industry_vertical`.
const WEIGHT_KEY_TO_LEVEL_KEY = {
  industries: 'industry',
  stage_maturity: 'stage_maturity',
  revenue_range: 'revenue_range',
  company_type: 'company_type',
  geography: 'geography',
  buying_signal: 'buying_signal',
};

for (const key of Object.keys(RUBRIC.weights)) {
  if (!(key in WEIGHT_KEY_TO_LEVEL_KEY)) {
    throw new Error(`rubric_v6.json: unmapped weight key "${key}"`);
  }
}

// Components that carry weight. Used for confidence_overall (S7) so that the
// set follows the weights instead of being hardcoded here.
const WEIGHTED_COMPONENTS = Object.entries(RUBRIC.weights)
  .filter(([, w]) => w > 0)
  .map(([k]) => (k === 'industries' ? 'industry_vertical' : k));

const CONFIDENCE_RANK = { low: 0, medium: 1, high: 2 };
const VALID_LEVELS = new Set(RUBRIC.levels);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Half-up rounding to an integer, per rubric `rounding: "half_up_to_integer"`.
 *
 * Math.round alone is not enough: 74.5 arrived at by float arithmetic can be
 * 74.49999999999999, which rounds down and silently loses a grade boundary.
 * Collapsing to 10 decimal places first makes the boundary exact without
 * making 74.4 round up.
 */
export function roundHalfUp(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return null;
  const collapsed = Number(x.toFixed(10));
  return Math.floor(collapsed + 0.5);
}

/** Industry vertical -> tier -> level (S1). */
export function industryLevelFor(vertical) {
  const row = vertical === null || vertical === undefined
    ? undefined
    : RUBRIC.industry_verticals[vertical];
  if (!row) return { level: 0, tier: null, known: false };
  const level = RUBRIC.industry_vertical_map[row.tier];
  if (level === undefined) {
    throw new Error(
      `rubric_v6.json: vertical "${vertical}" has tier "${row.tier}" ` +
      `which is absent from industry_vertical_map`
    );
  }
  return { level, tier: row.tier, known: true, row };
}

/** Worst (lowest) of a list of confidence labels. */
function worstConfidence(labels) {
  let worst = 'high';
  for (const label of labels) {
    const rank = CONFIDENCE_RANK[label];
    // An absent or unrecognised confidence is treated as "low": we never let a
    // missing declaration read as a confident one.
    const effective = rank === undefined ? 'low' : label;
    if (CONFIDENCE_RANK[effective] < CONFIDENCE_RANK[worst]) worst = effective;
  }
  return worst;
}

function resolveLevel(raw) {
  if (raw === null || raw === undefined) return 0;
  if (!VALID_LEVELS.has(raw)) {
    throw new Error(
      `level ${JSON.stringify(raw)} is not one of ${JSON.stringify(RUBRIC.levels)}`
    );
  }
  return raw;
}

// ---------------------------------------------------------------------------
// score()
// ---------------------------------------------------------------------------

/**
 * Score one organization.
 *
 * @param {object} input see §5 of the build task / README
 * @returns {object} the scored result; deterministic for a given input (S10)
 */
export function score(input) {
  const flags = [];
  const levels = (input && input.levels) || {};
  const confidence = (input && input.confidence) || {};
  const missingInputs = (input && input.missing_inputs) || {};
  const factsSummary = (input && input.facts_summary) || {};

  // --- S1: industry vertical -> level -------------------------------------
  const industry = industryLevelFor(input ? input.industry_vertical : null);
  const industryLevel = industry.level;
  let industryConfidence = confidence.industry_vertical;
  if (!industry.known) {
    flags.push('unknown_vertical');
    industryConfidence = 'low';
  }

  // --- levels actually used in the composite (null -> 0, S6) -------------
  const levelsUsed = {
    industry: industryLevel,
    stage_maturity: resolveLevel(levels.stage_maturity),
    company_type: resolveLevel(levels.company_type),
    geography: resolveLevel(levels.geography),
    revenue_range: resolveLevel(levels.revenue_range),
    buying_signal: resolveLevel(levels.buying_signal),
  };

  // --- S2: composite = Sigma weight_i * level_i / 10 ----------------------
  let composite = 0;
  for (const [weightKey, weight] of Object.entries(RUBRIC.weights)) {
    const levelKey = WEIGHT_KEY_TO_LEVEL_KEY[weightKey];
    composite += (weight * levelsUsed[levelKey]) / 10;
  }
  composite = Number(composite.toFixed(10));

  // --- S3 + S9: activation state -----------------------------------------
  let activationStateUsed = input && input.activation_state
    ? input.activation_state
    : RUBRIC.activation_default_when_no_evidence;

  if (activationStateUsed === 'Contracting') {
    const age = input ? input.activation_evidence_dated_within_months : null;
    const maxAge = RUBRIC.activation_contracting_evidence_max_age_months;
    const dated = typeof age === 'number' && age <= maxAge;
    if (!dated) {
      activationStateUsed = RUBRIC.activation_default_when_no_evidence;
      flags.push('contracting_without_dated_evidence');
    }
  }

  const multiplier = RUBRIC.activation_multipliers[activationStateUsed];
  if (multiplier === undefined) {
    throw new Error(`unknown activation_state "${activationStateUsed}"`);
  }

  // --- S4: final scores ---------------------------------------------------
  const finalScore = roundHalfUp(composite * multiplier);
  const finalScoreWithoutActivation = roundHalfUp(composite);

  // --- S6: insufficient data ---------------------------------------------
  const insufficient = RUBRIC.insufficient_data_rule.components.filter((component) => {
    if (levels[component] === null || levels[component] === undefined) return true;
    const missing = missingInputs[component];
    return confidence[component] === 'low' && Array.isArray(missing) && missing.length > 0;
  });
  const status = insufficient.length > 0 ? 'insufficient_data' : 'scored';
  if (status === 'insufficient_data') {
    flags.push(`insufficient:${insufficient.join(',')}`);
  }

  // --- S5: grade ----------------------------------------------------------
  const grade = status === 'insufficient_data' ? null : gradeFor(finalScore);

  // --- S7: overall confidence over the weighted components ----------------
  const confidenceOverall = worstConfidence(
    WEIGHTED_COMPONENTS.map((component) =>
      component === 'industry_vertical' ? industryConfidence : confidence[component]
    )
  );

  // --- S8: tier 2 candidate ----------------------------------------------
  const rule = RUBRIC.tier2_flag_rule;
  const revenue = factsSummary.revenue_usd;
  const headcount = factsSummary.headcount_total;
  const tier2Candidate = Boolean(
    (typeof revenue === 'number' && revenue > rule.revenue_usd_gt) ||
    (typeof headcount === 'number' && headcount > rule.headcount_gt) ||
    levelsUsed.company_type === rule.company_type_level_eq
  );
  if (tier2Candidate) flags.push('tier2_candidate');

  return {
    model_version: RUBRIC.model_version,
    industry_level: industryLevel,
    industry_tier: industry.tier,
    levels_used: levelsUsed,
    // S12: carried through untouched. Weight is 0, so it cannot reach composite.
    buying_signal_level: levels.buying_signal === undefined ? null : levels.buying_signal,
    composite,
    activation_state_used: activationStateUsed,
    multiplier,
    final_score: finalScore,
    final_score_without_activation: finalScoreWithoutActivation,
    grade,
    status,
    confidence_overall: confidenceOverall,
    tier2_candidate: tier2Candidate,
    flags,
  };
}

/** S5: grade from a final score. Boundaries inclusive. */
export function gradeFor(finalScore) {
  if (finalScore === null) return null;
  if (finalScore >= RUBRIC.thresholds.A) return 'A';
  if (finalScore >= RUBRIC.thresholds.B) return 'B';
  return 'C';
}

/** The human-facing label ("ICP A") for a grade, or the insufficient-data label. */
export function gradeLabel(grade) {
  if (grade === null || grade === undefined) return null;
  return RUBRIC.grade_labels[grade] || null;
}

export const _internals = { WEIGHTED_COMPONENTS, WEIGHT_KEY_TO_LEVEL_KEY, worstConfidence };
