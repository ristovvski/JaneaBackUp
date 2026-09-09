// BuildNote — the explanation a rep reads. Plain text, <= CONFIG.note_max_chars.
//
// Structure per §8.3: a header line, one line per scored component, then
// Activation, Composite, Reference and Missing / low-confidence lines.
//
//   NEEDS_DECISION: the build task points at §4 of
//   ICP_Scoring_Architecture_v2_1.md for the exact template. That document is
//   not in the repository, so the layout below is built from §8.3's own
//   description of it (header, one line per component as
//   "<name> <level> <text> — <evidence>", then the four trailing lines). Every
//   element §8.3 names is present and asserted by nodes_execute.test.mjs.
//   Reconcile the wording against §4 when the document is available; it is
//   this one node and one test.
//
// Level TEXT comes from CONFIG.component_scales, which is generated from
// config/rubric_v5.json. No rubric prose is typed into this node.
//
// The character budget is enforced by trimming in a fixed order — evidence
// first, then level text — so the output is deterministic rather than
// truncated mid-sentence at whatever length the data happened to be.

const cfg = $('CONFIG').item.json;
const parsed = $('ParseScored').item.json;

const score = parsed.score;
const components = parsed.components;
const facts = parsed.facts_summary || {};
const levels = score.levels_used;

const MAX = cfg.note_max_chars || 1500;
const DASH = '—'; // em dash
const ARROW = '→';

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------
const calculatedLabel = score.status === 'insufficient_data'
  ? cfg.label_insufficient
  : cfg.grade_labels[score.grade];

const headerScore = score.status === 'insufficient_data' ? '' : ` (${score.final_score}/100)`;
const header = `ICP ${cfg.model_version} ${DASH} Calculated: ${calculatedLabel}${headerScore}`;

// ---------------------------------------------------------------------------
// One line per scored component
// ---------------------------------------------------------------------------
const levelText = (component, level) => {
  const scale = cfg.component_scales[component];
  if (!scale) return '';
  const text = scale[String(level)];
  return text === undefined ? '' : text;
};

const vertical = components.industry_vertical.value;
const verticalTier = vertical === null || vertical === undefined
  ? null
  : (cfg.vertical_tier[vertical] || null);

const rows = [
  {
    name: 'Industry',
    level: score.industry_level,
    // The industry line carries the vertical and its tier rather than a level
    // definition: "FinTech (Anchor)" is what a rep can act on.
    text: vertical === null || vertical === undefined
      ? '(vertical not determined)'
      : `${vertical}${verticalTier ? ` (${verticalTier})` : ''}`,
    evidence: components.industry_vertical.evidence || [],
  },
  { name: 'Stage', level: levels.stage_maturity, text: levelText('stage_maturity', levels.stage_maturity), evidence: components.stage_maturity.evidence || [] },
  { name: 'Type', level: levels.company_type, text: levelText('company_type', levels.company_type), evidence: components.company_type.evidence || [] },
  { name: 'Geography', level: levels.geography, text: levelText('geography', levels.geography), evidence: components.geography.evidence || [] },
  { name: 'Revenue', level: levels.revenue_range, text: levelText('revenue_range', levels.revenue_range), evidence: components.revenue_range.evidence || [] },
];

const componentLine = (row, evidenceCount, textLimit) => {
  const text = textLimit !== null && row.text.length > textLimit
    ? `${row.text.slice(0, Math.max(0, textLimit - 1))}…`
    : row.text;
  const evidence = row.evidence.slice(0, evidenceCount).join('; ');
  const tail = evidence === '' ? '' : ` ${DASH} ${evidence}`;
  return `${row.name} ${row.level} ${text}${tail}`;
};

// ---------------------------------------------------------------------------
// Activation, Composite, Reference, Missing
// ---------------------------------------------------------------------------
const multiplierText = `×${Number(score.multiplier).toFixed(2)}`;
const activationEvidence = (components.activation_state.evidence || [])[0];
let activationLine = `Activation: ${score.activation_state_used} ${multiplierText}`;
if (activationEvidence) activationLine += ` ${DASH} ${activationEvidence}`;
if (score.flags.indexOf('contracting_without_dated_evidence') !== -1) {
  activationLine += ` ${DASH} Contracting claimed without dated evidence, downgraded to ` +
                    `${cfg.activation_default}`;
}

