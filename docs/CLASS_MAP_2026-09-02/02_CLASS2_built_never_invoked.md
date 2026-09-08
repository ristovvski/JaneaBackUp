# CLASS 2 — "built, never invoked"

**Read-only.** Nothing deactivated, deleted or changed. Every (b) recommendation below is a
proposal awaiting your word.

**The class:** a workflow or branch exists, is correct, and has no path by which it can ever run —
no schedule, no caller, no trigger anyone fires. It costs nothing at runtime and everything in
comprehension: it appears in the estate as capability we do not have.

**Method.** Built the full call graph from the live definitions: `executeWorkflow` edges, webhook
paths cross-referenced against every node's parameters, schedule triggers, other trigger kinds, and
unreachable nodes (no inbound edge, not a trigger). Execution counts are over the ~19-day retention
window.

> One false positive I checked and discarded: `WF-1-DO NOT USE` appears to reference WF-1's live
> webhook path, but the match is the shared `hr_token` value inside its own CONFIG plus a sticky
> note. It is not a caller.

---

## 1. The call graph

### Sub-workflows

| Sub-workflow | Callers | Live callers | Runs (19d) |
|---|---|---|---|
| `DNC__UpsertLedger__v1` | 8 | **5** (archived_responders_import, s3_surfe_backfill, s1, s2, s3_creation_watcher) | 3000+ |
| `DNC__CheckLedger__v1` | 2 — dnc_check_service *(inactive)*, dnc_wf4_sheet_intake *(inactive)* | **0** | 122, all on 26 Aug |
| `heyreach_reply_to_dnc_ledger` | **0** | 0 | 0 |
| `DNC__NormalizeIdentity__v1` | **0** | 0 | 0 |

*Of UpsertLedger's five "live" callers, four have their `FIRE_*` switch set to `false`. Only
`dnc_s3_creation_watcher` both runs on a schedule and is permitted to write — see Class 1.*

### Webhook endpoints

| Path | Workflow | State | Runs | Internal caller |
|---|---|---|---|---|
| `{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` | WF-2 | ACTIVE | 130 | WF-2S, WF-2R (replay) |
| `{{WEBHOOK_WF1_HEYREACH_RECEIVER}}` | WF-1 | ACTIVE | 387 | none — HeyReach |
| `{{WEBHOOK_I04_PD_EVENTS}}` | dnc_i04_event_receiver | ACTIVE | 1,355 | none — Pipedrive |
| `{{WEBHOOK_DNC_PRE_ADD_GATE}}` | dnc_pre_add_gate | ACTIVE | 3000+ | dnc_pre_add_gate_monitor |
| `{{WEBHOOK_DNC_LABEL_REVERSAL}}` | dnc_label_reversal | ACTIVE | 194 | none — hand |
| `{{WEBHOOK_DNC_S1_RESPONDED_TO_DNC}}` | dnc_s1 | ACTIVE | 36 | none — hand |
| `{{WEBHOOK_DNC_S2_MEETING_TO_DNC}}` | dnc_s2 | ACTIVE | 19 | none — hand |
| `{{WEBHOOK_DNC_S4_RETIREMENT_REMOVAL}}` | dnc_s4_retirement_removal | ACTIVE | 16 | none — hand |
| `{{WEBHOOK_DNC_ARCHIVED_RESPONDERS_IMPORT}}` | dnc_archived_responders_import | ACTIVE | 2 | none — hand |
| `{{WEBHOOK_DNC_ESCALATION_DETECTOR_TEST}}` | dnc_escalation_detector | ACTIVE | (shares 469) | none — test hook |
| **`{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}`** | dnc_projections_sweep | ACTIVE | **0** | **none** |
| **`{{WEBHOOK_DNC_S3_SURFE_BACKFILL_V2}}`** | dnc_s3_surfe_backfill | ACTIVE | **0** | **none** |
| `{{WEBHOOK_DNC_EXPIRY_NULL_ONESHOT}}` | dnc_expiry_null_oneshot | inactive | 15 | none |
| `{{WEBHOOK_DNC_S4_EVENT_POPULATIONS}}` | dnc_s4_event_populations | inactive | 194 | none |
| `hr-test-hrtest0712r2-e89986b7` | WF-1-DO NOT USE | inactive | 0 | none |
| `{{WEBHOOK_HEYREACH_CAPTURE}}` | HeyReach Phase 0 | inactive | 0 | none |

---

## 2. Classification

### (a) NEEDED — must be wired

