// CLASS STATIC — "all lead selection inside one execution resolves to the SAME lead."
//                 (Nik, 2026-09-03)
//
// A workflow may decide WHICH lead an event belongs to exactly once per execution. Every other node
// that needs a lead must take the id that decision produced. Re-selecting is the defect: two
// selectors over the same list, with different policies, silently send two writes to two different
// records.
//
// Bought by: WF-1's reply branch. `M7 Build` picked the lead whose Campaign field matched (the
// estate's one-lead-per-campaign rule) and fed the alert, the reply activity and the follow-up
// task. `M7 Labels Compute`, twenty nodes later, re-selected the NEWEST non-archived lead and fed
// the label PATCH. Five live people were in a state where those are different records - and in four
// of them the label target had no campaign at all, twice an inbound website enquiry. '3. Responded'
// is the handover trigger, so that is a false handover on a record that never saw the campaign.
// Five of WF-1's six selectors used campaign-match; the label step was the only outlier.
//
// TWO KINDS OF `find` OVER A LEAD LIST, and the rule turns on the difference:
//   POLICY selection - decides which lead this event is about (campaign match, or newest).
//                      At most ONE reachable in any single execution.
//   ID resolution    - looks up a lead whose id was ALREADY decided upstream. Always allowed;
//                      it is in fact the fix.
//
// GROUPING COMES FROM THE GRAPH, NOT FROM NODE NAMES.
// The first version of this static grouped by an `M5`/`M6`/`M7` name prefix - WF-1's convention and
// nothing else's. It lumped WF-2's four event branches (sent, reply, bounce, unsubscribe) into one
// bucket and reported four selectors racing, when each is the only selector on its own branch.
// A static whose grouping is a naming convention reports defects that are really spelling. Ask the
// graph: two nodes reached from DIFFERENT outputs of the same IF/Switch can never both run.
//
// Usage:  node static_lead_selection.js <workflows.json>
// Exit 0 = invariant holds. 1 = violation. 2 = could not check.

function touchesLeadList(js) {
  return /is_archived/.test(js) && /\.filter\(/.test(js);
}

function policyKind(js) {
  const byCampaign = /lead_campaign/.test(js) && /\.find\(/.test(js);
  const byNewest = /add_time/.test(js) && /\.sort\(/.test(js);
  if (byCampaign && byNewest) return 'campaign+newest';
  if (byCampaign) return 'campaign-match';
  if (byNewest) return 'newest';
  return null;
}

function resolvesById(js) {
  return /\.find\(\s*\w+\s*=>\s*\w+\.id\s*===/.test(js);
}

function reverseGraph(wf) {
  const rev = {};
  Object.keys(wf.connections || {}).forEach(src => {
    ((wf.connections[src] || {}).main || []).forEach((branch, oi) => {
      (branch || []).forEach(t => { (rev[t.node] = rev[t.node] || []).push({ src: src, oi: oi }); });
    });
  });
  return rev;
}

// every (gate, output) pair from which this node is reachable
function gateTags(wf, rev, name) {
  const byName = {};
  (wf.nodes || []).forEach(n => { byName[n.name] = n; });
  const tags = {}, seen = {}, q = [name];
  while (q.length) {
    const cur = q.shift();
    (rev[cur] || []).forEach(e => {
      const t = (byName[e.src] || {}).type;
      if (t === 'n8n-nodes-base.if' || t === 'n8n-nodes-base.switch') {
        (tags[e.src] = tags[e.src] || {})[e.oi] = true;
      }
      const k = e.src + '|' + cur;
      if (seen[k]) return;
      seen[k] = true;
      q.push(e.src);
    });
  }
  return tags;
}

// separated if some gate reaches each of them on exactly one, different, output
function separated(ta, tb) {
  return Object.keys(ta).some(function (g) {
    if (!tb[g]) return false;
    const a = Object.keys(ta[g]), b = Object.keys(tb[g]);
    if (a.length !== 1 || b.length !== 1) return false;
    return a[0] !== b[0];
  });
}

function check(workflows) {
  const rows = [];
  workflows.forEach(wf => {
    // Archived workflows are preserved artifacts, not live code. Their defects were often the
    // reason they were archived; reporting them for ever trains people to ignore the static.
    if (String(wf.name || '').indexOf('ARCHIVE__') === 0) return;
    const rev = reverseGraph(wf);
    (wf.nodes || []).forEach(n => {
      const js = String(((n.parameters || {}).jsCode) || '');
      if (!js || !touchesLeadList(js)) return;
      const kind = policyKind(js);
      if (!kind) return;   // resolves an already-decided id: allowed, and it is the fix
      rows.push({ workflow: wf.name, workflow_id: wf.id, active: wf.active === true,
                  node: n.name, kind: kind, alsoResolvesById: resolvesById(js),
                  tags: gateTags(wf, rev, n.name) });
    });
  });
  return rows;
}

function violations(rows) {
  const out = [];
  const byWf = {};
  rows.forEach(r => { (byWf[r.workflow_id] = byWf[r.workflow_id] || []).push(r); });
  Object.keys(byWf).forEach(k => {
    const g = byWf[k];
    for (let i = 0; i < g.length; i++) {
      for (let j = i + 1; j < g.length; j++) {
        if (separated(g[i].tags, g[j].tags)) continue;   // mutually exclusive branches
        const samePolicy = g[i].kind === g[j].kind;
        out.push({
          type: samePolicy ? 'two_selectors_same_execution' : 'two_policies_same_execution',
          workflow: g[i].workflow,
          nodes: [g[i].node + ' (' + g[i].kind + ')', g[j].node + ' (' + g[j].kind + ')'],
          detail: 'both are reachable in one execution and each decides which lead the event is '
                + 'about' + (samePolicy ? '.'
                  : ' - by DIFFERENT policies, so they disagree for anyone holding more than one lead.')
        });
      }
    }
  });
  return out;
}

if (require.main === module) {
  const fs = require('fs');
  const path = process.argv[2];
  if (!path) { console.error('usage: node static_lead_selection.js <workflows.json>'); process.exit(2); }
  const raw = JSON.parse(fs.readFileSync(path, 'utf8'));
  const wfs = Array.isArray(raw) ? raw : (raw.data || raw.workflows || null);
  if (!Array.isArray(wfs) || wfs.length === 0) {
    console.error('CLASS STATIC: could not read a workflow array - refusing to report PASS');
    process.exit(2);
  }
  const rows = check(wfs);
  const bad = violations(rows);
  console.log('class static: one lead decision per execution; nothing re-selects\n');
  console.log('   ' + 'workflow'.padEnd(28) + 'node'.padEnd(26) + 'policy');
  rows.sort((a, b) => (a.workflow + a.node).localeCompare(b.workflow + b.node));
  rows.forEach(r => console.log('  ' + (r.active ? 'A ' : '- ') + r.workflow.slice(0, 26).padEnd(28) +
      r.node.slice(0, 24).padEnd(26) + r.kind + (r.alsoResolvesById ? '  (+id resolution)' : '')));
  if (bad.length) {
    console.log('\nVIOLATIONS:');
    bad.forEach(v => {
      console.log('  x [' + v.type + '] ' + v.workflow);
      console.log('      ' + v.nodes.join('   |   '));
      console.log('      ' + v.detail);
    });
  }
  console.log('\n' + (bad.length ? 'FAIL - ' + bad.length + ' violation(s)' : 'PASS - invariant holds'));
  process.exit(bad.length ? 1 : 0);
}

module.exports = { check: check, violations: violations };
