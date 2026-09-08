# DNC Phase-1 Scenarios (S1-S4) — spec capture, NOT started yet

**Source: spoken on today's team sync (Melisa), written doc to follow as confirmation — treated as
spec per the owner's explicit instruction. Deadline Friday, team-facing.**

**Sequencing (explicit, from the owner): sweep verification → counts vs 623 → S1-S4 → FIRE
approvals from Nik per channel → Friday demo-ready.** Nothing below has been built. The sweep
re-fire itself is on hold for the live send wave (do not re-fire until the wave window closes
tonight + explicit announcement, per the most recent instruction — this supersedes the earlier
"wait for the auditor" condition as the actual gate). This document exists so the spec isn't lost
between now and when building actually starts, and to surface what's already known vs. still
needed per scenario — a preview, not a build.

## S1. RESPONDED → DNC

Every person whose lead carries **"3. Responded"** (or has a reply event in Smartlead/HeyReach
history) enters the registry, `reason = reply_dnc`. Extends the existing 143 rows (142 Amsterdam +
paul.gilford) to the full Responded population.

**Already known:**
- Label id for "3. Responded": `c9d4b550-bcf3-11ef-a843-357f91e826ec` (from
  `WF1_W1.0.1_build/t4_label_wiper_sweep.py`'s own `NAMES` dict — the full 5-label ladder:
  `1. Cold` / `2. Connected` / `3. Responded` / `4. Positive Reply` / `5. Meeting`).
- **The "~1,715" figure is a real trap, not a clean target.** Per the fix-owner session's own
  audit (`task-logs/2026-08-11_audit-addendum-archived-blindspot-and-resolver-check.md`): 1,713
  leads carried "3. Responded" as of 2026-08-10T15:45Z **measured via list read, which cannot see
  archived leads at all** — at least 2 archived leads also carry it, so the true figure is **≥1,715**
  and moving (a fixture lead has since been archived too, current non-archived count ≈1,717). A
  bulk list-read-by-label approach for S1 would inherit this exact blind spot and silently
  undercount by however many Responded leads are currently archived.
- This is very likely WHY the spec itself says "OR who has a reply event in Smartlead/HeyReach
  history" — that's a source that doesn't go through Pipedrive's archived-blind list reads at all.
  **Design implication**: S1 probably needs to resolve from Smartlead/HeyReach reply history as the
  primary signal (or at minimum as a cross-check), not a Pipedrive label list read alone, or it
  will reproduce the exact undercount the fix-owner session already found and reported once.

**RESOLVED 2026-08-11 — owner's design decision:** hold the authoritative-source question for
Melisa's written doc; build S1 to **UNION both sources** meanwhile — a person in either the
Pipedrive label OR provider reply history enters. That's the safe superset and dodges the archived
trap by construction (a person invisible to the Pipedrive list read due to archival is still caught
if they also show up in Smartlead/HeyReach reply history, and vice versa).

## S2. MEETING → DNC

Persons with **"5. Meeting"** label (or meeting activity), `reason = meeting_dnc`.

**Already known:** label id `35edf580-d19e-11ef-935e-7d712003f1b4` (same source as S1).
**Still needed:** what counts as "meeting activity" beyond the label (a Pipedrive Activity of a
specific type? a calendar event?) — not yet defined; Melisa's doc may specify.

## S3. SALES-CREATED → DNC ("the automation Melisa asked for by name")

Pipedrive person/lead created BY or OWNED BY **{Toby, Jim, Mario, Aruna, Noah}** → auto-enter
registry, `reason = sales_personal_outreach`. Must catch manual creations with **half-empty
records** — email OR LinkedIn URL alone is enough for an alias row. Design is open (poll-based
watcher on creator/owner filter, or webhook if Pipedrive offers one) — explicitly "your call."

**RESOLVED 2026-08-11 — Pipedrive user ids, via one `GET /v1/users` call (single-record scale,
fine under the current budget rule):**

| Name | Pipedrive user id | Confidence |
|---|---:|---|
| Toby | `17703023` | exact match |
| Jim (Ash) | `24721201` | exact match |
| Mario (Stalder) | `16029123` | exact match |
| Noah (Keimach) | `25733113` | exact match |
| Araks Grigoryan | `24902545` | **CONFIRMED by Nik, 2026-08-12** |

**Correction trail on the 5th name** — worth keeping for Melisa's written doc to confirm against:
1. Spoken transcript said "Aruna." No user by that name exists in the 44-user Pipedrive list.
2. Flagged as unconfirmed 2026-08-11: inferred "Araks Grigoryan" (`24902545`) as the only
   phonetically-close candidate, explicitly not asserted as fact.
