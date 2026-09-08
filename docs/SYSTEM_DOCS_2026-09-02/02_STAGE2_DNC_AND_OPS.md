# Stage 2 (part 2) — the DNC registry, the gate, capture sources and the ops jobs

> **⚠ SUPERSEDED IN PART — 2026-09-03: the I-04 simplification.**
> `dnc_i04_daily_summary` and `dnc_i04_weekly_reconciliation` were retired (deactivated and
> preserved). `dnc_i04_event_receiver` stays as a silent change log, and a new
> `dnc_i04_event_log_prune` keeps 90 days. The morning digest no longer reports I-04 status; it
> reports `CRM change log N events`. Tables `i04_snapshots` and `i04_walk_staging` are now orphaned
> and are referenced by name — do not build on them.
> Detail: [`I04_SIMPLIFY_2026-09-03/REPORT.md`](../I04_SIMPLIFY_2026-09-03/REPORT.md) · rule R-G in `RULEBOOK.md`.



Read live from the n8n API on 2026-09-02.

> **Read this first.** There are **two different things called "DNC"** in this estate, and they do not talk to each other today:
>
> 1. **The DNC registry** — a data table (`UOgKwlGsL28lX61O`) written only by `DNC__UpsertLedger__v1`. This is the record of *why* someone must not be contacted.
> 2. **The DNC label + Smartlead unsubscribe** applied directly by WF-2 when a reply is classified as do-not-contact. This changes Pipedrive and Smartlead but **writes no registry row**.
>
> The workflow that was built to connect them in the other direction — `dnc_projections_sweep`, which pushes registry rows out to Pipedrive and Smartlead — has **zero executions in the retention window and both of its write switches set to `false`**. Keep that in mind while reading everything below.

---

## dnc_pre_add_gate

`9aP2dP0jgAPFGDvA` · ACTIVE · 24 nodes · webhook `{{WEBHOOK_DNC_PRE_ADD_GATE}}` · ~3,000+ runs in 7 days

### Purpose
The "may I contact this person?" service. Before anyone loads a list into a sending campaign, they ask the gate, and it answers per row. It exists so that "are they on the do-not-contact list?" is one HTTP call rather than a manual cross-check.

### Trigger and inputs
`POST` a JSON body of rows, each carrying an email and/or a LinkedIn URL (optionally a name and a Pipedrive person id). A second mode, `{"retrieve": true, "rows": [...]}`, fetches the verdicts of a previously queued batch.

### What it does
1. **Caps the batch at 500 rows** — over that it refuses with an explanatory error rather than truncating.
2. **Normalises every identity**: lower-cases the email; canonicalises the LinkedIn URL to `https://www.linkedin.com/in/{slug}`; a LinkedIn URL that is not an `/in/` profile is marked unmatchable rather than guessed at.
3. **Decides synchronous or queued**: 50 rows or fewer *and* no pending queue work → answer immediately.
4. **Looks the batch up in the registry** by LinkedIn and by email.
5. **Classifies each row** into one of four verdicts and answers.

### The four verdicts
| Verdict | Meaning |
|---|---|
| `OWN_TEAM` | the email is `@janeasystems.com` — exclude from any campaign list |
| `UNRESOLVABLE` | no usable LinkedIn URL and no email, so nothing can be matched |
| `BLOCKED` | an **active** registry row exists; the reason returned is `{entry_type} / {source}` |
| `CLEAN` | no row, or only rows that are expired/removed (and then the reason says what it used to be) |

Where several rows match, the strongest wins: explicit opt-out 5 → negative reply 4 → replied 3 → employee connection 2 → manual 1, ties broken by the earliest entry.

### Systems it touches
Only n8n data tables (the registry, and a queue table). No CRM, no sending tool. That is deliberate — the gate is a read.

### Known failure modes — and one live trap
- **The queue path is a dead end.** The gate parks batches larger than 50 rows into a table called `dnc_gate_queue`, replies `{"queued": N, "eta_minutes": …}`, and expects `dnc_gate_queue_drainer` to classify them. **The drainer is inactive and has never run**, and the monitor's own code (dated 2026-08-31) states plainly that the `dnc_gate_queue` table does not exist. So a caller who submits 51–500 rows gets a cheerful "queued" and **never gets an answer**. Nothing alerts on this. *This is the single most dangerous thing I found. I could not verify table existence from the API — data tables are not exposed there — so please confirm in the UI.*
- A failed registry read is handled correctly: the sync/queue decision checks positively for the real row shape, so an unreadable queue table reads as "nothing pending" rather than crashing.
- The `Get Registry Match (Batch)` and `Lookup Queue By Key` reads have **no error handling**; if either fails the whole call fails, which is at least loud.

