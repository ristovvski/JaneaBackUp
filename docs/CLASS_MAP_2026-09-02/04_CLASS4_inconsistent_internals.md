# CLASS 4 — inconsistent internals

**Read-only.** Nothing changed.

**The class:** two copies of one idea, kept in step by memory. The cost is not today's behaviour —
both copies are currently correct-ish — it is that a fix applied to one is invisible to the other,
so the estate silently develops two truths.

**Method.** SHA-1 over every Code node body ≥150 chars across all 36 live workflows, exact and
normalised (comments, whitespace and module prefixes like `S1`/`M7`/`U`/`R` stripped). Data-table
references read from each node's `dataTableId` resource locator.

---

## 1. Duplicated code — 38 nodes in 10 groups

| # | Block | Copies | Where | Active? |
|---|---|---|---|---|
| 1 | **`Send Guard`** (1,225 chars) — **variant A** | 8 | DNC__UpsertLedger__v1, dnc_check_service, dnc_expiry_job ×2, **dnc_s3_creation_watcher**, dnc_wf4_sheet_intake, heyreach_reply_to_dnc_ledger, smartlead_observability_readonly | 1 active |
| 2 | **`Send Guard`** (1,225 chars) — **variant B** | 7 | **dnc_escalation_detector, dnc_label_reversal, dnc_projections_sweep, dnc_s1, dnc_s2, dnc_s3_surfe_backfill**, dnc_s4_event_populations | 6 active |
| 3 | `AR Ctx …` (7,098 chars) | 6 | WF-1, all six alert-context nodes | 6 active |
| 4 | `AR Ctx …` (7,097 chars) | 4 | WF-2, all four alert-context nodes | 4 active |
| 5 | `Lead Select` family (4,844 / 4,981) | 3 | WF-2: `B Lead Select`, `U Lead Select`, `Lead Resolve` (near-copy) | 3 active |
| 6 | `Person Pick` / `Lead Ctx` (1,134) | 3 | WF-2: `R Person Pick`, `B Lead Ctx`, `U Lead Ctx` | 3 active |
| 7 | **`Classify Batch`** (2,330) | 2 | **dnc_pre_add_gate**, dnc_gate_queue_drainer | 1 active |
| 8 | `Body SL Unsubscribe` (1,124) | 2 | WF-2: reply path + unsubscribe path | 2 active |
| 9 | `Send Guard` (259) | 2 | dnc_i04_daily_summary, dnc_i04_weekly_reconciliation | 1 active |
| 10 | `Limit Chunk` (222) | 2 | dnc_s1, dnc_s2 | 2 active |
| 11 | `Claim Bounce` / `Claim Unsub` (686 / 611) | 2 | WF-2 — near-copies | 2 active |

### 1.1 The drift has already happened

Groups 1 and 2 are both exactly 1,225 characters and differ by **one token**:

```diff
   ? JSON.parse(cfg.dev_channel_guard_list)
-  : [cfg.dev_channel_guard || 'C0B8GCVNR5W'];      // variant A — 8 workflows
+  : [cfg.dev_channel_guard || 'C0BFE6KAN8J'];      // variant B — 7 workflows
```

Two different hard-coded fallback channels for the same safety guard, split roughly down the middle
of the estate. Nobody chose this. It is what fifteen copy-pastes over six weeks produces.

Consequence: in any workflow that does **not** set `dev_channel_guard` or
`dev_channel_guard_list`, variant A permits the ops channel and variant B permits a channel
(`C0BFE6KAN8J`) that appears nowhere else in the estate except `WF-0 - Discovery`'s assembled
CONFIG. In practice every workflow does set the list, so the fallback is unreached today — which is
precisely why the divergence went unnoticed.

### 1.2 The one that is already a live correctness risk

**Group 8 — `Body SL Unsubscribe` vs `Body U SL Unsubscribe`** are byte-identical, and their
*siblings* `Body Lead Labels Union` vs `Body U Lead DNC Label` are not. The reply path grew a bounce
lock and an opt-out lock on 31 Aug; the unsubscribe path did not. See Class 3 §1.2 — that defect is
this class expressing itself.

**Group 7 — `Classify Batch`** is the gate's verdict logic, duplicated into a drainer that has never
run. If the gate's classification rules change, the drainer keeps the old ones. Since the drainer is
the thing that would answer queued batches, the two answers would eventually disagree about the same
person.

**Group 5 — three lead-selection implementations in one workflow.** `Lead Resolve` (4,981) is a
near-copy of `B Lead Select` / `U Lead Select` (4,844, identical to each other). WF-1 has the same
problem in a sharper form: `M7 Build` selects the lead by **campaign field match**, and
`M7 Labels Compute` twenty nodes later selects the **newest non-archived** lead. Under
one-lead-per-campaign those are different rules and can pick different leads, so the activity and
the labels can land on different records. *(Flagged in the Stage 1 questions; it belongs here as a
class instance, not an isolated bug.)*

### 1.3 Where this is already solved, and should be copied

Two blocks in the estate are **generated into the workflow from a single source file** by a build
script, and the same file is what the tests import. Both say so in their own header:

- `AR Decide` / the two standing rules — *"Embedded verbatim into both WF-1 and WF-2 by
  build_rules.py and required directly by the statics, so there is one implementation."*
- `dnc_wf_linter / Lint` — *"ONE source of truth: this exact text is embedded … by build_linter.py,
  and required directly by the statics. There is no second implementation."*

Groups 3 and 4 (`AR Ctx …`, ten copies) are that mechanism working as designed: ten identical
copies with one upstream source. **They are not the problem — they are the answer applied.**

The problem is groups 1, 2, 5, 7, 8, 10, 11, which have no source file.

