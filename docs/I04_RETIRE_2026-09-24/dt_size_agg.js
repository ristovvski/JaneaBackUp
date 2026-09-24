// DATA-TABLE STORAGE, ESTIMATED. The instance caps all data tables together at 50 MB, and hitting it
// makes every insert/update fail - every DNC write and every WF-1/WF-2 claim. n8n reports its real
// figure (database pages + indexes) only in the UI: no API route exposes it (checked 2026-09-24: the
// public API, the Data Table node on this version, the MCP tools). So this is the serialized size of
// every row the digest can read, printed with a "≈" - never as n8n's own number.
// It covers the tables this estate references by id. A table nothing references is not counted.
// Rules: a read that failed or came back in an unrecognised shape makes the TOTAL null ("n/a"), never
// a smaller number; the recognised shape is checked positively (a table's own key column), because a
// failed Data Table read can echo its input items with no error marker at all.
const cfg = $('CONFIG').first().json;
const prev = $('Sched Agg').first().json;
const CAP_MB = Number(cfg.data_table_cap_mb) || 50;

function measure(nodeName, keyCol) {
  let items;
  try { items = $(nodeName).all().map(i => i.json); }
  catch (e) { return { ok: false, why: nodeName + ' did not run' }; }
  // alwaysOutputData emits one KEYLESS item when a read matched nothing
  if (items.length === 1 && items[0] && Object.keys(items[0]).length === 0) items = [];
  const rows = items.filter(r => r && r.error === undefined && r[keyCol] !== undefined);
  if (rows.length !== items.length) {
    const err = items.find(r => r && r.error !== undefined);
    return { ok: false, why: nodeName + ': ' + (err ? String(err.error).slice(0, 100) : 'unrecognised row shape') };
  }
  let bytes = 0;
  for (const r of rows) bytes += Buffer.byteLength(JSON.stringify(r), 'utf8');
  return { ok: true, rows: rows.length, bytes };
}

const ledA = measure('DNC Active Rows', 'identity_key');
const ledR = measure('DNC Removed Rows', 'identity_key');
const dom = measure('DT Domains Rows', 'domain');
const clm = measure('DT Claims Rows', 'claim_key');
const parts = {
  ledger: (ledA.ok && ledR.ok) ? { ok: true, rows: ledA.rows + ledR.rows, bytes: ledA.bytes + ledR.bytes }
                               : (ledA.ok ? ledR : ledA),
  domains: dom,
  claims: clm,
};
const bad = Object.entries(parts).filter(([, p]) => !p.ok);
const mb = (b) => Math.round(b / 1e5) / 10;          // one decimal
const total = bad.length ? null : Object.values(parts).reduce((a, p) => a + p.bytes, 0);

// NET growth, from the last runs' own measurements (not "rows added": the claims table is pruned).
// Kept in static data, which persists only for production (scheduled) runs - a manual run reports
// no growth rather than a wrong one.
let growth7 = null;
try {
  const sd = $getWorkflowStaticData('global');
  const today = new Date().toISOString().slice(0, 10);
  const hist = Array.isArray(sd.dt_size_hist) ? sd.dt_size_hist.filter(h => h && h.date !== today) : [];
  const old = hist.filter(h => (Date.parse(today) - Date.parse(h.date)) >= 6 * 86400000)
                  .sort((a, b) => b.date.localeCompare(a.date))[0];
  if (total !== null && old && typeof old.total === 'number') growth7 = total - old.total;
  if (total !== null) hist.push({ date: today, total, per: Object.fromEntries(
    Object.entries(parts).map(([k, p]) => [k, p.bytes])) });
  sd.dt_size_hist = hist.slice(-10);
} catch (e) { /* static data unavailable in this run: growth stays null */ }

return [{ json: { ...prev,
  __dt_readable: total !== null,
  __dt_error: bad.length ? bad.map(([k, p]) => k + ' - ' + p.why).join('; ') : null,
  dt_total_mb: total === null ? null : mb(total),
  dt_cap_mb: CAP_MB,
  dt_pct: total === null ? null : Math.round(100 * total / (CAP_MB * 1e6)),
  dt_parts: Object.fromEntries(Object.entries(parts).map(([k, p]) => [k, p.ok ? mb(p.bytes) : null])),
  dt_growth_7d_mb: growth7 === null ? null : mb(growth7),
} }];
