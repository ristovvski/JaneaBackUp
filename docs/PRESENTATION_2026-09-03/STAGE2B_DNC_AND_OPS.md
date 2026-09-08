# Stage 2B — the DNC registry, the gate, capture sources and the ops jobs

Read from the live API on 2026-09-03, including the code inside every Code node.

> **Read this first — two different things are called "DNC".**
> **(1) The registry**, a data table written only by `DNC__UpsertLedger__v1`: the record of *why*
> someone must not be contacted.
> **(2) The labels and the Smartlead unsubscribe** applied directly by WF-2 when a reply says stop.
> Those change Pipedrive and Smartlead but write **no registry row**.
> The bridge between them, `dnc_projections_sweep`, is being fired for the first time today.

---

# dnc_pre_add_gate

`9aP2dP0jgAPFGDvA` · ACTIVE · 14 nodes · **3,500+ runs in 20 days, 0 errors** — the busiest webhook

## Purpose
The "may I contact these people?" service. Before a list goes into a sending campaign, you ask the
gate. It exists so that question is one call rather than a manual cross-check.

## Trigger and inputs
POST a list of rows, each with an email and/or a LinkedIn URL. Answers synchronously.

## Step by step, and the verdicts
Cap the batch at 500 → normalise every identity → look the whole batch up in the registry by
LinkedIn **or** email → classify each row → answer.

| Verdict | Meaning |
|---|---|
| `OWN_TEAM` | an `@janeasystems.com` address — exclude from any list |
| `UNRESOLVABLE` | no usable email and no usable LinkedIn URL; nothing to match on |
| `BLOCKED` | an **active** registry row exists; the reason returned is `{entry type} / {source}` |
| `CLEAN` | no row, or only retired ones — and then it says what it used to be |

Where several rows match, the strongest wins: explicit opt-out 5 → negative reply 4 → replied 3 →
employee connection 2 → manual 1, ties broken by the earliest entry.

## Business rules
- **A LinkedIn URL that is not an `/in/` profile is marked unmatchable rather than guessed at.**
- **The lookup is an OR across both identifiers**, so one identifier is enough.
- **Over 500 rows is an explicit error (413)**, never a silent truncation.
- **The queue is gone (2026-09-02).** It used to park batches over 50 rows and answer
  `{"queued": N, "eta_minutes": …}` — a promise nothing could keep, because the drainer never ran
  and the table did not exist. Everything up to 500 is now answered in the same response; the old
  `retrieve` call returns an explicit **410** rather than `pending` forever.

## Systems touched
**Only the registry table.** No CRM, no sending tool. The gate is a read — which is why it is safe
to ask as often as you like.

## Failure modes
Its registry read has **no error handling**, so a hard failure fails the whole call — loud, which is
right. The quieter risk: a read that **succeeds and returns nothing** makes every row `CLEAN`. There
is no assertion that the registry is non-empty; the 15-minute monitor is the only thing standing
between that and a fully open gate.

## Recovery
Pure read — re-ask any time. Nothing to replay, nothing to undo.

## Dependencies
Reads the registry written by the ledger. Polled by its monitor. Called by whoever is building a list.

---

# dnc_pre_add_gate_monitor

`g8MUOKFlUaeVrdBx` · ACTIVE · 13 nodes · every 15 min + 08:00 heartbeat · 787 runs

**Purpose:** prove the gate still answers correctly, so that "no alerts" means healthy rather than
"nobody asked".

**What it does:** sends the gate two rows whose answers are known — one that must come back blocked,
one clean — and asserts exactly `total 2, clean 1, blocked 1, unresolvable 0`. Tracks checks,
failures and latency for the day.

**The rule that matters:** *an alert fires once per state change, never per poll* — once when the
gate breaks, once when it recovers, plus a daily heartbeat. The previous version produced **96 false
alerts a day for five days** by reading a failing table call as depth 0 and wiring its test to the
false branch.

**Limits:** it proves the gate answers two known rows correctly. It cannot tell you the registry is
stale or that a capture source stopped writing.

---

# DNC__UpsertLedger__v1 — the single writer

`RolYGL3J2CNg6Yp3` · **inactive, and the busiest workflow in the estate** · 3,500+ runs, 2 errors

