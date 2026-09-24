'use strict';
// Static contract tests for the DNC subworkflows (Build 2). Pure-logic, no n8n runtime.
// Run: node subworkflows/tests/dnc_contract_tests.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const LIB = path.join(__dirname, '..', 'lib');
const SUB = path.join(__dirname, '..');
const { normalizeIdentityV1 } = require(path.join(LIB, 'normalize_v1.js'));
const { dncMergeDecisionV1, computeExpiry, dncStrongest, dncMergeSources, dncSlugifyName, dncSplitIdentityMergeV1 } =
  require(path.join(LIB, 'merge_v1.js'));
const { reasonEntryType, reasonStrongest, isOffboardRemovable, reasonMergeV1, reasonExpiryOverride } =
  require(path.join(LIB, 'reason_v1.js'));

let pass = 0, fail = 0;
function t(name, fn) { try { fn(); pass++; console.log('  ok  - ' + name); }
  catch (e) { fail++; console.log('  FAIL- ' + name + '\n        ' + e.message); } }

const NOW = '2026-07-23T00:00:00.000Z';
const CFG = { ttlMonths: 6, now: NOW };

// ---------------------------------------------------------------- normalize
console.log('normalize_v1:');
[
  ['linkedin lowercased + canonical',
    { linkedin_url: 'HTTPS://LinkedIn.com/IN/pii-e9f868d3/' },
    (o) => { assert.equal(o.linkedin_url_norm, 'https://www.linkedin.com/in/pii-e9f868d3');
             assert.equal(o.linkedin_slug, 'john-doe'); assert.equal(o.identity_key, 'john-doe'); }],
  ['linkedin strips query/fragment',
    { linkedin_url: 'https://www.linkedin.com/in/pii-f5c4ebe4?utm=x#frag' },
    (o) => { assert.equal(o.linkedin_url_norm, 'https://www.linkedin.com/in/pii-f5c4ebe4'); }],
  ['linkedin percent-decode slug',
    { linkedin_url: 'https://linkedin.com/in/pii-d7ab670b' },
    (o) => { assert.equal(o.linkedin_slug, 'josé'); }],
  ['company url is unmatchable',
    { linkedin_url: 'https://www.linkedin.com/company/acme' },
    (o) => { assert.equal(o.linkedin_unmatchable, true); assert.equal(o.linkedin_url_norm, null); }],
  ['sales-nav url unmatchable',
    { linkedin_url: 'https://www.linkedin.com/sales/lead/ABC123' },
    (o) => { assert.equal(o.linkedin_unmatchable, true); }],
  ['email trim + lowercase only',
    { email: '  John.Doe+Sales@Example.COM ' },
    (o) => { assert.equal(o.email_lc, 'john.doe+sales@example.com');
             assert.equal(o.identity_key, 'john.doe+sales@example.com'); }],
  ['no plus/dot stripping (false-merge guard)',
    { email: 'pii-ee6de387@example.invalid' },
    (o) => { assert.equal(o.email_lc, 'pii-ee6de387@example.invalid'); }],
  ['linkedin wins identity_key over email',
    { linkedin_url: 'https://linkedin.com/in/pii-4d0e3594', email: 'pii-83fd2c75@example.invalid' },
    (o) => { assert.equal(o.identity_key, 'lead1'); }],
  ['invalid email shape -> null',
    { email: 'not-an-email' },
    (o) => { assert.equal(o.email_lc, null); assert.equal(o.identity_key, null); }],
  ['no identifiers -> null identity',
    {}, (o) => { assert.equal(o.identity_key, null); }],
  ['norm_v stamped v1',
    { email: 'pii-fd989748@example.invalid' }, (o) => { assert.equal(o.norm_v, 'v1'); }],
].forEach(([n, inp, chk]) => t(n, () => chk(normalizeIdentityV1(inp))));

// ---------------------------------------------------------------- merge
console.log('merge_v1:');
const norm = (i) => normalizeIdentityV1(i);
const inc = (o) => Object.assign({ source: 'heyreach_reply', correlation_id: 'corr_1' }, o);

t('insert when no match -> replied is permanent, no expiry (expiry is dead, Melisa 2026-08-26 / Nik 2026-08-31)', () => {
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [], matchedByEmail: [] });
  assert.equal(d.action, 'insert');
  assert.equal(d.record.status, 'active');
  assert.equal(d.record.expires_at, null);
  assert.equal(d.record.norm_v, 'v1');
});

t('explicit_opt_out is permanent (null expiry)', () => {
  const d = dncMergeDecisionV1({ norm: norm({ email: 'pii-e2274dd3@example.invalid' }),
    incoming: inc({ entry_type: 'explicit_opt_out' }), config: CFG, matchedByLinkedin: [], matchedByEmail: [] });
  assert.equal(d.record.expires_at, null);
});

t('strongest wins + never downgrade explicit_opt_out', () => {
  const existing = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a',
    entry_type: 'explicit_opt_out', source: 'smartlead_category', status: 'active',
    added_at: '2026-01-01T00:00:00.000Z', expires_at: null, norm_v: 'v1' };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [existing], matchedByEmail: [] });
  assert.equal(d.record.entry_type, 'explicit_opt_out');   // not downgraded to replied
  assert.equal(d.record.expires_at, null);                 // stays permanent
});

t('source is appended + de-duped', () => {
  const existing = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a',
    entry_type: 'replied', source: 'heyreach_reply', status: 'active',
    added_at: '2026-01-01T00:00:00.000Z', expires_at: '2026-07-01T00:00:00.000Z', norm_v: 'v1' };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a' }),
    incoming: inc({ entry_type: 'replied', source: 'smartlead_category' }), config: CFG,
    matchedByLinkedin: [existing], matchedByEmail: [] });
  assert.equal(d.record.source, 'heyreach_reply,smartlead_category');
});

t('replay of same event is a no-op (idempotent)', () => {
  // expires_at: null -- matches real post-migration rows (the 2026-08-31 mass-null; expiry is
  // dead). A stale live-only fixture asserting the old '2027-01-23...' TTL value would falsely
  // register as a real change (update, not noop) against what computeExpiry now always returns.
  const existing = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a',
    email_lc: null, full_name: null, pipedrive_person_id: null,
    entry_type: 'replied', source: 'heyreach_reply', reply_category: null, status: 'active',
    added_at: '2026-07-23T00:00:00.000Z', expires_at: null, norm_v: 'v1' };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [existing], matchedByEmail: [] });
  assert.equal(d.action, 'noop');
});

t('conflict: linkedin and email resolve to different rows -> no write', () => {
  const liRow = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a', entry_type: 'replied', status: 'active', added_at: NOW };
  const emRow = { id: 2, identity_key: 'pii-188576fd@example.invalid', email_lc: 'pii-188576fd@example.invalid', entry_type: 'replied', status: 'active', added_at: NOW };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a', email: 'pii-188576fd@example.invalid' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [liRow], matchedByEmail: [emRow] });
  assert.equal(d.action, 'conflict');
  assert.ok(d.linkedin_row && d.email_row);
});

t('split-identity merge: Person-69cbb908 shape corroborates and merges into the pid row (2026-08-20)', () => {
  // exact live shape: a LinkedIn-only employee_connection row (Noah's Aug-11 import, no email,
  // no pid) collides with a row S3 itself wrote with email+pid but no LinkedIn (extraction was
  // broken at write time). Same real person -- must merge into the pid row, not stay a conflict.
  const empRow = { id: 20542, identity_key: 'barryheavey', linkedin_url_norm: 'https://www.linkedin.com/in/pii-8fcafbff',
    email_lc: null, full_name: null, pipedrive_person_id: null, entry_type: 'employee_connection',
    reason: 'manual_offboard_eligible', source_ref: 'Noah Keimach', source: 'onboarding_import:Noah Keimach',
    also_flagged: '[]', status: 'active', added_at: '2026-08-11T07:10:54.874Z', norm_v: 'v1' };
  const pidRow = { id: 23840, identity_key: 'pii-74b0e852@example.invalid', linkedin_url_norm: null,
    email_lc: 'pii-74b0e852@example.invalid', full_name: 'Person-69cbb908', pipedrive_person_id: 85763,
    entry_type: 'manual', reason: 'sales_personal_outreach', source_ref: 'Surfe',
    source: 'pipedrive_surfe,pipedrive_personal', also_flagged: '[]', status: 'active',
    added_at: '2026-08-13T12:15:46.826Z', norm_v: 'v1' };
  const conflictResult = { action: 'conflict', linkedin_row: empRow, email_row: pidRow };
  const r = dncSplitIdentityMergeV1(conflictResult, { incoming: inc({ entry_type: 'manual' }), config: CFG });
  assert.equal(r.corroborated, true);
  assert.equal(r.record.id, 23840, 'must merge INTO the pid row, never the LinkedIn-only row');
  assert.equal(r.record.identity_key, 'pii-74b0e852@example.invalid', 'identity_key stays put -- lookups match on linkedin_url_norm/email_lc columns, not this field');
  assert.equal(r.record.linkedin_url_norm, 'https://www.linkedin.com/in/pii-8fcafbff', 'LinkedIn must be unioned in');
  assert.equal(r.record.email_lc, 'pii-74b0e852@example.invalid');
  assert.equal(r.record.pipedrive_person_id, 85763);
  assert.equal(r.record.entry_type, 'employee_connection', 'stronger type (2) beats manual (1), never downgrades');
  assert.ok(r.record.source.includes('onboarding_import:Noah Keimach') && r.record.source.includes('pipedrive_surfe'),
    'sources from BOTH half-rows must be unioned, not one dropped');
  assert.equal(r.tombstone.id, 20542, 'the LinkedIn-only row is what gets tombstoned');
  assert.equal(r.tombstone.identity_key, 'barryheavey');
});

t('split-identity merge: names that do NOT corroborate stay a conflict (2026-08-20)', () => {
  // same SHAPE (LinkedIn-only employee_connection + pid-carrying row), but the names don't match
  // -- this really could be two different people who happen to collide on some other axis. Must
  // NOT auto-merge; must leave the original conflict untouched for a human to resolve.
  const empRow = { id: 1, identity_key: 'janedoe', linkedin_url_norm: 'https://www.linkedin.com/in/pii-597e35a0',
    email_lc: null, full_name: 'Person-fbbb498b', pipedrive_person_id: null, entry_type: 'employee_connection',
    status: 'active', added_at: NOW };
  const pidRow = { id: 2, identity_key: 'pii-715429ce@example.invalid', linkedin_url_norm: null, email_lc: 'pii-715429ce@example.invalid',
    full_name: 'Bob Smith', pipedrive_person_id: 999, entry_type: 'manual', status: 'active', added_at: NOW };
  const r = dncSplitIdentityMergeV1({ action: 'conflict', linkedin_row: empRow, email_row: pidRow },
    { incoming: inc({ entry_type: 'manual' }), config: CFG });
  assert.equal(r.corroborated, false);
  assert.equal(r.record, undefined, 'no merged record when names do not corroborate');
});

t('split-identity merge: shape must match exactly -- two pid-carrying rows never auto-merge', () => {
  // guards against widening the rule by accident: BOTH rows carrying a pipedrive_person_id (a
  // real ambiguous-person case, not a split-identity artifact) must never trigger this path,
  // even if the names happen to match (could be two employees who share a name).
  const rowA = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a',
    email_lc: null, full_name: 'Same Name', pipedrive_person_id: 111, entry_type: 'manual', status: 'active', added_at: NOW };
  const rowB = { id: 2, identity_key: 'pii-7ea89e72@example.invalid', linkedin_url_norm: null, email_lc: 'pii-7ea89e72@example.invalid',
    full_name: 'Same Name', pipedrive_person_id: 222, entry_type: 'manual', status: 'active', added_at: NOW };
  const r = dncSplitIdentityMergeV1({ action: 'conflict', linkedin_row: rowA, email_row: rowB },
    { incoming: inc({ entry_type: 'manual' }), config: CFG });
  assert.equal(r.corroborated, false);
});

t('dncSlugifyName: normalizes for comparison', () => {
  assert.equal(dncSlugifyName('Person-69cbb908'), 'barryheavey');
  assert.equal(dncSlugifyName("O'Brien-Smith Jr."), 'obriensmithjr');
  assert.equal(dncSlugifyName(null), '');
});

t('same person under both identifiers is NOT a conflict', () => {
  const row = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a', email_lc: 'pii-22fdb3ff@example.invalid', entry_type: 'replied', source: 'heyreach_reply', status: 'active', added_at: NOW, expires_at: '2027-01-23T00:00:00.000Z', norm_v: 'v1' };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a', email: 'pii-22fdb3ff@example.invalid' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [row], matchedByEmail: [row] });
  assert.notEqual(d.action, 'conflict');
});

t('reactivation: new event on expired row re-suppresses', () => {
  const expired = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a',
    entry_type: 'replied', source: 'heyreach_reply', status: 'expired',
    added_at: '2025-01-01T00:00:00.000Z', expires_at: '2025-07-01T00:00:00.000Z', norm_v: 'v1' };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [expired], matchedByEmail: [] });
  assert.equal(d.action, 'update');
  assert.equal(d.record.status, 'active');
  assert.equal(d.record.added_at, NOW);                     // fresh clock
  assert.equal(d.record.expires_at, null);                  // expiry is dead (Nik, 2026-08-31)
});

t('duplicate rows for identity -> self_heal_remove lists the extras', () => {
  const r1 = { id: 1, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a', entry_type: 'replied', source: 'heyreach_reply', status: 'active', added_at: '2026-01-01T00:00:00.000Z', expires_at: '2026-07-01T00:00:00.000Z', norm_v: 'v1' };
  const r2 = { id: 2, identity_key: 'a', linkedin_url_norm: 'https://www.linkedin.com/in/a', entry_type: 'replied', source: 'smartlead_category', status: 'active', added_at: '2026-02-01T00:00:00.000Z', expires_at: '2026-08-01T00:00:00.000Z', norm_v: 'v1' };
  const d = dncMergeDecisionV1({ norm: norm({ linkedin_url: 'https://linkedin.com/in/a' }),
    incoming: inc({ entry_type: 'replied' }), config: CFG, matchedByLinkedin: [r1, r2], matchedByEmail: [] });
  assert.ok(d.self_heal_remove.length >= 1);
});

t('computeExpiry: expiry is dead -- every entry_type is permanent (Nik, 2026-08-31)', () => {
  assert.equal(computeExpiry('negative_reply', NOW, 6), null);
  assert.equal(computeExpiry('replied', NOW, 6), null);
  assert.equal(computeExpiry('employee_connection', NOW, 6), null);
  assert.equal(computeExpiry('manual', NOW, 6), null);
});

// ---------------------------------------------------------------- reason_v1 (STAGE 1 addition)
console.log('reason_v1:');

t('reasonEntryType maps every domain value (backward-compat mapping)', () => {
  assert.equal(reasonEntryType('client'), 'explicit_opt_out');
  assert.equal(reasonEntryType('unsubscribe'), 'explicit_opt_out');
  assert.equal(reasonEntryType('reply_dnc'), 'negative_reply');   // corrected 2026-08-07, HANDOFF paul.gilford
  assert.equal(reasonEntryType('manual_offboard_eligible'), 'employee_connection');
  assert.equal(reasonEntryType('manual_sheet'), 'manual');
  assert.equal(reasonEntryType('offboard'), 'manual');
});

t('reasonStrongest: client > unsubscribe > reply_dnc > manual_offboard_eligible > manual_sheet', () => {
  assert.equal(reasonStrongest('manual_sheet', 'client'), 'client');
  assert.equal(reasonStrongest('client', 'unsubscribe'), 'client');
  assert.equal(reasonStrongest('unsubscribe', 'reply_dnc'), 'unsubscribe');
  assert.equal(reasonStrongest('reply_dnc', 'manual_offboard_eligible'), 'reply_dnc');
  assert.equal(reasonStrongest('manual_offboard_eligible', 'manual_sheet'), 'manual_offboard_eligible');
  assert.equal(reasonStrongest(null, 'manual_sheet'), 'manual_sheet');
});

t('isOffboardRemovable: only manual_offboard_eligible', () => {
  assert.equal(isOffboardRemovable('manual_offboard_eligible'), true);
  assert.equal(isOffboardRemovable('client'), false);
  assert.equal(isOffboardRemovable('reply_dnc'), false);
  assert.equal(isOffboardRemovable('manual_sheet'), false);
});

t('reasonMergeV1: reply_dnc beats manual_offboard_eligible, loser preserved in also_flagged', () => {
  // the exact ahmedmody/maaikepot/christian-ziegelt collision class from the People-DNC dry-run
  const existing = { reason: 'manual_offboard_eligible', source_ref: 'Benedetto', source: null };
  const incoming = { reason: 'reply_dnc', source_ref: null, source: 'Amsterdam 2025 Reply' };
  const m = reasonMergeV1(existing, incoming);
  assert.equal(m.reason, 'reply_dnc');
  assert.equal(m.also_flagged.length, 1);
  assert.equal(m.also_flagged[0].reason, 'manual_offboard_eligible');
  assert.equal(m.also_flagged[0].source_ref, 'Benedetto');
});

t('reasonMergeV1: client beats everything, never loses even to a later reply_dnc', () => {
  const existing = { reason: 'client', source_ref: 'Client List', also_flagged: [] };
  const incoming = { reason: 'reply_dnc', source_ref: null, source: 'some event' };
  const m = reasonMergeV1(existing, incoming);
  assert.equal(m.reason, 'client');
  assert.equal(m.also_flagged[0].reason, 'reply_dnc');
});

t('reasonMergeV1: same reason, different source_ref -> winner keeps first, loser flagged (no data loss)', () => {
  const existing = { reason: 'manual_offboard_eligible', source_ref: 'Toby', also_flagged: [] };
  const incoming = { reason: 'manual_offboard_eligible', source_ref: 'Mario Stalder', source: 'LinkedIn' };
  const m = reasonMergeV1(existing, incoming);
  assert.equal(m.reason, 'manual_offboard_eligible');
  assert.equal(m.source_ref, 'Toby');   // first-seen kept as primary attribution
  assert.equal(m.also_flagged[0].source_ref, 'Mario Stalder');
});

t('reasonMergeV1: no existing signal -> incoming wins outright, no also_flagged', () => {
  const m = reasonMergeV1(null, { reason: 'manual_sheet', source_ref: null, source: 'Pipedrive' });
  assert.equal(m.reason, 'manual_sheet');
  assert.deepEqual(m.also_flagged, []);
});

t('reasonExpiryOverride: reply_dnc + unknown precision -> forces null, otherwise no override', () => {
  assert.deepEqual(reasonExpiryOverride('reply_dnc', 'unknown'), { override: true, expires_at: null });
  assert.deepEqual(reasonExpiryOverride('reply_dnc', 'derived'), { override: false });
  assert.deepEqual(reasonExpiryOverride('client', 'unknown'), { override: false });
});

// ---------------------------------------------------------------- drift check
console.log('drift (JSON Code nodes embed frozen lib verbatim):');
function marker(file, name) {
  const src = fs.readFileSync(path.join(LIB, file), 'utf8');
  return src.match(new RegExp('//\\s*>>> ' + name + ' >>>\\n([\\s\\S]*?)\\n//\\s*<<< ' + name + ' <<<'))[1];
}
function codeOf(wfFile) {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, wfFile), 'utf8'));
  return wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code').map((n) => n.parameters.jsCode).join('\n');
}
const NORM = marker('normalize_v1.js', 'normalize_v1');
const MERGE = marker('merge_v1.js', 'merge_v1');
const REASON = marker('reason_v1.js', 'reason_v1');
t('NormalizeIdentity embeds normalize_v1 verbatim', () =>
  assert.ok(codeOf('DNC__NormalizeIdentity__v1.json').includes(NORM)));
t('UpsertLedger embeds normalize_v1 + merge_v1 + reason_v1 verbatim', () => {
  const c = codeOf('DNC__UpsertLedger__v1.json');
  assert.ok(c.includes(NORM), 'missing normalize'); assert.ok(c.includes(MERGE), 'missing merge');
  assert.ok(c.includes(REASON), 'missing reason_v1'); });
t('UpsertLedger: old-style entry_type-only callers still validated without reason', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const prep = wf.nodes.find((n) => n.name === 'Normalize + Prep').parameters.jsCode;
  assert.ok(prep.includes("s.entry_type"), 'prep no longer reads entry_type directly -- backward-compat path removed');
  assert.ok(prep.includes('if (s.reason)'), 'prep does not branch on reason presence');
});
t('CheckLedger embeds normalize_v1 verbatim', () =>
  assert.ok(codeOf('DNC__CheckLedger__v1.json').includes(NORM)));
t('UpsertLedger uses only the verified eq operator', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const conds = JSON.stringify(wf).match(/"condition":\s*"([^"]+)"/g) || [];
  conds.forEach((c) => assert.ok(c.includes('"eq"'), 'non-eq operator found: ' + c));
});

t('every dataTable upsert node has non-empty filters.conditions (regression guard, 2026-08-10)', () => {
  // Caught live by zz_probe_ verification: n8n's upsert operation throws "At least one condition
  // is required" if filters.conditions is empty/missing -- this shipped broken from Build 2
  // through this fix because no static test ever executed a real n8n instance. matchingColumns
  // alone does NOT satisfy the runtime requirement.
  for (const wfFile of ['DNC__UpsertLedger__v1.json', 'dnc_expiry_job.json']) {
    const full = wfFile === 'dnc_expiry_job.json' ? path.join(SUB, '..', 'workflows', 'dnc_expiry_job', wfFile) : path.join(SUB, wfFile);
    const wf = JSON.parse(fs.readFileSync(full, 'utf8'));
    for (const n of wf.nodes) {
      if (n.type === 'n8n-nodes-base.dataTable' && n.parameters.operation === 'upsert') {
        const conds = (n.parameters.filters || {}).conditions || [];
        assert.ok(conds.length > 0, `${wfFile}/${n.name}: upsert with empty filters.conditions`);
        const matching = n.parameters.columns.matchingColumns || [];
        assert.deepEqual(conds.map((c) => c.keyName).sort(), matching.slice().sort(),
          `${wfFile}/${n.name}: filter conditions must match matchingColumns exactly`);
      }
    }
  }
});

t('dataTableId for dnc_registry_dev uses mode:id, never mode:name (regression guard, 2026-08-10)', () => {
  // Caught live by zz_probe_: mode:"name" resolves fine when a workflow runs from its OWN
  // trigger, but throws "Could not find the data table" when that workflow is invoked as a
  // SUBWORKFLOW (Execute Workflow -> executeWorkflowTrigger) -- which is how UpsertLedger and
  // CheckLedger ALWAYS run in production. This would have silently broken 100% of real traffic.
  for (const wfFile of ['DNC__UpsertLedger__v1.json', 'DNC__CheckLedger__v1.json', 'DNC__NormalizeIdentity__v1.json']) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, wfFile), 'utf8'));
    for (const n of wf.nodes) {
      if (n.type === 'n8n-nodes-base.dataTable') {
        const dt = n.parameters.dataTableId;
        if (dt.value === 'dnc_registry_dev' || dt.value === 'UOgKwlGsL28lX61O') {
          assert.equal(dt.mode, 'id', `${wfFile}/${n.name}: dnc_registry_dev must be referenced by mode:id in a subworkflow, found mode:${dt.mode}`);
        }
      }
    }
  }
});

t('reasonMergeV1: no incoming reason but existing has one -> existing PRESERVED, not lost', () => {
  // this is the exact case decide_js's old `if (ctx.incoming.reason && ...)` gate skipped
  // entirely -- a reason-less caller (e.g. heyreach tee) touching an already-classified row
  // must not silently null out reason/source_ref/also_flagged on that row.
  const existing = { reason: 'manual_offboard_eligible', source_ref: 'Toby', also_flagged: [] };
  const m = reasonMergeV1(existing, null);
  assert.equal(m.reason, 'manual_offboard_eligible');
  assert.equal(m.source_ref, 'Toby');
});
t('reasonMergeV1: neither side has a reason -> null (caller must leave the record untouched)', () => {
  assert.equal(reasonMergeV1(null, null), null);
  assert.equal(reasonMergeV1({ reason: null }, null), null);
});

