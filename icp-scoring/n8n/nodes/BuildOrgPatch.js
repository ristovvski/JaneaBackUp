// BuildOrgPatch — the Pipedrive organization PATCH body, or {} when nothing
// differs.
//
// v6 writes TWO fields, in one PATCH: Auto-ICP Score, text, "<final> -
// <grade>", and Auto-ICP Scored At, a date. That is the whole contract.
// Everything else a run produces — composite, levels, multiplier, the
// activation guard, the evidence — stays in the run's own trace rather than
// becoming a column a rep has to read past.
//
// The date is not decoration: it is the entire idempotency mechanism. Without
// it the gate can only ask "has this been scored?", and the answer is yes
// forever. With it the gate asks "recently, and under this rubric?".
//
// What this node used to write and no longer does: ICP Calculated (enum),
// ICP Score (number), ICP Scored At (date), ICP Model Version (text), ICP Final
// (enum), and the fill-if-empty of website and linkedin. All five fields were
// DELETED from the account on 2026-09-17, so there is no deny-list to keep in
// step — the guarantee below is that the patch contains at most the two keys
// CONFIG names, which does not rot.
//
// Three invariants, all ASSERTED rather than merely satisfied — a future edit
// that breaks one fails loudly instead of quietly writing to a human's field:
//
//   1. Sales Rep ICP Score is NEVER written. It is the human's column, and the
//      only reason this workflow knows its key is to check it is absent.

//   3. The patch contains at most the TWO keys CONFIG.fields_written names.
//      Not "no forbidden keys" — an allow-list, so a field added in future has
//      to be added there deliberately.
//
// No churn: the key is included only when the value actually differs from what
// the org already holds, so a re-score that changes nothing sends no write at
// all and Pipedrive's update_time is left alone.
//
// NOTE_WATCHDOG (NEEDS_DECISION #2 — honor system is the implemented default)
// -------------------------------------------------------------------------
// Nothing stops a rep overwriting Auto-ICP Score by hand, and the next
// re-score silently reverts it. The chosen default is the honor system:
// Auto-ICP Score belongs to the system, Sales Rep ICP Score belongs to the
// human, and the system never touches the human's field. If that does not
// hold, the watchdog attaches here: a second Pipedrive webhook on
// change.organization filtered to CONFIG.f_auto_icp_score, comparing
// meta.change_source, posting one Slack notice on an 'app' change with no
// matching execution in the ledger. It would NOT revert the edit.

// CONFIG on Path A, CONFIG B on Path B. The two Set nodes hold the same JSON,
// but a Code node may only reference a node that is CONNECTED upstream of it:
// n8n raises a "no connection" expression error otherwise, and in the task
// runner that error's own constructor then throws
// `Cannot assign to read only property 'name'`, which hides the real message
// completely. A node that runs on both paths therefore has to ask for
// whichever CONFIG is upstream of it. Kept byte-identical across the nodes
// that need it; tests/static/workflow_review.test.mjs enforces that.
let cfg = null;
try { cfg = $('CONFIG').item.json; } catch (e) { cfg = null; }
if (cfg === null || cfg === undefined) {
  try { cfg = $('CONFIG B').item.json; } catch (e) { cfg = null; }
}
if (cfg === null || cfg === undefined) {
  throw new Error('ICP_NO_CONFIG: neither CONFIG nor CONFIG B is upstream of this node');
}
// ParseScored's output: the table's grade, validated and flattened. There is
// no Score node any more — the table scores and this workflow writes.
const parsed = $('ParseScored').item.json;
const fetched = $input.first().json;
const org = fetched.data || fetched;
const existing = org.custom_fields || {};

