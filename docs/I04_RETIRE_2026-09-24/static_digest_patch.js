#!/usr/bin/env node
// Statics for the dnc_morning_digest patch. Executes the DEPLOYED code (read from
// dnc_morning_digest.post.json, not from the .js sources) with a mocked n8n runtime, on the real
// Sched Agg / CONFIG / Window output of execution 68402 (2026-09-24 07:00).
// Exit 0 = all passed.
const fs = require('fs');
const path = require('path');
const H = __dirname;
const post = JSON.parse(fs.readFileSync(path.join(H, 'dnc_morning_digest.post.json'), 'utf8'));
const pre = JSON.parse(fs.readFileSync(path.join(H, 'backup', 'dnc_morning_digest.pre.json'), 'utf8'));
const fx = JSON.parse(fs.readFileSync(path.join(H, 'fixture_digest_68402.json'), 'utf8'));
const code = (wf, n) => wf.nodes.find(x => x.name === n).parameters.jsCode;
const cfgPost = JSON.parse(post.nodes.find(x => x.name === 'CONFIG').parameters.jsonOutput);

function run(src, nodes, input, sd) {
  const $ = (n) => {
    if (!(n in nodes)) throw new Error(`Referenced node is unexecuted: ${n}`);
    const items = nodes[n].map(j => ({ json: j }));
    return { first: () => items[0], all: () => items };
  };
  const $input = { first: () => ({ json: input[0] }), all: () => input.map(j => ({ json: j })) };
  const $getWorkflowStaticData = () => sd;
  return new Function('$', '$input', '$getWorkflowStaticData', 'Buffer', src)($, $input, $getWorkflowStaticData, Buffer)
    .map(i => i.json);
}

let pass = 0, fail = 0;
const ok = (label, cond, detail = '') => {
  if (cond) pass++; else fail++;
  console.log(`  [${cond ? 'ok ' : 'FAIL'}] ${label}${cond ? '' : '\n         ' + detail}`);
};

const led = (n, pad = 0) => Array.from({ length: n }, (_, i) => ({ id: i + 1, identity_key: 'k' + i, status: 'active', blob: 'x'.repeat(pad), createdAt: '2026-09-01T00:00:00Z' }));
const doms = Array.from({ length: 5 }, (_, i) => ({ id: i + 1, domain: 'd' + i + '.com', status: 'active' }));
const clms = Array.from({ length: 3 }, (_, i) => ({ id: i + 1, claim_key: 'c' + i }));
const base = (over = {}) => Object.assign({
  'CONFIG': [cfgPost], 'Sched Agg': [fx.sched_agg],
  'DNC Active Rows': led(10), 'DNC Removed Rows': led(2),
  'DT Domains Rows': doms, 'DT Claims Rows': clms,
}, over);
const size = (nodes, sd = {}) => run(code(post, 'DT Size Agg'), nodes, [{}], sd)[0];
const compose = (d, wf = post) => run(code(wf, 'Compose'),
  { 'CONFIG': [cfgPost], 'Window': [fx.window] }, [d])[0].slack_text;

console.log('DT Size Agg');
let r = size(base());
ok('readable on well-shaped rows', r.__dt_readable === true && r.dt_total_mb !== null, JSON.stringify(r).slice(0, 200));
ok('carries every Sched Agg field through', Object.keys(fx.sched_agg).every(k => k in r));
ok('cap comes from CONFIG (50)', r.dt_cap_mb === 50);
const bytes = [...led(10), ...led(2), ...doms, ...clms].reduce((a, x) => a + Buffer.byteLength(JSON.stringify(x)), 0);
ok('total = serialized bytes of all four reads', r.dt_total_mb === Math.round(bytes / 1e5) / 10, `${r.dt_total_mb} vs ${bytes}`);

r = size(base({ 'DT Claims Rows': [{ ...fx.sched_agg, __dt_domains_marker: true }] }));
ok('ECHO of the input item (no claim_key) -> unreadable, total null', r.__dt_readable === false && r.dt_total_mb === null && /claims/.test(r.__dt_error), JSON.stringify(r.__dt_error));
r = size(base({ 'DT Claims Rows': [{ error: "Could not find the data table: 'x'" }] }));
ok('error item -> unreadable, error text kept', r.__dt_readable === false && /Could not find/.test(r.__dt_error));
r = size(base({ 'DT Domains Rows': [...doms, { id: 9, somethingElse: 1 }] }));
ok('ONE mis-shaped row -> unreadable (not a smaller number)', r.__dt_readable === false && r.dt_total_mb === null);
r = size(base({ 'DT Claims Rows': [{}] }));
ok('empty table (keyless placeholder) -> readable, claims 0', r.__dt_readable === true && r.dt_parts.claims === 0);
const nodesNoLedger = base(); delete nodesNoLedger['DNC Removed Rows'];
r = size(nodesNoLedger);
ok('ledger read did not run -> unreadable', r.__dt_readable === false && /ledger/.test(r.__dt_error));

