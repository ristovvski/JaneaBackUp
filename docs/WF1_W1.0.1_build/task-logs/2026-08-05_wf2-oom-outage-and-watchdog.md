# Task log — 2026-08-05 — WF-2 outage: OOM, not a bad deploy. Watchdog + aborted recovery

**Scope as given:** step 0+1 — reactivate WF-2 in shadow, verify one full WF-2S cycle returns 200s;
add `active === true` to the WF-2S watchdog (and WF-2H if it reads WF-2 state); then ONE recovery
cycle with `lookback_minutes` raised to cover since yesterday 12:00Z (~830 SENT replays), confirm cap
handling, restore lookback=180, report the ledger delta; plus a root-cause note on why an activate
returning 200 did not take.

**Outcome: watchdog shipped and it immediately earned its keep. The recovery was ABORTED — attempting
it crashed the n8n instance. Ledger delta is ZERO: nothing was recovered.**

---

## I must correct my own root-cause note from earlier today

**What I said:** "a PUT at 14:30:52Z left WF-2 deactivated and the activate step was never verified,"
and I named the class as *a deploy that ends at the PUT*.

**That was wrong.** The evidence:

| time | event |
|---|---|
| 2026-08-04T14:30:25–27Z | six WF-2 webhook executions (13391–13396) all **crashed** |
| 2026-08-04T14:30:52Z | WF-2 `updatedAt` — which I read as a deploy |
| 2026-08-05T07:00:06Z | WF-2S exec 13551: **`WorkflowCrashedError: Workflow did not finish, possible out-of-memory issue`**, `lastNodeExecuted = Replay Into WF-2` |
| 2026-08-05T07:00:12–13Z | four WF-2 webhook executions (13552–13555) all **crashed** |
| 2026-08-05T07:00:39Z | WF-2 `updatedAt` again, `active=False` again |

The same signature, twice, and the second time I watched it happen live. The `updatedAt` stamp I
treated as proof of a deploy is n8n writing `active=false` while recovering from the crash. There was
no deploy at 14:30 yesterday.

**The real class: an out-of-memory crash during a replay burst takes the instance down and leaves
WF-2 deactivated.** That matters because the fix I proposed — verify `active` after activating —
would only have *detected* it faster. It does not prevent recurrence, and I presented it as if it
addressed the cause.

The activate endpoint was never at fault: it returned 200 and `active=true` on the first re-read,
both times, with the webhook answering 200.

## What is live now

| | state |
|---|---|
| WF-2 | **active**, `WRITE_MODE=shadow`, webhook probe 200, version `e9242d0a` (unchanged) |
| WF-2S | **active**, version `719bde15`, `lookback_minutes=180`, `max_per_run=100` (both restored) |
| WF-1 | **active**, `5525eba3`, 110 nodes, 30 retained executions, **0 failures** |

### The watchdog (step 1) — shipped, and it caught the recurrence on its first live cycle

`WF-2 Mode Read` already GETs the whole workflow object, so `active` was in the response all along
and `WF-2 Mode Eval` simply never looked at it. That is why WF-2 could sit dead for 15 hours while
the watchdog reported `WRITE_MODE=shadow` quite happily: reading CONFIG works fine on an inactive
workflow. Code-only change in two nodes, no graph change:

- `WF-2 Mode Eval` → `__wf2_active`, `__wf2_inactive`, folded into the existing `__mode_overdue`
  alarm flag so no nodes were added to a live workflow.
- `Ops Warn Mode Overdue` → a dedicated first branch: *"🚨 WF-2 IS NOT ACTIVE — every SENT replay is
  being rejected with 404…"*

Proof from cycle 13571 (07:15Z): `mode='shadow' wf2_active=False inactive=True overdue=True`, and the
alarm branch was taken. Before this change that cycle would have reported healthy.

**WF-2H needed no patch** — its nodes are `Daily → CONFIG → SL Campaigns → Pick Active → SL Stats →
SL Stats Summary → PD Leads → Quality Digest → WF-2H Digest`. It never reads WF-2's state.

## The recovery cycle — aborted, and why

`lookback_minutes` 180 → 1200 (covering from ~10:50Z yesterday). `max_per_run` deliberately left at
100 for the first cycle to measure before raising it.

That first cycle **OOM-crashed the instance**. So the answer to "raise the batch cap or drain over
several cycles" is neither, as configured: **`max_per_run=100` is already past what this instance
survives** when the lookback is wide enough to fill the batch. Raising it would have made the outage
worse and longer.

I restored `lookback=180` immediately rather than continuing. With no sends in the last several hours,
batches are empty again and the crash loop is stopped.

**Ledger delta: zero.** `__marked` stayed 0 across every cycle, `__store_size` 0. Cycle 13571
replayed 100 and had 100 rejected. Nothing from yesterday's ~830 SENT events was recovered, and with
lookback back at 180 they are outside the window again.

Worth stating plainly: leaving the recovery running would have kept crashing an instance that also
hosts **WF-1, the live LinkedIn receiver**. WF-1 shows no failures, but the exposure was real.

## Open / blocked — the flip is still RED

| item | state |
|---|---|
| **The OOM itself is undiagnosed** | We know the trigger (a ~100-item replay burst) and the symptom. We do not know the memory ceiling, whether it is WF-2S building payloads or WF-2's 145-node executions, or whether the n8n Cloud plan's limit is adjustable. **This must be understood before the flip**: in live mode the same burst would crash mid-write |
| Recovering yesterday's ~830 SENT events | Not done. Needs a safe batch size, which needs the OOM ceiling. A slow drain (e.g. 20–25/cycle) would take 8–10 hours of cycles |
| `max_per_run=100` | Restored to its original value, but it is the trigger. Lowering it is a real change and I left it to you rather than deciding it |
| Flip | RED — unchanged gates (Melisa's go, bot invite to `C07LTD8UT70`, campaign-rename risk) **plus** this new one: an unbounded replay burst can crash the instance |

## What can be improved

- **`updatedAt` is not an audit trail.** I built a root-cause story on one timestamp because it fit,
  and it was the wrong story. The crashed-execution list was available the whole time and would have
  answered it correctly in one query. Ask what *else* changed at that timestamp before attributing it.
- **A watchdog that detects the symptom is not a fix for the cause.** I shipped the right check, but
  I framed it as closing the incident. It closes the *blindness*, not the outage.
- **Bounded bursts, not bounded caps.** `max_per_run` bounds items, not memory. The replay step should
  bound concurrent in-flight work (n8n batching with a delay) so batch size cannot translate directly
  into instance pressure.
- The recovery attempt should have started at a deliberately tiny cap (10–20) precisely because the
  failure mode was unknown. I chose 100 because it was the existing value, which is not a safety
  argument.

## Files

| file | what |
|---|---|
| `patch_wf2s_active_watchdog.py` | the watchdog patch + recovery config, verified deploy |
| `restore_and_reactivate.py` | restore lookback, reactivate WF-2, verify, WF-1 exposure check |
| `watch_recovery.py` | per-cycle recovery monitor (caught the crash) |
| `wf2_reactivate.py` | step 0, with the path-collision / trigger-sanity rule-outs |
| `wf2s_config_before_recovery.json` | the saved originals used for the restore |
