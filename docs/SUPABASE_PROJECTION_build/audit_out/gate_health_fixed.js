// Read the monitor's own last probe rather than firing the gate again: the digest must not add
// synthetic traffic to a workflow whose health it is reporting on.
const prev = $('Supabase Mirror Agg').first().json;
const r = $input.first().json || {};
const ex = (Array.isArray(r.data) ? r.data : [])[0] || null;
if (!ex) {
  return [{ json: { ...prev, __gate_readable: false, __gate_error: 'no execution returned' } }];
}
const rd = (((ex.data || {}).resultData) || {}).runData || {};
const tr = ((rd['Track + Report'] || [])[0] || {});
const item = ((((tr.data || {}).main || [])[0] || [])[0] || {}).json || null;
if (!item) {
  return [{ json: { ...prev, __gate_readable: false,
    __gate_error: 'Track + Report produced no item', gate_last_at: ex.startedAt || null } }];
}
return [{ json: { ...prev, __gate_readable: true,
  gate_healthy: item.healthy === true,
  gate_counts: item.counts || null,
  gate_latency_ms: item.duration_ms ?? null,
  gate_failures_today: item.failures_today ?? null,
  gate_checks_today: item.checks_today ?? null,
  gate_last_at: ex.startedAt || null } }];