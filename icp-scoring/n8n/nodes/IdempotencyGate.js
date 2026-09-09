// IdempotencyGate — should this organization be scored at all?
//
// Skip when ALL of:
//   1. ICP Calculated already holds a real grade, and
//   2. ICP Model Version equals the current rubric version, and
//   3. ICP Scored At is younger than CONFIG.rescore_after_days.
//
// Any one failing means re-score. Emits a boolean plus the reason, so the IF
// downstream is a pure read and the reason reaches the audit row.
//
// Deviation on record (CONFIG.rescore_on_error_or_insufficient, default true):
// §8.1 says skip when ICP Calculated is PRESENT. Taken literally, an org whose
// last run errored, or came back Insufficient data, would not be looked at
// again for 180 days — a transient Clay outage would freeze an account out of
// scoring for half a year. So only a real grade (ICP A/B/C) counts as a fresh
// score. Set the flag false in CONFIG to follow §8.1 to the letter.

const cfg = $('CONFIG').item.json;
const n = $('Normalize').item.json;
const fetched = $input.first().json;
const org = fetched.data || fetched;
const custom = org.custom_fields || {};

const nowIso = cfg.now_iso;
const now = new Date(nowIso);

const rawCalculated = custom[cfg.f_icp_calculated];
const rawScoredAt = custom[cfg.f_icp_scored_at];
const rawModelVersion = custom[cfg.f_icp_model_version];
const rawScore = custom[cfg.f_icp_score];

// An enum comes back as an option id unless include_option_labels is set, so
// resolve through CONFIG's option map rather than comparing to a label.
const optionIdToLabel = {};
for (const [label, id] of Object.entries(cfg.opt_icp_calculated || {})) {
  if (id !== null && id !== undefined) optionIdToLabel[String(id)] = label;
}
const calculatedLabel = rawCalculated === null || rawCalculated === undefined
  ? null
  : (optionIdToLabel[String(rawCalculated)] || String(rawCalculated));

const gradeLabels = Object.values(cfg.grade_labels || {});
const isRealGrade = calculatedLabel !== null && gradeLabels.indexOf(calculatedLabel) !== -1;

const hasCalculated = cfg.rescore_on_error_or_insufficient
  ? isRealGrade
  : calculatedLabel !== null;

const modelMatches = String(rawModelVersion || '') === String(cfg.model_version);

let ageDays = null;
if (rawScoredAt) {
  // Pipedrive date fields come back as YYYY-MM-DD; accept a full timestamp too.
  const scoredAt = new Date(String(rawScoredAt).slice(0, 10) + 'T00:00:00Z');
  if (!isNaN(scoredAt.getTime())) {
    ageDays = Math.floor((now.getTime() - scoredAt.getTime()) / 86400000);
  }
}
const isFresh = ageDays !== null && ageDays < cfg.rescore_after_days;

const skip = Boolean(hasCalculated && modelMatches && isFresh);

let reason;
if (skip) {
  reason = `fresh: ${calculatedLabel} on model ${rawModelVersion}, scored ${ageDays}d ago ` +
           `(< ${cfg.rescore_after_days}d)`;
} else if (!hasCalculated) {
  reason = calculatedLabel === null
    ? 'never scored'
    : `previous result "${calculatedLabel}" is not a grade — re-scoring`;
} else if (!modelMatches) {
  reason = `model version "${rawModelVersion || '(none)'}" != "${cfg.model_version}" — re-scoring`;
} else if (ageDays === null) {
  reason = 'no usable ICP Scored At date — re-scoring';
} else {
  reason = `stale: scored ${ageDays}d ago (>= ${cfg.rescore_after_days}d) — re-scoring`;
}

return [{
  json: {
    skip,
    reason,
    request_id: n.request_id,
    org_id: n.org_id,
    deal_id: n.deal_id,

    org_name: org.name || null,
    org_website: org.website || null,
    org_linkedin: org.linkedin || null,
    org_country: (org.address && org.address.country) || null,
    org_state: (org.address && org.address.admin_area_level_1) || null,

    existing: {
      calculated_option_id: rawCalculated === undefined ? null : rawCalculated,
      calculated_label: calculatedLabel,
      score: rawScore === undefined ? null : rawScore,
      scored_at: rawScoredAt || null,
      model_version: rawModelVersion || null,
      age_days: ageDays,
    },
  },
}];
