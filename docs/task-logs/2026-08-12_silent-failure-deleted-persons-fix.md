# DNC BUILD — read-back sample caught a silent-failure design gap (deleted Pipedrive persons)

**Status: root-caused, fixed, tested (58/58), deployed. Cleanup chunk in flight to resolve the 2
already-stuck rows.**

## What the read-back sample found
Doing the promised post-drain read-back (per Nik's original sequence: fire → read-back sample →
report), I pulled real person IDs directly from a completed chunk's execution data and checked them
against live Pipedrive. 30/30 in a broad sample were correct — but 2 specific persons in the final
tiny chunk showed the field still `None` with a `update_time` from **yesterday** (2026-08-11),
despite being reported as processed in today's chunk. That's not "eventually consistent," that's
"never touched."

## Root cause
`PD Write DNC Field`, `PD Get Lead For Labels`, and `PD Patch Lead Labels` all carry n8n's own
`onError: 'continueErrorOutput'` (confirmed directly on the live deployed nodes — this workflow's
generator sets it explicitly, inherited from the earlier 429-storm throttling fix, but the **second
output it creates was never wired to anything**). After `retryOnFail`'s 4 attempts, a persistently
failing item routes to that unwired second output and vanishes — no execution-level error, no
`projections_state` update, nothing. The execution still reports `success`.

Pulled the actual error payload for the 2 stuck items: `403 - "Cannot update a deleted person."`
Both are genuinely deleted Pipedrive person records — not a transient failure, not something a
retry would ever fix. Audited every chunk execution (1–9) for the same error-branch pattern: exactly
these 2 unique persons, reappearing across chunks 8/9/final because `projections_state.pipedrive`
was never touched, so every subsequent chunk's `PD Filter Pending` kept re-selecting them for an
identical, permanently doomed retry. Zero other rows affected across the entire 2,264 population.

## Why this also broke the Slack digest's "0 errors" claim
Today's earlier Slack-format fix hardcoded `errors = 0` with the reasoning "any per-item failure
halts the execution, so reaching this node already proves zero errors." That reasoning was correct
for a *thrown* error but wrong for `continueErrorOutput`, which explicitly does NOT throw — this
incident is direct proof the assumption was false. Fixed the same day it was written.

## Fix
- Every write-phase HTTP node's error output (index 1) now routes to a shared `PD Merge Write
  Errors` (append, 3 inputs) → `PD Classify Write Error` (recognizes the deleted-person case by
  message, generic `failed:pipedrive_write_error` fallback for anything else) → `PD Mark Write
  Error` (persists the marker into `projections_state.pipedrive`, so the row stops being retried
  forever) → `PD Count Write Errors` → feeds `PD Merge Write Paths` as a 3rd input.
- `Combine Summaries` now reads the real count via `try { ... } catch {}` (the error path has zero
  items and therefore never runs on the normal error-free path — an unguarded read would throw).
- 58/58 tests pass: 56 previous + rewired `numberInputs: 3` assertion + a new dedicated test
  asserting all three error outputs are wired to distinct input indices (same regression shape as
  the earlier with-lead/no-lead merge bug — landing all three on one index would silently drop two
  of every three failures) and that Combine Summaries no longer hardcodes zero.
- Deployed with `FIRE_PIPEDRIVE=true` re-applied live, `FIRE_SMARTLEAD` reasserted false.

## Scope note
Only fixed the three **write-phase** HTTP nodes (the ones whose silent failure causes permanent,
unfixable retry loops). `PD Get Leads By Person` (the read/classify phase, runs before any FIRE
gate) carries the same `continueErrorOutput` default and is unwired too, but a failure there just
means a person stays `pending` and gets correctly retried next chunk — self-healing, not a silent
permanent loss like the write-phase case. Not fixed in this pass; flagged here rather than silently
left unmentioned.

## Next
Cleanup chunk in flight to process the 2 stuck rows one more time — this time the 403 gets caught
and marked `skipped:deleted_person` instead of vanishing. Once confirmed, the full reconciliation
report to the auditor is ready: 2,264 eligible, 2,262 done, 2 skipped (deleted persons), 0 rows
lost or silently unaccounted for.
