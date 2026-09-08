# 2026-09-02 — class-level map (4 classes)

**Task:** map every instance of four recurring defect classes across the live n8n estate. Read-only,
no Slack of any kind, output to markdown files only, no patching of individual findings.

**Access:** `GET /api/v1/workflows` (re-fetched at start — no `versionId` changed since the morning
inventory) and `GET /api/v1/executions`. Zero write calls issued (verified: every script uses
`requests.get` only). No Slack tool was invoked in this pass.

**Output:** `CLASS_MAP_2026-09-02/` — summary + one file per class (63.6 KB).

---

## DONE

- **Class 1** — all 19 switches enumerated (what each gates, live value, verification status), built
  from CONFIG extraction + reader search + graph traversal of each gate's true/false targets.
  Proposed one effect verification (`dnc_intent_vs_reality`) plus a digest backlog line.
- **Class 2** — full call graph: `executeWorkflow` edges, webhook paths cross-referenced against all
  node parameters, schedules, other triggers, unreachable nodes. Every workflow classified
  (a) needed / (b) obsolete / (c) hand-fired by design / (d) inactive-with-a-real-trigger.
- **Class 3** — three shapes (success without effect / empty read as fact / queued with no
  processor), 12 traced instances, plus the deployed linter's rule code run offline against the live
  definitions (195 findings, 45 high, 109 active) and triaged.
- **Class 4** — SHA-1 duplicate detection over all Code nodes (exact + normalised): 38 nodes in 10
  groups. Data-table reference audit: 30 by name, 7 on active workflows.
- Fix order in four waves with explicit dependencies and five decisions needed from the owner.

### New findings (not in the earlier documentation pass)

1. **WF-ERR's WF-1 recovery verdict is false.** WF-1 wiring is
   `Webhook → Respond to Webhook ({"ok":true}, 200) → CONFIG → …`, identical to WF-2. HeyReach is
   told 200 before processing, so it never retries a processing failure, and WF-1 has no
   reconciler. The verdict says `DELAYED — the event should come back on its own`; the truth is
   `LOST`. WF-2's own entry states the same structural fact correctly.
2. **An unsubscribe writes "3. Responded".** `Body U Lead DNC Label` sets
   `cold + connected + responded` unconditionally; its sibling `Body Lead Labels Union` grew a
   bounce lock and an opt-out lock on 31 Aug and the unsubscribe path did not. Linter `R14` high,
   ACTIVE.
3. **Three WF-2 switches are read by no node:** `flags.dnc_auto`, `flags.forward_enabled`,
   `flags.create_assignment_task`. Flipping `dnc_auto` would not stop the automatic unsubscribe.
4. **Eight `IF MODE == dev?` nodes have an empty FALSE branch** — setting `MODE: "live"` silences
   those workflows entirely rather than routing output to production.
5. **The `Send Guard` has already diverged**: two byte-length-identical variants differing only in
   the hard-coded fallback channel (`C0B8GCVNR5W` in 8 workflows, `C0BFE6KAN8J` in 7).
6. **`projections_state` is a write-only column** — written on every registry row, read only by the
   workflow that never runs. No surface reports the backlog.
7. **`dnc_i04_daily_summary / Alert Post Failed` has no inbound edge** — the only orphan node in the
   estate; the alarm for a failed daily post can never fire.
8. **`dnc_s4_retirement_removal` and `dnc_archived_responders_import` report "WRITTEN"** from item
   counts regardless of write outcome; the latter also counts ledger `conflict` results as
   processed and computes `conflicts_declined` from a Slack-response shape.

---

## PARTIAL

- **Data-table existence still unverifiable.** `/api/v1/data-tables` → 404, `/api/v1/projects` →
  403. The `dnc_gate_queue` absence rests on a code comment plus the drainer's zero executions.
  Flagged in three places; Wave 2.1 is blocked on a UI check.
- **Linter findings triaged by sampling, not exhaustively.** I traced the high-severity findings and
  the active-workflow R04/R05 set; the 44 medium `R02` fan-in findings were not individually
  verified against the graph (the rule's own mutual-exclusion filter is doing that work).
- **The WF-1 lead-selection mismatch** (`M7 Build` campaign-match vs `M7 Labels Compute`
  newest-lead) is recorded as a Class 4 instance but still not confirmed against a real execution
  where one person has leads in two campaigns.
- **Existing docs not corrected.** `SYSTEM_DOCS_2026-09-02/10_DOMAIN_heyreach…md` §6 repeats WF-ERR's
  false retry verdict. Left in place deliberately — the instruction was to map, not patch. It is
  Wave 0.2's companion edit.

## BLOCKED

- Nothing blocked the map. Five decisions are needed before Wave 2 and later can start; they are
  listed at the end of `00_SUMMARY_AND_FIX_ORDER.md`.

## IMPROVABLE

- **`R17` and `R18` are the highest-value additions to the linter** (`continueRegularOutput` with no
  downstream `.error` test; identical normalised Code bodies across workflows with no "embedded by"
  header). Both are mechanical and would make Classes 3 and 4 self-policing.
- **WF-ERR's verdict table should be derived, not hand-maintained.** Whether a workflow responds
  before processing, and whether a reconciler covers an event type, are both computable from the
  graph. Finding 1 existed because a human wrote the verdict once and the wiring outlived it.
- **The gate monitor is carrying more weight than anyone realises**: its 1-clean/1-blocked assertion
  is the only thing that would catch a registry read returning empty and making every row `CLEAN`.
  Worth stating explicitly in the runbook.

## Working files (scratchpad, not in the project)

`c1_switches.py`, `c1b.py`, `c2_callers.py`, `deployed_lint.js`, `runlint.js`, `lint_live.json`
(195 findings), plus the earlier `workflows_raw.json` / `execs_raw.json` / `exec_summary.json` /
`digest.txt` / `code/`.
