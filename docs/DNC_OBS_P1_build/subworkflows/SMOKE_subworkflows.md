# Smoke checklist — DNC subworkflows (Build 2)

Human executes in the DEV UI after `dnc_ledger` exists (Build 1). Amendment 4.

## Pre
- [ ] `dnc_ledger` table created (all 16 cols incl. `norm_v`).
- [ ] Import the 3 files in `subworkflows/`. On open, each Data Table node's `columns` schema
      auto-fills (`refreshIncompleteSchemaOnOpen`) — click each Data Table node once to confirm the
      column list populated and the `dataTableId` resolved to `dnc_ledger` (mode "name").
- [ ] Confirm the returned row object exposes an `id` field (used by Build 4 dedup). If the field
      name differs, note it — Build 4 targets rows by `identity_key`+`added_at`, not `id`, so this
      is informational only.

## DNC__NormalizeIdentity__v1
Pin input `{ "linkedin_url": "HTTPS://LinkedIn.com/IN/pii-e9f868d3/", "email": " pii-3e101357@example.invalid " }` → run.
- [ ] Output: `linkedin_url_norm=https://www.linkedin.com/in/pii-e9f868d3`, `linkedin_slug=john-doe`,
      `email_lc=pii-3e101357@example.invalid`, `identity_key=john-doe`, `norm_v=v1`.

## DNC__UpsertLedger__v1
Input `{ "linkedin_url":"https://linkedin.com/in/pii-d1f7ffa9","entry_type":"replied","source":"heyreach_reply","correlation_id":"smoke_1" }`.
- [ ] Run #1: `Decide` → `action=insert`; `Route` → 3rd output; `Upsert Ledger Row` writes a row
      (`status=active`, `entry_type=replied`, `expires_at ≈ now+6mo`, `norm_v=v1`).
- [ ] Run #2 (same input, replay): `Decide` → `action=noop`; `Route` → 2nd output → `Noop`; NO new row.
- [ ] Conflict: seed a second row `identity_key=pii-188576fd@example.invalid,email_lc=pii-188576fd@example.invalid,status=active`, then
      input `{linkedin_url:"https://linkedin.com/in/pii-d1f7ffa9", email:"pii-188576fd@example.invalid", entry_type:"replied", source:"heyreach_reply"}`
      → `Decide` action=conflict → `Send Guard` passes (channel==C0BFE6KAN8J) → Slack conflict alert
      posts to `C0BFE6KAN8J`; NO write.
- [ ] Send-guard proof: temporarily set CONFIG `alert_channel` to any other id → conflict run must
      HARD-FAIL at `Send Guard` (never posts elsewhere). Restore to `C0BFE6KAN8J`.

## DNC__CheckLedger__v1
- [ ] `{linkedin_url:"https://linkedin.com/in/pii-d1f7ffa9"}` → `result=on_dnc`, `entry_type=replied`, `since`, `expires_at`.
- [ ] `{linkedin_url:"https://linkedin.com/in/pii-6e2f970e"}` → `result=clean`.
- [ ] `{email:"garbage"}` → `result=usage_hint`.

Cleanup: soft-remove or delete the `smoke1`/`pii-188576fd@example.invalid` rows before real use.
