> **⚠ ORPHANED as of 2026-09-03.** `i04_snapshots` has no active reader or writer: the only
> workflows that used it (`dnc_i04_daily_summary`, `dnc_i04_weekly_reconciliation`) were
> retired. The table is left in place, not deleted. **Do not build on it** — it is
> referenced **by name**, not by id, which has failed live on tables that certainly
> existed (linter rule `R13`). Anything that needs it must first switch to `mode: "id"`
> using the id from the table's URL.

# Create the `i04_snapshots` Data Table

Same situation as every other Data Table this project has needed: there's no verified API for
table *creation* (only for reading/writing rows once a table exists — confirmed live again this
build, same as `datatables/CREATE_DATATABLES.md`'s own note from the original registry build).
The UI is the fast, risk-free path.

**In the target n8n project: Data Tables → Create data table**, name it exactly `i04_snapshots`,
then **Add Column** for each of the 8 columns below (do not add `id`/`createdAt`/`updatedAt` —
n8n manages those). Do this once; `dnc_i04_daily_diff` and its DEV__ sandbox twin both read/write
this same table by name.

| column | n8n type | notes |
|---|---|---|
| `date` | String | `"2026-08-20"` — the row key. Upsert matches on this column. |
| `captured_at` | Date | when the walk actually ran |
| `source` | String | `"n8n live walk"` |
| `counts_json` | String | JSON: `{leads, persons, dnc_labelled, dnc_field_686}` |
| `leads_json` | String | JSON: `{lead_id: [labels_joined, person_id, add_time]}` — the whole day's lead estate |
| `persons_json` | String | JSON: `{person_id: [add_time, update_time, email_lc, lh_slug, dnc686]}` |
| `dnc_labelled_json` | String | JSON array of lead ids carrying the DNC label |
| `kept_reason` | String | `"daily"` or `"weekly"` — set by the retention-prune step, drives what survives the rolling cutoff |

## Storage size — read before creating

At the current ~58k-lead estate, `leads_json` + `persons_json` together run an estimated
**8–15 MB per row** (uncompressed JSON — gzip isn't available inside n8n's Code node sandbox;
verified live, not assumed — see `build_i04.py`'s own header comment). With 30 daily rows rolling
plus ~26 weekly rows kept for 6 months, that's roughly **56 rows × 8–15 MB ≈ 450 MB–840 MB**
total table size.

n8n's Data Table default cap is **50 MB**. This table will exceed it almost immediately.
**`N8N_DATA_TABLES_MAX_SIZE_BYTES` needs raising before this goes live for real** — the same
lever the original registry build already flagged for exactly this reason. Recommend setting it
to at least 1 GB to leave headroom.

If a single **row's** own size also has a hard n8n-side ceiling (not yet verified — the earlier
gzip round-trip test only proved a 5000-record ~500 KB payload compresses cleanly, not that an
8-15 MB row write succeeds), that's the next thing to check once the table exists and the first
real snapshot is stored. Flagging it rather than assuming either way.

## Once created

Nothing else to configure — `dnc_i04_daily_diff` (and its `DEV__` sandbox copy) already reference
this table by name in every read/write node. Run the sandbox copy once real end-to-end (walk →
store → diff → post) is what confirms the row-size question above; that run is blocked until this
table exists.
