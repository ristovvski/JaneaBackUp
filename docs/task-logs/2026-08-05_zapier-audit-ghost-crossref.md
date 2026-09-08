# Task log — 2026-08-05 — reconciling the Zapier "Outreach infrastructure" audit against project memory

**What arrived:** the user pasted a read-only audit of a Zapier folder ("Outreach infrastructure," 5
active Zaps + 2 inactive) doing LinkedHelper→Pipedrive lead tagging, produced in a *different* Claude
Code session where Zapier-MCP was actually working (this session never got MCP access despite several
restart attempts — see the earlier part of this conversation). That session had already written its
own memory file, `zapier-outreach-infra-folder.md`, and a full writeup to
`ZAPIER_outreach_infrastructure_zaps.md` in the project root.

**What I did:** read the new memory file, then checked it against `wf1-parallel-automation-clobber.md`
(the "ghost" label-clobber incident, closed 2026-07-17 per that memory) — because the five Zap IDs in
the new audit looked identical to the five Zap IDs named as the ghost's cause. They are: `274354645`,
`274357463`, `274357187`, `274318213`, `274316027`, exact match on all five.

## The finding

The new audit's own timestamps show something the ghost memory doesn't account for: all five Zaps show
**last-paused ≈13:45Z and last-live ≈15:56Z, both on 2026-07-17** — i.e. every one of them was switched
back ON about two hours after the disable that memory calls "CLOSED & VERIFIED," and per the new audit
they have been on continuously since (about three weeks, unnoticed until this audit).

The ghost memory's own verification (a 15-minute clobber-absent trap) ran inside the
~13:47–14:02Z window — entirely **before** the 15:56 re-enable. So that verification says nothing
about behavior after these Zaps came back on. Whether what went live at 15:56 was a deliberate fixed
redeploy (plausible — two of the five are explicitly titled "Make.com replacement," suggesting an
intentional migration cutover that afternoon) or the ghost quietly reopening is **not established by
either document**. The 2026-07-20 "known accepted cohabitant" entry in the same memory found only
union-safe additive label behavior (no strip) around that date, which is reassuring but describes a
possibly-different Zap (a republished sprint reply-Zap draft) and is now over two weeks stale itself.

## What I did about it

- Appended a dated, clearly-labeled "OPEN QUESTION, NOT YET RESOLVED" note to
  `wf1-parallel-automation-clobber.md`, rather than rewriting its resolution — I don't have evidence
  strong enough to declare the closure wrong, only evidence that it's incomplete.
- Added the reciprocal cross-reference to `zapier-outreach-infra-folder.md`.
- Did **not** set up any live check, trap, or read of current lead label state. Standing memory rule
  ("Traps only run on Nik's explicit word going forward," recorded 2026-07-20) applies squarely here,
  and I have not received that word for this specific question.
- Flagged the discrepancy to the user directly and asked whether the 15:56 re-enable was known/
  intentional, since that answer determines whether any further checking is warranted at all.

## Blocked

- **No independent evidence either way on current behavior.** I have not read Pipedrive lead/label
  state, activity history, or n8n executions to check for a live strip — that would itself start
  becoming the kind of check the "no traps" rule is about, so it needs the user's word first.
- **Field-level configuration is unrecoverable read-only.** Both this session and the one that ran the
  audit hit the same wall: Zapier's step editor forces an unsaved-draft state the moment you open a
  step's config, so exact filter conditions and label-ID writes on the *current* live version were
  never captured. Without that, even a live check could tell us "labels moved" but not definitively
  "this Zap did it via a replace-semantics write," the way the original ghost diagnosis could.

## What can be improved

- The other session's memory file didn't cross-reference the ghost incident at all — it only linked to
  the Make.com memories. Same project, same memory store, and a five-way exact ID match went unnoticed
  until this session read both files side by side. Worth remembering: a new audit should be checked
  against *all* existing project memories with overlapping subject matter, not just the ones the
  triggering context made obviously relevant (Make.com, in that session's case — it was building a
  Make-vs-Zapier migration picture, not looking for the ghost).
- If Nik confirms the 15:56 restart was unintentional or unknown, the next step is a proper, authorized
  trap — same design as the original ghost investigation (long window, not the 5-minute one that gave
  false negatives), and it should check execution-truth (n8n node outputs) rather than final Pipedrive
  label state, per the lesson already recorded in that same memory file.