---

## 2. Data tables — 30 references by name, 7 on ACTIVE workflows

The deployed linter's `R13` exists because `mode:"name"` has failed live on tables that certainly
existed. Current state:

### 2.1 By NAME (unsafe)

| Table | Workflow | Nodes | Active? |
|---|---|---|---|
| `dnc_gate_queue` | **dnc_pre_add_gate** | Lookup Queue By Key, Check Queue Depth, Log Ingress, Enqueue Rows, Mark Sync Done | **ACTIVE ×5** |
| `dnc_gate_queue` | dnc_gate_queue_drainer | Fetch Pending Batch, Write Back Results | inactive ×2 |
| `i04_snapshots` | **dnc_i04_daily_summary** | Load Watermark Row, Save Watermark | **ACTIVE ×2** |
| `i04_snapshots` | dnc_i04_weekly_reconciliation | 10 nodes | inactive |
| `i04_walk_staging` | dnc_i04_weekly_reconciliation | 3 nodes | inactive |
| `obs_state` | smartlead_observability_readonly | 6 nodes | inactive |
| `obs_state` | dnc_expiry_job | 2 nodes | inactive |

### 2.2 By ID (safe)

| Table | Id | Used by |
|---|---|---|
| DNC registry | `UOgKwlGsL28lX61O` | UpsertLedger, CheckLedger, the gate, projections, escalation, expiry, label reversal, s4_retirement, morning digest |
| I-04 events | `zAW2IYoO6Dj0vdIt` | i04 event receiver, i04 daily summary |
| WF-1 dedupe claims | `euyostwJYfJefItC` | WF-1 |

**The pattern is not random.** Every table that was created early and is central is referenced by
id; every table added later is referenced by name. And the one table referenced by name from an
ACTIVE workflow five times over — `dnc_gate_queue` — is the one the gate monitor says does not
exist. Whether it is absent or merely unresolvable by name, the estate cannot currently tell the
difference, which is exactly why `R13` is a rule.

*I could not verify table existence: `GET /api/v1/data-tables` returns 404 and `/api/v1/projects`
returns 403. The ids above must come from each table's UI URL.*

---

## 3. Two more inconsistencies worth folding into the same wave

### 3.1 Error-handling policy is inconsistent in a way that does not track importance

Across the estate: 787 nodes default (stop the run), 82 `continueRegularOutput`, 51
`continueErrorOutput`, 6 `stopWorkflow`.

Within **one workflow** (WF-2), the Pipedrive core stops the run on failure while the Smartlead
calls and `SL Forward Email` continue silently. Nothing in the code explains the split, and
"forward an interested reply to a salesperson" is in the silent group. See Class 3 §3.2.

### 3.2 CONFIG shape is split two ways

`mode: "raw"` with a JSON blob — WF-1, WF-2, WF-2S, WF-2R, WF-2H, WF-ERR, morning digest, linter.
Assignment list — the whole DNC family.

Both work. The raw form is materially better for large configs and is what the newer workflows use.
Worth stating as the standard so the next one does not flip a coin. Low priority.

---

## 4. Proposal

### 4.1 One source file per shared block, embedded by build script

Extend the mechanism that already exists (`build_rules.py`, `build_linter.py`) rather than invent
one. Priority order, highest drift-risk first:

| Block | Source file | Consumers | Why first |
|---|---|---|---|
| **Send Guard** | `shared/send_guard.js` | 17 nodes / 15 workflows | already diverged (§1.1), and it is a safety guard |
| **Lead selection** | `shared/lead_select.js` | WF-2 ×3, WF-1 ×2 | already causing a suspected live mismatch (§1.2) |
| **Label target set** | `shared/label_target.js` | WF-2 `Body Lead Labels Union` + `Body U Lead DNC Label` | the Class 3 §1.2 defect is exactly this block being copied without its locks |
| **Classify Batch** | `shared/gate_classify.js` | gate + drainer | only worth doing if the queue path survives (Class 3 §2.1) |
| **Identity normaliser** | `shared/normalize_identity.js` | UpsertLedger, CheckLedger, the gate — and `DNC__NormalizeIdentity__v1`, the unused fourth copy | four copies of the thing that decides who a person *is* |
| **Person pick / Lead ctx** | `shared/person_pick.js` | WF-2 ×3 | mechanical |
| **Limit Chunk** | `shared/limit_chunk.js` | S1, S2 | trivial, do it while you are there |

Add a linter rule (`R18`): **two Code nodes with identical normalised bodies in different
workflows, where neither carries an "embedded by <script>" header, is a finding.** That makes the
class self-policing — which is the only reason the `AR Ctx` groups are not a problem today.

### 4.2 Data tables: convert all seven active-workflow name references to ids

Requires the ids from the UI. Do the two `i04_snapshots` references in `dnc_i04_daily_summary`
first — that is a live daily job whose watermark read is already flagged `R04`. The five
`dnc_gate_queue` references resolve themselves if the queue path is removed (Class 3 §2.1(a)); if
it is kept, they must be converted *and* the table created before the drainer is activated.

### 4.3 Write down the error-handling policy

Three tiers, applied deliberately per node rather than inherited:

- **Stop the run** — anything whose failure makes the rest of the execution wrong (Pipedrive person
  / lead creation, the registry upsert). Already the default; keep it.
- **Continue and count** — anything recoverable by a later cycle, *provided* the error is counted
  and reported (the WF-2S `Summary` pattern).
- **Continue and ignore** — Slack posts only, and only because a failed post must never take down a
  CRM write.

`SL Forward Email`, `SL Category`, `SL Unsubscribe`, `Reply Activity` and `Bounce Note` are
currently in tier 3 and belong in tier 2.
