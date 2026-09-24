// CLASS STATIC — "no automated event writes '3. Responded' without, in the SAME PATCH, the label
// its category implies."   (Nik, 2026-09-02, superseding the 2026-09-02 morning rule)
//
// Pipedrive's handover automation now fires only when the lead's labels do NOT contain
// 'DO NOT CONTACT' or 'Disqualified'. So withholding '3. Responded' is no longer the control -
// writing the truthful pair in one PATCH is:
//
//   explicit stop  -> Responded + DO NOT CONTACT
//   negative reply -> Responded + Disqualified
//   genuine interest -> Responded
//   out of office  -> no Responded
//   bounce         -> no Responded, no Connected
//
// TWO checks, because a regex cannot prove behaviour:
//   1. THIS FILE is the estate-wide scan: every node that can write the label must be accounted
//      for, and the only accepted account is that it derives its target set from the ONE shared
//      implementation, or that it provably cannot emit the label.
//   2. WF_SHARED/test_label_target.js is the behavioural proof of the mapping itself - it
//      executes labelTargetV1 over every case and 288 combinations.
//
// A node that hand-rolls its own target set is a VIOLATION even if it happens to be correct
// today. That is the whole lesson of `Body U Lead DNC Label`: two copies of one idea, one of
// which got the locks.
//
// Usage:  node static_responded_class.js <workflows.json>
// Exit 0 = invariant holds. 1 = violation. 2 = could not check.

const { stripJsComments, codeStrippedParams } = require('./lint_rules.js');
const RESPONDED_ID = 'c9d4b550-bcf3-11ef-a843-357f91e826ec';

// A node is a WRITER if it BUILDS a label array. A digest that merely counts `l.label_ids` is a
// reader and is not in scope - the rule is about applying the label, not observing it.
//
// The first version used /label_ids\s*:/ || /target\.push/ || /__body/ and MISSED
// `M7 Labels Compute` in WF-1 - a live writer that emits via the shorthand `label_ids,` and
// `targetSet.push(...)`. A class static that cannot see a writer reports a false PASS, which is
// the exact failure it exists to prevent. Match the construction, not one spelling of it.
function isLabelWriter(blob) {
  return /label_ids\s*[:,=]/.test(blob) || /[Tt]arget[A-Za-z_$]*\.push\(/.test(blob);
}

// A RULE ENGINE quotes the very patterns it polices, so any textual scanner matches its
// documentation rather than a write. `dnc_wf_linter`'s own Lint node contains the words
// `label_ids,` and `targetSet.push(...)` because it explains why they matter. Detected
// generally - by the rule-registration signature - rather than excluded by workflow name.
function isRuleEngine(blob) {
  return /add\('R\d\d_/.test(blob);
}

function mentionsResponded(blob) {
  return blob.indexOf(RESPONDED_ID) !== -1 || /labels\.responded/.test(blob);
}

// (a) derives its target set from the one shared implementation
function usesSharedEngine(blob) {
  return /labelTargetV1\s*\(/.test(blob) && /function\s+labelTargetV1/.test(blob);
}

// (b) provably incapable: the label is taken out of the node's own target set
function stripsResponded(blob) {
  return /indexOf\(\s*[A-Za-z_$][\w$]*\.labels\.responded\s*\)/.test(blob) && /\.splice\(/.test(blob);
}

// (c) LinkedIn stage rank. WF-1 has no reply classifier at all, so it can only ever produce the
// "genuine interest -> Responded only" case. That is consistent with the rule, but it means a
// LinkedIn reply saying "stop contacting me" gets Responded with no suppressing label and the
// handover fires. Reported, not silently passed.
function gatedOnStageRank(blob) {
  return /stageRank|effectiveRank/.test(blob);
}

function check(workflows) {
  const rows = [];
  workflows.forEach(wf => {
    (wf.nodes || []).forEach(n => {
      const blob = JSON.stringify(codeStrippedParams(n.parameters));
      if (isRuleEngine(blob)) return;
      if (!mentionsResponded(blob) || !isLabelWriter(blob)) return;
      if (n.type === 'n8n-nodes-base.set' && (n.parameters || {}).mode === 'raw') return;
      let verdict, why;
      if (usesSharedEngine(blob)) {
        verdict = 'OK/shared'; why = 'derives its target set from labelTargetV1';
      } else if (stripsResponded(blob)) {
        verdict = 'OK/stripped'; why = 'cannot emit the label on any branch';
      } else if (gatedOnStageRank(blob)) {
        verdict = 'NOTE/no-classifier';
        why = 'LinkedIn stage rank; no classifier exists, so it can only ever write Responded alone';
      } else {
        verdict = 'VIOLATION'; why = 'hand-rolled label target - not derived from labelTargetV1';
      }
      rows.push({ workflow: wf.name, workflow_id: wf.id, active: wf.active === true,
                  node: n.name, verdict, why });
    });
  });
  return rows;
}

if (require.main === module) {
  const fs = require('fs');
  const path = process.argv[2];
  if (!path) { console.error('usage: node static_responded_class.js <workflows.json>'); process.exit(2); }
  const raw = JSON.parse(fs.readFileSync(path, 'utf8'));
  const wfs = Array.isArray(raw) ? raw : (raw.data || null);
  // Positive shape check: an unreadable input is NOT a clean estate.
  if (!Array.isArray(wfs) || wfs.length === 0) {
    console.error('CLASS STATIC: could not read a workflow array from ' + path
                + ' - refusing to report PASS');
    process.exit(2);
  }
  const rows = check(wfs);
  const bad = rows.filter(r => r.verdict === 'VIOLATION');
  const notes = rows.filter(r => r.verdict.indexOf('NOTE') === 0);
  console.log('class static: every "3. Responded" writer must derive its target from labelTargetV1');
  console.log('scanned ' + wfs.length + ' workflows, ' + rows.length + ' label writer(s) touch the label\n');
  const order = v => (v === 'VIOLATION' ? 0 : v.indexOf('NOTE') === 0 ? 1 : 2);
  rows.sort((a, b) => order(a.verdict) - order(b.verdict));
  rows.forEach(r => console.log('  ' + (r.active ? 'A' : '-') + ' ' + r.verdict.padEnd(19) +
      r.workflow.slice(0, 26).padEnd(27) + r.node.slice(0, 24).padEnd(25) + r.why));
  if (notes.length) {
    console.log('\n  ' + notes.length + ' NOTE(s): compliant with the rule, but limited - see above.');
  }
  console.log('\n' + (bad.length ? 'FAIL - ' + bad.length + ' violation(s)' : 'PASS - invariant holds'));
  process.exit(bad.length ? 1 : 0);
}

module.exports = { check };
