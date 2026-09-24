// W1.0.15 static contract tests - ONE reply alert per lead, ever.
//
// The premise we were given (label-read race + fail-open) was WRONG, and the tests encode what the
// executions actually showed: `M7 Critical Slack` sat INLINE between M7 Build and M7 IF Patch and
// posted on every `every_message_reply_received`. HeyReach emits one per message, so Person-ec2fedcf's
// three messages on 2026-08-02 (execs 12894 / 12896 / 12898) produced three identical alerts with no
// race involved at all.
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const WF = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'WF-1 HeyReach Receiver - W1.0.15 patched.json'), 'utf8'));
const N = new Map(WF.nodes.map((n) => [n.name, n]));
const C = WF.connections;
const getNode = (n) => N.get(n) || (() => { throw new Error('no node ' + n); })();
const CFG = JSON.parse(getNode('CONFIG').parameters.jsonOutput);
const RESPONDED = CFG.labels.responded;

let pass = 0; const fails = [];
function t(id, fn) { try { fn(); pass++; } catch (e) { fails.push(id + ': ' + e.message); } }
function eq(a, b, m) {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error((m || '') + ' expected ' + B + ' got ' + A);
}
function ok(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

// Runs the gate with a REAL staticData object so the registry persists across calls, exactly as it
// does across executions of the live workflow.
function gate({ build = {}, norm = {}, leadGet = null, sd = {} } = {}) {
  const js = getNode('M7 Alert Gate').parameters.jsCode;
  const outputs = {
    CONFIG: CFG,
    Normalize: norm,
    'M7 Lead Get': leadGet === null ? undefined : leadGet,
  };
  const ctx = {
    $json: build,
    $: (name) => {
      if (!(name in outputs) || outputs[name] === undefined) {
        throw new Error('node ' + name + ' unavailable');
      }
      return { item: { json: outputs[name] }, first: () => ({ json: outputs[name] }) };
    },
    $getWorkflowStaticData: () => sd,
    Date, JSON, Number, String, Array, Object, Boolean, Math, isNaN, parseInt, parseFloat, Error,
  };
  return vm.runInNewContext('(function(){' + js + '})()', ctx, { timeout: 5000 })[0].json;
}

// Rahul's real shape: campaign 513000, a lead that exists, no responded label on the first reply
const CAMP = { id: 513000, name: '[Events Visiting] [Ai4 2026] - Rune - LinkedIn' };
const norm = (over = {}) => ({
  campaign: CAMP,
  lead: { full_name: 'Person-ec2fedcf', member_id: 'ACoAAA-rahul', li_url: 'https://li/in/rahulp' },
  ...over,
});
const leadPage = (labels) => ({ data: [{
  id: 'a8215a00-8cc5-11f1-ad9f-cfed4f7204bd', is_archived: false,
  [CFG.fields.lead_campaign]: CAMP.name, label_ids: labels }] });
const build = (over = {}) => ({ lead_id: 'a8215a00-8cc5-11f1-ad9f-cfed4f7204bd',
                                person_id: 84949, alert_text: 'reply!', ...over });

// ---------------------------------------------------------------- burst fixture
t('W15-1 BURST: three events for one lead in a minute -> exactly ONE alert', () => {
  const sd = {};
  const outs = [1, 2, 3].map(() => gate({ build: build(), norm: norm(),
                                          leadGet: leadPage([CFG.labels.cold]), sd }));
  eq(outs.map((o) => o.__should_alert), [true, false, false],
     'this is the Rahul defect: 3 messages produced 3 identical alerts');
  eq(outs[0].__alert_reason, 'first_alert');
  eq(outs[1].__alert_reason, 'already_alerted');
});
t('W15-2 the burst is deduped even when the label never updates between events', () => {
  // labels lag behind a burst - the registry must not depend on them
  const sd = {};
  const a = gate({ build: build(), norm: norm(), leadGet: leadPage([CFG.labels.cold]), sd });
  const b = gate({ build: build(), norm: norm(), leadGet: leadPage([CFG.labels.cold]), sd });
  eq([a.__should_alert, b.__should_alert], [true, false], 'registry must be the primary gate');
});

// ---------------------------------------------------------------- late-repeat fixture
t('W15-3 LATE REPEAT: an 18-minute-later message -> ZERO alerts', () => {
  const sd = { __alerted_v1: { 'La8215a00-8cc5-11f1-ad9f-cfed4f7204bd|513000':
                               new Date(Date.now() - 18 * 60000).toISOString() } };
  const o = gate({ build: build(), norm: norm(), leadGet: leadPage([RESPONDED]), sd });
  eq(o.__should_alert, false, 'exec 12898 - a race could never explain this one');
  eq(o.__alert_reason, 'already_alerted');
});
t('W15-4 a repeat is suppressed by the label even when the registry was wiped', () => {
  // n8n staticData does not survive everything; the persisted label is the backstop
  const o = gate({ build: build(), norm: norm(), leadGet: leadPage([RESPONDED]), sd: {} });
  eq(o.__should_alert, false, 'secondary gate did not fire');
  eq(o.__alert_reason, 'responded_label');
});

// ---------------------------------------------------------------- genuinely first
t('W15-5 GENUINELY FIRST: no registry entry, no responded label -> ONE alert', () => {
  const sd = {};
  const o = gate({ build: build(), norm: norm(), leadGet: leadPage([CFG.labels.cold]), sd });
  eq(o.__should_alert, true, 'a first reply must always alert');
  eq(o.__alert_reason, 'first_alert');
  ok(sd.__alerted_v1['La8215a00-8cc5-11f1-ad9f-cfed4f7204bd|513000'], 'not registered');
});

// ---------------------------------------------------------------- Rahul no-lead-thread shape
t('W15-6 NO-LEAD shape: three events with no lead resolved -> still exactly ONE alert', () => {
  const sd = {};
  const outs = [1, 2, 3].map(() => gate({
    build: build({ lead_id: null, person_id: 84949 }), norm: norm(), leadGet: { data: [] }, sd }));
  eq(outs.map((o) => o.__should_alert), [true, false, false],
     'without a lead the label gate cannot help - the registry must carry it');
  eq(outs[0].__alert_key, 'P84949|513000', 'falls back to the person id');
});
t('W15-7 no lead AND no person -> falls back to the LinkedIn identity, still deduped', () => {
  const sd = {};
  const a = gate({ build: build({ lead_id: null, person_id: null }), norm: norm(),
                   leadGet: { data: [] }, sd });
  const b = gate({ build: build({ lead_id: null, person_id: null }), norm: norm(),
                   leadGet: { data: [] }, sd });
  eq(a.__alert_key, 'MACoAAA-rahul|513000', 'member id not used');
  eq([a.__should_alert, b.__should_alert], [true, false]);
});

// ---------------------------------------------------------------- fail direction
t('W15-8 label unreadable + registry silent -> alert ONCE, then never again', () => {
  const sd = {};
  const a = gate({ build: build(), norm: norm(), leadGet: null, sd });   // M7 Lead Get unavailable
  eq(a.__should_alert, true, 'a first reply must never be lost to a failed read');
  eq(a.__alert_reason, 'first_alert_label_unreadable');
  const b = gate({ build: build(), norm: norm(), leadGet: null, sd });
  eq(b.__should_alert, false, 'the fail-open must be once, not every time');
  eq(b.__alert_reason, 'already_alerted');
});
t('W15-9 a registry hit beats an unreadable label - repeats never re-alert', () => {
  const sd = { __alerted_v1: { 'La8215a00-8cc5-11f1-ad9f-cfed4f7204bd|513000':
                               new Date().toISOString() } };
  const o = gate({ build: build(), norm: norm(), leadGet: null, sd });
  eq(o.__should_alert, false, 'owner rule: better a missed duplicate than a duplicate');
});
t('W15-10 no identity at all -> alerts, and SAYS it cannot dedupe', () => {
  const o = gate({ build: build({ lead_id: null, person_id: null }),
                   norm: { campaign: CAMP, lead: {} }, leadGet: { data: [] }, sd: {} });
  eq(o.__should_alert, true, 'a first reply must never be lost');
  eq(o.__alert_reason, 'no_identity', 'the only remaining duplicate path must be named');
  eq(o.__alert_key, null);
});

// ---------------------------------------------------------------- keys and hygiene
t('W15-11 the key is per lead AND per campaign - a different campaign still alerts', () => {
  const sd = {};
  gate({ build: build(), norm: norm(), leadGet: leadPage([CFG.labels.cold]), sd });
  const other = gate({ build: build({ lead_id: 'OTHERLEAD' }),
                       norm: norm({ campaign: { id: 512995, name: 'Mario - LinkedIn' } }),
                       leadGet: { data: [] }, sd });
  eq(other.__should_alert, true, 'a second campaign is a legitimately separate first reply');
});
t('W15-12 two different people never share a key', () => {
  const sd = {};
  gate({ build: build(), norm: norm(), leadGet: leadPage([CFG.labels.cold]), sd });
  const other = gate({ build: build({ lead_id: 'LEAD-B', person_id: 999 }),
                       norm: norm({ lead: { member_id: 'someone-else' } }),
                       leadGet: { data: [] }, sd });
  eq(other.__should_alert, true, 'a campaign-only key would silence everyone after the first');
});
t('W15-13 the registry is pruned at 90 days', () => {
  const sd = { __alerted_v1: {
    ancient: new Date(Date.now() - 120 * 86400000).toISOString(),
    recent: new Date(Date.now() - 3 * 86400000).toISOString() } };
  const o = gate({ build: build(), norm: norm(), leadGet: leadPage([CFG.labels.cold]), sd });
  ok(!('ancient' in sd.__alerted_v1), 'an unbounded registry is a slow leak');
  ok('recent' in sd.__alerted_v1, 'pruned something still relevant');
  ok(o.__alert_pruned >= 1, 'pruning must be reported');
});

// ---------------------------------------------------------------- graph invariants
t('W15-14 the alert is GATED - M7 Build no longer reaches Slack directly', () => {
  eq(C['M7 Build'].main[0].map((x) => x.node), ['M7 Alert Gate']);
  eq(C['M7 Alert Gate'].main[0].map((x) => x.node), ['M7 IF Should Alert']);
  eq(C['M7 IF Should Alert'].main[0].map((x) => x.node), ['M7 Critical Slack']);
  eq(C['M7 IF Should Alert'].main[1].map((x) => x.node), ['M7 Alert Suppressed']);
});
t('W15-15 BOTH branches continue to the CRM work (B20 lesson)', () => {
  eq(C['M7 Critical Slack'].main[0].map((x) => x.node), ['M7 IF Patch']);
  eq(C['M7 Alert Suppressed'].main[0].map((x) => x.node), ['M7 IF Patch'],
     'a suppressed alert must never skip the person/label/activity update');
});
t('W15-16 node count and the W1.0.13.1 surfaces are intact', () => {
  eq(WF.nodes.length, 98);
  ok(getNode('Normalize').parameters.jsCode.includes('W1.0.13.1 two-bracket event-marker parser'),
     'the event parser was disturbed');
  eq(WF.active, false, 'must ship inactive');
});

console.log('W1.0.15 statics: ' + pass + ' passed, ' + fails.length + ' failed');
if (fails.length) { fails.forEach((f) => console.log('  FAIL ' + f)); process.exit(1); }
