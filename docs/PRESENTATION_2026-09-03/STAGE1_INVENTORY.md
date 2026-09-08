# Stage 1 — Inventory of the live n8n estate

**Instance:** `janea-systems-2025.app.n8n.cloud`
**Read from the API at 2026-09-03 08:20Z.** Every field below comes from the live workflow
definitions and the live execution log. Read-only: only `GET /api/v1/workflows` and
`GET /api/v1/executions` were called.

**Totals at first read: 37 workflows — 22 ACTIVE, 15 inactive, 925 nodes, 309 of them Code nodes.**

> **⚠ Updated 2026-09-03 09:10Z. Current state: 40 workflows, 20 ACTIVE, 944 nodes.**
> Three sets of changes since this was first read, all in §E: the **I-04 simplification** (§F), the
> **archive pass** (§G — 12 workflows deactivated and renamed `ARCHIVE__*`, nothing deleted), and
> the concurrent session's **WF-1** work. Rows below are annotated where they moved; treat §E–§G as
> the current truth where they disagree with the tables.

### Two things to know before reading the table

**"Last execution" is a ~20-day window.** The oldest execution retained anywhere in the instance is
`2026-08-14 13:30Z`. "Never" below means *not since 14 August*, not *never ran*.

**A concurrent session is making live fixes** (duplicates/staticData, projections, WF-1 ack). Every
workflow's `versionId` was captured at read time; anything that changes underneath this document is
listed in §E at the end.

---

## A. ACTIVE workflows (22)

