// WF-2S static contract tests.
//
// These execute the real node code out of wf2s-built.json - not a copy of it - against fixtures
// taken from the live responses. Every one of the three defects below shipped and reached
// production; two of them (S2, S3) would never have thrown, so only a behavioural test finds them.
//
//   S1  backward .item lookups across the HTTP fan-out  -> crashed cycle 1 (exec 11764)
//   S2  Pick Active read $json from a SPLIT array       -> zero ACTIVE campaigns, silent forever
//   S3  Build SENT Payload returned one item            -> one send replayed per cycle, silently
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const WF = JSON.parse(fs.readFileSync(
  path.join(__dirname, 'wf1-release-evidence', 'wf2s-built.json'), 'utf8'));
const nodeByName = (n) => WF.nodes.find((x) => x.name === n)
  || (() => { throw new Error('no such node: ' + n); })();
const CFG = JSON.parse(nodeByName('CONFIG').parameters.jsonOutput);

let pass = 0; const fails = [];
function t(id, fn) {
  try { fn(); pass++; } catch (e) { fails.push(id + ': ' + e.message); }
}
function eq(a, b, m) {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error((m || '') + ' expected ' + B + ' got ' + A);
}
function ok(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

// Runs a Code node's jsCode with a stubbed n8n runtime. `named` maps node name -> items, which
// is what $('X').all()/.first() read; `input` is what $input.all()/$json read.
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
        all: () => its,
        first: () => its[0],
        // .item is deliberately a landmine: if any node reaches for a paired item, the test
        // fails the same way production did, instead of quietly working on a fixture.
        get item() { throw new Error("Paired item data for item from node '" + n + "' is unavailable"); },
      };
    },
    $getWorkflowStaticData: () => statics,
    Date, JSON, Number, String, Array, Object, Boolean, Math, isNaN, parseInt, parseFloat, Error,
    encodeURIComponent,
  };
  const out = vm.runInNewContext('(function(){' + js + '})()', ctx, { timeout: 5000 });
  return (out || []).map((i) => i.json);
}

// ---------------------------------------------------------------- fixtures (live-shaped)
// /campaigns returns a BARE ARRAY. n8n splits it into one item per element - 116 in exec 11764.
// That is the whole of S2, so the fixture must be split the same way.
const campaignsSplit = [
  { id: 3686193, name: '[Events Visiting] AI4 2026 - Rune - Catch-alls', status: 'ACTIVE' },
  { id: 3686187, name: '[Events Visiting] AI4 2026 - Rune - Valids', status: 'ACTIVE' },
  { id: 3565502, name: 'Old paused thing', status: 'PAUSED' },
  { id: 3738259, name: 'Drafted thing', status: 'DRAFTED' },
  { id: 3600001, name: 'Completed thing', status: 'COMPLETED' },
];
const statRow = (email, sent, sid) => ({
  lead_name: 'X Y', lead_email: email, lead_category: '', sequence_number: 1, stats_id: sid,
  email_campaign_seq_id: 9777758, seq_variant_id: 7047176, email_subject: 'Meeting at AI4?',
  sent_time: sent, open_count: 0, is_unsubscribed: false, is_bounced: false,
});
const NOW = Date.now();
const iso = (msAgo) => new Date(NOW - msAgo).toISOString();