### How to safely restart or replay
It is a pure read: re-ask any time, as many times as you like. Keep batches **at or under 50 rows** until the queue path is fixed or removed.

### Dependencies
Reads the registry written by `DNC__UpsertLedger__v1`. Polled every 15 minutes by `dnc_pre_add_gate_monitor`. Would depend on `dnc_gate_queue_drainer` for anything over 50 rows.

---

## dnc_pre_add_gate_monitor

`g8MUOKFlUaeVrdBx` · ACTIVE · 13 nodes · every 15 min + 08:00 heartbeat

### Purpose
Proves the gate still answers correctly, so that "no alerts" means "healthy" rather than "nobody asked".

### What it does
Fires a synthetic two-row request at the gate every 15 minutes and asserts the answer is exactly: total 2, one clean, one blocked, none unresolvable. Tracks checks, failures and latency for the day. **Alerts on the transition only** — once when the gate goes unhealthy, once when it recovers — plus a daily heartbeat at 08:00.

### Business rules
- **A monitor alert fires once per state change, never per poll.** This rule was written after the previous version produced 96 false "queue STUCK" alerts a day for five days: it read a failing data-table call as depth 0 instead of "unknown", and its IF was wired to the FALSE output. Both the queue branch and the per-poll repetition were removed.

### Known failure modes
It only proves the gate *responds correctly to two known rows*. It cannot detect that the registry itself is stale or that a capture source stopped writing.

### How to restart
Nothing to restart; it is stateless apart from the day counters in static data.

---

## DNC__UpsertLedger__v1  *(inactive, but the busiest workflow in the estate)*

`RolYGL3J2CNg6Yp3` · 14 nodes · sub-workflow · 3,000+ executions, last 2026-09-01

### Purpose
**The single writer to the DNC registry.** Everything that adds someone to the do-not-contact list goes through here, so that the merge rules exist in exactly one place.

> Being "inactive" is normal and correct for a sub-workflow — n8n only requires the *calling* workflow to be active. Do not switch it on.

### Trigger and inputs
Called by another workflow with an identity (`linkedin_url`, `email`, `full_name`, `pipedrive_person_id`) plus a signal (`entry_type`, `reason`, `source`, `source_ref`, `reply_category`, `correlation_id`).

### What it does
1. **Normalises the identity** to a canonical LinkedIn URL and lower-cased email.
2. **Looks the person up twice** — once by LinkedIn, once by email.
3. **Decides one of five actions**:
   - **conflict** — LinkedIn and email resolve to two *different* people. Alerts a human; writes nothing.
   - **merge_split_identity** — the narrow exception to conflict: one side is a LinkedIn-only bulk-import row with no email and no person id, the other carries a person id, *and* the names corroborate. Then it is one person split across two half-rows, and they are merged with the loser tombstoned.
   - **insert** — nobody matched.
   - **update** — merge onto the strongest existing row, soft-removing duplicates.
   - **noop** — nothing material changed.
4. Writes the row and, where applicable, tombstones the superseded one.

### Business rules encoded in it
- **Strength never downgrades.** explicit opt-out 5 > negative reply 4 > replied 3 > employee connection 2 > manual 1.
- **Reason priority** (0 strongest): client, unsubscribe, meeting, reply-DNC, sales personal outreach, manual offboard-eligible, event contacted, manual sheet, offboard. The losing reason is not discarded — it is appended to `also_flagged` so an offboarding scan can still see it.
- **Identity fields fill in but never overwrite.** An existing non-null value is kept.
- **Sources accumulate** as a comma-separated set.
- **A re-appearing signal reactivates** an expired or removed row and resets `added_at`.
- **Expiry is dead.** `computeExpiry()` returns `null` for every entry type. The code says why: on 2026-08-26 time-based expiry was replaced by reason-based retention, and 1,353 rows carrying an `expires_at` were nulled on 2026-08-31. Registry entries are now permanent unless explicitly retired.
- **Every new row is created with `projections_state` = pending for Pipedrive, Smartlead and HeyReach.** Nothing currently consumes that field — see `dnc_projections_sweep`.

### Known failure modes
- **Conflict alerts** are the expected human-in-the-loop path, not a bug.
- The registry write is the only node in the estate set to `stopWorkflow` on error — a failed write stops the run rather than continuing silently. That is right.
- 2 errored executions in the window.

