# Pre-fire artifact — P1 REPAIR: strip DO NOT CONTACT from every lead we labeled

Item 4 (second half) of Nik's 2026-09-16 P1 instructions: "REPAIR: strip DO NOT CONTACT from every
lead where WE added it (we have the union snapshots — only remove ours, never a human's), §9f.2
pre-post → my word → fire." **This artifact does not fire anything. Waiting for Nik's explicit go.**

Incident: [task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md](../task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md).
FIX (removing the branch that caused this) is already deployed and verified live —
`ARTIFACT_prefire_p1_projections_sweep_fix.md`.

## What's changing

Strips the DO NOT CONTACT label (`52a7c290-fc73-11f0-ad98-81d4703453f3`) from every lead in
`audit-artifacts/p1_frozen_lead_ids_600.json` — the exact 600 leads confirmed this incident,
extracted from `dnc_projections_sweep`'s own execution history (14 executions, 2026-09-08 →
2026-09-16). Every other label on each lead is left untouched (union-preserving strip, not a
replace). The person-level DNC Status field (686) is never touched by this — that's the sanctioned
mechanism and stays exactly as-is for everyone in the list.

## Mechanism — reusing, not rebuilding

`dnc_label_reversal` (live id `LQRfmEl4Wv0qpXsI`, currently `ARCHIVE__dnc_label_reversal` /
inactive — preserved not deleted after the 2026-08-14 incident it was built for, per this project's
"never delete incident workflow" rule) already implements exactly this operation: a webhook-
triggered, chunked (100/chunk), frozen-snapshot-driven strip with KEEP/REMOVE classification
(`client`/`unsubscribe` registry reasons are kept-labeled, everything else stripped) and defensive
handling of vanished/already-correct leads. **Confirmed live == local, zero node drift** — no
rebuild, no redeploy, reuse as-is.

**Why `frozen_ids` scoped to our 600 already satisfies "only remove ours, never a human's":** this
isn't a registry re-scan that could catch a human-applied label by coincidence of reason — it's the
literal list of leads the sweep's own PATCH calls targeted, extracted directly from n8n execution
data. A lead not in this list is never touched, full stop, regardless of what label it carries or
why.

## Pre-verified against the confirmed data (`dnc_label_incident_final_live.json`)

| | Count | What the tool will do |
|---|---|---|
| Total frozen ids | 600 | candidate set |
| Reason = `client` or `unsubscribe` (would be KEPT, not stripped) | **0** | none — verified, all 600 are `reply_dnc` (378), `sales_personal_outreach` (132), or `meeting_dnc` (90) |
| Currently still carries the label | 593 | → `stripped` |
| Already manually corrected by someone else | 6 (Person-e0711106, Daniel de Moraes Branco, Person-8c0e0fb8, Linda McQuade, Person-4f9fbdb2, Stefan Lukianov) | → `already_correct`, safe no-op, not re-touched |
| Lead converted to a deal / deleted since | 1 (Person-a731ca52, person 84141) | → `fetch_error`, a known non-crashing outcome (matches the 5-vanished-lead case from the 2026-08-14 incident), surfaced not silently dropped |

**Expected final tally: `stripped=593 already_correct=6 fetch_error=1 kept_for_reason=0
no_registry_match=0 no_lead=0` (sum=600, matches the frozen set exactly).**

## What firing actually does (`zz_fire_p1_label_repair.py`)

1. Reactivates `dnc_label_reversal` (required — a webhook trigger on an inactive workflow never
   receives production calls) and sets `FIRE_REVERSAL=true`.
2. Fires chunks of 100 sequentially against the local webhook, `frozen_ids` = the 600, no
   `live_exclusion_ids` needed (the tool's own already-built classification handles the 6-fixed and
   1-gone cases cleanly, as shown above).
3. Between chunks: refuses to fire if a prior execution is still running, polls each execution to
   completion, aggregates `R Combine`'s per-chunk tallies, stops on any non-`success` execution
   status rather than pushing through.
4. On completion (or any abort): deactivates `dnc_label_reversal` again — re-archived, preserved,
   matching how it's kept between incidents.
5. Prints the final tally against the expected numbers above — a mismatch is visible immediately,
   not buried.

`CLEARED_TO_FIRE = False` is hardcoded at the top of the script — same pattern as the original
reversal's own driver (`dnc_fire_reversal_chunk.py`). It refuses to run at all until that's flipped
by hand, and only after Nik has seen this artifact and said go.

## Risk

- **Reversible in principle** (re-adding a label is a normal PATCH) but not something to fire
  casually — hence the explicit hold. The 593 stripped leads regain visibility to Melisa's handover
  automation (425 of them currently blocked positive repliers) — that IS the intended effect, not a
  side effect.
- The only write this touches is `label_ids` on each of the 600 leads, PATCHed to remove exactly one
  id. Nothing else on the lead, and no person-level field, is touched.
- No other automation in this estate writes to this same label (confirmed during the FIX work — the
  only writer was the now-removed branch), so no race with a live writer is possible.

## Plan once Nik says go

1. Flip `CLEARED_TO_FIRE = True` in `zz_fire_p1_label_repair.py`.
2. `python zz_fire_p1_label_repair.py`.
3. Report the final tally back, cross-checked against the 593/6/1 expectation above, and confirm
   `dnc_label_reversal` is deactivated again afterward.
