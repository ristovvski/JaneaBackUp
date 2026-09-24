# Pre-fire artifact — dnc_projections_sweep go-live (item 1 of Nik's 2026-09-15 GO)

## What already happened (structural fix, deployed, verified)

- Live workflow `8qVXtI2ez5o6a9hc` patched via `zz_patch_projections_sweep_fanin_and_schedule.py
  --apply`: removed `PD Merge Write Paths` (Merge append, 3-input fan-in — the I-04 race shape) and
  `PD Write Barrier`; `PD Aggregate` now fans OUT directly to `SL Get Candidates` (single-source,
  matching the delta pusher's proven fix). Added `Sweep Timer` (hourly `scheduleTrigger`), wired to
  `CONFIG` alongside the existing `Webhook` (which stays — `dnc_fire_pipedrive_chunk.py`'s
  sanctioned concurrency-guarded fire path depends on it).
- Also synced two pieces of real live drift found while diffing (both pre-existing 2026-09-08 live
  fixes the generator never had — same "sync before patch" discipline used earlier this session):
  `PD Label Union`'s shape guard (refuses to derive a label set from an unrecognized `/v1/leads`
  response instead of silently wiping existing labels — the 224-lead incident this guards against),
  and `Combine Summaries`'s DRY RUN MARKER (prefixes every Slack line when `MODE != 'live'`, so a
  dry run can never read as a real success).
- Added: `PD Filter Pending` now also requires `status === 'active'` — a registry row that's been
  tombstoned (e.g. a false-positive reply) must never get a live Pipedrive DNC field write with no
  reverse path.
- `dnc_contract_tests.js`: 107/107 passing (2 old regression-guard tests rewritten for the new
  topology, 2 new tests added for the schedule trigger and the status guard).
- Post-patch verify: live node count 40 (41 − 2 removed + 1 added), active=true, names match
  exactly.

## What has NOT happened yet (this artifact gates it)

CONFIG still reads `MODE=dev`, `FIRE_PIPEDRIVE=false` on the live workflow — the schedule trigger
exists but every fire so far would be a dry run (Slack-only, `DRY RUN — ` prefixed, zero writes).
Going live is a separate, deliberate CONFIG-only patch (project convention: live-value flips are
never baked into the generator so a future regeneration/redeploy reverts to safe).

## Current pending backlog (fresh pull, 2026-09-15, post status-guard fix)

- **385** active registry rows with `pipedrive_person_id` set and `projections_state.pipedrive`
  null or `'pending'` — i.e. rows a live-mode chunk will actually try to write. (Was 386 before the
  status-guard fix excluded 1 tombstoned row.)
- `pd_chunk_size` = 250 → **2 chunks** to fully drain (250 + 135), not more, at the current backlog
  size. New organic reply_dnc/sales_personal_outreach entries keep arriving at roughly 4–8/day,
  negligible next to a 250-row chunk.
- Sample of 8 pending rows (random seed 1, for spot-check after the run):
  `pii-3547ae0f@example.invalid` (pid 47077, reply_dnc, added 2026-08-18)
  `pii-02b6a2a0@example.invalid` (pid 4753, meeting_dnc, added 2026-08-18)
  `pii-f620519e@example.invalid` (pid 45956, reply_dnc, added 2026-08-18)
  `pii-c9c2038c@example.invalid` (pid 58810, reply_dnc, added 2026-08-18)
  `pii-1e1ca090@example.invalid` (pid 46959, reply_dnc, added 2026-08-18)
  `pii-1e5c9fd2@example.invalid` (pid 44345, meeting_dnc, added 2026-08-18)
  `pii-1f1cd14e@example.invalid` (pid 4202, meeting_dnc, added 2026-08-18)
  `pii-b1108e59@example.invalid` (pid 42837, meeting_dnc, added 2026-08-18)
- These will be field-checked live (686 = 686) after the supervised first fire, same method used
  in the audit (direct Pipedrive API v2 GET, not trusting the workflow's own success claim).

## Plan

1. Patch CONFIG only: `MODE: "dev" → "live"`, `FIRE_PIPEDRIVE: false → true`. `FIRE_SMARTLEAD`
   stays `false` (per Nik: "stays false until the reason split exists").
2. Fire chunk 1 via `dnc_fire_pipedrive_chunk.py` (the sanctioned, concurrency-guarded firer —
   refuses to fire if a previous execution is still running, resolves the exact execution id,
   polls to terminal). Supervised: watch it to completion, don't walk away.
3. Post-verify: re-read the 8 sample rows' live Pipedrive 686 field directly; check the Slack post
   landed in #niks-channel (final-chunk / ops) or #gtm-telemetry (intermediate) as expected, with
   no `DRY RUN` prefix; confirm `projections_state.pipedrive` flipped to `done` for a processed
   sample via the registry.
4. Leave the hourly `Sweep Timer` to drain chunk 2 (135 rows) automatically on its own next fire —
   not manually forced, per Nik: "the 3 remaining windows drain automatically" (here, 1 remaining
   window).
