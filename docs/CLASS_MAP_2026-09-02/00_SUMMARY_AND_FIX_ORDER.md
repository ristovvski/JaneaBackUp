# Class-level map — summary and fix order

**Read 2026-09-02 from the live n8n instance** (`GET /api/v1/workflows`, `GET /api/v1/executions`).
Definitions were re-fetched at the start of this pass: **no `versionId` changed** since the morning
inventory, so this map and `SYSTEM_DOCS_2026-09-02/` describe the same estate.

**Nothing was deployed, activated, deactivated, written or posted. No Slack message of any kind.**
Everything below is a proposal awaiting your approval.

| File | Class |
|---|---|
| [01_CLASS1_switch_without_effect_verification.md](01_CLASS1_switch_without_effect_verification.md) | the switch is off and nothing knows it |
| [02_CLASS2_built_never_invoked.md](02_CLASS2_built_never_invoked.md) | built, never invoked |
| [03_CLASS3_confident_and_false.md](03_CLASS3_confident_and_false.md) | the answer is confident and false |
| [04_CLASS4_inconsistent_internals.md](04_CLASS4_inconsistent_internals.md) | inconsistent internals |

---

## What the map found

| Class | Instances | Worst instance |
|---|---|---|
| **1 — switch without effect verification** | **19 switches.** 1 has a switch-state check, 3 paths have a genuine effect check, **15 have nothing**. 3 switches in WF-2 are read by no node at all. 8 `MODE == dev?` gates have an empty FALSE branch. `projections_state` is written on every registry row and read by one workflow that never runs. | `dnc_auto`, `forward_enabled`, `create_assignment_task` in WF-2 — **flipping them changes nothing**, and the CONFIG reads as if it would |
| **2 — built, never invoked** | 4 sub-workflows (2 with zero callers ever), 2 ACTIVE webhooks with 0 runs, 3 inactive workflows with real triggers nobody enabled, 8 dead branches, 1 unreachable node | `heyreach_reply_to_dnc_ledger` — the reason LinkedIn replies never reach the DNC registry, 0 callers, one edge away from working |
| **3 — confident and false** | 2 severe + 10 traced instances across 3 shapes; the deployed linter's own rules produce 195 findings, 45 high, 109 on ACTIVE workflows (I triaged out 5 false-positive groups) | **an unsubscribe stamps "3. Responded"** on the lead — the handover trigger — because the unsubscribe path never got the locks the reply path got on 31 Aug |
| **4 — inconsistent internals** | 38 nodes in 10 duplicate groups; 30 data-table references by name (7 on ACTIVE workflows); error-handling policy split with no rule behind it | the `Send Guard`, copied 15 times, **has already diverged** into two variants with different hard-coded fallback channels |

---

## Two findings that were not on your list and outrank most of what was

### A. WF-ERR tells the operator a lost HeyReach event will come back on its own. It will not.

WF-1's live wiring is `Webhook → Respond to Webhook ({"ok": true}, 200) → CONFIG → everything`.
HeyReach is told the event was accepted **before any processing runs**, so it never retries a
processing failure — and WF-1 has no reconciler. WF-2 has byte-identical wiring and its own WF-ERR
entry says so correctly (*"answers 200 before processing, so Smartlead will NOT retry"*). WF-1's
says the opposite.

The verdict is read at the exact moment someone decides whether to repair by hand. It is currently
`DELAYED`; the truth is `LOST`.
→ Class 3 §1.1. *(This also makes §6 of `SYSTEM_DOCS_2026-09-02/10_DOMAIN_heyreach…md` wrong — I
took that line from WF-ERR. It is on the fix list rather than patched, per your instruction.)*

### B. An unsubscribe marks the lead "3. Responded"

`Body Lead Labels Union` (reply path) has a bounce lock and an opt-out lock, both added 31 Aug.
`Body U Lead DNC Label` (unsubscribe path) has neither and writes `cold + connected + responded`
unconditionally. The deployed linter flags it high (`R14`) on an ACTIVE workflow. We are handing
opt-outs to humans as warm leads.
→ Class 3 §1.2. This is Class 4 expressing itself: two copies of one idea, one of which got fixed.

---

## The single insight across all four classes

Every class is the same failure at a different altitude:

> **We check the thing we control instead of the thing we care about.**

- Class 1 checks the switch, not the write.
- Class 2 checks that a workflow exists, not that anything calls it.
- Class 3 checks that we reached a node, not that the provider accepted it.
- Class 4 checks that a block is correct here, not that it is the same block everywhere.

So the fixes below are ordered by **how much of the class each one retires**, not by how bad the
individual instance is.

---

## Fix order

### Wave 0 — correctness defects, no dependencies, do these regardless of what you decide about the rest

| # | Fix | Class | Size | Why now |
|---|---|---|---|---|
| 0.1 | Unsubscribe path: `cold + dnc` only — copy the bounce/opt-out locks from `Body Lead Labels Union` | 3 §1.2 | one node | live CRM defect, opt-outs being handed over as warm leads |
| 0.2 | WF-ERR: WF-1 verdict → `LOST — no reconciler covers HeyReach` | 3 §1.1 | one CONFIG string | wrong guidance at the decision moment |
| 0.3 | Wire `dnc_i04_daily_summary / Alert Post Failed` — it has no inbound edge | 3 §4.3 | one connection | an alarm that cannot fire |

### Wave 1 — measure before you change anything else

