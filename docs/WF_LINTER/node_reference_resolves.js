/**
 * LINTER RULE — node_reference_resolves
 *
 * WHY THIS RULE EXISTS
 * On 2026-09-03 the I-04 simplification deleted the digest's `I04 Status` node. `No Match Count`
 * still called $('I04 Status'). n8n does not validate node references at save time, so the workflow
 * deployed clean and then threw at 04:00Z every morning for five days:
 *
 *     Cannot assign to read only property 'name' of object 'Error: Referenced node doesn't exist'
 *
 * The break sat UPSTREAM of `Post Digest`, so five digests were lost with no other symptom. This
 * rule is the class check: every static node reference must resolve to a node in the same workflow.
 *
 * TWO THINGS ITS OWN SELF-TEST CAUGHT IN THE FIRST VERSION, both now fixed:
 *  - Node parameters are read as JSON, so a DOUBLE-quoted reference arrives escaped —
 *    $("Name") becomes $(\"Name\"). Matching only single quotes silently passed every
 *    double-quoted reference. The patterns now tolerate the backslash.
 *  - A "literal" containing + or a template is really concatenation, not a name. The linter's own
 *    Lint node ($(' + s + ')) was reported as a missing node. Those are classified dynamic.
 *
 * SCOPE AND LIMITS (stated, not hidden)
 *  - Static references only. A name built at runtime cannot be checked statically; those are
 *    reported as `dynamic` so they stay visible instead of silently passing.
 *  - Sticky notes are skipped: they are documentation, and a stale reference in a comment is not a
 *    defect. Every executing node type is checked, including disabled ones (flagged), because
 *    re-enabling a node would fire the bad reference.
 *  - It does NOT check that the referenced node RAN before the referring one. That is the B12 class
 *    (a __field read after a json-replacing node) and belongs to its own rule.
 *  - KNOWN RESIDUAL BLIND SPOT, measured and pinned by self-test 10: resolution runs first, so a
 *    node whose real name contains a plus (e.g. "Normalize + Prep") resolves correctly. But an
 *    UNRESOLVED reference that also looks like concatenation lands in the informational `dynamic`
 *    bucket instead of failing the run. So a dangling reference to a plus-named node is surfaced,
 *    not enforced. This is deliberate: the alternative — failing on the concatenation shape — made
 *    the linter's own Lint node a false finding and would fire on every plus-named node in the
 *    estate. Read the dynamic list when a plus-named node is deleted.
 *
 * USAGE
 *   node node_reference_resolves.js <workflows.json>     // array of full workflow objects
 *   node node_reference_resolves.js --self-test
 *
 * Exit 0 = PASS (no unresolved references), 1 = FAIL, 2 = bad usage.
 */

'use strict';
const { stripJsComments, codeStrippedParams } = require('./lint_rules.js');

