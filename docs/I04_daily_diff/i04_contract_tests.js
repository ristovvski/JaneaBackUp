'use strict';
// Static contract tests for dnc_i04_daily_diff. Executes the ACTUAL extracted "Diff" node jsCode
// (not a reimplementation) against synthetic fixtures, matching DNC_OBS_P1_build's own established
// test discipline (subworkflows/tests/dnc_contract_tests.js).
// Run: node i04_contract_tests.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');

let pass = 0, fail = 0;
function t(name, fn) { try { fn(); pass++; console.log('  ok  - ' + name); }
  catch (e) { fail++; console.log('  FAIL- ' + name + '\n        ' + e.message); } }

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, 'dnc_i04_daily_diff.json'), 'utf8'));
const diffNode = wf.nodes.find((n) => n.name === 'Diff');
const diffJs = diffNode.parameters.jsCode;

// Run the extracted Diff jsCode against a mocked {Build Snapshot, Pick Previous Snapshot} pair.
function runDiff(todaySnapshotBuiltJson, prevRow) {
  const fn = new Function('$', diffJs);
  const mock$ = (name) => {
    if (name === 'Build Snapshot') return { first: () => ({ json: todaySnapshotBuiltJson }) };
    if (name === 'Pick Previous Snapshot') return { first: () => ({ json: prevRow }) };
    throw new Error('unexpected $() reference: ' + name);
  };
  return fn(mock$)[0].json;
}

function makeSnapshot(date, leads, persons, dncLabelled, dnc686) {
  const counts = { leads: Object.keys(leads).length, persons: Object.keys(persons).length,
    dnc_labelled: dncLabelled.length, dnc_field_686: dnc686 };
  return {
    date, counts_json: JSON.stringify(counts),
    leads_json: JSON.stringify(leads), persons_json: JSON.stringify(persons),
    dnc_labelled_json: JSON.stringify(dncLabelled),
  };
}

// ---------------------------------------------------------------- structural
t('Diff node references the correct upstream nodes by name', () => {
  assert.ok(diffJs.includes("$('Build Snapshot').first().json"));
  assert.ok(diffJs.includes("$('Pick Previous Snapshot').first().json"));
});

t('first run (no previous snapshot) is handled without crashing, not a false anomaly', () => {
  const today = makeSnapshot('2026-08-20', { L1: ['', null, 't'] }, {}, [], 0);
  const r = runDiff(today, {}); // {} = no previous row found
  assert.equal(r.ok, false);
  assert.ok(r.reason.includes('no previous snapshot'));
});

// -------------------------------------------------- seeded two-snapshot fixture: known departures
t('seeded two-snapshot fixture: known departures are detected exactly, reconciliation closes', () => {
  const EXPECTED_DNC = JSON.parse(fs.readFileSync(
    path.join(path.dirname(__dirname), 'audit-artifacts', 'prereversal_baseline_FINAL.json'), 'utf8'
  )).expected_survivors;

  // yesterday: 5 leads, including all 7... no -- keep it small and self-contained. Use the real
  // EXPECTED_DNC set for the DNC-label check (baked into diff_js), everything else synthetic.
  const yesterdayLeads = {};
  for (let i = 0; i < 10; i++) yesterdayLeads['lead_' + i] = ['', 1000 + i, '2026-08-01T00:00:00Z'];
  // 3 KNOWN departures: lead_0, lead_1, lead_2 leave the estate.
  const todayLeads = Object.assign({}, yesterdayLeads);
  delete todayLeads.lead_0; delete todayLeads.lead_1; delete todayLeads.lead_2;
  // 1 known arrival.
  todayLeads.lead_new = ['', 2000, '2026-08-20T00:00:00Z'];

  const yesterdayPersons = { p1: ['2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z', 'pii-22fdb3ff@example.invalid', 'a-slug', 0] };
  const todayPersons = Object.assign({}, yesterdayPersons);

  const prev = makeSnapshot('2026-08-19', yesterdayLeads, yesterdayPersons, EXPECTED_DNC, 7);
  const currLeads = todayLeads;
  // put the correct 7-id EXPECTED_DNC set on today too, so the DNC-label check itself is green
  // and doesn't confound this test (which is specifically about check 1+2, departures/reconciliation).
  const curr = makeSnapshot('2026-08-20', currLeads, todayPersons, EXPECTED_DNC, 7);

  const r = runDiff(curr, prev);
  assert.equal(r.ok, true);
  assert.equal(r.departures_count, 3, 'must detect exactly the 3 known departures, not more/fewer');
  assert.deepEqual(r.departures_all.sort(), ['lead_0', 'lead_1', 'lead_2']);
  assert.equal(r.arrivals_count, 1);
  assert.deepEqual(r.arrivals_sample.map((x) => x), ['lead_new']);
  // reconciliation: 10 - 3 + 1 = 8 == today's actual lead count (8)
  assert.equal(r.reconciles, true);
  assert.equal(Object.keys(currLeads).length, 8);
  assert.equal(r.dnc.exact, true, 'DNC label set unchanged between the two snapshots -- must read as exact');
});

