// Local, no-n8n sanity check of dnc_supabase_delta_pusher's node logic.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const wf = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'workflows', 'dnc_supabase_delta_pusher', 'dnc_supabase_delta_pusher.json'), 'utf8'));
const byName = Object.fromEntries(wf.nodes.map(n => [n.name, n]));

let passed = 0;
function t(name, fn) { fn(); passed++; console.log('  ok  -', name); }

// ---- Parse Claim Id (runOnceForEachItem -- $json is the current claim row) ----
{
  const fn = new Function('$json', byName['Parse Claim Id'].parameters.jsCode);
  t('Parse Claim Id: returns a bare object, not an array (runOnceForEachItem contract)', () => {
    const out = fn({ claim_key: 'supabase_delta_registry|12345' });
    assert.ok(!Array.isArray(out), 'must NOT be array-wrapped in each-item mode');
    assert.ok(out.json && typeof out.json === 'object');
  });
  t('Parse Claim Id: well-formed key extracts the numeric registry id', () => {
    const out = fn({ claim_key: 'supabase_delta_registry|12345' }).json;
    assert.equal(out.registry_id, 12345);
    assert.equal(out.claim_key, 'supabase_delta_registry|12345');
  });
  t('Parse Claim Id: wrong-prefix key (foreign family, shared table) yields null id, not a crash', () => {
    const out = fn({ claim_key: 'some_other_family|999' }).json;
    assert.equal(out.registry_id, null);
  });
  t('Parse Claim Id: non-numeric suffix yields null id', () => {
    const out = fn({ claim_key: 'supabase_delta_registry|not-a-number' }).json;
    assert.equal(out.registry_id, null);
  });
}

// ---- Build Push Item (runOnceForAllItems -- explicit join, not pairedItem inference) ----
{
  const fn = new Function('$input', '$', byName['Build Push Item'].parameters.jsCode);
  const call = (claims, rows) => {
    const mockDollar = (name) => {
      if (name === 'Parse Claim Id') return { all: () => claims.map((c) => ({ json: c })) };
      throw new Error('unexpected $() ref: ' + name);
    };
    const mockInput = { all: () => rows.map((r) => ({ json: r })) };
    return fn(mockInput, mockDollar);
  };

  t('Build Push Item: exact N-claims-in/N-items-out even when 0 rows were found', () => {
    const claims = [{ claim_key: 'k1', registry_id: 1 }, { claim_key: 'k2', registry_id: 2 }];
    const out = call(claims, []);
    assert.equal(out.length, 2);
    assert.ok(out.every((o) => o.json.found === false));
  });
  t('Build Push Item: correctly joins by id, not by array position', () => {
    const claims = [{ claim_key: 'k1', registry_id: 1 }, { claim_key: 'k2', registry_id: 2 }];
    const rows = [
      { id: 2, identity_key: 'second' },
      { id: 1, identity_key: 'first' },
    ];
    const out = call(claims, rows);
    assert.equal(out.find((o) => o.json.claim_key === 'k1').json.__body[0].identity_key, 'first');
    assert.equal(out.find((o) => o.json.claim_key === 'k2').json.__body[0].identity_key, 'second');
  });
  t('Build Push Item: a malformed claim (null registry_id) is always found:false, never crashes on lookup', () => {
    const claims = [{ claim_key: 'bad', registry_id: null }];
    const out = call(claims, [{ id: 1, identity_key: 'x' }]);
    assert.equal(out[0].json.found, false);
  });
  t('Build Push Item: a row missing the positive shape (echoed error, not real data) is treated as not-found', () => {
    const claims = [{ claim_key: 'k1', registry_id: 1 }];
    const out = call(claims, [{ error: 'something' }]);
    assert.equal(out[0].json.found, false);
  });
  t('Build Push Item: found row projects only the documented registry columns', () => {
    const claims = [{ claim_key: 'k1', registry_id: 1 }];
    const rows = [{ id: 1, identity_key: 'x', SOME_UNEXPECTED_COLUMN: 'nope', status: 'active' }];
    const out = call(claims, rows);
    assert.equal(out[0].json.found, true);
    const body = out[0].json.__body[0];
    assert.equal(body.SOME_UNEXPECTED_COLUMN, undefined);
    assert.equal(body.status, 'active');
    assert.equal(body.full_name, null, 'a documented-but-absent column must project as null, not be omitted');
  });
}

