/**
 * LINTER RULE — prev_read_matches_direct_ancestor
 *
 * WHY THIS RULE EXISTS
 * Nik, 2026-09-15: "this is the third time." The established pattern across these long linear
 * digest/sweep-style workflows is: every Code node does `const prev = $('<node>').first().json;`
 * then returns `{ ...prev, ...newFields }`, chaining an accumulator object forward through nodes
 * whose type would otherwise destroy `$json` (httpRequest / dataTable / webhook — this codebase's
 * own comments call this out explicitly: "the HTTP node between them destroys $json"). `<node>`
 * MUST be the nearest real ancestor capable of carrying that accumulator — i.e. walking BACKWARD
 * through the wire graph and skipping over $json-destroying node types lands exactly on `<node>`.
 *
 * Three confirmed incidents of this exact class:
 *  1. 2026-09-03 — the I-04 simplification deleted `I04 Status`; `No Match Count` still referenced
 *     it. A DANGLING reference (node no longer exists) — caught by node_reference_resolves.js,
 *     which explicitly scoped this ordering/staleness class OUT: "It does NOT check that the
 *     referenced node RAN before the referring one... belongs to its own rule."
 *  2. The WF-1 "named reference needs an ancestor, not a sibling" incident (memory:
 *     n8n-named-reference-needs-ancestor-not-sibling) — a $() reference to a node that exists but
 *     is a parallel sibling, never actually upstream in execution order.
 *  3. 2026-09-15 — `dnc_morning_digest`'s `Gate Health` still read `$('DNC Removed Agg')` after the
 *     Supabase-mirror patch spliced three new nodes between them. The reference RESOLVED (the node
 *     still exists — this is NOT case 1) and IS a true ancestor (not case 2) — it's just no longer
 *     the DIRECT one, so every field the new nodes added was silently dropped one hop later. This
 *     is the specific, narrower gap neither existing rule covers: a resolvable, genuine-ancestor
 *     reference that has gone STALE because something was inserted into the chain after it.
 *
 * WHAT THIS RULE CHECKS
 * For every node whose code contains `prev = $('X')` (or `$("X")`), walk backward through the
 * connection graph from that node's own direct predecessor, skipping over any node whose type is
 * httpRequest / dataTable / webhook (this project's documented $json-destroying types), until
 * landing on the first Code or Set node. That node's name must equal X.
 *
 * SCOPE AND LIMITS (stated, not hidden)
 *  - Only the specific `prev = $('X')` assignment shape is checked — deliberately narrow, so a
 *    node using $('CONFIG') or $('Some Node') for an unrelated lookup (not the accumulator-carry
 *    pattern) is never flagged. This rule is NOT a general "every $() must be the direct ancestor"
 *    check; node_reference_resolves.js already covers "does it resolve at all," and going further
 *    would flag legitimate config/lookup references that were never meant to track chain position.
 *  - A node fed by more than one DISTINCT source node at any point during the backward walk is
 *    reported as `ambiguous` (informational), not silently passed and not failed on a guess — same
 *    discipline node_reference_resolves.js uses for `dynamic` references it cannot resolve
 *    statically. Two wires from the SAME source node (e.g. its success output AND its
 *    continueErrorOutput error output, both targeting the same downstream node) count as ONE
 *    source, matching this project's own established safe case (memory:
 *    n8n-multi-input-node-fires-per-branch) — a node's own two branches are mutually exclusive per
 *    execution, so the walk can still resolve through it.
 *  - Sticky notes are skipped (documentation, not executing nodes).
 *  - Does not itself re-derive whether skipping httpRequest/dataTable/webhook is semantically safe
 *    for a given node's OWN logic — it only checks that the reference matches what the chain
 *    ACTUALLY looks like now, which is exactly the drift class all three incidents share.
 *
 * USAGE
 *   node prev_read_matches_direct_ancestor.js <workflows.json>     // array of full workflow objects
 *   node prev_read_matches_direct_ancestor.js --self-test
 *
 * Exit 0 = PASS (no stale prev-reads), 1 = FAIL, 2 = bad usage.
 */

'use strict';
const { stripJsComments, codeStrippedParams } = require('./lint_rules.js');

const PREV_ASSIGN_RX = /\bprev\s*=\s*\$\(\s*\\?['"]([^'"\\]+)\\?['"]\s*\)/;
const SKIP_TYPES = new Set(['httpRequest', 'dataTable', 'webhook']);
const NON_EXECUTING_TYPES = new Set(['stickyNote']);

function shortType(n) {
  return String(n.type || '').split('.').pop();
}

// Returns { name, ambiguous } — the effective backward-walk landing node for `nodeName`, skipping
// SKIP_TYPES, or ambiguous:true the moment more than one incoming wire is met at any hop.
function walkBackToAncestor(nodeName, byName, incomingOf) {
  let cur = nodeName;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const preds = incomingOf.get(cur) || [];
    if (preds.length !== 1) return { name: null, ambiguous: true };
    const pred = preds[0];
    const predNode = byName.get(pred);
    if (!predNode) return { name: null, ambiguous: true }; // dangling wire target -- not this rule's job
    const t = shortType(predNode);
    if (SKIP_TYPES.has(t)) {
      cur = pred;
      continue;
    }
    return { name: pred, ambiguous: false };
  }
}