const RX_CALL = /\$\(\s*\\?['"]([^'"\\]+)\\?['"]\s*\)/g;
const RX_NODE = /\$node\s*\[\s*\\?['"]([^'"\\]+)\\?['"]\s*\]/g;
const RX_DYNAMIC = /\$\(\s*(?!\\?['"])[^)]{1,120}\)/g;
// a captured "literal" that is really concatenation or a template is NOT a node name
const NOT_LITERAL = /[+`]|\$\{/;
// documentation-only node types
const NON_EXECUTING_TYPES = new Set(['stickyNote']);

function refsIn(text) {
  const out = { statics: new Set(), dynamic: [] };
  let m;
  // Capture every literal as-is. The concatenation test is NOT applied here: a real node name may
  // legitimately contain a plus ("Normalize + Prep"), and treating it as concatenation would make a
  // dangling reference to such a node invisible. Resolution happens first, in lintWorkflow.
  RX_CALL.lastIndex = 0;
  while ((m = RX_CALL.exec(text)) !== null) out.statics.add(m[1]);
  RX_NODE.lastIndex = 0;
  while ((m = RX_NODE.exec(text)) !== null) out.statics.add(m[1]);
  RX_DYNAMIC.lastIndex = 0;
  while ((m = RX_DYNAMIC.exec(text)) !== null) {
    if (!/^\$\(\s*\)$/.test(m[0])) out.dynamic.push(m[0].slice(0, 60));
  }
  return out;
}

function lintWorkflow(wf) {
  const nodes = wf.nodes || [];
  const names = new Set(nodes.map((n) => n.name));
  const findings = [];
  const dynamic = [];
  for (const n of nodes) {
    const ntype = String(n.type || '').split('.').pop();
    if (NON_EXECUTING_TYPES.has(ntype)) continue;
    const blob = JSON.stringify(codeStrippedParams(n.parameters));
    const r = refsIn(blob);
    for (const ref of r.statics) {
      if (names.has(ref)) continue;                 // resolves — done, whatever it looks like
      if (NOT_LITERAL.test(ref)) {                  // only now: unresolved AND concatenation-shaped
        dynamic.push({ workflow: wf.name, node: n.name, expression: "$('" + ref + "')" });
        continue;
      }
      {
        findings.push({
          workflow: wf.name,
          workflowId: wf.id,
          active: wf.active === true,
          node: n.name,
          nodeType: ntype,
          reference: ref,
          disabled: n.disabled === true,
        });
      }
    }
    for (const d of r.dynamic) {
      dynamic.push({ workflow: wf.name, node: n.name, expression: d });
    }
  }
  return { findings, dynamic };
}

function lintAll(workflows) {
  const all = { findings: [], dynamic: [], scanned: workflows.length };
  for (const wf of workflows) {
    const r = lintWorkflow(wf);
    all.findings.push(...r.findings);
    all.dynamic.push(...r.dynamic);
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

  // 1. the real regression, single-quoted
  const digest = {
    id: 'wf1', name: 'digest', active: true,
    nodes: [
      { name: 'CONFIG', type: 'n8n-nodes-base.set', parameters: {} },
      { name: 'No Match Count', type: 'n8n-nodes-base.code',
        parameters: { jsCode: "const prev = $('I04 Status').first().json;" } },
      { name: 'Post Digest', type: 'n8n-nodes-base.slack', parameters: {} },
    ],
  };
  check('digest regression caught', lintWorkflow(digest).findings.map((f) => f.reference),
    ['I04 Status']);

  // 2. DOUBLE-quoted reference, as it arrives after JSON.stringify — the first version missed this
  const dq = {
    id: 'wf2', name: 'dq', active: true,
    nodes: [{ name: 'A', type: 'n8n-nodes-base.code',
      parameters: { jsCode: 'const p = $("Ghost").first().json;' } }],
  };
  check('double-quoted reference caught', lintWorkflow(dq).findings.map((f) => f.reference),
    ['Ghost']);

  // 3. a resolvable reference must NOT be reported
  const good = {
    id: 'wf3', name: 'ok', active: true,
    nodes: [
      { name: 'Lead Resolve', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'Merge', type: 'n8n-nodes-base.code',
        parameters: { jsCode: "const lr = $('Lead Resolve').item.json;" } },
    ],
  };
  check('valid reference passes', lintWorkflow(good).findings, []);

  // 4. legacy $node["Name"] form
  const legacy = {
    id: 'wf4', name: 'legacy', active: true,
    nodes: [{ name: 'A', type: 'n8n-nodes-base.code',
      parameters: { jsCode: 'return $node["Ghost2"].json;' } }],
  };
  check('legacy $node[] form caught', lintWorkflow(legacy).findings.map((f) => f.reference),
    ['Ghost2']);

  // 5. disabled node still reported, flagged
  const dis = {
    id: 'wf5', name: 'dis', active: true,
    nodes: [{ name: 'A', type: 'n8n-nodes-base.code', disabled: true,
      parameters: { jsCode: "$('Ghost3')" } }],
  };
  check('disabled node still reported',
    lintWorkflow(dis).findings.map((f) => [f.reference, f.disabled]), [['Ghost3', true]]);

  // 6. sticky note is documentation, not a defect
  const sticky = {
    id: 'wf6', name: 'sticky', active: true,
    nodes: [{ name: 'PROGRESS', type: 'n8n-nodes-base.stickyNote',
      parameters: { content: "see $('M5..') for the old shape" } }],
  };
  check('sticky note excluded', lintWorkflow(sticky).findings, []);

  // 7. concatenation is dynamic, not a missing node
  const concat = {
    id: 'wf7', name: 'concat', active: true,
    nodes: [{ name: 'Lint', type: 'n8n-nodes-base.code',
      parameters: { jsCode: "const r = $(' + s + ');" } }],
  };
  const cr = lintWorkflow(concat);
  check('concatenated reference is dynamic', [cr.findings.length, cr.dynamic.length > 0],
    [0, true]);

  // 8. a runtime-built name is surfaced as dynamic, never silently passed
  const dyn = {
    id: 'wf8', name: 'dyn', active: true,
    nodes: [{ name: 'A', type: 'n8n-nodes-base.code',
      parameters: { jsCode: 'return $(nm).json;' } }],
  };
  const dr = lintWorkflow(dyn);
  check('runtime name reported as dynamic', [dr.findings.length, dr.dynamic.length], [0, 1]);

  // 9. NON-VACUOUS: the rule must fail the thing it exists to fail
  check('rule is non-vacuous', lintWorkflow(digest).findings.length > 0, true);

  // 10. a REAL node name containing '+' must resolve (resolution runs before the shape test)
  const plus = {
    id: 'wf10', name: 'plus', active: true,
    nodes: [
      { name: 'Normalize + Prep', type: 'n8n-nodes-base.code', parameters: {} },
      { name: 'Get by LinkedIn', type: 'n8n-nodes-base.dataTable',
        parameters: { q: "$('Normalize + Prep').item.json" } },
    ],
  };
  const pr = lintWorkflow(plus);
  check('plus-named node resolves', [pr.findings.length, pr.dynamic.length], [0, 0]);

  // 10b. PINS THE KNOWN BLIND SPOT: a DANGLING plus-shaped reference is surfaced as dynamic,
  // not enforced as a failure. If this ever changes, that is a deliberate decision, not a drift.
  const plusGone = {
    id: 'wf10b', name: 'plusGone', active: true,
    nodes: [{ name: 'A', type: 'n8n-nodes-base.code',
      parameters: { q: "$('Gone + Missing').item.json" } }],
  };
  const pg = lintWorkflow(plusGone);
  check('dangling plus-shaped ref is informational, not a failure',
    [pg.findings.length, pg.dynamic.length], [0, 1]);

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
    console.error('usage: node node_reference_resolves.js <workflows.json> | --self-test');
    process.exit(2);
  }
  const data = JSON.parse(require('fs').readFileSync(arg, 'utf8'));
  const workflows = Array.isArray(data) ? data : (data.data || [data]);
  const res = lintAll(workflows);
  console.log('scanned ' + res.scanned + ' workflow(s)');
  console.log('UNRESOLVED node references: ' + res.findings.length);
  for (const f of res.findings) {
    console.log('  ' + (f.active ? 'ACTIVE  ' : 'inactive') + ' ' + f.workflow + ' / ' + f.node +
      ' (' + f.nodeType + ')' + (f.disabled ? ' [node disabled]' : '') +
      "  ->  $('" + f.reference + "') MISSING");
  }
  console.log('dynamic (unresolvable statically, informational): ' + res.dynamic.length);
  const seen = new Set();
  for (const d of res.dynamic) {
    const k = d.workflow + '|' + d.expression;
    if (seen.has(k)) continue;
    seen.add(k);
    console.log('  ' + d.workflow + ' / ' + d.node + '  ' + d.expression);
  }
  process.exit(res.findings.length === 0 ? 0 : 1);
}

module.exports = { lintWorkflow, lintAll, refsIn };
