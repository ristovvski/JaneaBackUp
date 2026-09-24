// WF-2 `Normalize` (final stage). The parsing lives in `Normalize Parse`; this node applies the
// ONE part of it that needs shared state - the recent-bounce memory - reading the atomic claims
// table instead of workflow memory.
//
// WHY IT IS SPLIT AT ALL. The bounce memory does not merely tag the item, it RECLASSIFIES the
// event (`event = 'BOUNCED'`), which reroutes the whole execution. So it cannot be moved
// downstream, and the key it needs (lead email + campaign) is only known after parsing. Splitting
// at the verdict keeps the 231-line parser untouched and patches exactly five published fields:
// event, event_alias, __is_bounce, __bounce_signal, __bounce_duplicate.
//
// WHY THIS STORE MATTERS MOST. Smartlead double-sends a bounce and shapes the second copy as a
// reply. The two copies arrive seconds apart - which is precisely the condition that produces
// overlapping executions, and staticData loses one whole execution's delta on every overlap. The
// store this replaces was the one most likely to be losing writes, not the least.
//
// FALLBACK. `Normalize Parse` still keeps its staticData copy, so if the table cannot be read we
// use the verdict it already computed rather than losing the protection entirely. That is the
// rollback path, live, per-execution.
const p = $('Normalize Parse').item.json;
const cfg = $('CONFIG').item.json;
const row = $json;

// POSITIVE SHAPE CHECK (n8n's dataTable error shape is non-uniform: some ops return an error
// object, others echo the input item unchanged). A hit is only a hit if it looks like a stored row.
const isRow = !!(row && row.family === 'wf2_bounce' && row.claimed_at && row.claim_key);
// `alwaysOutputData` emits ONE EMPTY item when the read matched nothing - that is a genuine
// miss. A NON-empty item that is not a row is the echo, and that is the outage.
const lookupBroken = !!(row && (row.error || row.__error))
                  || (!!row && Object.keys(row).length > 0 && !isRow);

const winSec = Math.max(60, Number(p.__bounce_window_sec) || 3600);
// TYPE-ASSERTED, never coerced - Number(ISO) is NaN and NaN comparisons are all false, which is
// exactly how four entries in the old alert registry became immortal.
let prevAgeSec = null;
if (isRow) {
  const t = Date.parse(row.claimed_at);
  if (Number.isFinite(t)) prevAgeSec = Math.floor((Date.now() - t) / 1000);
}
const memoryHit = prevAgeSec !== null && prevAgeSec >= 0 && prevAgeSec <= winSec;

let signal = p.__sig_base || null;
if (!signal && p.__event_pre_bounce === 'REPLIED' && p.__bkey) {
  if (memoryHit) signal = 'recent_memory';
  else if (lookupBroken && p.__bounce_signal === 'recent_memory') signal = 'recent_memory';
}
let dup = false, reclassified = false, ev = p.__event_pre_bounce;
if (signal) {
  reclassified = (ev !== 'BOUNCED');
  ev = 'BOUNCED';
  if (p.__bkey) dup = memoryHit || (lookupBroken && p.__bounce_duplicate === true);
}
// event_alias depends on the reclassification, so it is recomputed here rather than inherited.
const canon = (cfg.canonical_events || {})[ev] || null;
const alias = reclassified ? null
  : ((ev !== 'UNKNOWN' && canon && p.raw_event && p.raw_event !== canon) ? p.raw_event : null);

return [{ json: Object.assign({}, p, {
  event: ev,
  event_alias: alias,
  __is_bounce: ev === 'BOUNCED',
  __bounce_signal: signal,
  __bounce_duplicate: dup,
  __bounce_backend: lookupBroken ? 'staticData_fallback' : 'dataTable',
  __bounce_prev_age_sec: prevAgeSec,
  __bounce_claim_key: p.__bkey ? ('wf2_bounce|' + p.__bkey) : null
}) }];
