# Pre-fire artifact — S3 persons branch goes live (Nik's 2026-09-15 follow-up GO)

## What's changing

Structural patch to `dnc_s3_creation_watcher` (live id `QM21Vd7VId7PBdqh`): adds a write path off
the existing report-only persons branch (`S3 Persons Split Matches` → `S3 Persons Build Upsert
Input` → `S3 Persons Has Identity?` → `FIRE_S3_PERSONS?` → `S3 Persons Call UpsertLedger`), plus
updates `S3 Classify Persons` to extract LinkedIn/email during classification (the list fetch
already carries full identity per person — confirmed live, no extra per-item HTTP call needed
unlike the leads path) and `S3 Persons Report` to show live/dry-run status + a no-identity skip
list (defensively guarded — learned live today on S2's own rebuild that an unguarded named-ref
read throws when that node didn't run this poll).

Gated by its own new flag, `FIRE_S3_PERSONS`, deliberately separate from `FIRE_S3` (already
permanently `true` for the leads path) — this patch explicitly **preserves** that live value rather
than reverting it to the generator's safe default, same custom-merge approach used for the
original persons extension. `FIRE_S3_PERSONS` starts `false` — one supervised poll cycle gets
verified with the new code live but not writing, before flipping it.

110/110 tests passing (rewrote the now-obsolete "report-only, never calls UpsertLedger" test to
assert the new live-write structure instead — no Merge node on the persons path, clean dead ends,
FIRE gate wired correctly, defensive named-ref read). Linted clean (0 stale prev-reads, 0
unresolved references).

## Policy change (Nik, this message)

"No distinction needed — Surfe-sourced or personal, roster-owned means protected... owner ∈
roster → registry row, no source check." Supersedes the original report-only design's whole
rationale. `DNC__UpsertLedger__v1`'s own reason-strength merge (unchanged, already proven) handles
"already covered by something stronger" automatically — no extra logic needed here for that.

## What already happened moments ago, informing this deploy

Backfilled 111 people (10 "ambiguous" + 101 campaign-import, excluding 32 already-`reply_dnc`)
under the same new policy — see `ARTIFACT_prefire_s3_roster_owned_backfill.md`. Found live: all 10
"ambiguous" ones were ALREADY `sales_personal_outreach` (the original, untouched leads watcher
caught them independently via its own stricter creator-based rule). 82 written fresh — with one
real bug found and fixed along the way: `dnc_archived_responders_import` doesn't auto-resolve a
Pipedrive person id from name/email (same lesson from this session's very first backfill,
re-learned the hard way by not applying it here first time either — corrected via a direct,
verified, person-id-matched patch of all 82 rows). Confirmed clean now.

## Plan

1. Deploy structurally (`FIRE_S3_PERSONS=false`).
2. Watch the next natural 15-min poll cycle land safely as report-only-equivalent (write path
   exists but the FIRE gate blocks it) — no forced test fire needed, the existing schedule covers
   it within 15 minutes.
3. Flip `FIRE_S3_PERSONS: false → true`, permanently (matching Nik's stated intent for this to be
   a standing capture like the leads path, not hand-fired).
4. Confirm the following poll cycle actually writes, via direct registry read-back.
