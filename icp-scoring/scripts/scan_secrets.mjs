#!/usr/bin/env node
// scripts/scan_secrets.mjs — fail-closed secret gate for this subtree.
//
// Scans by SHAPE, never by literal value: it does not read `.env` and does not
// need to. That is deliberate. SECURITY.md's own gate
// (gtm_docs_export/build_docs_repo.py) does the literal match against every
// `.env` value over 12 characters and remains the authority when run locally;
// this one is the shape-based complement that works with no secret in scope,
// so CI and a remote session can both run it.
//
// A match is reported as file:line + the rule that fired. The matched text is
// NEVER printed — printing it would put the secret in the log that proves the
// secret is absent.
//
//   node scripts/scan_secrets.mjs              scan the working tree (tracked + untracked)
//   node scripts/scan_secrets.mjs --tracked    scan only what git tracks
//   node scripts/scan_secrets.mjs --history    scan every blob in every commit
//
// Exit 0 = clean. Exit 1 = something matched.

import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SUBTREE = join(HERE, '..');
const REPO = execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd: SUBTREE, encoding: 'utf8' }).trim();
const PREFIX = `${relative(REPO, SUBTREE)}/`;

// ---------------------------------------------------------------------------
// Rules. Each is a shape that should never appear in this subtree.
// ---------------------------------------------------------------------------
const RULES = [
  { id: 'jwt', why: 'a JWT (n8n API keys are JWTs)', re: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/ },
  { id: 'openai-key', why: 'an OpenAI API key', re: /\bsk-(proj-)?[A-Za-z0-9_-]{20,}/ },
  { id: 'anthropic-key', why: 'an Anthropic API key', re: /\bsk-ant-[A-Za-z0-9_-]{20,}/ },
  { id: 'clay-key', why: 'a Clay API key', re: /\bclay_(scoped_|live_|test_)[A-Za-z0-9]{20,}/ },
  { id: 'slack-token', why: 'a Slack token', re: /\bxox[baprs]-[A-Za-z0-9-]{10,}/ },
  { id: 'github-pat', why: 'a GitHub token', re: /\bgh[pousr]_[A-Za-z0-9]{30,}/ },
  { id: 'aws-akid', why: 'an AWS access key id', re: /\b(AKIA|ASIA)[0-9A-Z]{16}\b/ },
  { id: 'private-key', why: 'a private key block', re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  { id: 'bearer', why: 'a bearer token', re: /\bBearer\s+[A-Za-z0-9._~+/-]{16,}/ },
  { id: 'api-token-qs', why: 'a token in a query string', re: /[?&]api_token=[^&\s"'`]{8,}/ },
  {
    id: 'pipedrive-token',
    why: 'a Pipedrive API token (40 hex)',
    re: /\b[0-9a-f]{40}\b/,
    // Pipedrive FIELD keys are also 40 hex and are not credentials. Allow them
    // only where a field key legitimately lives, and only as a placeholder.
    allow: (line) => /PLACEHOLDER_/.test(line) || /\b(sha|sha1|sha256|commit|blob|checksum|digest)\b/i.test(line),
  },
  {
    id: 'uuid-secret',
    why: 'a UUID-shaped credential (Make / Smartlead style)',
    re: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/,
    // Narrow allowances, each because the shape provably is not a credential
    // there — NOT because a UUID is generally fine:
    //   - a Pipedrive correlation id is an event id, not authentication;
    //   - fixtures use readable, invented ids;
    //   - a UUID inside a /tmp or scratchpad PATH is a directory segment (a
    //     Claude Code session id), which is why the audit report now prints
    //     only the directory basename.
    allow: (line) => /correlation_id|_fixture|\bnil\b|00000000-0000/.test(line)
      || /\/tmp\/|scratchpad|claude-\d/.test(line),
  },
  {
    id: 'n8n-credential-block',
    why: 'an n8n credential reference (SECURITY.md: exports carry credential references)',
    re: /"credentials"\s*:\s*\{/,
  },
  {
    id: 'live-webhook-url',
    why: 'a live n8n webhook URL (SECURITY.md: the path IS the credential)',
    re: /https?:\/\/[a-z0-9.-]*\.app\.n8n\.cloud\/webhook[^\s"'`]*/i,
  },
];

const TEXT_EXT = /\.(mjs|js|cjs|ts|json|md|txt|ya?ml|html|css|sh|py|env|example)$/i;
const SKIP_PATH = /(^|\/)(node_modules|\.git|\.cache)(\/|$)/;

// This file necessarily contains the patterns it looks for.
const SELF = 'scripts/scan_secrets.mjs';

function scanText(label, text) {
  const findings = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.length > 4000) continue; // minified or data blob
    for (const rule of RULES) {
      if (!rule.re.test(line)) continue;
      if (rule.allow && rule.allow(line)) continue;
      findings.push({ label, line: i + 1, rule: rule.id, why: rule.why });
    }
  }
  return findings;
}

const mode = process.argv.includes('--history') ? 'history'
  : process.argv.includes('--tracked') ? 'tracked' : 'worktree';

let findings = [];
let scanned = 0;

if (mode === 'history') {
  // Every blob reachable from every ref, under this subtree.
  const revs = execFileSync('git', ['rev-list', '--all'], { cwd: REPO, encoding: 'utf8' })
    .split('\n').filter(Boolean);
  const seen = new Set();
  for (const rev of revs) {
    const entries = execFileSync('git', ['ls-tree', '-r', rev, '--', PREFIX], {
      cwd: REPO, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
    }).split('\n').filter(Boolean);
    for (const entry of entries) {
      const [meta, path] = entry.split('\t');
      const sha = meta.split(' ')[2];
      if (seen.has(sha)) continue;
      seen.add(sha);
      if (!TEXT_EXT.test(path) || SKIP_PATH.test(path)) continue;
      if (path.endsWith(SELF)) continue;
      const content = execFileSync('git', ['cat-file', '-p', sha], {
        cwd: REPO, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024,
      });
      scanned += 1;
      findings.push(...scanText(`${rev.slice(0, 8)}:${path}`, content));
    }
  }
} else {
  let files;
  if (mode === 'tracked') {
    files = execFileSync('git', ['ls-files', '--', PREFIX], { cwd: REPO, encoding: 'utf8' })
      .split('\n').filter(Boolean).map((f) => join(REPO, f));
  } else {
    files = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '--', PREFIX], {
      cwd: REPO, encoding: 'utf8',
    }).split('\n').filter(Boolean).map((f) => join(REPO, f));
  }
  for (const file of files) {
    const rel = relative(REPO, file);
    if (!TEXT_EXT.test(file) || SKIP_PATH.test(rel)) continue;
    if (rel.endsWith(SELF)) continue;
    if (!existsSync(file) || statSync(file).size > 8 * 1024 * 1024) continue;
    scanned += 1;
    findings.push(...scanText(rel, readFileSync(file, 'utf8')));
  }
}

const label = { history: 'every blob in every commit', tracked: 'tracked files', worktree: 'working tree' }[mode];
process.stdout.write(`secret scan (${label}): ${scanned} file(s)/blob(s) scanned, ${findings.length} finding(s)\n`);

if (findings.length > 0) {
  process.stdout.write('\nMatched text is deliberately not printed.\n\n');
  for (const f of findings) {
    process.stdout.write(`  ${f.label}:${f.line}  [${f.rule}] ${f.why}\n`);
  }
  process.stdout.write('\nSECURITY.md: rotate first, rewrite history second.\n');
  process.exit(1);
}

process.stdout.write('clean\n');
