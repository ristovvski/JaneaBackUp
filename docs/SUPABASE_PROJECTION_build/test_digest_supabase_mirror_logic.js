// Local sanity check of the patched dnc_morning_digest Compose DNC line + the new Agg node.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, 'patched_dnc_morning_digest.json'), 'utf8'));
const byName = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));

let passed = 0;
function t(name, fn) { fn(); passed++; console.log('  ok  -', name); }

// ---- Supabase Mirror Agg ----
{
  const fn = new Function('$', byName['Supabase Mirror Agg'].parameters.jsCode);
  const dollar = (prev, countResp, metaResp) => (name) => {
    if (name === 'DNC Removed Agg') return { first: () => ({ json: prev }) };
    if (name === 'Supabase Mirror Check') return { first: () => ({ json: countResp }) };
    if (name === 'Supabase Meta Check') return { first: () => ({ json: metaResp }) };
    throw new Error('unexpected $() ref: ' + name);
  };
  t('Agg: reachable + fresh sync computes rows and a small age', () => {
    const now = Date.now();
    const out = fn(dollar({ some_prior_field: 1 },
      { headers: { 'content-range': '0-0/25729' } },
      { body: [{ last_sync_at: new Date(now - 5 * 60000).toISOString() }] }))[0].json;
    assert.equal(out.supabase_reachable, true);
    assert.equal(out.supabase_rows, 25729);
    assert.ok(out.supabase_age_min >= 4 && out.supabase_age_min <= 6);
    assert.equal(out.some_prior_field, 1, 'must preserve all prior digest fields');
  });
  t('Agg: a failed count check (network error) reads as unreachable, not a stale 0', () => {
    const out = fn(dollar({}, { error: { message: 'timeout' } }, { body: [] }))[0].json;
    assert.equal(out.supabase_reachable, false);
    assert.equal(out.supabase_rows, null);
  });
  t('Agg: no meta rows at all (never synced) gives reachable:true but age:null, never a fake 0', () => {
    const out = fn(dollar({}, { headers: { 'content-range': '0-0/0' } }, { body: [] }))[0].json;
    assert.equal(out.supabase_reachable, true);
    assert.equal(out.supabase_age_min, null);
  });
}

// ---- Compose DNC line ----
{
  const js = byName['Compose'].parameters.jsCode;
  assert.ok(js.includes('Supabase mirror'), 'patch must actually be present in Compose');
  // extract just the DNC block body for isolated execution (it references d, num, dot, base, cfg
  // from Compose's outer scope -- reconstruct a minimal harness matching that contract).
  const dot = (s) => (s === 'red' ? ':red_circle:' : s === 'amber' ? ':large_yellow_circle:' : ':large_green_circle:');
  const num = (v) => (v === null || v === undefined ? 'n/a' : String(v));
  const runDncBlock = (d) => {
    const cfg = { gate_monitor_id: 'x' };
    const base = 'https://n8n.example';
    const L = [];
    const fn = new Function('d', 'cfg', 'base', 'L', 'dot', 'num',
      js.slice(js.indexOf('// ---------- 4 DNC'), js.indexOf('// ---------- 5 HEALTH')));
    fn(d, cfg, base, L, dot, num);
    return L[0];
  };

  t('DNC line: reachable + fresh -> green dot, "reachable" text', () => {
    const line = runDncBlock({ dnc_active: 100, dnc_added_24h: 1, dnc_removed_24h: 0,
      __gate_readable: true, gate_healthy: true, gate_latency_ms: 150, gate_failures_today: 0, gate_checks_today: 96,
      supabase_reachable: true, supabase_rows: 25729, supabase_age_min: 3 });
    assert.ok(line.startsWith(':large_green_circle:'));
    assert.ok(line.includes('Supabase mirror: 25729 rows · age 3 min · reachable'));
  });
  t('DNC line: reachable but stale (>60min) -> amber, even with a healthy gate', () => {
    const line = runDncBlock({ dnc_active: 100, dnc_added_24h: 1, dnc_removed_24h: 0,
      __gate_readable: true, gate_healthy: true, gate_latency_ms: 150, gate_failures_today: 0, gate_checks_today: 96,
      supabase_reachable: true, supabase_rows: 25729, supabase_age_min: 90 });
    assert.ok(line.startsWith(':large_yellow_circle:'));
  });
  t('DNC line: unreachable -> red, even with a healthy gate', () => {
    const line = runDncBlock({ dnc_active: 100, dnc_added_24h: 1, dnc_removed_24h: 0,
      __gate_readable: true, gate_healthy: true, gate_latency_ms: 150, gate_failures_today: 0, gate_checks_today: 96,
      supabase_reachable: false, supabase_rows: null, supabase_age_min: null });
    assert.ok(line.startsWith(':red_circle:'));
    assert.ok(line.includes('UNREACHABLE'));
  });
  t('DNC line: gate FAILING still wins red even if Supabase is fine (existing behavior preserved)', () => {
    const line = runDncBlock({ dnc_active: 100, dnc_added_24h: 1, dnc_removed_24h: 0,
      __gate_readable: true, gate_healthy: false, gate_latency_ms: 30000, gate_failures_today: 5, gate_checks_today: 96,
      supabase_reachable: true, supabase_rows: 25729, supabase_age_min: 3 });
    assert.ok(line.startsWith(':red_circle:'));
    assert.ok(line.includes('gate FAILING'));
  });
  t('DNC line: null age (never synced) counts as stale, not a crash', () => {
    const line = runDncBlock({ dnc_active: 100, dnc_added_24h: 1, dnc_removed_24h: 0,
      __gate_readable: true, gate_healthy: true, gate_latency_ms: 150, gate_failures_today: 0, gate_checks_today: 96,
      supabase_reachable: true, supabase_rows: 0, supabase_age_min: null });
    assert.ok(line.startsWith(':large_yellow_circle:'));
    assert.ok(line.includes('age n/a min'));
  });
}

// ---- structural ----
{
  const names = new Set(wf.nodes.map((n) => n.name));
  t('every connection target is a real node', () => {
    for (const [src, conn] of Object.entries(wf.connections)) {
      for (const branch of conn.main) {
        for (const c of branch) assert.ok(names.has(c.node), `${src} -> missing node ${c.node}`);
      }
    }
  });
  t('no duplicate node names', () => {
    const counts = {};
    wf.nodes.forEach((n) => { counts[n.name] = (counts[n.name] || 0) + 1; });
    const dupes = Object.entries(counts).filter(([, c]) => c > 1);
    assert.deepEqual(dupes, []);
  });
  t('both new HTTP checks have onError:continueErrorOutput (must not crash the whole digest)', () => {
    assert.equal(byName['Supabase Mirror Check'].onError, 'continueErrorOutput');
    assert.equal(byName['Supabase Meta Check'].onError, 'continueErrorOutput');
  });
}

console.log(`\n${passed} passed, 0 failed`);
