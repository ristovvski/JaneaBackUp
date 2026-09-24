/**
 * WF-2R static contract tests.
 *
 * Every Code node is executed against fixtures captured from the REAL Smartlead responses used in
 * the 2026-08-06 investigation - not hand-written shapes. The lesson that forced this
 * (verify-shapes-before-fixtures): a mock copied from the wrong endpoint makes statics and mutants
 * agree with the bug.
 *
 * Run:  node wf2r_static_contract_tests.js "WF-2R Smartlead REPLY Reconciler - built.json"
 */
const fs = require('fs');

const path = process.argv[2] || 'WF-2R Smartlead REPLY Reconciler - built.json';
const WF = JSON.parse(fs.readFileSync(path, 'utf8'));
const NODES = Object.fromEntries(WF.nodes.map(n => [n.name, n]));
const CFG = JSON.parse(NODES['CONFIG'].parameters.jsonOutput);

let pass = 0, fail = 0;
const results = [];
function t(name, fn) {
  try { fn(); pass++; results.push(['PASS', name, '']); }
  catch (e) { fail++; results.push(['FAIL', name, e.message]); }
}
function eq(a, b, m) {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A !== B) throw new Error(`${m || ''} expected ${B}, got ${A}`);
}
function ok(c, m) { if (!c) throw new Error(m || 'expected truthy'); }

/* ---------------------------------------------------------------- code-node harness */
function runCode(nodeName, { input = [], nodes = {}, statics = {} } = {}) {
  const js = NODES[nodeName].parameters.jsCode;
  const sd = statics;
  const mk = (arr) => ({
    all: () => arr,
    first: () => arr[0],
    get item() { throw new Error('backward .item used - forbidden in a fan-out region'); },
  });
  const $ = (nm) => {
    if (!(nm in nodes)) throw new Error(`node ${nm} not stubbed`);
    return mk(nodes[nm]);
  };
  const $input = mk(input);
  const $json = input.length ? input[0].json : {};
  const $getWorkflowStaticData = () => sd;
  // eslint-disable-next-line no-new-func
  const fn = new Function('$', '$input', '$json', '$getWorkflowStaticData',
    `${js}`);
  return { out: fn($, $input, $json, $getWorkflowStaticData), statics: sd };
}
const item = (json) => ({ json });

