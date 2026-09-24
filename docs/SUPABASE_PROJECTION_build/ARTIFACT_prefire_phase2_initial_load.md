# Phase 2 — Supabase initial load — §9f.2 pre-post artifact

Дата: 2026-09-14. Files built, logic-tested locally (15/15 pass), **NOT deployed, NOT fired**.
Waiting on Nik's word before anything touches Supabase for real.

## What's built (files only)

- `build_supabase_sync.py` → generates `workflows/dnc_supabase_initial_load/dnc_supabase_initial_load.json`
  (9 nodes): webhook takes `{table, rows, dry_run}` for ONE CHUNK, or `{table, finalize:true,
  row_count, dry_run}` to log the sync-run summary. `dry_run` defaults `true` and gates BOTH
  real-write paths (chunk upsert AND the meta-log insert) — verified structurally (a dry-run
  finalize call cannot reach either Supabase-writing node).
- Auth: `predefinedCredentialType` + `nodeCredentialType: supabaseApi`, credential id
  `u6wyGnYC71Sr1KgT` ("Supabase account") — confirmed live via read-only probes against all three
  tables today.
- Write mechanism: real PostgREST upsert — `POST .../rest/v1/<table>?on_conflict=<pk>` with
  `Prefer: resolution=merge-duplicates`. `on_conflict=id` for `dnc_registry`, `on_conflict=domain`
  for `dnc_domains`.
- `fire_supabase_initial_load.py` — driver: reads both source n8n Data Tables fresh (via a
  throwaway read-only probe, deployed/fired/deleted each run), maps each row to the exact target
  column set, chunks at 500, dry-run by default, `--live` to write for real.
- **Design choice flagged for your awareness**: no second meta table was created for
  `dnc_domains` — its sync runs log into the existing `dnc_registry_meta` table too, distinguished
  by `source = 'initial_load:dnc_domains'` vs `'initial_load:dnc_registry'` (that column is free
  text already, no schema change). Say the word if you'd rather it get its own table.

## Count (fresh, live, read-only — pulled today, not the 2026-09-09 numbers)

| source | total | breakdown |
|---|---|---|
| `dnc_registry_dev` (n8n) | **25,729** | 25,726 active + 3 removed |
| `dnc_domains` (n8n) | **1,373** | all active |
| `dnc_registry` (Supabase) | 0 | empty, confirmed accessible |
| `dnc_registry_meta` (Supabase) | 0 | empty, confirmed accessible |
| `dnc_domains` (Supabase) | 0 | empty, confirmed accessible (after your grant fix) |

Registry total dropped from the 2026-09-09 probe's 33,138 mostly because of the 26-Aug tombstone
hard-delete (7,450 rows) done earlier this project, plus normal churn since.

## 5 examples (real, from today's live read)

**`dnc_registry` → Supabase `dnc_registry`** (all 26 columns copied 1:1, including the literal
`createdAt`/`updatedAt` camelCase system columns):

| id | identity_key | entry_type | reason | status | full_name |
|---|---|---|---|---|---|
| 1 | arjunmoorthy | employee_connection | manual_offboard_eligible | active | (null) |
| 2 | zacwalker | explicit_opt_out | client | active | (null) |
| 3 | pii-f59eb465@example.invalid | negative_reply | reply_dnc | active | Person-ce4c420c |
| 4 | debadiptab | employee_connection | manual_offboard_eligible | active | (null) |
| 5 | rochaboto | employee_connection | manual_offboard_eligible | active | (null) |

**`dnc_domains` → Supabase `dnc_domains`** (only 5 columns copied — `domain`, `added_at`,
`source`, `reason`, `status`; the n8n row's own `id`/`createdAt`/`updatedAt` are dropped since
Supabase's `dnc_domains` schema doesn't carry them, `domain` is its PK):

| domain | added_at | source | status |
|---|---|---|---|
| 100programmers.com | 2026-06-29T15:03:51.311Z | clay_company_dnc_import | active |
| 10pearls.com | 2026-06-29T10:37:15.059Z | clay_company_dnc_import | active |
| 10xhumans.io | 2026-07-13T13:20:50.609Z | clay_company_dnc_import | active |
| 180dc.org | 2026-06-29T10:35:12.710Z | clay_company_dnc_import | active |
| 20visioneers15.com | 2026-06-29T15:03:28.819Z | clay_company_dnc_import | active |

## Fire plan (chunked, matches every other bulk write in this project)

1. Deploy `dnc_supabase_initial_load` (not yet done).
2. Dry-run BOTH tables in full (52 chunks of ≤500 for `dnc_registry`, 3 for `dnc_domains`) — the
   driver already defaults to this; confirms 0 validation errors before any real write.
3. Live fire, chunked (same 500-row chunk size as `dnc_domains_import`/`dnc_tombstone_hard_delete`).
4. One `finalize:true` call per table logs the sync run to `dnc_registry_meta`.
5. Post-verify: independent read-back of both Supabase tables — total row count matches source
   count exactly, plus the same 5 spot-check rows above compared field-by-field.

## Waiting on

Your word to (a) deploy `dnc_supabase_initial_load` and (b) run the driver — dry-run first is safe
to run unprompted (writes nothing), but I'm holding even that until you say go, per "nothing runs
without my word."
