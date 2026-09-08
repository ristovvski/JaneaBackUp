# S3 GO: skip+log built, a critical silent-data-loss bug found and fixed on the real fire, then completed

**Status: DONE. 24/27 written (3 correctly skipped+logged), verified three independent ways
(registry query, live Pipedrive spot-check, execution data). Watcher active. Backfill's job is done
(idempotent, no need to re-run again).**

## Skip+log built for both S3 workflows
Identity-less matches (no email, no LinkedIn) now route to an explicit `S3(B) Has Identity?` gate
before ever reaching UpsertLedger, tagged `skip_reason: 'no_identity'`, merged back in (a real
`Merge` node, not a naive second edge — this varies per split-item within one execution, same shape
as the with-lead/no-lead bug from yesterday) and named in the Slack report for manual enrichment.
68 tests passed before touching anything live.

## Critical bug found DURING the live fire, not before it
First live fire reported "27 matches, 3 skipped" and posted successfully — but a direct registry
query (per the instruction to verify on the wire, not just trust the report) found only **1** row
where 24 were expected. Root cause: `exec_wf()`'s `executeWorkflow` node hardcoded `mode: "once"`,
which batches every fan-out item reaching it in one execution into a **single** subworkflow call —
but `DNC__UpsertLedger__v1` is written for single-item semantics (`$input.first()`). With "once",
only the first of 24 identity-bearing matches was ever processed; the other 23 were silently
dropped, with **zero errors and execution status "success" throughout**. Person-69cbb908 (the one that
landed) was luck of the fan-out order, not a real distinction.

Verified the fix (`mode: "each"`) directly before trusting it: fired 3 items with distinct emails
through a throwaway probe, confirmed all 3 came back independently correct (not the same first
item's result three times). Fixed at the `exec_wf()` helper level — every call site, not just the
two that fan out today, since a workflow that only ever sends 1 item now could start sending N
later with nobody remembering to re-check this. Added a regression test asserting every
`executeWorkflow` node across every workflow uses `mode: "each"`. Redeployed all four affected live
workflows (`heyreach_reply_to_dnc_ledger`, `dnc_wf4_sheet_intake`, both new S3 workflows) — the
first two are currently inactive so carried no live risk, but were wrong regardless and are now
fixed for whenever they do go live.

## Final state, verified three ways
- **Registry query** (direct, not just trusting the workflow's own report): 24 rows,
  `reason=sales_personal_outreach`, all `source_signal: surfe`.
- **3 random live Pipedrive spot-checks** (Person-9d5affed, Person-a81a10d5, Person-1ed215a4): all
  independently confirm `channel_id: "Surfe"`, `origin: "Marketplace"` on the actual lead record.
- **Execution data**: re-fire after the fix processed all 24 correctly; the earlier partial write
  (Person-69cbb908) was safely no-op'd by UpsertLedger's own idempotent merge, not duplicated.
- Posted final count + the bug disclosure to ops.

## Also live now
`dnc_s3_creation_watcher` activated (15-min poll, both signals unioned, same skip+log +
routine-vs-final channel routing). `FIRE_S3`/`FIRE_S3_BACKFILL` both `true` on their respective
live workflows (this backfill's job is done — a future re-fire would just find 0 pending Surfe
leads and report cleanly, but there's no reason to re-run it again for this org's current state).

## Next
Pivoting to Nik's new priority: the escalation-detector-first redesign for the cold-campaign
add-path gate (dominant add-path turned out to be manual Smartlead UI uploads, not an automated
path we control — inverts the build order). Starting with the mandated recon: Smartlead's
upload-to-first-send timing gap, since the detector's polling cadence must beat it.
