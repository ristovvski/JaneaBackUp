// BuildNoWebsiteWrite — Path A's only write, and the only one it ever makes.
//
// An organization with no usable Website URL is not sent to the Clay table at
// all. That is the owner's ruling and it is not a degradation to work around:
// the domain is THE identifier, and the alternatives — search by company name,
// fall back to a LinkedIn slug — resolve to the wrong company often enough
// that a wrong grade arrives looking exactly like a right one. Six Pipedrive
// organizations named Sumersports is what that failure looks like from the
// inside.
//
// So the run ends here, and it ends the same way a scored run does, with the
// same footprint: the SAME TWO organization fields, written together, plus one
// activity that says what a human has to do. Nothing else on the record is
// touched. A rep who opens the org sees "n/a - no website" where a grade would
// be, and an activity telling them which single field to fill.
//
// Why the written value matters as much as the activity: "n/a - no website"
// fails IdempotencyGate's grade-shape test, so it is not a finished answer —
// the next deal on this organization re-runs, and once the Website URL is
// filled it scores normally. A blank field would have re-run too, but it would
// not have told anyone why nothing happened.

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

const decision = $input.first().json;
// The organization as GET organization returned it, already read once by the
// gate. Reading it from there rather than re-fetching keeps Path A at one
// Pipedrive read per run.
const gate = $('IdempotencyGate').item.json;

// This node sits on the FALSE output of "IF has website?". If it ever runs on
// the other one, the graph has been rewired and an organization that has a
// domain is about to be marked as having none.
if (decision.has_website !== false) {
  const error = new Error(
    'ICP_WRONG_BRANCH: BuildNoWebsiteWrite ran for an organization that HAS a ' +
    `usable domain (${JSON.stringify(decision.domain)}). Check the IF has website? wiring.`
  );
  error.name = 'IcpWrongBranch';
  throw error;
}

const autoScore = cfg.label_no_website;
const scoredAt = String(cfg.now_iso).slice(0, 10); // Pipedrive date = YYYY-MM-DD

// ---------------------------------------------------------------------------
// The two move together, always — the same rule BuildOrgPatch applies on
// Path B, for the same reason: a score without its date is a score the gate
// can never age out. A second deal on the same day for the same website-less
// organization therefore writes nothing at all, and still gets its activity.
// ---------------------------------------------------------------------------
const existing = gate.existing || {};
const currentScore = existing.auto_icp_score;
const currentDate = existing.auto_icp_scored_at;
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
// The same three invariants BuildOrgPatch asserts. Asserted here too rather
// than assumed, because this is a SECOND place that writes to an organization
// and a second writer is exactly where a contract quietly stops holding.
// ---------------------------------------------------------------------------
const keys = Object.keys(customFields);

for (const forbidden of cfg.fields_never_write || []) {
  if (Object.prototype.hasOwnProperty.call(customFields, forbidden)) {
    const error = new Error(
      `ICP_FORBIDDEN_WRITE: the patch contains ${forbidden}, which is in ` +
      'CONFIG.fields_never_write (Sales Rep ICP Score belongs to the human)'
    );
    error.name = 'IcpForbiddenWrite';
    throw error;
  }
}

const permitted = cfg.fields_written || [];
for (const key of keys) {
  if (permitted.indexOf(key) === -1) {
    const error = new Error(
      'ICP_UNEXPECTED_WRITE: a run writes only the fields in ' +
      `CONFIG.fields_written. This patch also carries ${key}.`
    );
    error.name = 'IcpUnexpectedWrite';
    throw error;
  }
}
if (keys.length !== 0 && keys.length !== permitted.length) {
  const error = new Error(
    'ICP_PARTIAL_WRITE: the score and its date move together. This patch ' +
    `carries ${JSON.stringify(keys)} instead of all ${permitted.length} or none.`
  );
  error.name = 'IcpPartialWrite';
  throw error;
}

// Nothing at the top level. A standard field written here — website, linkedin,
// a label — would be an org mutation this contract does not allow, so the
// shape makes one impossible rather than relying on nobody adding one.
const patch = changed ? { custom_fields: customFields } : {};

// ---------------------------------------------------------------------------
// The activity. One sentence, the one the owner wrote, in the words a rep
// reads.
//
// A second sentence appears only when the field was not empty but unusable —
// "acme", "n/a", a phone number. Telling someone to fill a field they can see
// is already filled reads as a bug in us; quoting what is actually in it says
// what to do in one glance. The raw value is quoted and length-capped, never
// interpreted.
// ---------------------------------------------------------------------------
const sentences = [cfg.activity_no_website];

const raw = decision.website_raw;
if (typeof raw === 'string' && raw.trim() !== '') {
  const shown = raw.trim().length > 120 ? `${raw.trim().slice(0, 117)}...` : raw.trim();
  sentences.push(
    `The Website URL on the record reads "${shown}", which is not a usable web address.`
  );
}

let body = sentences.join('\n\n');
const budget = cfg.activity_max_chars || 900;
// Drop whole sentences rather than cutting one mid-word: a truncated
// instruction is worse than a shorter one.
while (body.length > budget && sentences.length > 1) {
  sentences.pop();
  body = sentences.join('\n\n');
}
if (body.length > budget) body = body.slice(0, budget);

return [{
  json: {
    request_id: decision.request_id,
    org_id: decision.org_id,
    deal_id: decision.deal_id,

    patch,
    patch_is_empty: !changed,
    auto_icp_score: autoScore,
    auto_icp_scored_at: scoredAt,
    previous_auto_icp_score: currentScore === undefined ? null : currentScore,
    previous_auto_icp_scored_at: currentDate === undefined ? null : currentDate,
    changed_fields: changed ? permitted : [],
    unchanged_fields: changed ? [] : permitted,

    subject: cfg.activity_subject_skipped,
    type: cfg.activity_type,
    body,
    chars: body.length,

    skipped: true,
    reason: decision.reason,
    website_raw: raw === undefined ? null : raw,
  },
}];
