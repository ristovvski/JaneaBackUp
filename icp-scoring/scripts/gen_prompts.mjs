#!/usr/bin/env node
// scripts/gen_prompts.mjs — write engine/prompts/*.md from config/rubric_v5.json.
//
// The level definitions are the business rubric. Hand-copying them into seven
// prompt files is exactly the drift that tests/contract/prompts.test.mjs
// exists to catch, so the prose lives here and the rubric text is spliced in.
// Changing a level definition means editing config/rubric_v5.json and running
// `npm run gen:prompts`. The contract test fails if the files are stale.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const RUBRIC = JSON.parse(readFileSync(join(ROOT, 'config', 'rubric_v5.json'), 'utf8'));
const OUT = join(ROOT, 'engine', 'prompts');

// The fenced block the contract test parses. Keep the label stable.
const ALLOWED = 'allowed-values';

/** Render the 10/7/3/0 ladder for a component, verbatim from the rubric. */
function levelLadder(component) {
  const scale = RUBRIC.component_scales[component];
  if (!scale) throw new Error(`no component_scales entry for "${component}"`);
  return ['10', '7', '3', '0'].map((level) => `- \`${level}\` — ${scale[level]}`).join('\n');
}

/** Render the named-value ladder (activation_state), verbatim from the rubric. */
function namedLadder(component) {
  const scale = RUBRIC.component_scales[component];
  return Object.entries(scale).map(([name, text]) => `- \`${name}\` — ${text}`).join('\n');
}

function fenced(values) {
  return ['```' + ALLOWED, ...values, '```'].join('\n');
}

const WEIGHTS = RUBRIC.weights;

// ---------------------------------------------------------------------------
// The hand-written half: what each classifier is for, which facts to read,
// and how to break ties. One entry per component.
// ---------------------------------------------------------------------------

