# DNC BUILD — Projections Pass design plan (Pipedrive/Smartlead/HeyReach)

**Status: DONE (plan only, per instruction — "bring me the plan, not the execution").**

## What was asked
Design the projection pass (Pipedrive DNC labels for the 2,264, Smartlead global block where
email exists, HeyReach exclusion) as its own reviewed step, with per-channel dry-run counts before
any live fire. Plan only.

## What happened
Researched existing Pipedrive/Smartlead/HeyReach write patterns already proven in this codebase
(WF-2's lead-label and Smartlead-unsubscribe calls, HeyReach's read-only-only history) before
writing the plan, so it reuses real mechanisms instead of inventing new ones. Key findings:

- **Smartlead**: a proven, live `POST /leads/{lid}/unsubscribe` mechanism exists (WF-2). Gap: our
  registry has `email_lc`, not Smartlead `lead_id` — needs a resolve step. 987 of the 2,264 matched
  persons have a real email (from seed data, already known, no new pull needed).
- **Pipedrive**: NO existing person-level DNC field or write mechanism. Only a lead-level label
  write exists (WF-2), which under-covers persons with no open lead. Real open decision for the
  owner: new Pipedrive person field vs. accept the lead-label coverage gap.
- **HeyReach**: ZERO existing write/exclusion mechanism, and a documented prior finding that
  `RemoveFromCampaign` has historically broken reply webhooks for that lead — a real risk, not
  speculation. Recommended as the last channel, needing its own separate go/no-go.

Full plan: [PROJECTIONS_PASS_PLAN_2026-08-11.md](../DNC_OBS_P1_build/PROJECTIONS_PASS_PLAN_2026-08-11.md).

## Improvable
- Pipedrive's field-creation decision blocks that channel's live-write design (not the dry-run
  count) — flagged clearly, not guessed at.
- HeyReach's webhook-breaking risk should be re-verified against HeyReach's current API before any
  live-write branch is designed, independent of the other two channels.

## Next
Awaiting owner review of the plan shape. If approved, next step is building the three dry-run
branches (count-only, zero external API calls) and bringing back real counts — still no live
writes at that point.
