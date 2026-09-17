// BuildOrgPatch — the Pipedrive organization PATCH body, or {} when nothing
// differs.
//
// v6 writes ONE field: Auto-ICP Score, text, "<final> - <grade>". That is the
// whole contract. Everything a run produces — composite, levels, multiplier,
// the activation guard, the trace — goes to icp_audit, where it can be queried
// without adding a column a rep has to read past.
//
// What this node used to write and no longer does: ICP Calculated (enum),
// ICP Score (number), ICP Scored At (date), ICP Model Version (text), and the
// fill-if-empty of website and linkedin. The four fields still exist in the
// account; whether they are deleted is Nik's call. They are kept in
// CONFIG.f_retired_v5 so the static suite can assert no patch ever contains
// one again.
//
// Three invariants, all ASSERTED rather than merely satisfied — a future edit
// that breaks one fails loudly instead of quietly writing to a human's field:
//
//   1. Sales Rep ICP Score is NEVER written. It is the human's column, and the
//      only reason this workflow knows its key is to check it is absent.
//   2. ICP Final is NEVER written. Same reason, older field.
//   3. The patch contains at most ONE key, and that key is Auto-ICP Score.
//      Not "no forbidden keys" — exactly one permitted key, so a field added
//      in future has to be added here deliberately.
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
// Score's output is ParseScored's, plus the grade — so one lookup gets both
// the classifier evidence and the number it produced.
const parsed = $('Score').item.json;
const fetched = $input.first().json;
const org = fetched.data || fetched;
const existing = org.custom_fields || {};

const score = parsed.score;

// ---------------------------------------------------------------------------
// The one value.
//
// "<final> - <grade>", e.g. "56 - B". On insufficient_data the score is not a
// number and saying "0 - C" would be a lie with the same shape as a real
// answer, so the whole string is replaced — and it keeps the separator so a
// column of these still sorts and filters as one thing.
// ---------------------------------------------------------------------------
let autoScore;
if (score.status === 'insufficient_data') {
  autoScore = cfg.label_insufficient;
} else if (score.grade === null || score.grade === undefined || score.final_score === null) {
  const error = new Error(
    `ICP_UNSCORED: status is ${JSON.stringify(score.status)} but there is no grade to write ` +
    `(grade ${JSON.stringify(score.grade)}, final ${JSON.stringify(score.final_score)})`
  );
  error.name = 'IcpUnscored';
  throw error;
} else {
  autoScore = `${score.final_score}${cfg.auto_score_separator}${score.grade}`;
}

// ---------------------------------------------------------------------------
// Include it only if it differs.
// ---------------------------------------------------------------------------
const current = existing[cfg.f_auto_icp_score];
const same = (a, b) => {
  if (a === null || a === undefined || a === '') return b === null || b === undefined || b === '';
  if (b === null || b === undefined) return false;
  return String(a).trim() === String(b).trim();
};

const changed = !same(current, autoScore);
const customFields = {};
if (changed) customFields[cfg.f_auto_icp_score] = autoScore;

// ---------------------------------------------------------------------------
// Invariants 1-3. Asserted, not assumed.
// ---------------------------------------------------------------------------
const keys = Object.keys(customFields);

for (const forbidden of cfg.fields_never_write || []) {
  if (Object.prototype.hasOwnProperty.call(customFields, forbidden)) {
    const error = new Error(
      `ICP_FORBIDDEN_WRITE: the patch contains ${forbidden}, which is in ` +
      `CONFIG.fields_never_write (Sales Rep ICP Score and ICP Final belong to the human)`
    );
    error.name = 'IcpForbiddenWrite';
    throw error;
  }
}

for (const retired of cfg.f_retired_v5 || []) {
  if (Object.prototype.hasOwnProperty.call(customFields, retired)) {
    const error = new Error(
      `ICP_RETIRED_FIELD_WRITE: the patch contains ${retired}, a v5 field this ` +
      `workflow no longer writes. Everything but Auto-ICP Score goes to icp_audit.`
    );
    error.name = 'IcpRetiredFieldWrite';
    throw error;
  }
}

if (keys.length > 1 || (keys.length === 1 && keys[0] !== cfg.f_auto_icp_score)) {
  const error = new Error(
    `ICP_UNEXPECTED_WRITE: a Path B run writes at most one organization field ` +
    `(Auto-ICP Score). This patch carries ${JSON.stringify(keys)}.`
  );
  error.name = 'IcpUnexpectedWrite';
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
    previous_auto_icp_score: current === undefined ? null : current,
    changed_fields: changed ? [cfg.f_auto_icp_score] : [],
    unchanged_fields: changed ? [] : [cfg.f_auto_icp_score],
  },
}];
