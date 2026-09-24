// Local, no-n8n sanity check of dnc_supabase_nightly_reconcile's node logic.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const wf = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'workflows', 'dnc_supabase_nightly_reconcile', 'dnc_supabase_nightly_reconcile.json'), 'utf8'));
const byName = Object.fromEntries(wf.nodes.map(n => [n.name, n]));

let passed = 0;
function t(name, fn) { fn(); passed++; console.log('  ok  -', name); }

// ---- Compute Pages Registry ----
{
  const fn = new Function('$', byName['Compute Pages Registry'].parameters.jsCode);
  const dollar = (headerVal) => (name) => {
    if (name === 'Count Supabase Registry') return { first: () => ({ json: { headers: { 'content-range': headerVal } } }) };
    throw new Error('unexpected $() ref: ' + name);
  };
  t('Compute Pages: paginates by 1000 up to the real total', () => {
    const out = fn(dollar('0-0/25729'));
    assert.equal(out.length, 26); // ceil(25729/1000)
    assert.equal(out[0].json.offset, 0);
    assert.equal(out[25].json.offset, 25000);
  });
  t('Compute Pages: an empty table still yields exactly ONE page (so the diff sees 0 supabase rows, not skips entirely)', () => {
    const out = fn(dollar('*/0'));
    assert.equal(out.length, 1);
    assert.equal(out[0].json.offset, 0);
  });
  t('Compute Pages: missing/malformed content-range degrades to a single page, not a crash', () => {
    const out = fn(dollar(undefined));
    assert.equal(out.length, 1);
  });
}

// ---- Diff Registry ----
{
  const fn = new Function('$input', '$', byName['Diff Registry'].parameters.jsCode);
  const call = (n8nRows, supabaseRows) => {
    const dollar = (name) => {
      if (name === 'Get N8N Registry') return { all: () => n8nRows.map((r) => ({ json: r })) };
      throw new Error('unexpected $() ref: ' + name);
    };
    const input = { all: () => supabaseRows.map((r) => ({ json: r })) };
    return fn(input, dollar)[0].json;
  };

  t('Diff: identical rows on both sides -> 0 drift', () => {
    const row = { id: 1, identity_key: 'a', status: 'active', added_at: '2026-01-01T00:00:00.000Z' };
    const out = call([row], [row]);
    assert.equal(out.drifted_count, 0);
    assert.equal(out.matched, 1);
  });
  const full = (over) => Object.assign({
    id: 1, identity_key: 'a', norm_v: 'v1', entry_type: 'manual', reason: 'reply_dnc', source: 's',
    correlation_id: 'c:1', date_precision: 'exact', expiry_review_pending: false, offboard_removable: false,
    also_flagged: '[]', projections_state: '{}', status: 'active', added_at: '2026-01-01T00:00:00.000Z',
    createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z', full_name: 'A B',
  }, over);
  t('Diff: a row missing entirely from Supabase counts as drift', () => {
    const out = call([full({})], []);
    assert.equal(out.drifted_count, 1);
    assert.equal(out.drifted[0].id, 1);
    assert.deepEqual(out.drift_meta[0].changed, ['new_row']);
  });
  t('Diff: a row with a null NOT NULL column is set aside as unhealable, never put in the upsert body', () => {
    const bad = full({ id: 2, correlation_id: null, date_precision: null, full_name: 'Person-054b9bef' });
    const out = call([full({}), bad], []);
    assert.equal(out.drifted_count, 2, 'unhealable rows still count as drift');
    assert.equal(out.healable_count, 1);
    assert.deepEqual(out.drifted.map((r) => r.id), [1], 'the poisoned row must not reach the upsert body');
    assert.deepEqual(out.unhealable[0].null_cols, ['correlation_id', 'date_precision']);
    assert.equal(out.unhealable[0].name, 'Person-054b9bef');
  });
  t('Diff: records WHICH columns changed, minus updatedAt, plus the correlation_id origin', () => {
    const n8nRow = full({ projections_state: '{"pipedrive":"done"}', updatedAt: '2026-09-15T13:00:00.000Z', correlation_id: 's3_persons_watch:86675' });
    const supRow = full({ projections_state: '{"pipedrive":"pending"}', correlation_id: 's3_persons_watch:86675' });
    const m = call([n8nRow], [supRow]).drift_meta[0];
    assert.deepEqual(m.changed, ['projections_state']);
    assert.equal(m.origin, 's3_persons_watch');
  });
  t('Diff: a real field mismatch (status changed in n8n, not yet synced) counts as drift', () => {
    const n8nRow = { id: 1, identity_key: 'a', status: 'removed' };
    const supRow = { id: 1, identity_key: 'a', status: 'active' };
    const out = call([n8nRow], [supRow]);
    assert.equal(out.drifted_count, 1);
  });
  t('Diff: timestamp FORMAT differences (Z vs +00:00, trailing-zero truncation) are NOT drift', () => {
    const n8nRow = { id: 1, added_at: '2026-06-29T15:03:51.310Z' };
    const supRow = { id: 1, added_at: '2026-06-29T15:03:51.31+00:00' };
    const out = call([n8nRow], [supRow]);
    assert.equal(out.drifted_count, 0, 'must not falsely flag equivalent timestamps as drift');
  });
  t('Diff: a row Supabase has but n8n no longer does is reported as extra_in_supabase, NOT deleted', () => {
    const out = call([], [{ id: 99, identity_key: 'ghost' }]);
    assert.equal(out.extra_in_supabase, 1);
    assert.equal(out.drifted_count, 0, 'extras must never be treated as something to overwrite/heal');
  });
  t('Diff: a malformed supabase row (no pk field, e.g. an echoed error) is filtered out, not crashed on', () => {
    const out = call([{ id: 1, identity_key: 'a' }], [{ error: 'nope' }]);
    assert.equal(out.drifted_count, 1); // the real row wasn't found among filtered supabase rows -> drift
  });
}

