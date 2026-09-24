// tests/static/workflow_review.test.mjs — lint the exported workflow (§9.3).
//
// These assertions run against the JSON that would be imported into n8n, so a
// violation is caught before a workflow exists rather than after it runs.
// n8n/patch/validate.mjs enforces the same rules at build time; this suite is
// the independent read of the artefact, and it also checks things validate()
// does not (positions, graph reachability, the CONFIG payload's provenance).

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

import { validate, CONTINUE_ON_FAIL_ALLOWLIST, MUST_NOT_RETRY } from '../../n8n/patch/validate.mjs';
import { PLACEHOLDER_PATH_A, PLACEHOLDER_PATH_B, USING_PLACEHOLDER_PATHS, stripCredentials } from '../../n8n/patch/patch.mjs';
import { buildConfig, ENV_KEYS, USING_LIVE_REGISTRY } from '../../scripts/gen_config_node.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const WF_PATH = join(ROOT, 'n8n', 'workflows', 'WF-ICP-Score.dev.json');
const NODES_DIR = join(ROOT, 'n8n', 'nodes');

const raw = readFileSync(WF_PATH, 'utf8');
const wf = JSON.parse(raw);
const byName = new Map(wf.nodes.map((n) => [n.name, n]));
const nodeParams = (n) => JSON.stringify(n.parameters || {});

describe('the patcher and the artefact agree', () => {
  test('validate() is clean on the exported workflow', () => {
    const findings = validate(wf, { nodesDir: NODES_DIR });
    assert.deepEqual(findings, [], `validate() findings:\n  ${findings.join('\n  ')}`);
  });

  test('a rebuild is byte-identical (the patcher is deterministic)', () => {
    execFileSync(process.execPath, [join(ROOT, 'n8n', 'patch', 'patch.mjs'), '--check'], { stdio: 'pipe' });
  });

  test('the export uses LF endings and ends with a newline', () => {
    assert.ok(!raw.includes('\r'), 'CRLF would make every diff noise');
    assert.ok(raw.endsWith('\n'));
  });

  test('a real Pipedrive field key never reaches a tracked file', () => {
    // On a machine that has run create_fields, CONFIG.local.json and the
    // workflow export carry real 40-hex keys. Both are gitignored. The
    // committed CONFIG.json must stay placeholders.
    const committed = readFileSync(join(ROOT, 'n8n', 'nodes', 'CONFIG.json'), 'utf8');
    assert.ok(
      !/\b[0-9a-f]{40}\b/.test(committed),
      'the committed CONFIG.json contains a 40-hex field key — it must stay the placeholder template'
    );
    assert.ok(committed.includes('PLACEHOLDER_'), 'and must visibly be a placeholder');

    const registry = readFileSync(join(ROOT, 'config', 'pipedrive_fields.json'), 'utf8');
    assert.ok(
      !/\b[0-9a-f]{40}\b/.test(registry),
      'the committed field registry contains a real key — a live run writes .local.json'
    );
  });

  test('the DEV import payload attaches NO credentials', () => {
    // Imported into a shared instance, the workflow must not be able to reach
    // Pipedrive, Slack or Sheets before a human has attached credentials.
    const payload = JSON.parse(
      readFileSync(join(ROOT, 'n8n', 'workflows', 'import-dev-no-credentials.json'), 'utf8')
    );
    const withCredentials = payload.nodes.filter((n) => n.credentials);
    assert.deepEqual(withCredentials.map((n) => n.name), [], 'no node may carry credentials');
    assert.ok(!JSON.stringify(payload).includes('"credentials"'));
  });

  test('the DEV import payload is tagged DEV in its name and is not active', () => {
    const payload = JSON.parse(
      readFileSync(join(ROOT, 'n8n', 'workflows', 'import-dev-no-credentials.json'), 'utf8')
    );
    assert.match(payload.name, /\[DEV\]$/, 'the name must mark it as DEV in any workflow list');
    assert.ok(!('active' in payload), 'active is not settable on import; arming is a human act');
  });

  test('the import payload is otherwise identical to the canonical export', () => {
    // Same graph, same node parameters, same settings — credentials and the
    // name are the only differences, so reviewing one reviews both.
    const payload = stripCredentials(wf);
    assert.deepEqual(payload.connections, wf.connections);
    assert.deepEqual(payload.settings, wf.settings);
    assert.equal(payload.nodes.length, wf.nodes.length);
    for (let i = 0; i < wf.nodes.length; i += 1) {
      const { credentials, ...expected } = wf.nodes[i];
      assert.deepEqual(payload.nodes[i], expected, wf.nodes[i].name);
    }
  });

  test('the canonical export is NOT tracked by git (it carries credential refs)', () => {
    // SECURITY.md excludes workflow exports. The patcher rebuilds this file
    // byte-identically, and `pretest` runs the patcher, so a fresh clone still
    // has it for the tests.
    let tracked = true;
    try {
      execFileSync('git', ['ls-files', '--error-unmatch', 'n8n/workflows/WF-ICP-Score.dev.json'],
        { cwd: ROOT, stdio: 'pipe' });
    } catch { tracked = false; }
    assert.equal(tracked, false, 'the export must stay out of git; the patcher regenerates it');
  });

  test('api-payload.json carries only the four API-writable keys', () => {
    const payload = JSON.parse(readFileSync(join(ROOT, 'n8n', 'workflows', 'api-payload.json'), 'utf8'));
    assert.deepEqual(Object.keys(payload).sort(), ['connections', 'name', 'nodes', 'settings']);
    assert.ok(!('active' in payload), 'active is not API-writable on create/update');
  });
});