| # | Name | id | Nodes | Trigger | Last run | Runs (20d) | What it does |
|---|---|---|---|---|---|---|---|
| 1 | **WF-1 HeyReach Receiver** | `2jdjKM2NJr473GdA` | 126 | webhook `hr-eGVpz…` | 09-03 04:40 | 458 | Turns every LinkedIn event from HeyReach — invite sent, invite accepted, message sent, reply — into Pipedrive: finds or creates the company, the person and one lead per campaign, moves the person's stage forward, adds labels, logs the conversation, and announces real replies in Slack. |
| 2 | **WF-2 Smartlead Receiver** | `jp7rum9Z0YDJkQWv` | 174 | webhook `{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` | 09-01 18:01 | 130 | The same job for cold email, plus the things only email has: it reads each reply with an LLM, classifies it, writes the category back to Smartlead, forwards interesting replies to the salesperson who owns that inbox, and unsubscribes people who ask to stop. |
| 3 | **WF-2S SENT Reconciler** | `6Y92ryBwYoy6z0Jx` | 24 | schedule, 15 min | 09-03 08:15 | 1,899 | Asks Smartlead every 15 minutes which emails actually went out and feeds them into WF-2 — because Smartlead never tells us on its own. Also watches that the daily health digest still runs and that WF-2 is still in live mode. |
| 4 | **WF-2R REPLY Reconciler** | `U8Bb7Pdq7S6nzYPa` | 25 | schedule, 15 min | 09-03 08:15 | 1,899 | The same recovery for replies: finds replies the webhook missed and replays them, carefully excluding bounces, which Smartlead reports in the same place as replies. Also watches that WF-2S is alive. |
| 5 | **WF-2H Health & Digest** | `nK3yIOqRcBearV8s` | 9 | schedule, daily 07:15 | 09-03 07:15 | 20 | Once a day compares how much Smartlead says it sent against what arrived in Pipedrive, and reports how many new leads carry the fields and labels they should. |
| 6 | **WF-ERR Error Handler** | `BbrXPABgOaaTJjD6` | 12 | error trigger | 09-02 12:18 | 184 | The single place every failure in the estate surfaces: it pulls the failed run, classifies the failure, says whether the lost event will come back on its own, suppresses storms, and posts one Slack message. |
| 7 | **dnc_pre_add_gate** | `9aP2dP0jgAPFGDvA` | 14 | webhook `{{WEBHOOK_DNC_PRE_ADD_GATE}}` | 09-03 08:15 | 3,500+ | The "may I contact these people?" service — you send it a list, it answers clean / blocked / our own team / can't identify, per row, against the do-not-contact registry. |
| 8 | **dnc_pre_add_gate_monitor** | `g8MUOKFlUaeVrdBx` | 13 | schedule, 15 min + 08:00 | 09-03 08:15 | 787 | Asks the gate a question it knows the answer to, every 15 minutes, and shouts once when the answer goes wrong and once when it comes back. |
| 9 | **dnc_s3_creation_watcher** | `QM21Vd7VId7PBdqh` | 23 | schedule, 15 min + 23:55 | 09-03 08:15 | 1,920 | Watches for leads a salesperson created by hand (or that came from Surfe) and files those people onto the do-not-contact registry, so cold campaigns don't email someone a colleague already owns. |
| 10 | **dnc_i04_event_receiver** | `wqORtqgRJ3W5YvBL` | 5 | webhook `{{WEBHOOK_I04_PD_EVENTS}}` | 09-03 04:40 | 1,562 | Catches Pipedrive's own notifications about leads and people changing and files each one. **Since 2026-09-03 this is all of I-04**: a silent change log, no summaries, no alerts. Untouched by that change. |
| 10b | **dnc_i04_event_log_prune** *(new 09-03)* | `xNQLf4nx9Feo77XZ` | 10 | schedule, daily 06:20 + manual webhook | 09-03 08:45 | 3 | Keeps 90 days of the change log and deletes what ages out, reading only the rows past the cutoff — never the whole table. A no-op until ~24 Nov 2026. |
| 11 | ~~**dnc_i04_daily_summary**~~ **RETIRED 09-03** | `8sT1XjDDVmrz05CA` | 22 → **18** | — | 09-03 08:15 | 690 (5 errors) | Turned yesterday's CRM changes into a Slack summary. **Deactivated and preserved on 2026-09-03**; its 15-minute idle watchdog was removed so it cannot alarm about a summary it no longer produces. See §F. |
| 12 | **dnc_morning_digest** | `qJKfR602wV9yfFrj` | 40 | schedule, daily 07:00 | 09-03 04:00 | 3 | One post every morning answering "is the machine fine?": sending volume on both channels, CRM volume, registry counts, gate health, failures in the last day, and anything scheduled that didn't run. |
| 13 | **dnc_escalation_detector** | `QO1zRhUfG7otk06N` | 20 | schedule, hourly + 06:10 | 09-03 08:00 | 496 | Every hour, cross-checks people on the do-not-contact registry against the lead lists of live cold campaigns and shouts if anyone protected is still sitting in one. |
| 14 | **dnc_wf_linter** | `fziGeigC48aGTLT8` | 8 | schedule, daily 06:40 | 09-03 03:40 | 3 | Reads every workflow in the instance each morning and reports only what newly broke or newly got fixed against a list of rules, each written after a real incident. |
| 15 | **dnc_intent_vs_reality** | `tnW7agCbha7rhNnS` | 9 | webhook `{{WEBHOOK_DNC_INTENT_VS_REALITY}}` | 09-02 12:31 | 23 (1 error) | Takes registry rows and checks whether the protection actually exists in Pipedrive and Smartlead, then compares that against what the registry claims about itself. |
| 16 | **dnc_s1_responded_to_dnc** | `BxJZmz1HY5AdaQqE` | 17 | webhook, hand-fired | 08-18 07:52 | 36 | Files a supplied list of people who replied onto the registry. Nothing calls it; a human posts to it. |
| 17 | **dnc_s2_meeting_to_dnc** | `E0oTTvHHQ0hVTNDD` | 17 | webhook, hand-fired | 08-18 08:02 | 19 (1 error) | The same for people who booked a meeting. |
| 18 | **dnc_s3_surfe_backfill** | `1fpep0U4XC8KNzta` | 18 | webhook, hand-fired | **never** | 0 | The historical version of #9 — pages back through older leads instead of watching new ones. |
| 19 | **dnc_s4_retirement_removal** | `DYb9jArdS7xKs3nA` | 7 | webhook, hand-fired | 08-26 16:34 | 16 | Retires named rows from the registry. Dry-run unless you explicitly say otherwise. |
| 20 | **dnc_archived_responders_import** | `07sGtABZiqLrBChX` | 8 | webhook, hand-fired | 08-28 13:15 | 2 | Imports a validated list of past responders onto the registry, refusing the whole batch if any row is malformed. |
| 21 | **dnc_label_reversal** | `LQRfmEl4Wv0qpXsI` | 20 | webhook, hand-fired | 08-14 15:18 | 20 | Repair tool: re-reads leads and strips labels that shouldn't be there. Currently dry-run. |
| 22 | **dnc_projections_sweep** ⚠ | `8qVXtI2ez5o6a9hc` | 41 | webhook, hand-fired | **never** | 0 | The piece that would make a registry entry mean something outside the registry — set the do-not-contact field on the person, label the lead, unsubscribe them in Smartlead. **See §C1.** |

