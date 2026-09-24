// tests/static/note_format.test.mjs — the note block Nik pastes into Clay,
// executed rather than read.
//
// engine/clay_note_format.md carries the JavaScript for the table's `note:`
// column. n8n writes whatever that column produces verbatim, so this block IS
// the note a rep reads. A doc that nobody runs drifts; this test runs it.

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DOC = readFileSync(join(ROOT, 'engine', 'clay_note_format.md'), 'utf8');

// The one ```js block under "The replacement for the `note: [...]` block".
const section = DOC.split('## The replacement for the `note: [...]` block')[1] || '';
const BLOCK = (section.match(/```js\n([\s\S]*?)```/) || [])[1];

// Every value the block reads, as the table computes it.
const INPUTS = [
  'grade', 'final', 'confidence_overall',
  'industry_level', 'industry_vertical', 'industry_why',
  'type_level', 'type_why', 'stage_level', 'stage_why', 'geo_level', 'geo_why',
  'revenue_level', 'revenue_band', 'revenue_source', 'revenue_why',
  'eng_open', 'eng_open_60d_plus', 'leader_titles', 'hiring_why',
  'activation_used', 'multiplier', 'activation_why', 'composite',
  'tier2_candidate', 'guard_reason', 'conflict_note', 'buying_level', 'buying_why',
];

const render = (values) => {
  // eslint-disable-next-line no-new-func
  const fn = new Function(...INPUTS, `${BLOCK}\nreturn note;`);
  return fn(...INPUTS.map((k) => values[k]));
};

// The live Intellistack row (org 22586) — the values behind
// tests/fixtures/clay/note_html_rendered.txt.
const INTELLISTACK = {
  grade: 'B', final: 62, confidence_overall: 'medium',
  industry_level: 7, industry_vertical: 'SaaS — Other',
  industry_why: 'Sells horizontal no-code workflow, forms, eSignature, and contract software across many industries — a general SaaS vendor.',
  type_level: 10, type_why: 'Named cloud products, demos, integrations, and a 63-person engineering team show software is the business.',
  stage_level: 3, stage_why: 'With no recorded funding and missing normalized hiring metrics, this 2006 company best fits mature steady-state, but capacity pressure remains unknown.',
  geo_level: 10, geo_why: 'Headquarters is in Denver, Colorado, placing Intellistack inside the primary US market.',
  revenue_level: 10, revenue_band: '$25M–$500M', revenue_source: 'apollo',
  revenue_why: 'Apollo estimates $55.3M, about $230K per employee, a plausible software-company level that falls within the $25M–$500M band.',
  eng_open: 0, eng_open_60d_plus: 0, leader_titles: [],
  hiring_why: 'No job postings were provided, so no open engineering roles, aged roles, or leadership hires are detectable.',
  activation_used: 'Stable', multiplier: 0.8,
  activation_why: 'No recorded funding and flat annual headcount provide no evidence of a current transformation, so the company appears stable.',
  composite: 78, tier2_candidate: false, guard_reason: null, conflict_note: null,
  buying_level: 0, buying_why: 'No job postings or funding rounds are recorded, so no buying signal is detectable.',
};

describe('the Clay note block, executed', () => {
  test('the doc carries exactly one runnable block', () => {
    assert.ok(BLOCK, 'no ```js block under the replacement heading');
    assert.equal(typeof render(INTELLISTACK), 'string');
  });

  test('it reproduces the note that went through the live pipeline, byte for byte', () => {
    const fixture = readFileSync(join(ROOT, 'tests', 'fixtures', 'clay', 'note_html_rendered.txt'), 'utf8')
      .replace(/\n$/, '');
    assert.equal(render(INTELLISTACK), fixture);
  });

  test('the buying signal says "not scored" on every note — even with no sentence', () => {
    // The 22 Sep notes (activities 47040, 47041) had no buying line at all,
    // because the line used to hang on buying_why. Chrissy: keep it.
    for (const buying_why of [null, undefined, '']) {
      for (const buying_level of [0, 3, 10, null]) {
        const note = render({ ...INTELLISTACK, buying_why, buying_level });
        assert.match(note, /Buying signal \(not scored\): /, `buying_why=${buying_why} level=${buying_level}`);
        assert.ok(note.endsWith(`Buying signal (not scored): ${buying_level === null ? '—' : buying_level}`),
          'the last line, level shown, no dangling dash');
      }
    }
  });

  test('it is the last line, after any optional tail', () => {
    const note = render({ ...INTELLISTACK, tier2_candidate: true, conflict_note: 'Apollo and PDL were two bands apart.' });
    const blocks = note.split('<br><br>');
    assert.match(blocks[blocks.length - 1], /^Buying signal \(not scored\)/);
    assert.match(blocks[blocks.length - 2], /Sources disagreed/);
  });

  test('a buying level never moves the score line', () => {
    // The weight is 0: the same composite with buying 0 and buying 10 renders
    // the same Score line. (The arithmetic itself is the formula's; this pins
    // that the note does not imply otherwise.)
    const scoreLine = (n) => n.split('<br><br>').find((b) => b.startsWith('<b>Score '));
    assert.equal(
      scoreLine(render({ ...INTELLISTACK, buying_level: 0 })),
      scoreLine(render({ ...INTELLISTACK, buying_level: 10 }))
    );
  });
});
