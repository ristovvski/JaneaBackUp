#!/usr/bin/env node
// scripts/gen_fixtures.mjs — build the tests/fixtures/clay/*.json events.
//
// The `score` block of every clay fixture is produced by engine/scoring.mjs
// from the component values, never typed by hand. A hand-typed score block
// would let a fixture assert a grade the engine does not actually produce,
// which is the one thing a fixture must never do.
//
// The malformed fixture is the exception: it is hand-shaped to violate the
// schema on purpose, and is written last so the generator's own validation
// pass can confirm it fails.

import { writeFileSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { score } from '../engine/scoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tests', 'fixtures', 'clay');

/** Build a complete icp.scored event from a compact case description. */
function buildEvent(spec) {
  const c = spec.components;

  const input = {
    industry_vertical: c.industry_vertical.value,
    levels: {
      stage_maturity: c.stage_maturity.value,
      company_type: c.company_type.value,
      geography: c.geography.value,
      revenue_range: c.revenue_range.value,
      buying_signal: c.buying_signal.value,
    },
    activation_state: c.activation_state.value,
    activation_evidence_dated_within_months: c.activation_state.evidence_dated_within_months ?? null,
    confidence: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.confidence])),
    missing_inputs: Object.fromEntries(Object.entries(c).map(([k, v]) => [k, v.missing_inputs])),
    facts_summary: spec.facts_summary,
  };

  const scored = score(input);

  return {
    event: 'icp.scored',
    event_id: spec.event_id,
    request_id: spec.request_id,
    emitted_at: spec.emitted_at,
    model_version: 'v5',
    org_id: spec.org_id,
    deal_id: spec.deal_id,
    identifier_kind: spec.identifier_kind,
    identifier_value: spec.identifier_value,
    components: c,
    score: scored,
    facts_summary: spec.facts_summary,
    clay_table: 'ICP_Engine',
    clay_row_url: null,
  };
}

const cmp = (value, confidence, evidence, missing = [], extra = {}) => ({
  value, evidence, confidence, missing_inputs: missing, ...extra,
});

