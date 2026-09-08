# TEST REPORT — DNC Ledger + Smartlead Observability (Phase 1)

Run: `node run_all_tests.js` (DEV/local, no live systems). Date 2026-07-23.
**ALL SUITES PASSED — 63 assertions, 0 failed, 2 deferred (R2/R3, evidence-backed).**

| Suite | Result |
|---|---|
| subworkflows/tests/dnc_contract_tests.js | 25 / 0 |
| workflows/heyreach_reply_to_dnc_ledger/tests/tee_tests.js | 5 / 0 |
| workflows/dnc_expiry_job/tests/expiry_tests.js | 10 / 0 |
| workflows/smartlead_observability_readonly/tests/obs_tests.js | 12 / 0 (+2 deferred) |
| workflows/dnc_check_service/tests/check_tests.js | 11 / 0 |

## Coverage vs spec test_cases

**1.1 tee** — reply_with_linkedin_only_creates_entry ✅ · reply_with_both_ids_matching_same_row_upserts ✅
· conflicting_identifiers_alert_no_write ✅ · duplicate_webhook_replay_is_ignored ✅ ·
existing_explicit_opt_out_not_downgraded ✅

**1.2 check** — active_entry_found ✅ · expired_entry_reported_as_clean_with_history ✅ · clean_person ✅
· garbage_input_gets_usage_hint ✅

**1.3 expiry** — due_row_expires ✅ · permanent_row_untouched ✅ (explicit_opt_out + null-expiry) ·
rerun_same_day_is_noop ✅ · (bonus) dedup self-heal + ambiguous-skip ✅

**1.4 observability (R1–R4 simulations)**
- R1 stalled_categories_fire_R1 ✅ (fires past stall threshold; not before; clears on resume)
- R4 pipeline delta fires beyond threshold ✅ ; forwarded_reply_matches_no_alert ✅
- alert_dedupe_suppresses_repeat ✅ (≤1 / 4h) ; smartlead_429_backs_off ✅ (retryOnFail/maxTries)
- **ZERO writes to Smartlead** — test-enforced (all httpRequest = GET; all DT writes → obs_state) ✅
- R2 unmatched_interested_reply / R3 wrong_person_digest — **DEFERRED**: require a per-lead
  message-history endpoint that is NOT documented (verified via llms.txt + leads core page, 2026-07-23).
  obs_state keys `pending_forward:*` / `digest:last_run:*` reserved for when it's confirmed.

## Cross-cutting properties proven
- Normalization frozen v1; every Code node embeds the lib **verbatim** (drift tests) → `norm_v` can't
  drift silently (amendment 1).
- Duplicate tolerance (amendment 2): CheckLedger strongest-wins across rows; expiry job dedups.
- Idempotency: replay → `noop` (merge is a pure fn of preserved `added_at`).
- Only the **verified `eq`** operator appears in ledger filters (tests scan the JSON).

## What tests do NOT cover (confirm in DEV UI via each SMOKE.md)
- Live n8n execution semantics (paired items, `alwaysOutputData`, resourceMapper schema auto-fill).
- Real Smartlead `leads-statistics` response field names (one confirm-on-capture step; parser has fallbacks).
- Actual Slack delivery + Slack event subscription for the mention trigger.