// =============================================================== S2: Pick Active
// allowlist defaults to [] so the parsing tests stay independent of whatever scope the deployed
// CONFIG currently carries - during a live window that value is deliberately non-empty.
function pickActive(input, allowlist, statics, cfgOverrides) {
  const cfg = { ...CFG, campaign_allowlist: allowlist || [], ...(cfgOverrides || {}) };
  return run('Pick Active', { input, named: { CONFIG: [cfg] }, statics: statics || {} });
}
t('S2-1 split array yields every ACTIVE campaign', () => {
  const out = pickActive(campaignsSplit);
  eq(out.map((o) => o.campaign_id), [3686193, 3686187], 'active ids');
});
t('S2-2 the pre-fix read ($json only) would have found nothing', () => {
  // proves the fixture actually discriminates: campaign #1 alone has no .data and is not an array
  const first = campaignsSplit[0];
  ok(!Array.isArray(first) && first.data === undefined,
     'fixture does not reproduce the split-array condition');
});
t('S2-3 campaign names are carried for the payload', () => {
  const out = pickActive(campaignsSplit);
  ok(out[0].campaign_name.includes('Rune'), 'name lost');
});
t('S2-4 non-ACTIVE statuses are excluded', () => {
  const out = pickActive(campaignsSplit);
  ok(!out.some((o) => [3565502, 3738259, 3600001].includes(o.campaign_id)), 'non-active leaked');
});
t('S2-5 wrapped {data:[...]} shape also parses', () => {
  const out = pickActive([{ data: campaignsSplit }]);
  eq(out.map((o) => o.campaign_id), [3686193, 3686187], 'wrapped shape');
});
t('S2-6 an unparseable poll THROWS rather than reporting idle', () => {
  let threw = false;
  try { pickActive([]); } catch (e) { threw = /nothing parseable/.test(e.message); }
  ok(threw, 'empty poll silently reported idle - this is the S2 failure mode');
});
t('S2-7 zero ACTIVE among real campaigns is idle, not an error', () => {
  const out = pickActive([campaignsSplit[2]]);
  eq(out, [{ __none: true, __scanned: 1, __allowlist: 0, __campaign_overflow: 0 }],
     'idle shape');
});

// ---- AL: the live-window scope. Wide open in live mode the reconciler would replay a 180-minute
// backlog as fresh Pipedrive creations, duplicating what Make already did hours ago.
t('AL1 an empty allowlist means every ACTIVE campaign (normal operation)', () => {
  eq(pickActive(campaignsSplit, []).map((o) => o.campaign_id), [3686193, 3686187], 'unscoped');
});
t('AL2 a populated allowlist scopes the reconciler to exactly those campaigns', () => {
  const out = pickActive(campaignsSplit, [3686187]);
  eq(out.map((o) => o.campaign_id), [3686187], 'scope not applied');
});
t('AL3 the allowlist cannot resurrect a long-dormant campaign', () => {
  const out = pickActive(campaignsSplit, [3565502]);
  eq(out[0].__none, true, 'a stale PAUSED campaign was polled because it was allowlisted');
});

t('AL4 ids compare as strings, so a numeric config value still matches', () => {
  eq(pickActive(campaignsSplit, ['3686187']).map((o) => o.campaign_id), [3686187], 'string id');
});
t('AL5 being scoped is REPORTED, so a narrowed reconciler cannot read as a full one', () => {
  eq(pickActive(campaignsSplit, [3686187])[0].__allowlist, 1, 'scope not surfaced');
  const sum = run('Summary', {
    named: { CONFIG: [{ ...CFG, campaign_allowlist: [3686187] }], 'Build SENT Payload': [] },
    input: [], statics: {} });
  eq(sum[0].__allowlist, 1, 'the ops report would not mention the scope');
});

// ---- S5 v2: a campaign flips to COMPLETED the moment its last lead is sent, so an ACTIVE-only
// poll loses the FINAL batch of every campaign - and SENT arrives only through this workflow.
// v1 keyed on `updated_at within lookback`; Smartlead bumps that field in BULK (all four ACTIVE
// campaigns share the identical timestamp), so it dragged in 23 long-dead campaigns, 8219 stale
// rows, and is the prime suspect for the worker OOM. v2 keys on OUR OWN state instead.
const doneNow = { id: 3738616, name: 'WF2 Live Test', status: 'COMPLETED',
                  updated_at: iso(60000) };
t('S5-1 a campaign that was ACTIVE last cycle is still polled after it completes', () => {
  const sd = { __prev_active_ids: ['3738616'] };
  const ids = pickActive([...campaignsSplit, doneNow], null, sd).map((o) => o.campaign_id);
  ok(ids.includes(3738616), 'the tail of every campaign would be lost');
});
t('S5-2 a campaign we never saw ACTIVE is NOT polled, however recent its updated_at', () => {
  // this is the exact v1 failure: a bulk-bumped timestamp must no longer widen the poll
  const ids = pickActive([...campaignsSplit, doneNow], null, {}).map((o) => o.campaign_id);
  ok(!ids.includes(3738616),
     'a bulk-bumped updated_at still widens the poll - that is the 23-campaign blowup');
});
t('S5-3 the currently-ACTIVE ids are recorded for the next cycle', () => {
  const sd = {};
  pickActive(campaignsSplit, null, sd);
  eq(sd.__prev_active_ids.sort(), ['3686187', '3686193'], 'next cycle cannot catch any tail');
});
t('S5-4 recency never overrides the allowlist scope', () => {
  const sd = { __prev_active_ids: ['3738616'] };
  const out = pickActive([...campaignsSplit, doneNow], [3686187], sd);
  eq(out.map((o) => o.campaign_id), [3686187], 'a completed campaign escaped the scope');
});
t('S5-5 the poll reports the real campaign status, never a hardcoded ACTIVE', () => {
  const sd = { __prev_active_ids: ['3738616'] };
  const row = pickActive([...campaignsSplit, doneNow], null, sd)
    .find((o) => o.campaign_id === 3738616);
  eq(row.campaign_status, 'COMPLETED', 'status is asserted rather than observed');
});

