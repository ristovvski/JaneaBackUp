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
// config/rubric_v6.json. No rubric prose is typed into this node.
//
// v6: geography, revenue_range and buying_signal carry no evidence, because
// the table computes them rather than a classifier deciding them. Their lines
// still appear — a rep reading the note needs to see every component that
// moved the score — they simply have no evidence tail. The conflict note the
// table emits when two sources disagreed gets a line of its own.
//
// The character budget is enforced by trimming in a fixed order — evidence
// first, then level text — so the output is deterministic rather than
// truncated mid-sentence at whatever length the data happened to be.

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

const score = parsed.score;
const components = parsed.components;
const apollo = parsed.apollo_summary || {};
const hiring = parsed.hiring || {};
const levels = score.levels;

const MAX = cfg.note_max_chars || 1500;
const DASH = '—'; // em dash
const ARROW = '→';
const GTE = '\u2265'; // ≥

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
    level: levels.industries,
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
if (score.contracting_guard_applied) {
  activationLine += ` ${DASH} Contracting claimed but not backed (${score.contracting_guard_reason}), ` +
                    `downgraded to ${cfg.activation_default}`;
}

let compositeLine = `Composite: ${score.composite}`;
if (score.status === 'insufficient_data') {
  compositeLine += ` ${ARROW} not graded (insufficient data)`;
} else {
  compositeLine += ` ${multiplierText} ${ARROW} ${score.final_score} ${ARROW} ${calculatedLabel}`;
}

// A zeroed or discounted score is illegible without the counterfactual, so the
// without-activation number is always shown once the multiplier is not 1.00 —
// and always, without exception, when Contracting zeroed it.
if (score.activation_state_used === 'Contracting' || Number(score.multiplier) !== 1) {
  const withoutGrade = score.final_score_without_activation >= cfg.thresholds.A
    ? cfg.grade_labels.A
    : score.final_score_without_activation >= cfg.thresholds.B
      ? cfg.grade_labels.B
      : cfg.grade_labels.C;
  compositeLine += ` | without activation: ${score.final_score_without_activation} ` +
                   `${ARROW} ${withoutGrade}`;
}

const show = (v) => (v === null || v === undefined ? 'n/a' : v);
const engHeadcount = apollo.eng_headcount === null || apollo.eng_headcount === undefined
  ? hiring.eng_headcount
  : apollo.eng_headcount;

const ref = [];
ref.push(`HC ${show(apollo.employees)}`);
ref.push(`eng HC ${show(engHeadcount)}`);
ref.push(`buying signal ${show(levels.buying_signal)}`);
if (score.tier2_candidate) ref.push('Tier 2 candidate');
const referenceLine = `Reference: ${ref.join(' · ')}`;

// ---------------------------------------------------------------------------
// Hiring
//
// Three distinct states, and collapsing any two of them would be a lie a rep
// acts on: postings found, no postings found, and postings found but undated
// (so "open 60+ days" cannot be computed). A zero and an unknown are opposite
// facts — that distinction is the whole reason stage_maturity was wrong on
// Akuvo — so an absent count prints as a sentence, never as 0.
// ---------------------------------------------------------------------------
let hiringLine;
if (hiring.eng_open === null || hiring.eng_open === undefined) {
  hiringLine = 'Hiring no postings found';
} else if (hiring.dates_available === false) {
  hiringLine = `Hiring ${hiring.eng_open} eng open, dates unavailable`;
} else {
  const bits = [`${hiring.eng_open} eng open`];
  if (hiring.eng_open_60d_plus !== null && hiring.eng_open_60d_plus !== undefined) {
    bits.push(`${hiring.eng_open_60d_plus} ${GTE}60d`);
  }
  const leader = (hiring.leader_titles || [])[0];
  bits.push(leader ? `leader: ${leader}` : 'no eng leader found');
  if (typeof hiring.eng_open_ratio === 'number') bits.push(`ratio ${hiring.eng_open_ratio}`);
  hiringLine = `Hiring ${bits.join(', ')}`;
}

// ---------------------------------------------------------------------------
// Revenue — the line that names where the number came from.
//
// A band inferred from headcount and a band read off a filing are not the same
// claim, and the rep deciding whether to trust a B is the person who needs to
// know which one this is.
// ---------------------------------------------------------------------------
const revenue = components.revenue_range || {};
const revenueBits = [`Revenue ${levels.revenue_range}`];
if (revenue.revenue_band_used) revenueBits.push(revenue.revenue_band_used);
if (revenue.revenue_source) revenueBits.push(`via ${revenue.revenue_source}`);
let revenueLine = revenueBits.join(' ');
const discarded = (revenue.evidence || []).filter((e) => /discard|rejected|ignored/i.test(e));
if (discarded.length > 0) revenueLine += ` (${discarded[0]})`;

// The table reports a disagreement between two sources here rather than
// resolving it silently. It never touches the score; it explains it.
const conflictLine = parsed.conflict_note ? `Conflict: ${parsed.conflict_note}` : null;

// Missing / low confidence. Mandatory and non-empty on insufficient_data.
const missingBits = [];
for (const component of Object.keys(components)) {
  const c = components[component];
  // A component the table computed carries no confidence label at all. That is
  // not "low" — there was no classifier to be unsure — so it contributes
  // nothing to this line.
  if (c.computed_by_table) continue;
  const missing = c.missing_inputs || [];
  const parts = [];
  if (missing.length > 0) parts.push(missing.join(', '));
  if (c.confidence === 'low') parts.push('low confidence');
  else if (c.confidence === 'medium') parts.push('medium confidence');
  if (parts.length > 0) missingBits.push(`${component} (${parts.join('; ')})`);
}
// The component that made this insufficient_data may have no classifier object
// at all in v6 — revenue_range is computed by the table — so the reason would
// otherwise be invisible in the very note that says "Insufficient data". The
// table names them in a flag; this reads them back out.
for (const flag of score.flags || []) {
  const match = /^insufficient:(.+)$/.exec(flag);
  if (!match) continue;
  for (const name of match[1].split(',')) {
    const component = name.trim();
    if (component === '') continue;
    if (missingBits.some((bit) => bit.indexOf(`${component} (`) === 0)) continue;
    missingBits.push(`${component} (insufficient)`);
  }
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
  revenueLine,
  hiringLine,
  activationLine,
  compositeLine,
  referenceLine,
  ...(conflictLine === null ? [] : [conflictLine]),
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
