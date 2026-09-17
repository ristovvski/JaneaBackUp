#!/usr/bin/env node
// scripts/gen_fixtures.mjs — build the tests/fixtures/clay/*.json events.
//
// These are SCORED events: the Clay table grades, and Path B's job is to write
// what arrived. So unlike the v6.0 fixtures, which were pure inputs whose grade
// the Score node produced, each of these carries its own answer — because that
// is now what the wire actually carries.
//
// One of them is not synthetic at all. `icp_scored_live_intellistack.json` is
// the body Clay posted on 2026-09-17 (execution 60629), kept verbatim: the
// contract is written against what the table sends, not against what we would
// like it to send.
//
// The malformed fixtures are hand-shaped to violate the contract on purpose,
// one violation class each.

import { writeFileSync, readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { validateEvent } from '../engine/validate_event.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tests', 'fixtures', 'clay');

const REQUESTED_AT = '2026-09-18T10:42:00Z';
const CFG = { levels: [0, 3, 7, 10] };

/** The eight required keys, plus whatever working the case wants to show. */
const event = (spec) => ({
  request_id: spec.request_id,
  org_id: spec.org_id,
  deal_id: spec.deal_id === undefined ? null : spec.deal_id,
  requested_at: REQUESTED_AT,
  final: spec.final,
  grade: spec.grade,
  status: spec.status,
  note: spec.note,
  ...(spec.working || {}),
});

const working = (over = {}) => ({
  composite: 78,
  multiplier: 0.8,
  final_without_activation: 78,
  industry_level: 7,
  stage_level: 3,
  type_level: 10,
  geo_level: 10,
  revenue_level: 10,
  activation_used: 'Stable',
  confidence_overall: 'medium',
  tier2_candidate: false,
  flags: [],
  ...over,
});

const NOTE_A = [
  'ICP v6 — Calculated: ICP A (93/100) · Confidence: high',
  'Industry 10/10 · FinTech — Lending decisioning sold to credit unions.',
  'Stage 7/10 — Four engineering roles open past 60 days.',
  'Type 10/10 — Named cloud products and a 50-person engineering team.',
  'Geo 10/10 — Headquarters in Colorado, inside the primary US market.',
  'Revenue 7/10 · $10M–$25M via apollo — Apollo estimates $18M.',
  'Activation Accelerating ×1.00 — Headcount up 22% over six months.',
  'Composite 92.5 × 1.00 = 93 → ICP A',
].join('\n');

const CASES = {
  // --- the ordinary case: a grade, its working, a note --------------------
  icp_scored_A: {
    request_id: 'req-icp-0001', org_id: 10001, deal_id: 55001,
    final: 93, grade: 'A', status: 'scored', note: NOTE_A,
    working: working({
      composite: 92.5, multiplier: 1, final_without_activation: 92.5,
      industry_level: 10, stage_level: 7, revenue_level: 7,
      activation_used: 'Accelerating', confidence_overall: 'high',
    }),
  },

  // --- the activation multiplier visibly costing a grade ------------------
  icp_scored_B_stable: {
    request_id: 'req-icp-0002', org_id: 10002, deal_id: 55002,
    final: 74, grade: 'B', status: 'scored',
    note: 'ICP v6 — Calculated: ICP B (74/100) · Confidence: high\n'
      + 'Composite 92.5 × 0.80 = 74 → ICP B\n'
      + 'Activation Stable ×0.80 — No evidence of a current transformation.',
    working: working({
      composite: 92.5, multiplier: 0.8, final_without_activation: 92.5,
      industry_level: 10, stage_level: 7, revenue_level: 7,
      confidence_overall: 'high',
    }),
  },

  // --- Contracting takes an account off the board -------------------------
  icp_scored_contracting: {
    request_id: 'req-icp-0003', org_id: 10003, deal_id: null,
    final: 0, grade: 'C', status: 'scored',
    note: 'ICP v6 — Calculated: ICP C (0/100) · Confidence: medium\n'
      + 'Activation Contracting ×0.00 — Layoffs reported 2026-03-14.\n'
      + 'Composite 92.5 × 0.00 = 0 → ICP C',
    working: working({
      composite: 92.5, multiplier: 0, final_without_activation: 92.5,
      industry_level: 10, stage_level: 7, revenue_level: 7,
      activation_used: 'Contracting',
    }),
  },

  // --- nothing to grade: final and grade are null, and that is legal ------
  icp_scored_insufficient: {
    request_id: 'req-icp-0004', org_id: 10004, deal_id: null,
    final: null, grade: null, status: 'insufficient_data',
    note: 'ICP v6 — Not calculated: insufficient data\n'
      + 'Stage, revenue and company type could not be established from the '
      + 'available enrichment, so no grade was produced.',
    working: working({
      composite: null, multiplier: null, final_without_activation: null,
      industry_level: null, stage_level: null, type_level: null,
      revenue_level: null, activation_used: null, confidence_overall: 'low',
      flags: ['insufficient_data'],
    }),
  },

  // --- the eight required keys and nothing else ---------------------------
  icp_scored_bare: {
    request_id: 'req-icp-0005', org_id: 10005, deal_id: 55005,
    final: 56, grade: 'B', status: 'scored',
    note: 'ICP v6 — Calculated: ICP B (56/100)\nNo working was sent with this row.',
  },

  // --- tier 2, carried as a flag and acted on by nobody -------------------
  icp_scored_tier2: {
    request_id: 'req-icp-0006', org_id: 10006, deal_id: 55006,
    final: 30, grade: 'C', status: 'scored',
    note: 'ICP v6 — Calculated: ICP C (30/100) · Confidence: low\n'
      + 'Flagged as a Tier 2 candidate: enterprise scale, different motion.',
    working: working({
      composite: 38, multiplier: 0.8, final_without_activation: 38,
      industry_level: 3, stage_level: 0, type_level: 3, revenue_level: 0,
      confidence_overall: 'low', tier2_candidate: true, flags: ['tier2_candidate'],
    }),
  },
};