3. **Nik corrected 2026-08-12: "Aruna" was a mis-transcription — Aruna is a developer, not in
   scope for S3 at all. The intended 5th person is Araks Grigoryan (BDR), confirmed.** Final S3
   roster: **Toby, Jim, Mario, Noah, Araks Grigoryan** — five names, `24902545` for Araks.

Ongoing vs. one-time: "auto-enter" implies a live, ongoing watcher (unlike S1/S2/S4, which read as
one-time backfill passes over existing history) — this is the only scenario that's a genuinely
new *live* automation, closer in kind to WF-4 than to a sweep branch.

## S4. AI4 EVENT LEADS → DNC

Everyone contacted via the four AI4 Smartlead campaigns + both HeyReach campaigns enters with
`reason = event_contacted`. One pass over campaign lead lists.

**Already known — all six campaign ids resolved locally, zero new API calls needed to find them:**
- Smartlead (four campaigns, from `WF1_W1.0.1_build/backfill_ai4_persons.py`'s own
  `EVENT_HYPOTHESIS_BY_CAMPAIGN`): `3686193, 3686187, 3686184, 3686181` (all mapped to "Ai4 2026").
- HeyReach (both campaigns, confirmed live this session): `513000` ("...Rune - LinkedIn"),
  `512995` ("...Mario - LinkedIn") — both currently `IN_PROGRESS`.

**Still needed:** same schema-domain gap as S3 (`event_contacted` isn't in the `reason` enum yet).
Otherwise this is the most straightforward of the four — pure list reads (Smartlead
`campaign/leads-statistics` or similar, HeyReach `GetLeadsFromCampaign`, both already-proven
endpoints in this codebase) with no Pipedrive dependency at all.

## Out of scope (explicit) — do not build
Jim's GetSales tool, Surfe sync — Phase 2, separate tasks per Sergey.

## Cross-cutting, before ANY of S1-S4 gets real code

### Schema design for the three new `reason` values — my proposal, not yet applied to any file

No new `entry_type` values — that ladder (`merge_v1.js`'s `DNC_STRENGTH`) governs core
never-downgrade/lifecycle semantics used everywhere and changing it is a much bigger, riskier move
than adding a `reason` that maps to an *existing* tier, exactly the pattern `reason_v1.js` was
built for. Proposal, mapping each new reason to the closest-fitting existing tier:

| New reason | → `entry_type` | Reasoning | `offboard_removable` |
|---|---|---|---|
| `meeting_dnc` | `replied` | A meeting is a deeper engagement signal than a bare reply, but it's still the person engaging *with us*, not an explicit opt-out — same tier as the existing reply-derived rows, never the permanent opt-out tier. | `false` |
| `sales_personal_outreach` | `manual` | Personally-owned-by-sales is an internal relationship decision, not a customer-driven signal — same tier as `manual_sheet`. Deliberately NOT `employee_connection`: that tier's `isOffboardRemovable()` semantics are specifically about a departing employee's LinkedIn connections, an unrelated concept this would incorrectly borrow. | `false` |
| `event_contacted` | `manual` | Weakest signal of the four — "we touched them once," not that they responded. Same tier as `manual_sheet`, same permanent-unless-explicit-expiry default. | `false` |

Proposed extension to `reason_v1.js`'s `REASON_PRIORITY` collision ladder (lower number wins a
collision; only relative ordering matters, exact numbers are free to renumber):

```
client: 0, unsubscribe: 1, meeting_dnc: 2, reply_dnc: 3, sales_personal_outreach: 4,
manual_offboard_eligible: 5, event_contacted: 6, manual_sheet: 7, offboard: 8
```

Reasoning for the three insertions: `meeting_dnc` ranks above `reply_dnc` (a meeting is stronger
evidence of engagement than a bare reply); `sales_personal_outreach` ranks below `reply_dnc` but
above `manual_offboard_eligible` (an active internal sales relationship outranks a passive LinkedIn
connection, but a genuine customer-driven signal still outranks an internal ownership decision);
`event_contacted` ranks just above `manual_sheet` (barely stronger than a bare manual entry, still
weaker than everything else). **This whole ladder is my proposal for the spec doc, not a decision**
— cheap to override before any code is written, since nothing has touched `reason_v1.js` yet.

### Everything else
1. Extend `dnc_registry_dev.schema.yaml`'s `reason` domain + `reason_to_entry_type_mapping` per the
   table above when S1-S4 building actually starts (not done yet — sequencing).
2. Each scenario gets its own dry-run count before any live write — same discipline as the sweep,
   per the owner's explicit instruction.
3. S1 specifically resolves the archived-leads-blind-spot risk by unioning both sources (see
   above) rather than needing a design decision to be blocked on.
