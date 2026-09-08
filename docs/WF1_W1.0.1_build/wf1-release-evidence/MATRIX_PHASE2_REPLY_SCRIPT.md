# PHASE 2 — REPLY SCRIPT FOR NIK

All 10 emails are already in your inbox, from different `chrissy*` senders. Each subject ends with
the case id: **"WF2 Matrix T5 - please reply"**, etc.

**Reply from `pii-c61c7d08@example.invalid` (the address the mail was sent to). Reply to the email whose
subject matches. Send the text EXACTLY as written — the classifier's behaviour is the thing under
test.**

## ORDER MATTERS — do 1–6 first, then 7, then 8 last

T9 and T12 both globally suppress your address in Smartlead, so they must come after everything else.

| # | reply to subject | reply with EXACTLY this | what it proves |
|---|---|---|---|
| 1 | `WF2 Matrix T5 - please reply` | `Very interested, let's schedule a call` | **T5** — high-confidence classify, SL category written, forward to owner (mapped to you), **first-ever live Slack reply alert (B26)**, labels union, activity with body |
| 2 | `WF2 Matrix T5 - please reply` *(reply a SECOND time to the same thread, after #1 has landed)* | `Also, next week works better for me` | **T7** — CRM updated, **no second alert** (first-reply gate) |
| 3 | `WF2 Matrix T6 - please reply` | `ok` | **T6** — low confidence → Uncategorized, **no** SL category, **review forward → your gmail (B25, never once worked before)**, Ops Warn Classify posts |
| 4 | `WF2 Matrix T8 - please reply` | `Sounds useful, send me the details` | **T8** — a manual label I pre-seed on that lead must survive the union (Silva-class) |
| 5 | `WF2 Matrix T10 - please reply` | `Happy to take a look, what's the timeline?` | **T10** — I delete the Pipedrive records first, so this exercises the no-lead path + warn with search link |
| 6 | `WF2 Matrix T13 - please reply` | `Yes, keep me posted` | **T13** — nurture campaign → Slack note only, **zero CRM writes** |
| 7 | `WF2 Matrix T9 - please reply` | `Remove me from your list, do not contact me again` | **T9** — DNC category, Smartlead unsubscribe, Pipedrive DNC label, **no forward, no alert** (silence assert) |
| 8 | `WF2 Matrix T12 - please reply` | *do NOT reply — instead click the **unsubscribe** link at the bottom of that email* | **T12** — DNC procedure minus classification, silent |

### Two things I must do between your replies

* **before #4 (T8)** — I pre-seed a manual label on the T8 lead. Tell me when you're at that point,
  or just do #1–#3 and pause; I'll seed it and say go.
* **before #5 (T10)** — I delete the Pipedrive person+lead for the T10 campaign so the reply has
  nothing to resolve to. Same: pause after #4.

If you'd rather not pause, do #1, #2, #3, #6 in one go and stop; I'll prepare T8 and T10 and then
ask for #4, #5, #7, #8.

## Campaign / sender map (for finding the right email)

| case | campaign id | sender | recipient |
|---|---|---|---|
| T5 | 3745475 | pii-f06c1226@example.invalid | pii-c61c7d08@example.invalid |
| T6 | 3745476 | pii-a695ef8a@example.invalid | pii-c61c7d08@example.invalid |
| T8 | 3745477 | pii-969484f9@example.invalid | pii-c61c7d08@example.invalid |
| T9 | 3745478 | pii-b37a3cad@example.invalid | pii-c61c7d08@example.invalid |
| T10 | 3745479 | pii-c6fb1ee9@example.invalid | pii-c61c7d08@example.invalid |
| T12 | 3745480 | pii-6e864061@example.invalid | pii-c61c7d08@example.invalid |
| T13 | 3745481 | pii-52b02f88@example.invalid | pii-c61c7d08@example.invalid |

## Window state while you do this

`WRITE_MODE=live`. Chrissy → your gmail. `forward_review_address` → your gmail. WF-2S scoped to the
10 matrix campaigns, cap raised to 14. Revert checklist armed at `MATRIX_REVERT_CHECKLIST.md`
(**note: it must also restore `max_campaigns_per_cycle` 14 → 8**).
