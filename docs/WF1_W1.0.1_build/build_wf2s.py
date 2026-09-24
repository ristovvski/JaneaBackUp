"""WF-2S - Smartlead SENT reconciler. The PRIMARY source of SENT events.

WHY THIS EXISTS
Smartlead does not deliver `EMAIL_SENT` to our webhook entries. Measured, four times, across two
separate entries (703611 and the recreated 704352), each with "First email sent" ticked, each with
the send confirmed via `/campaigns/{id}/statistics`, each with a 12-minute window:
    15:18:22  15:32:08  15:56:23  17:08:17   -> zero webhook deliveries
The same entries deliver `EMAIL_REPLY` in ~36 seconds, and Make's entry (151526) demonstrably DOES
receive `EMAIL_SENT` (Pipedrive lead for Person-6fe1a561 created 2.7s after her send). So the capability
exists account-wide; the delivery to our entries does not.

DESIGN
Rather than duplicate the SENT branch's logic (person -> org -> lead with the title convention), this
workflow SYNTHESISES the webhook payload Smartlead should have sent and POSTs it to WF-2's own
webhook. Consequences worth stating:
  * one code path, one set of tests - the SENT branch stays the only implementation
  * WF-2's Dedupe keys on campaign_id + sl_lead_id, so re-polling the same send is naturally
    idempotent even if this workflow's own state is lost
  * `/statistics` was visible within ~3 minutes for every one of the four sends above, so the
    latency cost over a working webhook is small

CAPS ARE REPORTED, NOT SILENT: `max_per_run` bounds a single cycle; anything dropped is logged and
posted to ops, because a quiet truncation would read as "all caught up".

AUTH FOLLOW-UP (needed only when the webhook secret is armed)
WF-2's Verify Secret checks a `secret_key` in the BODY. n8n credentials can inject HEADERS but not
body fields, so a replayer cannot carry the real secret without embedding it in this workflow's JSON
(forbidden - static AU4). When the secret is armed, add a header-based replay credential:
`X-Replay-Auth` validated against `CONFIG.replay_secret_sha256` in WF-2, injected here from an
httpHeaderAuth credential. Until then the secret is unarmed and accept-all, so replay works as is.
"""
import argparse
import json
import sys
from pathlib import Path

from wf_item_guard import violations as item_violations
from build_wf2_branches import slack as _wf2_slack  # noqa: F401  (shape reference only)


def slack_first(nid, name, pos, channel_key, text_expr, cred):
    """Pairing-free Slack node.

    The shared WF-2 helper resolves its channel with a backward .item lookup. That works in
    WF-2 (its ops posts are observed live), but every node in WF-2S sits downstream of an
    HTTP fan-out where paired items are unavailable - so this one reads CONFIG with .first().
    A local variant rather than a change to the shared helper: WF-2 is live and has no such
    defect, and rewiring 20+ of its nodes to fix a problem it does not have is not a trade
    worth making.
    """
    return {"parameters": {"select": "channel",
                           "channelId": {"__rl": True, "mode": "id",
                                         "value": "={{ $('CONFIG').first().json."
                                                  + channel_key + " }}"},
                           "text": text_expr, "otherOptions": {}},
            "id": nid, "name": name, "type": "n8n-nodes-base.slack",
            "typeVersion": 2.3, "position": pos,
            "credentials": cred, "onError": "continueRegularOutput"}

ERROR_WORKFLOW = "BbrXPABgOaaTJjD6"
SLACK_CRED = {"slackApi": {"id": "F9CCCbTx8KB5b2OO", "name": "Slack WF-2"}}
SL_CRED = {"httpQueryAuth": {"id": "YXf5ez4pxDNd2g2B", "name": "Smartlead API"}}
# read-only n8n API key, used ONLY to ask when WF-2H last succeeded
N8N_CRED = {"httpHeaderAuth": {"id": "3dbKbrfihcGrOJck", "name": "n8n API (WF-2S watchdog)"}}