// ---- S5 v3: the T2 shape - a campaign that starts AND completes between two polls. v2 could not
// see it (never in prevActive), so its SENT was never reconciled. created_at is immutable, unlike the
// bulk-bumped updated_at that v1 wrongly trusted.
t('S5-6 a campaign born since the last poll is polled even if already COMPLETED', () => {
  const t2 = { id: 3745473, name: 'WF2 Matrix T2', status: 'COMPLETED',
               created_at: iso(6 * 60000), updated_at: iso(60000) };
  const ids = pickActive([...campaignsSplit, t2], null, {}).map((o) => o.campaign_id);
  ok(ids.includes(3745473), 'the T2 hole: start and finish between two cycles = SENT never observed');
});
t('S5-7 an OLD campaign is not resurrected by a bulk-bumped updated_at', () => {
  const old = { id: 999003, name: 'Ag Tech', status: 'COMPLETED',
                created_at: iso(90 * 86400000), updated_at: iso(60000) };
  const ids = pickActive([...campaignsSplit, old], null, {}).map((o) => o.campaign_id);
  ok(!ids.includes(999003),
     'this is v1s 23-campaign blowup - updated_at must never widen the poll');
});
t('S5-8 an unreadable created_at excludes rather than includes', () => {
  for (const cr of [undefined, '', 'nope', null]) {
    const c = { id: 999004, name: 'X', status: 'PAUSED', created_at: cr };
    ok(!pickActive([...campaignsSplit, c], null, {}).map((o) => o.campaign_id).includes(999004),
       'an unreadable timestamp must not widen the poll: ' + String(cr));
  }
});
t('S5-9 created_at admission still respects the allowlist', () => {
  const t2 = { id: 3745473, name: 'T2', status: 'COMPLETED', created_at: iso(60000) };
  const out = pickActive([...campaignsSplit, t2], [3686187], {});
  eq(out.map((o) => o.campaign_id), [3686187], 'a newborn campaign escaped the scope');
});

// ---- CAP: OOM insurance. A cap cannot make a wrong predicate right, but it bounds the damage.
t('CAP1 the cycle is capped and the overflow is REPORTED, not silent', () => {
  const many = [];
  for (let i = 0; i < 20; i++) {
    many.push({ id: 900000 + i, name: 'c' + i, status: 'ACTIVE' });
  }
  const out = pickActive(many, null, {}, { max_campaigns_per_cycle: 5 });
  eq(out.length, 5, 'cap not applied');
  eq(out[0].__campaign_overflow, 15, 'a silent truncation reads as "all campaigns polled"');
});
t('CAP2 ACTIVE campaigns are kept ahead of finished tails when the cap bites', () => {
  const tails = [];
  for (let i = 0; i < 10; i++) {
    tails.push({ id: 800000 + i, name: 'tail' + i, status: 'COMPLETED' });
  }
  const sd = { __prev_active_ids: tails.map((c) => String(c.id)) };
  const out = pickActive([...tails, ...campaignsSplit], null, sd,
                         { max_campaigns_per_cycle: 3 });
  // the invariant is not "everything returned is ACTIVE" - with a cap of 3 and only 2 ACTIVE
  // campaigns the third slot correctly goes to a tail. It is "no ACTIVE campaign is dropped
  // while a finished one is kept", which is what actually costs us live sends.
  const returned = out.map((o) => o.campaign_id);
  eq(returned.filter((id) => [3686193, 3686187].includes(id)).sort(), [3686187, 3686193],
     'a live campaign was dropped in favour of a finished one');
  eq(out.length, 3, 'cap not applied');
});
t('CAP3 prev-active is recorded BEFORE the cap, so capping cannot lose a tail', () => {
  const many = [];
  for (let i = 0; i < 20; i++) {
    many.push({ id: 700000 + i, name: 'c' + i, status: 'ACTIVE' });
  }
  const sd = {};
  pickActive(many, null, sd, { max_campaigns_per_cycle: 2 });
  eq(sd.__prev_active_ids.length, 20,
     'only the capped subset was remembered - the rest would never have their tail collected');
});