t('UpsertLedger decide_js: reason-merge overlay is NOT gated on ctx.incoming.reason (regression guard, 2026-08-11)', () => {
  // real bug found while building WF-4: gating on ctx.incoming.reason meant a reason-less caller
  // updating a row that ALREADY had a reason would write d.record.reason = undefined (merge_v1's
  // own record object never carries `reason` at all), silently wiping the classification on the
  // very next live event to touch any of the 23,838 seeded rows.
  const decide = codeOf('DNC__UpsertLedger__v1.json');
  assert.ok(!/if \(ctx\.incoming\.reason && d\.action/.test(decide),
    'old buggy gate reintroduced -- reason-less callers would skip the merge overlay entirely');
  assert.ok(/if \(d\.action !== 'conflict' && d\.record\)/.test(decide),
    'expected the ungated overlay condition');
  assert.ok(/if \(merged\)/.test(decide), 'expected a null-guard around merged (reasonMergeV1 can return null)');
});

t('UpsertLedger decide_js: projections_state defaults on insert, carried forward (not reset) on update (regression guard, 2026-08-11)', () => {
  // caught live via zz_probe_reason_preservation.py: an insert correctly set the 3-pending
  // default, but the VERY NEXT update (simulating the heyreach tee) wiped it back to null --
  // merge_v1's own `merged` record never carries projections_state forward at all, so an
  // insert-only guard is not enough; the update path must explicitly pull it from `primary`.
  const decide = codeOf('DNC__UpsertLedger__v1.json');
  assert.ok(/if \(d\.record && d\.record\.projections_state == null\)/.test(decide),
    'expected the ungated null-check (must run on update too, not just insert)');
  assert.ok(/\(primary && primary\.projections_state\) \? JSON\.parse\(primary\.projections_state\) : null/.test(decide),
    'update path must carry projections_state forward from the primary row');
  assert.ok(decide.includes("pipedrive: 'pending', smartlead: 'pending', heyreach: 'pending'"),
    'expected the 3-channel pending default on insert');
});

t('UpsertLedger decide_js: skipped:no_person re-eligible once pipedrive_person_id becomes known (regression guard, 2026-08-20)', () => {
  // found live: Person-83a8d74b's Aug-11 onboarding-import row stayed stuck at
  // pipedrive:'skipped:no_person' even after a later backfill linked her pipedrive_person_id --
  // the plain carry-forward (previous test) copies the OLD stored value verbatim with no re-check,
  // so the Stage-2 sweep's pending-only filter would skip her forever. Must flip that one channel
  // back to pending exactly when the reason it was skipped no longer holds, and touch nothing else.
  const decide = codeOf('DNC__UpsertLedger__v1.json');
  assert.ok(/proj\.pipedrive === 'skipped:no_person' && d\.record\.pipedrive_person_id != null/.test(decide),
    'must gate the re-eligibility flip on both the specific stale value AND a now-known person_id');
  assert.ok(/proj\.pipedrive = 'pending'/.test(decide),
    'must flip pipedrive back to pending, not fabricate a new projections_state shape');
  // must not blanket-reset on every update -- only this one specific transition
  assert.ok(!/proj\.smartlead\s*=/.test(decide) && !/proj\.heyreach\s*=/.test(decide),
    'must not touch smartlead/heyreach -- their own skip/failed/done states have unrelated causes');
});

t('UpsertLedger decide_js: owner_tag recomputed from the FINAL merged reason, only for manual_offboard_eligible', () => {
  const decide = codeOf('DNC__UpsertLedger__v1.json');
  assert.ok(/d\.record\.owner_tag = \(merged\.reason === 'manual_offboard_eligible'\) \? \(merged\.source_ref \|\| null\) : null;/.test(decide));
});

t('UpsertLedger writes owner_tag and projections_state to the table (regression guard, 2026-08-11)', () => {
  // these two columns existed in the schema since STAGE 1 but were never wired into UP_VALUE --
  // confirmed live via zz_probe_ needing a "Direct-set remaining 4 cols" bypass node to even test
  // the columns existed. WF-4 depends on real inserts populating projections_state correctly.
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const upsertNode = wf.nodes.find((n) => n.type === 'n8n-nodes-base.dataTable' && n.parameters.operation === 'upsert');
  const value = upsertNode.parameters.columns.value;
  assert.equal(value.owner_tag, '={{ $json.record.owner_tag }}');
  assert.equal(value.projections_state, '={{ $json.record.projections_state }}');
});

t('UpsertLedger: split-identity merge is wired end-to-end (regression guard, 2026-08-20)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const decide = codeOf('DNC__UpsertLedger__v1.json');
  assert.ok(decide.includes("dncSplitIdentityMergeV1(d,"), 'decide_js must call the corroboration check on every conflict');
  assert.ok(decide.includes("d.action === 'conflict'"), 'must only attempt corroboration when the base decision was a conflict');

  // fallbackOutput on Route catches merge_split_identity automatically (it isn't 'conflict' or
  // 'noop') -- confirm the switch still has exactly those two explicit rules, not a third one
  // that would need its own wiring.
  const route = wf.nodes.find((n) => n.name === 'Route');
  const outputKeys = route.parameters.rules.values.map((v) => v.outputKey);
  assert.deepEqual(outputKeys.sort(), ['conflict', 'noop'].sort(),
    'merge_split_identity must ride the existing fallback, not need a new explicit branch');

  const gate = wf.nodes.find((n) => n.name === 'Has Tombstone?');
  assert.ok(gate, 'expected a gate deciding whether this write also needs a tombstone');
  assert.ok(JSON.stringify(gate.parameters).includes("Decide').first().json.tombstone"));
  // Upsert Ledger Row -> Enqueue Supabase Delta -> Has Tombstone? (2026-09-14, Phase 2 delta
  // pusher) -- the claim-enqueue is fire-and-forget (onError:continueErrorOutput) and must sit
  // between the write and the gate on BOTH its output branches, never gating or blocking the real
  // tombstone decision.
  assert.equal(wf.connections['Upsert Ledger Row'].main[0][0].node, 'Enqueue Supabase Delta',
    'every real write must enqueue a Supabase delta-push claim right after writing');
  const enqueueConn = wf.connections['Enqueue Supabase Delta'].main;
  assert.equal(enqueueConn[0][0].node, 'Has Tombstone?', 'success branch must still reach the tombstone gate');
  assert.equal(enqueueConn[1][0].node, 'Has Tombstone?', 'error branch must ALSO still reach the tombstone gate -- a failed claim-enqueue must never block the real write path');

  const gateConn = wf.connections['Has Tombstone?'].main;
  assert.equal(gateConn[0][0].node, 'Tombstone Split-Identity Row');
  assert.equal(gateConn[1].length, 0, 'false branch (no tombstone) must be a clean dead end');

  // the tombstoned (losing) identity's row also changed and needs its OWN delta-push claim, keyed
  // by ITS id (the tombstone target), not the primary ledger row's id.
  assert.equal(wf.connections['Tombstone Split-Identity Row'].main[0][0].node, 'Enqueue Supabase Delta (Tombstone)');
  const tombEnqueue = wf.nodes.find((n) => n.name === 'Enqueue Supabase Delta (Tombstone)');
  assert.ok(tombEnqueue, 'expected a second claim-enqueue node for the tombstoned row');
  assert.ok(JSON.stringify(tombEnqueue.parameters.columns.value.claim_key).includes("tombstone.id"),
    'the tombstone claim must key off the tombstoned row\'s own id, not the primary ledger row\'s id');
  for (const n of ['Enqueue Supabase Delta', 'Enqueue Supabase Delta (Tombstone)']) {
    const node = wf.nodes.find((x) => x.name === n);
    assert.equal(node.onError, 'continueErrorOutput', `${n} must never fail/stop the subworkflow it's chained into`);
    assert.equal(node.parameters.dataTableId.value, 'euyostwJYfJefItC', `${n} must target the shared claims table`);
  }

  const tombNode = wf.nodes.find((n) => n.name === 'Tombstone Split-Identity Row');
  assert.equal(tombNode.parameters.operation, 'update');
  assert.equal(tombNode.parameters.columns.value.status, 'removed');
  assert.ok(tombNode.parameters.columns.value.removed_reason.includes("'merged_into:'"),
    'removed_reason must record which row this was merged into, per Nik\'s spec');
  assert.equal(tombNode.parameters.filters.conditions[0].keyName, 'id',
    'must match the tombstone target by row id, never identity_key (the LI-only row already has identity_key === the LinkedIn slug being merged in)');
});

t('UpsertLedger: Slack Conflict Alert can never kill the calling execution (regression guard, 2026-08-20)', () => {
  // crashed live: "channel_not_found" on the (now-fixed) dead alert_channel took down the ENTIRE
  // S3 watcher poll -- every S1-S4/reversal caller inherits this node via executeWorkflow, so an
  // alert-delivery failure alone must never be able to stop the actual write path. Both halves
  // matter: onError:continueErrorOutput opts out of the crash, and the error output must be
  // WIRED (an unwired continueErrorOutput branch is the exact same "check that cannot fire" class
  // as the OOM postmortem's unwired write-path onError -- silent data loss instead of a crash).
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const alertNode = wf.nodes.find((n) => n.name === 'Slack Conflict Alert');
  assert.equal(alertNode.onError, 'continueErrorOutput', 'must not use n8n\'s stop-the-execution default');
  assert.equal(alertNode.retryOnFail, true, 'a transient Slack blip should get a retry before giving up');
  assert.equal(alertNode.maxTries, 3);

  const errConn = wf.connections['Slack Conflict Alert'].main;
  assert.equal(errConn[0].length, 0, 'success output: nothing downstream, same as before this fix');
  assert.equal(errConn[1].length, 1, 'error output (index 1) must be wired, not a dead end');
  assert.equal(errConn[1][0].node, 'Conflict Alert Failed');

  const failNode = wf.nodes.find((n) => n.name === 'Conflict Alert Failed');
  assert.ok(failNode, 'the error-output target node must actually exist');
  assert.ok(failNode.parameters.jsCode.includes('alert_failed: true'));
  // the conflict detail itself must still be recoverable from this same execution even when the
  // human-facing alert never sent -- not just a bare "something failed" with no context.
  assert.ok(/\$\('Decide'\)\.first\(\)\.json/.test(failNode.parameters.jsCode),
    'must pull the actual conflict detail from Decide, not just report a bare failure flag');
});

t('slack_post helper: retry/error-handling behavior is documented, project-wide gap flagged (2026-08-20)', () => {
  // point 4 of the addendum: retry behavior was undocumented. It's also, on inspection, absent --
  // every OTHER Slack post in the project still inherits n8n's no-retry/stop-on-error default.
  // This test locks in that the gap is at least written down where the next person will look,
  // not that every call site has been fixed (it hasn't -- see the sweep count below).
  const src = fs.readFileSync(path.join(__dirname, '..', '..', 'build_dnc.py'), 'utf8');
  const helperMatch = src.match(/def slack_post\([^)]*\):[\s\S]*?return node\(/);
  assert.ok(helperMatch, 'expected to find the slack_post helper definition');
  assert.ok(/RETRY\/ERROR BEHAVIOR/.test(helperMatch[0]),
    'the helper must document that it sets neither retryOnFail nor onError by default');

  // count how many slack_post call sites exist vs. how many opted into continueErrorOutput --
  // documents the current state of the sweep rather than asserting a specific number, so this
  // test doesn't need editing every time one more call site gets fixed.
  const callSites = (src.match(/slack_post\(/g) || []).length;
  const optedOut = (src.match(/extra_props=\{"onError": "continueErrorOutput"/g) || []).length;
  assert.ok(callSites > optedOut,
    'sanity check: if this ever equals callSites, the "project-wide gap" framing above is stale and should be updated');
});

t('executeWorkflow nodes reference already-deployed subworkflows by mode:id, never a REPLACE_ placeholder (regression guard, 2026-08-11)', () => {
  // found live on the deployed heyreach_reply_to_dnc_ledger and dnc_check_service: both still had
  // mode:"list" + value:"REPLACE_<name>_ID" -- would fail immediately with "workflow not found"
  // the moment either is ever triggered. Neither had been activated yet so nothing noticed.
  const KNOWN_IDS = {
    'DNC__NormalizeIdentity__v1': 'K2M1Z0m1gKX6LdFI',
    'DNC__UpsertLedger__v1': 'RolYGL3J2CNg6Yp3',
    'DNC__CheckLedger__v1': 'kv7reJYAAgsOV33t',
  };
  const files = ['DNC__UpsertLedger__v1.json', 'DNC__CheckLedger__v1.json',
    path.join('..', 'workflows', 'heyreach_reply_to_dnc_ledger', 'heyreach_reply_to_dnc_ledger.json'),
    path.join('..', 'workflows', 'dnc_check_service', 'dnc_check_service.json')];
  for (const rel of files) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, rel), 'utf8'));
    for (const n of wf.nodes) {
      if (n.type !== 'n8n-nodes-base.executeWorkflow') continue;
      const wid = n.parameters.workflowId;
      const target = wid.cachedResultName;
      if (KNOWN_IDS[target]) {
        assert.equal(wid.mode, 'id', `${rel}/${n.name}: ${target} is deployed, must use mode:id`);
        assert.equal(wid.value, KNOWN_IDS[target], `${rel}/${n.name}: wrong id for ${target}`);
        assert.ok(!String(wid.value).startsWith('REPLACE_'), `${rel}/${n.name}: unresolved placeholder`);
      }
    }
  }
});

t('httpQueryAuth-credentialed HTTP nodes use genericCredentialType, never predefinedCredentialType (regression guard, 2026-08-11)', () => {
  // httpQueryAuth is a GENERIC credential type (genericAuth=true in n8n's own source) -- the HTTP
  // Request node only injects the query-auth param when authentication="genericCredentialType" +
  // genericAuthType="httpQueryAuth". "predefinedCredentialType"+nodeCredentialType silently sends
  // the request UNAUTHENTICATED (live-verified: Pipedrive served its HTML login page instead of a
  // JSON 401). Every prior use of this helper had a REPLACE_ME placeholder and was never actually
  // executed with a real credential, so this shipped unnoticed since Build 1.
  const files = [
    path.join(SUB, '..', 'workflows', 'smartlead_observability_readonly', 'smartlead_observability_readonly.json'),
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'),
  ];
  for (const full of files) {
    const wf = JSON.parse(fs.readFileSync(full, 'utf8'));
    for (const n of wf.nodes) {
      if (n.type !== 'n8n-nodes-base.httpRequest') continue;
      if (!(n.credentials || {}).httpQueryAuth) continue;
      assert.equal(n.parameters.authentication, 'genericCredentialType',
        `${full}/${n.name}: httpQueryAuth credential requires authentication=genericCredentialType`);
      assert.equal(n.parameters.genericAuthType, 'httpQueryAuth',
        `${full}/${n.name}: missing genericAuthType=httpQueryAuth`);
      assert.equal(n.parameters.nodeCredentialType, undefined,
        `${full}/${n.name}: nodeCredentialType is the wrong mechanism for a generic credential type`);
    }
  }
});

t('dnc_projections_sweep: FIRE_PIPEDRIVE and FIRE_SMARTLEAD default false in CONFIG (regression guard, 2026-08-11)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const get = (k) => cfg.parameters.assignments.assignments.find((a) => a.name === k).value;
  assert.strictEqual(get('FIRE_PIPEDRIVE'), false, 'live-write firing must default off');
  assert.strictEqual(get('FIRE_SMARTLEAD'), false, 'live-write firing must default off');
});

t('dnc_projections_sweep: no HeyReach live-write branch exists (regression guard, 2026-08-11)', () => {
  // HeyReach projections are explicitly OUT of the build until the paused-lead-webhook question
  // resolves (PROJECTIONS_PASS_PLAN_2026-08-11.md) -- the HeyReach branch must be count-only.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const heyreachHttp = wf.nodes.filter((n) =>
    n.type === 'n8n-nodes-base.httpRequest' && JSON.stringify(n.parameters.url || '').includes('heyreach'));
  assert.equal(heyreachHttp.length, 0, 'no HTTP node should target heyreach.io in this workflow yet');
  const hrNode = wf.nodes.find((n) => n.name === 'HR Count Pending');
  assert.ok(hrNode, 'expected a count-only HeyReach node');
});

t('dnc_projections_sweep: SL Get Candidates fans OUT from a single always-executes source, never fans IN from the per-item write outcomes (regression guard, 2026-08-11, rewired 2026-08-12, REWRITTEN 2026-09-15)', () => {
  // History: without SOME barrier, the moment FIRE_PIPEDRIVE is ever flipped true, the Split Out
  // fan-out (one item per row) would cause the Smartlead branch to run once PER ROW instead of
  // once overall. 2026-08-12 first fixed this with an explicit Merge(append, numberInputs:3)
  // converging PD Mark Done (with lead) / PD Mark Done (no lead) / PD Count Write Errors before a
  // "PD Write Barrier" node. That Merge was itself the SAME class of bug one level up (see
  // dnc_supabase_delta_pusher's 2026-09-14 incident, memory: n8n-multi-input-node-fires-per-branch):
  // it only reliably fires when MULTIPLE of its declared inputs receive items in a given execution
  // -- fine for a typical mixed chunk (with-lead + no-lead both populated) but silently never fires
  // the moment a chunk lands on only ONE of those branches (plausible for a small/homogeneous tail
  // chunk), which would silently stop the Smartlead branch AND Combine Summaries/Dev Summary from
  // ever running -- exactly the operational blindness an unattended hourly schedule cannot
  // tolerate. Fixed 2026-09-15 (Nik's GO, before scheduling): removed PD Merge Write Paths / PD
  // Write Barrier entirely; "PD Aggregate" (which already runs exactly once per execution, before
  // the with-lead/no-lead fork) now fans OUT directly to both FIRE_PIPEDRIVE? and SL Get
  // Candidates. PD Mark Done (with lead)/(no lead)/PD Count Write Errors are now clean dead ends --
  // Combine Summaries already reads their data via $() named references, never via a wired
  // connection, so nothing downstream loses any data.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  assert.ok(!wf.nodes.some((n) => n.name === 'PD Merge Write Paths'),
    'PD Merge Write Paths must be gone -- it is the fan-in shape being fixed');
  assert.ok(!wf.nodes.some((n) => n.name === 'PD Write Barrier'),
    'PD Write Barrier must be gone -- nothing downstream needs its {done:true} payload');
  assert.ok(wf.nodes.some((n) => n.name === 'SL Write Barrier'));

  const targets = (src) => ((wf.connections[src] && wf.connections[src].main[0]) || []).map((c) => c.node);
  // PD Aggregate fans out to BOTH FIRE_PIPEDRIVE? (unchanged) AND directly to SL Get Candidates.
  assert.deepEqual(targets('PD Aggregate').sort(), ['FIRE_PIPEDRIVE?', 'SL Get Candidates'].sort());
  assert.deepEqual(targets('SL Mark Done').sort(), ['SL Enqueue Supabase Delta', 'SL Write Barrier']);

  // the exact regression this test guards against: SL Get Candidates must have exactly ONE
  // incoming source node (PD Aggregate) -- never two or more distinct sources feeding it in the
  // same execution, which is the "fires once per branch" trap.
  const incomingToSl = Object.entries(wf.connections)
    .filter(([, out]) => out.main.some((branch) => (branch || []).some((c) => c.node === 'SL Get Candidates')))
    .map(([src]) => src);
  assert.deepEqual(incomingToSl, ['PD Aggregate'],
    'SL Get Candidates must have exactly one incoming source (PD Aggregate), not a converging Merge/Barrier or a second FIRE_PIPEDRIVE? branch');

  // FIRE_PIPEDRIVE?'s own false branch must NOT also target SL Get Candidates -- that would be a
  // second distinct source feeding it (on top of PD Aggregate's direct wire), reintroducing the
  // same fan-in risk on any FIRE_PIPEDRIVE=false dev/test run.
  const firePdFalseBranch = wf.connections['FIRE_PIPEDRIVE?'].main[1] || [];
  assert.deepEqual(firePdFalseBranch, [], 'FIRE_PIPEDRIVE? false branch must be a clean dead end');

  // PD Mark Done (with lead)/(no lead)/PD Count Write Errors are now clean dead ends -- their data
  // table writes are what mattered, sequencing no longer depends on their output.
  assert.deepEqual(targets('PD Mark Done (with lead)'), []);
  assert.deepEqual(targets('PD Mark Done (no lead)'), []);
  assert.deepEqual(targets('PD Count Write Errors'), []);
});

t('dnc_projections_sweep: hourly schedule trigger added alongside the manual webhook (2026-09-15, Nik\'s GO)', () => {
  // Root cause found in the full DNC audit: this workflow existed since 2026-08-11 with only a
  // webhook trigger and nothing in the estate ever called it, so it only ran twice (manual test
  // fires, both 2026-09-08) -- 78/79 recent registry rows never got their Pipedrive 686 field.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const timer = wf.nodes.find((n) => n.name === 'Sweep Timer');
  assert.ok(timer, 'expected an hourly Schedule Trigger node');
  assert.equal(timer.type, 'n8n-nodes-base.scheduleTrigger');
  assert.equal(timer.parameters.rule.interval[0].minutesInterval, 60);
  assert.ok(wf.nodes.some((n) => n.name === 'Webhook'),
    'the webhook must stay -- dnc_fire_pipedrive_chunk.py\'s sanctioned supervised-fire path depends on it');
  const targets = (src) => ((wf.connections[src] && wf.connections[src].main[0]) || []).map((c) => c.node);
  assert.deepEqual(targets('Sweep Timer'), ['CONFIG']);
  assert.deepEqual(targets('Webhook'), ['CONFIG']);
});

t('dnc_projections_sweep: PD Filter Pending excludes non-active registry rows (2026-09-15, Nik\'s GO)', () => {
  // Found while wiring the schedule: PD Filter Pending only checked projections_state.pipedrive,
  // never row status -- a status=removed row (e.g. a tombstoned false-positive reply) would still
  // get its Pipedrive DNC field written, which is wrong (a removed row is not DNC anymore) and has
  // no reverse path to undo once written.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const node = wf.nodes.find((n) => n.name === 'PD Filter Pending');
  assert.ok(/r\.status !== 'active'/.test(node.parameters.jsCode));
});

t('dnc_projections_sweep: per-item classify/union nodes use runOnceForEachItem (regression guard, 2026-08-11)', () => {
  // caught live: these nodes were generated as runOnceForAllItems (code_node()'s default) while
  // written assuming per-item $json/.item semantics -- collapsed 330 items to 1 (Pipedrive) and
  // 201 items to 1 (Smartlead) on the sweep's first real execution.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  // PD Classify / PD Label Union removed 2026-09-16 (P1 label incident) -- SL Classify is the
  // only per-item node left in this original finding's scope.
  for (const name of ['SL Classify']) {
    const n = wf.nodes.find((x) => x.name === name);
    assert.equal(n.parameters.mode, 'runOnceForEachItem', `${name}: must run per-item, not per-batch`);
    assert.ok(!/return \[\{ json:/.test(n.parameters.jsCode),
      `${name}: runOnceForEachItem must return a bare { json } object, not an array`);
  }
});

t('dnc_projections_sweep: Pipedrive/Smartlead HTTP nodes are throttled (regression guard, 2026-08-11)', () => {
  // no throttle caused an 85% (Pipedrive) and ~80% (Smartlead) request failure rate from rate
  // limiting on the sweep's first real execution -- n8n's own error message named the fix.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  for (const n of wf.nodes) {
    if (n.type !== 'n8n-nodes-base.httpRequest') continue;
    const batch = (n.parameters.options || {}).batching;
    assert.ok(batch && batch.batch && batch.batch.batchInterval > 0,
      `${n.name}: HTTP node calling an external API in a loop must set a batching interval`);
  }
});

t('dnc_projections_sweep: alert_channel is the confirmed ops channel, guard configured to match (regression guard, 2026-08-11)', () => {
  // the OLD default (C0BFE6KAN8J) returned "channel_not_found" on this sweep's first-ever real
  // Slack post -- the first time any workflow in this project actually posted for real. Every
  // other workflow keeps validating against the historical default; only this one overrides it.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const get = (k) => cfg.parameters.assignments.assignments.find((a) => a.name === k).value;
  assert.equal(get('alert_channel'), 'C0B8GCVNR5W');
  assert.equal(get('dev_channel_guard'), 'C0B8GCVNR5W');
});

t('other DNC workflows retargeted off the dead historical channel (regression guard, 2026-08-11, corrected 2026-08-20)', () => {
  // ORIGINAL intent (2026-08-11): the ops-channel migration for the newer S1-S4/reversal
  // workflows must be additive, not global -- confirm these six legacy workflows kept their own
  // "historical default" (C0BFE6KAN8J) unchanged as a side effect of the SEND_GUARD_JS edit.
  // That premise is now WRONG: C0BFE6KAN8J is a dead channel for the bot credential -- confirmed
  // live 2026-08-20 via the S3 conflict-alert crash ("channel_not_found"), which happened in
  // DNC__UpsertLedger__v1, one of these exact six. The guard now checks the opposite: all six
  // must point at the same live, reachable channel everything else already uses.
  const files = ['DNC__UpsertLedger__v1.json',
    path.join('..', 'workflows', 'heyreach_reply_to_dnc_ledger', 'heyreach_reply_to_dnc_ledger.json'),
    path.join('..', 'workflows', 'dnc_expiry_job', 'dnc_expiry_job.json'),
    path.join('..', 'workflows', 'smartlead_observability_readonly', 'smartlead_observability_readonly.json'),
    path.join('..', 'workflows', 'dnc_check_service', 'dnc_check_service.json'),
    path.join('..', 'workflows', 'dnc_wf4_sheet_intake', 'dnc_wf4_sheet_intake.json')];
  for (const rel of files) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, rel), 'utf8'));
    const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
    const alertChannel = cfg.parameters.assignments.assignments.find((a) => a.name === 'alert_channel');
    assert.equal(alertChannel.value, 'C0B8GCVNR5W', `${rel}: must be retargeted off the dead channel`);
    const guard = cfg.parameters.assignments.assignments.find((a) => a.name === 'dev_channel_guard');
    assert.equal(guard, undefined, `${rel}: should not set dev_channel_guard`);
  }
});