// ---- Chunk Drift Registry ----
{
  const fn = new Function('$', byName['Chunk Drift Registry'].parameters.jsCode);
  const dollar = (drifted) => (name) => {
    if (name === 'Diff Registry') return { first: () => ({ json: { drifted } }) };
    throw new Error('unexpected $() ref: ' + name);
  };
  t('Chunk Drift: zero healable rows still emits ONE 0-row sentinel, so the upsert->tally->report chain runs', () => {
    const out = fn(dollar([]));
    assert.equal(out.length, 1);
    assert.equal(out[0].json.__n, 0);
    assert.deepEqual(out[0].json.__body, []);
  });
  t('Chunk Drift: exactly 500 rows makes ONE chunk, 501 makes two, each carrying its row count', () => {
    const rows500 = Array.from({ length: 500 }, (_, i) => ({ id: i }));
    assert.equal(fn(dollar(rows500)).length, 1);
    const rows501 = Array.from({ length: 501 }, (_, i) => ({ id: i }));
    const out = fn(dollar(rows501));
    assert.equal(out.length, 2);
    assert.deepEqual(out.map((c) => c.json.__n), [500, 1]);
  });
}

// ---- Tally Upsert Registry ----
{
  const fn = new Function('$input', '$', byName['Tally Upsert Registry'].parameters.jsCode);
  const call = (chunks, results) => fn(
    { all: () => results.map((r) => ({ json: r })) },
    (name) => { if (name === 'Chunk Drift Registry') return { all: () => chunks.map((c) => ({ json: c })) };
      throw new Error('unexpected $() ref: ' + name); })[0].json;
  t('Tally: a rejected chunk counts its rows as FAILED with the error text, never as healed', () => {
    const out = call([{ __n: 500 }, { __n: 1 }], [
      { error: { description: 'null value in column "correlation_id" violates not-null constraint' } },
      { statusCode: 201 },
    ]);
    assert.equal(out.healed, 1);
    assert.equal(out.failed, 500);
    assert.ok(out.errors[0].includes('correlation_id'));
  });
  t('Tally: the 0-row sentinel neither heals nor fails anything, even if the empty POST errored', () => {
    const out = call([{ __n: 0 }], [{ error: { message: 'whatever' } }]);
    assert.deepEqual([out.healed, out.failed, out.errors.length], [0, 0, 0]);
  });
}

