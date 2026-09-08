# CLASS 1 — "the switch is off and nothing knows it"

**Read-only.** Live definitions re-fetched 2026-09-02; no `versionId` changed since the morning read.
**Nothing was changed, deployed or posted.**

**The class, stated once:** a boolean decides whether an effect happens, and the only thing anyone
ever checks is *the boolean*. Nobody checks the effect. So a switch left off, a switch nothing
reads, and a switch whose branch goes nowhere are all indistinguishable from a healthy system.

---

## 1. Every switch in the estate

Compiled by extracting each workflow's `CONFIG` node and finding every node whose parameters
reference the key. "Gates" is what the switch actually decides, read from the graph — not from the
switch's name.

### 1.1 Write switches — they decide whether an outside system is touched

| # | Workflow | Switch | Live value | What it gates (true → false) | Anything verify the effect? |
|---|---|---|---|---|---|
| 1 | WF-2 Smartlead Receiver | `WRITE_MODE` | `"live"` | **14 gates**: Org Create, Person Patch, Person Create, Lead Create, Nurture Alert, Reply Alert, SL Category, SL Unsubscribe, SL Forward Email, Lead Labels Union, Reply Activity, Bounce Note, U SL Unsubscribe, U Lead DNC Label → each falls to a `Skip …` node | **Switch-state only.** WF-2S reads WF-2's *definition* and asserts `WRITE_MODE === "live"`. It never checks that a write landed. |
| 2 | dnc_projections_sweep | `FIRE_PIPEDRIVE` | **`false`** | `PD Split Rows` (person DNC field + lead label) → skips straight to the Smartlead leg | **None** |
| 3 | dnc_projections_sweep | `FIRE_SMARTLEAD` | **`false`** | `SL Split Rows` (Smartlead unsubscribe) → skips to the HeyReach counter | **None** |
| 4 | dnc_s1_responded_to_dnc | `FIRE_S1` | **`false`** | `S1 Call UpsertLedger` → `S1 Write Barrier` | **None** |
| 5 | dnc_s2_meeting_to_dnc | `FIRE_S2` | **`false`** | `S2 Call UpsertLedger` → `S2 Write Barrier` | **None** |
| 6 | dnc_s3_creation_watcher | `FIRE_S3` | **`true`** | `S3 Call UpsertLedger` → `S3 Write Barrier` | Indirect only — the registry count in the morning digest |
| 7 | dnc_s3_surfe_backfill | `FIRE_S3_BACKFILL` | **`false`** | `S3B Call UpsertLedger` → `S3B Write Barrier` | **None** |
| 8 | dnc_s4_event_populations *(inactive)* | `FIRE_S4` | **`false`** | `S4 Call UpsertLedger` → `S4 Write Barrier` | **None** |
| 9 | dnc_label_reversal | `FIRE_REVERSAL` | **`false`** | `R Patch Lead Labels` → `R To-Strip (dry-run)` | **None** |
| 10 | WF-1 HeyReach Receiver | `create_assignment_task` | **`false`** | `M8 Task` (Pipedrive follow-up task) → nothing | n/a — deliberately owned elsewhere |
| 11 | dnc_s4_retirement_removal | `dry_run` *(request body, default `true`)* | caller-supplied | `Update Row` on the registry → `Report Dry Run` | **None** — and see Class 3 §2.3 |
| 12 | dnc_archived_responders_import | `dry_run` *(request body, default `true`)* | caller-supplied | `Call UpsertLedger` → `Report Dry Run` | **None** — and see Class 3 §2.4 |

### 1.2 Behaviour switches — they change what happens, not whether it happens

| # | Workflow | Switch | Live value | What it gates | Verified? |
|---|---|---|---|---|---|
| 13 | WF-2 | `classify_enabled` | `true` | `IF Classify Enabled` → `LLM Classify` vs `Classify Skipped` | no |
| 14 | WF-2 | `forward_on_uncategorized` | `true` | a low-confidence reply is forwarded to review instead of dropped | no |
| 15 | WF-2 | `sheets.enabled` | `false` | the Google-Sheets inbox→owner map. `forward_map_source: "config"`, so the inline map is authoritative | no |
| 16 | WF-2 | `flags.alert_every_reply` | `false` | read by `First Reply Gate` — first-reply-only announcements | no |
| 17 | WF-2S / WF-2R | `campaign_allowlist` | `[]` | empty = every campaign is in scope | no |
| 18 | WF-2S | `write_mode_expected` | `"live"` | the value WF-2's `WRITE_MODE` is compared against | this *is* the check — see §3 |
| 19 | dnc_wf_linter | `active_only` | `false` | lint inactive workflows too | no |

