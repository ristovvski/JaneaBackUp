// CLASS-LEVEL invariants. Not "bounce does not set Responded" — "NO automated event sets
// Responded without a human-reply signal", asserted against every workflow in the estate.
//
// A static written at instance level only protects the instance. Each of these is the general
// form of a defect that has actually shipped, and each one FAILS the run if any workflow in the
// estate violates it — including workflows that do not exist yet.
//
// Usage:  node class_invariants.js            (fetches live definitions)
//         node class_invariants.js file.json  (a saved /workflows response)
const { stripJsComments, codeStrippedParams } = require('./lint_rules.js');
const fs = require('fs');
const https = require('https');

const RESPONDED = 'c9d4b550-bcf3-11ef-a843-357f91e826ec';   // '3. Responded'
const CONNECTED = 'ca698a50-bdfb-11ef-8172-510383583b0e';

let P = 0, F = 0;
const fail = [];
function t(name, ok, detail) {
  if (ok) { P++; console.log('  PASS  ' + name); }
  else { F++; fail.push(name); console.log('  FAIL  ' + name + (detail ? '\n          ' + detail : '')); }
}

function get(path) {
  const KEY = process.env.N8N_API_KEY;
  const BASE = (process.env.N8N_BASE_URL || '').replace(/\/+$/, '') + '/api/v1';
  const CA = fs.readFileSync(process.env.REQUESTS_CA_BUNDLE);
  return new Promise((res, rej) => {
    const u = new URL(BASE + path);
    https.get({ hostname: u.hostname, path: u.pathname + u.search, ca: CA,
                headers: { 'X-N8N-API-KEY': KEY, Accept: 'application/json' } }, r => {
      let b = ''; r.on('data', d => b += d);
      r.on('end', () => { try { res(JSON.parse(b)); } catch (e) { rej(e); } });
    }).on('error', rej);
  });
}

function graph(wf) {
  const byName = {}; (wf.nodes || []).forEach(n => { byName[n.name] = n; });
  const fwd = {};
  Object.keys(wf.connections || {}).forEach(src => {
    ((wf.connections[src] || {}).main || []).forEach((br, oi) => {
      (br || []).forEach(t => { (fwd[src] = fwd[src] || []).push({ node: t.node, out: oi }); });
    });
  });
  const reach = (start, outFilter) => {
    const seen = {}; const q = [];
    ((fwd[start] || [])).forEach(e => {
      if (outFilter === undefined || e.out === outFilter) q.push(e.node); });
    while (q.length) {
      const cur = q.shift();
      if (seen[cur]) continue;
      seen[cur] = true;
      (fwd[cur] || []).forEach(e => { if (!seen[e.node]) q.push(e.node); });
    }
    return Object.keys(seen);
  };
  return { byName, fwd, reach };
}

const blob = n => JSON.stringify(codeStrippedParams(n.parameters));

