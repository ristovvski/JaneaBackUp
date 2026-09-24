#!/usr/bin/env node
// test_dnc_check.mjs - executes DNC_CHECK.sql in REAL Postgres (PGlite, Postgres compiled to WASM)
// against the REAL Supabase schema file, and checks it four ways:
//
//   1. PARITY - dnc_identity_v1 vs the real normalizeIdentityV1 (normalize_v1.js), byte for byte,
//      on the documented examples, hand-picked edge cases and a random fuzz
//   2. BEHAVIOUR - the gate's verdict on fixture rows, including the correction this function
//      exists for: a person keyed by email, looked up WITH a LinkedIn URL
//   3. GATE PARITY - the pre-add gate's OWN classifier code (Classify Batch in dnc_pre_add_gate),
//      run on the same fixtures, must return the same gate_result / reason / registry_row_ref for
//      every input. Needs the gate workflow JSON (not in the repository - JSON is excluded); when it
//      cannot be found this section says SKIPPED instead of passing quietly.
//   4. NON-VACUITY - the old single-key lookup must MISS that person, or the test proves nothing
//
// Run:  npm i @electric-sql/pglite@0.2   then   node test_dnc_check.mjs
// Paths default to this repository's layout; override with DNC_SCHEMA_SQL / DNC_NORMALIZE_JS /
// DNC_GATE_JSON. Exit 0 = everything that ran passed.

import { PGlite } from '@electric-sql/pglite';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const first = (...c) => c.find((p) => p && existsSync(p));
const SCHEMA = first(process.env.DNC_SCHEMA_SQL,
  join(HERE, '..', 'docs', 'SUPABASE_PROJECTION_build', 'dnc_registry_phase1.sql'),
  join(HERE, '..', '..', 'SUPABASE_PROJECTION_build', 'dnc_registry_phase1.sql'));
const NORM = first(process.env.DNC_NORMALIZE_JS,
  join(HERE, '..', 'docs', 'DNC_OBS_P1_build', 'subworkflows', 'lib', 'normalize_v1.js'),
  join(HERE, '..', '..', 'DNC_OBS_P1_build', 'subworkflows', 'lib', 'normalize_v1.js'));
