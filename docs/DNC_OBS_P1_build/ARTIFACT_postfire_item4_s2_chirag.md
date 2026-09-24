# Post-fire — item 4 of Nik's 2026-09-15 GO: dnc_s2_meeting_to_dnc

## Schedule — NOT activated, holding for your direction

See the pre-fire artifact for the full reasoning: `dnc_s2_meeting_to_dnc` has no live Pipedrive
query of its own — it only processes a caller-supplied `person_ids` list, and the one existing
driver replays a frozen 2026-08-14 snapshot (541 ids). An n8n Schedule Trigger added to this
workflow's own graph would fire with an empty `person_ids` every time (a schedule carries no
webhook body) — that's a no-op dressed as "active," which is worse than leaving it as-is. Real daily
detection needs a new live-query component (re-derive label "5. Meeting" ∪ deal stage "Qualified
Meeting Set" fresh each day) — not built, needs your sign-off on the exact Pipedrive query approach
before I build it.

## Chirag R Shah — backfilled successfully

Fired S2's webhook directly with `person_ids: ["86650"]` (bypassing the frozen-file driver, which
predates his Pipedrive record and is hardcoded to a 541-id snapshot). Dry-run first (FIRE_S2 still
false) came back clean. Flipped `FIRE_S2: false → true`, fired for real.

**The live HTTP call returned a 500** — but the execution itself (56896, 2026-09-15T14:00:51Z)
shows `status: success` in n8n's own execution log, and direct registry read-back confirms the
write landed correctly:

```
id 33189, identity_key pii-6d874338@example.invalid, reason meeting_dnc, entry_type replied,
source meeting_sweep, pipedrive_person_id 86650, status active
```

The 500 looks like a response-delivery glitch (n8n's `responseMode: lastNode` failing to hand the
Slack post's own response back to the caller) rather than a workflow failure — the write happened
regardless, verified independently rather than trusted from the HTTP status, per this project's
standing discipline. Flipped `FIRE_S2` back to `false` immediately after (nothing is scheduling
this workflow yet, so leaving the live-write gate on by default was unnecessary risk).

Chirag's `pipedrive_person_id` is now set, so he will correctly enter the projections sweep's (item
1) candidate pool on its next automatic chunk — no separate action needed for his 686 field.

## Residual, flagged not fixed

`S2 Merge Identity Paths` (2-input `Merge(append)`, converging the with-identity/no-identity
outcome branches before `S2 Combine`) is the same fan-in shape as item 1's fixed bug. Empirically
fired correctly for Chirag's single-item, single-branch-populated case (the same shape proven
unreliable elsewhere this session) — one clean data point, not proof it's safe in general. Not
fixed today (out of scope for this item, and S2 isn't going into unattended scheduled operation
yet) — worth fixing alongside whatever build implements the live daily detection, before that ever
runs unsupervised.
