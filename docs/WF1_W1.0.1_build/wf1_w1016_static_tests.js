/**
 * W1.0.16 statics — member_id / public_id fallback in the person resolver.
 *
 * Fixtures are REAL cases from the 2026-08-04 audit, not invented ones:
 *   Person-cea537c7  HeyReach sent the ACoAA URN; CRM holds vanity 'frank-diepmaat', member_id 147312655
 *   Person-65faef13         HeyReach sent 'luyang2014';  CRM li_url is 'lu-yang-04496392', public_id has both
 *   Person-1c4bfa8e    HeyReach sent the ACoAA URN; member_id 459678747
 *
 * The expressions are evaluated for real (n8n `={{ }}` unwrapped and run), so a broken expression
 * fails here rather than in production.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = __dirname;
const PATCHED = path.join(DIR, 'WF-1 HeyReach Receiver - W1.0.16 patched.json');
const BASELINE = path.join(DIR, 'wf1_live_w1015.json');

const wf = JSON.parse(fs.readFileSync(PATCHED, 'utf8'));
const base = JSON.parse(fs.readFileSync(BASELINE, 'utf8'));
const N = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const C = wf.connections;
const BRANCHES = [
  ['', 'Person Create'],
  ['M5 ', 'M5 Slack Warn'],
  ['M6 ', 'M6 Slack Warn'],
  ['M7 ', 'M7 Slack Warn'],
];
const F = {
  member_id: '010fc51128116e8c73ae2b33fd52fd4537451f2b',
  public_id: '2339d1c7a7cda05651dff68ff82b2d56b20e241d',
  li_url: '66f0af69bec838dc3f90bb3f16c7d6087d8dbb20',
};

let pass = 0;
const fails = [];
function test(name, fn) {
  try {
    fn();
    pass++;
  } catch (e) {
    fails.push(`${name}: ${e.message}`);
  }
}

/** Unwrap an n8n expression and run it with a mocked node context. */
function evalExpr(expr, { lead, items }) {
  const inner = String(expr).replace(/^=/, '').trim().replace(/^\{\{/, '').replace(/\}\}$/, '');
  const ctx = {
    $: (nodeName) => {
      if (nodeName === 'Normalize') return { item: { json: { lead } } };
      if (nodeName === 'CONFIG') return { item: { json: { fields: F } } };
      throw new Error(`unexpected $('${nodeName}')`);
    },
    $json: { data: { items } },
  };
  return vm.runInNewContext(`(${inner})`, ctx, { timeout: 3000 });
}

const term = (b) => N[`${b}Person Search Member`].parameters.queryParameters.parameters
  .find((p) => p.name === 'term').value;
const verify = (b) => N[`${b}IF Member Verified`].parameters.conditions.conditions[0].leftValue;
const pid = (b) => N[`${b}PID From Member`].parameters.assignments.assignments
  .find((a) => a.name === 'person_id').value;

/**
 * REAL response shape, verified against the live API on 2026-08-04:
 *   data.items[].item.custom_fields is a FLAT ARRAY OF STRINGS with no field keys.
 * The first cut of this suite mocked a keyed object (copied from the *full person* object), the
 * expressions indexed by field key, every verification silently returned false, and the statics
 * agreed with the fiction. Live acceptance is what caught it. Fixtures below are the true shape.
 */
const cand = (id, mid, pub) => ({
  result_score: 0.04,
  item: {
    id,
    type: 'person',
    name: `p${id}`,
    emails: [],
    custom_fields: [
      'https://www.linkedin.com/in/pii-1436c6d8',
      'SomeCo',
      'Some Title',
      mid === null || mid === undefined ? null : String(mid),
      pub === null || pub === undefined ? null : String(pub),
      'Invited',
    ].filter((v) => v !== undefined),
  },
});
/** a candidate holding NO custom fields at all */
const bare = (id) => ({ item: { id, type: 'person', name: `p${id}` } });

// ---------------------------------------------------------------- graph
test('G1 node count 98 -> 110, exactly 12 added', () => {
  assert.equal(base.nodes.length, 98);
  assert.equal(wf.nodes.length, 110);
});

test('G2 every branch has the three new nodes', () => {
  for (const [b] of BRANCHES) {
    for (const suf of ['Person Search Member', 'IF Member Verified', 'PID From Member']) {
      assert(N[`${b}${suf}`], `missing ${b}${suf}`);
    }
  }
});