### 1.3 The channel guard — 13 workflows

`MODE` is `"dev"` in: dnc_escalation_detector, dnc_i04_daily_summary, dnc_label_reversal,
dnc_projections_sweep, dnc_s1, dnc_s2, dnc_s3, dnc_s3_surfe_backfill, DNC__UpsertLedger__v1,
dnc_check_service, dnc_expiry_job, dnc_i04_weekly_reconciliation, dnc_s4_event_populations,
dnc_wf4_sheet_intake, heyreach_reply_to_dnc_ledger, smartlead_observability_readonly.
`MODE` is `"live"` in dnc_morning_digest only.

It gates the shared `Send Guard`, which **throws** if the target channel is not on the allow-list.

---

## 2. Three findings that fall out of the table

### 2.1 Three switches in WF-2 that control nothing at all

`flags.create_assignment_task`, `flags.forward_enabled`, `flags.dnc_auto` — **no node in the
workflow reads any of them.** I searched every node's parameters for each key name; zero hits.

The consequence worth saying out loud: **setting `dnc_auto: false` would not stop the automatic
unsubscribe**, and setting `forward_enabled: false` would not stop forwarding. The only thing
actually gating those paths is `WRITE_MODE`. Anyone who believes they can switch off auto-DNC
without a redeploy is wrong, and the CONFIG says otherwise in a way that reads as authoritative.

*(`flags.alert_every_reply` **is** read, by `First Reply Gate`. The `flags` object as a whole is
referenced by four nodes, which is why a naive grep would say these are all live. They are not.)*

### 2.2 Eight `MODE == dev?` gates have an empty FALSE branch

In dnc_s1, dnc_s2, dnc_s3, dnc_s3_surfe_backfill, dnc_s4_event_populations, dnc_wf4_sheet_intake,
heyreach_reply_to_dnc_ledger and dnc_expiry_job the wiring is:

```
IF MODE == dev?   TRUE → Send Guard → Dev Summary
                  FALSE → (nothing)
```

So flipping any of those to `MODE: "live"` does not route the summary somewhere production-safe —
**it silences the workflow completely.** The switch that reads like "go to production" is in
practice "stop reporting". `dnc_projections_sweep` is the one exception: its FALSE branch goes to
`Respond`.

### 2.3 `projections_state` is a write-only column

Written by `DNC__UpsertLedger__v1` (`Decide`, `Upsert Ledger Row`) — every new row gets
`{pipedrive: pending, smartlead: pending, heyreach: pending}`.

Read by exactly one workflow: `dnc_projections_sweep`, which has **0 executions in the 19-day
retention window and both write switches `false`**.

Nothing else in the estate reads the field. Not the morning digest, not the escalation detector,
not the gate. So the system records "this has not been projected yet" for every row it creates and
**no surface anywhere reports that backlog.** The count could be five or five thousand; nothing in
n8n would say.

---

## 3. What verification actually exists today

I searched every node for verify / read-back / confirm / assert patterns and traced each. There
are exactly three things in the estate that check reality rather than configuration, and one that
looks like it does but doesn't.

| Mechanism | What it asserts | Is it an effect check? |
|---|---|---|
| **`dnc_pre_add_gate_monitor`** — fires a synthetic 2-row request every 15 min and requires the answer to be exactly `total 2, clean 1, blocked 1, unresolvable 0` | the gate still returns a correct verdict against real registry data | **Yes.** The best example in the estate, and the template for everything below. |
| **`dnc_escalation_detector`** — hourly, intersects live Smartlead cold-campaign lead lists against the registry's active rows | "nobody on the do-not-contact list is sitting in a sending campaign" | **Yes** — intent vs reality, in the third-party tool, independent of any switch. Limited to Smartlead, and to 500 leads per campaign. |
| **WF-2S / WF-2R `Summary`** — inspects each replay response for `.error` and only claims the key on success | the replay was accepted by WF-2 | **Yes, narrowly** — it verifies handoff, not the CRM outcome. |
| **WF-2S `WF-2 Mode Eval`** — reads WF-2's definition via the n8n API and asserts `WRITE_MODE === "live"` | **the switch's value** | **No.** This is the purest example of the class: the one automated check we have over WF-2's writing is a check of the flag, not of a write. |
| WF-2 `Person Verify` / `R Person Verify` | that a matched person id still exists | identity, not effect |
| dnc_label_reversal `R Confirm Strip` | reads back after a PATCH | effect — but inside a workflow whose `FIRE_REVERSAL` is `false`, so it never runs |