t('no workflow anywhere still references the dead C0BFE6KAN8J channel (regression guard, 2026-08-20)', () => {
  // full sweep, not just the six known offenders -- any future CONFIG or node channelId literal
  // that reintroduces this value is exactly the crash-waiting class this fix exists to close.
  const workflowFiles = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name.endsWith('.json')) workflowFiles.push(p);
    }
  };
  walk(path.join(SUB, '..', 'workflows'));
  workflowFiles.push(path.join(SUB, 'DNC__NormalizeIdentity__v1.json'));
  workflowFiles.push(path.join(SUB, 'DNC__UpsertLedger__v1.json'));
  workflowFiles.push(path.join(SUB, 'DNC__CheckLedger__v1.json'));
  for (const f of workflowFiles) {
    const raw = fs.readFileSync(f, 'utf8');
    assert.ok(!raw.includes('C0BFE6KAN8J'), `${f}: still references the dead channel`);
  }
});

t('every DNC workflow has a real, resolved errorWorkflow (regression guard, 2026-08-11)', () => {
  // found live by the fix-owner session's audit: 6 workflows carried the literal unresolved
  // "REPLACE_CORE__ErrorHandler_ID" placeholder and 3 had no errorWorkflow at all -- all 9 were
  // inactive so nothing silently failed yet, but activation would have meant invisible failures.
  const files = [
    'DNC__NormalizeIdentity__v1.json', 'DNC__UpsertLedger__v1.json', 'DNC__CheckLedger__v1.json',
    path.join('..', 'workflows', 'heyreach_reply_to_dnc_ledger', 'heyreach_reply_to_dnc_ledger.json'),
    path.join('..', 'workflows', 'dnc_expiry_job', 'dnc_expiry_job.json'),
    path.join('..', 'workflows', 'smartlead_observability_readonly', 'smartlead_observability_readonly.json'),
    path.join('..', 'workflows', 'dnc_check_service', 'dnc_check_service.json'),
    path.join('..', 'workflows', 'dnc_wf4_sheet_intake', 'dnc_wf4_sheet_intake.json'),
    path.join('..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'),
  ];
  for (const rel of files) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, rel), 'utf8'));
    const ew = wf.settings && wf.settings.errorWorkflow;
    assert.ok(ew, `${rel}: missing errorWorkflow`);
    assert.ok(!String(ew).startsWith('REPLACE_'), `${rel}: unresolved errorWorkflow placeholder`);
    assert.equal(ew, 'BbrXPABgOaaTJjD6', `${rel}: expected the confirmed WF-ERR handler`);
  }
});

// "PD Get Leads By Person is paginated" (2026-08-11) REMOVED 2026-09-16 -- that whole node is
// gone (P1 label incident: it existed only to check has_open_lead for the label branch, which no
// longer exists). Nothing left to test.

t('dnc_projections_sweep: SL Mark Done applies the PROJECTION RULE (permanent on unsubscribe) (regression guard, 2026-08-12)', () => {
  // Nik's ruling 2026-08-12: a performed IRREVERSIBLE projection makes the row permanent.
  // Smartlead's unsubscribe is explicitly non-undoable via API, so a successful write must null
  // expires_at regardless of the row's own reason/TTL (covers the 38 reply_dnc-with-TTL rows in
  // the 623) and mark the smartlead projection as a distinguishable 'done:permanent' state.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const n = wf.nodes.find((x) => x.name === 'SL Mark Done');
  assert.equal(n.parameters.columns.value.expires_at, null, 'SL Mark Done must null expires_at');
  assert.ok(n.parameters.columns.value.projections_state.includes("smartlead: 'done:permanent'"),
    'expected the done:permanent compound status, not a bare done');
  // PD Mark Done must NOT get this treatment -- the person-field write is freely reversible,
  // unlike Smartlead's unsubscribe, so Nik's rule explicitly does not extend to it. (Was two nodes,
  // "(with lead)"/"(no lead)" -- collapsed to one "PD Mark Done" 2026-09-16 when the label branch
  // that made the distinction meaningful was removed.)
  const pdNode = wf.nodes.find((x) => x.name === 'PD Mark Done');
  assert.equal(pdNode.parameters.columns.value.expires_at, undefined,
    'PD Mark Done: Pipedrive writes are reversible, must not null expires_at');
});

t('dnc_projections_sweep: PD Limit Chunk bounds every execution to a chunk (OOM fix, 2026-08-12)', () => {
  // Incident: 3 concurrent live executions each holding the full ~2,264-row pending set (read
  // phase + write phase) crashed with "Workflow did not finish, possible out-of-memory issue".
  // Fix: cap every execution to pd_chunk_size (200-300 range, default 250) BEFORE the first heavy
  // per-item HTTP call, so read phase and write phase are both bounded regardless of concurrency.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const chunkNode = wf.nodes.find((x) => x.name === 'PD Limit Chunk');
  assert.ok(chunkNode, 'expected a PD Limit Chunk node');
  assert.ok(/chunkSize = \$\('CONFIG'\)\.first\(\)\.json\.pd_chunk_size/.test(chunkNode.parameters.jsCode),
    'chunk size must be read from CONFIG, not hardcoded');
  assert.ok(/rows\.slice\(0, chunkSize\)/.test(chunkNode.parameters.jsCode),
    'must actually slice the pending set down to the chunk size');

  const cfg = wf.nodes.find((x) => x.name === 'CONFIG');
  const assigns = cfg.parameters.assignments.assignments;
  const chunkCfg = assigns.find((a) => a.name === 'pd_chunk_size');
  assert.ok(chunkCfg, 'expected pd_chunk_size in CONFIG');
  assert.ok(chunkCfg.value >= 200 && chunkCfg.value <= 300,
    `pd_chunk_size ${chunkCfg.value} outside the owner-directed 200-300 range`);

  // wiring: PD Filter Pending -> PD Limit Chunk -> PD Aggregate (chunk gates the first heavy
  // per-item HTTP call, which runs regardless of FIRE_PIPEDRIVE -- dry-run mode must be bounded
  // too, not just the live-write branch). Simplified 2026-09-16: PD Limit Chunk now feeds
  // PD Aggregate directly -- the PD Get Leads By Person / PD Classify hop that used to sit
  // between them existed only to check has_open_lead for the (now removed) label branch.
  const filterOut = wf.connections['PD Filter Pending'].main[0].map((c) => c.node);
  assert.deepEqual(filterOut, ['PD Limit Chunk']);
  const chunkOut = wf.connections['PD Limit Chunk'].main[0].map((c) => c.node);
  assert.deepEqual(chunkOut, ['PD Aggregate']);
});

t('dnc_projections_sweep: PD Aggregate reports total-vs-chunk so partial fires are visible (regression guard, 2026-08-12)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const agg = wf.nodes.find((x) => x.name === 'PD Aggregate');
  assert.ok(agg.parameters.jsCode.includes('remaining_after_chunk'),
    'aggregate must report how many pending rows are left after this chunk');
  assert.ok(agg.parameters.jsCode.includes('chunk_processed'),
    'aggregate must report how many rows this specific execution actually processed');
});

t('dnc_projections_sweep: Slack digest format rules (Nik ruling, 2026-08-12)', () => {
  // Verdict on the chunk-1 digest: unreadable brick paragraph, HeyReach's static PARKED line
  // repeated every post, an internal doc filename leaking into Slack, and a hardcoded "dev,
  // dry-run" label on a run with FIRE_PIPEDRIVE=true. All formatting now lives in Combine
  // Summaries' JS (slack_text) -- the Slack node itself is just {{ $json.slack_text }}, so a
  // wording tweak never means hand-editing a giant conditional n8n expression again.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const slackNode = wf.nodes.find((x) => x.name === 'Dev Summary');
  assert.equal(slackNode.parameters.text, '={{ $json.slack_text }}',
    'Slack node must post the precomputed slack_text field, not an inline template');

  const combine = wf.nodes.find((x) => x.name === 'Combine Summaries');
  const js = combine.parameters.jsCode;

  // (a)/(b) multi-line with chunk N/M progress
  assert.ok(js.includes('lines.join'), 'must build a real multi-line message, not one string');
  assert.ok(/chunk \$\{chunkNumber\}\/\$\{totalChunks\}/.test(js), 'must show chunk N/M progress');

  // (c) HeyReach's static PARKED line must never appear in the intermediate-chunk branch
  const elseBranch = js.slice(js.indexOf('} else {'));
  assert.ok(!elseBranch.includes('HeyReach'), 'HeyReach must not appear on intermediate-chunk posts');
  assert.ok(js.includes('HeyReach'), 'HeyReach must still appear once, on the final chunk');

  // (d) no internal file references anywhere in anything that reaches slack_text
  assert.ok(!/lines\.push\(.*PROJECTIONS_PASS_PLAN/.test(js),
    'a build-doc filename must never be pushed into the Slack lines array');
  assert.ok(!/DNC \\\\u2192 Pipedrive.*PROJECTIONS_PASS_PLAN/.test(js));

  // (e) Smartlead line gated on a real changed-since-last-post check, not always shown
  assert.ok(js.includes("$getWorkflowStaticData('global')"), 'must persist the last posted snapshot');
  assert.ok(js.includes('slChanged'), 'Smartlead line must be conditional on a real change check');
  assert.ok(/if \(slChanged\) lines\.push\(slLine\)/.test(js));

  // (f) errors suffix always present
  assert.ok(js.includes('errLine'), 'must always include an errors suffix');

  // mode-label fix: the old hardcoded "(dev, dry-run)" claim must be gone -- it was false on a
  // live-write (FIRE_PIPEDRIVE=true) run.
  assert.ok(!js.includes('dry-run'), 'must not hardcode a dry-run claim regardless of FIRE_PIPEDRIVE');
});

t('dnc_projections_sweep: write-phase HTTP failures are caught, not silently dropped (2026-08-12, simplified 2026-09-16)', () => {
  // Incident: PD Write DNC Field (and, before 2026-09-16, two now-removed label-write nodes) all
  // default to n8n's onError:'continueErrorOutput' (confirmed on the live deployed nodes, not
  // something this generator explicitly sets that could just be removed) -- a persistently-failing
  // item routes to a SECOND output that was never wired to anything. Caught live: 2 Pipedrive
  // persons deleted (403 "Cannot update a deleted person") retried silently across 3 chunks,
  // execution status stayed "success" throughout, and the Slack digest claimed "0 errors" the
  // whole time. Fix: route the write node's error output into a classify+mark-failed path so the
  // row stops being retried forever and the failure is actually counted.
  //
  // Simplified 2026-09-16 (P1 label incident): PD Write DNC Field is now the ONLY write-phase HTTP
  // node in this workflow (the label branch is gone), so its error output feeds
  // PD Classify Write Error DIRECTLY -- no Merge needed for a single source, and no Merge means no
  // repeat of the exact "fires once per branch" class this session fixed elsewhere.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));

  const n = wf.nodes.find((x) => x.name === 'PD Write DNC Field');
  assert.equal(n.onError, 'continueErrorOutput', "PD Write DNC Field: expected n8n's actual deployed default");
  const out = wf.connections['PD Write DNC Field'].main;
  assert.equal(out.length, 2, 'PD Write DNC Field: must have both a success and an error output wired');
  assert.ok(out[1] && out[1].length > 0, 'PD Write DNC Field: error output (index 1) must be wired somewhere, not dead-ended');
  assert.equal(out[1][0].node, 'PD Classify Write Error', 'PD Write DNC Field: error output must feed the classify step directly');
  assert.ok(!wf.nodes.some((x) => x.type === 'n8n-nodes-base.merge'),
    'no Merge node should exist anywhere in dnc_projections_sweep -- a single error source needs no convergence');

  const classify = wf.nodes.find((x) => x.name === 'PD Classify Write Error');
  assert.ok(classify.parameters.jsCode.includes('deleted_person'),
    'must specifically recognize the deleted-person case seen live, not just a generic bucket');
  assert.ok(classify.parameters.jsCode.includes('failed:pipedrive_write_error'),
    'must have a generic fallback marker for any other write failure');

  const markError = wf.nodes.find((x) => x.name === 'PD Mark Write Error');
  assert.ok(markError.parameters.columns.value.projections_state.includes('error_marker'),
    'must persist the classified marker, not just log it -- otherwise the row keeps retrying forever');

  // PD Count Write Errors is a clean dead end (2026-09-15 fan-in fix removed the merge/barrier it
  // used to feed -- see the SL Get Candidates fan-out test above) -- Combine Summaries must read it
  // defensively instead (this branch has ZERO items, and therefore never RUNS, on the normal
  // error-free path).
  assert.deepEqual(((wf.connections['PD Count Write Errors'] || {}).main || [])[0] || [], []);
  const combine = wf.nodes.find((x) => x.name === 'Combine Summaries');
  assert.ok(/try\s*\{\s*errors = \$\('PD Count Write Errors'\)\.first\(\)\.json\.count/.test(combine.parameters.jsCode),
    'must read the real error count defensively (try/catch), not assume the node ran');
  assert.ok(!combine.parameters.jsCode.includes('const errors = 0;'),
    'must not still hardcode zero errors -- that claim was proven false by this exact incident');
});

t('P1 2026-09-16: dnc_projections_sweep NEVER touches Pipedrive lead labels, field write only', () => {
  // Incident: this workflow wrote the "DO NOT CONTACT" LEAD LABEL (id
  // 52a7c290-fc73-11f0-ad98-81d4703453f3) via a PD Patch Lead Labels node, which was never the
  // sanctioned mechanism -- the field-only ruling (write ONLY the person-level DNC Status custom
  // field, key 9c018b7406ebc481b9c108a487f76c4d09f91c9b, never touch label_ids) predates this
  // workflow but the label branch was built anyway and went live at scale, mislabeling 600 real
  // leads since 2026-09-08 -- 425 of them positive repliers, silently withheld from Melisa's
  // handover automation (which fires on label "3. Responded" only when "DO NOT CONTACT" is
  // absent). Full incident: task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md.
  //
  // This is the durable guard against it ever coming back: the ENTIRE workflow file, not just one
  // node, must never reference label_ids or the "DO NOT CONTACT" label id, and must never call the
  // Pipedrive leads endpoint at all (only the v2 persons endpoint, for the field write).
  const raw = fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8');
  assert.ok(!raw.includes('label_ids'), 'dnc_projections_sweep must never reference label_ids anywhere');
  assert.ok(!raw.includes('52a7c290-fc73-11f0-ad98-81d4703453f3'),
    'dnc_projections_sweep must never reference the DO NOT CONTACT label id');
  assert.ok(!raw.includes('pd_label_dnc'), 'the pd_label_dnc CONFIG field must be gone entirely');

  const wf = JSON.parse(raw);
  for (const n of wf.nodes) {
    if (n.type !== 'n8n-nodes-base.httpRequest') continue;
    const url = (n.parameters && n.parameters.url) || '';
    if (url.includes('api.pipedrive.com')) {
      assert.ok(url.includes('/api/v2/persons/'),
        `${n.name}: the only Pipedrive HTTP call this workflow makes must be the v2 persons field write, found: ${url}`);
      assert.ok(!url.includes('/v1/leads'),
        `${n.name}: must never call the Pipedrive leads endpoint`);
    }
  }
  // node-name-level guard too, in case a future edit reintroduces a lead-touching node under any
  // name -- catches the class, not just this literal incident's node names. "smartlead" is a
  // legitimate, unrelated channel name in this same workflow (FIRE_SMARTLEAD?, SL Get Candidates,
  // etc.) and must not trip the "lead" pattern -- strip it out before testing.
  const forbiddenNamePatterns = [/label/i, /lead/i];
  for (const n of wf.nodes) {
    const nameSansSmartlead = n.name.replace(/smartlead/gi, '');
    for (const pat of forbiddenNamePatterns) {
      assert.ok(!pat.test(nameSansSmartlead), `${n.name}: node name suggests a reintroduced lead/label touch -- verify and rename if legitimate`);
    }
  }
});

t('reason_v1: sales_personal_outreach added correctly (S3, 2026-08-12)', () => {
  // per PHASE1_SCENARIOS_SPEC_2026-08-11.md's proposal: ranks below reply_dnc, above
  // manual_offboard_eligible; maps to entry_type 'manual', deliberately NOT 'employee_connection'
  // (that tier's isOffboardRemovable semantics are an unrelated concept).
  assert.equal(reasonEntryType('sales_personal_outreach'), 'manual');
  assert.equal(isOffboardRemovable('sales_personal_outreach'), false);
  assert.equal(reasonStrongest('reply_dnc', 'sales_personal_outreach'), 'reply_dnc');
  assert.equal(reasonStrongest('sales_personal_outreach', 'reply_dnc'), 'reply_dnc');
  assert.equal(reasonStrongest('sales_personal_outreach', 'manual_offboard_eligible'), 'sales_personal_outreach');
  assert.equal(reasonStrongest('manual_offboard_eligible', 'sales_personal_outreach'), 'sales_personal_outreach');
});

t('reason_v1: event_contacted added correctly (S4, 2026-08-14)', () => {
  // per PHASE1_SCENARIOS_SPEC_2026-08-11.md's proposal: weakest signal of the four scenarios --
  // "we touched them," not that they responded -- ranks just above manual_sheet, maps to
  // entry_type 'manual' (same reasoning as sales_personal_outreach: not employee_connection,
  // an unrelated concept).
  assert.equal(reasonEntryType('event_contacted'), 'manual');
  assert.equal(isOffboardRemovable('event_contacted'), false);
  assert.equal(reasonStrongest('manual_offboard_eligible', 'event_contacted'), 'manual_offboard_eligible');
  assert.equal(reasonStrongest('event_contacted', 'manual_offboard_eligible'), 'manual_offboard_eligible');
  assert.equal(reasonStrongest('event_contacted', 'manual_sheet'), 'event_contacted');
  assert.equal(reasonStrongest('manual_sheet', 'event_contacted'), 'event_contacted');
});

t('S3: Surfe recon fixtures are discriminating, not universal (statics per Nik: f96f4cf0 positive, one WF-1 lead negative)', () => {
  const fixtures = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'fixtures', 's3_surfe_recon.json'), 'utf8'));
  const isSurfe = (lead) => lead.channel_id === 'Surfe';

  assert.equal(fixtures.surfe_positive_lead.id, 'f96f4cf0-967f-11f1-9312-db82f8cd0680');
  assert.ok(isSurfe(fixtures.surfe_positive_lead), 'the known Surfe fixture must match on channel_id');
  assert.equal(fixtures.surfe_positive_lead.origin, 'Marketplace',
    'origin is the corroborating assert, not the match key, but must still be present on the positive');

  assert.ok(!isSurfe(fixtures.wf1_negative_lead), 'a WF-1/campaign-created lead must NOT match');
  assert.equal(fixtures.wf1_negative_lead.origin, 'API', 'confirms the negative is a genuinely different creation path');

  // the marker lives on the LEAD, never the person -- this is the corrected finding that changed
  // Signal B's design from a person-field read to a person-scoped lead lookup.
  const positivePersonKeys = Object.keys(fixtures.surfe_positive_person).map((k) => k.toLowerCase());
  assert.ok(!positivePersonKeys.some((k) => k.includes('channel') || k.includes('origin') || k.includes('marketplace')),
    'the person object must carry no origin/channel/marketplace field -- if this ever fails, Signal B could move back to a direct person-field read');
});

t('dnc_s3_creation_watcher: union semantics, FIRE_S3 default false, ops channel (2026-08-12)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const get = (k) => cfg.parameters.assignments.assignments.find((a) => a.name === k).value;
  assert.equal(get('FIRE_S3'), false, 'must default false -- flipping is a live one-off patch, never baked in');
  assert.equal(get('alert_channel'), 'C0B8GCVNR5W');
  assert.equal(get('dev_channel_guard'), 'C0B8GCVNR5W');
  assert.deepEqual(JSON.parse(get('sales_user_ids')),
    [17703023, 24721201, 16029123, 25733113, 24902545, 25151686, 25035678, 16340280],
    'roster widened 2026-08-19: old 5 + Rune/Slava/Melisa, Jim Ash retained (GetSales phase 2)');
  assert.equal(get('automation_creator_id'), 25112064);

  const classify = wf.nodes.find((n) => n.name === 'S3 Classify');
  const js = classify.parameters.jsCode;
  assert.ok(js.includes("lead.channel_id === 'Surfe'"), 'Signal B match key must be channel_id, not origin');
  assert.ok(/creatorMatch\s*&&\s*surfeMatch.*'both'/.test(js), "must produce 'both' when both signals fire on the same lead");
  assert.ok(js.includes('creatorMatch || '.trim()) || /creatorMatch.*surfeMatch/.test(js),
    'must be a union (OR), not an intersection, of the two signals');
  assert.ok(/creator_id\s*===\s*automationId\s*&&\s*lead\.origin\s*===\s*'API'/.test(js),
    'automation exclusion must be narrow: id AND origin===API, never the id alone');

  // regression guard, 2026-08-20: http_pipedrive() (no pagination) returns the whole Pipedrive
  // envelope {success, data, additional_data} as ONE item, never split per-lead. Reading
  // $input.all().map(i => i.json) built a "leads" array of exactly one fake lead (the envelope,
  // every field undefined) -- every live poll silently classified 0 matches regardless of what
  // was actually in Pipedrive. Confirmed live: a poll with 10 real channel_id==='Surfe' leads in
  // the envelope's own .data still reported count:0 before this fix. Must unwrap .data first.
  assert.ok(!js.includes('$input.all().map(i => i.json)'),
    'must not treat the raw HTTP envelope as if it were already split into per-lead items');
  assert.ok(/\$input\.first\(\)\.json\.data/.test(js),
    'must unwrap the envelope\'s .data array before classifying leads');

  // union means the aggregate gate is count>0, not creatorMatch>0 XOR surfeMatch>0 separately
  const gate = wf.nodes.find((n) => n.name === 'S3 Any Matches?');
  assert.ok(JSON.stringify(gate.parameters).includes('$json.count > 0'));

  const upsertCall = wf.nodes.find((n) => n.name === 'S3 Call UpsertLedger');
  assert.ok(upsertCall, 'must call the canonical UpsertLedger subworkflow, not a raw dataTable write');
});

