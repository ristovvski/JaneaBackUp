#!/usr/bin/env node
// scripts/pipedrive_audit_coverage.mjs — Phase 0 coverage audit. READ ONLY.
//
// Answers the questions Phase 1 stands or falls on:
//   1. Can we identify an organization at all? (native website / linkedin,
//      plus the four overlapping custom URL fields FIELD_AUDIT.md found)
//   2. How many organizations are duplicates of each other, by root domain and
//      by normalized name?
//   3. How many already carry an ICP field?
//   4. How dirty is the data we would feed Clay? (LinkedIn URLs typed into the
//      website field, people URLs, placeholder text, ...)
//
// This script makes ZERO writes. It issues only GETs. Run it before anything
// else touches the account.
//
// Two input modes:
//
//   live   PIPEDRIVE_API_TOKEN is set -> pages the whole org collection over
//          the v2 API and resolves custom field keys to names over v1
//          /organizationFields. This is the real audit.
//
//   pages  --pages <dir> -> aggregates saved getOrganizations JSON pages
//          (e.g. captured through the Pipedrive MCP server when no API token
//          is available). Same aggregation, stated as a sample, and custom
//          field keys stay unresolved because /organizationFields needs a
//          token.
//
// Output: reports/coverage.md

import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { basename, dirname, join } from 'node:path';
import {
  normalizeDomain, normalizeLinkedInCompanyUrl, normalizeCompanyName, NON_COMPANY_HOSTS,
} from '../engine/normalize.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'reports', 'coverage.md');
const BASE = 'https://api.pipedrive.com';

const argPages = (() => {
  const i = process.argv.indexOf('--pages');
  return i !== -1 ? process.argv[i + 1] : null;
})();
const token = process.env.PIPEDRIVE_API_TOKEN || null;

// --------------------------------------------------------------------------
// Fetch helpers (live mode)
// --------------------------------------------------------------------------

async function get(path, params = {}) {
  const url = new URL(path, BASE);
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined) url.searchParams.set(k, String(v));
  }
  // The token goes in the header, never in the URL: a URL ends up in logs.
  const response = await fetch(url, {
    headers: { 'x-api-token': token, accept: 'application/json' },
  });
  if (response.status === 429) {
    const wait = Number(response.headers.get('retry-after') || 2) * 1000;
    process.stderr.write(`  429 — backing off ${wait}ms\n`);
    await new Promise((r) => setTimeout(r, wait));
    return get(path, params);
  }
  if (!response.ok) {
    throw new Error(`GET ${path} -> ${response.status}: ${(await response.text()).slice(0, 300)}`);
  }
  return response.json();
}

async function fetchAllOrgs() {
  const orgs = [];
  let cursor = null;
  let page = 0;
  do {
    const payload = await get('/api/v2/organizations', { limit: 500, cursor });
    orgs.push(...(payload.data || []));
    cursor = payload.additional_data?.next_cursor || null;
    page += 1;
    process.stderr.write(`  page ${page}: ${orgs.length} organizations\n`);
  } while (cursor);
  return orgs;
}

async function fetchOrgFieldNames() {
  // v2 organizationFields, cursor-paginated (limit max 500).
  const byKey = {};
  let cursor = null;
  do {
    const payload = await get('/api/v2/organizationFields', { limit: 500, cursor });
    for (const field of payload.data || []) {
      byKey[field.key] = { name: field.name, type: field.field_type, id: field.id };
    }
    cursor = payload.additional_data?.next_cursor || null;
  } while (cursor);
  return byKey;
}

// --------------------------------------------------------------------------
// Load
// --------------------------------------------------------------------------

let orgs = [];
let fieldNames = {};
let mode;
let sourceNote;

