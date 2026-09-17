#!/usr/bin/env node
// scripts/gen_fixtures.mjs — build the tests/fixtures/clay/*.json events.
//
// v6 events carry NO score: the table classifies and enriches, n8n scores. So
// unlike v5 these fixtures are pure inputs, and the grade each one produces is
// whatever the Score node makes of it. That is the point — a fixture that
// carried its own answer could assert a grade the engine does not produce.
//
// The banner each file prints is computed here by running engine/scoring.mjs
// over the same inputs, so `npm run gen:fixtures` doubles as a statement of
// what each case is FOR.
//
// The malformed fixture is hand-shaped to violate the schema on purpose.

import { writeFileSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { score, RUBRIC } from '../engine/scoring.mjs';
import { activationStateFor } from '../engine/activation_guard.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tests', 'fixtures', 'clay');

const REQUESTED_AT = '2026-09-18T10:42:00Z';

const hiring = (over = {}) => ({
  total_open: null, eng_open: null, eng_open_60d_plus: null, dates_available: null,
  leader_titles: [], eng_titles_with_days: [], eng_open_ratio: null, eng_headcount: null,
  ...over,
});

const apollo = (over = {}) => ({
  employees: null, eng_headcount: null, country: null, state: null, founded_year: null,
  last_round_date: null, headcount_6mo_growth: null, headcount_12mo_growth: null,
  publicly_traded_symbol: null, owned_by_organization_id: null,
  ...over,
});

const levelled = (level, confidence, evidence, missing = []) =>
  ({ level, evidence, confidence, missing_inputs: missing });

function buildEvent(spec) {
  return {
    request_id: spec.request_id,
    org_id: spec.org_id,
    deal_id: spec.deal_id,
    requested_at: REQUESTED_AT,
    domain: spec.domain,
    resolved: spec.resolved,
    cls_all: spec.cls_all,
    apollo_summary: spec.apollo_summary,
    model_version: RUBRIC.model_version,
  };
}

/** What the Score node will make of this event. Printed, never written. */
function preview(event) {
  const c = event.cls_all;
  const guard = activationStateFor(
    c.activation_state, event.apollo_summary, event.requested_at,
    RUBRIC.activation_default_when_no_evidence
  );
  const conf = (x) => (x && x.confidence !== undefined ? x.confidence : null);
  const miss = (x) => (x && x.missing_inputs ? x.missing_inputs : []);
  const scored = score({
    industry_vertical: c.industry_vertical.value,
    levels: {
      stage_maturity: c.stage_maturity.level, company_type: c.company_type.level,
      geography: c.geography.level, revenue_range: c.revenue_range.level,
      buying_signal: c.buying_signal.level,
    },
    activation_state: guard.state,
    activation_evidence_dated_within_months: 0,
    confidence: {
      industry_vertical: conf(c.industry_vertical), stage_maturity: conf(c.stage_maturity),
      company_type: conf(c.company_type), geography: conf(c.geography),
      revenue_range: conf(c.revenue_range), buying_signal: conf(c.buying_signal),
    },
    missing_inputs: {
      industry_vertical: miss(c.industry_vertical), stage_maturity: miss(c.stage_maturity),
      company_type: miss(c.company_type), geography: miss(c.geography),
      revenue_range: miss(c.revenue_range), buying_signal: miss(c.buying_signal),
    },
    facts_summary: {
      revenue_usd: null,
      headcount_total: event.apollo_summary.employees,
      headcount_eng: event.apollo_summary.eng_headcount,
    },
  });
  return { scored, guard };
}

