// W1.0.15 identity, W1.0.17 semantics: ONE alert per lead, suppressed on DELIVERY.
// Two things changed 2026-08-11:
//   * the '3. Responded' LABEL no longer suppresses. Labels are written by Make, Zaps, backfills
//     and humans - never a delivery receipt. 1,713 leads carried it, so any writer could silence us.
//   * the registry is NO LONGER written here. Claiming at decision time means a failed Slack post
//     burns the lead's only alert forever. `M7 Labels Compute` writes it on ok:true.
const CFG = $('CONFIG').item.json;
const b = $json;                                  // M7 Build output (carries alert_text)
const n = $('Normalize').item.json;
const sd = $getWorkflowStaticData('global');
const reg = sd.__alerted_v1 = sd.__alerted_v1 || {};

const camp = String((n.campaign && (n.campaign.id ?? n.campaign.name)) ?? 'nocamp');
const li = (n.lead && (n.lead.member_id || n.lead.public_id || n.lead.li_url)) || null;
// STABLE KEY (Nik, 2026-08-31). The key must NOT depend on whether the lead is visible.
// It used to prefer 'L' + lead_id, so archiving Person-b093030e's lead moved his key from
// 'L8694ea30-a30b-11f1-8297-bb888c95b31f|572715' to 'P85903|572715'; the registry had no record
// of the new key and his SECOND message was announced as a first alert. Lead visibility is
// mutable state - a human archiving a lead must never reset that lead's alert suppression.
// Order: pipedrive person id -> canonical provider identity -> nothing (then fail open).
const who = b.person_id ? ('P' + b.person_id)
          : (li ? ('K' + String(li).toLowerCase()) : null);
const key = who ? (who + '|' + camp) : null;
// MIGRATION, not a rewrite of history: entries already delivered under the old lead-keyed form
// are still honoured, so deploying this does not re-announce everything that was keyed 'L...'.
// Only `key` is ever written back.
const legacyKey = b.lead_id ? ('L' + b.lead_id + '|' + camp) : null;

const now = Date.now();
let pruned = 0;
for (const k of Object.keys(reg)) {
  const t = Date.parse(reg[k]);
  if (Number.isFinite(t) && (now - t) > 90 * 86400000) { delete reg[k]; pruned++; }
}

// CAMPAIGN-ORIGIN GATE (Melisa, 2026-08-27): "We shouldn't get notifications about personal chats
// (lead not from campaigns)". A HeyReach inbox thread with no campaign is the exec's own
// conversation. Labels and the reply activity still run on their own branches - this suppresses the
// ANNOUNCEMENT only. Placed BEFORE the !key fail-open on purpose: that fail-open protects campaign
// replies from being lost, and must not resurrect a personal chat that has no identity either.
//
// RULING (Nik, 2026-08-28) — WHERE DO MANUAL-THREAD REPLIES GO INSTEAD? **NOWHERE.**
// A manual conversation gets the silent CRM activity write and nothing else: no #lead-processing
// alert, no thread note, no digest line, no alternate channel, no telemetry line. The exec's own
// conversations are the exec's own business; the CRM records them so the history exists, and the
// system never announces them to anyone. This silence is DELIBERATE - do not "restore" it as a
// quiet line somewhere on the assumption it was an oversight.
const __manual_thread = !(n.campaign && (n.campaign.id ?? n.campaign.name));

let should, reason;
if (__manual_thread) {
  should = false; reason = 'manual_conversation';
} else if (!key) {
  // no stable identity: a first reply must never be lost, so it alerts. Named, because this is the
  // only path that can still duplicate.
  should = true; reason = 'no_identity';
} else if (reg[key] || (legacyKey && reg[legacyKey])) {
  should = false;
  reason = reg[key] ? 'already_delivered' : 'already_delivered_legacy_lead_key';
} else {
  should = true; reason = 'first_alert';
}
return [{ json: { ...b, __alert_key: key, __should_alert: should,
                  __manual_thread, __alert_reason: reason,
                  __alert_registry_size: Object.keys(reg).length, __alert_pruned: pruned } }];