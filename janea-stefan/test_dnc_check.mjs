#!/usr/bin/env node
// test_dnc_check.mjs - executes DNC_CHECK.sql in REAL Postgres (PGlite, Postgres compiled to WASM)
// against the REAL Supabase schema file, and checks it three ways:
//
//   1. PARITY - dnc_identity_v1 vs the real normalizeIdentityV1 (normalize_v1.js), byte for byte,
//      on the documented examples, hand-picked edge cases and a random fuzz
//   2. BEHAVIOUR - blocked / not blocked on fixture rows, including the correction this function
//      exists for: a person keyed by email, looked up WITH a LinkedIn URL
//   3. NON-VACUITY - the old single-key lookup must MISS that person, or the test proves nothing
//
// Run:  npm i @electric-sql/pglite@0.2   then   node test_dnc_check.mjs
// Paths default to this repository's layout; override with DNC_SCHEMA_SQL / DNC_NORMALIZE_JS.
// Exit 0 = everything passed.

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
console.log(`schema: ${SCHEMA}\nnormalizer: ${NORM}\n`);

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

// ------------------------------------------------------------------ 2. behaviour
console.log('\n--- 2. behaviour ---');
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
];
for (const r of ROWS) {
  const cols = Object.keys(r).map((c) => (c === 'createdAt' || c === 'updatedAt') ? `"${c}"` : c);
  await db.query(`insert into dnc_registry (${cols.join(',')}) values (${cols.map((_, i) => '$' + (i + 1)).join(',')})`,
                 Object.values(r));
}
await db.query(`insert into dnc_domains (domain, added_at, status) values
                ('blocked-co.com', now(), 'active'), ('cleared-co.com', now(), 'removed')`);

await db.exec('set role anon');                       // run AS the Clay role, through RLS
const chk = async (li, em) =>
  (await db.query('select dnc_check($1, $2) r', [li, em])).rows[0].r;

let r = await chk('https://linkedin.com/in/Jane-Doe/', null);
ok('person active by LinkedIn -> blocked, person_active', r.blocked && r.block_reasons.includes('person_active'));
r = await chk(null, 'Gone@Old.com');
ok('person removed -> NOT blocked, row still reported', !r.blocked && r.persons.length === 1 && r.persons[0].status === 'removed');
r = await chk(null, 'someone@blocked-co.com');
ok('clean person at a blocked company -> blocked, company_active', r.blocked && r.block_reasons.join() === 'company_active');
r = await chk(null, 'someone@www.blocked-co.com');
ok('leading www. stripped from the domain', r.domain === 'blocked-co.com' && r.blocked);
r = await chk(null, 'someone@cleared-co.com');
ok('removed company -> NOT blocked', !r.blocked && r.company.status === 'removed');
r = await chk('https://www.linkedin.com/in/mail-only-person', 'MailOnly@Acme.io');
ok('THE CORRECTION: keyed by email, looked up WITH LinkedIn -> found and blocked',
   r.blocked && r.persons.length === 1 && r.persons[0].matched_by === 'email',
   JSON.stringify(r));
r = await chk('https://linkedin.com/in/stale-guy', null);
ok('active but past expires_at -> flagged expired_but_active and STILL blocks',
   r.blocked && r.persons[0].expired_but_active === true);
r = await chk('https://www.linkedin.com/company/nobody', 'not-an-email');
ok('nothing resolves -> not blocked, identity_key null', !r.blocked && r.identity.identity_key === null);
r = await chk(null, null);
ok('both null -> not blocked, no error', r.blocked === false);

// ------------------------------------------------------------------ 3. non-vacuity
console.log('\n--- 3. non-vacuity ---');
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

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