/* ---------------------------------------------------------------- real fixtures */
// captured verbatim from /campaigns/3686193/leads-statistics (2026-08-06)
const PAGE_1 = {
  hasMore: true, skip: 0, limit: 100,
  data: [
    { lead_id: 4214227144, to: 'pii-280f963f@example.invalid', from: 'pii-72aef0b6@example.invalid',
      email_lead_map_id: 3423643499, status: 'COMPLETED', last_seq_num: 3,
      history: [
        { type: 'SENT', time: '2026-08-04T14:47:24.469+00:00', stats_id: '8acc9c09',
          message_id: '<pii-5a652efa@example.invalid>', subject: 'RE: Meeting at AI4?',
          email_body: '<div>Hope the first day...</div>', email_seq_number: '3' },
        { type: 'REPLY', time: '2026-08-05T06:08:38.000+00:00', stats_id: '8acc9c09',
          message_id: '<pii-f76c051f@example.invalid>', subject: 'RE: Meeting at AI4?',
          email_body: 'Hi Rune - I think you have the wrong email.', email_seq_number: '3' },
      ] },
    { lead_id: 4214095760, to: 'pii-567b1851@example.invalid',
      from: 'pii-d1f235df@example.invalid', email_lead_map_id: 111, status: 'COMPLETED',
      history: [
        { type: 'REPLY', time: '2026-08-04T16:55:41.000+00:00', stats_id: 'ffff',
          message_id: '<pii-f331ff3c@example.invalid>', subject: 'Re: AI4',
          email_body: 'My apologies, these messages have been buried', email_seq_number: '2' },
        // SAME lead, SAME stats_id, SECOND reply - the case that makes stats_id an invalid key
        { type: 'REPLY', time: '2026-08-04T17:15:19.000+00:00', stats_id: 'ffff',
          message_id: '<pii-830ceb1e@example.invalid>', subject: 'Re: AI4',
          email_body: 'Sounds good, thank you Mario', email_seq_number: '2' },
      ] },
  ],
};
const PAGE_2 = {
  hasMore: false, skip: 100, limit: 100,
  data: [
    { lead_id: 4214208250, to: 'pii-6f8f48e5@example.invalid', from: 'pii-daf29f59@example.invalid',
      email_lead_map_id: 222,
      history: [{ type: 'REPLY', time: '2026-08-04T16:31:45.000+00:00', stats_id: 'aaaa',
                  message_id: null, subject: 'Re: AI4', email_body: 'How about 5pm?',
                  email_seq_number: '1' }] },
    // a stale reply, outside lookback
    { lead_id: 999, to: 'old@example.com', from: 'pii-daf29f59@example.invalid',
      history: [{ type: 'REPLY', time: '2026-01-01T00:00:00.000+00:00', stats_id: 'old',
                  message_id: '<old@x>', subject: 'x', email_body: 'x' }] },
  ],
};
// mirrors the live shape measured 2026-08-06: 5 ACTIVE, a long COMPLETED tail, some of it ancient
const RECENT = '2026-07-20T00:00:00.000Z';
const ANCIENT = '2024-01-01T00:00:00.000Z';
const CAMPAIGNS = [
  { id: 3686193, name: '[Events Visiting] AI4 2026 - Rune - Catch-alls', status: 'ACTIVE',
    created_at: RECENT },
  { id: 3686187, name: '[Events Visiting] AI4 2026 - Rune - Valids', status: 'ACTIVE',
    created_at: RECENT },
  { id: 3686184, name: '[Events Visiting] AI4 2026 - Mario - Catch-alls', status: 'ACTIVE',
    created_at: RECENT },
  { id: 3686181, name: '[Events Visiting] AI4 2026 - Mario - Valids', status: 'ACTIVE',
    created_at: RECENT },
  { id: 3721506, name: 'Lead Nurturing - Rune', status: 'COMPLETED', created_at: RECENT },
  { id: 2222222, name: 'AWS Re:Invent 2024 - ancient', status: 'COMPLETED', created_at: ANCIENT },
  { id: 1111111, name: 'AI Summit 2024 - ancient', status: 'PAUSED', created_at: ANCIENT },
  { id: 99, name: 'archived thing', status: 'ARCHIVED', created_at: RECENT },
];
const CAMP_ITEM = {
  campaign_id: 3686193, campaign_name: '[Events Visiting] AI4 2026 - Rune - Catch-alls',
  campaign_status: 'COMPLETED', __pool: 4, __cursor: 0,
};
const cfgNodes = () => ({ CONFIG: [item(CFG)] });

// freeze "now" so lookback maths is deterministic
const REAL_NOW = Date.now;
function withNow(iso, fn) {
  const t = Date.parse(iso);
  Date.now = () => t;
  try { return fn(); } finally { Date.now = REAL_NOW; }
}
const NOW = '2026-08-05T08:00:00Z';

/* =================================================================== CONFIG contract */
t('R-C1 polls leads-statistics, never the undercounting /statistics', () => {
  const p = JSON.stringify(NODES['SL Leads Statistics'].parameters);
  ok(p.includes('leads-statistics'), 'must call leads-statistics');
  ok(!p.includes("'/statistics'"), 'must not call /statistics');
});
t('R-C2 max_per_run is 20 (owner spec)', () => eq(CFG.max_per_run, 20));
t('R-C3 one campaign per cycle (OOM guard)', () => eq(CFG.max_campaigns_per_cycle, 1));
t('R-C4 reply floor is stamped', () => ok(CFG.ignore_replies_before, 'floor missing'));
t('R-C5 pagination is driven by the API hasMore flag, with a page cap', () => {
  const pg = NODES['SL Leads Statistics'].parameters.options.pagination.pagination;
  ok(pg.completeExpression.includes('hasMore'), 'completion must key on hasMore');
  ok(pg.limitPagesFetched === true, 'page cap must be on');
});
t('R-C6 built inactive', () => eq(WF.active, false));
t('R-C7 error workflow wired', () => eq(WF.settings.errorWorkflow, 'BbrXPABgOaaTJjD6'));
t('R-C8 no secret material in the workflow JSON', () => {
  const s = JSON.stringify(WF);
  ok(!/api_key=|Bearer\s+[A-Za-z0-9]{12}|sk-[A-Za-z0-9]{12}/.test(s), 'looks like a secret');
});