const GATE = first(process.env.DNC_GATE_JSON,
  join(HERE, '..', '..', 'DNC_OBS_P1_build', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'),
  join(HERE, '..', '..', '..', 'DNC_OBS_P1_build', 'workflows', 'dnc_pre_add_gate', 'dnc_pre_add_gate.json'));
if (!SCHEMA || !NORM) {
  console.error('cannot find the schema SQL or normalize_v1.js - set DNC_SCHEMA_SQL / DNC_NORMALIZE_JS');
  process.exit(2);
}
const { normalizeIdentityV1 } = createRequire(import.meta.url)(NORM);

let pass = 0, fail = 0;
const ok = (label, cond, detail = '') => {
  if (cond) pass++; else fail++;
  console.log(`  [${cond ? 'ok ' : 'FAIL'}] ${label}${cond || !detail ? '' : '\n         ' + detail}`);
};

const db = new PGlite();
// Supabase provides these roles and grants by default; PGlite does not.
await db.exec(`create role anon; create role authenticated;`);
await db.exec(readFileSync(SCHEMA, 'utf8'));
await db.exec(`grant usage on schema public to anon, authenticated;
               grant select on all tables in schema public to anon, authenticated;`);
await db.exec(readFileSync(join(HERE, 'DNC_CHECK.sql'), 'utf8'));
const env = (await db.query(`select (select datctype from pg_database where datname = current_database()) c, version() v`)).rows[0];
console.log(`engine: ${env.v.split(' on ')[0]}   lc_ctype=${env.c}`);
console.log(`schema: ${SCHEMA}\nnormalizer: ${NORM}\ngate: ${GATE || '(not found)'}\n`);

// ------------------------------------------------------------------ 1. parity
console.log('--- 1. parity with normalizeIdentityV1 ---');
const sqlId = async (li, em) =>
  (await db.query('select * from dnc_identity_v1($1, $2)', [li, em])).rows[0];
const jsId = (li, em) => {
  const o = normalizeIdentityV1({ linkedin_url: li, email: em });
  return { identity_key: o.identity_key, linkedin_slug: o.linkedin_slug,
           linkedin_url_norm: o.linkedin_url_norm, email_lc: o.email_lc };
};
const same = (a, b) => ['identity_key', 'linkedin_slug', 'linkedin_url_norm', 'email_lc']
  .every((k) => (a[k] ?? null) === (b[k] ?? null));

const CASES = [
  // the five documented examples
  ['HTTPS://WWW.LinkedIn.com/in/Jane-Doe/?utm_source=x&utm_medium=y', null],
  ['https://www.linkedin.com/in/Andr%C3%A9-Martin/', null],
  [null, '  John.SMITH+sales@Example.COM  '],
  ['https://www.linkedin.com/company/acme-corp', 'Jane@Acme.com'],
  [null, null],
  // edge cases the prose does not state
  ['  https://linkedin.com/in/bob  ', null],              // trimmed before lowercasing
  [' https://linkedin.com/in/nbsp ', null],        // JS trim includes NBSP
  ['﻿https://linkedin.com/in/bom', null],               // ... and BOM
  ['https://linkedin.com/in/%41nna', null],                  // lowercase BEFORE decode -> 'Anna'
  ['https://linkedin.com/in/bad%zzslug', null],              // malformed -> keep undecoded
  ['https://linkedin.com/in/half%4', null],                  // truncated escape -> keep undecoded
  ['https://linkedin.com/in/%c3%28', null],                  // invalid UTF-8 -> keep undecoded
  ['https://linkedin.com/in/a%2fb%2f%2f', null],             // decoded slashes, stripped again
  ['https://linkedin.com/in/x%20', null],                    // decoded trailing space, trimmed
  ['https://linkedin.com/in/%20%20', 'z@y.com'],             // slug decodes to blank -> email wins
  ['https://linkedin.com/in/', 'z@y.com'],                   // /in/ with nothing after
  ['https://linkedin.com/in//x', null],                      // /in/ followed by /
  ['https://linkedin.com/in/one#frag', null],
  ['https://linkedin.com/in/two?x=/in/three', null],         // FIRST /in/ wins
  ['https://www.linkedin.com/pub/dir/x', 'Mail@Host.io'],
  ['   ', 'a@b.co'],
  [null, '@nope.com'], [null, 'a@b'], [null, 'a.b@c'], [null, 'a@.c'], [null, 'a@@b.c'],
  [null, '  UPPER@CASE.ORG '], [null, 'x@y.z'],
];
let parityBad = 0;
for (const [li, em] of CASES) {
  const s = await sqlId(li, em), j = jsId(li, em);
  if (!same(s, j)) {
    parityBad++;
    console.log(`  [FAIL] ${JSON.stringify([li, em])}\n         sql=${JSON.stringify(s)}\n         js =${JSON.stringify(j)}`);
  }
}
ok(`${CASES.length} documented + edge cases identical to the JavaScript`, parityBad === 0);

// random fuzz: URL-ish strings from a hostile alphabet
const ALPH = ['a', 'Z', 'é', '-', '_', '/', '?', '#', '%', '2', 'F', 'c', '3', 'A', '9', ' ', '.', '@'];
let seed = 20260924;
const rnd = (n) => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed % n; };
let fuzzBad = 0, fuzzN = 600, firstBad = null;
for (let i = 0; i < fuzzN; i++) {
  let tail = ''; const len = 1 + rnd(14);
  for (let k = 0; k < len; k++) tail += ALPH[rnd(ALPH.length)];
  const li = (rnd(3) === 0 ? ' ' : '') + ['https://www.linkedin.com/in/', 'HTTPS://LinkedIn.com/IN/', 'linkedin.com/company/'][rnd(3)] + tail;
  const em = rnd(2) ? ['Ann@Acme.com', 'bad@', ' c.d@E.F ', null][rnd(4)] : null;
  const s = await sqlId(li, em), j = jsId(li, em);
  if (!same(s, j)) { fuzzBad++; firstBad ??= { li, em, s, j }; }
}
ok(`${fuzzN} fuzzed inputs identical to the JavaScript`, fuzzBad === 0,
   firstBad && `first divergence: ${JSON.stringify(firstBad)}`);