const COMPONENTS = {
  industry_vertical: {
    weight: WEIGHTS.industries,
    title: 'Industry vertical',
    task: 'Assign the company to exactly one of the 17 Janea ICP verticals.',
    body() {
      const rows = Object.entries(RUBRIC.industry_verticals)
        .map(([name, row]) => {
          const note = row.note ? ` — ${row.note}` : '';
          const tier2 = row.tier2_path ? ' *(Tier 2 path)*' : '';
          return `| ${name} | ${row.tier} | ${row.total} |${note ? ` ${row.note}` : ' '}${tier2} |`;
        })
        .join('\n');

      return `## Allowed values

Return one of these strings, byte for byte, or \`null\`. Any other string is a
schema violation and the row will be rejected.

${fenced(Object.keys(RUBRIC.industry_verticals))}

## What each vertical means to us

The tier is why the vertical scores what it scores: it is the sum of five
sub-rubric dimensions (named wins, capability proof, team domain depth, market
size, engagement history). You do not need to reproduce the tier — pick the
vertical and the engine derives the rest.

| Vertical | Tier | Sub-rubric total | Reference accounts / note |
|---|---|---|---|
${rows}

## How to decide

1. Read \`li_industry\`, \`li_description\` and \`website_summary\`. What does the
   company *sell*, not what technology it happens to use.
2. A company that sells software **to** a vertical belongs to that vertical
   (a lending platform for credit unions is \`FinTech\`, not \`SaaS — Other\`).
3. \`SaaS — Other\` is the fallback for a software-native company whose market is
   not one of the named verticals. It is not a shrug: only use it when the
   company genuinely sells software.
4. \`Analytics / ML\` and \`Data Platform SaaS\` describe what the product *is*.
   Prefer the more specific of the two; prefer a named market vertical over both.
5. A hyperscaler, or an enterprise whose software is internal-only at that
   scale, is \`Enterprise Tech / Hyperscalers\`.
6. If the facts genuinely do not say what the company sells, return \`null\` with
   \`confidence: "low"\` and name the missing facts. Do not guess from the name.`;
    },
  },

  stage_maturity: {
    weight: WEIGHTS.stage_maturity,
    title: 'Stage / maturity',
    task: 'Score how much the company\'s stage creates demand for external engineering capacity.',
    body() {
      return `## Levels

${levelLadder('stage_maturity')}

## How to decide

1. Read \`funding_stage\`, \`last_round_date\`, \`last_round_usd\`, \`li_headcount\`,
   \`eng_headcount_estimate\`, \`open_eng_roles_count\`, \`eng_roles_open_60d_plus\`
   and \`news_last_12mo\`.
2. The axis is **capacity pressure**, not size. A Series C company that has
   already built the team it needs is not a 10; a mature company with roles open
   past 60 days and a public roadmap commitment can be.
3. \`eng_roles_open_60d_plus > 0\` is the strongest available proxy for a
   *documented capacity gap*. Cite it when you use it.
4. "Fully self-sufficient enterprise" is the 0 that catches the large accounts:
   tens of thousands of engineers and no evidence of outsourcing.
5. Funding stage alone is never enough for a 10 — pair it with either open
   roles or a dated roadmap/hiring signal from \`news_last_12mo\`.
6. No funding data and no hiring data → \`null\`, \`confidence: "low"\`, and list
   both as missing. This component gates \`insufficient_data\`, so a guess here
   is more expensive than an admission.`;
    },
  },

  company_type: {
    weight: WEIGHTS.company_type,
    title: 'Company type',
    task: 'Score how central custom software engineering is to what the company sells.',
    body() {
      return `## Levels

${levelLadder('company_type')}

## How to decide

1. Read \`li_description\`, \`website_summary\`, \`li_industry\`.
2. The question is who owns the product software. A company whose product *is*
   software is a 10. A company whose product depends on mission-critical
   software it must build itself is a 7.
3. Level \`7\` also raises the Tier 2 flag downstream, so use it deliberately:
   regulated industries, pharma, banking cores — software-dependent, not
   software-native.
4. Hardware with a real software layer (embedded, device firmware, a companion
   platform) is a 3. Hardware with only an IT department is a 0.
5. "IT-led" means no engineering organization owns a shipped product. An
   internal-tools team is not a product engineering organization.
6. No description and no site summary → \`null\`, \`confidence: "low"\`. This
   component gates \`insufficient_data\`.`;
    },
  },

  geography: {
    weight: WEIGHTS.geography,
    title: 'Geography',
    task: 'Score the headquarters region.',
    body() {
      return `## Levels

${levelLadder('geography')}

## How to decide

1. Read \`hq_country\`, \`hq_state\`, \`li_hq\`. Prefer \`hq_country\` when they disagree,
   and say in the evidence which you used.
2. Score the **headquarters**, not the largest office and not the incorporation
   country.
3. Western Europe for level \`7\` means: Austria, Belgium, Denmark, Finland,
   France, Germany, Iceland, Ireland, Italy, Luxembourg, Netherlands, Norway,
   Portugal, Spain, Sweden, Switzerland. Canada scores \`7\` alongside them.
4. The UK is named at level \`3\`, with AU, NZ and Singapore — not at \`7\`.
   Follow the rubric text, not intuition about the UK's proximity to the EU.
5. Everything else is \`0\`.
6. No location facts at all → \`null\`, \`confidence: "low"\`. Geography does **not**
   gate \`insufficient_data\`, so a null here costs 10 weight and nothing more.

> **Deviation on record (NEEDS_DECISION #3).** The signed rubric qualifies levels
> 10 and 7 with "within network reach" / "with network coverage". Network reach
> is not derivable from any enrichment fact, so this classifier scores by region
> alone. Do not attempt to infer network coverage.`;
    },
  },

  revenue_range: {
    weight: WEIGHTS.revenue_range,
    title: 'Revenue range',
    task: 'Score the revenue band, which stands in for buyer infrastructure.',
    body() {
      return `## Levels

${levelLadder('revenue_range')}

## How to decide

1. Read \`revenue_estimate_usd\` and \`revenue_source\`. Always cite the source: an
   Apollo estimate and a reported figure are not the same evidence.
2. The band is non-monotonic on purpose. Both "under $10M" and "over $500M" are
   a \`3\`, and "over $1B" drops to \`0\`. Read the boundaries from the text above
   rather than assuming bigger is better.
3. Boundary handling: a value that sits exactly on a boundary belongs to the
   band the rubric text names first. \`$25M\` is a \`10\`; \`$10M\` is a \`7\`;
   \`$500M\` is a \`10\`; \`$500,000,001\` is a \`3\`.
4. When only a headcount is available, do **not** convert it to revenue. Return
   \`null\` with \`confidence: "low"\` and \`missing_inputs: ["revenue_estimate_usd"]\`.
   A revenue guessed from headcount is the single most damaging error this
   system can make: it carries ${WEIGHTS.revenue_range} of the 100 weight.
5. Pre-revenue must be evidenced (pre-product, pre-seed, stealth), not inferred
   from an absent estimate.
6. This component gates \`insufficient_data\`.`;
    },
  },

  activation_state: {
    weight: null, // a multiplier, not a weighted component
    title: 'Activation state',
    task: 'Classify the company\'s current direction of travel. This becomes a multiplier on the whole composite, not a weighted component.',
    body() {
      const mult = Object.entries(RUBRIC.activation_multipliers)
        .map(([state, m]) => `| \`${state}\` | ×${m.toFixed(2)} |`).join('\n');
      return `## Allowed values

${fenced(Object.keys(RUBRIC.component_scales.activation_state))}

## What each state means

${namedLadder('activation_state')}

## What it costs

| State | Multiplier on the composite |
|---|---|
${mult}

\`Contracting\` zeroes the score outright. \`Stable\` costs 15%. This is the only
component that can move a score by more than its own weight, so the evidence
bar is correspondingly higher.

## How to decide

1. Read \`news_last_12mo\` (each item carries a date), \`last_round_date\`,
   \`open_eng_roles_count\`, \`eng_roles_open_60d_plus\`, \`senior_eng_roles\`.
2. \`Accelerating\` and \`Transitioning\` both need a dated event. A funding round,
   a named exec change, a re-platforming announcement, a hiring cluster.
3. **\`Contracting\` requires an evidence item with a date within
   ${RUBRIC.activation_contracting_evidence_max_age_months} months.** Set
   \`evidence_dated_within_months\` to the age in months of that item. Without it,
   return \`${RUBRIC.activation_default_when_no_evidence}\` instead — an undated
   layoff rumour must never zero a score.
4. \`${RUBRIC.activation_default_when_no_evidence}\` is the default when nothing is
   dated either way. It is a real answer, not a failure: return it with the
   confidence the facts support rather than returning \`null\`.
5. Layoffs *and* a funding round in the same window: prefer \`Transitioning\` and
   cite both. Restructuring is not the same as decline.`;
    },
  },

  buying_signal: {
    weight: WEIGHTS.buying_signal,
    title: 'Buying signal',
    task: 'Score the current buying signal. Logged for the rep, not scored — the weight is 0 in v5.',
    body() {
      return `## Levels

${levelLadder('buying_signal')}

## How this is used

The weight of this component is \`${WEIGHTS.buying_signal}\`. It **cannot** move the
composite, the final score or the grade. It is written to the note and the audit
row so a rep can see why an account is worth a call this week, and so that a
future rubric version has a scored history to calibrate against.

Score it honestly. Inflating it does not help anyone and pollutes the history.

## How to decide

1. Read \`open_eng_roles_count\`, \`eng_roles_open_60d_plus\`, \`senior_eng_roles\`,
   \`last_round_date\`, \`last_round_usd\`, \`news_last_12mo\`.
2. "Compound" at level \`10\` means genuinely several independent signals: a
   posting cluster **and** (a funding event **or** an exec change) **and**
   tech-stack investment. Two of the three is a \`7\`.
3. "Current window" means the last 12 months. A two-year-old round is not a
   signal; say so in the evidence rather than silently discounting it.
4. \`0\` is a legitimate and common answer. Prefer it to inventing a weak signal.
5. Absent job and news data → \`null\`, \`confidence: "low"\`. This component does
   not gate \`insufficient_data\`.`;
    },
  },
};

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

