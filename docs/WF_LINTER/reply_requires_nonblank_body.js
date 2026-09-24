/**
 * LINTER RULE — reply_requires_nonblank_body
 *
 * WHY THIS RULE EXISTS
 * On 2026-09-11 HeyReach delivered `connection_request_accepted` and `message_reply_received` in
 * the same millisecond for Person-8768306e. The reply carried one correspondent entry with
 * `message: ""`, created 1.5 s after our own connection message. WF-1 alerted #lead-processing,
 * wrote a PERMANENT reply_dnc registry row, set `3. Responded` and opened a handover task — for a
 * man who had said nothing. The workflow already knew: `M7 Build.render()` had been returning
 * '[empty message]' all along and writing it into the CRM note. Nothing gated on it.
 *
 * THE RULE
 * From every reply-event branch, no consequence — Slack post, dataTable write, CRM POST/PATCH,
 * sub-workflow call — may be reachable without passing a blank-body gate first.
 *
 * HOW A GATE IS RECOGNISED (either is enough)
 *   - the marker `BLANK_BODY_GATE_V1` anywhere in the node's parameters   (WF-2 `Blank Body Gate`)
 *   - a node name matching /blank[ _-]*(reply|body)[ _-]*gate/i           (WF-1 `M7 Blank Reply Gate`)
 * Only the gate's TRUE output (index 0) continues as gated. A consequence wired to the FALSE
 * output is a finding, not a pass — that is the shape a careless "fix" would take.
 *
 * SCOPE AND LIMITS (stated, not hidden)
 *   - A reply branch is an output of a Switch/IF whose rightValue matches a known reply-event
 *     name. A workflow that routes replies some other way is NOT checked, and is reported as
 *     `unchecked` rather than silently passed.
 *   - It checks REACHABILITY, not whether the gate's predicate is correct. A gate that always
 *     returns true passes this rule. Correctness of the predicate is the statics' job.
 *   - Reconcilers that replay a reply by POSTing to a receiver's webhook are not consequences here;
 *     the receiver they call is checked on its own.
 *
 * USAGE
 *   node reply_requires_nonblank_body.js <workflows.json>   // array of full workflow objects
 *   node reply_requires_nonblank_body.js --self-test
 *
 * Exit 0 = PASS, 1 = FAIL, 2 = bad usage.
 */

'use strict';
const { stripJsComments, codeStrippedParams } = require('./lint_rules.js');

const REPLY_EVENTS = [
  'every_message_reply_received',
  'message_reply_received',
  'replied',
  'email_reply',
];

const MUT_OPS = ['insert', 'update', 'upsert', 'deleterows', 'delete'];

function isConsequence(node) {
  const t = String(node.type || '');
  const p = node.parameters || {};
  if (t.endsWith('slack')) return 'slack post';
  if (t.endsWith('dataTable')) {
    return MUT_OPS.includes(String(p.operation || '').toLowerCase())
      ? 'dataTable ' + p.operation : null;
  }
  if (t.endsWith('httpRequest')) {
    const m = String(p.method || 'GET').toUpperCase();
    return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(m) ? 'HTTP ' + m : null;
  }
  if (t.includes('executeWorkflow')) return 'sub-workflow call';
  if (t.endsWith('pipedrive')) return 'pipedrive node';
  return null;
}

function isGate(node) {
  const blob = JSON.stringify(codeStrippedParams(node.parameters));
  if (blob.indexOf('BLANK_BODY_GATE_V1') !== -1) return true;
  return /blank[ _-]*(reply|body)[ _-]*gate/i.test(String(node.name || ''));
}