## B. INACTIVE workflows (15)

| # | Name | id | Nodes | Trigger | Last run | Runs | What it does |
|---|---|---|---|---|---|---|---|
| 23 | **DNC__UpsertLedger__v1** | `RolYGL3J2CNg6Yp3` | 14 | sub-workflow | 09-03 02:15 | **3,500+** (2 err) | **Inactive but the busiest thing in the estate** — the single writer to the registry. Decides insert / update / no-op / conflict and merges duplicate identities. Sub-workflows don't need to be "active" to run. |
| 24 | **DNC__CheckLedger__v1** | `kv7reJYAAgsOV33t` | 5 | sub-workflow | 08-26 06:15 | 122 | Read-only twin: given a person, says whether they're on the registry. |
| 25 | **DNC__NormalizeIdentity__v1** | `K2M1Z0m1gKX6LdFI` | 2 | sub-workflow | never | 0 | The identity-cleaning step as its own unit. Nothing calls it; the same logic is copied inside three other workflows. |
| 26 | **dnc_gate_queue_drainer** | `fZl1vpRsQ6Fko3sB` | 6 | schedule, 2 min | never | 0 | Was meant to process gate requests too large to answer immediately. The gate no longer queues anything, so this has nothing to do. |
| 27 | **dnc_expiry_job** | `alpy9rsunqnFwQml` | 17 | schedule, daily 06:00 | never | 0 | Would age out registry entries on a timer. Deliberately retired — see #28. |
| 28 | **dnc_expiry_null_oneshot** | `CUpl8PVOOYXMysVN` | 5 | webhook | 08-31 11:29 | 15 | One-shot that removed the expiry date from every registry row on 31 August, i.e. made entries permanent. |
| 29 | **dnc_i04_weekly_reconciliation** **RETIRED 09-03** | `gjVZkkvm05jj8CNM` | 53 | schedule, 5 min walker | never | 0 | The heavy weekly version of #11: walks the whole CRM, snapshots it, diffs against last week. **Formally retired 2026-09-03** — it never ran once, and its full-estate walk is the out-of-memory shape. Verified inactive by read; deliberately *not* written to, so it is preserved byte-for-byte. |
| 30 | **dnc_s4_event_populations** | `hhdnug5xdFLAxrOg` | 24 | webhook | 08-14 14:27 | 148 | Bulk-loads an entire campaign's contact list onto the registry as "we touched them once". |
| 31 | **heyreach_reply_to_dnc_ledger** | `YgufwSg1EAJaT0ra` | 7 | sub-workflow | never | 0 | Would turn a LinkedIn reply into a registry entry. Nothing calls it. **This is why LinkedIn replies never reach the registry.** |
| 32 | **dnc_check_service** | `PViKUykLaDd7Xze1` | 7 | Slack @mention | never | 0 | A Slack bot: mention it with a name or email and it answers whether they're protected. |
| 33 | **dnc_wf4_sheet_intake** | `bluGflKaUI3bGodQ` | 16 | Google Sheet row | never | 0 | Manual intake: watches a spreadsheet and files new rows onto the registry. |
| 34 | **smartlead_observability_readonly** | `XWtxUzBgNJuguJlg` | 18 | schedule, 30 min | never | 0 | An anomaly watcher for one Smartlead campaign. Its campaign id is still the literal placeholder text. |
| 35 | **WF-0 - Discovery** | `5TCZwAZ3xeXQr0vI` | 7 | manual | never | 0 | Run by hand: reads Pipedrive's field, label, user and activity-type definitions and produces the settings block the two receivers depend on. |
| 36 | **WF-1-DO NOT USE** | `NNOVii5ImjFKDSM0` | 89 | webhook (test path) | never | 0 | The previous generation of WF-1, kept and renamed. |
| 37 | **HeyReach — Phase 0 Payload Capture** | `rnPaPoVQNe2SShkc` | 3 | webhook | never | 0 | Scaffolding from before WF-1 existed: acknowledge the webhook and record what HeyReach sends. |

