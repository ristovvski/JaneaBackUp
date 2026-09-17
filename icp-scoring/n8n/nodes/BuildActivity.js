// BuildActivity — the one activity a scoring run leaves on the organization.
//
// Body rules (§2): plain words, discarded inputs written as sentences, an
// activation block, exactly one CHECK line, no raw field names, <= 900 chars.
//
// "No raw field names" is the rule that shapes everything else. The evidence
// the table sends is full of them — `li_industry: Financial Services`,
// `apollo.funding_events[0].date: 2025-09-01` — so this node does NOT pass
// evidence through and try to clean it. It writes the note from the STRUCTURED
// facts in its own words, and touches evidence in exactly one place: the
// discarded-input sentences, where the value is the point and the prefix is
// stripped. Anything it cannot say in plain words, it does not say.
//
// Level text comes from CONFIG.component_scales, generated from
// config/rubric_v6.json, so no rubric prose is typed into this node.
//
// The budget is enforced by dropping whole sentences in a fixed order, so two
// runs on the same input produce the same note rather than the same note cut
// at a different place.

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
const parsed = $('Score').item.json;

const score = parsed.score;
const c = parsed.components;
const hiring = parsed.hiring || {};
const apollo = parsed.apollo_summary || {};
const levels = score.levels;
const MAX = cfg.activity_max_chars || 900;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

/** The rubric's own words for a level, with its parenthetical trimmed off. */
const levelText = (component, level) => {
  const scale = cfg.component_scales[component] || {};
  const text = scale[String(level)];
  if (text === undefined) return null;
  return String(text).replace(/\s*\([^)]*\)\s*$/, '').trim();
};

/** Strip a leading `some.path[0]:` label, which is the raw-field-name form. */
const valueOf = (evidence) => {
  const text = String(evidence || '').trim();
  const m = /^[A-Za-z_][A-Za-z0-9_.\[\]]*\s*:\s*(.+)$/.exec(text);
  return (m ? m[1] : text).trim();
};

// Provider names are proper nouns a rep recognises, not raw field names, so
// they are capitalised rather than stripped. Anything not on this list stays
// exactly as the table wrote it.
const PROVIDERS = { apollo: 'Apollo', linkedin: 'LinkedIn', clay: 'Clay', crunchbase: 'Crunchbase' };
const properNouns = (text) => String(text).replace(
  /\b(apollo|linkedin|clay|crunchbase)\b/gi,
  (word) => PROVIDERS[word.toLowerCase()]
);

/**
 * "apollo revenue $1.1M discarded: $12k/employee"
 *   -> "We set aside Apollo revenue $1.1M — $12k/employee."
 *
 * The table writes these as "<what> discarded: <why>", so the verb is the
 * split point and both halves are kept — the why is the part that makes the
 * sentence worth reading.
 */
const discardSentence = (evidence) => {
  const text = properNouns(valueOf(evidence));
  const m = /^(.*?)\s*\b(?:discarded|rejected|ignored|overridden)\b\s*:?\s*(.*)$/i.exec(text);
  if (!m) return sentence(`We set aside ${text}`);
  const what = m[1].trim();
  const why = m[2].trim();
  if (what === '') return sentence(`We set aside one input${why ? ` — ${why}` : ''}`);
  return sentence(`We set aside ${what}${why ? ` — ${why}` : ''}`);
};

const sentence = (text) => {
  const t = String(text || '').trim().replace(/\s+/g, ' ');
  if (t === '') return null;
  const capped = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(capped) ? capped : `${capped}.`;
};

// Source codes are for machines; this note is for a person.
const REVENUE_SOURCE_WORDS = {
  headcount_band: 'inferred from headcount rather than read from a filing',
  apollo_revenue: "taken from Apollo's revenue figure",
  filing: 'read from a public filing',
  manual: 'entered by hand',
};
const revenueSourceWords = (source) => {
  if (!source) return null;
  return REVENUE_SOURCE_WORDS[source] || `from ${String(source).replace(/_/g, ' ')}`;
};

// ---------------------------------------------------------------------------
// Headline
// ---------------------------------------------------------------------------
const insufficient = score.status === 'insufficient_data';
const headline = insufficient
  ? 'Not scored — not enough was found to judge this company.'
  : `ICP ${score.grade} — ${score.final_score} out of 100.`;

// ---------------------------------------------------------------------------
// What it is. One sentence per thing a rep would ask about.
// ---------------------------------------------------------------------------
const profile = [];

const vertical = c.industry_vertical.value;
if (vertical && levels.industries > 0) {
  const tier = (cfg.vertical_tier || {})[vertical];
  profile.push(sentence(
    tier ? `${vertical}, ${String(tier).toLowerCase()} for us` : `${vertical}`
  ));
} else if (vertical) {
  profile.push(sentence(`${vertical}, which is outside our rubric, so industry counted for nothing`));
} else {
  profile.push(sentence('The vertical could not be determined'));
}

const typeWords = levelText('company_type', levels.company_type);
if (typeWords) profile.push(sentence(typeWords));

const geoWords = levelText('geography', levels.geography);
if (geoWords) profile.push(sentence(geoWords));

const band = c.revenue_range.revenue_band_used;
const sourceWords = revenueSourceWords(c.revenue_range.revenue_source);
if (band) {
  profile.push(sentence(sourceWords ? `Revenue around ${band}, ${sourceWords}` : `Revenue around ${band}`));
} else {
  profile.push(sentence('Revenue could not be established'));
}

