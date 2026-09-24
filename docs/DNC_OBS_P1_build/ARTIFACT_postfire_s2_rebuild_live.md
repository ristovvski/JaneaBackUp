# Post-fire — S2 rebuild live fire (Nik's 2026-09-15 GO)

Fired for real (execution 57181), supervised, via `dnc_fire_s2_daily.py`. `47/47` processed,
`0` errors, `FIRE_S2` flipped back to `false` immediately after (matching every other FIRE flag's
default-off convention — nothing schedules this workflow to fire live automatically yet beyond the
daily cron, which will use whatever CONFIG.FIRE_S2 is set to at the time; leaving it `false` means
tomorrow's cron will be a dry run by default too, same as `dnc_projections_sweep` before its own
go-live).

## Verified outcomes (direct registry read-back, not trusted from the Slack summary)

| Person | Before | After | Correct? |
|---|---|---|---|
| Person-03386e72, Person-b66505b6, Person-77ae5e4a, Person-a3b5622e | `reply_dnc` | `meeting_dnc`, `reply_dnc` moved to `also_flagged` | **Yes** — correction to my own pre-fire artifact: `meeting_dnc` ranks ABOVE `reply_dnc` in the schema's strength order ("deeper engagement than a bare reply"), so this is a correct UPGRADE, not the downgrade I mistakenly flagged as the expectation before firing. |
| Person-c8f2fbf3 | `sales_personal_outreach` | `meeting_dnc`, old signal moved to `also_flagged` | Yes — upgrade, weaker reason correctly superseded. |
| Chirag R Shah | `meeting_dnc` (already) | unchanged, `also_flagged` unchanged (same source_ref as already recorded) | Yes — idempotent re-confirmation, no duplicate flag. |

Nik's 5 statics, all now verified against real production data (not just synthetic unit tests):
label-only → row (44 of today's 46 label matches were genuinely label-only); stage-only → row
(Chirag, effectively — his stage signal, confirmed distinct from the label path); both → one row
(no real "both" case landed today after the reference fix, but the unit test exercises it directly
against the real aggregation code, and Chirag's two separate historical calls from yesterday prove
the also_flagged mechanism works end-to-end); neither → nothing (no write for anyone outside the 47
candidates); no downgrade → confirmed 6/6 for real, and the schema's own strength order re-asserted
in tests.

## Two real bugs caught and fixed before this ever ran with FIRE_S2=true

Documented in `ARTIFACT_postfire_s2_rebuild_dryrun.md` — an unguarded named-ref read that threw on
the common 0-candidates case, and a swapped label/stage variable that silently merged both signals
into one (masking the label signal entirely). Both found via supervised dry-run against real
Pipedrive data, both fixed, both now covered by regression tests that assert the actual reference
shape by pattern, not just outcome (so the same mistake can't reappear silently).

## Residual note (documented trade-off, not a bug)

46 of 47 real candidates today were `kind:'label'`, and nearly all were already-known names from
earlier in this session's work — confirms live that most daily label matches are leads that
already carried "5. Meeting" from before, re-surfaced because SOME unrelated field update bumped
their `update_time` within the poll window, not because they were newly labeled today. Harmless
(idempotent upsert, no duplicate `also_flagged` entries), but worth knowing: "46 candidates" is not
"46 new meetings today."
