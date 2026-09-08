# FLIP DAY — automation map (I0, read-only inventory freeze)

2026-08-05. Consolidates every automation touching the LH/Pipedrive/Smartlead lead pipeline before
the flip decision. Nothing in this document was written by executing anything — it's inventory only.

## Make.com

| scenario | role | known defects |
|---|---|---|
| **8557031** | email SENT → create Lead in Pipedrive | **D1** person-matched by NAME (`exact_match`, limit 1) → 58 confirmed wrong-person attachments; **D2** every Pipedrive step wraps `builtin:Ignore`, so 40/40 runs log "successful" while people go missing; **D3** a bracket-regex kill-switch (`\[([^\]]+)\]`, `continueWhenNoRes:false`) silently halts lead creation for any campaign name without square brackets. **34% of Ai4 email prospects have no Pipedrive person** as of the 08-04 audit. Resumed running 2026-08-04T21:41Z after the day's sends restarted. |
| **8557478** | campaign response → "responded" label + **the real forwarding router** | 14 hardcoded `forward-email` calls in router 82 (one per owner). This is the mechanism behind the double-forward incident — our own WF-2 forward duplicates it whenever both run. Confirmed active. |

Full detail: `wf1-release-evidence/PROD_ISSUES_2026-08-04.md`, memories
[[make-lead-creation-defects]], [[make-forwards-second-copy]].

## Zapier — "Outreach infrastructure" folder (5 active Zaps)

| Zap ID | title | writes |
|---|---|---|
| 274354645 | Add "Cold" label on LH connection sent | Cold |
| 274357463 | Add "Connected" label on LH response | Connected |
| 274357187 | Add "Responded" label on LH response | Responded **+ Slack post** (only Zap with a Slack side-effect — a duplicate poster relative to our own alerting) |
| 274318213 | Make.com replacement — connection already exists | Connected |
| 274316027 | Make.com replacement — connection accepted | Connected |

**Ghost history (critical, and still open):** these are the exact five Zaps behind the "ghost"
label-clobber incident ([[wf1-parallel-automation-clobber]]). Disabled 2026-07-17T13:45Z, reappeared
**ON at 15:56Z the same day**, and per the earlier audit have run continuously since — three weeks,
unnoticed. **Nik has now confirmed this was not him and nobody knowingly fixed them.** So: clobber
history is *proven* (the original 2026-07-17 diagnosis), current behavior is *unverified*. Not a flip
blocker by itself, but scheduled as its own check (C5) and a hard requirement that our own writes stay
read-merge-write union so we can never be blamed for what these Zaps do independently.

## Pipedrive-native automations (as given by Nik — no read API exists for these, confirmed this
session: `/v1/automations` 404s, `/api/v2/automations` 200s but is the web-app HTML shell, not data)

- **13 Marci deal/project automations** — out of contour, DO-NOT-TOUCH.
- **In contour (DO-NOT-TOUCH, we feed them):**
  - *"Responded handover to Melisa"* — Lead updated + label "3. Responded" + owner=Melisa + no next
    activity → Handover. 46 executions / 7 days.
  - *"Responded already there"* — same condition on Lead ADDED. 0 executions / 64 discarded (i.e. the
    condition fires on add but never finds "no next activity" true — matches the plan's premise that
    a backfill write could trigger it live).
  - *"New lead owner"* — owner changed FROM Melisa → Follow-up for new owner. 43 executions / 7 days.

These three are why the backfill guard in Phase C2 exists: a bulk label/lead write can mint live
Handover activities for historical events unless suppressed.

## Yesterday's new leads (2026-08-04) — who created them

Read-only Pipedrive scan, sorted/paginated. **82 leads created on 2026-08-04** (plan text said ~64 —
actual count differs; reporting what was measured, not reconciling the discrepancy further).

| creator | count | pattern |
|---|---|---|
| Mykyta Kryvosheia (creator_id 25112064) | 80 | channel=578 (LinkedIn), titles follow the WF-1 convention `{campaign.id} - {campaign.name} - {name}` — **this is WF-1's own automated creation**, not a human. (`creator_id` reflects the API-token identity, not manual authorship — see [[wf1-parallel-automation-clobber]] correction.) |
| Marci Csomor (creator_id 13015123) | 2 | one titled with no campaign prefix ("Remzi Gokhan Goral") — a manual hand-created lead |

No creator in this pass is attributable to Make or Zapier — those platforms write through Pipedrive's
API under their own connected accounts, which may not surface distinctly via `creator_id`; not
independently confirmed either way.

## WF-2 outage root cause — CORRECTED from earlier in this session

Established by direct observation (twice), not the "unverified activate" theory reported earlier
today: **`WorkflowCrashedError: possible out-of-memory issue`** on a WF-2S replay burst crashes the
n8n instance and leaves WF-2 `active=false`; every subsequent replay then 404s
("Active version not found"). This — not a bad deploy — caused the original ~15h/~830-event outage
(2026-08-04T14:30Z) and a second crash during my own recovery attempt (2026-08-05T07:00Z, wide
lookback + old cap). Full record: [[wf2-oom-replay-burst]].

**Consequences already acted on:**
- WF-2S alarms on WF-2 `active===false` unconditionally (patched, live).
- **Phase A1 done, verified**: `max_per_run` set to **20, permanently** (was 100). `lookback_minutes`
  left at 180 — deliberately not widened; the backlog stays unreachable until Phase C4.
- **Phase A2, confirmed**: 745 SENT events from the outage are currently 100% outside the 180-minute
  window (oldest is 1205+ min old and growing) — no recovery today; slow drain (cap 20, ~38 cycles,
  ~9.5h) is a Phase C action, after the flip is stable.
- **Phase A3, advanced but not closed.** Both documented crashes show **WF-2S and WF-2 crashing
  together, in the same few seconds** — exec 13391 (outage start) killed WF-2S before it persisted
  even the CONFIG node, with all 6 concurrent WF-2 executions also `crashed`; exec 13551 (recovery
  attempt) got WF-2S as far as `Replay Into WF-2` (1 item) before the `WorkflowCrashedError`, with the
  4 concurrent WF-2 executions in that same window also `crashed`. Both going down together, every
  time, points to a **shared instance-wide memory ceiling** rather than either workflow's graph in
  isolation — which means **WF-1 (live production LinkedIn receiver, same instance) shares this exposure**
  whenever a large-enough burst fires anywhere on the instance. Whether n8n Cloud's memory ceiling is
  visible or raisable is **not answerable via the API** (`/api/v1/license`,
  `/api/v1/source-control/status` both 404 — self-hosted/enterprise-only endpoints); it needs a human
  check of the account/billing dashboard.

## What this means for the flip gate

Nothing here blocks B1/B2 pre-checks from proceeding. The OOM finding **is** a flip blocker per its
own memory until the batch-size fix is confirmed durable under live load. Phase A1 (cap=20) reduces
*how often* a burst is large enough to trip the ceiling, but does not prove the ceiling itself, and
the instance-wide framing means WF-1 is exposed too — that risk exists independent of anything WF-2
does. This is a genuine open item for the flip decision, not fully resolved by A1 alone.