let count = 0;
const lines = [];
for (const [name, spec] of Object.entries(CASES)) {
  const body = event(spec);
  const problems = validateEvent(body, CFG);
  if (problems.length > 0) {
    throw new Error(`fixture ${name} does not satisfy its own contract: ${problems.join('; ')}`);
  }
  writeFileSync(join(OUT, `${name}.json`), `${JSON.stringify(body, null, 2)}\n`, 'utf8');
  count += 1;
  lines.push(
    `${name.padEnd(32)} ${String(body.final ?? 'null').padStart(4)} ${String(body.grade ?? '-').padEnd(2)}`
    + ` ${body.status.padEnd(17)} note ${String(body.note.length).padStart(4)} chars`
    + ` · ${Object.keys(body).length} keys`
  );
}

// --- the deliberately invalid ones -----------------------------------------
//
// One violation class each, so a failure names which rule caught it rather
// than "the fixture is bad".
const valid = JSON.parse(readFileSync(join(OUT, 'icp_scored_A.json'), 'utf8'));

const malformed = structuredClone(valid);
malformed.request_id = 'req-icp-0007';
malformed.org_id = '10001';                    // 1. quoted id
malformed.grade = 'D';                         // 2. not a grade
malformed.stage_level = 5;                     // 3. off-ladder level
delete malformed.note;                         // 4. the one field a rep reads
malformed.cls_all = { industry_vertical: {} }; // 5. the v6.0 shape, now unknown
writeFileSync(join(OUT, 'icp_scored_malformed.json'), `${JSON.stringify(malformed, null, 2)}\n`, 'utf8');
count += 1;
lines.push('icp_scored_malformed             5 deliberate violations, one per check class');

// The exact shape that reached Path B on 2026-09-17 and was rejected: a v6.0
// event, carrying classifiers and no grade. Kept so the regression that
// started this rewrite stays covered.
const v60 = {
  request_id: 'req-icp-0008',
  org_id: 10001,
  deal_id: 55001,
  requested_at: REQUESTED_AT,
  domain: 'akuvo.com',
  resolved: { domain: 'akuvo.com', linkedin_url: null, website: 'https://akuvo.com' },
  cls_all: { industry_vertical: { value: 'FinTech', evidence: [], confidence: 'high', missing_inputs: [] } },
  apollo_summary: { employees: 260 },
  model_version: 'v6',
};
writeFileSync(join(OUT, 'icp_scored_v60_shape.json'), `${JSON.stringify(v60, null, 2)}\n`, 'utf8');
count += 1;
lines.push('icp_scored_v60_shape             the old contract — must be rejected, loudly');

// The live capture, if it has been placed here. Never generated.
const live = join(OUT, 'icp_scored_live_intellistack.json');
if (existsSync(live)) {
  const body = JSON.parse(readFileSync(live, 'utf8'));
  const problems = validateEvent(body, CFG);
  lines.push(
    `icp_scored_live_intellistack     CAPTURED from execution 60629 — `
    + (problems.length === 0 ? 'satisfies the contract' : `FAILS: ${problems.join('; ')}`)
  );
  if (problems.length > 0) throw new Error('the live capture does not satisfy the contract');
}

process.stdout.write(`${lines.join('\n')}\n\n${count} fixtures written\n`);