CONFIG = {
    "sl_api": "https://server.smartlead.ai/api/v1",
    "wf2_webhook": "https://janea-systems-2025.app.n8n.cloud/webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}",
    "ops_channel": "C0B8GCVNR5W",
    # Sized from the first live cycle: 4 ACTIVE Ai4 campaigns produced 39 fresh sends in one
    # 15-minute window, so a cap of 25 dropped 14 - and with a 60-minute lookback those 14 would
    # have aged out before the next cycle claimed them, i.e. permanently unobserved. A longer
    # lookback is cheap because dedupe is on stats_id: widening the window cannot cause a replay,
    # it only gives a dropped send more cycles to be picked up.
    "lookback_minutes": 180,
    "max_per_run": 100,
    # the event name WF-2's discriminator expects, and the one Make receives from Smartlead
    "synthetic_event_type": "EMAIL_SENT",
    # Empty = every ACTIVE campaign (normal operation). Non-empty SCOPES the reconciler to those
    # campaign ids, which exists for one purpose: a WRITE_MODE=live window. Wide open in live mode
    # this workflow would replay a 180-minute backlog of already-processed sends as fresh Pipedrive
    # person+org+lead creations - duplicating what Make did hours ago. Scoping is reported, never
    # silent, because a narrowed reconciler must not read like a full one.
    "campaign_allowlist": [],
    # OOM insurance, independent of whether the predicate above is right. The S5 updated_at rule
    # pulled 23 campaigns / 8219 statistics rows into one cycle and is the prime suspect for the
    # worker OOM on 2026-07-30 09:45 that also killed a concurrent WF-1 execution. A cap cannot
    # prevent a bad predicate, but it bounds the blast radius - and it is REPORTED, never silent.
    "max_campaigns_per_cycle": 8,
    # WF-2H is a daily workflow: it cannot notice its own failure, and it failed every run for its
    # entire life without anyone seeing it. This 15-minute workflow watches it instead.
    "wf2h_workflow_id": "nK3yIOqRcBearV8s",
    "wf2h_stale_hours": 48,
    # A live window is a promise to revert. On 2026-07-31 that promise was kept for 72 hours instead
    # of minutes, and low-confidence prospect replies were forwarded to a personal Gmail the whole
    # time. A promise is not a control - this is the control.
    "wf2_workflow_id": "jp7rum9Z0YDJkQWv",
    "write_mode_max_hours": 2,
    "n8n_api": "https://janea-systems-2025.app.n8n.cloud/api/v1",
}

# .first() not .item: CONFIG is a singleton, and .item would demand paired-item resolution
# back through the HTTP fan-out below, which is exactly what killed cycle 1 (exec 11764).
SL = "={{ $('CONFIG').first().json.sl_api }}"


def node(nid, name, ntype, tv, pos, params, **extra):
    n = {"parameters": params, "id": nid, "name": name, "type": ntype,
         "typeVersion": tv, "position": pos}
    n.update(extra)
    return n


def code(nid, name, pos, js):
    return node(nid, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js})


def sl_get(nid, name, pos, tail):
    return node(nid, name, "n8n-nodes-base.httpRequest", 4.2, pos,
                {"method": "GET", "url": SL + tail, "sendHeaders": True,
                 "headerParameters": {"parameters": [{"name": "Content-Type",
                                                      "value": "application/json"}]},
                 "options": {},
                 "authentication": "genericCredentialType", "genericAuthType": "httpQueryAuth"},
                credentials=SL_CRED, retryOnFail=True, maxTries=3, waitBetweenTries=1000,
                onError="continueRegularOutput")


PICK_ACTIVE = r"""
// only ACTIVE campaigns can produce new sends; polling the other 112 would be waste.
// S2: /campaigns returns a bare ARRAY, and n8n splits an array response into one item per
// element (116 of them, verified in exec 11764) - so $json is campaign #1, NOT the array.
// Reading $json here found zero ACTIVE campaigns and idled forever, silently. Use $input.all().
const rows = $input.all().map(i => i.json)
  .flatMap(j => Array.isArray(j) ? j : (Array.isArray(j.data) ? j.data : [j]));
const CFG = $('CONFIG').first().json;
const allow = (CFG.campaign_allowlist ?? []).map(String);
// S5 (v2): a campaign flips to COMPLETED the moment its last lead is sent, so polling ACTIVE
// alone loses the FINAL batch of every campaign - and SENT arrives only through this workflow.
//
// v1 used `updated_at within lookback`. That was WRONG on this platform: Smartlead bumps
// updated_at in BULK (all four ACTIVE campaigns carry the identical timestamp 07:00:21.004Z), so
// the rule dragged in up to 23 long-finished campaigns - 5.75x the API calls and 9.2x the rows,
// every one of them stale and discarded.
//
// v2 asks the only question that actually matters: was this campaign ACTIVE when we last looked?
// If yes and it is not ACTIVE now, it finished during the gap and its tail is exactly what we came
// for. State is ours, not Smartlead's, so no bulk timestamp can inflate it.
const sd = $getWorkflowStaticData('global');
const prevActive = new Set((sd.__prev_active_ids ?? []).map(String));
const nowActiveIds = rows.filter(c => String(c.status).toUpperCase() === 'ACTIVE')
                         .map(c => String(c.id));
// S5 (v3): v2 caught a campaign we had SEEN ACTIVE. It could not catch one whose entire ACTIVE
// life fell between two polls - matrix T2 started and completed at 07:10:30, between the 07:00 and
// 07:15 cycles, so it was never in prevActive and its SENT was never reconciled.
// created_at closes that hole and is safe where updated_at was not: it is IMMUTABLE, so Smartlead's
// bulk timestamp bumps (which dragged 23 dead campaigns into a cycle under v1) cannot touch it.
const createdCut = Date.now() - Number(CFG.lookback_minutes) * 60000;
const active = rows.filter(c => {
  const isActive = String(c.status).toUpperCase() === 'ACTIVE';
  if (isActive) return true;
  if (prevActive.has(String(c.id))) return true;   // was ACTIVE last cycle -> catch its tail
  const cr = Date.parse(c.created_at ?? '');       // born since the last poll -> never seen ACTIVE
  return Number.isFinite(cr) && cr >= createdCut;
}).filter(c => !allow.length || allow.includes(String(c.id)));
// record for the next cycle BEFORE any cap is applied, so capping cannot lose a tail
sd.__prev_active_ids = nowActiveIds;
// a poll that finds no campaigns at all is a broken poll, not an idle account - say so loudly
if (!rows.length) {
  throw new Error('WF-2S: /campaigns returned nothing parseable - refusing to report "idle"');
}
if (!active.length) return [{ json: { __none: true, __scanned: rows.length,
                                     __allowlist: allow.length, __campaign_overflow: 0 } }];
// hard cap: bound the memory a single cycle can consume regardless of predicate correctness
const capC = Math.max(1, Number(CFG.max_campaigns_per_cycle) || 8);
const overflow = Math.max(0, active.length - capC);
// keep ACTIVE campaigns first - a live campaign matters more than a finished one's tail
const ordered = active.slice().sort((a, b) => {
  const aa = String(a.status).toUpperCase() === 'ACTIVE' ? 0 : 1;
  const bb = String(b.status).toUpperCase() === 'ACTIVE' ? 0 : 1;
  return aa - bb;
});
return ordered.slice(0, capC).map(c => ({ json: { campaign_id: c.id, campaign_name: c.name,
                                  campaign_status: String(c.status ?? '').toUpperCase(),
                                  __scanned: rows.length, __allowlist: allow.length,
                                  __campaign_overflow: overflow } }));
"""