> Being inactive is correct for a sub-workflow — n8n only requires the *caller* to be active.
> **Do not switch it on.**

## Purpose
Everything that adds a person to the do-not-contact registry goes through here, so the merge rules
exist in exactly one place.

## What it does
Normalise the identity → look the person up twice, once by LinkedIn and once by email → decide one
of five outcomes → write.

| Outcome | Meaning |
|---|---|
| **conflict** | LinkedIn and email resolve to two *different* people. Alerts a human, **writes nothing** |
| **merge_split_identity** | the narrow exception: one side is a LinkedIn-only bulk-import row with no email and no person id, the other carries a person id, **and the names corroborate**. One person split across two half-rows — merged, loser tombstoned |
| **insert** | nobody matched |
| **update** | merge onto the strongest existing row, soft-removing duplicates |
| **noop** | nothing material changed |

## Business rules
- **Strength never downgrades:** explicit opt-out 5 > negative reply 4 > replied 3 > employee
  connection 2 > manual 1.
- **Reason priority**, strongest first: client, unsubscribe, meeting, reply-DNC, sales personal
  outreach, manual offboard-eligible, event contacted, manual sheet, offboard. **The losing reason
  is kept** in a secondary field so an offboarding scan can still see it.
- **Identity fields fill in but never overwrite.**
- **Sources accumulate** as a set.
- **A new signal reactivates** a removed or expired row and resets its date.
- **Expiry is dead.** The expiry function returns nothing for every entry type; the reasoning is in
  the code — a six-month timer on *replied* and *negative reply* applied a countdown to exactly the
  rows that represent a response. Retention is now by reason, not by clock.
- **Every new row records that it has not been projected yet** — for Pipedrive, Smartlead and
  HeyReach separately.
- **Auto-merging two different real people would be a data-integrity incident**; the code refuses
  except in the one corroborated shape.

## Failure modes — both real errors in the window
- **`invalid reason meeting_dnc`** (18 Aug) — a caller sent a reason the writer did not recognise,
  the same day the meeting capture source failed. **Open question: has the meeting source ever
  successfully written a row?**
- **Slack `channel_not_found`** (20 Aug) on its conflict alert. A conflict alert that cannot be
  delivered is a human decision nobody was asked to make.

The registry write is the only node in the estate set to **stop the workflow** on error, which is
right: a failed write must not be followed by anything that assumes it worked.

## Recovery
Idempotent by construction — calling again with the same signal produces a no-op. Safe to re-run.

## Dependencies
Called by S1, S2, S3, the Surfe backfill, S4, the archived-responders import, the LinkedIn-reply
bridge and the sheet intake. **Of those, only S3 currently runs and is permitted to write.**

---

# The capture sources — and which actually run

All five share a shape: a settings block with a `FIRE_*` switch, a classifier, a Pipedrive person
lookup to obtain a usable identity, and a call to the ledger. **Dry-run is the default.**

| Source | What it captures | Switch | Runs |
|---|---|---|---|
| **S1** responded → DNC | a supplied list of people who replied | `FIRE_S1` **false** | hand-fired, last 18 Aug |
| **S2** meeting → DNC | people who booked a meeting | `FIRE_S2` **false** | hand-fired, last 18 Aug, 1 error |
| **S3** creation watcher | leads a salesperson created by hand, or that came from Surfe | `FIRE_S3` **TRUE** | **every 15 min, 1,920 runs** |
| **S3-backfill** | the same, historically | `FIRE_S3_BACKFILL` **false** | never |
| **S4** event populations | everyone in a given campaign | `FIRE_S4` **false** | inactive, 148 runs on 14 Aug |

### S3 — the only live one
Reads the newest 100 Pipedrive leads every 15 minutes, newest-first, and remembers the ids it saw
last time. **Keeps** a lead when the creator is one of eight named sales users **or** the channel is
Surfe. **Rejects** automation writes via the API, web-form leads, and Memurai leads. Files each
keeper as *sales personal outreach* with the salesperson's name.

