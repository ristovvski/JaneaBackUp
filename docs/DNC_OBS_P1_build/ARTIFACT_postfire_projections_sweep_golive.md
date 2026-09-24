# Post-fire — dnc_projections_sweep go-live (item 1 of Nik's 2026-09-15 GO)

## Deployed

1. Structural patch (`zz_patch_projections_sweep_fanin_and_schedule.py --apply`): removed
   `PD Merge Write Paths`/`PD Write Barrier` (the fan-in bug), rewired `PD Aggregate` to fan OUT
   directly to `SL Get Candidates`, added hourly `Sweep Timer`, added `status==='active'` guard to
   `PD Filter Pending`, synced two pieces of real live drift found while diffing (`PD Label Union`'s
   shape guard, `Combine Summaries`'s DRY RUN marker). 107/107 contract tests passing.
2. Live-only CONFIG flip: `MODE: dev→live`, `FIRE_PIPEDRIVE: false→true`. `FIRE_SMARTLEAD` confirmed
   still `false`.
3. Chunk 1 fired via the sanctioned `dnc_fire_pipedrive_chunk.py` (concurrency-guarded, polled to
   terminal) — supervised start to finish.

## Result — execution 56426, 2026-09-15T13:34:39Z → 13:50:31Z (~16 min), status=success

```
DNC → Pipedrive: chunk 10/11 done
250 processed (186 labels, 64 field-only) · 135 remaining · 0 errors
Smartlead: 871 pending, 46 already unsub, 656 not found
```
(`chunk 10/11` is the display math treating the full 2,703-row historical candidate pool as the
denominator — 250+135=385 matches the pre-fire pending count exactly; the actual work done is
correct, this is just how the pre-existing chunk-number label is computed.)

Posted live (`mode: live, dry_run: false`, no `DRY RUN —` prefix) to `#gtm-telemetry`
(intermediate chunk, correct routing — final chunk goes to ops). `SL Get Candidates` fired
correctly (`Smartlead: 871 pending...` line present), confirming the fan-out fix works. `PD Count
Write Errors` never ran (0 errors, the normal case) — `Combine Summaries` read it defensively via
try/catch as designed.

## Independent post-verify (direct Pipedrive API, not trusting the workflow's own success claim)

8-row pre-committed sample: 6 confirmed `686` set live; 2 (Person-9d0affb0 pid 4753, Juan
Castellanos pid 44345) still unset — checked the registry directly, both still show
`projections_state.pipedrive: "pending"`, i.e. they fell in the 135-row remainder, not yet
processed. No drift between registry bookkeeping and live Pipedrive state in either direction.

## Outstanding

135 rows remain. The hourly `Sweep Timer` will pick them up on its own next fire — not force-fired
manually, per Nik: "the 3 remaining windows drain automatically" (here, 1 remaining window). Will
confirm fully drained (`0 remaining`, final-chunk post to ops/#niks-channel) on a later check.
