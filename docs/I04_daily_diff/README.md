# I-04 — the daily Pipedrive anomaly diff

> **⚠ SUPERSEDED IN PART — 2026-09-03: the I-04 simplification.**
> `dnc_i04_daily_summary` and `dnc_i04_weekly_reconciliation` were retired (deactivated and
> preserved). `dnc_i04_event_receiver` stays as a silent change log, and a new
> `dnc_i04_event_log_prune` keeps 90 days. The morning digest no longer reports I-04 status; it
> reports `CRM change log N events`. Tables `i04_snapshots` and `i04_walk_staging` are now orphaned
> and are referenced by name — do not build on them.
> Detail: [`I04_SIMPLIFY_2026-09-03/REPORT.md`](../I04_SIMPLIFY_2026-09-03/REPORT.md) · rule R-G in `RULEBOOK.md`.



**The invariant:** *no change to the CRM goes unnoticed for more than a day.* This is the answer to
Sergey's "1,500 leads could vanish and nobody would notice".

## Why a persisted snapshot is the whole point

Archived leads are **invisible to every Pipedrive list read** — `/v1/leads`, `/v1/leads?person_id=`,
and `archived_status` is silently ignored on both (proven with a known-archived positive control,
lead `5050e6a0…`, person 70255 → 0 rows either way; only `/v1/leads/search`,
`/api/v2/leads/search` and `/v1/itemSearch?item_types=lead` reach them, and all three are
term-based, so there is no way to *enumerate* what left).

So a lead that leaves the estate can only ever be detected by comparing today's id set against a set
persisted **before** it left. **A day without a snapshot is permanent blindness** — the 13–14 Aug
2026 archival wave can now only be bounded (6 leads, found because they happened to leave a dangling
activity behind), never counted.

## The two scripts

```bash
python i04_snapshot.py            # live walk, snapshot for today  -> audit-artifacts/snapshots/pd_YYYY-MM-DD.json.gz
python i04_diff.py                # diff the two newest snapshots  -> audit-artifacts/i04_diff_YYYY-MM-DD.json
```

Both are **read-only** against Pipedrive. The only writes are the snapshot and the diff report, both
under `audit-artifacts/`. `i04_snapshot.py` also accepts
`--date YYYY-MM-DD --leads <walk.json> --persons <walk.json>` to seed a snapshot from an existing
walk; `i04_diff.py` accepts `--prev`/`--curr`.

Snapshot size is ~2.4 MB gzipped per day (~0.9 GB/year). Shape is deliberately minimal — it has to
stay cheap enough to keep forever:

```
{date, captured_at, source, counts,
 leads:   {lead_id:   [labels_joined, person_id, add_time]},
 persons: {person_id: [add_time, update_time, email_lc, lh_slug, dnc686]},
 dnc_labelled: [lead_id, ...]}
```

## The five checks

| # | check | why |
|---|---|---|
| 1 | **lead departures** — ids present yesterday, absent today; each detail-read and classified archived (+`archive_time`) or **deleted** | the only check that cannot be reconstructed later |
| 2 | **reconciliation** — `yesterday − departures + arrivals == today` | if it does not close, something moved that neither set explains |
| 3 | **DNC label set** — must equal the 7 expected survivors **by id, not by count** | the reversal's standing invariant |
| 4 | **new persons** — each checked for a duplicate (same email or same LinkedIn slug) against the whole estate | caught the `p85764`/`p85765` website-form double-fire |
| 5 | **danglers + 686** — activities touched since the prior snapshot whose `lead_id` is not in today's live set, plus the DNC field-686 population delta | an open task stranded on an archived lead is invisible to its owner |

## Missing is not zero

If a snapshot's source never captured the DNC field, it records `None`, **not 0**, and the diff
prints *"delta NOT COMPUTABLE"* rather than a fake `+2262` jump. Any future field added to the
snapshot must follow the same rule.

## Acceptance — it works, proven cold

Run against the real 19 → 20 Aug pair with no knowledge of what had happened:

```
1. LEAD DEPARTURES: 162   arrivals: 3
   archived : 162   [('2026-08-19', 162)]      <- found the London dedup unaided
   DELETED  : 0
2. RECONCILIATION: 57854 - 162 + 3 = 57695 vs 57695 walked -> OK
3. DNC LABEL SET: 7 labelled | matches the expected survivors exactly: True
4. NEW PERSONS: 4 — all ok, no duplicates
5. DANGLERS: 0 ... 686 delta NOT COMPUTABLE (seeded prior snapshot)
```

Two honest caveats on that run, both seeding artifacts that disappear once two real snapshots exist:
check 5's window was ~0 because the seeded 19 Aug snapshot carries today's `captured_at`, and the
686 delta was unmeasurable for the reason above.

## Reading the verdict

`archived departures are expected only if an operation declared them` — the diff cannot know whether
an archival was sanctioned. **Cross-check departures against the day's §9f.2 posts.** An undeclared
archival wave is exactly the finding this exists to produce.

## Daily job — RETIRED 2026-09-08

**The scheduled task `i04-daily-diff` was deleted on 2026-09-08 (Nik's call).** Its `SKILL.md` is
left at `~/.claude/scheduled-tasks/i04-daily-diff/SKILL.md` so the prompt is recoverable; 11 run
sessions were archived. The scripts in this folder still work when run by hand.

**Why it was killed, and the correction that matters:** the last snapshot on disk is
`pd_2026-08-28`, but the task was **not** dead — it was still enabled and its `lastRunAt` was
**2026-09-08T08:45:50Z**, minutes before the review. So the cron was firing and the *work* was
silently producing nothing, which is strictly worse than not running: the schedule looked healthy
while the invariant was not being maintained. A scheduled run is its own session, so nothing in the
estate and nobody in the channel would ever learn it had stopped delivering.

**What replaces it: nothing, deliberately.** Per the 3 Sep simplification, the surviving I-04 leg is
`dnc_i04_event_receiver` — a live change log (≈215 events/day) with `dnc_i04_event_log_prune`
keeping 90 days. That is the leg the team decided to keep.

**What that costs, stated plainly.** The change log records changes that *happen*; it cannot answer
"what left the estate", because an archived lead is invisible to every Pipedrive list read (see
above). Lead-departure detection is therefore **no longer an automated check** — 29 Aug → 8 Sep is
already unmeasurable and will stay that way. If departure detection is wanted again, the snapshot
has to live somewhere that reports its own failure — n8n, on the estate's own error path — not a
local Claude cron.

Historic behaviour, for the record: the task ran at 06:08 local and posted to **#niks-channel**
(`C0B8GCVNR5W`) — three lines when green, the full anomaly list when not.
