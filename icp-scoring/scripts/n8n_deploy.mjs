#!/usr/bin/env node
/**
 * scripts/n8n_deploy.mjs — build WF-ICP-Score and PUT it over the live one.
 *
 * The three things a real deployment needs that a build cannot have — the
 * webhook paths, the error workflow id and the three environment URLs — are
 * read back OUT of the workflow already on the instance, not out of a file and
 * not out of the operator's shell. That is deliberate:
 *
 *   - SECURITY.md treats a webhook path as a credential, so it cannot live in
 *     git. It already lives in n8n. Reading it from there means a redeploy
 *     cannot silently rotate a live endpoint and break the Pipedrive
 *     subscription, which is what happens when the path comes from an env var
 *     somebody forgot to export.
 *   - The Clay engine and callback URLs are unguessable endpoints for the same
 *     reason, and the CONFIG Set node already carries them baked in.
 *
 * So the first deploy of a fresh workflow still needs ICP_WEBHOOK_PATH_A/B and
 * friends in the environment; every deploy after that inherits them.
 *
 * Credentials are resolved the same way: by TYPE, from whatever the live
 * workflow attaches. n8n rejects a whole PUT with "You don't have access to the
 * credentials in the 'X' node" if a NEW node carries a credential name the
 * instance does not know, so a new node inherits the live credential of its
 * type, and a type nothing live carries is dropped rather than guessed.
 *
 * Usage:
 *   N8N_BASE_URL=... N8N_API_KEY=... node scripts/n8n_deploy.mjs <workflow-id>
 *   node scripts/n8n_deploy.mjs <workflow-id> --dry-run
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

const argv = process.argv.slice(2);
const DRY = argv.includes('--dry-run');
const ID = argv.find((a) => !a.startsWith('--')) || process.env.ICP_N8N_WORKFLOW_ID;

const BASE = (process.env.N8N_BASE_URL || '').replace(/\/$/, '');
const KEY = process.env.N8N_API_KEY;
if (!BASE || !KEY) { console.error('N8N_BASE_URL and N8N_API_KEY must be set'); process.exit(1); }
if (!ID) { console.error('usage: node scripts/n8n_deploy.mjs <workflow-id>'); process.exit(1); }

const api = async (path, init = {}) => {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    ...init,
    headers: { 'X-N8N-API-KEY': KEY, 'Content-Type': 'application/json', ...(init.headers || {}) },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${init.method || 'GET'} ${path} -> ${res.status} ${text.slice(0, 400)}`);
  return text ? JSON.parse(text) : null;
};

// ---------------------------------------------------------------------------
// 1. What is live now
// ---------------------------------------------------------------------------
const live = await api(`/workflows/${ID}`);
const liveByName = new Map(live.nodes.map((n) => [n.name, n]));

const livePath = (name) => {
  const node = liveByName.get(name);
  return node && node.parameters ? node.parameters.path : null;
};

// The CONFIG Set node's expression carries `const BAKED = {...}` — the three
// environment URLs, baked at the last build. Read them back rather than asking
// the operator to re-export them.
const bakedFromLive = () => {
  const cfg = liveByName.get('CONFIG');
  if (!cfg || !cfg.parameters || typeof cfg.parameters.jsonOutput !== 'string') return {};
  const m = cfg.parameters.jsonOutput.match(/const BAKED = (\{.*?\}); const pick/s);
  if (!m) return {};
  try { return JSON.parse(m[1]); } catch { return {}; }
};

const baked = bakedFromLive();
const env = { ...process.env };
const inherit = (key, value) => { if (!env[key] && value) env[key] = value; };

inherit('ICP_WEBHOOK_PATH_A', livePath('Webhook Pipedrive'));
inherit('ICP_WEBHOOK_PATH_B', livePath('Webhook Clay'));
inherit('ICP_ERROR_WORKFLOW_ID', live.settings && live.settings.errorWorkflow);
inherit('ICP_CLAY_ENGINE_URL', baked.clay_engine_url);
inherit('ICP_CLAY_CALLBACK_URL', baked.clay_callback_url);
inherit('ICP_SLACK_CHANNEL', baked.slack_channel_ops);

// ---------------------------------------------------------------------------
// 2. Build
// ---------------------------------------------------------------------------
execFileSync(process.execPath, [join(ROOT, 'n8n', 'patch', 'patch.mjs')], { env, stdio: 'inherit' });
const payload = JSON.parse(readFileSync(join(ROOT, 'n8n', 'workflows', 'api-payload.json'), 'utf8'));

// ---------------------------------------------------------------------------
// 3. Resolve credentials by type against the live workflow
// ---------------------------------------------------------------------------
const liveCredentialByType = new Map();
for (const node of live.nodes) {
  for (const [type, ref] of Object.entries(node.credentials || {})) {
    if (!liveCredentialByType.has(type)) liveCredentialByType.set(type, ref);
  }
}

const attached = [];
const dropped = [];
for (const node of payload.nodes) {
  if (!node.credentials) continue;
  const resolved = {};
  for (const type of Object.keys(node.credentials)) {
    const ref = liveCredentialByType.get(type);
    if (ref) { resolved[type] = ref; attached.push(`${node.name}:${type}`); }
    else dropped.push(`${node.name}:${type}`);
  }
  if (Object.keys(resolved).length > 0) node.credentials = resolved;
  else delete node.credentials;
}

// n8n rejects a PUT carrying keys it does not own on update.
const body = {
  name: live.name,
  nodes: payload.nodes,
  connections: payload.connections,
  settings: payload.settings,
};

const newNodes = payload.nodes.filter((n) => !liveByName.has(n.name)).map((n) => n.name);
const goneNodes = live.nodes.filter((n) => !payload.nodes.some((p) => p.name === n.name)).map((n) => n.name);

console.log(`\n${live.name} (${ID})`);
console.log(`  nodes: ${live.nodes.length} live -> ${payload.nodes.length} built`);
if (newNodes.length) console.log(`  added:   ${newNodes.join(', ')}`);
if (goneNodes.length) console.log(`  removed: ${goneNodes.join(', ')}`);
console.log(`  credentials attached: ${attached.length ? attached.join(', ') : '(none)'}`);
if (dropped.length) console.log(`  credentials DROPPED (nothing live carries the type): ${dropped.join(', ')}`);

if (DRY) { console.log('\n--dry-run: nothing sent.'); process.exit(0); }

await api(`/workflows/${ID}`, { method: 'PUT', body: JSON.stringify(body) });
const after = await api(`/workflows/${ID}`);
console.log(`\nPUT ok — ${after.nodes.length} nodes, active=${after.active}, updated ${after.updatedAt}`);
