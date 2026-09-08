# 2026-08-26 — Аудитор: full-day post-mortem (00:00Z → 13:45Z)

Read-only. Independent — I audited none of today's incidents. Report posted to #niks-channel;
artifact `audit-artifacts/postmortem_20260826.json`.

## Headline

**172 errors today. 169 are collateral of ONE self-inflicted action. 3 are genuine bugs. 0 are
organic production failures. 0 came from the staged load tests. No data lost.**

## DONE

### §1 Error census — 172, confined to two workflows
`dnc_pre_add_gate` 121 · `DNC__CheckLedger__v1` 50 · `zz_probe_i04_full_fire` 1.
Messages: 169 OOM, 2 `body.rows must be a non-empty array` (06:08Z), 1 missing dataTable
`dnc_gate_queue` (07:45Z). By hour: 05h 140 · 06h 31 · 07h 1 · **nothing after 08:00Z**.
Bursts: 05:18(7) 05:19(33) 05:31(39) 05:59(40) 06:08(2) 06:24(3) 07:45(1).

**Deliberate vs organic:** the originating action (`zz_probe_i04_full_fire`, the full-estate I-04
walk against production) contributed exactly **one** error; the other 168 are its collateral, and
the victims were real Clay traffic — the gate served 10 successful calls in the minute before it
began crashing.

**The staged load tests did NOT crash the gate** — this contradicts the incident skeleton.
07:44–07:52Z: 209 success / 1 crash (the missing-table bug). 08:30–08:55Z: 1,256 success / 0 crashes.

**Evidence destroyed:** workflow `ShILatVJvootkmeU` deleted, execution `31181` → HTTP 404.

### §2 Lost work
* **(a)** 66 gate invocations died without answering. **66/66 retained no input payload** — the loss
  set is unknowable from n8n. Clay unreadable (`403 must be logged in as an admin`). The ask:
  rows submitted 05:18Z–06:09Z with no verdict. Mitigating: the gate is synchronous, so it returns
  an error rather than a false `clean`.
* **(b)** Smartlead 0 active campaigns, 0 stat rows today. HeyReach: the only message today is our
  own outbound (`sender=ME`, 01:22:30Z); the preceding inbound reply (2026-08-25T23:31:48Z) was
  processed by WF-1 at 23:35:48Z. Nothing dropped.
* **(c)** Receiver 15 executions, Pipedrive reports zero delivery failures. The 4 post-11:09Z person
  bumps carry zero changelog rows → no-op writes, legitimately no event. Residual: person webhook
  `last_delivery_time` stuck at 09:38:25Z; one dataTable read closes it (no public API for that).
* **(d)** S3 watcher 55/55, WF-2R 55/55, WF-2S 55/55, escalation detector 15/15 — no gaps.

### §3 Detection
Alerts fired 28–40s after each burst. **The auto-deactivation raised no alert** — Clay's 404 and a
human found it. Closed same day by `dnc_pre_add_gate_monitor` (05:33:40Z), which itself has a
29-minute hole today (07:30:43→08:00:00).

### §4 Unfinished (verifiable only)
Weekly reconciliation INACTIVE (pending GO, confirmed) · gate queue half-built (`dnc_gate_queue`
missing, drainer inactive) · `i04_walk_staging` requested 05:50Z, unconfirmed · **#niks-channel
silent since 05:59:31Z** across three workflow creations, a gate rewrite and 1,465 test executions.
Not verifiable from my seat: Noah's connections export, Finovate verdict, Stefan's recipe v3,
the Memurai lead name.

### §5 Net damage
No data lost (shown, not asserted). No check missed. Protection degraded ~51 min (05:18Z–06:09Z),
never blind — the hourly detector held. Real cost: 2,261 executions against a plan discussed as
10k/month, ~51 min of degraded pre-add cover, unknown Clay rows to re-submit, and a deleted
root-cause execution.

## IMPROVABLE — three of my own errors, all caught pre-publication

1. **The first census was wrong.** n8n's unfiltered `/executions` list omits crashed executions AND
   under-returns successes: it gave 4 failures / 1,988 executions; the truth is **172 / 2,261**.
   Corrected via `status=error` + per-workflow walks.
2. **"6-hour overnight scheduler outage"** — same bad list. Per-workflow walks show 55/55 complete
   grids. Withdrawn.
3. **Read Slack timestamps as UTC when they are IDT (UTC+3)** — correcting it is what aligned the
   alerts with the crashes and produced the detection numbers.

## New API facts

* `GET /api/v1/executions` (unfiltered) is **not a reliable census** — use `status=error` (crashed
  executions return under it; `status=crashed` is a 400) and per-workflow walks.
* n8n **data tables have no public API** (404 on `/data-tables`, `/dataTables`, `/data-table`).
* Deleting a workflow deletes its executions — `31181` → 404.
* Clay public API: `403 must be logged in as an admin` on `/v3/workspaces` and `/v3/tables`.

## BLOCKED

The Clay-side loss set and the receiver dataTable — both need access I do not have.