// ---- Count Claims Seen / Any Claims? / Build Delta Meta Row ----
// Redesigned 2026-09-14: reporting is a SEPARATE, single-source branch fed directly off "Fetch
// Pending Claims" (fan-OUT, safe), not an aggregation converging from the per-claim push/delete
// branches (fan-IN, proven unreliable live -- a Merge(append,3) collapsing skipped/pushed/failed
// worked with a genuinely mixed multi-claim batch but silently never fired with exactly one
// populated outcome, which is the NORMAL steady-state case). The trade-off: row_count is "claims
// seen this cycle", not "claims successfully pushed" -- never persisted with that precision
// anyway (dnc_registry_meta only has last_sync_at/row_count/source).
{
  const countFn = new Function('$input', byName['Count Claims Seen'].parameters.jsCode);
  t('Count Claims Seen: reflects Fetch Pending Claims\' own item count directly', () => {
    const out = countFn({ all: () => [{ json: {} }, { json: {} }, { json: {} }] })[0].json;
    assert.equal(out.claims_seen, 3);
  });
  t('Count Claims Seen: zero pending claims is a clean zero, not a crash', () => {
    const out = countFn({ all: () => [] })[0].json;
    assert.equal(out.claims_seen, 0);
  });

  const metaFn = new Function('$input', byName['Build Delta Meta Row'].parameters.jsCode);
  t('Build Delta Meta Row: shapes a dnc_registry_meta row keyed source=delta_push:dnc_registry', () => {
    const out = metaFn({ first: () => ({ json: { claims_seen: 4 } }) })[0].json;
    assert.equal(out.__body[0].source, 'delta_push:dnc_registry');
    assert.equal(out.__body[0].row_count, 4);
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
  t('Fetch Pending Claims has alwaysOutputData (an empty queue is the common case, must not kill the report)', () => {
    assert.equal(byName['Fetch Pending Claims'].alwaysOutputData, true);
  });
  t('Get Current Row has alwaysOutputData (a not-yet-found row must not kill the report)', () => {
    assert.equal(byName['Get Current Row'].alwaysOutputData, true);
  });
  t('Has Row? false branch and Upsert To Supabase error branch are clean dead ends (no attempt to converge for reporting)', () => {
    assert.deepEqual(wf.connections['Has Row?'].main[1], []);
    assert.deepEqual(wf.connections['Upsert To Supabase'].main[1], []);
    assert.deepEqual(wf.connections['Delete Claim'].main, [[], []]);
  });
  t('regression 2026-09-14: reporting (Count Claims Seen) is fed ONLY by Fetch Pending Claims, never by the per-claim push branches -- the exact fan-in shape that silently never fired for a single-outcome batch', () => {
    const incoming = Object.entries(wf.connections)
      .filter(([, conn]) => conn.main.some((b) => b.some((c) => c.node === 'Count Claims Seen')))
      .map(([src]) => src);
    assert.deepEqual(incoming.sort(), ['Fetch Pending Claims']);
  });
  t('Fetch Pending Claims fans OUT to both Parse Claim Id and Count Claims Seen on both its own branches (success + continueErrorOutput)', () => {
    for (const branch of wf.connections['Fetch Pending Claims'].main) {
      const targets = branch.map((c) => c.node).sort();
      assert.deepEqual(targets, ['Count Claims Seen', 'Parse Claim Id']);
    }
  });
  t('Manual Trigger webhook uses responseMode:onReceived (no respondToWebhook needed for the cron path)', () => {
    assert.equal(byName['Manual Trigger'].parameters.responseMode, 'onReceived');
  });
  t('both triggers feed the same Fetch Pending Claims entry point', () => {
    assert.equal(wf.connections['Drain Timer'].main[0][0].node, 'Fetch Pending Claims');
    assert.equal(wf.connections['Manual Trigger'].main[0][0].node, 'Fetch Pending Claims');
  });
  t('no node anywhere (besides the tolerated trigger pair) is fed by more than one distinct source node', () => {
    const incoming = {};
    for (const [src, conn] of Object.entries(wf.connections)) {
      for (const branch of conn.main) {
        for (const c of branch) {
          if (!incoming[c.node]) incoming[c.node] = new Set();
          incoming[c.node].add(src);
        }
      }
    }
    const triggerPair = new Set(['Drain Timer', 'Manual Trigger']);
    const offenders = Object.entries(incoming).filter(([, srcs]) => {
      if (srcs.size <= 1) return false;
      return !(srcs.size === 2 && [...srcs].every((s) => triggerPair.has(s)));
    });
    assert.deepEqual(offenders, []);
  });
}

console.log(`\n${passed} passed, 0 failed`);