// ------------------------------------------------------------------ fixtures
const row = (id, key, li, em, status, extra = {}) => ({
  id, identity_key: key, norm_v: 'v1', linkedin_url_norm: li, email_lc: em, entry_type: 'negative_reply',
  reason: 'reply_dnc', source: 'test', correlation_id: 'test:' + id, date_precision: 'unknown',
  status, added_at: '2026-09-01T00:00:00Z', createdAt: '2026-09-01T00:00:00Z',
  updatedAt: '2026-09-01T00:00:00Z', ...extra });
const ROWS = [
  row(1, 'jane-doe', 'https://www.linkedin.com/in/jane-doe', null, 'active'),
  row(2, 'gone@old.com', null, 'gone@old.com', 'removed', { removed_at: '2026-09-10T00:00:00Z' }),
  row(3, 'mailonly@acme.io', null, 'mailonly@acme.io', 'active'),               // keyed by EMAIL
  row(4, 'stale-guy', 'https://www.linkedin.com/in/stale-guy', null, 'active',
      { expires_at: '2020-01-01T00:00:00Z' }),
  // one person, two active rows: the gate's pick() must choose the stronger entry_type
  row(5, 'two-rows', 'https://www.linkedin.com/in/pii-d69db7be', null, 'active',
      { entry_type: 'manual', source: 'sheet', added_at: '2026-01-01T00:00:00Z' }),
  row(6, 'pii-80ba4851@example.invalid', null, 'pii-80ba4851@example.invalid', 'active',
      { entry_type: 'explicit_opt_out', source: 'unsubscribe', added_at: '2026-06-01T00:00:00Z' }),
  // equal strength: the OLDER added_at wins
  row(7, 'twin', 'https://www.linkedin.com/in/pii-7615cbf4', null, 'active', { added_at: '2026-05-01T00:00:00Z' }),
  row(8, 'pii-9a23ca78@example.invalid', null, 'pii-9a23ca78@example.invalid', 'active', { added_at: '2026-02-01T00:00:00Z', source: '' }),
  // a person on the list who ALSO works at a banned company, and one of our own team
  row(9, 'pii-a369ca15@example.invalid', null, 'pii-a369ca15@example.invalid', 'active'),
  row(10, 'teammate@janeasystems.com', null, 'teammate@janeasystems.com', 'active'),
];
for (const r of ROWS) {
  const cols = Object.keys(r).map((c) => (c === 'createdAt' || c === 'updatedAt') ? `"${c}"` : c);
  await db.query(`insert into dnc_registry (${cols.join(',')}) values (${cols.map((_, i) => '$' + (i + 1)).join(',')})`,
                 Object.values(r));
}
const DOMAINS = [{ domain: 'blocked-co.com', status: 'active' }, { domain: 'cleared-co.com', status: 'removed' }];
for (const d of DOMAINS) {
  await db.query('insert into dnc_domains (domain, added_at, status) values ($1, now(), $2)', [d.domain, d.status]);
}

await db.exec('set role anon');                       // run AS the Clay role, through RLS
const chk = async (li, em) =>
  (await db.query('select dnc_check($1, $2) r', [li, em])).rows[0].r;

// ------------------------------------------------------------------ 2. behaviour
console.log('\n--- 2. behaviour (the gate verdict) ---');
let r = await chk('https://linkedin.com/in/Jane-Doe/', null);
ok('person active by LinkedIn -> BLOCKED, reason entry_type / source, row ref',
   r.gate_result === 'BLOCKED' && r.reason === 'negative_reply / test' && r.registry_row_ref === 1
   && r.block_reasons.join() === 'person_dnc', JSON.stringify(r));
r = await chk(null, 'Gone@Old.com');
ok('person removed -> CLEAN with the gate\'s "was ... until ..., currently clean"',
   r.gate_result === 'CLEAN' && !r.blocked && r.persons.length === 1
   && r.reason === 'was negative_reply until 2026-09-10T00:00:00.000Z, currently clean', JSON.stringify(r));
