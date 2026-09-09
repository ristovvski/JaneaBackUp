// tests/golden/golden.test.mjs — acceptance against human-graded accounts.
//
// HARD (must pass, §9.5): Akuvo = A, Microsoft != A, Merck != A. These three are
// written into the Test Accounts sheet as validation rules.
//
// SOFT: agreement >= 85% over accounts that have a human grade. Printed as a
// table for REPORT.md. Asserted only once the graded sample is large enough to
// mean anything — 85% of three rows is not a measurement.
//
// An account with no captured facts is SKIPPED and printed. It is never a pass.

import { test, describe, before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { score, industryLevelFor, RUBRIC } from '../../engine/scoring.mjs';
import { classifyAll, toScoreInput, cacheSize, COMPONENTS, MODEL } from './classify.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const FACTS = join(HERE, 'facts');

const expected = JSON.parse(readFileSync(join(HERE, 'expected.json'), 'utf8'));
const noCache = process.argv.includes('--no-cache') || process.env.ICP_GOLDEN_NO_CACHE === '1';

// Minimum graded accounts before the agreement rate is asserted rather than
// merely reported.
const AGREEMENT_MIN_SAMPLE = 5;
const AGREEMENT_THRESHOLD = 0.85;

const results = [];
const skipped = [];

before(async () => {
  for (const account of expected.accounts) {
    const file = account.facts_file;
    if (!file || !existsSync(join(FACTS, file))) {
      skipped.push({ org: account.org, reason: file ? `facts file ${file} not found` : 'no facts_file bound' });
      continue;
    }

    const facts = JSON.parse(readFileSync(join(FACTS, file), 'utf8'));
    const classified = await classifyAll(file, facts, { noCache });

    if (classified.mode === 'skip') {
      skipped.push({ org: account.org, reason: classified.reason });
      continue;
    }

    const input = toScoreInput(classified.outputs);
    input.facts_summary = {
      revenue_usd: facts.revenue_estimate_usd ?? null,
      headcount_total: facts.li_headcount ?? null,
      headcount_eng: facts.eng_headcount_estimate ?? null,
    };

    results.push({
      account,
      facts,
      mode: classified.mode,
      synthetic: facts.SYNTHETIC === true,
      outputs: classified.outputs,
      scored: score(input),
    });
  }

  printTable();
});

function printTable() {
  const lines = [];
  lines.push('');
  lines.push('GOLDEN SET — ICP v5');
  lines.push(`  classifier model : ${MODEL}`);
  lines.push(`  cache entries    : ${cacheSize()}${noCache ? ' (--no-cache: cache bypassed)' : ''}`);
  lines.push(`  accounts scored  : ${results.length} of ${expected.accounts.length}`);
  lines.push(`  accounts skipped : ${skipped.length}`);
  lines.push(`  expected.json    : ${expected.source}`);
  lines.push('');

  const syntheticCount = results.filter((r) => r.synthetic).length;
  if (syntheticCount > 0) {
    lines.push(`  !! ${syntheticCount} of ${results.length} scored accounts use SYNTHETIC facts.`);
    lines.push('     These prove the HARNESS runs. They do not validate the classifiers.');
    lines.push('     Replace them with facts captured from Clay runs before trusting a grade.');
    lines.push('');
  }

  const head = ['account', 'src', 'vertical', 'ind', 'stg', 'typ', 'geo', 'rev', 'activation', 'mult', 'comp', 'final', 'grade', 'exp', 'ok'];
  const rows = results.map((r) => {
    const s = r.scored;
    const l = s.levels_used;
    const exp = r.account.expected_grade;
    const hard = r.account.hard_assertion;
    let ok = '-';
    if (exp !== null) ok = exp === s.grade ? 'YES' : 'NO';
    else if (hard === 'must_not_be_A') ok = s.grade === 'A' ? 'NO' : 'YES';
    return [
      r.account.org,
      r.synthetic ? 'SYNTH' : r.mode,
      s.industry_tier === null ? '(unknown)' : `${r.account.vertical || '?'}`,
      String(s.industry_level), String(l.stage_maturity), String(l.company_type),
      String(l.geography), String(l.revenue_range),
      s.activation_state_used,
      s.multiplier.toFixed(2),
      String(s.composite),
      String(s.final_score),
      String(s.grade),
      exp === null ? (hard === 'must_not_be_A' ? 'not A' : '—') : exp,
      ok,
    ];
  });

  const widths = head.map((h, i) => Math.max(h.length, ...rows.map((r) => r[i].length)));
  const fmt = (cells) => '  ' + cells.map((c, i) => c.padEnd(widths[i])).join('  ');
  lines.push(fmt(head));
  lines.push('  ' + widths.map((w) => '-'.repeat(w)).join('  '));
  for (const row of rows) lines.push(fmt(row));
  lines.push('');

  const graded = results.filter((r) => r.account.expected_grade !== null);
  const agreed = graded.filter((r) => r.account.expected_grade === r.scored.grade);
  if (graded.length > 0) {
    const pct = ((agreed.length / graded.length) * 100).toFixed(1);
    lines.push(`  agreement: ${agreed.length}/${graded.length} = ${pct}%` +
      (graded.length < AGREEMENT_MIN_SAMPLE
        ? `  (reported only — under the ${AGREEMENT_MIN_SAMPLE}-account sample needed to assert ${AGREEMENT_THRESHOLD * 100}%)`
        : ''));
  } else {
    lines.push('  agreement: no account carries a human grade yet (Toby owes Stage/Type/Geo/Revenue).');
  }
  lines.push('');

  if (skipped.length > 0) {
    lines.push('  SKIPPED (not passes):');
    for (const s of skipped) lines.push(`    - ${s.org}: ${s.reason}`);
    lines.push('');
  }

  process.stdout.write(lines.join('\n') + '\n');
}

describe('golden set — hard acceptance assertions', () => {
  test('every account with a hard assertion was actually scored', () => {
    const hard = expected.accounts.filter((a) => a.hard_assertion);
    assert.ok(hard.length >= 3, 'at least the three §9.5 validation rules must be present');
    for (const account of hard) {
      const found = results.find((r) => r.account.org === account.org);
      assert.ok(
        found,
        `${account.org} carries a hard assertion but was skipped — a hard assertion cannot be skipped. ` +
        `Reason: ${(skipped.find((s) => s.org === account.org) || {}).reason || 'unknown'}`
      );
    }
  });

  test('Akuvo scores A', () => {
    const akuvo = results.find((r) => r.account.org === 'Akuvo');
    assert.ok(akuvo, 'Akuvo must be scored');
    assert.equal(akuvo.scored.status, 'scored');
    assert.equal(
      akuvo.scored.grade, 'A',
      `Akuvo scored ${akuvo.scored.grade} (composite ${akuvo.scored.composite} ` +
      `x${akuvo.scored.multiplier} = ${akuvo.scored.final_score})`
    );
  });

  test('Microsoft does not score A — the composite gates out an Anchor vertical', () => {
    const ms = results.find((r) => r.account.org === 'Microsoft');
    assert.ok(ms, 'Microsoft must be scored');
    assert.equal(ms.scored.industry_level, 10, 'Enterprise Tech / Hyperscalers is an Anchor');
    assert.notEqual(
      ms.scored.grade, 'A',
      `Microsoft scored A (composite ${ms.scored.composite} x${ms.scored.multiplier} = ${ms.scored.final_score})`
    );
    assert.equal(ms.scored.tier2_candidate, true, 'and it is flagged as Tier 2');
  });

  test('Merck does not score A', () => {
    const merck = results.find((r) => r.account.org === 'Merck');
    assert.ok(merck, 'Merck must be scored');
    assert.notEqual(
      merck.scored.grade, 'A',
      `Merck scored A (composite ${merck.scored.composite} x${merck.scored.multiplier} = ${merck.scored.final_score})`
    );
    assert.equal(merck.scored.tier2_candidate, true);
  });
});

describe('golden set — every scored account is internally coherent', () => {
  test('each classifier returned the component it was asked for', () => {
    for (const r of results) {
      for (const component of COMPONENTS) {
        const out = r.outputs[component];
        assert.ok(out, `${r.account.org}: no output for ${component}`);
        assert.equal(out.component, component, `${r.account.org}: ${component} mislabelled`);
      }
    }
  });

  test('the vertical the classifier chose matches the sheet, where the sheet says', () => {
    for (const r of results) {
      if (!r.account.vertical) continue;
      assert.equal(
        r.outputs.industry_vertical.value, r.account.vertical,
        `${r.account.org}: classifier said "${r.outputs.industry_vertical.value}", ` +
        `sheet says "${r.account.vertical}"`
      );
    }
  });

  test('vertical -> industry_level mapping is correct for every account, graded or not', () => {
    // This is the assertion §9.5 keeps for rows whose expected_grade is still
    // blank: even without a human grade, the vertical mapping must be right.
    for (const account of expected.accounts) {
      if (!account.vertical) continue;
      const expectedLevel = industryLevelFor(account.vertical).level;
      const scored = results.find((r) => r.account.org === account.org);
      if (!scored) continue;
      assert.equal(
        scored.scored.industry_level, expectedLevel,
        `${account.org}: ${account.vertical} should map to ${expectedLevel}`
      );
    }
  });

  test('every evidence item is cited as <fact_key>: <value>', () => {
    for (const r of results) {
      for (const component of COMPONENTS) {
        for (const item of r.outputs[component].evidence || []) {
          assert.match(
            item, /^[a-z_][a-z0-9_]*:\s/,
            `${r.account.org}/${component}: evidence "${item}" is not cited as <fact_key>: <value>`
          );
          assert.ok(item.length <= 200, `${r.account.org}/${component}: evidence over 200 chars`);
        }
        assert.ok((r.outputs[component].evidence || []).length <= 6, `${r.account.org}/${component}`);
      }
    }
  });

  test('a cited fact key exists in the fact set', () => {
    for (const r of results) {
      const keys = new Set(Object.keys(r.facts));
      for (const component of COMPONENTS) {
        for (const item of r.outputs[component].evidence || []) {
          const key = item.split(':')[0];
          assert.ok(keys.has(key), `${r.account.org}/${component}: cited unknown fact key "${key}"`);
        }
      }
    }
  });

  test('a missing_input names a real fact key', () => {
    for (const r of results) {
      const keys = new Set(Object.keys(r.facts));
      for (const component of COMPONENTS) {
        for (const key of r.outputs[component].missing_inputs || []) {
          assert.ok(keys.has(key), `${r.account.org}/${component}: missing_inputs names unknown key "${key}"`);
        }
      }
    }
  });

  test('Contracting only ever appears with dated evidence', () => {
    for (const r of results) {
      if (r.outputs.activation_state.value !== 'Contracting') continue;
      const age = r.outputs.activation_state.evidence_dated_within_months;
      assert.equal(typeof age, 'number', `${r.account.org}: Contracting with no dated evidence`);
      assert.ok(age <= RUBRIC.activation_contracting_evidence_max_age_months, `${r.account.org}`);
    }
  });

  test('re-scoring the same classifier output is byte-identical', () => {
    for (const r of results) {
      const again = score(toScoreInput(r.outputs));
      // facts_summary drives only tier2, so compare everything else.
      const strip = (o) => { const c = { ...o }; delete c.tier2_candidate; c.flags = c.flags.filter((f) => f !== 'tier2_candidate'); return c; };
      assert.deepEqual(strip(again), strip(r.scored), r.account.org);
    }
  });
});

describe('golden set — agreement', () => {
  test(`agreement is at or above ${AGREEMENT_THRESHOLD * 100}% once ${AGREEMENT_MIN_SAMPLE} accounts are graded`, () => {
    const graded = results.filter((r) => r.account.expected_grade !== null);
    if (graded.length < AGREEMENT_MIN_SAMPLE) {
      // Reported in the table above, not asserted: too small to measure.
      assert.ok(true);
      return;
    }
    const agreed = graded.filter((r) => r.account.expected_grade === r.scored.grade);
    const rate = agreed.length / graded.length;
    const disagreements = graded
      .filter((r) => r.account.expected_grade !== r.scored.grade)
      .map((r) => `${r.account.org}: expected ${r.account.expected_grade}, got ${r.scored.grade}`);
    assert.ok(
      rate >= AGREEMENT_THRESHOLD,
      `agreement ${(rate * 100).toFixed(1)}% is below ${AGREEMENT_THRESHOLD * 100}%:\n  ${disagreements.join('\n  ')}`
    );
  });

  test('every account that has a human grade was scored, not skipped', () => {
    for (const account of expected.accounts) {
      if (account.expected_grade === null) continue;
      assert.ok(
        results.some((r) => r.account.org === account.org),
        `${account.org} has a human grade but was skipped`
      );
    }
  });
});

describe('golden set — fixture hygiene', () => {
  test('every SYNTHETIC fixture is labelled in its name AND its body', () => {
    for (const file of readdirSync(FACTS).filter((f) => f.endsWith('.json'))) {
      const facts = JSON.parse(readFileSync(join(FACTS, file), 'utf8'));
      const namedSynthetic = file.startsWith('SYNTHETIC_');
      const flaggedSynthetic = facts.SYNTHETIC === true;
      assert.equal(
        namedSynthetic, flaggedSynthetic,
        `${file}: the SYNTHETIC_ filename prefix and the SYNTHETIC flag must agree`
      );
    }
  });

  test('no captured fact set carries authored classifier output', () => {
    for (const file of readdirSync(FACTS).filter((f) => f.endsWith('.json'))) {
      const facts = JSON.parse(readFileSync(join(FACTS, file), 'utf8'));
      if (file.startsWith('SYNTHETIC_')) continue;
      assert.ok(
        !facts.synthetic_classifier_output,
        `${file} is presented as captured facts but carries synthetic_classifier_output`
      );
      assert.ok(facts.captured_at, `${file}: captured facts must record captured_at`);
    }
  });

  test('the three §9.5 validation rules are bound to a facts file', () => {
    for (const org of ['Akuvo', 'Microsoft', 'Merck']) {
      const account = expected.accounts.find((a) => a.org === org);
      assert.ok(account, `${org} must be in expected.json`);
      assert.ok(account.facts_file, `${org} must have a facts_file`);
      assert.ok(existsSync(join(FACTS, account.facts_file)), `${org}: ${account.facts_file} must exist`);
    }
  });
});