CARRY_CAMPAIGN = r"""
// /statistics does not echo which campaign it belongs to (verified against the live response:
// rows carry lead/sequence fields only), so attribution is positional against Pick Active.
// The HTTP node emits exactly one item per input item, in order, even on failure
// (onError=continueRegularOutput) - so the counts must match. If they ever don't, HARD FAIL:
// a shifted zip would file real sends under the wrong campaign, and campaign_id is half of
// WF-2's dedupe key, so mis-attribution corrupts lead resolution. A dead cycle is recoverable,
// silently wrong data is not.
const camps = $('Pick Active').all();
const stats = $input.all();
if (camps.length !== stats.length) {
  throw new Error('WF-2S alignment broken: ' + camps.length + ' campaigns polled but '
    + stats.length + ' statistics items returned - refusing to guess the attribution');
}
return stats.map((it, i) => ({
  json: { ...(it.json || {}),
          __campaign_id: camps[i].json.campaign_id ?? null,
          __campaign_name: camps[i].json.campaign_name ?? null,
          __campaign_status: camps[i].json.campaign_status ?? null },
}));
"""

FIND_NEW = r"""
const CFG = $('CONFIG').first().json;
const sd = $getWorkflowStaticData('global');
// S4: the store is READ here and written only after a replay actually succeeds (see Summary).
// It used to be written here, which meant a send was marked seen before anyone knew whether
// WF-2 accepted it - and one transient outage (a deploy window returned 404 for 100 sends)
// silently and permanently lost those events. Observability that quietly gives up is worse
// than none, because the gap is invisible.
// _v2 abandons the keys poisoned by that outage, so those sends get replayed once more.
// Safe by construction: WF-2 dedupes on campaign_id + sl_lead_id, so an already-processed
// send is absorbed there rather than double-counted.
const seen = sd.__sent_seen_v2 = sd.__sent_seen_v2 || {};
const cutoff = Date.now() - Number(CFG.lookback_minutes) * 60000;

// one item per campaign arrives here, each carrying its own /statistics response
const out = [];
let considered = 0, stale = 0, already = 0;
for (const item of $input.all()) {
  const j = item.json || {};
  const camp = j.__campaign_id ?? null;
  const campName = j.__campaign_name ?? null;
  const campStatus = j.__campaign_status ?? null;
  for (const row of (j.data ?? [])) {
    considered++;
    const t = Date.parse(row.sent_time || 0);
    if (!Number.isFinite(t) || t < cutoff) { stale++; continue; }
    const key = String(row.stats_id || (camp + '|' + row.lead_email));
    if (seen[key]) { already++; continue; }
    out.push({ campaign_id: camp, campaign_name: campName, campaign_status: campStatus,
               stats_id: row.stats_id,
               lead_email: row.lead_email, lead_name: row.lead_name,
               sequence_number: row.sequence_number, sent_time: row.sent_time,
               email_subject: row.email_subject, __key: key });
  }
}
out.sort((a, b) => String(a.sent_time).localeCompare(String(b.sent_time)));
const cap = Number(CFG.max_per_run);
const dropped = Math.max(0, out.length - cap);
const batch = out.slice(0, cap);

if (!batch.length) return [{ json: { __idle: true, considered, stale, already, dropped: 0 } }];
return batch.map((b, i) => ({ json: { ...b, __batch: batch.length, __dropped: dropped,
                                      __considered: considered, __first: i === 0 } }));
"""

