// engine/validate_event.mjs — the v6 Path B boundary check.
//
// v5 had n8n re-derive the score from seven classifier objects and flag a
// disagreement with Clay. v6 cannot work that way: geography, revenue_range
// and buying_signal are levelled inside the table and arrive already scored,
// so there is nothing left for n8n to derive them from. The posture changes
// accordingly — n8n VALIDATES the posted score and REJECTS the event on a
// mismatch. It never substitutes a number of its own.
//
// Three kinds of check, all of them answerable from the payload alone:
//
//   shape       every required key present, every enum in range
//   arithmetic  weights sum to 100; composite is the weighted sum of the
//               posted levels; the multiplier is the one the rubric assigns to
//               the activation state used; both finals are the posted
//               composite rounded half-up; the grade is what the thresholds
//               say about the final score
//   coherence   the levels inside `score` agree with the classifier objects
//               they came from, and the industry level agrees with the
//               vertical's tier
//
// Two fields are taken on trust because the payload does not carry what would
// be needed to check them: `confidence_overall` (the table sees per-source
// confidences n8n never receives) and `tier2_candidate` (the rule reads a
// revenue NUMBER, and v6 sends a band string).
//
// NO IMPORTS. This file is spliced verbatim into the ParseScored Code node by
// scripts/gen_nodes.mjs, which strips the `export` keywords — an n8n Code node
// cannot import, and a hand-maintained second copy of this logic is exactly
// the drift that ships wrong grades.

export const STATES = ['Accelerating', 'Transitioning', 'Stable', 'Contracting'];
export const CONFIDENCES = ['high', 'medium', 'low'];
export const IDENTIFIER_KINDS = ['domain', 'linkedin', 'name'];

export const CLS_LEVELLED = ['company_type', 'stage_maturity'];

export const JOBS_KEYS = [
  'eng_open', 'eng_open_60d_plus', 'has_eng_leader', 'eng_leader_titles',
  'eng_open_ratio', 'eng_headcount', 'dates_available', 'eng_titles', 'as_of',
];

export const APOLLO_KEYS = [
  'employees', 'eng_headcount', 'country', 'state', 'founded_year',
  'last_round_date', 'revenue_band_used', 'revenue_source',
];

export const RESOLVED_KEYS = ['domain', 'linkedin_url', 'website'];

export const SCORE_LEVEL_KEYS = [
  'industries', 'stage_maturity', 'company_type',
  'geography', 'revenue_range', 'buying_signal',
];

// Keys that may appear and are ignored. They carry no scoring weight, so
// neither their presence nor their absence is a contract break.
export const IGNORED_TOP = ['event', 'event_id', 'emitted_at', 'clay_table', 'clay_row_url'];

export const REQUIRED_TOP = [
  'request_id', 'org_id', 'identifier_kind', 'identifier_value',
  'resolved', 'cls_all', 'jobs', 'score', 'apollo_summary', 'model_version',
];

/** Half-up rounding to an integer. Mirrors engine/scoring.mjs; parity-tested. */
export function roundHalfUp(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return null;
  const collapsed = Number(x.toFixed(10));
  return Math.floor(collapsed + 0.5);
}

/** Grade from a final score and the rubric thresholds. Boundaries inclusive. */
export function gradeFor(finalScore, thresholds) {
  if (finalScore === null || finalScore === undefined) return null;
  if (finalScore >= thresholds.A) return 'A';
  if (finalScore >= thresholds.B) return 'B';
  return 'C';
}

/**
 * Validate one v6 icp.scored event against the rubric carried in CONFIG.
 *
 * @param {object} raw the POSTed body
 * @param {object} cfg the CONFIG node's json
 * @returns {string[]} every problem found, in reading order. Empty means the
 *   event may be written. The caller throws; this function never does, so that
 *   one malformed field does not hide the other nine.
 */
