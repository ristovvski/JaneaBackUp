#!/usr/bin/env node
// scripts/gen_fixtures.mjs — build the tests/fixtures/clay/*.json events.
//
// The `score` block of every fixture is produced by engine/scoring.mjs from the
// component values, never typed by hand. A hand-typed score block would let a
// fixture assert a grade the engine does not actually produce, which is the one
// thing a fixture must never do.
//
// v6 shape. The table sends ONE consolidated event: four classifiers under
// `cls_all`, three components already levelled inside `score`, plus `resolved`,
// `jobs` and `apollo_summary`. These fixtures therefore describe what the TABLE
// would have decided — the per-component confidences below are the table's, and
// scoring.mjs turns them into the score the table would have posted.
//
// The malformed fixture is the exception: it is hand-shaped to violate the
// schema on purpose, and is written last so its violations can be listed.

import { writeFileSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { score, RUBRIC } from '../engine/scoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tests', 'fixtures', 'clay');

const MAX_AGE = RUBRIC.activation_contracting_evidence_max_age_months;

/** Build a complete v6 icp.scored event from a compact case description. */
function buildEvent(spec) {
  const c = spec.components;

  const scored = score({
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
  });

  // engine/scoring.mjs names the industry level `industry`; v6's `score.levels`
  // uses the rubric's own weight key, `industries`. One rename, made here so
  // the fixtures cannot disagree with the schema about it.
  const levels = {
    industries: scored.levels_used.industry,
    stage_maturity: scored.levels_used.stage_maturity,
    company_type: scored.levels_used.company_type,
    geography: scored.levels_used.geography,
    revenue_range: scored.levels_used.revenue_range,
    buying_signal: scored.levels_used.buying_signal,
  };

  const months = c.activation_state.evidence_dated_within_months;
  const dated = typeof months === 'number' ? months <= MAX_AGE : false;

  return {
    request_id: spec.request_id,
    org_id: spec.org_id,
    deal_id: spec.deal_id,
    identifier_kind: spec.identifier_kind,
    identifier_value: spec.identifier_value,
    resolved: spec.resolved,
    cls_all: {
      industry_vertical: {
        value: c.industry_vertical.value,
        evidence: c.industry_vertical.evidence,
        confidence: c.industry_vertical.confidence,
        missing_inputs: c.industry_vertical.missing_inputs,
      },
      company_type: {
        level: c.company_type.value,
        evidence: c.company_type.evidence,
        confidence: c.company_type.confidence,
        missing_inputs: c.company_type.missing_inputs,
      },
      stage_maturity: {
        level: c.stage_maturity.value,
        evidence: c.stage_maturity.evidence,
        confidence: c.stage_maturity.confidence,
        missing_inputs: c.stage_maturity.missing_inputs,
      },
      activation_state: {
        value: c.activation_state.value,
        evidence: c.activation_state.evidence,
        activation_evidence_dated: dated,
        confidence: c.activation_state.confidence,
        missing_inputs: c.activation_state.missing_inputs,
      },
      conflict_note: spec.conflict_note ?? null,
    },
    jobs: spec.jobs,
    score: {
      levels,
      composite: scored.composite,
      activation_state_used: scored.activation_state_used,
      multiplier: scored.multiplier,
      final_score: scored.final_score,
      final_score_without_activation: scored.final_score_without_activation,
      grade: scored.grade,
      status: scored.status,
      confidence_overall: scored.confidence_overall,
      tier2_candidate: scored.tier2_candidate,
      flags: scored.flags,
    },
    apollo_summary: spec.apollo_summary,
    model_version: RUBRIC.model_version,
  };
}

const cmp = (value, confidence, evidence, missing = [], extra = {}) => ({
  value, evidence, confidence, missing_inputs: missing, ...extra,
});

const noJobs = {
  eng_open: null, eng_open_60d_plus: null, has_eng_leader: null, eng_leader_titles: [],
  eng_open_ratio: null, eng_headcount: null, dates_available: null, eng_titles: [], as_of: null,
};

