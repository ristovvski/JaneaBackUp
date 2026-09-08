# Smoke checklist — heyreach_reply_to_dnc_ledger (Build 3)

Standalone tee. **We never attach it to WF-1** — the human wires WF-1's reply branch to call it at
/publish. Import after Build 2 subworkflows exist.

## Pre
- [ ] Import; open `Call DNC__UpsertLedger__v1` and bind `workflowId` to the imported
      `DNC__UpsertLedger__v1` (placeholder `REPLACE_DNC__UpsertLedger__v1_ID`).
- [ ] Set the workflow's Error Workflow to your `CORE__ErrorHandler` / WF-ERR
      (placeholder `REPLACE_CORE__ErrorHandler_ID`).
- [ ] CONFIG `MODE=dev`, `alert_channel=C0BFE6KAN8J`.

## Runs (pin fixtures from `fixtures/heyreach/`)
- [ ] `reply_received_linkedin_only.json` → `Map` builds `entry_type=replied, source=heyreach_reply,
      idempotency_key=heyreach:hr_evt_1001:dnc`; UpsertLedger inserts `mario-rossi`; `MODE==dev?`
      true → Send Guard → **dev summary posts to C0BFE6KAN8J** (`action`, identity, idem key, exec id).
- [ ] `reply_received_both_ids.json` → same identity; UpsertLedger `update` (email + reply_category added).
- [ ] `reply_received_conflict.json` (after seeding `pii-5fb991e9@example.invalid`) → UpsertLedger
      `Decide.action=conflict` → conflict alert to C0BFE6KAN8J; **no ledger write**.
- [ ] `reply_received_replay.json` → UpsertLedger `noop`; no new/changed row (idempotent replay).
- [ ] Prod-silence check: set CONFIG `MODE=prod`, replay linkedin_only → `MODE==dev?` false → **no
      Slack** on the happy path (Melisa's rule). Conflict still alerts. Restore `MODE=dev`.

Note: the tee posts NOTHING to any outbound provider; it only calls the ledger sub + (dev) Slack.