| Workflow / branch | Why it is needed | What wires it |
|---|---|---|
| **`dnc_projections_sweep`** `8qVXtI2ez5o6a9hc` — ACTIVE, 0 runs, no caller, both switches off | It is the only mechanism that gives a registry entry an effect in Pipedrive and Smartlead. Without it the registry is a private notebook. | **A schedule trigger** (daily is enough; the sweep is chunked at 250) **plus** the Class 1 §4.2 reality check running *before* it, so the first live run is sized in advance. Order matters: measure, then enable Pipedrive only, then Smartlead separately — the Smartlead unsubscribe is irreversible via the API. |
| **`dnc_gate_queue_drainer`** `fZl1vpRsQ6Fko3sB` — inactive, 0 runs, 2-min schedule ready | Without it the gate's >50-row path is a black hole (Class 3 §2.1). | Two options, and **the honest one is to remove the queue path from the gate rather than wire the drainer** — see Class 3 §2.1 and Class 4 §2.2. If the queue is kept: create the `dnc_gate_queue` table with the real id, switch the drainer's references to `mode:"id"`, activate it, and add it to the gate monitor's assertions. Activating the drainer alone, against a table the monitor says does not exist, changes nothing. |
| **`heyreach_reply_to_dnc_ledger`** `YgufwSg1EAJaT0ra` — inactive, 0 runs, 0 callers | This is the *entire* reason LinkedIn replies never become registry entries. It is the single largest asymmetry between the two channels. | One `executeWorkflow` node in **WF-1**, on the M7 (reply) branch, after `M7 Build` and behind its own `FIRE_*` switch. WF-1 currently calls no sub-workflow at all, so this is a new edge, not a rewire. Needs a decision first: which registry `reason` does a LinkedIn reply earn — `reply_dnc`, or something weaker? |
| **`dnc_s1_responded_to_dnc`** / **`dnc_s2_meeting_to_dnc`** — ACTIVE webhooks, no caller, `FIRE_*` false, last fired 18 Aug | Two of the four capture reasons the registry is *defined* around ("they replied", "they booked a meeting") are currently only filled by hand. | Both take a candidate list in the request body, so they cannot simply be scheduled — **something must produce the list.** Either (i) a small scheduled feeder that queries Pipedrive for the label/stage population and POSTs it in ≤100-row chunks, or (ii) fold the criteria into `dnc_s3_creation_watcher`'s 15-minute poll, which already reads recent leads. (ii) is less code and one fewer moving part; (i) preserves the chunking and dry-run reporting that already exist. **My recommendation: (i)**, because S1/S2's populations are label/stage-driven, not creation-driven, and S3's newest-100-leads window cannot see them. |

### (b) OBSOLETE — propose deactivate, delete nothing

| Workflow | Evidence | Proposal |
|---|---|---|
| **`DNC__NormalizeIdentity__v1`** `K2M1Z0m1gKX6LdFI` — inactive, 0 runs, **0 callers ever** | The same normaliser is inlined in UpsertLedger, CheckLedger and the gate. It is the fourth copy and the only one nothing uses. | **Deactivate is already true.** Real action belongs in Class 4: make the inlined copies generated from one source, then this workflow either becomes that source or goes. Until then, leave it and label it. |
| **`smartlead_observability_readonly`** `XWtxUzBgNJuguJlg` — inactive, 0 runs | `campaign_id` is still the literal string `REPLACE_WITH_AI4_CAMPAIGN_ID`. It was never configured, and WF-2S/WF-2R now do the polling with better claim semantics. | **Obsolete. Propose: leave deactivated, rename with an `OBSOLETE__` prefix so the estate list reads honestly.** Do not delete — its watermark/dedupe design is the reference for anything that polls Smartlead. |
| **`WF-1-DO NOT USE`** `NNOVii5ImjFKDSM0` — inactive, 0 runs, 89 nodes | Superseded 126-node WF-1 is live. | **Obsolete, but its webhook path `hr-test-hrtest0712r2-e89986b7` is still defined.** Inactive workflows do not serve production webhooks, so the exposure is low; the real cost is that it doubles every linter finding (34 of the 195 findings are its duplicates). **Propose: keep deactivated, and exclude it from the linter by name** rather than delete. |
| **`HeyReach — Phase 0 Payload Capture`** `rnPaPoVQNe2SShkc` — inactive, 0 runs, 3 nodes | Payload-shape scaffolding from before WF-1 existed. | Obsolete. Harmless. Leave. |
| **`dnc_expiry_job`** `alpy9rsunqnFwQml` — inactive, 0 runs | Deliberately retired: `computeExpiry()` returns `null` for every entry type, and `dnc_expiry_null_oneshot` blanked the column on 31 Aug. | **Correctly obsolete and correctly preserved.** Leave exactly as is. |
| **`dnc_expiry_null_oneshot`** `CUpl8PVOOYXMysVN` — inactive, 15 runs on 31 Aug | Single-purpose migration, completed. | Leave. |
| **`dnc_s4_event_populations`** `hhdnug5xdFLAxrOg` — inactive, 194 runs on 14 Aug | One bulk load, done. It still works and is the only bulk-campaign loader. | **Not obsolete — dormant by design.** Reclassify as (c). |

