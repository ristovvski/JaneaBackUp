// First-run / ad-hoc estate lint. Reads every workflow definition from the n8n API and prints
// the backlog grouped by pattern. Read-only.
const fs = require('fs');
const https = require('https');
const { lintAll } = require('./lint_rules.js');

const KEY = process.env.N8N_API_KEY;
const BASE = (process.env.N8N_BASE_URL || '').replace(/\/+$/, '') + '/api/v1';
const CA = fs.readFileSync(process.env.REQUESTS_CA_BUNDLE);

function get(path) {
  return new Promise((res, rej) => {
    const u = new URL(BASE + path);
    https.get({ hostname: u.hostname, path: u.pathname + u.search, ca: CA,
                headers: { 'X-N8N-API-KEY': KEY, Accept: 'application/json' } }, r => {
      let b = ''; r.on('data', d => b += d);
      r.on('end', () => { try { res(JSON.parse(b)); } catch (e) { rej(e); } });
    }).on('error', rej);
  });
}

(async () => {
  let all = [], cursor = null;
  do {
    const d = await get('/workflows?limit=250' + (cursor ? '&cursor=' + cursor : ''));
    all = all.concat(d.data || []);
    cursor = d.nextCursor;
  } while (cursor);
  console.log('workflows scanned: ' + all.length
    + '  (active ' + all.filter(w => w.active).length + ')');

  const f = lintAll(all);
  const onlyActive = process.argv.indexOf('--active-only') !== -1;
  const use = onlyActive ? f.filter(x => x.active) : f;

  const byRule = {};
  use.forEach(x => (byRule[x.rule] = byRule[x.rule] || []).push(x));
  const order = ['high', 'medium', 'low'];
  const keys = Object.keys(byRule).sort((a, b) => {
    const sa = order.indexOf(byRule[a][0].severity), sb = order.indexOf(byRule[b][0].severity);
    return sa !== sb ? sa - sb : byRule[b].length - byRule[a].length;
  });

  console.log('\nfindings: ' + use.length
    + '  (high ' + use.filter(x => x.severity === 'high').length
    + ', medium ' + use.filter(x => x.severity === 'medium').length + ')');
  console.log('affected workflows: '
    + new Set(use.map(x => x.workflow)).size + ' of ' + all.length);

  keys.forEach(k => {
    const g = byRule[k];
    console.log('\n' + '='.repeat(78));
    console.log('[' + g[0].severity.toUpperCase() + '] ' + k + '  —  ' + g.length + ' finding(s)');
    console.log('  ' + g[0].detail);
    const byWf = {};
    g.forEach(x => (byWf[x.workflow] = byWf[x.workflow] || []).push(x));
    Object.keys(byWf).sort().forEach(w => {
      const act = byWf[w][0].active ? 'ACTIVE  ' : 'inactive';
      console.log('  ' + act + ' ' + w);
      byWf[w].slice(0, 6).forEach(x => console.log('      · ' + x.node + '   [' + x.evidence + ']'));
      if (byWf[w].length > 6) console.log('      · … +' + (byWf[w].length - 6) + ' more');
    });
  });

  fs.writeFileSync(__dirname + '/lint_report.json',
    JSON.stringify({ generated_at: new Date().toISOString(),
                     workflows: all.length, findings: use }, null, 1));
  console.log('\nartifact -> WF_LINTER/lint_report.json');
})().catch(e => { console.error(e); process.exit(1); });
