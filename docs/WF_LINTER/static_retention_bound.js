// CLASS STATIC - "every state store has a retention bound." (Nik, 2026-09-03)
//
// A store that only ever grows is a defect with a long fuse: it looks perfect for months and then
// becomes an outage, a cost, or - worse - a correctness problem, because the thing that was meant
// to expire never does.
//
// BOUGHT TWICE, and the second time by us:
//   * dnc_i04_event_log grew unbounded until it needed a retention job bolted on.
//   * The WF-1 alert registry PRUNED AT 90 DAYS in staticData. When it was ported to the claims
//     table on 2026-09-03 the prune did not come with it, and nothing anywhere deleted from that
//     table. The port silently removed a property the old implementation had. That is the class:
//     A FIX THAT LOSES A PROPERTY NOBODY NOTICES.
//
// WHAT COUNTS AS BOUNDED
//   staticData: the workflow that writes the store also deletes from it (a rotation loop), or the
//               store is a scalar (a flag or a timestamp, which cannot grow).
//   dataTable:  SOME workflow in the estate performs a deleteRows on that table. The bound does
//               not have to live in the writer - dnc_claims_prune and dnc_i04_event_log_prune are
//               separate scheduled workflows - so this check is ESTATE-WIDE, not per workflow.
//
// Usage:  node static_retention_bound.js <workflows.json>
// Exit 0 = every store is bounded. 1 = an unbounded store. 2 = could not check.

// PERMANENT BY DESIGN. A store is exempt only when someone has written down WHY - the point
// of this static is to force the decision, not to let "we meant to" pass silently.
// ACCEPTED UNBOUNDED (Nik, 2026-09-03). Not bounded, deliberately: each is a handful of keys
// whose worst case is a duplicate ops message, and adding retention nodes to a 188-node
// receiver costs more than it saves. Recorded here so 'we decided' cannot decay into
// 'nobody noticed' - and so a NEW unbounded store still fails this static.
const { stripJsComments, codeStrippedParams } = require('./lint_rules.js');
const ACCEPTED_UNBOUNDED = {
  'WF-2 Smartlead Receiver|__event_aliases_seen':
    'one key per Smartlead event name we have not seen before, so it is bounded by how many '
  + 'names Smartlead has. Worst case is a duplicate ops warning; nothing gates on it. Adding '
  + 'a rotation to a 188-node receiver costs more than it saves. (Nik, 2026-09-03.)'
};

const PERMANENT_BY_DESIGN = {
  'UOgKwlGsL28lX61O': 'the DNC ledger. A do-not-contact record must outlive everything; '
                    + 'expiring one would re-open contact with somebody who asked us to '
                    + 'stop. 25,653 active rows as of 2026-09-03.'
};