r = await chk(null, 'someone@blocked-co.com');
ok('clean person at a banned company -> BLOCKED, company_dnc / <domain>',
   r.gate_result === 'BLOCKED' && r.reason === 'company_dnc / blocked-co.com'
   && r.registry_row_ref === null && r.block_reasons.join() === 'company_dnc', JSON.stringify(r));
r = await chk(null, 'pii-a369ca15@example.invalid');
ok('listed person at a banned company -> company_dnc WINS (gate precedence), both checks reported',
   r.gate_result === 'BLOCKED' && r.reason.startsWith('company_dnc')
   && r.block_reasons.join() === 'company_dnc,person_dnc', JSON.stringify(r));
r = await chk(null, 'someone@www.blocked-co.com');
ok('domain is taken exactly as the gate takes it (no www. stripping)',
   r.domain === 'www.blocked-co.com' && r.gate_result === 'CLEAN', JSON.stringify(r));
r = await chk(null, 'someone@cleared-co.com');
ok('removed company -> CLEAN', r.gate_result === 'CLEAN' && r.company.status === 'removed');
r = await chk(null, 'Teammate@JaneaSystems.com');
ok('our own team -> OWN_TEAM, blocked, wins over its own registry row',
   r.gate_result === 'OWN_TEAM' && r.blocked && r.block_reasons.join() === 'own_team,person_dnc', JSON.stringify(r));
r = await chk('https://www.linkedin.com/in/mail-only-person', 'MailOnly@Acme.io');
ok('THE CORRECTION: keyed by email, looked up WITH LinkedIn -> found and BLOCKED',
   r.gate_result === 'BLOCKED' && r.registry_row_ref === 3 && r.persons.length === 1
   && r.persons[0].matched_by === 'email', JSON.stringify(r));
r = await chk('https://linkedin.com/in/stale-guy', null);
ok('active but past expires_at -> flagged expired_but_active and STILL BLOCKED',
   r.gate_result === 'BLOCKED' && r.persons[0].expired_but_active === true);
r = await chk('https://www.linkedin.com/in/pii-d69db7be', 'pii-80ba4851@example.invalid');
ok('two active rows -> the STRONGER entry_type is the reason (explicit_opt_out over manual)',
   r.gate_result === 'BLOCKED' && r.registry_row_ref === 6 && r.reason === 'explicit_opt_out / unsubscribe', JSON.stringify(r));
r = await chk('https://www.linkedin.com/in/pii-7615cbf4', 'pii-9a23ca78@example.invalid');
ok('equal strength -> the OLDER row wins; an empty source adds no " / "',
   r.registry_row_ref === 8 && r.reason === 'negative_reply', JSON.stringify(r));
r = await chk('https://www.linkedin.com/company/nobody', 'not-an-email');
ok('nothing resolves -> UNRESOLVABLE, not blocked', r.gate_result === 'UNRESOLVABLE' && !r.blocked
   && r.identity.identity_key === null);
r = await chk(null, null);
ok('both null -> UNRESOLVABLE, no error', r.gate_result === 'UNRESOLVABLE' && r.blocked === false);
r = await chk(null, 'pii-41334f0f@example.invalid');
ok('a stranger -> CLEAN, reason null', r.gate_result === 'CLEAN' && r.reason === null && !r.blocked);

