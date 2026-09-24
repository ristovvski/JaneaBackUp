"""WF-2R - Smartlead REPLY reconciler. The recovery path replies never had.

WHY THIS EXISTS
On 2026-08-04/05 WF-2 died of an instance-wide OOM and stayed down for 973 minutes. Ten replies
arrived in that window. Every one of their webhooks hit an inactive workflow, returned 404, and
created NO execution record - so there was nothing to retry, nothing to alert on, and nothing in
n8n that even knew they had existed. WF-2S recovers SENT events by polling statistics. Nothing
recovered replies. Measured cost of that asymmetry: 10 lost replies, including a Head of
Computational Drug Design answering "How about 5pm?" that sat unread for two days.

DESIGN - deliberately the same shape as WF-2S
Poll Smartlead, synthesise the webhook payload Smartlead should have sent, POST it to WF-2's own
webhook. One code path, one set of tests: the reply branch stays the only implementation, and
WF-2's Dedupe (event|campaign_id|sl_lead_id|timestamp) absorbs anything already processed.

SOURCE ENDPOINT - the choice is load-bearing, not incidental
  /campaigns/{id}/leads-statistics  ->  history[] entries with type == "REPLY"
NOT /campaigns/{id}/statistics.reply_time. Measured 2026-08-03..06 over all four campaigns:
statistics.reply_time reports 8 replies where leads-statistics reports 12 (-33%). It collapses
repeat replies onto one row per sequence step and omitted two first-replies outright
(pii-6f8f48e5@example.invalid, pii-135b4c7b@example.invalid). A reconciler built on the undercounting endpoint would
have missed the exact reply that triggered this whole investigation.

ONE CAMPAIGN PER CYCLE, TWO-RING ROTATION - also load-bearing
leads-statistics accepts NO server-side sort and NO time filter (probed live: `sort`,
`sent_time_start_date`, `reply_time_start_date` all HTTP 400), and its page order is arbitrary.
So "recent replies" cannot be read off page 1 - that is the banned unsorted-list-read class. Every
page of a campaign must be walked. Walking many campaigns in one cycle is what OOM'd this instance
before (8219 rows, 2026-07-30). So: ONE campaign per cycle. That also means every page item in a
cycle provably belongs to the same campaign - there is no zip to slip and no attribution to lose.

The FIRST version rotated over every non-archived campaign, on the assumption that meant "the four
Ai4 campaigns". Live measurement after activation: the pool is 114 campaigns (5 ACTIVE, 98
COMPLETED, 11 PAUSED), so a full sweep took 28.5 HOURS - inside the lookback, so nothing was lost,
but a reply could wait a day to be noticed, which defeats the point. Two rings instead:

  hot  = ACTIVE campaigns                       -> picked 3 cycles out of 4
  cold = non-ACTIVE created within cold_max_age_days -> picked 1 cycle out of 4

Measured today: hot 5 -> full sweep 1.7h; cold 20 -> full sweep 20h. Both comfortably inside the
2880-minute lookback. Campaigns older than the cutoff are EXCLUDED and their count is reported on
every cycle, because an unswept campaign that nobody mentions is indistinguishable from one that
is clean. Every cycle also recomputes both sweep times against the lookback and warns if either
ring has grown past it - the failure that hid here was an assumption about scale, so the workflow
now measures its own scale instead of trusting a comment.

CLAIM-AFTER-SUCCESS (WF-2S's S4 lesson, inherited deliberately)
The seen-store is READ in Find New Replies and WRITTEN only in Summary, and only for replays WF-2
actually accepted. Marking before the replay succeeds is how WF-2S permanently lost 100 sends to
one deploy window: observability that quietly gives up is worse than none.

FLOOR
`ignore_replies_before` is stamped at deploy time. Without it, the first cycle would replay every
reply inside the lookback - including the ten just backfilled by hand on 2026-08-06 - and WF-2's
dedupe would not stop them, because WF-2 never saw them in the first place.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from wf_item_guard import violations as item_violations

ERROR_WORKFLOW = "BbrXPABgOaaTJjD6"
SLACK_CRED = {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Slack WF-2"}}
SL_CRED = {"httpQueryAuth": {"id": "YXf5ez4pxDNd2g2B", "name": "Smartlead API"}}
N8N_CRED = {"httpHeaderAuth": {"id": "3dbKbrfihcGrOJck", "name": "n8n API (WF-2S watchdog)"}}

CONFIG = {
    "sl_api": "https://server.smartlead.ai/api/v1",
    "wf2_webhook": "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}",
    "sl_inbox_base": "https://app.smartlead.ai/app/master-inbox?leadMap=",
    "ops_channel": "C0B8GCVNR5W",
    # 48h - and the size is load-bearing, not padding. WF-2R replays INTO WF-2's webhook, so
    # during a WF-2 outage its own replays are rejected and (correctly) left unclaimed. The
    # recovery therefore happens AFTER WF-2 returns, which means the window must still contain
    # replies from the START of the outage. The observed OOM outage was 973 minutes; a 300-minute
    # window would have aged those ten replies out before WF-2 came back - the reconciler would
    # have looked healthy and recovered nothing. 2880 covers a 48h outage.
    # Widening is nearly free: the full page walk happens regardless, and claim-after-success
    # dedupe means a longer window cannot cause a replay, only more chances to catch one.
    "lookback_minutes": 2880,
    # owner-specified. Replies are low-volume (12 in the busiest 72h observed); this cap exists for
    # the pathological case, and it is REPORTED, never silent.
    "max_per_run": 20,
    # ONE. See the module docstring: this is the OOM guard, not a tuning knob.
    "max_campaigns_per_cycle": 1,
    # two-ring rotation. 3 hot cycles per 1 cold cycle: hot (5 ACTIVE) sweeps in 1.7h, cold
    # (20 campaigns created within the cutoff) in 20h - both inside the 2880-min lookback.
    "hot_cycles_per_cold": 3,
    # 180d -> cold ring of 20. Without a cutoff the ring is 109 and sweeps in 109h, i.e. LONGER
    # than the lookback, which would lose replies silently. Excluded campaigns are counted and
    # reported every cycle rather than quietly dropped.
    "cold_max_age_days": 180,
    "page_limit": 100,
    # A CEILING PER CYCLE, NOT A COVERAGE LIMIT. Raising this alone was the wrong fix: London-Valids
    # has 3,145 leads and a 2,000-lead ceiling left ~1,145 (36%) unreachable EVERY cycle for three
    # days. A bigger number just moves the cliff to the next oversized campaign. The real fix is
    # the resume cursor below: when a cycle cannot finish a campaign, it records where it stopped
    # and the NEXT cycle continues from there, so the walk always completes - it just takes more
    # than one cycle. The cap now only bounds memory per cycle.
    "max_pages_per_campaign": 35,
    # If a campaign still has not finished after this many consecutive cycles, stop treating it as
    # normal continuation and alarm with the UNSCANNED OFFSET RANGE named. Silent slow progress and
    # a stuck cursor look identical otherwise.
    "max_resume_rounds": 5,
    "synthetic_event_type": "EMAIL_REPLY",
    "campaign_allowlist": [],
    # stamped at deploy: never replay anything older than the moment this workflow went in
    "ignore_replies_before": None,
    "wf2_workflow_id": "jp7rum9Z0YDJkQWv",
    "wf2s_workflow_id": None,          # filled by --wf2s-id: mutual watchdog
    "wf2s_stale_minutes": 90,
    "n8n_api": "https://janea-systems-2025.app.n8n.cloud/api/v1",
}

SL = "={{ $('CONFIG').first().json.sl_api }}"


def node(nid, name, ntype, tv, pos, params, **extra):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype,
         "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def code(nid, name, pos, js):
    return node(nid, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js})


def slack_first(nid, name, pos, channel_key, text_expr):
    """.first() not .item - every node here is downstream of an HTTP fan-out, where a backward
    paired-item lookup is unavailable. Same reason WF-2S carries its own variant."""
    return {"parameters": {"select": "channel",
                           "channelId": {"__rl": True, "mode": "id",
                                         "value": "={{ $('CONFIG').first().json."
                                                  + channel_key + " }}"},
                           "text": text_expr, "otherOptions": {}},
            "id": nid, "name": name, "type": "n8n-nodes-base.slack",
            "typeVersion": 2.3, "position": pos,
            "credentials": SLACK_CRED, "onError": "continueRegularOutput"}


def if_true(nid, name, pos, expr, cid):
    return node(nid, name, "n8n-nodes-base.if", 2, pos,
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                            "typeValidation": "strict", "version": 1},
                                "conditions": [{"id": cid, "leftValue": expr, "rightValue": True,
                                                "operator": {"type": "boolean",
                                                             "operation": "true",
                                                             "singleValue": True}}],
                                "combinator": "and"}, "options": {}})


PICK_ONE = r"""
// ONE campaign per cycle, round-robin. See the module docstring: leads-statistics cannot be
// sorted or time-filtered server-side, so every page must be walked, and walking all four
// campaigns at once is what OOM'd this instance on 2026-07-30.
//
// S2 (inherited from WF-2S): /campaigns returns a bare ARRAY and n8n splits an array response
// into one item per element, so $json is campaign #1, NOT the list. Use $input.all().
const rows = $input.all().map(i => i.json)
  .flatMap(j => Array.isArray(j) ? j : (Array.isArray(j.data) ? j.data : [j]));
