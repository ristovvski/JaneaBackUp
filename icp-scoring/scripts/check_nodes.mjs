#!/usr/bin/env node
// scripts/check_nodes.mjs — syntax-check the Code-node sources.
//
// n8n Code-node source has a top-level `return`, which is legal in a function
// body and illegal in a module, so `node --check` rejects every one of them.
// Wrapping each source in a Function constructor is exactly how n8n evaluates
// it, so this checks the syntax n8n will actually see.

import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const NODES = join(dirname(fileURLToPath(import.meta.url)), '..', 'n8n', 'nodes');
const files = readdirSync(NODES).filter((f) => f.endsWith('.js')).sort();

// The names n8n injects into a Code node's scope.
const INJECTED = ['$json', '$input', '$', '$getWorkflowStaticData', '$execution', '$now', '$env', '$workflow', 'items'];

let failed = 0;
for (const file of files) {
  const source = readFileSync(join(NODES, file), 'utf8');
  try {
    // eslint-disable-next-line no-new-func
    new Function(...INJECTED, source);
    process.stdout.write(`  ok    ${file.padEnd(22)} ${String(source.split('\n').length).padStart(4)} lines\n`);
  } catch (error) {
    failed += 1;
    process.stdout.write(`  FAIL  ${file}: ${error.message}\n`);
  }
}

process.stdout.write(`\n${files.length - failed}/${files.length} Code-node sources parse.\n`);
process.exit(failed === 0 ? 0 : 1);
