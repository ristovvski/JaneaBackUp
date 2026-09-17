// engine/validate_event.mjs — the v6 Path B boundary check.
//
// v6 splits the work cleanly: the table classifies and enriches, n8n scores.
// So this file no longer validates anybody's arithmetic — there is no score in
// the event to check. What it does is refuse a payload the Score node could
// only guess at, and refuse it loudly: every problem is listed at once, so a
// table that is wrong in four places is fixed in one pass rather than four.
//
// Mirrors engine/schemas/icp_scored_event.schema.json. The schema is the
// contract a reviewer reads; this is the same constraints as code, because an
// n8n Code node cannot load ajv.
//
// NO IMPORTS. Spliced verbatim into the ParseScored Code node by
// scripts/gen_nodes.mjs, which strips the `export` keywords.

export const STATES = ['Accelerating', 'Transitioning', 'Stable', 'Contracting'];
export const CONFIDENCES = ['high', 'medium', 'low'];
export const IDENTIFIER_KINDS = ['domain', 'linkedin', 'name'];

export const REQUIRED_TOP = [
  'request_id', 'org_id', 'requested_at', 'identifier_kind', 'identifier_value',
  'resolved', 'cls_all', 'apollo_summary', 'model_version',
];

// Present or absent, both fine, and ignored either way.
export const IGNORED_TOP = ['event', 'event_id', 'emitted_at', 'clay_table', 'clay_row_url'];

export const RESOLVED_KEYS = ['domain', 'linkedin_url', 'website'];

export const HIRING_KEYS = [
  'total_open', 'eng_open', 'eng_open_60d_plus', 'dates_available',
  'leader_titles', 'eng_titles_with_days', 'eng_open_ratio', 'eng_headcount',
];

export const APOLLO_KEYS = [
  'employees', 'eng_headcount', 'country', 'state', 'founded_year',
  'last_round_date', 'headcount_6mo_growth', 'headcount_12mo_growth',
  'publicly_traded_symbol', 'owned_by_organization_id',
];

// Every component, and which of confidence / missing_inputs it must carry.
// geography and buying_signal are shown in the task without them; accepting
// either shape costs nothing, and rejecting a run because a sibling key
// travelled would cost a score.
export const COMPONENTS = [
  { name: 'industry_vertical', valueKey: 'value', requires: ['confidence', 'missing_inputs'] },
  { name: 'company_type', valueKey: 'level', requires: ['confidence', 'missing_inputs'] },
  { name: 'stage_maturity', valueKey: 'level', requires: ['confidence', 'missing_inputs'] },
  { name: 'activation_state', valueKey: 'value', requires: ['confidence', 'missing_inputs'], extra: ['activation_evidence_dated'] },
  { name: 'geography', valueKey: 'level', requires: [] },
  { name: 'revenue_range', valueKey: 'level', requires: ['confidence', 'missing_inputs'], extra: ['revenue_band_used', 'revenue_source'] },
  { name: 'buying_signal', valueKey: 'level', requires: [] },
];

