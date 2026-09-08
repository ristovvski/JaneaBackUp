# I-04 CONSOLIDATION — 2026-08-27

Запрос: all three legs were dead simultaneously (local cron 6 days silent, daily_summary crashed
on 'Load Watermark' — exec 34078, weekly recon 0 runs ever). Fix as one package, 5 points.

## 1. daily_summary 'Load Watermark' bug — FIXED, deployed live

Root cause (verified live, not guessed): `Load Watermark Row` (dataTable get) points at
`i04_snapshots` — that table **does not exist at all** (`"Could not find the data table:
'i04_snapshots'"`, confirmed by an isolated live probe, not a `mode:"name"` resolution flake this
time). With no `onError` set, n8n never even scheduled the downstream `Load Watermark` code node —
not "ran with 0 items," genuinely never invoked — so `Summarize`'s unconditional
`$('Load Watermark').first().json` read threw. Today's crash was this workflow's FIRST real
attempt at its 05:30 slot (it was created after 05:30 on 08-26, so its only two lifetime
executions are an 08:00 idle-guard tick that day and today's crash — not a regression, a bug that
had never been exercised yet).

Fix: `Load Watermark Row` now runs with `onError: continueErrorOutput`, and **both** its outputs
(success incl. empty-on-first-run, and error incl. "table missing entirely") are wired into
`Load Watermark`. Its own JS already handled every one of those shapes gracefully (falls back to a
24h lookback whenever `counts_json` is absent) — this was always a wiring gap, not a logic gap.
Also made `Save Watermark` fail-open (`guard=False`) — it writes into the same missing table, and
without this a missing table would still red the whole execution even after Post Summary already
sent Slack the message successfully.

Verified live: isolated minimal repro (webhook → Load Watermark Row → Load Watermark, table
missing) returned a correct 24h-fallback `since`/`now` pair end-to-end. Deployed to the live
workflow (`8sT1XjDDVmrz05CA`) via a surgical patch (diffed every node + the connections dict against
regenerated local JSON, confirmed only the intended nodes differed, deactivate → PUT → reactivate
→ verify).

## 2. Weekly reconciliation staged fire — BLOCKED, cannot fire

**Correction to what was previously recorded**: this was tracked as "blocked on `mode:"name"`
resolution, need the real table id." That was wrong. Verified live just now: **`i04_snapshots` and
`i04_walk_staging` do not exist as tables at all** — no amount of `mode:"id"` substitution fixes
this, there is no id to substitute. Checked every live workflow on the instance (32 scanned) for
any prior reference that might carry a resolved id — none exists anywhere.

This is architecturally unfireable right now: the weekly walk stores its walk-state sentinel rows
*inside* `i04_snapshots` and its per-record staging rows in `i04_walk_staging` — without both
tables, the very first tick would fail the same way daily_summary just did.

**What's needed before this can move at all**: Nik (or whoever has table-creation access) needs to
create both tables — specs already written and posted earlier: `CREATE_I04_SNAPSHOTS_TABLE.md`,
`CREATE_I04_WALK_STAGING_TABLE.md` (both in this directory). Once they exist, the 10-page staged
chunk → verify → Sunday activation sequence can run as originally planned — nothing else is
blocking it.

## 3. Deal-conversion arm for Check 1 — DONE, static test with today's real 13 passes