// ------------------------------------------------------------------ 3. gate parity
console.log('\n--- 3. parity with the pre-add gate\'s own classifier ---');
if (!GATE) {
  console.log('  [SKIPPED] dnc_pre_add_gate.json not found (set DNC_GATE_JSON) - gate parity NOT checked');
} else {
  const gate = JSON.parse(readFileSync(GATE, 'utf8'));
  const classify = gate.nodes.find((n) => n.name === 'Classify Batch').parameters.jsCode;
  const runGate = (li, em) => {
    const norm = normalizeIdentityV1({ linkedin_url: li, email: em });
    const s = { row_index: 0, norm, li_key: norm.linkedin_url_norm || '__DNC_NO_LI__',
                em_key: norm.email_lc || '__DNC_NO_EM__' };
    // what "Get Registry Match (Batch)" returns: rows whose linkedin_url_norm OR email_lc equals the keys
    const found = ROWS.filter((x) => x.linkedin_url_norm === s.li_key || x.email_lc === s.em_key)
      .map((x) => ({ ...x, added_at: new Date(x.added_at).toISOString(),
                     removed_at: x.removed_at ? new Date(x.removed_at).toISOString() : null,
                     expires_at: x.expires_at ? new Date(x.expires_at).toISOString() : null }));
    const items = (a) => ({ all: () => a.map((json) => ({ json })) });
    const $ = (n) => {
      if (n === 'Get Domain Blocklist') return items(DOMAINS.filter((d) => d.status === 'active'));
      if (n === 'Normalize Batch') return items([s]);
      throw new Error('unexpected $() in the gate classifier: ' + n);
    };
    return new Function('$', '$input', classify)($, items(found))[0].json;
  };
  const INPUTS = [
    ['https://linkedin.com/in/Jane-Doe/', null], [null, 'Gone@Old.com'], [null, 'someone@blocked-co.com'],
    [null, 'pii-a369ca15@example.invalid'], [null, 'someone@www.blocked-co.com'], [null, 'someone@cleared-co.com'],
    [null, 'Teammate@JaneaSystems.com'], ['https://linkedin.com/in/stale-guy', null],
    ['https://www.linkedin.com/in/pii-d69db7be', 'pii-80ba4851@example.invalid'], ['https://www.linkedin.com/in/pii-7615cbf4', 'pii-9a23ca78@example.invalid'],
    ['https://www.linkedin.com/company/nobody', 'not-an-email'], [null, null], [null, 'pii-41334f0f@example.invalid'],
  ];
  let bad = 0;
  for (const [li, em] of INPUTS) {
    const g = runGate(li, em), q = await chk(li, em);
    const gv = [g.gate_result, g.reason, g.registry_row_ref ?? null];
    const qv = [q.gate_result, q.reason, q.registry_row_ref ?? null];
    if (JSON.stringify(gv) !== JSON.stringify(qv)) {
      bad++;
      console.log(`  [FAIL] ${JSON.stringify([li, em])}\n         gate=${JSON.stringify(gv)}\n         sql =${JSON.stringify(qv)}`);
    }
  }
  ok(`${INPUTS.length} inputs: dnc_check verdict identical to the gate's Classify Batch`, bad === 0);
  // the one place matching is deliberately wider than the gate: the correction case
  const g = runGate('https://www.linkedin.com/in/mail-only-person', 'MailOnly@Acme.io');
  const q = await chk('https://www.linkedin.com/in/mail-only-person', 'MailOnly@Acme.io');
  ok('the correction case agrees with the gate too (it matches on the email column)',
     g.gate_result === q.gate_result && g.registry_row_ref === q.registry_row_ref,
     JSON.stringify({ gate: [g.gate_result, g.registry_row_ref], sql: [q.gate_result, q.registry_row_ref] }));
}

// ------------------------------------------------------------------ 4. non-vacuity
console.log('\n--- 4. non-vacuity ---');
const naive = (await db.query(
  `select count(*)::int n from dnc_registry
    where identity_key = (select identity_key from dnc_identity_v1($1, $2))`,
  ['https://www.linkedin.com/in/mail-only-person', 'MailOnly@Acme.io'])).rows[0].n;
ok('the old single identity_key lookup MISSES that person (so the correction is real)', naive === 0,
   `naive lookup found ${naive}`);

// ------------------------------------------------------------------ engine-dependent
console.log('\n--- engine-dependent (reported, not failed) ---');
const u = await sqlId('https://linkedin.com/in/ÉCOLE', null), uj = jsId('https://linkedin.com/in/ÉCOLE', null);
console.log(`  non-ASCII uppercase: sql=${u.linkedin_slug}  js=${uj.linkedin_slug}  -> ${u.linkedin_slug === uj.linkedin_slug ? 'identical' : 'DIFFERS in this engine (lc_ctype=' + env.c + '); re-check on Supabase with test_dnc_check_postgrest.mjs'}`);

console.log(`\n${pass} passed, ${fail} failed${GATE ? '' : '   (gate parity SKIPPED)'}`);
process.exit(fail ? 1 : 0);
