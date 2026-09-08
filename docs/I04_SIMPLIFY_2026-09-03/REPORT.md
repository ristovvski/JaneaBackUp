# I-04 simplification — what changed, 2026-09-03

**I-04 is now a change log, not a reporting system.** The event receiver stays and keeps recording
every Pipedrive lead/person change; the daily summary and the weekly reconciliation are retired and
preserved; a bounded retention job replaces the pruning the summary used to do as a side effect.

All four affected workflows were backed up to `backups/` before any change.

---

## 1. Final state

| Component | Before | After |
|---|---|---|
| `dnc_i04_event_receiver` | ACTIVE, 5 nodes, 1,562 runs, 0 errors | **unchanged — not written to at all** |
| `dnc_i04_daily_summary` | ACTIVE, 22 nodes | **INACTIVE, 18 nodes** — idle watchdog removed, everything else preserved |
| `dnc_i04_weekly_reconciliation` | inactive, 53 nodes | **inactive, 53 nodes — verified by read, not written to** |
| `dnc_i04_event_log_prune` | did not exist | **NEW, ACTIVE, 10 nodes** — daily 06:20 Asia/Jerusalem, 90-day retention |
| `dnc_morning_digest` | reported `I-04 FAILING` | reports **`CRM change log N events`** |

New versionIds: daily summary `d8827dda`, morning digest `8b758242`, prune `4fd4d974`.

## 2. The sizing you asked for

Measured on the live table with a throwaway read-only workflow (created, run, deleted):

| | |
|---|---|
| rows now | **1,563** across 9 days (oldest 2026-08-26 08:48Z) |
| **mean per complete day** | **215 events** (7 complete days counted) |
| peak day | 484 |
| average row size | **~3.4 KB** — the stored raw payload dominates |
| mix | 838 lead / 725 person · 779 create, 777 change, 7 delete |
| **projected at 90-day retention** | **~19,400 rows, ~62 MB** |

**The prune is a no-op until about 24 November 2026.** The oldest row is 26 August and the cutoff
is 90 days, so nothing ages out before then. Verified: a live run today reports
`stale_found: 0, outcome: "nothing older than the cutoff"`.

**62 MB is the number that shaped the design.** A single full-table read of this table at steady
state is precisely the out-of-memory shape that has taken this instance down before — and it did so
again during this work: a probe that chained four unfiltered reads returned **502 from the
instance**. Nothing was lost and no live workflow was deactivated, but it is why the prune never
scans the whole table.

## 3. Why the prune is its own workflow, not a step in the receiver

You offered either. I chose the separate workflow, for two reasons:

1. **The receiver is the one thing with a perfect record** — 5 nodes, 1,562 runs, zero errors, on
   the hot path of every Pipedrive event. Adding a read-and-delete loop to it puts table-sized work
   on that path and risks the asset you explicitly said to keep as is.
2. **The prune can then be bounded.** It reads `received_at < cutoff` **server-side** — so its read
   is one day of aged-out rows (~215), never the table. `lt` and `gte` were verified to work
   server-side on this column before anything was built on them.

Other properties worth knowing:

- **Capped at 500 deletions per run.** A backlog gets worked off over several days rather than in
  one burst.
- **Counts outcomes, not items.** The delete node can hand back an error item; the report separates
  `deleted` from `failed` rather than reporting the input count as success.
- **Refuses to report "nothing to prune" off a failed read.** A zero-row result is the *normal*
  answer here, which makes empty and unreadable genuinely indistinguishable — so the plan step
  checks positively for the row shape and throws on anything else.
- **A second, independent date check** re-filters in code, so a server-side filter that silently
  stopped filtering cannot delete live rows.
- It has both a daily schedule and a manual webhook (`{{WEBHOOK_I04_EVENT_LOG_PRUNE}}`), matching the
  established pattern in `dnc_escalation_detector`. That fan-in of two triggers into one CONFIG
  node will produce one `R02` *medium* linter finding, the same accepted one that workflow already
  carries.

## 4. Morning digest

