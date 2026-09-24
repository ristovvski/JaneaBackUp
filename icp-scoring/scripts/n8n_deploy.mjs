#!/usr/bin/env node
/**
 * scripts/n8n_deploy.mjs — the safe patch: build WF-ICP-Score and PUT it over
 * the live one, or put a saved version back.
 *
 * The protocol, in order, and every step refuses rather than guesses:
 *
 *   1. GET the live workflow and SAVE IT as the rollback — outside the repo,
 *      because it carries the live webhook paths (SECURITY.md: a path is a
 *      credential).
 *   2. Quiet window: refuse while an execution of this workflow is running.
 *   3. Build IN MEMORY from the repo, inheriting from the live workflow the
 *      things a build cannot have: the webhook paths, the error workflow id,
 *      the baked Clay/Slack values. Nothing with a live path is written to disk.
 *   4. Refuse if a built webhook path differs from the live one. A deploy must
 *      never rotate an endpoint: Pipedrive's subscription and Clay's callback
 *      column both hold these paths, and neither would tell us it broke.
 *   5. Resolve credentials by TYPE against the live workflow (then the
 *      instance), never by pasting an id into a tracked file.
 *   6. PUT {name, nodes, connections, settings, staticData}. The NAME is the
 *      build's, not the live one — that is how a rename ships. staticData is
 *      echoed back so the Dedupe ledger survives the deploy.
 *   7. Re-GET and diff intended against actual: "DIFFS none", or exit 3 with
 *      the rollback command.
 *   8. The live active state is restored and verified.
 *
 * Deliberate deviation from the golden example's "deactivate → PUT →
 * reactivate": this workflow is PUT while active. n8n re-registers the
 * webhooks itself on an update, and a deactivated window would answer Clay's
 * callback with a 404 — Clay does not retry, so a scored row would be lost.
 * Every deploy since 2026-09-17 has been an active PUT.
 *
 * Usage:
 *   N8N_BASE_URL=... N8N_API_KEY=... node scripts/n8n_deploy.mjs <workflow-id> --dry-run
 *   N8N_BASE_URL=... N8N_API_KEY=... node scripts/n8n_deploy.mjs <workflow-id>
 *   N8N_BASE_URL=... N8N_API_KEY=... node scripts/n8n_deploy.mjs <workflow-id> --rollback <saved.json>
 *
 *   --backup-dir <dir>   where the rollback copy goes (default: $TMPDIR/icp-deploy)
 *   --allow-running      deploy even while an execution is running
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join, resolve, relative, isAbsolute } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = join(ROOT, '..');

const argv = process.argv.slice(2);
const flag = (name) => {
  const i = argv.indexOf(name);
  return i === -1 ? null : argv[i + 1];
};
const DRY = argv.includes('--dry-run');
const ALLOW_RUNNING = argv.includes('--allow-running');
const ROLLBACK = flag('--rollback');
const BACKUP_DIR = resolve(flag('--backup-dir') || join(tmpdir(), 'icp-deploy'));
const valued = new Set([flag('--rollback'), flag('--backup-dir')].filter(Boolean));
const ID = argv.find((a) => !a.startsWith('--') && !valued.has(a)) || process.env.ICP_N8N_WORKFLOW_ID;

const BASE = (process.env.N8N_BASE_URL || '').replace(/\/$/, '');
const KEY = process.env.N8N_API_KEY;
const die = (msg, code = 1) => { console.error(msg); process.exit(code); };
if (!BASE || !KEY) die('N8N_BASE_URL and N8N_API_KEY must be set');
if (!ID) die('usage: node scripts/n8n_deploy.mjs <workflow-id> [--dry-run] [--rollback <saved.json>]');

// The rollback copy holds live webhook paths. It must not land where git sees it.
const rel = relative(REPO, BACKUP_DIR);
if (!rel.startsWith('..') && !isAbsolute(rel)) {
  die(`--backup-dir ${BACKUP_DIR} is inside the repository; the rollback copy carries live webhook paths`);
}

const api = async (path, init = {}) => {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    ...init,
    headers: { 'X-N8N-API-KEY': KEY, 'Content-Type': 'application/json', ...(init.headers || {}) },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${init.method || 'GET'} ${path} -> ${res.status} ${text.slice(0, 400)}`);
  return text ? JSON.parse(text) : null;
};

// The settings keys the public API accepts on a PUT. n8n adds others
// server-side (timeSavedMode, availableInMCP) and then rejects them on the way
// back in, so a rollback copied verbatim from a GET would be refused.
const WRITABLE_SETTINGS = [
  'executionOrder', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution',
  'saveExecutionProgress', 'errorWorkflow', 'timezone', 'callerPolicy', 'callerIds', 'executionTimeout',
];
const writableSettings = (settings = {}) =>
  Object.fromEntries(Object.entries(settings).filter(([k]) => WRITABLE_SETTINGS.includes(k)));

const webhookPaths = (nodes) => Object.fromEntries(
  nodes.filter((n) => n.type === 'n8n-nodes-base.webhook').map((n) => [n.name, n.parameters && n.parameters.path])
);

// ---------------------------------------------------------------------------
// 1. What is live now, saved before anything else happens
// ---------------------------------------------------------------------------
const live = await api(`/workflows/${ID}`);
const liveByName = new Map(live.nodes.map((n) => [n.name, n]));
const livePaths = webhookPaths(live.nodes);

mkdirSync(BACKUP_DIR, { recursive: true, mode: 0o700 });
const backupPath = join(BACKUP_DIR, `${ID}-${live.versionId || 'noversion'}.json`);
writeFileSync(backupPath, `${JSON.stringify(live, null, 2)}\n`, { mode: 0o600 });

console.log(`\n${live.name} (${ID})  version ${live.versionId}  active=${live.active}`);
console.log(`  rollback saved: ${backupPath}`);

// ---------------------------------------------------------------------------
// 2. Quiet window
// ---------------------------------------------------------------------------
const last = await api(`/executions?workflowId=${ID}&limit=1`);
const lastRun = last && last.data && last.data[0];
console.log(`  last execution: ${lastRun ? `${lastRun.id} at ${lastRun.startedAt} (${lastRun.status})` : 'none'}`);
// Older instances reject status=running; then the newest execution is the
// evidence, and an unfinished one counts as running.
let runningIds;
try {
  const running = await api(`/executions?workflowId=${ID}&status=running&limit=5`);
  runningIds = ((running && running.data) || []).map((e) => e.id);
} catch {
  runningIds = lastRun && lastRun.finished === false && !lastRun.stoppedAt ? [lastRun.id] : [];
}
if (runningIds.length > 0 && !ALLOW_RUNNING) {
  die(`  REFUSED: ${runningIds.length} execution(s) running now (${runningIds.join(', ')}). ` +
    'Wait for a lull, or pass --allow-running.', 2);
}

// ---------------------------------------------------------------------------
// 3-5. The body to PUT: a fresh build, or the saved version
// ---------------------------------------------------------------------------
let body;
let credentialReport = [];

if (ROLLBACK) {
  const saved = JSON.parse(readFileSync(ROLLBACK, 'utf8'));
  body = {
    name: saved.name,
    nodes: saved.nodes,
    connections: saved.connections,
    settings: writableSettings(saved.settings),
    ...(saved.staticData ? { staticData: saved.staticData } : {}),
  };
  console.log(`  ROLLBACK to ${ROLLBACK} (version ${saved.versionId})`);
} else {
  // The CONFIG Set node's expression carries `const BAKED = {...}` — the three
  // environment URLs, baked at the last build. Read them back rather than
  // asking the operator to re-export them.
  const bakedFromLive = () => {
    const cfg = liveByName.get('CONFIG');
    if (!cfg || !cfg.parameters || typeof cfg.parameters.jsonOutput !== 'string') return {};
    const m = cfg.parameters.jsonOutput.match(/const BAKED = (\{.*?\}); const pick/s);
    if (!m) return {};
    try { return JSON.parse(m[1]); } catch { return {}; }
  };
  const baked = bakedFromLive();
  const inherit = (key, value) => { if (!process.env[key] && value) process.env[key] = value; };
  inherit('ICP_WEBHOOK_PATH_A', livePaths['Webhook Pipedrive']);
  inherit('ICP_WEBHOOK_PATH_B', livePaths['Webhook Clay']);
  inherit('ICP_ERROR_WORKFLOW_ID', live.settings && live.settings.errorWorkflow);
  inherit('ICP_CLAY_ENGINE_URL', baked.clay_engine_url);
  inherit('ICP_CLAY_CALLBACK_URL', baked.clay_callback_url);
  inherit('ICP_SLACK_CHANNEL', baked.slack_channel_ops);

  // In memory: patch.mjs reads the environment when it is first imported, and
  // writes files only when run as a script, so no live path reaches the disk.
  const { buildWorkflow } = await import(pathToFileURL(join(ROOT, 'n8n', 'patch', 'patch.mjs')).href);
  const { validate } = await import(pathToFileURL(join(ROOT, 'n8n', 'patch', 'validate.mjs')).href);
  const built = buildWorkflow();
  const findings = validate(built, { nodesDir: join(ROOT, 'n8n', 'nodes') });
  if (findings.length > 0) die(`  REFUSED: validate() found ${findings.length} problem(s):\n    ${findings.join('\n    ')}`);

  // 4. Never rotate a live endpoint.
  const builtPaths = webhookPaths(built.nodes);
  for (const [name, path] of Object.entries(builtPaths)) {
    if (livePaths[name] && livePaths[name] !== path) {
      die(`  REFUSED: "${name}" would move off its live path. The Pipedrive subscription and the ` +
        'Clay callback hold that path; a deploy must not change it.', 2);
    }
    if (!livePaths[name] && !process.env[name === 'Webhook Clay' ? 'ICP_WEBHOOK_PATH_B' : 'ICP_WEBHOOK_PATH_A']) {
      die(`  REFUSED: "${name}" has no live counterpart and no path in the environment.`, 2);
    }
  }

  // 5. Credentials by type: the live workflow first, then the instance.
  const byType = new Map();
  for (const node of live.nodes) {
    for (const [type, ref] of Object.entries(node.credentials || {})) {
      if (!byType.has(type)) byType.set(type, ref);
    }
  }
  const wanted = new Set();
  for (const node of built.nodes) {
    for (const type of Object.keys(node.credentials || {})) if (!byType.has(type)) wanted.add(type);
  }
  if (wanted.size > 0) {
    // The ERROR WORKFLOW is asked first: its Slack credential posts where this
    // workflow's failures already land. Archived and throwaway workflows last.
    const all = await api('/workflows?limit=200');
    const errorWorkflowId = live.settings && live.settings.errorWorkflow;
    const rank = (s) => (s.id === errorWorkflowId ? 0 : /^(ARCHIVE__|zz_)/.test(s.name || '') ? 2 : 1);
    for (const summary of (all.data || []).filter((s) => s.id !== ID).sort((a, b) => rank(a) - rank(b))) {
      if (wanted.size === 0) break;
      const other = await api(`/workflows/${summary.id}`);
      for (const node of other.nodes || []) {
        for (const [type, ref] of Object.entries(node.credentials || {})) {
          if (!wanted.has(type)) continue;
          byType.set(type, ref);
          credentialReport.push(`BORROWED ${type} <- ${summary.name} / ${node.name}`);
          wanted.delete(type);
        }
      }
    }
  }
  for (const node of built.nodes) {
    if (!node.credentials) continue;
    const resolved = {};
    for (const type of Object.keys(node.credentials)) {
      const ref = byType.get(type);
      if (ref) resolved[type] = ref;
      else credentialReport.push(`DROPPED ${node.name}:${type} (nothing on the instance carries it)`);
    }
    if (Object.keys(resolved).length > 0) node.credentials = resolved;
    else delete node.credentials;
  }

  body = {
    name: built.name,
    nodes: built.nodes,
    connections: built.connections,
    settings: built.settings,
    ...(live.staticData ? { staticData: live.staticData } : {}),
  };
}

// ---------------------------------------------------------------------------
// The plan
// ---------------------------------------------------------------------------
const added = body.nodes.filter((n) => !liveByName.has(n.name)).map((n) => n.name);
const removed = live.nodes.filter((n) => !body.nodes.some((b) => b.name === n.name)).map((n) => n.name);
console.log(`  name:  ${live.name === body.name ? `${body.name} (unchanged)` : `"${live.name}" -> "${body.name}"`}`);
console.log(`  nodes: ${live.nodes.length} live -> ${body.nodes.length}`);
if (added.length) console.log(`  added:   ${added.join(', ')}`);
if (removed.length) console.log(`  removed: ${removed.join(', ')}`);
console.log(`  webhook paths: ${Object.keys(livePaths).join(', ')} — unchanged (asserted)`);
console.log(`  staticData: ${body.staticData ? 'echoed back (Dedupe ledger kept)' : 'none live'}`);
for (const line of credentialReport) console.log(`  credentials ${line}`);

if (DRY) { console.log('\n--dry-run: nothing sent.'); process.exit(0); }

// ---------------------------------------------------------------------------
// 6-8. PUT, verify, active state
// ---------------------------------------------------------------------------
await api(`/workflows/${ID}`, { method: 'PUT', body: JSON.stringify(body) });
let after = await api(`/workflows/${ID}`);

if (live.active && !after.active) {
  await api(`/workflows/${ID}/activate`, { method: 'POST' });
  after = await api(`/workflows/${ID}`);
}

const diffs = [];
if (after.name !== body.name) diffs.push(`name is "${after.name}", intended "${body.name}"`);
const names = (nodes) => nodes.map((n) => n.name).sort().join('|');
if (names(after.nodes) !== names(body.nodes)) diffs.push('node set differs');
const afterPaths = webhookPaths(after.nodes);
for (const [name, path] of Object.entries(livePaths)) {
  if (afterPaths[name] !== path) diffs.push(`"${name}" path changed`);
}
const afterByName = new Map(after.nodes.map((n) => [n.name, n]));
for (const node of body.nodes) {
  const got = afterByName.get(node.name);
  if (!got) continue;
  if (got.type !== node.type) diffs.push(`${node.name}: type ${got.type}`);
  const code = (n) => n.parameters && n.parameters.jsCode;
  if (code(node) !== code(got)) diffs.push(`${node.name}: jsCode differs`);
}
if (JSON.stringify(after.connections) !== JSON.stringify(body.connections)) diffs.push('connections differ');
if (after.active !== live.active) diffs.push(`active is ${after.active}, was ${live.active}`);

console.log(`\nPUT ok — version ${live.versionId} -> ${after.versionId}, ${after.nodes.length} nodes, active=${after.active}`);
if (diffs.length) {
  console.log(`DIFFS ${diffs.length}:\n  ${diffs.join('\n  ')}`);
  console.log(`rollback: node scripts/n8n_deploy.mjs ${ID} --rollback ${backupPath}`);
  process.exit(3);
}
console.log('DIFFS none');
console.log(`rollback, if ever needed: node scripts/n8n_deploy.mjs ${ID} --rollback ${backupPath}`);
