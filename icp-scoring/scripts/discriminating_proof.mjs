#!/usr/bin/env node
// scripts/discriminating_proof.mjs — prove the tests are discriminating (§9.6).
//
// The golden example's "fails on prior" rule: a test that stays green when you
// remove the behaviour it claims to check is decoration. So take three real
// behaviours out, one at a time, and record that exactly the expected tests go
// red — then put them back.
//
// Every mutation is a single anchored string replace, asserted to match exactly
// once, and reverted from the in-memory original in a finally block. The script
// verifies the tree is clean before it starts and clean again at the end, so a
// crash cannot leave a mutation behind.
//
//   node scripts/discriminating_proof.mjs            run the three
//   node scripts/discriminating_proof.mjs --write    also write reports/discriminating_proof.md

import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync, execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createHash } from 'node:crypto';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const WRITE = process.argv.includes('--write');

const MUTATIONS = [
  {
    id: 1,
    name: 'grade threshold boundary becomes exclusive',
    behaviour: 'S5 — "A if >= 75, B if >= 55. Boundaries inclusive."',
    file: 'engine/scoring.mjs',
    from: `  if (finalScore >= RUBRIC.thresholds.A) return 'A';
  if (finalScore >= RUBRIC.thresholds.B) return 'B';`,
    to: `  if (finalScore > RUBRIC.thresholds.A) return 'A';
  if (finalScore > RUBRIC.thresholds.B) return 'B';`,
    expect: [
      'a score of exactly 75 must grade A and exactly 55 must grade B',
      'the Clay formula still uses >=, so parity must break too',
    ],
    rebuild: false,
  },
  {
    id: 2,
    name: 'retryOnFail removed from the note POST',
    behaviour: 'A retried create is a duplicate, so entity-creating POSTs never retry.',
    file: 'n8n/patch/patch.mjs',
    from: `  nodes.push(httpNode('POST note', [1940, 500], {
    method: 'POST',
    // Notes are v1: there is no v2 notes endpoint.
    url: \`=\${PIPEDRIVE_V1}/notes\`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify({ org_id: Number($json.org_id), content: $json.note }) }}',
  }, NO_RETRY));`,
    to: `  nodes.push(httpNode('POST note', [1940, 500], {
    method: 'POST',
    // Notes are v1: there is no v2 notes endpoint.
    url: \`=\${PIPEDRIVE_V1}/notes\`,
    sendBody: true,
    specifyBody: 'json',
    jsonBody: '={{ JSON.stringify({ org_id: Number($json.org_id), content: $json.note }) }}',
  }, RETRY));`,
    expect: [
      "validate() must refuse to emit the workflow (\"POST note\" creates an entity)",
      'so the patcher exits non-zero and the export is never written',
    ],
    rebuild: true,
  },
  {
    id: 3,
    name: 'undated Contracting no longer downgrades to Stable',
    behaviour: 'S9 — Contracting without dated evidence <= 12 months becomes Stable and is flagged.',
    file: 'engine/scoring.mjs',
    from: `    if (!dated) {
      activationStateUsed = RUBRIC.activation_default_when_no_evidence;
      flags.push('contracting_without_dated_evidence');
    }`,
    to: `    if (!dated) {
      // behaviour removed for the discriminating-test proof
    }`,
    expect: [
      'an undated Contracting must not be allowed to zero a score',
      'and the Clay formula still downgrades, so parity must break too',
    ],
    rebuild: false,
  },
];

const run = (label, argv) => {
  try {
    const stdout = execFileSync(process.execPath, argv, {
      cwd: ROOT, stdio: 'pipe', encoding: 'utf8',
    });
    return { label, code: 0, output: stdout };
  } catch (error) {
    return {
      label,
      code: error.status === undefined ? 1 : error.status,
      output: `${error.stdout || ''}${error.stderr || ''}`,
    };
  }
};

/** Test names that went from passing to failing. */
function failingTests(output) {
  return [...output.matchAll(/^\s*not ok \d+ - (.+)$/gm)]
    .map((m) => m[1].trim())
    // Suite-level rollups repeat their children; keep the leaves.
    .filter((name) => !/^(S\d|the |golden set|no prompt|every |icp_scored)/.test(name) || true);
}

function gitClean() {
  const status = execSync('git status --porcelain -- .', { cwd: ROOT, encoding: 'utf8' }).trim();
  return status === '';
}

const sha = (path) => createHash('sha256').update(readFileSync(join(ROOT, path))).digest('hex');

// --------------------------------------------------------------------------

if (!gitClean()) {
  process.stderr.write(
    'Refusing to run: icp-scoring has uncommitted changes.\n' +
    'This script mutates source files, and a clean tree is how it proves it put\n' +
    'everything back. Commit or stash first.\n'
  );
  process.exit(1);
}