---

## C. Flags

### C1. ⚠ Switched on, but has never run — and could not write anything if it did

**`dnc_projections_sweep`** is ACTIVE, has **zero executions in the 20-day window**, and its two
write switches are both `false`:

```
FIRE_PIPEDRIVE : false      FIRE_SMARTLEAD : false
```

This is the only mechanism that pushes a registry entry outward into Pipedrive and Smartlead. Both
facts together mean: **nothing has projected the registry anywhere in at least three weeks, and
invoking it today would produce a dry-run report.** Everything in Stage 3 doc 3 depends on this.

**`dnc_s3_surfe_backfill`** is also ACTIVE with zero executions — a one-off backfill tool left
switched on. Harmless, but its webhook is reachable.

### C2. The complete switch state, read from the live settings blocks

| Switch | Workflow | Value |
|---|---|---|
| `FIRE_S3` | s3 creation watcher | **true** |
| `FIRE_S1` · `FIRE_S2` · `FIRE_S4` · `FIRE_S3_BACKFILL` · `FIRE_REVERSAL` · `FIRE_PIPEDRIVE` · `FIRE_SMARTLEAD` | the rest | **false** |
| `WRITE_MODE` | WF-2 | **live** |
| `create_assignment_task` | WF-1 | false |
| `classify_enabled` | WF-2 | true |
| `MODE` | 19 workflows | `dev` everywhere except the morning digest, which is `live` |

**Of the five ways a person can get onto the registry, exactly one runs by itself and is allowed to
write: the creation watcher.** Everything else needs a human to fire it, and most would report a
dry run if fired today.

### C3. Dead — no executions in the 20-day window

Thirteen workflows: `dnc_projections_sweep`*, `dnc_s3_surfe_backfill`*, `DNC__NormalizeIdentity__v1`,
`dnc_gate_queue_drainer`, `dnc_expiry_job`, `dnc_i04_weekly_reconciliation`,
`heyreach_reply_to_dnc_ledger`, `dnc_check_service`, `dnc_wf4_sheet_intake`,
`smartlead_observability_readonly`, `WF-0 - Discovery`, `WF-1-DO NOT USE`,
`HeyReach — Phase 0 Payload Capture`.
*(\* the two marked are ACTIVE, i.e. reachable, unlike the rest.)*

Three of those are dormant **by design** and should not be read as rot: `WF-0 - Discovery` is run by
hand whenever Pipedrive's fields change, `dnc_expiry_job` was deliberately retired, and
`dnc_s3_surfe_backfill` is a one-off.

### C4. Failures in the window — all five distinct causes

| Workflow | When | What failed |
|---|---|---|
| **dnc_i04_daily_summary** | 27, 28, 29, 30, 31 Aug — **five days running** | the summary step could not read the step before it ("node hasn't been executed"). **Fixed on 31 Aug; every run since 1 Sep has succeeded.** The daily CRM summary was silently absent for five days. |
| WF-2R | 27 Aug | the reply-scanning step hit n8n's 60-second limit for a single step |
| WF-2S | 20 Aug | same, on the campaign-picking step |
| dnc_s3_creation_watcher, DNC__UpsertLedger__v1 | 20 Aug | Slack refused the post: `channel_not_found` |
| DNC__UpsertLedger__v1 | 18 Aug | a caller sent a reason the registry did not recognise (`invalid reason meeting_dnc`) — the same day `dnc_s2_meeting_to_dnc` failed |
| dnc_intent_vs_reality | 2 Sep | first-run configuration error, corrected the same minute |