BUILD_PAYLOAD = r"""
const CFG = $('CONFIG').first().json;
// S3: this node runs ONCE FOR ALL ITEMS. Reading $json and returning a single item replayed
// exactly one send per cycle no matter how many were found. Map over every item instead.
// S1: reaching backward for Find New Sends' paired item across the lead-lookup HTTP hop is
// unavailable - zip by index and then PROVE the zip with the lead's own email.
const rows = $('Find New Sends').all().map(i => i.json);
const out = [];
$input.all().forEach((it, i) => {
  const row = rows[i];
  if (!row) return;                                   // nothing to attribute this response to
  const r = it.json || {};
  const lead = (r && r.email) ? r : (r.data?.[0] ?? {});
  // cross-check, not an assumption: the lookup was keyed on row.lead_email, so a mismatch
  // means the zip slipped and the ids belong to somebody else. Drop rather than mis-attribute.
  const same = lead.email
    && String(lead.email).trim().toLowerCase() === String(row.lead_email).trim().toLowerCase();
  const mapId = (() => {
    for (const c of (lead.lead_campaign_data ?? [])) {
      if (String(c.campaign_id) === String(row.campaign_id)) {
        return c.campaign_lead_map_id ?? c.lead_campaign_map_id ?? null;
      }
    }
    return null;
  })();
  const body = {
    event_type: CFG.synthetic_event_type,
    campaign_id: row.campaign_id,
    campaign_name: row.campaign_name,
    campaign_status: row.campaign_status ?? null,
    // an unverified zip contributes NO ids - WF-2 falls back to email resolution, which is
    // slower but cannot attach the wrong person
    sl_email_lead_id: same ? (lead.id ?? null) : null,
    sl_email_lead_map_id: same ? mapId : null,
    app_url: (same && mapId) ? ('https://app.smartlead.ai/app/master-inbox?leadMap=' + mapId) : null,
    to_email: row.lead_email,
    to_name: row.lead_name ?? null,
    from_email: null,              // /statistics does not expose the sending inbox
    sequence_number: row.sequence_number ?? 1,
    event_timestamp: row.sent_time,
    time_sent: row.sent_time,
    subject: row.email_subject ?? null,
    stats_id: row.stats_id ?? null,
    // provenance: WF-2 records this verbatim in Shadow Log, so a reconciled event is never
    // mistaken for a genuine webhook delivery when the diff is read later
    __reconciled: true,
    __reconciled_by: 'WF-2S',
  };
  out.push({ json: { __body: body, __key: row.__key, __id_verified: !!same,
                     __batch: row.__batch ?? 0, __dropped: row.__dropped ?? 0,
                     __considered: row.__considered ?? 0 } });
});
return out;
"""

SUMMARY = r"""
// .all() needs no paired-item resolution, which is the whole point of doing it here
const CFG = $('CONFIG').first().json;
const built = $('Build SENT Payload').all().map(i => i.json);
const resp = $input.all().map(i => i.json || {});
// Replay Into WF-2 is onError=continueRegularOutput, so a rejected replay arrives as an item
// with .error rather than failing the cycle. Counting them is the only way anyone finds out.
const failed = resp.filter(r => r.error !== undefined).length;
const unverified = built.filter(b => b.__id_verified !== true).length;
// S4: mark seen ONLY for replays WF-2 accepted. resp[i] pairs with built[i] because the HTTP
// node emits one item per input item in order. A rejected replay stays unmarked and is picked
// up by the next cycle while it is still inside lookback_minutes.
const sd = $getWorkflowStaticData('global');
const seen = sd.__sent_seen_v2 = sd.__sent_seen_v2 || {};
built.forEach((b, i) => {
  if (!b || !b.__key) return;
  if (resp[i] && resp[i].error !== undefined) return;   // rejected - leave it retryable
  // store the SEND time, which is what makes pruning below possible
  seen[b.__key] = b.__body?.time_sent ?? new Date().toISOString();
});
// prune: at ~100 sends per cycle this store would grow by ~10k keys a day and never shrink.
// A key is only useful while its send is still inside lookback_minutes; keep a wide margin.
const keepMs = Math.max(Number(CFG.lookback_minutes) * 60000 * 8, 86400000);
const now = Date.now();
let pruned = 0;
for (const k of Object.keys(seen)) {
  const t = Date.parse(seen[k]);
  if (Number.isFinite(t) && (now - t) > keepMs) { delete seen[k]; pruned++; }
}
const f = built[0] ?? {};
return [{ json: { __batch: built.length, __failed: failed, __unverified: unverified,
                  __dropped: f.__dropped ?? 0, __considered: f.__considered ?? 0,
                  __marked: built.length - failed, __pruned: pruned,
                  __allowlist: (CFG.campaign_allowlist ?? []).length,
                  __campaign_overflow: (() => {
                    try { return $('Pick Active').first().json.__campaign_overflow ?? 0; }
                    catch (e) { return 0; } })(),
                  __store_size: Object.keys(seen).length } }];
"""


