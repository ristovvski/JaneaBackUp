# n8n estate — full inspection report

**Instance:** `https://janea-systems-2025.app.n8n.cloud`
**Read:** 2026-09-02, ~07:00Z, read-only (`GET /api/v1/workflows`, `GET /api/v1/executions`).
No writes, no activations, no deploys.
**Sources:** the live workflow definitions and the live execution log only. Chat history, task logs
and prior notes were not used. Where a statement comes from the project rulebook rather than from
n8n, the text says so.

**Scope:** 36 workflows — 21 active, 15 inactive, 1,090 nodes.

**Updated 2026-09-02 after Wave 0 deployed:** domain 1 §6 carried WF-ERR's incorrect "HeyReach retries" advice and has been corrected in place.

This single file is the complete, uncut concatenation of all nine documents in
`SYSTEM_DOCS_2026-09-02/`. Nothing has been summarised or removed; only heading levels were
demoted by one so the parts nest under the contents below.

## Contents

1. [Front matter — scope, sources, caveats](#front-matter--scope-sources-caveats)
2. [STAGE 1 — Inventory of every workflow](#stage-1--inventory-of-every-workflow)
3. [STAGE 2, part 1 — Receivers, reconcilers, error handler](#stage-2-part-1--receivers-reconcilers-error-handler)
4. [STAGE 2, part 2 — DNC registry, gate, capture sources, ops jobs](#stage-2-part-2--dnc-registry-gate-capture-sources-ops-jobs)
5. [STAGE 3, domain 1 — HeyReach to Pipedrive + DNC](#stage-3-domain-1--heyreach-to-pipedrive--dnc)
6. [STAGE 3, domain 2 — Smartlead to Pipedrive + DNC](#stage-3-domain-2--smartlead-to-pipedrive--dnc)
7. [STAGE 3, domain 3 — The do-not-contact registry](#stage-3-domain-3--the-do-not-contact-registry)
8. [STAGE 3, domain 4 — n8n conventions and traps](#stage-3-domain-4--n8n-conventions-and-traps)
9. [STAGE 4 — Slide outline](#stage-4--slide-outline)


---

## Front matter — scope, sources, caveats

*(source file: `README.md`)*

## System documentation — read live from n8n, 2026-09-02

Source of truth for everything in this folder: the live workflow definitions and execution log of
`https://janea-systems-2025.app.n8n.cloud`, read read-only via `GET /api/v1/workflows` and
`GET /api/v1/executions` on 2026-09-02 (~07:00Z). No writes, no deploys, no activations.
Chat history, task logs and prior notes were not used as sources; where a statement comes from the
project rulebook rather than from n8n, the document says so.

| File | What it is | Who it's for |
|---|---|---|
| [00_STAGE1_INVENTORY.md](00_STAGE1_INVENTORY.md) | All 36 workflows: state, nodes, trigger, last run, one-line purpose. Flags: dead-looking, duplicates, and 12 open questions. | you, building the deck |
| [01_STAGE2_RECEIVERS_AND_RECONCILERS.md](01_STAGE2_RECEIVERS_AND_RECONCILERS.md) | Per-workflow detail: WF-1, WF-2, WF-2S, WF-2R, WF-2H, WF-ERR | whoever maintains the bridges |
| [02_STAGE2_DNC_AND_OPS.md](02_STAGE2_DNC_AND_OPS.md) | Per-workflow detail: the gate, the ledger, S1–S4, projections, escalation, I-04, digest, linter | whoever maintains the DNC side |
| [10_DOMAIN_heyreach_to_pipedrive_and_dnc.md](10_DOMAIN_heyreach_to_pipedrive_and_dnc.md) | Domain 1 — LinkedIn → CRM | a new operator |
| [11_DOMAIN_smartlead_to_pipedrive_and_dnc.md](11_DOMAIN_smartlead_to_pipedrive_and_dnc.md) | Domain 2 — cold email → CRM | a new operator |
| [12_DOMAIN_dnc_registry.md](12_DOMAIN_dnc_registry.md) | Domain 3 — the do-not-contact record | a new operator |
| [13_DOMAIN_n8n_conventions_and_traps.md](13_DOMAIN_n8n_conventions_and_traps.md) | Domain 4 — conventions and the 22 traps we have paid for | whoever changes a workflow next |
| [20_SLIDE_OUTLINE.md](20_SLIDE_OUTLINE.md) | 23 slides, ~39 minutes, for Melisa / Sergey / Stefan | you, presenting |

### The three things to read first

1. **The do-not-contact record has no automatic effect on the sending tools right now.** The
   projector has zero executions in the retention window and both of its write switches are off.
   → `12_DOMAIN_dnc_registry.md` §6.
2. **The gate silently swallows batches over 50 rows.** Keep batches at or under 50.
   → `02_STAGE2_DNC_AND_OPS.md`, first section.
3. **Almost all cold-email traffic arrives by catch-up replay, not by live webhook** (130 live runs
   vs 1,845 reconciler cycles in 19 days), and a lost bounce or unsubscribe is not recovered by
   anything. → `11_DOMAIN_smartlead_to_pipedrive_and_dnc.md` §6.

### Caveats on the evidence

- **Execution history is a rolling ~19-day window** — the oldest execution retained anywhere is
  2026-08-14T01:15Z. "No executions" means "not since 14 Aug", never "never ran".
- **n8n's public API does not expose data tables**, so no statement about a table's existence or
  contents could be verified directly. Where a claim about a table comes from a code comment, the
  document says so and asks for UI confirmation.
- Two execution counts hit the paging cap (`dnc_pre_add_gate`, `DNC__UpsertLedger__v1`); both are
  reported as `3000+`.

---

## STAGE 1 — Inventory of every workflow

*(source file: `00_STAGE1_INVENTORY.md`)*

## Stage 1 — n8n workflow inventory

**Instance:** `https://janea-systems-2025.app.n8n.cloud`
**Read live from the n8n public API on 2026-09-02 (~07:00Z).** Nothing here comes from chat history, task logs or memory — every field below was read from the live workflow definitions and the live execution log.
**Read-only:** only `GET /api/v1/workflows` and `GET /api/v1/executions` were called. No writes, no activations, no deploys.

**Totals:** 36 workflows — **21 ACTIVE**, 15 inactive. 1,090 nodes in total.

#### About the "last execution" column

The n8n execution log is a rolling window, not a full history. The oldest execution retained **anywhere in the instance** right now is `2026-08-14T01:15Z` — i.e. a **~19-day retention horizon**, and it is consistent across all high-volume workflows. So "no executions" means *no executions since ~14 Aug*, not *never ran*. Where that distinction matters I say so.

Execution counts marked `3000+` hit my paging cap; the real number is higher.

---

### A. ACTIVE workflows (21)

| # | Name | id | Nodes | Trigger | Last execution | Runs (19d) | What it does |
|---|------|----|-------|---------|----------------|-----------|--------------|
| 1 | **WF-1 HeyReach Receiver** | `2jdjKM2NJr473GdA` | 126 | webhook `{{WEBHOOK_WF1_HEYREACH_RECEIVER}}` | 2026-09-02 04:55 | 387 | Takes every HeyReach LinkedIn event (invite sent, invite accepted, message sent, reply) and writes it into Pipedrive — finds or creates the organisation, person and lead, moves the person's stage forward, unions lead labels, and logs an activity. |
| 2 | **WF-2 Smartlead Receiver** | `jp7rum9Z0YDJkQWv` | 174 | webhook `{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` | 2026-09-01 18:01 | 130 | Same job for cold email: takes Smartlead events (sent, reply, bounce, unsubscribe), resolves the person and lead in Pipedrive, classifies reply text with an LLM, alerts Slack on real replies, and unsubscribes/marks DNC when the reply is a refusal. |
| 3 | **WF-2S Smartlead SENT Reconciler** | `6Y92ryBwYoy6z0Jx` | 24 | schedule, every 15 min | 2026-09-02 06:30 | 1,845 | Polls Smartlead campaign stats for newly-sent emails and replays them into WF-2, because Smartlead never actually delivers SENT webhooks to us. Also watches that WF-2H still runs and that WF-2 has not been left in a temporary mode. |
| 4 | **WF-2R Smartlead REPLY Reconciler** | `U8Bb7Pdq7S6nzYPa` | 25 | schedule, every 15 min | 2026-09-02 06:30 | 1,845 | Same idea for replies: polls Smartlead for replies we have not seen and replays them into WF-2, so a webhook outage does not lose a reply. Also watches that WF-2S is still alive. |
| 5 | **WF-2H Health & Digest** | `nK3yIOqRcBearV8s` | 9 | schedule, daily 07:15 | 2026-09-01 07:15 | 19 | Posts a once-a-day Slack digest comparing Smartlead campaign volume against what landed in Pipedrive, as a data-quality check. |
| 6 | **WF-ERR Error Handler** | `BbrXPABgOaaTJjD6` | 12 | error trigger | 2026-08-31 05:30 | 185 | The instance-wide error sink. Every other workflow points its `errorWorkflow` here; it pulls the failed execution, classifies the failure (asking an LLM when the class is unknown), suppresses bursts, and posts one Slack message. |
| 7 | **dnc_pre_add_gate** | `9aP2dP0jgAPFGDvA` | 24 | webhook `{{WEBHOOK_DNC_PRE_ADD_GATE}}` | 2026-09-02 06:30 | 3000+ | The "may I contact this person?" service. You post a batch of identities, it answers allow/deny against the DNC registry. Has a batch cap, and a queue fallback when it is under load. |
| 8 | **dnc_pre_add_gate_monitor** | `g8MUOKFlUaeVrdBx` | 13 | schedule, every 15 min + daily 08:00 heartbeat | 2026-09-02 06:30 | 682 | Calls the gate every 15 minutes with a synthetic request and alerts Slack on the *edge* — when it goes unhealthy and when it recovers — plus a daily "still fine" heartbeat. |
| 9 | **dnc_s3_creation_watcher** | `QM21Vd7VId7PBdqh` | 23 | schedule, every 15 min + daily 23:55 heartbeat | 2026-09-02 06:30 | 1,865 | DNC capture source S3: polls the newest Pipedrive leads every 15 minutes, spots ones that match the do-not-contact criteria, and files them into the registry. |
| 10 | **dnc_i04_event_receiver** | `wqORtqgRJ3W5YvBL` | 5 | webhook `{{WEBHOOK_I04_PD_EVENTS}}` | 2026-09-02 03:44 | 1,355 | Receives Pipedrive's own webhooks for lead and person changes and drops each one into a data table, so the daily CRM diff has a record of what changed. |
| 11 | **dnc_i04_daily_summary** | `8sT1XjDDVmrz05CA` | 22 | schedule, daily 05:30 + idle-guard every 15 min | 2026-09-02 06:30 | 586 (**5 errors**, latest 08-31) | Turns yesterday's captured Pipedrive events into the daily CRM-change summary in Slack, prunes old event rows, and raises an alarm if the day's summary never got posted. |
| 12 | **dnc_morning_digest** | `qJKfR602wV9yfFrj` | 40 | schedule, daily 07:00 (Asia/Jerusalem) | 2026-09-02 04:00 | 2 | The single "state of the machine" morning post: Smartlead + HeyReach volume, Pipedrive lead volume, DNC registry counts, gate health, workflow errors in 24h, and which scheduled jobs are overdue. Created 31 Aug, so only two runs exist. |
| 13 | **dnc_wf_linter** | `fziGeigC48aGTLT8` | 8 | schedule, daily 06:40 (Asia/Jerusalem) | 2026-09-02 03:40 | 2 | Reads every workflow definition in the instance daily and posts a Slack report on convention breaches and drift. Created 31 Aug, so only two runs exist. |
| 14 | **dnc_escalation_detector** | `QO1zRhUfG7otk06N` | 20 | schedule, hourly + daily 06:10 heartbeat + test webhook | 2026-09-02 06:10 | 469 | Hourly safety net: cross-checks people who are on the DNC registry against the lead lists of live Smartlead cold campaigns, and shouts in Slack if someone on the registry is still sitting in a sending campaign. |
| 15 | **dnc_s1_responded_to_dnc** | `BxJZmz1HY5AdaQqE` | 17 | webhook `{{WEBHOOK_DNC_S1_RESPONDED_TO_DNC}}` | 2026-08-18 07:52 | 36 | DNC capture source S1: takes a list of Pipedrive people who have responded, resolves their identity, and files them into the registry. Fired by hand — nothing in n8n calls it. |
| 16 | **dnc_s2_meeting_to_dnc** | `E0oTTvHHQ0hVTNDD` | 17 | webhook `{{WEBHOOK_DNC_S2_MEETING_TO_DNC}}` | 2026-08-18 08:02 | 19 (1 error) | DNC capture source S2: same, for people who have booked a meeting. Fired by hand. |
| 17 | **dnc_label_reversal** | `LQRfmEl4Wv0qpXsI` | 20 | webhook `{{WEBHOOK_DNC_LABEL_REVERSAL}}` | 2026-08-14 15:19 | 194 (2 errors) | Repair tool: walks registry rows, re-reads the Pipedrive lead, and strips labels that should no longer be there. Has its own `FIRE_REVERSAL` switch and is dry-run by default. |
| 18 | **dnc_s4_retirement_removal** | `DYb9jArdS7xKs3nA` | 7 | webhook `{{WEBHOOK_DNC_S4_RETIREMENT_REMOVAL}}` | 2026-08-26 16:34 | 16 | Small operator tool: marks named registry rows as removed/retired. Dry-run by default. |
| 19 | **dnc_archived_responders_import** | `07sGtABZiqLrBChX` | 8 | webhook `{{WEBHOOK_DNC_ARCHIVED_RESPONDERS_IMPORT}}` | 2026-08-28 13:15 | 2 | One-shot importer: pushes a supplied list of archived responders into the registry via the ledger sub-workflow. Dry-run by default. |
| 20 | **dnc_projections_sweep** | `8qVXtI2ez5o6a9hc` | 41 | webhook `{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}` | **never (in 19d)** | 0 | The projector: takes registry rows that are not yet reflected downstream and pushes them out — sets the DNC field on the Pipedrive person, unions the lead labels, and unsubscribes the lead in Smartlead. Gated by `FIRE_PIPEDRIVE` / `FIRE_SMARTLEAD`. **See flags.** |
| 21 | **dnc_s3_surfe_backfill** | `1fpep0U4XC8KNzta` | 18 | webhook `{{WEBHOOK_DNC_S3_SURFE_BACKFILL_V2}}` | **never (in 19d)** | 0 | Historical backfill twin of S3: pages back through older Pipedrive leads and files the matching ones into the registry. **See flags.** |

### B. INACTIVE workflows (15)

| # | Name | id | Nodes | Trigger | Last execution | Runs (19d) | What it does |
|---|------|----|-------|---------|----------------|-----------|--------------|
| 22 | **DNC__UpsertLedger__v1** | `RolYGL3J2CNg6Yp3` | 14 | sub-workflow (called by others) | 2026-09-01 19:00 | 3000+ (2 errors) | **Inactive but the busiest thing in the instance.** The single writer to the DNC registry: normalises an identity, looks it up by LinkedIn and by email, decides insert/update/no-op/conflict, writes the row, and tombstones split identities. Sub-workflows do not need to be "active" to run. |
| 23 | **DNC__CheckLedger__v1** | `kv7reJYAAgsOV33t` | 5 | sub-workflow | 2026-08-26 06:15 | 122 | Read-only twin: given an identity, answers whether it is on the registry. |
| 24 | **DNC__NormalizeIdentity__v1** | `K2M1Z0m1gKX6LdFI` | 2 | sub-workflow | never (in 19d) | 0 | Identity normaliser (email lower-casing, LinkedIn slug extraction) as a callable unit. No caller found in any current definition — the same logic is inlined in UpsertLedger and CheckLedger. |
| 25 | **dnc_gate_queue_drainer** | `fZl1vpRsQ6Fko3sB` | 6 | schedule, every 2 min | never (in 19d) | 0 | Drains the gate's overflow queue: picks up rows the gate parked instead of answering synchronously, classifies them, and writes the verdicts back. **See flags.** |
| 26 | **dnc_expiry_job** | `alpy9rsunqnFwQml` | 17 | schedule, daily 06:00 | never (in 19d) | 0 | Ages the registry: expires rows past their TTL, de-duplicates, keeps a week counter and posts a weekly digest. |
| 27 | **dnc_expiry_null_oneshot** | `CUpl8PVOOYXMysVN` | 5 | webhook `{{WEBHOOK_DNC_EXPIRY_NULL_ONESHOT}}` | 2026-08-31 11:29 | 15 | One-shot that blanks `expires_at` on registry rows. Created, run 15 times, and switched off on 31 Aug — i.e. expiry was deliberately unwound. |
| 28 | **dnc_i04_weekly_reconciliation** | `gjVZkkvm05jj8CNM` | 53 | schedule, every 5 min walker + daily 08:00 idle-guard | never (in 19d) | 0 | The heavy weekly sweep: pages the whole Pipedrive lead and person estate into a staging table, builds a snapshot, diffs it against last week's, and reports departures. Off. |
| 29 | **dnc_s4_event_populations** | `hhdnug5xdFLAxrOg` | 24 | webhook `{{WEBHOOK_DNC_S4_EVENT_POPULATIONS}}` | 2026-08-14 14:27 | 194 | DNC capture source S4: bulk-loads a whole Smartlead or HeyReach campaign's lead list into the registry. Used on 14 Aug, then switched off. |
| 30 | **heyreach_reply_to_dnc_ledger** | `YgufwSg1EAJaT0ra` | 7 | sub-workflow | never (in 19d) | 0 | Would map a HeyReach reply into a registry write. Never ran and nothing calls it — **HeyReach replies currently do not reach the DNC registry.** |
| 31 | **dnc_check_service** | `PViKUykLaDd7Xze1` | 7 | Slack `@mention` in `C0B8GCVNR5W` | never (in 19d) | 0 | Slack bot: mention it with an identity and it replies with that person's DNC status via CheckLedger. |
| 32 | **dnc_wf4_sheet_intake** | `bluGflKaUI3bGodQ` | 16 | Google Sheets row trigger | never (in 19d) | 0 | Manual DNC intake: watches a Google Sheet, checks each row against the registry, and files new ones. |
| 33 | **smartlead_observability_readonly** | `XWtxUzBgNJuguJlg` | 18 | schedule, every 30 min | never (in 19d) | 0 | Read-only Smartlead anomaly watcher (single campaign) with its own watermark and alert de-duplication state. Superseded in practice by WF-2S/WF-2R. |
| 34 | **WF-1-DO NOT USE** | `NNOVii5ImjFKDSM0` | 89 | webhook `hr-test-hrtest0712r2-e89986b7` | never (in 19d) | 0 | Old copy of WF-1 on a test webhook path, kept and renamed rather than deleted. |
| 35 | **HeyReach — Phase 0 Payload Capture** | `rnPaPoVQNe2SShkc` | 3 | webhook `{{WEBHOOK_HEYREACH_CAPTURE}}` | never (in 19d) | 0 | The original throwaway: ACK the HeyReach webhook and record the raw payload, used to learn the payload shape before WF-1 existed. |
| 36 | **WF-0 - Discovery** | `5TCZwAZ3xeXQr0vI` | 7 | manual | never (in 19d) | 0 | Run-by-hand utility that reads Pipedrive's person fields, lead fields, lead labels, users and activity types and assembles the CONFIG block the receivers use. This is how the field-hash constants get regenerated. |

---

### C. Flags

#### C1. Looks dead — but is switched ON

These are ACTIVE (so their webhook path is live and reachable) yet have not run once in the 19-day window:

| Workflow | Why it matters |
|---|---|
| **dnc_projections_sweep** | This is the *only* thing that pushes registry state outward — Pipedrive person DNC field, lead labels, Smartlead unsubscribe. If it has not run in 19 days, nothing that entered the registry in that period has been projected anywhere. **And its live CONFIG carries `FIRE_PIPEDRIVE: false` and `FIRE_SMARTLEAD: false`, so even if it were invoked today it would report a dry run.** Question for you: intentional, or has it silently stopped being invoked? |
| **dnc_s3_surfe_backfill** | A one-shot backfill left switched on. Harmless but its webhook is live. |

#### C2. Live but hand-fired only — and mostly switched to dry-run

`dnc_s1_responded_to_dnc`, `dnc_s2_meeting_to_dnc`, `dnc_label_reversal`, `dnc_s4_retirement_removal`, `dnc_archived_responders_import` are all ACTIVE webhooks with no caller anywhere in the instance — they only run when a human posts to them. S1 and S2 have not been fired since 18 Aug.

**Live switch state, read from the deployed CONFIG nodes:**

| Switch | Value |
|---|---|
| `FIRE_S3` (creation watcher) | **true** |
| `FIRE_S1`, `FIRE_S2`, `FIRE_S4`, `FIRE_S3_BACKFILL`, `FIRE_REVERSAL`, `FIRE_PIPEDRIVE`, `FIRE_SMARTLEAD` | **false** |

So of the four DNC capture sources, **only S3 both runs on its own and is permitted to write.** Question: is that the intended steady state, or are S1/S2 supposed to be scheduled?

#### C2b. One live trap found in Stage 2 — belongs on the Stage 1 flag list

**`dnc_pre_add_gate` answers synchronously for batches of 50 rows or fewer.** Above that it parks the batch in a queue table, replies `{"queued": N, "eta_minutes": …}`, and relies on `dnc_gate_queue_drainer` to process it. The drainer is **inactive and has never run**, and the gate monitor's own code (dated 2026-08-31) states the `dnc_gate_queue` table **does not exist**. A caller submitting 51–500 rows therefore gets a confident "queued" and never receives an answer. Nothing alerts on this.

*Data tables are not exposed by the n8n public API, so I could not verify the table's absence myself — please confirm in the UI. Until then: keep gate batches at or under 50 rows.*

#### C3. Off, but something depends on them

| Workflow | Consequence of it being off |
|---|---|
| **dnc_gate_queue_drainer** | The gate parks requests in `dnc_gate_queue` when queue depth is exceeded, and answers "queued". With the drainer off, a queued item is never classified and never gets a verdict. Today's traffic is being answered synchronously, so this has not bitten — but it is a live trapdoor. |
| **heyreach_reply_to_dnc_ledger** | HeyReach replies never become DNC entries. WF-2 does this for email; there is no equivalent path for LinkedIn. |
| **dnc_expiry_job** | Nothing ages the registry. Combined with `dnc_expiry_null_oneshot` having blanked `expires_at` on 31 Aug, the registry is now effectively permanent. Reads as deliberate — **please confirm.** |
| **dnc_i04_weekly_reconciliation** | The weekly full-estate sweep does not run; only the daily event-based summary does. The daily one cannot see changes Pipedrive does not send a webhook for. |

#### C4. Duplicates / overlapping pairs

| Pair | Note |
|---|---|
| **WF-1 HeyReach Receiver** (126 nodes) vs **WF-1-DO NOT USE** (89 nodes) | Old copy on a live-but-unused test webhook path. Rename is doing the safety work; the path is still reachable. |
| **dnc_pre_add_gate** vs **dnc_gate_queue_drainer** | Both contain a byte-identical `Classify Batch` (2,330 chars) and `Normalize Batch`. Copy-paste, not a shared sub-workflow — they will drift. |
| **dnc_expiry_job** vs **dnc_expiry_null_oneshot** | The second exists to undo the first. Both off. |
| **dnc_i04_daily_summary** vs **dnc_i04_weekly_reconciliation** | Two generations of the same CRM-diff idea; daily is live, weekly is off. |
| **smartlead_observability_readonly** vs **WF-2S / WF-2R** | Three Smartlead pollers with three separate watermark stores; only two are live. |
| **DNC__NormalizeIdentity__v1** vs inline copies | The normaliser exists as a sub-workflow *and* is inlined in UpsertLedger, CheckLedger, and the gate. |
| **Heartbeat / send-guard blocks** | The same 1,225-char `Send Guard` code node appears in at least 8 workflows verbatim. Same story: copied, not shared. |

#### C5. Things I could not explain from the definitions — questions for you

1. **`dnc_projections_sweep` has zero executions *and* both write switches off.** Either projections are being done by something outside n8n, or they have stopped. I cannot tell which from here. *(Highest-priority question — everything in domain doc 3 hangs on the answer.)*
2. **Who called `DNC__CheckLedger__v1` 122 times on 26 Aug?** Its only two callers (`dnc_check_service`, `dnc_wf4_sheet_intake`) have never executed and are both inactive. Manual runs during a build session is my guess, but it is a guess.
3. **`dnc_i04_daily_summary` has 5 errored runs, most recently 2026-08-31 05:30** — that is the daily summary trigger itself failing, not the idle-guard. I have not yet opened the failures (Stage 2).
4. **WF-1 carries `settings.timeSavedMode: "fixed"` and no other workflow does.** Deliberate, or a leftover from a UI edit?
5. **`dnc_expiry_null_oneshot` blanked `expires_at` on 31 Aug and `dnc_expiry_job` is off.** I read this as "TTL abandoned". Confirm, because the domain doc has to state whether registry entries are permanent.
6. **WF-2 ran 130 times in 19 days; WF-2S and WF-2R each ran 1,845 times.** So nearly all Smartlead traffic reaching the CRM arrives via reconciler replay rather than the live webhook. Expected, or a sign the Smartlead webhook is only partly wired?
7. **`dnc_escalation_detector` has a live test webhook** (`{{WEBHOOK_DNC_ESCALATION_DETECTOR_TEST}}`) alongside its hourly schedule. Fine to leave exposed?
8. **`dnc_s4_event_populations` is inactive but has 194 executions on 14 Aug** and a `FIRE_S4` switch — one bulk load, then off. Was that the London/Ai4 population load, and is it expected to be re-run?

**Added after Stage 2 (found by reading the code, not the metadata):**

9. **WF-1 selects the lead two different ways on the reply path.** The reply builder picks the lead whose *Campaign field* matches the HeyReach campaign; the label step immediately after picks the *newest non-archived* lead instead. Under one-lead-per-campaign those can be different leads, so the activity and the labels could land on different records. Deliberate, or a leftover from before the lead-per-campaign rule?
10. **The gate's over-50-row queue path is a dead end** (see C2b). Confirm whether `dnc_gate_queue` exists.
11. **The linter's rules run R01–R14 and R16 — R15 does not exist** in either the deployed code or the repo copy, while the rulebook says "16 rules". Withdrawn, or never written?
12. **`smartlead_observability_readonly` still has `campaign_id: "REPLACE_WITH_AI4_CAMPAIGN_ID"`.** It was never configured. Delete, or finish?

---

### D. Conventions visible across the whole instance

Stated here because they show up in the counts, and they are the backbone of Stage 3 doc 4:

- **34 of 36 workflows set `errorWorkflow` to `BbrXPABgOaaTJjD6` (WF-ERR).** The two that do not are `WF-0 - Discovery` and `HeyReach — Phase 0 Payload Capture` — both pre-convention scaffolding.
- **`callerPolicy: workflowsFromSameOwner`** on all 34 of those.
- **A `CONFIG` Set node as node #2** is near-universal: channels, API bases, Pipedrive custom-field hashes, and `FIRE_*` / `MODE` switches all live there, never scattered through the graph.
- **`MODE: "dev"` is still the value in the CONFIG of the S1–S4 family, the projector, the reversal tool and the ledger** — those workflows branch on it to decide whether to post verbose Slack summaries.
- **`FIRE_*` booleans** (`FIRE_S1`…`FIRE_S4`, `FIRE_PIPEDRIVE`, `FIRE_SMARTLEAD`, `FIRE_REVERSAL`, `FIRE_S3_BACKFILL`, `create_assignment_task`) gate every outward write. Dry-run is the default posture.
- **Two Slack channels dominate:** `C0B8GCVNR5W` (ops/alerts) and `C0BTP6VHP1B` (digest), plus `C0BQM1X9ZUY` for the linter.
- **Four data tables carry all state:** the DNC registry `UOgKwlGsL28lX61O`, the I-04 event table `zAW2IYoO6Dj0vdIt`, WF-1's dedupe claim table `euyostwJYfJefItC`, and `dnc_gate_queue` / `i04_snapshots` / `i04_walk_staging` / `obs_state` referenced by name.
- **Data tables are referenced two different ways** — some by real id (`mode: "id"`), some by name (`mode: "name"`). Both appear in live ACTIVE workflows. This is a known hazard and gets its own section in Stage 3.

---

*Stage 2 (per-workflow detail), Stage 3 (four domain docs) and Stage 4 (slide outline) follow in this same folder.*

---

## STAGE 2, part 1 — Receivers, reconcilers, error handler

*(source file: `01_STAGE2_RECEIVERS_AND_RECONCILERS.md`)*

## Stage 2 (part 1) — Receivers, reconcilers and the error handler

Read live from the n8n API on 2026-09-02. Every rule quoted below is in the deployed definition, not in a design doc.

Covered here: **WF-1**, **WF-2**, **WF-2S**, **WF-2R**, **WF-2H**, **WF-ERR**.
Part 2 (`02_STAGE2_DNC_AND_OPS.md`) covers the DNC registry, the gate, the capture sources and the daily/ops jobs.

---

### WF-1 HeyReach Receiver

`2jdjKM2NJr473GdA` · ACTIVE · 126 nodes · versionId `cec8f544` · last updated 2026-08-31

#### Purpose
LinkedIn outreach happens in HeyReach; the business runs on Pipedrive. WF-1 is the bridge. Without it, someone would have to watch HeyReach and hand-copy every invite, acceptance and reply into the CRM. It serves Melisa first (she owns the leads and gets the reply alerts) and the sales team second (their pipeline is only accurate because this runs).

#### Trigger and inputs
A HeyReach webhook, `POST /webhook/{{WEBHOOK_WF1_HEYREACH_RECEIVER}}`. Each call carries one event: the person, the campaign, the sender inbox, the conversation id, and the recent message history. Four event types are handled:

| HeyReach event | Internal name | Meaning |
|---|---|---|
| `connection_request_sent` | Invited | we sent a connection request |
| `connection_request_accepted` | M5 / Accepted | they accepted |
| `message_sent` | M6 | we sent a message in the thread |
| `every_message_reply_received` | M7 | **they replied** |

Anything else falls through to a no-op.

#### What it does, step by step
1. **Refuses to process the same event twice.** A 48-hour memory keyed on HeyReach's correlation id (or, when that is the all-zeros placeholder, on event type + profile URL + timestamp + conversation).
2. **Normalises the person.** Lower-cases and canonicalises the LinkedIn URL, extracts the profile slug.
3. **Reads the campaign name for an event marker.** A campaign named `[Events Visiting] [Ai4 2026]` means "this person came from an event"; the two brackets become the person's Hypothesis and Event Name fields. One bracket, or a second bracket that is empty or longer than 60 characters, is treated as a naming mistake: the event fields are skipped and Slack gets a warning naming the campaign.
4. **Checks whether this campaign's lead was archived.** Before anything else it searches Pipedrive for an archived lead for this campaign and person. If it finds one, the whole event passes through silently — no lead, no activity, no label, no alert. Someone archived that lead on purpose.
5. **Finds or creates the organisation**, by company name.
6. **Finds the person** — by email, then by LinkedIn URL, then by HeyReach member id / public id (with a verification step so a loose match cannot bind the wrong person). Creates them if genuinely new.
7. **Moves the person's stage forward, never backward.** Stages are ranked Invited 1 → Accepted 2 → First follow-up sent 3 → Replied 4. A write only happens if the incoming stage outranks the current one.
8. **Finds or creates the lead — one lead per campaign.** The match is on the lead's Campaign field equalling the HeyReach campaign name; the title is written as `{campaign id} - {campaign name} - {full name}`, but the title is never what the match is made on.
9. **Unions the lead labels.** Labels are only ever added, never removed: rank ≥1 adds *Cold*, rank ≥4 adds *3. Responded*.
10. **Writes an activity** recording the message or reply, with the reply text (attachments and voice notes get a placeholder instead of an empty note).
11. **On a reply, decides whether to announce it** (below), and posts to the replies channel `C07LTD8UT70`.

#### Systems it touches
Pipedrive (organisations, persons, leads, activities — v2 for persons/orgs/activities, v1 for leads), Slack (`C07LTD8UT70` replies, `C0B8GCVNR5W` ops, `C0BTUHSSM3K` alerts), one n8n data table (`euyostwJYfJefItC`) used as a dedupe claim log. It does **not** talk to Smartlead, HeyReach's API, or the DNC registry.

#### Business rules encoded in it
- **Archived lead = ignore.** Detection requires an archived-visible search route; the ordinary lead-list endpoints cannot see archived leads at all.
- **A personal LinkedIn chat is never announced.** If the event has no campaign, it is the exec's own conversation: the CRM activity is still written so the history exists, and nothing is posted anywhere. This silence is deliberate.
- **One alert per person per campaign, and only on delivery.** The suppression key is the Pipedrive person id (falling back to the canonical LinkedIn identity), never the lead id — archiving a lead must not reset someone's alert suppression. The key is recorded *after* Slack confirms the post landed in the team channel, so a failed post cannot burn a lead's only alert. Entries expire after 90 days.
- **Labels are cumulative.** Never removed by us.
- **The follow-up task is switched off** (`create_assignment_task: false`) — another automation owns task creation.
- **"Replied to invite" vs "Replied"** is decided by whether we had sent an outbound message in the thread yet.

#### Known failure modes
| Symptom | Cause | Diagnosis |
|---|---|---|
| A reply appears in Pipedrive but no Slack alert | suppression fired, or the event had no campaign | check `__alert_reason` in the execution: `already_delivered`, `manual_conversation`, `first_alert`, `no_identity` |
| Two alerts for the same person | the person could not be resolved at all (`no_identity` path fails open on purpose) | look for `no_identity` in the alert gate output |
| Labels applied to a different lead than the activity | **suspected defect** — the reply builder picks the lead whose Campaign field matches; the label step picks the *newest non-archived* lead instead. With one lead per campaign these can differ. See the questions list. |
| Nothing happens at all | duplicate suppression, or the archived-lead rule | the dedupe memory is 48h; the archived probe result is in `__ar` |
| Event Marker Warn in Slack | a campaign was renamed and no longer has two valid brackets | fix the campaign name in HeyReach; do not rename live campaigns mid-flight |

#### How to safely restart or replay
There is no replayer for HeyReach. **HeyReach itself retries a failed webhook up to 5 times over 24 hours**, so a single failure usually self-heals — WF-ERR says so explicitly in its verdict table. If it does not: re-firing the same payload by hand is safe, because the dedupe memory will reject an exact repeat within 48 hours and the stage/label logic only ever moves forward. Do **not** re-run a whole campaign's history; the alert gate would announce nothing (suppression holds) but activities would duplicate.

#### Dependencies
Feeds Pipedrive and Slack. Depends on WF-0 - Discovery for the field-hash constants in CONFIG. Reports failures to WF-ERR. Nothing else calls it, and it calls no other workflow.

---

### WF-2 Smartlead Receiver

`jp7rum9Z0YDJkQWv` · ACTIVE · 174 nodes · versionId `8cee9f06` · last updated 2026-08-31

#### Purpose
The cold-email equivalent of WF-1, and the larger of the two because email has more failure modes than LinkedIn: bounces, unsubscribes, out-of-office, wrong-person, and replies that need reading before anyone is bothered.

#### Trigger and inputs
Webhook `POST /webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}`. Four canonical events after normalisation: **SENT**, **REPLIED**, **BOUNCED**, **UNSUB**. Most traffic arrives not from Smartlead directly but as a **replay from WF-2S / WF-2R** (see the flag in Stage 1: 130 live executions vs 1,845 reconciler cycles).

#### What it does, step by step
1. **Authenticates the call** and warns (rate-limited) on a bad secret.
2. **Normalises** the payload into a single shape, and **watches for unknown event aliases** — a new Smartlead event name posts an ops warning rather than being silently dropped.
3. **De-duplicates** on a 48-hour window.
4. **SENT:** if it is a nurture campaign, stop. If it is not the first email in the sequence, stop. Otherwise enrich the lead from Smartlead if the payload was thin, resolve or create the organisation, person and lead in Pipedrive, and record the send.
5. **REPLIED:** resolve the person and the lead, then
   - decide whether this is the **first reply worth announcing**, and if so post to the replies channel;
   - **classify the reply body with an LLM** (GPT, JSON-only response, minimum confidence 0.7) into one of ten categories;
   - write the category back to Smartlead;
   - if the classification says do-not-contact → unsubscribe the lead in Smartlead and apply the DNC label in Pipedrive;
   - if the category is forwardable (Interested, Meeting Request, Not Interested, Information Request) → work out which human owns that sending inbox and forward the thread to them;
   - union the lead labels and write a reply activity.
6. **BOUNCED:** resolve person and lead, write a bounce note, count it, and suppress duplicate bounces within an hour.
7. **UNSUB:** resolve person and lead, unsubscribe in Smartlead, apply the DNC label.

#### Systems it touches
Smartlead (lead fetch, category write, unsubscribe, forward-email, message history), Pipedrive (orgs, persons, leads, activities, labels), OpenAI (classification), Slack (replies `C07LTD8UT70`, ops `C0B8GCVNR5W`, telemetry `C0BQM1X9ZUY`, alerts `C0BTUHSSM3K`).

#### Business rules encoded in it
- **Every outward write is behind a `Gate …` node** that checks `WRITE_MODE === 'live'`. Flipping one CONFIG value turns the whole workflow into a dry run. It has been live since 2026-08-10.
- **Classification guardrail:** invalid JSON, an unknown category, or confidence below 0.7 → category `Uncategorized`, Smartlead is left untouched, and the reply is forwarded to a review address instead of an owner.
- **Do-not-contact is automatic** (`dnc_auto: true`) — a reply classified as DNC unsubscribes the lead in Smartlead and labels the Pipedrive lead. **Note: this does not write a row in the DNC registry.** See the domain doc; these are two different things today.
- **Forwarding is address-driven, not name-driven.** A large explicit map of sending-inbox addresses → owner name → owner email. An unknown inbox posts an ops warning rather than guessing.
- **Nurture campaigns are excluded** from the SENT path by campaign marker.
- **Only the first email of a sequence creates CRM records** — later steps in the same sequence do not.
- **Alerts are recorded on delivery, not on decision** — same rule as WF-1.

#### Known failure modes
| Symptom | Cause | Diagnosis |
|---|---|---|
| A reply reached Pipedrive but nobody was told | first-reply gate suppressed it, or the Slack post failed | the alert-delivery registry is only written on `ok: true`; check the execution |
| Reply forwarded to the wrong person | the sending inbox is not in the forward map | look for `Ops Warn Unknown Inbox`; the map lives entirely in CONFIG |
| Everything classified `Uncategorized` | OpenAI error, or confidence below threshold | `__classify_ok: false` on the item; `Ops Warn Classify` fires |
| Person created with a missing company | the real SENT payload carries no lead data and enrichment did not run | this is the "B16" class — the enriched copy must be read, not the raw one |
| Bounce announced as a reply | Smartlead records bounces as history type `REPLY` on the stats endpoint | the reconciler keeps a bounce index to prevent exactly this |

#### How to safely restart or replay
**WF-2 answers 200 before it processes, so Smartlead never retries.** Recovery is ours:
- a lost **REPLIED** is recovered by WF-2R within ~15 minutes — it only marks a reply as seen after WF-2 accepts the replay;
- a lost **SENT** is recovered by WF-2S on its next 15-minute cycle, same claim-after-success rule;
- a lost **BOUNCED** or **UNSUB** is **not** recovered by anything. There is no reconciler for those two event types.

To replay by hand, POST the same envelope to the webhook. Be aware the replay envelope is shaped **inversely** to the live webhook: on a replay, `to_email` is the lead and the lead's address must also be sent as `sl_lead_email`, or WF-2 will not identify the lead.

**Do not replay ~100 items in one burst.** A burst of that size has previously exhausted the instance's memory and left the workflow deactivated.

#### Dependencies
Fed by Smartlead and by WF-2S / WF-2R. Watched by WF-2S (which alerts if WF-2 is left in a non-live write mode). Reports to WF-ERR. Calls no sub-workflow.

---

### WF-2S Smartlead SENT Reconciler

`6Y92ryBwYoy6z0Jx` · ACTIVE · 24 nodes · every 15 minutes

#### Purpose
**Smartlead never sends us the "email was sent" webhook.** WF-2S is therefore not a safety net — it is the *primary* source of SENT events, and every cold-email lead in Pipedrive exists because this job ran.

#### Trigger and inputs
A 15-minute schedule. Each cycle picks **one** campaign (hot campaigns three cycles for every cold one; a campaign older than 180 days counts as cold) and pages its lead statistics, 100 rows a page, up to 35 pages.

#### What it does
1. Picks the campaign — resuming an unfinished walk before starting a new one.
2. Reads each lead's history and keeps entries of type `SENT` inside a 3-hour lookback.
3. Drops anything already claimed (keyed on Smartlead's `stats_id`).
4. Sorts oldest-first, takes at most **20 per run**, looks up each lead's full record, and **replays a synthetic `EMAIL_SENT` into WF-2's webhook**.
5. Marks a send as seen **only after WF-2 accepted it**.
6. Posts a report, and separately checks that WF-2H has run in the last 48 hours and that WF-2 is still in `live` write mode.

#### Business rules
- **Claim-after-success.** Nothing is marked seen unless the replay succeeded — this is what makes a crash safe.
- **Continuation, not truncation.** A cycle that cannot finish a campaign records where it stopped; the next cycle resumes from exactly there. After 5 consecutive unfinished rounds it declares itself stuck and names the unscanned range.
- **20 per run** deliberately caps the burst size.

#### Known failure modes
- **Silent under-scan.** The Smartlead statistics endpoint defaults to the *oldest* rows; this workflow pages explicitly, but any change to its paging can make it report "idle" while sends pile up. A cycle that reports idle every time for hours on an active campaign is the signal.
- **Stuck walk** — reported explicitly with the offset range.
- **Replay burst → out-of-memory.** The instance has been taken down by a large replay burst before; that is why `max_per_run` is 20.

#### How to restart
Just let it run — the next cycle re-claims anything unconfirmed. If you must force a rescan, the claim memory is in the workflow's static data; clearing it will re-replay everything inside the lookback window, so shorten `lookback_minutes` first.

#### Dependencies
Writes into WF-2. Watches WF-2H and WF-2's write mode. Watched by WF-2R.

---

### WF-2R Smartlead REPLY Reconciler

`U8Bb7Pdq7S6nzYPa` · ACTIVE · 25 nodes · every 15 minutes

#### Purpose
Recovers replies the live webhook missed. Built after an outage during which replies were lost with no way to get them back.

#### Trigger and inputs
15-minute schedule, one campaign per cycle, same rotation and resume logic as WF-2S. Lookback is **48 hours** (much wider than the SENT job's 3 hours, because a missed reply matters more than a missed send).

#### What it does
1. Builds a **bounce index** first, from campaign statistics.
2. Pages the campaign's lead statistics for reply events.
3. **Excludes bounces.** The statistics endpoint records a bounce as history type `REPLY` — there is no bounce type there — so without the index every bounce would replay into WF-2 as a genuine reply. A replayed event carries none of the bounce markers the live webhook has, so this index is the only defence.
4. Ignores anything before a hard floor date (`2026-08-06T13:50Z`) so it can never rake up ancient history.
5. Replays at most 20 per run into WF-2 as synthetic `EMAIL_REPLY`, marking each seen only after acceptance.
6. Reports, and alerts if WF-2S has not succeeded in 90 minutes.

#### Business rules
- **The replay envelope is inverted** relative to the live webhook: `to_email` carries the lead, and `sl_lead_email` must be set or WF-2 cannot identify the lead. This exact omission silenced every recovered reply until it was found.
- Bounce exclusion is mandatory, and the index must be both readable and complete before it is trusted.

#### Known failure modes
- **Recovered replies that go nowhere** — the envelope-identity defect above.
- **Bounces announced as replies** — if the bounce index is unusable, the code knows it (`__bounce_index_ok`, `__bounce_index_complete`) and should say so.
- **Idle-noisy** warnings when a campaign returns nothing for a long time.

#### How to restart
Same as WF-2S: it is self-healing by design. Widening `lookback_minutes` re-examines older replies; the `ignore_replies_before` floor stops it going too far.

#### Dependencies
Writes into WF-2. Watches WF-2S. Watched by nothing.

---

### WF-2H Health & Digest

`nK3yIOqRcBearV8s` · ACTIVE · 9 nodes · daily 07:15

#### Purpose
A once-a-day sanity check that what Smartlead thinks it sent matches what Pipedrive received, plus a data-quality read on the leads created in the last 24 hours.

#### What it does
Reads active Smartlead campaigns and their statistics, reads the most recent 500 Pipedrive leads (sorted newest-first, and explicitly including archived ones), and posts a comparison to the ops channel: volume on each side, and how many new leads carry the expected Campaign / Hypothesis / Medium fields and the expected labels.

#### Known failure modes
Its numbers are a *comparison*, not a reconciliation — it will not tell you *which* lead is missing. Because it reads only 500 leads, a very high-volume day can push older leads out of its window.

#### How to restart
It recomputes from scratch each run; a missed day is simply late, nothing is lost.

#### Dependencies
Watched by WF-2S (stale after 48 hours).

---

### WF-ERR Error Handler

`BbrXPABgOaaTJjD6` · ACTIVE · 12 nodes · error trigger

#### Purpose
One place where every failure in the instance surfaces, in language an operator can act on. 34 of the 36 workflows name it as their error workflow.

#### What it does
1. Fetches the failed execution in full.
2. Builds a report: which workflow, which node, whether the failing node was a **write** node (it keeps an explicit list — Person Create, Lead Create, SL Unsubscribe, Reply Activity, Replay Into WF-2, and others), and what the recovery verdict is for that source.
3. **Classifies the failure** against five known classes: paired-item defect, out-of-memory, upstream 5xx, auth, bad request — each with a written "what to do".
4. If the class is unknown, asks an LLM for a one-paragraph read.
5. **Suppresses bursts** within a 15-minute window so one storm is one message.
6. Posts to the ops channel.

#### The recovery verdicts it encodes — this is the single most useful table in the estate
| Failing workflow | What happens to the lost event |
|---|---|
| WF-1 HeyReach receiver | **DELAYED** — HeyReach retries up to 5× over 24h, the event should come back on its own |
| WF-2, event = REPLIED | **RECOVERABLE** — WF-2R replays it within ~15 min; check its next report before hand-repairing |
| WF-2, event = SENT | **RECOVERABLE** — WF-2S re-claims it next cycle |
| WF-2, any other event | **LOST** — no reconciler covers it; it will not be delivered again |
| WF-2S | **SAFE** — next cycle re-claims |
| WF-2H | **DELAYED** — the digest is just late |

#### Known failure modes
It cannot report on an execution that never started, and it cannot see a workflow that n8n auto-deactivated. Silence from WF-ERR is not proof of health.

#### Dependencies
Every workflow except `WF-0 - Discovery` and `HeyReach — Phase 0 Payload Capture`.

---

## STAGE 2, part 2 — DNC registry, gate, capture sources, ops jobs

*(source file: `02_STAGE2_DNC_AND_OPS.md`)*

## Stage 2 (part 2) — the DNC registry, the gate, capture sources and the ops jobs

Read live from the n8n API on 2026-09-02.

> **Read this first.** There are **two different things called "DNC"** in this estate, and they do not talk to each other today:
>
> 1. **The DNC registry** — a data table (`UOgKwlGsL28lX61O`) written only by `DNC__UpsertLedger__v1`. This is the record of *why* someone must not be contacted.
> 2. **The DNC label + Smartlead unsubscribe** applied directly by WF-2 when a reply is classified as do-not-contact. This changes Pipedrive and Smartlead but **writes no registry row**.
>
> The workflow that was built to connect them in the other direction — `dnc_projections_sweep`, which pushes registry rows out to Pipedrive and Smartlead — has **zero executions in the retention window and both of its write switches set to `false`**. Keep that in mind while reading everything below.

---

### dnc_pre_add_gate

`9aP2dP0jgAPFGDvA` · ACTIVE · 24 nodes · webhook `{{WEBHOOK_DNC_PRE_ADD_GATE}}` · ~3,000+ runs in 7 days

#### Purpose
The "may I contact this person?" service. Before anyone loads a list into a sending campaign, they ask the gate, and it answers per row. It exists so that "are they on the do-not-contact list?" is one HTTP call rather than a manual cross-check.

#### Trigger and inputs
`POST` a JSON body of rows, each carrying an email and/or a LinkedIn URL (optionally a name and a Pipedrive person id). A second mode, `{"retrieve": true, "rows": [...]}`, fetches the verdicts of a previously queued batch.

#### What it does
1. **Caps the batch at 500 rows** — over that it refuses with an explanatory error rather than truncating.
2. **Normalises every identity**: lower-cases the email; canonicalises the LinkedIn URL to `https://www.linkedin.com/in/{slug}`; a LinkedIn URL that is not an `/in/` profile is marked unmatchable rather than guessed at.
3. **Decides synchronous or queued**: 50 rows or fewer *and* no pending queue work → answer immediately.
4. **Looks the batch up in the registry** by LinkedIn and by email.
5. **Classifies each row** into one of four verdicts and answers.

#### The four verdicts
| Verdict | Meaning |
|---|---|
| `OWN_TEAM` | the email is `@janeasystems.com` — exclude from any campaign list |
| `UNRESOLVABLE` | no usable LinkedIn URL and no email, so nothing can be matched |
| `BLOCKED` | an **active** registry row exists; the reason returned is `{entry_type} / {source}` |
| `CLEAN` | no row, or only rows that are expired/removed (and then the reason says what it used to be) |

Where several rows match, the strongest wins: explicit opt-out 5 → negative reply 4 → replied 3 → employee connection 2 → manual 1, ties broken by the earliest entry.

#### Systems it touches
Only n8n data tables (the registry, and a queue table). No CRM, no sending tool. That is deliberate — the gate is a read.

#### Known failure modes — and one live trap
- **The queue path is a dead end.** The gate parks batches larger than 50 rows into a table called `dnc_gate_queue`, replies `{"queued": N, "eta_minutes": …}`, and expects `dnc_gate_queue_drainer` to classify them. **The drainer is inactive and has never run**, and the monitor's own code (dated 2026-08-31) states plainly that the `dnc_gate_queue` table does not exist. So a caller who submits 51–500 rows gets a cheerful "queued" and **never gets an answer**. Nothing alerts on this. *This is the single most dangerous thing I found. I could not verify table existence from the API — data tables are not exposed there — so please confirm in the UI.*
- A failed registry read is handled correctly: the sync/queue decision checks positively for the real row shape, so an unreadable queue table reads as "nothing pending" rather than crashing.
- The `Get Registry Match (Batch)` and `Lookup Queue By Key` reads have **no error handling**; if either fails the whole call fails, which is at least loud.

#### How to safely restart or replay
It is a pure read: re-ask any time, as many times as you like. Keep batches **at or under 50 rows** until the queue path is fixed or removed.

#### Dependencies
Reads the registry written by `DNC__UpsertLedger__v1`. Polled every 15 minutes by `dnc_pre_add_gate_monitor`. Would depend on `dnc_gate_queue_drainer` for anything over 50 rows.

---

### dnc_pre_add_gate_monitor

`g8MUOKFlUaeVrdBx` · ACTIVE · 13 nodes · every 15 min + 08:00 heartbeat

#### Purpose
Proves the gate still answers correctly, so that "no alerts" means "healthy" rather than "nobody asked".

#### What it does
Fires a synthetic two-row request at the gate every 15 minutes and asserts the answer is exactly: total 2, one clean, one blocked, none unresolvable. Tracks checks, failures and latency for the day. **Alerts on the transition only** — once when the gate goes unhealthy, once when it recovers — plus a daily heartbeat at 08:00.

#### Business rules
- **A monitor alert fires once per state change, never per poll.** This rule was written after the previous version produced 96 false "queue STUCK" alerts a day for five days: it read a failing data-table call as depth 0 instead of "unknown", and its IF was wired to the FALSE output. Both the queue branch and the per-poll repetition were removed.

#### Known failure modes
It only proves the gate *responds correctly to two known rows*. It cannot detect that the registry itself is stale or that a capture source stopped writing.

#### How to restart
Nothing to restart; it is stateless apart from the day counters in static data.

---

### DNC__UpsertLedger__v1  *(inactive, but the busiest workflow in the estate)*

`RolYGL3J2CNg6Yp3` · 14 nodes · sub-workflow · 3,000+ executions, last 2026-09-01

#### Purpose
**The single writer to the DNC registry.** Everything that adds someone to the do-not-contact list goes through here, so that the merge rules exist in exactly one place.

> Being "inactive" is normal and correct for a sub-workflow — n8n only requires the *calling* workflow to be active. Do not switch it on.

#### Trigger and inputs
Called by another workflow with an identity (`linkedin_url`, `email`, `full_name`, `pipedrive_person_id`) plus a signal (`entry_type`, `reason`, `source`, `source_ref`, `reply_category`, `correlation_id`).

#### What it does
1. **Normalises the identity** to a canonical LinkedIn URL and lower-cased email.
2. **Looks the person up twice** — once by LinkedIn, once by email.
3. **Decides one of five actions**:
   - **conflict** — LinkedIn and email resolve to two *different* people. Alerts a human; writes nothing.
   - **merge_split_identity** — the narrow exception to conflict: one side is a LinkedIn-only bulk-import row with no email and no person id, the other carries a person id, *and* the names corroborate. Then it is one person split across two half-rows, and they are merged with the loser tombstoned.
   - **insert** — nobody matched.
   - **update** — merge onto the strongest existing row, soft-removing duplicates.
   - **noop** — nothing material changed.
4. Writes the row and, where applicable, tombstones the superseded one.

#### Business rules encoded in it
- **Strength never downgrades.** explicit opt-out 5 > negative reply 4 > replied 3 > employee connection 2 > manual 1.
- **Reason priority** (0 strongest): client, unsubscribe, meeting, reply-DNC, sales personal outreach, manual offboard-eligible, event contacted, manual sheet, offboard. The losing reason is not discarded — it is appended to `also_flagged` so an offboarding scan can still see it.
- **Identity fields fill in but never overwrite.** An existing non-null value is kept.
- **Sources accumulate** as a comma-separated set.
- **A re-appearing signal reactivates** an expired or removed row and resets `added_at`.
- **Expiry is dead.** `computeExpiry()` returns `null` for every entry type. The code says why: on 2026-08-26 time-based expiry was replaced by reason-based retention, and 1,353 rows carrying an `expires_at` were nulled on 2026-08-31. Registry entries are now permanent unless explicitly retired.
- **Every new row is created with `projections_state` = pending for Pipedrive, Smartlead and HeyReach.** Nothing currently consumes that field — see `dnc_projections_sweep`.

#### Known failure modes
- **Conflict alerts** are the expected human-in-the-loop path, not a bug.
- The registry write is the only node in the estate set to `stopWorkflow` on error — a failed write stops the run rather than continuing silently. That is right.
- 2 errored executions in the window.

#### How to restart or replay
Idempotent by construction: calling it again with the same signal produces `noop`. Safe to re-run.

#### Dependencies
Called by: S1, S2, S3, S3-backfill, S4, `dnc_archived_responders_import`, `heyreach_reply_to_dnc_ledger`, `dnc_wf4_sheet_intake`. **Of those, only S3 currently runs.**

---

### DNC__CheckLedger__v1 · DNC__NormalizeIdentity__v1  *(inactive)*

- **CheckLedger** (`kv7reJYAAgsOV33t`, 5 nodes) — read-only twin of the ledger: normalise, look up by LinkedIn and by email, report status. 122 executions all on 2026-08-26; both of its callers are inactive, so **who invoked it that day is an open question**.
- **NormalizeIdentity** (`K2M1Z0m1gKX6LdFI`, 2 nodes) — the identity normaliser as a callable unit. Zero executions, no caller. The same logic is inlined in UpsertLedger, CheckLedger and the gate. Dead code with a maintenance cost: four copies to keep in step.

---

### The four capture sources (S1–S4)

They share one shape: a `CONFIG` node with a `FIRE_Sn` boolean, a classifier, a person lookup in Pipedrive to get the identity, and a call to `DNC__UpsertLedger__v1`. Dry-run is the default; nothing writes unless `FIRE_Sn` is `true`.

**Live switch state, read from the deployed CONFIG today:**

| Source | Switch | Value | Runs |
|---|---|---|---|
| S1 responded → DNC | `FIRE_S1` | **false** | last 2026-08-18 |
| S2 meeting → DNC | `FIRE_S2` | **false** | last 2026-08-18 |
| S3 creation watcher | `FIRE_S3` | **true** | every 15 min |
| S3 Surfe backfill | `FIRE_S3_BACKFILL` | **false** | never |
| S4 event populations | `FIRE_S4` | **false** | last 2026-08-14 |

**So S3 is the only capture source writing to the registry.** S1, S2 and S4 would produce a dry-run report if fired today.

#### dnc_s1_responded_to_dnc — `BxJZmz1HY5AdaQqE` · ACTIVE · webhook
Takes a supplied list of Pipedrive person ids that have responded, reads each person for a LinkedIn URL or email, and files them as `reply_dnc`. Skips anyone with no resolvable identity and logs that separately. Hand-fired; chunked 100 at a time with an offset.

#### dnc_s2_meeting_to_dnc — `E0oTTvHHQ0hVTNDD` · ACTIVE · webhook
Same, for people who booked a meeting (`meeting_dnc`, mapped to entry type *replied*). The source population is defined outside n8n: lead label "5. Meeting" union deal stage "Qualified Meeting Set", with Memurai/partner pipeline explicitly excluded.

#### dnc_s3_creation_watcher — `QM21Vd7VId7PBdqh` · ACTIVE · every 15 min · **the live one**
**Purpose:** if a salesperson creates a lead by hand, or Surfe creates one, that person now has a human relationship and must not be swept into a cold campaign.

**How it decides.** Reads the newest 100 Pipedrive leads (explicitly sorted newest-first) and keeps a lead when:
- the creator is one of eight named sales users, **or** the lead's channel is `Surfe`;

and rejects it when:
- it was written by the automation account via the API, **or**
- it came from a web form (either the legacy creator id or origin `webforms`), **or**
- it is a Memurai lead (by channel or title).

Each keeper is filed as `sales_personal_outreach` with the salesperson's name as the source reference.

**The limits you must know.** It reads the **newest 100 leads** and remembers the ids it saw last poll. That means it is **forward-only** — a lead that arrives while it is behind can drop out of the window — and it is **lead-shaped**: a person created without a lead, or a person plus a deal, is invisible to it. Pipedrive persons carry no creator field, so there is no equivalent watch for them.

**Restart:** safe. Its memory is just the previous poll's lead ids; the ledger is idempotent. It also posts a nightly heartbeat at 23:55 so a silent failure is visible.

#### dnc_s3_surfe_backfill — `1fpep0U4XC8KNzta` · ACTIVE · webhook · never run
Historical twin of S3: pages back through older leads 500 at a time, 3 pages per call. `FIRE_S3_BACKFILL: false`.

#### dnc_s4_event_populations — `hhdnug5xdFLAxrOg` · INACTIVE · 194 runs on 2026-08-14
Bulk-loads an entire Smartlead or HeyReach campaign's lead list into the registry as `event_contacted` — the weakest signal: "we touched them once via an event campaign", not "they responded". One bulk load on 14 Aug, then switched off.

---

### dnc_s4_retirement_removal

`DYb9jArdS7xKs3nA` · ACTIVE · 7 nodes · webhook

Operator tool. POST `{"row_ids": [...], "dry_run": false}` and it marks those registry rows removed with reason `rule_change_2026-08-26_melisa`. **Dry-run is the default** — you must pass `dry_run: false` explicitly to write. Used 16 times on 26 Aug when the retention rule changed.

**Restart:** re-running the same ids is harmless (they are already removed). There is no undo — re-adding means re-filing through the ledger.

---

### dnc_archived_responders_import

`07sGtABZiqLrBChX` · ACTIVE · 8 nodes · webhook · 2 runs on 2026-08-28

One-shot importer for a supplied list of archived responders. **Validates every row before writing anything**: the reason must be one of the nine known reasons, `reply_dnc` requires a reply category, and every row must have an email or a LinkedIn URL. If any row fails, the whole call throws with the first ten problems named. Then calls the ledger per row. Dry-run by default.

---

### dnc_projections_sweep  ⚠️

`8qVXtI2ez5o6a9hc` · ACTIVE · 41 nodes · webhook `{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}` · **zero executions**, **`FIRE_PIPEDRIVE: false`, `FIRE_SMARTLEAD: false`**

#### Purpose
The projector — the piece that makes a registry entry mean something outside the registry. For each row not yet projected it would:
- **Pipedrive:** set the DNC custom field on the person, and if the person has an open lead, add the DNC label to it (union, never replacing existing labels);
- **Smartlead:** resolve the lead by email and unsubscribe it;
- **HeyReach:** count what is pending — there is no HeyReach write path at all, only a counter.

It then marks each row's `projections_state` done, or records a write error.

#### Current state
It has not run in the 19-day retention window, and both write switches are off, so **even if it were invoked it would report a dry run**. Every registry row written since at least 14 Aug still carries `projections_state: pending` as far as this workflow is concerned.

#### Why this matters
The DNC registry currently has no automatic outward effect. The only things actually stopping a send today are (a) whoever remembers to call the gate before loading a list, (b) `dnc_escalation_detector` shouting after the fact, and (c) WF-2's own reply-classification path, which unsubscribes in Smartlead directly and never consults the registry.

#### How to restart safely
Set `FIRE_PIPEDRIVE` / `FIRE_SMARTLEAD` deliberately, one at a time, and fire the webhook with a small chunk first (`pd_chunk_size` is 250). **Smartlead unsubscribe is irreversible via the API** — treat the Smartlead half as a one-way door and confirm the candidate list before enabling it.

---

### dnc_label_reversal

`LQRfmEl4Wv0qpXsI` · ACTIVE · 20 nodes · webhook · last used 2026-08-14 · `FIRE_REVERSAL: false`

Repair tool for the opposite problem: labels that should not be there. Walks registry candidates, re-reads each Pipedrive lead, and strips the DNC label where the rule says it does not belong. Accepts `frozen_ids` and `live_exclusion_ids` so specific leads can be protected. Dry-run unless `FIRE_REVERSAL` is set.

---

### dnc_escalation_detector

`QO1zRhUfG7otk06N` · ACTIVE · 20 nodes · hourly + 06:10 heartbeat + a test webhook

#### Purpose
The after-the-fact safety net: **is anyone on the do-not-contact list still sitting in a live sending campaign?**

#### What it does
Every hour: lists Smartlead campaigns, keeps those that are not COMPLETED/PAUSED/DRAFTED/STOPPED and are not one of seven known nurture campaigns, pulls up to 500 leads from each, and intersects them against the registry's active rows by email and by LinkedIn URL. Any hit is posted to the ops channel with the person, campaign, entry type and reason. It flags `truncated` when a campaign returns the full 500.

#### Known failure modes
- **500-lead ceiling per campaign** — a bigger campaign is only partly checked, and the workflow says so rather than hiding it.
- Matching is exact-string on email and canonical LinkedIn URL; a person on the registry under a different address is invisible.

#### Why it matters right now
With the projector dormant, **this is the main thing standing between the registry and a compliance incident** — and it detects rather than prevents.

---

### dnc_expiry_job *(inactive)* and dnc_expiry_null_oneshot *(inactive)*

`alpy9rsunqnFwQml` — the daily 06:00 ager: expire rows past TTL, de-duplicate, weekly digest. Never ran in the window and is switched off.
`CUpl8PVOOYXMysVN` — created, run 15 times and switched off on 2026-08-31; it blanked `expires_at` on every registry row.

Together with `computeExpiry()` now returning `null`, the position is: **registry entries do not expire.** They are retired explicitly, by reason, via `dnc_s4_retirement_removal`.

---

### dnc_gate_queue_drainer *(inactive)*

`fZl1vpRsQ6Fko3sB` · 6 nodes · every 2 min · never run

Would pick pending rows out of `dnc_gate_queue`, classify them against the registry, and write verdicts back. Its `Classify Batch` and `Normalize Batch` code is **byte-identical** to the gate's — a copy, not a shared sub-workflow, so the two will drift.

Off, plus a queue table the monitor says does not exist, is what makes the gate's over-50-row path a dead end.

---

### The I-04 CRM-change watch

#### dnc_i04_event_receiver — `wqORtqgRJ3W5YvBL` · ACTIVE · 5 nodes · 1,355 runs
Receives Pipedrive's own webhooks at `/webhook/{{WEBHOOK_I04_PIPEDRIVE_EVENTS}}`, understands both v1 and v2 webhook shapes, keeps only `lead` and `person` objects, and writes one row per event into the event table with the raw payload preserved. Answers `200` on receipt, before processing.

**Failure mode:** if the Pipedrive subscription is deleted or expires, this simply goes quiet — and quiet looks identical to "nothing changed". The daily summary is what catches that (below).

#### dnc_i04_daily_summary — `8sT1XjDDVmrz05CA` · ACTIVE · 22 nodes · daily 05:30 · **5 errored runs, latest 2026-08-31**
Turns the captured events into a Slack summary: arrivals, departures, lead updates, person events, and **mass-relabel detection** (ten or more distinct leads updated inside the same minute — the signature of a bulk relabel operation, which is how a label-wiping automation was caught before). Then prunes old event rows and saves a watermark.

**Two rules worth repeating:**
- It distinguishes **"no events received"** from **"zero real changes"** and reports them as different findings — an empty event log may mean the Pipedrive subscription died.
- It degrades instead of throwing if the watermark cannot be read, because a throw would blind the estate for the whole day.
- A separate idle-guard runs every 15 minutes and alerts if today's summary never got posted. **A missing post means the job did not run** — that is the whole invariant.

**Open item:** the 5 errored executions are on the daily trigger itself. Worth opening before the presentation.

#### dnc_i04_weekly_reconciliation — `gjVZkkvm05jj8CNM` · INACTIVE · 53 nodes · never run
The heavy version: a five-minute ticker walks the entire Pipedrive lead and person estate into a staging table, builds a snapshot, diffs it against the previous one, looks up each departure, reports, then prunes old snapshots. It has a circuit breaker. Currently off, so the estate has event-based change detection only — which cannot see anything Pipedrive does not send a webhook for.

---

### dnc_morning_digest

`qJKfR602wV9yfFrj` · ACTIVE · 40 nodes · daily 07:00 Asia/Jerusalem · created 2026-08-31

#### Purpose
One post that answers "is the machine fine this morning?" without opening n8n.

#### What it reports
Smartlead campaign volume and next-step due dates; HeyReach volume; Pipedrive lead volume; an **integrity** line (emails sent with no corresponding lead); DNC registry active count plus added/removed in 24h; gate latency, checks and failures today; failed executions in 24h and **missed schedules**; and a count of "no match found" messages in the ops channel.

#### The rules that make it trustworthy
- **It posts every single day, including a wholly green one.** There is deliberately no "only post if interesting" gate: a day with no message must mean the job did not run.
- **It refuses to report a number it could not read honestly.** If the Pipedrive lead page comes back unsorted, new-lead counts are suppressed with a named reason rather than printed as a possibly-wrong figure; a saturated page is reported as a floor, not a total; an unreadable source is listed under "not measured".

#### Restart
Recomputed from scratch each run; a missed day is a missed day, nothing is lost.

---

### dnc_wf_linter

`fziGeigC48aGTLT8` · ACTIVE · 8 nodes · daily 06:40 · created 2026-08-31

#### Purpose
Reads every workflow definition in the instance and reports convention breaches. **Fifteen rules, each one written after a real incident**, and each carrying the incident in a comment so nobody deletes a rule whose reason has been forgotten. The full rule list is in domain doc 4.

#### The rules that make it trustworthy
- **It posts only what is NEW or NEWLY RESOLVED**, keeping the standing backlog in its own memory. The first-ever run only records a baseline and says so, rather than dumping the whole backlog into a channel where it would be ignored.
- **An unreadable workflow list is reported as unreadable**, never as zero findings — which is exactly the failure the linter exists to catch, so it must not commit it itself.
- Findings are recorded *before* the Slack post is composed, so a Slack failure cannot cause a re-post storm.

#### Note
The rule numbering runs R01–R14 and R16. **R15 is absent** — either withdrawn or never written; worth confirming.

---

### The remaining inactive tools, briefly

| Workflow | What it would do | Why it matters |
|---|---|---|
| **heyreach_reply_to_dnc_ledger** `YgufwSg1EAJaT0ra` | map a HeyReach reply into a registry write | never ran, no caller — **LinkedIn replies never become registry entries**, which is the biggest asymmetry between the two channels |
| **dnc_check_service** `PViKUykLaDd7Xze1` | Slack bot: `@mention` it with an identity, get that person's DNC status | would make the registry self-service; off |
| **dnc_wf4_sheet_intake** `bluGflKaUI3bGodQ` | watch a Google Sheet and file new rows into the registry | the manual-intake path; off |
| **smartlead_observability_readonly** `XWtxUzBgNJuguJlg` | 30-minute anomaly watch on one Smartlead campaign | its `campaign_id` is still the literal placeholder `REPLACE_WITH_AI4_CAMPAIGN_ID` — it was never configured |
| **WF-0 - Discovery** `5TCZwAZ3xeXQr0vI` | read Pipedrive's field / label / user / activity-type definitions and assemble the CONFIG block | **run this by hand whenever Pipedrive fields change** — it is how the field hashes in WF-1 and WF-2 are regenerated |
| **WF-1-DO NOT USE** `NNOVii5ImjFKDSM0` | an old 89-node copy of WF-1 | its test webhook path is still reachable; the name is doing all the safety work |
| **HeyReach — Phase 0 Payload Capture** `rnPaPoVQNe2SShkc` | ACK and record raw HeyReach payloads | build-time scaffolding from before WF-1 existed |

---

## STAGE 3, domain 1 — HeyReach to Pipedrive + DNC

*(source file: `10_DOMAIN_heyreach_to_pipedrive_and_dnc.md`)*

## Domain 1 — HeyReach → Pipedrive (+ DNC)

*Written for someone who has to keep this running without asking the person who built it.*
*State as read live from n8n on 2026-09-02.*

---

### 1. What this domain is for

We run LinkedIn outreach in **HeyReach**. The company runs on **Pipedrive**. This domain is the automatic bridge between them: every invite, acceptance, message and reply on LinkedIn becomes a person, a lead, an activity and — when it's a real reply — a Slack notification to the team.

If it stops, nothing breaks loudly. LinkedIn keeps working, the CRM just quietly stops learning about it, and Melisa stops being told when someone replies. **That is the failure to fear: silence that looks like calm.**

### 2. The pieces

| Piece | Where | Role |
|---|---|---|
| HeyReach campaigns | HeyReach | send the invites and messages |
| **WF-1 HeyReach Receiver** | n8n, ACTIVE | the whole bridge — 126 nodes, one workflow |
| Pipedrive | CRM | organisations, persons, leads, activities, labels |
| Slack `#lead-processing` (`C07LTD8UT70`) | Slack | where a reply is announced |
| Slack ops (`C0B8GCVNR5W`) | Slack | where problems are announced |
| WF-ERR | n8n | catches any crash |

There is **no reconciler for HeyReach**. If an event is lost, HeyReach's own retry (up to 5 times over 24 hours) is the only recovery.

### 3. The flow, in one paragraph

HeyReach posts an event to a private webhook URL. WF-1 rejects it if it has seen the same event in the last 48 hours. It reads the campaign name for an event marker, checks whether this campaign's lead was deliberately archived (if so it stops, silently), then finds or creates the organisation and the person, moves the person's stage forward if the event is a step up, finds or creates *one lead for this campaign*, adds the appropriate labels without ever removing any, and writes an activity. If the event was a reply, it decides whether this is the first reply worth announcing and posts it to `#lead-processing`.

### 4. The rules a human needs to know

**One lead per campaign.** A person in three campaigns gets three leads. The lead is matched on its **Campaign field**, never on its title — the title is a convention (`{campaign id} - {campaign name} - {name}`) and titles get edited.

**Stages only move forward.** Invited (1) → Accepted (2) → First follow-up sent (3) → Replied (4). A late-arriving older event cannot pull someone backwards.

**Labels are cumulative.** We add *Cold* and, on a reply, *3. Responded*. We never remove a label. If a label disappears, something else did it.

**"3. Responded" is a handover trigger.** Writing it hands a human a lead as warm. No automated event may set it without an engagement check — a bounce or an unsubscribe must never look like a reply. There is a linter rule enforcing this across the whole estate.

**Archived lead = ignore.** If someone archived the campaign lead, the event passes through in total silence: no lead, no activity, no label, no post anywhere. Someone made that decision on purpose. *(Detecting this needs a special search — the ordinary lead endpoints cannot see archived leads at all. If the search itself fails, WF-1 deliberately does **not** block: a real reply must never be silenced by a lookup we couldn't perform.)*

**A personal LinkedIn chat is never announced.** If the event has no campaign, it's the exec's own conversation. The CRM activity is still written so the history exists; nothing is posted anywhere — not `#lead-processing`, not `#alerts`, not ops. This silence is deliberate; do not "restore" it as a quiet line somewhere.

**One alert per person per campaign, recorded on delivery.** The suppression key is the Pipedrive person id (or the canonical LinkedIn identity), and it is only written after Slack confirms the message landed in the team channel. Two consequences: a failed Slack post does not burn that person's only alert, and archiving a lead does not reset their suppression.

**Event campaigns need two brackets.** A campaign named `[Events Visiting] [Ai4 2026]` writes the person's Hypothesis and Event Name. One bracket, an empty second bracket, or one longer than 60 characters → the event fields are skipped and Slack warns, naming the campaign. **Do not rename live campaigns mid-flight.**

**The follow-up task is off.** `create_assignment_task: false` — a different automation owns task creation.

### 5. When something looks wrong

| What you see | What it usually is | What to do |
|---|---|---|
| A reply is in Pipedrive but nobody was told | suppression, or no campaign on the event | open the execution, read `__alert_reason`: `already_delivered`, `manual_conversation`, `first_alert`, `no_identity` |
| Two alerts for the same person | the person couldn't be identified at all — that path alerts on purpose rather than risk losing a first reply | look for `no_identity` |
| A duplicate lead appeared | the archived-lead probe couldn't be read, so it failed open | look for `probe_unreadable` |
| Nothing happened at all | duplicate within 48h, or the archived-lead rule | check the dedupe and the `__ar` block |
| `Event Marker Warn` in Slack | a campaign name lost its brackets | fix the name in HeyReach |
| Silence for hours on a working campaign | the webhook may be unregistered on the HeyReach side | check WF-1's execution list; if it is empty, the problem is upstream of n8n |

**The daily safety nets:** the morning digest (07:00) reports HeyReach volume in the last 24 hours, so a dead webhook shows up as a zero. WF-ERR posts any crash immediately, with the verdict *"DELAYED — HeyReach retries, the event should come back on its own"*.

### 6. Restarting and replaying

> **Corrected 2026-09-02.** This section previously said "do nothing first — HeyReach retries, so
> it's a delay, not a loss." That was taken from WF-ERR's verdict table, and the verdict was wrong.
> WF-1 answers `{"ok": true}` with HTTP 200 from the Webhook node **before any processing runs**, so
> HeyReach is told the event was accepted and will **not** retry a processing failure — its 5×/24h
> retry only covers a delivery failure (n8n unreachable, or a 5xx at the HTTP layer). WF-1 has no
> reconciler. WF-ERR's verdict has been changed to `LOST`.

- **A failed HeyReach event is LOST.** Nothing will re-deliver it, and nothing will replay it. Repair
  it by hand from the HeyReach inbox, using the campaign and profile URL in the failed execution.
  *(This is the one open design question in this domain: making WF-1 respond **after** processing
  would turn HeyReach's retry into a real safety net, at the cost of webhook latency. The 48-hour
  dedupe already handles the duplicate delivery that would come with it.)*
- **To replay by hand:** POST the same payload to the WF-1 webhook. Safe — the 48-hour dedupe rejects exact repeats, stages only move forward, labels only accumulate.
- **Do not** bulk-replay a campaign's history. Alerts would stay suppressed (fine) but activities would duplicate (not fine).
- **After changing Pipedrive fields or labels:** run `WF-0 - Discovery` by hand. It reads Pipedrive's field, label, user and activity-type definitions and produces the CONFIG block WF-1 depends on. Those long hex strings in CONFIG are Pipedrive field keys; if a field is recreated, its key changes and WF-1 silently writes nothing.

### 7. HeyReach and the DNC registry — the honest picture

**HeyReach replies do not reach the do-not-contact registry.** The workflow written to do that (`heyreach_reply_to_dnc_ledger`) has never run and nothing calls it.

**There is no HeyReach write path out of the registry either.** The projector (`dnc_projections_sweep`) can set a DNC field in Pipedrive and unsubscribe in Smartlead; for HeyReach it only *counts* what is pending. And the projector itself has not run in the last 19 days and has both its write switches off.

**What that means in practice.** For LinkedIn, "do not contact" is enforced by:
1. asking the gate (`dnc_pre_add_gate`) before loading a campaign list — a manual step someone has to remember;
2. the Pipedrive labels WF-1 maintains, which a human reads.

There is no automatic suppression inside HeyReach. **If someone tells us on LinkedIn to stop, the only thing that records it is the CRM activity and whatever a human does next.** That is the largest known gap in this domain and it should be on the "what's still open" slide.

### 8. Dependencies at a glance

```
HeyReach ──webhook──► WF-1 ──► Pipedrive (org, person, lead, activity, labels)
                       │
                       ├──► Slack #lead-processing   (reply alerts, on delivery)
                       ├──► Slack ops / #alerts      (problems only)
                       └──► WF-ERR                   (on crash)

WF-0 - Discovery ──(run by hand)──► the field keys WF-1's CONFIG holds

NOT connected:  WF-1 ──✗──► DNC registry
                DNC registry ──✗──► HeyReach
```

---

## STAGE 3, domain 2 — Smartlead to Pipedrive + DNC

*(source file: `11_DOMAIN_smartlead_to_pipedrive_and_dnc.md`)*

## Domain 2 — Smartlead → Pipedrive (+ DNC)

*Written for someone who has to keep this running without asking the person who built it.*
*State as read live from n8n on 2026-09-02.*

---

### 1. What this domain is for

Cold email goes out through **Smartlead**. This domain turns what happens to those emails — sent, replied, bounced, unsubscribed — into CRM records, Slack notifications, and forwarded emails to the right salesperson.

It is bigger and busier than the LinkedIn side because email has more ways to go wrong, and because **Smartlead does not reliably tell us what happened**. Most of the machinery here exists to work around that.

### 2. The pieces

| Piece | Where | Role |
|---|---|---|
| **WF-2 Smartlead Receiver** | n8n, ACTIVE, 174 nodes | does all the work |
| **WF-2S SENT Reconciler** | n8n, ACTIVE, every 15 min | **the primary source of "email was sent"** |
| **WF-2R REPLY Reconciler** | n8n, ACTIVE, every 15 min | recovers replies the webhook missed |
| **WF-2H Health & Digest** | n8n, ACTIVE, daily 07:15 | compares Smartlead volume against Pipedrive |
| OpenAI | external | reads and classifies each reply |
| Pipedrive, Slack | as in domain 1 | |

#### The one thing to understand before anything else

**Smartlead never sends us a "sent" webhook.** WF-2S polls Smartlead's statistics every 15 minutes and *replays* each send into WF-2's own webhook as if it had arrived normally. In the last 19 days WF-2 ran 130 times; WF-2S and WF-2R ran 1,845 times each. **Almost everything in this domain arrives by replay, not by live webhook.** If WF-2S stops, cold-email leads simply stop appearing in Pipedrive, and nothing else will tell you.

### 3. The flow

#### An email is sent
WF-2S notices it in Smartlead's statistics → replays it into WF-2 → WF-2 skips it if the campaign is a nurture campaign or if it is not the first email in the sequence → otherwise enriches the lead from Smartlead, finds or creates the organisation, person and lead in Pipedrive.

#### Someone replies
The reply arrives (live webhook, or replayed by WF-2R within ~15 minutes) → WF-2 resolves the person and the lead → decides whether this is the first reply worth announcing and posts it to `#lead-processing` → **sends the reply text to an LLM to be classified** → writes the category back to Smartlead → then, depending on the category:
- **Do Not Contact** → unsubscribe the lead in Smartlead **and** put the DNC label on the Pipedrive lead;
- **Interested / Meeting Request / Not Interested / Information Request** → work out which human owns the sending inbox and **forward the thread to them**;
- anything else → no forward.

Finally it unions the lead labels and writes a reply activity.

#### An email bounces
Resolve person and lead → write a bounce note on the lead → count it → ignore a repeat bounce for the same lead within the hour.

#### Someone unsubscribes
Resolve person and lead → unsubscribe in Smartlead → apply the DNC label in Pipedrive.

### 4. The rules a human needs to know

**One switch turns all writing off.** `WRITE_MODE` in WF-2's CONFIG. Every outward call sits behind a gate checking it equals `live`. It has been live since 2026-08-10, and WF-2S raises an alarm if it is left non-live.

**Classification has a guardrail.** The LLM must return valid JSON, a known category, and confidence of at least **0.7**. If any of that fails, the category becomes `Uncategorized`, **Smartlead is left untouched**, and the reply is forwarded to a review address instead of a salesperson. That threshold was chosen from evidence, not taste.

**Forwarding is by inbox address, never by name.** There is a large explicit map from every sending-inbox address to an owner. An address that is not in the map raises an ops warning rather than guessing. If you add a sending inbox in Smartlead, **you must add it to that map** or its replies go to the default.

**Only the first email of a sequence creates CRM records.** Steps 2, 3, 4 of a sequence do not.

**Nurture campaigns are excluded** from the sent path.

**Bounces are not replies — but Smartlead's statistics say they are.** On the statistics endpoint a bounce is recorded as history type `REPLY`; there is no bounce type there. WF-2R therefore builds a bounce index first and excludes them, because a replayed event carries none of the markers the live webhook has. If that index is ever unreadable, bounces start being announced as genuine replies.

**Alerts are recorded on delivery.** Same rule as the LinkedIn side: the suppression key is written only after Slack confirms.

### 5. When something looks wrong

| What you see | What it usually is | What to do |
|---|---|---|
| No new cold-email leads in Pipedrive today | WF-2S is not running, or its campaign rotation is stuck | check WF-2S's last execution and its Slack report; a "stuck" report names the unscanned offset range |
| Replies land in Pipedrive but nobody is told | first-reply suppression, or Slack post failed | check the execution's alert-gate output |
| A reply went to the wrong person | the sending inbox is missing from the forward map | look for `Ops Warn Unknown Inbox`; fix CONFIG, not the node |
| Everything is `Uncategorized` | OpenAI is failing or confidence is low | `Ops Warn Classify` fires; replies still reach the review address, nothing is lost |
| A bounce was announced as a reply | the bounce index was unusable in that cycle | WF-2R reports `__bounce_index_ok` / `__bounce_index_complete` |
| Person created with no company | the real sent payload has no lead data and enrichment did not run | known class; the enriched copy must be read, not the raw payload |
| WF-2 deactivated itself | an out-of-memory event, usually a large replay burst | reactivate, then check burst size before replaying anything |

**The daily safety nets:** WF-2H at 07:15 compares Smartlead volume against Pipedrive and reports how many new leads carry the expected fields; the morning digest at 07:00 reports the same volumes plus an "emails sent with no lead" integrity line. WF-2S watches WF-2H; WF-2R watches WF-2S; WF-2S watches WF-2's write mode. The watchers watch each other on purpose.

### 6. Restarting and replaying — read this before touching anything

**WF-2 answers `200` before it processes. Smartlead never retries.** Recovery is entirely ours, and it depends on the event type:

| Lost event | Recovery |
|---|---|
| **SENT** | automatic — WF-2S re-claims it next cycle (it only marks a send seen after WF-2 accepted it) |
| **REPLIED** | automatic — WF-2R replays within ~15 minutes, same claim-after-success rule |
| **BOUNCED** | **none** — no reconciler covers it |
| **UNSUB** | **none** — no reconciler covers it |

So: for a sent or a reply, **wait one cycle and check the reconciler's next report before hand-repairing anything.** For a bounce or an unsubscribe, the event is gone and the repair is manual.

**If you replay by hand**, note that the replay envelope is shaped **inversely** to the live webhook: `to_email` carries the *lead's* address (on a live webhook it is whoever replied), and the lead's address must also be sent as `sl_lead_email` or WF-2 cannot identify the lead. Getting this wrong is silent — the replay succeeds and nothing happens.

**Never replay ~100 items in one burst.** A burst that size has exhausted the instance's memory before and left the workflow deactivated. WF-2S and WF-2R are capped at 20 per run for exactly this reason; respect the same cap by hand.

### 7. Smartlead and the DNC registry — the honest picture

There are **two separate mechanisms** and they are not connected:

**A. What WF-2 does today (working).** A reply classified as do-not-contact → unsubscribe in Smartlead + DNC label on the Pipedrive lead. Immediate, automatic, and effective for that one person in that one tool. **It writes no row in the DNC registry**, so the registry does not know about it and neither does anything reading the registry.

**B. What the registry does (dormant).** Rows are written by the capture sources, and `dnc_projections_sweep` is supposed to push them out — including unsubscribing the person in Smartlead. That sweep has **not run in the last 19 days and has both write switches set to `false`**.

**What actually protects a Smartlead campaign today:**
1. `dnc_pre_add_gate` — if whoever builds the list remembers to ask it;
2. `dnc_escalation_detector` — hourly, cross-checks live cold campaigns against the registry and shouts if someone on the list is in a sending campaign. **This detects after the fact; it does not prevent.**

**Irreversibility warning.** A Smartlead unsubscribe cannot be undone through the API. Treat any bulk unsubscribe as a one-way door: confirm the candidate list before firing, and read back afterwards — a Smartlead "add lead" call can report success on an add that silently did not happen for an unsubscribed lead.

### 8. Dependencies at a glance

```
Smartlead ──(rarely)──► WF-2 webhook
Smartlead ◄──poll──── WF-2S ──replay──► WF-2 webhook      (SENT: the main path)
Smartlead ◄──poll──── WF-2R ──replay──► WF-2 webhook      (REPLIED: recovery)

WF-2 ──► Pipedrive (org, person, lead, activity, labels, DNC label)
     ├─► Smartlead (category, unsubscribe, forward email)
     ├─► OpenAI    (reply classification)
     ├─► Slack     #lead-processing / ops / #alerts / #gtm-telemetry
     └─► WF-ERR    (on crash)

WF-2S ──watches──► WF-2H, WF-2 write mode
WF-2R ──watches──► WF-2S

NOT connected:  WF-2 ──✗──► DNC registry
                DNC registry ──✗(dormant)──► Smartlead
```

---

## STAGE 3, domain 3 — The do-not-contact registry

*(source file: `12_DOMAIN_dnc_registry.md`)*

## Domain 3 — The do-not-contact registry

*Definition, capture sources, the gate, projections — and what is actually switched on.*
*State as read live from n8n on 2026-09-02.*

---

### 1. What the registry is

One n8n data table (`UOgKwlGsL28lX61O`) holding one row per person we must not put into a cold campaign — **and the reason why**. The reason is the point. "Don't email Barry" is a fact; "Barry replied on 12 Aug and Toby now owns that relationship" is a fact you can act on, defend, and eventually retire.

**A row records:**

| Field | Meaning |
|---|---|
| `identity_key`, `linkedin_url_norm`, `email_lc` | who — canonical LinkedIn URL and lower-cased email |
| `full_name`, `pipedrive_person_id` | who, in human and CRM terms |
| `entry_type` | how strong the signal is (see ladder below) |
| `reason`, `source_ref`, `also_flagged` | why, who/what caused it, and any weaker reasons also seen |
| `source` | which capture source(s) filed it — accumulates, never replaced |
| `status`, `added_at`, `removed_at`, `removed_reason` | lifecycle |
| `projections_state` | whether Pipedrive / Smartlead / HeyReach have been told |
| `correlation_id`, `norm_v` | traceability and the normalisation version used |

**Strength ladder** (never downgrades): explicit opt-out **5** → negative reply **4** → replied **3** → employee connection **2** → manual **1**.

**Reason priority** (0 is strongest): client → unsubscribe → meeting → reply-DNC → sales personal outreach → manual offboard-eligible → event contacted → manual sheet → offboard. When two reasons meet, the stronger wins and **the weaker is kept in `also_flagged`** rather than discarded.

### 2. Entries do not expire

Time-based expiry was retired on 2026-08-31. `computeExpiry()` returns `null` for every entry type; the 1,353 rows that carried an expiry were blanked; `dnc_expiry_job` is deactivated and preserved.

The reasoning is in the code: a six-month timer on *replied* and *negative reply* applied a countdown to precisely the rows that represent a response — it said the response stops mattering, which is backwards. **Retention is now reason-based**: the registry keeps replies, meetings, sales-created/Surfe leads, employee connections and explicit opt-outs, and rows whose only reason was "we contacted them once" get retired explicitly, by a human, via `dnc_s4_retirement_removal`.

### 3. One writer, always

**`DNC__UpsertLedger__v1` is the only thing that writes the registry.** It is marked inactive in n8n, which is correct and normal for a sub-workflow — n8n only requires the caller to be active. It has run over 3,000 times in the last 19 days. **Do not switch it on.**

Every write goes through the same decision:

```
normalise identity → look up by LinkedIn → look up by email
    │
    ├─ two different people?              → CONFLICT: alert a human, write nothing
    │     └─ unless it is the narrow split-identity case:
    │        one side a LinkedIn-only bulk-import row with no email and no person id,
    │        the other carrying a person id, AND the names corroborate
    │        → merge them, tombstone the loser
    ├─ nobody matched                     → INSERT
    ├─ matched, something changed         → UPDATE onto the strongest row,
    │                                       soft-remove any duplicates
    └─ matched, nothing changed           → NOOP
```

Consequences worth remembering:
- **Calling it twice with the same signal is safe** — the second call is a no-op.
- **Identity fields fill in but never overwrite.** A blank email gets filled; a wrong one does not get corrected here.
- **A new signal on a removed or expired row reactivates it** and resets `added_at`.
- **A conflict is a human decision, not a bug.** Auto-merging two different real people would be a data-integrity incident; the code refuses to do it except in the one corroborated shape above.

### 4. The capture sources — and which are actually on

Every source has the same skeleton: a `CONFIG` node with a `FIRE_Sn` boolean, a classifier, a Pipedrive person lookup to get a usable identity, and a call to the ledger. **Dry-run is the default. Nothing writes unless the switch is `true`.**

| Source | What it captures | Switch | Runs today |
|---|---|---|---|
| **S1** `dnc_s1_responded_to_dnc` | Pipedrive people who responded | `FIRE_S1` = **false** | hand-fired, last 18 Aug |
| **S2** `dnc_s2_meeting_to_dnc` | people who booked a meeting (label "5. Meeting" ∪ deal stage "Qualified Meeting Set", Memurai/partner pipeline excluded) | `FIRE_S2` = **false** | hand-fired, last 18 Aug |
| **S3** `dnc_s3_creation_watcher` | leads created by a named salesperson, or by Surfe | `FIRE_S3` = **TRUE** | **every 15 minutes** |
| **S3-backfill** `dnc_s3_surfe_backfill` | the same, historically | `FIRE_S3_BACKFILL` = **false** | never |
| **S4** `dnc_s4_event_populations` | everyone in a given Smartlead/HeyReach campaign ("we touched them once") | `FIRE_S4` = **false** | one bulk load, 14 Aug |
| `dnc_archived_responders_import` | a validated CSV of archived responders | `dry_run` default true | 2 runs, 28 Aug |
| `dnc_wf4_sheet_intake` | a Google Sheet a human fills in | inactive | never |
| `heyreach_reply_to_dnc_ledger` | a LinkedIn reply | inactive | never |

**Read that table twice. S3 is the only source writing to the registry.** Everything else needs a human to fire it, and most would produce a dry-run report if fired today.

#### What S3 can and cannot see
S3 reads the **newest 100 Pipedrive leads** every 15 minutes, newest-first, and remembers the ids it saw last time. It keeps a lead if the creator is one of eight named sales users or the channel is `Surfe`, and rejects automation writes, web-form leads and Memurai leads.

Two limits that matter:
- **It is forward-only.** If it falls behind, leads can pass out of the 100-lead window unseen. An audit of "new rows" measures the backfill, not a rate.
- **It is lead-shaped.** A person created without a lead — or a person plus a deal — is invisible to it, and Pipedrive persons carry no creator field, so there is no equivalent watch for them.

It posts a heartbeat at 23:55 so a silent failure is visible.

### 5. The gate — the only preventive control

`dnc_pre_add_gate`, webhook `{{WEBHOOK_DNC_PRE_ADD_GATE}}`. POST a list of identities, get a verdict per row:

- **`OWN_TEAM`** — an `@janeasystems.com` address; exclude from any list
- **`UNRESOLVABLE`** — no usable email or LinkedIn URL; nothing can be matched
- **`BLOCKED`** — an active registry row exists; the reason is returned
- **`CLEAN`** — no row, or only retired ones (and it says what it used to be)

It is a pure read — no CRM, no sending tool — so you can ask it as often as you like. `dnc_pre_add_gate_monitor` fires a synthetic two-row check every 15 minutes and alerts **once when the gate breaks and once when it recovers**, plus a daily heartbeat.

#### ⚠ The gate has a live trap: batches over 50 rows

The gate answers synchronously for **50 rows or fewer**. Above that it parks the batch in a table called `dnc_gate_queue`, replies `{"queued": N, "eta_minutes": …}`, and expects `dnc_gate_queue_drainer` to process it.

**The drainer has never run and is inactive**, and the monitor's own code states the `dnc_gate_queue` table does not exist. So a caller submitting 51–500 rows gets a confident "queued" and **never receives an answer**. Nothing alerts on it.

**Rule until this is fixed: send the gate at most 50 rows per call.** *(I could not verify table existence from the API — n8n does not expose data tables there — so confirm in the UI before acting on the "table does not exist" claim.)*

### 6. Projections — what is supposed to happen next, and does not

Being on the registry should have consequences in the tools:

| Target | What the projector would do | Status |
|---|---|---|
| Pipedrive | set the DNC field on the person; add the DNC label to any open lead (union, never replacing) | **not running** |
| Smartlead | resolve the lead by email and unsubscribe it | **not running** |
| HeyReach | nothing — there is only a counter of what is pending | **no write path exists at all** |

`dnc_projections_sweep` has **zero executions in the 19-day retention window** and its CONFIG carries `FIRE_PIPEDRIVE: false` and `FIRE_SMARTLEAD: false`. So even if someone invoked it today, it would report a dry run.

Every row the ledger has inserted since at least 14 August still carries `projections_state` = pending.

#### So what actually stops a send today?

1. **The gate** — but only if the person building the list remembers to ask it.
2. **`dnc_escalation_detector`** — hourly, cross-references live Smartlead cold campaigns against the registry's active rows and posts every hit to ops. Nurture campaigns are excluded; it reads up to 500 leads per campaign and says so when a campaign is bigger than that. **This finds people who are already in a campaign. It does not stop them being added.**
3. **WF-2's own reply path** — unsubscribes in Smartlead directly when a reply classifies as do-not-contact. Effective, immediate, and completely independent of the registry.

**Plain statement for the deck: the registry is currently a well-maintained record with no automatic effect on the sending tools.** The enforcement is a manual gate call plus an hourly detector.

### 7. When something looks wrong

| What you see | What it means | What to do |
|---|---|---|
| Escalation alert: "X is on DNC and in campaign Y" | someone was added to a campaign without a gate check, or after being registered | remove them from the campaign; the alert names the entry type and reason |
| Gate says `queued` and nothing comes back | the over-50-row trap above | resend in batches of ≤ 50 |
| Gate monitor: "unhealthy" | the gate's synthetic check no longer returns 1 clean + 1 blocked | usually a registry read failure; the recovery alert will follow when it clears |
| A conflict alert from the ledger | one identity resolves to two different registry rows | a human decides; do not auto-merge |
| Registry count not growing | expected — only S3 writes, and only from new hand-created or Surfe leads | check S3's 23:55 heartbeat and the morning digest's DNC line |
| Someone was contacted who should not have been | check, in order: was the gate asked? is there a registry row? is it `active`? did the escalation detector see the campaign (is it >500 leads, or a nurture campaign)? |

### 8. If you need to change something

- **Retire rows:** `POST /webhook/{{WEBHOOK_DNC_S4_RETIREMENT}}` with `{"row_ids": [...], "dry_run": false}`. Dry-run is the default; you must pass `false` explicitly. There is no undo — re-adding means re-filing through the ledger.
- **Import a list:** `POST /webhook/{{WEBHOOK_DNC_ARCHIVED_IMPORT}}` with validated rows. It refuses the whole call if any row has an unknown reason, a `reply_dnc` without a category, or no email and no LinkedIn URL.
- **Turn a capture source on:** flip its `FIRE_Sn` in that workflow's CONFIG node. Fire it once with a small chunk and read the dry-run report first.
- **Turn projections on:** enable one target at a time, smallest chunk first. **The Smartlead half is irreversible** — an unsubscribe cannot be undone through the API. Confirm the candidate list before firing and read back afterwards.

### 9. Dependencies at a glance

```
S1 ─┐
S2 ─┤   (all dry-run except S3)
S3 ─┼──► DNC__UpsertLedger__v1 ──► registry table UOgKwlGsL28lX61O
S4 ─┤         (single writer,             │
import ─┘      idempotent)                │
                                          ├──► dnc_pre_add_gate ──► "may I contact?"  (preventive, manual)
                                          ├──► dnc_escalation_detector (hourly, detective)
                                          ├──► dnc_morning_digest (counts)
                                          └──✗ dnc_projections_sweep  (dormant: no runs, switches off)
                                                    │
                                                    ├──✗ Pipedrive DNC field + label
                                                    ├──✗ Smartlead unsubscribe
                                                    └──✗ HeyReach (no path exists)
```

---

## STAGE 3, domain 4 — n8n conventions and traps

*(source file: `13_DOMAIN_n8n_conventions_and_traps.md`)*

## Domain 4 — n8n conventions and the traps we have paid for

*For whoever has to change a workflow here next.*
*Conventions verified against the live definitions of all 36 workflows on 2026-09-02. Where a rule comes from the project rulebook rather than from n8n, it says so.*

---

### Part A — the conventions

#### A1. The CONFIG node

**Every workflow's second node is a `Set` node called `CONFIG`.** 33 of 36 have one; the three that do not are pre-convention scaffolding and one small monitor.

Everything environmental lives there and nowhere else: Slack channel ids, API base URLs, Pipedrive custom-field keys, owner ids, label ids, thresholds, campaign maps, and the `FIRE_*` / `MODE` / `WRITE_MODE` switches.

**Why it is worth defending:** routing a workflow to a different channel, or turning its writes off, must be **one edit in one visible place** — not a hunt through forty nodes. The linter enforces the negative case (`R06`: a literal channel id anywhere outside CONFIG is a finding).

Two styles exist in the estate — `mode: raw` with a JSON blob (the receivers, the digest, the linter) and the assignment list (the DNC family). Both are fine; the raw style is easier to read for large configs.

#### A2. Dry-run by default — the `FIRE_*` discipline

Nothing that writes to an outside system does so unless a boolean says it may:

| Switch | Workflow | Live value today |
|---|---|---|
| `WRITE_MODE` | WF-2 | `live` |
| `FIRE_S1` / `FIRE_S2` / `FIRE_S3` / `FIRE_S3_BACKFILL` / `FIRE_S4` | the capture sources | false / false / **true** / false / false |
| `FIRE_PIPEDRIVE`, `FIRE_SMARTLEAD` | `dnc_projections_sweep` | **false / false** |
| `FIRE_REVERSAL` | `dnc_label_reversal` | false |
| `dry_run` (request body, default **true**) | the operator tools | must pass `dry_run: false` explicitly to write |
| `create_assignment_task` | WF-1, WF-2 | false |

A new workflow ships with the switch off, is fired once, and its dry-run report is read before the switch is flipped. **The default is always the safe one, and turning it on is a deliberate, separate act.**

#### A3. Pre-fire discipline

*(Project convention — the artifacts live in the build folders, e.g. `ARCHIVED_RESPONDERS_build/ARTIFACT_prefire.md`.)*

Before any bulk write, a pre-fire document is produced that states:
- **where the input came from and how it was counted** — parsed properly, never `wc -l`;
- **every exclusion, with the reason**, and specifically what was *not* excluded despite looking excludable;
- **the classification of every row** and the mechanism that produced it;
- **the ambiguous cases listed individually for a human to decide** — never auto-promoted.

The archived-responders import is the model: a first pass produced 45 "opt-outs" by phrase matching; manual review found most matches were *our own* courtesy wording quoted back inside the reply. After truncating at quote markers in three languages the list fell to 10, and the final ruling was that **no phrase match is ever auto-promoted** — only an explicit label is. The count reached the registry as 10, not 45.

#### A4. The channel map

| Id | Used as | What goes there |
|---|---|---|
| `C07LTD8UT70` | `slack_channel_replies` — **#lead-processing** | reply announcements. Only campaign members ever reach it |
| `C0B8GCVNR5W` | `ops_channel` / `alert_channel` | operational problems, dev summaries, conflict alerts |
| `C0BTUHSSM3K` | `slack_channel_alerts` — **#alerts** | WF-1 / WF-2 alerting |
| `C0BQM1X9ZUY` | `telemetry_channel` — **#gtm-telemetry** | dry-run progress, chunk telemetry, and the linter's findings |
| `C0BTP6VHP1B` | `digest_channel` | the morning digest |
| `C0BFE6KAN8J` | historical default | the fallback inside the shared Send Guard when a workflow sets no guard |

**The split that matters:** routine progress and dry-run chatter go to telemetry; final results and things needing a decision go to ops; person-level announcements go to #lead-processing and only for campaign members.

**Every Slack post passes a `Send Guard`** — the same 1,225-character code node copied into eight workflows. In `MODE: dev` it **throws** if the target channel is not on that workflow's allow-list. It is a deliberate hard failure: better a visible crash than a dry-run summary landing in the team channel.

One exception is pinned on purpose: WF-1's alert-delivery check compares against the literal team channel id rather than reading it from CONFIG, because if CONFIG were ever pointed back at ops, a config-derived check would silently re-mute everyone.

#### A5. Alerts fire once per state change

A scheduled job that posts behind an `IF` must remember what it said last time, or it re-posts on every tick. The gate monitor posts once when the gate breaks and once when it recovers, and keeps the state in the workflow's static data. The linter's `R07` finds the violation.

**The deliberate exception: an unconditional daily digest.** It posts every day, including a wholly green one, precisely so that **a day with no message means the job did not run**. There is no "only post if interesting" gate in the morning digest, and the code says there must never be one.

#### A6. Claim after success, never at decision time

Anything that records "I have handled this" must record it **after** the handling succeeded:
- WF-2S marks a send seen only after WF-2 accepted the replay;
- WF-2R does the same for replies;
- WF-1 and WF-2 write the alert-suppression key only when Slack confirms the post landed.

Claiming at decision time means a failed post burns that lead's only alert, forever.

#### A7. Report "could not read", never "zero"

A count derived from a source you did not verify must be **null**, not 0. The morning digest suppresses new-lead counts and names the reason when the Pipedrive page comes back unsorted; it reports a saturated page as a floor rather than a total; the daily CRM summary distinguishes *"no events received"* (the subscription may be dead) from *"zero real changes"*; the linter reports an unreadable workflow list as unreadable rather than as a clean estate. The linter's `R05` finds the violation.

#### A8. Every workflow points at WF-ERR

34 of 36 set `errorWorkflow: BbrXPABgOaaTJjD6` and `callerPolicy: workflowsFromSameOwner`. Do this on anything new.

#### A9. The sandbox protocol

*(Project convention.)* A change to a live workflow is rehearsed on a **`DEV__`-prefixed twin deployed as a new workflow**, run once end-to-end against real data, before the live one is touched.

**There are no `DEV__` workflows in the instance today** — the twins were cleaned up after use, which is the intended end state. If you see one, it is either in flight or was forgotten.

#### A10. One implementation, embedded — not copied by hand

The linter rules, and the two standing rules embedded in WF-1 and WF-2 (`AR Decide`), are **generated into the workflow from a single source file** by a build script, and the same file is what the tests import. The comment at the top of each says so.

Where this discipline was *not* applied, the estate is already drifting: `dnc_pre_add_gate` and `dnc_gate_queue_drainer` contain byte-identical `Classify Batch` code; the identity normaliser exists as a sub-workflow *and* inlined in three places; the `Send Guard` block is copied verbatim into eight workflows.

#### A11. Rules carry their incident

Every linter rule and every rulebook entry names the incident that bought it. The reason given, verbatim: *"a rule whose reason is forgotten is a rule someone will delete."* Keep doing this.

---

### Part B — the platform traps

These are the ones that have actually broken something here. The first fifteen are enforced daily by `dnc_wf_linter`, which posts only what is **new** or **newly resolved** to `#gtm-telemetry`.

#### B1 — `R01` A `__field` cannot survive a node that replaces `$json`  *(the "B12" class)*
Code nodes, HTTP nodes, data-table nodes and Slack nodes emit a **new** object. A field written upstream is gone. `IF`, `Switch`, `NoOp` and `Filter` pass items through unchanged, which is what makes this invisible — on the canvas the writer and the reader look adjacent with only an `IF` between them.
**Cost:** 53 of 55 Finovate leads created **orphaned**, because a lead-body builder read `$json.__person_id` after a lead-list HTTP call.
**Fix:** read the owning node **by name** — `$('Person Id Final').item.json…` — never `$json` across a replacing node.

#### B2 — `R02` Two producers into one input is a **race**, not a join
n8n runs the target node once **per branch arrival**. Two different nodes feeding one input means it fires twice, and if the target reads either producer by name it throws *"hasn't been executed"*.
**Cost:** five days of I-04 outage.
**Fix:** chain them, or accept it runs twice. A diamond off a single `IF` is fine — those branches are mutually exclusive and the linter knows the difference.

#### B3 — `R03` An `IF`'s output 1 is **FALSE**
Wiring only output 1 means "when NOT true".
**Cost:** ~500 "queue STUCK" alerts, fired on exactly the polls where nothing was stuck.
**Fix:** when only output 1 is wired, say out loud what the false case means.

#### B4 — `R04` A failed data-table op does **not** reliably return `{error}`
Some operations return an error object; others — same table, different operation — **echo the original input items with no marker at all**. A negative test (`if (!x.error)`) therefore cannot work.
**Cost:** `dnc_gate_queue` read back as depth 0, producing ~500 false alerts.
**Fix:** check **positively** for the real row shape. The gate does this correctly: it accepts a queue row only if it has a string `row_key` and a string `status`.

#### B5 — `R05` A missing read is not zero
See A7.
**Cost:** the I-04 686-row delta, and the queue depth above.

#### B6 — `R06` A Slack channel id outside CONFIG
See A4.

#### B7 — `R07` A scheduled alert with no state memory
See A5. **Cost:** 96 identical messages a day, twice over, for five days.

#### B8 — `R08` A manual-mode `Set` node silently drops everything it does not list
Unless `includeOtherFields` is true. Downstream reads of carried context then see `undefined` with no error.

#### B9 — `R09` `/v1/leads` without an explicit sort returns the **oldest** page
**Cost:** a count taken off an unsorted page reported zero new leads on a day with fifty; the page started in 2023.
**Fix:** always `sort=add_time DESC`. And remember the 500-row horizon: a "500-row read" of `/v1/leads` is roughly a 7-day window, not the whole estate.

#### B10 — `R10` Pipedrive search returns **zero** items when `limit >= 500`
It looks like a successful "nothing found".
**Fix:** cap search reads at 100.

#### B11 — `R11` An existence guard that forgets the campaign
The estate rule is **one lead per campaign**. A guard that asks "does this person have a lead?" suppresses a legitimate new one.
**Cost:** a 2025 lead suppressed the same person's 2026 lead.

#### B12 — `R12` `/executions` unfiltered omits crashed runs and under-returns successes
It reported 4 errors against 172 real ones.
**Fix:** use `status=error`, or walk per workflow.

#### B13 — `R13` Data tables referenced by **name** are unreliable
`mode: "name"` has failed live on tables that certainly existed — two confirmed-real tables in one day.
**Fix:** `mode: "id"`, with the id taken from the table's UI URL.
**Live state:** both styles are in use in ACTIVE workflows today. The registry (`UOgKwlGsL28lX61O`) and the I-04 event table are referenced by id; `dnc_gate_queue`, `i04_snapshots`, `i04_walk_staging` and `obs_state` are referenced **by name**. Those are the ones to convert.

#### B14 — `R14` No automated event may set **"3. Responded"** without an engagement gate
That label is the handover trigger — writing it hands a human a lead as warm. Found on the bounce path, and then on the unsubscribe path, which set it unconditionally while its own sibling node deliberately withheld it.
**Fix:** any node writing that label must also check bounce / out-of-office / opt-out / reply class / stage rank.

#### B15 — `R16` `settings.timeSavedMode` is rejected by the public PUT API
`PUT /workflows/{id}` answers **`request/body/settings must NOT have additional properties`**. It is a UI-only field. Strip it from the payload every time — **omitting it does not clear it server-side**, so it comes back on the next read.
**Cost:** WF-1's stable-key deploy was rejected while WF-2's identical deploy succeeded, leaving the two receivers briefly out of step.
**Live state:** **WF-1 still carries `timeSavedMode: "fixed"` and is the only workflow that does.** Anything that redeploys WF-1 must strip it.

*(Numbering note: the rules run R01–R14 and R16 — **R15 does not exist** in either the deployed code or the repository copy. The rulebook's claim of "16 rules" is documentation drift, not a missing rule.)*

#### Traps not covered by a linter rule

**B16 — Archived leads are invisible to the list endpoints.** `/v1/leads` and `/v1/leads?person_id=` **cannot see archived leads at all**, and they ignore `archived_status` everywhere — including `person_id`-scoped reads. Only `/v1/leads/search`, `/api/v2/leads/search` and `/v1/itemSearch` reach them, and all three are term-based: **the term is an index, and the match must be confirmed by person id. A name is never what decides.**
*Cost:* a lead that existed, archived, read as "no lead", producing a wrong Slack message and a near-duplicate lead.

**B17 — A suppression key must never derive from mutable state.** Keying on `lead_id` meant that archiving a lead silently reset that lead's own alert suppression, and a genuine second message was announced as a first alert. Anything that can be archived, converted to a deal, or fall past a read horizon is mutable state. When a key format changes, honour the legacy key on lookup so a deploy does not re-announce history, and write only the new key.

**B18 — Never put a large IIFE in an n8n expression.** A 1,154-character inline function in WF-2's reply alert was rejected by the expression parser and **25 of 25 executions failed**. Worse, code in an expression combined with `onError: continueRegularOutput` fails *silently* while the execution still reports success.
**Fix:** build strings in a Code node; keep expressions to one short clause.

**B19 — An inactive sub-workflow still runs.** `DNC__UpsertLedger__v1` is marked inactive and executes thousands of times a week via `executeWorkflow` (`mode: "integrated"`). Never judge whether something is live by the Active toggle alone; check the execution list.

**B20 — Out-of-memory kills, and workflows that come back switched off.** A large replay burst can exhaust the instance and take a workflow down with it; WF-ERR classifies OOM as an instance-level event rather than a workflow defect. Two defences are in place: the reconcilers cap themselves at 20 replays per run, and the morning digest reports **missed schedules** and failed executions daily.
*This is the one item in this list I could not confirm from the live API today — the retention window does not reach the incident. The defences are visible in the live definitions; the incident itself is recorded in the project rulebook and in WF-ERR's own class table.*
**Fix:** never hand-replay in bursts of ~100; check the morning digest's missed-schedule line as the daily proof that everything scheduled actually ran.

**B21 — Execution history is a rolling ~19-day window.** The oldest execution retained anywhere in this instance today is 2026-08-14. "No executions" never means "never ran". For anything older, Smartlead (2024-09 onwards) and Pipedrive (2020 onwards) are the long-memory sources; n8n is not.

**B22 — n8n's Code node sandbox has no `zlib`/`gzip`.** `Module 'zlib' is disallowed`. Anything that needs compression has to be done outside n8n.

---

### Part C — a checklist for changing a workflow here

1. Read the linter's last post for that workflow — the standing backlog is real.
2. Rehearse on a `DEV__` twin, run it once end-to-end, then delete the twin.
3. Put every new constant in `CONFIG`, never in a node.
4. Ship the write switch **off**; fire once; read the dry-run report; then flip it.
5. Point `errorWorkflow` at WF-ERR and set `callerPolicy: workflowsFromSameOwner`.
6. If you added a data-table node, use `mode: "id"`.
7. If you added a Slack post on a schedule, add state memory — or make it unconditional and daily.
8. If you inserted any node between a writer and a reader, re-check every `$json.__field` downstream (B1).
9. If you are redeploying WF-1, strip `settings.timeSavedMode` from the payload (B15).
10. Sweep the whole estate for the same **pattern**, not just the instance you fixed, and report the sweep. Write the rule down with the incident that bought it.

---

## STAGE 4 — Slide outline

*(source file: `20_SLIDE_OUTLINE.md`)*

## Stage 4 — Slide outline

**Session:** How the outreach-to-CRM system works
**Audience:** Melisa, Sergey, Stefan — business-fluent, not n8n-fluent
**Length:** 30–40 minutes, plus questions
**Rule for the deck:** no tool names on slides beyond HeyReach / Smartlead / Pipedrive / Slack, no workflow names, no node names, no code. Everything below is written so a slide can carry the sentence as-is.

---

### Section 0 — Frame (2 min, 2 slides)

#### Slide 1 — Title
**"From an outreach message to a CRM record — how the machine actually works"**
Sub-line: *what runs by itself, what needs a person, and what to do when it looks wrong.*

#### Slide 2 — Why we're here
Three sentences:
- You depend on this system daily, but only one person can currently explain it.
- Today you get the map, the failure signals, and the list of what is still open.
- Nothing here is a proposal — it is a description of what is running right now.

---

### Section 1 — The whole system in one picture (6 min, 3 slides)

#### Slide 3 — The one-line version
> **Two outreach channels feed one CRM, one alerting channel, and one do-not-contact record — and a set of small watchdogs whose only job is to notice when that stops happening.**

#### Slide 4 — The picture (one diagram, in words)
Left to right, four columns:

1. **We reach out** — LinkedIn (HeyReach) and cold email (Smartlead).
2. **Something happens** — invite accepted, message sent, reply, bounce, unsubscribe.
3. **The bridge** — takes each event, works out who the person is, finds or creates their record, moves them along the pipeline, records the conversation, and decides whether a human should be told.
4. **The result** — a person, a company, a lead and an activity in Pipedrive; a message in the team channel when someone actually replies; a forwarded email to the salesperson who owns that inbox.

Underneath, a fifth band across the whole width: **the watchdogs** — the jobs that check the bridge is still working and post one morning summary.

*Speaker note:* the bridge is two big automations, one per channel, plus about a dozen small ones. Twenty-one are running right now; another fifteen are built and switched off.

#### Slide 5 — The five promises the system makes
1. **Every campaign event ends up in the CRM.**
2. **A real reply reaches a human, once — not twice, not never.**
3. **Nothing we do removes information.** Labels only accumulate; stages only move forward.
4. **A decision someone made by hand is respected.** If a lead was archived on purpose, the automation stays out of the way.
5. **Silence is never ambiguous.** Every daily job posts even when the news is "all fine", so a missing message means the job did not run.

*Speaker note:* promise 5 is the one to dwell on. It is why the channels look chatty.

---

### Section 2 — The four domains (14 min, 8 slides)

#### Slide 6 — LinkedIn → CRM: what it does
Every invite, acceptance, message and reply becomes: the right company, the right person, **one lead per campaign**, an activity with the message text, and — for a reply — a notification to the team channel.

#### Slide 7 — LinkedIn → CRM: the rules worth knowing
- **One lead per campaign.** Three campaigns, three leads. Matched on the campaign field, never on the lead title.
- **Stages only move forward.** A late event cannot pull someone backwards.
- **Archived means leave it alone.** No lead, no activity, no label, no message — total silence.
- **A personal LinkedIn chat is never announced.** The conversation is still recorded in the CRM; nobody is notified. That is deliberate.
- **One notification per person per campaign** — and it only counts as sent when Slack confirms it landed.
- **Event campaigns need their name formatted correctly** (`[Events Visiting] [Ai4 2026]`). Rename a live campaign and the event fields stop being filled — and you get told.

#### Slide 8 — Email → CRM: what it does
Sent, replied, bounced, unsubscribed. Same CRM outcome, plus three things LinkedIn does not have:
- **every reply is read and classified** (interested, meeting request, not interested, information request, out of office, wrong person, do not contact, …);
- **forwardable replies are emailed to the salesperson who owns that sending inbox**;
- **a "do not contact" reply unsubscribes them immediately.**

#### Slide 9 — Email → CRM: the one fact that explains everything else
> **The email tool does not tell us when it sends an email.**

So we ask it, every fifteen minutes, and feed the answer back in as if it had told us. The same trick recovers replies that go missing.

In the last three weeks: the live channel fired **130 times**; the two catch-up jobs fired **1,845 times each**.

*Speaker note:* this is why there are so many moving parts on the email side, and why "the catch-up job stopped" is the single most important failure to notice. Also worth saying plainly: **a lost bounce or a lost unsubscribe is not recovered by anything.**

#### Slide 10 — The do-not-contact record: what it is
A list of people we must not put into a cold campaign — **and the reason why**, because the reason is what lets us defend it and eventually retire it.

Reasons, strongest first: they explicitly opted out → they told us no → they replied → they booked a meeting → a salesperson owns them personally → they came in through an event → someone added them by hand.

**Entries no longer expire on a timer.** Since late August, retention is by reason, not by clock: a reply does not stop mattering after six months.

#### Slide 11 — The do-not-contact record: how someone gets on it, and how we check
**Getting on it** — one component does all the writing, and refuses to merge two people who only look alike. When it cannot tell, it asks a human.

**Checking** — there is a service you can ask before loading a list: *may I contact these people?* It answers per row: clean / blocked / our own team / cannot identify. It is checked automatically every fifteen minutes to prove it still gives the right answers.

#### Slide 12 — The do-not-contact record: the honest gap
Say it plainly:

> **The record is well maintained. It currently has no automatic effect on the sending tools.**

- The piece built to push it out to Pipedrive and the email tool **has not run in the last three weeks**, and its two switches are off.
- **There is no path to LinkedIn at all** — replies on LinkedIn never reach the record, and the record cannot reach HeyReach.
- What actually protects a campaign today: **someone remembering to ask the checking service**, plus an hourly detector that shouts if a listed person is found inside a live campaign. **That detects; it does not prevent.**

*Speaker note:* this is the most important slide in the deck. Do not soften it, and do not fix it live — bring it to the "still open" section with a proposed decision.

#### Slide 13 — The safety net around all of it
- Every automation reports its failures to **one place**, in plain language, with a verdict: *delayed and will come back on its own* / *recoverable, wait one cycle* / *lost, repair by hand*.
- A **daily digest at 07:00** — volumes on both channels, CRM counts, do-not-contact counts, gate health, failures in the last 24 hours, and anything scheduled that did not run.
- A **daily conventions check** that reads every automation and reports only what changed.
- **Watchdogs watching each other:** the sent-catch-up watches the health digest, the reply-catch-up watches the sent-catch-up.

---

### Section 3 — What to do when something looks wrong (7 min, 4 slides)

#### Slide 14 — The three signals, in order
1. **A message in ops** — something failed; the message says whether it will fix itself.
2. **No morning digest** — the daily job did not run. This is more serious than a bad number in the digest.
3. **A quiet channel on a busy day** — no reply notifications while campaigns are clearly sending. Silence is the failure mode to distrust.

#### Slide 15 — The five questions to ask, in this order
1. **Is anything actually broken, or just late?** The failure message says which.
2. **Which channel?** LinkedIn or email — they fail differently.
3. **Did the CRM get it, and only the notification is missing?** Usually yes, and that is much less serious.
4. **Did the catch-up job run in the last fifteen minutes?** If yes, wait one cycle before doing anything by hand.
5. **Is anything scheduled overdue?** The morning digest answers this.

#### Slide 16 — What fixes itself, and what does not
| Situation | Recovery |
|---|---|
| A LinkedIn event failed | **Comes back on its own** — the tool retries for 24 hours |
| An email send was missed | **Automatic** — the catch-up job re-claims it next cycle |
| A reply was missed | **Automatic** — recovered within ~15 minutes |
| A bounce or unsubscribe was missed | **Not recovered by anything** — manual repair |
| The daily digest did not post | **Not automatic** — someone has to look |

*Speaker note:* the recurring theme — **wait one cycle before hand-repairing anything.** Manual repair on top of an automatic one is how duplicates get created.

#### Slide 17 — Two things never to do
1. **Never bulk-replay.** Replaying ~100 items at once has taken the whole system down before and left an automation switched off. The catch-up jobs deliberately do twenty at a time.
2. **Never bulk-unsubscribe without confirming the list first.** Unsubscribing in the email tool cannot be undone.

---

### Section 4 — What is manual, and why (5 min, 3 slides)

#### Slide 18 — Manual on purpose
| Manual step | Why it stays manual |
|---|---|
| Deciding whether two look-alike records are the same person | Merging two different real people is a data-integrity incident. The system refuses and asks. |
| Retiring someone from the do-not-contact record | Removing a protection is a business decision, not an automatic one. |
| Promoting an ambiguous reply to "explicit opt-out" | Phrase-matching got this wrong: most matches were **our own** wording quoted back inside the reply. First pass said 45; the truth was 10. Nothing is auto-promoted now. |
| Turning any bulk write on | Everything ships switched off and is fired once in dry-run first. |

#### Slide 19 — Manual by omission (i.e. it should probably be automatic)
| Manual step | Consequence today |
|---|---|
| Remembering to ask the checking service before loading a list | It is the only preventive control we have |
| Filing "responded" and "booked a meeting" people onto the record | Those two capture routes are built but switched off — someone fires them by hand |
| Anything at all to do with LinkedIn and do-not-contact | No automatic path exists in either direction |
| Pushing the record out to the sending tools | Built, switched off, has not run in three weeks |

#### Slide 20 — Where a person is genuinely required
Reading the ten ambiguous replies. Deciding whether an event campaign name is right before it goes live. Deciding who owns a newly added sending inbox. Deciding when a relationship has ended.

*Speaker note:* these four are not automation gaps. They are judgement, and the system is built to route them to a person rather than guess.

---

### Section 5 — What is still open (5 min, 3 slides)

#### Slide 21 — The three decisions I need from you
1. **Do we turn the do-not-contact projections on?** Today the record has no automatic effect on the sending tools. Turning it on is a one-way door for the email half — an unsubscribe cannot be undone. *(Recommendation: yes, Pipedrive half first, in small batches, with a read-back.)*
2. **Do the "responded" and "meeting" capture routes get switched on and scheduled?** Right now only one of the four routes runs by itself, and it only sees hand-created and Surfe leads.
3. **What do we do about LinkedIn and do-not-contact?** There is no path in either direction. Everything else in this deck has an answer; this one does not.

#### Slide 22 — The known holes, stated plainly
- **Lists over 50 people sent to the checking service get an answer that never arrives.** Batches must stay at or under 50 until it is fixed. *(Being verified.)*
- **A missed bounce or unsubscribe is gone.** No catch-up job covers those two.
- **The one route that runs by itself only sees the newest hundred leads**, and only leads — a person created without a lead is invisible to it.
- **The weekly full CRM sweep is switched off.** We have daily change detection only, which cannot see anything the CRM does not notify us about.
- **Our own history only goes back about three weeks.** Anything older has to come from the CRM or the email tool.

#### Slide 23 — What good looks like in 30 days
- The do-not-contact record has an automatic effect on at least one sending tool.
- Every capture route either runs on a schedule or is deleted.
- The over-50 dead end is closed.
- Someone other than me has followed the "when something looks wrong" page end to end, on a real incident.

---

### Timing summary

| Section | Slides | Minutes |
|---|---|---|
| Frame | 1–2 | 2 |
| The whole system | 3–5 | 6 |
| The four domains | 6–13 | 14 |
| When something looks wrong | 14–17 | 7 |
| What is manual | 18–20 | 5 |
| What is still open | 21–23 | 5 |
| **Total** | **23** | **~39** |

Cut first if short on time: slide 7 (compress into 6) and slide 20. Never cut slides 12, 16, 17 or 21.

---

### Handouts

Put two one-pagers on the table rather than in the deck:
1. **"When something looks wrong"** — slides 14–17 as a single printed page.
2. **"Who to tell, and what fixes itself"** — the recovery table plus the two never-dos.
