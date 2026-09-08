# S3 follow-ups: UpsertLedger redeploy fix, cleanup, telemetry/ops channel split, review post

**Status: all 5 items from Nik's message done. Holding backfill FIRE + watcher activation for
his review-pass word on the 27-candidate list (posted to ops).**

## 1. source_signal unblocked — 27-candidate list posted for review
Posted the full list (name/email/LinkedIn/person_id, all 27) to ops (C0B8GCVNR5W) via direct Slack
message. Flagged one real finding before asking for sign-off: 3 of the 27 (Person-b0fb1597, Vibhooti
Dev, James Capps) have **neither** email nor LinkedIn — not the spec's "half-empty" floor, genuinely
empty on both identifiers, so `UpsertLedger` computes a null `identity_key` for them and they'd be
silently skipped on a live fire, not written as a broken alias. Holding backfill `FIRE_S3_BACKFILL`
and watcher activation until Nik's word closes this, exactly as instructed (together, not
separately).

## 2. Three dead backfill copies — already gone
`wD6pNVYXCrETLsJv`, `4HJJ1bdv2Kh5JxsL`, `8vND45UUSydnA2UH` all 404 on delete — already removed
during my own debugging cleanup earlier (each deleted right after creating its replacement, while
chasing the `responseNode` webhook bug). Only `1fpep0U4XC8KNzta` remains, confirmed active.

## 3. Real gap found: DNC__UpsertLedger__v1 was never redeployed with the schema update
Execution 16131's "invalid entry_type undefined" was itself just my own throwaway diagnostic probe
hitting the live UpsertLedger with an empty payload (correctly rejected) — but chasing it down
surfaced a genuine, separate problem: **I built and locally tested the `sales_personal_outreach`
schema addition but never actually pushed the updated `DNC__UpsertLedger__v1` to the live n8n
instance.** Confirmed directly (`'sales_personal_outreach' in <live deployed jsCode>` was `False`).
Any real S3/S4/S1/S2 write attempting that reason would have crashed identically. Deployed now,
confirmed present live. Also spot-checked `NormalizeIdentity`/`CheckLedger` for the same kind of
drift — both byte-identical to local already, no action needed there.

## 4. Routine vs. final Slack channel routing
Dry-runs/chunk progress now post to `#gtm-telemetry` (`C0BQM1X9ZUY`); only the final/complete result
posts to ops (`C0B8GCVNR5W`). Implemented as a per-post `target_channel` computed in each workflow's
own Combine step (not a static config choice), read by the Slack node via
`{{ $json.target_channel }}`. `SEND_GUARD_JS` extended to validate against a *list* of allowed
channels (`dev_channel_guard_list`) when set, falling back to the exact prior single-channel
behavior for every workflow that doesn't set it — verified no other workflow's guard changed.
Applied to `dnc_projections_sweep` (intermediate chunks → telemetry, final chunk → ops),
`dnc_s3_surfe_backfill` (same pattern, final = `done:true`), and `dnc_s3_creation_watcher` (always
telemetry — a recurring poll has no "final" concept). 66/66 tests pass. All three redeployed live;
the sweep's `FIRE_PIPEDRIVE` was also reverted to `false` on redeploy — the authorized write is
complete, no reason to leave it armed.

## 5. FYI, no action — Melisa's "120" is AI4 replies
Confirmed by Nik: already covered by S1's Responded→DNC union (Pipedrive label OR provider reply
history). No separate list to build for this.

## Next
S4 (AI4 campaign populations → registry, one pass — the spec doc's own assessment: "most
straightforward of the four, no Pipedrive dependency at all") → S1/S2 (Responded/Meeting unions),
per the stated priority order.
