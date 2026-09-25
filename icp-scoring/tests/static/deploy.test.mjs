// tests/static/deploy.test.mjs — scripts/n8n_deploy.mjs against a mock n8n.
//
// The deploy is the one step that touches the live workflow, so it is the one
// that most needs to be run before it is trusted. The mock plays the live
// instance as it stood before the PROD promotion: named "[DEV]", still carrying
// the dead "Append audit row" node, active, with a Dedupe ledger in staticData.

import { test, describe, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { mkdtempSync, readFileSync, statSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DEPLOY = join(ROOT, 'scripts', 'n8n_deploy.mjs');
const BUILT = JSON.parse(readFileSync(join(ROOT, 'n8n', 'workflows', 'WF-ICP-Score.dev.json'), 'utf8'));
const ID = 'wfMOCK123';
const PATH_A = 'live-path-a-7f3e';
const PATH_B = 'live-path-b-91cc';

function liveFixture() {
  const nodes = JSON.parse(JSON.stringify(BUILT.nodes)).map((n) => {
    if (n.name === 'Webhook Pipedrive') n.parameters.path = PATH_A;
    if (n.name === 'Webhook Clay') n.parameters.path = PATH_B;
    return n;
  });
  nodes.push({
    id: 'dead-audit', name: 'Append audit row', type: 'n8n-nodes-base.dataTable', typeVersion: 1,
    position: [0, 0], parameters: { dataTableId: { value: 'icp_audit' } },
  });
  return {
    id: ID, name: 'WF-ICP-Score [DEV]', active: true, versionId: 'v-before',
    nodes, connections: { ...BUILT.connections, BuildRunSummary: { main: [[{ node: 'Append audit row', type: 'main', index: 0 }]] } },
    settings: { ...BUILT.settings, errorWorkflow: 'wfERR', timeSavedMode: 'fixed', availableInMCP: false },
    staticData: { global: { dedupe: { 'req-1': 1790000000000 } } },
  };
}

let server, port, state;
const reset = (overrides = {}) => {
  state = { live: liveFixture(), puts: [], activations: 0, running: [], ...overrides };
};

before(async () => {
  reset();
  server = createServer((req, res) => {
    let raw = '';
    req.on('data', (c) => { raw += c; });
    req.on('end', () => {
      const url = new URL(req.url, 'http://x');
      const send = (code, body) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
      if (req.headers['x-n8n-api-key'] !== 'test-key') return send(401, { message: 'unauthorized' });
      if (url.pathname === `/api/v1/workflows/${ID}` && req.method === 'GET') return send(200, state.live);
      if (url.pathname === `/api/v1/workflows/${ID}` && req.method === 'PUT') {
        const body = JSON.parse(raw);
        const bad = Object.keys(body.settings || {}).filter((k) => ['timeSavedMode', 'availableInMCP'].includes(k));
        if (bad.length) return send(400, { message: `request/body/settings must NOT have additional properties (${bad})` });
        state.puts.push(body);
        state.live = { ...state.live, ...body, versionId: `v-after-${state.puts.length}`, active: state.deactivateOnPut ? false : state.live.active };
        return send(200, state.live);
      }
      if (url.pathname === `/api/v1/workflows/${ID}/activate` && req.method === 'POST') {
        state.activations++; state.live.active = true; return send(200, state.live);
      }
      if (url.pathname === '/api/v1/workflows') return send(200, { data: [{ id: ID, name: state.live.name }] });
      if (url.pathname === '/api/v1/executions') {
        if (url.searchParams.get('status') === 'running') return send(200, { data: state.running });
        return send(200, { data: [{ id: '66210', startedAt: '2026-09-24T13:30:02Z', status: 'success', finished: true }] });
      }
      return send(404, { message: `mock has no ${req.method} ${url.pathname}` });
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  port = server.address().port;
});
after(() => server.close());

const run = (args, extraEnv = {}) => new Promise((resolve) => {
  const env = { ...process.env, N8N_BASE_URL: `http://127.0.0.1:${port}`, N8N_API_KEY: 'test-key', ...extraEnv };
  for (const k of ['ICP_WEBHOOK_PATH_A', 'ICP_WEBHOOK_PATH_B', 'ICP_ERROR_WORKFLOW_ID', 'ICP_CLAY_ENGINE_URL', 'ICP_CLAY_CALLBACK_URL', 'ICP_SLACK_CHANNEL']) {
    if (!(k in extraEnv)) delete env[k];
  }
  execFile(process.execPath, [DEPLOY, ...args], { env, cwd: ROOT }, (err, stdout, stderr) => {
    resolve({ code: err ? err.code : 0, out: stdout + stderr });
  });
});

const backupDir = () => mkdtempSync(join(tmpdir(), 'icp-deploy-test-'));

describe('n8n_deploy: the PROD promotion', () => {
  test('dry-run shows the rename and the dead node going, and sends nothing', async () => {
    reset();
    const dir = backupDir();
    const r = await run([ID, '--dry-run', '--backup-dir', dir]);
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /name: {2}"WF-ICP-Score \[DEV\]" -> "WF-ICP-Score"/);
    assert.match(r.out, /removed: Append audit row/);
    assert.match(r.out, /--dry-run: nothing sent/);
    assert.equal(state.puts.length, 0);
    rmSync(dir, { recursive: true });
  });

  test('the deploy renames, drops the audit node, keeps both paths and the ledger: DIFFS none', async () => {
    reset();
    const dir = backupDir();
    const r = await run([ID, '--backup-dir', dir]);
    assert.equal(r.code, 0, r.out);
    assert.match(r.out, /DIFFS none/);
    assert.equal(state.puts.length, 1);
    const put = state.puts[0];
    assert.equal(put.name, 'WF-ICP-Score', 'no [DEV] suffix');
    assert.ok(!put.nodes.some((n) => n.name === 'Append audit row'), 'the dead node is gone');
    assert.ok(!JSON.stringify(put).includes('dataTable'), 'nothing reaches a Data Table');
    const path = (name) => put.nodes.find((n) => n.name === name).parameters.path;
    assert.equal(path('Webhook Pipedrive'), PATH_A, 'the Pipedrive subscription keeps working');
    assert.equal(path('Webhook Clay'), PATH_B, 'the Clay callback keeps working');
    assert.deepEqual(put.staticData, { global: { dedupe: { 'req-1': 1790000000000 } } }, 'Dedupe ledger kept');
    assert.equal(put.settings.errorWorkflow, 'wfERR', 'error workflow inherited');
    assert.equal(state.live.active, true);
    rmSync(dir, { recursive: true });
  });

  test('the rollback copy is saved before the PUT, outside the repo, owner-only', async () => {
    reset();
    const dir = backupDir();
    await run([ID, '--backup-dir', dir]);
    const [file] = readdirSync(dir);
    assert.equal(file, `${ID}-v-before.json`);
    const saved = JSON.parse(readFileSync(join(dir, file), 'utf8'));
    assert.equal(saved.name, 'WF-ICP-Score [DEV]', 'the pre-deploy version, not the new one');
    assert.equal(statSync(join(dir, file)).mode & 0o777, 0o600);
    rmSync(dir, { recursive: true });
  });

  test('a PUT that leaves the workflow inactive is reactivated and verified', async () => {
    reset({ deactivateOnPut: true });
    const dir = backupDir();
    const r = await run([ID, '--backup-dir', dir]);
    assert.equal(r.code, 0, r.out);
    assert.equal(state.activations, 1);
    assert.match(r.out, /active=true/);
    rmSync(dir, { recursive: true });
  });

  test('--rollback puts the saved version back, minus the settings n8n refuses', async () => {
    reset();
    const dir = backupDir();
    await run([ID, '--backup-dir', dir]);
    const saved = join(dir, `${ID}-v-before.json`);
    const r = await run([ID, '--rollback', saved, '--backup-dir', dir]);
    assert.equal(r.code, 0, r.out);
    const put = state.puts[1];
    assert.equal(put.name, 'WF-ICP-Score [DEV]');
    assert.ok(put.nodes.some((n) => n.name === 'Append audit row'));
    assert.ok(!('timeSavedMode' in put.settings) && !('availableInMCP' in put.settings));
    assert.match(r.out, /DIFFS none/);
    rmSync(dir, { recursive: true });
  });
});

describe('n8n_deploy: what it refuses', () => {
  test('it will not move a webhook off its live path', async () => {
    reset();
    const dir = backupDir();
    const r = await run([ID, '--backup-dir', dir], { ICP_WEBHOOK_PATH_A: 'somewhere-else' });
    assert.equal(r.code, 2, r.out);
    assert.match(r.out, /REFUSED: "Webhook Pipedrive" would move off its live path/);
    assert.equal(state.puts.length, 0);
    rmSync(dir, { recursive: true });
  });

  test('it will not deploy while an execution is running', async () => {
    reset({ running: [{ id: '66211' }] });
    const dir = backupDir();
    const r = await run([ID, '--backup-dir', dir]);
    assert.equal(r.code, 2, r.out);
    assert.match(r.out, /REFUSED: 1 execution\(s\) running now \(66211\)/);
    assert.equal(state.puts.length, 0);
    rmSync(dir, { recursive: true });
  });

  test('it will not write the rollback copy inside the repository', async () => {
    reset();
    const r = await run([ID, '--dry-run', '--backup-dir', join(ROOT, 'tmp-backup')]);
    assert.equal(r.code, 1, r.out);
    assert.match(r.out, /inside the repository/);
    assert.equal(state.puts.length, 0);
  });
});