function lintWorkflow(wf) {
  const nodes = wf.nodes || [];
  const byName = new Map(nodes.map((n) => [n.name, n]));

  // reverse-adjacency: node name -> array of direct predecessor node names (main output only,
  // any branch index -- a node fed by two DISTINCT sources on purpose is exactly the "ambiguous"
  // case this rule declines to guess through).
  const incomingOf = new Map();
  for (const [src, conn] of Object.entries(wf.connections || {})) {
    for (const branch of conn.main || []) {
      for (const c of branch || []) {
        if (!incomingOf.has(c.node)) incomingOf.set(c.node, new Set());
        incomingOf.get(c.node).add(src); // Set: two branches of the SAME source count once
      }
    }
  }
  for (const [k, v] of incomingOf) incomingOf.set(k, Array.from(v));

  const findings = [];
  const ambiguous = [];
  for (const n of nodes) {
    const ntype = shortType(n);
    if (NON_EXECUTING_TYPES.has(ntype)) continue;
    const blob = JSON.stringify(codeStrippedParams(n.parameters));
    const m = PREV_ASSIGN_RX.exec(blob);
    if (!m) continue;
    const referenced = m[1];

    const result = walkBackToAncestor(n.name, byName, incomingOf);
    if (result.ambiguous) {
      ambiguous.push({ workflow: wf.name, node: n.name, referenced });
      continue;
    }
    if (result.name !== referenced) {
      findings.push({
        workflow: wf.name,
        workflowId: wf.id,
        active: wf.active === true,
        node: n.name,
        referenced,
        actualDirectAncestor: result.name,
      });
    }
  }
  return { findings, ambiguous };
}

function lintAll(workflows) {
  const all = { findings: [], ambiguous: [], scanned: workflows.length };
  for (const wf of workflows) {
    const r = lintWorkflow(wf);
    all.findings.push(...r.findings);
    all.ambiguous.push(...r.ambiguous);
  }
  return all;
}

