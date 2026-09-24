const cfg = $('CONFIG').first().json;
const w = $('Window').first().json;
const d = $input.first().json;
const sl = (d.__sl || []);
const base = cfg.n8n_base;
const L = [];
const dot = (s) => s === 'red' ? ':red_circle:' : s === 'amber' ? ':large_yellow_circle:' : ':large_green_circle:';
const num = (v) => (v === null || v === undefined) ? 'n/a' : String(v);

// campaign names are long and repetitive; the digest keeps the distinguishing tail so five of
// them still fit on one line.
const short = (n) => String(n || '').replace(/\[Events Visiting\]\s*/g, '')
  .replace(/\[([^\]]+)\]\s*/g, '$1 ').replace(/\s+/g, ' ').trim();
// ---------- 1 CAMPAIGNS
{
  const bad = sl.filter(c => !c.__stats_readable || c.__due_readable === false).length;
  const zipBad = sl.some(c => c.__zip_ok === false || c.__an_zip_proven === false);
  const st = (sl.length === 0) ? 'amber' : (bad || zipBad) ? 'amber' : 'green';
  const parts = sl.map(c => {
    const nx = c.next_step
      ? ('s' + c.next_step + ' due ' + (c.next_due ? ((c.__due_partial ? '≥' : '') + c.next_due)
                                                   : 'unknown (no send found)'))
      : 'sequence complete';
    return short(c.campaign_name) + ' (' + num(c.sends_24h) + ' sent 24h, ' + nx + ')';
  });
  L.push(dot(st) + ' *CAMPAIGNS* SL ' + sl.length + ' · HR '
    + (d.__hr_readable ? d.__hr_active : 'unreadable')
    + (parts.length ? ' — ' + parts.join(' · ') : '')
    + (d.__hr_readable && d.__hr_campaigns
        ? ' | HR: ' + d.__hr_campaigns.map(c => short(c.name)).join(' · ') : ''));
}
// ---------- 2 VOLUME
{
  const sends = sl.reduce((a, c) => a + (Number(c.sends_24h) || 0), 0);
  const real = sl.reduce((a, c) => a + (Number(c.replies_real) || 0), 0);
  const ooo = sl.reduce((a, c) => a + (Number(c.replies_ooo) || 0), 0);
  const bnc = sl.reduce((a, c) => a + (Number(c.bounces) || 0), 0);
  const unread = sl.some(c => !c.__stats_readable) || d.__pd_readable === false
              || d.__hr_stats_readable === false;
  const srcs = Object.entries(d.pd_by_source || {}).map(([k, v]) => k + ' ' + v).join(', ') || 'none';
  L.push(dot(unread ? 'amber' : 'green') + ' *VOLUME 24h* email sent ' + sends
    + ' · LinkedIn msg ' + num(d.hr_messages_sent) + '/inv ' + num(d.hr_connections_sent)
    + ' · replies ' + real + ' real / ' + ooo + ' OOO / ' + bnc + ' bounce'
    + ' · new leads ' + num(d.pd_new_leads) + ' (' + srcs + ')'
    + (d.__pd_page_saturated ? ' :warning: lead page saturated, count is a floor' : ''));
}
// ---------- 3 INTEGRITY
{
  const per = d.integrity_per_campaign || [];
  const unread = per.filter(p => !p.readable).length || d.__integrity_zip_ok === false
              || per.some(p => p.readable && p.sent_without_lead === null);
  const nameless = per.reduce((a, p) => a + (Number(p.nameless_leads) || 0), 0);
  const noLead = per.reduce((a, p) => a + (Number(p.sent_without_lead) || 0), 0);
  const noPerson = Number(d.pd_leads_no_person) || 0;
  const gaps = per.map(p => p.campaign_id + ':' + num(p.sent_without_lead)).join(' ');
  const st = (noPerson > 0 || nameless > 0 || noLead > 0) ? 'red' : unread ? 'amber' : 'green';
  let line = dot(st) + ' *INTEGRITY* sent-without-lead ' + (gaps || 'n/a')
    + ' · leads w/o person ' + noPerson + ' · nameless campaign leads ' + nameless;
  if (noPerson > 0 || nameless > 0 || noLead > 0) {
    line += ' — <' + cfg.pd_base + '/leads/inbox|open leads>';
  }
  L.push(line);
}
// ---------- 4 DNC
{
  const st = d.__dnc_active_readable === false ? 'amber'
           : (d.__gate_readable && d.gate_healthy === false) ? 'red' : 'green';
  let line = dot(st) + ' *DNC* active ' + num(d.dnc_active)
    + ' (+' + num(d.dnc_added_24h) + ' / -' + num(d.dnc_removed_24h) + ' 24h)'
    + ' · gate ' + (d.__gate_readable ? (d.gate_healthy ? 'OK' : 'FAILING') : 'unreadable')
    + ' ' + num(d.gate_latency_ms) + 'ms'
    + ' (' + num(d.gate_failures_today) + '/' + num(d.gate_checks_today) + ' fail today)';
  if (d.__gate_readable && d.gate_healthy === false) {
    line += ' — <' + base + '/workflow/' + cfg.gate_monitor_id + '/executions|gate monitor>';
  }
  L.push(line);
}
// ---------- 5 HEALTH
{
  const errs = Number(d.errors_24h);
  const missed = d.missed_count;
  // I-04 became a change log on 2026-09-03: the daily summary and the weekly reconciliation were
  // retired, so there is no reporting job left to be 'ok' or 'FAILING'. What remains is the event
  // receiver, and the honest measure of it is how many CRM changes it actually captured.
  const st = (errs > 0 || (missed && missed > 0)) ? 'red'
           : (d.__err_readable === false || missed === null || d.__changelog_readable === false)
             ? 'amber' : 'green';
  let line = dot(st) + ' *HEALTH* failed execs ' + num(d.errors_24h)
    + ' · missed schedules ' + num(missed)
    + ' · CRM change log ' + (d.__changelog_readable ? num(d.changelog_24h) + ' events' : 'unreadable')
    + ' · no-match ' + num(d.no_match_24h);
  if (errs > 0) line += ' — <' + base + '/home/executions?status=error|failed executions>';
  else if (missed > 0) line += ' — ' + (d.missed || []).map(m => m.name).slice(0, 3).join(', ');
  L.push(line);
  if (missed > 0) {
    L.push('   ↳ missed: ' + (d.missed || []).map(m => m.name + ' (' + m.why + ')').slice(0, 3).join(' · '));
  }
}
// ---------- footer: what was NOT measured. Never a silent gap.
{
  const gaps = [];
  if (cfg.enrich_queue === null) gaps.push('enrich-queue depth: no such queue exists in the estate (WF-2 enriches synchronously) — not 0, absent');
  if (d.__nomatch_readable === false) gaps.push('no-match count unreadable: ' + d.__nomatch_error);
  if (d.__changelog_readable === false) gaps.push('CRM change log unreadable: ' + d.__changelog_error);
  if (d.__sched_zip_ok === false) gaps.push('schedule check could not be paired — treat missed-schedule as unmeasured');
  if (sl.some(c => c.__page_truncated)) gaps.push('a campaign send page was truncated — sends is a floor');
  if (d.__pd_sorted_desc === false) gaps.push('Pipedrive lead page came back UNSORTED — new-lead counts suppressed');
  if ((d.integrity_per_campaign || []).some(p => p.search_saturated)) gaps.push('a campaign lead search hit the 100-item cap — sent-without-lead suppressed for it');
  if (Number(d.__unparsed_rules) > 0) gaps.push(d.__unparsed_rules + ' schedule rule(s) had an unrecognised shape and were assumed daily');
  if (d.errors_page_saturated) gaps.push('the error page was full — failed-exec count is a floor');
  if (gaps.length) L.push(':information_source: _not measured: ' + gaps.join(' · ') + '_');
}
const header = ':sunrise: *Morning digest* ' + w.since_iso.slice(0, 16).replace('T', ' ')
  + 'Z → ' + w.until_iso.slice(0, 16).replace('T', ' ') + 'Z';
const text = [header].concat(L).slice(0, 12).join('\n');
return [{ json: { slack_text: text, __lines: L.length + 1, __digest: d } }];