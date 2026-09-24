// WF-2H static contract tests.
//
// WF-2H shipped with no suite at all and failed EVERY run of its entire life - two defect classes
// that had already been found and fixed in WF-2S and simply never carried over:
//   S1  backward $('CONFIG').item downstream of the Pick Active fan-out -> paired item unavailable
//   S2  Pick Active read $json from the SPLIT /campaigns array -> saw campaign #1, not the list
// Both are behavioural, so only executing the node code catches them.
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const WF = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'wf1-release-evidence', 'wf2h-built.json'), 'utf8'));
const nodeByName = (n) => WF.nodes.find((x) => x.name === n)
  || (() => { throw new Error('no such node: ' + n); })();
const CFG = JSON.parse(nodeByName('CONFIG').parameters.jsonOutput);

let pass = 0; const fails = [];
function t(id, fn) { try { fn(); pass++; } catch (e) { fails.push(id + ': ' + e.message); } }
function eq(a, b, m) {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error((m || '') + ' expected ' + B + ' got ' + A);
}
function ok(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

function run(nodeName, { input = [], named = {} } = {}) {
  const js = nodeByName(nodeName).parameters.jsCode;
  const items = input.map((j) => ({ json: j }));
  const ctx = {
    $input: { all: () => items, first: () => items[0] },
    $json: items.length ? items[0].json : {},
    $: (n) => {
      if (!(n in named)) throw new Error('node ' + n + ' not available to ' + nodeName);
      const its = named[n].map((j) => ({ json: j }));
      return {
        all: () => its,
        first: () => its[0],
        // the landmine: any backward paired lookup fails exactly as it did in production
        get item() {
          throw new Error("Paired item data for item from node '" + n + "' is unavailable");
        },
      };
    },
    Date, JSON, Number, String, Array, Object, Boolean, Math, isNaN, parseInt, parseFloat, Error,
  };
  return (vm.runInNewContext('(function(){' + js + '})()', ctx, { timeout: 5000 }) || [])
    .map((i) => i.json);
}

// /campaigns is a bare array; n8n splits it into one item per campaign
const campaignsSplit = [
  { id: 3686193, name: '[Events Visiting] AI4 - Rune - Catch-alls', status: 'ACTIVE' },
  { id: 3686187, name: '[Events Visiting] AI4 - Rune - Valids', status: 'ACTIVE' },
  { id: 3565502, name: 'Old paused thing', status: 'PAUSED' },
  { id: 3600001, name: 'Completed thing', status: 'COMPLETED' },
];

// ---------------------------------------------------------------- S2
t('H-S2-1 Pick Active reads the SPLIT array, not $json', () => {
  const out = run('Pick Active', { input: campaignsSplit });
  eq(out.map((o) => o.campaign_id), [3686193, 3686187],
     'reading $json here sees campaign #1 only - the digest silently covered one arbitrary campaign');
});
t('H-S2-2 the fixture genuinely reproduces the split condition', () => {
  ok(!Array.isArray(campaignsSplit[0]) && campaignsSplit[0].data === undefined,
     'fixture does not discriminate');
});
t('H-S2-3 a wrapped {data:[...]} response also parses', () => {
  eq(run('Pick Active', { input: [{ data: campaignsSplit }] }).map((o) => o.campaign_id),
     [3686193, 3686187], 'wrapped shape');
});
t('H-S2-4 an unparseable poll THROWS rather than emitting an empty digest', () => {
  let threw = false;
  try { run('Pick Active', { input: [] }); } catch (e) { threw = /nothing parseable/.test(e.message); }
  ok(threw, 'a digest that says "0 campaigns" when the API failed is worse than no digest');
});
t('H-S2-5 no ACTIVE campaigns is a legitimate quiet day, not an error', () => {
  const out = run('Pick Active', { input: [campaignsSplit[2]] });
  eq(out[0].__none, true, 'idle shape');
});

// ---------------------------------------------------------------- S1
t('H-S1-1 no node reaches backward for a paired item', () => {
  const bad = WF.nodes.filter((n) => JSON.stringify(n.parameters).includes(').item'));
  eq(bad.map((n) => n.name), [],
     'this is the exact defect that failed every WF-2H run ever attempted');
});
t('H-S1-2 CONFIG is resolved with .first() everywhere it is read', () => {
  const users = WF.nodes.filter((n) => JSON.stringify(n.parameters).includes("$('CONFIG')"));
  ok(users.length >= 4, 'expected several CONFIG readers');
  for (const n of users) {
    ok(JSON.stringify(n.parameters).includes("$('CONFIG').first()"),
       `${n.name}: CONFIG not read with .first()`);
  }
});
t('H-S1-3 Quality Digest runs with CONFIG available only via .first()', () => {
  const out = run('Quality Digest', {
    input: [{ data: [{ add_time: new Date().toISOString(), label_ids: [CFG.labels.responded] }] }],
    named: { CONFIG: [CFG] },
  });
  eq(out[0].__leads_recent, 1, 'recent lead not counted');
  eq(out[0].__responded, 1, 'responded label not counted');
});
t('H-S1-4 SL Stats Summary folds every campaign, not just the first', () => {
  const out = run('SL Stats Summary', {
    input: [{ total_stats: 227 }, { total_stats: 204 }, { total_stats: 206 }],
  });
  eq(out[0].__campaigns, 3, 'campaign count');
  eq(out[0].__stat_rows, 637, 'row totals must sum across campaigns');
});

// ---------------------------------------------------------------- PAGINATION (third strike)
// Any /v1 list read used for COUNTING must prove its ordering. Unsorted, /v1/leads returns the
// OLDEST page first (verified live: first row add_time 2023-05-02), so the 24h filter matched
// nothing and this digest reported "leads touched: 0" for its entire life.
t('H-PG-1 the leads read explicitly requests newest-first ordering', () => {
  const url = String(nodeByName('PD Leads').parameters.url);
  ok(/sort=add_time(%20|\+| )DESC/i.test(url),
     'an unsorted list read cannot be counted from - it returns the oldest page');
});
t('H-PG-2 the trap fixture: old leads outnumber the window and must NOT be counted', () => {
  const old = [];
  for (let i = 0; i < 40; i++) old.push({ add_time: '2023-05-02T20:58:13.449Z', label_ids: [] });
  const fresh = [{ add_time: new Date().toISOString(), label_ids: [CFG.labels.cold] }];
  // DESC order, as the fixed URL now guarantees
  const out = run('Quality Digest', { input: [{ data: [...fresh, ...old] }],
                                      named: { CONFIG: [CFG] } });
  eq(out[0].__leads_recent, 1, 'the 2023 backlog leaked into a 24h count');
  eq(out[0].__cold, 1, 'label counters must follow the same window');
});
t('H-PG-3 a saturated page is REPORTED, not silently truncated', () => {
  const now = new Date().toISOString();
  const all = [];
  for (let i = 0; i < 500; i++) all.push({ add_time: now, label_ids: [] });
  const out = run('Quality Digest', { input: [{ data: all }], named: { CONFIG: [CFG] } });
  eq(out[0].__leads_recent, 500);
  eq(out[0].__leads_capped, true, 'saying 500 when it might be 900 is a quiet lie');
});
t('H-PG-4 an unsaturated page is not flagged', () => {
  const out = run('Quality Digest', {
    input: [{ data: [{ add_time: new Date().toISOString(), label_ids: [] },
                     { add_time: '2023-01-01T00:00:00Z', label_ids: [] }] }],
    named: { CONFIG: [CFG] } });
  eq(out[0].__leads_capped, false, 'false saturation warning');
});

// ---------------------------------------------------------------- structural
t('H-ST-1 the digest posts to the ops channel from CONFIG', () => {
  const n = nodeByName('WF-2H Digest');
  ok(JSON.stringify(n.parameters).includes('ops_channel'), 'channel not from CONFIG');
  eq(CFG.ops_channel, 'C0B8GCVNR5W', 'ops channel changed unexpectedly');
});
t('H-ST-2 the error workflow is bound - a silent daily failure is the whole problem here', () => {
  eq(WF.settings.errorWorkflow, 'BbrXPABgOaaTJjD6');
});
t('H-ST-3 every node is reachable from the trigger', () => {
  const seen = new Set(['Daily']);
  let grew = true;
  while (grew) {
    grew = false;
    for (const [from, out] of Object.entries(WF.connections)) {
      if (!seen.has(from)) continue;
      for (const branch of out.main || []) {
        for (const c of branch || []) if (!seen.has(c.node)) { seen.add(c.node); grew = true; }
      }
    }
  }
  eq(WF.nodes.map((n) => n.name).filter((n) => !seen.has(n)), [], 'orphaned node');
});
t('H-ST-4 no key material and no hardcoded hosts outside CONFIG', () => {
  const blob = JSON.stringify(WF);
  ok(!/api_key=[A-Za-z0-9]{8}/.test(blob), 'api_key in a URL');
  const bad = WF.nodes.filter((n) => n.name !== 'CONFIG'
    && /server\.smartlead\.ai|api\.pipedrive\.com/.test(JSON.stringify(n.parameters)));
  eq(bad.map((n) => n.name), [], 'hardcoded host outside CONFIG');
});
t('H-ST-5 every HTTP call is authenticated', () => {
  const bad = WF.nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest'
    && !n.parameters.authentication);
  eq(bad.map((n) => n.name), [], 'unauthenticated call');
});

console.log('WF-2H statics: ' + pass + ' passed, ' + fails.length + ' failed');
if (fails.length) { fails.forEach((f) => console.log('  FAIL ' + f)); process.exit(1); }