const CASES = {
  // --- A: Akuvo-shaped fintech, accelerating, must grade A -----------------
  icp_scored_A: {
    request_id: 'req-icp-0001', org_id: 10001, deal_id: 55001,
    domain: 'akuvo.com',
    resolved: { domain: 'akuvo.com', linkedin_url: 'https://www.linkedin.com/company/akuvo', website: 'http://www.akuvo.com' },
    cls_all: {
      engineering_hiring: hiring({
        total_open: 5, eng_open: 3, eng_open_60d_plus: 2, dates_available: true,
        leader_titles: ['Head of Engineering'],
        eng_titles_with_days: ['Senior Backend Engineer (74d)', 'Platform Engineer (61d)', 'Data Engineer (12d)'],
        eng_open_ratio: 0.17, eng_headcount: 18,
      }),
      industry_vertical: { value: 'FinTech', evidence: ['li_industry: Financial Services', 'website: collections platform for credit unions'], confidence: 'high', missing_inputs: [] },
      company_type: levelled(10, 'high', ['li_description: SaaS collections platform']),
      stage_maturity: levelled(10, 'medium', ['apollo.funding_events[0]: Series B', 'eng_open_60d_plus: 2']),
      activation_state: {
        value: 'Accelerating',
        evidence: ['apollo.funding_events[0].date: 2025-09-01', 'headcount_12mo_growth: 0.253'],
        activation_evidence_dated: 'apollo.funding_events[0].date: 2025-09-01',
        confidence: 'high', missing_inputs: [],
      },
      geography: { level: 10, evidence: ['apollo.country: United States', 'apollo.state: Pennsylvania'], confidence: 'high' },
      revenue_range: {
        level: 7, revenue_band_used: '$10M–$25M', revenue_source: 'headcount_band',
        evidence: ['apollo.employees: 91', 'apollo revenue $1.1M discarded: $12k/employee'],
        confidence: 'low', missing_inputs: [],
      },
      buying_signal: { level: 7, evidence: ['eng_open_60d_plus: 2', 'leader_titles: Head of Engineering'] },
      conflict_note: null,
    },
    apollo_summary: apollo({
      employees: 91, eng_headcount: 18, country: 'United States', state: 'Pennsylvania',
      founded_year: 2019, last_round_date: '2025-09-01',
      headcount_6mo_growth: 0.028, headcount_12mo_growth: 0.253,
    }),
  },

  // --- B_stable: composite >= 75, x0.80 drags it to B ---------------------
  icp_scored_B_stable: {
    request_id: 'req-icp-0002', org_id: 10002, deal_id: 55002,
    domain: 'qcash.io',
    resolved: { domain: 'qcash.io', linkedin_url: 'https://www.linkedin.com/company/qcash', website: 'https://qcash.io' },
    cls_all: {
      engineering_hiring: hiring({
        total_open: 2, eng_open: 1, eng_open_60d_plus: 0, dates_available: true,
        leader_titles: ['VP Engineering'], eng_titles_with_days: ['Backend Engineer (9d)'],
        eng_open_ratio: 0.025, eng_headcount: 40,
      }),
      industry_vertical: { value: 'FinTech', evidence: ['li_industry: Financial Services'], confidence: 'high', missing_inputs: [] },
      company_type: levelled(10, 'high', ['li_description: cloud lending software']),
      stage_maturity: levelled(10, 'high', ['apollo.funding_events[0]: Series C']),
      activation_state: {
        value: 'Stable', evidence: ['no funding event in 24 months', 'headcount flat'],
        activation_evidence_dated: null, confidence: 'high', missing_inputs: [],
      },
      geography: { level: 10, evidence: ['apollo.country: United States'], confidence: 'high' },
      revenue_range: {
        level: 7, revenue_band_used: '$10M–$25M', revenue_source: 'apollo_revenue',
        evidence: ['apollo.annual_revenue: 14000000'], confidence: 'high', missing_inputs: [],
      },
      buying_signal: { level: 3, evidence: ['eng_open: 1'] },
      conflict_note: null,
    },
    apollo_summary: apollo({
      employees: 130, eng_headcount: 40, country: 'United States', state: 'Washington',
      founded_year: 2015, headcount_6mo_growth: 0.004, headcount_12mo_growth: 0.01,
    }),
  },

  // --- contracting_valid: apollo says it shrank, so Contracting stands ----
  icp_scored_contracting_valid: {
    request_id: 'req-icp-0003', org_id: 10003, deal_id: 55003,
    domain: 'invoicecloud.com',
    resolved: { domain: 'invoicecloud.com', linkedin_url: null, website: 'https://invoicecloud.com' },
    cls_all: {
      engineering_hiring: hiring({
        total_open: 0, eng_open: 0, eng_open_60d_plus: 0, dates_available: true,
        leader_titles: ['CTO'], eng_titles_with_days: [], eng_open_ratio: 0, eng_headcount: 70,
      }),
      industry_vertical: { value: 'FinTech', evidence: ['li_industry: Financial Services'], confidence: 'high', missing_inputs: [] },
      company_type: levelled(10, 'high', ['li_description: payments SaaS']),
      stage_maturity: levelled(10, 'high', ['apollo.funding_events[0]: Series C']),
      activation_state: {
        value: 'Contracting',
        evidence: ['headcount_6mo_growth: -0.18', 'news: restructuring announced'],
        activation_evidence_dated: 'apollo.headcount_6mo_growth: -0.18',
        confidence: 'high', missing_inputs: [],
      },
      geography: { level: 10, evidence: ['apollo.country: United States'], confidence: 'high' },
      revenue_range: {
        level: 7, revenue_band_used: '$10M–$25M', revenue_source: 'headcount_band',
        evidence: ['apollo.employees: 240'], confidence: 'medium', missing_inputs: [],
      },
      buying_signal: { level: 0, evidence: ['eng_open: 0'] },
      conflict_note: 'headcount fell 18% in six months while the funding stage still reads Series C',
    },
    apollo_summary: apollo({
      employees: 240, eng_headcount: 70, country: 'United States', state: 'Massachusetts',
      founded_year: 2009, last_round_date: '2023-02-14',
      headcount_6mo_growth: -0.18, headcount_12mo_growth: -0.24,
    }),
  },

  // --- contracting_unbacked: Sol says Contracting, apollo says +0.05 ------
  icp_scored_contracting_unbacked: {
    request_id: 'req-icp-0004', org_id: 10004, deal_id: 55004,
    domain: 'formstack.com',
    resolved: { domain: 'formstack.com', linkedin_url: 'https://www.linkedin.com/company/formstack', website: 'https://formstack.com' },
    cls_all: {
      engineering_hiring: hiring({
        total_open: 6, eng_open: 2, eng_open_60d_plus: 0, dates_available: true,
        leader_titles: ['Director of Engineering'], eng_titles_with_days: ['Full Stack Engineer (14d)'],
        eng_open_ratio: 0.04, eng_headcount: 50,
      }),
      industry_vertical: { value: 'SaaS — Other', evidence: ['li_industry: Software Development'], confidence: 'high', missing_inputs: [] },
      company_type: levelled(10, 'high', ['li_description: workflow automation SaaS']),
      stage_maturity: levelled(7, 'medium', ['apollo.funding_events[0]: Series A']),
      activation_state: {
        value: 'Contracting',
        evidence: ['one article speculates about a slowdown'],
        // Names no layoff and carries no date: the guard must downgrade this.
        activation_evidence_dated: 'apollo.funding_events[0].date: 2025-09-01',
        confidence: 'low', missing_inputs: [],
      },
      geography: { level: 10, evidence: ['apollo.country: United States'], confidence: 'high' },
      revenue_range: {
        level: 7, revenue_band_used: '$10M–$25M', revenue_source: 'headcount_band',
        evidence: ['apollo.employees: 260'], confidence: 'medium', missing_inputs: [],
      },
      buying_signal: { level: 3, evidence: ['eng_open: 2'] },
      conflict_note: 'classifier called Contracting; apollo headcount grew 5% over six months',
    },
    apollo_summary: apollo({
      employees: 260, eng_headcount: 50, country: 'United States', state: 'Indiana',
      founded_year: 2006, last_round_date: '2025-09-01',
      headcount_6mo_growth: 0.05, headcount_12mo_growth: 0.09,
    }),
  },

  // --- insufficient: stage confidence low + missing_inputs ----------------
  icp_scored_insufficient: {
    request_id: 'req-icp-0005', org_id: 10005, deal_id: null,
    // A real domain that enrichment could make nothing of — which is what
    // insufficient_data means now. v6.0 had this fixture carry a NAME
    // identifier; a name is no longer sendable, so the shortage has to come
    // from the enrichment, not from the identifier.
    domain: 'stealthrobotics.io',
    resolved: { domain: null, linkedin_url: null, website: null },
    cls_all: {
      engineering_hiring: hiring(),
      industry_vertical: { value: 'Manufacturing tech / Industrial IoT', evidence: ['company_name: Stealth Robotics'], confidence: 'low', missing_inputs: ['website', 'li_description'] },
      company_type: levelled(3, 'low', ['company_name only'], ['li_description']),
      stage_maturity: levelled(null, 'low', [], ['funding_stage', 'eng_open']),
      activation_state: { value: null, evidence: [], activation_evidence_dated: null, confidence: 'low', missing_inputs: ['news'] },
      geography: { level: 10, evidence: ['apollo.country: United States'], confidence: 'medium' },
      revenue_range: { level: null, revenue_band_used: null, revenue_source: null, evidence: [], confidence: 'low', missing_inputs: ['apollo.annual_revenue', 'apollo.employees'] },
      buying_signal: { level: 0, evidence: [] },
      conflict_note: null,
    },
    apollo_summary: apollo({ country: 'United States' }),
  },

  // --- tier2: revenue level 0, employees > 1000 ---------------------------
  icp_scored_tier2: {
    request_id: 'req-icp-0006', org_id: 10006, deal_id: 55006,
    domain: 'merck.com',
    resolved: { domain: 'merck.com', linkedin_url: 'https://www.linkedin.com/company/merck', website: 'https://www.merck.com' },
    cls_all: {
      engineering_hiring: hiring({
        total_open: 400, eng_open: 40, eng_open_60d_plus: 12, dates_available: true,
        leader_titles: ['SVP Technology'], eng_titles_with_days: ['Data Engineer (30d)'],
        eng_open_ratio: 0.01, eng_headcount: 4000,
      }),
      industry_vertical: { value: 'Pharma / Life Sciences', evidence: ['li_industry: Pharmaceuticals'], confidence: 'high', missing_inputs: [] },
      company_type: levelled(7, 'high', ['mission-critical regulated custom software']),
      stage_maturity: levelled(0, 'high', ['apollo.employees: 71000']),
      activation_state: { value: 'Stable', evidence: ['no material news'], activation_evidence_dated: null, confidence: 'high', missing_inputs: [] },
      geography: { level: 10, evidence: ['apollo.country: United States', 'apollo.state: New Jersey'], confidence: 'high' },
      revenue_range: {
        level: 0, revenue_band_used: '$10B–$100B', revenue_source: 'apollo_revenue',
        evidence: ['apollo.annual_revenue: 64000000000'], confidence: 'high', missing_inputs: [],
      },
      buying_signal: { level: 3, evidence: ['eng_open: 40'] },
      conflict_note: null,
    },
    apollo_summary: apollo({
      employees: 71000, eng_headcount: 4000, country: 'United States', state: 'New Jersey',
      founded_year: 1891, headcount_6mo_growth: 0.01, headcount_12mo_growth: 0.02,
      publicly_traded_symbol: 'MRK',
    }),
  },

  // --- unknown_vertical: not one of the 17 --------------------------------
  icp_scored_unknown_vertical: {
    request_id: 'req-icp-0007', org_id: 10007, deal_id: 55007,
    domain: 'example-horizontal.com',
    resolved: { domain: 'example-horizontal.com', linkedin_url: null, website: 'https://example-horizontal.com' },
    cls_all: {
      engineering_hiring: hiring({
        total_open: 3, eng_open: 2, eng_open_60d_plus: 1, dates_available: true,
        leader_titles: ['Head of Platform'], eng_titles_with_days: ['Engineer (40d)'],
        eng_open_ratio: 0.08, eng_headcount: 25,
      }),
      // Deliberately outside the v6 sub-rubric: level 0 and a flag, never a guess.
      industry_vertical: { value: 'Horizontal B2B Software', evidence: ['li_industry: Software Development'], confidence: 'high', missing_inputs: [] },
      company_type: levelled(10, 'high', ['li_description: B2B SaaS']),
      stage_maturity: levelled(10, 'high', ['apollo.funding_events[0]: Series B']),
      activation_state: { value: 'Accelerating', evidence: ['apollo.funding_events[0].date: 2026-03-01'], activation_evidence_dated: 'apollo.funding_events[0].date: 2026-03-01', confidence: 'high', missing_inputs: [] },
      geography: { level: 10, evidence: ['apollo.country: United States'], confidence: 'high' },
      revenue_range: { level: 10, revenue_band_used: '$25M–$50M', revenue_source: 'apollo_revenue', evidence: ['apollo.annual_revenue: 30000000'], confidence: 'high', missing_inputs: [] },
      buying_signal: { level: 7, evidence: ['eng_open_60d_plus: 1'] },
      conflict_note: null,
    },
    apollo_summary: apollo({
      employees: 300, eng_headcount: 25, country: 'United States', state: 'New York',
      founded_year: 2017, last_round_date: '2026-03-01',
      headcount_6mo_growth: 0.12, headcount_12mo_growth: 0.3,
    }),
  },
};

