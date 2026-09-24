# Pre-fire artifact — item 4 of Nik's 2026-09-15 GO: dnc_s2_meeting_to_dnc

## Important finding before proceeding: "activate on a schedule" needs a design decision first

`dnc_s2_meeting_to_dnc` is NOT a self-contained detector the way `dnc_projections_sweep` is. Its
own build comment states it plainly: "the auditor already resolved the union to a concrete
person-id set (`r3_s2_persons.json`)... this workflow never re-derives the union itself, it just
consumes whatever `person_ids` the driver POSTs." `S2 Classify` reads `cfg.person_ids` — a value
that only ever comes from the webhook request body — and does NO live Pipedrive querying of its
own. The one existing driver (`dnc_fire_s2_chunk.py`) replays a FROZEN snapshot file
(`audit-artifacts/r3_s2_persons.json`, captured 2026-08-14, 541 ids, asserted exactly that count)
— it does not recompute anything either.

Adding an n8n Schedule Trigger to this workflow's own graph (the fix item 1 used) would NOT make it
detect new meetings — a scheduled fire carries no webhook body, so `person_ids` would default to
`[]` every time: a schedule that runs and does nothing, which is worse than not scheduling at all
(looks active, silently no-ops forever).

**Real "daily schedule" activation needs a new live-query component**: re-derive the union of label
"5. Meeting" + deal stage "Qualified Meeting Set" (Janea Systems Consulting pipeline) fresh each
day, diff against what's already in the registry, and POST only the new ids. That's a genuine build
(matching the Pipedrive search/label/stage-filter methodology the original auditor used to produce
the 541-id list), not a one-line addition — I'm not building and deploying that without confirming
the exact query approach with you first, rather than risk silently getting an important detection
mechanism wrong. **Not done — holding for your direction.** Backfilling Chirag (below) doesn't
depend on this and proceeds now as asked.

## Chirag R Shah backfill — proceeding now

Found by the full DNC audit: Chirag R Shah, Pipedrive person 86650, added 2026-09-14 via a
Surfe-sourced deal owned by Jim Ash, deal in "Qualified Meeting Set" stage — qualifies for S2
(meeting_dnc) directly; also a likely S3 (sales_personal_outreach, Surfe signal) match, but
`meeting_dnc` outranks `sales_personal_outreach` in the registry's strength order, so one
UpsertLedger call with `reason=meeting_dnc` is the correct, complete write (source is appended, not
overwritten, on any future S3 pass that also finds him).

Not in `r3_s2_persons.json` (that snapshot predates his Pipedrive record by a month) — firing S2's
own webhook directly with a single-id override (`person_ids: ["86650"]`), bypassing
`dnc_fire_s2_chunk.py`'s frozen-file/541-count assertion (correctly not usable for an ad-hoc single
id).

**Dry-run already fired (FIRE_S2 still false at the time, zero write risk)**: clean —
`chunk offset 0 -> DONE (1 total candidates)`, `dry-run -- FIRE_S2 is false, nothing written`. This
also empirically exercised `S2 Merge Identity Paths` (a 2-input Merge, same fan-in shape as item 1's
fixed bug — Chirag has a resolvable identity so only one of its two inputs populated, the exact
single-branch case proven unreliable elsewhere this session) for a real single-item batch, and it
fired correctly. **Flagging, not fixing today** (out of scope for this GO item, and S2 isn't going
into scheduled/unattended operation yet regardless) — worth revisiting before S2 ever does run on a
real schedule, once the live-query design above is settled.

## Plan

1. Flip CONFIG on the live workflow: `FIRE_S2: false → true` (temporary — will flip back to `false`
   immediately after this one supervised fire, since nothing is scheduling this workflow yet and a
   stray webhook POST should not write for real by default).
2. Fire once with `person_ids: ["86650"]`, supervised.
3. Flip `FIRE_S2` back to `false`.
4. Post-verify: read Chirag's registry row directly.