/* =================================================================== Pick Campaign */
function cycles(n, st = {}, camps = CAMPAIGNS) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const r = withNow(NOW, () => runCode('Pick Campaign',
      { input: camps.map(item), nodes: cfgNodes(), statics: st }));
    out.push(r.out[0].json);
  }
  return out;
}
t('R-P1 one campaign per cycle, ARCHIVED excluded from both rings', () => {
  const c = cycles(1)[0];
  eq(c.__hot, 4, 'hot ring = ACTIVE only');
  eq(c.__cold, 1, 'cold ring = recent non-ACTIVE only');
  eq(c.__excluded, 2, 'the two ancient campaigns must be excluded and COUNTED');
});
t('R-P2 the hot ring gets 3 cycles out of every 4', () => {
  const seen = cycles(8);
  const hotCycles = seen.filter(c => c.__ring === 'hot').length;
  eq(hotCycles, 6, '8 cycles at a 3:1 ratio -> 6 hot, 2 cold');
});
t('R-P3 every ACTIVE campaign is visited inside one hot sweep', () => {
  const seen = cycles(8);
  const hotIds = new Set(seen.filter(c => c.__ring === 'hot').map(c => String(c.campaign_id)));
  eq(hotIds.size, 4, 'all four ACTIVE campaigns must appear');
});
t('R-P3b the cold tail is still reached, just less often', () => {
  const seen = cycles(8);
  const coldIds = seen.filter(c => c.__ring === 'cold').map(c => String(c.campaign_id));
  ok(coldIds.includes('3721506'), 'a recent COMPLETED campaign must still be polled');
});
t('R-P3c ancient campaigns are excluded but never silently', () => {
  const c = cycles(8).map(x => String(x.campaign_id));
  ok(!c.includes('2222222') && !c.includes('1111111'), 'ancient campaigns must not be polled');
  eq(cycles(1)[0].__excluded, 2, 'and their count must be reported every cycle');
});
t('R-P3d a campaign with an unparseable created_at is kept, not dropped blind', () => {
  const camps = CAMPAIGNS.concat([{ id: 555, name: 'no date', status: 'COMPLETED' }]);
  const c = withNow(NOW, () => runCode('Pick Campaign',
    { input: camps.map(item), nodes: cfgNodes(), statics: {} })).out[0].json;
  eq(c.__cold, 2, 'undated campaign must stay in the cold ring');
});
t('R-P3e sweep times are measured against the lookback, not assumed', () => {
  const c = cycles(1)[0];
  ok(typeof c.__hot_sweep_h === 'number' && typeof c.__cold_sweep_h === 'number');
  eq(c.__sweep_overrun, false, 'at this ring size both sweeps fit inside the lookback');
});
t('R-P3f a ring grown past the lookback raises the overrun flag', () => {
  const many = [];
  for (let i = 0; i < 400; i++) {
    many.push({ id: 900000 + i, name: 'c' + i, status: 'COMPLETED', created_at: RECENT });
  }
  const c = withNow(NOW, () => runCode('Pick Campaign',
    { input: CAMPAIGNS.concat(many).map(item), nodes: cfgNodes(), statics: {} })).out[0].json;
  eq(c.__sweep_overrun, true, 'an oversized ring must announce itself, not degrade quietly');
});
t('R-P4 an unparseable campaign list throws instead of reporting idle', () => {
  let threw = false;
  try { withNow(NOW, () => runCode('Pick Campaign',
    { input: [], nodes: cfgNodes(), statics: {} })); } catch (e) { threw = true; }
  ok(threw, 'empty /campaigns must be a hard error, not "idle"');
});

