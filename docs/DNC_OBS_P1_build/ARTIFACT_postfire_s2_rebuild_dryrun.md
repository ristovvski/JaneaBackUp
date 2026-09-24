# Dry-run results + 2 bugs found and fixed — S2 rebuild (before going live)

## Bug 1: unguarded named-ref read (execution 57171, error)

`S2 Combine` read `$('S2 Log No Identity').all()` unconditionally. On the (common) 0-candidates
poll, that node never executes at all, and n8n's named-ref `.all()` throws
`ExpressionError: Node hasn't been executed` rather than returning an empty array. Fixed with the
same try/catch guard already used elsewhere in this project for exactly this shape (PD Count Write
Errors). Redeployed, re-tested clean (execution 57176, success).

## Bug 2: swapped label/stage reference (execution 57176, wrong data, not caught by CI)

`S2 Aggregate Candidates`'s own direct wire predecessor is `S2 Classify Stage Signals` (stage runs
second in the hand-sequenced chain) — so `$json` inside it is the STAGE aggregate. The first build
had this backwards: `$json` was treated as `labelAgg`, and the named reference ALSO pointed at
`S2 Classify Stage Signals` a second time for `stageAgg` — so both variables held identical stage
data. Real consequence, caught live: execution 57176 showed a single real dual-signal-looking
candidate (Chirag R Shah) with BOTH entries as `kind:'stage'` — the label signal was structurally
never read at all. My own unit test made the exact same mistake in its mock, so it didn't catch
this either — fixed both the implementation and the test (now asserts the specific reference shape
by regex, not just behavior, so this can't silently regress the same way twice).

Fixed and redeployed (execution 57177, success): now shows `label_count: 46, stage_count: 1` —
Chirag correctly appears ONLY as `kind:'stage'` (he has a deal in the target stage but was never
actually given the "5. Meeting" lead label — the earlier "both" reading was purely the bug).

## What the real data actually looks like (still dry-run, FIRE_S2=false)

46 of the 47 candidates are `kind:'label'` — almost all names already familiar from earlier in this
session's audit (Person-c8f2fbf3, Person-a3b5622e, Person-77ae5e4a, Person-b66505b6, Person-03386e72, etc.).
Spot-checked 5 directly against the current registry before firing for real:

| Person | Current reason | Expected after S2 fires |
|---|---|---|
| Person-03386e72, Person-b66505b6, Person-77ae5e4a, Person-a3b5622e | `reply_dnc` (stronger) | unchanged reason, `also_flagged` gains a `meeting_dnc` entry (source_ref differs from their existing reply_dnc source_ref) |
| Person-c8f2fbf3 | `sales_personal_outreach` (weaker) | **upgraded to `meeting_dnc`**, her existing signal moves to `also_flagged` |
| Chirag R Shah | `meeting_dnc` already (from yesterday's manual S2 test), `also_flagged` already has the S3/Surfe signal | idempotent re-confirmation, no new `also_flagged` entry (same source_ref as already recorded) |

Confirms the real-world scale of the documented trade-off: most of today's 46 label matches are
NOT genuinely new "5. Meeting" applications today, they're leads that already carried the label
from earlier and got touched for an unrelated reason in the last 24h (bumping `update_time`).
Harmless by design (idempotent upsert; a same-reason/same-source_ref repeat adds nothing new) but
worth knowing before treating "46" as "46 new meetings."

## Next: flip FIRE_S2 live, fire for real, verify the predicted outcomes above directly.
