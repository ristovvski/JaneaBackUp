// Local, no-n8n sanity check of dnc_supabase_initial_load's node logic (Build Items, Build Meta
// Row, Report) -- extracted directly from the generated workflow JSON so this can't drift from
// what's actually deployed.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const wf = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'workflows', 'dnc_supabase_initial_load', 'dnc_supabase_initial_load.json'), 'utf8'));
const byName = Object.fromEntries(wf.nodes.map(n => [n.name, n]));

let passed = 0;
function t(name, fn) { fn(); passed++; console.log('  ok  -', name); }

// ---- Build Items ----
{
  const fn = new Function('$', byName['Build Items'].parameters.jsCode);
  const call = (body) => fn((name) => { if (name === 'Webhook') return { first: () => ({ json: { body } }) };
    throw new Error('unexpected $() ref: ' + name); });

  t('Build Items: rejects unknown table', () => {
    assert.throws(() => call({ table: 'nope', rows: [{ id: 1 }] }), /table must be dnc_registry or dnc_domains/);
  });
  t('Build Items: rejects empty rows (non-finalize)', () => {
    assert.throws(() => call({ table: 'dnc_registry', rows: [] }), /non-empty array/);
  });
  t('Build Items: rejects a row missing its PK column', () => {
    assert.throws(() => call({ table: 'dnc_registry', rows: [{ identity_key: 'x' }] }), /missing PK column id/);
  });
  t('Build Items: rejects a domains row missing domain', () => {
    assert.throws(() => call({ table: 'dnc_domains', rows: [{ status: 'active' }] }), /missing PK column domain/);
  });
  t('Build Items: dry_run defaults true when omitted', () => {
    const out = call({ table: 'dnc_registry', rows: [{ id: 1 }] })[0].json;
    assert.equal(out.dry_run, true);
  });
  t('Build Items: dry_run=false only when explicitly false', () => {
    const out = call({ table: 'dnc_registry', rows: [{ id: 1 }], dry_run: false })[0].json;
    assert.equal(out.dry_run, false);
  });
  t('Build Items: happy path carries row_count + __body', () => {
    const rows = [{ id: 1 }, { id: 2 }];
    const out = call({ table: 'dnc_registry', rows, dry_run: true })[0].json;
    assert.equal(out.finalize, false);
    assert.equal(out.row_count, 2);
    assert.deepEqual(out.__body, rows);
  });
  t('Build Items: finalize:true bypasses the rows requirement', () => {
    const out = call({ table: 'dnc_domains', finalize: true, row_count: 1373, dry_run: true })[0].json;
    assert.equal(out.finalize, true);
    assert.equal(out.row_count, 1373);
    assert.equal(out.table, 'dnc_domains');
  });
}

// ---- Build Meta Row ----
{
  const fn = new Function('$input', byName['Build Meta Row'].parameters.jsCode);
  t('Build Meta Row: shapes a dnc_registry_meta row keyed by source=initial_load:<table>', () => {
    const out = fn({ first: () => ({ json: { table: 'dnc_registry', row_count: 25729 } }) })[0].json;
    assert.equal(out.__body.length, 1);
    assert.equal(out.__body[0].source, 'initial_load:dnc_registry');
    assert.equal(out.__body[0].row_count, 25729);
    assert.ok(out.__body[0].last_sync_at);
  });
}

// ---- Build Report ----
{
  const fn = new Function('$input', '$', byName['Build Report'].parameters.jsCode);
  const ctx = (o) => (name) => { if (name === 'Build Items') return { first: () => ({ json: o }) };
    throw new Error('unexpected $() ref: ' + name); };

  t('Build Report: dry run reports without ok/error framing as a failure', () => {
    const out = fn({ first: () => ({ json: {} }) },
      ctx({ table: 'dnc_registry', dry_run: true, row_count: 5, finalize: false }))[0].json;
    assert.equal(out.ok, true);
    assert.match(out.note, /DRY RUN/);
  });
  t('Build Report: live chunk write reports WRITTEN', () => {
    const out = fn({ first: () => ({ json: { statusCode: 200, headers: {}, body: '' } }) },
      ctx({ table: 'dnc_registry', dry_run: false, row_count: 500, finalize: false }))[0].json;
    assert.equal(out.ok, true);
    assert.match(out.note, /WRITTEN/);
  });
  t('Build Report: finalize reports meta-logged', () => {
    const out = fn({ first: () => ({ json: { statusCode: 200, headers: {}, body: '' } }) },
      ctx({ table: 'dnc_domains', dry_run: false, row_count: 1373, finalize: true }))[0].json;
    assert.equal(out.ok, true);
    assert.match(out.note, /logged to dnc_registry_meta/);
  });
  t('Build Report: an HTTP error surfaces as ok=false with the real error', () => {
    const out = fn({ first: () => ({ json: { error: { description: 'permission denied for table dnc_registry' } } }) },
      ctx({ table: 'dnc_registry', dry_run: false, row_count: 500, finalize: false }))[0].json;
    assert.equal(out.ok, false);
    assert.match(out.note, /permission denied/);
  });
}

// ---- structural: every connection resolves, dry_run gates BOTH real-write paths ----
{
  const names = new Set(wf.nodes.map(n => n.name));
  t('every connection target is a real node', () => {
    for (const [src, conn] of Object.entries(wf.connections)) {
      for (const branch of conn.main) {
        for (const c of branch) assert.ok(names.has(c.node), `${src} -> missing node ${c.node}`);
      }
    }
  });
  t('Is Dry Run? gates BOTH Upsert Chunk and Insert Meta Row (via Is Finalize?)', () => {
    // true (dry) branch must NOT reach Upsert Chunk or Insert Meta Row at all.
    const dryBranch = wf.connections['Is Dry Run?'].main[0].map(c => c.node);
    assert.deepEqual(dryBranch, ['Build Report']);
    const liveBranch = wf.connections['Is Dry Run?'].main[1].map(c => c.node);
    assert.deepEqual(liveBranch, ['Is Finalize?']);
  });
}

console.log(`\n${passed} passed, 0 failed`);
