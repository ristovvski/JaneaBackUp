const cfg = $('CONFIG').first().json;
const retention = cfg.retention_days_by_family || {};
const floorDays = Math.max(1, Number(cfg.read_cutoff_days) || 7);
const cap = Math.max(1, Number(cfg.max_deletes_per_run) || 250);
const dry = cfg.dry_run === true;
const now = Date.now();
const readCutoff = new Date(now - floorDays * 86400000).toISOString();

// POSITIVE shape check. The read is filtered `claimed_at < cutoff`, so ZERO ROWS IS THE NORMAL,
// HEALTHY ANSWER. That makes "empty" and "unreadable" indistinguishable unless the failure shape
// is looked for explicitly: some dataTable ops return an error object, others echo the input.
const raw = $input.all().map(i => i.json);
const placeholder = raw.length === 1 && raw[0] && Object.keys(raw[0]).length === 0;
const items = placeholder ? [] : raw;
const errored = items.filter(r => r && r.error !== undefined);
if (errored.length) {
  throw new Error('claims prune: the stale-row read failed ('
    + String(errored[0].error).slice(0, 160) + '). Refusing to report "nothing to prune".');
}
const rows = items.filter(r => r && typeof r.claim_key === 'string' && r.claim_key);
if (items.length && !rows.length) {
  throw new Error('claims prune: read returned ' + items.length + ' item(s) of an unrecognised '
    + 'shape. Refusing to treat that as an empty result.');
}

// THE REFUSAL (Nik, 2026-09-03 - do not soften this).
// This prune replaces one that pruned with `now - Number(value) > maxAge`. Number(ISO) is NaN and
// every comparison with NaN is false, so four entries in the old registry could never expire -
// three of them real people who would have been permanently un-re-alertable from ~2026-11-09.
// A timestamp we cannot parse is CORRUPT STATE. We do not guess at it, and we do not quietly keep
// it either: the whole run stops and says so, because a corrupt row means something upstream is
// writing a shape we did not expect and deleting on that basis would be worse than waiting.
const unparsable = rows.filter(r => !Number.isFinite(Date.parse(String(r.claimed_at || ''))));
if (unparsable.length) {
  throw new Error('claims prune REFUSING TO RUN: ' + unparsable.length + ' row(s) have a '
    + 'claimed_at that will not parse, e.g. ' + JSON.stringify(unparsable[0].claim_key) + ' = '
    + JSON.stringify(unparsable[0].claimed_at) + '. Fix the writer before pruning.');
}

// Per-family retention. Dedupe families only need to outlive the reconcilers' 48h lookback; alert
// families carry the 90 days the staticData registry used to promise and the port dropped.
const expired = [], keptUnknown = {}, byFamily = {};
for (const r of rows) {
  const fam = typeof r.family === 'string' ? r.family : '(none)';
  byFamily[fam] = (byFamily[fam] || 0) + 1;
  const days = retention[fam];
  if (days === undefined) { keptUnknown[fam] = (keptUnknown[fam] || 0) + 1; continue; }
  const ageDays = (now - Date.parse(r.claimed_at)) / 86400000;
  // defence in depth: the server-side filter bounds the read, but re-check here so a filter that
  // silently stopped filtering cannot delete live rows.
  if (ageDays > Number(days) && r.claimed_at < readCutoff) expired.push(r);
}
const batch = expired.slice(0, cap);
return [{ json: {
  read_cutoff: readCutoff, read_cutoff_days: floorDays, dry_run: dry,
  rows_read: rows.length, by_family: byFamily,
  unknown_families: keptUnknown,          // retained, never quietly
  expired_found: expired.length,
  will_delete: dry ? 0 : batch.length,
  capped: expired.length > cap,
  remaining_after_run: Math.max(0, expired.length - (dry ? 0 : batch.length)),
  oldest_expired: expired.length ? expired.map(r => r.claimed_at).sort()[0] : null,
  keys: dry ? [] : batch.map(r => ({ claim_key: r.claim_key, family: r.family,
                                     claimed_at: r.claimed_at }))
} }];
