# 2026-08-06 — R2 (WF-2R reply reconciler) + R3 (delta digest) + C2 guard re-check

## Done

### C2 Handover guard re-check with v2 (`c2_handover_recheck_v2.py`)
The old guard sat on `/v1/activities?lead_id=`, which silently returns zero. Re-measured:

| set | leads | with an open Handover |
|---|---|---|
| backfill-25 (received `3. Responded`) | 2 | **1** (Person-ef1ea617) — invisible to the v1 guard |
| backfill-300 (cold-only) | 374 | **0** — empirically confirms the task-log reasoning |
| all Melisa-owned `3. Responded` leads | 25 | **19** |

The 19, by creation day: 07-24 ×1, 07-28 ×1, 07-31 ×4, 08-05 ×7, 08-06 ×6. The 08-05 batch is
what yesterday's blind guard could not see. **Melisa's real number is 19 open Handovers, 6 of them
today's recovered replies.** Standing decision applied: LEAVE them — legitimate queue, not litter.

Added a **BANNED ENDPOINTS** section to `wf1-system-reference.md` (§9b) covering the v1-activities
silent null, v1-activities `owner_id`, unsorted `/v1` list counting, `persons/search` by name,
`statistics.reply_time` as a reply source, and substring-over-blob field checks — each with its
measured failure and its replacement. Also recorded the Handover-hydra behaviour there.

### R2 — WF-2R Smartlead REPLY Reconciler
Built (`build_wf2r.py`), 37/37 static contract tests green (`wf2r_static_contract_tests.js`),
deployed **INACTIVE** and round-trip verified (`deploy_wf2r.py`).

- id `U8Bb7Pdq7S6nzYPa` · versionId `77cec14e` · 23 nodes · **active: false**
- polls `leads-statistics` `history[] type=="REPLY"` — the proven surface, asserted by a test
- **claim-after-success**: store read in Find New Replies, written only in Summary and only for
  replays WF-2 accepted; a rejected replay stays retryable
- `max_per_run: 20` (owner spec), **one campaign per cycle** round-robin (OOM guard — walking all
  four campaigns at once is what OOM'd this instance on 2026-07-30)
- reply floor stamped at deploy (`2026-08-06T13:50:17Z`) so the first cycle cannot replay this
  afternoon's manual backfill
- mutual watchdog: WF-2R watches WF-2S (nothing watched WF-2S before); a blind watchdog reports
  STALE rather than healthy

**Two real bugs the tests caught before deploy:**
1. A stray `)` in `Build REPLY Payload` — the node would have thrown on every cycle.
2. **`lookback_minutes: 300` was wrong by design.** WF-2R replays *into* WF-2's webhook, so during
   a WF-2 outage its own replays are rejected and correctly left unclaimed — recovery only starts
   once WF-2 returns. A 5h window would have aged out the 973-minute outage's replies before that,
   recovering nothing while looking healthy. Now **2880** (48h), with a validator and a test
   asserting `lookback > 973`.

### R3 — delta digest (`r3_delta_digest.py`)
Per campaign: **Smartlead truth | WF-2 processed | delta**, delta>0 = alarm, `0|0|0` renders as
"no traffic — path UNVERIFIED", plus a "last real (non-probe) inbound webhook" line that excludes
our own probes by user-agent.

Live today: 24h = `0 | 0 | 0` → **path unverified**, last real inbound webhook **47h ago**
(UA `axios/1.18.0`); 9 probe executions correctly excluded. 72h = 10 leads / 1 processed /
**delta 9**. Posted: https://janea.slack.com/archives/C0B8GCVNR5W/p1786024796782649

**Bug caught in my own digest before shipping:** v1 compared 12 reply *events* against executions
deduped by *email*, and printed every reply of an alarming campaign rather than the unmatched
ones — it named `richard.spitz` as lost when execution 13143 had processed him. A digest that
cries wolf on a handled reply is the mirror of the bug it replaces. Now a set difference at lead
granularity, with raw event counts reported alongside.

## WF-2R activated — and the first cycles exposed a defect I had shipped

Activated 14:04Z after asserting (not assuming) the safety property: the newest backfilled reply
(adeshpande, 2026-08-05T06:08:38Z) sits **31.7h before the reply floor**, so all ten hand-backfilled
replies are structurally unreplayable. The activate script was written to refuse if that failed.

First 5 cycles: all `success`, 0 incomplete page walks, 0 replay batches, **0 backfilled leads
touched** — the floor behaved exactly as designed (`floored` counts of 20/29/16/28/6).

**But the cycles were polling AWS Re:Invent and AI Summit NYC campaigns, not the four Ai4 ones.**
My rotation filter was "any non-ARCHIVED/DRAFTED campaign", and I had documented that as "~4
campaigns, ~60 min per sweep". Measured reality: **114 campaigns** (5 ACTIVE, 98 COMPLETED, 11
PAUSED) → **28.5 hours per full sweep**. Inside the 48h lookback, so nothing would have been lost,
but a reply could wait a day to be noticed — which guts the flip-gate sensor.

**Fix (built, tested 43/43, redeployed, verified):** two-ring rotation, still one campaign per
cycle so the no-attribution-risk property holds.

| ring | membership | share of cycles | full sweep |
|---|---|---|---|
| hot | ACTIVE (5 today — all four Ai4 campaigns are ACTIVE) | 3 of 4 | **1.7h** |
| cold | non-ACTIVE created within 180d (20 today) | 1 of 4 | **20h** |
| excluded | older than 180d (89) | — | reported every cycle, never silent |

Every cycle now recomputes both sweep times against the lookback and raises `__sweep_overrun` if
either ring has grown past it — the defect was an unchecked assumption about scale, so the workflow
measures its own scale instead of trusting a comment. A build-time validator asserts the same at
today's ring sizes. Live: versionId `0b30dcf6`, active, floor preserved, backup
`wf2r_backup_before_tworing_1786029634.json`.

**Lesson:** the static tests all passed against a 4-campaign fixture that encoded my assumption.
Only live observation caught it. Same family as `verify-shapes-before-fixtures` — a fixture that
agrees with the belief cannot falsify it.

## Not done / next

- **WF-2R is INACTIVE.** Activating it while WF-2 is in shadow writes nothing and would catch the
  next organic reply end-to-end — i.e. it can satisfy the R4 flip gate on its own. Needs a word.
- **R4 flip gate** still open: no real inbound reply since 2026-08-04T14:15Z. Rune's answer to
  hwang's "How about 5pm?" is the natural organic trigger; fallback is a controlled reply Thursday
  evening.
- Duplicate forensics sweep (task #9) still parked — owned by the other session.
