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
//   node scripts/scan_secrets.mjs --repo       widen any mode to the whole repo
//                                              (the default is this subtree only,
//                                              and the output always says which)
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
    //   - a Clay `actionPackageId` is a PUBLIC catalog identifier: it is the
    //     same value in every Clay workspace, it is what
    //     `clay workflows actions list` prints, and it authenticates nothing.
    //     Allowed only on a line that names it as such, so a real credential
    //     cannot hide behind the word.
    //   - an n8n correlation id carried as a `request_id` is written
    //     `req-<uuid>`: it is the value Path A minted to tie one scoring run
    //     together, it authenticates nothing, and the live Clay capture in
    //     tests/fixtures/clay/ is only worth keeping if it is kept VERBATIM.
    //     The `req-` prefix is what makes it distinguishable from a bare
    //     credential, so the allowance requires it.
    allow: (line) => /correlation_id|_fixture|\bnil\b|00000000-0000/.test(line)
      || /\/tmp\/|scratchpad|claude-\d/.test(line)
      || /req-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/.test(line)
      || /actionPackageId|packageId|^\s*(cpj|clay|apollo|predictleads|pdl):\s*'/.test(line),
  },
  {
    id: 'foreign-workspace',
    why: 'a reference to a Clay workspace other than Janea Systems (332169)',
    // Only the Janea workspace may be named anywhere in this repository.
    re: new RegExp(['\\b3091', '40\\b|\\bPostindu', 'stria\\b|@postindu', 'stria\\.com'].join(''), 'i'),  // built from fragments: this file may not contain the names it hunts for
    allow: (line) => /\{\{OTHER_WORKSPACE|\{\{REDACTED_EMAIL/.test(line),
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

// --- scope ------------------------------------------------------------------
//
// Every mode defaults to THIS SUBTREE, which is what `npm test` needs and what
// the pathspec below expresses. That default was also a trap: the output said
// "every blob in every commit" while scanning `icp-scoring/` only, so a green
// --history run read as "the repository is clean" when it only ever meant "this
// subtree is clean". Four files outside the subtree carried a marker through 14
// commits the whole time that line was printing green.
//
// --repo drops the pathspec and scans the whole repository. The scope is now
// named in the output either way, so the claim always matches the work.
const repoWide = process.argv.includes('--repo');
const PATHSPEC = repoWide ? [] : ['--', PREFIX];

let findings = [];
let scanned = 0;

if (mode === 'history') {
  // Every blob reachable from every ref, within the chosen scope.
  const revs = execFileSync('git', ['rev-list', '--all'], { cwd: REPO, encoding: 'utf8' })
    .split('\n').filter(Boolean);
  const seen = new Set();
  for (const rev of revs) {
    const entries = execFileSync('git', ['ls-tree', '-r', rev, ...PATHSPEC], {
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
    files = execFileSync('git', ['ls-files', ...PATHSPEC], { cwd: REPO, encoding: 'utf8' })
      .split('\n').filter(Boolean).map((f) => join(REPO, f));
  } else {
    files = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', ...PATHSPEC], {
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
const scope = repoWide ? 'whole repository' : `${PREFIX} only`;
process.stdout.write(
  `secret scan (${label}, ${scope}): ${scanned} file(s)/blob(s) scanned, ${findings.length} finding(s)\n`,
);

if (findings.length > 0) {
  process.stdout.write('\nMatched text is deliberately not printed.\n\n');
  for (const f of findings) {
    process.stdout.write(`  ${f.label}:${f.line}  [${f.rule}] ${f.why}\n`);
  }
  process.stdout.write('\nSECURITY.md: rotate first, rewrite history second.\n');
  process.exit(1);
}

process.stdout.write('clean\n');