| # | Fix | Class | Why here |
|---|---|---|---|
| 1.1 | Build `dnc_intent_vs_reality` — sample 50 registry rows/day, assert the consequence in Pipedrive / Smartlead / HeyReach, and compare against the row's own `projections_state` claim | 1 §4.2 | this is the single "effect verification" you asked for. It also **sizes** the projection backlog before anyone touches a switch |
| 1.2 | Add the "switches holding work back" block to the morning digest — one line per off switch, with its backlog count | 1 §4.3a | makes every off switch visible daily; costs nothing; no behaviour change |
| 1.3 | Activate `dnc_check_service` (Slack `@mention` → DNC status) | 2 §2d | read-only, zero risk, and it takes you out of the loop for lookups |

**Stop here and read a week of output before Wave 2.** Wave 1 is the only part that is safe to do
without knowing the numbers.

### Wave 2 — close the false answers

| # | Fix | Class |
|---|---|---|
| 2.1 | Gate: **remove** the queue path — cap at 50, return the honest over-cap error above it *(recommended)*; or complete it properly with a real table, `mode:"id"`, an active drainer and a monitor assertion | 3 §2.1 |
| 2.2 | `Mark DNC`: derive `__dnc_label` from the unsubscribe response instead of asserting it | 3 §3.1 |
| 2.3 | Outcome counting in `dnc_s4_retirement_removal` and `dnc_archived_responders_import` — `{written, failed, conflicts, skipped}`, note derived from `failed === 0` | 3 §3.3 |
| 2.4 | Three-state reads (`true` / `false` / `unavailable`) starting with the gate's registry read, the digest's DNC block, and `retrieve_status` | 3 §2.2, §4.1 |
| 2.5 | Move `SL Forward Email`, `SL Category`, `SL Unsubscribe`, `Reply Activity`, `Bounce Note` from "continue and ignore" to "continue and count" | 3 §3.2, 4 §4.3 |

### Wave 3 — consolidate, so Wave 0.1 cannot happen again

| # | Fix | Class |
|---|---|---|
| 3.1 | `shared/send_guard.js` embedded by build script → 17 nodes; **resolves the existing A/B divergence** | 4 §4.1 |
| 3.2 | `shared/label_target.js` → the two label builders. This is the block that produced defect B | 4 §4.1 |
| 3.3 | `shared/lead_select.js` → WF-2 ×3 and WF-1 ×2, which also settles the WF-1 campaign-match vs newest-lead mismatch | 4 §1.2 |
| 3.4 | `shared/normalize_identity.js` → the four copies of the thing that decides who a person is | 4 §4.1 |
| 3.5 | Convert the 7 active-workflow data-table name references to ids (`i04_snapshots` first) | 4 §4.2 |
| 3.6 | New linter rules: `R17` (a `continueRegularOutput` node whose downstream never tests `.error`), `R18` (identical normalised Code bodies across workflows with no "embedded by" header) | 3 §5, 4 §4.1 |

### Wave 4 — wire what is missing, in dependency order

| # | Fix | Class | Gate |
|---|---|---|---|
| 4.1 | Schedule `dnc_projections_sweep`, **Pipedrive leg only**, small chunks | 1, 2 | needs Wave 1.1 numbers |
| 4.2 | S1/S2 feeder — a scheduled list producer, then `FIRE_S1` / `FIRE_S2` | 2 §2a | needs your ruling on the population definition |
| 4.3 | Wire `heyreach_reply_to_dnc_ledger` into WF-1's reply branch behind its own switch | 2 §2a | needs your ruling on which `reason` a LinkedIn reply earns |
| 4.4 | `dnc_projections_sweep` Smartlead leg | 1, 2 | **last — irreversible.** A Smartlead unsubscribe cannot be undone via the API |
| 4.5 | Wire or retire `dnc_i04_weekly_reconciliation` | 2 §2d | after 3.5 — it holds 13 name-referenced table nodes |

### Housekeeping (no deletions, your word required for each)

- Rename `smartlead_observability_readonly` with an `OBSOLETE__` prefix — never configured, its
  `campaign_id` is still the literal placeholder.
- Exclude `WF-1-DO NOT USE` from the linter — it contributes 34 of the 195 findings as duplicates.
- Either wire or remove WF-2's three no-op flags (`dnc_auto`, `forward_enabled`,
  `create_assignment_task`).
- Adopt a naming convention for "ACTIVE but hand-fired" so those stop reading as anomalies.

---

## Decisions I need from you before Wave 2 or later can start

1. **Gate queue: remove or complete?** I recommend remove.
2. **Should WF-1 respond *after* processing** so HeyReach's retry becomes real? Costs latency,
   gains a free reconciler. The 48-hour dedupe already covers duplicate delivery.
3. **Which registry `reason` does a LinkedIn reply earn** — `reply_dnc`, or something weaker?
4. **How are the S1/S2 populations defined** for a scheduled feeder — the label/stage query as
   written in the docs, or something narrower?
5. **Projections: Pipedrive-only first, or both legs together?** I strongly recommend Pipedrive
   first and Smartlead separately, weeks apart.

## Caveats on the evidence

- **Data tables are not exposed by the n8n public API** (`/api/v1/data-tables` → 404,
  `/api/v1/projects` → 403). Every claim about `dnc_gate_queue` not existing rests on a code comment
  in `dnc_pre_add_gate_monitor` dated 2026-08-31 plus the drainer's zero executions. Confirm in the
  UI before acting on Wave 2.1.
- **Execution history is a rolling ~19 days** (oldest anywhere: 2026-08-14T01:15Z). "0 runs" means
  "not since 14 Aug".
- The 195 linter findings come from running the **deployed** rule code offline against the live
  definitions. I traced and triaged them rather than passing them through; the five discarded groups
  are named in Class 3 §4.2.
