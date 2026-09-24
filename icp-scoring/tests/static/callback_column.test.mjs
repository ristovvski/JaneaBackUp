// tests/static/callback_column.test.mjs — engine/clay_callback_column.md is the
// page Nik configures the Clay callback from. It went stale once (it described
// the consolidated event for five days after a5ac404 retired it), so it is now
// checked against the validator it documents.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { validateEvent, REQUIRED_TOP, OPTIONAL_TOP } from '../../engine/validate_event.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DOC = readFileSync(join(ROOT, 'engine', 'clay_callback_column.md'), 'utf8');
const section = DOC.split('## What `icp_event_json` must return')[1] || '';
const EXAMPLE = JSON.parse((section.match(/```json\n([\s\S]*?)```/) || [])[1]);

describe('the Clay callback column doc', () => {
  test('its example is a valid event', () => {
    assert.deepEqual(validateEvent(EXAMPLE), []);
  });

  test('its example carries every required key and nothing the validator does not allow', () => {
    for (const key of REQUIRED_TOP) assert.ok(key in EXAMPLE, `missing ${key}`);
    for (const key of Object.keys(EXAMPLE)) {
      assert.ok(REQUIRED_TOP.includes(key) || OPTIONAL_TOP.includes(key), `unknown key ${key}`);
    }
  });

  test('the first eight keys it calls required are exactly the validator\'s', () => {
    assert.deepEqual(Object.keys(EXAMPLE).slice(0, REQUIRED_TOP.length), REQUIRED_TOP);
  });

  test('the types table names every key the validator knows', () => {
    const table = DOC.split('## Types, exactly')[1].split('\n---\n')[0];
    for (const key of [...REQUIRED_TOP, 'composite', 'multiplier', 'final_without_activation',
      'activation_used', 'confidence_overall', 'tier2_candidate', 'flags']) {
      assert.ok(table.includes(`\`${key}\``), `${key} missing from the types table`);
    }
  });

  test('nothing of the retired consolidated event survives in it', () => {
    for (const gone of ['cls_all', '"resolved"', 'engineering_hiring', 'apollo_summary', '`Score`']) {
      assert.ok(!DOC.includes(gone), `still describes ${gone}`);
    }
  });
});
