
const CFG = { fields: {}, forward_inbox_map: {}, forward_owner_map: {}, forward_default: 'x@y.z' };
const ENV = {"event_type": "EMAIL_REPLY", "campaign_id": 3085711, "lead_id": "999", "to_email": "pii-10d2dcec@example.invalid", "to_name": "Person-7267ff83", "from_email": "pii-6b9f81bf@example.invalid", "reply_body": "sounds good", "reply_category": "Interested", "message_id": "M1", "stats_id": "S1", "__reconciled_by": "WF-2R", "event_timestamp": "2026-08-13T17:30:00Z", "sl_lead_email": "pii-eb7de9be@example.invalid"};
const $json = { body: ENV };
const $ = (nm) => (nm === 'CONFIG'
  ? { item: { json: CFG }, first: () => ({ json: CFG }) }
  : { item: { json: { body: ENV } }, first: () => ({ json: { body: ENV } }) });
const $getWorkflowStaticData = () => ({ wf2_seen: {} });
const items = [{ json: { body: ENV } }];
const NZOUT = (() => {
// WF-2 Normalize - the single translation layer (architecture SS2)
// Defensive by design: EVERY payload field is optional (A3 is UNVERIFIED).
// B11: Normalize's $json is the CONFIG node's output, NOT the webhook body - the spine is
// Webhook -> Respond -> CONFIG -> Normalize. Reading $json.body silently produced an EMPTY
// payload on every single event. Always name the source node.
const b = $('Webhook').item.json.body ?? $('Webhook').item.json ?? {};
const cfg = $('CONFIG').item.json;

const CANON_WS = (s) => String(s ?? '')
  .replace(/[     ]/g, ' ')   // nbsp + friends -> plain space
  .replace(/\s+/g, ' ')
  .trim();
const low = (s) => CANON_WS(s).toLowerCase();
const mail = (s) => String(s ?? '').trim().toLowerCase();
const pick = (...vals) => { for (const v of vals) if (v !== undefined && v !== null && String(v).trim() !== '') return v; return null; };

// ---- event discriminator (defensive: Smartlead naming varies by webhook version)
const rawEvent = low(pick(b.event_type, b.event, b.webhook_event, b.type));
let event = 'UNKNOWN';
if (/first.*sent|email.?sent|email_sent/.test(rawEvent)) event = 'SENT';
else if (/repl/.test(rawEvent)) event = 'REPLIED';
else if (/bounce/.test(rawEvent)) event = 'BOUNCED';
else if (/unsub/.test(rawEvent)) event = 'UNSUB';
else if (/categor/.test(rawEvent)) event = 'CATEGORY_UPDATED';   // Make's trigger; we ignore it

const ld = b.lead_data ?? b.lead ?? {};
const campaign_name_raw = pick(b.campaign_name, b.campaign?.name, ld.campaign_name);
const campaign_name = CANON_WS(campaign_name_raw);

// ---- marker parser (same contract as W1.0.13.1: two-bracket convention)
const groups = [];
{ const re = /\[([^\]]*)\]/g; let m; while ((m = re.exec(campaign_name)) !== null) groups.push(m[1]); }
const canon = cfg.marker_canon || {};
let hypothesis = null, event_name = null, marker_unknown = null, is_nurture = false;
if (groups.length) {
  const key = low(groups[0]);
  if (Object.prototype.hasOwnProperty.call(canon, key)) {
    const v = canon[key];
    if (v === '__NURTURE__') is_nurture = true; else hypothesis = v;
  } else {
    marker_unknown = CANON_WS(groups[0]);
  }
  if (groups.length >= 2) {
    const ev = CANON_WS(groups[1]);
    if (ev !== '' && ev.length <= 60 && !/\[|\]/.test(ev)) event_name = ev;
  }
}
// FALLBACK (2026-08-06): single-bracket email campaigns structurally can't carry a 2nd bracket
// for Event name. Consult an explicit CONFIG map before leaving it null. Never overrides a
// successful bracket-derived value - additive only.
const campIdStr = String(pick(b.campaign_id, b.campaign?.id, ld.campaign_id) ?? '');
const camFallback = (cfg.campaign_event_map || {})[campIdStr];
if (camFallback) {
  if (!hypothesis) hypothesis = camFallback.hypothesis ?? hypothesis;
  if (!event_name) event_name = camFallback.event_name ?? event_name;
}

// nurture may also be signalled without brackets (Make parity: name contains "lead nurturing")
if (!is_nurture && /lead nurtur/.test(low(campaign_name))) is_nurture = true;

// ---- REPLY IDENTITY (2026-08-13). `to_email` is WHO REPLIED; `sl_lead_email` is THE CAMPAIGN LEAD.
// Taking to_email as the lead made WF-2 adopt a stranger on threaded replies: the real lead got no
// label and no activity, and an alert fired naming someone who was never a lead (Ganga, exec 16265).
const __mailOf = (s) => String(s ?? '').trim().toLowerCase();
const __localOf = (s) => __mailOf(s).split('@')[0].replace(/[._+\-0-9]/g, '');
const __domOf = (s) => __mailOf(s).split('@')[1] || '';
const __isAlias = (x, y) => {
  if (!x || !y) return false;
  if (__domOf(x) !== __domOf(y)) return false;      // SAME DOMAIN REQUIRED
  const a = __localOf(x), b = __localOf(y);
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.indexOf(b) !== -1 || b.indexOf(a) !== -1) return true;
  const ini = (p, q) => p.length > 1 && q.length > 1 && p[0] === q[0]
                        && q.slice(q.length - (p.length - 1)) === p.slice(1);
  return ini(a, b) || ini(b, a);
};
const __reply_from = __mailOf(b.to_email) || null;
const __sl_lead = __mailOf(b.sl_lead_email) || null;
let __reply_class;
if (!__reply_from || !__sl_lead) { __reply_class = 'ambiguous'; }
else if (__reply_from === __sl_lead) { __reply_class = 'lead'; }
else if (__isAlias(__reply_from, __sl_lead)) { __reply_class = 'alias'; }
else { __reply_class = 'third_party'; }
const __lead_email = mail(pick(b.sl_lead_email, ld.email, b.to_email, b.email));