if (argPages) {
  mode = 'pages';
  if (!existsSync(argPages)) {
    process.stderr.write(`--pages directory not found: ${argPages}\n`);
    process.exit(1);
  }
  const files = readdirSync(argPages).filter((f) => f.endsWith('.json')).sort();
  if (files.length === 0) {
    process.stderr.write(`no .json pages in ${argPages}\n`);
    process.exit(1);
  }
  for (const file of files) {
    const payload = JSON.parse(readFileSync(join(argPages, file), 'utf8'));
    orgs.push(...(payload.data || []));
  }
  // Only the directory NAME goes in the report. An absolute path can carry a
  // session id or a username, and this file is committed.
  const pagesLabel = basename(argPages.replace(/\/+$/, '')) || '(pages)';
  sourceNote =
    `SAMPLE of ${orgs.length} organizations from ${files.length} saved getOrganizations ` +
    `page(s) (source directory \`${pagesLabel}\`), newest-first by add_time. Custom field keys ` +
    `are NOT resolved to names in this mode (that needs GET /api/v2/organizationFields, which ` +
    `needs a token).`;
} else if (token) {
  mode = 'live';
  process.stderr.write('Live mode: paging the full organization collection (read-only)...\n');
  [orgs, fieldNames] = await Promise.all([fetchAllOrgs(), fetchOrgFieldNames()]);
  sourceNote = `FULL PASS over ${orgs.length} organizations via GET /api/v2/organizations, with ` +
    `custom field keys resolved via GET /v1/organizationFields. Read-only.`;
} else {
  process.stderr.write(
    'Neither PIPEDRIVE_API_TOKEN nor --pages <dir> given.\n\n' +
    '  Full audit:   PIPEDRIVE_API_TOKEN=... npm run audit:coverage\n' +
    '  From pages:   node scripts/pipedrive_audit_coverage.mjs --pages ./pd-pages\n'
  );
  process.exit(1);
}

if (orgs.length === 0) {
  process.stderr.write('No organizations loaded.\n');
  process.exit(1);
}

// --------------------------------------------------------------------------
// Aggregate
// --------------------------------------------------------------------------

const live = orgs.filter((o) => !o.is_deleted);
const deleted = orgs.length - live.length;

const pct = (n) => `${((n / live.length) * 100).toFixed(1)}%`;

// -- identifier reachability ----------------------------------------------
const stats = {
  nativeWebsite: 0,
  nativeLinkedin: 0,
  usableDomain: 0,
  usableLinkedin: 0,
  neither: 0,
  nameOnly: 0,
  noName: 0,
};

// -- data-quality defects --------------------------------------------------
const defects = {
  websiteHoldsLinkedIn: [],
  websiteHoldsPeopleUrl: [],
  websiteUnparseable: [],
  linkedinHoldsNonCompany: [],
  websiteIsAggregator: [],
};

// Shared with engine/normalize.mjs so the audit and the resolver can never
// disagree about what counts as a company domain.
const AGGREGATOR_HOSTS = NON_COMPANY_HOSTS;

const byDomain = new Map();
const byName = new Map();
const customFieldFill = new Map();

for (const org of live) {
  const rawWebsite = org.website || null;
  const rawLinkedin = org.linkedin || null;

  if (rawWebsite) stats.nativeWebsite += 1;
  if (rawLinkedin) stats.nativeLinkedin += 1;

  // A LinkedIn URL typed into the website field is the defect that matters
  // most: normalizeDomain would reduce it to `linkedin.com` and Clay would
  // enrich LinkedIn Corporation instead of the account.
  let domain = null;
  if (rawWebsite) {
    const asLinkedIn = normalizeLinkedInCompanyUrl(rawWebsite);
    const asDomain = normalizeDomain(rawWebsite);
    if (asLinkedIn) {
      defects.websiteHoldsLinkedIn.push({ id: org.id, name: org.name, value: rawWebsite });
    } else if (asDomain === 'linkedin.com') {
      defects.websiteHoldsPeopleUrl.push({ id: org.id, name: org.name, value: rawWebsite });
    } else if (asDomain === null) {
      defects.websiteUnparseable.push({ id: org.id, name: org.name, value: rawWebsite });
    } else if (AGGREGATOR_HOSTS.has(asDomain)) {
      defects.websiteIsAggregator.push({ id: org.id, name: org.name, value: rawWebsite });
    } else {
      domain = asDomain;
    }
  }

  let linkedin = rawLinkedin ? normalizeLinkedInCompanyUrl(rawLinkedin) : null;
  if (rawLinkedin && !linkedin) {
    defects.linkedinHoldsNonCompany.push({ id: org.id, name: org.name, value: rawLinkedin });
  }
  // A LinkedIn company URL in the website field is still a usable identifier —
  // just of the other kind. Recover it rather than throwing it away.
  if (!linkedin && rawWebsite) linkedin = normalizeLinkedInCompanyUrl(rawWebsite);

  if (domain) stats.usableDomain += 1;
  if (linkedin) stats.usableLinkedin += 1;

  const name = normalizeCompanyName(org.name);
  if (!name) stats.noName += 1;

  if (!domain && !linkedin) {
    stats.neither += 1;
    if (name) stats.nameOnly += 1;
  }

  if (domain) {
    if (!byDomain.has(domain)) byDomain.set(domain, []);
    byDomain.get(domain).push({ id: org.id, name: org.name });
  }
  if (name) {
    if (!byName.has(name)) byName.set(name, []);
    byName.get(name).push({ id: org.id, name: org.name });
  }

  for (const [key, value] of Object.entries(org.custom_fields || {})) {
    if (!customFieldFill.has(key)) customFieldFill.set(key, 0);
    if (value !== null && value !== undefined && value !== '') {
      customFieldFill.set(key, customFieldFill.get(key) + 1);
    }
  }
}