WRITE_MODE_WATCH = r"""
// A live window must expire on its own. staticData remembers when we FIRST saw live mode, so the
// age is measured from observation rather than trusting anyone to record a start time.
const CFG = $('CONFIG').first().json;
const wf = (($json && ($json.data ?? $json)) || {});
let mode = null;
try {
  const cfgNode = (wf.nodes || []).find(n => n.name === 'CONFIG');
  mode = JSON.parse(cfgNode.parameters.jsonOutput).WRITE_MODE;
} catch (e) { mode = null; }
const sd = $getWorkflowStaticData('global');
const now = Date.now();
if (mode === 'live') {
  if (!sd.__wf2_live_since) sd.__wf2_live_since = new Date(now).toISOString();
} else {
  delete sd.__wf2_live_since;                 // back in shadow -> the clock resets
}
const since = sd.__wf2_live_since ? Date.parse(sd.__wf2_live_since) : null;
const hours = since ? Math.round(((now - since) / 3600000) * 10) / 10 : null;
const limit = Number(CFG.write_mode_max_hours) || 2;
return [{ json: {
  __mode: mode,
  __mode_live_since: sd.__wf2_live_since || null,
  __mode_hours: hours,
  __mode_limit: limit,
  // unreadable mode is NOT treated as fine: if we cannot tell, say so rather than stay quiet
  __mode_overdue: (mode === 'live' && hours !== null && hours >= limit) || mode === null,
} }];
"""

MODE_WARN_TEXT = (
    "={{ (() => { const j=$json;"
    " if (j.__mode === null) { return ':warning: *WF-2S cannot read WF-2’s WRITE_MODE* -"
    " the live-window expiry check is blind right now.'; }"
    " return ':rotating_light: *WF-2 has been in WRITE_MODE=live for ' + j.__mode_hours + 'h*'"
    " + ' (limit ' + j.__mode_limit + 'h, live since ' + j.__mode_live_since + ')."
    " A live window is supposed to last minutes. While it is open, forward remaps may be sending"
    " real prospect replies somewhere they do not belong - this exact situation ran for 72 hours"
    " on 2026-07-31. Revert per MATRIX_REVERT_CHECKLIST.md or say it is deliberate.'; })() }}"
)

WF2H_WATCH = r"""
// The guard gets a guard. WF-2H runs once a day and cannot observe its own failure - it errored on
// every run of its life and only a manual sweep noticed. This workflow runs every 15 minutes, so it
// is the natural watchdog. Read-only against the n8n API.
const CFG = $('CONFIG').first().json;
const rows = (($json && ($json.data ?? $json)) || []);
const list = Array.isArray(rows) ? rows : [];
const last = list.length ? list[0] : null;
const at = last ? (last.stoppedAt || last.startedAt || null) : null;
const t = at ? Date.parse(at) : NaN;
const hours = Number.isFinite(t) ? ((Date.now() - t) / 3600000) : null;
const limit = Number(CFG.wf2h_stale_hours) || 48;
return [{ json: {
  __wf2h_last: at,
  __wf2h_hours: hours === null ? null : Math.round(hours * 10) / 10,
  // no successful run on record is the WORST case, not an unknown one - treat it as stale
  __wf2h_stale: (hours === null) || (hours > limit),
  __wf2h_limit: limit,
} }];
"""

WF2H_WARN_TEXT = (
    "={{ (() => { const j=$json;"
    " const age = (j.__wf2h_hours === null || j.__wf2h_hours === undefined)"
    " ? 'no successful run on record' : (j.__wf2h_hours + 'h ago');"
    " return ':rotating_light: *WF-2H has not produced a digest* \u2014 last success: ' + age"
    " + ' (threshold ' + j.__wf2h_limit + 'h). The daily health digest is the thing that would tell"
    " you WF-2 had gone quiet, so while it is down that alarm is not armed.'; })() }}"
)