const CASES = {
  // --- A: an Akuvo-shaped fintech, accelerating -----------------------------
  icp_scored_A: {
    event_id: 'clay-evt-a1b2c3d4e5f6',
    request_id: 'req-icp-0001',
    emitted_at: '2026-09-09T10:15:00Z',
    org_id: '10001',
    deal_id: '55001',
    identifier_kind: 'domain',
    identifier_value: 'akuvo.com',
    components: {
      industry_vertical: cmp('FinTech', 'high', [
        'li_industry: Financial Services',
        'website_summary: lending and collections platform for credit unions',
      ]),
      stage_maturity: cmp(10, 'high', [
        'funding_stage: Series B',
        'eng_roles_open_60d_plus: 4',
      ]),
      company_type: cmp(10, 'high', [
        'li_description: SaaS lending origination platform',
      ]),
      geography: cmp(10, 'high', ['hq_country: United States', 'hq_state: Colorado']),
      revenue_range: cmp(7, 'medium', [
        'revenue_estimate_usd: 18000000',
        'revenue_source: Apollo',
      ]),
      activation_state: cmp('Accelerating', 'high', [
        'last_round_date: 2026-04-02',
        'open_eng_roles_count: 11',
      ], [], { evidence_dated_within_months: 5 }),
      buying_signal: cmp(7, 'high', [
        'senior_eng_roles: 2',
        'last_round_usd: 21000000',
      ]),
    },
    facts_summary: { revenue_usd: 18000000, headcount_total: 190, headcount_eng: 62 },
  },

  // --- B: composite clears 75 but the Stable multiplier drags it under ------
  icp_scored_B_stable: {
    event_id: 'clay-evt-b1b2c3d4e5f6',
    request_id: 'req-icp-0002',
    emitted_at: '2026-09-09T10:16:00Z',
    org_id: '10002',
    deal_id: '55002',
    identifier_kind: 'domain',
    identifier_value: 'qcash.io',
    components: {
      industry_vertical: cmp('FinTech', 'high', ['li_industry: Financial Services']),
      stage_maturity: cmp(7, 'high', ['funding_stage: Series A', 'eng_roles_open_60d_plus: 2']),
      company_type: cmp(10, 'high', ['li_description: cloud lending software']),
      geography: cmp(10, 'high', ['hq_country: United States']),
      revenue_range: cmp(7, 'high', ['revenue_estimate_usd: 14000000', 'revenue_source: Apollo']),
      activation_state: cmp('Stable', 'high', ['news_last_12mo: []']),
      buying_signal: cmp(3, 'medium', ['open_eng_roles_count: 1']),
    },
    facts_summary: { revenue_usd: 14000000, headcount_total: 130, headcount_eng: 40 },
  },

  // --- Contracting: multiplier 0 zeroes an otherwise strong composite ------
  icp_scored_contracting: {
    event_id: 'clay-evt-c1b2c3d4e5f6',
    request_id: 'req-icp-0003',
    emitted_at: '2026-09-09T10:17:00Z',
    org_id: '10003',
    deal_id: '55003',
    identifier_kind: 'domain',
    identifier_value: 'invoicecloud.com',
    components: {
      industry_vertical: cmp('FinTech', 'high', ['li_industry: Financial Services']),
      stage_maturity: cmp(10, 'high', ['funding_stage: Series C']),
      company_type: cmp(10, 'high', ['li_description: payments SaaS']),
      geography: cmp(10, 'high', ['hq_country: United States']),
      revenue_range: cmp(7, 'high', ['revenue_estimate_usd: 22000000']),
      activation_state: cmp('Contracting', 'high', [
        'news_last_12mo: 2026-06-11 — cuts 12% of staff in restructuring',
      ], [], { evidence_dated_within_months: 3 }),
      buying_signal: cmp(0, 'high', ['open_eng_roles_count: 0']),
    },
    facts_summary: { revenue_usd: 22000000, headcount_total: 240, headcount_eng: 70 },
  },

  // --- Insufficient: revenue missing, low confidence ------------------------
  icp_scored_insufficient: {
    event_id: 'clay-evt-d1b2c3d4e5f6',
    request_id: 'req-icp-0004',
    emitted_at: '2026-09-09T10:18:00Z',
    org_id: '10004',
    deal_id: '55004',
    identifier_kind: 'name',
    identifier_value: 'stealth robotics',
    components: {
      industry_vertical: cmp('Manufacturing tech / Industrial IoT', 'low', [
        'company_name: Stealth Robotics',
      ], ['website_summary', 'li_description']),
      stage_maturity: cmp(null, 'low', [], ['funding_stage', 'open_eng_roles_count']),
      company_type: cmp(3, 'low', ['company_name: Stealth Robotics'], ['li_description']),
      geography: cmp(10, 'medium', ['hq_country: United States']),
      revenue_range: cmp(null, 'low', [], ['revenue_estimate_usd']),
      activation_state: cmp('Stable', 'low', [], ['news_last_12mo']),
      buying_signal: cmp(null, 'low', [], ['open_eng_roles_count', 'news_last_12mo']),
    },
    facts_summary: { revenue_usd: null, headcount_total: null, headcount_eng: null },
  },

  // --- Tier 2: over $1B revenue, software-dependent ------------------------
  icp_scored_tier2: {
    event_id: 'clay-evt-e1b2c3d4e5f6',
    request_id: 'req-icp-0005',
    emitted_at: '2026-09-09T10:19:00Z',
    org_id: '10005',
    deal_id: '55005',
    identifier_kind: 'domain',
    identifier_value: 'merck.com',
    components: {
      industry_vertical: cmp('Pharma / Life Sciences', 'high', ['li_industry: Pharmaceuticals']),
      stage_maturity: cmp(0, 'high', [
        'li_headcount: 71000',
        'website_summary: in-house digital and data platform organisation',
      ]),
      company_type: cmp(7, 'high', [
        'website_summary: mission-critical regulated custom software',
      ]),
      geography: cmp(10, 'high', ['hq_country: United States', 'hq_state: New Jersey']),
      revenue_range: cmp(0, 'high', [
        'revenue_estimate_usd: 64000000000',
        'revenue_source: Apollo',
      ]),
      activation_state: cmp('Stable', 'high', ['news_last_12mo: 3 items, none material']),
      buying_signal: cmp(3, 'medium', ['open_eng_roles_count: 40']),
    },
    facts_summary: { revenue_usd: 64000000000, headcount_total: 71000, headcount_eng: 4000 },
  },
};

let count = 0;
for (const [name, spec] of Object.entries(CASES)) {
  const event = buildEvent(spec);
  writeFileSync(join(OUT, `${name}.json`), `${JSON.stringify(event, null, 2)}\n`, 'utf8');
  count += 1;
  const s = event.score;
  process.stdout.write(
    `${name.padEnd(26)} composite ${String(s.composite).padStart(6)} ` +
    `x${s.multiplier.toFixed(2)} -> final ${String(s.final_score).padStart(3)} ` +
    `(no-activation ${String(s.final_score_without_activation).padStart(3)}) ` +
    `grade ${String(s.grade).padEnd(4)} ${s.status}` +
    `${s.tier2_candidate ? ' TIER2' : ''}\n`
  );
}

// --- The deliberately invalid one -----------------------------------------
// Four independent violations so the error message is informative and so the
// test cannot pass by accident if one of them is ever legalised.
const valid = JSON.parse(readFileSync(join(OUT, 'icp_scored_A.json'), 'utf8'));
const malformed = structuredClone(valid);
malformed.event_id = 'clay-evt-malformed01';
malformed.request_id = 'req-icp-0006';
delete malformed.components.geography;          // 1. required component missing
malformed.score.final_score = 105;              // 2. out of range
malformed.score.multiplier = 0.5;               // 3. not a rubric multiplier
malformed.score.status = 'insufficient_data';   // 4. status/grade contradiction
malformed.unexpected_key = 'this should fail additionalProperties';
writeFileSync(join(OUT, 'icp_scored_malformed.json'), `${JSON.stringify(malformed, null, 2)}\n`, 'utf8');
count += 1;
process.stdout.write('icp_scored_malformed       4 deliberate schema violations + 1 extra key\n');

process.stdout.write(`\n${count} clay fixtures written.\n`);
