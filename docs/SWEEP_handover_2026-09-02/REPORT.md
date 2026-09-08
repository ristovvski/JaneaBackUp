# Sweep — open handover activities on registry-suppressed people

**2026-09-02. Report only. Nothing was written, closed or modified.**
Every call was a `GET`, except the do-not-contact lookups, which went through `dnc_pre_add_gate`
(a read-only service).

**Decision needed from you: close them or leave them.** The list is in
`hits_optout_or_negative_reply.csv`, with a clickable Pipedrive URL per row.

---

## The number

**71 open handover activities sit on people the registry holds as an opt-out or a negative reply.**
They cover **66 distinct people** and **64 distinct leads** (5 people carry two open handovers each).

| | count |
|---|---:|
| Open activities in Pipedrive (all types) | 5,474 |
| …of type **Handover** | **161** |
| **→ matched: registry `negative_reply`** | **68** |
| **→ matched: registry `explicit_opt_out`** | **3** |
| also blocked, but `employee_connection` — outside your target set | 11 |
| checked and genuinely clean | 27 |
| could not be checked | 52 |

**All 71 predate the automation condition** — the oldest is 2025-02-12, the newest 2026-08-14.
Split 25 from 2025 and 46 from 2026. **70 of the 71 are owned by Melisa** (one by Toby).

## What their leads look like now

| | count |
|---|---:|
| lead already carries **Disqualified** | 42 |
| lead already carries **DO NOT CONTACT** | 2 |
| lead carries **neither suppressing label** | **29** |
| lead is archived | 63 |
| lead is live | 6 |
| activity has no lead at all | 2 |

Two things follow from that table:

- **For 42 of them the new condition would already suppress the handover** if it were re-evaluated
  today — the label is there, the activity just predates the rule. Those are the safest to close.
- **29 have neither suppressing label.** They are in the registry, but their Pipedrive lead was
  never labelled — which is the projection backlog from Wave 1 showing up in a second place. If you
  close these activities without labelling the leads, nothing stops a future handover on the same
  person. *Worth doing in the same pass: label the lead, then close the activity.*

## The 52 that could not be checked

Not a silent zero — named:

| | count |
|---|---:|
| activity has **no person and no lead** (nothing to look up) | 46 |
| activity has a lead, but the lead has **no person attached** | 6 |

All 52 have subject "Assign this lead to a sales exec!" or "Follow up with the lead". These are the
`person_id: null` leads — the Make-created population that never got a person. They cannot be
matched against the registry by any identifier, so I cannot tell you whether they belong on this
list. **They are neither included nor implicitly cleared.**

## The 11 outside your target set

`employee_connection` / `manual_offboard_eligible` — a departing colleague's LinkedIn connection,
not someone who declined us. All LinkedIn-only, all created 2025-04 → 2026-05. Listed separately in
`also_blocked_employee_connection.csv`; **not included in the 71** because you specified
unsubscribe/negative_reply. Say the word if you want them counted.

## How the match was made, and what it cannot distinguish

- Open handover activities: paged `GET /api/v2/activities?done=false` in full (11 pages, 5,474
  activities), filtered client-side on `type == "handover"` — the v2 endpoint rejects a `type`
  filter, so filtering server-side was not an option.
- Each activity → its person (directly, or via its lead) → the person's email, or, where there was
  no email, their LinkedIn URL from the person's custom fields. 28 of the 80 email-less activities
  were matched that way.
- Registry membership came from `dnc_pre_add_gate`, which returns `entry_type / source`.
- **The limitation:** the gate exposes `entry_type`, not the registry's `reason` column. So
  `explicit_opt_out` covers both the `unsubscribe` and `client` reasons, and I cannot separate them
  without a registry reader that does not exist. Three rows are affected. `negative_reply` maps
  one-to-one to `reply_dnc`, so the other 68 are exact.

## Files

| file | rows | what |
|---|---:|---|
| `hits_optout_or_negative_reply.csv` | 71 | **the decision list** — person, email, entry type, lead, current labels, archived flag, Pipedrive links |
| `also_blocked_employee_connection.csv` | 11 | blocked but outside the target set |
| `not_checkable.csv` | 52 | no identifier to match on |
| `sweep_raw.json` | — | everything, including the 27 clean |

## If you decide to close them

I have not written anything. When you decide, the safe order is:

1. **Label first, close second** for the 29 with no suppressing label — otherwise the same person
   can generate a fresh handover.
2. Close in batches with a fixed `note` naming this sweep, so the change is attributable.
3. The 6 live (non-archived) leads deserve a human look before anything is closed — a live lead
   with an open handover may be a real, current conversation that outranks a 2025 registry row.
