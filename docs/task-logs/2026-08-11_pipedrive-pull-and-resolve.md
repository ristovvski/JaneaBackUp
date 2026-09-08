# DNC BUILD — Pipedrive pull (Phase A) + resolve (Phase B), gate override

**Status: DONE.**

## What was asked
Owner granted a gate override for the PULL only (read-only): don't wait for the FLIP-STABLE
sentinel or tonight's window — run the full Pipedrive pull (56k persons, throttled, checkpointed)
+ Phase B in-memory resolve now, while the system is in a quiet paused state. Produce a resolution
report (matched/creatable/needs-review counts). SEED WRITE gate stays unchanged (migration ✅ +
resolution report + owner's explicit word, in that order). Disable/adjust the
`dnc-pipedrive-pull-gate` scheduled watcher so it doesn't double-run when the sentinel eventually
posts.

## What happened
1. Disabled the `dnc-pipedrive-pull-gate` scheduled task (`enabled: false`, description updated to
   explain why) before starting, so it can't fire mid-run or duplicate the work overnight.
2. Ran a 1-page `--sanity` pull first to confirm the Pipedrive token still works before committing
   to the full throttled run — it did (500 persons, valid next_cursor).
3. Ran the full pull (`dnc_pull_pipedrive_persons.py`, no `--sanity`). Completed clean in ~2
   minutes: **56,657 persons**, no interruption, no checkpoint resume needed. Index built
   (`fixtures/pipedrive_persons_index.json`) by li_url_canon/email_lc/member_id, live vs
   soft-deleted tracked separately.
4. Ran Phase B resolve (`dnc_resolve_people_dnc.py`) against the 23,838-row People-DNC seed
   preview. Zero API calls, zero writes, zero persons created (script-enforced, not just policy).

## Result — resolution counts
- Matched, clean single person: **2,264**
- Matched, needs review (ambiguous — identity resolves to >1 live person): **64**
- Matched only a soft-deleted person: **0**
- Creatable (no existing person): **21,510** (manual_offboard_eligible 21,269 / manual_sheet 123 /
  client 93 / reply_dnc 25)

Full writeup: [PIPEDRIVE_RESOLUTION_REPORT_2026-08-11.md](../DNC_OBS_P1_build/PIPEDRIVE_RESOLUTION_REPORT_2026-08-11.md).
Raw detail: `DNC_OBS_P1_build/fixtures/people_dnc_resolution_report.json`.

## Gate status
SEED WRITE gate unchanged and still pending: migration done ✅ + resolution report ✅ (this) +
owner's explicit word ⏳. Nothing was written to Pipedrive or to `dnc_registry_dev`.

## Improvable
- The 64 ambiguous rows need an owner decision before Pass 1 seed write: pick a canonical person
  per identity, or confirm they're legitimately distinct people sharing a normalized LinkedIn slug.
  Full list is in the raw JSON (`results.matched` where `ambiguous: true`).