### C5. Duplicates — 38 nodes are exact copies of another node

| Copies | What | Where |
|---|---|---|
| 8 + 7 | the Slack channel-guard block, **in two variants** | 15 workflows. The two variants are the same length and differ only in a hard-coded fallback channel — the drift has already happened |
| 6 | alert-context block | inside WF-1 |
| 4 | alert-context block | inside WF-2 |
| 3 | person/lead lookup block | inside WF-2 |
| 2 | the gate's classification logic | `dnc_pre_add_gate` **and** `dnc_gate_queue_drainer` |
| 2 | lead-selection block | inside WF-2 |
| 2 | chunk-limiting block | s1 and s2 |
| 2 | summary send-guard | i04 daily and weekly |

Plus **whole-workflow duplication**: `WF-1-DO NOT USE` (89 nodes) is a previous copy of WF-1, and
`dnc_i04_weekly_reconciliation` is a second generation of `dnc_i04_daily_summary`.

### C6. Data tables — how they are referenced

Four tables carry all the state. **Referenced by id (reliable):** the registry `UOgKwlGsL28lX61O`
(12 workflows), the CRM-event log `zAW2IYoO6Dj0vdIt`, WF-1's duplicate-guard `euyostwJYfJefItC`.
**Referenced by name (unreliable — see Stage 3 doc 4):** `i04_snapshots` (2 uses in the *active*
daily summary), `i04_walk_staging`, `obs_state`, `dnc_gate_queue`.

The gate itself **no longer references `dnc_gate_queue`** — only the inactive drainer does.

---

## D. Questions for Nik — not guesses

1. **`dnc_projections_sweep`: never run, both switches off.** Is the registry deliberately
   record-only right now, or has this silently stopped? Everything downstream hangs on the answer.
2. **Only `FIRE_S3` is true.** Is "one automatic capture source out of five" the intended steady
   state, or should S1/S2 be scheduled?
3. **`DNC__UpsertLedger__v1` rejected `invalid reason meeting_dnc` on 18 Aug**, the same day `s2`
   failed. Was the meeting source ever accepted, or has it never successfully written a row?
4. **Two Slack `channel_not_found` failures on 20 Aug** in the creation watcher and the ledger. Was
   a channel renamed or archived? Are those alerts still reaching anyone?
5. ~~**`dnc_i04_daily_summary` failed five consecutive days (27–31 Aug)**~~ — **moot as of
   2026-09-03: the summary is retired.** The five-day gap still happened and the underlying events
   are all in the change log, so the period is reconstructible if anyone wants it.
6. **`WF-1` is the only workflow carrying `timeSavedMode` in its settings** — a UI-only field the
   API rejects on write. Deliberate, or leftover?
7. **`smartlead_observability_readonly` still has `REPLACE_WITH_AI4_CAMPAIGN_ID`** as its campaign.
   Finish it or retire it?
8. **`WF-1-DO NOT USE` still has a defined webhook path.** Keep as an archive, or remove?
9. **`dnc_check_service`** (ask the registry from Slack) is built, complete, and never switched on.
   Deliberate?
10. **Who calls `DNC__CheckLedger__v1`?** It ran 122 times on 26 August; both of its callers are
    inactive and have never run.

---

## E. Concurrency log

Baseline 2026-09-03 **08:20Z**; re-read at **08:50Z**, **09:00Z** and **09:09Z**.

| Workflow | Change | By |
|---|---|---|
| **WF-1 HeyReach Receiver** | nodes **126 → 130**, `cec8f544` → `7e3e86cf`, 08:32Z — the alert-delivery registry moved from workflow memory to the shared claims table | **other session** |
| `zz_migrate_wf1_alert_registry` / `zz_verify_wf1_alert_registry` | created, inactive throwaways | other session |
| **dnc_i04_daily_summary** | 22 → 18 nodes, ACTIVE → inactive, then archived | this session (§F, §G) |
| **dnc_morning_digest** | I-04 status line replaced, `73f5dcad` → `491f65b8` | this session (§F) |
| **dnc_i04_event_log_prune** | created, ACTIVE, 10 nodes | this session (§F) |
| **12 workflows** | deactivated + renamed `ARCHIVE__*` | this session (§G) |

