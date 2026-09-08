# Wave 0 — pre-fire artifact

**Date:** 2026-09-02 · **Authorised by:** Nik, this session ("GO Wave 0 … deploy today").
**Instance:** `https://janea-systems-2025.app.n8n.cloud`

Every workflow's full pre-change definition is saved under `backups/`; every post-change definition
under `patched/`. Both are byte-for-byte what was read from and sent to the API.

---

## 1. What is being changed — 12 patches across 12 workflows

| Patch | Workflow | id | Active | Change |
|---|---|---|---|---|
| **P1** | WF-2 Smartlead Receiver | `jp7rum9Z0YDJkQWv` | yes | `Body U Lead DNC Label`: label target becomes `cold + connected` (+`dnc`), never `3. Responded`; a hard strip enforces it |
| **P3a** | WF-2 Smartlead Receiver | (same PUT) | yes | CONFIG: delete dead flags `create_assignment_task`, `forward_enabled`, `dnc_auto` |
| **P2** | WF-ERR Error Handler | `BbrXPABgOaaTJjD6` | yes | CONFIG: WF-1 verdict `DELAYED` → `LOST`, retry text corrected |
| **P5** | dnc_pre_add_gate | `9aP2dP0jgAPFGDvA` | yes | queue path removed: 11 nodes deleted, `retrieve` now returns 410, zero `dnc_gate_queue` references |
| **P4** ×9 | s1, s2, s3, s3_surfe_backfill, label_reversal, s4_event_populations, wf4_sheet_intake, heyreach_reply_to_dnc_ledger, expiry_job | — | 5 yes / 4 no | `IF MODE == dev?` FALSE output wired to that workflow's own Send Guard |

**Node counts:** only the gate changes, 24 → 14. Every other workflow keeps its node count.

## 2. Why each one, in one line

- **P1** — an unsubscribe was writing `3. Responded`, the Handover trigger, so opt-outs were being
  handed to humans as warm leads. Its sibling `Body Lead Labels Union` got bounce/OOO/opt-out locks
  on 31 Aug; this node never did.
- **P2** — WF-1 answers `{"ok":true}` 200 from the Webhook node *before* processing, so HeyReach
  never retries a processing failure, and WF-1 has no reconciler. The verdict said the event would
  come back on its own. It will not.
- **P3a** — no node reads those three flags. `dnc_auto: false` would not have stopped the automatic
  unsubscribe. A switch that does nothing is worse than no switch.
- **P4** — the FALSE branch was wired to nothing, so `MODE: "live"` silenced the workflow instead of
  promoting it. Now both branches reach the Send Guard; the guard's throw-on-wrong-channel still
  only applies in dev.
- **P5** — Nik's decision: remove, do not complete. `>500` keeps its explicit 413; 51–500 is now
  answered synchronously; `retrieve` returns an explicit 410 instead of `pending` forever.

## 3. What is deliberately **not** changed

- `create_assignment_task` at the **top level of WF-1's CONFIG** — that one *is* read, by
  `M8 IF Task Enabled`. Only WF-2's dead `flags.*` copies are removed.
- `alert_every_reply` stays — it is the only flag with a real reader (`First Reply Gate`).
- `dnc_projections_sweep`'s `MODE == dev?` — its FALSE branch already goes to `Respond`.
- Every `FIRE_*` switch keeps its current value. **No projection, capture or reversal switch is
  touched by Wave 0.**
- `dnc_gate_queue_drainer` — already inactive with zero executions; no write needed, verified only.
- The `Get Registry Match (Batch)` filter uses `matchType: "anyCondition"` (OR), which I checked
  because an AND would have made the gate miss single-identifier matches. It is correct; untouched.

## 4. Rehearsal — done before any live write

A throwaway twin `DEV__dnc_pre_add_gate_wave0` was created from the patched gate JSON on webhook
path `dev-{{WEBHOOK_DNC_PRE_ADD_GATE}}-wave0`, activated, exercised, then deactivated and **deleted**.

| Contract | Payload | Result |
|---|---|---|
| the monitor's own 15-minute probe | the exact 2 rows `dnc_pre_add_gate_monitor` sends | **PASS** — `total 2, clean 1, blocked 1, unresolvable 0`, 103 ms |
| 51–500 rows answered synchronously | 60 rows (59 synthetic + 1 known-blocked) | **PASS** — `total 60, clean 59, blocked 1`, 1,905 ms, no `queued` key |
| retrieve is honest | `{"retrieve": true, …}` | **PASS** — HTTP 410, `error: retrieve_removed` |
| over-cap unchanged | 501 rows | **PASS** — HTTP 413, `error: too_many_rows` |

Twin deleted, confirmed 200.

## 5. Deploy mechanics and their hazards

- `PUT /api/v1/workflows/{id}` with **only** `name`, `nodes`, `connections`, `settings`.
- `settings` is filtered to the keys the public API accepts. Two UI-only keys are stripped on every
  write: **`timeSavedMode`** (linter `R16`; it is what made an earlier WF-1 deploy fail while WF-2's
  identical deploy succeeded) and `availableInMCP`. None of the 12 workflows in this wave carries
  `timeSavedMode` — only WF-1 does, and WF-1 is not in this wave.
- Activation state is not sent. Each PUT is followed by a **readback** asserting `active` is
  unchanged and the node count is as expected.
- Order: WF-2 first (the correctness defect), then WF-ERR, then the gate, then the nine P4 rewires.

## 6. Blast radius if a patch is wrong

| Patch | Worst case | Recovery |
|---|---|---|
| P1 | labels on unsubscribed leads are wrong in a new way | restore `backups/WF-2…json`; labels are additive so nothing was destroyed |
| P3a | a node reads a flag I did not find | WF-2 executions error loudly and reach WF-ERR; restore from backup |
| P2 | text only — no execution path touched | trivial |
| P5 | the gate stops answering → the monitor alerts within 15 min and the morning digest reports it | restore `backups/dnc_pre_add_gate…json`; rehearsal already covered all four contracts |
| P4 | a dev summary posts where it should not → the Send Guard throws rather than mis-posting | restore from backup; only 5 of the 9 are active, and 4 of those 5 have their `FIRE_*` off, so they produce reports, not writes |

**Nothing in Wave 0 changes what is written to Pipedrive, Smartlead or HeyReach except P1, which
removes one label from one path.**

## 7. Post-deploy verification (executed, results in `POSTFIRE.md`)

1. Readback of every PUT: `active` unchanged, node count as expected.
2. The gate re-probed with the monitor's exact payload against the **live** path.
3. The deployed linter re-run offline against the live estate: `R14` (Responded without engagement
   gate) must go to zero, and `R13` `dnc_gate_queue` findings must drop from 7 to 2.
4. A class-level static asserting **no node in the estate can set `3. Responded` without an
   engagement gate** — the rule Nik asked for, checked against every workflow, not just this one.