// ---- WM: WRITE_MODE expiry. A live window is a promise to revert; on 2026-07-31 that promise was
// kept for 72 hours instead of minutes, and low-confidence prospect replies were forwarded to a
// personal Gmail the whole time. This is the control that a promise was not.
function modeEval(mode, sd, cfgOver) {
  const wf = mode === undefined ? {} : { nodes: [{ name: 'CONFIG', parameters: {
    jsonOutput: JSON.stringify({ WRITE_MODE: mode }) } }] };
  return run('WF-2 Mode Eval', {
    input: [wf], named: { CONFIG: [{ ...CFG, ...(cfgOver || {}) }] }, statics: sd || {} })[0];
}
t('WM1 shadow mode is quiet and leaves no clock running', () => {
  const sd = {};
  const o = modeEval('shadow', sd);
  eq(o.__mode_overdue, false, 'false alarm in shadow');
  eq(sd.__wf2_live_since, undefined, 'a shadow cycle must not start the clock');
});
t('WM2 the clock starts on the FIRST cycle that observes live', () => {
  const sd = {};
  const o = modeEval('live', sd);
  eq(o.__mode_overdue, false, '0h is not overdue');
  ok(sd.__wf2_live_since, 'clock not started');
});
t('WM3 a live window past the limit is REPORTED', () => {
  const sd = { __wf2_live_since: iso(5 * 3600000) };
  const o = modeEval('live', sd);
  eq(o.__mode_overdue, true, '72 hours went unnoticed once - never again');
  ok(o.__mode_hours >= 4.9, 'age mis-computed');
});
t('WM4 returning to shadow resets the clock', () => {
  const sd = { __wf2_live_since: iso(9 * 3600000) };
  modeEval('shadow', sd);
  eq(sd.__wf2_live_since, undefined, 'a stale clock would alarm forever after a clean revert');
});
t('WM5 an unreadable mode is NOT treated as fine', () => {
  const o = modeEval(undefined, {});
  eq(o.__mode, null);
  eq(o.__mode_overdue, true, 'silence when we cannot tell is how the 72h window survived');
});
t('WM6 the limit comes from CONFIG', () => {
  const sd = { __wf2_live_since: iso(3 * 3600000) };
  eq(modeEval('live', sd, { write_mode_max_hours: 8 }).__mode_overdue, false, 'limit ignored');
  eq(modeEval('live', { __wf2_live_since: iso(3 * 3600000) },
             { write_mode_max_hours: 1 }).__mode_overdue, true, 'limit ignored');
});
t('WM7 it runs on EVERY cycle, hanging off CONFIG rather than the send chain', () => {
  const targets = (WF.connections['CONFIG'].main[0] || []).map((c) => c.node);
  ok(targets.includes('WF-2 Mode Read'), 'an idle cycle must still check');
});
t('WM8 both branches terminate, and the alarm says what is at risk', () => {
  eq(WF.connections['IF Mode Overdue'].main[0].map((c) => c.node), ['Ops Warn Mode Overdue']);
  eq(WF.connections['IF Mode Overdue'].main[1].map((c) => c.node), ['NoOp Mode OK']);
  const txt = nodeByName('Ops Warn Mode Overdue').parameters.text;
  ok(/prospect replies/.test(txt), 'the alarm must say what is actually at stake');
  ok(/REVERT|Revert/.test(txt), 'and what to do');
});