t('reconciliation catches a count that does not close (something moved unexplained)', () => {
  // deliberately corrupt curr_counts.leads so the walked total disagrees with the departures/
  // arrivals math -- this simulates the check catching real drift.
  const yesterdayLeads = { a: ['', 1, 't'], b: ['', 2, 't'], c: ['', 3, 't'] };
  const todayLeads = { a: ['', 1, 't'] }; // b, c departed, nothing arrived -- calc should be 3-2+0=1, matches len=1... so we need to break the WALKED counts.counts.leads itself, not the reconstructed len, to prove the check reacts to counts.leads specifically (not just Object.keys(B.leads).length, which the code doesn't even use for the .curr_counts.leads comparison -- it uses B.counts.leads verbatim).
  const prev = makeSnapshot('2026-08-19', yesterdayLeads, {}, [], 0);
  const curr = makeSnapshot('2026-08-20', todayLeads, {}, [], 0);
  const currParsed = JSON.parse(curr.counts_json);
  currParsed.leads = 999; // corrupt the WALKED total specifically
  curr.counts_json = JSON.stringify(currParsed);
  const r = runDiff(curr, prev);
  assert.equal(r.reconciles, false, 'a walked total that disagrees with departures/arrivals math must fail reconciliation');
});

// -------------------------------------------------------------- missing-field fixture: NOT COMPUTABLE
t('missing-field fixture: dnc686 delta is null (NOT COMPUTABLE), never a fake number', () => {
  const leads = { a: ['', 1, 't'] };
  const persons = {};
  // prev snapshot never captured the field at all -- counts.dnc_field_686 is null, matching
  // i04_snapshot.py's own "missing is not zero" rule verbatim.
  const prev = makeSnapshot('2026-08-19', leads, persons, [], null);
  const curr = makeSnapshot('2026-08-20', leads, persons, [], 42);
  const r = runDiff(curr, prev);
  assert.equal(r.dnc686_delta, null, 'one side missing the measurement -> delta must be null, not curr-0');
  assert.equal(r.dnc686_prev, null);
  assert.equal(r.dnc686_curr, 42);
});

t('missing-field fixture, both sides missing: still null, not 0-0', () => {
  const leads = { a: ['', 1, 't'] };
  const prev = makeSnapshot('2026-08-19', leads, {}, [], null);
  const curr = makeSnapshot('2026-08-20', leads, {}, [], null);
  const r = runDiff(curr, prev);
  assert.equal(r.dnc686_delta, null);
});

t('a real, present delta on both sides computes a genuine number, not suppressed', () => {
  const leads = { a: ['', 1, 't'] };
  const prev = makeSnapshot('2026-08-19', leads, {}, [], 100);
  const curr = makeSnapshot('2026-08-20', leads, {}, [], 102);
  const r = runDiff(curr, prev);
  assert.equal(r.dnc686_delta, 2, 'a genuine measured delta must NOT be swallowed by the missing-is-not-zero guard');
});

// ---------------------------------------------------------------- DNC label set, id-exact
t('DNC label set check is id-exact, not count-exact -- same count wrong ids still fails', () => {
  const EXPECTED_DNC = JSON.parse(fs.readFileSync(
    path.join(path.dirname(__dirname), 'audit-artifacts', 'prereversal_baseline_FINAL.json'), 'utf8'
  )).expected_survivors;
  const leads = { a: ['', 1, 't'] };
  const prev = makeSnapshot('2026-08-19', leads, {}, EXPECTED_DNC, 7);
  // same COUNT (7) but a completely different set of ids -- must still fail exact-match.
  const wrongIds = EXPECTED_DNC.slice(0, 6).concat(['not-a-real-survivor-id']);
  const curr = makeSnapshot('2026-08-20', leads, {}, wrongIds, 7);
  const r = runDiff(curr, prev);
  assert.equal(r.dnc.exact, false, 'same count but wrong ids must NOT read as exact -- this is the whole point of id-exact over count-exact');
  assert.equal(r.dnc.unexpected.length, 1);
  assert.equal(r.dnc.missing.length, 1);
});

// ---------------------------------------------------------------- new person duplicate detection
t('new person duplicate check catches same-email and same-slug twins (the p85764/p85765 class)', () => {
  const prevPersons = { p1: ['2026-08-01T00:00:00Z', 't', 'pii-eb11aba1@example.invalid', 'existing-slug', 0] };
  const currPersons = Object.assign({}, prevPersons, {
    p2: ['2026-08-20T00:00:00Z', 't', 'pii-eb11aba1@example.invalid', '', 0],       // email twin of p1
    p3: ['2026-08-20T00:00:00Z', 't', '', 'existing-slug', 0],        // slug twin of p1
    p4: ['2026-08-20T00:00:00Z', 't', 'pii-584297e8@example.invalid', 'new-slug', 0], // genuinely clean new person
  });
  const prev = makeSnapshot('2026-08-19', {}, prevPersons, [], 0);
  const curr = makeSnapshot('2026-08-20', {}, currPersons, [], 0);
  const r = runDiff(curr, prev);
  assert.equal(r.new_persons_count, 3);
  assert.equal(r.new_person_duplicates.length, 2, 'p2 (email twin) and p3 (slug twin) must both be flagged; p4 must not');
  const flaggedIds = r.new_person_duplicates.map((d) => d.person).sort();
  assert.deepEqual(flaggedIds, ['p2', 'p3']);
});

console.log('\n%d passed, %d failed', pass, fail);
process.exit(fail ? 1 : 0);
