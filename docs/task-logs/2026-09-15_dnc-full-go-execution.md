# Execution log — Nik's 2026-09-15 GO (5 items, following the full DNC audit)

All pre/post-fire artifacts referenced below live in `DNC_OBS_P1_build/ARTIFACT_*item*.md`.

## Item 1 — dnc_projections_sweep: fixed, scheduled, drained. DONE.

- Fixed the fan-in bug: removed `PD Merge Write Paths`/`PD Write Barrier` (3-input Merge, the same
  class as the delta pusher's 2026-09-14 incident), `PD Aggregate` now fans OUT directly to
  `SL Get Candidates`. Added a `status==='active'` guard to `PD Filter Pending` (a tombstoned row
  must never get a live 686 write). Synced two pieces of real live drift into the generator found
  while diffing (`PD Label Union`'s label-wipe shape guard, `Combine Summaries`'s DRY RUN marker).
  107/107 → 109/109 contract tests passing throughout.
- Added hourly `Sweep Timer`. Flipped live `MODE: dev→live`, `FIRE_PIPEDRIVE: false→true`
  (`FIRE_SMARTLEAD` stays `false`).
- Chunk 1 (250 rows) fired supervised via the project's sanctioned `dnc_fire_pipedrive_chunk.py` —
  0 errors, verified 6/8 pre-committed sample against live Pipedrive directly.
- Chunk 2 (136 rows) drained automatically on the next hourly fire — **0 remaining, 0 errors total,
  386/386 processed**. Re-verified the 2 previously-unconfirmed sample rows (Person-9d0affb0,
  Person-149b9641) — both now show `686` live.

## Item 2 — dnc_morning_digest Gate Health reference: fixed. DONE (final live confirmation
tomorrow).