### (c) HAND-FIRED BY DESIGN — correct as-is

| Workflow | Why hand-firing is right |
|---|---|
| `dnc_s4_retirement_removal` | Removing a protection is a business decision. `dry_run` defaults true. |
| `dnc_archived_responders_import` | One-off imports of a validated list; it refuses the whole call if any row is malformed. |
| `dnc_label_reversal` | A repair tool with `frozen_ids` / `live_exclusion_ids` — it exists to be aimed by a human. |
| `dnc_s3_surfe_backfill` | Historical backfill, run once per range. |
| `dnc_s4_event_populations` | Bulk campaign load, aimed at one named campaign at a time. |
| `WF-0 - Discovery` | Manual trigger, run when Pipedrive field definitions change. **This one is load-bearing and undocumented in the UI** — if a Pipedrive field is recreated its hash changes and WF-1/WF-2 silently stop writing it. |
| `dnc_escalation_detector`'s test webhook | A deliberate manual probe alongside the hourly schedule. |

**Two of these are ACTIVE with 0 runs** (`dnc_s3_surfe_backfill`, and `dnc_projections_sweep` which
is in (a)). Active + hand-fired is a legitimate combination; it only looks alarming in an inventory.
Worth a naming convention so it stops being a question every time — see Class 4 §4.

### (d) INACTIVE with a real trigger that nobody has enabled

| Workflow | Trigger built | Status |
|---|---|---|
| `dnc_check_service` | Slack `@mention` in the ops channel | Would make the registry self-service. **Cheap win** — no new logic, just activation, and it only reads. Needs its `MODE`/channel guard checked first. |
| `dnc_wf4_sheet_intake` | Google Sheets row trigger | The manual-intake path. Only worth activating if a human actually maintains that sheet — **question for you.** |
| `dnc_i04_weekly_reconciliation` | 5-min walk ticker + 08:00 idle guard | The full-estate CRM sweep. Off means we have event-based change detection only, which cannot see anything Pipedrive does not send a webhook for. **Needed, but heavy** (53 nodes, 13 data-table nodes all by name); wire it after Class 4 §2.1. |

---

## 3. Dead branches inside live workflows

| Workflow | Branch | Why it can never run |
|---|---|---|
| `dnc_i04_daily_summary` | **`Alert Post Failed`** (code node) | **Unreachable — no inbound edge at all.** The alarm that exists to say "the daily summary failed to post" can never fire. The only remaining safety net for a failed post is the 15-minute idle-guard, which checks a different condition. This is the single orphan node in the entire estate. |
| WF-1 | `M8 Task` | `create_assignment_task: false` — deliberate, another automation owns tasks |
| dnc_projections_sweep | `PD Split Rows` → … → `PD Patch Lead Labels`; `SL Split Rows` → `SL Unsubscribe` | both `FIRE_*` false |
| dnc_s1 / s2 / s3_surfe_backfill / s4 | `… Call UpsertLedger` | `FIRE_*` false |
| dnc_label_reversal | `R Patch Lead Labels` | `FIRE_REVERSAL` false |
| WF-2 | the Google-Sheets inbox-map path | `sheets.enabled: false`, `forward_map_source: "config"` |
| 8 workflows | the FALSE output of `IF MODE == dev?` | wired to nothing — see Class 1 §2.2 |
| `dnc_pre_add_gate` | the whole queue path (`Enqueue Rows` → `Respond Queued`) | reachable, and that is the problem — see Class 3 §2.1 |

No disabled nodes exist anywhere in the estate.

---

## 4. Proposal

**Wire (a) in this order**, because each step makes the next one measurable:

1. `dnc_check_service` — activate. Read-only, zero risk, and it gives everyone a way to query the
   registry without asking you.
2. The Class 1 §4.2 reality check — build and run for a week. It tells you the true size of the
   projection backlog before anything is enabled.
3. `dnc_projections_sweep` — schedule it, Pipedrive leg only, small chunks.
4. S1/S2 feeder — a scheduled list-producer, then flip `FIRE_S1` / `FIRE_S2`.
5. `heyreach_reply_to_dnc_ledger` — wire into WF-1's reply branch, behind its own switch. Needs
   your ruling on which `reason` a LinkedIn reply earns.
6. `dnc_projections_sweep` Smartlead leg — last, because it is irreversible.
7. The gate queue — decide *remove or complete* (Class 3 §2.1) rather than defaulting to the
   drainer.

**Deactivate/rename in (b):** only `smartlead_observability_readonly` needs a name change, and
`WF-1-DO NOT USE` needs a linter exclusion. Nothing gets deleted.