// growth
const today = new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
let sd = {};
r = size(base(), sd);
ok('first run: no growth printed, one sample stored', r.dt_growth_7d_mb === null && sd.dt_size_hist.length === 1 && sd.dt_size_hist[0].date === today);
sd = { dt_size_hist: [{ date: daysAgo(1), total: 1 }] };
r = size(base(), sd);
ok('only a 1-day-old sample: still no 7-day growth', r.dt_growth_7d_mb === null);
sd = { dt_size_hist: [{ date: daysAgo(7), total: 0 }] };
r = size(base({ 'DNC Active Rows': led(10, 200000) }), sd);
ok('7-day-old sample -> net growth computed', r.dt_growth_7d_mb !== null && r.dt_growth_7d_mb > 0, String(r.dt_growth_7d_mb));
sd = { dt_size_hist: Array.from({ length: 15 }, (_, i) => ({ date: daysAgo(i + 1), total: 1 })) };
size(base(), sd);
ok('history bounded to 10 samples', sd.dt_size_hist.length === 10);
sd = { dt_size_hist: [{ date: today, total: 999 }] };
size(base(), sd);
ok('a second run on the same day replaces, not duplicates, today', sd.dt_size_hist.filter(h => h.date === today).length === 1 && sd.dt_size_hist[0].total !== 999);

console.log('Compose');
const d0 = size(base());
let t = compose(d0);
ok('no change-log text anywhere', !/change log/i.test(t), t);
ok('DATA TABLES line present, marked ≈, "/ 50"', /\*DATA TABLES\* ≈[\d.]+ MB \/ 50 \(\d+%\)/.test(t), t);
ok('HEALTH line still present', /\*HEALTH\* failed execs/.test(t));
const tPre = compose({ ...fx.sched_agg, __changelog_readable: true, changelog_24h: 5 }, pre);
ok('NON-VACUITY: the old Compose did print the change log', /CRM change log 5 events/.test(tPre), tPre);
const lvl = (mb) => {
  const d = { ...d0, dt_total_mb: mb, dt_pct: Math.round(mb * 2) };
  return compose(d).split('\n').find(l => l.includes('*DATA TABLES*'));
};
ok('< 80% green', lvl(30).startsWith(':large_green_circle:'), lvl(30));
ok('>= 80% amber', lvl(41).startsWith(':large_yellow_circle:'), lvl(41));
ok('>= 90% red', lvl(46).startsWith(':red_circle:'), lvl(46));
t = compose(size(base({ 'DT Claims Rows': [{ error: 'boom' }] })));
ok('unreadable -> "n/a / 50" amber AND a footer gap', /:large_yellow_circle: \*DATA TABLES\* n\/a \/ 50/.test(t) && /data-table size unreadable: claims/.test(t), t);
t = compose({ ...d0, dt_growth_7d_mb: 0.4 });
ok('growth rendered', / · \+0\.4 MB\/7d/.test(t), t);
// 12-line cap keeps the footer
const many = { ...d0, missed_count: 3, missed: [{ name: 'a', why: 'x' }, { name: 'b', why: 'y' }] };
const bigSl = Array.from({ length: 20 }, (_, i) => ({ ...(fx.sched_agg.__sl || [{}])[0], name: 'Campaign ' + i }));
t = compose({ ...many, __sl: (fx.sched_agg.__sl || []).concat(bigSl) });
ok('at most 12 lines', t.split('\n').length <= 12, String(t.split('\n').length));
ok('the "not measured" footer survives the cap', t.split('\n').pop().startsWith(':information_source:'), t.split('\n').pop());

// graph
console.log('Graph');
const names = new Set(post.nodes.map(n => n.name));
ok('changelog nodes gone', !names.has('CRM Changelog 24h') && !names.has('Changelog Count'));
const nxt = (n) => ((post.connections[n] || {}).main || [[]])[0].map(x => x.node);
ok('Sched Agg -> DT Domains Rows -> DT Domains Agg -> DT Claims Rows -> DT Size Agg -> Compose',
  JSON.stringify(['Sched Agg', 'DT Domains Rows', 'DT Domains Agg', 'DT Claims Rows', 'DT Size Agg'].map(nxt))
  === JSON.stringify([['DT Domains Rows'], ['DT Domains Agg'], ['DT Claims Rows'], ['DT Size Agg'], ['Compose']]));
const inbound = {};
for (const [s, v] of Object.entries(post.connections)) for (const br of v.main || []) for (const x of br) (inbound[x.node] = inbound[x.node] || []).push(s);
ok('every new node has exactly ONE inbound source (no per-branch double fire)',
  ['DT Domains Rows', 'DT Domains Agg', 'DT Claims Rows', 'DT Size Agg', 'Compose'].every(n => (inbound[n] || []).length === 1), JSON.stringify(inbound));
// what safe_patch PUTs: nodes + connections (activeVersion is the GET's read-only copy of the OLD version)
ok('no reference to the deleted table in what is deployed',
  !JSON.stringify({ n: post.nodes, c: post.connections }).includes('zAW2IYoO6Dj0vdIt'));
const reads = post.nodes.filter(n => n.name.startsWith('DT ') && n.type.endsWith('dataTable'));
ok('both new reads: mode id, alwaysOutputData, continueRegularOutput', reads.length === 2 && reads.every(n =>
  n.parameters.dataTableId.mode === 'id' && n.alwaysOutputData === true && n.onError === 'continueRegularOutput'));
ok('everything unchanged outside CONFIG/Compose/new nodes', pre.nodes.filter(n => !['CONFIG', 'Compose', 'CRM Changelog 24h', 'Changelog Count'].includes(n.name))
  .every(n => JSON.stringify(n) === JSON.stringify(post.nodes.find(m => m.name === n.name))));

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
