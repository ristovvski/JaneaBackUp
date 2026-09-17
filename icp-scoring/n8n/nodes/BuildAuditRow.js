// BuildAuditRow — one row per Path B run, in the exact column order of §8.4.
//
// Written for EVERY run, including a dropped duplicate (flagged in `error`).
// A dedupe that leaves no trace is indistinguishable from a lost event when
// someone asks why an organization was not scored.
//
// The icp_audit Data Table's columns must match COLUMNS below by NAME: the
// Data Table node maps input keys onto columns by name, so a column added here
// and not to the table is silently dropped rather than shifting the row.
// RUNBOOK.md carries the column list and its types.
//
// tests/static/nodes_execute.test.mjs asserts the emitted row has exactly these
// keys in exactly this order. Order does not affect the write — it keeps the
// row readable in a trace, and it makes an added column a failing test rather
// than a quiet change of shape.

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

// The patch and note nodes do not run on a duplicate or an error branch, so
// read them defensively rather than assuming the happy path.
let patch = null;
try { patch = $('BuildOrgPatch').item.json; } catch (e) { patch = null; }
let note = null;
try { note = $('BuildNote').item.json; } catch (e) { note = null; }
let noteResponse = null;
try { noteResponse = $('POST note').item.json; } catch (e) { noteResponse = null; }

const score = parsed.score;
const components = parsed.components;
const levels = score.levels;

const COLUMNS = [
  'ts', 'request_id', 'execution_id', 'trigger', 'deal_id', 'org_id',
  'identifier_kind', 'identifier_value', 'model_version',
  'industry_vertical', 'industry_level', 'stage_level', 'type_level',
  'geo_level', 'revenue_level', 'buying_level',
  'activation_state', 'multiplier', 'composite', 'final',
  'final_without_activation', 'grade', 'status', 'confidence_overall',
  'tier2_candidate', 'flags', 'missing_inputs', 'evidence_json',
  'patch_written', 'note_id', 'error',
];

// Collapse every component's gaps into one auditable string.
const missing = [];
for (const component of Object.keys(components)) {
  if (components[component].computed_by_table) continue;
  const items = components[component].missing_inputs || [];
  if (items.length > 0) missing.push(`${component}:${items.join('|')}`);
}

// Evidence as JSON so a row stays one cell and stays machine-readable.
const evidence = {};
for (const component of Object.keys(components)) {
  // A component the table computed has no evidence by construction. Writing
  // `"geography": []` into every row would suggest the evidence was looked for
  // and not found, which is not what happened.
  if (components[component].computed_by_table) continue;
  evidence[component] = components[component].evidence || [];
}

const errorBits = [];
if (parsed._duplicate) errorBits.push('duplicate');
if (parsed._rate_exceeded) errorBits.push(`rate_exceeded:${parsed._rate_this_hour}/h`);
// v5 recorded a drift between Clay's score and n8n's recompute here. v6 has no
// recompute to disagree with: a score that does not match the rubric is
// rejected outright by ParseScored and never reaches this node. What takes its
// place is the table's own conflict note, which explains a score rather than
// contradicting it.
if (parsed.conflict_note) errorBits.push(`conflict:${parsed.conflict_note}`);

const row = {
  ts: cfg.now_iso,
  request_id: parsed.request_id,
  execution_id: $execution.id,
  trigger: `clay.${cfg.clay_event_name}`,
  deal_id: parsed.deal_id === null || parsed.deal_id === undefined ? '' : parsed.deal_id,
  org_id: parsed.org_id,
  identifier_kind: parsed.identifier_kind,
  identifier_value: parsed.identifier_value,
  model_version: parsed.model_version,

  industry_vertical: components.industry_vertical.value === null ? '' : components.industry_vertical.value,
  industry_level: levels.industries,
  stage_level: levels.stage_maturity,
  type_level: levels.company_type,
  geo_level: levels.geography,
  revenue_level: levels.revenue_range,
  buying_level: levels.buying_signal,

  activation_state: score.activation_state_used,
  multiplier: score.multiplier,
  composite: score.composite,
  final: score.final_score,
  final_without_activation: score.final_score_without_activation,
  grade: score.grade === null ? '' : score.grade,
  status: score.status,
  confidence_overall: score.confidence_overall,
  tier2_candidate: score.tier2_candidate,

  flags: (score.flags || []).join('|'),
  missing_inputs: missing.join(' · '),
  evidence_json: JSON.stringify(evidence),

  patch_written: patch === null ? false : patch.patch_is_empty === false,
  note_id: noteResponse && (noteResponse.id || (noteResponse.data && noteResponse.data.id))
    ? String(noteResponse.id || noteResponse.data.id)
    : '',
  error: errorBits.join(' · '),
};

// Emit in COLUMNS order. The Data Table maps by name, so this is for the
// human reading the execution, not for the write.
const ordered = {};
for (const column of COLUMNS) ordered[column] = row[column];

const missingColumns = COLUMNS.filter((c) => !Object.prototype.hasOwnProperty.call(row, c));
if (missingColumns.length > 0) {
  throw new Error(`ICP_AUDIT_COLUMN_MISSING: ${missingColumns.join(', ')}`);
}

return [{ json: ordered, pairedItem: { item: 0 } }];