WARN_TEXT = (
    "={{ (() => { const j=$json;"
    " const lines=[':arrows_counterclockwise: *WF-2S SENT reconciler*'];"
    " lines.push('replayed ' + (j.__batch ?? 0) + ' send(s) into WF-2'"
    " + ' \\u00b7 considered ' + (j.__considered ?? 0));"
    " if ((j.__dropped ?? 0) > 0) { lines.push(':warning: ' + j.__dropped"
    " + ' send(s) exceeded max_per_run and were NOT replayed this cycle - they will be picked up'"
    " + ' next run only if still inside lookback_minutes'); }"
    " if ((j.__allowlist ?? 0) > 0) { lines.push(':lock: SCOPED to ' + j.__allowlist"
    " + ' campaign(s) - organic SENT is NOT being reconciled while this is set'); }"
    " if ((j.__failed ?? 0) > 0) { lines.push(':x: ' + j.__failed"
    " + ' replay(s) were REJECTED by the WF-2 webhook - those sends are unobserved'); }"
    " if ((j.__unverified ?? 0) > 0) { lines.push(':warning: ' + j.__unverified"
    " + ' send(s) replayed without Smartlead lead ids (lookup miss) - WF-2 resolves by email'); }"
    " const wd = (() => { try { return $('WF-2H Watch Eval').first().json; } catch (e) { return {}; } })();"
    " if (wd.__wf2h_last !== undefined) { lines.push('WF-2H last success: '"
    " + (wd.__wf2h_hours === null ? 'never' : (wd.__wf2h_hours + 'h ago'))"
    " + (wd.__wf2h_stale ? '  :rotating_light: STALE' : '')); }"
    " if ((j.__campaign_overflow ?? 0) > 0) { lines.push(':warning: ' + j.__campaign_overflow"
    " + ' campaign(s) exceeded max_campaigns_per_cycle and were NOT polled this cycle'); }"
    " lines.push('_Smartlead does not deliver EMAIL_SENT to our webhook entry; this is the"
    " substitute source._');"
    " return lines.join('\\n'); })() }}"
)