function replyBranches(wf) {
  // [{node, output}] — every branch of a router that selects a reply event
  const out = [];
  for (const n of wf.nodes || []) {
    const t = String(n.type || '');
    if (!t.endsWith('switch') && !t.endsWith('if')) continue;
    const p = n.parameters || {};
    const rules = ((p.rules || {}).values) || null;
    if (rules) {
      rules.forEach((r, i) => {
        const blob = JSON.stringify(r).toLowerCase();
        if (REPLY_EVENTS.some((e) => blob.indexOf('"' + e + '"') !== -1)) {
          out.push({ node: n.name, output: i });
        }
      });
    } else {
      const blob = JSON.stringify(p).toLowerCase();
      if (REPLY_EVENTS.some((e) => blob.indexOf('"' + e + '"') !== -1)) {
        out.push({ node: n.name, output: 0 });
      }
    }
  }
  return out;
}

function lint(wf) {
  const nodes = {};
  for (const n of wf.nodes || []) nodes[n.name] = n;
  const conns = wf.connections || {};
  const branches = replyBranches(wf);
  if (!branches.length) return { name: wf.name, id: wf.id, unchecked: true, findings: [] };

  const findings = [];
  for (const br of branches) {
    const first = (((conns[br.node] || {}).main || [])[br.output] || [])
      .filter(Boolean).map((l) => l.node);
    // walk, stopping at gates (their TRUE output is gated; their FALSE output keeps walking)
    const seen = new Set();
    const stack = first.map((nm) => ({ nm, gated: false }));
    while (stack.length) {
      const cur = stack.pop();
      const key = cur.nm + '|' + cur.gated;
      if (seen.has(key)) continue;
      seen.add(key);
      const node = nodes[cur.nm];
      if (!node) continue;
      const gate = isGate(node);
      const why = isConsequence(node);
      if (why && !cur.gated) {
        findings.push({ branch: br.node + '[' + br.output + ']', node: cur.nm, why });
      }
      const outs = ((conns[cur.nm] || {}).main) || [];
      outs.forEach((b, bi) => {
        (b || []).filter(Boolean).forEach((l) => {
          // a gate gates only its TRUE output
          const gated = cur.gated || (gate && bi === 0);
          stack.push({ nm: l.node, gated });
        });
      });
    }
  }
  return { name: wf.name, id: wf.id, unchecked: false, findings };
}

