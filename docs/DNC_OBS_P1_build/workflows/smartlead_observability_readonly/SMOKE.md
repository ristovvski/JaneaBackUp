# Smoke checklist — smartlead_observability_readonly (Build 5)

**READ-ONLY toward Smartlead — AI4 is live. This workflow must never issue a non-GET Smartlead call.**
R1 + R4 only; R2/R3 deferred (see BUILD_LOG). Import after `obs_state` exists.

## Pre
- [ ] Credential `Smartlead DEV (readonly)` of type **Query Auth** (`httpQueryAuth`): param name
      `api_key`, value = the dedicated read-only key. Bind it on `GET leads-statistics`.
- [ ] CONFIG: `campaign_id` = a real AI4 campaign id; `MODE=dev`; `alert_channel=C0BFE6KAN8J`;
      `smartlead_base=https://server.smartlead.ai/api/v1`; `r1_stall_hours=6`; `r4_delta_threshold=25`;
      `dedupe_hours=4`; `forwardable=[interested,not_interested,information_request]`.
- [ ] **Confirm response field names** against ONE real capture: run `GET leads-statistics` once,
      inspect `data[]` — the parser reads `last_reply_time` / `category_updated_at` / `lead_category`
      (with fallbacks). If the live names differ, update `parseLeadsStatisticsV1` in
      `subworkflows/lib/obs_v1.js`, rebuild (`python build_dnc.py`), re-run tests. **This is the one
      confirm-on-capture item.**

## Fixture replay (no live call needed)
- [ ] Pin `fixtures/smartlead/leads_statistics_page.json` onto `Parse leads-statistics` → metrics
      `replies=3, categorized=1, forwardable_new=1`.
- [ ] Pin `leads_statistics_stalled.json`, set `r1_since` (obs_state) to 7h ago → `Evaluate` emits an
      R1 alert → dedupe check → `Slack Anomaly Alert` to `C0BFE6KAN8J`; `Upsert Dedupe` writes
      `alert_dedupe:R1:{campaign}` with `expires_at = now+4h`.
- [ ] Re-run immediately → `Fire?` sees the active dedupe row → **no repeat alert** (≤1 per 4h).
- [ ] Balanced page (replies≈categorized) → no alert.

## Live read (optional, safe)
- [ ] One manual run against the real campaign. Verify: only a **GET** appears in the execution;
      `obs_state` gets a `watermark:leads_stats:{campaign}` row; NO Smartlead write anywhere.
- [ ] 429 handling: the HTTP node retries (`retryOnFail`, `maxTries=4`) then routes to
      `Poll Error (skip)` — silent, no alert spam.

## Guards
- [ ] Send-guard: flip `alert_channel` to a non-test id → an alerting run HARD-FAILS at `Send Guard`.
- [ ] MODE=prod behaves the same for alerts (anomalies always alert; there is no happy-path noise here).

Deferred (do NOT build until the per-lead message-history endpoint is confirmed): R2 forward-gap,
R3 edge-category digest. Their obs_state key conventions (`pending_forward:*`, `digest:last_run:*`)
are already reserved in the schema.