Added to `i04_diff.py` (the local script, not n8n — "Check 1" is its own LEAD DEPARTURES check):
`classify_conversion()` (pure, no network) and `find_conversion_deal()` (one READ-ONLY
`/v1/persons/{id}/deals` call per 404'd departure, bounded to the deleted-count). A departure only
prints "irreversible, escalate" now if no deal evidence is found; converted ones print separately
and are excluded from the escalation alert.

Two-tier evidence, weakest tier only used when the strong one is unavailable:
- **timestamp** (tight): a real delete-webhook timestamp is known and a deal for the same person
  was created within ±60s.
- **window** (fallback, for departures inside the un-snapshotted 08-21→08-26 gap with no webhook
  record): a deal was created sometime inside the diff's own snapshot window.

Static test (`test_i04_conversion_static.py`, no network) replays today's real 13 as fixtures —
lead/person ids and real deal `add_time`s pulled live from `/v1/persons/{id}/deals` for all 13,
delete-webhook timestamps for the 6 that have one (from today's post). **20/20 checks pass**: all
13 classify CONVERTED (6 via tight timestamp match, 7 via window fallback, matching exactly what
today's manual investigation found by hand), plus 4 negative/boundary cases (no deal at all, a
deal outside the window, a 90-minute-off same-day deal that must NOT count as tight, and the exact
60s/61s boundary).

Not yet exercised on a live re-run of `i04_diff.py` (next natural run is whenever it's next
invoked) — the classification logic itself is proven correct against real data, not just live-fired
end to end.

## 4. Retire local cron — NOT YET, correcting the premise

Cannot post the "safe to kill" line — the replacement isn't ready. `dnc_i04_weekly_reconciliation`
has **zero successful executions ever** (blocked by #2) and `dnc_i04_daily_summary`'s only real
attempt crashed until the fix above. Right now the **local cron is the only thing that produced any
full-estate reconciliation coverage at all** in the last week — today's manual run is what caught
both the 13 false-positive deletions and the 3 undeclared archived departures. Killing it now would
remove the only working safety net.

**Actual state per leg**:
- `dnc_i04_event_receiver` — healthy, 47/47 success, but only covers events from its own creation
  (08-26T07:10Z) onward. Fine as the event-capture leg.
- `dnc_i04_daily_summary` — fixed above, unverified in production yet (next real test is tomorrow's
  05:30 UTC slot, or whenever manually confirmed).
- `dnc_i04_weekly_reconciliation` — cannot even start until #2's tables exist.

Retirement becomes safe once weekly_reconciliation has run successfully at least once (ideally a
few weeks in a row) AND daily_summary has a clean streak. Not there yet — this is the honest one
line: **not yet, blocked on #2**.

## 5. Self-guard proof — FIXED, kill-tested

The existing idle-guard (`Idle-Guard Trigger` → `Check Idle` → `Missed Today?` → `Idle Alert`) was
real but too coarse to matter: it only ticked once a day (8am UTC) and compared date STRINGS
("did the date change"), so a same-morning crash like today's could go unreported for up to 24h.
That's why "neither path reported its own death" today — the daily post crashed silently (no Slack
message at all, no separate alert about the crash itself), and the idle-guard's own 8am check
hadn't fired yet when this investigation started (current time was still ~06:10 UTC).

Rebuilt: ticks every 15 minutes now, compares against the real 05:30 UTC slot + a 45-minute grace
using actual timestamps (not date strings) — guarantees the first scream lands on the 60-minute
tick at the latest. Re-arms automatically the next day (still just a date comparison for the
"already posted today" check — no sticky flag, no manual reset).

**Kill-tested** (`zz_killtest_idle_guard.js`, 6 scenarios, pure logic replay, no live risk to
production Slack):
1. 40min after a missed slot → correctly stays quiet (inside grace).
2. 65min after a missed slot → correctly screams.
3. Already posted today → stays quiet all day.
4. Never-initialized static data → reads as missed (fails loud, never silently "healthy").
5. A fresh success the next day → auto re-arms, no manual reset needed.
6. Cadence sweep (every 15min from slot to +90min) → first scream lands exactly at +60min, never
   later.

All 6 pass. Deployed live to `8sT1XjDDVmrz05CA` via the same surgical-patch method as #1.

## Improvable
- `dnc_i04_weekly_reconciliation` staged test itself remains fully blocked, not just delayed — flag
  to Nik as the single highest-priority unblock (#2 above).
- Once the tables exist, re-run `classify_conversion`'s live path (not just the static fixture) end
  to end against a real weekly-walk departure to confirm the wiring, not just the unit logic.
- The idle-guard currently only exists for `dnc_i04_daily_summary`. `dnc_i04_weekly_reconciliation`
  will need its own (looser-cadence, since it's weekly) once #2 unblocks it — not built yet.
