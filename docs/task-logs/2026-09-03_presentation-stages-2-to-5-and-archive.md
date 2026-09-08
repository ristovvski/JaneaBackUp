# 2026-09-03 — presentation Stages 2–5, plus the archive pass

**Task:** Stage 2 (per-workflow detail), then archive unused workflows, then Stages 3–5 (four domain
docs, the lead journey, the slide outline). Re-read WF-1 and the gate first, since a concurrent
session moved them. Read-only for the doc stages; the archive was a separate authorised write task.

**Output:** `PRESENTATION_2026-09-03/` (10 files, 140 KB) and `ARCHIVE_2026-09-03/` + `ONE_SHOT_TOOLS.md`.

---

## DONE

### Re-read before writing
Fresh snapshot at 09:00Z and a full re-dump of all **944 node payloads**. Diffed WF-1 126 → 130
against my 08:20Z baseline to see exactly what the other session changed: four nodes added
(`M7 Alert Key`, `M7 DT Alert Get`, `M7 IF Alert Delivered`, `M7 DT Alert Claim`), two rewritten,
five connections rerouted — the alert-delivery registry moved from workflow memory to the claims
table. Read the new code rather than assuming what the port did.

### Stage 2 — two files, eight headings each
`STAGE2A` (WF-1, WF-2, WF-2S, WF-2R, WF-2H, WF-ERR) and `STAGE2B` (gate, monitor, registry writer,
capture sources, projector, escalation, I-04, digest, linter, intent-vs-reality, operator tools,
remaining inactive).

### Archive pass — 12 archived, 0 deleted, active 22 → 20
Deactivate + rename `ARCHIVE__*`. Three safety checks before any write: every candidate id searched
across all 40 workflows (**zero references**); each live name asserted to match exactly, so a
concurrent rename would abort rather than archive the wrong thing; full backup. Every workflow
re-read afterwards and asserted renamed **and** inactive. KEEP list re-verified.
`WF-1-DO NOT USE` also had its webhook path neutralised — node kept, since other nodes reference it
by name and the artifact exists to be readable.

### Stages 3–5
Four domain docs (LinkedIn, cold email, the registry, conventions + **24 traps** each with its
incident), the lead journey as one narrative per provider, and a 24-slide / ~39-minute outline with
speaker notes, cut list and two printed handouts.

Nik's supplied facts were used as given rather than re-derived: the alert-registry port, the
projections being fired today (~564 Pipedrive rows; Smartlead limited to negative-reply and meeting
rows pending the list), and the I-04 numbers.

---

## PARTIAL

- **Stage 2's "step by step" for WF-1 and WF-2 is written from the graph and the code, not from
  observed executions.** I did not open individual runs to trace a single event end to end. For the
  130-node and 174-node workflows that is a real gap between "what the code says" and "what happens".
- **The 24 traps in doc 4 are sourced from code comments and the rulebook**, which name incidents,
  dates and execution ids. I verified the ones I could see in the current definitions; I did not
  re-verify each historical incident against execution data, most of which is outside the 20-day
  window anyway.
- **Slide numbers are estimates.** Timing was allocated by section, not rehearsed.
- **`heyreach_reply_to_dnc_ledger` was not archived** — it was not on Nik's list. It remains
  inactive under its own name, which is arguably right: it is the un-built bridge rather than dead
  code, and archiving it would make the LinkedIn gap harder to see.

## BLOCKED

Nothing. Three decisions are surfaced on slide 22 rather than assumed.

## IMPROVABLE

- **WF-2 still has three separate pieces of workflow memory** — the alert registry, the duplicate
  guard and the bounce memory — all of which have the read-modify-write loss that WF-1 was ported off
  today. WF-2's live volume is low, which is the only reason it has not bitten. The reconcilers do
  replay in batches, so it is not impossible. Worth porting for the same reason WF-1 was.
- **WF-1's two lead-selection rules still disagree** — the reply builder matches on campaign, the
  label step takes the newest non-archived lead. Flagged in Stage 1, Stage 2A and domain doc 1, still
  unverified against a real two-campaign person. One query would settle it.
- **27 of the 47 assignment-mode Set nodes do not set `includeOtherFields`**, so they silently drop
  carried context. The linter flags it; nobody has swept it.
- **Nothing watches WF-2R.** WF-2S watches WF-2H, WF-2R watches WF-2S, and the chain ends there.
- **The gate's registry read has no non-empty assertion.** A read that succeeds and returns nothing
  makes every row `CLEAN`. Its 15-minute monitor is the only thing standing between that and a fully
  open gate — that monitor is carrying more weight than its 13 nodes suggest.
- **`WF-0 - Discovery` is load-bearing and invisible** — never runs, never appears in an execution
  list, and regenerates the Pipedrive field keys both receivers depend on. It is one careless
  archive away from being lost. It is called out in three documents now; it deserves a rulebook line.

## Concurrency

Snapshots at 08:20Z, 08:50Z, 09:00Z, 09:09Z and 10:25Z. Other-session movement: WF-1 126 → 130 at
08:32Z plus two inactive `zz_*` throwaways. **No movement between 09:09Z and 10:25Z.** All logged in
Stage 1 §E; Stage 2A describes WF-1 at its current 130-node version.

## Final state

40 workflows, **20 active**, 944 nodes. Every active workflow has run in the last 20 days except
`dnc_projections_sweep`, which is active because it is being fired today.
