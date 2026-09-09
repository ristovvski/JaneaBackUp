#!/usr/bin/env node
// scripts/export_golden_set.mjs — Test Accounts CSV -> tests/golden/expected.json
//
// Nik exports the "Test Accounts" sheet from the ICP workbook as CSV and points
// this at it:
//
//   node scripts/export_golden_set.mjs path/to/Test_Accounts.csv
//   ICP_TEST_ACCOUNTS_CSV=path/to/file.csv npm run golden:export
//
// With no CSV it does NOT invent rows and does NOT wipe what is there: it
// reports what the existing expected.json holds and exits 0, so `npm test`
// keeps working before the sheet lands.
//
// Expected CSV headers (case- and space-insensitive, extra columns ignored):
//   Account | Vertical | Activation | Expected Grade
// `Expected Grade` is blank for most rows until Toby fills in Stage/Type/Geo/
// Revenue. A blank grade is preserved as null, and golden.test.mjs then asserts
// only the vertical -> industry_level mapping for that row.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, basename } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tests', 'golden', 'expected.json');
const RUBRIC = JSON.parse(readFileSync(join(ROOT, 'config', 'rubric_v5.json'), 'utf8'));

const csvPath = process.argv[2] || process.env.ICP_TEST_ACCOUNTS_CSV || null;

/** RFC 4180-ish parser: quoted fields, embedded commas, doubled quotes, CRLF. */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 1; } else { quoted = false; }
      } else { field += ch; }
      continue;
    }
    if (ch === '"') { quoted = true; continue; }
    if (ch === ',') { row.push(field); field = ''; continue; }
    if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i += 1;
      row.push(field); field = '';
      if (row.some((f) => f.trim() !== '')) rows.push(row);
      row = [];
      continue;
    }
    field += ch;
  }
  row.push(field);
  if (row.some((f) => f.trim() !== '')) rows.push(row);
  return rows;
}

const norm = (s) => String(s || '').trim().toLowerCase().replace(/[\s_]+/g, ' ');

/** Map a sheet vertical string onto a rubric vertical, or report it unmatched. */
function matchVertical(raw) {
  const value = String(raw || '').trim();
  if (value === '') return null;
  const verticals = Object.keys(RUBRIC.industry_verticals);
  const exact = verticals.find((v) => v === value);
  if (exact) return exact;
  // Tolerate hyphen/en-dash and spacing differences, nothing more. A vertical
  // the sheet spells differently is a discrepancy worth reporting, not
  // silently coercing.
  const loose = (s) => s.toLowerCase().replace(/[\s—–-]+/g, '');
  return verticals.find((v) => loose(v) === loose(value)) || { unmatched: value };
}

if (!csvPath) {
  process.stdout.write('No CSV given (argv[1] or ICP_TEST_ACCOUNTS_CSV).\n');
  if (existsSync(OUT)) {
    const current = JSON.parse(readFileSync(OUT, 'utf8'));
    const graded = current.accounts.filter((a) => a.expected_grade !== null).length;
    process.stdout.write(
      `Left tests/golden/expected.json untouched: ${current.accounts.length} accounts, ` +
      `${graded} with a human grade, source "${current.source}".\n`
    );
  } else {
    process.stdout.write('tests/golden/expected.json does not exist yet.\n');
  }
  process.stdout.write(
    '\nTo populate it: export the "Test Accounts" sheet as CSV and re-run with the path.\n'
  );
  process.exit(0);
}

if (!existsSync(csvPath)) {
  process.stderr.write(`CSV not found: ${csvPath}\n`);
  process.exit(1);
}

const rows = parseCsv(readFileSync(csvPath, 'utf8'));
if (rows.length < 2) {
  process.stderr.write('CSV has no data rows.\n');
  process.exit(1);
}

const header = rows[0].map(norm);
const col = (...names) => {
  for (const name of names) {
    const idx = header.indexOf(norm(name));
    if (idx !== -1) return idx;
  }
  return -1;
};

const iAccount = col('account', 'org', 'organization', 'company', 'company name');
const iVertical = col('vertical', 'industry vertical', 'industry');
const iActivation = col('activation', 'activation state');
const iGrade = col('expected grade', 'grade', 'expected', 'icp');

if (iAccount === -1) {
  process.stderr.write(`No account column found. Headers seen: ${rows[0].join(' | ')}\n`);
  process.exit(1);
}

const existing = existsSync(OUT) ? JSON.parse(readFileSync(OUT, 'utf8')) : { accounts: [] };
const priorByOrg = new Map(existing.accounts.map((a) => [norm(a.org), a]));

const accounts = [];
const discrepancies = [];

for (const row of rows.slice(1)) {
  const org = String(row[iAccount] || '').trim();
  if (org === '') continue;

  const verticalRaw = iVertical === -1 ? '' : row[iVertical];
  const matched = matchVertical(verticalRaw);
  let vertical = null;
  if (matched && matched.unmatched) {
    discrepancies.push(`${org}: vertical "${matched.unmatched}" is not one of the 17 rubric verticals`);
  } else {
    vertical = matched;
  }

  const activationRaw = iActivation === -1 ? '' : String(row[iActivation] || '').trim();
  let activation = null;
  if (activationRaw !== '') {
    const states = Object.keys(RUBRIC.activation_multipliers);
    activation = states.find((s) => norm(s) === norm(activationRaw)) || null;
    if (activation === null) {
      discrepancies.push(`${org}: activation "${activationRaw}" is not one of ${states.join('/')}`);
    }
  }

  const gradeRaw = iGrade === -1 ? '' : String(row[iGrade] || '').trim();
  let expectedGrade = null;
  if (gradeRaw !== '') {
    const m = gradeRaw.toUpperCase().match(/\b([ABC])\b/);
    if (m) expectedGrade = m[1];
    else discrepancies.push(`${org}: expected grade "${gradeRaw}" is not A, B or C`);
  }

  // Hard assertions and facts_file bindings are properties of this repo, not
  // of the sheet, so carry them forward from the existing file.
  const prior = priorByOrg.get(norm(org)) || {};

  accounts.push({
    org,
    facts_file: prior.facts_file || null,
    vertical,
    activation,
    expected_grade: expectedGrade,
    hard_assertion: prior.hard_assertion || null,
  });
}

// Keep any prior account the sheet no longer lists, so the three hard
// assertions cannot be dropped by an incomplete export.
for (const prior of existing.accounts) {
  if (!accounts.some((a) => norm(a.org) === norm(prior.org))) {
    accounts.push({ ...prior, _retained: 'not present in the latest CSV export' });
  }
}

const out = {
  _comment: 'GENERATED by scripts/export_golden_set.mjs from the Test Accounts sheet. facts_file and hard_assertion are repo-side bindings and are carried forward across exports.',
  source: basename(csvPath),
  exported_at: new Date().toISOString(),
  model_version: RUBRIC.model_version,
  accounts,
};

writeFileSync(OUT, `${JSON.stringify(out, null, 2)}\n`, 'utf8');

const graded = accounts.filter((a) => a.expected_grade !== null).length;
process.stdout.write(
  `wrote tests/golden/expected.json — ${accounts.length} accounts, ${graded} with a human grade\n`
);
if (discrepancies.length > 0) {
  process.stdout.write(`\n${discrepancies.length} discrepancy/ies against the rubric:\n`);
  for (const d of discrepancies) process.stdout.write(`  - ${d}\n`);
  process.stdout.write('\nThe CSV wins on business content; these are reported, not corrected.\n');
}
