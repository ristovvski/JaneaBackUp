# Pre-fire artifact — item 5 of Nik's 2026-09-15 GO: extend S3 to poll Persons

## What's changing

Adding 8 new nodes to live `dnc_s3_creation_watcher` (`QM21Vd7VId7PBdqh`), fully parallel to the
existing (tested, running) leads path — same `Poll Timer`/`CONFIG` trigger, new independent branch:
`S3 Get Recent Persons` → `S3 Classify Persons` → `S3 Filter New Persons` → `S3 Persons Any New?`
→ `S3 Persons Report` → `S3 Persons MODE == dev?` → `S3 Persons Send Guard` → `S3 Persons Dev
Summary`.

**Report-only — no registry writes from this path, at all.** Root cause (confirmed live via direct
API check against real records, pid 86650 and 86158): Pipedrive's Person object has no `creator_id`
field whatsoever, list or single-GET — only `owner_id`. The leads path's real admission rule is
CREATOR, not owner (Nik's 2026-08-19/08-20 ruling: owner-only membership isn't sufficient, since a
bulk campaign import gets assigned an owner after the fact with no personal outreach involved).
That signal doesn't exist for a bare person record, so this extension surfaces owner-roster-matched
persons to `#gtm-telemetry` for human review and stops there — no `UpsertLedger` call anywhere on
this path, not gated by `FIRE_S3` because there's nothing for that flag to gate.

`CONFIG`'s live values (including `FIRE_S3: true`, already flipped in an earlier session for the
existing leads path) are explicitly preserved — this patch adds the new fan-out wire without
touching or reverting anything already live. 109/109 contract tests passing (2 new tests added:
persons path is fully separate from the leads path and never calls UpsertLedger; the classifier
correctly reads `owner_id` as a nested object, not a bare id — confirmed via a targeted regression
test after finding this shape mismatch live). Linted clean (0 stale prev-reads, 0 unresolved
references) with both `WF_LINTER` rules before deploying.

## Known residual, not fixed today (flagged, matching item 4's S2 finding)

`S3 Merge Identity Paths` — the EXISTING leads path's own 2-input `Merge(append)` — is the same
fan-in shape as item 1's fixed bug. Pre-existing, already running in production; out of scope for
this item (extending to persons, not fixing the leads path). Flagging for awareness alongside item
4's identical finding on S2.

## Post-fire plan

Deploy, then watch the next 1-2 poll cycles (15-min cadence) for a clean `S3 Persons Report` post
(or correctly silent if nothing new matches) — no forced test fire needed, the existing 15-min
schedule already covers verification within the hour.
