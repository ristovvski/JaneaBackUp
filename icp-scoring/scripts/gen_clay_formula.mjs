#!/usr/bin/env node
// scripts/gen_clay_formula.mjs — write engine/clay_formula.txt from config/rubric_v5.json.
//
// Clay runs the score in a formula column; n8n and the tests run
// engine/scoring.mjs. Two implementations of one rubric is a drift machine, so
// every constant below is read from the rubric and inlined, and
// tests/contract/clay_parity.test.mjs asserts the generated body returns
// deep-equal results to score() on the golden inputs plus random inputs.
//
// Run: npm run gen:formula   (the contract test fails if the file is stale)

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const RUBRIC = JSON.parse(readFileSync(join(ROOT, 'config', 'rubric_v5.json'), 'utf8'));

// The markers the parity test slices between. Keep them byte-stable.
export const BEGIN = '/* ---8<--- BEGIN PORTABLE BODY (parity-tested; do not edit) --- */';
export const END = '/* ---8<--- END PORTABLE BODY --- */';

const j = (v) => JSON.stringify(v);

// Industry vertical -> level, flattened through the tier so Clay does not need
// the tier table at runtime.
const verticalToLevel = {};
for (const [name, row] of Object.entries(RUBRIC.industry_verticals)) {
  verticalToLevel[name] = RUBRIC.industry_vertical_map[row.tier];
}
const verticalToTier = {};
for (const [name, row] of Object.entries(RUBRIC.industry_verticals)) {
  verticalToTier[name] = row.tier;
}