const CFG = $('CONFIG').first().json;
const allow = (CFG.campaign_allowlist ?? []).map(String);
const sd = $getWorkflowStaticData('global');

if (!rows.length) {
  throw new Error('WF-2R: /campaigns returned nothing parseable - refusing to report "idle"');
}

// A campaign can receive replies long after it stops SENDING, so ACTIVE-only would go blind on
// exactly the tail where late replies live - but rotating over ALL 114 non-archived campaigns
// takes 28.5h per sweep. Two rings: ACTIVE gets most cycles, a recency-bounded tail gets the rest.
const live = rows
  .filter(c => !['ARCHIVED', 'DRAFTED'].includes(String(c.status ?? '').toUpperCase()))
  .filter(c => !allow.length || allow.includes(String(c.id)));
const byId = (a, b) => String(a.id).localeCompare(String(b.id));   // stable order for the cursors
const isActive = (c) => String(c.status ?? '').toUpperCase() === 'ACTIVE';
const ageCut = Date.now() - Number(CFG.cold_max_age_days) * 86400000;

const hot = live.filter(isActive).sort(byId);
const coldAll = live.filter(c => !isActive(c));
const cold = coldAll.filter(c => {
  const cr = Date.parse(c.created_at ?? '');
  return Number.isFinite(cr) ? cr >= ageCut : true;   // unparseable date -> keep, never drop blind
}).sort(byId);
const excluded = coldAll.length - cold.length;

