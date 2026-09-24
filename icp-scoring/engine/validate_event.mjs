// engine/validate_event.mjs — Path B's boundary check.
//
// THE TABLE SCORES. n8n writes.
//
// v6.0 split it the other way: the table classified, n8n held the rubric and
// produced the grade. That is reversed here by the owner's ruling. The Clay
// table already computes `final`, `grade` and the whole note, and running a
// second rubric in n8n to agree with it was two implementations pretending to
// be one. So this file validates a SCORED event: a grade, a status, a note,
// and the working shown as optional detail.
//
// What that costs, stated rather than discovered: nothing in n8n now checks
// the arithmetic, and nothing catches a vertical name the table spells
// differently from the rubric. `SaaS - Other` with a hyphen scored 7 in Clay
// and would have scored 0 here; with n8n out of the scoring business, only
// Clay's own map decides. That is the trade the ruling makes, and the note the
// rep reads is the table's note, verbatim.
//
// Mirrors engine/schemas/icp_scored_event.schema.json. The schema is the
// contract a reviewer reads; this is the same constraints as code, because an
// n8n Code node cannot load ajv.
//
// NO IMPORTS. Spliced verbatim into the ParseScored Code node by
// scripts/gen_nodes.mjs, which strips the `export` keywords.

export const GRADES = ['A', 'B', 'C'];
export const STATUSES = ['scored', 'insufficient_data'];
export const CONFIDENCES = ['high', 'medium', 'low'];
export const STATES = ['Accelerating', 'Transitioning', 'Stable', 'Contracting'];

// What a write cannot happen without.
export const REQUIRED_TOP = [
  'request_id', 'org_id', 'deal_id', 'requested_at',
  'final', 'grade', 'status', 'note',
];

// The working. Carried into the run summary, never into a decision.
export const OPTIONAL_TOP = [
  'composite', 'multiplier', 'final_without_activation',
  'industry_level', 'stage_level', 'type_level', 'geo_level', 'revenue_level',
  'activation_used', 'confidence_overall', 'tier2_candidate', 'flags',
];

// additionalProperties: false over exactly REQUIRED_TOP + OPTIONAL_TOP. A
// column the table starts sending that this list does not name is a contract
// change, and a contract change should be loud rather than silently ignored.
export const ALLOWED_TOP = REQUIRED_TOP.concat(OPTIONAL_TOP);

export const LEVEL_KEYS = [
  'industry_level', 'stage_level', 'type_level', 'geo_level', 'revenue_level',
];

export function validateEvent(raw, cfg) {
  const problems = [];
  const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const isIntOrNull = (v) => v === null || Number.isInteger(v);
  const isNumberOrNull = (v) => v === null || (typeof v === 'number' && !Number.isNaN(v));
  const isStringArray = (v) => Array.isArray(v) && v.every((x) => typeof x === 'string');
  const levels = (cfg && cfg.levels) || [0, 3, 7, 10];

  if (!isObject(raw)) return ['the body is not an object'];

  // --- presence -----------------------------------------------------------
  for (const key of REQUIRED_TOP) {
    if (!Object.prototype.hasOwnProperty.call(raw, key)) problems.push(`missing "${key}"`);
  }
  for (const key of Object.keys(raw)) {
    if (ALLOWED_TOP.indexOf(key) === -1) problems.push(`unknown top-level key "${key}"`);
  }

  // --- identity -----------------------------------------------------------
  if (typeof raw.request_id !== 'string' || raw.request_id === '') {
    problems.push('request_id must be a non-empty string');
  }
  // Numeric, as Pipedrive has it and as Path A sent it. A quoted id is not
  // "close enough": org_id becomes a URL path segment on the PATCH.
  if (!Number.isInteger(raw.org_id) || raw.org_id < 1) {
    problems.push(`org_id must be a positive integer, got ${JSON.stringify(raw.org_id)}`);
  }
  // Present always; null is legal, because a re-score can happen outside a
  // deal and rejecting that would be rejecting a correct run.
  if (!isIntOrNull(raw.deal_id)) {
    problems.push(`deal_id must be an integer or null, got ${JSON.stringify(raw.deal_id)}`);
  }
  if (typeof raw.requested_at !== 'string' || raw.requested_at.length < 10) {
    problems.push('requested_at must be an ISO timestamp');
  }

  // --- the grade ----------------------------------------------------------
  if (STATUSES.indexOf(raw.status) === -1) {
    problems.push(`status must be one of ${JSON.stringify(STATUSES)}, got ${JSON.stringify(raw.status)}`);
  }
  if (!(raw.final === null || (Number.isInteger(raw.final) && raw.final >= 0 && raw.final <= 100))) {
    problems.push(`final must be an integer 0-100 or null, got ${JSON.stringify(raw.final)}`);
  }
  if (!(raw.grade === null || GRADES.indexOf(raw.grade) !== -1)) {
    problems.push(`grade must be one of ${JSON.stringify(GRADES)} or null, got ${JSON.stringify(raw.grade)}`);
  }
  // The one cross-field rule, and the reason it exists: "scored" with no grade
  // would be written to the organization as a grade-shaped blank, which is the
  // single worst thing this workflow could put in front of a rep.
  if (raw.status === 'scored' && (raw.final === null || raw.grade === null)) {
    problems.push('status is "scored" but final or grade is null — there is nothing to write');
  }

  // --- the note -----------------------------------------------------------
  // Written to the activity VERBATIM, so it is the one field a human actually
  // reads. Empty is a failure, not an empty note.
  if (typeof raw.note !== 'string' || raw.note.trim() === '') {
    problems.push('note must be a non-empty string — it is written to the activity verbatim');
  }

  // --- the working (optional, typed when present) -------------------------
  if (raw.composite !== undefined && !isNumberOrNull(raw.composite)) {
    problems.push('composite must be a number or null');
  }
  if (raw.final_without_activation !== undefined && !isNumberOrNull(raw.final_without_activation)) {
    problems.push('final_without_activation must be a number or null');
  }
  if (raw.multiplier !== undefined && !isNumberOrNull(raw.multiplier)) {
    problems.push('multiplier must be a number or null');
  }
  for (const key of LEVEL_KEYS) {
    if (raw[key] === undefined) continue;
    if (!(raw[key] === null || levels.indexOf(raw[key]) !== -1)) {
      problems.push(`${key} must be null or one of ${JSON.stringify(levels)}, got ${JSON.stringify(raw[key])}`);
    }
  }
  if (raw.activation_used !== undefined
    && !(raw.activation_used === null || STATES.indexOf(raw.activation_used) !== -1)) {
    problems.push(`activation_used must be null or one of ${JSON.stringify(STATES)}`);
  }
  if (raw.confidence_overall !== undefined
    && !(raw.confidence_overall === null || CONFIDENCES.indexOf(raw.confidence_overall) !== -1)) {
    problems.push(`confidence_overall must be null or one of ${JSON.stringify(CONFIDENCES)}`);
  }
  if (raw.tier2_candidate !== undefined
    && !(raw.tier2_candidate === null || typeof raw.tier2_candidate === 'boolean')) {
    problems.push('tier2_candidate must be a boolean or null');
  }
  if (raw.flags !== undefined && !(raw.flags === null || isStringArray(raw.flags))) {
    problems.push('flags must be an array of strings or null');
  }

  return problems;
}
