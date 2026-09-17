#!/usr/bin/env node
// scripts/audit_table.mjs — print the icp_audit Data Table's columns.
//
// Why this is a print and not a create: n8n's PUBLIC API has no data-tables
// endpoint (GET /api/v1/data-tables is 404), and the internal REST API wants a
// browser session, so the only component on this instance that can talk to
// data tables with an API key is a workflow node. Measured 2026-09-16 against
// janea-systems-2025.app.n8n.cloud by running each operation in a throwaway
// webhook workflow:
//
//   resource=row,   operation=get     -> "Could not find the data table: 'icp_audit'"
//   resource=row,   operation=insert  -> reached the mapper
//   resource=table, operation=list    -> "Could not get parameter"
//   resource=table, operation=create  -> "Could not get parameter"
//
// The row resource works; the table resource does not exist in this build of
// the node. So the table itself is created once in the UI, and this prints
// exactly what to type. Everything after that is automated.
//
// Run: node scripts/audit_table.mjs

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const spec = JSON.parse(readFileSync(join(ROOT, 'config', 'icp_audit_table.json'), 'utf8'));

const width = Math.max(...spec.columns.map((c) => c.name.length));
const out = [];
out.push(`n8n → Data tables → Create data table → name it exactly:  ${spec.name}`);
out.push(`Then add ${spec.columns.length} columns, in this order:`);
out.push('');
for (const [i, column] of spec.columns.entries()) {
  const note = column.note ? `   # ${column.note}` : '';
  out.push(`  ${String(i + 1).padStart(2)}. ${column.name.padEnd(width)}  ${column.type.padEnd(7)}${note}`);
}
out.push('');
out.push('The names must match exactly: the Data Table node maps by name, so a');
out.push('mismatched column is dropped silently rather than failing the write.');
process.stdout.write(`${out.join('\n')}\n`);