const CASES = {
  // --- A: an Akuvo-shaped fintech, accelerating -----------------------------
  icp_scored_A: {
    request_id: 'req-icp-0001',
    org_id: '10001',
    deal_id: '55001',
    identifier_kind: 'domain',
    identifier_value: 'akuvo.com',
    resolved: { domain: 'akuvo.com', linkedin_url: 'https://www.linkedin.com/company/akuvo', website: 'https://akuvo.com' },
    components: {
      industry_vertical: cmp('FinTech', 'high', [
        'li_industry: Financial Services',
        'website_summary: lending and collections platform for credit unions',
      ]),
      stage_maturity: cmp(10, 'high', ['funding_stage: Series B', 'eng_roles_open_60d_plus: 4']),
      company_type: cmp(10, 'high', ['li_description: SaaS lending origination platform']),
      geography: cmp(10, 'high', ['hq_country: United States', 'hq_state: Colorado']),
      revenue_range: cmp(7, 'medium', ['revenue_estimate_usd: 18000000', 'revenue_source: Apollo']),
      activation_state: cmp('Accelerating', 'high', [
        'last_round_date: 2026-04-02',
        'open_eng_roles_count: 11',
      ], [], { evidence_dated_within_months: 5 }),
      buying_signal: cmp(7, 'high', ['senior_eng_roles: 2', 'last_round_usd: 21000000']),
    },
    jobs: {
      eng_open: 11, eng_open_60d_plus: 4, has_eng_leader: true,
      eng_leader_titles: ['VP Engineering'], eng_open_ratio: 0.18, eng_headcount: 62,
      dates_available: true, eng_titles: ['Senior Backend Engineer', 'Platform Engineer'],
      as_of: '2026-09-09',
    },
    apollo_summary: {
      employees: 190, eng_headcount: 62, country: 'United States', state: 'Colorado',
      founded_year: 2018, last_round_date: '2026-04-02',
      revenue_band_used: '$10M-$25M', revenue_source: 'Apollo',
    },
    facts_summary: { revenue_usd: 18000000, headcount_total: 190, headcount_eng: 62 },
  },

  // --- B: composite clears 75 but the Stable multiplier drags it under ------
  icp_scored_B_stable: {
    request_id: 'req-icp-0002',
    org_id: '10002',
    deal_id: '55002',
    identifier_kind: 'domain',
    identifier_value: 'qcash.io',
    resolved: { domain: 'qcash.io', linkedin_url: 'https://www.linkedin.com/company/qcash', website: 'https://qcash.io' },
    components: {
      industry_vertical: cmp('FinTech', 'high', ['li_industry: Financial Services']),
      stage_maturity: cmp(7, 'high', ['funding_stage: Series A', 'eng_roles_open_60d_plus: 2']),
      company_type: cmp(10, 'high', ['li_description: cloud lending software']),
      geography: cmp(10, 'high', ['hq_country: United States']),
      revenue_range: cmp(7, 'high', ['revenue_estimate_usd: 14000000', 'revenue_source: Apollo']),
      activation_state: cmp('Stable', 'high', ['news_last_12mo: []']),
      buying_signal: cmp(3, 'medium', ['open_eng_roles_count: 1']),
    },
    jobs: {
      eng_open: 1, eng_open_60d_plus: 2, has_eng_leader: true,
      eng_leader_titles: ['Head of Engineering'], eng_open_ratio: 0.025, eng_headcount: 40,
      dates_available: true, eng_titles: ['Backend Engineer'], as_of: '2026-09-09',
    },
    apollo_summary: {
      employees: 130, eng_headcount: 40, country: 'United States', state: 'Washington',
      founded_year: 2015, last_round_date: null,
      revenue_band_used: '$10M-$25M', revenue_source: 'Apollo',
    },
    facts_summary: { revenue_usd: 14000000, headcount_total: 130, headcount_eng: 40 },
  },

  // --- Contracting: multiplier 0 zeroes an otherwise strong composite ------
  icp_scored_contracting: {
    request_id: 'req-icp-0003',
    org_id: '10003',
    deal_id: '55003',
    identifier_kind: 'domain',
    identifier_value: 'invoicecloud.com',
    resolved: { domain: 'invoicecloud.com', linkedin_url: null, website: 'https://invoicecloud.com' },
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
    conflict_note: 'headcount fell 12% while the funding stage still reads Series C',
    jobs: {
      eng_open: 0, eng_open_60d_plus: 0, has_eng_leader: true,
      eng_leader_titles: ['CTO'], eng_open_ratio: 0, eng_headcount: 70,
      dates_available: true, eng_titles: [], as_of: '2026-09-09',
    },
    apollo_summary: {
      employees: 240, eng_headcount: 70, country: 'United States', state: 'Massachusetts',
      founded_year: 2009, last_round_date: '2023-02-14',
      revenue_band_used: '$10M-$25M', revenue_source: 'Apollo',
    },
    facts_summary: { revenue_usd: 22000000, headcount_total: 240, headcount_eng: 70 },
  },

  // --- Insufficient: revenue missing, low confidence ------------------------
  icp_scored_insufficient: {
    request_id: 'req-icp-0004',
    org_id: '10004',
    deal_id: '55004',
    identifier_kind: 'name',
    identifier_value: 'stealth robotics',
    resolved: { domain: null, linkedin_url: null, website: null },
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
    jobs: noJobs,
    apollo_summary: {
      employees: null, eng_headcount: null, country: 'United States', state: null,
      founded_year: null, last_round_date: null, revenue_band_used: null, revenue_source: null,
    },
    facts_summary: { revenue_usd: null, headcount_total: null, headcount_eng: null },
  },

  // --- Tier 2: over $1B revenue, software-dependent ------------------------
  icp_scored_tier2: {
    request_id: 'req-icp-0005',
    org_id: '10005',
    deal_id: '55005',
    identifier_kind: 'domain',
    identifier_value: 'merck.com',
    resolved: { domain: 'merck.com', linkedin_url: 'https://www.linkedin.com/company/merck', website: 'https://www.merck.com' },
    components: {
      industry_vertical: cmp('Pharma / Life Sciences', 'high', ['li_industry: Pharmaceuticals']),
      stage_maturity: cmp(0, 'high', [
        'li_headcount: 71000',
        'website_summary: in-house digital and data platform organisation',
      ]),
      company_type: cmp(7, 'high', ['website_summary: mission-critical regulated custom software']),
      geography: cmp(10, 'high', ['hq_country: United States', 'hq_state: New Jersey']),
      revenue_range: cmp(0, 'high', ['revenue_estimate_usd: 64000000000', 'revenue_source: Apollo']),
      activation_state: cmp('Stable', 'high', ['news_last_12mo: 3 items, none material']),
      buying_signal: cmp(3, 'medium', ['open_eng_roles_count: 40']),
    },
    jobs: {
      eng_open: 40, eng_open_60d_plus: 12, has_eng_leader: true,
      eng_leader_titles: ['SVP Technology', 'VP Data Platform'], eng_open_ratio: 0.01,
      eng_headcount: 4000, dates_available: true,
      eng_titles: ['Data Engineer', 'Cloud Architect'], as_of: '2026-09-09',
    },
    apollo_summary: {
      employees: 71000, eng_headcount: 4000, country: 'United States', state: 'New Jersey',
      founded_year: 1891, last_round_date: null,
      revenue_band_used: '$10B-$100B', revenue_source: 'Apollo',
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
// Five independent violations, one per class of check the validator makes, so
// the error message is informative and the test cannot pass by accident if any
// single one is ever legalised.
const valid = JSON.parse(readFileSync(join(OUT, 'icp_scored_A.json'), 'utf8'));
const malformed = structuredClone(valid);
malformed.request_id = 'req-icp-0006';
delete malformed.jobs.eng_open;                 // 1. required key missing
malformed.score.final_score = 105;              // 2. out of range
malformed.score.multiplier = 0.5;               // 3. not a rubric multiplier
malformed.score.status = 'insufficient_data';   // 4. status/grade contradiction
malformed.unexpected_key = 'this should fail additionalProperties';  // 5. unknown key
writeFileSync(join(OUT, 'icp_scored_malformed.json'), `${JSON.stringify(malformed, null, 2)}\n`, 'utf8');
count += 1;
process.stdout.write('icp_scored_malformed       5 deliberate violations, one per check class\n');

process.stdout.write(`\n${count} fixtures written to tests/fixtures/clay/ (model ${RUBRIC.model_version})\n`);