### How to restart or replay
Idempotent by construction: calling it again with the same signal produces `noop`. Safe to re-run.

### Dependencies
Called by: S1, S2, S3, S3-backfill, S4, `dnc_archived_responders_import`, `heyreach_reply_to_dnc_ledger`, `dnc_wf4_sheet_intake`. **Of those, only S3 currently runs.**

---

## DNC__CheckLedger__v1 · DNC__NormalizeIdentity__v1  *(inactive)*

- **CheckLedger** (`kv7reJYAAgsOV33t`, 5 nodes) — read-only twin of the ledger: normalise, look up by LinkedIn and by email, report status. 122 executions all on 2026-08-26; both of its callers are inactive, so **who invoked it that day is an open question**.
- **NormalizeIdentity** (`K2M1Z0m1gKX6LdFI`, 2 nodes) — the identity normaliser as a callable unit. Zero executions, no caller. The same logic is inlined in UpsertLedger, CheckLedger and the gate. Dead code with a maintenance cost: four copies to keep in step.

---

## The four capture sources (S1–S4)

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

### dnc_s1_responded_to_dnc — `BxJZmz1HY5AdaQqE` · ACTIVE · webhook
Takes a supplied list of Pipedrive person ids that have responded, reads each person for a LinkedIn URL or email, and files them as `reply_dnc`. Skips anyone with no resolvable identity and logs that separately. Hand-fired; chunked 100 at a time with an offset.

### dnc_s2_meeting_to_dnc — `E0oTTvHHQ0hVTNDD` · ACTIVE · webhook
Same, for people who booked a meeting (`meeting_dnc`, mapped to entry type *replied*). The source population is defined outside n8n: lead label "5. Meeting" union deal stage "Qualified Meeting Set", with Memurai/partner pipeline explicitly excluded.

### dnc_s3_creation_watcher — `QM21Vd7VId7PBdqh` · ACTIVE · every 15 min · **the live one**
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

### dnc_s3_surfe_backfill — `1fpep0U4XC8KNzta` · ACTIVE · webhook · never run
Historical twin of S3: pages back through older leads 500 at a time, 3 pages per call. `FIRE_S3_BACKFILL: false`.

### dnc_s4_event_populations — `hhdnug5xdFLAxrOg` · INACTIVE · 194 runs on 2026-08-14
Bulk-loads an entire Smartlead or HeyReach campaign's lead list into the registry as `event_contacted` — the weakest signal: "we touched them once via an event campaign", not "they responded". One bulk load on 14 Aug, then switched off.

---

## dnc_s4_retirement_removal

`DYb9jArdS7xKs3nA` · ACTIVE · 7 nodes · webhook

Operator tool. POST `{"row_ids": [...], "dry_run": false}` and it marks those registry rows removed with reason `rule_change_2026-08-26_melisa`. **Dry-run is the default** — you must pass `dry_run: false` explicitly to write. Used 16 times on 26 Aug when the retention rule changed.

**Restart:** re-running the same ids is harmless (they are already removed). There is no undo — re-adding means re-filing through the ledger.

---

## dnc_archived_responders_import

`07sGtABZiqLrBChX` · ACTIVE · 8 nodes · webhook · 2 runs on 2026-08-28

One-shot importer for a supplied list of archived responders. **Validates every row before writing anything**: the reason must be one of the nine known reasons, `reply_dnc` requires a reply category, and every row must have an email or a LinkedIn URL. If any row fails, the whole call throws with the first ten problems named. Then calls the ledger per row. Dry-run by default.

---

## dnc_projections_sweep  ⚠️

`8qVXtI2ez5o6a9hc` · ACTIVE · 41 nodes · webhook `{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}` · **zero executions**, **`FIRE_PIPEDRIVE: false`, `FIRE_SMARTLEAD: false`**

### Purpose
The projector — the piece that makes a registry entry mean something outside the registry. For each row not yet projected it would:
- **Pipedrive:** set the DNC custom field on the person, and if the person has an open lead, add the DNC label to it (union, never replacing existing labels);
- **Smartlead:** resolve the lead by email and unsubscribe it;
- **HeyReach:** count what is pending — there is no HeyReach write path at all, only a counter.

It then marks each row's `projections_state` done, or records a write error.

### Current state
It has not run in the 19-day retention window, and both write switches are off, so **even if it were invoked it would report a dry run**. Every registry row written since at least 14 Aug still carries `projections_state: pending` as far as this workflow is concerned.

