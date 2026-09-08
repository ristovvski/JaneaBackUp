# DNC BUILD — auditor's recovery map + structural concurrency guard

**Status: guard script built. Cursor-distinction question answered honestly (gap exists, safe
anyway). Waiting on chunk 1 (execution 15958) to finish before using the new guard for chunk 2+.**

## Auditor's recovery map (their measurement, recorded here for continuity)
- 2,010 of 2,264 person fields **written** (clean `None→686` sets, zero prior values destroyed —
  independently confirms the field-write idempotency claim on the wire, not just in code).
- **Zero** lead labels written anywhere.
- ~254 persons untouched.
- **Zero** labels lost — the auditor's 5-id baseline stayed intact across a full walk.

So the remaining work is: label stage for the 2,010 (whichever subset of those has an open lead)
plus both stages for the ~254 untouched.

## Cursor-distinction question — answered honestly, not assumed
Auditor asked me to verify `projections_state` distinguishes "field done, label pending" from
"nothing done" before firing again. Checked the actual node wiring in `build_dnc.py`
(`pd_mark_done_expr` / `pd_mark_done_with_lead_expr` / their `dt_update` call sites): **it does
not.** `projections_state.pipedrive` is only ever written to `'done'` at the end of the full
per-person chain — single-stage for no-lead rows (marked done right after the field write, correct
already), but gated on the label PATCH succeeding for with-lead rows. There is no intermediate
`field_done` marker.

**Why this is still safe to fire without adding one**: no-lead rows among the 2,010 are already
correctly marked `done` and get skipped entirely by `PD Filter Pending`. With-lead rows among the
2,010 are NOT marked done, so a re-fire will redundantly re-PATCH their field (idempotent, a no-op
`686→686` set) before correctly running the label stage for the first time. This is wasteful (some
extra API calls) but not incorrect — and it's exactly the case the auditor's own point 3 is designed
to verify (no second changelog entry for field 686 on those rows). Did not add a new intermediate
marker under incident pressure — that would add a new write/failure surface to fix a waste problem,
not a correctness one.

## Structural concurrency guard — built as a script, not a habit
`DNC_OBS_P1_build/dnc_fire_pipedrive_chunk.py`: refuses to fire if any execution of this workflow is
already `running` (the exact failure class that caused the incident — three fires landing before any
of them were visible as running). Fires exactly once, resolves the **specific** execution id it just
created (never "the newest execution in the list," which was the ambiguity that let duplicates
through), and polls that id specifically until terminal. Exits non-zero and refuses to suggest firing
again if the chunk didn't finish cleanly. This is now the only sanctioned way to fire this workflow.

## Attribution + timestamp notes (FYI from the auditor, no action needed)
- Two distinct Pipedrive credentials exist in n8n (`u25112064` sweep vs `u24599218` WF-1) — "axios"
  alone in a log line never identifies which workflow wrote something.
- `stoppedAt` lags real write activity — the last real write landed 16:03:58Z, after every recorded
  `stoppedAt` on the three crashed executions. Noted for any future timeline reconstruction: don't
  treat `stoppedAt` as the true boundary of a crashed execution's actual work.

## Next
Chunk 1 (execution 15958) still running as of this note. Once terminal: use
`dnc_fire_pipedrive_chunk.py` for every subsequent chunk, one at a time, until
`remaining_after_chunk` reaches 0. One full reconciliation report to the auditor at the end.