def build():
    N, C = [], {}
    N.append(node("s-cron", "Every 15 min", "n8n-nodes-base.scheduleTrigger", 1.2, [0, 0],
                  {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}))
    N.append(node("s-cfg", "CONFIG", "n8n-nodes-base.set", 3.4, [200, 0],
                  {"mode": "raw", "jsonOutput": json.dumps(CONFIG, indent=2, ensure_ascii=False),
                   "options": {}}))
    N.append(sl_get("s-camps", "SL Campaigns", [400, 0], "{{ '/campaigns' }}"))
    N.append(code("s-pick", "Pick Active", [600, 0], PICK_ACTIVE))
    N.append(sl_get("s-stats", "SL Statistics", [800, 0],
                    "{{ '/campaigns/' + ($json.campaign_id || 0) + '/statistics' }}"))
    N.append(code("s-carry", "Carry Campaign", [1000, 0], CARRY_CAMPAIGN))
    N.append(code("s-find", "Find New Sends", [1200, 0], FIND_NEW))
    N.append(node("s-ifidle", "IF Has Sends", "n8n-nodes-base.if", 2, [1400, 0],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "s-c1",
                                                  "leftValue": "={{ $json.__idle !== true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(code("s-idle", "NoOp Idle", [1600, 160], "return [{ json: { idle: true } }];"))
    N.append(sl_get("s-lead", "SL Lead Lookup", [1600, -80],
                    "{{ '/leads?email=' + encodeURIComponent($json.lead_email) }}"))
    N.append(code("s-payload", "Build SENT Payload", [1800, -80], BUILD_PAYLOAD))
    N.append(node("s-post", "Replay Into WF-2", "n8n-nodes-base.httpRequest", 4.2, [2000, -80],
                  {"method": "POST", "url": "={{ $('CONFIG').first().json.wf2_webhook }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type",
                                                        "value": "application/json"}]},
                   "options": {}, "sendBody": True, "specifyBody": "json",
                   "jsonBody": "={{ JSON.stringify($json.__body) }}"},
                  retryOnFail=True, maxTries=3, waitBetweenTries=2000,
                  onError="continueRegularOutput"))
    # S1: the old "IF Report" gated on a Find New Sends paired lookup to make the Slack node
    # fire once - a paired-item lookup across TWO HTTP hops. A run-once-for-all-items Summary
    # collapses N items to 1 by itself, so the gate (and its NoOp) are not needed at all.
    N.append(code("s-sum", "Summary", [2200, -80], SUMMARY))
    N.append(slack_first("s-slack", "WF-2S Report", [2600, -160], "ops_channel", WARN_TEXT, SLACK_CRED))

    # ---- watchdog branch: WF-2H cannot see its own failure, so this 15-minute workflow looks
    # ---- for it. Runs on EVERY cycle, including idle ones, because an idle cycle posts nothing
    # ---- and a watchdog that only speaks when something else happens is not a watchdog.
    N.append(node("s-wh", "WF-2H Watch", "n8n-nodes-base.httpRequest", 4.2, [400, 260],
                  {"method": "GET",
                   "url": "={{ $('CONFIG').first().json.n8n_api }}"
                          "{{ '/executions?workflowId=' + $('CONFIG').first().json.wf2h_workflow_id"
                          " + '&status=success&limit=1' }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Accept",
                                                        "value": "application/json"}]},
                   "options": {},
                   "authentication": "genericCredentialType",
                   "genericAuthType": "httpHeaderAuth"},
                  credentials=N8N_CRED, retryOnFail=True, maxTries=2, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("s-whe", "WF-2H Watch Eval", [600, 260], WF2H_WATCH))
    # WRITE_MODE expiry: read WF-2's own CONFIG and shout if it has been live too long
    N.append(node("s-wm", "WF-2 Mode Read", "n8n-nodes-base.httpRequest", 4.2, [400, 420],
                  {"method": "GET",
                   "url": "={{ $('CONFIG').first().json.n8n_api }}"
                          "{{ '/workflows/' + $('CONFIG').first().json.wf2_workflow_id }}",
                   "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Accept",
                                                        "value": "application/json"}]},
                   "options": {},
                   "authentication": "genericCredentialType",
                   "genericAuthType": "httpHeaderAuth"},
                  credentials=N8N_CRED, retryOnFail=True, maxTries=2, waitBetweenTries=1000,
                  onError="continueRegularOutput"))
    N.append(code("s-wme", "WF-2 Mode Eval", [600, 420], WRITE_MODE_WATCH))
    N.append(node("s-wmif", "IF Mode Overdue", "n8n-nodes-base.if", 2, [800, 420],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "s-c4",
                                                  "leftValue": "={{ $json.__mode_overdue === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(slack_first("s-wmslack", "Ops Warn Mode Overdue", [1000, 380], "ops_channel",
                         MODE_WARN_TEXT, SLACK_CRED))
    N.append(code("s-wmok", "NoOp Mode OK", [1000, 500],
                  "return [{ json: { write_mode: 'ok' } }];"))
    N.append(node("s-whif", "IF WF-2H Stale", "n8n-nodes-base.if", 2, [800, 260],
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                              "typeValidation": "strict", "version": 1},
                                  "conditions": [{"id": "s-c3",
                                                  "leftValue": "={{ $json.__wf2h_stale === true }}",
                                                  "rightValue": True,
                                                  "operator": {"type": "boolean",
                                                               "operation": "true",
                                                               "singleValue": True}}],
                                  "combinator": "and"}, "options": {}}))
    N.append(slack_first("s-whslack", "Ops Warn WF-2H Stale", [1000, 200], "ops_channel",
                         WF2H_WARN_TEXT, SLACK_CRED))
    N.append(code("s-whok", "NoOp WF-2H OK", [1000, 330],
                  "return [{ json: { wf2h: 'fresh' } }];"))

    C["Every 15 min"] = {"main": [[{"node": "CONFIG", "type": "main", "index": 0}]]}
    C["CONFIG"] = {"main": [[{"node": "SL Campaigns", "type": "main", "index": 0},
                             {"node": "WF-2H Watch", "type": "main", "index": 0},
                             {"node": "WF-2 Mode Read", "type": "main", "index": 0}]]}
    C["WF-2 Mode Read"] = {"main": [[{"node": "WF-2 Mode Eval", "type": "main", "index": 0}]]}
    C["WF-2 Mode Eval"] = {"main": [[{"node": "IF Mode Overdue", "type": "main", "index": 0}]]}
    C["IF Mode Overdue"] = {"main": [[{"node": "Ops Warn Mode Overdue", "type": "main", "index": 0}],
                                     [{"node": "NoOp Mode OK", "type": "main", "index": 0}]]}
    C["WF-2H Watch"] = {"main": [[{"node": "WF-2H Watch Eval", "type": "main", "index": 0}]]}
    C["WF-2H Watch Eval"] = {"main": [[{"node": "IF WF-2H Stale", "type": "main", "index": 0}]]}
    C["IF WF-2H Stale"] = {"main": [[{"node": "Ops Warn WF-2H Stale", "type": "main", "index": 0}],
                                    [{"node": "NoOp WF-2H OK", "type": "main", "index": 0}]]}
    C["SL Campaigns"] = {"main": [[{"node": "Pick Active", "type": "main", "index": 0}]]}
    C["Pick Active"] = {"main": [[{"node": "SL Statistics", "type": "main", "index": 0}]]}
    C["SL Statistics"] = {"main": [[{"node": "Carry Campaign", "type": "main", "index": 0}]]}
    C["Carry Campaign"] = {"main": [[{"node": "Find New Sends", "type": "main", "index": 0}]]}
    C["Find New Sends"] = {"main": [[{"node": "IF Has Sends", "type": "main", "index": 0}]]}
    C["IF Has Sends"] = {"main": [[{"node": "SL Lead Lookup", "type": "main", "index": 0}],
                                  [{"node": "NoOp Idle", "type": "main", "index": 0}]]}
    C["SL Lead Lookup"] = {"main": [[{"node": "Build SENT Payload", "type": "main", "index": 0}]]}
    C["Build SENT Payload"] = {"main": [[{"node": "Replay Into WF-2", "type": "main", "index": 0}]]}
    C["Replay Into WF-2"] = {"main": [[{"node": "Summary", "type": "main", "index": 0}]]}
    C["Summary"] = {"main": [[{"node": "WF-2S Report", "type": "main", "index": 0}]]}

    return {"name": "WF-2S Smartlead SENT Reconciler", "nodes": N, "connections": C,
            "active": False,
            "settings": {"executionOrder": "v1", "errorWorkflow": ERROR_WORKFLOW,
                         "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all"}}


