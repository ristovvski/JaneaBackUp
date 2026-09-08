# Smoke checklist — dnc_check_service (Build 6)

Read-only self-check. Salesperson @mentions the bot in `C0BFE6KAN8J` with a LinkedIn URL or email.

## Pre
- [ ] Slack app has `app_mention` event subscription + bot invited to `C0BFE6KAN8J`.
- [ ] `On @mention` node: `Slack DEV (bot)` credential bound; `channelId=C0BFE6KAN8J`.
- [ ] `Call DNC__CheckLedger__v1` bound to the imported CheckLedger sub.
- [ ] CONFIG `MODE=dev`, `alert_channel=C0BFE6KAN8J`. Seed ledger from `fixtures/ledger_seeds.json`.

## Live (mention the bot in C0BFE6KAN8J)
- [ ] `@bot https://www.linkedin.com/in/pii-d1c8a360` → reply `:no_entry: ON DNC — explicit_opt_out
      since 2026-03-01 (permanent) · source: smartlead_category`.
- [ ] `@bot https://www.linkedin.com/in/pii-10597f04` → `clean now — was on DNC (replied) until …`.
- [ ] `@bot https://www.linkedin.com/in/pii-b21c22c6` → `clean — not on the DNC ledger`.
- [ ] `@bot hello` (no id) → usage hint.
- [ ] Mention the bot in a DIFFERENT channel → `Parse Input` returns nothing → no reply (channel guard).
- [ ] Send-guard: flip CONFIG `alert_channel` → HARD-FAIL at `Send Guard` (never replies elsewhere).

Read-only: this workflow has no Data Table writes and no non-Slack HTTP (test-enforced).
Trigger UX is the phase-1 choice (mention in test channel); slash-command / n8n Form is a later upgrade.
