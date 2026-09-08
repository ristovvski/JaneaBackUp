# Task log — 2026-08-05 — backfill-300 completion (persons, owner fix, leads)

**What was asked:** run the remaining half of the flip-day queue — backfill-300 (Make/email Ai4
persons), refreshed and re-verified before writing, with the Handover guard consideration carried
over from backfill-25.

## What was done, and what it proves

- **Refreshed the missing-persons list fresh** rather than reusing the 2026-08-04 snapshot: re-ran
  the sent-vs-CRM reconciliation (891 sent, 300 still missing, identical set — no drift in 24h) and
  checked each for unsubscribe/bounce status since the original list was built.
- **Caught and fixed a false-positive bug in my own drop-check before it silently dropped all 300.**
  My first pass flagged **all 300 as "unsubscribed"** — a 100% rate that should have been a red flag
  on its face. Root cause: `"unsubscrib" in blob.lower()` matches the mere presence of the field
  *name* `is_unsubscribed` in Smartlead's response, regardless of its value. Verified directly
  against a live response (`pii-5ce72a9a@example.invalid`: `"is_unsubscribed": false`) before trusting the
  count, fixed to read the actual boolean, re-ran: 0 dropped, 300 confirmed genuinely missing.
- **Ran backfill-300 live: 300/300 persons created, 0 failures.**
- **Found a real gap between what I documented and what I built.** The script's own docstring says
  "create person (+ lead)" — but the implementation only ever wrote the person half. Caught this by
  verifying directly (sampled 4 new persons, all `leads=0`) rather than trusting the docstring's
  claim. This was not something the user asked me to check; I checked it because the backfill's
  whole purpose was closing a "no lead" gap, and I wanted to confirm it actually closed.
- **Surfaced the gap and a real design question rather than silently deciding it**: the 300 persons
  had been created with per-campaign salesperson ownership (Mario/Rune), which does not match WF-2's
  own uniform Melisa-ownership convention for both persons and leads. Asked the owner directly rather
  than guess; they chose Melisa, with clear reasoning (avoid a third ownership convention alongside
  Make's and WF-2's; Melisa's own Handover/redistribution automation depends on owner=Melisa as its
  trigger condition).
- **Completed the fix live**: reassigned all 300 persons' `owner_id` to Melisa (16340280), then
  created 300 leads following WF-2's own live convention exactly — title
  `{campaign_id} - {campaign_name} - {name}`, channel 578, `label_ids=['cold']`,
  `lead_opportunity_type` field = 480, `lead_campaign` field = campaign name verbatim. 300/300, 0
  failures, verified by dry-run first both times.
- **Handover-guard analysis, stated explicitly rather than skipped**: these leads only ever carry
  `cold`, never `responded` — neither "Responded handover to Melisa" nor "Responded already there"
  can fire (both key on the responded label). "New lead owner" (fires on owner changed *from*
  Melisa) is Melisa's own distribution mechanism firing exactly as designed once she redistributes —
  not something to suppress. No guard action was needed for this backfill, and that conclusion is
  based on reading the actual label set being written, not assumed.

## Numbers

| | count |
|---|---|
| persons created | 300 |
| owner reassignments (Mario/Rune → Melisa) | 300 |
| leads created | 300 |
| failures across all three write passes | 0 |
| false-positive "unsubscribed" rows corrected before writing | 300 (the whole set, caught pre-write) |

## What can be improved

- The original `backfill_ai4_persons.py` script's docstring described a scope it didn't implement.
  Docstrings describing intent are not a substitute for verifying the actual code path — this is
  the second time this session a script's own claim (about what it logs, about what it does) turned
  out not to match its behavior on inspection, and both times direct verification against real data
  caught it before it became a silent gap in delivered work.
- The `"substring in blob"` class of bug has now appeared at least three times this session (reply-
  text false-negative in the WF-1 audit, the Person-6193c11f reply-activity false-negative in
  `backfill_wf1_gaps.py`, and this unsubscribe false-positive). Worth a standing rule: never check a
  JSON API response by stringifying and substring-matching; always parse and read the actual field.