// ---- WD: the guard gets a guard. WF-2H runs daily and cannot observe its own failure; it errored
// on every run of its entire life and only a manual sweep noticed.
function watch(payload) {
  return run('WF-2H Watch Eval', { input: [payload], named: { CONFIG: [CFG] } })[0];
}
t('WD1 no successful run on record counts as STALE, not as unknown', () => {
  const o = watch({ data: [] });
  eq(o.__wf2h_stale, true, 'silence must be the alarm, not the absence of one');
  eq(o.__wf2h_hours, null);
});
t('WD2 a recent success is fresh', () => {
  const o = watch({ data: [{ stoppedAt: iso(2 * 3600000), status: 'success' }] });
  eq(o.__wf2h_stale, false, 'false alarm');
  ok(o.__wf2h_hours >= 1.9 && o.__wf2h_hours <= 2.1, 'age mis-computed');
});
t('WD3 a success older than the threshold is stale', () => {
  const o = watch({ data: [{ stoppedAt: iso((CFG.wf2h_stale_hours + 5) * 3600000) }] });
  eq(o.__wf2h_stale, true, 'a dead digest went unnoticed');
});
t('WD4 the watchdog runs on EVERY cycle, not only on cycles that replay something', () => {
  // it hangs off CONFIG, not off the send-processing chain, so idle cycles still check
  const targets = (WF.connections['CONFIG'].main[0] || []).map((c) => c.node);
  ok(targets.includes('WF-2H Watch'),
     'a watchdog that only speaks when other work happens is not a watchdog');
  ok(targets.includes('SL Campaigns'), 'the poll chain must still run');
});
t('WD5 both watchdog branches terminate somewhere', () => {
  eq(WF.connections['IF WF-2H Stale'].main[0].map((c) => c.node), ['Ops Warn WF-2H Stale']);
  eq(WF.connections['IF WF-2H Stale'].main[1].map((c) => c.node), ['NoOp WF-2H OK']);
});
t('WD6 the alert says why it matters, not just that it fired', () => {
  const txt = nodeByName('Ops Warn WF-2H Stale').parameters.text;
  ok(txt.includes('WF-2H'), 'names the workflow');
  ok(/not armed|gone quiet/.test(txt),
     'an alert that does not say what is now unprotected gets ignored');
});
t('WD7 the watchdog reads the n8n API with a credential, never an inline key', () => {
  const n = nodeByName('WF-2H Watch');
  eq(n.parameters.authentication, 'genericCredentialType');
  ok(n.credentials && n.credentials.httpHeaderAuth, 'no credential bound');
  ok(!JSON.stringify(n.parameters).includes('n8n_api_key'), 'key material in the workflow');
});

// =============================================================== S1/attribution: Carry Campaign
t('CC-1 campaign attribution is re-attached positionally', () => {
  const camps = [{ campaign_id: 11, campaign_name: 'A' }, { campaign_id: 22, campaign_name: 'B' }];
  const out = run('Carry Campaign', {
    named: { 'Pick Active': camps },
    input: [{ data: [statRow('pii-22fdb3ff@example.invalid', iso(60000), 's1')] },
            { data: [statRow('pii-7ea89e72@example.invalid', iso(60000), 's2')] }],
  });
  eq(out.map((o) => o.__campaign_id), [11, 22], 'attribution');
});
t('CC-2 a length mismatch HARD FAILS instead of shifting the zip', () => {
  let threw = false;
  try {
    run('Carry Campaign', {
      named: { 'Pick Active': [{ campaign_id: 11 }, { campaign_id: 22 }] },
      input: [{ data: [] }],
    });
  } catch (e) { threw = /alignment broken/.test(e.message); }
  ok(threw, 'mis-attribution would have been silent: campaign_id is half of WF-2 dedupe');
});
t('CC-3 the statistics body survives alongside the attribution', () => {
  const out = run('Carry Campaign', {
    named: { 'Pick Active': [{ campaign_id: 11, campaign_name: 'A' }] },
    input: [{ data: [statRow('pii-22fdb3ff@example.invalid', iso(60000), 's1')], total_stats: 1 }],
  });
  eq(out[0].data.length, 1, 'rows dropped');
  eq(out[0].total_stats, 1, 'envelope dropped');
});

