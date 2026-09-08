# 2026-08-06 — Reply-gap investigation (Person-b9e6150b / digest showed 0)

Read-only diagnosis, no fixes deployed (explicit user gate: "No fixes deployed without my word").

Full report: `WF1_W1.0.1_build/wf1-release-evidence/REPLY_GAP_INVESTIGATION_2026-08-06.md`

## Done

- **Step 1** — reply confirmed on 3 independent Smartlead surfaces, exact ts `2026-08-05T06:08:38Z`,
  `lead_category_id 7` = Wrong Person.
- **Step 2** — WF-2 executions: 973-min dead gap `2026-08-04T14:30:27Z → 2026-08-05T06:42:59Z`;
  **0 executions within ±30 min of the reply**. Webhook 404'd, no execution record exists.
  Named the cause: **WF-2S is SENT-only; no reply-side reconciler exists.**
- **Step 3** — digest's "Replies (24h)" = `c1_daily_reports.py:142`, counts WF-2 `Shadow Log`
  rows only → measures *our processing*, never *reality*. Proposed (not deployed) the
  Smartlead-vs-processed-with-delta fix.
- **Step 4** — 72h sweep, 4 campaigns: **12 replies exist, WF-2 processed 2, 10 missing**, and the
  boundary is exact (before-window 2/0 missing, in-window 10/10 missing, after-window 0 replies).
- **Step 5** — Make run history + Pipedrive labels: **Make did NOT handle the Ashwin reply**, and
  handled only 1 of 10 leads overall. The "Make is the safety net" premise is **disproven**.
- Wrote the report + 6 evidence artifacts.

## Findings that change prior assumptions

1. **Make is not a redundant safety net.** Scenario 8557478 is instant/webhook-triggered
   (`hookId 3819933`) and received only 3 of 12 reply webhooks. It shares the same fragile
   Smartlead delivery as WF-2. Last Make run of any kind: 2026-08-04T22:01:15Z (37h ago).
2. **Business impact is real, not absorbed.** 8 leads sit at `1. Cold` with real replies against
   them, incl. one `Interested` and one `Not Interested`. Ashwin's reply has zero trace in any
   system.
3. **Smartlead has two reply surfaces and they disagree.** `/campaigns/{id}/statistics.reply_time`
   → 8 replies; `/campaigns/{id}/leads-statistics` `history[] type=REPLY` → 12. The obvious
   endpoint under-reports by 33%. Any "source of truth" reply count must use the latter.
4. **No positive control exists.** Smartlead sent 0 emails on 08-05/08-06; the only post-recovery
   WF-2 executions are my own probes (`Python-urllib/3.12`). The reply path is **unverified**
   since recovery, not verified.
5. `pii-7b1c0e1a@example.invalid` — Make fired but the person has **0 leads**, so nothing could be
   labeled. Independent instance of the known Make lead-creation defect class.

## Partial / not done

- **Make per-run bundle attribution** — API cannot reach it (`/logs/{execId}`, `/executions/{execId}`
  both fail; `/dlqs` 400 at org level, 404 at scenario level). Attribution done by timestamp +
  Pipedrive `Make/production` changelog evidence instead. The 2026-08-04T22:01:15Z run is
  **unattributed**.
- **No fix deployed** — digest fix, reply reconciler, and the 8-lead backfill are all proposed
  only, awaiting the owner's word.

## Blocked

- Nothing blocked; the gate is deliberate.

## Improvable

- `ashwin_wf2_deadwindow_sweep_v2.py` used a substring-over-blob cross-reference — the banned
  class from `no-substring-blob-checks`. v3 redid it with parsed `Shadow Log` fields and got the
  same answer, so the conclusion held, but the v2 method should not be reused.
- v6's first run filtered labels with `startswith("respond")` against a label literally named
  `3. Responded` → printed a false `0 / 10`. Caught before reporting; filter corrected to a
  substring test and re-run. Same root shape as the blob-check class: **matching a label/field by
  guessed prefix instead of reading the actual value.**
- The Windows CA bundle in scratchpad was gone (old session dir) — regenerated from the cert
  store. Worth a durable path if this keeps recurring.