if (!hot.length && !cold.length) {
  return [{ json: { __none: true, __scanned: rows.length, __hot: 0, __cold: 0,
                    __excluded: excluded } }];
}

// RESUME TAKES PRIORITY OVER ROTATION. If the last cycle could not finish a campaign's page walk
// it left a cursor; continuing it now is the whole point - rotating away would leave the tail
// unscanned indefinitely, which is exactly how London-Valids stayed 36% blind for three days.
// hoisted: the sweep-time maths below needs it whichever branch picks the campaign
const ratio = Math.max(1, Number(CFG.hot_cycles_per_cold) || 3);
const resume = sd.__resume || null;
let c = null, ringName = null, startOffset = 0, cursor = null, resumeRound = 0;
if (resume && resume.campaign_id) {
  const still = live.find(x => String(x.id) === String(resume.campaign_id));
  if (still) {
    c = still;
    ringName = 'resume';
    startOffset = Number(resume.next_offset) || 0;
    resumeRound = Number(resume.round) || 1;
  } else {
    sd.__resume = null;              // campaign vanished (archived) - drop the cursor, do not stall
  }
}
if (!c) {
  // 3 hot cycles then 1 cold. The counter lives in staticData so the ratio holds across restarts.
  const tick = Number(sd.__tick ?? 0);
  sd.__tick = tick + 1;
  const wantCold = (tick % (ratio + 1)) === ratio;
  const ring = (wantCold && cold.length) ? cold : (hot.length ? hot : cold);
  ringName = ring === cold ? 'cold' : 'hot';
  const curKey = ringName === 'cold' ? '__rr_cold' : '__rr_hot';
  cursor = Number(sd[curKey] ?? 0) % ring.length;
  c = ring[cursor];
  sd[curKey] = (cursor + 1) % ring.length;
}

// measure our own scale instead of trusting a comment - the first version's whole defect was an
// assumption about pool size that nothing ever checked
const cycleMin = 15;
const hotSweepH = hot.length ? hot.length * ((ratio + 1) / ratio) * cycleMin / 60 : 0;
const coldSweepH = cold.length ? cold.length * (ratio + 1) * cycleMin / 60 : 0;
const lookbackH = Number(CFG.lookback_minutes) / 60;
const sweepOverrun = (hotSweepH > lookbackH) || (coldSweepH > lookbackH);

return [{ json: {
  campaign_id: c.id, campaign_name: c.name,
  campaign_status: String(c.status ?? '').toUpperCase(),
  start_offset: startOffset, resume_round: resumeRound,
  __scanned: rows.length, __ring: ringName, __cursor: cursor,
  __hot: hot.length, __cold: cold.length, __excluded: excluded,
  __hot_sweep_h: Math.round(hotSweepH * 10) / 10,
  __cold_sweep_h: Math.round(coldSweepH * 10) / 10,
  __sweep_overrun: sweepOverrun, __none: false } }];
"""

FIND_NEW = r"""
const CFG = $('CONFIG').first().json;
const sd = $getWorkflowStaticData('global');
// READ here, WRITTEN only in Summary and only for replays WF-2 accepted (WF-2S's S4 lesson).
const seen = sd.__reply_seen_v1 = sd.__reply_seen_v1 || {};

// exactly one campaign was polled this cycle, so every page item belongs to it - which is the
// whole reason for one-per-cycle: there is no zip to slip and no attribution to get wrong.
const camp = $('Pick Campaign').first().json;
const cutoff = Date.now() - Number(CFG.lookback_minutes) * 60000;
const floorTs = CFG.ignore_replies_before ? Date.parse(CFG.ignore_replies_before) : null;

// n8n's pagination emits one item per PAGE. hasMore on the LAST page tells us whether the walk
// was complete; a partial scan must never read as a clean one.
const pages = $input.all().map(i => i.json || {});
const lastPage = pages.length ? pages[pages.length - 1] : {};
const truncated = lastPage.hasMore === true;
const startOffset = Number(camp.start_offset) || 0;
const pageLimit = Number(CFG.page_limit) || 100;
const scannedTo = startOffset + pages.length * pageLimit;

// CONTINUATION, not truncation. A cycle that cannot finish records where it stopped; the next
// cycle resumes from exactly there (Pick Campaign gives resume priority over rotation), so the
// walk always completes even when one cycle cannot hold it. The cursor is cleared on completion.
const sdRounds = Number(camp.resume_round) || 0;
if (truncated) {
  sd.__resume = { campaign_id: camp.campaign_id, campaign_name: camp.campaign_name,
                  next_offset: scannedTo, round: sdRounds + 1 };
} else {
  sd.__resume = null;
}
// A cursor that keeps advancing is healthy. A campaign that STILL is not done after this many
// consecutive cycles is stuck, and the unscanned range gets named rather than implied.
const stuck = truncated && (sdRounds + 1) > (Number(CFG.max_resume_rounds) || 5);

