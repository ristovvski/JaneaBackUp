# 2026-08-31 — two alert loops killed, channel-split table posted, gate + Finovate status

Requested by Nik in-terminal. Read-only investigation, then two live deploys, then a
gated proposal. Backups of every touched workflow: `audit-artifacts/wf_backups_2026-08-31/`.

## DONE

### 1. `dnc_gate_queue_drainer` "STUCK" — false alert loop, killed

**Root cause was not the predicate, it was the wiring.** `dnc_pre_add_gate_monitor`
(`g8MUOKFlUaeVrdBx`) had `Queue Stuck? [out 1] -> Alert: Queue Stuck`. Output 1 of an n8n IF
is the **FALSE** branch. So the node posted "STUCK" on precisely the ticks where
`should_alert_queue` was `false` — i.e. every 15-minute poll, 96/day. Proven on execution
39292: `Queue Stuck?` branches `[0, 1]` (nothing on TRUE, one item on FALSE) and
`Alert: Queue Stuck` ran anyway.

The 08-28 predicate fix (positive shape check, explicit `depth > 0`) was correct and is
still in the code — it just could never help, because the alert was not reading the
predicate's TRUE branch.

**Two further defects underneath it:**

* `dnc_gate_queue` does not exist. Not a `mode:"name"` resolution flake — proven on the live
  gate: `Log Ingress`, `Check Queue Depth` and `Mark Sync Done` all report
  `status=error` on **every** gate execution, silently, because all three are
  `onError: continueErrorOutput`. The gate has had no ingress audit log since it was added
  on 08-26, and `Enqueue Rows` has never run.
* Missing read as zero. `Check Queue`'s error output carried **no marker** — it echoed the
  input items (the documented non-uniform dataTable error shape), so
  `$('Check Queue').all()` returned `[]` from output 0, `[].every()` was `true`, and depth
  came back `0` instead of `null`. That is why the message said "depth 0".

**The alert text was false in its own right.** "Real Clay/Stefan requests are waiting past
the accepted ~30min turnaround" — no real request has ever reached the gate. All 15 retained
gate executions are the monitor's own 2-row probe. `dnc_gate_queue_drainer` has **zero**
executions.

**Fix — took the strip option.** Deleted `Check Queue`, `Queue Stuck?`, `Alert: Queue Stuck`;
`Merge Health Paths` 3 inputs → 2; queue logic removed from `Track + Report`.
13 nodes, versionId `1ed40f89`.

### 2. `dnc_i04_daily_summary` dying at Summarize — fixed

The 08-27 patch did not touch this. All five daily runs 08-27 → 08-31 died identically at
`Summarize` with `Node 'Load Watermark' hasn't been executed`.

**Root cause: a fan-in race, not the watermark.** `Load Watermark` *and* `Get New Events`
were both wired into `Summarize`'s input 0. n8n fires a node once per branch **arrival**, and
under `executionOrder: v1` `Get New Events` (y=180) is scheduled ahead of
`Load Watermark Row` (y=300), so `Summarize` always fired on the wrong branch and threw
before the watermark existed. `Combine Summary` had the identical shape
(`Summarize` + `Check Subscriptions` both into input 0).

Same class as the already-recorded "n8n Merge append is not a barrier" note: **two producers
into one input is not a join.**

**Fix** — one linear chain, no fan-in except success/error pairs where only one side can fire:

```
CONFIG -> Load Watermark Row -> Load Watermark -> Get New Events -> Summarize
      -> Check Subscriptions HTTP -> Check Subscriptions -> Combine Summary
      -> Send Guard -> Post Summary -> Mark Posted Today -> Save Watermark
CONFIG -> Get Old Events -> Compute Old Events -> Split Old Events -> Delete Old Event
```

Also fixed in the same pass:

* `Mark Posted Today` moved **after** `Post Summary`. It used to run before `Send Guard`, so a
  post that never reached Slack still told the watchdog "posted today" and silenced it.
* `Load Watermark` now reports `watermark_source` (`persisted` / `fallback_24h`) with a
  positive row-shape check. `i04_snapshots` is referenced by `mode:"name"` and I could not
  confirm the table resolves (no data-table endpoint in the n8n public API), so the summary
  now **says** when it is standing on a 24h fallback instead of implying a persisted window.
* `Check Subscriptions` distinguishes UNREADABLE from "no active subscriptions" — an
  unreachable Pipedrive was about to read as a dead webhook.
* `Summarize`'s watermark lookup is now guarded so an off-sequence run degrades, not throws.

versionId `d66d5f04`.

### 3. Class rule — alerts fire once per state change, never per poll

