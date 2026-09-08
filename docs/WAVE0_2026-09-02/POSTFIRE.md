# Wave 0 — post-fire verification

**Deployed 2026-09-02.** 13 PUTs, all HTTP 200, all read back. No workflow changed activation state.
Pre-change definitions are in `backups/`, post-change in `patched/`.

---

## 1. What landed

| # | Workflow | id | New versionId | Nodes | Active |
|---|---|---|---|---|---|
| 1 | WF-2 Smartlead Receiver (P1 + P3a) | `jp7rum9Z0YDJkQWv` | `fb2e2ac3` | 174 → 174 | yes |
| 2 | WF-ERR Error Handler (P2) | `BbrXPABgOaaTJjD6` | `392238c5` | 12 → 12 | yes |
| 3 | dnc_pre_add_gate (P5) | `9aP2dP0jgAPFGDvA` | `fe1e4b57` | **24 → 14** | yes |
| 4 | dnc_s1_responded_to_dnc (P4) | `BxJZmz1HY5AdaQqE` | `1de24040` | 17 | yes |
| 5 | dnc_s2_meeting_to_dnc (P4) | `E0oTTvHHQ0hVTNDD` | `be4c2cef` | 17 | yes |
| 6 | dnc_s3_creation_watcher (P4) | `QM21Vd7VId7PBdqh` | `a5d54767` | 23 | yes |
| 7 | dnc_s3_surfe_backfill (P4) | `1fpep0U4XC8KNzta` | `0acebf15` | 18 | yes |
| 8 | dnc_label_reversal (P4) | `LQRfmEl4Wv0qpXsI` | `94208262` | 20 | yes |
| 9 | dnc_s4_event_populations (P4) | `hhdnug5xdFLAxrOg` | `a843d0c4` | 24 | no |
| 10 | dnc_wf4_sheet_intake (P4) | `bluGflKaUI3bGodQ` | `ad2918f7` | 16 | no |
| 11 | heyreach_reply_to_dnc_ledger (P4) | `YgufwSg1EAJaT0ra` | `5c865064` | 7 | no |
| 12 | dnc_expiry_job (P4) | `alpy9rsunqnFwQml` | `eda05d57` | 17 | no |
| 13 | dnc_wf_linter (rule update) | `fziGeigC48aGTLT8` | `e4e774d6` | 8 | yes |

`availableInMCP` was stripped from every payload (the public PUT API rejects unknown settings keys).
`timeSavedMode` does not appear on any workflow in this wave — only WF-1 carries it, and WF-1 was
not touched.

## 2. Verification results

### 2.1 The gate, probed live after deploy

| Check | Result |
|---|---|
| `dnc_pre_add_gate_monitor`'s exact 15-minute payload | **PASS** — `total 2, clean 1, blocked 1, unresolvable 0`, 182 ms |
| `{"retrieve": true, …}` | **PASS** — HTTP **410**, `error: retrieve_removed` |
| 60 rows (rehearsal, on the twin) | **PASS** — answered synchronously, `total 60, clean 59, blocked 1`, 1.9 s |
| 501 rows (rehearsal, on the twin) | **PASS** — HTTP **413**, `error: too_many_rows` |

The monitor's health contract is unchanged, so the 15-minute watchdog keeps working with no edit.

### 2.2 Estate lint, before vs after

Ran the **deployed** rule engine offline against the live definitions, before and after.

|  | before | after |
|---|---|---|
| findings | 195 | **185** |
| high | 45 | **39** |
| on ACTIVE workflows | 109 | **99** |
| `R14` responded-without-engagement-gate | 1 | **0** |
| `R13` `dnc_gate_queue` by name | 7 | **2** (both in the inactive drainer) |
| **new findings introduced** | — | **0** |

Nine findings resolved, all in `dnc_pre_add_gate`: four `R13` high (`Lookup Queue By Key`,
`Check Queue Depth`, `Log Ingress`, `Enqueue Rows`, `Mark Sync Done`), plus `R04`/`R05` on
`Build Retrieve Report`, `Decide Sync Or Queue` and `Build Queue Response`.

### 2.3 The class-level static Nik asked for

New file: **`WF_LINTER/static_responded_class.js`**. Not an instance test — it enumerates every node
in the estate that can put the label into a write and requires each one to justify itself:
`OK/gated` (consults bounce / OOO / opt-out / reply-class / stage-rank), `OK/stripped` (provably
cannot emit it), or `VIOLATION`.