const n = {
  event, raw_event: rawEvent,
  campaign_id: pick(b.campaign_id, b.campaign?.id, ld.campaign_id),
  campaign_name, campaign_name_raw: campaign_name_raw ?? null,
  // B15: field names come from REAL webhook samples recovered from the Make blueprints
  // (wf2-webhook-payloads.md). EMAIL_SENT carries sl_email_lead_id, NOT lead_id - without this
  // sl_lead_id was null on every SENT event, and since the dedupe key is campaign_id + sl_lead_id
  // every first-email in a campaign collapsed onto ONE key and all but the first were dropped.
  sl_lead_id: pick(b.lead_id, b.sl_email_lead_id, ld.id, b.sl_lead_id),
  // the map id is what the Smartlead UI deep link keys on (?leadMap=), and the payload also ships
  // the finished link itself - prefer the given link over anything we construct
  sl_lead_map_id: pick(b.sl_email_lead_map_id, b.lead_map_id, b.campaign_lead_map_id),
  sl_app_url: pick(b.app_url, b.ui_master_inbox_link),
  // F5: Smartlead ships its OWN category on reply events (observed: reply_category "Interested").
  // While classify_enabled is false this is the category source, so the shadow diff measures real
  // gating instead of fail-open. At flip it becomes the comparison baseline for our classifier.
  // Smartlead sends this as a NAME in its test payload ("Interested") but as a NUMERIC ID on real
  // organic replies (observed: 2). Resolve ids back to names via category_map, so the F5 native
  // fallback and the accuracy comparison both see one consistent vocabulary.
  reply_category: (() => {
    const raw = pick(b.reply_category, b.lead_category?.new_name, b.lead_data?.category?.name,
                     b.lead_category?.new_id, b.lead_data?.category?.id);
    if (raw === null) return null;
    const asNum = Number(raw);
    if (Number.isFinite(asNum) && String(raw).trim() !== '') {
      for (const [nm, id] of Object.entries(cfg.category_map || {})) if (id === asNum) return nm;
      return null;                      // an id we do not know is worse than no category
    }
    return String(raw);
  })(),
  reply_source: pick(b.reply_source),
  // F1: the reply event turned out to be EMAIL_REPLY, not EMAIL_REPLIED - an assumption I had
  // recorded as verified. The regexes are deliberately loose, so a wrong constant routes correctly
  // and hides the mismatch. Flag it instead, so live traffic teaches us the other three names.
  event_alias: (() => {
    const canon = (cfg.canonical_events || {})[event] || null;
    return (event !== 'UNKNOWN' && canon && rawEvent && rawEvent !== canon) ? rawEvent : null;
  })(),
  sequence_number: (() => { const v = pick(b.sequence_number, b.current_seq_num, b.seq_number); const num = Number(v); return Number.isFinite(num) ? num : null; })(),
  timestamp: pick(b.timestamp, b.time_sent, b.event_timestamp, b.created_at),
  sender_inbox: mail(pick(b.from_email, b.email_account, b.sender_email)),
  __reply_class,
  __reply_from,
  lead: {
    email: __lead_email,
    first: pick(ld.first_name, b.first_name),
    last: pick(ld.last_name, b.last_name),
    full_name: pick(b.to_name, ld.full_name, [pick(ld.first_name, b.first_name), pick(ld.last_name, b.last_name)].filter(Boolean).join(' ') || null),
    company: CANON_WS(pick(ld.company_name, b.company_name)) || null,
    website: pick(ld.website, b.website),
    linkedin: pick(ld.linkedin_profile, b.linkedin_profile, ld.linkedin),
    location: pick(ld.location, b.location, ld.city, b.city),
    title: pick(ld.job_title, b.job_title, ld.title, b.title),
    custom_fields: ld.custom_fields ?? b.custom_fields ?? {},
  },
  reply: {
    subject: pick(b.subject, b.reply_subject, b.email_subject, b.last_reply?.subject),
    body: pick(b.reply_body, b.body, b.email_body, b.reply_message, b.message,
               b.last_reply?.email_body),
    received_at: pick(b.reply_time, b.time_replied, b.received_at, b.timestamp),
    message_id: pick(b.message_id, b.reply_message_id, b.last_reply?.message_id),
    stats_id: pick(b.stats_id, b.last_reply?.stats_id),
  },
  hypothesis, event_name, marker_unknown, is_nurture,
  // Provenance. Normalize whitelists its output, which silently dropped these two - so a
  // WF-2S-reconciled SENT event was indistinguishable from a genuine Smartlead delivery in
  // Shadow Log and the diff harness. That distinction is the entire reason the reconciler
  // stamps them: SENT arrives ONLY by replay today, and when Smartlead eventually fixes
  // delivery we need to see which source a given event came from.
  __reconciled: b.__reconciled === true,
  __reconciled_by: b.__reconciled === true ? pick(b.__reconciled_by) : null,
};
return [{ json: n }];

})();
const NZ = Array.isArray(NZOUT) ? NZOUT[0].json : NZOUT;

