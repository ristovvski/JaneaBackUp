# Zapier — "Outreach infrastructure" folder: active workflow audit

- **Source**: Zapier account, folder `Outreach infrastructure` (folder id `01944674-5e38-efad-9589-97666bef4589`)
- **Method**: read-only — Zapier Manager MCP actions (`Find Zap`, folder/Zap enumeration) + view-only page loads of each Zap's published editor (no drafts saved, no steps edited)
- **Scope**: this folder contains 7 Zaps total; **5 are active (ON)**, 2 are OFF. This doc covers the 5 active ones in detail, with the 2 inactive ones listed briefly for completeness.
- **Caveat**: step-level filter conditions and exact field mappings (e.g. which Pipedrive field/value the filter checks, which label ID gets written) could not be safely extracted — opening a step's edit panel put the Zap into a "has unsaved changes" draft state in the browser, which was discarded every time rather than risk saving. What's documented below is the **trigger → step chain (apps + step types) and each Zap's own descriptive title**, which together indicate what each one does and how, but not the literal field-level configuration.

## Active Zaps (5)

### 1. Add "Connected" label to lead if LH response is received
- **Zap ID**: 274357463 · [editor link](https://zapier.com/editor/274357463)
- **State**: ON · last live 2026-07-17T15:56:19Z · last paused 2026-07-17T13:45:38Z (before that ON period) · last edited by: (not recorded)
- **Steps**: Pipedrive *Updated Person* (trigger) → Filter by Zapier *Filter conditions* → Pipedrive *Find Lead* → Pipedrive *Update Lead*
- **What it does**: Fires when a Person record is updated in Pipedrive (this is how LinkedHelper (LH) activity gets surfaced — LH writes back to a Pipedrive Person field). A filter step gates on the specific condition that indicates "an LH response was received." If it passes, the Zap looks up the associated Lead and updates it to add a **"Connected"** label.

### 2. Add "Responded" label to lead if LH response is received
- **Zap ID**: 274357187 · [editor link](https://zapier.com/editor/274357187)
- **State**: ON · last live 2026-07-17T16:03:25Z · last paused 2026-07-17T13:22:03Z · last edited by: mykyta@janeasystems.com
- **Steps**: Pipedrive *Updated Person* (trigger) → Filter by Zapier *Filter conditions* → Pipedrive *Find Leads* (search, plural — may return/consider multiple candidate leads) → Pipedrive *Update Lead* → Slack *Send Channel Message*
- **What it does**: Same trigger pattern as #1 (Pipedrive Person update signalling an LH response), but tags the Lead **"Responded"** instead, and additionally posts a notification to a Slack channel — this is the only Zap in the folder with a Slack side-effect.

### 3. Add "Cold" label to lead if LH connection request is sent
- **Zap ID**: 274354645 · [editor link](https://zapier.com/editor/274354645)
- **State**: ON · last live 2026-07-17T15:56:18Z · last paused 2026-07-17T13:45:40Z
- **Steps**: Pipedrive *Updated Person* (trigger) → Filter by Zapier *Filter conditions* → Pipedrive *Find Lead* → Pipedrive *Update Lead*
- **What it does**: Same structural pattern, but keyed off a different signal — a LinkedHelper **connection request having been sent** (not yet accepted/responded) — and labels the Lead **"Cold"** (i.e., outreach initiated, no engagement yet).

### 4. Make.com replacement for LH connection already exists - put connected tag in lead
- **Zap ID**: 274318213 · [editor link](https://zapier.com/editor/274318213)
- **State**: ON · last live 2026-07-17T15:56:16Z · last paused 2026-07-17T13:45:24Z
- **Steps**: Pipedrive *Person Matching Filter* (trigger — a "new/updated Person matching a filter" style Pipedrive trigger, filtering is built into the trigger step itself rather than a separate Filter-by-Zapier step) → Pipedrive *Find Lead* → Pipedrive *Update Lead*
- **What it does**: Explicitly named as a **migration off a former Make.com scenario**. Handles the LinkedHelper case where a connection **"already exists"** (i.e., you were already connected before outreach started) and tags the associated Lead as connected.

### 5. Make.com replacement for LH connection accepted - put connected tag in lead
- **Zap ID**: 274316027 · [editor link](https://zapier.com/editor/274316027)
- **State**: ON · last live 2026-07-17T15:56:16Z · last paused 2026-07-17T13:45:15Z
- **Steps**: Pipedrive *Updated Person* (trigger) → Pipedrive *Find Lead* → Pipedrive *Update Lead*
- **What it does**: Sibling of #4, also a **Make.com replacement**. Fires when a LinkedHelper connection request is **accepted**, and tags the associated Lead as connected. No explicit Filter step was visible in the step chain — the trigger itself may be pre-filtered, or filtering happens inside the trigger's own configuration (not independently confirmed).

## Inactive Zaps in the same folder (OFF — out of "active" scope, listed for completeness)

| Zap | ID | State | Notes |
|---|---|---|---|
| TechEx 2025 - Slack Voice Note to Clay | 324242615 | OFF | Never shows a live/paused timestamp — appears to have never been activated. |
| Conference status update notification to Melisa, CC Karol | 293788452 | OFF | Last live 2025-04-24, paused 2026-06-06. Last edited by marcell@janeasystems.com. |

Neither of these fits the LinkedHelper/Pipedrive lead-tagging pattern the 5 active Zaps share — they look like one-off conference/notification automations, not part of the core outreach pipeline.

## Overall picture

All 5 active Zaps form one coherent subsystem: **LinkedHelper (LinkedIn outreach automation) writes activity signals into Pipedrive Person records → each Zap watches for one specific signal (response received, connection request sent, connection already existed, connection accepted) → resolves the matching Pipedrive Lead → stamps a status label onto it** ("Connected", "Responded", "Cold"), with one variant (`Add "Responded" label...`) also notifying a Slack channel.

Two of the five (#4 and #5) are explicitly documented in their own titles as **replacements for prior Make.com scenarios** — this Zapier folder is a partial/full migration off Make.com for LinkedHelper-driven lead tagging. This is consistent with prior project history around Make.com scenarios handling LinkedHelper connection events (see project memory on Make.com lead-creation/duplication issues) — worth confirming with the team whether the Make.com originals have since been deactivated, since that wasn't checked as part of this audit.

## Open questions for follow-up (not resolved by this read-only pass)

1. Exact filter conditions on each Filter-by-Zapier step (which Pipedrive field/value triggers each one).
2. Exact field(s)/label IDs written by each "Update Lead" step.
3. Whether the corresponding Make.com scenarios (for #4 and #5) are still active in parallel, which would risk duplicate tagging.
4. Whether "Find Lead" vs "Find Leads" (Zap #2) behaves differently when multiple leads match, and what happens to extras.