/* =================================================================== Find New Replies */
const findNodes = () => ({ CONFIG: [item(CFG)], 'Pick Campaign': [item(CAMP_ITEM)] });
function findRun(statics = {}, pages = [PAGE_1, PAGE_2]) {
  // the fixture replies span 2026-08-04 16:31 .. 2026-08-05 06:08 (~14h), deliberately wider than
  // a short window - that spread is exactly why lookback must outlive an outage (see R-C9)
  const cfg2 = { ...CFG, ignore_replies_before: '2026-01-01T00:00:00Z' };
  return withNow(NOW, () => runCode('Find New Replies', {
    input: pages.map(item),
    nodes: { CONFIG: [item(cfg2)], 'Pick Campaign': [item(CAMP_ITEM)] },
    statics,
  }));
}
t('R-F1 extracts exactly the REPLY entries, ignoring SENT', () => {
  const r = findRun();
  const emails = r.out.map(o => o.json.lead_email);
  eq(emails.length, 4, 'ashwin + brum x2 + hwang');
  ok(!emails.includes(undefined));
});
t('R-F2 the SAME lead replying TWICE yields TWO events (stats_id is not an identity)', () => {
  const r = findRun();
  const brum = r.out.filter(o => o.json.lead_email === 'pii-567b1851@example.invalid');
  eq(brum.length, 2, 'both brum replies must survive');
  ok(brum[0].json.__key !== brum[1].json.__key, 'their claim keys must differ');
  eq(brum[0].json.stats_id, brum[1].json.stats_id, 'fixture check: same stats_id by design');
});
t('R-F3 a reply with no message_id still gets a distinct key', () => {
  const r = findRun();
  const hw = r.out.find(o => o.json.lead_email === 'pii-6f8f48e5@example.invalid');
  ok(hw, 'hwang must be found');
  ok(hw.json.__key.startsWith('T|'), 'must fall back to the campaign|lead|time triple');
});
t('R-F4 replies outside lookback are dropped as stale', () => {
  const r = findRun();
  ok(!r.out.some(o => o.json.lead_email === 'old@example.com'), 'stale reply leaked');
  ok(r.out[0].json.__stale >= 1, 'stale count must be reported');
});
t('R-C9 lookback outlives the observed 973-minute outage', () => {
  ok(CFG.lookback_minutes > 973,
    `lookback_minutes=${CFG.lookback_minutes} would age out an outage's replies before WF-2 `
    + 'returns - WF-2R replays INTO WF-2, so recovery only starts once WF-2 is back');
});
t('R-F5 the floor suppresses replies older than deploy', () => {
  const cfg2 = { ...CFG, ignore_replies_before: '2026-08-05T00:00:00Z' };
  const r = withNow(NOW, () => runCode('Find New Replies', {
    input: [PAGE_1, PAGE_2].map(item),
    nodes: { CONFIG: [item(cfg2)], 'Pick Campaign': [item(CAMP_ITEM)] }, statics: {},
  }));
  const emails = r.out.filter(o => !o.json.__idle).map(o => o.json.lead_email);
  eq(emails, ['pii-280f963f@example.invalid'], 'only the post-floor reply survives');
});
t('R-F6 Find New Replies READS but never WRITES the claim store', () => {
  const st = {};
  findRun(st);
  const store = st.__reply_seen_v1 || {};
  eq(Object.keys(store).length, 0, 'claiming must happen only after a successful replay');
});
t('R-F7 an already-claimed reply is not re-emitted', () => {
  const st = { __reply_seen_v1: { 'M|<pii-f331ff3c@example.invalid>': '2026-08-04T16:55:41Z' } };
  const r = findRun(st);
  const brum = r.out.filter(o => o.json.lead_email === 'pii-567b1851@example.invalid');
  eq(brum.length, 1, 'the claimed reply must be skipped, its sibling must not');
  eq(r.out[0].json.__already, 1);
});
t('R-F8 an incomplete page walk leaves a RESUME CURSOR, not a truncated scan', () => {
  const st = {};
  const r = findRun(st, [PAGE_1]);          // last page still hasMore:true
  ok(r.out[0].json.__truncated === true, 'truncation must be surfaced');
  ok(st.__resume, 'a cursor must be recorded so the next cycle continues');
  eq(st.__resume.campaign_id, CAMP_ITEM.campaign_id);
  eq(st.__resume.next_offset, 100, 'one page of 100 scanned from offset 0');
  eq(r.out[0].json.__scanned_to, 100);
});
t('R-F8b a completed walk CLEARS the cursor', () => {
  const st = { __resume: { campaign_id: 999, next_offset: 500, round: 2 } };
  findRun(st, [PAGE_1, PAGE_2]);            // last page hasMore:false
  eq(st.__resume, null, 'finishing must not leave a stale cursor behind');
});
t('R-F8c the cursor advances from a resumed offset', () => {
  const st = {};
  const cfg2 = { ...CFG, ignore_replies_before: '2026-01-01T00:00:00Z' };
  const resumed = { ...CAMP_ITEM, start_offset: 300, resume_round: 2 };
  const r = withNow(NOW, () => runCode('Find New Replies', {
    input: [PAGE_1].map(item),
    nodes: { CONFIG: [item(cfg2)], 'Pick Campaign': [item(resumed)] }, statics: st,
  }));
  eq(r.out[0].json.__start_offset, 300);
  eq(st.__resume.next_offset, 400, 'resumed 300 + one page of 100');
  eq(st.__resume.round, 3, 'round counter must increment');
});
t('R-F8d a cursor stuck past max_resume_rounds raises __stuck', () => {
  const st = {};
  const cfg2 = { ...CFG, ignore_replies_before: '2026-01-01T00:00:00Z', max_resume_rounds: 2 };
  const resumed = { ...CAMP_ITEM, start_offset: 900, resume_round: 5 };
  const r = withNow(NOW, () => runCode('Find New Replies', {
    input: [PAGE_1].map(item),
    nodes: { CONFIG: [item(cfg2)], 'Pick Campaign': [item(resumed)] }, statics: st,
  }));
  eq(r.out[0].json.__stuck, true, 'a walk that never finishes must be named, with its range');
  eq(r.out[0].json.__scanned_to, 1000, 'the UNSCANNED RANGE starts here');
});
t('R-P4b resume takes priority over rotation', () => {
  const st = { __resume: { campaign_id: 3686187, campaign_name: 'x', next_offset: 400, round: 1 } };
  const c = withNow(NOW, () => runCode('Pick Campaign',
    { input: CAMPAIGNS.map(item), nodes: cfgNodes(), statics: st })).out[0].json;
  eq(String(c.campaign_id), '3686187', 'the unfinished campaign must be re-picked');
  eq(c.__ring, 'resume');
  eq(c.start_offset, 400, 'and continue from where it stopped');
});
t('R-P4c a resume cursor for a vanished campaign does not stall the reconciler', () => {
  const st = { __resume: { campaign_id: 99999, next_offset: 400, round: 1 } };
  const c = withNow(NOW, () => runCode('Pick Campaign',
    { input: CAMPAIGNS.map(item), nodes: cfgNodes(), statics: st })).out[0].json;
  ok(c.campaign_id && String(c.campaign_id) !== '99999', 'must fall back to normal rotation');
  eq(st.__resume, null, 'and drop the dead cursor');
});
t('R-F9 the cap is applied and the overflow reported', () => {
  const cfg2 = { ...CFG, max_per_run: 2,
                 ignore_replies_before: '2026-01-01T00:00:00Z' };
  const r = withNow(NOW, () => runCode('Find New Replies', {
    input: [PAGE_1, PAGE_2].map(item),
    nodes: { CONFIG: [item(cfg2)], 'Pick Campaign': [item(CAMP_ITEM)] }, statics: {},
  }));
  eq(r.out.length, 2, 'cap must bound the batch');
  eq(r.out[0].json.__dropped, 2, 'the drop must be counted, not silent');
});
t('R-F10 output is ordered oldest-first', () => {
  const r = findRun();
  const times = r.out.map(o => o.json.reply_time);
  eq(times.slice().sort(), times, 'replies must replay in chronological order');
});