**Two limits that matter and belong on a slide:** it is **forward-only** — a lead that arrives while
it is behind can fall out of the 100-lead window unseen; and it is **lead-shaped** — a person created
without a lead is invisible to it, and Pipedrive persons carry no creator field, so no equivalent
watch is possible. It posts a nightly heartbeat at 23:55 so a silent failure is visible.

**Its one error (20 Aug) was a Slack `channel_not_found`,** the same failure as the ledger's.

---

# dnc_projections_sweep — the bridge, being fired today

`8qVXtI2ez5o6a9hc` · ACTIVE · 41 nodes · **zero executions in the 20-day window**

## Purpose
The only mechanism that makes a registry entry mean something outside the registry.

| Target | What it would do | State |
|---|---|---|
| Pipedrive | set the do-not-contact field on the person; union the label onto any open lead | **approved, being fired today — ~564 rows** |
| Smartlead | resolve the lead by email and unsubscribe | **approved for negative-reply and meeting rows only, pending the exact list** |
| HeyReach | nothing — only a counter of what is pending | **no write path exists at all** |

## Business rules
- It only touches rows that have not yet been projected to that specific target.
- The Pipedrive label write is a **union**, never a replacement.
- Each row is marked done, or marked with the write error, per target independently.
- Both write switches read `false` in the live settings; enabling is a deliberate act per target.

## Failure modes and recovery
It has never run, so nothing about its behaviour is proven live. **The Smartlead half is a one-way
door** — an unsubscribe cannot be undone through the API. Read back afterwards: a Smartlead call can
report success on something that did not happen.

---

# dnc_escalation_detector

`QO1zRhUfG7otk06N` · ACTIVE · hourly + 06:10 heartbeat · 496 runs, 0 errors

**Purpose:** the after-the-fact safety net — *is anyone protected still sitting in a live sending
campaign?*

**What it does:** every hour, lists Smartlead campaigns, keeps those not COMPLETED/PAUSED/DRAFTED/
STOPPED and not one of seven known nurture campaigns, pulls up to 500 leads from each, and
intersects them against the registry's active rows by email and by canonical LinkedIn URL. Every hit
goes to ops with the person, campaign, entry type and reason.

**Limits:** 500 leads per campaign — a bigger campaign is only partly checked, and it says so rather
than hiding it. Matching is exact-string.

**Why it matters right now:** with the projector only being enabled today, **this is the main thing
standing between the registry and a compliance incident — and it detects rather than prevents.**

---

# The change log — I-04, as of 2026-09-03

**I-04 is now a change log, not a reporting system.**

### dnc_i04_event_receiver · ACTIVE · 5 nodes · 1,562 runs, 0 errors
Receives Pipedrive's own notifications about leads and people, understands both webhook formats,
keeps only lead and person objects, and files each one with its action, object, timestamp and raw
payload. Answers on receipt. **Silent by design** — no summaries, no alerts. Its value is
retrospective: *who changed this, and when.*

### dnc_i04_event_log_prune · ACTIVE · 10 nodes · new today
Keeps 90 days. Reads **only rows past the cutoff**, never the whole table; caps deletions at 500 per
run; counts outcomes rather than items; refuses to report "nothing to prune" off a failed read.
Measured: **215 events/day, ~3.4 KB per row, ~19,400 rows / ~62 MB at steady state**. A **no-op
until ~24 November** — nothing is 90 days old yet.

### Retired and preserved
`dnc_i04_daily_summary` (deactivated, watchdog removed) and `dnc_i04_weekly_reconciliation`
(never ran once). **What is lost:** automatic detection of bulk changes — the summary flagged ten or
more distinct leads updated inside the same minute, which is how a label-wiping automation was caught
before. **What is kept:** full retrospective traceability for 90 days.

**Orphaned:** the tables `i04_snapshots` and `i04_walk_staging` now have no active reader or writer,
and both are referenced **by name** — the unreliable form. Do not build on them.

---

# dnc_morning_digest

`qJKfR602wV9yfFrj` · ACTIVE · 40 nodes · daily 07:00 local · 3 runs

**Purpose:** one post that answers "is the machine fine this morning?" without opening n8n.

**What it reports:** Smartlead and HeyReach volume and next-step due dates; Pipedrive lead volume;
an integrity line (emails sent with no corresponding lead); registry active count and 24-hour
movement; gate latency and failures; failed executions and **missed schedules**; and, since today,
**CRM change log — N events**, read from the event table rather than from whether a reporting job ran.