// =============================================================== Find New Sends
function findNew(rows, statics) {
  return run('Find New Sends', {
    named: { CONFIG: [CFG] },
    input: [{ __campaign_id: 11, __campaign_name: 'A', data: rows }],
    statics: statics || {},
  });
}
t('FN-1 fresh sends are emitted with the campaign attached', () => {
  const out = findNew([statRow('pii-22fdb3ff@example.invalid', iso(60000), 's1')]);
  eq(out.length, 1, 'count');
  eq(out[0].campaign_id, 11, 'campaign');
  eq(out[0].lead_email, 'pii-22fdb3ff@example.invalid', 'email');
});
t('FN-2 sends older than lookback_minutes are skipped', () => {
  const out = findNew([statRow('pii-22fdb3ff@example.invalid', iso((CFG.lookback_minutes + 30) * 60000), 's1')]);
  eq(out[0].__idle, true, 'stale send was replayed');
});
t('FN-3 a send already marked seen is not replayed again', () => {
  const sd = { __sent_seen_v2: { sX: iso(60000) } };
  const out = findNew([statRow('pii-22fdb3ff@example.invalid', iso(60000), 'sX')], sd);
  eq(out[0].__idle, true, 'same send replayed twice');
});
t('FN-3b finding a send does NOT mark it seen - only a successful replay does (S4)', () => {
  const sd = {};
  const out = findNew([statRow('pii-22fdb3ff@example.invalid', iso(60000), 'sX')], sd);
  eq(out.length, 1, 'found');
  eq(Object.keys(sd.__sent_seen_v2 || {}), [],
     'marking at find time loses the send whenever WF-2 rejects the replay');
});
t('FN-3c the store is namespaced _v2, abandoning keys poisoned by the 404 outage', () => {
  const sd = { __sent_seen: { sX: iso(60000) } };   // the old, poisoned store
  const out = findNew([statRow('pii-22fdb3ff@example.invalid', iso(60000), 'sX')], sd);
  eq(out.length, 1, 'the old store must no longer suppress replays');
});
t('FN-4 max_per_run bounds the batch and REPORTS the remainder', () => {
  const rows = [];
  for (let i = 0; i < CFG.max_per_run + 7; i++) rows.push(statRow('a' + i + '@x.com', iso(60000), 's' + i));
  const out = findNew(rows);
  eq(out.length, CFG.max_per_run, 'cap not applied');
  eq(out[0].__dropped, 7, 'silent truncation reads as "all caught up"');
});
t('FN-5 sends beyond the cap stay unmarked, so the next cycle claims them', () => {
  const sd = {};
  const rows = [];
  for (let i = 0; i < CFG.max_per_run + 3; i++) rows.push(statRow('a' + i + '@x.com', iso(60000), 's' + i));
  const first = findNew(rows, sd);
  eq(first.length, CFG.max_per_run, 'cap');
  // nothing is marked at find time now, so the whole set is still claimable
  const next = findNew(rows, sd);
  eq(next.length, CFG.max_per_run, 'dropped sends were lost instead of retried');
});
t('FN-6 output is ordered oldest-first', () => {
  const out = findNew([statRow('pii-7ea89e72@example.invalid', iso(60000), 's2'), statRow('pii-22fdb3ff@example.invalid', iso(600000), 's1')]);
  eq(out.map((o) => o.lead_email), ['pii-22fdb3ff@example.invalid', 'pii-7ea89e72@example.invalid'], 'order');
});

// =============================================================== S3: Build SENT Payload
const leadRes = (email, id, mapId, campId) => ({
  id, email, first_name: 'X',
  lead_campaign_data: [{ campaign_id: campId, campaign_lead_map_id: mapId }],
});
function buildPayload(rows, leads) {
  return run('Build SENT Payload', {
    named: { CONFIG: [CFG], 'Find New Sends': rows },
    input: leads,
  });
}
const row1 = { campaign_id: 11, campaign_name: 'A', lead_email: 'pii-22fdb3ff@example.invalid', lead_name: 'A A',
               sequence_number: 1, sent_time: iso(60000), email_subject: 'S', stats_id: 's1',
               __key: 's1', __batch: 2, __dropped: 0, __considered: 9 };
const row2 = { ...row1, lead_email: 'pii-7ea89e72@example.invalid', stats_id: 's2', __key: 's2' };