const $json2 = { __dedupe_key: 'K1', __lead_id: null };
const GATEOUT = (() => {
  const $json = $json2;
  const $ = (nm) => (nm === 'Normalize' ? { item: { json: NZ } }
                     : { item: { json: CFG }, first: () => ({ json: CFG }) });
  const $getWorkflowStaticData = () => ({});
const CFG = $('CONFIG').item.json;
const n = (() => { try { return $('Normalize').item.json; } catch (e) { return {}; } })();
// DELIVERY-BASED suppression (2026-08-10). The old rule read the '3. Responded' LABEL, which is
// written by Make, Zaps, backfills and humans - never a delivery receipt. Two failures followed:
// any writer could silence our alerts, and a FAILED Slack post still burned the lead's single
// alert forever. This registry is set ONLY when Slack returns ok:true (see Classify Body).
const sd = $getWorkflowStaticData('global');
const reg = sd.__alert_delivered = (sd.__alert_delivered || {});
const nowSec = Math.floor(Date.now() / 1000);
const maxAge = Number(CFG.alert_registry_max_age_sec ?? 7776000);   // 90d, bounded memory
let pruned = 0;
for (const k of Object.keys(reg)) {
  if (nowSec - Number(reg[k]) > maxAge) { delete reg[k]; pruned++; }
}
const key = String($json.__lead_id ?? $json.__person_id ?? (n.lead && n.lead.email) ?? '');
const already = key ? Object.prototype.hasOwnProperty.call(reg, key) : false;
const alertEvery = !!(CFG.flags && CFG.flags.alert_every_reply === true);
// no key at all -> fail OPEN and alert; a missed notification is worse than a duplicate

// OOO-GATE: Smartlead's own reply_category, available from Normalize (#6) - long before the alert
// decision (#21) and independent of our LLM (#29), so an LLM outage cannot leak OOO alerts.
// FAIL-OPEN by design: unknown/missing category => treat as a REAL reply.
const __isOOO = (() => {
  try {
    const c = String(($('Normalize').item.json || {}).reply_category ?? '').trim().toLowerCase();
    if (!c) return false;
    const auto = ['out of office', 'ooo', 'auto reply', 'auto-reply', 'automatic reply',
                  'autoreply', 'vacation', 'away'];
    return auto.indexOf(c) !== -1;
  } catch (e) { return false; }
})();

// An autoresponder is not engagement, and it must NOT burn the lead's single alert. Because the
// registry is written only when Reply Alert returns ok:true, suppressing here leaves the slot
// intact automatically - the human's real reply on their return still counts as their first.
// Third-party replies do not alert the team channel: a colleague on someone else's thread is not
// the lead speaking. AMBIGUOUS DOES ALERT (Nik, 2026-08-14, section 0). The earlier 'fail quiet'
// reading was wrong about which direction is safe: a missing identity field is an INTERNAL failure,
// and an internal failure must never eat a live reply. It ate one - Person-7267ff83's 'Interested'
// (exec 16278, a WF-2R replay whose envelope carried no sl_lead_email). Silence is now reserved for
// a CONFIRMED third party; an unverified identity alerts with the doubt stated in the body.
const __rc = (() => { try { return $('Normalize').item.json.__reply_class || 'lead'; }
                      catch (e) { return 'lead'; } })();
const __suppress_class = (__rc === 'third_party');
const __identity_unverified = (__rc === 'ambiguous');
const should = (__isOOO || __suppress_class) ? false
  : (alertEvery ? true : (!key ? true : !already));
const __reason = __isOOO ? 'ooo_no_alert'
  : __suppress_class ? ('suppressed_' + __rc)
  : alertEvery ? 'alert_every_reply'
  : !key ? 'fail_open_no_key'
  : already ? 'already_delivered'
  : 'first_reply';
return [{ json: { ...$json, __should_alert: should, __alert_key: key, __ooo: __isOOO,
  __reply_class: __rc,
  __identity_unverified: __identity_unverified,
  __alert_reason: __reason,
  __alert_pruned: pruned, __alert_registry_size: Object.keys(reg).length } }];
})();
const G = GATEOUT[0].json;
console.log(JSON.stringify({ cls: NZ.__reply_class, should: G.__should_alert,
                              reason: G.__alert_reason, flag: G.__identity_unverified }));