const domainClusters = [...byDomain.entries()].filter(([, v]) => v.length > 1)
  .sort((a, b) => b[1].length - a[1].length);
const nameClusters = [...byName.entries()].filter(([, v]) => v.length > 1)
  .sort((a, b) => b[1].length - a[1].length);

const dupOrgsByDomain = domainClusters.reduce((n, [, v]) => n + v.length, 0);
const dupOrgsByName = nameClusters.reduce((n, [, v]) => n + v.length, 0);
const excessByDomain = domainClusters.reduce((n, [, v]) => n + v.length - 1, 0);
const excessByName = nameClusters.reduce((n, [, v]) => n + v.length - 1, 0);

// -- existing ICP fields ---------------------------------------------------
const icpish = [...customFieldFill.keys()].filter((key) => {
  const name = fieldNames[key]?.name;
  return name && /\bicp\b|ideal customer/i.test(name);
});
const orgsWithAnyIcpField = icpish.length === 0 ? 0 : live.filter((org) =>
  icpish.some((key) => {
    const v = (org.custom_fields || {})[key];
    return v !== null && v !== undefined && v !== '';
  })
).length;

// --------------------------------------------------------------------------
// Render
// --------------------------------------------------------------------------

const addTimes = live.map((o) => o.add_time).filter(Boolean).sort();
const table = (rows) => rows.map((r) => `| ${r.join(' | ')} |`).join('\n');

const sample = (list, n = 8) => list.slice(0, n)
  .map((d) => `| ${d.id} | ${String(d.name).slice(0, 44)} | \`${String(d.value).slice(0, 60)}\` |`)
  .join('\n');