const out = [];
let leads = 0, replies = 0, stale = 0, already = 0, floored = 0;
for (const page of pages) {
  for (const row of (page.data ?? [])) {
    leads++;
    for (const h of (row.history ?? [])) {
      if (String(h.type ?? '').toUpperCase() !== 'REPLY') continue;
      replies++;
      const t = Date.parse(h.time || 0);
      if (!Number.isFinite(t)) { stale++; continue; }
      if (floorTs && t < floorTs) { floored++; continue; }
      if (t < cutoff) { stale++; continue; }
      // identity of a REPLY, not of a lead: message_id when Smartlead gives one, else the
      // (campaign, lead, time) triple. stats_id alone is WRONG - a reply shares its stats_id
      // with the SENT step it answers, and one lead can reply twice (jonathan.brum did).
      const key = h.message_id
        ? ('M|' + h.message_id)
        : ('T|' + camp.campaign_id + '|' + row.lead_id + '|' + h.time);
      if (seen[key]) { already++; continue; }
      out.push({ campaign_id: camp.campaign_id, campaign_name: camp.campaign_name,
                 campaign_status: camp.campaign_status,
                 lead_id: row.lead_id, lead_email: row.to, sender_inbox: row.from ?? null,
                 email_lead_map_id: row.email_lead_map_id ?? null,
                 reply_time: h.time, subject: h.subject ?? null,
                 email_body: h.email_body ?? null, message_id: h.message_id ?? null,
                 stats_id: h.stats_id ?? null,
                 sequence_number: h.email_seq_number ?? null, __key: key });
    }
  }
}
out.sort((a, b) => String(a.reply_time).localeCompare(String(b.reply_time)));
const cap = Math.max(1, Number(CFG.max_per_run) || 20);
const dropped = Math.max(0, out.length - cap);
const batch = out.slice(0, cap);

const meta = { __campaign_id: camp.campaign_id, __campaign_name: camp.campaign_name,
               __pages: pages.length, __truncated: truncated, __leads: leads,
               __replies_seen: replies, __stale: stale, __already: already,
               __floored: floored, __dropped: dropped,
               __start_offset: startOffset, __scanned_to: scannedTo,
               __resume_round: sdRounds + (truncated ? 1 : 0), __stuck: stuck,
               __resuming: truncated,
               __ring: camp.__ring ?? null, __hot: camp.__hot ?? null,
               __cold: camp.__cold ?? null, __excluded: camp.__excluded ?? 0,
               __hot_sweep_h: camp.__hot_sweep_h ?? null,
               __cold_sweep_h: camp.__cold_sweep_h ?? null,
               __sweep_overrun: camp.__sweep_overrun === true,
               __cursor: camp.__cursor ?? null };
if (!batch.length) return [{ json: { __idle: true, ...meta } }];
return batch.map((b, i) => ({ json: { ...b, ...meta, __batch: batch.length, __first: i === 0 } }));
"""

BUILD_PAYLOAD = r"""
const CFG = $('CONFIG').first().json;
// runs ONCE FOR ALL ITEMS - map over every item. Reading $json here would replay exactly one
// reply per cycle regardless of how many were found (WF-2S's S3).
// The lead lookup is zipped by index and then PROVEN by email before its ids are used.
const rows = $('Find New Replies').all().map(i => i.json);
const out = [];
$input.all().forEach((it, i) => {
  const row = rows[i];
  if (!row) return;
  const r = it.json || {};
  const lead = (r && r.email) ? r : (r.data?.[0] ?? {});
  const same = lead.email
    && String(lead.email).trim().toLowerCase() === String(row.lead_email).trim().toLowerCase();
  // Smartlead's own category for this lead in this campaign - the baseline WF-2's classifier is
  // measured against. Only taken from a VERIFIED lookup; a slipped zip contributes nothing.
  const lcd = same ? ((lead.lead_campaign_data ?? [])
      .find(c => String(c.campaign_id) === String(row.campaign_id)) ?? null) : null;
  const mapId = row.email_lead_map_id
    ?? (lcd ? (lcd.campaign_lead_map_id ?? lcd.lead_campaign_map_id ?? null) : null);
  const body = {
    event_type: CFG.synthetic_event_type,
    campaign_id: row.campaign_id,
    campaign_name: row.campaign_name,
    campaign_status: row.campaign_status ?? null,
    // WF-2 Normalize reads sl_lead_id from lead_id first; leads-statistics gives it directly,
    // so unlike WF-2S this reconciler does not depend on the lookup succeeding to identify a lead
    lead_id: row.lead_id,
    sl_email_lead_map_id: mapId,
    app_url: mapId ? (CFG.sl_inbox_base + mapId) : null,
    to_email: row.lead_email,
    to_name: same ? ([lead.first_name, lead.last_name].filter(Boolean).join(' ') || null) : null,
    // leads-statistics carries the sending inbox as row.from - WF-2S could never supply this, and
    // it is what Forward Resolve maps to an owner. Without it every forward would go to default.
    from_email: row.sender_inbox,
    sequence_number: Number(row.sequence_number) || null,
    // drives WF-2's dedupe key (event|campaign_id|sl_lead_id|timestamp), so it MUST be the
    // reply's own time - a wall-clock stamp here would let the same reply through on every cycle
    timestamp: row.reply_time,
    event_timestamp: row.reply_time,
    reply_time: row.reply_time,
    subject: row.subject,
    reply_body: row.email_body,
    message_id: row.message_id,
    stats_id: row.stats_id,
    reply_category: lcd ? (lcd.lead_category_id ?? null) : null,
    lead_data: same ? { email: lead.email, first_name: lead.first_name ?? null,
                        last_name: lead.last_name ?? null,
                        company_name: lead.company_name ?? null, website: lead.website ?? null,
                        linkedin_profile: lead.linkedin_profile ?? null,
                        location: lead.location ?? null,
                        custom_fields: lead.custom_fields ?? {} } : undefined,
    __reconciled: true,
    __reconciled_by: 'WF-2R',
  };
  out.push({ json: { __body: body, __key: row.__key, __id_verified: !!same,
                     __reply_time: row.reply_time, __lead_email: row.lead_email,
                     __batch: row.__batch ?? 0, __dropped: row.__dropped ?? 0,
                     __truncated: row.__truncated === true, __pages: row.__pages ?? 0,
                     __campaign_name: row.__campaign_name ?? null,
                     __replies_seen: row.__replies_seen ?? 0 } });
});
return out;
"""

SUMMARY = r"""
const CFG = $('CONFIG').first().json;
const built = $('Build REPLY Payload').all().map(i => i.json);
const resp = $input.all().map(i => i.json || {});
const failed = resp.filter(r => r.error !== undefined).length;
const unverified = built.filter(b => b.__id_verified !== true).length;