(async () => {
  let wfs;
  if (process.argv[2]) wfs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).data;
  else {
    wfs = [];
    let cur = null;
    do { const d = await get('/workflows?limit=250' + (cur ? '&cursor=' + cur : ''));
         wfs = wfs.concat(d.data || []); cur = d.nextCursor; } while (cur);
  }
  console.log('workflows: ' + wfs.length + ' (active ' + wfs.filter(w => w.active).length + ')\n');

  // ============================================================ INVARIANT 1
  // NO automated path may add '3. Responded' in a workflow that can also classify a delivery
  // failure, unless that same node carries an explicit bounce guard. '3. Responded' is Marci's
  // Handover trigger: it hands a human a lead as warm. A dead mailbox must never trip it.
  // General form of: the bounce-as-reply defect, 2026-08-31.
  console.log('[1] no automated event sets 3. Responded without a bounce guard');
  {
    const offenders = [];
    wfs.forEach(wf => {
      const handlesBounce = JSON.stringify(wf.nodes || []).indexOf('BOUNCED') !== -1;
      if (!handlesBounce) return;
      (wf.nodes || []).forEach(n => {
        // a raw Set node DECLARES the label map; it does not apply it
        if (n.type === 'n8n-nodes-base.set' && (n.parameters || {}).mode === 'raw') return;
        const b = blob(n);
        const writes = b.indexOf(RESPONDED) !== -1 || /labels\.responded/.test(b);
        if (!writes) return;
        const guarded = /__is_bounce|__isBounce|is_bounced/.test(b);
        if (!guarded) offenders.push(wf.name + ' / ' + n.name + (wf.active ? ' (ACTIVE)' : ''));
      });
    });
    t('every Responded writer in a bounce-handling workflow carries a bounce guard',
      offenders.length === 0, offenders.join('\n          '));
  }

  // ============================================================ INVARIANT 2
  // Nothing downstream of a BOUNCED classification may alert a human or write a label.
  // A bounce is the absence of contact; announcing it is the defect, whatever produced it.
  console.log('\n[2] the BOUNCED branch reaches no alert and no label write');
  {
    const offenders = [];
    wfs.forEach(wf => {
      const g = graph(wf);
      const sw = (wf.nodes || []).find(n => n.type === 'n8n-nodes-base.switch'
        && blob(n).indexOf('BOUNCED') !== -1);
      if (!sw) return;
      const rules = (((sw.parameters || {}).rules || {}).values || []);
      const idx = rules.findIndex(r => JSON.stringify(r).indexOf('BOUNCED') !== -1);
      if (idx < 0) return;
      g.reach(sw.name, idx).forEach(nm => {
        const n = g.byName[nm]; if (!n) return;
        if (n.type === 'n8n-nodes-base.slack') {
          offenders.push(wf.name + ': BOUNCED reaches Slack node "' + nm + '"');
        }
        if (blob(n).indexOf(RESPONDED) !== -1 || blob(n).indexOf(CONNECTED) !== -1) {
          offenders.push(wf.name + ': BOUNCED reaches label writer "' + nm + '"');
        }
      });
    });
    t('no Slack node and no Responded/Connected writer is reachable from BOUNCED',
      offenders.length === 0, offenders.join('\n          '));
  }

  // ============================================================ INVARIANT 3
  // Every conditional Slack post on a schedule must remember its last verdict. General form of:
  // the drainer-STUCK and I-04 did-not-post floods, 2026-08-31.
  console.log('\n[3] no scheduled conditional alert re-fires per poll');
  {
    const offenders = [];
    wfs.forEach(wf => {
      if (!(wf.nodes || []).some(n => n.type === 'n8n-nodes-base.scheduleTrigger')) return;
      const slacks = (wf.nodes || []).filter(n => n.type === 'n8n-nodes-base.slack');
      if (!slacks.length) return;
      if (JSON.stringify(wf.nodes).indexOf('getWorkflowStaticData') !== -1) return;
      const g = graph(wf);
      const gated = {};
      (wf.nodes || []).filter(n => n.type === 'n8n-nodes-base.if')
        .forEach(f => g.reach(f.name).forEach(nm => { gated[nm] = true; }));
      slacks.filter(s => gated[s.name]).forEach(s => {
        offenders.push(wf.name + ' / ' + s.name + (wf.active ? ' (ACTIVE)' : ''));
      });
    });
    t('every IF-gated Slack post on a schedule has state memory',
      offenders.length === 0, offenders.join('\n          '));
  }

  // ============================================================ INVARIANT 4
  // Linter output is single-destination. General form of: the channel-split ruling.
  console.log('\n[4] linter output goes to exactly one channel');
  {
    const lint = wfs.find(w => w.name === 'dnc_wf_linter');
    if (!lint) { t('dnc_wf_linter exists', false, 'not found'); }
    else {
      const chans = new Set();
      (lint.nodes || []).forEach(n => {
        (blob(n).match(/C0[A-Z0-9]{8,}/g) || []).forEach(c => chans.add(c));
      });
      t('the linter names only C0BQM1X9ZUY',
        chans.size === 1 && chans.has('C0BQM1X9ZUY'), Array.from(chans).join(', '));
      const guard = (lint.nodes || []).find(n => n.name === 'Lint Send Guard');
      t('a send guard enforces it at runtime, not just by convention',
        !!guard && /allowed_channels/.test(blob(guard)));
    }
  }

  // ============================================================ INVARIANT 5
  // A count derived from a provider read must be able to be null. General form of:
  // queue depth 0, the I-04 686 delta.
  console.log('\n[5] the digest can express "not measured"');
  {
    const dg = wfs.find(w => w.name === 'dnc_morning_digest');
    if (!dg) t('dnc_morning_digest exists', false, 'not found');
    else {
      const compose = (dg.nodes || []).find(n => n.name === 'Compose');
      t('the digest renders a "not measured" footer',
        !!compose && /not measured/.test(blob(compose)));
      t('the absent enrich queue is reported as absent, never as 0',
        !!compose && /no such queue exists/.test(blob(compose)));
    }
  }

  console.log('\n==== ' + P + ' passed, ' + F + ' failed');
  if (F) { console.log('failing invariants:\n  - ' + fail.join('\n  - ')); }
  process.exit(F ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
