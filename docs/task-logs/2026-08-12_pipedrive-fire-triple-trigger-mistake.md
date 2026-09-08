# DNC BUILD — Pipedrive FIRE: triple-trigger mistake, root cause, and current state

**Status: 3 real concurrent executions confirmed running. My mistake caused the 3rd. No data
corruption expected (writes are idempotent). Auditor's window assumptions need one correction.**

## What actually happened (corrected diagnosis)
My original "the webhook trigger is dead" read was wrong. Diagnostic proof, run just now:
- A deliberately wrong path (`{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}-DEFINITELY-NOT-REGISTERED`) returns a clean
  404 with a clear "not registered" message in **0.4s**.
- The real path (`{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}`) holds the connection open with **no response for 12s+**
  (connect succeeds instantly; it's the read that times out). That is the correct signature of "the
  workflow received it and is running" for a `responseMode: "responseNode"` webhook that can't
  respond until a `Respond to Webhook` node is reached — which, on the live-write branch, is a long
  way off.

So every POST I made to the real path was a real trigger. Confirmed via `GET
/api/v1/executions?workflowId=...&status=running`: **three genuinely concurrent executions**,
all started after the `FIRE_PIPEDRIVE` flip (versionId `a40368ce`):

| Execution | Started (UTC) | Source |
|---|---|---|
| 15943 | 15:20:25 | my original post-flip fire |
| 15944 | 15:28:10 | my "re-fire" after being told no execution had appeared |
| 15951 | 15:48:58 | my own diagnostic POST to the real path, meant only to inspect response timing |

**Root cause of my error**: I mistook "no execution visible yet" (correctly explained by this
instance's established behavior — in-progress executions are invisible until they finish) for "the
trigger never fired," then re-fired instead of just waiting longer. Then, while diagnosing, I POSTed
to the real production path a third time instead of testing only against a bogus path — that call
should have been the control-only test from the start.

## Why this probably doesn't corrupt anything
All three executions run the identical logic against the identical `pending` rows:
- Pipedrive person field write: sets `DNC Status` to the same option id (`686`) — idempotent,
  re-setting the same value is a no-op in effect.
- Lead-label write: union-append of the same label id
  (`52a7c290-fc73-11f0-ad98-81d4703453f3`) — union means duplicate adds don't create duplicate
  labels.
- `projections_state` write: all three set `pipedrive: done` — last write wins, same value either
  way.

So the **end state** should be correct regardless of execution count. The real cost is **3x the API
call volume** during this window, not 3x the risk of a wrong final value.

## What I checked and did NOT do
- **Did not attempt to cancel any of the three.** n8n's public API (this version) exposes no
  stop/cancel endpoint for a running execution — the only uncertain option was `DELETE
  /api/v1/executions/{id}`, whose behavior against a *running* (not finished) execution is
  undocumented and could plausibly abort mid-write, leaving a genuinely inconsistent partial state
  (worse than 3x redundant idempotent writes). Chose not to gamble on an unverified destructive
  operation.
- **Did not fire again.** No further POSTs to the real path since discovering this.
- **Checked Pipedrive's daily rate-limit budget** as a real risk check, not a guess:
  `x-daily-ratelimit-token-remaining: 1,666,626 / 1,890,000` (~88% headroom) at the time of
  checking — tripled call volume for this sweep's scale is very unlikely to exhaust the day's
  budget. The per-2-second window limit (`x-ratelimit-limit: 80`) is the more relevant risk under
  3x concurrent load and could produce transient 429s, which is the one failure mode from the first
  real fire this project already hit and fixed via throttling+batching — each execution still
  respects its own configured interval, so this is a "maybe some retries," not "guaranteed repeat of
  the original storm."

## Correction for the auditor's window
The auditor's post-run reconciliation for this window should expect **3 execution IDs** (15943,
15944, 15951) behind the one logical Pipedrive write, not 1 — API call-volume in any digest will
read ~3x the single-run estimate. The **final row counts and field values** should still match the
single-run expectation, since all three writes are idempotent and converge on the same end state.

## Next
Watching all three (background poll) until every one reaches a terminal status. Once all three are
done: pull `Combine Summaries` run data from whichever is most complete (or all three, to confirm
convergence), do the read-back sample of real Pipedrive writes, and report final counts. No more
fires. `FIRE_SMARTLEAD` untouched throughout (still `false`).