**Summary: of 19 switches, one is covered by a switch-state check, three paths are covered by a
genuine effect check, and 15 have nothing at all.**

---

## 4. Proposal — one effect verification, not twelve

### 4.1 The principle

> **Assert the consequence in the system of record, on a schedule, with no reference to any switch.**
> A check that reads a flag can only tell you what you already configured. A check that reads the
> outside world tells you whether the configuration is true.

Three properties, all of which the gate monitor already has and should be copied from:

1. **It samples reality**, not our own state table.
2. **It reports a number every run, including zero** — so silence means the checker died, never
   "nothing to report". (Same rule as the morning digest.)
3. **It never consults the switch.** If a switch is off, the check must *fail loudly with a count*,
   not skip. "12,400 registry rows have never reached Smartlead" is the finding; "projections are
   disabled" is not.

### 4.2 The concrete thing to build: `dnc_intent_vs_reality`

One new scheduled workflow, daily, read-only, posting one block into the morning digest.

For a sample of **N active registry rows** (N ≈ 50, rotated by oldest-checked-first so the whole
registry is covered over time), assert each of these independently:

| Assertion | Read | Passes when |
|---|---|---|
| **A1 — Pipedrive person** | `GET /api/v2/persons/{id}` | the DNC custom field is set |
| **A2 — Pipedrive lead** | archived-visible lead search by person | every open lead carries the DNC label |
| **A3 — Smartlead** | `GET /api/v1/leads?email=…` | the lead is unsubscribed, or absent from every campaign |
| **A4 — HeyReach** | campaign membership for the identity | the identity is in no active campaign |
| **A5 — the ledger's own claim** | the row's `projections_state` | it agrees with A1–A4 |

Output, every day, as five numbers plus a drift line:

```
DNC reality check — 50 of 4,812 rows sampled (oldest-first, full cycle 97 days)
  Pipedrive person field   48/50 ✓   2 missing
  Pipedrive lead label     44/47 ✓   3 missing   (3 rows have no open lead)
  Smartlead unsubscribed   12/50 ✓  38 MISSING   ← 38 people on DNC are still contactable
  HeyReach not in campaign 50/50 ✓
  Ledger claim agrees      50/50 ✓  (all say "pending" — and they are right)
  Estate backlog: 4,806 rows have projections_state = pending
```

**A5 is the load-bearing one.** It is the assertion that catches this whole class: it compares what
we *say* we did against what is *there*. A row claiming `done` that fails A1–A4 is a silent write
failure. A row claiming `pending` that passes A1–A4 means something else is doing the work and we
do not know what.

### 4.3 Two supporting changes, both cheap

**(a) Every off switch declares its backlog.** A switch that is off must produce a number
somewhere, every day. Add one line to the morning digest, computed without running any of the
gated workflows:

```
Switches holding work back:
  FIRE_PIPEDRIVE=false   4,806 rows pending projection
  FIRE_SMARTLEAD=false   4,806 rows pending projection
  FIRE_S1=false          (last fired 18 Aug — unknown backlog, source is hand-supplied)
  FIRE_S2=false          (last fired 18 Aug — unknown backlog, source is hand-supplied)
  FIRE_REVERSAL=false    n candidate rows
```

This is the minimum honest version: an off switch stops being invisible.

**(b) Delete or wire the three dead flags** (§2.1). A switch nobody reads is worse than no switch,
because it advertises a control that does not exist. Either wire `dnc_auto` into `Gate SL
Unsubscribe` and `forward_enabled` into `Gate SL Forward Email`, or remove them from CONFIG.
*(No action taken — awaiting your word.)*

### 4.4 What I deliberately did **not** propose

- **Not** a per-switch monitor. Twelve monitors is twelve more things that can be off.
- **Not** an alert on switch state. That re-commits the class.
- **Not** turning anything on. The map comes first; §4.2 tells you the size of the problem before
  anyone decides whether to flip `FIRE_PIPEDRIVE`, which is a one-way door on the Smartlead half.