describe('deployment safety', () => {
  test('active === false', () => {
    assert.equal(wf.active, false);
  });

  test('no pinData', () => {
    assert.ok(!('pinData' in wf));
    assert.ok(!raw.includes('pinData'));
  });

  test('settings.errorWorkflow is set, and is env-sourced not hardcoded', () => {
    assert.ok(wf.settings.errorWorkflow, 'terminal errors must reach an alerting error workflow');
    // n8n resolves an ID here, and the ID is instance-specific, so the source
    // must come from the environment. Unset, it is the readable placeholder.
    const source = readFileSync(join(ROOT, 'n8n', 'patch', 'patch.mjs'), 'utf8');
    assert.ok(source.includes('process.env.ICP_ERROR_WORKFLOW_ID'), 'must be env-sourced');
    if (!process.env.ICP_ERROR_WORKFLOW_ID) {
      assert.equal(wf.settings.errorWorkflow, 'WF-ERR');
    }
  });

  test('the committed source holds a PLACEHOLDER webhook path, never a live one', () => {
    // SECURITY.md: "an n8n webhook path is the only authentication those
    // endpoints have ... The path IS the credential." So a real path must
    // never be reachable from git. The patcher takes it from
    // ICP_WEBHOOK_PATH_A/B at build time and defaults to a placeholder.
    const source = readFileSync(join(ROOT, 'n8n', 'patch', 'patch.mjs'), 'utf8');
    assert.ok(
      source.includes("process.env.ICP_WEBHOOK_PATH_A"),
      'the path must come from the environment, not a literal'
    );
    for (const placeholder of [PLACEHOLDER_PATH_A, PLACEHOLDER_PATH_B]) {
      assert.match(placeholder, /^REPLACE-ME-/, 'the default must be obviously not-a-real-path');
    }
  });

  test('a build with no path set produces the placeholder, and says so', () => {
    // This suite runs without ICP_WEBHOOK_PATH_* set, so the export under test
    // must carry the placeholders.
    if (process.env.ICP_WEBHOOK_PATH_A || process.env.ICP_WEBHOOK_PATH_B) return;
    const paths = wf.nodes
      .filter((n) => n.type === 'n8n-nodes-base.webhook')
      .map((n) => n.parameters.path);
    assert.deepEqual(paths, [PLACEHOLDER_PATH_A, PLACEHOLDER_PATH_B]);
    assert.equal(USING_PLACEHOLDER_PATHS, true);
  });

  test('an env-supplied path reaches the built workflow', () => {
    // Build in-process with the variables set, so the mechanism is proven
    // rather than assumed. Restored afterwards.
    const before = [process.env.ICP_WEBHOOK_PATH_A, process.env.ICP_WEBHOOK_PATH_B];
    try {
      process.env.ICP_WEBHOOK_PATH_A = 'unit-test-path-a';
      process.env.ICP_WEBHOOK_PATH_B = 'unit-test-path-b';
      const built = execFileSync(
        process.execPath,
        ['-e', `import('${pathToFileURL(join(ROOT, 'n8n', 'patch', 'patch.mjs')).href}')
          .then((m) => { const w = m.buildWorkflow();
            process.stdout.write(JSON.stringify(w.nodes
              .filter((n) => n.type === 'n8n-nodes-base.webhook')
              .map((n) => n.parameters.path))); });`],
        { encoding: 'utf8', env: process.env }
      );
      assert.deepEqual(JSON.parse(built), ['unit-test-path-a', 'unit-test-path-b']);
    } finally {
      if (before[0] === undefined) delete process.env.ICP_WEBHOOK_PATH_A;
      else process.env.ICP_WEBHOOK_PATH_A = before[0];
      if (before[1] === undefined) delete process.env.ICP_WEBHOOK_PATH_B;
      else process.env.ICP_WEBHOOK_PATH_B = before[1];
    }
  });
});