const md = `# Phase 0 — Pipedrive organization coverage audit

**Read-only.** This run issued only GET requests and made no writes of any kind.

- **Mode:** ${mode}
- **Scope:** ${sourceNote}
- **Organizations analysed:** ${live.length}${deleted > 0 ? ` (${deleted} soft-deleted excluded)` : ''}
- **add_time range:** ${addTimes[0] || 'n/a'} → ${addTimes[addTimes.length - 1] || 'n/a'}
- **Generated:** ${new Date().toISOString()}

---

## 1. Can we identify an organization? (the Phase 1 gate)

\`engine/normalize.mjs\` \`resolveIdentifier()\` picks **domain → LinkedIn company URL → name**.
This is what Clay receives, so this table is the ceiling on enrichment quality.

${table([
  ['Signal', 'Orgs', 'Share', 'Meaning'],
  ['---', '---:', '---:', '---'],
  ['Native `website` non-empty', String(stats.nativeWebsite), pct(stats.nativeWebsite), 'a value is present'],
  ['→ of those, a **usable root domain**', String(stats.usableDomain), pct(stats.usableDomain), 'survives normalization and is not an aggregator'],
  ['Native `linkedin` non-empty', String(stats.nativeLinkedin), pct(stats.nativeLinkedin), 'a value is present'],
  ['→ **usable LinkedIn company URL** (either field)', String(stats.usableLinkedin), pct(stats.usableLinkedin), 'includes URLs recovered from the website field'],
  ['**Neither** domain nor LinkedIn', String(stats.neither), pct(stats.neither), 'scored from name + HQ at low confidence (NEEDS_DECISION #5)'],
  ['→ of those, at least a usable name', String(stats.nameOnly), pct(stats.nameOnly), 'still scoreable'],
  ['No usable name at all', String(stats.noName), pct(stats.noName), 'not scoreable — cannot even be looked up'],
])}

**Read this before Tuesday.** ${pct(stats.usableDomain)} of organizations yield a usable root
domain. The other ${pct(live.length - stats.usableDomain)} reach Clay as a LinkedIn URL or as a bare
name, and a bare name is explicitly a low-confidence identifier. Since \`revenue_range\`,
\`stage_maturity\` and \`company_type\` all gate \`insufficient_data\`, expect a
substantial share of first-pass results to come back **Insufficient data** rather than graded.
That is the system working as specified, not a failure — but it is what the demo will show.

## 2. Data-quality defects in the identifier fields

These are the ones that would silently corrupt a score rather than fail loudly.

${table([
  ['Defect', 'Count', 'Share', 'Why it matters'],
  ['---', '---:', '---:', '---'],
  ['`website` holds a LinkedIn **company** URL', String(defects.websiteHoldsLinkedIn.length), pct(defects.websiteHoldsLinkedIn.length), 'naive domain normalization yields `linkedin.com` → Clay enriches LinkedIn Corporation'],
  ['`website` holds another LinkedIn URL (person/school)', String(defects.websiteHoldsPeopleUrl.length), pct(defects.websiteHoldsPeopleUrl.length), 'same failure, and not recoverable as a company'],
  ['`website` holds another aggregator/social host', String(defects.websiteIsAggregator.length), pct(defects.websiteIsAggregator.length), 'enriches the platform, not the company'],
  ['`website` unparseable', String(defects.websiteUnparseable.length), pct(defects.websiteUnparseable.length), 'placeholder text, prose, or a malformed URL'],
  ['`linkedin` is not a company URL', String(defects.linkedinHoldsNonCompany.length), pct(defects.linkedinHoldsNonCompany.length), 'a person profile is not a company identifier'],
])}

${defects.websiteHoldsLinkedIn.length > 0 ? `### Sample: LinkedIn company URLs stored in \`website\`

| org id | name | website value |
|---|---|---|
${sample(defects.websiteHoldsLinkedIn)}

**Handled.** \`resolveIdentifier()\` tries \`normalizeLinkedInCompanyUrl\` on the website field
before treating it as a domain, so these are routed to the \`linkedin\` identifier kind instead of
collapsing to \`linkedin.com\`. Note that the sampled rows show the LinkedIn URL does not always
name the same company as the org record — that is a data problem no normalizer can fix, and a
reason to prefer the native \`linkedin\` field where both are present.
` : ''}
${defects.websiteUnparseable.length > 0 ? `### Sample: unparseable \`website\` values

| org id | name | website value |
|---|---|---|
${sample(defects.websiteUnparseable)}
` : ''}
${defects.websiteIsAggregator.length > 0 ? `### Sample: aggregator hosts in \`website\`

| org id | name | website value |
|---|---|---|
${sample(defects.websiteIsAggregator)}
` : ''}

## 3. Duplicate clusters

A duplicate cluster means two or more organization records that Phase 1 would score
**separately**, producing two grades for one company and two notes for one buyer.

${table([
  ['Clustering key', 'Clusters', 'Orgs in a cluster', 'Excess records'],
  ['---', '---:', '---:', '---:'],
  ['Root domain (`normalizeDomain`)', String(domainClusters.length), `${dupOrgsByDomain} (${pct(dupOrgsByDomain)})`, String(excessByDomain)],
  ['Normalized name (`normalizeCompanyName`)', String(nameClusters.length), `${dupOrgsByName} (${pct(dupOrgsByName)})`, String(excessByName)],
])}

${mode === 'pages' ? `> **Sample caveat, and it is a big one.** Duplicate detection on a sample
> systematically *undercounts*: for two records of one company to be seen as a pair, both must fall
> inside the sample. On a ${live.length}-record slice of a larger collection the true cluster count is
> materially higher than the figure above. Treat these numbers as a floor, and re-run in live mode
> for the real count.

` : ''}${domainClusters.length > 0 ? `### Largest domain clusters

${domainClusters.slice(0, 10).map(([domain, members]) =>
  `- **${domain}** — ${members.length} records: ${members.slice(0, 6).map((m) => `${m.name} (#${m.id})`).join(', ')}${members.length > 6 ? ', …' : ''}`
).join('\n')}
` : '_No domain clusters in this scope._'}