* Monitor: `Track + Report` keeps `sd.gateUnhealthy`; new `Gate Failed (edge)?` fires only on
  the false→true transition, and a new `Gate Recovered (edge)?` + `Alert: Gate Recovered`
  closes the loop so "still broken" is distinguishable from "broke again".
* I-04: `Check Idle` keeps `sd.idleAlertedForDate`; at most one idle alert per calendar day.
  Text now says `never` rather than rendering an empty `last post: `.

**Verified live**, monitor execution 39305 at 06:45:57Z: `Merge Health Paths` fires with one
item, both edge-IFs route to FALSE, **zero Slack posts**.

### 4. Channel-split enumeration table — posted, not deployed

Three messages in #niks-channel (`p1788159070737269`, `p1788159093467549`,
`p1788159119795789`). **Exactly three ACTIVE nodes post to #lead-processing:**
WF-1 `M7 Critical Slack`, WF-2 `Reply Alert`, WF-2 `Nurture Alert`.

Nodes 1 and 2 each emit *both* a resolved and an unresolved shape from one node, so rule 4
("static per posting node") requires a genuine node split gated on `lead_id`, not a runtime
channel expression: +2 nodes in WF-1, +2 in WF-2.

## PARTIAL / UNPROVEN

* **The I-04 05:30Z path is deployed but not proven live.** A replay of execution 39267
  against the fixed workflow (`POST /executions/39267/retry {"loadWorkflow":true}`) was
  blocked by the permission classifier. First real proof is tomorrow's 05:30Z run.
* `Alert Post Failed` in `dnc_i04_daily_summary` is now an orphan node (its only producer was
  `Post Summary [out 1]`, and `Post Summary` has `onError: None` so that output never
  existed). Left in place deliberately: `Post Summary` failing should hard-fail the execution
  so `WF-ERR` catches it, which is better than a no-op code node swallowing it.

## BLOCKED

* Channel split itself — waiting on Nik's answers to Q1 (Nurture Alert), Q2 (Table B breadth),
  Q3 (telemetry), and the `M7 Labels Compute` hardcoded-`__TEAM` exception to rule 2.

## STATUS ANSWERS

### Gate

* `dnc_pre_add_gate` (`9aP2dP0jgAPFGDvA`) — **ACTIVE**, 24 nodes, versionId `a732bfb1`.
* **It is v2** — the sub-workflow fan-out is gone (no `executeWorkflow` to
  `DNC__CheckLedger__v1`; the two lookups are inline as `Get Registry Match (Batch)`).
  v2 was deployed 2026-08-26 as `c5eb6a6a`; `a732bfb1` is the 08-26 16:47 successor.
* **Classification is healthy.** Every 15-minute probe returns
  `total 2 / clean 1 / blocked 1 / unresolvable 0`, latency avg ~3.2s.
* **Three nodes are permanently and silently erroring** (`Log Ingress`,
  `Check Queue Depth`, `Mark Sync Done`) because `dnc_gate_queue` is absent. The gate answers
  correctly; it just has no ingress log and no queue. Stripping those from the gate is the
  other half of the strip option and is **not yet done** — it is live-DNC-gate surgery and I
  did not bundle it with an alert fix.
* **Fixture is Dennis, not Barry.** The probe is
  `pii-d50f3785@example.invalid` (known-blocked, resolves to real registry row 31517) plus
  `monitor-clean-probe-xyz@example.invalid` (known-clean). "Barry" in this estate is
  **Person-69cbb908**, the 2026-08-20 split-identity corroboration case in
  `DNC__UpsertLedger__v1` — a different thing entirely, and that workflow is inactive.

### Finovate

The **9-lead email backfill did run and holds** — independently re-verified today against
Pipedrive, not re-read from the fire report: persons 85881–85889 all exist, each with exactly
one campaign-titled lead, person-linked, owner Noah (25733113).

What did **not** run:

1. `dnc_i04_weekly_reconciliation` (`gjVZkkvm05jj8CNM`, 53 nodes) — **INACTIVE, zero
   executions ever.** This is the literal reconciliation that has never run.
2. **The 105 LinkedIn Finovate members** — deliberately deferred, not dropped: the
   contacted-only ruling scoped the fire to the 9 email members because 25/25 contacted
   LinkedIn members already had leads. Under "membership = existence" those 105 are still
   owed leads, and no upload-time creation mechanism exists for any campaign family.
3. **Person-a9a7d542's bounce-as-reply** — still open as a class. Checked his record today: lead
   `378cdb50`, labels `['1. Cold']` only, **no** false `3. Responded`, zero activities. So the
   bounce never contaminated the CRM; the damage was confined to the Slack announcement.