```
BEFORE          scanned 36 workflows, 6 label writers
  A VIOLATION   WF-2 Smartlead Receiver    Body U Lead DNC Label     no engagement gate and no strip
  A OK/gated    WF-1 HeyReach Receiver     M5 Labels Compute         gated on stage rank
  A OK/gated    WF-1 HeyReach Receiver     M7 Labels Compute         gated on stage rank
  A OK/stripped WF-2 Smartlead Receiver    Body Lead Labels Union    cannot emit the label
  FAIL - 1 violation

AFTER           scanned 36 workflows, 6 label writers
  A OK/gated    WF-1 HeyReach Receiver     M5 Labels Compute         gated on stage rank
  A OK/gated    WF-1 HeyReach Receiver     M7 Labels Compute         gated on stage rank
  A OK/stripped WF-2 Smartlead Receiver    Body Lead Labels Union    cannot emit the label
  A OK/stripped WF-2 Smartlead Receiver    Body U Lead DNC Label     cannot emit the label
  PASS - invariant holds
```

### 2.4 A gap found in the detector itself — worth more than the fix it was checking

The first version of the static, and **the deployed `R14` rule it was modelled on**, both used
`/label_ids\s*:/ || /target\.push/ || /__body/` to decide whether a node writes labels. That test
**cannot see `M7 Labels Compute` in WF-1** — a live, active writer that emits the label through the
shorthand property `label_ids,` and `targetSet.push(...)`.

So the rule that exists to protect the Handover trigger was blind to one of the four real writers of
that label, and had been since it was written. `M7 Labels Compute` happens to be correctly gated on
stage rank, so nothing was broken by it — but the rule was reporting a clean estate it had not
actually checked, which is the same class of defect the rule polices.

Both were widened to match the *construction* rather than one spelling of it:
`/label_ids\s*[:,=]/ || /[Tt]arget[A-Za-z_$]*\.push\(/`. `__body` alone was dropped — it was
matching the linter's own rule text.

`R14` also learned that a node which **strips** the label from its own target set is stronger than a
gated one and needs no gate. Without that, the unsubscribe fix would have left a permanent high
finding for having done the safer thing.

`WF_LINTER/lint_rules.js` and the deployed `dnc_wf_linter` Code node were both rebuilt from the same
source via `build_linter.py`, so they cannot drift. **The 46 existing statics still pass.**

## 3. What changed in behaviour, precisely

| Change | Before | After |
|---|---|---|
| A Smartlead unsubscribe | lead labelled `cold + connected + 3. Responded + DNC` → **Handover fired on an opt-out** | lead labelled `cold + connected + DNC`. Labels already earned are untouched. |
| A WF-1 processing failure | WF-ERR said *"DELAYED — the event should come back on its own"* | WF-ERR says *"LOST — no reconciler covers HeyReach … repair by hand from the HeyReach inbox"*, and explains that the 200-before-processing response means HeyReach never retries |
| `dnc_auto` / `forward_enabled` / `create_assignment_task` in WF-2 | present in CONFIG, read by nothing | gone, with a `_flags_note` recording why |
| `MODE: "live"` in 9 workflows | silenced the summary entirely | routes it to the same Send Guard → the summary posts |
| Gate, 51–500 rows | `{"queued": N, "eta_minutes": …}` and no answer, ever | a real synchronous verdict per row |
| Gate, `retrieve` | `retrieve_status: "pending"` forever | HTTP 410 `retrieve_removed` with instructions |
| Gate, >500 rows | HTTP 413 `too_many_rows` | unchanged |

## 4. Not done, deliberately

- **`SYSTEM_DOCS_2026-09-02/10_DOMAIN_heyreach…md` §6** still repeats the old retry advice.
  Corrected in the same pass — see that file's §6, now marked with the 2026-09-02 change.
- `dnc_gate_queue_drainer` was **not** written to. It is already inactive with zero executions;
  `active: false` was verified by read, not set. Its two `dnc_gate_queue` references remain, which
  is why `R13` still shows 2 — deactivating it further or deleting it needs your word.
- No `FIRE_*` switch was touched. No projection was enabled.

## 5. Rollback

Each workflow's exact pre-change definition is in `backups/<name>__<id>.json`. To roll one back:
PUT that file's `name`/`nodes`/`connections`/`settings` back to the same id, stripping
`availableInMCP` and `timeSavedMode` from `settings` first.