t('S3 predicate fix: owner-in-roster alone must NEVER admit a non-roster-created lead (2026-08-20)', () => {
  // found live (Melisa's report): website-form/Memurai leads entered the registry because the
  // OLD predicate matched on creator_id OR owner_id -- any lead later ASSIGNED to a roster member
  // as owner got swept in regardless of who actually created it. Nik's ruling was always
  // "created by a sales-team user," not "currently owned by one." Actually EXECUTES the extracted
  // classify logic against synthetic leads, not just a pattern check -- this is exactly the class
  // of bug a structural assertion alone would have missed (the old code still read "creatorMatch",
  // it just computed it wrong).
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));
  const classify = wf.nodes.find((n) => n.name === 'S3 Classify').parameters.jsCode;
  const ROSTER = [17703023, 24721201, 16029123, 25733113, 24902545, 25151686, 25035678, 16340280];
  const NAMES = { 25733113: 'Noah Keimach' };

  const runClassify = (leads, cfgOverrides) => {
    const cfg = Object.assign({
      sales_user_ids: JSON.stringify(ROSTER), user_names: JSON.stringify(NAMES),
      automation_creator_id: 25112064, webform_legacy_creator_id: 13015123,
    }, cfgOverrides || {});
    const mock$ = (name) => { if (name === 'CONFIG') return { first: () => ({ json: cfg }) };
      throw new Error('unexpected $() reference: ' + name); };
    // rename target, not "leads" -- the extracted code itself does `const leads = ...`, so
    // passing a same-named parameter would collide with that declaration.
    const body = classify.replace("$input.first().json.data || []", "inputLeads");
    const fn = new Function('inputLeads', '$', body);
    return fn(leads, mock$)[0].json;
  };

  // STATIC (Nik's spec, point 4): webform-created lead, later assigned to a roster member as
  // owner -- must NOT be captured. This is the exact leak shape reported.
  const webformSalesOwned = [{ id: 'L1', creator_id: 13015123, owner_id: 25733113,
    origin: 'API', channel_id: null, title: 'some webform lead', person_id: 'P1' }];
  const r1 = runClassify(webformSalesOwned);
  assert.equal(r1.count, 0, 'webform-created + sales-owned must NOT be captured');

  // control: the SAME lead, but genuinely created by the roster member -- must be captured
  // (proves the fix didn't just break matching entirely).
  const genuineSalesCreated = [{ id: 'L2', creator_id: 25733113, owner_id: 25733113,
    origin: 'Marketplace', channel_id: null, title: 'a real one', person_id: 'P2' }];
  const r2 = runClassify(genuineSalesCreated);
  assert.equal(r2.count, 1, 'genuinely creator=roster-member leads must still be captured');
  assert.equal(r2.matches[0].source_signal, 'creator');

  // Memurai exclusion: even a roster-CREATED lead must be excluded if it's Memurai's pipeline.
  const memuraiChatbot = [{ id: 'L3', creator_id: 25733113, owner_id: 25733113,
    origin: 'Chatbot', channel_id: 'Memurai Chatbot', title: '[Memurai Chatbot] Someone', person_id: 'P3' }];
  const r3 = runClassify(memuraiChatbot);
  assert.equal(r3.count, 0, 'Memurai pipeline must be excluded even when creator IS a roster member');

  const memuraiByTitleOnly = [{ id: 'L4', creator_id: 25733113, owner_id: 25733113,
    origin: 'Marketplace', channel_id: null, title: 'Memurai Renewal Chat', person_id: 'P4' }];
  const r4 = runClassify(memuraiByTitleOnly);
  assert.equal(r4.count, 0, 'Memurai exclusion must also catch title-only signals, not just channel_id');

  // legacy webform creator excluded outright, regardless of owner or origin casing/shape.
  const webformSurfaceMatch = [{ id: 'L5', creator_id: 13015123, owner_id: 16340280,
    origin: 'Marketplace', channel_id: 'Surfe', title: 'looks like a real one', person_id: 'P5' }];
  const r5 = runClassify(webformSurfaceMatch);
  assert.equal(r5.count, 0, 'the legacy webform creator must be excluded even when channel_id looks like a genuine Surfe match');

  // Surfe-only match (creator not in roster, not the webform token either) must still work --
  // the fix must not have collateral-damaged the surfe signal.
  const genuineSurfeOnly = [{ id: 'L6', creator_id: 99999999, owner_id: 99999999,
    origin: 'Marketplace', channel_id: 'Surfe', title: 'surfe person', person_id: 'P6' }];
  const r6 = runClassify(genuineSurfeOnly);
  assert.equal(r6.count, 1, 'a genuine Surfe-sourced lead from a non-roster, non-webform creator must still match');
  assert.equal(r6.matches[0].source_signal, 'surfe');
});

t('S3: person LinkedIn extraction reads the top-level field, not a nested custom_fields object (2026-08-20)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));
  const build = wf.nodes.find((n) => n.name === 'S3 Build Upsert Input');
  const js = build.parameters.jsCode;
  // BUG: v1 GET /persons/{id} puts custom fields at the TOP LEVEL of the person object -- there
  // is no nested person.custom_fields sub-object on this endpoint at all. Reading
  // person.custom_fields[key] was always undefined, so the LinkedIn URL was silently dropped for
  // every live person regardless of what Pipedrive actually had (confirmed live against Emily
  // Philander, Person-b0fb1597, Vibhooti Dev -- all three have a real LinkedIn URL that this bug
  // hid, misclassifying them as "no identity" every poll).
  assert.ok(!/person\.custom_fields\s*&&/.test(js),
    'must not gate the LinkedIn read on a nested custom_fields object that this endpoint never returns');
  assert.ok(/const li = person\[/.test(js), 'must read the LinkedIn field directly off the person object');
});

t('S3: loop-spam fix -- unchanged estate across two consecutive polls produces zero new matches (2026-08-20)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));
  const filterNode = wf.nodes.find((n) => n.name === 'S3 Filter New');
  assert.ok(filterNode, 'S3 Filter New must exist between S3 Classify and S3 Track Poll Stats');
  assert.deepEqual(wf.connections['S3 Classify'].main[0][0].node, 'S3 Filter New');
  assert.deepEqual(wf.connections['S3 Filter New'].main[0][0].node, 'S3 Track Poll Stats');

  // Actually EXECUTE the extracted jsCode against two simulated consecutive polls -- a pattern
  // check alone can't catch a logic bug in the dedup itself, and this is genuine stateful logic
  // (unlike most of this suite's static shape assertions).
  const runFilterNew = (jsonInput, staticDataStore) => {
    const fn = new Function('$json', '$getWorkflowStaticData', filterNode.parameters.jsCode);
    return fn(jsonInput, () => staticDataStore);
  };
  const rawMatches = {
    matches: [
      { lead_id: 'lead-a', person_id: 1, source_signal: 'surfe', source_ref: 'Surfe' },
      { lead_id: 'lead-b', person_id: 2, source_signal: 'creator', source_ref: 'Toby' },
    ],
    count: 2, by_signal: { creator: 1, surfe: 1, both: 0 },
  };
  const sd = {};
  const poll1 = runFilterNew(rawMatches, sd)[0].json;
  assert.equal(poll1.count, 2, 'first poll: both leads are new');
  assert.deepEqual(poll1.matches.map((m) => m.lead_id), ['lead-a', 'lead-b']);

  // Static test: same raw snapshot again (nothing changed in Pipedrive) -> zero new matches.
  const poll2 = runFilterNew(rawMatches, sd)[0].json;
  assert.equal(poll2.count, 0, 'second poll over an UNCHANGED estate must produce zero new matches');
  assert.deepEqual(poll2.matches, []);

  // A third poll where ONE new lead joins the same unchanged pair -> exactly one new match.
  const rawMatches2 = {
    matches: rawMatches.matches.concat([{ lead_id: 'lead-c', person_id: 3, source_signal: 'both', source_ref: 'Noah' }]),
    count: 3, by_signal: { creator: 1, surfe: 1, both: 1 },
  };
  const poll3 = runFilterNew(rawMatches2, sd)[0].json;
  assert.equal(poll3.count, 1, 'only the genuinely new lead should surface, not the two already-seen ones');
  assert.equal(poll3.matches[0].lead_id, 'lead-c');

  // S3 Combine must read the FILTERED aggregate, not the raw per-snapshot one, or the burst
  // threshold and alert text would react to re-detections instead of new activity.
  const combine = wf.nodes.find((n) => n.name === 'S3 Combine');
  assert.ok(combine.parameters.jsCode.includes("$('S3 Filter New').first().json"),
    'S3 Combine must read S3 Filter New\'s output, not S3 Classify\'s raw snapshot');
  assert.ok(!combine.parameters.jsCode.includes("$('S3 Classify').first().json"),
    'must not still read the unfiltered snapshot for alerting');
});

t('dnc_s3_surfe_backfill: chunked, guarded, resumable via caller-supplied cursor, not staticData (2026-08-12)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_surfe_backfill', 'dnc_s3_surfe_backfill.json'), 'utf8'));
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const get = (k) => cfg.parameters.assignments.assignments.find((a) => a.name === k).value;
  assert.equal(get('FIRE_S3_BACKFILL'), false);
  assert.equal(get('leads_per_page'), 500);
  assert.equal(get('pages_per_chunk'), 3);
  // the cursor is read from the incoming webhook body, not a hardcoded literal -- this is what
  // makes it externally resumable across chunk-fires without a new Data Table.
  assert.ok(String(get('start_offset')).includes('$json.body.start_offset'));

  const getPage = wf.nodes.find((n) => n.name === 'S3B Get Leads Page');
  assert.equal(getPage.parameters.options.pagination.pagination.maxRequests, 3,
    'must bound pages per execution -- unbounded pagination over a multi-thousand-lead org is exactly today\'s OOM pattern');

  const filterJs = wf.nodes.find((n) => n.name === 'S3B Filter Surfe').parameters.jsCode;
  assert.ok(filterJs.includes('flatMap'),
    'paginated output is one item PER PAGE (each with its own .data array) -- must flatten before filtering, not treat pages as leads');

  const combineJs = wf.nodes.find((n) => n.name === 'S3B Combine').parameters.jsCode;
  assert.ok(combineJs.includes('pages[pages.length - 1]'),
    'must read the LAST page\'s pagination cursor, not the first -- the first page\'s next_start is stale after chunk 1 fetches more pages');

  // responseMode: 'lastNode', NOT 'responseNode' -- a dedicated Respond node reproducibly
  // triggered n8n's own "No Respond to Webhook node found in the workflow" error live on this
  // specific workflow despite a byte-for-byte-correct, fully-reachable connections graph (checked
  // three ways: isolated minimal probes of every node type involved, a full delete+recreate, a
  // fresh never-used path/webhookId). Root cause not conclusively identified; not worth chasing
  // further since this workflow never needed the HTTP response body anyway -- the cursor is read
  // from execution data by the driver script instead, same technique proven for every
  // projections-sweep chunk fire today.
  const webhookNode = wf.nodes.find((n) => n.name === 'Webhook');
  assert.equal(webhookNode.parameters.responseMode, 'lastNode');
  assert.ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.respondToWebhook'),
    'must have no respondToWebhook node -- lastNode mode needs none, and one previously broke this workflow live');
  const combineJs2 = wf.nodes.find((n) => n.name === 'S3B Combine').parameters.jsCode;
  assert.ok(combineJs2.includes('next_offset'),
    'the cursor must still be computed and returned in S3B Combine\'s own output for the driver script to read via execution data');
});

t('S3: person LinkedIn/email extraction matches the verified live field shapes (2026-08-12, corrected 2026-08-20)', () => {
  // verified live against the Surfe fixture person (85760): email is an ARRAY of
  // {label,value,primary}, never a bare string. LinkedIn is custom field 66f0af69..., but -- fixed
  // 2026-08-20 -- as a TOP-LEVEL key on the person object from v1 GET /persons/{id}, never nested
  // under a person.custom_fields sub-object (that sub-object doesn't exist on this endpoint at
  // all; the original assertion here actually encoded the bug, not the fix). Getting either wrong
  // is exactly the "check that cannot fire" class this whole build was warned against.
  for (const [wfDir, wfFile] of [
    ['dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'],
    ['dnc_s3_surfe_backfill', 'dnc_s3_surfe_backfill.json'],
  ]) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', wfDir, wfFile), 'utf8'));
    const buildNode = wf.nodes.find((n) => /Build Upsert Input/.test(n.name));
    const js = buildNode.parameters.jsCode;
    assert.ok(js.includes("const li = person['66f0af69bec838dc3f90bb3f16c7d6087d8dbb20']"),
      `${wfFile}: must read LinkedIn directly off the person object, not a nested custom_fields object`);
    assert.ok(!/person\.custom_fields\s*&&/.test(js),
      `${wfFile}: must not gate the read on a custom_fields sub-object this endpoint never returns`);
    assert.ok(js.includes('emailArr.find(e => e.primary)'),
      `${wfFile}: must handle email as an array, not a bare string`);
    assert.ok(js.includes('$json.data'), `${wfFile}: must unwrap the {success,data} envelope`);
  }
});

t('S3: no dead-end nodes on the reporting/write path (regression guard, 2026-08-12)', () => {
  // found live, TWICE, same bug class: "...Build Upsert Input" and separately "...Combine" each
  // had NO outgoing connection in one or both workflows. Execution silently stopped at whichever
  // dead end it hit first every single time -- for Build Upsert Input this meant never reaching
  // the FIRE gate/UpsertLedger/report at all; for Combine specifically it meant slack_text got
  // computed and happened to surface in the lastNode HTTP response (masking the gap), while the
  // actual Slack post never fired. The first instance triggered a long, expensive debugging detour
  // (three isolated node-type probes, a full delete+recreate, a fresh path/webhookId) chasing what
  // looked like an n8n webhook-response bug before the real cause turned out to be this simple.
  // General guard: neither of these specific hop points may be a dead end in either S3 workflow.
  for (const [wfDir, buildNodeName, identityGateName, fireGateName, combineNodeName, modeGateName] of [
    ['dnc_s3_creation_watcher', 'S3 Build Upsert Input', 'S3 Has Identity?', 'FIRE_S3?', 'S3 Combine', 'S3 MODE == dev?'],
    ['dnc_s3_surfe_backfill', 'S3B Build Upsert Input', 'S3B Has Identity?', 'FIRE_S3_BACKFILL?', 'S3B Combine', 'S3B MODE == dev?'],
  ]) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', wfDir, `${wfDir}.json`), 'utf8'));
    const buildOut = wf.connections[buildNodeName];
    assert.ok(buildOut && buildOut.main && buildOut.main[0] && buildOut.main[0].length > 0,
      `${wfDir}: ${buildNodeName} must not be a dead end`);
    // as of 2026-08-12 (Nik's skip+log GO ruling), Build Upsert Input feeds the identity gate
    // FIRST, not the FIRE gate directly -- an identity-less row must never reach UpsertLedger.
    assert.equal(buildOut.main[0][0].node, identityGateName,
      `${wfDir}: ${buildNodeName} must feed the identity gate, not skip straight to FIRE`);

    const combineOut = wf.connections[combineNodeName];
    assert.ok(combineOut && combineOut.main && combineOut.main[0] && combineOut.main[0].length > 0,
      `${wfDir}: ${combineNodeName} must not be a dead end`);
    assert.equal(combineOut.main[0][0].node, modeGateName,
      `${wfDir}: ${combineNodeName} must feed the MODE gate so the Slack post actually fires`);
  }
});

t('dnc_s3_creation_watcher: persons write path went LIVE 2026-09-15 (Nik\'s follow-up GO), gated by its own flag, no fan-in anywhere', () => {
  // Shipped report-only first (owner-only membership wasn't sufficient evidence per Nik's
  // 2026-08-19/08-20 ruling). SUPERSEDED same day: "roster-owned means protected... no source
  // check -- report-only becomes live." Now calls UpsertLedger directly -- gated by its OWN flag
  // (FIRE_S3_PERSONS), deliberately separate from the leads path's already-permanent FIRE_S3, so
  // this brand-new code gets its own one supervised verify window before firing for real.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));
  const reportNodeNames = ['S3 Get Recent Persons', 'S3 Classify Persons', 'S3 Filter New Persons',
    'S3 Persons Any New?', 'S3 Persons Report', 'S3 Persons MODE == dev?', 'S3 Persons Send Guard',
    'S3 Persons Dev Summary'];
  const writeNodeNames = ['S3 Persons Split Matches', 'S3 Persons Build Upsert Input',
    'S3 Persons Has Identity?', 'S3 Persons Log No Identity', 'FIRE_S3_PERSONS?',
    'S3 Persons Call UpsertLedger'];
  const personsNodeNames = [...reportNodeNames, ...writeNodeNames];
  for (const n of personsNodeNames) {
    assert.ok(wf.nodes.some((x) => x.name === n), `expected node ${n} to exist`);
  }
  const execNode = wf.nodes.find((n) => n.name === 'S3 Persons Call UpsertLedger');
  assert.equal(execNode.type, 'n8n-nodes-base.executeWorkflow');
  assert.equal(execNode.parameters.mode, 'each');

  // FIRE_S3_PERSONS is its own CONFIG field, not a reuse of FIRE_S3.
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const cfgNames = cfg.parameters.assignments.assignments.map((a) => a.name);
  assert.ok(cfgNames.includes('FIRE_S3_PERSONS'));
  assert.ok(cfgNames.includes('FIRE_S3'));

  // structural: CONFIG fans OUT to both the leads path and the persons path (plain fan-out, not a
  // second source feeding an existing node).
  const targets = (src) => ((wf.connections[src] && wf.connections[src].main[0]) || []).map((c) => c.node);
  assert.deepEqual(targets('CONFIG').sort(), ['S3 Get Recent Leads', 'S3 Get Recent Persons'].sort());

  // "S3 Persons Any New?" true branch fans OUT to both the report AND the new write path -- same
  // proven shape used throughout this session (PD Aggregate, S2 Aggregate Candidates), not a
  // Merge convergence.
  assert.deepEqual(targets('S3 Persons Any New?').sort(),
    ['S3 Persons Report', 'S3 Persons Split Matches'].sort());
  assert.deepEqual(wf.connections['S3 Persons Any New?'].main[1], []);
  assert.deepEqual(wf.connections['S3 Persons MODE == dev?'].main[1], []);

  // write path: identity-less matches skip+log instead of reaching UpsertLedger, matching the
  // leads path's own established Nik GO ruling; FIRE gate's false branch and UpsertLedger's own
  // output are both clean dead ends -- no Merge node anywhere, no converged per-item outcome.
  assert.deepEqual(targets('S3 Persons Has Identity?'), ['FIRE_S3_PERSONS?']);
  assert.deepEqual(wf.connections['S3 Persons Has Identity?'].main[1].map((c) => c.node),
    ['S3 Persons Log No Identity']);
  assert.deepEqual(targets('FIRE_S3_PERSONS?'), ['S3 Persons Call UpsertLedger']);
  assert.deepEqual(wf.connections['FIRE_S3_PERSONS?'].main[1], []);
  assert.deepEqual(targets('S3 Persons Call UpsertLedger'), []);
  assert.deepEqual(targets('S3 Persons Log No Identity'), []);
  // the persons path itself introduces no Merge node (the pre-existing leads-path "S3 Merge
  // Identity Paths" is a separate, already-flagged, out-of-scope residual risk -- not this test's
  // job to re-litigate).
  for (const n of personsNodeNames) {
    const node = wf.nodes.find((x) => x.name === n);
    assert.notEqual(node.type, 'n8n-nodes-base.merge', `${n} must not be a Merge node`);
  }

  // the report reads matches/no-identity via named references (from the single-source aggregate
  // and the write path's own log node), never from a converged stream -- and does it defensively
  // (the no-identity node may not have run at all this poll).
  const report = wf.nodes.find((n) => n.name === 'S3 Persons Report');
  assert.ok(/try\s*\{\s*noIdentity = \$\('S3 Persons Log No Identity'\)\.all\(\)/.test(report.parameters.jsCode));

  // no separate per-item Get Person call on the persons path -- the list fetch already carries
  // full identity, unlike the leads path which only has person_id and needs one.
  assert.ok(!wf.nodes.some((n) => n.name === 'S3 Persons Get Person'));
  const buildInput = wf.nodes.find((n) => n.name === 'S3 Persons Build Upsert Input');
  assert.ok(buildInput.parameters.jsCode.includes("reason: 'sales_personal_outreach'"));
});

t('dnc_s3_creation_watcher: persons classifier reads owner_id as a nested object, not a bare id (2026-09-15)', () => {
  // Confirmed live 2026-09-15 against real records (pid 86650, 86158): person.owner_id is
  // {id, name, email, ..., value}, unlike lead.owner_id which is a bare number. Using it as a bare
  // id anywhere here would silently match nothing, ever (an object is never == a numeric roster id).
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));
  const node = wf.nodes.find((n) => n.name === 'S3 Classify Persons');
  assert.ok(/owner_id\.value/.test(node.parameters.jsCode));
  assert.ok(/typeof p\.owner_id === 'object'/.test(node.parameters.jsCode));
});

t('S3: identity-less matches skip+log instead of reaching UpsertLedger (Nik GO ruling, 2026-08-12)', () => {
  // found live in the 27-candidate review: 3 of 27 (Pickering, Dev, Capps) have neither email nor
  // LinkedIn. UpsertLedger would compute a null identity_key for these and the row would vanish
  // silently -- must be skipped explicitly and named in the report so a human can manually enrich
  // them, never routed to UpsertLedger at all. The identity check varies per split-item within one
  // execution (same as the with-lead/no-lead split), so it needs a real Merge before the barrier,
  // not a naive second edge -- verified the same way that regression class was caught before.
  for (const [wfDir, identityGateName, fireGateName, logNodeName, mergeNodeName, barrierName, combineNodeName] of [
    ['dnc_s3_creation_watcher', 'S3 Has Identity?', 'FIRE_S3?', 'S3 Log No Identity', 'S3 Merge Identity Paths', 'S3 Write Barrier', 'S3 Combine'],
    ['dnc_s3_surfe_backfill', 'S3B Has Identity?', 'FIRE_S3_BACKFILL?', 'S3B Log No Identity', 'S3B Merge Identity Paths', 'S3B Write Barrier', 'S3B Combine'],
  ]) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', wfDir, `${wfDir}.json`), 'utf8'));
    const gate = wf.nodes.find((n) => n.name === identityGateName);
    assert.ok(gate, `${wfDir}: expected an identity gate`);
    assert.ok(JSON.stringify(gate.parameters).includes('linkedin_url || $json.email'),
      `${wfDir}: gate must check both identifiers`);

    const gateOut = wf.connections[identityGateName].main;
    assert.equal(gateOut[0][0].node, fireGateName, `${wfDir}: has-identity branch must reach the FIRE gate`);
    assert.equal(gateOut[1][0].node, logNodeName, `${wfDir}: no-identity branch must reach the log node`);

    const mergeNode = wf.nodes.find((n) => n.name === mergeNodeName);
    assert.ok(mergeNode, `${wfDir}: expected an explicit Merge combining both identity outcomes`);
    assert.equal(mergeNode.type, 'n8n-nodes-base.merge');
    assert.equal(mergeNode.parameters.mode, 'append');
    assert.equal(mergeNode.parameters.numberInputs, 2);

    // the barrier (has-identity path) and the log node (no-identity path) must land on DIFFERENT
    // input indices of the merge -- same regression shape as the with-lead/no-lead merge bug.
    const barrierIdx = wf.connections[barrierName].main[0][0].index;
    const logIdx = wf.connections[logNodeName].main[0][0].index;
    assert.notEqual(barrierIdx, logIdx, `${wfDir}: barrier and log-node must not collide on the same merge input`);
    assert.equal(wf.connections[barrierName].main[0][0].node, mergeNodeName);
    assert.equal(wf.connections[logNodeName].main[0][0].node, mergeNodeName);
    assert.equal(wf.connections[mergeNodeName].main[0][0].node, combineNodeName,
      `${wfDir}: the merge must feed Combine, not re-introduce a dead end`);

    const combineJs = wf.nodes.find((n) => n.name === combineNodeName).parameters.jsCode;
    assert.ok(combineJs.includes("skip_reason === 'no_identity'"),
      `${wfDir}: Combine must tally the skipped-no-identity rows`);
    assert.ok(combineJs.includes('manual enrich'),
      `${wfDir}: the report must name the skipped rows for manual enrichment, not just count them`);
  }
});

t('routine-vs-final Slack channel routing (Nik ruling, 2026-08-12): telemetry for progress, ops for results', () => {
  // dry-runs/chunk progress -> #gtm-telemetry (C0BQM1X9ZUY); ops (C0B8GCVNR5W) gets final results
  // and questions only. Every other workflow's single-channel alert_channel/dev_channel_guard
  // behavior must stay byte-identical (checked by the existing "other DNC workflows still
  // validate against the historical default channel" test -- not duplicated here).
  const OPS = 'C0B8GCVNR5W', TELEMETRY = 'C0BQM1X9ZUY';

  for (const [wfDir, isAlwaysRoutine, combineNodeName] of [
    ['dnc_projections_sweep', false, 'Combine Summaries'],
    ['dnc_s3_creation_watcher', true, 'S3 Combine'],
    ['dnc_s3_surfe_backfill', false, 'S3B Combine'],
  ]) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', wfDir, `${wfDir}.json`), 'utf8'));
    const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
    const get = (k) => cfg.parameters.assignments.assignments.find((a) => a.name === k).value;
    assert.equal(get('alert_channel'), OPS, `${wfDir}: alert_channel must stay the ops channel`);
    assert.equal(get('telemetry_channel'), TELEMETRY, `${wfDir}: telemetry_channel must be set`);
    assert.deepEqual(JSON.parse(get('dev_channel_guard_list')).sort(), [OPS, TELEMETRY].sort(),
      `${wfDir}: guard must allow BOTH channels, not just the historical single one`);

    const slackNode = wf.nodes.find((n) => n.type === 'n8n-nodes-base.slack');
    assert.equal(slackNode.parameters.channelId.value, '={{ $json.target_channel }}',
      `${wfDir}: Slack node must route dynamically per-post, not to a fixed CONFIG value`);

    const combineNode = wf.nodes.find((n) => n.name === combineNodeName);
    const js = combineNode.parameters.jsCode;
    assert.ok(js.includes('target_channel'), `${wfDir}: combine step must compute target_channel`);
    if (isAlwaysRoutine) {
      assert.ok(js.includes('cfg.telemetry_channel'),
        `${wfDir}: a recurring watcher with no 'final' concept must always route to telemetry`);
    } else {
      assert.ok(/\?\s*cfg\.alert_channel\s*:\s*cfg\.telemetry_channel/.test(js),
        `${wfDir}: must route intermediate chunks to telemetry, the final chunk to ops`);
    }
  }

  // SEND_GUARD_JS itself: must check $json.target_channel first (falling back to the historical
  // single-channel field), and validate against a LIST when dev_channel_guard_list is set.
  const anyWf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'), 'utf8'));
  const guardJs = anyWf.nodes.find((n) => n.name === 'Send Guard').parameters.jsCode;
  assert.ok(guardJs.includes('$json && $json.target_channel'));
  assert.ok(guardJs.includes('dev_channel_guard_list'));
  assert.ok(guardJs.includes('allowed.includes(ch)'));
});