### Why this matters
The DNC registry currently has no automatic outward effect. The only things actually stopping a send today are (a) whoever remembers to call the gate before loading a list, (b) `dnc_escalation_detector` shouting after the fact, and (c) WF-2's own reply-classification path, which unsubscribes in Smartlead directly and never consults the registry.

### How to restart safely
Set `FIRE_PIPEDRIVE` / `FIRE_SMARTLEAD` deliberately, one at a time, and fire the webhook with a small chunk first (`pd_chunk_size` is 250). **Smartlead unsubscribe is irreversible via the API** — treat the Smartlead half as a one-way door and confirm the candidate list before enabling it.

---

## dnc_label_reversal

`LQRfmEl4Wv0qpXsI` · ACTIVE · 20 nodes · webhook · last used 2026-08-14 · `FIRE_REVERSAL: false`

Repair tool for the opposite problem: labels that should not be there. Walks registry candidates, re-reads each Pipedrive lead, and strips the DNC label where the rule says it does not belong. Accepts `frozen_ids` and `live_exclusion_ids` so specific leads can be protected. Dry-run unless `FIRE_REVERSAL` is set.

---

## dnc_escalation_detector

`QO1zRhUfG7otk06N` · ACTIVE · 20 nodes · hourly + 06:10 heartbeat + a test webhook

### Purpose
The after-the-fact safety net: **is anyone on the do-not-contact list still sitting in a live sending campaign?**

### What it does
Every hour: lists Smartlead campaigns, keeps those that are not COMPLETED/PAUSED/DRAFTED/STOPPED and are not one of seven known nurture campaigns, pulls up to 500 leads from each, and intersects them against the registry's active rows by email and by LinkedIn URL. Any hit is posted to the ops channel with the person, campaign, entry type and reason. It flags `truncated` when a campaign returns the full 500.

### Known failure modes
- **500-lead ceiling per campaign** — a bigger campaign is only partly checked, and the workflow says so rather than hiding it.
- Matching is exact-string on email and canonical LinkedIn URL; a person on the registry under a different address is invisible.

### Why it matters right now
With the projector dormant, **this is the main thing standing between the registry and a compliance incident** — and it detects rather than prevents.

---

## dnc_expiry_job *(inactive)* and dnc_expiry_null_oneshot *(inactive)*

`alpy9rsunqnFwQml` — the daily 06:00 ager: expire rows past TTL, de-duplicate, weekly digest. Never ran in the window and is switched off.
`CUpl8PVOOYXMysVN` — created, run 15 times and switched off on 2026-08-31; it blanked `expires_at` on every registry row.

Together with `computeExpiry()` now returning `null`, the position is: **registry entries do not expire.** They are retired explicitly, by reason, via `dnc_s4_retirement_removal`.

---

## dnc_gate_queue_drainer *(inactive)*

`fZl1vpRsQ6Fko3sB` · 6 nodes · every 2 min · never run

Would pick pending rows out of `dnc_gate_queue`, classify them against the registry, and write verdicts back. Its `Classify Batch` and `Normalize Batch` code is **byte-identical** to the gate's — a copy, not a shared sub-workflow, so the two will drift.

Off, plus a queue table the monitor says does not exist, is what makes the gate's over-50-row path a dead end.

---

## The I-04 CRM-change watch

### dnc_i04_event_receiver — `wqORtqgRJ3W5YvBL` · ACTIVE · 5 nodes · 1,355 runs
Receives Pipedrive's own webhooks at `/webhook/{{WEBHOOK_I04_PIPEDRIVE_EVENTS}}`, understands both v1 and v2 webhook shapes, keeps only `lead` and `person` objects, and writes one row per event into the event table with the raw payload preserved. Answers `200` on receipt, before processing.

**Failure mode:** if the Pipedrive subscription is deleted or expires, this simply goes quiet — and quiet looks identical to "nothing changed". The daily summary is what catches that (below).

### dnc_i04_daily_summary — `8sT1XjDDVmrz05CA` · ACTIVE · 22 nodes · daily 05:30 · **5 errored runs, latest 2026-08-31**
Turns the captured events into a Slack summary: arrivals, departures, lead updates, person events, and **mass-relabel detection** (ten or more distinct leads updated inside the same minute — the signature of a bulk relabel operation, which is how a label-wiping automation was caught before). Then prunes old event rows and saves a watermark.

