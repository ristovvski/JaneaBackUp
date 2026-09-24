# 2026-09-08 — pii-9b2ca0d1@example.invalid: first live reply through the email-side capture

Traced on request. Four questions, each answered from a different system so no single source could
flatter the result. **All four confirmed.** Evidence: `WF1_W1.0.1_build/trace_amity_curry.json`,
`_trace_amity.txt`.

## What actually happened — two replies, not one

| time (UTC) | what | execution |
|---|---|---|
| 12:57:20 | reply 1: *"apologies for slow reply … propose meeting in the morning"* | — |
| 12:58:03 | WF-2 direct from Smartlead, uncategorised, classified, **alerted**, claimed, DNC written | `48527` (79 nodes) |
| 13:15:59 | WF-2R replay of reply 1, now carrying the category | `48543` |
| 13:16:02 | WF-2 re-delivery — **deduped**, 20 nodes, no alert, no DNC, no labels | `48544` |
| 13:23:14 | reply 2: *"Looks good. I'll accept. See you tomorrow."* | — |
| 13:24:04 | WF-2 direct, classified, **alert suppressed by the registry**, DNC written | `48554` (74 nodes) |
| 14:45:59 | WF-2R replay of reply 2 — the 17:46 local cycle | `48601` |
| 14:46:05 | WF-2 re-delivery — deduped, 24 nodes | `48602` |

## The four answers

**1. Category — real, not OOO.** Our classifier ran twice: **Meeting Request**, confidence 0.94 and
0.92, `is_dnc: false`. Smartlead's own category arrived later, also Meeting Request (id 2).
`__is_bounce: false`, `__reply_class: lead`.

**2. Alert — posted exactly once, to #lead-processing.** `Reply Alert` → `C07LTD8UT70`, ts
`1788872287.406949`, exec `48527`. Enumerated every Slack node in WF-2 across all five executions:
**one** reply alert, total. The mechanism is on the wire — `48527` read `DT Alert Get → {}`,
alerted, then claimed `wf2_alert|85878` (row 1219, `claimed_at 12:58:21.764Z`); `48554`, the second
*real* reply, read that row and `IF Should Alert` emitted **0 items**.

**This is the live multi-event proof of the #26 registry port.** The staticData rollback copy can
come out.

Consequence worth naming: the key is person-scoped, so reply 2 — a materially different message,
accepting the meeting — produced no notification at all. By design (first-reply alert), but the team
saw only reply 1.

**3. DNC row — written, via the new inline path.** `DNC Reply Gate → DNC Build Input →
DNC Upsert Call` fired on both real replies with `reason: reply_dnc`,
`correlation_id: wf2_reply:3868449:pii-9b2ca0d1@example.invalid`; the ledger sub-workflow executed at
12:58:22Z and 13:24:27Z with the same correlation_id, so one row. **First live proof of the
email-side capture** (3 Sep deploy).

**And this is the first named case of the consequence I flagged before building it.** Person-d86d9627
wrote *"Looks good. I'll accept. See you tomorrow."*, her lead carries **4. Positive Reply**, she is
meeting Noah tomorrow — and she is now in **DNC active, entry_type `negative_reply`, permanent**
(`expires_at: null`, via `date_precision: 'unknown'`). The rule is executing exactly as ruled
("EVERYONE WHO REPLIES TO ANY OF OUR CAMPAIGNS GOES TO DNC ACTIVE"). Recorded, not re-litigated.

**4. Label `3. Responded` — set.** Read back from Pipedrive rather than inferred: lead
`98176190-a2dc-11f1-8c80-f7dd29ef5cd5` carries **1. Cold, 2. Connected, 3. Responded, 4. Positive
Reply**. Union preserved, nothing removed. `4. Positive Reply` is not ours — our union body had
three — so a cohabitant added it after us, consistent with the known accepted cohabitant.
Reply activities 46024 and 46028 both landed on the lead.

## Unplanned bonus proof — the auth-notice port, live

Exec `48602` (14:46:05Z) ran the chain deployed an hour earlier:
`DT Auth Notice Get → Auth Notice Decide → DT Auth Notice Claim → Auth Notice Ctx`, verdict
**`no_row_first_notice`**, row `wf2_auth_notice` written with
`{"mode":"unconfigured","suppressed_since_last":0,"last_posted_date":"2026-09-08"}`, one post to
`#alerts` (`C0BTUHSSM3K`). The first-notice half is proven. The **suppression** half is not — it
needs a second non-valid event today reading `already_posted_today`.

## Two defects the trace exposed

1. **`reply_category` in the ledger row is `email_reply_uncategorised`** even though our own
   classifier had returned "Meeting Request" at 0.94 confidence in the same execution.
   `DNC Build Input` reads Smartlead's `reply_category`, which is `null` on the direct webhook
   because of the categorisation race. It should prefer `Classify Parse.__category` when the
   provider's is absent. One-line fix; the row is currently less informative than the evidence we
   held at the time of writing it.
2. **`__deal_check_failed: true` in every execution.** The deal guard is not completing. Harmless
   here because the lead already existed, but this is the guard that blocks lead creation when a
   person is already represented by an open deal — the guard that exists because of Andrea's
   duplicate. Worth its own look.

## Improvable — mine

* The first trace pass looked for a node called `Critical Slack`, which is **WF-1's** name for the
  alert node. WF-2's is `Reply Alert`. So the first pass showed the gate opening and no delivery,
  and I would have had to infer the post from `IF Alert Delivered` firing. Enumerating the Slack
  nodes from the workflow definition — rather than from a remembered name — is what produced the
  channel and the timestamp. Same class as the leads-statistics key mistake: read the shape, do not
  recall it.