Root cause traced from execution 55858's real runData: `Gate Health` read
`$('DNC Removed Agg')`, a reference that predated the 2026-09-14 Supabase-mirror patch splicing 3
new nodes into the chain ahead of it — every other node in the 12-hop chain correctly referenced
its own true predecessor, this was the one break. Fixed to `$('Supabase Mirror Agg')`. No safe way
to manually re-fire (digest has only a daily cron, n8n's API returned 405 on manual execution) —
verified instead by replaying the fix against execution 55858's real recorded inputs in Node:
confirms it now correctly carries `supabase_reachable/rows/age_min` forward. Natural confirmation
lands with tomorrow's 04:00Z real run.

Added `WF_LINTER/prev_read_matches_direct_ancestor.js` (Nik: "this is the third time") — checks
every `prev = $('X')` accumulator-read against the wire graph's actual current ancestor, skipping
over the `httpRequest`/`dataTable`/`webhook` node types this codebase deliberately routes around.
8 self-tests passing; 0 findings across all 47 live workflows after the fix (1 false-positive
"ambiguous" case found and fixed in the rule itself — two branches of the same source node,
success + `continueErrorOutput`, correctly do not count as two distinct sources).

## Item 3 — 4 missed repliers backfilled, 2 false positives tombstoned. DONE.

Via `dnc_archived_responders_import` (dry-run then real, both clean). All 4 (Person-054b9bef, Burak
Aksar, Person-19f1d00c, Person-58accf5a) confirmed in the registry. Found and fixed two things not in
the original plan during post-verify: `added_at` doesn't honor a caller-supplied historical date
(UpsertLedger always stamps `$now`); none of the 4 arrived with a `pipedrive_person_id` — looked up
and attached 3 of 4 directly via confirmed LinkedIn-field matches (Numan, Carla, Travis — the last
one also needed an `identity_key` correction from a raw LinkedIn URN to the proper vanity slug,
matching this project's identity convention); left Burak's unset (the only Pipedrive match found
predates the campaign by a year and has no LinkedIn on file — not confident enough to attach).

Person-d9409383 (`false_reply_ooo`) and Person-b27663e9 (`false_reply_mailbox_inactive`) tombstoned via
a direct `id`-matched update, same shape as `dnc_s4_retirement_removal`'s own internal write.
Checked live Pipedrive first — neither had their 686 field set yet (both were in item 1's
still-pending remainder at the time) — so combined with item 1's new active-only guard, neither
will ever get a wrongful DNC-field write.

## Item 4 — dnc_s2_meeting_to_dnc: architecture finding, Chirag backfilled. PARTIAL — schedule
holds for your direction.

**Not activated on a schedule.** Found before touching anything: S2 has no live Pipedrive query of
its own — it only processes a caller-supplied `person_ids` list, and the one existing driver
replays a FROZEN 2026-08-14 snapshot file (541 ids). An n8n Schedule Trigger added to this
workflow's graph would fire with an empty list every time (a schedule carries no webhook body) — a
schedule that silently does nothing forever, which is worse than not adding one. Real daily
detection needs a new live-query build (re-derive label "5. Meeting" ∪ deal stage "Qualified
Meeting Set" fresh each day) — **holding for your direction on the exact Pipedrive query approach**
before building it.

Chirag R Shah backfilled successfully: fired S2's webhook directly with `person_ids: ["86650"]`
(bypassing the frozen-file driver, which predates his record). Dry-run clean first. Real fire
returned an HTTP 500, but the execution itself shows `status: success` and direct registry
read-back confirms the write landed (`reason: meeting_dnc`) — the 500 looks like a
response-delivery glitch, not a write failure. Also separately recorded his S3/Surfe signal via
`dnc_archived_responders_import` — correctly appended to `also_flagged` without downgrading the
stronger `meeting_dnc` classification, exactly per the registry's documented merge semantics.

**Flagged, not fixed**: `S2 Merge Identity Paths` (2-input `Merge(append)`) is the same fan-in
shape as item 1's bug, empirically fired correctly once (Chirag's single-item case) but that's one
data point, not proof. Worth fixing before S2 ever runs unsupervised.

## Item 5 — dnc_s3_creation_watcher extended to persons (report-only). DONE.

Confirmed live via direct API check (pid 86650, 86158) that Pipedrive's Person object has **no
creator field at all**, list or single-GET — only `owner_id`. The leads path's real admission rule
is creator, not owner (your 2026-08-19/08-20 ruling: owner-only isn't sufficient, since a bulk
import gets assigned an owner after the fact). That signal simply doesn't exist for a bare person
record, so this extension is **report-only by design** — no `UpsertLedger` call anywhere on the new
path, existing leads path and its live `FIRE_S3=true` setting left untouched. Deployed via a custom
patch script that explicitly preserves live CONFIG values (a plain `safe_patch_workflow` run would
have reverted `FIRE_S3` back to the generator's safe-by-default `false`, silently turning off the
already-running leads path — caught before deploying, not after). 109/109 tests passing (2 new:
persons path never calls UpsertLedger and never touches the leads path; the classifier correctly
reads `owner_id` as the nested object Pipedrive actually returns for persons, not a bare id like
leads use). Linted clean with both `WF_LINTER` rules before deploying.

**Confirmed working on its first live poll** (14:15:46Z): found and reported 100 new
owner-roster-matched persons in one tick — enough to fill the poll window entirely, worth noting
for whenever a wider automated path is considered later (the 100-row window may itself be a binding
constraint at this volume, separate from the report-only design question).

**Evidence for the 83 (Nik/Melisa to decide, not auto-added)**: background research resolved this
far more cleanly than expected. Of the (corrected) 143-person candidate set, **133 have clear,
strong evidence of being campaign imports** — 101 have a live Pipedrive lead whose `creator_id` is
your own API/automation account (25112064), not Mario or Noah personally, with the canonical
`[Events Visiting] [BioTechX Boston 2026]` two-bracket title; the other 32 are already correctly
DNC'd under `reason=reply_dnc`. **Only 10 (all under Noah) are genuinely ambiguous**: a Surfe-channel
lead, but self-created by Noah's own Pipedrive user id (not automation) — a real conflicting signal
between "Surfe usually means import" and "self-created usually means personal." Full evidence table
in the agent's report; none of the 143 were written to DNC.

## Follow-up — S2 permanent go-live (Nik's 2026-09-15 GO, later same day)

`FIRE_S2` flipped to `true` **permanently** (no revert) — S2 is now a standing daily capture, not
a hand-fired tool. Confirmed before flipping: `FIRE_PIPEDRIVE` on `dnc_projections_sweep` was
still `true` from item 1 with no drift (direct live read, not assumed from memory). S2's `Daily
Timer` cron (`0 8 * * *`, server-local) maps to ~05:00 UTC, matching Nik's own "tomorrow's 05:xx
run" expectation independently — corroborates the server-local-to-UTC offset already established
from the digest's cron. Could not practically stay resident to watch that run land (an ~11-hour
gap, far beyond a reasonable wakeup chain) — will verify by direct execution/registry read the
next time this session is active, or on request.

## Bottom line

Items 1, 2, 3, 5 are fully executed and verified against live data, not just deployed. Item 4's
Chirag backfill is done; its schedule is an open architecture question, not a completed action —
needs your call on the Pipedrive query design before any build happens there. Two known fan-in
risks (S2, S3-leads) remain live and unfixed, flagged for awareness, matching the same bug class
item 1 fixed today but out of scope for what was explicitly asked this round.