// ----------------------------------------------------------------- self-test
function selfTest() {
  const mk = (nodes, connections, name) => ({ name: name || 'wf', id: 'x', nodes, connections });
  const SW = {
    name: 'Switch', type: 'n8n-nodes-base.switch',
    parameters: { rules: { values: [
      { conditions: { conditions: [{ rightValue: 'SENT' }] } },
      { conditions: { conditions: [{ rightValue: 'REPLIED' }] } },
    ] } },
  };
  const SLACK = { name: 'Alert', type: 'n8n-nodes-base.slack', parameters: {} };
  const GATE_MARK = { name: 'Body Check', type: 'n8n-nodes-base.if',
    parameters: { conditions: { conditions: [{ leftValue: '={{ /* BLANK_BODY_GATE_V1 */ true }}' }] } } };
  const GATE_NAME = { name: 'M7 Blank Reply Gate', type: 'n8n-nodes-base.if', parameters: {} };
  const DT = { name: 'Claim', type: 'n8n-nodes-base.dataTable', parameters: { operation: 'upsert' } };
  const GET = { name: 'Lead Get', type: 'n8n-nodes-base.httpRequest', parameters: { method: 'GET' } };
  const SKIP = { name: 'Skipped', type: 'n8n-nodes-base.code', parameters: {} };
  const L = (n) => [{ node: n, type: 'main', index: 0 }];

  const tests = [];
  const t = (label, wf, wantFindings) => tests.push({ label, wf, wantFindings });

  t('ungated reply branch -> FAIL',
    mk([SW, SLACK], { Switch: { main: [[], L('Alert')] } }), 1);
  t('gated by marker -> pass',
    mk([SW, GATE_MARK, SLACK],
      { Switch: { main: [[], L('Body Check')] }, 'Body Check': { main: [L('Alert'), []] } }), 0);
  t('gated by node name -> pass',
    mk([SW, GATE_NAME, SLACK],
      { Switch: { main: [[], L('M7 Blank Reply Gate')] },
        'M7 Blank Reply Gate': { main: [L('Alert'), []] } }), 0);
  t('consequence on the gate FALSE output -> FAIL',
    mk([SW, GATE_MARK, SLACK],
      { Switch: { main: [[], L('Body Check')] }, 'Body Check': { main: [[], L('Alert')] } }), 1);
  t('two consequences behind one gate -> pass',
    mk([SW, GATE_MARK, SLACK, DT],
      { Switch: { main: [[], L('Body Check')] },
        'Body Check': { main: [[{ node: 'Alert', type: 'main', index: 0 },
          { node: 'Claim', type: 'main', index: 0 }], []] } }), 0);
  t('read-only node is not a consequence',
    mk([SW, GET], { Switch: { main: [[], L('Lead Get')] } }), 0);
  t('SENT branch is not checked',
    mk([SW, SLACK], { Switch: { main: [L('Alert'), []] } }), 0);
  t('terminal skip node after the gate is fine',
    mk([SW, GATE_MARK, SKIP], { Switch: { main: [[], L('Body Check')] },
      'Body Check': { main: [[], L('Skipped')] } }), 0);
  t('no reply branch at all -> unchecked, no findings',
    mk([SLACK], {}), 0);
  t('deep chain: consequence three hops past the gate -> pass',
    mk([SW, GATE_MARK, GET, SLACK],
      { Switch: { main: [[], L('Body Check')] }, 'Body Check': { main: [L('Lead Get'), []] },
        'Lead Get': { main: [L('Alert')] } }), 0);
  t('deep chain with NO gate -> FAIL',
    mk([SW, GET, SLACK],
      { Switch: { main: [[], L('Lead Get')] }, 'Lead Get': { main: [L('Alert')] } }), 1);
  // non-vacuity: the marker alone, on a node that is NOT on the path, must not rescue it
  t('non-vacuity: gate present but off the path -> FAIL',
    mk([SW, GATE_MARK, SLACK],
      { Switch: { main: [[], L('Alert')] }, 'Body Check': { main: [[], []] } }), 1);

  let pass = 0, fail = 0;
  for (const tc of tests) {
    const got = lint(tc.wf).findings.length;
    if (got === tc.wantFindings) { pass++; } else {
      fail++;
      console.log('  FAIL ' + tc.label + ' — findings ' + got + ', expected ' + tc.wantFindings);
    }
  }
  console.log('\nself-test: ' + pass + ' passed, ' + fail + ' failed');
  return fail === 0 ? 0 : 1;
}

function main() {
  const arg = process.argv[2];
  if (!arg) {
    console.error('usage: node reply_requires_nonblank_body.js <workflows.json> | --self-test');
    process.exit(2);
  }
  if (arg === '--self-test') process.exit(selfTest());

  const data = JSON.parse(require('fs').readFileSync(arg, 'utf8'));
  const workflows = Array.isArray(data) ? data : (data.data || [data]);
  let live = 0, archived = 0, checked = 0, unchecked = 0;
  for (const wf of workflows) {
    const r = lint(wf);
    if (r.unchecked) { unchecked++; continue; }
    checked++;
    for (const f of r.findings) {
      if (wf.active) live++; else archived++;
      console.log('  ' + (wf.active ? 'ACTIVE' : 'inact ') + '  ' + r.name
        + ' / ' + f.node + '  (' + f.why + ')  reachable from ' + f.branch
        + ' with no blank-body gate');
    }
  }
  console.log('scanned ' + workflows.length + ' workflow(s): '
    + checked + ' with a reply branch, ' + unchecked + ' without (unchecked)');
  console.log('UNGATED on ACTIVE workflows: ' + live
    + '   |   on inactive/archived (informational): ' + archived);
  // The exit code follows ACTIVE workflows only. `ARCHIVE__WF-1-DO NOT USE` is a frozen pre-fix
  // snapshot and would hold this rule red forever; a permanently failing gate gets ignored, which
  // is worse than a narrower one. Archived findings are still printed, never hidden.
  process.exit(live === 0 ? 0 : 1);
}

main();
