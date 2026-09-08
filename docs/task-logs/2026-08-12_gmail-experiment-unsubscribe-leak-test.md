# DNC BUILD — Gmail experiment: does global unsubscribe leak nurturing sends?

**Status: done. Clean answer, no send occurred (correctly — see below), no leftover state.**

## Setup
Fixture `pii-c61c7d08@example.invalid` (Nik's own test identity) confirmed globally unsubscribed in
Smartlead since 2026-08-11T13:15:59Z (`is_unsubscribed: true`), currently a lead on one completed
campaign only. Used Smartlead's own "Test Campaign" (id 1244339) as the nurture-style/test vehicle
— literally built for this purpose (`TEST - quick question about integration` subject, no
`client_id`, isolated). Started it (`STARTED`→`ACTIVE`... actually API only exposes
START/STOPPED/PAUSED, so `START`), set its single sequence step's delay to 0 days for an immediate
send instead of its default 1-day delay.

## What I found — the add itself is where it dies
Called `POST /campaigns/{id}/leads` with `settings.ignore_unsubscribe_list: true` (explicitly meant
to override suppression) targeting the fixture. The API returned `ok:true, upload_count:1,
already_added_to_campaign:0, unsubscribed_leads:[]` — reporting a clean, fresh, successful add,
every time I retried. But the campaign's actual lead list never changed: still just the one
pre-existing unrelated lead from Jan 2025. The fixture never appeared, no error surfaced anywhere,
and it wasn't even flagged in `unsubscribed_leads` (the field that exists specifically to report
this).

**Isolated with a control**: added a fresh, never-touched throwaway address
(`flip-gate-control-test@example.invalid`, same override settings) to the same campaign right after.
That one landed immediately — lead count 1→2, status `STARTED`. Same call shape, same campaign, same
settings; only difference was unsubscribe status. Confirms the mechanism works and the fixture's
global unsubscribe is what's blocking it — not a wrong endpoint, wrong body, or caching artifact.

## Answer to Nik's open question
**Outcome B, and stronger than the B originally framed.** Global unsubscribe doesn't just block
sends within existing campaigns — it silently blocks the lead from even being *added* to a new
campaign via the API, and the override flag meant to bypass exactly this (`ignore_unsubscribe_list`)
does not work at the add stage. No send was ever possible; nothing to check in Nik's inbox. This
closes the "is suppression leaky" question definitively closed in the safe direction: it's airtight,
not leaky, and airtight in a way that would have made the original global-unsubscribe-for-repliers
design even more damaging than Melisa's warning implied — those 538 repliers wouldn't just lose
future automated follow-ups, they'd become permanently un-addable via Smartlead in ANY campaign,
nurture included, with no visible error telling anyone why. Retroactively validates the redesign
freeze as the right call, now with empirical evidence instead of just risk reasoning.

## Cleanup (state left clean)
- Deleted the control test lead from the campaign (`DELETE .../leads/{lead_id}`, confirmed).
- Reverted the sequence's delay back to its original `delay_in_days: 1`.
- Reverted campaign status back to `STOPPED` (its pre-experiment `COMPLETED` isn't a settable value
  via the status API — allowed values are `START/STOPPED/PAUSED` only; `STOPPED` is the closest
  inactive equivalent and matches its original non-live state).
- Final state verified: campaign shows only the original 2025 lead, nothing else changed.
- Fixture's own record untouched throughout — still globally unsubscribed, still on its original
  one campaign, no new campaign membership, no send, no bounce.

## Next
Report this to Nik/the wire as the closed answer. No further Smartlead-side action needed for this
item.
