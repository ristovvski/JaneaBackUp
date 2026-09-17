// IdempotencyGate — should this organization be scored at all?
//
// Skip when ALL THREE hold:
//
//   1. Auto-ICP Score holds a real grade — "93 - A", matched on shape. A run
//      that came back "n/a - insufficient data" is NOT a score: it says the
//      enrichment found too little, and freezing an account out for six months
//      because of that would be the wrong lesson to draw from it.
//   2. Auto-ICP Scored At is younger than CONFIG.rescore_after_days.
//   3. Auto-ICP Scored At is on or after CONFIG.model_effective_date.
//
// Rule 3 is how "was this scored under the current rubric?" is answered with a
// date field instead of a version field. Nothing on the organization stores a
// model version any more — the field that did was deleted — and the question
// still has to be answerable, so bumping the rubric means bumping its
// effective date, and every organization re-scores on its next trigger. The
// cost, stated rather than discovered: an org scored the same day a rubric
// ships is not re-scored by rule 3 alone, and waits for rule 2.
//
// Any one failing means re-score, and a re-score overwrites BOTH fields.

const cfg = $('CONFIG').item.json;
const n = $('Normalize').item.json;
const fetched = $input.first().json;
const org = fetched.data || fetched;
const custom = org.custom_fields || {};

const rawAutoScore = custom[cfg.f_auto_icp_score];
const rawScoredAt = custom[cfg.f_auto_icp_scored_at];
const autoScore = rawAutoScore === null || rawAutoScore === undefined
  ? null
  : String(rawAutoScore).trim();

// "93 - A" is a grade. "n/a - insufficient data" and "n/a - error" are not.
const GRADE_PATTERN = /^\s*\d{1,3}\s*-\s*[ABC]\s*$/;
const isRealGrade = autoScore !== null && autoScore !== '' && GRADE_PATTERN.test(autoScore);

const hasScore = cfg.rescore_on_error_or_insufficient
  ? isRealGrade
  : autoScore !== null && autoScore !== '';

// Pipedrive dates come back as YYYY-MM-DD; a full timestamp is accepted too.
const scoredAtDay = rawScoredAt ? String(rawScoredAt).slice(0, 10) : null;
let ageDays = null;
if (scoredAtDay && /^\d{4}-\d{2}-\d{2}$/.test(scoredAtDay)) {
  const then = Date.parse(`${scoredAtDay}T00:00:00Z`);
  const now = Date.parse(`${String(cfg.now_iso).slice(0, 10)}T00:00:00Z`);
  if (!Number.isNaN(then) && !Number.isNaN(now)) ageDays = Math.floor((now - then) / 86400000);
}
const isFresh = ageDays !== null && ageDays < cfg.rescore_after_days;

// A string comparison is the right one here: both sides are YYYY-MM-DD, which
// sorts lexicographically, and it cannot be thrown by a timezone.
const currentModel = scoredAtDay !== null && cfg.model_effective_date
  ? scoredAtDay >= String(cfg.model_effective_date).slice(0, 10)
  : false;

const skip = Boolean(hasScore && isFresh && currentModel);

let reason;
if (skip) {
  reason = `fresh: "${autoScore}" scored ${ageDays}d ago (< ${cfg.rescore_after_days}d), ` +
           `on or after the ${cfg.model_effective_date} model`;
} else if (!hasScore) {
  reason = autoScore === null || autoScore === ''
    ? 'never scored'
    : `previous result "${autoScore}" is not a grade — re-scoring`;
} else if (ageDays === null) {
  reason = 'no usable Auto-ICP Scored At date — re-scoring';
} else if (!isFresh) {
  reason = `stale: scored ${ageDays}d ago (>= ${cfg.rescore_after_days}d) — re-scoring`;
} else {
  reason = `scored ${scoredAtDay}, before the ${cfg.model_effective_date} model took effect — re-scoring`;
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
      auto_icp_score: autoScore,
      auto_icp_scored_at: scoredAtDay,
      is_real_grade: isRealGrade,
      age_days: ageDays,
      on_current_model: currentModel,
    },
  },
}];