test('G3 the URL not-found branch now goes to the member search, in all four branches', () => {
  for (const [b] of BRANCHES) {
    assert.deepEqual(C[`${b}IF URL Found`].main[1].map((t) => t.node),
      [`${b}Person Search Member`]);
  }
});

test('G4 a verified match reaches Person Get; a miss reaches the ORIGINAL not-found target', () => {
  for (const [b, notfound] of BRANCHES) {
    assert.deepEqual(C[`${b}IF Member Verified`].main[0].map((t) => t.node),
      [`${b}PID From Member`]);
    assert.deepEqual(C[`${b}IF Member Verified`].main[1].map((t) => t.node), [notfound]);
    assert.deepEqual(C[`${b}PID From Member`].main[0].map((t) => t.node), [`${b}Person Get`]);
  }
});

test('G5 the existing FOUND path is untouched', () => {
  for (const [b] of BRANCHES) {
    assert.deepEqual(C[`${b}IF URL Found`].main[0].map((t) => t.node), [`${b}PID From URL`]);
    assert.deepEqual(C[`${b}PID From URL`].main[0].map((t) => t.node), [`${b}Person Get`]);
  }
});

test('G6 EVERY pre-existing node is byte-identical (this is a frozen workflow)', () => {
  const baseByName = Object.fromEntries(base.nodes.map((n) => [n.name, n]));
  for (const [name, n] of Object.entries(baseByName)) {
    assert(N[name], `node disappeared: ${name}`);
    assert.equal(JSON.stringify(N[name]), JSON.stringify(n), `node MUTATED: ${name}`);
  }
});

test('G7 no pre-existing connection changed except the four false-branch re-points', () => {
  for (const [src, d] of Object.entries(base.connections)) {
    const now = C[src];
    assert(now, `connection block vanished: ${src}`);
    const isResolverIf = /IF URL Found$/.test(src);
    for (let i = 0; i < (d.main || []).length; i++) {
      if (isResolverIf && i === 1) continue; // the one intended change
      assert.equal(JSON.stringify(now.main[i]), JSON.stringify(d.main[i]),
        `edge changed: ${src}[${i}]`);
    }
  }
});

test('G8 the new search nodes carry the SAME credentials as the node they clone', () => {
  for (const [b] of BRANCHES) {
    const src = N[`${b}Person Search URL`];
    const nw = N[`${b}Person Search Member`];
    assert.equal(JSON.stringify(nw.credentials), JSON.stringify(src.credentials));
    assert.equal(nw.type, src.type);
    assert.equal(nw.typeVersion, src.typeVersion);
  }
});

test('G9 search is exact_match over custom_fields (never a fuzzy name search)', () => {
  for (const [b] of BRANCHES) {
    const qp = N[`${b}Person Search Member`].parameters.queryParameters.parameters;
    assert.equal(qp.find((p) => p.name === 'fields').value, 'custom_fields');
    assert.equal(String(qp.find((p) => p.name === 'exact_match').value), 'true');
    const url = N[`${b}Person Search Member`].parameters.url;
    assert(/persons\/search/.test(url), url);
  }
});

test('G10 node ids are unique across the whole workflow', () => {
  const ids = wf.nodes.map((n) => n.id);
  assert.equal(ids.length, new Set(ids).size);
});

// ---------------------------------------------------------------- the search term
test('T1 numeric member id becomes the term (Person-cea537c7, ACoAA URN case)', () => {
  const lead = { id: 147312655, slug: 'acoaaajh0a8bsj6aos9jdrlekl9wt4glhnmljdk' };
  assert.equal(evalExpr(term(''), { lead, items: [] }), '147312655');
});

test('T2 a string-typed id is still used, coerced to a number (webhook JSON varies)', () => {
  assert.equal(evalExpr(term(''), { lead: { id: '280181007', slug: 'luyang2014' }, items: [] }),
    '280181007');
});

test('T3 no numeric id -> falls back to the slug (public_id path)', () => {
  assert.equal(evalExpr(term(''), { lead: { id: null, slug: 'luyang2014' }, items: [] }),
    'luyang2014');
});