// ---------------------------------------------------------------------------
// The one value.
//
// "<final> - <grade>", e.g. "62 - B". On insufficient_data the score is not a
// number and saying "0 - C" would be a lie with the same shape as a real
// answer, so the whole string is replaced — and it keeps the separator so a
// column of these still sorts and filters as one thing.
// ---------------------------------------------------------------------------
let autoScore;
if (parsed.status === 'insufficient_data') {
  autoScore = cfg.label_insufficient;
} else if (parsed.grade === null || parsed.grade === undefined || parsed.final === null) {
  // ParseScored already refuses status "scored" with a null grade, so this is
  // the belt to that braces: it cannot be reached without the boundary having
  // been changed, and if it ever is, nothing grade-shaped gets written.
  const error = new Error(
    `ICP_UNSCORED: status is ${JSON.stringify(parsed.status)} but there is no grade to write ` +
    `(grade ${JSON.stringify(parsed.grade)}, final ${JSON.stringify(parsed.final)})`
  );
  error.name = 'IcpUnscored';
  throw error;
} else {
  autoScore = `${parsed.final}${cfg.auto_score_separator}${parsed.grade}`;
}

const scoredAt = String(cfg.now_iso).slice(0, 10); // Pipedrive date = YYYY-MM-DD

// ---------------------------------------------------------------------------
// The two move together, always.
//
// A score without its date is a score the gate can never age out, and a date
// without its score is a date that means nothing — so "did anything change?"
// is asked once, over the pair. A re-score on the same day with the same grade
// writes nothing at all; a re-score on a later day writes both, because the
// date IS the thing that changed and it is what the next gate reads.
// ---------------------------------------------------------------------------
const currentScore = existing[cfg.f_auto_icp_score];
const currentDate = existing[cfg.f_auto_icp_scored_at];
const same = (a, b) => {
  if (a === null || a === undefined || a === '') return b === null || b === undefined || b === '';
  if (b === null || b === undefined) return false;
  return String(a).trim().slice(0, 10) === String(b).trim().slice(0, 10);
};

const changed = !same(currentScore, autoScore) || !same(currentDate, scoredAt);
const customFields = {};
if (changed) {
  customFields[cfg.f_auto_icp_score] = autoScore;
  customFields[cfg.f_auto_icp_scored_at] = scoredAt;
}

// ---------------------------------------------------------------------------
// Invariants 1-3. Asserted, not assumed.
// ---------------------------------------------------------------------------
const keys = Object.keys(customFields);

for (const forbidden of cfg.fields_never_write || []) {
  if (Object.prototype.hasOwnProperty.call(customFields, forbidden)) {
    const error = new Error(
      `ICP_FORBIDDEN_WRITE: the patch contains ${forbidden}, which is in ` +
      `CONFIG.fields_never_write (Sales Rep ICP Score belongs to the human)`
    );
    error.name = 'IcpForbiddenWrite';
    throw error;
  }
}

const permitted = cfg.fields_written || [];
for (const key of keys) {
  if (permitted.indexOf(key) === -1) {
    const error = new Error(
      `ICP_UNEXPECTED_WRITE: a Path B run writes only the fields in ` +
      `CONFIG.fields_written. This patch also carries ${key}.`
    );
    error.name = 'IcpUnexpectedWrite';
    throw error;
  }
}
if (keys.length !== 0 && keys.length !== permitted.length) {
  const error = new Error(
    `ICP_PARTIAL_WRITE: the score and its date move together. This patch ` +
    `carries ${JSON.stringify(keys)} instead of all ${permitted.length} or none.`
  );
  error.name = 'IcpPartialWrite';
  throw error;
}

// The patch body itself carries NOTHING at the top level. A standard field
// written here — website, linkedin, a label — would be an org mutation this
// contract does not allow, so the shape makes one impossible rather than
// relying on nobody adding one.
const patch = changed ? { custom_fields: customFields } : {};

return [{
  json: {
    request_id: parsed.request_id,
    org_id: parsed.org_id,
    deal_id: parsed.deal_id,
    patch,
    patch_is_empty: !changed,
    auto_icp_score: autoScore,
    auto_icp_scored_at: scoredAt,
    previous_auto_icp_score: currentScore === undefined ? null : currentScore,
    previous_auto_icp_scored_at: currentDate === undefined ? null : currentDate,
    changed_fields: changed ? permitted : [],
    unchanged_fields: changed ? [] : permitted,
  },
}];