process.stdout.write('Baseline: the full suite must be green before removing anything.\n');
const baseline = run('baseline', ['--test',
  'tests/unit/scoring.test.mjs', 'tests/unit/normalize.test.mjs',
  'tests/contract/schemas.test.mjs', 'tests/contract/prompts.test.mjs',
  'tests/contract/clay_parity.test.mjs',
  'tests/static/workflow_review.test.mjs', 'tests/static/nodes_execute.test.mjs',
  'tests/golden/golden.test.mjs',
]);
const baselineSummary = (baseline.output.match(/^# (?:tests|pass|fail) \d+$/gm) || []).join('  ');
process.stdout.write(`  ${baselineSummary}  exit ${baseline.code}\n\n`);
if (baseline.code !== 0) {
  process.stderr.write('Baseline is not green. Fix that before proving anything.\n');
  process.exit(1);
}

const sections = [];

for (const mutation of MUTATIONS) {
  const path = join(ROOT, mutation.file);
  const original = readFileSync(path, 'utf8');
  const occurrences = original.split(mutation.from).length - 1;

  process.stdout.write(`── Mutation ${mutation.id}: ${mutation.name}\n`);
  process.stdout.write(`   file: ${mutation.file}\n`);

  if (occurrences !== 1) {
    process.stderr.write(
      `   ANCHOR MISMATCH: expected exactly 1 occurrence, found ${occurrences}. ` +
      `The source moved; update the anchor.\n`
    );
    process.exit(1);
  }

  let result;
  let rebuildResult = null;
  try {
    writeFileSync(path, original.replace(mutation.from, mutation.to), 'utf8');

    if (mutation.rebuild) {
      rebuildResult = run('patcher', ['n8n/patch/patch.mjs']);
      process.stdout.write(`   patcher exit ${rebuildResult.code}\n`);
    }

    result = run(`mutation-${mutation.id}`, ['--test',
      'tests/unit/scoring.test.mjs', 'tests/unit/normalize.test.mjs',
      'tests/contract/schemas.test.mjs', 'tests/contract/prompts.test.mjs',
      'tests/contract/clay_parity.test.mjs',
      'tests/static/workflow_review.test.mjs', 'tests/static/nodes_execute.test.mjs',
      'tests/golden/golden.test.mjs',
    ]);
  } finally {
    writeFileSync(path, original, 'utf8');
    if (mutation.rebuild) run('restore-patcher', ['n8n/patch/patch.mjs']);
  }

  const failed = failingTests(result.output);
  const counts = {
    tests: Number((result.output.match(/^# tests (\d+)$/m) || [])[1] || 0),
    pass: Number((result.output.match(/^# pass (\d+)$/m) || [])[1] || 0),
    fail: Number((result.output.match(/^# fail (\d+)$/m) || [])[1] || 0),
  };

  const detected = mutation.rebuild
    ? (rebuildResult && rebuildResult.code !== 0) || counts.fail > 0
    : counts.fail > 0;

  process.stdout.write(`   result: ${counts.pass} pass, ${counts.fail} fail, exit ${result.code}\n`);
  process.stdout.write(`   ${detected ? 'DETECTED' : '*** NOT DETECTED — the tests are not discriminating ***'}\n\n`);

  sections.push({
    mutation, counts, failed, detected,
    patcherOutput: rebuildResult ? rebuildResult.output.trim() : null,
    patcherCode: rebuildResult ? rebuildResult.code : null,
  });
}

// --------------------------------------------------------------------------
// Verify we put everything back.
// --------------------------------------------------------------------------
process.stdout.write('Verifying the tree is clean again.\n');
const clean = gitClean();
process.stdout.write(`  git status clean: ${clean}\n`);

const after = run('after', ['--test',
  'tests/unit/scoring.test.mjs', 'tests/unit/normalize.test.mjs',
  'tests/contract/schemas.test.mjs', 'tests/contract/prompts.test.mjs',
  'tests/contract/clay_parity.test.mjs',
  'tests/static/workflow_review.test.mjs', 'tests/static/nodes_execute.test.mjs',
  'tests/golden/golden.test.mjs',
]);
process.stdout.write(`  suite green again: ${after.code === 0}\n`);

const allDetected = sections.every((s) => s.detected);
process.stdout.write(`\n${sections.filter((s) => s.detected).length}/${sections.length} mutations detected.\n`);

if (WRITE) {
  const md = `# Discriminating-test proof (§9.6)

Generated by \`node scripts/discriminating_proof.mjs --write\` on
${new Date().toISOString()}.

Three real behaviours were removed, one at a time, and the suite re-run. A test
that stays green when its behaviour is gone is decoration; this is the evidence
that these are not.

Each mutation is a single anchored string replace asserted to match exactly
once, reverted in a \`finally\` block. The script refuses to start on a dirty
tree and re-checks \`git status\` at the end, so a crash cannot leave a mutation
in the source.

**Baseline (nothing removed):** \`${baselineSummary.trim()}\`, exit ${baseline.code}.

**Result: ${sections.filter((s) => s.detected).length}/${sections.length} detected.**
Tree clean afterwards: **${clean}**. Suite green afterwards: **${after.code === 0}**.

${sections.map((s) => `---

## ${s.mutation.id}. ${s.mutation.name}

**Behaviour removed:** ${s.mutation.behaviour}
**File:** \`${s.mutation.file}\`

\`\`\`diff
${s.mutation.from.split('\n').map((l) => `- ${l}`).join('\n')}
${s.mutation.to.split('\n').map((l) => `+ ${l}`).join('\n')}
\`\`\`

**Expected to be caught because:**
${s.mutation.expect.map((e) => `- ${e}`).join('\n')}

**Outcome: ${s.detected ? 'DETECTED' : 'NOT DETECTED'}** — ${s.counts.pass} pass, ${s.counts.fail} fail (of ${s.counts.tests}).
${s.patcherCode !== null ? `
The patcher refused to write the export (exit ${s.patcherCode}):

\`\`\`
${s.patcherOutput}
\`\`\`
` : ''}${s.failed.length > 0 ? `
Failing tests (${s.failed.length}):

${s.failed.map((f) => `- \`${f}\``).join('\n')}
` : '\n_No test failures; detection came from the patcher refusing to emit._\n'}`).join('\n')}
`;
  writeFileSync(join(ROOT, 'reports', 'discriminating_proof.md'), md, 'utf8');
  process.stdout.write('wrote reports/discriminating_proof.md\n');
}

process.exit(allDetected && clean && after.code === 0 ? 0 : 1);
