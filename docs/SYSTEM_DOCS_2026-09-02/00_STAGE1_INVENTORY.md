# Stage 1 — n8n workflow inventory

> **⚠ SUPERSEDED IN PART — 2026-09-03: the I-04 simplification.**
> `dnc_i04_daily_summary` and `dnc_i04_weekly_reconciliation` were retired (deactivated and
> preserved). `dnc_i04_event_receiver` stays as a silent change log, and a new
> `dnc_i04_event_log_prune` keeps 90 days. The morning digest no longer reports I-04 status; it
> reports `CRM change log N events`. Tables `i04_snapshots` and `i04_walk_staging` are now orphaned
> and are referenced by name — do not build on them.
> Detail: [`I04_SIMPLIFY_2026-09-03/REPORT.md`](../I04_SIMPLIFY_2026-09-03/REPORT.md) · rule R-G in `RULEBOOK.md`.



**Instance:** `https://janea-systems-2025.app.n8n.cloud`
**Read live from the n8n public API on 2026-09-02 (~07:00Z).** Nothing here comes from chat history, task logs or memory — every field below was read from the live workflow definitions and the live execution log.
**Read-only:** only `GET /api/v1/workflows` and `GET /api/v1/executions` were called. No writes, no activations, no deploys.

**Totals:** 36 workflows — **21 ACTIVE**, 15 inactive. 1,090 nodes in total.

### About the "last execution" column

The n8n execution log is a rolling window, not a full history. The oldest execution retained **anywhere in the instance** right now is `2026-08-14T01:15Z` — i.e. a **~19-day retention horizon**, and it is consistent across all high-volume workflows. So "no executions" means *no executions since ~14 Aug*, not *never ran*. Where that distinction matters I say so.

Execution counts marked `3000+` hit my paging cap; the real number is higher.

---

## A. ACTIVE workflows (21)

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

## B. INACTIVE workflows (15)

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

## C. Flags

### C1. Looks dead — but is switched ON

These are ACTIVE (so their webhook path is live and reachable) yet have not run once in the 19-day window:

| Workflow | Why it matters |
|---|---|
| **dnc_projections_sweep** | This is the *only* thing that pushes registry state outward — Pipedrive person DNC field, lead labels, Smartlead unsubscribe. If it has not run in 19 days, nothing that entered the registry in that period has been projected anywhere. **And its live CONFIG carries `FIRE_PIPEDRIVE: false` and `FIRE_SMARTLEAD: false`, so even if it were invoked today it would report a dry run.** Question for you: intentional, or has it silently stopped being invoked? |
| **dnc_s3_surfe_backfill** | A one-shot backfill left switched on. Harmless but its webhook is live. |

### C2. Live but hand-fired only — and mostly switched to dry-run

`dnc_s1_responded_to_dnc`, `dnc_s2_meeting_to_dnc`, `dnc_label_reversal`, `dnc_s4_retirement_removal`, `dnc_archived_responders_import` are all ACTIVE webhooks with no caller anywhere in the instance — they only run when a human posts to them. S1 and S2 have not been fired since 18 Aug.

**Live switch state, read from the deployed CONFIG nodes:**

| Switch | Value |
|---|---|
| `FIRE_S3` (creation watcher) | **true** |
| `FIRE_S1`, `FIRE_S2`, `FIRE_S4`, `FIRE_S3_BACKFILL`, `FIRE_REVERSAL`, `FIRE_PIPEDRIVE`, `FIRE_SMARTLEAD` | **false** |

So of the four DNC capture sources, **only S3 both runs on its own and is permitted to write.** Question: is that the intended steady state, or are S1/S2 supposed to be scheduled?

### C2b. One live trap found in Stage 2 — belongs on the Stage 1 flag list

**`dnc_pre_add_gate` answers synchronously for batches of 50 rows or fewer.** Above that it parks the batch in a queue table, replies `{"queued": N, "eta_minutes": …}`, and relies on `dnc_gate_queue_drainer` to process it. The drainer is **inactive and has never run**, and the gate monitor's own code (dated 2026-08-31) states the `dnc_gate_queue` table **does not exist**. A caller submitting 51–500 rows therefore gets a confident "queued" and never receives an answer. Nothing alerts on this.

*Data tables are not exposed by the n8n public API, so I could not verify the table's absence myself — please confirm in the UI. Until then: keep gate batches at or under 50 rows.*

### C3. Off, but something depends on them

| Workflow | Consequence of it being off |
|---|---|
| **dnc_gate_queue_drainer** | The gate parks requests in `dnc_gate_queue` when queue depth is exceeded, and answers "queued". With the drainer off, a queued item is never classified and never gets a verdict. Today's traffic is being answered synchronously, so this has not bitten — but it is a live trapdoor. |
| **heyreach_reply_to_dnc_ledger** | HeyReach replies never become DNC entries. WF-2 does this for email; there is no equivalent path for LinkedIn. |
| **dnc_expiry_job** | Nothing ages the registry. Combined with `dnc_expiry_null_oneshot` having blanked `expires_at` on 31 Aug, the registry is now effectively permanent. Reads as deliberate — **please confirm.** |
| **dnc_i04_weekly_reconciliation** | The weekly full-estate sweep does not run; only the daily event-based summary does. The daily one cannot see changes Pipedrive does not send a webhook for. |

### C4. Duplicates / overlapping pairs

| Pair | Note |
|---|---|
| **WF-1 HeyReach Receiver** (126 nodes) vs **WF-1-DO NOT USE** (89 nodes) | Old copy on a live-but-unused test webhook path. Rename is doing the safety work; the path is still reachable. |
| **dnc_pre_add_gate** vs **dnc_gate_queue_drainer** | Both contain a byte-identical `Classify Batch` (2,330 chars) and `Normalize Batch`. Copy-paste, not a shared sub-workflow — they will drift. |
| **dnc_expiry_job** vs **dnc_expiry_null_oneshot** | The second exists to undo the first. Both off. |
| **dnc_i04_daily_summary** vs **dnc_i04_weekly_reconciliation** | Two generations of the same CRM-diff idea; daily is live, weekly is off. |
| **smartlead_observability_readonly** vs **WF-2S / WF-2R** | Three Smartlead pollers with three separate watermark stores; only two are live. |
| **DNC__NormalizeIdentity__v1** vs inline copies | The normaliser exists as a sub-workflow *and* is inlined in UpsertLedger, CheckLedger, and the gate. |
| **Heartbeat / send-guard blocks** | The same 1,225-char `Send Guard` code node appears in at least 8 workflows verbatim. Same story: copied, not shared. |

### C5. Things I could not explain from the definitions — questions for you

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

## D. Conventions visible across the whole instance

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