// ---- Report Registry ----
{
  const fn = new Function('$input', '$', byName['Report Registry'].parameters.jsCode);
  const diff = {
    table: 'Registry', n8n_total: 10, supabase_total: 9, matched: 7, drifted_count: 3, extra_in_supabase: 0,
    drift_meta: [
      { key: 5, name: 'A', changed: ['projections_state'], origin: 's1' },
      { key: 6, name: 'B', changed: ['projections_state'], origin: null },
    ],
    unhealable: [{ key: 9, name: 'Person-054b9bef', changed: ['new_row'], origin: null, null_cols: ['correlation_id'] }],
  };
  const out = fn({ first: () => ({ json: { healed: 2, failed: 0, errors: [] } }) },
    (name) => { if (name === 'Diff Registry') return { first: () => ({ json: diff }) };
      throw new Error('unexpected $() ref: ' + name); })[0].json;
  t('Report: carries the tally outcome and names drifted rows grouped by changed-column signature', () => {
    assert.equal(out.drifted_count, 3);
    assert.equal(out.healed, 2);
    assert.equal(out.unhealable_count, 1);
    assert.deepEqual(out.groups, [{ sig: 'projections_state', count: 2, examples: ['A (#5, s1)', 'B (#6)'] }]);
    assert.equal(out.unhealable_groups[0].sig, 'null correlation_id');
    assert.deepEqual(out.unhealable_groups[0].examples, ['Person-054b9bef (#9)']);
  });
}

// ---- Combine Reports / Any Drift routing ----
{
  const fn = new Function('$', byName['Combine Reports'].parameters.jsCode);
  const dollar = (reg, dom) => (name) => {
    if (name === 'Report Registry') return { first: () => ({ json: reg }) };
    if (name === 'Report Domains') return { first: () => ({ json: dom }) };
    throw new Error('unexpected $() ref: ' + name);
  };
  t('Combine Reports: sums drift across both tables', () => {
    const out = fn(dollar({ drifted_count: 2, n8n_total: 100 }, { drifted_count: 3, n8n_total: 50 }))[0].json;
    assert.equal(out.total_drift, 5);
  });
  t('Combine Reports: zero drift on both sides sums to zero', () => {
    const out = fn(dollar({ drifted_count: 0, n8n_total: 100 }, { drifted_count: 0, n8n_total: 50 }))[0].json;
    assert.equal(out.total_drift, 0);
  });
}