The HEALTH line used to end with `· I-04 ok | FAILING | unreadable`, computed by asking the n8n API
how the summary workflow was doing. It was reporting **FAILING**.

Two nodes were swapped in place — same position in the chain, no other node touched:

- `I04 Last` (n8n API → executions of the summary) → **`CRM Changelog 24h`** (event table, filtered
  `received_at >= since` server-side)
- `I04 Status` → **`Changelog Count`**

The line now reads **`· CRM change log 208 events`**. It measures what the receiver actually
captured, not whether a reporting job ran.

Three details kept in line with the digest's own rules:
- an unreadable read prints **`unreadable`**, never `0`, and adds a line to the "not measured"
  footer;
- I-04 no longer contributes to the red/amber/green status — an unreadable change log is **amber**,
  not red, because it is an observability gap, not a failure;
- `CONFIG.i04_workflow_id` was removed and `event_table_id` added.

**Verified before hand-off:** the exact deployed read and count nodes were run against the live
table on a throwaway workflow and returned **208 events in the last 24 h (90 leads, 118 persons)**.
`Compose` passes a syntax check, contains no I-04 references, and does contain the change-log ones.

## 5. Item 3 — not done, and why

> *"WF-2S watches that the daily digest still runs — remove that check so it doesn't start
> reporting a dead component."*

**WF-2S does not watch I-04.** It watches `nK3yIOqRcBearV8s` — **`WF-2H Health & Digest`**, the
Smartlead-volume digest that runs daily at 07:15, has 20 runs in the retention window, and is not
part of I-04. Evidence:

- WF-2S's CONFIG contains exactly two workflow ids: `wf2h_workflow_id = nK3yIOqRcBearV8s` and
  `wf2_workflow_id = jp7rum9Z0YDJkQWv`.
- Searching WF-2S for all three I-04 ids returns **nothing**.
- The watch node's own comment: *"WF-2H runs once a day and cannot observe its own failure — it
  errored on every run of its life and only a manual sweep noticed. This workflow runs every 15
  minutes, so it is the natural watchdog."*

Removing it would delete a live safety net for a component that is staying, and would not stop
anything reporting on I-04. **The only thing that reported the retired summary was the morning
digest, and that is fixed.** Say the word if you want it removed anyway.

## 6. Sweep — nothing else expects these

A full re-scan of all 40 workflows for `8sT1XjDDVmrz05CA` and `gjVZkkvm05jj8CNM` returns
**zero references**. The only remaining mentions of the two orphaned tables are inside the two
retired workflows themselves, which is what preservation means.

## 7. Orphaned tables

`i04_snapshots` and `i04_walk_staging` now have **no active reader or writer**.

**Do not build on them.** Both are referenced **by name**, not by id — a form that has failed live
on tables that certainly existed, and the reason `R13` exists. Anything that needs them must first
convert to `mode: "id"` with the id from the table's URL. They are left in place, not deleted.

`i04_event_log` (`zAW2IYoO6Dj0vdIt`) is referenced **by id** by both the receiver and the prune,
which is correct.

## 8. What was lost and what was kept

**Lost — automatic detection of bulk changes.** The daily summary flagged ten or more distinct leads
updated inside the same minute, which is how a label-wiping automation was caught before. Nothing
watches for that now. The raw material is still in the event log, so the question is answerable
retrospectively — but only if someone asks.

**Kept — full retrospective traceability.** Every lead and person change is still recorded with its
action, object, timestamp and raw payload. "Who changed this, and when" remains answerable for 90
days.

**Unchanged — departures inside a window with no snapshot were never recoverable.** The weekly
reconciliation was the only thing that could have caught them and it never ran once. That limit is
now explicit instead of implied.

## 9. Rollback

`backups/` holds each workflow's exact pre-change definition. To restore one, PUT its
`name`/`nodes`/`connections`/`settings` back to the same id, stripping `availableInMCP` from
`settings` first, then reactivate. To retire the prune, deactivate it — deleting it is not required
and not recommended.