t('every workflow: every connection reference resolves to a real node (regression guard, 2026-08-14)', () => {
  // found live: dnc_label_reversal shipped with a stale connections.update() call left over from
  // an earlier node-removal refactor ("R Limit Chunk" -> a since-deleted "R Split Chunk"), running
  // AFTER the corrected wiring and silently re-overwriting it. n8n's own pre-flight validation
  // caught it ("Cannot read properties of undefined (reading 'disabled')") only at fire time --
  // this check catches the exact same class of bug for free, statically, for every workflow, not
  // just the one that happened to get fired today.
  const allWorkflowFiles = [
    'DNC__NormalizeIdentity__v1.json', 'DNC__UpsertLedger__v1.json', 'DNC__CheckLedger__v1.json',
    path.join('..', 'workflows', 'heyreach_reply_to_dnc_ledger', 'heyreach_reply_to_dnc_ledger.json'),
    path.join('..', 'workflows', 'dnc_expiry_job', 'dnc_expiry_job.json'),
    path.join('..', 'workflows', 'smartlead_observability_readonly', 'smartlead_observability_readonly.json'),
    path.join('..', 'workflows', 'dnc_check_service', 'dnc_check_service.json'),
    path.join('..', 'workflows', 'dnc_wf4_sheet_intake', 'dnc_wf4_sheet_intake.json'),
    path.join('..', 'workflows', 'dnc_projections_sweep', 'dnc_projections_sweep.json'),
    path.join('..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'),
    path.join('..', 'workflows', 'dnc_s3_surfe_backfill', 'dnc_s3_surfe_backfill.json'),
    path.join('..', 'workflows', 'dnc_s4_event_populations', 'dnc_s4_event_populations.json'),
    path.join('..', 'workflows', 'dnc_label_reversal', 'dnc_label_reversal.json'),
    path.join('..', 'workflows', 'dnc_s2_meeting_to_dnc', 'dnc_s2_meeting_to_dnc.json'),
    path.join('..', 'workflows', 'dnc_s1_responded_to_dnc', 'dnc_s1_responded_to_dnc.json'),
    path.join('..', 'workflows', 'dnc_escalation_detector', 'dnc_escalation_detector.json'),
  ];
  for (const rel of allWorkflowFiles) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, rel), 'utf8'));
    const nodeNames = new Set(wf.nodes.map((n) => n.name));
    for (const [src, out] of Object.entries(wf.connections)) {
      assert.ok(nodeNames.has(src), `${rel}: connections source "${src}" is not a real node (stale reference?)`);
      for (const branch of out.main || []) {
        for (const edge of branch || []) {
          assert.ok(nodeNames.has(edge.node),
            `${rel}: ${src} -> "${edge.node}" is not a real node (stale reference?)`);
        }
      }
    }
  }
});

t('DNC__UpsertLedger__v1: reply_dnc requires reply_category (registry hygiene, 2026-08-14)', () => {
  // direct fallout of the label-reversal incident: 116 reply_dnc rows turned out unclassifiable
  // (explicit "do not contact" vs a soft "not interested" decline) because reply_category was
  // never captured when they were written. Schema-level assert now, not a habit -- S1's build
  // inherits this the moment it starts calling UpsertLedger with reason: 'reply_dnc'.
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const prep = wf.nodes.find((n) => n.name === 'Normalize + Prep');
  const js = prep.parameters.jsCode;
  assert.ok(js.includes("s.reason === 'reply_dnc' && !s.reply_category"),
    'must reject a reply_dnc write with no reply_category, not silently accept it');
  assert.ok(js.includes('throw new Error'));
});

t('every executeWorkflow call uses mode:each, never mode:once (regression guard, 2026-08-12)', () => {
  // found live: "once" batches every fan-out item reaching the node in one execution into a
  // SINGLE subworkflow call; UpsertLedger/CheckLedger are both written for single-item semantics
  // ($input.first()), so "once" silently processed only the FIRST of N items every time -- caught
  // live when the S3 Surfe backfill's real fire wrote 1 registry row where 24 were expected, with
  // execution status "success" throughout and zero errors surfaced. Every call site, not just the
  // two that fan out today -- a workflow that only ever sends 1 item now could start sending N
  // later without anyone remembering to check this.
  const files = [
    path.join('..', 'workflows', 'heyreach_reply_to_dnc_ledger', 'heyreach_reply_to_dnc_ledger.json'),
    path.join('..', 'workflows', 'dnc_wf4_sheet_intake', 'dnc_wf4_sheet_intake.json'),
    path.join('..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'),
    path.join('..', 'workflows', 'dnc_s3_surfe_backfill', 'dnc_s3_surfe_backfill.json'),
    path.join('..', 'workflows', 'dnc_s4_event_populations', 'dnc_s4_event_populations.json'),
    path.join('..', 'workflows', 'dnc_s2_meeting_to_dnc', 'dnc_s2_meeting_to_dnc.json'),
    path.join('..', 'workflows', 'dnc_s1_responded_to_dnc', 'dnc_s1_responded_to_dnc.json'),
  ];
  let found = 0;
  for (const rel of files) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, rel), 'utf8'));
    for (const n of wf.nodes) {
      if (n.type === 'n8n-nodes-base.executeWorkflow') {
        found++;
        assert.equal(n.parameters.mode, 'each',
          `${rel}: ${n.name} must use mode:each, not mode:once (silent data loss on >1 item)`);
      }
    }
  }
  assert.ok(found >= 7, 'expected to find every known executeWorkflow call site, not silently miss one');
});

t('dnc_s3_creation_watcher: 0-match polls post nothing, bursts escalate to ops, daily heartbeat (Nik, 2026-08-13)', () => {
  // live complaint: the watcher was posting "0 matches" every 15 minutes -- noise in any channel,
  // telemetry included. Fix: (a) 0 matches -> no post at all; (b) a burst in one poll -> ops, not
  // just telemetry; (c) one daily heartbeat line so silence stays distinguishable from a dead
  // watcher -- the exact "__idle" lesson this rule is named for.
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s3_creation_watcher', 'dnc_s3_creation_watcher.json'), 'utf8'));

  // (a) the 0-match branch must be a true dead end -- no Combine, no Slack post.
  const gateOut = wf.connections['S3 Any Matches?'].main;
  assert.ok(gateOut[1].length === 0, '0-match branch must have zero outgoing connections');

  // poll-stats tracking must run on EVERY poll (before the gate), not just when there's a match --
  // otherwise the heartbeat's poll count would only count polls that found something.
  // S3 Filter New (2026-08-20 loop-spam fix) now sits between Classify and the tracker -- still
  // runs on every poll, same as before, just diffed against last poll's snapshot first.
  const trackerIdx = wf.nodes.findIndex((n) => n.name === 'S3 Track Poll Stats');
  assert.ok(trackerIdx >= 0, 'expected a poll-stats tracker node');
  assert.equal(wf.connections['S3 Classify'].main[0][0].node, 'S3 Filter New');
  assert.equal(wf.connections['S3 Filter New'].main[0][0].node, 'S3 Track Poll Stats');
  assert.equal(wf.connections['S3 Track Poll Stats'].main[0][0].node, 'S3 Any Matches?');
  const trackerJs = wf.nodes[trackerIdx].parameters.jsCode;
  assert.ok(trackerJs.includes("$getWorkflowStaticData('global')"));
  assert.ok(trackerJs.includes('sd.pollsToday += 1'));
  assert.ok(trackerJs.includes('sd.matchesToday += agg.count'));

  // (b) burst escalation: a single poll finding >= threshold matches routes to ops, not telemetry.
  const combineJs = wf.nodes.find((n) => n.name === 'S3 Combine').parameters.jsCode;
  assert.ok(/isBurst = agg\.count >= \d+/.test(combineJs), 'must define a real numeric burst threshold');
  assert.ok(combineJs.includes('isBurst ? cfg.alert_channel : cfg.telemetry_channel'),
    'a burst must route to ops (alert_channel), normal activity stays on telemetry');

  // (c) daily heartbeat: a separate trigger, independent of CONFIG/Send Guard (always telemetry,
  // nothing to misconfigure), reading and resetting the SAME counters the tracker maintains.
  const heartbeatTimer = wf.nodes.find((n) => n.name === 'Heartbeat Timer');
  assert.ok(heartbeatTimer, 'expected a dedicated daily heartbeat trigger');
  assert.equal(heartbeatTimer.type, 'n8n-nodes-base.scheduleTrigger');
  const heartbeatPost = wf.nodes.find((n) => n.name === 'S3 Heartbeat Post');
  assert.ok(heartbeatPost.parameters.jsCode.includes("$getWorkflowStaticData('global')"));
  assert.ok(heartbeatPost.parameters.jsCode.includes('polls'), 'heartbeat must report the poll count');
  assert.ok(heartbeatPost.parameters.jsCode.includes('match'), 'heartbeat must report the match count');
  assert.ok(heartbeatPost.parameters.jsCode.includes('C0BQM1X9ZUY'),
    'heartbeat channel must be hardcoded to telemetry, not read from a mutable CONFIG value');
  assert.equal(wf.connections['Heartbeat Timer'].main[0][0].node, 'S3 Heartbeat Post');
  assert.equal(wf.connections['S3 Heartbeat Post'].main[0][0].node, 'S3 Heartbeat Slack');
});

t('webhook-body CONFIG fields read $json.body.*, never bare $json.* (regression guard, 2026-08-14)', () => {
  // found live on S4's first real fire: n8n's Webhook node wraps the entire POST body under a
  // `.body` key (alongside .headers/.query/.params) -- every CONFIG field reading bare
  // $json.<field> was silently null. For S4 this was catastrophic: "S4 Is Smartlead?" compared
  // that null against 'smartlead', always got false, and routed EVERY call to HeyReach regardless
  // of the requested source_type -- HeyReach then failed on a null campaignId. Same mistake
  // existed in the S3 Surfe backfill's start_offset, latent only because that population fit in
  // one chunk (offset was always the literal 0 default regardless).
  // dnc_s2_meeting_to_dnc REBUILT 2026-09-15 (Nik's GO): no longer reads any webhook-body field at
  // all -- the live daily poll drives everything from Pipedrive queries + static CONFIG values,
  // not a caller-supplied offset/person_ids payload. Removed from this list on purpose.
  for (const [wfDir, fields] of [
    ['dnc_s3_surfe_backfill', ['start_offset']],
    ['dnc_s4_event_populations', ['source_type', 'campaign_id', 'campaign_name', 'offset']],
    ['dnc_s1_responded_to_dnc', ['offset', 'candidates']],
  ]) {
    const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', wfDir, `${wfDir}.json`), 'utf8'));
    const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
    for (const field of fields) {
      const a = cfg.parameters.assignments.assignments.find((x) => x.name === field);
      assert.ok(a, `${wfDir}: expected a CONFIG field named ${field}`);
      assert.ok(String(a.value).includes(`$json.body.${field}`),
        `${wfDir}.${field}: must read $json.body.${field}, not bare $json.${field} (value: ${a.value})`);
    }
  }
});

t('dnc_label_reversal: correct KEEP/REMOVE classification, 3-way merge, no dead ends (Melisa ruling, 2026-08-14)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_label_reversal', 'dnc_label_reversal.json'), 'utf8'));

  // candidate SOURCE is the auditor's frozen id-set (via cfg.frozen_ids), not a fresh registry
  // scan -- and Person-d443dfbd (4538ad40, pre-labelled before the projection ran) must be
  // excluded from that frozen set even if the driver ever forgot to filter him out itself.
  const classify = wf.nodes.find((n) => n.name === 'R Classify');
  const classifyJs = classify.parameters.jsCode;
  assert.ok(classifyJs.includes('cfg.frozen_ids'), 'must source candidates from the frozen id-set, not re-derive from the registry');
  assert.ok(classifyJs.includes('4538ad40-4eb7-11f1-9d0a-8ddac4d89290'),
    'Martinets exclusion must be enforced in the workflow itself, not rely solely on the driver');

  // KEEP/REMOVE reason classification happens per-lead in R Check And Strip, AFTER the lead is
  // fetched by id -- found live: the frozen artifact's ids are Pipedrive LEAD ids (uuid), not
  // person ids, so joining against the registry's numeric pipedrive_person_id requires fetching
  // the lead first (its person_id is inline on the lead object) rather than joining up front.
  const strip = wf.nodes.find((n) => n.name === 'R Check And Strip');
  const stripJs = strip.parameters.jsCode;
  assert.ok(stripJs.includes('"unsubscribe"') && stripJs.includes('"client"') && stripJs.includes('KEEP.includes(reason)'),
    'only client/unsubscribe (entry_type=explicit_opt_out) may be excluded from removal');
  assert.ok(!stripJs.includes('"reply_dnc"') && !stripJs.includes('"manual_sheet"'),
    'reply_dnc/manual_sheet/etc. must NOT be in the keep-list -- confirmed remove-by-default 2026-08-14');
  assert.ok(stripJs.includes('no_registry_match') && stripJs.includes('kept_for_reason'),
    'anomalies (frozen lead absent from registry / kept for explicit-opt-out reason) must be surfaced, not silently absorbed');
  assert.ok(stripJs.includes("lead.person_id"),
    'must join the fetched lead to the registry via lead.person_id, not the frozen lead-id itself');

  // the lead lookup fetches by lead id directly (GET /v1/leads/{id}), NOT by person_id -- the
  // frozen candidate set is already lead ids, so a person_id-keyed lookup would need an id-space
  // translation this workflow no longer has upstream.
  const getLead = wf.nodes.find((n) => n.name === 'R Get Lead By Id');
  assert.ok(getLead, 'R Get Lead By Id must exist');
  assert.ok(String(getLead.parameters.url).includes('/v1/leads/{{ $json.lead_id }}'));

  // webhook-body field reads, same regression class as S3B/S4's earlier bug.
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const offsetField = cfg.parameters.assignments.assignments.find((a) => a.name === 'offset');
  assert.ok(String(offsetField.value).includes('$json.body.offset'));
  const frozenIdsField = cfg.parameters.assignments.assignments.find((a) => a.name === 'frozen_ids');
  assert.ok(frozenIdsField, 'CONFIG must expose frozen_ids for R Classify to read');
  assert.ok(String(frozenIdsField.value).includes('$json.body.frozen_ids'));

  // four genuinely-simultaneous outcomes (real strip / already-correct-or-no-lead / to-strip-
  // but-dry-run / fetch-error) must each land on a distinct merge input -- same regression class
  // as every other Merge bug caught today; a shared node here would double-fire exactly like
  // "R Skip Strip" did in the first draft of this workflow before it shipped.
  const mergeNode = wf.nodes.find((n) => n.name === 'R Merge Outcomes');
  assert.equal(mergeNode.parameters.mode, 'append');
  assert.equal(mergeNode.parameters.numberInputs, 4);
  const idxByName = {};
  // NOT 'R Patch Lead Labels' directly -- its raw HTTP response has no .outcome field, must go
  // through 'R Confirm Strip' first (see the dedicated test below for why).
  for (const src of ['R Confirm Strip', 'R Already Correct/No Lead', 'R To-Strip (dry-run)', 'R Lead Fetch Error']) {
    idxByName[src] = wf.connections[src].main[0][0].index;
    assert.equal(wf.connections[src].main[0][0].node, 'R Merge Outcomes');
  }
  assert.deepEqual(Object.values(idxByName).sort(), [0, 1, 2, 3], 'all four outcomes must land on distinct merge inputs');

  // found live 2026-08-14 (auditor's boundary-check re-verification): 5 frozen leads no longer
  // resolve at all -- R Get Lead By Id's error output was previously unwired, exactly the silent-
  // write-failure-gap bug class from the Pipedrive sweep, just on a read. Must be wired and
  // tallied, never silently dropped (which would under-advance next_offset with no visibility).
  const getLeadConn = wf.connections['R Get Lead By Id'].main;
  assert.equal(getLeadConn.length, 2, 'R Get Lead By Id must have both outputs wired');
  assert.equal(getLeadConn[0][0].node, 'R Check And Strip');
  assert.equal(getLeadConn[1][0].node, 'R Lead Fetch Error');
  const combineJsR = wf.nodes.find((n) => n.name === 'R Combine').parameters.jsCode;
  assert.ok(combineJsR.includes("outcome === 'fetch_error'"),
    'R Combine must tally fetch_error outcomes, not silently drop them from the chunk total');

  // live_exclusion_ids: a caller-supplied exclusion list (auditor's re-anchor pass) must be
  // subtracted from the frozen candidate set BEFORE chunking, same frozen-external-list shape as
  // frozen_ids itself -- not hardcoded, since the exact drifted ids are still being confirmed.
  const liveExclField = cfg.parameters.assignments.assignments.find((a) => a.name === 'live_exclusion_ids');
  assert.ok(liveExclField, 'CONFIG must expose live_exclusion_ids');
  assert.ok(String(liveExclField.value).includes('$json.body.live_exclusion_ids'));
  assert.ok(classifyJs.includes('liveExclusions.has(id)'),
    'R Classify must subtract live_exclusion_ids from the frozen candidate set');

  // found live in the first real 100-item dry-run chunk (auditor's frozen-id-set rerun,
  // 2026-08-14): both passthrough nodes feeding the merge used mode:runOnceForAllItems with a
  // bare $input.first() -- collapsing 100 incoming items down to 1 before the merge, same bug
  // class as PD Classify/SL Classify (see code_node_per_item's own comment) but on a passthrough
  // instead of a transform. "R Merge Outcomes" emitted 1 item where 100 were expected.
  for (const src of ['R Already Correct/No Lead', 'R To-Strip (dry-run)']) {
    const passNode = wf.nodes.find((n) => n.name === src);
    assert.equal(passNode.parameters.mode, 'runOnceForEachItem',
      `${src} must run per-item -- runOnceForAllItems + $input.first() silently collapses every chunk to 1 item`);
    assert.ok(!passNode.parameters.jsCode.includes('$input.first()'),
      `${src} must not use $input.first() (drops every item but the first)`);
  }

  // union-preserving strip: only OUR label id may be removed, via a plain array filter -- never a
  // full label_ids overwrite that could silently drop someone else's label.
  const stripNode = wf.nodes.find((n) => n.name === 'R Check And Strip');
  assert.ok(stripNode.parameters.jsCode.includes('lead.label_ids.filter(id => id !=='),
    'must filter the existing label_ids array, not replace it wholesale');

  // no dead ends on the reporting path.
  assert.equal(wf.connections['R Merge Outcomes'].main[0][0].node, 'R Combine');
  assert.equal(wf.connections['R Combine'].main[0][0].node, 'R MODE == dev?');

  // found live 2026-08-14 on the FIRST real live fire: R Patch Lead Labels is a raw HTTP node,
  // its response REPLACES $json with the Pipedrive PATCH body -- discarding the
  // {outcome:'to_strip', lead_id, ...} object entirely. R Combine's outcomes filter then silently
  // dropped all 100 real successes (no .outcome field on a raw API response): reported
  // stripped=0 and concluded done=true after exactly one chunk, even though the underlying writes
  // had already succeeded correctly. Must restore the outcome via the paired-item reference
  // before reaching the merge, never feed the raw HTTP response into it directly.
  assert.equal(wf.connections['R Patch Lead Labels'].main[0][0].node, 'R Confirm Strip',
    'R Patch Lead Labels must not feed the merge directly -- its response has no .outcome field');
  assert.equal(wf.connections['R Confirm Strip'].main[0][0].node, 'R Merge Outcomes');
  const confirmStrip = wf.nodes.find((n) => n.name === 'R Confirm Strip');
  assert.ok(confirmStrip.parameters.jsCode.includes("$('R Check And Strip').item.json"),
    'R Confirm Strip must restore outcome context from the paired upstream item');
});

t('dnc_s4_event_populations: dual-provider merge, identity gate, mode:each, no dead ends (2026-08-14)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s4_event_populations', 'dnc_s4_event_populations.json'), 'utf8'));

  // responseMode: lastNode, no dedicated Respond node -- same pragmatic choice as the S3 Surfe
  // backfill after its unresolved "No Respond to Webhook node found" mystery; not worth
  // re-risking here for a workflow with the identical shape.
  const webhookNode = wf.nodes.find((n) => n.name === 'Webhook');
  assert.equal(webhookNode.parameters.responseMode, 'lastNode');
  assert.ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.respondToWebhook'));

  // found live 2026-08-14 (S4 build resumed, first real dry-run fire): S4 Aggregate had NO
  // outgoing connection anywhere in the generator -- every execution silently dead-ended there,
  // and since responseMode is lastNode the webhook just returned Aggregate's raw output, masking
  // the gap exactly like the S3 Combine dead-end did (slack_text computed but never posted). S4
  // Any Matches?/Split/Combine never ran at all until this was caught and fixed.
  assert.equal(wf.connections['S4 Aggregate'].main[0][0].node, 'S4 Any Matches?',
    'S4 Aggregate must not be a dead end -- must feed S4 Any Matches?');

  // 4-way merge: Smartlead success/error + HeyReach success/error, each on a DISTINCT input index
  // -- same regression shape as every other merge bug caught today (two sources landing on the
  // same index silently drops one of them).
  const mergeSources = wf.nodes.find((n) => n.name === 'S4 Merge Sources');
  assert.equal(mergeSources.parameters.mode, 'append');
  assert.equal(mergeSources.parameters.numberInputs, 4);
  const idxByName = {};
  for (const src of ['S4 Normalize Smartlead', 'S4 Fetch Error (Smartlead)', 'S4 Normalize HeyReach', 'S4 Fetch Error (HeyReach)']) {
    idxByName[src] = wf.connections[src].main[0][0].index;
    assert.equal(wf.connections[src].main[0][0].node, 'S4 Merge Sources');
  }
  const usedIndices = Object.values(idxByName).sort();
  assert.deepEqual(usedIndices, [0, 1, 2, 3], 'all four sources must land on distinct merge inputs');

  // both fetch nodes' error (2nd) output must be wired -- an unwired one here is exactly the
  // Pipedrive-sweep silent-failure bug, just for a fetch instead of a write.
  for (const name of ['S4 Get Smartlead Leads', 'S4 Get HeyReach Leads']) {
    const n = wf.nodes.find((x) => x.name === name);
    assert.equal(n.onError, 'continueErrorOutput');
    const out = wf.connections[name].main;
    assert.equal(out.length, 2, `${name}: must have both outputs wired`);
    assert.ok(out[1] && out[1].length > 0, `${name}: error output must not dead-end`);
  }

  // HeyReach node must use a REAL credential, not a placeholder -- checked directly since this
  // integration point (n8n calling OUT to HeyReach's API) never existed before S4; every prior
  // HeyReach workflow only ever received inbound webhooks FROM HeyReach.
  const hrNode = wf.nodes.find((n) => n.name === 'S4 Get HeyReach Leads');
  assert.ok(!JSON.stringify(hrNode.credentials).includes('PLACEHOLDER'),
    'HeyReach credential must be a real, created credential id, not a placeholder');

  // identity gate + mode:each, same classes already caught twice today -- re-verified here rather
  // than assumed just because the pattern was copied correctly.
  assert.equal(wf.connections['S4 Build Upsert Input'].main[0][0].node, 'S4 Has Identity?');
  const execNode = wf.nodes.find((n) => n.name === 'S4 Call UpsertLedger');
  assert.equal(execNode.parameters.mode, 'each');

  // Combine must not be a dead end (same class as the S3 "slack post never fired" bug).
  assert.equal(wf.connections['S4 Combine'].main[0][0].node, 'S4 MODE == dev?');

  // found live 2026-08-14 on the Sales Sprint fire: STOPPED-status leads have EVERY lead.* field
  // nulled out by Smartlead, including lead.id -- external_id must fall back to
  // row.campaign_lead_map_id (the one field that survives) so the skip report never renders the
  // literal string "undefined" (both full_name AND external_id nullish at once).
  const normalizeSl = wf.nodes.find((n) => n.name === 'S4 Normalize Smartlead');
  assert.ok(normalizeSl.parameters.jsCode.includes('l.id || row.campaign_lead_map_id'),
    'external_id must fall back to campaign_lead_map_id when lead.id is null');
  // and external_id must actually be propagated onto the upsert-input object -- it was computed
  // upstream but only ever used inline for correlation_id, never copied through, so the skip
  // report's own fallback saw it as literally undefined regardless of the normalize-side fix.
  const buildInput = wf.nodes.find((n) => n.name === 'S4 Build Upsert Input');
  assert.ok(buildInput.parameters.jsCode.includes('external_id: match.external_id'),
    'external_id must be copied onto the upsert-input object, not just used inline for correlation_id');
  const combineJs = wf.nodes.find((n) => n.name === 'S4 Combine').parameters.jsCode;
  assert.ok(!combineJs.includes('n.full_name || n.external_id'),
    'the skip-report fallback must label a bare external_id, not silently interpolate it unexplained');
});

