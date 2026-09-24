// WF-ERR v2 static contract tests + the historical-failure fixture gallery.
//
// Every fixture below is a REAL failure this stack produced, replayed through the new report
// builder. `node wferr_static_contract_tests.js --show` prints the before/after for each.
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const WF = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'wf1-release-evidence', 'wferr-built.json'), 'utf8'));
const nodeByName = (n) => WF.nodes.find((x) => x.name === n)
  || (() => { throw new Error('no such node: ' + n); })();
const CFG = JSON.parse(nodeByName('CONFIG').parameters.jsonOutput);
const SHOW = process.argv.includes('--show');

let pass = 0; const fails = [];
function t(id, fn) { try { fn(); pass++; } catch (e) { fails.push(id + ': ' + e.message); } }
function eq(a, b, m) {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error((m || '') + ' expected ' + B + ' got ' + A);
}
function ok(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

function run(nodeName, { input = [], named = {}, statics = {} } = {}) {
  const js = nodeByName(nodeName).parameters.jsCode;
  const items = input.map((j) => ({ json: j }));
  const ctx = {
    $input: { all: () => items, first: () => items[0] },
    $json: items.length ? items[0].json : {},
    $: (n) => {
      if (!(n in named)) throw new Error('node ' + n + ' not available to ' + nodeName);
      const its = named[n].map((j) => ({ json: j }));
      return {
        all: () => its, first: () => its[0],
        get item() { throw new Error("Paired item unavailable for '" + n + "'"); },
      };
    },
    $getWorkflowStaticData: () => statics,
    Date, JSON, Number, String, Array, Object, Boolean, Math, isNaN, parseInt, parseFloat, Error,
    RegExp,
  };
  return (vm.runInNewContext('(function(){' + js + '})()', ctx, { timeout: 5000 }) || [])
    .map((i) => i.json);
}

// ---------------------------------------------------------------- fixture helpers
function trig(wfId, wfName, node, message, execId) {
  return { workflow: { id: wfId, name: wfName },
           execution: { id: execId || 9999, lastNodeExecuted: node,
                        error: { message, node: { name: node } },
                        url: 'https://janea-systems-2025.app.n8n.cloud/workflow/' + wfId
                             + '/executions/' + (execId || 9999) } };
}
function exec(runData) { return { data: { resultData: { runData } } }; }
function normalize(event, campaign, email) {
  return { Normalize: [{ data: { main: [[{ json: {
    event, campaign_name: campaign, lead: { email } } }]] } }] };
}
function ran(name) { return { [name]: [{ data: { main: [[{ json: {} }]] } }] }; }

// v1's message, for the before/after gallery
function v1Text(f) {
  return ':rotating_light: ' + f.t.workflow.name + ' — execution failed\n'
    + 'Failed node: ' + f.t.execution.lastNodeExecuted + '\n'
    + 'Error: ' + f.t.execution.error.message + '\n'
    + 'Execution: ' + f.t.execution.url;
}

function report(f, statics) {
  const built = run('Build Report', {
    input: [f.fetched || {}],
    named: { CONFIG: [CFG], 'Error Trigger': [f.t] },
  })[0];
  const burst = run('Burst Gate', {
    input: [built], named: { CONFIG: [CFG] }, statics: statics || {},
  })[0];
  const named = { CONFIG: [CFG], 'Burst Gate': [burst] };
  if (f.llm) named['LLM Assist'] = [f.llm];
  const composed = run('Compose', { input: [burst], named })[0];
  return { built, burst, composed };
}

// ---------------------------------------------------------------- the real failures
const FIXTURES = {
  leadList400: {
    name: 'Lead List 400 lavina (B23) - WF-2 SENT, no Pipedrive person',
    t: trig('jp7rum9Z0YDJkQWv', 'WF-2 Smartlead Receiver', 'Lead List',
            'Bad request - please check your parameters (provided dataset is not valid)', 11767),
    fetched: exec(Object.assign(
      normalize('SENT', '[Events Visiting] AI4 2026 - Mario - Catch-alls', 'pii-77eb2775@example.invalid'),
      ran('Person Patch'))),
  },
  oomWf1: {
    name: 'OOM pair #1 - WF-1 HeyReach, worker died',
    t: trig('2jdjKM2NJr473GdA', 'WF-1 HeyReach Receiver', 'M6 IF Email Present',
            'Workflow did not finish, possible out-of-memory issue', 12216),
    fetched: exec({}),
  },
  oomWf2s: {
    name: 'OOM pair #2 - WF-2S reconciler, same worker event',
    t: trig('6Y92ryBwYoy6z0Jx', 'WF-2S Smartlead SENT Reconciler', 'Find New Sends',
            'Workflow did not finish, possible out-of-memory issue', 12215),
    fetched: exec({}),
  },
  pairedItem: {
    name: 'WF-2H paired-item - the defect that failed every run of its life',
    t: trig('nK3yIOqRcBearV8s', 'WF-2H Health & Digest', 'PD Leads',
            "Paired item data for item from node 'Pick Active' is unavailable. "
            + "Ensure 'Pick Active' is providing the required output.", 12103),
    fetched: exec({}),
  },
  pipedrive504: {
    name: 'Pipedrive 504 - transient upstream',
    t: trig('jp7rum9Z0YDJkQWv', 'WF-2 Smartlead Receiver', 'Reply Activity',
            'The service was not able to process your request (504 Gateway Timeout)', 12301),
    fetched: exec(Object.assign(
      normalize('REPLIED', '[Events Visiting] AI4 2026 - Rune - Valids', 'pii-b9ee8bb5@example.invalid'),
      ran('SL Category'), ran('SL Forward Email'))),
  },
  novel: {
    name: 'UNKNOWN novel error - nothing in the dictionary matches',
    t: trig('jp7rum9Z0YDJkQWv', 'WF-2 Smartlead Receiver', 'Classify Parse',
            'Unexpected token < in JSON at position 0 while reading model output', 12302),
    fetched: exec(normalize('REPLIED', '[Lead Nurturing] Q3', 'someone@example.com')),
    llm: { choices: [{ message: { content: JSON.stringify({
      hypothesis: 'The model endpoint returned an HTML error page instead of JSON, which usually '
                  + 'means a gateway or auth failure upstream of the API itself.',
      next_check: 'Open the LLM Classify node output and look at the first 200 characters of the '
                  + 'raw response body.' }) } }] },
  },
};

// ---------------------------------------------------------------- WHAT / IMPACT / ACTION
t('E1 a known class produces all three lines with a documented action', () => {
  const r = report(FIXTURES.leadList400);
  eq(r.built.__class, 'bad_request', 'class not matched');
  ok(r.composed.__text.includes('*WHAT*'), 'WHAT missing');
  ok(r.composed.__text.includes('*IMPACT*'), 'IMPACT missing');
  ok(r.composed.__text.includes('*ACTION*'), 'ACTION missing');
  ok(!r.composed.__text.includes('hypothesis'), 'a known class must not need the LLM');
});
t('E2 WHAT names the event, campaign and lead when runData has them', () => {
  const w = report(FIXTURES.leadList400).built.__what;
  ok(w.includes('SENT'), 'event type missing');
  ok(w.includes('Mario - Catch-alls'), 'campaign missing');
  ok(w.includes('pii-77eb2775@example.invalid'), 'lead missing');
});
t('E3 IMPACT lists writes that really completed, read from runData', () => {
  const i = report(FIXTURES.leadList400).built.__impact;
  ok(i.includes('Person Patch'), 'a completed write was not reported');
  ok(i.includes('COMPLETED'), 'wording must make it clear these happened');
});
t('E4 IMPACT states the retry verdict per source - LOST for Smartlead replies', () => {
  ok(report(FIXTURES.leadList400).built.__impact.includes('LOST'),
     'WF-2 answers 200 first, so the event is gone - that must be said');
  ok(report(FIXTURES.oomWf1).built.__impact.includes('DELAYED'),
     'HeyReach retries 5x/24h');
  ok(report(FIXTURES.oomWf2s).built.__impact.includes('SAFE'),
     'WF-2S marks seen only after success, so the next cycle re-claims it');
});
t('E5 no writes completed is stated positively, not left blank', () => {
  ok(report(FIXTURES.oomWf1).built.__impact.includes('no write completed')
     || report(FIXTURES.oomWf1).built.__impact.includes('UNKNOWN'),
     'silence about writes is what made v1 useless');
});
t('E6 an unreadable execution says UNKNOWN rather than inventing an impact', () => {
  const f = { ...FIXTURES.leadList400, fetched: { error: 'not found' } };
  ok(report(f).built.__impact.includes('UNKNOWN'), 'must not claim "no writes" when it cannot see');
});
t('E7 the paired-item class routes to the guard, not to guesswork', () => {
  const r = report(FIXTURES.pairedItem);
  eq(r.built.__class, 'paired_item');
  ok(r.built.__action.includes('wf_item_guard'), 'action must name the tool that finds it');
});
t('E8 OOM is called an instance event, not a workflow defect', () => {
  const r = report(FIXTURES.oomWf1);
  eq(r.built.__class, 'oom');
  ok(/instance-level/i.test(r.built.__action), 'blaming the workflow sends triage the wrong way');
});
t('E9 a transient 5xx says no action', () => {
  const r = report(FIXTURES.pipedrive504);
  eq(r.built.__class, 'upstream_5xx');
  ok(/no action/i.test(r.built.__action), 'transient noise must not create work');
  ok(r.built.__impact.includes('SL Category'), 'writes before the failure still matter');
});

// ---------------------------------------------------------------- LLM assist
t('E10 an unknown class asks the LLM and marks the answer as a hypothesis', () => {
  const r = report(FIXTURES.novel);
  eq(r.built.__class, 'unknown');
  ok(r.composed.__text.includes('hypothesis, not fact'), 'an LLM guess must never read as fact');
  ok(r.composed.__text.includes('HTML error page'), 'hypothesis text missing');
  ok(r.composed.__text.includes('First check'), 'next check missing');
});
t('E11 GUARDRAIL: LLM down still produces a usable report', () => {
  const f = { ...FIXTURES.novel, llm: { error: { message: 'connect ETIMEDOUT' } } };
  const r = report(f);
  ok(r.composed.__text.includes('*WHAT*') && r.composed.__text.includes('*IMPACT*'),
     'error reporting must never depend on the LLM being up');
  ok(r.composed.__text.includes('add it to CONFIG.known_classes'),
     'it should still tell the reader what to do');
});
t('E12 malformed LLM JSON degrades instead of throwing', () => {
  const f = { ...FIXTURES.novel, llm: { choices: [{ message: { content: 'not json at all' } }] } };
  ok(report(f).composed.__text.includes('*ACTION*'), 'a bad parse must not lose the report');
});
t('E13 the LLM never sees secrets or full payloads', () => {
  const body = run('LLM Body', {
    input: [report(FIXTURES.novel).burst], named: { CONFIG: [CFG] },
  })[0].__body;
  // scope the check to what we actually SEND as data. Checking the whole body matched our own
  // parameter name `max_completion_tokens` on /token/i - a false positive in the test, not a leak.
  const sent = body.messages.map((m) => m.content).join(' | ');
  ok(!/api_key|Bearer |sk-proj-|secret[ _-]?key|password/i.test(sent),
     'credential-shaped text reached the LLM');
  ok(sent.includes('Classify Parse'), 'node name should be included - it is the useful part');
  ok(!/reply_body|__history|email_body|"body"/i.test(sent), 'a full payload leaked');
  ok(sent.length < 1500, 'context should be a summary, not a dump');
});

// ---------------------------------------------------------------- burst
t('E14 the Lead List lavina posts once, not N times', () => {
  const sd = {};
  const first = report(FIXTURES.leadList400, sd);
  eq(first.burst.__suppress, false, 'the first failure must always be reported');
  for (let i = 0; i < 7; i++) {
    eq(report(FIXTURES.leadList400, sd).burst.__suppress, true, 'repeat ' + i + ' not suppressed');
  }
  eq(sd.__burst[first.burst.__burst_key].suppressed, 7, 'suppressed count not tracked');
});
t('E15 a different node in the same workflow is NOT suppressed', () => {
  const sd = {};
  report(FIXTURES.leadList400, sd);
  eq(report(FIXTURES.pipedrive504, sd).burst.__suppress, false,
     'burst keys must be per (workflow, node) - a real second problem must still surface');
});
t('E16 the next window reports how many were swallowed', () => {
  const sd = {};
  report(FIXTURES.leadList400, sd);
  report(FIXTURES.leadList400, sd);
  report(FIXTURES.leadList400, sd);
  // age the window out
  sd.__burst[Object.keys(sd.__burst)[0]].first = Date.now() - 999 * 60000;
  const r = report(FIXTURES.leadList400, sd);
  eq(r.burst.__suppress, false, 'a new window must report again');
  eq(r.burst.__carried, 2, 'swallowed count lost');
  ok(r.composed.__text.includes('+2 more suppressed'), 'the tail must appear in the message');
});
t('E17 the burst store is pruned so it cannot grow forever', () => {
  const sd = { __burst: { 'old|node': { first: Date.now() - 90000000, count: 1, suppressed: 0 } } };
  report(FIXTURES.leadList400, sd);
  ok(!('old|node' in sd.__burst), 'stale keys must be pruned');
});

// ---------------------------------------------------------------- structural
t('E18 WF-ERR does not chain to itself', () => {
  ok(!WF.settings.errorWorkflow, 'an error handler that triggers itself is a loop');
});
t('E19 the LLM node cannot break reporting', () => {
  eq(nodeByName('LLM Assist').onError, 'continueRegularOutput');
  eq(nodeByName('Fetch Execution').onError, 'continueRegularOutput');
});
t('E20 both IF branches terminate', () => {
  eq(WF.connections['IF Suppressed'].main[0].map((c) => c.node), ['NoOp Suppressed']);
  eq(WF.connections['IF Suppressed'].main[1].map((c) => c.node), ['IF Unknown Class']);
  eq(WF.connections['IF Unknown Class'].main[0].map((c) => c.node), ['LLM Body']);
  eq(WF.connections['IF Unknown Class'].main[1].map((c) => c.node), ['Compose']);
});
t('E21 no key material in the workflow JSON', () => {
  const blob = JSON.stringify(WF);
  ok(!/sk-proj-|api_key=[A-Za-z0-9]{8}/.test(blob), 'credential material embedded');
});
t('E22 every documented class carries both a what and an action', () => {
  for (const c of CFG.known_classes) {
    ok(c.what && c.action, `${c.id}: incomplete class`);
  }
});

if (SHOW) {
  for (const key of Object.keys(FIXTURES)) {
    const f = FIXTURES[key];
    const r = report(f, {});
    console.log('\n' + '='.repeat(94));
    console.log(f.name);
    console.log('='.repeat(94));
    console.log('--- BEFORE (v1) ---');
    console.log(v1Text(f));
    console.log('\n--- AFTER (v2) ---');
    console.log(r.composed.__text);
  }
  console.log('');
}

console.log('WF-ERR statics: ' + pass + ' passed, ' + fails.length + ' failed');
if (fails.length) { fails.forEach((f) => console.log('  FAIL ' + f)); process.exit(1); }