export function validateEvent(raw, cfg) {
  const problems = [];
  const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const isStringOrNull = (v) => v === null || typeof v === 'string';
  const isIntOrNull = (v) => v === null || Number.isInteger(v);
  const isNumberOrNull = (v) => v === null || (typeof v === 'number' && !Number.isNaN(v));
  const isBoolOrNull = (v) => v === null || typeof v === 'boolean';
  const isStringArray = (v) => Array.isArray(v) && v.every((x) => typeof x === 'string');
  const levels = cfg.levels || [0, 3, 7, 10];
  const isLevelOrNull = (v) => v === null || levels.indexOf(v) !== -1;

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
  // Numeric, as Pipedrive has it and as Path A sends it. A quoted id is not
  // "close enough": the audit table's columns are typed, and a column that is
  // sometimes 2695 and sometimes "2695" joins against nothing.
  if (!Number.isInteger(raw.org_id) || raw.org_id < 1) problems.push(`org_id must be a positive integer, got ${JSON.stringify(raw.org_id)}`);
  if (raw.deal_id !== undefined && !isIntOrNull(raw.deal_id)) problems.push(`deal_id must be an integer or null, got ${JSON.stringify(raw.deal_id)}`);
  if (typeof raw.requested_at !== 'string' || raw.requested_at.length < 10) problems.push('requested_at must be an ISO timestamp');
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
  if (!isObject(cls)) {
    problems.push('cls_all must be an object');
  } else {
    const known = COMPONENTS.map((c) => c.name).concat(['engineering_hiring', 'conflict_note']);
    for (const key of Object.keys(cls)) {
      if (known.indexOf(key) === -1) problems.push(`cls_all has an unknown key "${key}"`);
    }

    const hiring = cls.engineering_hiring;
    if (!isObject(hiring)) {
      problems.push('cls_all.engineering_hiring must be an object');
    } else {
      const SHAPE = {
        total_open: isIntOrNull, eng_open: isIntOrNull, eng_open_60d_plus: isIntOrNull,
        dates_available: isBoolOrNull, leader_titles: isStringArray,
        eng_titles_with_days: isStringArray, eng_open_ratio: isNumberOrNull,
        eng_headcount: isIntOrNull,
      };
      for (const key of HIRING_KEYS) {
        if (!Object.prototype.hasOwnProperty.call(hiring, key)) problems.push(`cls_all.engineering_hiring.${key} is missing`);
        else if (!SHAPE[key](hiring[key])) problems.push(`cls_all.engineering_hiring.${key} has the wrong type`);
      }
      for (const key of Object.keys(hiring)) {
        if (HIRING_KEYS.indexOf(key) === -1) problems.push(`cls_all.engineering_hiring has an unknown key "${key}"`);
      }
    }

    for (const spec of COMPONENTS) {
      const c = cls[spec.name];
      if (!isObject(c)) { problems.push(`cls_all.${spec.name} must be an object`); continue; }

      if (!Object.prototype.hasOwnProperty.call(c, spec.valueKey)) {
        problems.push(`cls_all.${spec.name}.${spec.valueKey} is missing`);
      } else if (spec.valueKey === 'level') {
        if (!isLevelOrNull(c.level)) problems.push(`cls_all.${spec.name}.level must be null or one of ${JSON.stringify(levels)}, got ${JSON.stringify(c.level)}`);
      } else if (spec.name === 'industry_vertical') {
        if (!isStringOrNull(c.value)) problems.push('cls_all.industry_vertical.value must be a string or null');
      } else if (c.value !== null && STATES.indexOf(c.value) === -1) {
        problems.push(`cls_all.activation_state.value must be null or one of ${JSON.stringify(STATES)}`);
      }

      if (!Array.isArray(c.evidence)) problems.push(`cls_all.${spec.name}.evidence must be an array`);
      else if (!isStringArray(c.evidence)) problems.push(`cls_all.${spec.name}.evidence must contain strings only`);
      else if (c.evidence.length > 20) problems.push(`cls_all.${spec.name}.evidence has more than 20 items`);

      for (const key of spec.requires) {
        if (!Object.prototype.hasOwnProperty.call(c, key)) problems.push(`cls_all.${spec.name}.${key} is missing`);
      }
      if (c.confidence !== undefined && CONFIDENCES.indexOf(c.confidence) === -1) {
        problems.push(`cls_all.${spec.name}.confidence must be one of ${JSON.stringify(CONFIDENCES)}`);
      }
      if (c.missing_inputs !== undefined && !isStringArray(c.missing_inputs)) {
        problems.push(`cls_all.${spec.name}.missing_inputs must be an array of strings`);
      }
      if (spec.name === 'activation_state' && c.activation_evidence_dated !== undefined && !isStringOrNull(c.activation_evidence_dated)) {
        problems.push('cls_all.activation_state.activation_evidence_dated must be a citation string or null');
      }
      if (spec.name === 'revenue_range') {
        for (const key of ['revenue_band_used', 'revenue_source']) {
          if (!Object.prototype.hasOwnProperty.call(c, key)) problems.push(`cls_all.revenue_range.${key} is missing`);
          else if (!isStringOrNull(c[key])) problems.push(`cls_all.revenue_range.${key} must be a string or null`);
        }
      }

      const allowedKeys = ['evidence', spec.valueKey].concat(spec.requires, spec.extra || [], ['confidence', 'missing_inputs']);
      for (const key of Object.keys(c)) {
        if (allowedKeys.indexOf(key) === -1) problems.push(`cls_all.${spec.name} has an unknown key "${key}"`);
      }
    }

    if (cls.conflict_note !== undefined && !isStringOrNull(cls.conflict_note)) {
      problems.push('cls_all.conflict_note must be a string or null');
    }
  }

  // --- apollo_summary ----------------------------------------------------
  const APOLLO_SHAPE = {
    employees: isIntOrNull, eng_headcount: isIntOrNull, country: isStringOrNull,
    state: isStringOrNull, founded_year: isIntOrNull, last_round_date: isStringOrNull,
    headcount_6mo_growth: isNumberOrNull, headcount_12mo_growth: isNumberOrNull,
    publicly_traded_symbol: isStringOrNull,
    owned_by_organization_id: (v) => v === null || typeof v === 'string' || Number.isInteger(v),
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

  return problems;
}
