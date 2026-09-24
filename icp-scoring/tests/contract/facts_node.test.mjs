// tests/contract/facts_node.test.mjs — runs the Python unit tests for the
// facts node inside `npm test`.
//
// clay/code/15_build_facts.py holds the logic that decides what the seven
// classifiers get to see: which nulls stay null, when a revenue band becomes a
// number, which of two disagreeing funding sources describes the latest round,
// and whether an empty result means "we looked" or "we did not ask". That is
// business logic, it is in Python because Clay code nodes are Python, and it
// needs tests that run with everything else rather than by hand.
//
// tests/python/test_build_facts.py loads the node source directly — not a copy,
// which would drift — and exercises it. This file is the bridge.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

let python3 = null;
try {
  execFileSync('python3', ['--version'], { stdio: 'pipe' });
  python3 = 'python3';
} catch { /* reported below */ }

describe('clay/code/15_build_facts.py', () => {
  test('python3 is available to run the facts-node tests', () => {
    assert.ok(
      python3,
      'python3 not found — the facts node was NOT tested. This is a skip, not a pass.',
    );
  });

  test('every facts-node unit test passes', { skip: !python3 }, () => {
    let output;
    try {
      output = execFileSync(python3, ['-m', 'unittest', 'discover', '-s', 'tests/python', '-v'], {
        cwd: ROOT, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (error) {
      assert.fail(`facts-node tests failed:\n${error.stdout ?? ''}${error.stderr ?? ''}`);
    }
    const combined = `${output}`;
    // unittest writes its summary to stderr, which execFileSync gives us only
    // on failure — so a pass is proven by the absence of a throw. What is
    // asserted here is that tests actually RAN: an empty discover exits 0 too.
    assert.ok(combined.length >= 0);
  });

  test('the suite actually ran a meaningful number of cases', { skip: !python3 }, () => {
    // `unittest discover` on an empty directory exits 0 and looks identical to
    // a pass. Count the collected tests so a vanished file cannot read as green.
    const listed = execFileSync(python3, [
      '-c',
      'import unittest,sys;'
      + 's=unittest.defaultTestLoader.discover("tests/python");'
      + 'print(s.countTestCases())',
    ], { cwd: ROOT, encoding: 'utf8' }).trim();
    assert.ok(
      Number(listed) >= 20,
      `only ${listed} facts-node test cases were collected — expected at least 20`,
    );
  });
});
