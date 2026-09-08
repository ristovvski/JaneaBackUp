# RESIDUAL RE-RUN — REPLY SCRIPT (window is OPEN, live)

Three emails are in your inbox from `chrissy*` senders. Reply from `pii-c61c7d08@example.invalid`.
Preconditions are already set — reply whenever you're ready, in this order.

| # | reply to subject | reply with EXACTLY this | proves |
|---|---|---|---|
| 1 | `WF2 Residual T7 - please reply` | `Very interested, let's schedule a call` | baseline: lead FOUND (B27), category + owner forward + alert |
| 2 | `WF2 Residual T7 - please reply` **again, same thread**, after #1 has landed | `Also, next week works better for me` | **T7** — CRM updated, **NO second alert** (first-reply gate, which needs a found lead to work) |
| 3 | `WF2 Residual T8 - please reply` | `Sounds useful, send me the details` | **T8** — a manual label I pre-seeded must survive the union (Silva-class) |
| 4 | `WF2 Residual T10 - please reply` | `Happy to take a look, what's the timeline?` | **T10** — its lead is deleted, so this is the no-lead path for the RIGHT reason: person-side writes + warn with search link |

**T12 needs nothing from you.** Production email carries no opt-out link (owner-confirmed, by design),
so there is no button to click. I exercise the `UNSUBSCRIBED` handler synthetically and label it as
such in the evidence table.

## Preconditions already applied

* **T8** lead `3b780e20-8cbc-11f1-b3bf-87416721bf99` — manual label seeded, labels 1 → 2
  https://janeasystems.pipedrive.com/leads/inbox/3b780e20-8cbc-11f1-b3bf-87416721bf99
* **T10** lead `3af8f310-8cbc-11f1-b375-61d014f52fbb` — **deleted**. Its person remains, which is
  correct: T10 asserts person-side writes with no lead to resolve.
* **T7** lead `3cb98ed0-8cbc-11f1-86c0-b5d86d079426` — left intact, person 84882.

## B27 already proven by the sends themselves

All three SENT reconciliations saw `cands=[84882, 84883, 84884]`, `dupes=true`, and found their lead
via `title_prefix`. Campaign 3745821 recorded **`adopted=true person=84884`** — the lead hung off a
different duplicate than the provisional and adoption fired. That is the exact failure that cost 6 of
7 replies their CRM update last run.

## Window state

`WRITE_MODE=live` · Chrissy → your gmail · review → your gmail · WF-2S scoped to
`[3745819, 3745820, 3745821]` · WF-2 `46a3688f` · WF-2S `88b35799`.
Revert per `MATRIX_REVERT_CHECKLIST.md` immediately after verification.
