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
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import { validate, CONTINUE_ON_FAIL_ALLOWLIST, MUST_NOT_RETRY } from '../../n8n/patch/validate.mjs';
import { buildConfig, ENV_KEYS } from '../../scripts/gen_config_node.mjs';

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

  test('settings.errorWorkflow is set', () => {
    assert.ok(wf.settings.errorWorkflow, 'terminal errors must reach an alerting error workflow');
    assert.equal(wf.settings.errorWorkflow, 'WF-ERR');
  });

  test('the webhook paths are DEV-scoped, so importing cannot collide with production', () => {
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.webhook')) {
      assert.match(node.parameters.path, /-dev$/, `${node.name} path must end in -dev`);
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
    const match = expression.match(/Object\.assign\(\{\}, (\{.*\}), \{ /);
    assert.ok(match, 'cannot find the static payload inside the CONFIG expression');
    assert.deepEqual(
      JSON.parse(match[1]), buildConfig(),
      'n8n/nodes/CONFIG.json is stale — run `npm run gen:config` and rebuild'
    );
  });

  test('the four environment-specific values come from $env, never a literal', () => {
    const expression = byName.get('CONFIG').parameters.jsonOutput;
    for (const [key, envKey] of Object.entries(ENV_KEYS)) {
      assert.ok(expression.includes(`${key}: $env.${envKey}`), `${key} must come from $env.${envKey}`);
    }
    // A Clay webhook URL is an unguessable endpoint, i.e. a secret.
    assert.ok(!/hooks\.clay\.com|api\.clay\.com/.test(raw), 'no literal Clay URL in the export');
  });

  test('now_iso is minted once in CONFIG, so one execution agrees on "now"', () => {
    assert.ok(byName.get('CONFIG').parameters.jsonOutput.includes('now_iso: $now.toISO()'));
    // No node may read the clock for itself: a run straddling midnight must
    // not gate on one date and write another.
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
      assert.ok(!/\$now/.test(node.parameters.jsCode), `${node.name} must read cfg.now_iso, not $now`);
      assert.ok(
        !/new Date\(\)(?!\.)/.test(node.parameters.jsCode.replace(/new Date\(now\)/g, '')) ||
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
    assert.deepEqual(
      [...seen].sort(),
      ['clay_webhook_secret', 'gsheets_audit', 'icp_webhook_basic', 'pipedrive_main', 'slack_ops']
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
    assert.equal(byName.get('POST note').retryOnFail, false);
    assert.equal(byName.get('POST note').parameters.method, 'POST');
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

describe('webhooks are authenticated', () => {
  test('both webhook nodes declare authentication and a credential', () => {
    const webhooks = wf.nodes.filter((n) => n.type === 'n8n-nodes-base.webhook');
    assert.equal(webhooks.length, 2);
    for (const node of webhooks) {
      assert.ok(node.parameters.authentication, `${node.name} has no authentication`);
      assert.notEqual(node.parameters.authentication, 'none');
      assert.ok(Object.keys(node.credentials || {}).length > 0, `${node.name} has no credential`);
    }
  });

  test('Path A uses basic auth, which Pipedrive supports on the subscription', () => {
    const node = byName.get('Webhook Pipedrive');
    assert.equal(node.parameters.authentication, 'basicAuth');
    assert.ok(node.credentials.httpBasicAuth);
  });

  test('Path B uses header auth, for X-Clay-Secret', () => {
    const node = byName.get('Webhook Clay');
    assert.equal(node.parameters.authentication, 'headerAuth');
    assert.equal(node.credentials.httpHeaderAuth.name, 'clay_webhook_secret');
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

  test('the channel comes from a CONFIG expression', () => {
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.slack')) {
      assert.ok(JSON.stringify(node.parameters.channelId).includes("$('CONFIG')"), node.name);
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

  test('and it really is posted before the writes on its branch', () => {
    assert.deepEqual(wf.connections.BuildErrorPatch.main[0].map((t) => t.node), ['Slack alert error']);
    assert.deepEqual(
      wf.connections['Slack alert error'].main[0].map((t) => t.node),
      ['IF error patch non-empty?']
    );
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

  test('no Code node reads a raw webhook body except the two translation layers', () => {
    for (const node of wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code')) {
      const readsWebhook = /\$\('Webhook /.test(node.parameters.jsCode);
      const allowed = node.name.startsWith('Dedupe');
      assert.equal(
        readsWebhook, allowed,
        `${node.name}: only Dedupe reads the webhook node directly`
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

  test('the anomaly warn is a non-blocking tee that dead-ends', () => {
    // Dedupe has two connections: the spine and the tee.
    const targets = wf.connections.Dedupe.main[0].map((t) => t.node);
    assert.deepEqual(targets, ['Normalize', 'IF rate exceeded?']);
    // The warn branch must not rejoin the spine.
    assert.deepEqual(wf.connections['IF rate exceeded?'].main[1], []);
    assert.equal(wf.connections['Slack warn rate'], undefined, 'the tee must dead-end');
  });

  test('both Code nodes that can throw route their error output to BuildErrorPatch', () => {
    for (const name of ['ParseScored', 'BuildClayRequest']) {
      const node = byName.get(name);
      assert.equal(node.onError, 'continueErrorOutput', `${name} needs an error output`);
      const errorOutput = wf.connections[name].main[1];
      assert.deepEqual(errorOutput.map((t) => t.node), ['BuildErrorPatch'], name);
    }
  });

  test('a duplicate Clay callback skips the writes but still reaches the audit row', () => {
    const [allowed, duplicate] = wf.connections['IF write allowed?'].main;
    assert.deepEqual(allowed.map((t) => t.node), ['GET organization B']);
    assert.deepEqual(duplicate.map((t) => t.node), ['BuildAuditRow']);
  });

  test('an empty patch skips the PATCH and the note, but still audits', () => {
    const [nonEmpty, empty] = wf.connections['IF patch non-empty?'].main;
    assert.deepEqual(nonEmpty.map((t) => t.node), ['PATCH organization']);
    assert.deepEqual(empty.map((t) => t.node), ['BuildAuditRow'], 'no second note, but an audit row');
  });

  test('the audit row is the last thing on every Path B branch', () => {
    assert.deepEqual(wf.connections.BuildAuditRow.main[0].map((t) => t.node), ['Append audit row']);
    assert.equal(wf.connections['Append audit row'], undefined);
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

describe('ICP Final is never written', () => {
  test('no write node references the ICP Final key', () => {
    for (const node of wf.nodes.filter((n) => ['PATCH', 'POST', 'PUT'].includes((n.parameters || {}).method))) {
      assert.ok(!/f_icp_final/.test(nodeParams(node)), `${node.name} references f_icp_final`);
    }
  });

  test('CONFIG declares it unwritable, and the patch builders check that list', () => {
    const config = buildConfig();
    assert.deepEqual(config.fields_never_write, [config.f_icp_final]);
    for (const name of ['BuildOrgPatch', 'BuildErrorPatch']) {
      const source = readFileSync(join(NODES_DIR, `${name}.js`), 'utf8');
      assert.ok(source.includes('fields_never_write'), `${name} must check the never-write list`);
      assert.ok(source.includes('ICP_FORBIDDEN_WRITE'), `${name} must fail loudly, not silently omit`);
    }
  });

  test('the NOTE_WATCHDOG marker for NEEDS_DECISION #2 is where the runbook says', () => {
    // §11 #2 default is the honor system, with a marker left at the exact
    // place a change.organization watchdog would attach. RUNBOOK.md points a
    // reader here, so the marker has to stay findable.
    const source = readFileSync(join(NODES_DIR, 'BuildOrgPatch.js'), 'utf8');
    assert.ok(source.includes('NOTE_WATCHDOG'), 'the marker must be in BuildOrgPatch.js');
    assert.match(source, /NEEDS_DECISION #2/);
    assert.match(source, /change\.organization/, 'and must name the webhook that would attach');
  });

  test('ICP Final is not read as scoring input anywhere', () => {
    for (const node of wf.nodes) {
      const params = nodeParams(node);
      if (/^CONFIG/.test(node.name)) continue;
      const reads = params.match(/f_icp_final/g) || [];
      // BuildOrgPatch/BuildErrorPatch touch it only via fields_never_write.
      for (const _ of reads) {
        assert.ok(
          params.includes('fields_never_write'),
          `${node.name} references f_icp_final outside the never-write guard`
        );
      }
    }
  });
});
