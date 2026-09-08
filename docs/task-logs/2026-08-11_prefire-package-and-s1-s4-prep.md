# DNC BUILD — pre-fire package closed + S1-S4 prep (spec capture only, no build)

**Status: pre-fire items 1-2 fixed/tested/deployed. S3 user ids resolved. Schema design drafted.
Not yet fired — proceeding to announce + fire next.**

## Pre-fire package (auditor's read-only review)
1. **Unpaginated candidate reads — real defect, fixed.** `PD Get Leads By Person` had no pagination
   handling on a v1 list read (default page size 100). Added n8n's native pagination
   (`updateAParameterInEachRequest`, completion on `!more_items_in_collection`, `maxRequests=10`
   safety cap) AND empirically proved it rarely matters: across 330 real responses from the
   earlier test fires, max leads for any one person was 3, `more_items_in_collection` was never
   true. Wire-tested the paginated config itself against 3 real persons post-fix — still exactly
   1 output item per input item, no regression. New regression test added. 53/53 pass.
2. **"2,264 is a floor" — reporting fix, not a logic fix.** Consequence was already correct (the
   person-level field is universal; the lead-label secondary correctly can't attach to an archived
   lead). Fixed the `Combine Summaries` output and Dev Summary text to report `>=2264` with an
   explicit note on the archived blind spot, so nobody downstream mistakes a floor for a population.
3. **Spacing** — batching (400/350ms) stays as designed; the wire proof (cadence, zero 429s) is a
   during/after-fire check, not a pre-fire code change.
4. **Accepted the auditor's independent verification offer** (FIRE-flag read-back before firing,
   post-run count reconciliation) — welcomed, not resisted.

Both code fixes redeployed (settings + node changes via PUT), workflow confirmed still inactive,
`FIRE_PIPEDRIVE`/`FIRE_SMARTLEAD` confirmed `false` immediately before firing.

## S1-S4 spec gaps closed (prep only, no scenario code written)
- S3's 5 Pipedrive user ids resolved via one `GET /v1/users` call: Toby `17703023`, Jim Ash
  `24721201`, Mario Stalder `16029123`, Noah Keimach `25733113`. **"Aruna" has no exact match** —
  inferred as Araks Grigoryan (`24902545`), flagged as unconfirmed, not asserted.
- Drafted (not applied to any file) the `reason`→`entry_type` mapping and collision-priority
  ordering for the three new reason values (`meeting_dnc`→`replied`, `sales_personal_outreach`→
  `manual`, `event_contacted`→`manual`, none offboard-removable) — full reasoning in
  `PHASE1_SCENARIOS_SPEC_2026-08-11.md`.
- S1 design decision confirmed: build to UNION Pipedrive-label + provider-reply-history sources
  (owner's explicit call, dodges the archived-blind-spot trap by construction).

## Next
Announce the Pipedrive bulk window, fire the sweep, cross-check counts vs 623/2,264, then S1-S4
building can start per the standing sequencing.