t('dnc_s2_meeting_to_dnc: REBUILT 2026-09-15 (Nik\'s GO) -- live daily poll, no fan-in anywhere, no dead ends', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s2_meeting_to_dnc', 'dnc_s2_meeting_to_dnc.json'), 'utf8'));

  // the old frozen-snapshot replay is GONE, not layered on -- no person_ids/offset webhook-body
  // config fields, no reference to a frozen id-set anywhere.
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const cfgNames = cfg.parameters.assignments.assignments.map((a) => a.name);
  assert.ok(!cfgNames.includes('person_ids'), 'the frozen person_ids config field must be gone');
  assert.ok(!cfgNames.includes('offset'), 'the frozen offset config field must be gone');
  assert.ok(cfgNames.includes('meeting_label_id') && cfgNames.includes('meeting_stage_id')
    && cfgNames.includes('lookback_hours'), 'must configure the live query instead');

  // Nik's GO: "fix the flagged fan-in before scheduling" -- no Merge node anywhere in this
  // workflow at all (the old S2 Merge Identity Paths is not just fixed, it's designed away).
  assert.ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.merge'),
    'no Merge node should exist anywhere in the rebuilt S2 -- fan-in eliminated by design, not patched');

  // daily schedule + webhook both feed CONFIG (mutually exclusive triggers, safe fan-out).
  const timer = wf.nodes.find((n) => n.name === 'Daily Timer');
  assert.ok(timer && timer.type === 'n8n-nodes-base.scheduleTrigger');
  assert.ok(wf.nodes.some((n) => n.name === 'Webhook'));
  const configTargets = (wf.connections['CONFIG'].main[0] || []).map((c) => c.node);
  assert.deepEqual(configTargets, ['S2 Get Recent Label Leads']);
  assert.deepEqual((wf.connections['Webhook'].main[0] || []).map((c) => c.node), ['CONFIG']);
  assert.deepEqual((wf.connections['Daily Timer'].main[0] || []).map((c) => c.node), ['CONFIG']);

  // the two signal branches are SEQUENCED (label fully classified before the deal fetch starts),
  // matching the nightly reconcile's proven fix for exactly this shape (a small, FIXED number of
  // branches is safe to hand-sequence; converging them via Merge is not).
  const targets = (src) => ((wf.connections[src] && wf.connections[src].main[0]) || []).map((c) => c.node);
  assert.deepEqual(targets('S2 Get Recent Label Leads'), ['S2 Classify Label Signals']);
  assert.deepEqual(targets('S2 Classify Label Signals'), ['S2 Get Recent Stage Deals']);
  assert.deepEqual(targets('S2 Get Recent Stage Deals'), ['S2 Classify Stage Signals']);
  assert.deepEqual(targets('S2 Classify Stage Signals'), ['S2 Aggregate Candidates']);

  // "S2 Aggregate Candidates" runs exactly once, BEFORE the per-item split, and fans OUT to both
  // the split and Combine directly -- the delta-pusher/PD-Aggregate fix pattern, applied from the
  // start. Combine must have exactly ONE incoming source (no converged per-item outcome stream).
  assert.deepEqual(targets('S2 Aggregate Candidates').sort(), ['S2 Any Candidates?', 'S2 Combine'].sort());
  const incomingToCombine = Object.entries(wf.connections)
    .filter(([, out]) => out.main.some((b) => (b || []).some((c) => c.node === 'S2 Combine')))
    .map(([src]) => src);
  assert.deepEqual(incomingToCombine, ['S2 Aggregate Candidates']);
  assert.deepEqual(targets('S2 Combine'), ['S2 MODE == dev?']);

  // both per-item branches (fire / skip-dry-run, has-identity / no-identity) are clean dead ends --
  // Combine reads their data via $() named references, never via a wired convergence.
  assert.deepEqual(targets('FIRE_S2?'), ['S2 Call UpsertLedger']);
  assert.deepEqual(wf.connections['FIRE_S2?'].main[1], []);
  assert.deepEqual(targets('S2 Call UpsertLedger'), []);
  assert.deepEqual(targets('S2 Log No Identity'), []);
  const combine = wf.nodes.find((n) => n.name === 'S2 Combine');
  assert.ok(combine.parameters.jsCode.includes("$('S2 Aggregate Candidates').first().json"));
  assert.ok(combine.parameters.jsCode.includes("$('S2 Log No Identity').all()"));

  // reason=meeting_dnc must actually be written, and this scenario is registry-only -- no
  // Pipedrive label write anywhere in the build (Melisa's label-policy ruling).
  const buildInput = wf.nodes.find((n) => n.name === 'S2 Build Upsert Input');
  assert.ok(buildInput.parameters.jsCode.includes("reason: 'meeting_dnc'"));
  assert.ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.httpRequest'
    && JSON.stringify(n.parameters).includes('label_ids')),
    'S2 must never write Pipedrive label_ids -- registry field only');
  assert.equal(wf.connections['S2 Build Upsert Input'].main[0][0].node, 'S2 Has Identity?');
  const execNode = wf.nodes.find((n) => n.name === 'S2 Call UpsertLedger');
  assert.equal(execNode.parameters.mode, 'each');

  // deal.person_id is a NESTED OBJECT, unlike lead.person_id (a bare id) -- confirmed live
  // 2026-09-15 (deal 2267, Chirag R Shah). Getting this wrong silently matches nothing, ever.
  const stageClassify = wf.nodes.find((n) => n.name === 'S2 Classify Stage Signals');
  assert.ok(/deal\.person_id && typeof deal\.person_id === 'object'/.test(stageClassify.parameters.jsCode));

  // update_time comes back in two different shapes (leads: ISO+Z, deals: bare space-separated UTC)
  // -- confirmed live against real records from both endpoints. Both classifiers must normalize.
  const labelClassify = wf.nodes.find((n) => n.name === 'S2 Classify Label Signals');
  assert.ok(labelClassify.parameters.jsCode.includes('function tsToIso'));
  assert.ok(stageClassify.parameters.jsCode.includes('function tsToIso'));

  // regression, found live 2026-09-15 on the rebuild's first real dry-run fire: "S2 Aggregate
  // Candidates" 's direct wire predecessor is "S2 Classify Stage Signals" (stage runs SECOND in
  // the hand-sequenced chain), so $json inside it is the STAGE data -- the first build had this
  // backwards (read $json as labelAgg, and named-referenced "S2 Classify Stage Signals" a second
  // time for "stageAgg"), so every real dual-signal candidate's label half silently vanished and
  // both entries came back kind:'stage'. Caught by inspecting live output, not by this test (which
  // made the identical mistake in its own mock) -- both are pinned now.
  const aggregate = wf.nodes.find((n) => n.name === 'S2 Aggregate Candidates');
  assert.ok(/const stageAgg = \$json/.test(aggregate.parameters.jsCode),
    '$json (the direct wire input) must be treated as the stage aggregate');
  assert.ok(/const labelAgg = \$\('S2 Classify Label Signals'\)\.first\(\)\.json/.test(aggregate.parameters.jsCode),
    'the label aggregate must be read via a named reference to S2 Classify Label Signals, not Stage Signals');
});

t('dnc_s2_meeting_to_dnc statics (Nik\'s GO, 2026-09-15): label-only / stage-only / both / neither / no-downgrade', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s2_meeting_to_dnc', 'dnc_s2_meeting_to_dnc.json'), 'utf8'));
  const aggFn = new Function('$json', '$',
    wf.nodes.find((n) => n.name === 'S2 Aggregate Candidates').parameters.jsCode);
  const run = (labelMatches, stageMatches) => {
    const labelAgg = { matches: labelMatches, count: labelMatches.length, possibly_truncated: false };
    const stageAgg = { matches: stageMatches, count: stageMatches.length, possibly_truncated: false };
    // "S2 Aggregate Candidates" is wired DIRECTLY after "S2 Classify Stage Signals" (stage runs
    // second in the hand-sequenced chain) -- $json is the stage aggregate, label is read via a
    // named reference. Getting this backwards in the test would hide the exact bug the real build
    // had on its first live fire (caught live 2026-09-15, both branches of a real dual-signal
    // candidate came back kind:'stage') -- mirror the real wiring, not the intent.
    const dollar = (name) => {
      if (name === 'S2 Classify Label Signals') return { first: () => ({ json: labelAgg }) };
      throw new Error('unexpected $() ref: ' + name);
    };
    return aggFn(stageAgg, dollar)[0].json;
  };
  const labelMatch = (pid) => ({ person_id: pid, ref_id: 'lead1', kind: 'label', source_ref: '5. Meeting label' });
  const stageMatch = (pid) => ({ person_id: pid, ref_id: 'deal1', kind: 'stage', source_ref: 'Qualified Meeting Set stage' });

  // label-only -> one candidate, one distinct person, zero "both"
  {
    const out = run([labelMatch(111)], []);
    assert.equal(out.count, 1);
    assert.equal(out.distinct_people, 1);
    assert.equal(out.both_signal_people, 0);
  }
  // stage-only -> one candidate, one distinct person, zero "both"
  {
    const out = run([], [stageMatch(222)]);
    assert.equal(out.count, 1);
    assert.equal(out.distinct_people, 1);
    assert.equal(out.both_signal_people, 0);
  }
  // both -> TWO candidate entries (not merged pre-write -- see the build's header comment for why:
  // Decide's own also_flagged logic only populates correctly across two sequential real calls),
  // but ONE distinct person and both_signal_people=1, so the Slack report still reads "one person".
  {
    const out = run([labelMatch(333)], [stageMatch(333)]);
    assert.equal(out.count, 2);
    assert.equal(out.distinct_people, 1);
    assert.equal(out.both_signal_people, 1);
    assert.deepEqual(out.candidates.map((c) => c.person_id), [333, 333]);
    assert.deepEqual(out.candidates.map((c) => c.kind).sort(), ['label', 'stage']);
  }
  // neither -> nothing
  {
    const out = run([], []);
    assert.equal(out.count, 0);
    assert.equal(out.distinct_people, 0);
  }

  // "already registered under a stronger reason -> no downgrade" is NOT this workflow's job to
  // enforce -- it is DNC__UpsertLedger__v1's Decide step (reason_v1.js's reasonMergeV1), already
  // covered by its own dedicated tests (see "reason_v1: meeting_dnc added correctly"). Re-asserting
  // the actual strength order here so a change to either file can't silently drift apart.
  assert.equal(reasonStrongest('client', 'meeting_dnc'), 'client');
  assert.equal(reasonStrongest('unsubscribe', 'meeting_dnc'), 'unsubscribe');
  assert.equal(reasonStrongest('meeting_dnc', 'reply_dnc'), 'meeting_dnc');
  assert.equal(reasonStrongest('meeting_dnc', 'sales_personal_outreach'), 'meeting_dnc');
});

t('reason_v1: meeting_dnc added correctly (S2, 2026-08-14)', () => {
  // per PHASE1_SCENARIOS_SPEC_2026-08-11.md's proposal: deeper engagement than a bare reply, but
  // still the person engaging WITH us, not an explicit opt-out -- maps to entry_type 'replied'
  // (standard reply-tier TTL), ranks above reply_dnc, below both explicit-opt-out reasons.
  assert.equal(reasonEntryType('meeting_dnc'), 'replied');
  assert.equal(isOffboardRemovable('meeting_dnc'), false);
  assert.equal(reasonStrongest('reply_dnc', 'meeting_dnc'), 'meeting_dnc');
  assert.equal(reasonStrongest('meeting_dnc', 'reply_dnc'), 'meeting_dnc');
  assert.equal(reasonStrongest('client', 'meeting_dnc'), 'client');
  assert.equal(reasonStrongest('unsubscribe', 'meeting_dnc'), 'unsubscribe');
});

t('dnc_s1_responded_to_dnc: union candidate list, reply_category always set, no dead ends (2026-08-14)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_s1_responded_to_dnc', 'dnc_s1_responded_to_dnc.json'), 'utf8'));

  // candidate source is a driver-resolved UNION list (Pipedrive '3. Responded' label + Smartlead
  // history REPLY events, any campaign, + HeyReach) -- same frozen-external-list shape as S2/the
  // label reversal, never re-derived inside the workflow.
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const candField = cfg.parameters.assignments.assignments.find((a) => a.name === 'candidates');
  assert.ok(candField, 'CONFIG must expose candidates for S1 Classify to read');
  assert.ok(String(candField.value).includes('$json.body.candidates'));
  const offsetField = cfg.parameters.assignments.assignments.find((a) => a.name === 'offset');
  assert.ok(String(offsetField.value).includes('$json.body.offset'));

  // dedupe-with-richer-category: if the same person surfaced via more than one source, a real
  // provider category must win over the 'unclassified' placeholder, never the reverse.
  const classify = wf.nodes.find((n) => n.name === 'S1 Classify');
  assert.ok(classify.parameters.jsCode.includes("prev.reply_category === 'unclassified'"),
    'dedupe must prefer a real reply_category over the unclassified placeholder');

  // reply_dnc requires reply_category on every single row -- this is the exact 116-row gap the
  // schema-level assert exists to close; S1 must always carry it through, never write null.
  const buildInput = wf.nodes.find((n) => n.name === 'S1 Build Upsert Input');
  assert.ok(buildInput.parameters.jsCode.includes("reason: 'reply_dnc'"));
  assert.ok(buildInput.parameters.jsCode.includes('reply_category: match.reply_category'));

  // registry-only: no Pipedrive label write anywhere in this build (Melisa's ruling -- "3.
  // Responded" already exists from the original activity and is untouched).
  assert.ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.httpRequest'
    && JSON.stringify(n.parameters).includes('label_ids')),
    'S1 must never write Pipedrive label_ids -- registry field only');

  // found live on this workflow's own first real dry-run (2026-08-14): matches_this_chunk
  // reported a hardcoded cfg.chunk_size every chunk (including the final partial one), so the
  // driver's own summed total overcounted (18*100=1800 reported vs. 1717 real candidates) --
  // registry writes were unaffected (they already used the real per-item flow), only this
  // telemetry field was wrong. Must be the real processed-item count, not the constant.
  const combine = wf.nodes.find((n) => n.name === 'S1 Combine');
  assert.ok(combine.parameters.jsCode.includes('matches_this_chunk: outcomes.length'),
    'matches_this_chunk must be the real per-chunk item count, not a hardcoded cfg.chunk_size');

  // found live 2026-08-18 (S1's first real live fire, running concurrently with S2's first
  // dry-run -- same bug on both): S1 Write Barrier used mode:runOnceForAllItems with a static
  // `[{json:{done:true}}]` return, collapsing every real identity-bearing item (e.g. 39 real
  // UpsertLedger calls in one chunk) down to 1 before reaching outcomes.length -- understating
  // matches_this_chunk on every single chunk (reported "62" combining 1 collapsed + 61 skipped,
  // instead of the real ~100). Writes themselves were correct (mode:each already fans out
  // upstream) and next_offset/done are driven by cfg.chunk_size not this count, so no run
  // terminated early -- but every reported number was wrong. Must be a genuine per-item
  // passthrough, not a static single-item return.
  const s1WriteBarrier = wf.nodes.find((n) => n.name === 'S1 Write Barrier');
  assert.equal(s1WriteBarrier.parameters.mode, 'runOnceForEachItem',
    'S1 Write Barrier must run per-item -- runOnceForAllItems + a static return silently collapses every chunk to 1 item');
  assert.ok(!s1WriteBarrier.parameters.jsCode.includes('{ done: true }'),
    'S1 Write Barrier must not use a static single-item return');

  // identity gate + mode:each, same classes caught repeatedly today.
  assert.equal(wf.connections['S1 Build Upsert Input'].main[0][0].node, 'S1 Has Identity?');
  const execNode = wf.nodes.find((n) => n.name === 'S1 Call UpsertLedger');
  assert.equal(execNode.parameters.mode, 'each');

  // no dead ends -- the exact bug class that hit S4 Aggregate today.
  assert.equal(wf.connections['S1 Classify'].main[0][0].node, 'S1 Any Candidates?');
  assert.equal(wf.connections['S1 Combine'].main[0][0].node, 'S1 MODE == dev?');

  const mergeNode = wf.nodes.find((n) => n.name === 'S1 Merge Identity Paths');
  assert.equal(mergeNode.parameters.mode, 'append');
  assert.equal(mergeNode.parameters.numberInputs, 2);
});

t('S1: Person-7267ff83 fixture merges without weakening (poster case, 2026-08-13)', () => {
  // Andrea / Owkin is already in the registry via seed import (manual_sheet) -- when S1's sweep
  // also finds her as a reply (Interested, active partnership talks), the merge must UPGRADE her
  // to reply_dnc (stronger than manual_sheet on reason_v1's ladder), populate reply_category, and
  // never let her drop out of the registry or move to a weaker/shorter-lived state in the process.
  const fixturePath = path.join(SUB, '..', 'fixtures', 's1_poster_case_andrea_tassistro.json');
  assert.ok(fs.existsSync(fixturePath), 'expected the Person-7267ff83 fixture to exist');
  const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
  const existing = JSON.stringify(fixture).includes('manual_sheet')
    ? fixture.existing || fixture.s1_poster_case_existing_registry_row || fixture
    : fixture;
  // the fixture must actually document the pre-existing weaker row -- if this ever regresses to a
  // fixture with no seeded prior state, the "merge-without-weakening" claim isn't being tested.
  assert.ok(JSON.stringify(fixture).includes('manual_sheet'),
    'fixture must document the pre-existing manual_sheet row this scenario merges onto');

  assert.equal(reasonStrongest('manual_sheet', 'reply_dnc'), 'reply_dnc',
    'reply_dnc must win the merge over the pre-existing manual_sheet row -- an upgrade, not a replacement risk');
  assert.equal(reasonStrongest('reply_dnc', 'manual_sheet'), 'reply_dnc');
});

t('dnc_escalation_detector: nurture exemption, zero-active-campaigns handled cleanly, silent-if-zero, no dead ends (2026-08-14)', () => {
  const wf = JSON.parse(fs.readFileSync(
    path.join(SUB, '..', 'workflows', 'dnc_escalation_detector', 'dnc_escalation_detector.json'), 'utf8'));

  // nurture exemption (Melisa raised it, Nik promised the patch): the classify step must exclude
  // nurture campaign ids before anything downstream ever sees them -- a registry person showing up
  // in a nurture campaign is by design, never an escalation.
  const classify = wf.nodes.find((n) => n.name === 'Classify Active Cold Campaigns');
  assert.ok(classify.parameters.jsCode.includes('nurture.has(c.id)'),
    'must exclude nurture campaign ids from the active-cold classification');
  const cfg = wf.nodes.find((n) => n.name === 'CONFIG');
  const nurtureField = cfg.parameters.assignments.assignments.find((a) => a.name === 'nurture_campaign_ids');
  assert.ok(nurtureField, 'CONFIG must carry the nurture campaign id list');
  const nurtureIds = JSON.parse(nurtureField.value);
  assert.equal(nurtureIds.length, 7, 'expected the 7 verified @janeasystems.com-sender campaigns');

  // handle zero-active-cold-campaigns cleanly: the false branch must skip the registry read AND
  // the lead fetch entirely (never attempt an intersection against nothing), landing on a trivial
  // zero-state item instead -- both paths converge on ONE merge, same double-fire-safe shape as
  // every other Merge in this project.
  const gateOut = wf.connections['Any Active Cold Campaigns?'].main;
  assert.equal(gateOut[0][0].node, 'Get Registry Active Rows');
  assert.equal(gateOut[1][0].node, 'Zero State');
  const mergeNode = wf.nodes.find((n) => n.name === 'Merge Campaign Paths');
  assert.equal(mergeNode.parameters.mode, 'append');
  assert.equal(mergeNode.parameters.numberInputs, 2);
  assert.equal(wf.connections['Aggregate Hits'].main[0][0].index, 0);
  assert.equal(wf.connections['Zero State'].main[0][0].index, 1);

  // the registry read must be a full returnAll scan, not the default-paginated dt_get() helper --
  // this project already burned itself once on a silent undercount from an unproven list read
  // (the archived-leads blind spot); a capped registry scan here would be the same mistake again.
  const regNode = wf.nodes.find((n) => n.name === 'Get Registry Active Rows');
  assert.equal(regNode.parameters.returnAll, true);

  // silent if zero: the "Any Hits?" false branch must be a true dead end -- no post at all.
  const hitsGate = wf.connections['Any Hits?'].main;
  assert.ok(hitsGate[1].length === 0, 'zero-hit branch must have zero outgoing connections');

  // ALERT-ONLY today: no Pipedrive/Smartlead write or pause action anywhere in this build --
  // auto-pause is explicitly next week's work, not today's.
  assert.ok(!wf.nodes.some((n) => n.type === 'n8n-nodes-base.httpRequest'
    && ['PATCH', 'PUT', 'POST', 'DELETE'].includes(n.parameters.method)),
    'detector must be read-only today -- no write/pause HTTP call of any kind');

  // daily heartbeat, independent of the hourly trigger, hardcoded to telemetry (same pattern as
  // S3's watcher -- silence must stay distinguishable from a dead detector).
  const heartbeatTimer = wf.nodes.find((n) => n.name === 'Heartbeat Timer');
  assert.ok(heartbeatTimer);
  assert.equal(heartbeatTimer.type, 'n8n-nodes-base.scheduleTrigger');
  const heartbeatPost = wf.nodes.find((n) => n.name === 'Heartbeat Post');
  assert.ok(heartbeatPost.parameters.jsCode.includes('C0BQM1X9ZUY'),
    'heartbeat channel must be hardcoded to telemetry, not read from a mutable CONFIG value');

  // no dead ends on the reporting path.
  assert.equal(wf.connections['Combine'].main[0][0].node, 'Any Hits?');
});

t('DNC__UpsertLedger__v1: source_signal fills-or-unions, never downgrades to a single signal (2026-08-12)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, 'DNC__UpsertLedger__v1.json'), 'utf8'));
  const decide = wf.nodes.find((n) => n.name === 'Decide');
  const js = decide.parameters.jsCode;
  assert.ok(js.includes("existingSig === incSig) ? incSig : 'both'"),
    "must union to 'both' on a differing second signal, not overwrite the first");
  const upValue = wf.nodes.find((n) => n.name === 'Upsert' || n.name === 'Insert' || n.name === 'Update');
  // source_signal must appear SOMEWHERE in the dataTable write value maps -- find any node whose
  // columns.value includes it, rather than assuming a specific node name.
  const anyWriteHasIt = wf.nodes.some((n) => n.parameters && n.parameters.columns
    && n.parameters.columns.value && Object.prototype.hasOwnProperty.call(n.parameters.columns.value, 'source_signal'));
  assert.ok(anyWriteHasIt, 'source_signal must be included in the ledger write, ready for the moment the column exists');
});

