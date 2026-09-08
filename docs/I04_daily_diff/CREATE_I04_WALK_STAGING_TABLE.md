> **⚠ ORPHANED as of 2026-09-03.** `i04_walk_staging` has no active reader or writer: the only
> workflows that used it (`dnc_i04_daily_summary`, `dnc_i04_weekly_reconciliation`) were
> retired. The table is left in place, not deleted. **Do not build on it** — it is
> referenced **by name**, not by id, which has failed live on tables that certainly
> existed (linter rule `R13`). Anything that needs it must first switch to `mode: "id"`
> using the id from the table's URL.

# Create the `i04_walk_staging` Data Table

Second table needed for the chunked-walk rebuild (the OOM incident's fix). Same UI-create
process as `i04_snapshots` — no verified creation API exists.

**In the target n8n project: Data Tables → Create data table**, name it exactly
`i04_walk_staging`, add these 4 columns:

| column | n8n type | notes |
|---|---|---|
| `walk_date` | String | which day's walk this row belongs to, e.g. `"2026-08-21"` |
| `resource` | String | `"lead"` or `"person"` |
| `entity_id` | String | the lead id (uuid) or person id (numeric, as string) |
| `data_json` | String | the minimal per-entity record, same shape as before: `[labels_joined, person_id, add_time]` for a lead, `[add_time, update_time, email_lc, lh_slug, dnc686]` for a person |

## Why a second table, not just bigger rows in `i04_snapshots`

The crash came from one execution holding the WHOLE estate's worth of HTTP-paginated data in
memory at once (hundreds of page-fetches accumulating in a single node's output). The fix is
chunked: each execution fetches only a small, bounded number of pages (matching S3B's own proven
chunk size — 3 pages × 500/page = 1,500 records) and writes THAT chunk as individual small rows
here, then stops. A separate scheduled tick picks up where the last one left off (cursor
persisted, not held in memory) until the whole estate is walked — spread across many small
executions instead of one giant one.

Once a day's walk is fully done, a single COMPACTION step reads all of that day's staging rows in
one bulk query (a plain Data Table read, not hundreds of network round-trips — a fundamentally
cheaper operation than the walk itself), builds the day's real snapshot row in `i04_snapshots`,
and deletes the staging rows for that day. So `i04_walk_staging` only ever holds AT MOST one day's
in-progress walk (~58k small rows momentarily) — never accumulates across days.

## Once created

Nothing else to configure — the rebuilt `dnc_i04_daily_diff` references this table by name.
