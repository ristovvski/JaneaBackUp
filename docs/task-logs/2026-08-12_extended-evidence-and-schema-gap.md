# DNC BUILD — extended 623 evidence artifact + registry permanence gap + Melisa flag

**Status: item 2 of Nik's final pre-fire sequence (mine, as "Хранитель") done.**

## Extended artifact
Added the auditor's requested columns: `match_method` (all 623 = `exact`, no case/whitespace
mismatches between registry `email_lc` and Smartlead's own stored email), `registry_email_lc` vs
`smartlead_email` shown separately, `last_sent_at`/`last_reply_at` (max rolled up across all of a
lead's campaigns, from `lead_campaign_data`). Needed fresh single-record fetches only for the 80
retry-resolved rows (the retry script hadn't captured full lead objects); the other 543 came
straight from execution 15913's cached data, zero new calls.

**Cross-signal flagged, not investigated further**: 538/623 (86%) have a recorded `last_reply_at`,
but only 38/623 are `reason=reply_dnc` — ~500 rows entering for an unrelated reason also separately
replied to Smartlead outreach. Left for the auditor's 623×4,024 cross-reference to surface properly.

## Four buckets defined
Wrote one-line, unambiguous definitions for all four (6 already-unsubscribed, 358 not-found from
the Smartlead branch; 1,978 with-lead, 286 without-lead from the Pipedrive branch) directly into
`PROJECTIONS_PASS_PLAN_2026-08-11.md`, specifically calling out that "without-lead" means archived
OR no-lead-at-all (not a gap, by design).

## Registry permanence rule — checked against real data, one real gap found
`reason=unsubscribe`/`client` → `explicit_opt_out` → already correctly permanent
(`expires_at=null`), verified against all 95 seeded `client` rows. **Real gap**: nothing makes a
row's `expires_at` permanent as a *consequence* of this project's own Smartlead unsubscribe action
— `SL Mark Done` only touches `projections_state`. 38 of the 623 about-to-be-unsubscribed rows are
`reply_dnc` with a real 6-month TTL; once Smartlead's side is permanently unsubscribed (irreversible
per their docs), the registry would still show that person expiring in months, silently disagreeing
with the external system. Flagged in the plan doc as a decision needed before `SL Mark Done` is
finalized — not fixed yet, since `FIRE_SMARTLEAD` hasn't flipped.

## Flagged for Melisa's doc
`reply_dnc` currently lumps an explicit "please remove me" and a soft "not interested" under one
reason and one TTL. paul.gilford's own seeded row is the "not interested" case, correctly
time-bound — but a genuine opt-out reply getting the same 6-month TTL would be wrong. Surfaced as
an open question, not resolved unilaterally.

## Next
Auditor's stratified-20 + random-5 spot-check on the extended CSV → Nik's GO → FIRE_SMARTLEAD.
Auditor's own 623×4,024 cross-reference and 288-not-found no-op count are theirs to run, not mine.