t('dnc_pre_add_gate v2: no subworkflow fan-out -- in-execution batch lookup, 4-way split correct (2026-08-26)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));

  // structural: incident #2's root cause was a per-row executeWorkflow spin-up -- v2 must have
  // ZERO executeWorkflow nodes. Direct dataTable query nodes replace it.
  const execNode = wf.nodes.find((n) => n.type === 'n8n-nodes-base.executeWorkflow');
  assert.equal(execNode, undefined, 'gate v2 must not call any subworkflow -- that spin-up was the memory/exec multiplier that crashed the instance');
  const dtNodes = wf.nodes.filter((n) => n.type === 'n8n-nodes-base.dataTable');
  // ONE lookup node (matchType anyCondition, both columns), not two-lookups-plus-Merge -- see
  // the v3 "byte-identical logic" / dt_get_or2 regression tests below for why (Merge("append")
  // does not reliably wait for both branches, silently misclassified Dennis as CLEAN).
  assert.ok(dtNodes.some((d) => d.name === 'Get Registry Match (Batch)'),
    'the single OR-condition lookup node must exist, fed the whole batch at once, no Merge barrier');
  assert.equal(wf.nodes.find((n) => n.name === 'Merge Lookups'), undefined,
    'Merge Lookups must not exist -- proven unreliable as a two-branch barrier for this graph shape');

  const classify = wf.nodes.find((n) => n.name === 'Classify Batch');
  assert.ok(classify, 'batch classify node must exist');
  const runClassifyBatch = (originals, found) => {
    const fn = new Function('$input', '$', classify.parameters.jsCode);
    const mockInput = { all: () => found.map((r) => ({ json: r })) };
    const mockDollar = (name) => { if (name === 'Normalize Batch') return { all: () => originals.map((r) => ({ json: r })) };
      if (name === 'Get Domain Blocklist') return { all: () => [] };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockInput, mockDollar);
  };
  const norm = (s) => ({ norm_v: 'v1', linkedin_url_norm: null, email_lc: s, identity_key: s });

  // 1. known opt-out -- explicit_opt_out is the strongest tier, must BLOCK.
  const optOutRow = { email: 'pii-89083fe8@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-89083fe8@example.invalid', norm: norm('pii-89083fe8@example.invalid') };
  const optOutFound = { id: 111, identity_key: 'pii-89083fe8@example.invalid', email_lc: 'pii-89083fe8@example.invalid', linkedin_url_norm: null,
    entry_type: 'explicit_opt_out', source: 'smartlead_category', status: 'active', added_at: '2026-01-01T00:00:00.000Z' };
  const r1 = runClassifyBatch([optOutRow], [optOutFound]).map((x) => x.json);
  assert.equal(r1[0].gate_result, 'BLOCKED');
  assert.equal(r1[0].registry_row_ref, 111);
  assert.ok(r1[0].reason.includes('explicit_opt_out'));
  assert.equal(r1[0].email, 'pii-89083fe8@example.invalid', 'original row fields must survive the classify step');

  // 2. known S4 (event_contacted) -- the WEAKEST reason tier, but still an active registry row --
  // must still BLOCK. A gate that only catches the strong signals isn't one.
  const s4Row = { linkedin_url: 'https://www.linkedin.com/in/pii-fb983e6c', li_key: 's4-example',
    em_key: '__DNC_NO_EM__', norm: { norm_v: 'v1', linkedin_url_norm: 's4-example', email_lc: null, identity_key: 's4-example' } };
  const s4Found = { id: 222, identity_key: 's4-example', email_lc: null, linkedin_url_norm: 's4-example',
    entry_type: 'manual', source: 'event_campaign', status: 'active', added_at: '2026-08-01T00:00:00.000Z' };
  const r2 = runClassifyBatch([s4Row], [s4Found]).map((x) => x.json);
  assert.equal(r2[0].gate_result, 'BLOCKED', 'the weakest reason tier must still block -- being IN the registry at all is the bar');
  assert.equal(r2[0].registry_row_ref, 222);

  // 3. clean row -- never in the registry (no found rows at all for it).
  const cleanRow = { email: 'pii-629908e2@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-629908e2@example.invalid', norm: norm('pii-629908e2@example.invalid') };
  const r3 = runClassifyBatch([cleanRow], []).map((x) => x.json);
  assert.equal(r3[0].gate_result, 'CLEAN');
  assert.equal(r3[0].registry_row_ref, null);
  assert.equal(r3[0].reason, null);

  // 4. alias case -- normalizeIdentityV1 (unit-tested elsewhere) already collapses format
  // variance into li_key/em_key before this step; the found row's own linkedin_url_norm must
  // still correlate correctly to BLOCK.
  const aliasRow = { linkedin_url: 'HTTPS://WWW.LinkedIn.com/in/Jane-Doe/?utm=x', li_key: 'jane-doe',
    em_key: '__DNC_NO_EM__', norm: { norm_v: 'v1', linkedin_url_norm: 'jane-doe', email_lc: null, identity_key: 'jane-doe' } };
  const aliasFound = { id: 333, identity_key: 'jane-doe', email_lc: null, linkedin_url_norm: 'jane-doe',
    entry_type: 'replied', source: 'heyreach_reply', status: 'active', added_at: '2026-06-01T00:00:00.000Z' };
  const r4 = runClassifyBatch([aliasRow], [aliasFound]).map((x) => x.json);
  assert.equal(r4[0].gate_result, 'BLOCKED', 'format variance in the input must not evade a real block');
  assert.equal(r4[0].identity_key, 'jane-doe');

  // 5. genuinely unresolvable (neither identifier).
  const noIdRow = { full_name: 'Some Person', li_key: '__DNC_NO_LI__', em_key: '__DNC_NO_EM__',
    norm: { norm_v: 'v1', linkedin_url_norm: null, email_lc: null, identity_key: null } };
  const r5 = runClassifyBatch([noIdRow], []).map((x) => x.json);
  assert.equal(r5[0].gate_result, 'UNRESOLVABLE');
  assert.equal(r5[0].registry_row_ref, null);

  // 6. batch correlation: TWO rows in the same call, only one of which is found -- proves
  // correlation is by the found row's OWN column value, not by array position/pairedItem, which
  // would silently misattribute one row's DNC status to another (a correctness bug far worse
  // than a performance one in a compliance gate).
  const batchClean = { email: 'pii-4b13e1e9@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-4b13e1e9@example.invalid', norm: norm('pii-4b13e1e9@example.invalid') };
  const batchBlocked = { email: 'pii-843addbd@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-843addbd@example.invalid', norm: norm('pii-843addbd@example.invalid') };
  const batchFound = { id: 444, identity_key: 'pii-843addbd@example.invalid', email_lc: 'pii-843addbd@example.invalid', linkedin_url_norm: null,
    entry_type: 'manual', source: 'x', status: 'active', added_at: '2026-01-01T00:00:00.000Z' };
  const r6 = runClassifyBatch([batchClean, batchBlocked], [batchFound]).map((x) => x.json);
  assert.equal(r6.find((r) => r.email === 'pii-4b13e1e9@example.invalid').gate_result, 'CLEAN');
  assert.equal(r6.find((r) => r.email === 'pii-843addbd@example.invalid').gate_result, 'BLOCKED');

  // internal working fields must not leak into the response Clay/Stefan parse.
  assert.equal(r1[0].norm, undefined, 'internal norm object must not leak into the response');
  assert.equal(r1[0].li_key, undefined, 'internal li_key must not leak into the response');
});

t('dnc_pre_add_gate v3: own-domain guard -- @janeasystems.com always OWN_TEAM, wins over CLEAN and over employee_connection BLOCKED (2026-08-26, Stefan/Noah Keimach)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const classify = wf.nodes.find((n) => n.name === 'Classify Batch');
  const runClassifyBatch = (originals, found) => {
    const fn = new Function('$input', '$', classify.parameters.jsCode);
    const mockInput = { all: () => found.map((r) => ({ json: r })) };
    const mockDollar = (name) => { if (name === 'Normalize Batch') return { all: () => originals.map((r) => ({ json: r })) };
      if (name === 'Get Domain Blocklist') return { all: () => [] };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockInput, mockDollar);
  };

  // 1. own-team row with NO registry entry at all -- would otherwise be plain CLEAN. Must come
  // back OWN_TEAM instead, since a Janea employee must never enter a campaign list regardless of
  // registry presence.
  const ownRow = { email: 'noah.keimach@janeasystems.com', li_key: '__DNC_NO_LI__',
    em_key: 'noah.keimach@janeasystems.com',
    norm: { norm_v: 'v1', linkedin_url_norm: null, email_lc: 'noah.keimach@janeasystems.com', identity_key: 'noah.keimach@janeasystems.com' } };
  const r1 = runClassifyBatch([ownRow], []).map((x) => x.json);
  assert.equal(r1[0].gate_result, 'OWN_TEAM', 'own-domain row with no registry hit must not fall through to plain CLEAN');
  assert.equal(r1[0].reason, 'own_team — exclude from any campaign list');
  assert.equal(r1[0].registry_row_ref, null);

  // 2. own-team row that ALSO has an active employee_connection registry row -- must still report
  // OWN_TEAM, not the plain employee_connection BLOCKED a personal-connection import would get.
  // Precedence matters here: Stefan's exact complaint was seeing a plain employee_connection block
  // for a teammate instead of a distinguishable own-team result.
  const ownBlockedRow = { email: 'noah.keimach@janeasystems.com', li_key: '__DNC_NO_LI__',
    em_key: 'noah.keimach@janeasystems.com',
    norm: { norm_v: 'v1', linkedin_url_norm: null, email_lc: 'noah.keimach@janeasystems.com', identity_key: 'noah.keimach@janeasystems.com' } };
  const ownFound = { id: 555, identity_key: 'noah.keimach@janeasystems.com', email_lc: 'noah.keimach@janeasystems.com',
    linkedin_url_norm: null, entry_type: 'employee_connection', source: 'onboarding_import:Noah Keimach', status: 'active',
    added_at: '2026-08-07T00:00:00.000Z' };
  const r2 = runClassifyBatch([ownBlockedRow], [ownFound]).map((x) => x.json);
  assert.equal(r2[0].gate_result, 'OWN_TEAM', 'own-domain guard must win over an ordinary employee_connection BLOCKED outcome');
  assert.notEqual(r2[0].reason, undefined);
  assert.ok(!r2[0].reason.includes('employee_connection'), 'must not fall back to the generic employee_connection reason text');

  // 3. an ordinary external row on a real personal-connection import must be UNAFFECTED --
  // regression guard that the own-domain check is domain-scoped, not accidentally broad.
  const externalRow = { email: 'pii-2d424803@example.invalid', li_key: '__DNC_NO_LI__',
    em_key: 'pii-2d424803@example.invalid',
    norm: { norm_v: 'v1', linkedin_url_norm: null, email_lc: 'pii-2d424803@example.invalid', identity_key: 'pii-2d424803@example.invalid' } };
  const externalFound = { id: 556, identity_key: 'pii-2d424803@example.invalid', email_lc: 'pii-2d424803@example.invalid',
    linkedin_url_norm: null, entry_type: 'employee_connection', source: 'onboarding_import:Toby', status: 'active',
    added_at: '2026-08-07T00:00:00.000Z' };
  const r3 = runClassifyBatch([externalRow], [externalFound]).map((x) => x.json);
  assert.equal(r3[0].gate_result, 'BLOCKED', 'a real external personal connection must still get an ordinary BLOCKED, not OWN_TEAM');
  assert.ok(r3[0].reason.includes('employee_connection'));

  // 4. own-team logic must also live in the drainer's copy of the SAME classify code (byte-
  // identical sharing tested elsewhere) -- confirm the drainer workflow's Classify Batch node
  // contains the same OWN_DOMAIN guard, not a stale pre-patch copy.
  const drainerWf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_gate_queue_drainer', 'dnc_gate_queue_drainer.json'), 'utf8'));
  const drainerClassify = drainerWf.nodes.find((n) => n.name === 'Classify Batch');
  assert.equal(drainerClassify.parameters.jsCode, classify.parameters.jsCode,
    'gate and drainer must still share byte-identical classify logic after the own-domain guard edit');
  assert.ok(classify.parameters.jsCode.includes('OWN_DOMAIN'), 'own-domain guard constant must be present in the generated node');
});

t('dnc_pre_add_gate v3: company-domain block -- banned domain BLOCKS regardless of person history, fail-open when the blocklist read fails (2026-09-09, Company DNC)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const classify = wf.nodes.find((n) => n.name === 'Classify Batch');
  const norm = (s) => ({ norm_v: 'v1', linkedin_url_norm: null, email_lc: s, identity_key: s });
  const runClassifyBatch = (originals, found, domainRows) => {
    const fn = new Function('$input', '$', classify.parameters.jsCode);
    const mockInput = { all: () => found.map((r) => ({ json: r })) };
    const mockDollar = (name) => {
      if (name === 'Normalize Batch') return { all: () => originals.map((r) => ({ json: r })) };
      if (name === 'Get Domain Blocklist') return { all: () => domainRows.map((r) => ({ json: r })) };
      throw new Error('unexpected $() reference: ' + name);
    };
    return fn(mockInput, mockDollar);
  };

  // 1. banned domain, person has NO registry history at all -- must still BLOCK.
  const bannedRow = { email: 'pii-55e57410@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-55e57410@example.invalid', norm: norm('pii-55e57410@example.invalid') };
  const domainRows = [{ domain: 'evilcorp.com', status: 'active', added_at: '2026-06-29T00:00:00.000Z', source: 'clay_company_dnc_import', reason: null }];
  const r1 = runClassifyBatch([bannedRow], [], domainRows).map((x) => x.json);
  assert.equal(r1[0].gate_result, 'BLOCKED', 'a banned company domain must block even with zero person-level history');
  assert.equal(r1[0].reason, 'company_dnc / evilcorp.com');
  assert.equal(r1[0].registry_row_ref, null);

  // 2. banned domain wins over a plain CLEAN registry outcome too (in addition to person checks,
  // not instead of them -- but when the person is otherwise clean, the domain block still fires).
  const bannedClean = { email: 'pii-2d566d6d@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-2d566d6d@example.invalid', norm: norm('pii-2d566d6d@example.invalid') };
  const r2 = runClassifyBatch([bannedClean], [], domainRows).map((x) => x.json);
  assert.equal(r2[0].gate_result, 'BLOCKED');

  // 2b. person CLEAN specifically via a found-but-removed registry row (would otherwise answer
  // "was manual until ..., currently clean") -- company_dnc must still win outright, not just when
  // there's zero registry history at all (distinct from case 2 above).
  const cleanWithHistory = { email: 'pii-85d78beb@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-85d78beb@example.invalid', norm: norm('pii-85d78beb@example.invalid') };
  const removedHistoryRow = { id: 999, identity_key: 'pii-85d78beb@example.invalid', email_lc: 'pii-85d78beb@example.invalid', linkedin_url_norm: null,
    entry_type: 'manual', source: 'onboarding_import:x', status: 'removed', removed_at: '2026-01-01T00:00:00.000Z', added_at: '2025-01-01T00:00:00.000Z' };
  const r2b = runClassifyBatch([cleanWithHistory], [removedHistoryRow], domainRows).map((x) => x.json);
  assert.equal(r2b[0].gate_result, 'BLOCKED', 'company_dnc must override even a "was X, currently clean" person outcome, not just a bare CLEAN');
  assert.equal(r2b[0].reason, 'company_dnc / evilcorp.com');

  // 3. same domain string but the entry is status='removed' (tombstoned block) -- must NOT block.
  const removedDomainRows = [{ domain: 'evilcorp.com', status: 'removed', added_at: '2026-06-29T00:00:00.000Z', source: 'clay_company_dnc_import', reason: null }];
  const r3 = runClassifyBatch([bannedRow], [], removedDomainRows).map((x) => x.json);
  assert.equal(r3[0].gate_result, 'CLEAN', 'a removed (tombstoned) domain block must not fire');

  // 4. an ordinary, non-banned domain must be unaffected.
  const cleanRow = { email: 'pii-e19530e7@example.invalid', li_key: '__DNC_NO_LI__', em_key: 'pii-e19530e7@example.invalid', norm: norm('pii-e19530e7@example.invalid') };
  const r4 = runClassifyBatch([cleanRow], [], domainRows).map((x) => x.json);
  assert.equal(r4[0].gate_result, 'CLEAN');

  // 5. fail-open: the blocklist read failed (non-uniform error shape -- same class of bug already
  // fixed once elsewhere: a row that doesn't actually look like a real domain row, e.g. an echoed
  // non-row item). Must degrade to "nothing is blocked", never crash, never falsely block.
  const badShapeRows = [{ error: "Could not find the data table: 'dnc_domains'" }];
  const r5 = runClassifyBatch([bannedRow], [], badShapeRows).map((x) => x.json);
  assert.equal(r5[0].gate_result, 'CLEAN', 'a failed/malformed blocklist read must fail OPEN (no block), not crash or false-block');

  // 6. own-domain guard still wins over company-domain block (checked first) -- a Janea address
  // must never read as company_dnc even in the freak case janeasystems.com is itself banned.
  const ownDomainBanned = [{ domain: 'janeasystems.com', status: 'active', added_at: '2026-01-01T00:00:00.000Z', source: 'clay_company_dnc_import', reason: null }];
  const ownRow = { email: 'nik@janeasystems.com', li_key: '__DNC_NO_LI__', em_key: 'nik@janeasystems.com', norm: norm('nik@janeasystems.com') };
  const r6 = runClassifyBatch([ownRow], [], ownDomainBanned).map((x) => x.json);
  assert.equal(r6[0].gate_result, 'OWN_TEAM', 'own-domain guard must still win even if janeasystems.com somehow appeared in the banned list');

  // 7. company-domain block must also live in the drainer's byte-identical classify copy.
  const drainerWf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_gate_queue_drainer', 'dnc_gate_queue_drainer.json'), 'utf8'));
  const drainerClassify = drainerWf.nodes.find((n) => n.name === 'Classify Batch');
  assert.equal(drainerClassify.parameters.jsCode, classify.parameters.jsCode);
  assert.ok(classify.parameters.jsCode.includes('bannedDomains'), 'company-domain block logic must be present in the generated node');
  const drainerDomainNode = drainerWf.nodes.find((n) => n.name === 'Get Domain Blocklist');
  assert.ok(drainerDomainNode, 'drainer must have its own Get Domain Blocklist node so the shared classify code\'s $() reference resolves');

  // 8. Get Domain Blocklist must be a true ANCESTOR of Classify Batch (chained sequentially),
  // never a parallel sibling -- found live 2026-09-09: a sibling branch has no execution-order
  // guarantee relative to Classify Batch's $() reference (unlike $('Normalize Batch'), which only
  // works because Normalize Batch IS an ancestor). BUT it must NOT feed directly into any node
  // that executes once-per-input-item (Get Registry Match (Batch), Fetch Pending Batch) --
  // found live 2026-09-14: chaining Get Domain Blocklist's 1,373-row output straight into
  // Get Registry Match (Batch) made THAT node re-invoke once per domain instead of once per
  // submitted row, causing 459 consecutive 30s-timeout monitor failures over ~5 days. The gate
  // routes it through Build Items (which ignores its own input via a named $('Webhook') ref); the
  // drainer routes it through a dedicated "Reset After Domains" swallow node (runOnceForAllItems,
  // ignores its own input, always emits exactly 1 item) before Fetch Pending Batch.
  const domainOut = wf.connections['Get Domain Blocklist'];
  assert.ok(domainOut, 'dnc_pre_add_gate: Get Domain Blocklist must have an outgoing connection (proves it is upstream of something, not a dead-end sibling)');
  assert.equal(domainOut.main[0][0].node, 'Build Items',
    'dnc_pre_add_gate: Get Domain Blocklist must feed into Build Items (which ignores its own input), making it a true ancestor of Classify Batch without amplifying Get Registry Match (Batch)');

  const drainerDomainOut = drainerWf.connections['Get Domain Blocklist'];
  assert.ok(drainerDomainOut, 'dnc_gate_queue_drainer: Get Domain Blocklist must have an outgoing connection (proves it is upstream of something, not a dead-end sibling)');
  assert.equal(drainerDomainOut.main[0][0].node, 'Reset After Domains',
    'dnc_gate_queue_drainer: Get Domain Blocklist must feed into a swallow node, never directly into a per-item-executing node like Fetch Pending Batch or Get Registry Match (Batch)');
  const resetNode = drainerWf.nodes.find((n) => n.name === 'Reset After Domains');
  assert.ok(resetNode, 'dnc_gate_queue_drainer: Reset After Domains node must exist');
  assert.equal(resetNode.parameters.mode, 'runOnceForAllItems',
    'Reset After Domains must run once total (ignoring the 1,373 domain rows), not once per row');

  for (const graph of [wf, drainerWf]) {
    // 9. alwaysOutputData is mandatory here -- found live 2026-09-09: a genuinely-empty-but-
    // working dnc_domains table (0 rows, no error) produced zero items, and because this node is
    // a true ANCESTOR of Classify Batch (point 8 above), zero items silently killed the entire
    // rest of the chain -- an empty gate response on every real submit call. Same root lesson as
    // filtered-read-needs-alwaysoutputdata, just missed here because only the throwaway
    // verification probe used it, not the real node definition.
    const domainNode = graph.nodes.find((n) => n.name === 'Get Domain Blocklist');
    assert.equal(domainNode.alwaysOutputData, true,
      graph.name + ': Get Domain Blocklist must set alwaysOutputData -- an empty (but successfully read) table must not silently kill the rest of the chain');
  }
});

t('dnc_pre_add_gate v2: hard 500-row cap rejects before any lookup, webhook body convention, no dead ends', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const build = wf.nodes.find((n) => n.name === 'Build Items');
  assert.ok(build.parameters.jsCode.includes("$('Webhook').first().json.body") ,
    'must read via $(\'Webhook\').first().json.body, not bare $json -- nodes now sit between Webhook and Build Items');

  const cap = wf.nodes.find((n) => n.name === 'Cap Check');
  const fn = new Function('$input', cap.parameters.jsCode);
  const many = Array.from({ length: 501 }, (_, i) => ({ json: { row_index: i } }));
  const overCap = fn({ all: () => many })[0].json;
  assert.equal(overCap.over_cap, true, '501 rows must trip the cap');
  assert.equal(overCap.count, 501);

  const few = Array.from({ length: 500 }, (_, i) => ({ json: { row_index: i } }));
  const underCap = fn({ all: () => few });
  assert.equal(underCap.length, 500, 'exactly 500 rows must pass through unrejected');
  assert.equal(underCap[0].json.over_cap, false);

  const report = wf.nodes.find((n) => n.name === 'Build Report');
  const js = report.parameters.jsCode;
  assert.ok(js.includes('by.CLEAN') && js.includes('by.BLOCKED') && js.includes('by.UNRESOLVABLE'));
  assert.ok(js.includes('counts'), 'must report counts alongside the full lists');
  assert.ok(js.includes('duration_ms') && js.includes('row_count'),
    'must self-report duration/row_count so the liveness monitor can track real headroom');

  // must be wired straight through, no dead ends, and the over-cap branch must short-circuit
  // BEFORE Normalize Batch (no lookup work for a rejected call). Webhook now routes through
  // "Is Retrieve?" first (gate v3) before reaching Mark Start on the submit path. Get Domain
  // Blocklist sits between Mark Start and Build Items (2026-09-14 latency-incident fix) -- it
  // must fire exactly once per gate call (Mark Start always carries 1 item), and Build Items
  // ignores its own direct input ($('Webhook') named ref) so the blocklist's 1,373-row output
  // never pollutes downstream per-row cardinality.
  assert.equal(wf.connections['Webhook'].main[0][0].node, 'Is Retrieve?');
  assert.equal(wf.connections['Is Retrieve?'].main[1][0].node, 'Mark Start');
  assert.equal(wf.connections['Mark Start'].main[0][0].node, 'Get Domain Blocklist');
  assert.equal(wf.connections['Get Domain Blocklist'].main[0][0].node, 'Build Items');
  assert.equal(wf.connections['Build Items'].main[0][0].node, 'Cap Check');
  assert.equal(wf.connections['Cap Check'].main[0][0].node, 'Over Cap?');
  assert.equal(wf.connections['Over Cap?'].main[0][0].node, 'Respond Over Cap');
  assert.equal(wf.connections['Over Cap?'].main[1][0].node, 'Normalize Batch');
  assert.equal(wf.connections['Normalize Batch'].main[0][0].node, 'Get Registry Match (Batch)',
    'Get Registry Match (Batch) must be fed directly by Normalize Batch (one invocation per submitted row), never by Get Domain Blocklist (which would re-invoke it once per domain -- the 2026-09-14 latency incident)');
  assert.equal(wf.connections['Get Registry Match (Batch)'].main[0][0].node, 'Classify Batch');
  assert.equal(wf.connections['Classify Batch'].main[0][0].node, 'Build Report');
  assert.equal(wf.connections['Build Report'].main[0][0].node, 'Respond');
});