// claim-after-success: a rejected replay stays unmarked and is picked up next cycle while it is
// still inside lookback_minutes. resp[i] pairs with built[i] because the HTTP node emits one item
// per input item, in order, even on failure (onError=continueRegularOutput).
const sd = $getWorkflowStaticData('global');
const seen = sd.__reply_seen_v1 = sd.__reply_seen_v1 || {};
built.forEach((b, i) => {
  if (!b || !b.__key) return;
  if (resp[i] && resp[i].error !== undefined) return;
  seen[b.__key] = b.__reply_time ?? new Date().toISOString();
});
// prune - a key is only useful while its reply is still inside lookback; keep a wide margin
const keepMs = Math.max(Number(CFG.lookback_minutes) * 60000 * 8, 86400000);
const now = Date.now();
let pruned = 0;
for (const k of Object.keys(seen)) {
  const t = Date.parse(seen[k]);
  if (Number.isFinite(t) && (now - t) > keepMs) { delete seen[k]; pruned++; }
}
const f = built[0] ?? {};
return [{ json: { __batch: built.length, __failed: failed, __unverified: unverified,
                  __marked: built.length - failed, __pruned: pruned,
                  __dropped: f.__dropped ?? 0, __truncated: f.__truncated === true,
                  __pages: f.__pages ?? 0, __campaign_name: f.__campaign_name ?? null,
                  __emails: built.map(b => b.__lead_email).filter(Boolean).slice(0, 10),
                  __store_size: Object.keys(seen).length } }];
"""

IDLE_REPORT = r"""
// An idle cycle is normally silent. It must NOT be silent when the scan itself was incomplete or
// when the cap dropped work - "nothing found" and "we did not look properly" are different
// answers and the digest already taught us what happens when they render identically.
// A ring that has grown until its sweep outlives the lookback loses replies SILENTLY - that is
// precisely the failure mode this workflow exists to end, so it is a reportable condition even on
// an otherwise idle cycle.
// Truncation alone is NO LONGER noteworthy - the resume cursor means the walk continues next
// cycle. What IS noteworthy: a campaign still unfinished after max_resume_rounds (stuck cursor),
// a dropped batch, or a rotation slower than the lookback. Alarming on ordinary continuation is
// what turned a real signal into three days of ignored cycle noise.
const j = $json;
const noisy = (j.__stuck === true) || (Number(j.__dropped) > 0)
           || (j.__sweep_overrun === true);
return [{ json: { ...j, __report: noisy } }];
"""

WF2S_WATCH = r"""
// Mutual watchdog. WF-2S watches WF-2H; nothing watched WF-2S, and nothing would watch WF-2R.
// Each 15-minute reconciler now watches the other, so a silent death has a witness either way.
const CFG = $('CONFIG').first().json;
const rows = (() => { const j = $json || {}; return j.data ?? (Array.isArray(j) ? j : []); })();
const last = rows.length ? rows[0] : null;
const t = last ? Date.parse(last.startedAt ?? last.stoppedAt ?? '') : NaN;
const maxAge = Number(CFG.wf2s_stale_minutes) * 60000;
const configured = !!CFG.wf2s_workflow_id;
// unreachable API or unparseable answer -> WARN. A watchdog that stays quiet when it cannot see
// is worse than no watchdog: it reads as "healthy".
const stale = configured && (!Number.isFinite(t) || (Date.now() - t) > maxAge);
return [{ json: { __wf2s_stale: stale, __wf2s_configured: configured,
                  __wf2s_last: Number.isFinite(t) ? new Date(t).toISOString() : null,
                  __wf2s_age_min: Number.isFinite(t)
                    ? Math.round((Date.now() - t) / 60000) : null } }];
