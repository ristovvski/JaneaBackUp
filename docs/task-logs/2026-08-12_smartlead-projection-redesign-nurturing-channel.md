# DNC BUILD — Smartlead projection redesign: nurturing channel near-miss

**Status: FIRE_SMARTLEAD frozen (was already false, stays false). Redesign locked and documented.
No further Smartlead-side writes attempted. Pipedrive unaffected, proceeds independently.**

## What happened
Melisa surfaced a fact nobody had going into the fire decision: Smartlead is not only the cold-
outreach channel — sales executives' real mailboxes are connected there, and ongoing
nurturing/conversation with repliers happens through it too. A global unsubscribe (the mechanism
already proven and about to be authorized) would have severed that nurturing channel for exactly
the warmest population: 538 of the 623 resolved leads are repliers. The auditor's earlier
"one-way door" caution (unsubscribe is non-undoable via API) turned out to be protecting against
the right *kind* of risk, just not yet pointed at the right cause.

Mid-investigation (before the freeze landed), I'd found Smartlead does have a genuine per-campaign
`pause` endpoint, explicitly documented as not touching other campaigns and explicitly recommended
for "replied via another channel... shouldn't get further follow-ups" — on paper, exactly a
nurturing-preserving tool. **Ruled out anyway** per the owner's redesign: no Smartlead-side write
for the general population at all, regardless of how scoped.

## Retroactive check on the one write that landed just before the freeze
I'd re-added 4 malformed block-list entries (comma-packed emails from an unrelated Oct-2025 import
bug, functionally dead — a comma-joined string never matches an exact email lookup) as 4 proper
single entries, seconds before the freeze message arrived. Checked retroactively: **none of the 4
addresses were ever a Smartlead lead at all** — no conversation, no reply, nothing to sever. No
remediation needed. Confirmed via a live `GET /leads?email=` check on each.

## New design, captured in `PROJECTIONS_PASS_PLAN_2026-08-11.md`
- Enforcement moves entirely to our own layer: every campaign-add path (WF-1/WF-2, future WF-3,
  any bulk add) checks the registry before adding to a **cold** campaign. Nurturing adds exempt by
  design — enforceable because every real add path already runs through our own n8n workflows.
- `SL Unsubscribe` retired for the general population. Only explicit hard opt-outs (pending
  Melisa's per-category word) remain candidates for a true unsubscribe — zero writes until she
  gives it.
- The 288-never-a-lead / block-list path: same freeze, same open question (does a block-list entry
  also suppress nurturing sends, not just cold ones?) — unanswered, no further entries beyond the
  one harmless `.invalid` fixture.
- `FIRE_SMARTLEAD` likely becomes a no-op concept — the sweep's Smartlead branch would shrink to a
  read-only escalation report (who's in the registry AND currently in a cold campaign), not a
  write branch. Not built yet — this is a design lock, not a build instruction.
- New standing review-protocol item, per the owner: any future projection design must state which
  *other* uses of the same provider it could break.

## What I did NOT do
Did not touch `FIRE_SMARTLEAD` (already false). Did not add anything to the block-list beyond the
already-completed, now-verified-harmless fixture + 4-dead-address fix. Did not start building the
new registry-check-before-add mechanism or the escalation report — that's a real, separate build
task and nothing so far asked for it to start now.

## Next
Whenever ready: scope and build the registry-check-before-cold-add gate (touches WF-1/WF-2/future
WF-3) and the read-only escalation report. Pipedrive's fire proceeds independently, unaffected.
