#!/usr/bin/env node
// test_dnc_check_postgrest.mjs - checks the DEPLOYED dnc_check against the live Supabase project,
// through PostgREST, with the same key Clay uses. Run it once after pasting DNC_CHECK.sql into the
// Supabase SQL editor, and again whenever that function is changed.
//
//   SUPABASE_URL=https://<project>.supabase.co  SUPABASE_KEY=<publishable key>  node test_dnc_check_postgrest.mjs
//
// Optional fixtures - real rows you KNOW the state of (from the Supabase table editor; never commit them):
//   DNC_KNOWN_EMAIL=...        an email that is an ACTIVE dnc_registry row          -> must be BLOCKED
//   DNC_KNOWN_ROW_REF=...      the id of that row, if you want the row checked too
//   DNC_KNOWN_DOMAIN=...       a domain that is an ACTIVE dnc_domains row           -> BLOCKED company_dnc
//   DNC_KNOWN_LINKEDIN=...     the LinkedIn URL of an ACTIVE row keyed by LinkedIn  -> every mangled form
//                              of it (case, www, slashes, query, fragment, whitespace, an escaped
//                              character) must resolve to the same row
// Without them the test proves the function exists, is callable with the Clay key, normalizes
// exactly like normalize_v1.js and clears strangers - but it cannot prove it BLOCKS anyone, and it
// says so instead of passing quietly.
//
// No dependencies (Node 18+ fetch). Exit 0 = passed, 1 = a check failed, 2 = not configured.

import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const URL_ = (process.env.SUPABASE_URL || '').replace(/\/+$/, '');
const KEY = process.env.SUPABASE_KEY || '';
if (!URL_ || !KEY) {
  console.error('set SUPABASE_URL and SUPABASE_KEY (the read-only publishable key Clay uses)');
  process.exit(2);
}

const HERE = dirname(fileURLToPath(import.meta.url));
const NORM = [process.env.DNC_NORMALIZE_JS,
  join(HERE, '..', 'docs', 'DNC_OBS_P1_build', 'subworkflows', 'lib', 'normalize_v1.js'),
  join(HERE, '..', '..', 'DNC_OBS_P1_build', 'subworkflows', 'lib', 'normalize_v1.js')]
  .find((p) => p && existsSync(p));
const js = NORM ? createRequire(import.meta.url)(NORM).normalizeIdentityV1 : null;

let pass = 0, fail = 0;
const ok = (label, cond, detail = '') => {
  if (cond) pass++; else fail++;
  console.log(`  [${cond ? 'ok ' : 'FAIL'}] ${label}${cond || !detail ? '' : '\n         ' + detail}`);
};