**Two rules worth repeating:**
- It distinguishes **"no events received"** from **"zero real changes"** and reports them as different findings — an empty event log may mean the Pipedrive subscription died.
- It degrades instead of throwing if the watermark cannot be read, because a throw would blind the estate for the whole day.
- A separate idle-guard runs every 15 minutes and alerts if today's summary never got posted. **A missing post means the job did not run** — that is the whole invariant.

**Open item:** the 5 errored executions are on the daily trigger itself. Worth opening before the presentation.

### dnc_i04_weekly_reconciliation — `gjVZkkvm05jj8CNM` · INACTIVE · 53 nodes · never run
The heavy version: a five-minute ticker walks the entire Pipedrive lead and person estate into a staging table, builds a snapshot, diffs it against the previous one, looks up each departure, reports, then prunes old snapshots. It has a circuit breaker. Currently off, so the estate has event-based change detection only — which cannot see anything Pipedrive does not send a webhook for.

---

## dnc_morning_digest

`qJKfR602wV9yfFrj` · ACTIVE · 40 nodes · daily 07:00 Asia/Jerusalem · created 2026-08-31

### Purpose
One post that answers "is the machine fine this morning?" without opening n8n.

### What it reports
Smartlead campaign volume and next-step due dates; HeyReach volume; Pipedrive lead volume; an **integrity** line (emails sent with no corresponding lead); DNC registry active count plus added/removed in 24h; gate latency, checks and failures today; failed executions in 24h and **missed schedules**; and a count of "no match found" messages in the ops channel.

### The rules that make it trustworthy
- **It posts every single day, including a wholly green one.** There is deliberately no "only post if interesting" gate: a day with no message must mean the job did not run.
- **It refuses to report a number it could not read honestly.** If the Pipedrive lead page comes back unsorted, new-lead counts are suppressed with a named reason rather than printed as a possibly-wrong figure; a saturated page is reported as a floor, not a total; an unreadable source is listed under "not measured".

### Restart
Recomputed from scratch each run; a missed day is a missed day, nothing is lost.

---

## dnc_wf_linter

`fziGeigC48aGTLT8` · ACTIVE · 8 nodes · daily 06:40 · created 2026-08-31

### Purpose
Reads every workflow definition in the instance and reports convention breaches. **Fifteen rules, each one written after a real incident**, and each carrying the incident in a comment so nobody deletes a rule whose reason has been forgotten. The full rule list is in domain doc 4.

### The rules that make it trustworthy
- **It posts only what is NEW or NEWLY RESOLVED**, keeping the standing backlog in its own memory. The first-ever run only records a baseline and says so, rather than dumping the whole backlog into a channel where it would be ignored.
- **An unreadable workflow list is reported as unreadable**, never as zero findings — which is exactly the failure the linter exists to catch, so it must not commit it itself.
- Findings are recorded *before* the Slack post is composed, so a Slack failure cannot cause a re-post storm.

### Note
The rule numbering runs R01–R14 and R16. **R15 is absent** — either withdrawn or never written; worth confirming.

---

## The remaining inactive tools, briefly

| Workflow | What it would do | Why it matters |
|---|---|---|
| **heyreach_reply_to_dnc_ledger** `YgufwSg1EAJaT0ra` | map a HeyReach reply into a registry write | never ran, no caller — **LinkedIn replies never become registry entries**, which is the biggest asymmetry between the two channels |
| **dnc_check_service** `PViKUykLaDd7Xze1` | Slack bot: `@mention` it with an identity, get that person's DNC status | would make the registry self-service; off |
| **dnc_wf4_sheet_intake** `bluGflKaUI3bGodQ` | watch a Google Sheet and file new rows into the registry | the manual-intake path; off |
| **smartlead_observability_readonly** `XWtxUzBgNJuguJlg` | 30-minute anomaly watch on one Smartlead campaign | its `campaign_id` is still the literal placeholder `REPLACE_WITH_AI4_CAMPAIGN_ID` — it was never configured |
| **WF-0 - Discovery** `5TCZwAZ3xeXQr0vI` | read Pipedrive's field / label / user / activity-type definitions and assemble the CONFIG block | **run this by hand whenever Pipedrive fields change** — it is how the field hashes in WF-1 and WF-2 are regenerated |
| **WF-1-DO NOT USE** `NNOVii5ImjFKDSM0` | an old 89-node copy of WF-1 | its test webhook path is still reachable; the name is doing all the safety work |
| **HeyReach — Phase 0 Payload Capture** `rnPaPoVQNe2SShkc` | ACK and record raw HeyReach payloads | build-time scaffolding from before WF-1 existed |