/* =================================================================== Build REPLY Payload */
const LEAD_LOOKUP = {
  id: '4214227144', email: 'pii-280f963f@example.invalid', first_name: 'Aniruddha',
  last_name: 'Deshpande', company_name: 'Netflix', website: 'netflix.com',
  linkedin_profile: 'https://www.linkedin.com/in/pii-79f592d7', location: 'Los Gatos, California',
  custom_fields: { Title: 'Senior software engineer' },
  lead_campaign_data: [{ campaign_id: 3686193, campaign_lead_map_id: 3423643499,
                         lead_category_id: 7 }],
};
function payloadRun(lookup) {
  // pair the lookup with ITS OWN row - rows are ordered oldest-first, so index 0 is hwang, and
  // feeding Ashwin's lookup against hwang's row would test the mismatch path by accident
  const found = findRun();
  const row = found.out.find(o => o.json.lead_email === 'pii-280f963f@example.invalid');
  return withNow(NOW, () => runCode('Build REPLY Payload', {
    input: [item(lookup)],
    nodes: { CONFIG: [item(CFG)], 'Find New Replies': [row] },
  }));
}
t('R-B1 payload carries the reply time as timestamp (drives WF-2 dedupe)', () => {
  const r = payloadRun(LEAD_LOOKUP);
  const b = r.out[0].json.__body;
  eq(b.timestamp, b.reply_time, 'timestamp must be the reply time, not wall clock');
  ok(b.timestamp.startsWith('2026-08-04') || b.timestamp.startsWith('2026-08-05'));
});
t('R-B2 event_type is EMAIL_REPLY and provenance is stamped', () => {
  const b = payloadRun(LEAD_LOOKUP).out[0].json.__body;
  eq(b.event_type, 'EMAIL_REPLY');
  eq(b.__reconciled, true);
  eq(b.__reconciled_by, 'WF-2R');
});
t('R-B3 sender inbox is carried - forwards route by it', () => {
  const b = payloadRun(LEAD_LOOKUP).out[0].json.__body;
  ok(b.from_email, 'from_email must be present or every forward goes to default');
});
t('R-B4 a mismatched lead lookup withholds ids instead of mis-attributing', () => {
  const r = payloadRun({ ...LEAD_LOOKUP, email: 'someone.else@example.com' });
  const o = r.out[0].json;
  eq(o.__id_verified, false);
  eq(o.__body.lead_data, undefined, 'unverified lookup must not contribute lead data');
  eq(o.__body.reply_category, null, 'unverified lookup must not contribute a category');
  ok(o.__body.lead_id, 'lead_id comes from leads-statistics itself and stays');
});
t('R-B5 Smartlead category is passed through when verified', () => {
  const b = payloadRun(LEAD_LOOKUP).out[0].json.__body;
  eq(b.reply_category, 7, 'Wrong Person id must reach WF-2 as the native baseline');
});
t('R-B6 runs once for all items - N replies produce N payloads', () => {
  const found = findRun();
  const r = withNow(NOW, () => runCode('Build REPLY Payload', {
    input: found.out.map(o => item({ ...LEAD_LOOKUP, email: o.json.lead_email })),
    nodes: { CONFIG: [item(CFG)], 'Find New Replies': found.out },
  }));
  eq(r.out.length, 4, 'one payload per reply');
});