async function rpc(body) {
  const r = await fetch(`${URL_}/rest/v1/rpc/dnc_check`, {
    method: 'POST',
    headers: { apikey: KEY, Authorization: `Bearer ${KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* keep text */ }
  return { status: r.status, json, text };
}

// ------------------------------------------------------------------ 1. it exists, the Clay key may call it
console.log('1. deployed and callable');
const probe = await rpc({ p_linkedin_url: null, p_email: null });
ok('POST /rest/v1/rpc/dnc_check answers 200', probe.status === 200,
  `HTTP ${probe.status}: ${probe.text.slice(0, 300)}` +
  (probe.status === 404 ? '\n         (404 = not deployed yet: paste DNC_CHECK.sql into the SQL editor)' : ''));
if (probe.status !== 200) {
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(1);
}
ok('empty input -> UNRESOLVABLE, not blocked, identity null', probe.json.gate_result === 'UNRESOLVABLE'
  && probe.json.blocked === false && probe.json.identity.identity_key === null && probe.json.norm_v === 'v1',
  JSON.stringify(probe.json));

// ------------------------------------------------------------------ 2. normalization parity, in THIS Postgres
console.log('2. normalization identical to normalize_v1.js' + (js ? '' : ' (normalize_v1.js not found - using recorded values)'));
const cases = [
  // [linkedin_url, email, expected identity_key]  - expected used only when normalize_v1.js is absent
  ['HTTPS://WWW.LinkedIn.com/in/Jane-Doe/?utm_source=x&utm_medium=y', null, 'jane-doe'],
  ['https://www.linkedin.com/in/Andr%C3%A9-Martin/', null, 'andré-martin'],
  [null, '  John.SMITH+sales@Example.COM  ', 'john.smith+sales@example.com'],
  ['https://www.linkedin.com/company/acme-corp', 'Jane@Acme.com', 'jane@acme.com'],
  [null, null, null],
  ['https://www.linkedin.com/in/%E0%A4%A', 'x@y.co', '%e0%a4%a'],     // malformed escape: kept undecoded
  ['https://www.linkedin.com/in/%41bc', null, 'Abc'],                 // lowercase BEFORE decode
  [' https://linkedin.com/in/jo-roe// ', null, 'jo-roe'],   // JS trim, double slash
  ['https://www.linkedin.com/in/ÉLODIE-ROE', null, 'élodie-roe'],     // non-ASCII lowercase: engine-dependent
  ['https://www.linkedin.com/in/', 'a@b.io', 'a@b.io'],               // empty slug -> email
  [null, '@acme.com', null],
  [null, 'jo@acmecom', null],
];
for (const [li, em, want] of cases) {
  const exp = js ? (js({ linkedin_url: li, email: em }) || {}).identity_key ?? null : want;
  const got = (await rpc({ p_linkedin_url: li, p_email: em })).json?.identity?.identity_key ?? null;
  ok(`${JSON.stringify(li)} / ${JSON.stringify(em)} -> ${JSON.stringify(exp)}`, got === exp,
    `deployed function produced ${JSON.stringify(got)}`);
}

// ------------------------------------------------------------------ 3. strangers are clean
console.log('3. an identity that cannot be on the list');
const nonce = 'zz-dnc-selftest-' + Math.random().toString(36).slice(2, 10);
const stranger = await rpc({ p_linkedin_url: `https://www.linkedin.com/in/${nonce}`,
  p_email: `${nonce}@${nonce}.invalid` });
ok('random identity -> CLEAN, reason null, no persons, no company',
  stranger.json.gate_result === 'CLEAN' && stranger.json.reason === null && stranger.json.blocked === false
  && stranger.json.persons.length === 0 && stranger.json.company === null, JSON.stringify(stranger.json));

// ------------------------------------------------------------------ 4. it blocks (needs known rows)
console.log('4. it blocks');
const knownEmail = process.env.DNC_KNOWN_EMAIL, knownRef = process.env.DNC_KNOWN_ROW_REF;
const knownDomain = process.env.DNC_KNOWN_DOMAIN, knownLi = process.env.DNC_KNOWN_LINKEDIN;
if (!knownEmail && !knownDomain && !knownLi) {
  console.log('  [SKIP] no DNC_KNOWN_* fixture set - blocking is UNPROVEN on this run');
}
const verdict = (j) => `gate_result=${j.gate_result} reason=${JSON.stringify(j.reason)} ref=${j.registry_row_ref}`;
if (knownEmail) {
  const r = await rpc({ p_email: knownEmail });
  ok('known person by email -> BLOCKED, person_dnc' + (knownRef ? `, row ${knownRef}` : ''),
    r.json.gate_result === 'BLOCKED' && r.json.block_reasons.includes('person_dnc')
    && (!knownRef || String(r.json.registry_row_ref) === String(knownRef)), verdict(r.json));
  // THE CORRECTION: the same person seen WITH a LinkedIn URL is still found
  const r2 = await rpc({ p_linkedin_url: `https://www.linkedin.com/in/${nonce}`, p_email: knownEmail });
  ok('known email + an unrelated LinkedIn URL -> STILL BLOCKED (the fix)', r2.json.gate_result === 'BLOCKED',
    verdict(r2.json) + ' - a single identity_key lookup would have missed this person');
}
if (knownDomain) {
  const r = await rpc({ p_email: `${nonce}@${knownDomain}` });
  ok('anyone at a banned company -> BLOCKED, reason company_dnc / <domain>',
    r.json.gate_result === 'BLOCKED' && r.json.reason === `company_dnc / ${knownDomain.toLowerCase()}`
    && r.json.block_reasons.includes('company_dnc'), verdict(r.json));
}
if (knownLi) {
  const base = await rpc({ p_linkedin_url: knownLi });
  ok('known LinkedIn URL -> BLOCKED', base.json.gate_result === 'BLOCKED', verdict(base.json));
  const slug = base.json.identity.linkedin_slug || '';
  const mangled = [
    `  HTTPS://LinkedIn.com/IN/${slug.toUpperCase()}//  `,
    `https://linkedin.com/in/${slug}/?utm_source=clay&trk=x#about`,
    `http://www.linkedin.com/in/${slug}/details/experience/`,
    `linkedin.com/in/${slug}`,
    `https://www.linkedin.com/in/%${slug.charCodeAt(0).toString(16)}${slug.slice(1)}`,
  ];
  for (const m of mangled) {
    const r = await rpc({ p_linkedin_url: m });
    ok(`mangled ${JSON.stringify(m.replace(slug.toUpperCase(), '<SLUG>').replace(slug.slice(1), '<slug>'))} -> same row`,
      r.json.gate_result === 'BLOCKED' && r.json.identity.linkedin_slug === slug
      && r.json.registry_row_ref === base.json.registry_row_ref, verdict(r.json));
  }
}

console.log(`\n${pass} passed, ${fail} failed${!knownEmail && !knownDomain && !knownLi ? ' (blocking not exercised)' : ''}`);
process.exit(fail ? 1 : 0);
