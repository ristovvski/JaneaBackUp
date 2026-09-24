#!/usr/bin/env node
// scripts/gen_synthetic_facts.mjs — the three SYNTHETIC day-one golden fixtures.
//
// READ THIS BEFORE TRUSTING A GOLDEN RESULT.
//
// §9.5 requires golden facts to be CAPTURED FROM CLAY RUNS, not authored. These
// three are authored, and they say so: every file carries "SYNTHETIC": true and
// a SYNTHETIC_ filename prefix. They exist so the harness, the scoring path and
// the acceptance assertions are all runnable and reviewable on day one, before
// the Clay table exists.
//
// They are NOT evidence that the classifiers work. They are evidence that the
// harness works. tests/golden/golden.test.mjs prints that distinction on every
// run and REPORT.md repeats it.
//
// `synthetic_classifier_output` is what a classifier WOULD plausibly return for
// these facts. It lets the harness exercise facts -> levels -> score with no
// Anthropic API key. Facts captured from Clay must never carry that block, and
// the harness refuses to use it on a non-SYNTHETIC file.

import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'tests', 'golden', 'facts');

const cls = (value, confidence, evidence, missing = [], extra = {}) => ({
  value, evidence, confidence, missing_inputs: missing, ...extra,
});

const FIXTURES = {
  // -- Akuvo: the account the rubric was calibrated on. Must land on A. ------
  SYNTHETIC_akuvo: {
    SYNTHETIC: true,
    captured_at: null,
    request_id: 'synthetic-akuvo',
    org_id: '10001',
    deal_id: null,
    domain: 'akuvo.com',
    linkedin_url: 'https://www.linkedin.com/company/akuvo',
    company_name: 'Akuvo',
    hq_country: 'United States',
    hq_state: 'Colorado',
    li_headcount: 190,
    li_industry: 'Financial Services',
    li_description: 'Cloud-native lending, collections and analytics platform built for credit unions and community banks.',
    li_founded: 2019,
    li_hq: 'Denver, Colorado, United States',
    website_summary: 'Product pages describe an origination, collections and analytics suite delivered as SaaS to credit unions. Careers page lists engineering roles across platform, data and mobile. About page names a Series B raise and a leadership team drawn from core banking vendors.',
    revenue_estimate_usd: 18000000,
    revenue_source: 'Apollo',
    funding_stage: 'Series B',
    last_round_date: '2026-04-02',
    last_round_usd: 21000000,
    open_eng_roles_count: 11,
    eng_roles_open_60d_plus: 4,
    senior_eng_roles: 2,
    eng_headcount_estimate: 62,
    news_last_12mo: [
      { date: '2026-04-02', headline: 'Akuvo raises $21M Series B to expand collections platform', source: 'Finextra', url: null },
      { date: '2026-06-18', headline: 'Akuvo names new VP of Engineering', source: 'company blog', url: null },
    ],
    synthetic_classifier_output: {
      industry_vertical: cls('FinTech', 'high', [
        'li_industry: Financial Services',
        'website_summary: origination, collections and analytics suite delivered as SaaS to credit unions',
      ]),
      stage_maturity: cls(10, 'high', [
        'funding_stage: Series B',
        'eng_roles_open_60d_plus: 4',
      ]),
      company_type: cls(10, 'high', ['li_description: Cloud-native lending … platform']),
      geography: cls(10, 'high', ['hq_country: United States', 'hq_state: Colorado']),
      revenue_range: cls(7, 'medium', ['revenue_estimate_usd: 18000000', 'revenue_source: Apollo']),
      activation_state: cls('Accelerating', 'high', [
        'last_round_date: 2026-04-02',
        'news_last_12mo: 2026-06-18 — names new VP of Engineering',
      ], [], { evidence_dated_within_months: 3 }),
      buying_signal: cls(7, 'high', ['eng_roles_open_60d_plus: 4', 'last_round_usd: 21000000']),
    },
  },

  // -- Microsoft: an Anchor vertical the composite must still gate out ------
  SYNTHETIC_microsoft: {
    SYNTHETIC: true,
    captured_at: null,
    request_id: 'synthetic-microsoft',
    org_id: '10002',
    deal_id: null,
    domain: 'microsoft.com',
    linkedin_url: 'https://www.linkedin.com/company/microsoft',
    company_name: 'Microsoft',
    hq_country: 'United States',
    hq_state: 'Washington',
    li_headcount: 228000,
    li_industry: 'Software Development',
    li_description: 'Technology company producing computer software, consumer electronics, personal computers and cloud services.',
    li_founded: 1975,
    li_hq: 'Redmond, Washington, United States',
    website_summary: 'Azure, Microsoft 365, Dynamics, Windows, gaming and devices. Careers pages list tens of thousands of engineering roles filled internally across dozens of countries. No indication of engineering capacity being sourced externally.',
    revenue_estimate_usd: 245000000000,
    revenue_source: 'Apollo',
    funding_stage: 'Public',
    last_round_date: null,
    last_round_usd: null,
    open_eng_roles_count: 4200,
    eng_roles_open_60d_plus: 900,
    senior_eng_roles: 700,
    eng_headcount_estimate: 90000,
    news_last_12mo: [
      { date: '2026-05-20', headline: 'Microsoft expands datacentre capacity for AI workloads', source: 'Reuters', url: null },
    ],
    synthetic_classifier_output: {
      industry_vertical: cls('Enterprise Tech / Hyperscalers', 'high', [
        'li_industry: Software Development',
        'website_summary: Azure, Microsoft 365, Dynamics, Windows, gaming and devices',
      ]),
      stage_maturity: cls(0, 'high', [
        'eng_headcount_estimate: 90000',
        'website_summary: engineering roles filled internally … no indication of engineering capacity being sourced externally',
      ]),
      company_type: cls(10, 'high', ['li_description: computer software … and cloud services']),
      geography: cls(10, 'high', ['hq_country: United States', 'hq_state: Washington']),
      revenue_range: cls(0, 'high', ['revenue_estimate_usd: 245000000000', 'revenue_source: Apollo']),
      activation_state: cls('Stable', 'high', ['news_last_12mo: 1 item, capacity expansion, not a transformation']),
      buying_signal: cls(3, 'low', ['open_eng_roles_count: 4200 — volume, not a targeted cluster']),
    },
  },

  // -- Merck: a Watch vertical on the Tier 2 path ---------------------------
  SYNTHETIC_merck: {
    SYNTHETIC: true,
    captured_at: null,
    request_id: 'synthetic-merck',
    org_id: '10003',
    deal_id: null,
    domain: 'merck.com',
    linkedin_url: 'https://www.linkedin.com/company/merck',
    company_name: 'Merck',
    hq_country: 'United States',
    hq_state: 'New Jersey',
    li_headcount: 71000,
    li_industry: 'Pharmaceutical Manufacturing',
    li_description: 'Global biopharmaceutical company researching, developing and manufacturing prescription medicines and vaccines.',
    li_founded: 1891,
    li_hq: 'Rahway, New Jersey, United States',
    website_summary: 'Therapeutic areas, pipeline and manufacturing. A digital and data science organisation is described as building validated internal platforms for clinical trial operations and manufacturing telemetry under GxP constraints.',
    revenue_estimate_usd: 64000000000,
    revenue_source: 'Apollo',
    funding_stage: 'Public',
    last_round_date: null,
    last_round_usd: null,
    open_eng_roles_count: 40,
    eng_roles_open_60d_plus: 11,
    senior_eng_roles: 6,
    eng_headcount_estimate: 4000,
    news_last_12mo: [
      { date: '2026-02-14', headline: 'Merck expands data science hub', source: 'Fierce Pharma', url: null },
    ],
    synthetic_classifier_output: {
      industry_vertical: cls('Pharma / Life Sciences', 'high', ['li_industry: Pharmaceutical Manufacturing']),
      stage_maturity: cls(0, 'high', [
        'li_headcount: 71000',
        'eng_headcount_estimate: 4000',
      ]),
      company_type: cls(7, 'high', [
        'website_summary: validated internal platforms … under GxP constraints',
      ]),
      geography: cls(10, 'high', ['hq_country: United States', 'hq_state: New Jersey']),
      revenue_range: cls(0, 'high', ['revenue_estimate_usd: 64000000000', 'revenue_source: Apollo']),
      activation_state: cls('Stable', 'medium', ['news_last_12mo: 2026-02-14 — data science hub expansion']),
      buying_signal: cls(3, 'medium', ['eng_roles_open_60d_plus: 11']),
    },
  },
};

for (const [name, facts] of Object.entries(FIXTURES)) {
  writeFileSync(join(OUT, `${name}.json`), `${JSON.stringify(facts, null, 2)}\n`, 'utf8');
  process.stdout.write(`wrote tests/golden/facts/${name}.json (SYNTHETIC)\n`);
}
