// BuildOrgPatch — the Pipedrive organization PATCH body, or {} when nothing
// differs.
//
// Organizations are v2, so custom fields nest under `custom_fields` keyed by
// the 40-hex field key (leads are v1 with TOP-LEVEL hashed keys — different
// object, different shape; do not copy one to the other).
//
// Two invariants live here:
//
//   1. ICP Final is NEVER written. It is the human's field. The key is in
//      CONFIG.fields_never_write and this node asserts against it rather than
//      merely omitting it, so a future edit that adds it fails loudly.
//
//   2. No churn. A key is included only when its value actually differs from
//      what the org already holds. Same event, same values -> {} -> the IF
//      gate skips the PATCH entirely, and Pipedrive sees no write at all.
//
//   3. Fill, never correct. website and linkedin are written only when the
//      record has none. See the block near the bottom.
//
// On ICP Scored At: it is included when the date differs, which means a
// re-score on a later day updates it (correct — it is what the 180-day gate
// reads) while a second run on the same day writes nothing (also correct).
//
// NOTE_WATCHDOG (NEEDS_DECISION #2 — honor system is the implemented default)
// -------------------------------------------------------------------------
// Nothing stops a rep overwriting ICP Calculated by hand, and the next
// re-score silently reverts it, up to 180 days later. The chosen default is
// the honor system: ICP Calculated belongs to the system, ICP Final belongs to
// the human, and the system never touches ICP Final.
//
// If the honor system does not hold, THIS is where the watchdog attaches: a
// second Pipedrive webhook on change.organization, filtered to
// CONFIG.f_icp_calculated, comparing meta.change_source. An 'app' change to
// that field with no matching execution in the ledger is a human edit, and the
// watchdog would post one Slack notice naming the org, the old value and the
// new one. It would NOT revert the edit — reverting a human's deliberate change
// without asking is worse than the drift it fixes.
//
// Deliberately a comment and not disabled code: an unused branch rots, and the
// decision is Nik's to make, not this node's to pre-empt.

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
const parsed = $('ParseScored').item.json;
const fetched = $input.first().json;
const org = fetched.data || fetched;
const existing = org.custom_fields || {};
const resolved = parsed.resolved || {};

const score = parsed.score;

// ---------------------------------------------------------------------------
// What should ICP Calculated say?
// ---------------------------------------------------------------------------
let targetLabel;
if (score.status === 'insufficient_data') {
  targetLabel = cfg.label_insufficient;
} else {
  targetLabel = cfg.grade_labels[score.grade];
}

if (!targetLabel) {
  const error = new Error(
    `ICP_UNMAPPED_GRADE: no label for grade ${JSON.stringify(score.grade)} ` +
    `with status ${JSON.stringify(score.status)}`
  );
  error.name = 'IcpUnmappedGrade';
  throw error;
}

// Enums are written by OPTION ID, never by label.
const optionId = cfg.opt_icp_calculated[targetLabel];
if (optionId === null || optionId === undefined) {
  const error = new Error(
    `ICP_MISSING_OPTION_ID: "${targetLabel}" has no option id in CONFIG. ` +
    `Run scripts/pipedrive_create_fields.mjs against the live account and ` +
    `npm run gen:config. Writing an enum by label is not supported.`
  );
  error.name = 'IcpMissingOptionId';
  throw error;
}

// ---------------------------------------------------------------------------
// The four target values.
// ---------------------------------------------------------------------------
const scoredAt = String(cfg.now_iso).slice(0, 10); // Pipedrive date = YYYY-MM-DD

const targets = {};
targets[cfg.f_icp_calculated] = optionId;
targets[cfg.f_icp_scored_at] = scoredAt;
targets[cfg.f_icp_model_version] = cfg.model_version;
// On insufficient_data the score must be ABSENT, not 0 and not "". Pipedrive
// clears a field with null, so null is the target rather than an omission —
// otherwise a previous numeric score would survive under an
// "Insufficient data" label, which reads as a score of the wrong kind.
targets[cfg.f_icp_score] = score.status === 'insufficient_data' ? null : score.final_score;

// ---------------------------------------------------------------------------
// Include only what differs.
// ---------------------------------------------------------------------------
const same = (a, b) => {
  if (a === null || a === undefined) return b === null || b === undefined;
  if (b === null || b === undefined) return false;
  if (typeof a === 'number' || typeof b === 'number') return Number(a) === Number(b);
  return String(a) === String(b);
};

const customFields = {};
const changed = [];
const unchanged = [];

for (const key of Object.keys(targets)) {
  if (same(existing[key], targets[key])) {
    unchanged.push(key);
  } else {
    customFields[key] = targets[key];
    changed.push(key);
  }
}

// Invariant 2: assert, do not merely omit.
for (const forbidden of cfg.fields_never_write || []) {
  if (Object.prototype.hasOwnProperty.call(customFields, forbidden)) {
    const error = new Error(
      `ICP_FORBIDDEN_WRITE: the patch contains ${forbidden}, which is in ` +
      `CONFIG.fields_never_write (ICP Final is the human's field)`
    );
    error.name = 'IcpForbiddenWrite';
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Fill-if-empty: website and LinkedIn URL from what the table resolved.
//
// A name-only org is the case this exists for. Path A sends the name, the
// table finds the company, and `resolved` comes back holding the domain and
// the LinkedIn URL that scoring actually used — which is exactly what the CRM
// record was missing and what makes the NEXT run a domain lookup instead of a
// name search.
//
// FILL, never correct. A value already on the record was put there by a human
// or by an earlier integration, and this workflow's job is scoring, not
// deciding that someone else's URL is wrong. An org with a website keeps it,
// even if the table resolved a different one — that disagreement belongs in
// the note, not in a silent overwrite.
//
// These are standard organization fields, so they sit at the TOP level of the
// v2 patch body, not under custom_fields.
// ---------------------------------------------------------------------------
const isBlank = (v) => v === null || v === undefined || String(v).trim() === '';

const standard = {};
const filled = [];
const FILL_IF_EMPTY = [
  // Pipedrive's own key <- the resolved key that feeds it. The Pipedrive
  // organization field is `linkedin` ("LinkedIn profile"), NOT `linkedin_url`;
  // both are short standard keys on this account, which is why they go at the
  // top level of the v2 body. `website` takes the table's website first and
  // falls back to the domain, which a lookup can always produce.
  { field: 'website', from: ['website', 'domain'] },
  { field: 'linkedin', from: ['linkedin_url'] },
];

for (const rule of FILL_IF_EMPTY) {
  if (!isBlank(org[rule.field])) continue;
  let value = null;
  for (const key of rule.from) {
    if (!isBlank(resolved[key])) { value = String(resolved[key]).trim(); break; }
  }
  if (value === null) continue;
  // A bare domain is not a URL. Pipedrive stores the string as given, and a
  // rep clicking "akuvo.com" in the UI should land on the site.
  if (rule.field === 'website' && !/^https?:\/\//i.test(value)) value = `https://${value}`;
  standard[rule.field] = value;
  filled.push(rule.field);
}

const patch = changed.length === 0 && filled.length === 0
  ? {}
  : Object.assign({}, standard, changed.length === 0 ? {} : { custom_fields: customFields });

return [{
  json: {
    request_id: parsed.request_id,
    org_id: parsed.org_id,
    deal_id: parsed.deal_id,
    patch,
    patch_is_empty: changed.length === 0 && filled.length === 0,
    changed_fields: changed,
    unchanged_fields: unchanged,
    filled_fields: filled,
    target_label: targetLabel,
    target_option_id: optionId,
    scored_at: scoredAt,
  },
}];