function staticStores(wf) {
  const out = [];
  (wf.nodes || []).forEach(n => {
    const js = stripJsComments((n.parameters || {}).jsCode);
    if (js.indexOf('getWorkflowStaticData') === -1) return;

    // ONLY keys hung off the staticData object itself.
    // The first version of this matched `<anything>.<key>[...] =`, which flagged
    // `d.by_inbox[inbox] = ...` where `d` is a LOCAL day bucket already inside a 30-day
    // rotation. Two false findings, and I came within one edit of recording them as accepted
    // fact. A static that invents stores is worse than no static.
    //
    // Regex LITERALS only, never `new RegExp('...\\.')` built from strings: the string form is
    // how this file got an empty alternation and hung the linter.
    const roots = new Set();
    let m;
    const reRoot = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*\$getWorkflowStaticData\s*\(/g;
    while ((m = reRoot.exec(js))) roots.add(m[1]);
    if (!roots.size) return;

    const asObject = new Set();
    const lines = js.split('\n');
    roots.forEach(root => {
      const pre = root + '.';
      lines.forEach(line => {
        let i = 0;
        while ((i = line.indexOf(pre, i)) !== -1) {
          const rest = line.slice(i + pre.length);
          const hit = rest.match(/^([A-Za-z_$][\w$]*)\s*(\[|=)/);
          if (hit) {
            // sd.X[k] = v        -> a collection keyed at runtime
            // sd.X = sd.X || {}  -> a collection being initialised
            if (hit[2] === '[') asObject.add(hit[1]);
            else if (/\|\|\s*\{\s*\}/.test(rest)) asObject.add(hit[1]);
          }
          i += pre.length;
        }
      });
    });
    asObject.forEach(k => out.push({ workflow: wf.name, node: n.name, store: k, js: js }));
  });
  return out;
}

function hasRotation(wf, store) {
  // Deliberately string-matching rather than building regexes from the store name: a regex
  // assembled by concatenation is how this check broke the first time it was written.
  const needleIdx = '.' + store + '[';
  const needleDot = '.' + store;
  return (wf.nodes || []).some(n => {
    const js = stripJsComments((n.parameters || {}).jsCode);
    if (js.indexOf('delete ') === -1) return false;
    const lines = js.split('\n');
    // direct:  delete sd.STORE[k]
    if (lines.some(l => l.indexOf('delete ') !== -1 && l.indexOf(needleIdx) !== -1)) return true;
    // aliased: const reg = sd.STORE ... delete reg[k]
    const aliases = [];
    lines.forEach(l => {
      if (l.indexOf(needleDot) === -1) return;
      const m = l.match(/(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/);
      if (m) aliases.push(m[1]);
    });
    // `delete c[k]` AND `delete c.by_day[k]` both bound the store rooted at `c`.
    return aliases.some(a => lines.some(l => l.indexOf('delete ' + a + '[') !== -1
                                          || l.indexOf('delete ' + a + '.') !== -1));
  });
}

function tableOps(workflows) {
  const written = {}, deleted = {};
  workflows.forEach(wf => {
    if (String(wf.name || '').indexOf('ARCHIVE__') === 0) return;
    (wf.nodes || []).forEach(n => {
      if (n.type !== 'n8n-nodes-base.dataTable') return;
      const p = n.parameters || {};
      const id = ((p.dataTableId || {}).value) || null;
      if (!id) return;
      const op = p.operation;
      if (op === 'upsert' || op === 'insert' || op === 'create') {
        (written[id] = written[id] || []).push(wf.name + ' / ' + n.name);
      }
      if (op === 'deleteRows' || op === 'delete') {
        (deleted[id] = deleted[id] || []).push(wf.name + ' / ' + n.name);
      }
    });
  });
  return { written, deleted };
}

function check(workflows) {
  const findings = [];
  workflows.forEach(wf => {
    if (String(wf.name || '').indexOf('ARCHIVE__') === 0) return;
    const seen = new Set();
    staticStores(wf).forEach(s => {
      const id = s.workflow + '|' + s.store;
      if (seen.has(id)) return;
      seen.add(id);
      if (!hasRotation(wf, s.store) && !ACCEPTED_UNBOUNDED[id]) {
        findings.push({ kind: 'staticData', workflow: wf.name, active: wf.active === true,
                        store: s.store, where: s.node,
                        detail: 'written as a collection, but no delete/rotation anywhere in this '
                              + 'workflow' });
      }
    });
  });
  const { written, deleted } = tableOps(workflows);
  Object.keys(written).forEach(id => {
    if (!deleted[id] && !PERMANENT_BY_DESIGN[id]) {
      findings.push({ kind: 'dataTable', workflow: written[id].join('; '), active: true,
                      store: id, where: written[id][0],
                      detail: 'rows are written by ' + written[id].length + ' node(s) and NO '
                            + 'workflow in the estate deletes from this table' });
    }
  });
  return findings;
}

if (require.main === module) {
  const fs = require('fs');
  const path = process.argv[2];
  if (!path) { console.error('usage: node static_retention_bound.js <workflows.json>'); process.exit(2); }
  const raw = JSON.parse(fs.readFileSync(path, 'utf8'));
  const wfs = Array.isArray(raw) ? raw : (raw.data || raw.workflows || null);
  if (!Array.isArray(wfs) || wfs.length === 0) {
    console.error('RETENTION STATIC: could not read a workflow array - refusing to report PASS');
    process.exit(2);
  }
  const bad = check(wfs);
  console.log('class static: every state store has a retention bound\n');
  Object.keys(PERMANENT_BY_DESIGN).forEach(k => {
    console.log('  - exempt (permanent by design): ' + k);
    console.log('      ' + PERMANENT_BY_DESIGN[k]);
  });
  Object.keys(ACCEPTED_UNBOUNDED).forEach(k => {
    console.log('  - accepted unbounded: ' + k);
    console.log('      ' + ACCEPTED_UNBOUNDED[k]);
  });
  if (Object.keys(PERMANENT_BY_DESIGN).length) console.log('');
  if (!bad.length) console.log('  (no unbounded stores)');
  bad.forEach(f => {
    console.log('  x [' + f.kind + '] ' + f.store);
    console.log('      ' + f.workflow + (f.kind === 'staticData' ? '  @ ' + f.where : ''));
    console.log('      ' + f.detail);
  });
  console.log('\n' + (bad.length ? 'FAIL - ' + bad.length + ' unbounded store(s)'
                                 : 'PASS - every state store is bounded'));
  process.exit(bad.length ? 1 : 0);
}

module.exports = { check: check };