const GENERATED_BANNER = `<!-- GENERATED by scripts/gen_prompts.mjs from config/rubric_v5.json. Do not edit by hand:
     tests/contract/prompts.test.mjs fails if this file is stale or if a level
     definition does not match the rubric byte for byte. -->`;

const HEADER = (component, spec) => {
  // activation_state is a multiplier on the composite, not a weighted
  // component, so it has no "N of 100" — claiming one would be a lie the
  // contract test now catches.
  const role = spec.weight === null
    ? '**Applies as:** multiplier on the composite'
    : `**Weight:** ${spec.weight} of 100`;
  return `${GENERATED_BANNER}

# ICP v5 classifier — ${spec.title}

**Component:** \`${component}\`  ·  ${role}  ·  **Model version:** ${RUBRIC.model_version}

${spec.task}

`;
};

const FOOTER = (component) => `

## Output

Return a single JSON object and nothing else:

\`\`\`json
{
  "component": "${component}",
  "value": <${component === 'industry_vertical' || component === 'activation_state' ? 'see Allowed values above' : 'one of 10 | 7 | 3 | 0 | null'}>,
  "evidence": ["<fact_key>: <value>", "..."],
  "confidence": "high" | "medium" | "low",
  "missing_inputs": ["<fact_key>", "..."]${component === 'activation_state' ? ',\n  "evidence_dated_within_months": <integer or null>' : ''}
}
\`\`\`

\`component\` must be exactly \`"${component}"\`. The object is validated against
\`engine/schemas/classifier_output.schema.json\`; a violation fails the row.
`;