// --------------------------------------------------------------------------- self-test
function selfTest() {
  let pass = 0;
  let fail = 0;
  const check = (label, got, want) => {
    if (JSON.stringify(got) === JSON.stringify(want)) {
      pass += 1;
    } else {
      fail += 1;
      console.log('  FAIL ' + label + '\n    got  ' + JSON.stringify(got) +
        '\n    want ' + JSON.stringify(want));
    }
  };

  // 1. the real regression: Gate Health reads DNC Removed Agg, but Supabase Mirror Agg now sits
  // directly between Gate Monitor Last (an httpRequest, skipped) and Gate Health.
  const digestBefore = {
    id: 'wf1', name: 'digest', active: true,
    nodes: [
      { name: 'DNC Removed Agg', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'Supabase Mirror Check', type: 'n8n-nodes-base.httpRequest', parameters: {} },
      { name: 'Supabase Meta Check', type: 'n8n-nodes-base.httpRequest', parameters: {} },
      { name: 'Supabase Mirror Agg', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'Gate Monitor Last', type: 'n8n-nodes-base.httpRequest', parameters: {} },
      { name: 'Gate Health', type: 'n8n-nodes-base.code',
        parameters: { jsCode: "const prev = $('DNC Removed Agg').first().json;" } },
    ],
    connections: {
      'DNC Removed Agg': { main: [[{ node: 'Supabase Mirror Check' }]] },
      'Supabase Mirror Check': { main: [[{ node: 'Supabase Meta Check' }]] },
      'Supabase Meta Check': { main: [[{ node: 'Supabase Mirror Agg' }]] },
      'Supabase Mirror Agg': { main: [[{ node: 'Gate Monitor Last' }]] },
      'Gate Monitor Last': { main: [[{ node: 'Gate Health' }]] },
    },
  };
  check('Gate Health regression caught', lintWorkflow(digestBefore).findings.map((f) => f.referenced),
    ['DNC Removed Agg']);
  check('Gate Health finding names the real ancestor',
    lintWorkflow(digestBefore).findings.map((f) => f.actualDirectAncestor), ['Supabase Mirror Agg']);

  // 2. the FIXED version must pass clean
  const digestFixed = JSON.parse(JSON.stringify(digestBefore));
  digestFixed.nodes.find((n) => n.name === 'Gate Health').parameters.jsCode =
    "const prev = $('Supabase Mirror Agg').first().json;";
  check('fixed version passes clean', lintWorkflow(digestFixed).findings, []);

  // 3. the legitimate skip-one-HTTP-node case (No Match Count -> Changelog Count) must pass
  const skipCase = {
    id: 'wf3', name: 'skip', active: true,
    nodes: [
      { name: 'Changelog Count', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'Ops Channel History', type: 'n8n-nodes-base.httpRequest', parameters: {} },
      { name: 'No Match Count', type: 'n8n-nodes-base.code',
        parameters: { jsCode: "const prev = $('Changelog Count').first().json;" } },
    ],
    connections: {
      'Changelog Count': { main: [[{ node: 'Ops Channel History' }]] },
      'Ops Channel History': { main: [[{ node: 'No Match Count' }]] },
    },
  };
  check('legitimate HTTP-skip case passes', lintWorkflow(skipCase).findings, []);

  // 4. a node fed by two distinct incoming wires is reported ambiguous, never guessed through
  const ambig = {
    id: 'wf4', name: 'ambig', active: true,
    nodes: [
      { name: 'A', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'B', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'C', type: 'n8n-nodes-base.code',
        parameters: { jsCode: "const prev = $('A').first().json;" } },
    ],
    connections: {
      A: { main: [[{ node: 'C' }]] },
      B: { main: [[{ node: 'C' }]] },
    },
  };
  const ar = lintWorkflow(ambig);
  check('two-incoming-wire node reported ambiguous, not failed', [ar.findings.length, ar.ambiguous.length],
    [0, 1]);

  // 4b. two wires from the SAME source (success + continueErrorOutput) must NOT count as ambiguous
  // -- the real live case: Supabase Meta Check feeds Supabase Mirror Agg on both its outputs.
  const sameSourceTwice = {
    id: 'wf4b', name: 'samesrc', active: true,
    nodes: [
      { name: 'Supabase Meta Check', type: 'n8n-nodes-base.httpRequest', parameters: {} },
      { name: 'Supabase Mirror Agg', type: 'n8n-nodes-base.code',
        parameters: { jsCode: "const prev = $('Supabase Meta Check').first().json;" } },
    ],
    connections: {
      'Supabase Meta Check': { main: [[{ node: 'Supabase Mirror Agg' }], [{ node: 'Supabase Mirror Agg' }]] },
    },
  };
  // Supabase Meta Check is itself an httpRequest, so the walk skips it and needs a real predecessor
  // to land on -- give it one, matching the live shape, and expect a clean pass (not ambiguous).
  sameSourceTwice.nodes.unshift({ name: 'Supabase Mirror Check', type: 'n8n-nodes-base.code', parameters: {} });
  sameSourceTwice.connections['Supabase Mirror Check'] = { main: [[{ node: 'Supabase Meta Check' }]] };
  sameSourceTwice.nodes.find((n) => n.name === 'Supabase Mirror Agg').parameters.jsCode =
    "const prev = $('Supabase Mirror Check').first().json;";
  const ssr = lintWorkflow(sameSourceTwice);
  check('two branches of the same source do not count as ambiguous', [ssr.findings.length, ssr.ambiguous.length],
    [0, 0]);

  // 5. a node with no prev=$() pattern at all is silently ignored (not this rule's job)
  const noPrev = {
    id: 'wf5', name: 'noprev', active: true,
    nodes: [{ name: 'A', type: 'n8n-nodes-base.code',
      parameters: { jsCode: "const cfg = $('CONFIG').first().json;" } }],
    connections: {},
  };
  check('non-prev $() reference ignored', lintWorkflow(noPrev).findings, []);

  // 6. NON-VACUOUS
  check('rule is non-vacuous', lintWorkflow(digestBefore).findings.length > 0, true);

  console.log('\nself-test: ' + pass + ' passed, ' + fail + ' failed');
  return fail === 0;
}

// --------------------------------------------------------------------------- cli
if (require.main === module) {
  const arg = process.argv[2];
  if (arg === '--self-test') {
    process.exit(selfTest() ? 0 : 1);
  }
  if (!arg) {
    console.error('usage: node prev_read_matches_direct_ancestor.js <workflows.json> | --self-test');
    process.exit(2);
  }
  const data = JSON.parse(require('fs').readFileSync(arg, 'utf8'));
  const workflows = Array.isArray(data) ? data : (data.data || [data]);
  const res = lintAll(workflows);
  console.log('scanned ' + res.scanned + ' workflow(s)');
  console.log('STALE prev-reads: ' + res.findings.length);
  for (const f of res.findings) {
    console.log('  ' + (f.active ? 'ACTIVE  ' : 'inactive') + ' ' + f.workflow + ' / ' + f.node +
      "  ->  reads $('" + f.referenced + "') but the direct ancestor is now $('" + f.actualDirectAncestor + "')");
  }
  console.log('ambiguous (multi-source node, not checked): ' + res.ambiguous.length);
  for (const a of res.ambiguous) {
    console.log('  ' + a.workflow + ' / ' + a.node + "  reads $('" + a.referenced + "')");
  }
  process.exit(res.findings.length === 0 ? 0 : 1);
}

module.exports = { lintWorkflow, lintAll };