test('T4 neither key -> the unmatchable sentinel, NEVER an empty term', () => {
  for (const lead of [{ id: null, slug: '' }, { id: '', slug: null }, {}, { id: 'abc', slug: '  ' }]) {
    const t = evalExpr(term(''), { lead, items: [] });
    assert.equal(t, '__wf1_no_member_key__', JSON.stringify(lead));
    assert(String(t).length >= 1, 'an empty term makes Pipedrive 400');
  }
});

test('T5 a non-numeric id does not become the term (NaN must not leak)', () => {
  const t = evalExpr(term(''), { lead: { id: 'ACoAAABc', slug: 'real-slug' }, items: [] });
  assert.equal(t, 'real-slug');
  assert(!/NaN/.test(t));
});

test('T6 all four branches use the identical term expression', () => {
  const seen = new Set(BRANCHES.map(([b]) => term(b)));
  assert.equal(seen.size, 1);
});

// ---------------------------------------------------------------- verification
test('V1 Person-cea537c7 resolves on member_id despite the URL mismatch', () => {
  const lead = { id: 147312655, slug: 'acoaaajh0a8bsj6aos9jdrlekl9wt4glhnmljdk' };
  const items = [cand(82451, 147312655, 'frank-diepmaat')];
  assert.equal(evalExpr(verify(''), { lead, items }), true);
  assert.equal(evalExpr(pid(''), { lead, items }), 82451);
});

test('V2 member_id stored as a NUMBER matches a string key (Person Create writes +lead.id)', () => {
  const lead = { id: '459678747', slug: 'acoaabtmjbsbfrponpijvwd-qgmnk9l7n3c0-fm' };
  const items = [cand(82981, 459678747, 'aditabraham')];
  assert.equal(evalExpr(verify(''), { lead, items }), true);
  assert.equal(evalExpr(pid(''), { lead, items }), 82981);
});

test('V3 Person-65faef13 resolves via public_id when the id is absent, incl. a comma list', () => {
  const lead = { id: null, slug: 'luyang2014' };
  const items = [cand(83903, 280181007, 'luyang2014, lu-yang-04496392')];
  assert.equal(evalExpr(verify(''), { lead, items }), true);
  assert.equal(evalExpr(pid(''), { lead, items }), 83903);
});

test('V4 THE MAKE GUARD: a candidate that does not own our key is REFUSED', () => {
  const lead = { id: 147312655, slug: 'frank-diepmaat-x' };
  const items = [cand(99999, 111111111, 'someone-else')];
  assert.equal(evalExpr(verify(''), { lead, items }), false);
  assert.equal(evalExpr(pid(''), { lead, items }), null);
});

test('V5 zero search hits -> not verified, falls through to the original path', () => {
  const lead = { id: 147312655, slug: 'x' };
  assert.equal(evalExpr(verify(''), { lead, items: [] }), false);
  assert.equal(evalExpr(pid(''), { lead, items: [] }), null);
});

test('V6 the sentinel search can never verify (no key -> no match, whatever comes back)', () => {
  const lead = { id: null, slug: '' };
  const items = [cand(1, '__wf1_no_member_key__', '__wf1_no_member_key__')];
  assert.equal(evalExpr(verify(''), { lead, items }), false);
});

test('V7 the RIGHT candidate is picked out of several, not items[0]', () => {
  const lead = { id: 280181007, slug: 'zzz' };
  const items = [cand(70001, 999, 'nope'), cand(83903, 280181007, 'luyang2014'),
    cand(70002, 888, 'also-no')];
  assert.equal(evalExpr(verify(''), { lead, items }), true);
  assert.equal(evalExpr(pid(''), { lead, items }), 83903);
});

test('V8 missing/blank custom fields on a candidate never throw and never match', () => {
  const lead = { id: 147312655, slug: 'frank-diepmaat' };
  for (const items of [[bare(5)], [{ item: { id: 5, custom_fields: [] } }],
    [{ item: { id: 5, custom_fields: [null, null] } }], [{}]]) {
    assert.equal(evalExpr(verify(''), { lead, items }), false, JSON.stringify(items));
    assert.equal(evalExpr(pid(''), { lead, items }), null);
  }
});

test('V9 a null/absent key never matches a candidate whose field is also null', () => {
  const lead = { id: null, slug: '' };
  const items = [cand(5, null, null)];
  assert.equal(evalExpr(verify(''), { lead, items }), false);
});