let compositeLine = `Composite: ${score.composite}`;
if (score.status === 'insufficient_data') {
  compositeLine += ` ${ARROW} not graded (insufficient data)`;
} else {
  compositeLine += ` ${multiplierText} ${ARROW} ${score.final_score} ${ARROW} ${calculatedLabel}`;
}

// A zeroed or discounted score is illegible without the counterfactual, so
// Contracting always shows what the score would have been.
if (score.activation_state_used === 'Contracting') {
  const withoutGrade = score.final_score_without_activation >= cfg.thresholds.A
    ? cfg.grade_labels.A
    : score.final_score_without_activation >= cfg.thresholds.B
      ? cfg.grade_labels.B
      : cfg.grade_labels.C;
  compositeLine += ` | without activation: ${score.final_score_without_activation} ` +
                   `${ARROW} ${withoutGrade}`;
}

const ref = [];
ref.push(`HC ${facts.headcount_total === null || facts.headcount_total === undefined ? 'n/a' : facts.headcount_total}`);
ref.push(`eng HC ${facts.headcount_eng === null || facts.headcount_eng === undefined ? 'n/a' : facts.headcount_eng}`);
ref.push(`buying signal ${score.buying_signal_level === null || score.buying_signal_level === undefined ? 'n/a' : score.buying_signal_level}`);
if (score.tier2_candidate) ref.push('Tier 2 candidate');
const referenceLine = `Reference: ${ref.join(' · ')}`;

// Missing / low confidence. Mandatory and non-empty on insufficient_data.
const missingBits = [];
for (const component of Object.keys(components)) {
  const c = components[component];
  const missing = c.missing_inputs || [];
  const parts = [];
  if (missing.length > 0) parts.push(missing.join(', '));
  if (c.confidence === 'low') parts.push('low confidence');
  else if (c.confidence === 'medium') parts.push('medium confidence');
  if (parts.length > 0) missingBits.push(`${component} (${parts.join('; ')})`);
}
let missingLine;
if (missingBits.length > 0) {
  missingLine = `Missing / low confidence: ${missingBits.join(' · ')}`;
} else if (score.status === 'insufficient_data') {
  // Should be unreachable: insufficient_data implies a null level or a
  // low-confidence component. Say so rather than emitting an empty line.
  missingLine = 'Missing / low confidence: insufficient data with no component reporting a gap ' +
                '(unexpected — check the Clay row)';
} else {
  missingLine = `Missing / low confidence: none ${DASH} overall confidence ${score.confidence_overall}`;
}

const footerBits = [`request_id ${parsed.request_id}`, `model ${cfg.model_version}`, String(cfg.now_iso).slice(0, 10)];
if (score.flags.indexOf('clay_score_drift') !== -1) footerBits.push('CLAY SCORE DRIFT - see audit row');
const footer = footerBits.join(' · ');

// ---------------------------------------------------------------------------
// Fit the budget. Deterministic: shrink evidence, then level text, in order.
// ---------------------------------------------------------------------------
const assemble = (evidenceCount, textLimit) => [
  header,
  ...rows.map((row) => componentLine(row, evidenceCount, textLimit)),
  activationLine,
  compositeLine,
  referenceLine,
  missingLine,
  footer,
].join('\n');

const BUDGETS = [
  [2, null], [1, null], [1, 90], [1, 60], [1, 40], [0, 40], [0, 24],
];

let note = assemble(2, null);
for (const [evidenceCount, textLimit] of BUDGETS) {
  note = assemble(evidenceCount, textLimit);
  if (note.length <= MAX) break;
}
// Last resort: a hard cut. Every structural line is short, so reaching this
// means a single evidence string is pathological.
if (note.length > MAX) note = `${note.slice(0, MAX - 1)}…`;

return [{
  json: {
    request_id: parsed.request_id,
    org_id: parsed.org_id,
    deal_id: parsed.deal_id,
    note,
    note_length: note.length,
    note_lines: note.split('\n').length,
    calculated_label: calculatedLabel,
  },
}];