def validate(wf):
    e, names = [], [n["name"] for n in wf["nodes"]]
    # class sweep (S1): no backward .item inside any fan-out region
    e.extend(item_violations(wf))
    if len(names) != len(set(names)):
        e.append("duplicate node names")
    if wf["settings"].get("errorWorkflow") != ERROR_WORKFLOW:
        e.append("errorWorkflow not bound")
    if wf.get("active") is not False:
        e.append("must ship inactive")
    cfg = json.loads(next(n for n in wf["nodes"] if n["name"] == "CONFIG")["parameters"]["jsonOutput"])
    if cfg["synthetic_event_type"] != "EMAIL_SENT":
        e.append("the synthetic event must be the one WF-2's discriminator expects")
    if not (0 < cfg["max_per_run"] <= 100):
        e.append("max_per_run out of range")
    # S1 guard: every node here sits downstream of an HTTP fan-out, so a backward .item lookup
    # cannot resolve its paired item. This is what broke cycle 1; ban the construct outright so
    # it cannot creep back in a later edit. Pairing-free .first()/.all() are the substitutes.
    for n in wf["nodes"]:
        blob = json.dumps(n["parameters"], ensure_ascii=False)
        if ").item" in blob:
            e.append(f"{n['name']}: backward .item lookup (S1 class) - use .first()/.all()")
    # S2 guard: /campaigns is a bare array that n8n splits into one item per campaign, so the
    # picker must read $input.all(). Reading $json there silently found zero ACTIVE campaigns.
    pick = next(n for n in wf["nodes"] if n["name"] == "Pick Active")
    if "$input.all()" not in pick["parameters"]["jsCode"]:
        e.append("Pick Active must read $input.all() (S2 class: split array response)")
    # S3 guard: a run-once-for-all-items node that returns a bare single-element list replays
    # one send per cycle regardless of batch size.
    pay = next(n for n in wf["nodes"] if n["name"] == "Build SENT Payload")
    if "$input.all()" not in pay["parameters"]["jsCode"]:
        e.append("Build SENT Payload must map over $input.all() (S3 class: batch collapsed)")
    for n in wf["nodes"]:
        p = n["parameters"]
        if n["type"] == "n8n-nodes-base.httpRequest":
            if "}}={{" in str(p.get("url")):
                e.append(f"{n['name']}: welded URL (B9 class)")
            if "smartlead" in str(p.get("url")) and not p.get("authentication"):
                e.append(f"{n['name']}: Smartlead call without auth")
    targets = {t["node"] for c in wf["connections"].values() for o in c["main"] for t in o}
    for t in targets:
        if t not in names:
            e.append(f"dangling connection target {t}")
    reachable = {"Every 15 min"}
    changed = True
    while changed:
        changed = False
        for src, c in wf["connections"].items():
            if src in reachable:
                for o in c["main"]:
                    for t in o:
                        if t["node"] not in reachable:
                            reachable.add(t["node"]); changed = True
    for n in names:
        if n not in reachable:
            e.append(f"orphan node {n}")
    blob = json.dumps(wf)
    for bad in ("api_key=", "sk-proj", "9f59ef3d"):
        if bad in blob:
            e.append(f"secret-ish literal: {bad}")
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    a = ap.parse_args()
    wf = build()
    errs = validate(wf)
    if errs:
        for x in errs:
            print(f"ERROR: {x}", file=sys.stderr)
        return 1
    payload = {k: wf[k] for k in ("name", "nodes", "connections", "settings")}
    a.output.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"WF-2S built -> {a.output} ({len(wf['nodes'])} nodes)")
    print("ships INACTIVE; activating makes it the primary SENT source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