${nameClusters.length > 0 ? `### Largest normalized-name clusters

${nameClusters.slice(0, 10).map(([name, members]) =>
  `- **${name}** — ${members.length} records: ${members.slice(0, 6).map((m) => `${m.name} (#${m.id})`).join(', ')}${members.length > 6 ? ', …' : ''}`
).join('\n')}
` : '_No name clusters in this scope._'}

**Out of Phase 1 by scope.** Dedup and org creation are explicitly not in this build. The audit
records the size of the problem so the decision to defer it is an informed one. The practical
consequence for the demo: a duplicated company can show two different grades, and the honest
answer to "why?" is "because there are two records."

## 4. Organizations already carrying an ICP field

${icpish.length === 0
  ? mode === 'live'
    ? '**None.** No organization custom field has a name matching `/\\bicp\\b|ideal customer/i`, so no organization can already hold an ICP value. `scripts/pipedrive_create_fields.mjs` will create all five fields on its first run.'
    : '**Not determinable in `pages` mode.** Matching a field by *name* needs `GET /api/v2/organizationFields`, which needs `PIPEDRIVE_API_TOKEN`. Re-run in live mode to answer this. What the sample does show is the per-key fill rate below.'
  : `Matched ICP-ish fields: ${icpish.map((k) => `\`${fieldNames[k].name}\``).join(', ')}.
**${orgsWithAnyIcpField} organizations (${pct(orgsWithAnyIcpField)}) already carry a value in at least one.**
Those values were written by a human or a prior process. \`ICP Final\` is never touched;
\`ICP Calculated\` is overwritten only when the computed value differs.`}

### Custom-field fill rates in this scope

${customFieldFill.size === 0 ? '_No custom fields were requested in this scope._' : table([
  ['Field key', 'Name', 'Non-empty', 'Share'],
  ['---', '---', '---:', '---:'],
  ...[...customFieldFill.entries()].sort((a, b) => b[1] - a[1]).slice(0, 30).map(([key, n]) =>
    [`\`${key.slice(0, 12)}…\``, fieldNames[key]?.name || '_(needs a token to resolve)_', String(n), pct(n)]
  ),
])}

---

## Findings that change the build

1. **The native \`website\` field is not a clean domain source.** It is the field
   \`resolveIdentifier()\` reads first, and in this scope
   ${defects.websiteHoldsLinkedIn.length + defects.websiteHoldsPeopleUrl.length + defects.websiteIsAggregator.length + defects.websiteUnparseable.length}
   record(s) hold something that is not the company's own domain. \`resolveIdentifier()\` handles
   this by trying the LinkedIn parse first and rejecting aggregator hosts — without that, those
   organizations would be enriched as LinkedIn, Facebook or Google.
2. **\`docs/DISCOVERY/FIELD_AUDIT.md\` (2026-07-23) found four overlapping custom URL fields** on
   organizations — \`Website\`, \`LinkedIn URL\`, \`lh_website\`, \`Website URL\` — at 20.7 / 18.0 /
   17.7 / 17.7% fill. Phase 1 reads only the **native** \`website\` and \`linkedin\` fields.
   If the native fields are emptier than those custom fields, identifier coverage improves by
   reading the custom fields as a fallback. That is a one-line CONFIG addition, and it is
   **NEEDS_DECISION**: which of the four is canonical is a data-ownership question, not a
   technical one.
3. **Duplicates are real and out of scope.** See §3.

## How to re-run

\`\`\`bash
# Full audit (read-only; needs a token with read access to organizations)
PIPEDRIVE_API_TOKEN=... npm run audit:coverage

# From saved MCP pages, no token needed
node scripts/pipedrive_audit_coverage.mjs --pages ./pd-pages
\`\`\`
`;

writeFileSync(OUT, md, 'utf8');
process.stdout.write(`wrote reports/coverage.md (${md.length} bytes) — ${live.length} organizations, mode=${mode}\n`);