/* =================================================================== Summary / claiming */
function summaryRun(responses, statics = {}) {
  const found = findRun();
  const built = withNow(NOW, () => runCode('Build REPLY Payload', {
    input: found.out.map(o => item({ ...LEAD_LOOKUP, email: o.json.lead_email })),
    nodes: { CONFIG: [item(CFG)], 'Find New Replies': found.out },
  })).out;
  return withNow(NOW, () => runCode('Summary', {
    input: responses.map(item),
    nodes: { CONFIG: [item(CFG)], 'Build REPLY Payload': built },
    statics,
  }));
}
t('R-S1 accepted replays are claimed', () => {
  const st = {};
  const r = summaryRun([{ ok: true }, { ok: true }, { ok: true }, { ok: true }], st);
  eq(Object.keys(st.__reply_seen_v1).length, 4);
  eq(r.out[0].json.__failed, 0);
});
t('R-S2 a REJECTED replay is NOT claimed - it must retry next cycle', () => {
  const st = {};
  const r = summaryRun([{ ok: true }, { error: 'boom' }, { ok: true }, { ok: true }], st);
  eq(Object.keys(st.__reply_seen_v1).length, 3, 'the rejected one must stay unclaimed');
  eq(r.out[0].json.__failed, 1, 'and it must be reported');
});
t('R-S3 the claim store prunes and reports its size', () => {
  const st = { __reply_seen_v1: { 'M|ancient': '2020-01-01T00:00:00Z' } };
  const r = summaryRun([{ ok: true }, { ok: true }, { ok: true }, { ok: true }], st);
  ok(r.out[0].json.__pruned >= 1, 'ancient keys must be pruned');
  ok(!('M|ancient' in st.__reply_seen_v1));
});

