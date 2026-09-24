// BuildRunSummary — the terminal node on Path B: one flat row describing what
// this run did.
//
// It is a summary, not a store. The audit Data Table was dropped, so nothing
// is appended anywhere; this row exists so that opening an execution shows the
// whole decision in one object instead of five nodes deep. If an audit store
// comes back, this is what it writes.
//
// Every key is present on every run, in a fixed order. A column that is
// sometimes absent is a column nobody can filter on.

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

// Reached on the duplicate branch too, where no write was attempted — so both
// lookups are optional and their absence is itself a fact worth recording.
let patch = null;
try { patch = $('BuildOrgPatch').item.json; } catch (e) { patch = null; }
let activity = null;
try { activity = $('BuildActivity').item.json; } catch (e) { activity = null; }
let activityResponse = null;
try { activityResponse = $('POST activity').item.json; } catch (e) { activityResponse = null; }

const COLUMNS = [
  'ts', 'requested_at', 'request_id', 'execution_id', 'trigger', 'deal_id', 'org_id',
  'model_version',
  'industry_level', 'stage_level', 'type_level', 'geo_level', 'revenue_level',
  'activation_used', 'multiplier', 'composite', 'final', 'final_without_activation',
  'grade', 'status', 'confidence_overall', 'tier2_candidate', 'flags',
  'note_chars', 'patch_written', 'auto_icp_score', 'auto_icp_scored_at',
  'activity_id', 'error',
];

const errorBits = [];
if (parsed._duplicate) errorBits.push('duplicate');
if (parsed._rate_exceeded) errorBits.push(`rate_exceeded:${parsed._rate_this_hour}/h`);

// Numbers stay numbers; only the ids become strings, because a column that is
// sometimes empty cannot be a number column.
const id = (v) => (v === null || v === undefined ? '' : String(v));
const num = (v) => (v === null || v === undefined ? '' : v);

const row = {
  ts: cfg.now_iso,
  requested_at: parsed.requested_at,
  request_id: parsed.request_id,
  execution_id: $execution.id,
  trigger: `clay.${cfg.clay_event_name}`,
  deal_id: id(parsed.deal_id),
  org_id: id(parsed.org_id),
  model_version: parsed.model_version,

  // The working, as the table showed it. Recorded, never acted on: nothing in
  // this workflow re-derives the grade from these, which is the whole point of
  // the table owning the rubric.
  industry_level: num(parsed.industry_level),
  stage_level: num(parsed.stage_level),
  type_level: num(parsed.type_level),
  geo_level: num(parsed.geo_level),
  revenue_level: num(parsed.revenue_level),
  activation_used: parsed.activation_used || '',
  multiplier: num(parsed.multiplier),
  composite: num(parsed.composite),
  final: num(parsed.final),
  final_without_activation: num(parsed.final_without_activation),
  grade: parsed.grade || '',
  status: parsed.status,
  confidence_overall: parsed.confidence_overall || '',
  tier2_candidate: parsed.tier2_candidate === true,
  flags: (parsed.flags || []).join('|'),

  // The note is written verbatim, so its length is the only thing worth
  // recording here — repeating the text would make the row unreadable and say
  // nothing the activity does not already say.
  note_chars: typeof parsed.note === 'string' ? parsed.note.length : 0,

  patch_written: Boolean(patch && patch.patch_is_empty === false),
  auto_icp_score: (patch && patch.auto_icp_score) || '',
  auto_icp_scored_at: (patch && patch.auto_icp_scored_at) || '',
  activity_id: activityResponse && activityResponse.data && activityResponse.data.id
    ? String(activityResponse.data.id)
    : (activity ? 'not-posted' : ''),
  error: errorBits.join(';'),
};

// Fixed order, asserted rather than assumed: a row whose keys drift is a row
// that silently stops lining up with every row before it.
const ordered = {};
for (const column of COLUMNS) ordered[column] = row[column];
const extra = Object.keys(row).filter((k) => COLUMNS.indexOf(k) === -1);
if (extra.length > 0) {
  throw new Error(`ICP_SUMMARY_DRIFT: ${JSON.stringify(extra)} is not in COLUMNS`);
}

return [{ json: ordered }];