t('S3-1 EVERY send in the batch produces a payload', () => {
  const out = buildPayload([row1, row2],
    [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11), leadRes('pii-7ea89e72@example.invalid', 102, 9002, 11)]);
  eq(out.length, 2, 'batch collapsed to one - this is the S3 failure mode');
  eq(out.map((o) => o.__body.to_email), ['pii-22fdb3ff@example.invalid', 'pii-7ea89e72@example.invalid'], 'wrong leads');
});
t('S3-2 lead ids and map id are resolved per item, not shared', () => {
  const out = buildPayload([row1, row2],
    [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11), leadRes('pii-7ea89e72@example.invalid', 102, 9002, 11)]);
  eq(out.map((o) => o.__body.sl_email_lead_id), [101, 102], 'ids crossed between leads');
  eq(out.map((o) => o.__body.sl_email_lead_map_id), [9001, 9002], 'map ids crossed');
});
t('S3-3 event_type is the one WF-2 discriminates on', () => {
  const out = buildPayload([row1], [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11)]);
  eq(out[0].__body.event_type, 'EMAIL_SENT', 'WF-2 would fall to the default branch');
});
t('S3-4 provenance is stamped so a replay is never read as a real delivery', () => {
  const out = buildPayload([row1], [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11)]);
  eq(out[0].__body.__reconciled, true, 'provenance');
  eq(out[0].__body.__reconciled_by, 'WF-2S', 'provenance source');
});
t('S3-5 a slipped zip contributes NO ids rather than the wrong ones', () => {
  // lead response belongs to somebody else: the email cross-check must catch it
  const out = buildPayload([row1], [leadRes('pii-8e71564a@example.invalid', 999, 9999, 11)]);
  eq(out[0].__body.sl_email_lead_id, null, 'attached another lead\'s id');
  eq(out[0].__body.app_url, null, 'deep link would point at the wrong lead');
  eq(out[0].__id_verified, false, 'misalignment not flagged');
});
t('S3-6 the cross-check normalises BOTH sides, not just the lead record', () => {
  // /statistics and /leads are different endpoints and neither promises a canonical form, so
  // the row side needs normalising too. An earlier version of this test only varied the lead
  // side, which let a "row side not normalised" mutant pass.
  const rowUpper = { ...row1, lead_email: ' pii-22fdb3ff@example.invalid ' };
  eq(buildPayload([rowUpper], [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11)])[0].__id_verified, true,
     'a real match was rejected because the ROW side was not normalised');
  eq(buildPayload([row1], [leadRes('  pii-22fdb3ff@example.invalid ', 101, 9001, 11)])[0].__id_verified, true,
     'a real match was rejected because the LEAD side was not normalised');
});
t('S3-7 a lookup miss degrades to email resolution, never to a broken link', () => {
  const out = buildPayload([row1], [{}]);
  eq(out[0].__body.sl_email_lead_id, null, 'invented an id');
  eq(out[0].__body.app_url, null, 'LK-class: no broken links, ever');
  eq(out[0].__body.to_email, 'pii-22fdb3ff@example.invalid', 'email must survive for WF-2 to resolve on');
});
t('S3-8 map id is taken from the MATCHING campaign only', () => {
  const out = buildPayload([row1], [leadRes('pii-22fdb3ff@example.invalid', 101, 7777, 999)]);
  eq(out[0].__body.sl_email_lead_map_id, null, 'used another campaign\'s map id');
});
t('S3-9 the deep link is built from the map id when verified', () => {
  const out = buildPayload([row1], [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11)]);
  eq(out[0].__body.app_url, 'https://app.smartlead.ai/app/master-inbox?leadMap=9001', 'link form');
});
t('S3-9b the payload carries the real campaign status, not a hardcoded ACTIVE', () => {
  const done = { ...row1, campaign_status: 'COMPLETED' };
  const out = buildPayload([done], [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11)]);
  eq(out[0].__body.campaign_status, 'COMPLETED', 'the synthetic payload lied about the status');
});
t('S3-10 counters ride along for the report', () => {
  const out = buildPayload([row1], [leadRes('pii-22fdb3ff@example.invalid', 101, 9001, 11)]);
  eq(out[0].__considered, 9, 'considered lost');
});