// ---------------------------------------------------------------------------
// The shared preamble. Generated for the same reason the components are: the
// Contracting window and the three gating components are rubric facts, and a
// hand-typed copy is a copy that goes stale.
// ---------------------------------------------------------------------------

function preamble() {
  const months = RUBRIC.activation_contracting_evidence_max_age_months;
  const fallback = RUBRIC.activation_default_when_no_evidence;
  const gating = RUBRIC.insufficient_data_rule.components;
  const gatingList = gating.map((c) => `\`${c}\``).join(', ').replace(/, ([^,]*)$/, ' and $1');

  return `${GENERATED_BANNER}

# ICP v5 classifier — shared rules

You are one of seven classifiers in Janea's ICP scoring engine. You are given a
fixed set of **enrichment facts** about one company and you return **one JSON
object** describing exactly one component of the rubric.

You do not compute the score. You do not see the other classifiers' answers.
You do not decide whether the company is a good fit. You read the facts, apply
the level definitions you are given, and say what you can defend.

---

## 1. The facts are all you have

- Use **only** the facts in the provided \`facts_json\` object. It is validated
  against \`engine/schemas/enrichment_facts.schema.json\`.
- **Never browse. Never assume. Never fill a gap from prior knowledge**, even
  when you recognise the company. If you know something about the company that
  is not in the facts, it is not evidence, and using it makes the score
  unreproducible for the next person who looks at the row.
- A fact that is \`null\` means enrichment did not find it. It does not mean the
  value is zero, absent or small. Treat \`revenue_estimate_usd: null\` as "we do
  not know the revenue", never as "pre-revenue".
- An empty array (\`news_last_12mo: []\`) *is* evidence: we looked and found
  nothing in the window.

## 2. Insufficient facts is an answer

If the facts do not support a defensible answer:

- set \`value\` to \`null\`,
- set \`confidence\` to \`"low"\`,
- list the fact keys you needed in \`missing_inputs\`.

${gating.length} components — ${gatingList} — gate the whole scoring run: a
\`null\`, or a low-confidence answer with missing inputs, on any of them marks
the organization **Insufficient data** rather than grading it. That is the
correct outcome. A confident guess that turns out wrong costs the sales team a
wasted call and costs the model its credibility; an honest \`null\` costs one
enrichment retry.

Do not pad \`missing_inputs\` with keys you did not actually need.

## 3. Confidence means something specific

| Value | Use it when |
|---|---|
| \`high\` | A fact states the answer directly, or two facts agree. |
| \`medium\` | You inferred it from adjacent facts and the inference is sound but not stated. |
| \`low\` | You are extrapolating, the facts conflict, or a fact you needed is \`null\`. |

Confidence is about the **evidence**, not about how you feel. Two facts that
contradict each other is \`low\`, however plausible your reading of them is.

## 4. Cite every evidence item as \`<fact_key>: <value>\`

Each string in \`evidence\` names the fact it came from:

\`\`\`
"funding_stage: Series B"
"eng_roles_open_60d_plus: 4"
"li_hq: Austin, Texas, United States"
\`\`\`

Not \`"they raised a Series B"\`. The prefix is what lets a rep click back to the
Clay column and a reviewer audit the score six months later. Keep each item
under 200 characters, at most 6 items, and quote the fact rather than
paraphrasing it. If you truncate a long value, end with \`…\`.

Evidence for a level you did **not** choose is welcome when it explains a close
call — say which way it cut.

## 5. \`Contracting\` requires a dated fact

For \`activation_state\` only: return \`Contracting\` **only** when you can cite an
evidence item carrying a date within the last **${months}** months (layoffs, a
hiring freeze, cost-cutting, declining reported metrics). Set
\`evidence_dated_within_months\` to that item's age in months.

Without such an item, return \`${fallback}\`.

\`Contracting\` multiplies the entire composite by
${RUBRIC.activation_multipliers.Contracting}. An undated rumour, a sector-wide
news story, or a "seems quiet" impression must never do that to an account. The
engine independently downgrades an undated \`Contracting\` to \`${fallback}\` and
flags it, so returning one anyway does not sneak it through — it just adds noise
to the audit trail.

## 6. Return JSON only

- One JSON object. No markdown fence, no preamble, no trailing commentary.
- \`component\` must be exactly the component name given in your prompt.
- The object is validated against
  \`engine/schemas/classifier_output.schema.json\`. \`additionalProperties\` is
  \`false\`: an extra key fails the row.
- \`value\` must be one of the allowed values for your component — a level
  (${RUBRIC.levels.slice().reverse().map((l) => `\`${l}\``).join(', ')}) as a
  **number**, one of the named strings, or \`null\`. \`"10"\` as a string is a
  violation.
- Temperature is 0. The same facts must produce the same object.

## 7. What you are not asked to do

- You are not asked for a grade, a band, a percentage or a recommendation.
- You are not asked to compare this company to another.
- You are not asked to be encouraging. The rubric has levels of \`0\` and they
  are used.
- You are not asked to apply the weights. \`buying_signal\` carries weight
  ${RUBRIC.weights.buying_signal} in ${RUBRIC.model_version} and is logged, not
  scored — score it honestly anyway.
`;
}

writeFileSync(join(OUT, '_preamble.md'), preamble(), 'utf8');
process.stdout.write(`wrote engine/prompts/_preamble.md (${preamble().length} bytes)\n`);

let written = 0;
for (const [component, spec] of Object.entries(COMPONENTS)) {
  const text = HEADER(component, spec) + spec.body() + FOOTER(component);
  writeFileSync(join(OUT, `${component}.md`), text, 'utf8');
  written += 1;
  process.stdout.write(`wrote engine/prompts/${component}.md (${text.length} bytes)\n`);
}
process.stdout.write(`\n${written} component prompts generated from rubric ${RUBRIC.model_version}.\n`);
