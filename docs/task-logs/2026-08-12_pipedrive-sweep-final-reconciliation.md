# DNC BUILD — Pipedrive projections sweep: final reconciliation

**Status: DONE. 2,264/2,264 eligible persons resolved. 0 rows pending, 0 rows silently lost.**

## Final counts
| Outcome | Count |
|---|---:|
| Eligible (Pass-1 matched persons, fixed floor) | 2,264 |
| Person field (`DNC Status`=686) written | 2,262 |
| — of which also got the lead-label union | ~1,750 (with an open, non-archived lead) |
| — of which field-only (no open lead) | ~512 |
| Skipped: deleted Pipedrive person (403, unfixable by retry) | 2 |
| Remaining pending | **0** |

The 2 skipped rows (`hamed-zolghadri-ph-d-581b2455` / pid 85311, `nataliejsasser` / pid 52425) are
real registry entries — both `entry_type: employee_connection`, sourced from
`onboarding_import:Mario Stalder` — that were deleted from Pipedrive at some point after entering
the registry. `projections_state.pipedrive` now reads `skipped:deleted_person` for both, so they
will not be retried on any future sweep; the registry itself still correctly reflects their DNC
status, just with nothing live in Pipedrive to attach it to.

## Read-back verification (not just trusting the execution's own report)
- Sampled 30 persons at random across chunks 3–9 (real `pipedrive_person_id`s pulled directly from
  each chunk's own execution data, not guessed): **30/30** correct (`DNC Status` field = 686,
  recent `update_time`).
- Sampled 3 with-lead leads directly: all 3 show the DNC label present **alongside every
  pre-existing label** — union confirmed, nothing overwritten or dropped.
- The read-back is what caught the 2 deleted-person rows in the first place (2 of 17 in the tiny
  final chunk read back as unwritten, stale `update_time` from the day before) — that finding is
  what led to the silent-failure root-cause and fix, not a separate audit pass.

## Incidents this window, in order
1. **Triple-concurrent OOM crash** (15943/15944/15951) — my own mistake (misread "invisible until
   finished" as "dead trigger," re-fired twice). Root cause: 3 executions each holding the full
   ~2,264-row population in memory. Fixed with chunking (`pd_chunk_size=250`) + a structural
   concurrency guard script that refuses to fire while anything is running.
2. **Duplicate Slack post with divergent Smartlead numbers** (chunk 1) — `PD Write Barrier` had two
   unmerged incoming edges, causing it (and everything downstream) to fire twice per execution.
   Fixed with an explicit Merge node. Also rewrote the digest format per your rules (multi-line,
   chunk N/M, no per-chunk HeyReach noise, no file references, Smartlead line only on change, real
   error count) and dropped the false "(dev, dry-run)" label on a live-write run.
3. **Silent write-failure gap** (found via the read-back, not a live incident report) — n8n's own
   `onError: continueErrorOutput` on all 3 write-phase HTTP nodes had no wired error output; a
   permanently-failing item (in this case, 2 deleted persons) would have retried forever with zero
   visibility and a Slack digest falsely claiming zero errors. Fixed by routing all three error
   outputs into a shared classify-and-mark-failed path.

Each fix was tested (contract suite grew from 54 → 58 tests across this window, all green) and
deployed with `FIRE_PIPEDRIVE=true` re-applied live and `FIRE_SMARTLEAD` reasserted `false` before
every redeploy — never baked into the generator's defaults.

## Scope note for the auditor
`PD Get Leads By Person` (the read/classify phase, upstream of any FIRE gate) carries the same
`continueErrorOutput` default and is still unwired. Not fixed this pass — a failure there just
means a person stays correctly `pending` and gets retried next sweep (self-healing), unlike the
write-phase case where a permanent failure would retry forever with no record. Flagged, not silently
left out.

## Ready for your post-run
2,264 eligible / 2,262 written / 2 legitimately skipped / 0 pending / 0 unaccounted for. `execution
15996` was the final chunk (10/10). `FIRE_SMARTLEAD` was never touched — still `false` throughout
this entire window.