// ---- Build Alert Text / Build Meta Rows ----
{
  const alertFn = new Function('$input', byName['Build Alert Text'].parameters.jsCode);
  const alert = (reg, dom) => alertFn({ first: () => ({ json: { reg, dom } }) })[0].json.text;
  const clean = { drifted_count: 0, n8n_total: 50, extra_in_supabase: 0 };
  t('Build Alert Text: only mentions tables that actually drifted', () => {
    const text = alert({ drifted_count: 2, n8n_total: 100, extra_in_supabase: 0, healed: 2, heal_failed: 0,
      unhealable_count: 0, groups: [], unhealable_groups: [] }, clean);
    assert.ok(text.includes('dnc_registry'));
    assert.ok(!text.includes('dnc_domains'));
  });
  t('Build Alert Text: a failed/unhealable night is NOT reported as healed (the 2026-09-16..24 false claim)', () => {
    const text = alert({ drifted_count: 500, n8n_total: 25946, extra_in_supabase: 0, healed: 0, heal_failed: 418,
      heal_errors: ['null value in column "correlation_id"'], unhealable_count: 82,
      groups: [{ sig: 'projections_state', count: 416, examples: ['Person-d9d8ef6b (#10561, s3_persons_watch)'] }],
      unhealable_groups: [{ sig: 'null correlation_id+date_precision', count: 82, examples: ['Person-054b9bef (#33185)'] }] }, clean);
    assert.ok(text.includes('NOT fully healed'));
    assert.ok(text.includes('healed 0'));
    assert.ok(text.includes('FAILED 418'));
    assert.ok(text.includes('unhealable 82'));
    assert.ok(text.includes('Person-054b9bef (#33185)'), 'unhealable rows must be named');
    assert.ok(text.includes('Person-d9d8ef6b (#10561, s3_persons_watch)'), 'drifted rows must be named');
    assert.ok(!text.includes('healed from n8n'), 'must not claim a heal that did not happen');
  });

  const metaFn = new Function('$input', byName['Build Meta Rows'].parameters.jsCode);
  t('Build Meta Rows: emits exactly 2 items, one per table, correctly sourced', () => {
    const out = metaFn({ first: () => ({ json: {
      reg: { n8n_total: 25729 }, dom: { n8n_total: 1373 },
    } }) });
    assert.equal(out.length, 2);
    assert.equal(out[0].json.__body[0].source, 'nightly_reconcile:dnc_registry');
    assert.equal(out[0].json.__body[0].row_count, 25729);
    assert.equal(out[1].json.__body[0].source, 'nightly_reconcile:dnc_domains');
    assert.equal(out[1].json.__body[0].row_count, 1373);
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
  t('Any Drift? false branch skips the Slack alert entirely, still logs meta', () => {
    const falseBranch = wf.connections['Any Drift?'].main[1].map((c) => c.node);
    assert.deepEqual(falseBranch, ['Build Meta Rows']);
  });
  t('Slack Drift Alert has onError:continueErrorOutput (a Slack outage must not block meta-logging)', () => {
    assert.equal(byName['Slack Drift Alert'].onError, 'continueErrorOutput');
  });
  t('both Get N8N nodes have alwaysOutputData (an empty result must not silently kill the diff)', () => {
    assert.equal(byName['Get N8N Registry'].alwaysOutputData, true);
    assert.equal(byName['Get N8N Domains'].alwaysOutputData, true);
  });
  t('Diff -> Chunk -> Upsert -> Tally -> Report is one linear chain; the upsert keeps failures on its single output', () => {
    for (const table of ['Registry', 'Domains']) {
      const next = (n) => wf.connections[n].main.map((b) => b.map((c) => c.node));
      assert.deepEqual(next(`Diff ${table}`), [[`Chunk Drift ${table}`]]);
      assert.deepEqual(next(`Chunk Drift ${table}`), [[`Upsert Corrections ${table}`]]);
      assert.deepEqual(next(`Upsert Corrections ${table}`), [[`Tally Upsert ${table}`]]);
      assert.deepEqual(next(`Tally Upsert ${table}`), [[`Report ${table}`]]);
      assert.equal(byName[`Upsert Corrections ${table}`].onError, 'continueRegularOutput',
        'continueErrorOutput would split outcomes across two wires into Tally -- the fires-per-branch trap');
    }
  });
  t('both triggers feed ONLY Get N8N Registry -- the two tables run SEQUENTIALLY, not in parallel', () => {
    for (const trig of ['Reconcile Timer', 'Manual Trigger']) {
      const targets = wf.connections[trig].main[0].map((c) => c.node);
      assert.deepEqual(targets, ['Get N8N Registry']);
    }
  });
  t('regression: no node anywhere is fed by more than one DISTINCT source node (the exact bug that fired Combine Reports 4x live 2026-09-14) -- two wires from the SAME trigger pair are the one allowed exception (only one ever fires per real execution)', () => {
    const incoming = {};
    for (const [src, conn] of Object.entries(wf.connections)) {
      for (const branch of conn.main) {
        for (const c of branch) {
          if (!incoming[c.node]) incoming[c.node] = new Set();
          incoming[c.node].add(src);
        }
      }
    }
    const triggerPair = new Set(['Reconcile Timer', 'Manual Trigger']);
    const offenders = Object.entries(incoming).filter(([node, srcs]) => {
      if (srcs.size <= 1) return false;
      // the only tolerated multi-source case: fed exclusively by the two alternative triggers.
      return !(srcs.size === 2 && [...srcs].every((s) => triggerPair.has(s)));
    });
    assert.deepEqual(offenders, [], `unexpected multi-source fan-in: ${JSON.stringify(offenders.map(([n, s]) => [n, [...s]]))}`);
  });
  t('Report Registry chains into Get N8N Domains (sequential handoff between tables)', () => {
    assert.equal(wf.connections['Report Registry'].main[0][0].node, 'Get N8N Domains');
  });
  t('Report Domains is Combine Reports\' only direct predecessor; Report Registry reaches it only via named reference', () => {
    assert.equal(wf.connections['Report Domains'].main[0][0].node, 'Combine Reports');
    const js = byName['Combine Reports'].parameters.jsCode;
    assert.ok(js.includes("$('Report Registry')"), 'Combine Reports must still read Report Registry via named ref');
  });
  t('Get N8N nodes chain through a swallow node before the per-item Supabase pipeline (never feed Count/Fetch Page directly with their own bulk output)', () => {
    for (const table of ['Registry', 'Domains']) {
      assert.equal(wf.connections[`Get N8N ${table}`].main[0][0].node, `Swallow N8N Read ${table}`);
      assert.equal(wf.connections[`Swallow N8N Read ${table}`].main[0][0].node, `Count Supabase ${table}`);
    }
  });
}

console.log(`\n${passed} passed, 0 failed`);
