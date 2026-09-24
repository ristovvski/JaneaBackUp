// The two standing rules, as pure functions. Embedded verbatim into both WF-1 and WF-2 by
// build_rules.py and required directly by the statics, so there is one implementation.
//
// RULE 1 — ARCHIVED LEAD = IGNORE.
//   If the identity's campaign lead is archived, the event passes through silently: no new lead,
//   no activity, no label, no post anywhere. Detection needs an ARCHIVED-VISIBLE lookup, because
//   /v1/leads and /v1/leads?person_id= cannot see archived leads at all - archived_status is
//   ignored on both. That blindness is why Person-b093030e read as "no lead" and got a second alert:
//   his lead existed, archived, and the list endpoint returned zero rows.
//   Only /v1/leads/search, /api/v2/leads/search and /v1/itemSearch reach archived leads, and all
//   three are term-based - so the term is an INDEX, and the match is confirmed by person id.
//   A name is never the thing that decides.
//
// RULE 2 — NON-CAMPAIGN PERSON = NEVER IN #lead-processing.
//   Only Smartlead/HeyReach campaign members reach that channel. An event with no campaign gets
//   no post of any kind - not #lead-processing, not #alerts. (The pre-existing 2026-08-28 ruling
//   stands: a manual thread still gets its silent CRM activity. Rule 2 governs POSTS.)
//
// STABLE KEYS — suppression and dedupe keys derive from person_id or the canonical identity,
//   NEVER from lead visibility. Keying on lead_id meant archiving a lead silently reset its own
//   suppression: Arnab's key moved from 'L8694ea30…|572715' to 'P85903|572715' and the gate
//   called a second message a first alert.

function arSlug(u) {
  var m = String(u == null ? '' : u).match(/linkedin\.com\/in\/([^/?#\s]+)/i);
  return m ? m[1].toLowerCase().replace(/\/+$/, '') : null;
}

function arCanon(s) {
  return String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
}

// Parse an archived-visible lead search response into campaign-scoped rows.
// POSITIVE shape check: a real response has data.items as an array. An error item, or the
// documented echo-the-input shape, must read as "could not look" - never as "nothing archived".
function arParseProbe(resp, campaignName, campaignId, campaignFieldKey) {
  var items = null;
  if (resp && resp.data && Array.isArray(resp.data.items)) items = resp.data.items;
  else if (resp && Array.isArray(resp.items)) items = resp.items;
  if (items === null) {
    return { ok: false, reason: (resp && resp.error && (resp.error.message || resp.error))
                               || 'no data.items array', rows: [], saturated: false };
  }
  var want = arCanon(campaignName);
  var pre = campaignId == null ? null : (String(campaignId) + ' - ');
  var rows = [];
  for (var i = 0; i < items.length; i++) {
    var it = items[i] && items[i].item ? items[i].item : items[i];
    if (!it) continue;
    var title = String(it.title == null ? '' : it.title);
    var cfs = it.custom_fields;
    var byField = false;
    if (Array.isArray(cfs)) {
      for (var k = 0; k < cfs.length; k++) if (arCanon(cfs[k]) === want) byField = true;
    } else if (cfs && campaignFieldKey && arCanon(cfs[campaignFieldKey]) === want) {
      byField = true;
    }
    var byPrefix = pre ? title.indexOf(pre) === 0 : false;
    if (!want && !pre) continue;
    if (!byField && !byPrefix) continue;
    rows.push({ id: it.id, title: title, is_archived: it.is_archived === true,
                person_id: (it.person && it.person.id != null) ? it.person.id : null });
  }
  return { ok: true, reason: null, rows: rows, saturated: items.length >= 100 };
}

// The verdict for one branch. personId is whatever that branch actually resolved.
function arVerdict(probe, personId) {
  if (!probe || probe.ok !== true) {
    // FAIL OPEN, deliberately and narrowly: an unreadable probe must not silence a real reply.
    // It is reported instead, so "we could not look" never renders as "nothing archived".
    return { block: false, why: 'probe_unreadable', archived_ids: [], probe_ok: false };
  }
  var rows = probe.rows || [];
  var pid = personId == null ? null : String(personId);
  var mineArch = [], anyArch = [], mineLive = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var samePerson = pid !== null && r.person_id != null && String(r.person_id) === pid;
    if (r.is_archived) {
      anyArch.push(r.id);
      if (samePerson) mineArch.push(r.id);
    } else if (samePerson) {
      mineLive.push(r.id);
    }
  }
  // A LIVE campaign lead for this very person wins: the lead is usable, so this is the ordinary
  // path and nothing is ignored, even if some namesake's lead is archived.
  if (mineLive.length) {
    return { block: false, why: 'live_lead_for_this_person', archived_ids: mineArch,
             live_ids: mineLive, probe_ok: true };
  }
  if (mineArch.length) {
    return { block: true, why: 'archived_campaign_lead_for_this_person',
             archived_ids: mineArch, live_ids: [], probe_ok: true };
  }
  // No person id to confirm with (resolution failed) but the campaign does have an archived lead
  // under this search term. Ignoring is the safe side of rule 1: the alternative is creating a
  // duplicate of a lead somebody archived on purpose.
  if (pid === null && anyArch.length) {
    return { block: true, why: 'archived_campaign_lead_unconfirmed_person',
             archived_ids: anyArch, live_ids: [], probe_ok: true };
  }
  return { block: false, why: 'no_archived_campaign_lead', archived_ids: [], live_ids: [],
           probe_ok: true };
}

// RULE 2: is this event attributable to a campaign at all?
function arIsCampaign(campaign) {
  if (!campaign) return false;
  var id = campaign.id == null ? null : campaign.id;
  var name = arCanon(campaign.name);
  return !!(id || name);
}

// STABLE suppression key. Never a lead id.
//   order: pipedrive person id -> canonical provider identity -> null
function arStableKey(personId, identity, campaignId) {
  var who = null;
  if (personId != null && String(personId) !== '') who = 'P' + String(personId);
  else {
    var ident = identity || {};
    var cand = arSlug(ident.linkedin_url) || ident.member_id || ident.public_id
            || (ident.email ? String(ident.email).trim().toLowerCase() : null);
    if (cand) who = 'K' + String(cand);
  }
  if (!who) return null;
  return who + '|' + String(campaignId == null ? 'nocamp' : campaignId);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { arSlug: arSlug, arCanon: arCanon, arParseProbe: arParseProbe,
                     arVerdict: arVerdict, arIsCampaign: arIsCampaign, arStableKey: arStableKey };
}