const body = `${BEGIN}
// Generated from config/rubric_v5.json — model ${RUBRIC.model_version}. Do not hand-edit.
var RUBRIC = {
  model_version: ${j(RUBRIC.model_version)},
  weights: ${j(RUBRIC.weights)},
  levels: ${j(RUBRIC.levels)},
  thresholds: ${j(RUBRIC.thresholds)},
  multipliers: ${j(RUBRIC.activation_multipliers)},
  activation_default: ${j(RUBRIC.activation_default_when_no_evidence)},
  contracting_max_age_months: ${j(RUBRIC.activation_contracting_evidence_max_age_months)},
  gating: ${j(RUBRIC.insufficient_data_rule.components)},
  tier2: ${j(RUBRIC.tier2_flag_rule)},
  vertical_level: ${j(verticalToLevel)},
  vertical_tier: ${j(verticalToTier)}
};

var WEIGHT_KEY_TO_LEVEL_KEY = {
  industries: 'industry',
  stage_maturity: 'stage_maturity',
  revenue_range: 'revenue_range',
  company_type: 'company_type',
  geography: 'geography',
  buying_signal: 'buying_signal'
};

var CONFIDENCE_RANK = { low: 0, medium: 1, high: 2 };

function roundHalfUp(x) {
  if (x === null || x === undefined || isNaN(x)) return null;
  return Math.floor(Number(x.toFixed(10)) + 0.5);
}

function resolveLevel(raw) {
  if (raw === null || raw === undefined) return 0;
  if (RUBRIC.levels.indexOf(raw) === -1) {
    throw new Error('level ' + JSON.stringify(raw) + ' is not one of ' + JSON.stringify(RUBRIC.levels));
  }
  return raw;
}

var flags = [];
var levels = (inputs && inputs.levels) || {};
var confidence = (inputs && inputs.confidence) || {};
var missingInputs = (inputs && inputs.missing_inputs) || {};
var facts = (inputs && inputs.facts_summary) || {};

// --- industry vertical -> level ------------------------------------------
var vertical = inputs ? inputs.industry_vertical : null;
var known = vertical !== null && vertical !== undefined &&
            Object.prototype.hasOwnProperty.call(RUBRIC.vertical_level, vertical);
var industryLevel = known ? RUBRIC.vertical_level[vertical] : 0;
var industryTier = known ? RUBRIC.vertical_tier[vertical] : null;
var industryConfidence = confidence.industry_vertical;
if (!known) { flags.push('unknown_vertical'); industryConfidence = 'low'; }

var levelsUsed = {
  industry: industryLevel,
  stage_maturity: resolveLevel(levels.stage_maturity),
  company_type: resolveLevel(levels.company_type),
  geography: resolveLevel(levels.geography),
  revenue_range: resolveLevel(levels.revenue_range),
  buying_signal: resolveLevel(levels.buying_signal)
};

// --- composite ------------------------------------------------------------
var composite = 0;
var weightKeys = Object.keys(RUBRIC.weights);
for (var wi = 0; wi < weightKeys.length; wi++) {
  var wk = weightKeys[wi];
  composite += (RUBRIC.weights[wk] * levelsUsed[WEIGHT_KEY_TO_LEVEL_KEY[wk]]) / 10;
}
composite = Number(composite.toFixed(10));

// --- activation state -----------------------------------------------------
var activationStateUsed = (inputs && inputs.activation_state)
  ? inputs.activation_state
  : RUBRIC.activation_default;

if (activationStateUsed === 'Contracting') {
  var age = inputs ? inputs.activation_evidence_dated_within_months : null;
  var dated = (typeof age === 'number') && age <= RUBRIC.contracting_max_age_months;
  if (!dated) {
    activationStateUsed = RUBRIC.activation_default;
    flags.push('contracting_without_dated_evidence');
  }
}

var multiplier = RUBRIC.multipliers[activationStateUsed];
if (multiplier === undefined) throw new Error('unknown activation_state "' + activationStateUsed + '"');

var finalScore = roundHalfUp(composite * multiplier);
var finalScoreWithoutActivation = roundHalfUp(composite);

// --- insufficient data ----------------------------------------------------
var insufficient = [];
for (var gi = 0; gi < RUBRIC.gating.length; gi++) {
  var c = RUBRIC.gating[gi];
  var lvl = levels[c];
  if (lvl === null || lvl === undefined) { insufficient.push(c); continue; }
  var miss = missingInputs[c];
  if (confidence[c] === 'low' && Object.prototype.toString.call(miss) === '[object Array]' && miss.length > 0) {
    insufficient.push(c);
  }
}
var status = insufficient.length > 0 ? 'insufficient_data' : 'scored';
if (status === 'insufficient_data') flags.push('insufficient:' + insufficient.join(','));

// --- grade ----------------------------------------------------------------
var grade = null;
if (status !== 'insufficient_data') {
  if (finalScore >= RUBRIC.thresholds.A) grade = 'A';
  else if (finalScore >= RUBRIC.thresholds.B) grade = 'B';
  else grade = 'C';
}

// --- overall confidence over the weighted components ----------------------
var weighted = [];
for (var wj = 0; wj < weightKeys.length; wj++) {
  if (RUBRIC.weights[weightKeys[wj]] > 0) {
    weighted.push(weightKeys[wj] === 'industries' ? 'industry_vertical' : weightKeys[wj]);
  }
}
var worst = 'high';
for (var ci = 0; ci < weighted.length; ci++) {
  var label = weighted[ci] === 'industry_vertical' ? industryConfidence : confidence[weighted[ci]];
  var effective = CONFIDENCE_RANK[label] === undefined ? 'low' : label;
  if (CONFIDENCE_RANK[effective] < CONFIDENCE_RANK[worst]) worst = effective;
}

// --- tier 2 ---------------------------------------------------------------
var revenue = facts.revenue_usd;
var headcount = facts.headcount_total;
var tier2Candidate = Boolean(
  (typeof revenue === 'number' && revenue > RUBRIC.tier2.revenue_usd_gt) ||
  (typeof headcount === 'number' && headcount > RUBRIC.tier2.headcount_gt) ||
  levelsUsed.company_type === RUBRIC.tier2.company_type_level_eq
);
if (tier2Candidate) flags.push('tier2_candidate');

return {
  model_version: RUBRIC.model_version,
  industry_level: industryLevel,
  industry_tier: industryTier,
  levels_used: levelsUsed,
  buying_signal_level: levels.buying_signal === undefined ? null : levels.buying_signal,
  composite: composite,
  activation_state_used: activationStateUsed,
  multiplier: multiplier,
  final_score: finalScore,
  final_score_without_activation: finalScoreWithoutActivation,
  grade: grade,
  status: status,
  confidence_overall: worst,
  tier2_candidate: tier2Candidate,
  flags: flags
};
${END}`;

