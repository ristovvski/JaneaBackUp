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
// API evidence (developers.pipedrive.com, Organization Fields) plus a live
// read of the account on 2026-09-09:
//
//   POST /api/v2/organizationFields  body: { field_name, field_type, options }
//   field_type: varchar | text | double | date | enum | set | ...
//   options for enum/set: [{ "label": "..." }]
//   GET  /api/v2/organizationFields  params: limit (max 500), cursor
//
// The v2 field object is NOT the v1 one, and the difference is a trap this
// script fell into once. v2 returns:
//     field_name, field_code, field_type, options, subfields,
//     is_custom_field, is_optional_response_field, is_writable
// There is no `name`, no `key` and no `id`. Reading `field.name` returns
// undefined for every field, so a name-matched idempotency check silently
// matches NOTHING and every run creates a fresh duplicate set. The --dry-run
// output that exposed this said "0 found, would create 5" against an account
// that already had 55 fields.
//
// Option ids ARE returned, as options: [{ id, label }] — verified live, on both
// v1 and v2. That closes the old NEEDS_DOC_EVIDENCE. The read-back below still
// fails loudly if an id is missing, because writing an enum by label is not
// something to fall back to silently.

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

/**
 * Normalize a v2 (or v1) field object to one internal shape, so the rest of
 * this script cannot care which spelling the API used.
 */
function normalizeField(raw) {
  return {
    name: raw.field_name !== undefined ? raw.field_name : raw.name,
    key: raw.field_code !== undefined ? raw.field_code : raw.key,
    field_type: raw.field_type,
    options: Array.isArray(raw.options) ? raw.options : null,
    is_custom: raw.is_custom_field !== undefined
      ? raw.is_custom_field
      : /^[0-9a-f]{40}$/.test(String(raw.key || '')),
    is_writable: raw.is_writable !== false,
    id: raw.id !== undefined ? raw.id : null,
    raw,
  };
}

async function listOrgFields() {
  const fields = [];
  let cursor = null;
  do {
    const params = new URLSearchParams({ limit: '500' });
    if (cursor) params.set('cursor', cursor);
    const payload = await api('GET', `/api/v2/organizationFields?${params}`);
    fields.push(...(payload.data || []).map(normalizeField));
    cursor = payload.additional_data?.next_cursor || null;
  } while (cursor);

  // Guard the trap above: if every name came back undefined we are reading the
  // wrong property and MUST NOT proceed to create.
  const named = fields.filter((f) => typeof f.name === 'string' && f.name !== '').length;
  if (fields.length > 0 && named === 0) {
    throw new Error(
      `NEEDS_DOC_EVIDENCE: read ${fields.length} organization fields but resolved 0 names. ` +
      `The API field shape changed; matching by name would match nothing and every run ` +
      `would create duplicates. Refusing to create anything. ` +
      `Keys seen on the first object: ${Object.keys(fields[0].raw).join(', ')}`
    );
  }
  return fields;
}

/** Compare field names the way a human would: case- and space-insensitively. */
const nameKey = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, ' ');

process.stderr.write('Reading the existing organization fields (read-only)...\n');
const existing = await listOrgFields();
const existingByName = new Map(existing.map((f) => [nameKey(f.name), f]));
process.stderr.write(
  `  ${existing.length} organization fields in the account ` +
  `(${existing.filter((f) => f.is_custom).length} custom), ` +
  `${existingByName.size} distinct names resolved\n\n`
);

const summary = { created: [], found: [], optionsAdded: [], problems: [] };

for (const [slug, spec] of Object.entries(registry.fields)) {
  const wanted = spec.name;
  let field = existingByName.get(nameKey(wanted));

  if (field) {
    summary.found.push(wanted);
    process.stderr.write(`FOUND    ${wanted} (type ${field.field_type}, custom=${field.is_custom})\n`);
    if (field.is_writable === false) {
      summary.problems.push(
        `"${wanted}" exists but the API reports it as not writable. The workflow cannot ` +
        `write it; check the field's permissions in Pipedrive.`
      );
    }
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
    field = normalizeField(created.data || {});
    if (!field.key) {
      throw new Error(
        `NEEDS_DOC_EVIDENCE: created "${wanted}" but the response carried no field ` +
        `code/key. The field EXISTS in Pipedrive now — re-run this script and it will ` +
        `adopt it. Response keys: ${Object.keys(created.data || {}).join(', ')}`
      );
    }
    summary.created.push(wanted);
    process.stderr.write(`CREATED  ${wanted} (type ${field.field_type})\n`);
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