Re-verified unchanged at 09:09Z: WF-2 `9c821fcc`, dnc_pre_add_gate `fe1e4b57`,
DNC__UpsertLedger__v1 `f5b99244`, dnc_projections_sweep `7506b9f4`, dnc_i04_event_receiver
`c0b702c4`. **No other-session movement between 09:00Z and 09:09Z.**

Stage 2A describes WF-1 at its **current** 130-node version, not the 126-node version in row 1.

---

## F. The I-04 simplification, 2026-09-03

**I-04 is now a change log, not a reporting system.** Detail:
[`../I04_SIMPLIFY_2026-09-03/REPORT.md`](../I04_SIMPLIFY_2026-09-03/REPORT.md) · rulebook R-G.

| | |
|---|---|
| kept | `dnc_i04_event_receiver` — untouched, still recording every Pipedrive lead/person change |
| retired | `dnc_i04_daily_summary`, `dnc_i04_weekly_reconciliation` — deactivated, preserved, now archived |
| added | `dnc_i04_event_log_prune` — 90-day retention, bounded reads, no-op until ~24 Nov 2026 |
| changed | `dnc_morning_digest` — reported `I-04 FAILING`; now reports `CRM change log N events` |

**Sizing:** 1,563 rows over 9 days · **215 events/day** · ~3.4 KB per row · **~19,400 rows / ~62 MB
at 90 days**. **Cost:** no automatic detection of bulk changes. **Kept:** full retrospective
traceability for 90 days. Tables `i04_snapshots` and `i04_walk_staging` are orphaned and referenced
by name — do not build on them.

---

## G. The archive pass, 2026-09-03

**12 archived · 0 deleted · active 22 → 20.** Rule: deactivate, rename `ARCHIVE__*`, never delete.
Full before/after and reasons: [`../ARCHIVE_2026-09-03/REPORT.md`](../ARCHIVE_2026-09-03/REPORT.md).
The four one-shot tools are registered with proposed delete-after dates in
[`../ONE_SHOT_TOOLS.md`](../ONE_SHOT_TOOLS.md).

Archived: `smartlead_observability_readonly` · `WF-1-DO NOT USE` *(webhook path neutralised)* ·
`HeyReach — Phase 0 Payload Capture` · `DNC__NormalizeIdentity__v1` · `dnc_gate_queue_drainer` ·
`dnc_expiry_job` · `dnc_expiry_null_oneshot` · `dnc_s4_event_populations` · `dnc_label_reversal` ·
`dnc_s3_surfe_backfill` · `dnc_i04_daily_summary` · `dnc_i04_weekly_reconciliation`.

Kept on purpose: `WF-0 - Discovery` · `DNC__CheckLedger__v1` · `dnc_check_service` ·
`dnc_s1_responded_to_dnc` · `dnc_s2_meeting_to_dnc` · `dnc_projections_sweep`.

**The useful property this buys:** of the 20 remaining active workflows, every one has run in the
last 20 days except `dnc_projections_sweep` — and that one is active because it is being fired
today. *If a workflow is active and has not run, either it is about to be, or it should be archived.*

### The 20 active workflows after the pass

WF-1 · WF-2 · WF-2S · WF-2R · WF-2H · WF-ERR · `dnc_pre_add_gate` · `dnc_pre_add_gate_monitor` ·
`dnc_s3_creation_watcher` · `dnc_s1_responded_to_dnc` · `dnc_s2_meeting_to_dnc` ·
`dnc_s4_retirement_removal` · `dnc_archived_responders_import` · `dnc_projections_sweep` ·
`dnc_escalation_detector` · `dnc_i04_event_receiver` · `dnc_i04_event_log_prune` ·
`dnc_morning_digest` · `dnc_wf_linter` · `dnc_intent_vs_reality`