"""

REPORT_TEXT = (
    "={{ (() => { const j = $json; const parts = []; "
    "parts.push('\\ud83d\\udd01 WF-2R replayed ' + j.__batch + ' repl' + "
    "(j.__batch === 1 ? 'y' : 'ies') + ' \\u00b7 ' + (j.__campaign_name || '?')); "
    "if (j.__emails && j.__emails.length) parts.push('> ' + j.__emails.join(', ')); "
    "if (j.__failed) parts.push('\\u26a0\\ufe0f ' + j.__failed + ' replay(s) REJECTED by WF-2 "
    "\\u2014 left unclaimed, will retry next cycle'); "
    "if (j.__unverified) parts.push('\\u26a0\\ufe0f ' + j.__unverified + ' lead lookup(s) "
    "unverified \\u2014 ids withheld, WF-2 falls back to email resolution'); "
    "if (j.__dropped) parts.push('\\u26a0\\ufe0f cap dropped ' + j.__dropped + ' repl(y/ies) "
    "this cycle \\u2014 they stay unclaimed and return next cycle'); "
    "if (j.__resuming && !j.__stuck) parts.push('\\u23ed\\ufe0f partial pass \\u2014 scanned "
    "offsets ' + j.__start_offset + '\\u2013' + j.__scanned_to + '; resuming from ' + "
    "j.__scanned_to + ' next cycle (round ' + j.__resume_round + ')'); "
    "if (j.__stuck) parts.push('\\ud83d\\uded1 SCAN STUCK \\u2014 ' + (j.__campaign_name || '?') + "
    "' still unfinished after ' + j.__resume_round + ' cycles. UNSCANNED RANGE: offset ' + "
    "j.__scanned_to + ' onward. Replies beyond that offset are NOT being seen.'); "
    "return parts.join('\\n'); })() }}")

IDLE_TEXT = (
    "={{ (() => { const j = $json; const parts = ['\\u26a0\\ufe0f WF-2R cycle found no new "
    "replies, but the cycle was not clean \\u00b7 ' + (j.__campaign_name || '?')]; "
    "if (j.__stuck) parts.push('\\ud83d\\uded1 SCAN STUCK \\u2014 ' + (j.__campaign_name || '?') + "
    "' still unfinished after ' + j.__resume_round + ' cycles. UNSCANNED RANGE: offset ' + "
    "j.__scanned_to + ' onward \\u2014 replies beyond that offset are NOT being seen. "
    "Raise max_pages_per_campaign or investigate the cursor.'); "
    "if (j.__dropped) parts.push('cap dropped ' + j.__dropped); "
    "if (j.__sweep_overrun) parts.push('\\ud83d\\uded1 ROTATION TOO SLOW \\u2014 hot ring sweeps "
    "in ' + j.__hot_sweep_h + 'h, cold ring in ' + j.__cold_sweep_h + 'h, but lookback is only ' "
    "+ ($('CONFIG').first().json.lookback_minutes / 60) + 'h. Replies WILL age out unseen.'); "
    "return parts.join('\\n'); })() }}")

WF2S_WARN_TEXT = (
    "={{ '\\ud83d\\udea8 WF-2S has not executed for ' + ($json.__wf2s_age_min ?? '?') + "
    "' min (threshold ' + $('CONFIG').first().json.wf2s_stale_minutes + '). SENT reconciliation "
    "is the only source of SENT events \\u2014 if it is dead, sends are going unobserved.' }}")


def build(wf2s_id=None, floor=None):
    CONFIG["wf2s_workflow_id"] = wf2s_id
    CONFIG["ignore_replies_before"] = floor or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    N, C = [], {}
    N.append(node("r-cron", "Every 15 min", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
                  {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}))
    N.append(node("r-cfg", "CONFIG", "n8n-nodes-base.set", 3.4, [200, 0],
                  {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2, ensure_ascii=False),
                   "options": {}}))
    N.append(node("r-camps", "SL Campaigns", "n8n-nodes-base.httpRequest", 4.2, [400, 0],
                  {"method": "GET", "url": SL + "{{ '/campaigns' }}", "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}, "authentication": "genericCredentialType",
                   "genericAuthType": "httpQueryAuth"},
                  credentials=SL_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("r-pick", "Pick Campaign", [600, 0], PICK_ONE))
    N.append(if_true("r-ifcamp", "IF Have Campaign", [800, 0],
                     "={{ $json.__none !== true }}", "r-c0"))
    N.append(code("r-nocamp", "NoOp No Campaign", [1000, 160],
                  "return [{ json: { idle: true, reason: 'no campaign in pool' } }];"))
    # pagination: leads-statistics has no sort and no time filter, so every page must be walked.
    # n8n emits one ITEM PER PAGE; completion is driven by the API's own hasMore flag.
    N.append(node("r-stats", "SL Leads Statistics", "n8n-nodes-base.httpRequest", 4.2, [1000, -80],
                  {"method": "GET",
                   "url": SL + "{{ '/campaigns/' + ($json.campaign_id || 0) + "
                               "'/leads-statistics' }}",
                   "sendQuery": True,
                   "queryParameters": {"parameters": [
                       {"name": "limit",
                        "value": "={{ $('CONFIG').first().json.page_limit }}"},
                       # resume from where the previous cycle stopped, not always from zero
                       {"name": "offset",
                        "value": "={{ $('Pick Campaign').first().json.start_offset || 0 }}"}]},
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "authentication": "genericCredentialType",
                   "genericAuthType": "httpQueryAuth",
                   "options": {"pagination": {"pagination": {
                       "paginationMode": "updateAParameterInEachRequest",
                       "parameters": {"parameters": [
                           {"type": "qs", "name": "offset",
                            "value": "={{ ($('Pick Campaign').first().json.start_offset || 0)"
                                     " + $pageCount"
                                     " * $('CONFIG').first().json.page_limit }}"}]},
                       "paginationCompleteWhen": "other",
                       "completeExpression": "={{ $response.body.hasMore !== true }}",
                       "limitPagesFetched": True,
                       "maxRequests":
                           "={{ $('CONFIG').first().json.max_pages_per_campaign }}"}}}},
                  credentials=SL_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=1500,
                  onError="continueRegularOutput"))
    N.append(code("r-find", "Find New Replies", [1200, -80], FIND_NEW))
    N.append(if_true("r-ifrep", "IF Has Replies", [1400, -80],
                     "={{ $json.__idle !== true }}", "r-c1"))
    N.append(code("r-idle", "Idle Eval", [1600, 120], IDLE_REPORT))
    N.append(if_true("r-ifidlerep", "IF Idle Noisy", [1800, 120],
                     "={{ $json.__report === true }}", "r-c2"))
    N.append(slack_first("r-idleslack", "WF-2R Idle Warn", [2000, 60], "ops_channel", IDLE_TEXT))
    N.append(code("r-idleok", "NoOp Idle Clean", [2000, 220],
                  "return [{ json: { idle: true, clean: true } }];"))
    N.append(node("r-lead", "SL Lead Lookup", "n8n-nodes-base.httpRequest", 4.2, [1600, -80],
                  {"method": "GET",
                   "url": SL + "{{ '/leads?email=' + encodeURIComponent($json.lead_email) }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}, "authentication": "genericCredentialType",
                   "genericAuthType": "httpQueryAuth"},
                  credentials=SL_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("r-payload", "Build REPLY Payload", [1800, -80], BUILD_PAYLOAD))
    N.append(node("r-post", "Replay Into WF-2", "n8n-nodes-base.httpRequest", 4.2, [2000, -80],
                  {"method": "POST", "url": "={{ $('CONFIG').first().json.wf2_webhook }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}, "sendBody": True, "specifyBody": "json",
                   "jsonBody": "={{ JSON.stringify($json.__body) }}"},
                  retryOnFail=True, maxTries=3, waitBetweenTries=2000,
                  onError="continueRegularOutput"))
    N.append(code("r-sum", "Summary", [2200, -80], SUMMARY))
    N.append(slack_first("r-slack", "WF-2R Report", [2400, -80], "ops_channel", REPORT_TEXT))

    # ---- mutual watchdog: WF-2R watches WF-2S. Runs on EVERY cycle, including idle ones.
    N.append(node("r-wsw", "WF-2S Watch", "n8n-nodes-base.httpRequest", 4.2, [400, 300],
                  {"method": "GET",
                   # unfiltered /executions omits crashed and under-returns successes (documented
                   # project-wide bug class) -- WF-2S's own mirror node (WF-2H Watch, build_wf2s.py)
                   # already gets this right with status=success&limit=1; this one didn't. Fixed
                   # 2026-08-26 (auditor P2 sweep) to match -- WF-2R is currently inactive so this
                   # was never live-wrong, but would have been the moment it activated.
                   "url": "={{ $('CONFIG').first().json.n8n_api }}"
                          "{{ '/executions?workflowId=' + "
                          "($('CONFIG').first().json.wf2s_workflow_id || '') + '&status=success&limit=1' }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Accept",
                                                        "value": "application/json"}]},
                   "options": {}, "authentication": "genericCredentialType",
                   "genericAuthType": "httpHeaderAuth"},
                  credentials=N8N_CRED, retryOnFail=True, maxTries=2, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("r-wswe", "WF-2S Watch Eval", [600, 300], WF2S_WATCH))
    N.append(if_true("r-wswif", "IF WF-2S Stale", [800, 300],
                     "={{ $json.__wf2s_stale === true }}", "r-c3"))
    N.append(slack_first("r-wswslack", "Ops Warn WF-2S Stale", [1000, 250], "ops_channel",
                         WF2S_WARN_TEXT))
    N.append(code("r-wswok", "NoOp WF-2S OK", [1000, 380],
                  "return [{ json: { wf2s: 'fresh' } }];"))

    C["Every 15 min"] = {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]}
    C["CONFIG"] = {"main": [[{"node": "SL Campaigns", "type": "main", "index": 0},
                             {"node": "WF-2S Watch", "type": "main", "index": 0}]]}
    C["SL Campaigns"] = {"main": [[{"node": "Pick Campaign", "type": "main", "index": 0}]]}
    C["Pick Campaign"] = {"main": [[{"node": "IF Have Campaign", "type": "main", "index": 0}]]}
    C["IF Have Campaign"] = {"main": [[{"node": "SL Leads Statistics", "type": "main", "index": 0}],
                                      [{"node": "NoOp No Campaign", "type": "main", "index": 0}]]}
    C["SL Leads Statistics"] = {"main": [[{"node": "Find New Replies", "type": "main", "index": 0}]]}
    C["Find New Replies"] = {"main": [[{"node": "IF Has Replies", "type": "main", "index": 0}]]}
    C["IF Has Replies"] = {"main": [[{"node": "SL Lead Lookup", "type": "main", "index": 0}],
                                    [{"node": "Idle Eval", "type": "main", "index": 0}]]}
    C["Idle Eval"] = {"main": [[{"node": "IF Idle Noisy", "type": "main", "index": 0}]]}
    C["IF Idle Noisy"] = {"main": [[{"node": "WF-2R Idle Warn", "type": "main", "index": 0}],
                                   [{"node": "NoOp Idle Clean", "type": "main", "index": 0}]]}
    C["SL Lead Lookup"] = {"main": [[{"node": "Build REPLY Payload", "type": "main", "index": 0}]]}
    C["Build REPLY Payload"] = {"main": [[{"node": "Replay Into WF-2", "type": "main", "index": 0}]]}
    C["Replay Into WF-2"] = {"main": [[{"node": "Summary", "type": "main", "index": 0}]]}
    C["Summary"] = {"main": [[{"node": "WF-2R Report", "type": "main", "index": 0}]]}
    C["WF-2S Watch"] = {"main": [[{"node": "WF-2S Watch Eval", "type": "main", "index": 0}]]}
    C["WF-2S Watch Eval"] = {"main": [[{"node": "IF WF-2S Stale", "type": "main", "index": 0}]]}
    C["IF WF-2S Stale"] = {"main": [[{"node": "Ops Warn WF-2S Stale", "type": "main", "index": 0}],
                                    [{"node": "NoOp WF-2S OK", "type": "main", "index": 0}]]}

    return {"name": "WF-2R Smartlead REPLY Reconciler", "nodes": N, "connections": C,
            "active": False,
            "settings": {"executionOrder": "v1", "errorWorkflow": ERROR_WORKFLOW,
                         "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all"}}


def validate(wf):
    e, names = [], [n["name"] for n in wf["nodes"]]
    e.extend(item_violations(wf))
    if len(names) != len(set(names)):
        e.append("duplicate node names")
    ids = [n["id"] for n in wf["nodes"]]
    if len(ids) != len(set(ids)):
        e.append("duplicate node ids")
    known = set(names)
    for src, conn in wf["connections"].items():
        if src not in known:
            e.append(f"connection from unknown node {src!r}")
        for branch in conn.get("main", []):
            for c in branch or []:
                if c["node"] not in known:
                    e.append(f"{src} -> unknown node {c['node']!r}")
    cfg = json.loads(next(n for n in wf["nodes"] if n["name"] == "CONFIG")
                     ["parameters"]["jsonOutput"])
    # the endpoint choice is the point of this workflow - assert it, do not assume it
    stats_node = next(n for n in wf["nodes"] if n["name"] == "SL Leads Statistics")
    if "leads-statistics" not in json.dumps(stats_node["parameters"]):
        e.append("WF-2R must poll leads-statistics, not statistics")
    if "'/statistics'" in json.dumps(stats_node["parameters"]):
        e.append("WF-2R must not poll the undercounting /statistics endpoint")
    if int(cfg["max_per_run"]) != 20:
        e.append(f"max_per_run must be 20 (owner spec), got {cfg['max_per_run']}")
    if int(cfg["max_campaigns_per_cycle"]) != 1:
        e.append("max_campaigns_per_cycle must be 1 (OOM guard)")
    if not cfg.get("cold_max_age_days"):
        e.append("cold_max_age_days must be set - an unbounded cold ring sweeps in 109h, longer "
                 "than the lookback, and loses replies silently")
    # measured pool today: hot 5, cold 20 at a 180d cutoff, 15-min cycles
    ratio = int(cfg.get("hot_cycles_per_cold") or 3)
    for name, size in (("hot", 5), ("cold", 20)):
        mult = ((ratio + 1) / ratio) if name == "hot" else (ratio + 1)
        sweep_min = size * mult * 15
        if sweep_min > int(cfg["lookback_minutes"]):
            e.append(f"{name} ring sweeps in {sweep_min / 60:.1f}h at today's size ({size}), "
                     f"longer than the {int(cfg['lookback_minutes']) / 60:.0f}h lookback")
    # the reconciler recovers only AFTER WF-2 is back, so its window must outlive an outage
    if int(cfg["lookback_minutes"]) <= 973:
        e.append(f"lookback_minutes={cfg['lookback_minutes']} does not cover the observed "
                 "973-minute outage - those replies would age out before WF-2 returned")
    if not cfg.get("ignore_replies_before"):
        e.append("ignore_replies_before must be stamped - otherwise the first cycle replays "
                 "the manual 2026-08-06 backfill")
    if not cfg.get("max_resume_rounds"):
        e.append("max_resume_rounds must be set - a stuck cursor and slow progress are otherwise "
                 "indistinguishable")
    pick = next(n for n in wf["nodes"] if n["name"] == "Pick Campaign")["parameters"]["jsCode"]
    if "__resume" not in pick or "resume priority" not in pick.lower().replace("takes ", ""):
        if "__resume" not in pick:
            e.append("Pick Campaign must honour the resume cursor, else an oversized campaign "
                     "never finishes its walk")
    stats = json.dumps(next(n for n in wf["nodes"]
                            if n["name"] == "SL Leads Statistics")["parameters"])
    if "start_offset" not in stats:
        e.append("SL Leads Statistics must start from the resume offset, not always 0")
    # claim-after-success: the store must not be written in Find New Replies
    find = next(n for n in wf["nodes"] if n["name"] == "Find New Replies")["parameters"]["jsCode"]
    if "__resume" not in find:
        e.append("Find New Replies must set/clear the resume cursor")
    if "seen[" in find.replace("if (seen[", "").replace("seen[key]", ""):
        e.append("Find New Replies appears to WRITE the seen store - claim must happen in Summary")
    summ = next(n for n in wf["nodes"] if n["name"] == "Summary")["parameters"]["jsCode"]
    if "error !== undefined" not in summ:
        e.append("Summary must skip claiming replays WF-2 rejected")
    # no backward .item anywhere (the WF-2S S1 class)
    for n in wf["nodes"]:
        js = (n.get("parameters") or {}).get("jsCode") or ""
        if "').item" in js:
            e.append(f"{n['name']}: backward .item lookup inside a fan-out region")
    if wf.get("active") is not False:
        e.append("must be built inactive")
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="WF-2R Smartlead REPLY Reconciler - built.json")
    ap.add_argument("--wf2s-id", default=None)
    ap.add_argument("--floor", default=None)
    a = ap.parse_args()
    wf = build(a.wf2s_id, a.floor)
    errs = validate(wf)
    print(f"nodes={len(wf['nodes'])} connections={len(wf['connections'])}")
    if errs:
        print("VALIDATION FAILED:")
        for x in errs:
            print("  -", x)
        sys.exit(1)
    print("validation: clean")
    Path(a.out).write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
