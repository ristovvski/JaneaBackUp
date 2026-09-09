#!/usr/bin/env node
// scripts/pipedrive_create_fields.mjs — create the five ICP organization fields.
//
// IDEMPOTENT BY CONSTRUCTION. Matching is by field NAME against the live
// account. A field that already exists is adopted, never recreated and never
// modified. A second run reports "0 created, 5 found" and changes nothing.
//
// Writes the resolved keys and enum option ids into config/pipedrive_fields.json,
// which is the only place CONFIG gets them from (npm run gen:config).
//
//   PIPEDRIVE_API_TOKEN=... npm run pipedrive:fields
//   PIPEDRIVE_API_TOKEN=... node scripts/pipedrive_create_fields.mjs --dry-run
//
// API evidence (developers.pipedrive.com, Organization Fields):
//   POST /api/v2/organizationFields  body: { field_name, field_type, options }
//   field_type: varchar | text | double | date | enum | set | ...
//   options for enum/set: [{ "label": "..." }]
//   GET  /api/v2/organizationFields  params: limit (max 500), cursor
//
// The option-id shape of the response is NOT documented. Writing an enum by
// option id (§8.2) requires it, so this script reads options[].id back and
// FAILS LOUDLY with NEEDS_DOC_EVIDENCE rather than guessing if it is absent.

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
// The template is committed and always holds placeholders. A live run writes
// the .local.json beside it, which is gitignored: real field keys and option
// ids are account identifiers and have no business in git (SECURITY.md
// excludes API captures for exactly this reason). npm run gen:config prefers
// the .local.json when it exists.
const TEMPLATE = join(ROOT, 'config', 'pipedrive_fields.json');
const REGISTRY = join(ROOT, 'config', 'pipedrive_fields.local.json');
const BASE = 'https://api.pipedrive.com';

const token = process.env.PIPEDRIVE_API_TOKEN;
const dryRun = process.argv.includes('--dry-run');

if (!token) {
  process.stderr.write(
    'PIPEDRIVE_API_TOKEN is not set.\n\n' +
    '  PIPEDRIVE_API_TOKEN=... npm run pipedrive:fields\n' +
    '  PIPEDRIVE_API_TOKEN=... node scripts/pipedrive_create_fields.mjs --dry-run\n\n' +
    'The token is read from the environment only. It is never written to a file,\n' +
    'never put in a URL, and never logged.\n'
  );
  process.exit(1);
}

// Start from the live registry if a previous run produced one, so re-running
// is genuinely idempotent; otherwise from the committed template.
const registry = JSON.parse(readFileSync(existsSync(REGISTRY) ? REGISTRY : TEMPLATE, 'utf8'));