// =============================================================== Summary
function summary(built, resp, sd) {
  return run('Summary', { named: { CONFIG: [CFG], 'Build SENT Payload': built },
                          input: resp, statics: sd || {} });
}
t('SUM-1 batch, failures and unverified ids are all counted', () => {
  const out = summary(
    [{ __key: 'k1', __id_verified: true, __dropped: 4, __considered: 30, __body: { time_sent: iso(1000) } },
     { __key: 'k2', __id_verified: false, __dropped: 4, __considered: 30, __body: { time_sent: iso(1000) } }],
    [{ ok: true }, { error: 'connect ETIMEDOUT' }]);
  eq(out[0].__batch, 2, 'batch');
  eq(out[0].__failed, 1, 'a rejected replay means that send is unobserved - must be counted');
  eq(out[0].__unverified, 1, 'unverified');
  eq(out[0].__dropped, 4, 'dropped');
});
t('SUM-2 a clean cycle reports no warnings', () => {
  const out = summary(
    [{ __key: 'k1', __id_verified: true, __dropped: 0, __considered: 3, __body: { time_sent: iso(1000) } }],
    [{ ok: true }]);
  eq([out[0].__failed, out[0].__unverified, out[0].__dropped], [0, 0, 0], 'false alarm');
});
t('SUM-3 (S4) only ACCEPTED replays are marked seen; a rejected one stays retryable', () => {
  const sd = {};
  const out = summary(
    [{ __key: 'good', __id_verified: true, __body: { time_sent: iso(1000) } },
     { __key: 'bad', __id_verified: true, __body: { time_sent: iso(1000) } }],
    [{ ok: true }, { error: '404 Active version not found' }], sd);
  eq(Object.keys(sd.__sent_seen_v2), ['good'],
     'a send rejected by a transient outage must not be marked - that is how 100 were lost');
  eq(out[0].__marked, 1, 'marked count');
});
t('SUM-4 the store is pruned so it cannot grow without bound', () => {
  const sd = { __sent_seen_v2: { ancient: new Date(NOW - 40 * 86400000).toISOString(),
                                 recent: iso(60000) } };
  const out = summary([{ __key: 'k1', __id_verified: true, __body: { time_sent: iso(1000) } }],
                      [{ ok: true }], sd);
  ok(!('ancient' in sd.__sent_seen_v2), 'at ~10k keys/day an unpruned store grows forever');
  ok('recent' in sd.__sent_seen_v2, 'pruned a key that is still inside the lookback window');
  eq(out[0].__pruned, 1, 'pruning must be reported, not silent');
});
t('SUM-5 the prune window is far wider than lookback, so nothing claimable is dropped', () => {
  const sd = { __sent_seen_v2: { edge: iso(CFG.lookback_minutes * 60000 + 60000) } };
  summary([], [], sd);
  ok('edge' in sd.__sent_seen_v2,
     'a key just past lookback was pruned - harmless today, but it invites a replay loop');
});

// =============================================================== structural
t('ST-1 no node reaches backward for a paired item (S1 class)', () => {
  const bad = WF.nodes.filter((n) => JSON.stringify(n.parameters).includes(').item'));
  eq(bad.map((n) => n.name), [], 'S1 regression');
});
t('ST-2 no literal Smartlead host outside CONFIG', () => {
  const bad = WF.nodes.filter((n) => n.name !== 'CONFIG'
    && JSON.stringify(n.parameters).includes('server.smartlead.ai'));
  eq(bad.map((n) => n.name), [], 'hardcoded host');
});
t('ST-3 no key material anywhere in the workflow JSON', () => {
  const blob = JSON.stringify(WF);
  ok(!/sk-proj-|api_key=[A-Za-z0-9]{8}/.test(blob), 'credential material embedded');
});
t('ST-4 every Smartlead call is authenticated', () => {
  const bad = WF.nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest'
    && String(n.parameters.url).includes('sl_api') && !n.parameters.authentication);
  eq(bad.map((n) => n.name), [], 'unauthenticated Smartlead call');
});
t('ST-5 no welded expressions (B9 class)', () => {
  const bad = WF.nodes.filter((n) => JSON.stringify(n.parameters).includes('}}={{'));
  eq(bad.map((n) => n.name), [], 'welded expression');
});
t('ST-6 the replay target is WF-2\'s own webhook, from CONFIG', () => {
  const n = nodeByName('Replay Into WF-2');
  ok(String(n.parameters.url).includes("$('CONFIG').first().json.wf2_webhook"), 'replay target');
  ok(CFG.wf2_webhook.endsWith('/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}'), 'not the production WF-2 path');
});
t('ST-7 every node is reachable from the trigger', () => {
  const seen = new Set(['Every 15 min']);
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
  const orphans = WF.nodes.map((n) => n.name).filter((n) => !seen.has(n));
  eq(orphans, [], 'orphaned node');
});
t('ST-8 the error workflow is bound', () => {
  eq(WF.settings.errorWorkflow, 'BbrXPABgOaaTJjD6', 'a silent failure is the worst outcome here');
});

console.log('WF-2S statics: ' + pass + ' passed, ' + fails.length + ' failed');
if (fails.length) { fails.forEach((f) => console.log('  FAIL ' + f)); process.exit(1); }
