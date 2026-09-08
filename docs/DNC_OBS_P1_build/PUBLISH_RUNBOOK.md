# PUBLISH RUNBOOK — DNC Ledger + Smartlead Observability (Phase 1)

**`/publish` is fully human-gated.** Nothing here has run against a live system. Follow the golden-example
release protocol: **start of week, quiet window, rollback recorded, refuse-if-active, verify after.**
Prod WF-1 is not modified except the single, explicit tee-attach step (7).

Prereq: target n8n **≥ 1.113** with `N8N_ENABLED_MODULES=data-table`.

## 0. Credentials (names only — never paste key values into JSON)
Create in the target instance, then bind by name on import:
- `Slack DEV (bot)` (→ rename to prod later) — chat:write to the target channel.
- `Smartlead DEV (readonly)` — type **Query Auth** (`httpQueryAuth`), param `api_key` = read-only key.
- (CheckLedger/tee use no external creds beyond Slack.)

## 1. Create the Data Tables (Build 1) — WITH `norm_v`
In the target project, create `dnc_ledger` (16 cols incl **`norm_v` String**) and `obs_state` (7 cols)
per `datatables/*.schema.yaml` + `datatables/CREATE_DATATABLES.md`. Confirm types are String/Number/
Boolean/Date (no enum/unique — enforced in code).

## 2. Import order (subworkflows first — parents reference them)
1. `subworkflows/DNC__NormalizeIdentity__v1.json`
2. `subworkflows/DNC__UpsertLedger__v1.json`
3. `subworkflows/DNC__CheckLedger__v1.json`
4. `workflows/dnc_expiry_job/…json`
5. `workflows/smartlead_observability_readonly/…json`
6. `workflows/dnc_check_service/…json`
7. `workflows/heyreach_reply_to_dnc_ledger/…json`  (the tee)

On import, open each **Data Table node** once so the `columns` schema auto-fills; confirm `dataTableId`
resolved (mode "name") to the right table.

## 3. Wire placeholder IDs
Replace these placeholders (they are intentional, instance-specific):
- `REPLACE_DNC__UpsertLedger__v1_ID` (in the tee's `Call` node) → the imported UpsertLedger.
- `REPLACE_DNC__CheckLedger__v1_ID` (in dnc_check_service) → the imported CheckLedger.
- `settings.errorWorkflow = REPLACE_CORE__ErrorHandler_ID` (every workflow) → your WF-ERR handler.
- `campaign_id = REPLACE_WITH_AI4_CAMPAIGN_ID` in the observability CONFIG.
- Slack/Smartlead credential `id = REPLACE_ME` → pick the named credential in the UI.

## 4. Per-workflow SMOKE (DEV, MODE=dev) — do all before any prod flip
Run each `SMOKE.md`. All alerts land in `C0BFE6KAN8J`; verbose dev summaries are expected there.
Confirm the send-guard HARD-FAILS if `alert_channel` ≠ `C0BFE6KAN8J`.
**Observability: do the one confirm-on-capture step** (real `leads-statistics` field names) and re-run
`node run_all_tests.js` if you touch `obs_v1.js`.

## 5. Rename DEV → prod
- Credentials: point workflows at the prod Slack bot / prod read-only Smartlead key (same NAMES or
  rebind). Never reuse the prod n8n encryption key context for dev.
- Optionally rename credential labels `… DEV (…)` → prod equivalents.

## 6. MODE=prod flip (per workflow CONFIG)
Set CONFIG `MODE=prod`. Effect: happy-path VERBOSE dev summaries go silent (Melisa's no-noise rule);
**conflict/anomaly alerts and the send-guard stay active**. Keep `alert_channel=C0BFE6KAN8J` until
burn-in is signed off, then switch to the ops/lead-processing channel and re-invite the bot.

## 7. Attach the 1.1 tee to prod WF-1 (the ONLY prod-WF-1 change)
- Record rollback: export current WF-1 (`versionId`) before editing.
- On WF-1's reply branch, add a non-blocking **Execute Workflow** call to
  `heyreach_reply_to_dnc_ledger`, passing the input contract
  `{reply_event_id, linkedin_url, email?, full_name?, pipedrive_person_id?, reply_category?, correlation_id}`.
  Map from WF-1's resolved reply fields (`lh_linkedin_profile_url`, person id, correlation_id).
- Make it a tee (its failure must not affect WF-1's own writes): call it on a branch that does not
  gate WF-1's CRM path; the tee already routes its own errors to the error workflow.
- Quiet-window, start-of-week; PUT-verify WF-1 shows the added node and nothing else changed.

## 8. Activation order
Activate: subworkflows are called (no activation needed) → `dnc_expiry_job` (schedule) →
`smartlead_observability_readonly` (schedule) → `dnc_check_service` (Slack trigger; ensure the Slack
app `app_mention` subscription + bot invited to `C0BFE6KAN8J`) → WF-1 (already active; the tee rides it).

## 9. Rollback (per workflow)
- **Tee / WF-1 change:** re-import the recorded WF-1 `versionId`; or delete the added Execute-Workflow
  node. The ledger keeps whatever it already wrote (soft state; harmless).
- **dnc_expiry_job / observability:** set inactive (deactivate). They are stateless beyond `obs_state`;
  no external writes to undo (observability is read-only; expiry only soft-flips ledger rows).
- **dnc_check_service:** deactivate (read-only; nothing to undo).
- **UpsertLedger bad write:** rows are soft only — set `status=removed`, `removed_reason=rollback`.
  Never hard-delete (audit trail).

## 10. Config & ops reference
- **CONFIG lives** in the `CONFIG` Set node at the top of each workflow (`MODE`, `alert_channel`,
  `ttl_months`/`DNC_TTL_MONTHS=6`, `r1_stall_hours`, `r4_delta_threshold`, `dedupe_hours`,
  `smartlead_base`, `campaign_id`, `digest_dow`). Change behavior here, not in node bodies.
- **Raise the ledger cap:** default 50 MB (~100k+ rows). If it nears the limit, set
  `N8N_DATA_TABLES_MAX_SIZE_BYTES` (bytes) and restart; if structural, move storage to Postgres
  behind the `dnc.check`/`dnc.upsert` contract (readers/writers unchanged).
- **Deferred (do not build until endpoint confirmed):** R2 forward-gap, R3 edge-category digest,
  and the observability multi-campaign loop (single-campaign per execution today).

## Publishing gate — all must be true before flipping MODE=prod / attaching the tee
- [ ] `node run_all_tests.js` green · [ ] every SMOKE.md executed in DEV · [ ] reviewer approved ·
- [ ] Slack approval received · [ ] credentials mapped in prod · [ ] rollback `versionId` recorded ·
- [ ] quiet window, start of week.