const stageWords = levelText('stage_maturity', levels.stage_maturity);
if (stageWords) profile.push(sentence(stageWords));

// Hiring: three states, and collapsing any two of them is a lie a rep acts on.
if (hiring.eng_open === null || hiring.eng_open === undefined) {
  profile.push(sentence('No job postings were found, which is not the same as none being open'));
} else if (hiring.dates_available === false) {
  profile.push(sentence(
    `${hiring.eng_open} engineering ${hiring.eng_open === 1 ? 'role' : 'roles'} open, with no posting dates available`
  ));
} else {
  const leader = (hiring.leader_titles || [])[0];
  const older = hiring.eng_open_60d_plus;
  const bits = [`${hiring.eng_open} engineering ${hiring.eng_open === 1 ? 'role' : 'roles'} open`];
  if (older !== null && older !== undefined && older > 0) bits.push(`${older} of them for more than two months`);
  if (leader) bits.push(`an engineering lead in post (${leader})`);
  profile.push(sentence(bits.join(', ')));
}

// ---------------------------------------------------------------------------
// Discarded inputs, as sentences. This is the ONE place evidence is quoted,
// and the label is stripped off it first.
// ---------------------------------------------------------------------------
const discarded = [];
for (const name of Object.keys(c)) {
  for (const item of c[name].evidence || []) {
    if (!/discard|rejected|ignored|overrid/i.test(item)) continue;
    discarded.push(discardSentence(item));
  }
}

// ---------------------------------------------------------------------------
// Activation block
// ---------------------------------------------------------------------------
const activation = [];
const multiplier = Number(score.multiplier);
if (multiplier === 1) {
  activation.push(sentence(`Activation: ${String(score.activation_state_used).toLowerCase()}, so the score stands in full`));
} else if (multiplier === 0) {
  activation.push(sentence('Activation: contracting, which zeroes the score'));
  activation.push(sentence(`Without that it would have been ${score.final_score_without_activation}`));
} else {
  activation.push(sentence(
    `Activation: ${String(score.activation_state_used).toLowerCase()}, which takes the score down from ` +
    `${score.final_score_without_activation} to ${score.final_score}`
  ));
}
if (score.contracting_guard_applied) {
  activation.push(sentence(
    'The classifier called this contracting, but nothing backed it up, so it was not applied'
  ));
}

// ---------------------------------------------------------------------------
// Exactly one CHECK line. The most load-bearing doubt, in precedence order —
// a note with three CHECK lines has none.
// ---------------------------------------------------------------------------
const lowConfidence = Object.keys(c)
  .filter((name) => c[name].confidence === 'low' && name !== 'buying_signal');

let check;
if (insufficient) {
  const gaps = (score.flags || [])
    .filter((f) => f.indexOf('insufficient:') === 0)
    .map((f) => f.slice('insufficient:'.length).split(',').join(', ').replace(/_/g, ' '));
  check = `CHECK: too little was found to score this${gaps.length ? ` (${gaps[0]})` : ''} — worth a look by hand.`;
} else if ((score.flags || []).indexOf('unknown_vertical') !== -1) {
  check = 'CHECK: the vertical is not in our rubric, so industry contributed nothing to this score — decide whether it belongs there.';
} else if (score.contracting_guard_applied) {
  check = 'CHECK: the contracting call was not backed by the headcount trend — confirm before writing the account off.';
} else if (c.revenue_range.revenue_source === 'headcount_band' || c.revenue_range.confidence === 'low') {
  check = 'CHECK: the revenue band is an estimate from headcount, not a filing — confirm before sizing a deal.';
} else if (lowConfidence.length > 0) {
  check = `CHECK: ${lowConfidence[0].replace(/_/g, ' ')} was a low-confidence call — worth a look before acting.`;
} else if (score.tier2_candidate) {
  check = 'CHECK: large enough to be relationship-gated rather than score-led.';
} else {
  check = 'CHECK: nothing stood out; the inputs were complete.';
}

// ---------------------------------------------------------------------------
// Assemble, and fit the budget by dropping whole sentences in a fixed order.
// The headline, the activation block and the CHECK line are never dropped —
// they are the note's job. Profile detail goes first, from the end.
// ---------------------------------------------------------------------------
const assemble = (profileCount, discardedCount) => [
  headline,
  profile.slice(0, profileCount).filter(Boolean).join(' '),
  discarded.slice(0, discardedCount).filter(Boolean).join(' '),
  activation.filter(Boolean).join(' '),
  check,
].filter((block) => block && block !== '').join('\n\n');

let body = assemble(profile.length, discarded.length);
let profileCount = profile.length;
let discardedCount = discarded.length;
while (body.length > MAX && (profileCount > 0 || discardedCount > 0)) {
  if (discardedCount > profileCount) discardedCount -= 1;
  else profileCount -= 1;
  body = assemble(profileCount, discardedCount);
}
// Last resort. Every block above is short, so reaching this means a single
// value from the table is pathological.
if (body.length > MAX) body = `${body.slice(0, MAX - 1)}…`;

return [{
  json: {
    request_id: parsed.request_id,
    org_id: parsed.org_id,
    deal_id: parsed.deal_id,
    subject: cfg.activity_subject,
    type: cfg.activity_type,
    done: true,
    body,
    body_length: body.length,
    check_line: check,
    dropped_sentences: (profile.length - profileCount) + (discarded.length - discardedCount),
  },
}];