let count = 0;
const lines = [];
for (const [name, spec] of Object.entries(CASES)) {
  const event = buildEvent(spec);
  writeFileSync(join(OUT, `${name}.json`), `${JSON.stringify(event, null, 2)}\n`, 'utf8');
  count += 1;
  const { scored, guard } = preview(event);
  lines.push(
    `${name.padEnd(32)} composite ${String(scored.composite).padStart(6)} ` +
    `x${scored.multiplier.toFixed(2)} -> ${String(scored.final_score).padStart(3)} ` +
    `(no-activation ${String(scored.final_score_without_activation).padStart(3)}) ` +
    `${String(scored.grade).padEnd(4)} ${scored.status}` +
    `${scored.tier2_candidate ? ' TIER2' : ''}${guard.guard_applied ? ' GUARD' : ''}`
  );
}

// --- The deliberately invalid one -----------------------------------------
const valid = JSON.parse(readFileSync(join(OUT, 'icp_scored_A.json'), 'utf8'));
const malformed = structuredClone(valid);
malformed.request_id = 'req-icp-0008';
malformed.org_id = '10001';                                  // 1. quoted id
delete malformed.cls_all.engineering_hiring.eng_open;        // 2. required key gone
malformed.cls_all.company_type.level = 5;                    // 3. off-ladder level
malformed.cls_all.revenue_range.confidence = 'certain';      // 4. not a confidence
delete malformed.apollo_summary.headcount_6mo_growth;        // 5. the guard's input
malformed.unexpected_key = 'this should fail additionalProperties';  // 6. unknown key
writeFileSync(join(OUT, 'icp_scored_malformed.json'), `${JSON.stringify(malformed, null, 2)}\n`, 'utf8');
count += 1;
lines.push('icp_scored_malformed             6 deliberate violations, one per check class');

process.stdout.write(`${lines.join('\n')}\n\n${count} fixtures written (model ${RUBRIC.model_version})\n`);