**The rules that make it trustworthy:**
- **It posts every day, including a wholly green one** — deliberately no "only if interesting" gate,
  so a day with no message means the job did not run.
- **It never prints a number it could not measure.** An unsorted Pipedrive page suppresses the
  new-lead count with a named reason; a saturated page is reported as a floor; an unreadable source
  is listed in a "not measured" footer. The change-log count is `null` — rendered `n/a` — when the
  read fails, and an unreadable change log is **amber**, not red: an observability gap, not a failure.

---

# dnc_wf_linter

`fziGeigC48aGTLT8` · ACTIVE · daily 06:40 local · 3 runs

Reads every workflow definition each morning and reports convention breaches. **Fifteen rules, each
written after a real incident, each carrying the incident in a comment** so nobody deletes a rule
whose reason has been forgotten. The full list is in Stage 3 doc 4.

**Why its output is trustworthy:** it posts only what is **new or newly resolved**, keeping the
standing backlog in its own memory; the first run recorded a baseline and said so rather than dumping
190 findings into a channel; **an unreadable workflow list is reported as unreadable, never as a
clean estate** — which is precisely the failure it exists to catch, so it must not commit it; and it
records state *before* composing the post, so a Slack failure cannot cause a re-post storm.

---

# dnc_intent_vs_reality

`tnW7agCbha7rhNnS` · ACTIVE · 9 nodes · webhook · 23 runs

**Purpose:** the answer to "did the protection actually happen?" — it asserts the consequence in
Pipedrive and Smartlead and compares it against what the registry claims about itself, never reading
a switch.

**How it is bounded:** chunked by the caller, capped per call, and both provider calls use full
responses so *"we could not look"* stays distinguishable from *"we looked and it is not there."*

**What it found on 2026-09-02** (1,000-row systematic sample of 25,653 active rows): **no false
claims in either direction**; ~564 Pipedrive rows genuinely pending; **62% of the rows that have an
email were still contactable in Smartlead**; and **88% of the registry has neither an email nor a
person id**, so no projection can reach it.

---

# The operator tools — hand-fired, dry-run by default

| Workflow | What it does | Safety |
|---|---|---|
| `dnc_s4_retirement_removal` | marks named registry rows retired | **dry-run unless you explicitly say otherwise**; no undo — re-adding means re-filing |
| `dnc_archived_responders_import` | imports a validated list of past responders | **refuses the whole batch** if any row has an unknown reason, a reply-DNC without a category, or no identifier |
| `dnc_label_reversal` | re-reads leads and strips labels that should not be there | dry-run; accepts explicit protect-lists |
| `dnc_s3_surfe_backfill` | the historical version of S3 | dry-run; never run |

---

# The remaining inactive pieces

| Workflow | Why it exists | State |
|---|---|---|
| `DNC__CheckLedger__v1` | read-only twin of the writer: is this person on the registry? | 122 runs on 26 Aug; **both of its callers are inactive and have never run — who invoked it is an open question** |
| `DNC__NormalizeIdentity__v1` | the identity-cleaning step as its own unit | never called; the same logic is copied inside three workflows |
| `dnc_check_service` | ask the registry from Slack by mentioning a bot | built, complete, never switched on |
| `dnc_wf4_sheet_intake` | manual intake from a spreadsheet | never run |
| `dnc_gate_queue_drainer` | would have drained the gate's queue | the gate no longer queues anything |
| `dnc_expiry_job` / `dnc_expiry_null_oneshot` | the retired time-based expiry, and the one-shot that removed it | correctly retired |
| `smartlead_observability_readonly` | anomaly watch on one campaign | **its campaign id is still the literal placeholder text** |
| `WF-0 - Discovery` | reads Pipedrive's field, label, user and activity-type definitions and assembles the settings block the receivers depend on | **load-bearing — run it by hand whenever Pipedrive fields change** |
| `WF-1-DO NOT USE` | the previous generation of WF-1 | 89 nodes; its webhook path is still defined |
| `HeyReach — Phase 0 Payload Capture` | pre-WF-1 scaffolding | — |
