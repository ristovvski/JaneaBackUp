# Get Registry Match (Batch) latency incident — root cause + fix

Дата: 2026-09-14. Incident began 2026-09-09T13:46:06Z (my own mistake), fixed and verified live today.

## What actually happened (correcting my earlier 2026-09-09 assessment)

On 2026-09-09 I noted `Get Registry Match (Batch)` had slowed to 28.5s right after the domains
import and called it "very likely transient I/O contention... flagged for Nik to re-check later
today." **That was wrong.** It was a sustained, severe outage: the monitor logged
**459 consecutive failures** (30s timeout ceiling) from 2026-09-09T13:46:06Z until the fix went in
today — roughly 5 days, not a same-day blip.

## Root cause

When I wired the company-domain-block feature on 2026-09-09, I chained `Get Domain Blocklist`
(a `dataTable get`, `returnAll:true`, 1,373 domain rows) directly into `Get Registry Match
(Batch)`'s input, specifically to make it a true *ancestor* of `Classify Batch` (closing a
different, real bug: a parallel-sibling execution-order gap — see
`n8n-named-reference-needs-ancestor-not-sibling`).

That fix introduced a new bug: n8n's `dataTable` "get" operation runs **once per input item**
(same as an HTTP Request node), not once total. Feeding `Get Domain Blocklist`'s 1,373-item output
directly into `Get Registry Match (Batch)` made *that* node re-invoke 1,373 times per gate call —
once per domain row — instead of once per submitted person. 1,373 × ~20ms ≈ 27.5s, matching the
observed 28-78s almost exactly.

Confirmed via: monitor execution data (459 consecutive `timeout of 30000ms exceeded` since
2026-09-09T13:46:06Z); a live gate call timing 31.6s today before the fix; an isolated replica of
the same lookup query running in 0.79s (query itself is fast); per-node execution timing on a live
run showing `Get Registry Match (Batch)` at 28,231ms vs. 35ms for `Get Domain Blocklist` itself;
and item-count inspection confirming 1,373 input items into that node.

## Fix

Reordered both the live gate and the (archived, inactive) drainer generator so
`Get Domain Blocklist` always fires **exactly once** per call, and its bulk output never becomes
another per-item node's input:

- **Gate** (`dnc_pre_add_gate`, live): `Mark Start` (always 1 item) → `Get Domain Blocklist` →
  `Build Items` (ignores its own input — reads `$('Webhook')` by name) → `Cap Check` → ... →
  `Normalize Batch` → `Get Registry Match (Batch)` (restored as a direct wire, correct 1-per-row
  cardinality) → `Classify Batch`. `Get Domain Blocklist` is still a true ancestor of `Classify
  Batch` (closing the original 2026-09-09 gap), just routed through a node that doesn't amplify.
- **Drainer** (`dnc_gate_queue_drainer`, archived/inactive, fixed for consistency only, NOT
  live-patched): `Drain Timer` → `Get Domain Blocklist` → new `Reset After Domains` node
  (`runOnceForAllItems`, ignores its own input, always emits exactly 1 item) → `Fetch Pending
  Batch` → `Normalize Batch` → `Get Registry Match (Batch)` → `Classify Batch`.

Regenerated via `build_dnc.py` (gate stays 15 nodes, drainer 7→8). Rewrote the one test assertion
that had baked in the buggy wiring (`dnc_pre_add_gate v3: company-domain block...`, point 8) plus
the gate wiring-order test; added an explicit regression check that `Normalize Batch` feeds
`Get Registry Match (Batch)` directly, never `Get Domain Blocklist`. Full suite: **105/105 pass.**

Deployed live to the gate via `safe_patch_workflow()` — zero unexpected node adds/removes/changes,
only the connection graph moved. The archived drainer copy (`ARCHIVE__dnc_gate_queue_drainer`,
inactive, renamed off the queue-mode removal on 2026-09-02) was deliberately left untouched per
the "never delete incident workflow" preserve-don't-touch convention; the local generator/JSON is
already correct if it's ever resurrected.

## Live verification

- 3 consecutive gate calls post-deploy: `duration_ms` 133 / 161 / 123 (server-side), full round
  trip 0.4-1.9s — baseline restored, down from 28-78s. Classification still correct
  (`pii-2faf1b29@example.invalid` → `BLOCKED, reason: company_dnc / 100programmers.com`).
- Monitor's first post-fix tick (08:30:36Z): `healthy: true`, `duration_ms: 175`,
  `consecutive_failures: 0`, `alert_recovered: true`.
- Confirmed both Slack alerts actually fired (this was previously unchecked): `Alert: Gate
  Unhealthy` fired at incident onset (execution 50335, 2026-09-09T13:45:36Z); `Alert: Gate
  Recovered` fired automatically just now to #niks-channel ("RECOVERED -- 2-row probe clean
  again (was failing since 2026-09-09T13:46:06.167Z). 2 failure(s) today out of 3 checks.").

## Auto-deactivation risk (Nik's flagged concern)

Not investigated in depth — n8n's public API doesn't expose a documented auto-deactivation-after-
N-failures policy, and I found no evidence the gate was ever auto-deactivated (it stayed `active:
true` throughout the 459-failure run, confirmed both before and after this patch). Treating this
as resolved by the fix itself (failures have stopped) rather than as a separate risk to chase
further, but flagging that I did not find an authoritative answer on whether/when n8n would auto-
deactivate a webhook workflow.

## Responsibility

Both the original wiring bug (2026-09-09) and the wrong "transient, recovering" call made the same
day are mine. The second mistake is the more concerning one operationally: it closed the loop on a
real, sustained outage as if it were self-resolving, and the monitor's own alert (which did fire
correctly) went unactioned for 5 days as a result of that mis-read, not a monitoring gap.

## Improvable

- No automated check cross-references "monitor says unhealthy" against "human said it's fine" —
  this incident shows that gap costs days, not hours, when a call like that is wrong.
