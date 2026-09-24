// Count outcomes, not items. deleteRows runs with continueRegularOutput and can hand back an error
// item; reporting "deleted N" off the input count would be a confident, false answer.
const plan = $('Plan').first().json;
const items = $input.all().map(i => i.json);
const failed = items.filter(r => r && r.error !== undefined);
const ok = items.length - failed.length;
return [{ json: {
  read_cutoff: plan.read_cutoff, dry_run: false, rows_read: plan.rows_read,
  by_family: plan.by_family, unknown_families: plan.unknown_families,
  expired_found: plan.expired_found, attempted: items.length,
  deleted: ok, failed: failed.length,
  first_error: failed.length ? String(failed[0].error).slice(0, 200) : null,
  capped: plan.capped, remaining_after_run: plan.remaining_after_run,
  outcome: failed.length ? 'PARTIAL - ' + failed.length + ' delete(s) failed'
                         : 'deleted ' + ok + ' row(s)'
} }];
