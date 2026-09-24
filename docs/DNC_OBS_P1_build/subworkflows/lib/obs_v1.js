'use strict';
// Smartlead observability logic v1 (R1 + R4 only; R2/R3 deferred — need per-lead message-history
// endpoint, not documented as of 2026-07-23). Pure; embedded in smartlead_observability_readonly
// Code nodes; tested by obs_tests.js. READ-ONLY: never writes to Smartlead.

// >>> obs_v1 >>>
function obsToMs(x) { return x ? new Date(x).getTime() : 0; }

// Parse one leads-statistics page for a campaign, counting events AFTER the watermark.
// FIELD NAMES ARE FIXTURE-BASED — confirm against a real read-only capture at smoke time
// (fallbacks included so a naming diff degrades gracefully rather than crashing).
function parseLeadsStatisticsV1(page, sinceIso, forwardableSet) {
  var since = obsToMs(sinceIso);
  var data = (page && (page.data || page.leads || page.items)) || [];
  var replies = 0, categorized = 0, forwardable_new = 0, maxEvt = since;
  forwardableSet = forwardableSet || {};
  data.forEach(function (r) {
    var rt = obsToMs(r.last_reply_time || r.reply_time || r.last_reply_at);
    var ct = obsToMs(r.category_updated_at || r.lead_category_updated_at);
    var cat = (r.lead_category || r.category || null);
    if (rt > since) { replies++; if (rt > maxEvt) maxEvt = rt; }
    if (ct > since) {
      categorized++; if (ct > maxEvt) maxEvt = ct;
      if (cat && forwardableSet[String(cat).toLowerCase()]) forwardable_new++;
    }
  });
  return { replies: replies, categorized: categorized, forwardable_new: forwardable_new,
           max_event_time: new Date(maxEvt).toISOString() };
}

// R1 (categories stalled) + R4 (pipeline delta), leads-statistics-only.
// input: { metrics, config:{campaign_id, r1_stall_hours, r4_delta_threshold}, r1_since, now }
function evaluateR1R4V1(input) {
  var m = input.metrics, cfg = input.config, now = input.now;
  var out = { alerts: [], r1_since_next: null };
  var stallMs = Number(cfg.r1_stall_hours) * 3600000;
  // R1: replies arriving but zero new categorizations => stall clock; fire once stall persists.
  if (m.replies > 0 && m.categorized === 0) {
    var since = input.r1_since || now;
    out.r1_since_next = since;
    if (new Date(now).getTime() - new Date(since).getTime() >= stallMs) {
      out.alerts.push({ rule: 'R1', key: 'R1:' + cfg.campaign_id,
        msg: 'active campaign has replies but 0 new lead categories', replies: m.replies, since: since });
    }
  } else {
    out.r1_since_next = null; // categorization resumed (or no replies) => reset
  }
  // R4: quantitative divergence between replies and categorizations in the window.
  var delta = m.replies - m.categorized;
  if (delta > Number(cfg.r4_delta_threshold)) {
    out.alerts.push({ rule: 'R4', key: 'R4:' + cfg.campaign_id,
      msg: 'Smartlead reply vs categorization pipeline delta', delta: delta,
      replies: m.replies, categorized: m.categorized });
  }
  return out;
}

// Alert dedupe: same key fires at most once per window. `dedupeRow` is the obs_state row (or null).
function obsIsDeduped(dedupeRow, now) {
  if (!dedupeRow || !dedupeRow.expires_at) return false;
  return new Date(dedupeRow.expires_at).getTime() > new Date(now).getTime();
}
// <<< obs_v1 <<<

module.exports = { parseLeadsStatisticsV1: parseLeadsStatisticsV1, evaluateR1R4V1: evaluateR1R4V1,
                   obsIsDeduped: obsIsDeduped, obsToMs: obsToMs };