export function validateEvent(raw, cfg) {
  const problems = [];
  const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const isStringOrNull = (v) => v === null || typeof v === 'string';
  const isIntOrNull = (v) => v === null || Number.isInteger(v);
  const isNumberOrNull = (v) => v === null || (typeof v === 'number' && !Number.isNaN(v));
  const isBoolOrNull = (v) => v === null || typeof v === 'boolean';
  const isStringArray = (v) => Array.isArray(v) && v.every((x) => typeof x === 'string');
  const levels = cfg.levels || [0, 3, 7, 10];
  const isLevel = (v) => levels.indexOf(v) !== -1;

  if (!isObject(raw)) return ['the body is not an object'];

  // --- top level ---------------------------------------------------------
  for (const key of REQUIRED_TOP) {
    if (!Object.prototype.hasOwnProperty.call(raw, key)) problems.push(`missing "${key}"`);
  }
  const allowed = REQUIRED_TOP.concat(IGNORED_TOP, ['deal_id']);
  for (const key of Object.keys(raw)) {
    if (allowed.indexOf(key) === -1) problems.push(`unknown top-level key "${key}"`);
  }

  if (typeof raw.request_id !== 'string' || raw.request_id === '') problems.push('request_id must be a non-empty string');
  if (typeof raw.org_id !== 'string' || raw.org_id === '') problems.push('org_id must be a non-empty string');
  if (raw.deal_id !== undefined && !isStringOrNull(raw.deal_id)) problems.push('deal_id must be a string or null');
  if (IDENTIFIER_KINDS.indexOf(raw.identifier_kind) === -1) problems.push(`identifier_kind must be one of ${JSON.stringify(IDENTIFIER_KINDS)}`);
  if (typeof raw.identifier_value !== 'string' || raw.identifier_value === '') problems.push('identifier_value must be a non-empty string');
  if (raw.model_version !== cfg.model_version) problems.push(`model_version must be "${cfg.model_version}", got ${JSON.stringify(raw.model_version)}`);

  // --- resolved ----------------------------------------------------------
  if (!isObject(raw.resolved)) {
    problems.push('resolved must be an object');
  } else {
    for (const key of RESOLVED_KEYS) {
      if (!Object.prototype.hasOwnProperty.call(raw.resolved, key)) problems.push(`resolved.${key} is missing`);
      else if (!isStringOrNull(raw.resolved[key])) problems.push(`resolved.${key} must be a string or null`);
    }
    for (const key of Object.keys(raw.resolved)) {
      if (RESOLVED_KEYS.indexOf(key) === -1) problems.push(`resolved has an unknown key "${key}"`);
    }
  }

  // --- cls_all -----------------------------------------------------------
  const cls = raw.cls_all;
  const checkCommon = (name, c) => {
    if (!Array.isArray(c.evidence)) problems.push(`cls_all.${name}.evidence must be an array`);
    else if (!isStringArray(c.evidence)) problems.push(`cls_all.${name}.evidence must contain strings only`);
    else if (c.evidence.length > 20) problems.push(`cls_all.${name}.evidence has more than 20 items`);
    if (CONFIDENCES.indexOf(c.confidence) === -1) problems.push(`cls_all.${name}.confidence must be one of ${JSON.stringify(CONFIDENCES)}`);
    if (!Array.isArray(c.missing_inputs)) problems.push(`cls_all.${name}.missing_inputs must be an array`);
  };

  if (!isObject(cls)) {
    problems.push('cls_all must be an object');
  } else {
    const known = ['industry_vertical', 'company_type', 'stage_maturity', 'activation_state', 'conflict_note'];
    for (const key of Object.keys(cls)) {
      if (known.indexOf(key) === -1) problems.push(`cls_all has an unknown key "${key}"`);
    }

    if (!isObject(cls.industry_vertical)) {
      problems.push('cls_all.industry_vertical must be an object');
    } else {
      if (!isStringOrNull(cls.industry_vertical.value)) problems.push('cls_all.industry_vertical.value must be a string or null');
      checkCommon('industry_vertical', cls.industry_vertical);
    }

    for (const name of CLS_LEVELLED) {
      const c = cls[name];
      if (!isObject(c)) { problems.push(`cls_all.${name} must be an object`); continue; }
      if (c.level !== null && !isLevel(c.level)) problems.push(`cls_all.${name}.level must be null or one of ${JSON.stringify(levels)}`);
      checkCommon(name, c);
    }

    const act = cls.activation_state;
    if (!isObject(act)) {
      problems.push('cls_all.activation_state must be an object');
    } else {
      if (act.value !== null && STATES.indexOf(act.value) === -1) problems.push(`cls_all.activation_state.value must be null or one of ${JSON.stringify(STATES)}`);
      if (act.activation_evidence_dated !== undefined && !isBoolOrNull(act.activation_evidence_dated)) {
        problems.push('cls_all.activation_state.activation_evidence_dated must be a boolean or null');
      }
      checkCommon('activation_state', act);
    }

    if (cls.conflict_note !== undefined && !isStringOrNull(cls.conflict_note)) problems.push('cls_all.conflict_note must be a string or null');
  }

  // --- jobs and apollo_summary -------------------------------------------
  const JOB_SHAPE = {
    eng_open: isIntOrNull, eng_open_60d_plus: isIntOrNull, has_eng_leader: isBoolOrNull,
    eng_leader_titles: isStringArray, eng_open_ratio: isNumberOrNull, eng_headcount: isIntOrNull,
    dates_available: isBoolOrNull, eng_titles: isStringArray, as_of: isStringOrNull,
  };
  if (!isObject(raw.jobs)) {
    problems.push('jobs must be an object');
  } else {
    for (const key of JOBS_KEYS) {
      if (!Object.prototype.hasOwnProperty.call(raw.jobs, key)) problems.push(`jobs.${key} is missing`);
      else if (!JOB_SHAPE[key](raw.jobs[key])) problems.push(`jobs.${key} has the wrong type`);
    }
    for (const key of Object.keys(raw.jobs)) {
      if (JOBS_KEYS.indexOf(key) === -1) problems.push(`jobs has an unknown key "${key}"`);
    }
  }

  const APOLLO_SHAPE = {
    employees: isIntOrNull, eng_headcount: isIntOrNull, country: isStringOrNull,
    state: isStringOrNull, founded_year: isIntOrNull, last_round_date: isStringOrNull,
    revenue_band_used: isStringOrNull, revenue_source: isStringOrNull,
  };
  if (!isObject(raw.apollo_summary)) {
    problems.push('apollo_summary must be an object');
  } else {
    for (const key of APOLLO_KEYS) {
      if (!Object.prototype.hasOwnProperty.call(raw.apollo_summary, key)) problems.push(`apollo_summary.${key} is missing`);
      else if (!APOLLO_SHAPE[key](raw.apollo_summary[key])) problems.push(`apollo_summary.${key} has the wrong type`);
    }
    for (const key of Object.keys(raw.apollo_summary)) {
      if (APOLLO_KEYS.indexOf(key) === -1) problems.push(`apollo_summary has an unknown key "${key}"`);
    }
  }

  // --- score: shape -------------------------------------------------------
  const score = raw.score;
  if (!isObject(score)) {
    problems.push('score must be an object');
    return problems; // nothing below can be checked without it
  }

  const SCORE_KEYS = [
    'levels', 'composite', 'activation_state_used', 'multiplier', 'final_score',
    'final_score_without_activation', 'grade', 'status', 'confidence_overall',
    'tier2_candidate', 'flags',
  ];
  for (const key of SCORE_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(score, key)) problems.push(`score.${key} is missing`);
  }
  for (const key of Object.keys(score)) {
    if (SCORE_KEYS.indexOf(key) === -1) problems.push(`score has an unknown key "${key}"`);
  }

  if (!isObject(score.levels)) {
    problems.push('score.levels must be an object');
  } else {
    for (const key of SCORE_LEVEL_KEYS) {
      if (!isLevel(score.levels[key])) problems.push(`score.levels.${key} must be one of ${JSON.stringify(levels)}, got ${JSON.stringify(score.levels[key])}`);
    }
    for (const key of Object.keys(score.levels)) {
      if (SCORE_LEVEL_KEYS.indexOf(key) === -1) problems.push(`score.levels has an unknown key "${key}"`);
    }
  }

  if (typeof score.composite !== 'number' || score.composite < 0 || score.composite > 100) problems.push('score.composite must be a number in 0..100');
  if (STATES.indexOf(score.activation_state_used) === -1) problems.push(`score.activation_state_used must be one of ${JSON.stringify(STATES)}`);
  // Checked here as well as in the arithmetic phase below, which the shape
  // phase short-circuits: a multiplier of 0.5 is nonsense on its own terms and
  // should be named even when something else is also wrong.
  const knownMultipliers = Object.keys(cfg.activation_multipliers || {}).map((k) => cfg.activation_multipliers[k]);
  if (knownMultipliers.indexOf(score.multiplier) === -1) problems.push(`score.multiplier must be one of ${JSON.stringify(knownMultipliers)}, got ${JSON.stringify(score.multiplier)}`);
  for (const key of ['final_score', 'final_score_without_activation']) {
    if (!Number.isInteger(score[key]) || score[key] < 0 || score[key] > 100) problems.push(`score.${key} must be an integer in 0..100`);
  }
  if (['scored', 'insufficient_data'].indexOf(score.status) === -1) problems.push('score.status must be "scored" or "insufficient_data"');
  if (CONFIDENCES.indexOf(score.confidence_overall) === -1) problems.push(`score.confidence_overall must be one of ${JSON.stringify(CONFIDENCES)}`);
  if (typeof score.tier2_candidate !== 'boolean') problems.push('score.tier2_candidate must be a boolean');
  if (!isStringArray(score.flags)) problems.push('score.flags must be an array of strings');
  if (score.status === 'insufficient_data' && score.grade !== null) problems.push('score.grade must be null when status is insufficient_data');
  if (score.status === 'scored' && ['A', 'B', 'C'].indexOf(score.grade) === -1) problems.push('score.grade must be A, B or C when status is scored');

  // Nothing below can be trusted if the shape is already wrong: an arithmetic
  // complaint computed from a malformed level is noise on top of the real
  // problem.
  if (problems.length > 0) return problems;

  // --- score: arithmetic --------------------------------------------------
  const weights = cfg.weights || {};
  const weightSum = Object.keys(weights).reduce((a, k) => a + weights[k], 0);
  if (weightSum !== 100) {
    problems.push(`CONFIG.weights must sum to 100, got ${weightSum} — the rubric in CONFIG is broken, not the event`);
    return problems;
  }

  let composite = 0;
  for (const key of Object.keys(weights)) {
    if (SCORE_LEVEL_KEYS.indexOf(key) === -1) {
      problems.push(`CONFIG.weights has key "${key}" with no matching score.levels entry`);
      return problems;
    }
    composite += (weights[key] * score.levels[key]) / 10;
  }
  composite = Number(composite.toFixed(10));
  if (composite !== Number(Number(score.composite).toFixed(10))) {
    problems.push(`score.composite is ${score.composite}, but the posted levels weigh ${composite}`);
  }

  const expectedMultiplier = (cfg.activation_multipliers || {})[score.activation_state_used];
  if (expectedMultiplier === undefined) {
    problems.push(`CONFIG.activation_multipliers has no entry for "${score.activation_state_used}"`);
  } else if (Number(score.multiplier) !== Number(expectedMultiplier)) {
    problems.push(`score.multiplier is ${score.multiplier}, but the rubric gives ${score.activation_state_used} a multiplier of ${expectedMultiplier}`);
  }

  const expectedWithout = roundHalfUp(score.composite);
  if (score.final_score_without_activation !== expectedWithout) {
    problems.push(`score.final_score_without_activation is ${score.final_score_without_activation}, but composite ${score.composite} rounds to ${expectedWithout}`);
  }
  if (expectedMultiplier !== undefined) {
    const expectedFinal = roundHalfUp(score.composite * Number(score.multiplier));
    if (score.final_score !== expectedFinal) {
      problems.push(`score.final_score is ${score.final_score}, but ${score.composite} x ${score.multiplier} rounds to ${expectedFinal}`);
    }
  }

  if (score.status === 'scored') {
    const expectedGrade = gradeFor(score.final_score, cfg.thresholds);
    if (score.grade !== expectedGrade) {
      problems.push(`score.grade is ${JSON.stringify(score.grade)}, but a final score of ${score.final_score} is ${expectedGrade} at thresholds A>=${cfg.thresholds.A} B>=${cfg.thresholds.B}`);
    }
  }

  // --- coherence between cls_all and score.levels -------------------------
  // A level inside `score` that disagrees with the classifier it came from
  // means the note and the score would tell a rep two different stories.
  const levelOf = (c) => (c && c.level !== null && c.level !== undefined ? c.level : 0);
  for (const name of CLS_LEVELLED) {
    if (score.levels[name] !== levelOf(cls[name])) {
      problems.push(`score.levels.${name} is ${score.levels[name]}, but cls_all.${name}.level is ${JSON.stringify(cls[name].level)}`);
    }
  }

  const vertical = cls.industry_vertical.value;
  const verticalLevel = (cfg.vertical_level || {})[vertical];
  if (vertical === null || verticalLevel === undefined) {
    // The rubric's unknown-vertical rule: level 0 and say so out loud.
    if (score.levels.industries !== 0) {
      problems.push(`industry vertical ${JSON.stringify(vertical)} is not in the rubric, so score.levels.industries must be 0, got ${score.levels.industries}`);
    }
    if (score.flags.indexOf('unknown_vertical') === -1) {
      problems.push(`industry vertical ${JSON.stringify(vertical)} is not in the rubric, so score.flags must contain "unknown_vertical"`);
    }
  } else if (score.levels.industries !== verticalLevel) {
    problems.push(`score.levels.industries is ${score.levels.industries}, but the rubric puts "${vertical}" at ${verticalLevel}`);
  }

  // The activation state the score used must be the one the rubric allows for
  // what the classifier found: an undated Contracting is downgraded, and a
  // state the classifier could not determine falls back to the default.
  const act = cls.activation_state;
  let expectedState = act.value === null || act.value === undefined ? cfg.activation_default : act.value;
  let expectDowngradeFlag = false;
  if (expectedState === 'Contracting' && act.activation_evidence_dated !== true) {
    expectedState = cfg.activation_default;
    expectDowngradeFlag = true;
  }
  if (score.activation_state_used !== expectedState) {
    problems.push(`score.activation_state_used is "${score.activation_state_used}", but cls_all.activation_state gives "${expectedState}"`);
  }
  if (expectDowngradeFlag && score.flags.indexOf('contracting_without_dated_evidence') === -1) {
    problems.push('Contracting was claimed without dated evidence, so score.flags must contain "contracting_without_dated_evidence"');
  }

  return problems;
}