async function api(method, path, body = null) {
  const response = await fetch(new URL(path, BASE), {
    method,
    headers: {
      'x-api-token': token,
      accept: 'application/json',
      ...(body ? { 'content-type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (response.status === 429) {
    const wait = Number(response.headers.get('retry-after') || 2) * 1000;
    process.stderr.write(`  429 — backing off ${wait}ms\n`);
    await new Promise((r) => setTimeout(r, wait));
    return api(method, path, body);
  }
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status}: ${text.slice(0, 400)}`);
  }
  return text ? JSON.parse(text) : {};
}

async function listOrgFields() {
  const fields = [];
  let cursor = null;
  do {
    const params = new URLSearchParams({ limit: '500' });
    if (cursor) params.set('cursor', cursor);
    const payload = await api('GET', `/api/v2/organizationFields?${params}`);
    fields.push(...(payload.data || []));
    cursor = payload.additional_data?.next_cursor || null;
  } while (cursor);
  return fields;
}

/** Compare field names the way a human would: case- and space-insensitively. */
const nameKey = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');

process.stderr.write('Reading the existing organization fields (read-only)...\n');
const existing = await listOrgFields();
const existingByName = new Map(existing.map((f) => [nameKey(f.name), f]));
process.stderr.write(`  ${existing.length} organization fields in the account\n\n`);

const summary = { created: [], found: [], optionsAdded: [], problems: [] };

for (const [slug, spec] of Object.entries(registry.fields)) {
  const wanted = spec.name;
  let field = existingByName.get(nameKey(wanted));

  if (field) {
    summary.found.push(wanted);
    process.stderr.write(`FOUND    ${wanted} (key ${field.key}, type ${field.field_type})\n`);
    if (field.field_type !== spec.field_type) {
      summary.problems.push(
        `"${wanted}" exists with type "${field.field_type}" but the registry expects ` +
        `"${spec.field_type}". Not modified — changing a live field's type is a data decision, ` +
        `not a script's call.`
      );
    }
  } else if (dryRun) {
    process.stderr.write(`WOULD CREATE  ${wanted} (${spec.field_type})\n`);
    continue;
  } else {
    const body = { field_name: wanted, field_type: spec.field_type };
    if (spec.options) body.options = Object.keys(spec.options).map((label) => ({ label }));
    const created = await api('POST', '/api/v2/organizationFields', body);
    field = created.data;
    summary.created.push(wanted);
    process.stderr.write(`CREATED  ${wanted} (key ${field.key}, type ${field.field_type})\n`);
  }

  // --- resolve the key and, for enums, every option id --------------------
  spec.key = field.key;
  spec.id = field.id ?? null;

  if (spec.options) {
    const live = field.options || [];
    if (live.length === 0) {
      summary.problems.push(
        `NEEDS_DOC_EVIDENCE: "${wanted}" is an enum but the API response carried no options ` +
        `array. §8.2 requires enum writes by option id, and an id cannot be invented. ` +
        `Inspect GET /api/v2/organizationFields for this field and re-run.`
      );
      continue;
    }
    const liveByLabel = new Map(live.map((o) => [nameKey(o.label), o]));
    for (const [label, entry] of Object.entries(spec.options)) {
      const match = liveByLabel.get(nameKey(label));
      if (!match) {
        summary.problems.push(
          `"${wanted}" is missing the option "${label}". Options are not added to a live ` +
          `enum by this script: an option list is a business decision. Add it in Pipedrive ` +
          `and re-run.`
        );
        continue;
      }
      if (match.id === undefined || match.id === null) {
        summary.problems.push(
          `NEEDS_DOC_EVIDENCE: option "${label}" of "${wanted}" has no id in the API response. ` +
          `§8.2 requires writing enums by option id.`
        );
        continue;
      }
      entry.id = match.id;
      entry.label = match.label;
    }
    // Report options that exist in Pipedrive but not in the registry, so a
    // rep-added option is visible rather than silently ignored.
    for (const option of live) {
      if (!Object.keys(spec.options).some((l) => nameKey(l) === nameKey(option.label))) {
        process.stderr.write(
          `  note: "${wanted}" also has option "${option.label}" (id ${option.id}), ` +
          `which the registry does not use\n`
        );
      }
    }
  }
}

if (dryRun) {
  process.stderr.write(
    `\nDRY RUN — nothing was written.\n` +
    `  would create: ${registry.expected_field_count - summary.found.length}\n` +
    `  found:        ${summary.found.length}\n`
  );
  process.exit(0);
}

registry.status = 'live';
registry.generated_at = new Date().toISOString();
registry.account = existing.length > 0 ? 'resolved from the authenticated token' : null;
delete registry._comment;
registry._comment =
  'GENERATED by scripts/pipedrive_create_fields.mjs against a live Pipedrive account. ' +
  'Field keys and enum option ids are read back from the API, never invented. ' +
  'Regenerate CONFIG after any change here: npm run gen:config.';

writeFileSync(REGISTRY, `${JSON.stringify(registry, null, 2)}\n`, 'utf8');

process.stderr.write(
  `\n${summary.created.length} created, ${summary.found.length} found` +
  ` (expected ${registry.expected_field_count}).\n` +
  `wrote config/pipedrive_fields.local.json (gitignored — real field keys)\n`
);

if (summary.problems.length > 0) {
  process.stderr.write(`\n${summary.problems.length} problem(s):\n`);
  for (const p of summary.problems) process.stderr.write(`  - ${p}\n`);
  process.exit(2);
}

process.stderr.write('\nNext: npm run gen:config  (regenerates n8n/nodes/CONFIG.json from this file)\n');