t('dnc_pre_add_gate v2: single-row calls get a flat top-level result (Stefan CSV finding, 2026-08-26)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const report = wf.nodes.find((n) => n.name === 'Build Report');
  const runReport = (rows, startedAt) => {
    const fn = new Function('$input', '$', report.parameters.jsCode);
    const mockInput = { all: () => rows.map((r) => ({ json: r })) };
    const mockDollar = (name) => { if (name === 'Mark Start') return { first: () => ({ json: { started_at: startedAt } }) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockInput, mockDollar);
  };

  // real finding: Stefan's live Clay export showed 15 rows had actually fired (HTTP 200), but
  // only the ONE that came back BLOCKED populated Clay's Gate Result/Reason columns -- the other
  // 14 (all CLEAN) came back empty. Clay's per-row column can only sensibly map a FLAT field, and
  // clean/blocked/unresolvable/rows are all bucketed -- nothing flat existed for the CLEAN case.
  const cleanRow = { row_index: 0, gate_result: 'CLEAN', reason: null, registry_row_ref: null, identity_key: 'pii-fd989748@example.invalid' };
  const r1 = runReport([cleanRow], Date.now() - 100)[0].json;
  assert.equal(r1.gate_result, 'CLEAN', 'a single CLEAN row must still populate a flat top-level gate_result for Clay to map');
  assert.equal(r1.reason, null);

  const blockedRow = { row_index: 0, gate_result: 'BLOCKED', reason: 'manual / x', registry_row_ref: 31517, identity_key: 'pii-fd989748@example.invalid' };
  const r2 = runReport([blockedRow], Date.now() - 100)[0].json;
  assert.equal(r2.gate_result, 'BLOCKED');
  assert.equal(r2.registry_row_ref, 31517);

  // a batch (2+ rows) must NOT get a misleading flat top-level result -- there is no single
  // "the" outcome for a multi-row call, so those fields must be absent, not silently wrong.
  const r3 = runReport([cleanRow, blockedRow], Date.now() - 100)[0].json;
  assert.equal('gate_result' in r3, false, 'batch calls must not carry a flat gate_result (ambiguous for 2+ rows)');
  assert.equal(r3.counts.total, 2, 'batch counts/buckets remain unchanged for existing consumers');
});

t('dnc_pre_add_gate v3: gate and drainer classify with the BYTE-IDENTICAL logic (no drift, 2026-08-26)', () => {
  const gateWf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const drainerWf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_gate_queue_drainer', 'dnc_gate_queue_drainer.json'), 'utf8'));
  const gateClassify = gateWf.nodes.find((n) => n.name === 'Classify Batch');
  const drainerClassify = drainerWf.nodes.find((n) => n.name === 'Classify Batch');
  assert.ok(gateClassify && drainerClassify, 'both workflows must have a Classify Batch node');
  assert.equal(drainerClassify.parameters.jsCode, gateClassify.parameters.jsCode,
    'the sync path and the drainer must use the EXACT same matching logic -- any divergence here ' +
    'means a row could get a different verdict depending on which path happened to process it');

  // structural: drainer must have zero executeWorkflow nodes too (same v2 lesson applies to the
  // background path, not just the request path).
  const execNode = drainerWf.nodes.find((n) => n.type === 'n8n-nodes-base.executeWorkflow');
  assert.equal(execNode, undefined, 'drainer must not spin up subworkflows either');
});

t('dnc_pre_add_gate v3: Barry fixture resolves correctly through the DRAINER path too (2026-08-26)', () => {
  const drainerWf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_gate_queue_drainer', 'dnc_gate_queue_drainer.json'), 'utf8'));
  const reconstruct = drainerWf.nodes.find((n) => n.name === 'Normalize Batch');
  const classify = drainerWf.nodes.find((n) => n.name === 'Classify Batch');

  // simulate one stored queue row for Dennis (the known-blocked fixture), as the drainer would
  // fetch it from dnc_gate_queue: payload_json holds the ALREADY-normalized item from enqueue time.
  const storedRow = {
    id: 7, row_key: 'pii-d50f3785@example.invalid',
    payload_json: JSON.stringify({
      email: 'pii-d50f3785@example.invalid', row_index: 0,
      norm: { identity_key: 'pii-d50f3785@example.invalid' },
      li_key: '__DNC_NO_LI__', em_key: 'pii-d50f3785@example.invalid',
    }),
  };
  const reconstructFn = new Function('$input', reconstruct.parameters.jsCode);
  const reconstructed = reconstructFn({ all: () => [{ json: storedRow }] });
  assert.equal(reconstructed[0].json.__row_key, 'pii-d50f3785@example.invalid');
  assert.equal(reconstructed[0].json.email, 'pii-d50f3785@example.invalid');

  const found = { id: 31517, identity_key: 'pii-d50f3785@example.invalid',
    email_lc: 'pii-d50f3785@example.invalid', linkedin_url_norm: null,
    entry_type: 'manual', source: 'pipedrive_personal', status: 'active', added_at: '2026-01-01T00:00:00.000Z' };
  const classifyFn = new Function('$input', '$', classify.parameters.jsCode);
  const mockDollar = (name) => { if (name === 'Normalize Batch') return { all: () => reconstructed };
    if (name === 'Get Domain Blocklist') return { all: () => [] };
    throw new Error('unexpected $() reference: ' + name); };
  const result = classifyFn({ all: () => [{ json: found }] }, mockDollar)[0].json;
  assert.equal(result.gate_result, 'BLOCKED');
  assert.equal(result.registry_row_ref, 31517);
  assert.equal(result.__row_key, 'pii-d50f3785@example.invalid', '__row_key must survive classify for Write Back Results to key on');
});

t('dnc_pre_add_gate_monitor: stuck-drainer detection alerts once, re-arms when depth drops (2026-08-26)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate_monitor', 'dnc_pre_add_gate_monitor.json'), 'utf8'));
  const report = wf.nodes.find((n) => n.name === 'Track + Report');
  const runCheck = (sd, queueDepth, healthy, rowsOverride) => {
    const fn = new Function('$json', '$getWorkflowStaticData', '$', report.parameters.jsCode);
    const mockGetSd = () => sd;
    const queueRows = rowsOverride || Array.from({ length: queueDepth },
      (_, i) => ({ row_key: 'k' + i, status: 'pending' }));
    const mockDollar = (name) => { if (name === 'Check Queue') return { all: () => queueRows.map((r) => ({ json: r })) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn({ healthy, counts: { total: 2, clean: 1, blocked: 1, unresolvable: 0 } }, mockGetSd, mockDollar)[0].json;
  };

  const sd = {};
  // 4 consecutive checks, depth never drops (10 -> 12 -> 15 -> 15) -- a real stuck drainer.
  let r;
  r = runCheck(sd, 10, true); assert.equal(r.should_alert_queue, false, 'not enough history yet');
  r = runCheck(sd, 12, true); assert.equal(r.should_alert_queue, false);
  r = runCheck(sd, 15, true); assert.equal(r.should_alert_queue, false);
  r = runCheck(sd, 15, true);
  assert.equal(r.queue_stuck, true, '4th non-decreasing reading in a row must flag stuck');
  assert.equal(r.should_alert_queue, true, 'first stuck detection must alert');

  // still stuck next tick -- must NOT alert again (avoid spamming every 15 min).
  r = runCheck(sd, 16, true);
  assert.equal(r.should_alert_queue, false, 'already-alerted episode must not re-fire while still stuck');

  // depth actually drops -- re-arms for a future episode.
  r = runCheck(sd, 2, true);
  assert.equal(r.queue_stuck, false, 'a real drop must clear the stuck flag');
});

t('dnc_pre_add_gate_monitor: depth-0 predicate fix -- idle queue never flags stuck, missing-table failure never masquerades as a healthy 0 (2026-08-28)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate_monitor', 'dnc_pre_add_gate_monitor.json'), 'utf8'));
  const report = wf.nodes.find((n) => n.name === 'Track + Report');
  const runCheck = (sd, rows) => {
    const fn = new Function('$json', '$getWorkflowStaticData', '$', report.parameters.jsCode);
    const mockDollar = (name) => { if (name === 'Check Queue') return { all: () => rows.map((r) => ({ json: r })) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn({ healthy: true, counts: { total: 2, clean: 1, blocked: 1, unresolvable: 0 } }, () => sd, mockDollar)[0].json;
  };

  // 1. genuinely drained queue, 4 consecutive empty reads -- must read as idle, never stuck, and
  // queue_ok must be true (an empty array is a legitimate, healthy result, not a failure).
  const sd1 = {};
  let r;
  for (let i = 0; i < 4; i++) r = runCheck(sd1, []);
  assert.equal(r.queue_depth, 0, 'empty pending-row read must report depth 0');
  assert.equal(r.queue_ok, true, 'an empty array is a healthy read, not a failure');
  assert.equal(r.queue_stuck, false, 'depth 0 across the whole window must never be stuck');
  assert.equal(r.should_alert_queue, false);

  // 2. the actual bug this fixes: "Check Queue" fails by echoing a non-row item (no status/
  // row_key -- e.g. the poll timer's own trigger item), NOT the {error:"..."} shape the old
  // negative check only recognized. Old code: length===1 && !row.error -> queueOk WRONGLY true,
  // depth WRONGLY 1, and if this repeats every tick it would falsely alert as permanently stuck.
  // New code: positive shape check on status+row_key -> must read as UNKNOWN, never a phantom
  // nonzero depth, and must never alert as stuck since it's never resolved to a real depth.
  const sd2 = {};
  for (let i = 0; i < 4; i++) r = runCheck(sd2, [{ timestamp: '2026-08-28T00:00:00Z' }]);
  assert.equal(r.queue_depth, null, 'a non-row echoed item must never be counted as 1 real pending row');
  assert.equal(r.queue_ok, false);
  assert.equal(r.queue_stuck, false, 'an unresolvable read must never falsely alert as a stuck queue');

  // 3. the documented {error:"..."} shape must also still resolve to unknown, not stuck (regression
  // guard for the shape this project has actually observed live: "Could not find the data table").
  const sd3 = {};
  for (let i = 0; i < 4; i++) r = runCheck(sd3, [{ error: "Could not find the data table: 'dnc_gate_queue'" }]);
  assert.equal(r.queue_depth, null);
  assert.equal(r.queue_ok, false);
  assert.equal(r.queue_stuck, false);

  // 4. a real backlog draining down TO zero must clear stuck on the very tick it hits 0, not
  // linger stuck because zero still satisfies some leftover >0-less condition.
  const sd4 = {};
  runCheck(sd4, Array.from({ length: 8 }, (_, i) => ({ row_key: 'k' + i, status: 'pending' })));
  runCheck(sd4, Array.from({ length: 5 }, (_, i) => ({ row_key: 'k' + i, status: 'pending' })));
  runCheck(sd4, Array.from({ length: 2 }, (_, i) => ({ row_key: 'k' + i, status: 'pending' })));
  r = runCheck(sd4, []);
  assert.equal(r.queue_depth, 0);
  assert.equal(r.queue_stuck, false, 'hitting 0 must clear stuck even mid-drain, not linger');
});

t('dnc_pre_add_gate v3: row_key stripped from response, single-row convenience fields (2026-09-09, post-queue-removal)', () => {
  // 2026-09-02: Nik removed the whole queue apparatus (dnc_gate_queue never existed, the drainer
  // never ran once -- every "queued" answer was a promise that could never be kept). Log Ingress,
  // Mark Sync Done, and the sync/queue split are gone with it; this test keeps only what still
  // applies post-removal -- row_key must still never leak into what Clay/Stefan see.
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const report = wf.nodes.find((n) => n.name === 'Build Report');
  assert.ok(report.parameters.jsCode.includes('delete r.row_key'),
    'row_key must be stripped from the response Clay parses');

  const runReport = (rows) => {
    const fn = new Function('$input', '$', report.parameters.jsCode);
    const mockInput = { all: () => rows.map((r) => ({ json: r })) };
    const mockDollar = (name) => { if (name === 'Mark Start') return { first: () => ({ json: { started_at: Date.now() - 5 } }) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockInput, mockDollar)[0].json;
  };
  const r = runReport([{ row_index: 0, row_key: 'pii-fd989748@example.invalid', gate_result: 'CLEAN', reason: null, registry_row_ref: null, identity_key: 'pii-fd989748@example.invalid' }]);
  assert.equal('row_key' in r, false, 'top-level single-row response must not carry row_key');
  assert.equal('row_key' in r.clean[0], false, 'row_key must not leak into the clean[] bucket either');
});

t('dnc_pre_add_gate v3: retrieve path returns an honest 410, not a fake queue lookup (2026-09-09, post-queue-removal)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'), 'utf8'));
  const removed = wf.nodes.find((n) => n.name === 'Retrieve Removed');
  assert.ok(removed, 'Retrieve Removed must exist -- the retrieve branch must not silently query a nonexistent queue table');
  const fn = new Function('$input', removed.parameters.jsCode);
  const r = fn({ all: () => [{ json: {} }] })[0].json;
  assert.equal(r.http_status, 410);
  assert.equal(r.error, 'retrieve_removed');
  assert.equal(wf.connections['Is Retrieve?'].main[0][0].node, 'Retrieve Removed',
    'the retrieve branch must route here, not to a queue lookup');
  assert.equal(wf.connections['Retrieve Removed'].main[0][0].node, 'Respond Retrieve');
});

t('dnc_s4_retirement_removal: dry_run defaults true, tombstone not delete, correct reason tag (2026-08-26)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_s4_retirement_removal', 'dnc_s4_retirement_removal.json'), 'utf8'));
  const build = wf.nodes.find((n) => n.name === 'Build Items');
  assert.ok(build.parameters.jsCode.includes("$('Webhook').first().json.body"),
    'must read via $(\'Webhook\').first().json.body, not bare $json');

  const runBuild = (body) => {
    const fn = new Function('$', '$execution', build.parameters.jsCode);
    const mockDollar = (name) => { if (name === 'Webhook') return { first: () => ({ json: { body } }) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockDollar, { id: 'test' });
  };

  // dry_run omitted entirely -> must default to true (write requires explicit false)
  const r1 = runBuild({ row_ids: [1, 2, 3] });
  assert.equal(r1.length, 3);
  assert.ok(r1.every((i) => i.json.dry_run === true), 'dry_run must default true when not specified');
  assert.ok(r1.every((i) => i.json.removed_reason === 'rule_change_2026-08-26_melisa'),
    'removed_reason must carry the exact ruling tag for audit');

  // explicit dry_run:false -> real write path
  const r2 = runBuild({ row_ids: [7138], dry_run: false });
  assert.equal(r2[0].json.dry_run, false);

  // empty row_ids must refuse, not silently no-op or (worse) touch everything
  assert.throws(() => runBuild({ row_ids: [] }), /non-empty array/);
  assert.throws(() => runBuild({}), /non-empty array/);

  // tombstone, never delete: Update Row must set status, never call deleteRows
  const updateNode = wf.nodes.find((n) => n.name === 'Update Row');
  assert.equal(updateNode.parameters.operation, 'update', 'must be an UPDATE (tombstone), never deleteRows');
  assert.equal(updateNode.parameters.columns.value.status, '=removed');
  assert.ok(String(updateNode.parameters.columns.value.removed_reason).includes('$json.removed_reason'));

  // report correctly distinguishes dry-run from real write regardless of which path fed it
  const report = wf.nodes.find((n) => n.name === 'Build Report');
  const runReport = (inputRows, dryRun) => {
    const fn = new Function('$input', '$', report.parameters.jsCode);
    const mockInput = { all: () => inputRows.map((r) => ({ json: r })) };
    const mockDollar = (name) => { if (name === 'Build Items') return { first: () => ({ json: { dry_run: dryRun } }) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockInput, mockDollar)[0].json;
  };
  // real-write branch: Update Row's own output doesn't carry dry_run at all -- report must not
  // be fooled by that into misreporting a write as a dry run.
  const writeResult = runReport([{ status: 'removed', removed_at: '2026-08-26T00:00:00Z' }], false);
  assert.equal(writeResult.dry_run, false);
  assert.ok(writeResult.note.includes('WRITTEN'));
  const dryResult = runReport([{ dry_run: true, id: 1 }], true);
  assert.equal(dryResult.dry_run, true);
  assert.ok(dryResult.note.includes('DRY RUN'));

  // no dead ends
  assert.equal(wf.connections['Webhook'].main[0][0].node, 'Build Items');
  assert.equal(wf.connections['Dry Run?'].main[0][0].node, 'Report Dry Run');
  assert.equal(wf.connections['Dry Run?'].main[1][0].node, 'Update Row');
  assert.equal(wf.connections['Build Report'].main[0][0].node, 'Respond');
});

t('dnc_archived_responders_import: dry_run defaults true, rejects invalid reason / missing reply_category / no identity, mode:each, no dead ends (2026-08-28)', () => {
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_archived_responders_import', 'dnc_archived_responders_import.json'), 'utf8'));
  const build = wf.nodes.find((n) => n.name === 'Build Items');
  assert.ok(build.parameters.jsCode.includes("$('Webhook').first().json.body"));

  const runBuild = (body) => {
    const fn = new Function('$', '$execution', build.parameters.jsCode);
    const mockDollar = (name) => { if (name === 'Webhook') return { first: () => ({ json: { body } }) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockDollar, { id: 'test' });
  };

  const goodRow = { email: 'pii-fd989748@example.invalid', reason: 'reply_dnc', reply_category: 'not_interested', source: 's', source_ref: 'r' };
  const optOutRow = { email: 'z@y.com', reason: 'unsubscribe', source: 's', source_ref: 'r' };

  // dry_run omitted -> defaults true
  const r1 = runBuild({ rows: [goodRow, optOutRow] });
  assert.equal(r1.length, 2);
  assert.ok(r1.every((i) => i.json.dry_run === true), 'dry_run must default true');

  // explicit false -> real write path
  const r2 = runBuild({ rows: [goodRow], dry_run: false });
  assert.equal(r2[0].json.dry_run, false);

  // empty/missing rows must refuse
  assert.throws(() => runBuild({ rows: [] }), /non-empty array/);
  assert.throws(() => runBuild({}), /non-empty array/);

  // the exact real-world bug this driver guards against: 'explicit_opt_out' is an ENTRY_TYPE
  // value from reason_v1.js, not a valid `reason` -- the correct reason for a stop-contact
  // signal is 'unsubscribe'. A row sent with the wrong one must be rejected here, before firing,
  // not discovered as a rejected write mid-batch.
  assert.throws(() => runBuild({ rows: [{ email: 'pii-da50e332@example.invalid', reason: 'explicit_opt_out', source: 's', source_ref: 'r' }] }),
    /invalid reason explicit_opt_out/);

  // reply_dnc without reply_category must be rejected here too (the 2026-08-14 schema assert
  // this project already got burned by once -- catch it in the batch validator, not per-row
  // deep into a live executeWorkflow fan-out).
  assert.throws(() => runBuild({ rows: [{ email: 'pii-da50e332@example.invalid', reason: 'reply_dnc', source: 's', source_ref: 'r' }] }),
    /reply_dnc requires reply_category/);

  // no email and no linkedin_url -- nothing to resolve an identity against, must be rejected
  // rather than silently attempted (mirrors "no identifiers -> honest unmatched", never invented).
  assert.throws(() => runBuild({ rows: [{ full_name: 'Nobody', reason: 'reply_dnc', reply_category: 'x', source: 's', source_ref: 'r' }] }),
    /no email\/linkedin_url/);

  // mode:each, not once (the exact class of silent-drop bug this project already hit live once).
  const execNode = wf.nodes.find((n) => n.name === 'Call UpsertLedger');
  assert.equal(execNode.parameters.mode, 'each');
  assert.equal(execNode.parameters.workflowId.value, 'RolYGL3J2CNg6Yp3', 'must call the real UpsertLedger id');

  // no dead ends. UpsertLedger has 3 disconnected terminal paths (conflict alert, real upsert,
  // idempotent noop) -- executeWorkflow(mode:each) surfaces each as its own output branch, found
  // live 2026-08-28 when a real fire under-reported "processed: 1" instead of 315 because only
  // one of the three was wired to Build Report. All three must merge before counting.
  assert.equal(wf.connections['Webhook'].main[0][0].node, 'Build Items');
  assert.equal(wf.connections['Dry Run?'].main[0][0].node, 'Report Dry Run');
  assert.equal(wf.connections['Dry Run?'].main[1][0].node, 'Call UpsertLedger');
  const execOut = wf.connections['Call UpsertLedger'].main;
  assert.equal(execOut.length, 3, 'all 3 of UpsertLedger\'s terminal-path outputs must be wired, not just the first');
  for (let i = 0; i < 3; i++) {
    assert.equal(execOut[i][0].node, 'Merge Outcomes');
    assert.equal(execOut[i][0].index, i, 'branch ' + i + ' must feed Merge Outcomes at the matching input index');
  }
  const mergeNode = wf.nodes.find((n) => n.name === 'Merge Outcomes');
  assert.equal(mergeNode.parameters.numberInputs, 3);
  assert.equal(wf.connections['Merge Outcomes'].main[0][0].node, 'Build Report');
  assert.equal(wf.connections['Build Report'].main[0][0].node, 'Respond');

  // report counts must reflect ALL merged branches, not just one -- regression guard for the
  // exact undercount bug (a lone conflict-alert item mixed in with real written rows).
  const report = wf.nodes.find((n) => n.name === 'Build Report');
  const runReport = (rows, dryRun) => {
    const fn = new Function('$input', '$', report.parameters.jsCode);
    const mockInput = { all: () => rows.map((r) => ({ json: r })) };
    const mockDollar = (name) => { if (name === 'Build Items') return { all: () => [1], first: () => ({ json: { dry_run: dryRun } }) };
      throw new Error('unexpected $() reference: ' + name); };
    return fn(mockInput, mockDollar)[0].json;
  };
  const merged = [
    { ok: true, channel: 'C0B8GCVNR5W', message: {} }, // 1 declined conflict
    ...Array.from({ length: 315 }, (_, i) => ({ identity_key: 'k' + i, reason: 'reply_dnc' })), // 315 real writes
  ];
  const rr = runReport(merged, false);
  assert.equal(rr.processed, 316, 'processed must count every merged branch, not just the first');
  assert.equal(rr.conflicts_declined, 1);
});

t('every registry write feeds a Supabase delta enqueue on its success output (drift guard, 2026-09-24)', () => {
  // The Supabase mirror only learns about a registry change through a claim in dnc_claims. On
  // 2026-09-24, 418 of 500 drifted rows came from registry writers that never enqueued one.
  const REGISTRY = 'UOgKwlGsL28lX61O';
  const CLAIMS = 'euyostwJYfJefItC';
  const READ_OPS = new Set(['get', 'getAll', 'rowExists', 'rowNotExists']);
  const files = fs.readdirSync(SUB).filter((f) => f.endsWith('.json')).map((f) => path.join(SUB, f));
  const wfRoot = path.join(SUB, '..', 'workflows');
  for (const dir of fs.readdirSync(wfRoot)) {
    const f = path.join(wfRoot, dir, dir + '.json');
    if (fs.existsSync(f)) files.push(f);
  }
  let writers = 0;
  for (const f of files) {
    const wf = JSON.parse(fs.readFileSync(f, 'utf8'));
    const byName = new Map(wf.nodes.map((n) => [n.name, n]));
    const isEnqueue = (n) => n && n.type === 'n8n-nodes-base.dataTable' &&
      ((n.parameters.dataTableId || {}).value === CLAIMS) &&
      JSON.stringify(n.parameters).includes('supabase_delta_registry');
    for (const n of wf.nodes) {
      if (n.type !== 'n8n-nodes-base.dataTable') continue;
      if ((n.parameters.dataTableId || {}).value !== REGISTRY) continue;
      if (READ_OPS.has(n.parameters.operation || 'get')) continue;
      writers++;
      const out0 = (((wf.connections[n.name] || {}).main || [])[0] || []).map((c) => byName.get(c.node));
      assert.ok(out0.some(isEnqueue),
        `${wf.name} / ${n.name}: writes the registry but its success output feeds no supabase_delta_registry enqueue`);
    }
  }
  assert.ok(writers >= 7, `non-vacuous: expected >= 7 registry writers across the generated workflows, found ${writers}`);
});

t('dnc_archived_responders_import never hands UpsertLedger a null correlation_id/date_precision (2026-09-24)', () => {
  // both are NOT NULL in Supabase's dnc_registry; 82 rows written without them on 2026-09-15 were
  // rejected by every delta push and nightly reconcile afterwards.
  const wf = JSON.parse(fs.readFileSync(path.join(SUB, '..', 'workflows', 'dnc_archived_responders_import',
    'dnc_archived_responders_import.json'), 'utf8'));
  const code = wf.nodes.find((n) => n.name === 'Build Items').parameters.jsCode;
  const run = new Function('$', '$execution', code);
  const $ = () => ({ first: () => ({ json: { body: { dry_run: true, rows: [
    { reason: 'sales_personal_outreach', linkedin_url: 'https://www.linkedin.com/in/a' },
    { reason: 'reply_dnc', reply_category: 'x', email: 'pii-7d41d0f9@example.invalid', correlation_id: 'keep:me', date_precision: 'exact' },
  ] } } }) });
  const out = run($, { id: '999' }).map((i) => i.json);
  assert.equal(out[0].correlation_id, 'archived_import:999:https://www.linkedin.com/in/a');
  assert.equal(out[0].date_precision, 'unknown');
  assert.equal(out[1].correlation_id, 'keep:me', 'a caller-supplied correlation_id must be preserved');
  assert.equal(out[1].date_precision, 'exact');
});

console.log('\n%d passed, %d failed', pass, fail);
process.exit(fail ? 1 : 0);
