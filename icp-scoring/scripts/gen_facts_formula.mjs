#!/usr/bin/env node
// scripts/gen_facts_formula.mjs — write engine/clay_facts_formula.txt.
//
// The facts_json column builds the object every classifier reads. Its key list
// IS engine/schemas/enrichment_facts.schema.json, so it is generated from that
// schema rather than typed: a key added to the schema and forgotten here would
// make every row fail validation at the n8n boundary, which is a slow and
// confusing way to find a typo.
//
// Run: npm run gen:facts   (tests/contract/clay_parity.test.mjs checks staleness)

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SCHEMA = JSON.parse(
  readFileSync(join(ROOT, 'engine', 'schemas', 'enrichment_facts.schema.json'), 'utf8')
);

export const BEGIN = '/* ---8<--- BEGIN FACTS BODY (generated; paste unchanged) --- */';
export const END = '/* ---8<--- END FACTS BODY --- */';

// Keys the webhook already delivers; everything else comes from enrichment.
const FROM_WEBHOOK = {
  request_id: 'Request Id',
  org_id: 'Org Id',
  deal_id: 'Deal Id',
  identifier_kind: 'Identifier Kind',
  identifier_value: 'Identifier Value',
  domain: 'Domain',
  linkedin_url: 'Linkedin Url',
  company_name: 'Company Name',
  hq_country: 'Hq Country',
  hq_state: 'Hq State',
};

// Harness bookkeeping — never sent to a classifier, never part of facts_json.
const EXCLUDE = new Set(['SYNTHETIC', 'synthetic_classifier_output', 'captured_at']);

const required = SCHEMA.required;
const allKeys = Object.keys(SCHEMA.properties).filter((k) => !EXCLUDE.has(k));
const enrichmentKeys = allKeys.filter((k) => !(k in FROM_WEBHOOK));

const line = (key) => {
  const prop = SCHEMA.properties[key];
  const types = []
    .concat(prop.type || (prop.enum ? 'enum' : 'any'))
    .filter((t) => t !== 'null')
    .join('|');
  const req = required.includes(key) ? '' : '   // optional';
  if (key in FROM_WEBHOOK) {
    return `    ${key}: W['${FROM_WEBHOOK[key]}'] ?? null,`.padEnd(58) +
           `// ${types}, from the webhook${req}`;
  }
  return `    ${key}: E.${key} ?? null,`.padEnd(58) + `// ${types}${req}`;
};

const body = `${BEGIN}
// Generated from engine/schemas/enrichment_facts.schema.json.
// ${allKeys.length} keys, ${required.length} of them required by the schema.
//
// EVERY key is present on EVERY row, with null where enrichment found nothing.
// That is not tidiness: the classifier preamble tells the model to read null as
// "enrichment did not find it" and an empty array as "we looked and there was
// nothing". Omitting a key destroys both readings, and additionalProperties is
// false, so an extra key fails the row at the n8n boundary.

return {
${allKeys.map(line).join('\n')}
};
${END}`;

const file = `Clay formula column: facts_json  (table ICP_Engine, column 6)
==============================================================

GENERATED from engine/schemas/enrichment_facts.schema.json by
scripts/gen_facts_formula.mjs. Do not hand-edit — regenerate with
\`npm run gen:facts\`.

This is the object every one of the seven classifiers reads. Build it BEFORE
the classifier columns exist: with the enrichment columns still absent it
emits all-nulls, which is a valid fact set, and the whole pipeline runs
end to end returning "Insufficient data". See engine/clay_build_order.md,
Phase 1.


STEP 1 — bind the two sources
-----------------------------

Clay's formula editor inserts its own reference token when you click a column;
that token is UI syntax and is NOT reproduced here (NEEDS_DOC_EVIDENCE #1 in
REPORT.md). Replace the two right-hand sides below, then paste STEP 2 unchanged.

  // The webhook source column, whose parsed subfields are already addressable
  // (verified live 2026-09-15: all 12 keys arrived, Deal Id as null).
  var W = /* click the "Webhook" source column */ {};

  // The enrichment columns. PHASE 1: leave this exactly as {} — every
  // enrichment key then resolves to null and the row still scores.
  // PHASE 2: replace with an object mapping each key below to its column.
  var E = {};


STEP 2 — the body (paste unchanged)
-----------------------------------

${body}


WHAT PHASE 1 PRODUCES
---------------------

With \`E = {}\`, \`facts_json\` is well-formed and every enrichment value is null.
Downstream:

  - the seven classifiers (once they exist) return value: null,
    confidence: "low", and list their missing_inputs;
  - \`score_json\` returns status "insufficient_data", grade null — because
    stage_maturity, revenue_range and company_type all gate it;
  - n8n writes ICP Calculated = "Insufficient data" plus a note whose
    Missing line names every absent fact.

That is the full loop working, honestly reporting that it has nothing to score
on. It is the correct behaviour, not a failure — and it is provable today
without spending an enrichment credit.

To turn it into a real grade for a demo, hand-type a few values into one row
(revenue_estimate_usd, funding_stage, li_headcount, eng_roles_open_60d_plus)
and the identical formula produces a genuine graded result.


KEYS, AND WHERE EACH COMES FROM
-------------------------------

From the webhook (${Object.keys(FROM_WEBHOOK).length}):
${Object.entries(FROM_WEBHOOK).map(([k, v]) => `  ${k.padEnd(24)} <- Webhook."${v}"`).join('\n')}

From enrichment (${enrichmentKeys.length}) — Phase 2:
${enrichmentKeys.map((k) => `  ${k}`).join('\n')}
`;

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  writeFileSync(join(ROOT, 'engine', 'clay_facts_formula.txt'), file, 'utf8');
  process.stdout.write(
    `wrote engine/clay_facts_formula.txt (${file.length} bytes)\n` +
    `  ${allKeys.length} keys: ${Object.keys(FROM_WEBHOOK).length} from the webhook, ${enrichmentKeys.length} from enrichment\n`
  );
}

export const FACTS_FILE = file;