describe('CONFIG is first, and holds everything', () => {
  test('a CONFIG node exists on each path, immediately after the Respond node', () => {
    assert.deepEqual(
      wf.nodes.filter((n) => /^CONFIG/.test(n.name)).map((n) => n.name).sort(),
      ['CONFIG', 'CONFIG B']
    );
    assert.deepEqual(wf.connections['Respond 200 A'].main[0].map((t) => t.node), ['CONFIG']);
    assert.deepEqual(wf.connections['Respond 200 B'].main[0].map((t) => t.node), ['CONFIG B']);
  });

  test('CONFIG comes before anything that reads it', () => {
    // Walk forward from each webhook; a $('CONFIG') reader must be downstream
    // of its own path's CONFIG node, because $('X') throws otherwise.
    const forward = (start) => {
      const seen = new Set();
      const queue = [start];
      while (queue.length > 0) {
        const name = queue.shift();
        if (seen.has(name)) continue;
        seen.add(name);
        for (const output of (wf.connections[name] || { main: [] }).main) {
          for (const target of output || []) queue.push(target.node);
        }
      }
      return seen;
    };
    const pathA = forward('Webhook Pipedrive');
    const pathB = forward('Webhook Clay');
    for (const node of wf.nodes) {
      if (!nodeParams(node).includes("$('CONFIG')")) continue;
      const onA = pathA.has(node.name);
      const onB = pathB.has(node.name);
      assert.ok(onA || onB, `${node.name} reads CONFIG but is on neither path`);
    }
    assert.ok(pathA.has('CONFIG'));
    assert.ok(pathB.has('CONFIG B'));
  });

  test('both CONFIG nodes carry the same payload', () => {
    assert.equal(byName.get('CONFIG').parameters.jsonOutput, byName.get('CONFIG B').parameters.jsonOutput);
  });

  test('the CONFIG payload is exactly what gen_config_node produces', () => {
    const expression = byName.get('CONFIG').parameters.jsonOutput;
    // ={{ JSON.stringify(Object.assign({}, <STATIC>, (() => { ... })())) }}
    const match = expression.match(/Object\.assign\(\{\}, (\{.*\}), \(\(\) => \{/);
    assert.ok(match, 'cannot find the static payload inside the CONFIG expression');
    assert.deepEqual(
      JSON.parse(match[1]), buildConfig(),
      `${USING_LIVE_REGISTRY ? 'n8n/nodes/CONFIG.local.json' : 'n8n/nodes/CONFIG.json'} ` +
      'is stale — run `npm run gen:config` and rebuild'
    );
  });

  test('the instance-specific values are resolved, never literals', () => {
    const expression = byName.get('CONFIG').parameters.jsonOutput;
    for (const [key, envKey] of Object.entries(ENV_KEYS)) {
      assert.ok(
        expression.includes(`${key}: pick('${envKey}', BAKED.${key})`),
        `${key} must resolve ${envKey} with a baked fallback`
      );
    }
    // $vars first (n8n Cloud), $env second (self-hosted), each guarded so a
    // blocked accessor cannot throw and fail the whole execution.
    assert.ok(expression.includes("typeof $vars !== 'undefined'"), 'must try $vars');
    assert.ok(expression.includes("typeof $env !== 'undefined'"), 'must fall back to $env');
    assert.equal((expression.match(/try \{/g) || []).length, 2, 'both lookups guarded');
    assert.ok(expression.includes('const BAKED ='), 'must carry a build-time fallback');

    // A Clay webhook URL is an unguessable endpoint, i.e. a secret. A build
    // with ICP_CLAY_ENGINE_URL set legitimately bakes it into the GITIGNORED
    // export; a build without it must contain no trace.
    if (!process.env.ICP_CLAY_ENGINE_URL) {
      assert.ok(!/api\.clay\.com|hooks\.clay\.com/.test(raw), 'no literal Clay URL in a placeholder build');
    }
  });

  test('whatever the build bakes in, it never reaches a tracked file', () => {
    // The export is gitignored; this asserts the rule rather than trusting it.
    let tracked = true;
    try {
      execFileSync('git', ['ls-files', '--error-unmatch', 'n8n/workflows/WF-ICP-Score.dev.json'],
        { cwd: ROOT, stdio: 'pipe' });
    } catch { tracked = false; }
    assert.equal(tracked, false);
    const committedConfig = readFileSync(join(ROOT, 'n8n', 'nodes', 'CONFIG.json'), 'utf8');
    assert.ok(!/api\.clay\.com|app\.n8n\.cloud/.test(committedConfig),
      'the committed CONFIG must carry no instance-specific URL');
  });

  test('now_iso is minted once in CONFIG, so one execution agrees on "now"', () => {
    assert.ok(byName.get('CONFIG').parameters.jsonOutput.includes('now_iso: $now.toISO()'));
    // No node may read the clock for itself: a run straddling midnight must
    // not gate on one date and write another.
    // Comments are allowed to NAME the accessor while explaining why the node
    // does not use it — that is the sentence a future reader needs. Only code
    // counts, so comments come out first.
    const codeOnly = (src) => src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .map((line) => line.replace(/^\s*\/\/.*$/, ''))
      .join('\n');

    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
      const src = codeOnly(node.parameters.jsCode);
      assert.ok(!/\$now/.test(src), `${node.name} must read cfg.now_iso, not the clock`);
      assert.ok(
        !/new Date\(\)(?!\.)/.test(src.replace(/new Date\(now\)/g, '')) ||
        node.name.startsWith('Dedupe'),
        `${node.name} must not construct its own clock`
      );
    }
  });
});

describe('no literal ids or secrets outside CONFIG', () => {
  test('no 40-hex Pipedrive field key outside CONFIG', () => {
    for (const node of wf.nodes) {
      if (/^CONFIG/.test(node.name)) continue;
      assert.ok(!/\b[0-9a-f]{40}\b/.test(nodeParams(node)), `${node.name} contains a 40-hex field key`);
    }
  });

  test('no literal Slack channel id outside CONFIG', () => {
    for (const node of wf.nodes) {
      if (/^CONFIG/.test(node.name)) continue;
      const params = nodeParams(node);
      assert.ok(!/['"`]C[A-Z0-9]{8,10}['"`]/.test(params), `${node.name} contains a channel id`);
    }
  });

  test('no literal Pipedrive option id outside CONFIG', () => {
    // Option ids reach a write only through cfg.opt_icp_calculated.
    for (const node of wf.nodes) {
      if (/^CONFIG/.test(node.name)) continue;
      assert.ok(
        !/opt_icp_calculated\s*[:=]\s*\{/.test(nodeParams(node)),
        `${node.name} redefines the option map`
      );
    }
  });

  test('nothing in the export looks like a secret', () => {
    for (const pattern of [/api_token=/, /Bearer\s+[A-Za-z0-9._-]{8,}/, /\bsk-[A-Za-z0-9]{8,}/, /\bxox[baprs]-/]) {
      assert.ok(!pattern.test(raw), `the export matches ${pattern}`);
    }
  });

  test('credentials are referenced by name only', () => {
    const seen = new Set();
    for (const node of wf.nodes) {
      for (const [type, credential] of Object.entries(node.credentials || {})) {
        assert.deepEqual(Object.keys(credential).sort(), ['id', 'name'], `${node.name}/${type}`);
        assert.equal(credential.id, credential.name, 'the placeholder id is the name until n8n assigns one');
        seen.add(credential.name);
      }
    }
    // No clay_webhook_secret and no icp_webhook_basic: both webhooks run on
    // the unguessable path as their only control, so neither carries one.
    // No gsheets_audit: the audit store is an n8n Data Table, which needs no
    // credential at all.
    assert.deepEqual(
      [...seen].sort(),
      ['pipedrive_main', 'slack_ops']
    );
  });
});

describe('retry semantics', () => {
  test('every entity-creating POST has retryOnFail false', () => {
    for (const name of MUST_NOT_RETRY) {
      const node = byName.get(name);
      assert.ok(node, name);
      assert.equal(node.retryOnFail, false, `${name}: a retried create is a duplicate`);
    }
  });

  test('the note POST specifically must never retry', () => {
    assert.equal(byName.get('POST activity').retryOnFail, false);
    assert.equal(byName.get('POST activity').parameters.method, 'POST');
  });

  test('every GET and PATCH has retry configured with a wait', () => {
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest')) {
      const method = node.parameters.method || 'GET';
      if (!['GET', 'PATCH'].includes(method)) continue;
      assert.equal(node.retryOnFail, true, `${node.name} (${method})`);
      assert.ok(node.maxTries >= 2, `${node.name} maxTries`);
      assert.ok(node.waitBetweenTries >= 1000, `${node.name} waitBetweenTries`);
    }
  });

  test('the Clay POST does not retry — a retry is a second row and a second credit', () => {
    assert.equal(byName.get('POST Clay').retryOnFail, false);
  });
});

describe('webhooks carry no half-configured authentication', () => {
  // The owner's ruling is that the unguessable path is the control on Path B,
  // and Path A's Pipedrive subscription carries no basic-auth pair. What this
  // suite guards is the failure mode in between: `authentication` set to a
  // scheme with no credential attached is not a weaker control, it is a dead
  // endpoint — n8n answers every delivery with 500 "No authentication data
  // defined on node!" and the trigger looks registered while firing nothing.
  test('a declared scheme always comes with a credential', () => {
    const webhooks = wf.nodes.filter((n) => n.type === 'n8n-nodes-base.webhook');
    assert.equal(webhooks.length, 2);
    for (const node of webhooks) {
      const scheme = node.parameters.authentication;
      assert.ok(scheme, `${node.name} must state a scheme, even if it is 'none'`);
      if (scheme === 'none') {
        assert.equal(
          Object.keys(node.credentials || {}).length, 0,
          `${node.name} says 'none' but still carries a credential`
        );
      } else {
        assert.ok(
          Object.keys(node.credentials || {}).length > 0,
          `${node.name} declares ${scheme} with no credential — every delivery 500s`
        );
      }
    }
  });
});

describe('Slack alerts', () => {
  test('every Slack node references execution_id and request_id', () => {
    const slack = wf.nodes.filter((n) => n.type === 'n8n-nodes-base.slack');
    assert.ok(slack.length >= 1);
    for (const node of slack) {
      assert.ok(node.parameters.text.includes('$execution.id'), `${node.name} omits execution_id`);
      assert.ok(
        /request_id|_dedupe_key/.test(node.parameters.text),
        `${node.name} omits request_id`
      );
    }
  });

  test('the channel comes from a CONFIG expression, never a literal id', () => {
    // Which CONFIG is the right one is the graph suite's job; here the point is
    // only that no Slack node hard-codes a channel.
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.slack')) {
      assert.match(JSON.stringify(node.parameters.channelId), /\$\(\\?'CONFIG( B)?\\?'\)/, node.name);
    }
  });

  test('every Slack text is an evaluated expression, not literal braces', () => {
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.slack')) {
      assert.ok(node.parameters.text.startsWith('='), `${node.name} would post literal {{ }}`);
    }
  });
});

describe('continueOnFail is allow-listed', () => {
  test('only the alert-before-writes Slack node sets it', () => {
    const offenders = wf.nodes.filter((n) => n.continueOnFail === true).map((n) => n.name);
    assert.deepEqual(offenders, CONTINUE_ON_FAIL_ALLOWLIST);
    assert.deepEqual(CONTINUE_ON_FAIL_ALLOWLIST, ['Slack alert error']);
  });

  test('and it really is posted before anything else on its branch', () => {
    // The alert is first because it is the one thing that must happen. The
    // activity comes after it and is CONDITIONAL: an activity needs an
    // organization to live on, and an event that never carried an org_id has
    // nowhere to put one — Number(null) is 0, which Pipedrive rejects, and
    // when it does not reject the activity lands on no record at all and is
    // invisible. That is what activity 46842 was.
    assert.deepEqual(wf.connections.BuildErrorContext.main[0].map((t) => t.node), ['Slack alert error']);
    assert.deepEqual(
      wf.connections['Slack alert error'].main[0].map((t) => t.node),
      ['IF error has an org?']
    );
    const [hasOrg, noOrg] = wf.connections['IF error has an org?'].main;
    assert.deepEqual(hasOrg.map((t) => t.node), ['POST activity error']);
    assert.deepEqual(noOrg.map((t) => t.node), ['FailLoudly'], 'no org, no activity — but still red');
    // Both branches end red, so the execution reaches WF-ERR either way.
    assert.deepEqual(
      wf.connections['POST activity error'].main[0].map((t) => t.node),
      ['FailLoudly']
    );
  });

  test('the error branch touches the organization not at all', () => {
    // v5 marked the org "Error" here. A field that says Error is a field a rep
    // learns to ignore, and it is indistinguishable from a judgement about the
    // company — so a failed run now leaves the same footprint a successful one
    // does: one activity, no field write.
    const branch = ['BuildErrorContext', 'Slack alert error', 'POST activity error'];
    for (const name of branch) assert.ok(byName.get(name), `${name} must exist`);
    const patchers = wf.nodes.filter((n) => n.parameters && n.parameters.method === 'PATCH');
    assert.deepEqual(
      patchers.map((n) => n.name).sort(),
      ['PATCH organization', 'PATCH organization (no website)'],
      'two PATCH nodes in the whole workflow, neither of them on the error branch'
    );
    // Neither is reachable from the error branch: an error writes nothing.
    for (const name of ['BuildErrorContext', 'Slack alert error', 'POST activity error']) {
      for (const output of (wf.connections[name] || { main: [] }).main) {
        for (const target of output || []) {
          assert.ok(
            !/^PATCH organization/.test(target.node),
            `${name} leads to ${target.node}`
          );
        }
      }
    }
  });
});

describe('Code nodes are the tested sources', () => {
  test('every jsCode is byte-identical to its file in n8n/nodes/', () => {
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
      const base = node.name.replace(/ [AB]$/, '');
      const source = readFileSync(join(NODES_DIR, `${base}.js`), 'utf8');
      assert.equal(
        node.parameters.jsCode, source,
        `${node.name} has drifted from n8n/nodes/${base}.js`
      );
    }
  });

  test('every source file is deployed by at least one Code node', () => {
    const deployed = new Set(
      wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')
        .map((n) => `${n.name.replace(/ [AB]$/, '')}.js`)
    );
    for (const file of readdirSync(NODES_DIR).filter((f) => f.endsWith('.js'))) {
      assert.ok(deployed.has(file), `n8n/nodes/${file} is not deployed anywhere`);
    }
  });

  test('the generated nodes are current', () => {
    const before = ['BuildClayRequest', 'ParseScored']
      .map((n) => readFileSync(join(NODES_DIR, `${n}.js`), 'utf8'));
    execFileSync(process.execPath, [join(ROOT, 'scripts', 'gen_nodes.mjs')], { stdio: 'pipe' });
    const after = ['BuildClayRequest', 'ParseScored']
      .map((n) => readFileSync(join(NODES_DIR, `${n}.js`), 'utf8'));
    assert.deepEqual(after, before, 'run `npm run gen:nodes` and rebuild the workflow');
  });

  test('no Code node reads a raw webhook body except Dedupe and the error path', () => {
    // Dedupe is the translation layer. BuildErrorContext is the exception that
    // had to be made: n8n's task runner does not carry a thrown error's own
    // properties across an error output, so the ids it needs are gone by the
    // time it runs and the only intact copy of the request is the webhook item
    // itself. Execution 60629 posted its failure activity with org_id null
    // because of that, and the activity landed on no organization at all.
    const ALLOWED = ['Dedupe', 'Dedupe B', 'BuildErrorContext'];
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
      const readsWebhook = /\$\('Webhook /.test(node.parameters.jsCode);
      const allowed = ALLOWED.includes(node.name);
      assert.equal(
        readsWebhook, allowed,
        `${node.name}: only ${ALLOWED.join(', ')} may read a webhook node directly`
      );
    }
  });
});

describe('the graph', () => {
  test('no node is orphaned — everything is reachable from a webhook', () => {
    const reachable = new Set();
    const queue = ['Webhook Pipedrive', 'Webhook Clay'];
    while (queue.length > 0) {
      const name = queue.shift();
      if (reachable.has(name)) continue;
      reachable.add(name);
      for (const output of (wf.connections[name] || { main: [] }).main) {
        for (const target of output || []) queue.push(target.node);
      }
    }
    const orphans = wf.nodes.map((n) => n.name).filter((n) => !reachable.has(n));
    assert.deepEqual(orphans, [], `unreachable nodes: ${orphans.join(', ')}`);
  });

  test('every $(\'node\') reference names a node that is upstream of it', () => {
    // n8n resolves `$('X')` only when X is CONNECTED upstream of the node doing
    // the asking — not merely when X ran. Path B's nodes have CONFIG B above
    // them and CONFIG nowhere, so a Path B expression naming CONFIG throws at
    // run time. Worse, in the task runner that error's own constructor throws
    // `Cannot assign to read only property 'name'` while being built, so the
    // trace says nothing about the missing connection. This test is the reason
    // that has to be found once rather than every time.
    //
    // References inside a `try` block are exempt: Dedupe asks for both webhook
    // nodes on purpose and reads the throw as "not this path".
    const ancestors = (target) => {
      const seen = new Set();
      let grew = true;
      while (grew) {
        grew = false;
        for (const [from, conn] of Object.entries(wf.connections)) {
          for (const output of conn.main || []) {
            for (const edge of output || []) {
              if ((edge.node === target || seen.has(edge.node)) && !seen.has(from)) {
                seen.add(from);
                grew = true;
              }
            }
          }
        }
      }
      return seen;
    };

    // Comments talk about `$('Name')` in the abstract; only code counts.
    const stripComments = (src) => src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .map((line) => line.replace(/^\s*\/\/.*$/, ''))
      .join('\n');

    // Remove every `try { ... }` body, brace-matched, so only unguarded
    // references remain.
    const stripTryBlocks = (src) => {
      let out = '';
      let i = 0;
      while (i < src.length) {
        const at = src.indexOf('try {', i);
        if (at === -1) { out += src.slice(i); break; }
        out += src.slice(i, at);
        let depth = 0;
        let j = at + 4;
        for (; j < src.length; j += 1) {
          if (src[j] === '{') depth += 1;
          else if (src[j] === '}') { depth -= 1; if (depth === 0) { j += 1; break; } }
        }
        i = j;
      }
      return out;
    };

    const problems = [];
    for (const node of wf.nodes) {
      const sources = [nodeParams(node)];
      if (node.parameters && typeof node.parameters.jsCode === 'string') {
        sources[0] = JSON.stringify({ ...node.parameters, jsCode: undefined });
        sources.push(stripTryBlocks(stripComments(node.parameters.jsCode)));
      }
      const above = ancestors(node.name);
      for (const src of sources) {
        for (const m of src.matchAll(/\$\(\\?'([^'\\]+)\\?'\)/g)) {
          const referenced = m[1];
          if (referenced === node.name) continue;
          if (!byName.has(referenced)) {
            problems.push(`${node.name} -> $('${referenced}') names no node in the workflow`);
          } else if (!above.has(referenced)) {
            problems.push(`${node.name} -> $('${referenced}') is not upstream of it`);
          }
        }
      }
    }
    assert.deepEqual(problems, [], `unreachable references:\n  ${problems.join('\n  ')}`);
  });

  test('the per-path CONFIG lookup is one block, copied verbatim', () => {
    // Six nodes carry the same fallback because n8n code nodes have no imports.
    // Copies drift; this is what stops them. If a seventh node ever needs it,
    // add the name here rather than retyping the block.
    const WITH_FALLBACK = [
      'Dedupe', 'Dedupe B', 'ParseScored', 'BuildOrgPatch',
      'BuildActivity', 'BuildRunSummary', 'BuildErrorContext',
    ];
    const extract = (src) => {
      const from = src.indexOf('let cfg = null;');
      assert.notEqual(from, -1, 'no fallback block');
      const to = src.indexOf('}', src.indexOf('ICP_NO_CONFIG'));
      return src.slice(from, to + 1);
    };
    const blocks = WITH_FALLBACK.map((name) => {
      const node = byName.get(name);
      assert.ok(node, `${name} is not in the workflow`);
      return [name, extract(node.parameters.jsCode)];
    });
    for (const [name, block] of blocks) {
      assert.equal(block, blocks[0][1], `${name}'s copy has drifted from ${blocks[0][0]}'s`);
    }
  });

  test('the anomaly warn is a non-blocking tee that dead-ends', () => {
    // Dedupe has two connections: the spine and the tee.
    const targets = wf.connections.Dedupe.main[0].map((t) => t.node);
    assert.deepEqual(targets, ['Normalize', 'IF rate exceeded?']);
    // The warn branch must not rejoin the spine.
    assert.deepEqual(wf.connections['IF rate exceeded?'].main[1], []);
    assert.equal(wf.connections['Slack warn rate'], undefined, 'the tee must dead-end');
  });

  test('both Code nodes that can throw route their error output to BuildErrorContext', () => {
    for (const name of ['ParseScored', 'BuildClayRequest']) {
      const node = byName.get(name);
      assert.equal(node.onError, 'continueErrorOutput', `${name} needs an error output`);
      const errorOutput = wf.connections[name].main[1];
      assert.deepEqual(errorOutput.map((t) => t.node), ['BuildErrorContext'], name);
    }
  });

  test('a duplicate Clay callback skips the writes but still reaches the audit row', () => {
    const [allowed, duplicate] = wf.connections['IF write allowed?'].main;
    assert.deepEqual(allowed.map((t) => t.node), ['GET organization B']);
    assert.deepEqual(duplicate.map((t) => t.node), ['BuildRunSummary']);
  });

  test('an empty patch skips the PATCH — and still posts the activity', () => {
    // The PATCH is conditional on something having CHANGED. The activity is
    // conditional on the run having HAPPENED. Skipping both is why a re-score
    // of jovia.org (org 22589, already reading "60 - B") left no trace a rep
    // could see: the branch went straight to the summary and the record showed
    // nothing at all.
    const [nonEmpty, empty] = wf.connections['IF patch non-empty?'].main;
    assert.deepEqual(nonEmpty.map((t) => t.node), ['PATCH organization']);
    assert.deepEqual(empty.map((t) => t.node), ['BuildActivity'],
      'an unchanged score still leaves an activity');
    // Both branches converge, so exactly one path runs and exactly one
    // activity is posted — never two.
    assert.deepEqual(
      wf.connections['PATCH organization'].main[0].map((t) => t.node),
      ['BuildActivity']
    );
  });

  test('no {{ }} expression contains a real newline', () => {
    // n8n parses the braces as JavaScript, so a literal line break inside a
    // string literal there is a syntax error — reported as
    // {"error":"invalid syntax"} and, on a continueOnFail node, swallowed.
    // Outside the braces a real newline is ordinary text.
    for (const node of wf.nodes) {
      const params = nodeParams(node);
      for (const [, span] of params.matchAll(/\{\{([\s\S]*?)\}\}/g)) {
        assert.ok(
          !span.includes('\n'),
          `${node.name}: an expression contains a real newline — write it as \\n`
        );
      }
    }
  });

  test('every Code node before the write gate has an error output', () => {
    // Anything that throws upstream of BuildErrorContext dies with no problem
    // list, no activity, no ledger release, and — because n8n's task runner
    // masks a thrown error — a message nobody can act on. Execution 65816 was
    // Dedupe B doing exactly that.
    for (const name of ['Dedupe B', 'ParseScored']) {
      const node = byName.get(name);
      assert.ok(node, `${name} must exist`);
      assert.equal(node.onError, 'continueErrorOutput', `${name} must route failures, not die`);
      const outputs = (wf.connections[name] || { main: [] }).main;
      assert.equal(outputs.length, 2, `${name} must have both outputs wired`);
      assert.deepEqual(outputs[1].map((t) => t.node), ['BuildErrorContext'],
        `${name}'s error output must reach the loud branch`);
    }
  });

  test('every non-duplicate Path B run reaches exactly one activity', () => {
    // Walk from the write gate and count the POST activity nodes reachable
    // along any single path. Two would be a double post; zero is jovia.
    const walk = (node, seen = new Set()) => {
      if (seen.has(node)) return [];
      seen.add(node);
      if (node === 'POST activity') return [[node]];
      const outs = (wf.connections[node] || { main: [] }).main.flat().map((t) => t.node);
      return outs.flatMap((next) => walk(next, new Set(seen)).map((p) => [node, ...p]));
    };
    const paths = walk('GET organization B');
    assert.ok(paths.length >= 2, 'both the changed and unchanged branches must reach it');
    for (const path of paths) {
      assert.equal(
        path.filter((n) => n === 'POST activity').length, 1,
        `a run down ${path.join(' -> ')} must post exactly one activity`
      );
    }
  });

  test('the run summary is the last thing on Path B, and nothing follows it', () => {
    // It is the end of the line: its output IS the trace, and it lands in the
    // n8n execution. Anything connected after it would be a sink that can go
    // red for a reason unrelated to the score, which is exactly what dropping
    // the Data Table removed.
    assert.equal(wf.connections.BuildRunSummary, undefined, 'nothing may follow the summary');
    const reaches = ['POST activity', 'IF write allowed?', 'IF patch non-empty?']
      .map((n) => (wf.connections[n] || { main: [] }).main.flat().map((t) => t.node));
    assert.ok(reaches.some((targets) => targets.includes('BuildRunSummary')));
  });

  test('an ignored deal goes to an explicit NoOp, not to an error', () => {
    const [scoreable, ignored] = wf.connections['IF deal.create?'].main;
    assert.deepEqual(scoreable.map((t) => t.node), ['GET organization']);
    assert.deepEqual(ignored.map((t) => t.node), ['Skip not scoreable']);
    assert.equal(byName.get('Skip not scoreable').type, 'n8n-nodes-base.noOp');
  });

  test('a fresh score goes to an explicit NoOp', () => {
    const [skip, rescore] = wf.connections['IF fresh score?'].main;
    assert.deepEqual(skip.map((t) => t.node), ['Skip fresh score']);
    assert.deepEqual(rescore.map((t) => t.node), ['BuildClayRequest']);
  });

  test('Path A ends at the Clay POST — scoring is asynchronous', () => {
    assert.equal(wf.connections['POST Clay'], undefined);
  });

  test('the webhook responds before any work, so Pipedrive never waits on Clay', () => {
    assert.deepEqual(wf.connections['Webhook Pipedrive'].main[0].map((t) => t.node), ['Respond 200 A']);
    assert.deepEqual(wf.connections['Webhook Clay'].main[0].map((t) => t.node), ['Respond 200 B']);
    for (const name of ['Respond 200 A', 'Respond 200 B']) {
      assert.equal(byName.get(name).parameters.options.responseCode, 200);
    }
  });

  test('every node has a unique name and a position', () => {
    const names = wf.nodes.map((n) => n.name);
    assert.equal(new Set(names).size, names.length);
    for (const node of wf.nodes) {
      assert.ok(Array.isArray(node.position) && node.position.length === 2, node.name);
    }
  });
});

describe("the human's field is never written", () => {
  test('no node references the Sales Rep key outside the never-write guard', () => {
    for (const node of wf.nodes) {
      if (/^CONFIG/.test(node.name)) continue;
      const params = nodeParams(node);
      if (!params.includes('f_sales_rep_icp_score')) continue;
      assert.ok(params.includes('fields_never_write'),
        `${node.name} names the human's field outside the never-write guard`);
    }
  });

  test('CONFIG declares the unwritable fields, and both patch builders check that list', () => {
    const config = buildConfig();
    // Two entries: the rep's own score, and the custom Website URL field the
    // gate READS as a fallback identifier. Reading a field is not a licence to
    // write it, and the second entry is what says so.
    assert.deepEqual(config.fields_never_write, [config.f_sales_rep_icp_score, config.f_website_url]);
    for (const file of ['BuildOrgPatch.js', 'BuildNoWebsiteWrite.js']) {
      const source = readFileSync(join(NODES_DIR, file), 'utf8');
      assert.ok(source.includes('fields_never_write'), `${file} must check the never-write list`);
      assert.ok(source.includes('ICP_FORBIDDEN_WRITE'), `${file} must fail loudly, not silently omit`);
    }
    const errorSource = readFileSync(join(NODES_DIR, 'BuildErrorContext.js'), 'utf8');
    assert.ok(!errorSource.includes('custom_fields'), 'BuildErrorContext must not build a patch at all');
  });

  test('the Website URL fallback is read and never written', () => {
    const config = buildConfig();
    assert.ok(!config.fields_written.includes(config.f_website_url), 'it must not be writable');
    assert.ok(config.fields_never_write.includes(config.f_website_url), 'and must be named as unwritable');
    const gate = readFileSync(join(NODES_DIR, 'IdempotencyGate.js'), 'utf8');
    assert.match(gate, /custom\[cfg\.f_website_url\]/, 'the gate reads it');
    assert.match(gate, /org\.website/, 'and reads the standard field first');
    // Nothing else may touch it at all.
    for (const file of readdirSync(NODES_DIR).filter((f) => f.endsWith('.js'))) {
      if (file === 'IdempotencyGate.js') continue;
      const source = readFileSync(join(NODES_DIR, file), 'utf8');
      assert.ok(
        !source.includes('f_website_url') || source.includes('fields_never_write'),
        `${file} names the fallback field outside the never-write guard`
      );
    }
  });

  test('the five v5 fields are gone from the build entirely', () => {
    // Deleted from the Pipedrive account on 2026-09-17.
    const config = buildConfig();
    const fieldKeys = Object.keys(config).filter((k) => k.startsWith('f_')).sort();
    assert.deepEqual(fieldKeys, [
      'f_auto_icp_score', 'f_auto_icp_scored_at', 'f_sales_rep_icp_score', 'f_website_url',
    ]);
    for (const legacy of ['f_icp_calculated', 'f_icp_score', 'f_icp_scored_at', 'f_icp_model_version', 'f_icp_final']) {
      assert.equal(config[legacy], undefined, `${legacy} must be gone from CONFIG`);
      assert.ok(!JSON.stringify(wf).includes(legacy), `${legacy} must be gone from the workflow`);
    }
  });

  test('the NOTE_WATCHDOG marker for NEEDS_DECISION #2 is where the runbook says', () => {
    const source = readFileSync(join(NODES_DIR, 'BuildOrgPatch.js'), 'utf8');
    assert.ok(source.includes('NOTE_WATCHDOG'), 'the marker must be in BuildOrgPatch.js');
    assert.match(source, /NEEDS_DECISION #2/);
    assert.match(source, /change\.organization/, 'and must name the webhook that would attach');
  });
});

describe('one run = at most one field write + exactly one activity (the v6 contract)', () => {
  // The four statements the contract makes, as four tests. Each is a thing
  // someone could break by adding a node, and none of them is checkable by
  // reading a single file — they are properties of the whole graph.

  const reachableFrom = (root) => {
    const seen = new Set();
    const queue = [root];
    while (queue.length > 0) {
      const name = queue.shift();
      if (seen.has(name)) continue;
      seen.add(name);
      for (const output of (wf.connections[name] || { main: [] }).main) {
        for (const target of output || []) queue.push(target.node);
      }
    }
    return seen;
  };
  const pathANodes = () => reachableFrom('Webhook Pipedrive');
  const pathBNodes = () => [...reachableFrom('Webhook Clay')].map((n) => byName.get(n)).filter(Boolean);

  test('two nodes write to an organization, one per path, both PATCHing custom_fields', () => {
    // Path B writes a grade. Path A writes "n/a - no website" for an
    // organization it could not send to the table at all. They are on
    // different webhooks, so one RUN still reaches at most one of them.
    const writers = wf.nodes.filter((n) => {
      const p = n.parameters || {};
      return typeof p.url === 'string' && /organizations/.test(p.url) && p.method && p.method !== 'GET';
    });
    assert.deepEqual(
      writers.map((n) => n.name).sort(),
      ['PATCH organization', 'PATCH organization (no website)']
    );
    for (const node of writers) {
      assert.equal(node.parameters.method, 'PATCH', node.name);
      assert.match(node.parameters.jsonBody, /\$json\.patch/,
        `${node.name} must write the patch a Code node built, never one it composes itself`);
    }

    const a = pathANodes();
    const b = new Set(pathBNodes().map((n) => n.name));
    assert.ok(a.has('PATCH organization (no website)') && !a.has('PATCH organization'));
    assert.ok(b.has('PATCH organization') && !b.has('PATCH organization (no website)'));
  });

  test('both writers assert the same allow-list before they hand over a patch', () => {
    // A second writer is exactly where a write contract quietly stops holding,
    // so the invariants are asserted in BOTH builders rather than in the one
    // that was written first.
    for (const file of ['BuildOrgPatch.js', 'BuildNoWebsiteWrite.js']) {
      const source = readFileSync(join(NODES_DIR, file), 'utf8');
      assert.match(source, /ICP_UNEXPECTED_WRITE/, `${file} must refuse an unlisted key`);
      assert.match(source, /ICP_PARTIAL_WRITE/, `${file} must refuse half the pair`);
      assert.match(source, /ICP_FORBIDDEN_WRITE/, `${file} must refuse the human's field`);
      assert.match(source, /cfg\.fields_written/, `${file} must allow-list, not deny-list`);
    }
  });

  test('the only fields that patch can contain are the two CONFIG names', () => {
    // Asserted at the source, because the node builds the body and the HTTP
    // node just forwards it.
    const source = readFileSync(join(NODES_DIR, 'BuildOrgPatch.js'), 'utf8');
    assert.match(source, /ICP_UNEXPECTED_WRITE/, 'the node must refuse an unlisted key');
    assert.match(source, /ICP_PARTIAL_WRITE/, 'and refuse to write one of the pair without the other');
    assert.match(source, /cfg\.fields_written/, 'by allow-list, not by deny-list');
    const config = buildConfig();
    assert.deepEqual(config.fields_written, [config.f_auto_icp_score, config.f_auto_icp_scored_at]);
  });

  test('Sales Rep ICP Score is in the never-write list and referenced nowhere else', () => {
    const config = buildConfig();
    assert.ok(config.fields_never_write.includes(config.f_sales_rep_icp_score));
    for (const node of wf.nodes) {
      if (/^CONFIG/.test(node.name)) continue;
      const params = nodeParams(node);
      if (!params.includes('f_sales_rep_icp_score')) continue;
      assert.ok(
        params.includes('fields_never_write'),
        `${node.name} names the human's field outside the never-write guard`
      );
    }
  });

  test('exactly one activity per run on each branch, and none anywhere else', () => {
    const activityNodes = wf.nodes.filter((n) => {
      const p = n.parameters || {};
      return typeof p.url === 'string' && /\/activities/.test(p.url);
    });
    assert.deepEqual(
      activityNodes.map((n) => n.name).sort(),
      ['POST activity', 'POST activity (no website)', 'POST activity error']
    );
    for (const node of activityNodes) {
      assert.match(node.parameters.jsonBody, /done: true/, `${node.name} must not leave an open task`);
      assert.equal(node.retryOnFail, false, `${node.name} must not retry — a retry is a second activity`);
      // Linked to the DEAL as well as the organization when the run had one.
      // Without it, Pipedrive shows nothing on the deal a rep just created —
      // the activity exists, on the organization, where they are not looking.
      // One activity, two records; it does not make two activities.
      assert.match(node.parameters.jsonBody, /deal_id: Number\(/,
        `${node.name} must link the activity to the deal when there is one`);
      assert.match(node.parameters.jsonBody, /\? \{ deal_id[^}]*\} : \{\}/,
        `${node.name} must OMIT deal_id rather than send null`);
      // n8n ends an ={{ }} expression at the FIRST "}}". A nested object
      // literal closing next to the terminator silently truncates the whole
      // expression, which is how CONFIG lost 2749 characters once already.
      const body = node.parameters.jsonBody;
      assert.equal(body.indexOf('}}'), body.length - 2,
        `${node.name}: an earlier "}}" would truncate the expression`);
    }

    // Three activity nodes, three mutually exclusive branches.
    const happy = pathBNodes().map((n) => n.name);
    assert.ok(happy.includes('POST activity'));
    assert.ok(happy.includes('POST activity error'));
    assert.ok(!happy.includes('POST activity (no website)'));
    assert.ok(pathANodes().has('POST activity (no website)'));
    assert.deepEqual(
      wf.connections['IF write allowed?'].main[0].map((t) => t.node), ['GET organization B'],
      'the happy branch leads to the write'
    );

    // The no-website branch converges: the PATCH runs or it does not, and
    // either way exactly one activity is posted.
    const skipIf = wf.connections['IF no-website write needed?'].main;
    assert.deepEqual(skipIf[0].map((t) => t.node), ['PATCH organization (no website)']);
    assert.deepEqual(skipIf[1].map((t) => t.node), ['POST activity (no website)']);
    assert.deepEqual(
      wf.connections['PATCH organization (no website)'].main[0].map((t) => t.node),
      ['POST activity (no website)']
    );
  });

  test('an organization with no website is never POSTed to Clay', () => {
    // The whole point of the ruling: no domain, no request, no credit, and no
    // grade derived from a company we guessed at.
    const gate = wf.connections['IF has website?'].main;
    assert.deepEqual(gate[0].map((t) => t.node), ['POST Clay'], 'true -> the table');
    assert.deepEqual(gate[1].map((t) => t.node), ['BuildNoWebsiteWrite'], 'false -> the skip write');
    assert.equal(
      [...reachableFrom('BuildNoWebsiteWrite')].includes('POST Clay'), false,
      'the skip branch must never rejoin the Clay request'
    );
  });

  test('no note, no label, no owner, no other organization mutation anywhere', () => {
    for (const node of wf.nodes) {
      const p = node.parameters || {};
      if (typeof p.url !== 'string') continue;
      const method = p.method || 'GET';
      if (method === 'GET') continue;
      // Everything that writes must be one of these four, by name.
      assert.ok(
        [
          'PATCH organization', 'PATCH organization (no website)',
          'POST activity', 'POST activity (no website)', 'POST activity error',
          'POST Clay',
        ].includes(node.name),
        `${node.name} writes ${method} ${p.url} — not in the v6 contract`
      );
    }
    assert.equal(JSON.stringify(wf).includes('/notes'), false, 'the notes endpoint is gone');
    assert.equal(JSON.stringify(wf).includes('label_ids'), false, 'nothing touches labels');
  });

  test('no node reaches the icp_audit Data Table any more', () => {
    assert.ok(!JSON.stringify(wf).includes('dataTable'), 'no Data Table node');
    assert.ok(!JSON.stringify(wf).includes('icp_audit'), 'no reference to the table');
    assert.equal(buildConfig().audit_data_table, undefined, 'and nothing in CONFIG names one');
  });
});