test('V10 slug compare is case-insensitive and comma-split; the key never matches a substring', () => {
  const lead = { id: null, slug: 'LuYang2014' };
  assert.equal(evalExpr(verify(''), { lead, items: [cand(83903, 1, ' luyang2014 , other')] }), true);
  // a 4-digit prefix of a real member id must not match it
  const lead2 = { id: 14731, slug: '' };
  assert.equal(evalExpr(verify(''), { lead: lead2, items: [cand(1, 147312655, '')] }), false);
});

test('V14 custom_fields is an ARRAY: a keyed-object candidate must not resolve (the shipped bug)', () => {
  const lead = { id: 147312655, slug: 'x' };
  const keyed = [{ item: { id: 82451, custom_fields: { [F.member_id]: 147312655 } } }];
  assert.equal(evalExpr(verify(''), { lead, items: keyed }), false,
    'a keyed object is not the real shape and must not be silently accepted');
});

test('V15 duplicate persons sharing our key resolve to the OLDEST id, never at random', () => {
  const lead = { id: 105856311, slug: 'arvind-dua-53354b2b' };
  // the real duplicate pair measured in production
  const items = [cand(84325, 105856311, 'arvind-dua-53354b2b'),
    cand(51553, 105856311, 'arvind-dua-53354b2b')];
  assert.equal(evalExpr(verify(''), { lead, items }), true);
  assert.equal(evalExpr(pid(''), { lead, items }), 51553, 'oldest (lowest) id wins, as in WF-2 B27');
  // order of the response must not change the answer
  assert.equal(evalExpr(pid(''), { lead, items: [...items].reverse() }), 51553);
});

test('V16 a short numeric id is never used as a key (Source=446 would match thousands)', () => {
  for (const id of [446, 1, 999, 9999]) {
    assert.equal(evalExpr(term(''), { lead: { id, slug: '' }, items: [] }),
      '__wf1_no_member_key__', `id ${id} must not become a key`);
  }
  assert.equal(evalExpr(term(''), { lead: { id: 10000, slug: '' }, items: [] }), '10000');
});

test('V17 a short slug is not used either', () => {
  assert.equal(evalExpr(term(''), { lead: { id: null, slug: 'ab' }, items: [] }),
    '__wf1_no_member_key__');
  assert.equal(evalExpr(term(''), { lead: { id: null, slug: 'abc' }, items: [] }), 'abc');
});

test('V11 verify and pid agree on every fixture (never verified-but-null)', () => {
  const cases = [
    [{ id: 147312655, slug: 'x' }, [cand(82451, 147312655, 'frank-diepmaat')]],
    [{ id: null, slug: 'luyang2014' }, [cand(83903, 1, 'luyang2014')]],
    [{ id: 999, slug: 'y' }, [cand(1, 2, 'z')]],
    [{ id: null, slug: '' }, []],
  ];
  for (const [lead, items] of cases) {
    const v = evalExpr(verify(''), { lead, items });
    const p = evalExpr(pid(''), { lead, items });
    assert.equal(v, p !== null, `disagreement for ${JSON.stringify(lead)}`);
  }
});

test('V12 all four branches share the identical verify and pid expressions', () => {
  assert.equal(new Set(BRANCHES.map(([b]) => verify(b))).size, 1);
  assert.equal(new Set(BRANCHES.map(([b]) => pid(b))).size, 1);
});

test('V13 the verifier checks exactly what was searched (term and match share one key fn)', () => {
  for (const b of BRANCHES.map(([x]) => x)) {
    for (const expr of [verify(b), pid(b)]) {
      assert(/Array\.isArray/.test(expr), 'must treat custom_fields as an array');
      assert(!/custom_fields\]/.test(expr) && !/\[f\.member_id\]/.test(expr),
        'must not index custom_fields by field key - the response has no keys');
      assert(/__wf1_no_member_key__/.test(expr), 'the sentinel must never verify');
      assert(/sort/.test(expr), 'duplicates must resolve deterministically');
    }
  }
});

console.log(`${pass} passed, ${fails.length} failed`);
if (fails.length) {
  for (const f of fails) console.log('  FAIL ' + f);
  process.exit(1);
}
