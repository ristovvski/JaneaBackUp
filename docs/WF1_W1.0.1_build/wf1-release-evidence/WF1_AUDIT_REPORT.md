# Did HeyReach → Pipedrive work fully correctly?

**No — 1087 of 1221 contacted leads are correct; 134 have a problem (131 absent, 3 label gaps, 0 replies with no text logged).**

_Read-only audit, 2026-08-04 14:30 UTC. HeyReach is the truth source; nothing was written._

## The numbers

| | count |
|---|---|
| HeyReach campaigns | 6 |
| leads in those campaigns | 1611 |
| **actually contacted** (invite sent / accepted / messaged) | **1221** |
| of those, accepted | 274 |
| of those, replied | 70 |
| nothing in CRM (no person, no lead) | 1 |
| person but no campaign lead | 130 |
| label gaps | 3 |
| replies with no text logged | 0 |

## Per campaign

| campaign | status | contacted | accepted | replied | no CRM record | no lead | label gaps | reply text missing |
|---|---|---|---|---|---|---|---|---|
| [Events Visiting] [Ai4 2026] - Rune - LinkedIn | IN_PROGRESS | 559 | 113 | 30 | 0 | 15 | 1 | 0 |
| [Events Visiting] [Ai4 2026] - Mario - LinkedIn | IN_PROGRESS | 556 | 123 | 34 | 1 | 9 | 2 | 0 |
| Final TEST | PAUSED | 52 | 18 | 2 | 0 | 52 | 0 | 0 |
| Final test  | PAUSED | 52 | 18 | 2 | 0 | 52 | 0 | 0 |
| TEST2 | FINISHED | 1 | 1 | 1 | 0 | 1 | 0 | 0 |
| TEST | FINISHED | 1 | 1 | 1 | 0 | 1 | 0 | 0 |

## Label detail (what was missing, by kind)

| expected label | leads missing it |
|---|---|
| `cold` on a contacted lead | 0 |
| `connected` on an accepted lead | 1 |
| `lh_connected_at` on an accepted person | 0 |
| `responded` on a replied lead | 2 |

**Labels present that HeyReach does not justify: 1.** These are *not* WF-1 defects — union labels never remove, and the sprint team's reply-Zap adds `connected`+`responded` to replied leads ~90 seconds after us (a known, accepted cohabitant). Listed in `wf1_audit_extra_labels.csv` for completeness.

## Re-keyed by member_id after W1.0.16 — and it corrected our own number

This run resolves people the way the workflow now does: LinkedIn URL, then the numeric `member_id`
(which equals HeyReach's `linkedin_id`), then the public slug. That changed the answer:

| | first run (URL-keyed) | this run (member_id-keyed) |
|---|---|---|
| nothing in CRM at all | 17 | **1** |
| person exists, no campaign lead | 24 | 24 |
| **production gaps** | **41 (3.7%)** | **25 (2.2%)** |

16 of the 41 were never actually missing. They are in the CRM, and only the audit's slug-keyed
matching could not see them — the same blind spot WF-1 had, which is why W1.0.16 exists. The honest
production gap is **25**, and the earlier 41 over-counted by our own measurement error.

Small drift against the first run (accepted 269→274, replied 69→70) is live campaign activity, not a
correction.

## The lost reply of 30.07 09:46 — can we now name who it was?

HeyReach's inbox holds **no inbound message in that hour** — and the inbox is provably complete for
the period (all messages returned, no truncation, back to 14 July), with 8 inbound replies that day
but none between 00:55Z and 16:10Z. So the lost event was **not** a reply; most likely a lost
`accepted` or `message_sent`, which HeyReach cannot timestamp retrospectively (it exposes current
per-lead status only, no event log). See the task log for the blocker.


## Files

| file | contents |
|---|---|
| `wf1_audit_missing.csv` | 131 contacted leads with no CRM record |
| `wf1_audit_label_mismatches.csv` | 3 leads with a missing label |
| `wf1_audit_missing_reply_text.csv` | 0 replies with no text |
| `wf1_audit_extra_labels.csv` | 1 extra labels (cohabitant, not ours) |

## The pre-production test campaigns — accepted gap, closed

`TEST`, `TEST2`, `Final test`, `Final TEST` contacted 106 people between 13 and 17 July, and **no
lead was ever created for any of them** (no CRM lead carries a `510736 -`, `510448 -`, `506813 -` or
`505075 -` title prefix). They ran before the production Ai4 campaigns started on 18 July, i.e.
before WF-1 was in production. **Owner decision: not backfilled, left as-is — an accepted
pre-production gap.** They are excluded from the daily reconciliation so they cannot re-surface as
recurring noise. Six of the 106 had accepted and replied.

## What is now watched, not guessed

`daily_linkedin_reconcile.py` runs this comparison every day and emits one digest line:

```
LinkedIn channel: 41 touches in the last 24h, 40 in CRM, gaps: 1 (Person-fbbb498b / Acme)
```

A webhook that never arrives leaves no execution to alert on, so reconciliation is the only way this
channel can be monitored at all. Results append to `linkedin_reconcile_ledger.jsonl`, because n8n
retains roughly 13 hours of executions and a gap trend needs history that outlives that.