/* =================================================================== watchdog */
t('R-W1 an unreachable n8n API reads as STALE, never as healthy', () => {
  const r = withNow(NOW, () => runCode('WF-2S Watch Eval', {
    input: [item({ error: 'ECONNREFUSED' })],
    nodes: { CONFIG: [item({ ...CFG, wf2s_workflow_id: '6Y92ryBwYoy6z0Jx' })] },
  }));
  eq(r.out[0].json.__wf2s_stale, true, 'a blind watchdog must shout, not stay quiet');
});
t('R-W2 a fresh WF-2S execution reads as healthy', () => {
  const r = withNow(NOW, () => runCode('WF-2S Watch Eval', {
    input: [item({ data: [{ startedAt: '2026-08-05T07:50:00.000Z' }] })],
    nodes: { CONFIG: [item({ ...CFG, wf2s_workflow_id: '6Y92ryBwYoy6z0Jx' })] },
  }));
  eq(r.out[0].json.__wf2s_stale, false);
});
t('R-W3 an old WF-2S execution reads as stale', () => {
  const r = withNow(NOW, () => runCode('WF-2S Watch Eval', {
    input: [item({ data: [{ startedAt: '2026-08-05T02:00:00.000Z' }] })],
    nodes: { CONFIG: [item({ ...CFG, wf2s_workflow_id: '6Y92ryBwYoy6z0Jx' })] },
  }));
  eq(r.out[0].json.__wf2s_stale, true);
});

/* =================================================================== idle honesty */
t('R-I1 a clean idle cycle stays silent', () => {
  const r = withNow(NOW, () => runCode('Idle Eval', {
    input: [item({ __idle: true, __truncated: false, __dropped: 0 })], nodes: cfgNodes(),
  }));
  eq(r.out[0].json.__report, false);
});
t('R-I2 ordinary continuation is NOT alarm-worthy (resume cursor handles it)', () => {
  const r = withNow(NOW, () => runCode('Idle Eval', {
    input: [item({ __idle: true, __truncated: true, __stuck: false, __dropped: 0 })],
    nodes: cfgNodes(),
  }));
  eq(r.out[0].json.__report, false,
    'alarming on every partial pass is what buried the real signal for three days');
});
t('R-I2b a STUCK cursor does speak up', () => {
  const r = withNow(NOW, () => runCode('Idle Eval', {
    input: [item({ __idle: true, __truncated: true, __stuck: true, __dropped: 0 })],
    nodes: cfgNodes(),
  }));
  eq(r.out[0].json.__report, true, 'a walk that never completes must be named');
});
t('R-I3 an idle cycle whose rotation outlives the lookback speaks up', () => {
  const r = withNow(NOW, () => runCode('Idle Eval', {
    input: [item({ __idle: true, __truncated: false, __dropped: 0, __sweep_overrun: true })],
    nodes: cfgNodes(),
  }));
  eq(r.out[0].json.__report, true, 'a rotation slower than the lookback loses replies silently');
});

/* =================================================================== report */
const W = 78;
console.log('='.repeat(W));
console.log('WF-2R static contract tests');
console.log('='.repeat(W));
for (const [s, n, m] of results) {
  console.log(`  ${s}  ${n}${m ? '\n        ' + m : ''}`);
}
console.log('='.repeat(W));
console.log(`  ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