const file = `Clay formula column: score_json  (table ICP_Engine, column 8)
================================================================

GENERATED from config/rubric_v5.json by scripts/gen_clay_formula.mjs — model ${RUBRIC.model_version}.
Do not hand-edit. Regenerate with \`npm run gen:formula\`.

tests/contract/clay_parity.test.mjs slices the block between the two 8<
markers below, evaluates it as \`new Function('inputs', body)\`, and asserts it
returns deep-equal output to engine/scoring.mjs across the golden inputs and
500 generated inputs. If the two ever disagree, the test is the thing that
tells you — not a rep looking at a wrong grade.


STEP 1 — bind the seven classifier columns
------------------------------------------

Clay's formula editor references other columns of the same row. The exact
reference token is Clay UI syntax and is NOT reproduced here — see
NEEDS_DOC_EVIDENCE #1 in REPORT.md. Paste the binding Clay's editor inserts
when you click each column, in place of the seven RIGHT-HAND SIDES below, then
paste the portable body underneath unchanged.

  var cls = {
    industry: /* click column cls_industry  */ null,
    stage:    /* click column cls_stage     */ null,
    type:     /* click column cls_type      */ null,
    geo:      /* click column cls_geo       */ null,
    revenue:  /* click column cls_revenue   */ null,
    activation: /* click column cls_activation */ null,
    buying:   /* click column cls_buying    */ null
  };

Each of those columns holds one object matching
engine/schemas/classifier_output.schema.json.


STEP 2 — assemble the input (paste unchanged)
---------------------------------------------

  var inputs = {
    industry_vertical: cls.industry ? cls.industry.value : null,
    levels: {
      stage_maturity: cls.stage    ? cls.stage.value    : null,
      company_type:   cls.type     ? cls.type.value     : null,
      geography:      cls.geo      ? cls.geo.value      : null,
      revenue_range:  cls.revenue  ? cls.revenue.value  : null,
      buying_signal:  cls.buying   ? cls.buying.value   : null
    },
    activation_state: cls.activation ? cls.activation.value : null,
    activation_evidence_dated_within_months:
      cls.activation ? cls.activation.evidence_dated_within_months : null,
    confidence: {
      industry_vertical: cls.industry   ? cls.industry.confidence   : 'low',
      stage_maturity:    cls.stage      ? cls.stage.confidence      : 'low',
      company_type:      cls.type       ? cls.type.confidence       : 'low',
      geography:         cls.geo        ? cls.geo.confidence        : 'low',
      revenue_range:     cls.revenue    ? cls.revenue.confidence    : 'low',
      buying_signal:     cls.buying     ? cls.buying.confidence     : 'low'
    },
    missing_inputs: {
      industry_vertical: cls.industry   ? cls.industry.missing_inputs   : [],
      stage_maturity:    cls.stage      ? cls.stage.missing_inputs      : [],
      company_type:      cls.type       ? cls.type.missing_inputs       : [],
      geography:         cls.geo        ? cls.geo.missing_inputs        : [],
      revenue_range:     cls.revenue    ? cls.revenue.missing_inputs    : [],
      buying_signal:     cls.buying     ? cls.buying.missing_inputs     : []
    },
    facts_summary: {
      // from facts_json (column 6), not from the classifiers
      revenue_usd:     null,  /* bind facts_json.revenue_estimate_usd  */
      headcount_total: null,  /* bind facts_json.li_headcount          */
      headcount_eng:   null   /* bind facts_json.eng_headcount_estimate */
    }
  };


STEP 3 — the portable body (paste unchanged)
--------------------------------------------

${body}


WHAT CLAY CANNOT DO, AND WHERE IT IS DONE INSTEAD
-------------------------------------------------

Nothing in the block above needs a Clay feature beyond plain JavaScript in a
formula column: no dates, no regex, no network, no imports. Everything the
rubric needs is arithmetic, object lookup and comparison.

Two things are deliberately NOT in the Clay formula:

  1. The note text (§8.3) and the audit row (§8.4) are built in n8n, from the
     event Clay posts. Clay produces numbers; n8n produces prose and the
     Pipedrive writes. Duplicating the note template in Clay would put user-
     visible copy in two places.

  2. Identifier normalization (engine/normalize.mjs) runs in n8n before the
     Clay request is built, so Clay receives an already-normalized
     identifier_value and never has to agree with n8n about what a domain is.

If a future rubric version needs something Clay's formula language cannot
express, the fallback is to move score_json out of Clay: n8n already imports
engine/scoring.mjs behaviour in ParseScored, so Path B can compute the score
from the seven classifier outputs and ignore Clay's score_json entirely. That
switch is a one-line CONFIG flag (score_source: clay | n8n), not a rebuild.
`;

export const FORMULA_FILE = file;

// Write ONLY when run directly. Importing this module (the parity test needs
// BEGIN and END from it) must not refresh the file it is about to check for
// staleness — otherwise the staleness assertion can never fail.
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  writeFileSync(join(ROOT, 'engine', 'clay_formula.txt'), file, 'utf8');
  process.stdout.write(`wrote engine/clay_formula.txt (${file.length} bytes)\n`);
}
