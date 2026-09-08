# 2026-08-31 — MORNING DIGEST (`dnc_morning_digest`)

Built, deployed, **ACTIVE**. Workflow id `qJKfR602wV9yfFrj`, 40 nodes, timezone
`Asia/Jerusalem`, cron `0 7 * * *`, errorWorkflow `WF-ERR`. Posts once a day to `C0BTP6VHP1B`.
Statics 61/61, re-run against the definition read back from the API after deploy.

## One manual step before it can post

`C0BTP6VHP1B` has exactly **one member: U0B64BVFK45 (Mykyta)**. The Slack app the digest posts
with — the `Smartlead Slack` credential, bot user `U0BLBUP50FM` — is **not in that channel**.
Until someone runs `/invite` for that app there, the 07:00 run will fail into WF-ERR rather than
post. Deployed active anyway so the schedule is live the moment the invite happens.

## Shape facts this build stands on — all probed live, none assumed

| fact | why it mattered |
|---|---|
| `/campaigns/{id}/statistics` **honours** `sent_time_start_date` / `sent_time_end_date` (3565502: 4381 rows → 570 for a 2-day window → 0 for an empty one) | makes a 24h count exact without paging |
| the same endpoint is **not time-ordered** (observed 07-13, 07-13, 07-17, 07-20, 07-14) | paging to a limit would have silently sampled the wrong rows; the date filter is what makes it safe |
| `?email_status=bounced` total equals `analytics.bounce_count` on 7/7 campaigns | bounce split is trustworthy |
| `/v1/leads` **without** `sort=add_time DESC` returns the OLDEST page (2023 rows) | the digest proves the sort applied before counting, and suppresses the count if it did not |
| `/campaigns` list carries **no** `sent_count` — only `/analytics` does | the integrity gap needs a second call per campaign |
| HeyReach active status is `IN_PROGRESS`, not `ACTIVE` | checking for ACTIVE would have reported 0 of 3 |
| `/api/v2/leads/search` silently returns **0 items** when `limit=500` | first attempt reported "no leads found" for campaigns that have 47 |
| `POST /stats/GetOverallStats` takes `campaignIds` + date range, returns `byDayStats` | LinkedIn 24h volume without walking leads |
| WF-2H declares its schedule as `{triggerAtHour, triggerAtMinute}` with **no `field` key** | the first extractor skipped it — a real schedule silently unmonitored |
| the DNC ledger active set is 25,653 rows and `dnc_escalation_detector` already walks it **hourly** | a once-a-day walk is proven safe, not hoped safe |
| **no enrichment queue exists anywhere** — no dataTable, no drainer; WF-2 enriches synchronously | reported as ABSENT, never as `0` |

## Sections

Five lines, one per section, plus a header and a "not measured" footer — capped at 12.

1. **CAMPAIGNS** — SL active count + HR active count, per-campaign sends-24h and next step with its
   due date (computed from the last send in a 30-day lookback + the step's `delayInDays`; rendered
   as `≥date` when the lookback page truncated, never as a false exact).
2. **VOLUME 24h** — email sends, LinkedIn messages/invites, replies split real / OOO / bounce
   (bounce by `is_bounced` only), new Pipedrive leads with a source breakdown.
3. **INTEGRITY** — sent-without-lead per campaign, leads without a person, nameless campaign leads.
   Zeros are printed, not omitted.
4. **DNC** — active set, +/- in 24h, gate health with latency, read from the monitor's own last
   probe rather than by firing the gate again.
5. **HEALTH** — failed executions (`status=error` only — the unfiltered list under-returns),
   missed schedules per-workflow, I-04 status, no-match count.

## Design rules it holds to

* **It posts every day, including a wholly green one.** There is no is-this-interesting gate in
  `Send Guard` and there must never be one: a missing message must mean the job did not run.
* **Missing is never zero.** Every section has a positive shape check; an unreadable source
  renders amber and names itself in the footer. Statics drive all ten HTTP sources unreadable one
  at a time, plus the documented echoed-input shape, and assert the digest never renders a fake
  green.
* **One clock.** Every section measures against the same window, so the sections reconcile.
* **No fan-in.** 40 nodes in a single linear chain; the builder asserts no node has two producers.
  (This is the defect that killed I-04 for five days.)
* **Zips are proven where they can be.** `/analytics` echoes its own campaign id, so that pairing
  is verified; the statistics pairing cannot be proven from content, so a length mismatch degrades
  the section to amber instead of attributing a number to the wrong campaign.
* **Page saturation is reported.** Full pages on leads, errors and the campaign lead search make
  the affected number a stated floor.
* Channel ids are CONFIG-driven; a static asserts no other node carries the literal.

## What it found on its first render (live fixtures)

* `s2 due 2026-09-04` on both Finovate campaigns — independently reproduces this morning's
  conclusion that the Smartlead silence is a 7-day sequence gap, not a fault.
* **72 nameless campaign leads** (`{id} - {campaign}` with no person suffix) across 3868449/3868450
  — the class in Nik's screenshot. Renders red.
* 1 sent-without-lead on 3868449.
* 53 new leads in 24h, all with a person; 50 of them HeyReach.
