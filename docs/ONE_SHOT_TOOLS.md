# One-shot tools

Workflows built to be fired **by hand, once or occasionally**, for a specific job. They are archived
(deactivated, `ARCHIVE__` prefix) but **kept**, because the job they do may come round again and
rebuilding one costs more than storing it.

**Nothing here is deleted without Nik's word.** The delete-after dates below are a proposal — a
prompt to re-decide, not an instruction to a future session.

| Tool | What it does | Last used | Archived | Delete-after *(proposed)* |
|---|---|---|---|---|
| `ARCHIVE__dnc_label_reversal` | Re-reads leads and strips labels that should no longer be there. Accepts explicit protect-lists (`frozen_ids`, `live_exclusion_ids`). Dry-run unless `FIRE_REVERSAL` is set. | 2026-08-14 | 2026-09-03 | 2027-03-03 |
| `ARCHIVE__dnc_s3_surfe_backfill` | Historical twin of the creation watcher: pages back through older Pipedrive leads 500 at a time instead of watching new ones. Dry-run unless `FIRE_S3_BACKFILL` is set. | **never run** | 2026-09-03 | 2027-03-03 |
| `ARCHIVE__dnc_s4_event_populations` | Bulk-loads an entire Smartlead or HeyReach campaign's contact list onto the registry as *event contacted* — the weakest signal: we touched them once. Dry-run unless `FIRE_S4` is set. | 2026-08-14 (148 runs) | 2026-09-03 | 2027-03-03 |
| `ARCHIVE__dnc_expiry_null_oneshot` | Removed `expires_at` from every registry row — the migration that made registry entries permanent. | 2026-08-31 (15 runs) | 2026-09-03 | **2026-12-03** — a completed one-way migration; keep only until the change is clearly settled |

## Before re-running any of them

1. **Read its dry-run report first.** All four default to dry-run and require an explicit flag to
   write. That default exists because three of the four write to the registry.
2. **Re-activate, run, then deactivate and re-archive.** Leaving a one-shot tool active is how
   `dnc_s3_surfe_backfill` ended up ACTIVE with zero runs for three weeks.
3. **Check the switch state has not drifted** — every one of them reads `MODE: dev` today, which
   controls where its summary posts.
4. `ARCHIVE__dnc_s4_event_populations` calls the registry writer. Confirm the reason it files is
   still the one you want; the writer rejected an unrecognised reason as recently as 18 August.

## Not one-shot, but also archived

The other eight archived workflows are superseded or scaffolding rather than tools, and are listed
with their reasons in [`ARCHIVE_2026-09-03/REPORT.md`](ARCHIVE_2026-09-03/REPORT.md).
