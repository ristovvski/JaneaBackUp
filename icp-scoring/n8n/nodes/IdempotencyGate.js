// IdempotencyGate — should this organization be scored at all?
//
// v6 changes what this can know. The workflow now writes ONE organization
// field, Auto-ICP Score ("93 - A"), and that field carries no date and no
// model version — the date and the version live in icp_audit, where the whole
// trace lives. So the three-part freshness test v5 ran (real grade + current
// model + younger than the window) has one part left that can be answered from
// the organization record.
//
// The rule is therefore: **skip when Auto-ICP Score already holds a real
// grade.** Clearing the field is what triggers a re-score.
//
// What that costs, stated plainly rather than discovered later:
//
//   - The 180-day re-score window is GONE. Nothing on the organization records
//     when it was scored, so nothing here can age it out.
//   - A model bump no longer forces a re-score by itself.
//
// Both are recoverable, and in the same place: icp_audit holds `ts`,
// `requested_at` and `model_version` per run, so a lookup on the table would
// restore both tests exactly. That is a Path A addition against a table that
// does not exist yet, so it is named here and not guessed at.
//
// The deviation that survives: a previous run that came back "insufficient
// data" is NOT a grade, so it is re-scored rather than freezing the account
// out. A transient failure must not cost an account its next look.

const cfg = $('CONFIG').item.json;
const n = $('Normalize').item.json;
const fetched = $input.first().json;
const org = fetched.data || fetched;
const custom = org.custom_fields || {};

const rawAutoScore = custom[cfg.f_auto_icp_score];
const autoScore = rawAutoScore === null || rawAutoScore === undefined
  ? null
  : String(rawAutoScore).trim();

// "93 - A" is a grade. "n/a - insufficient data" and "n/a - error" are not:
// they record that a run happened and produced nothing usable, and the whole
// point of the deviation above is that such a run gets looked at again.
const GRADE_PATTERN = /^\s*\d{1,3}\s*-\s*[ABC]\s*$/;
const isRealGrade = autoScore !== null && autoScore !== '' && GRADE_PATTERN.test(autoScore);

const hasScore = cfg.rescore_on_error_or_insufficient
  ? isRealGrade
  : autoScore !== null && autoScore !== '';

const skip = hasScore;

let reason;
if (skip) {
  reason = `already scored: "${autoScore}" — clear Auto-ICP Score to re-score`;
} else if (autoScore === null || autoScore === '') {
  reason = 'never scored';
} else {
  reason = `previous result "${autoScore}" is not a grade — re-scoring`;
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
      is_real_grade: isRealGrade,
    },
  },
}];
