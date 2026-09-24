# The 5 deleted tests — what each covered, and why deletion (not a fix) was correct

Дата: 2026-09-09. Written per direct request to account for exactly what coverage was lost when
the queue-mode tests were removed from `dnc_contract_tests.js` during the same-day incident fix.

| # | Test name | What it covered |
|---|---|---|
| 1 | `dnc_pre_add_gate v3: sync/queue split — 20 rows sync, 300 rows queue, backlog forces queue` | The routing decision (`Decide Sync Or Queue`) that sent small batches synchronously and large/backlogged ones to `dnc_gate_queue`. That table never existed and the decision logic itself no longer exists post-removal. |
| 2 | `dnc_pre_add_gate v3: fail-open survives a NON-uniform dataTable error shape` | Guarded `Decide Sync Or Queue`'s queue-depth check against a specific non-uniform n8n error shape (a passthrough echo instead of `{error:...}`) so a broken queue-depth read wouldn't wrongly force every call to queue. The node it tested no longer exists. |
| 3 | `dnc_pre_add_gate v3: retrieval — done/pending split, single-row convenience fields` | `Build Retrieve Report`'s logic for splitting a retrieve request's rows into done/pending buckets by querying `dnc_gate_queue`. The whole retrieve-by-queue mechanism is gone, replaced by the honest 410 (`Retrieve Removed`). |
| 4 | `dnc_pre_add_gate v3: queue response reports an eta, retrieval note included` | `Build Queue Response`'s ETA-estimate math (backlog size ÷ drain batch size × interval) for the 202-queued response. There is no queued response anymore — every call answers synchronously or 413s. |
| 5 | `dnc_pre_add_gate v3: ingress logging exists before any lookup, row_key stripped from response` | Two things bundled in one test: (a) `Log Ingress` writing a `status='received'` row to `dnc_gate_queue` before any lookup, for crash-loss-set enumerability — gone with the queue table; (b) `row_key` stripped from the response — **this half is still true and was NOT lost**, it's now covered by a new, narrower test (`row_key stripped from response, single-row convenience fields`). |

**None of these were "fixed" — all were deleted** because the mechanisms they tested (the queue,
the drainer, retrieve-by-queue, ETA estimation, pre-lookup ingress logging) were the exact things
Nik removed on 2026-09-02, for the reason recorded in `Retrieve Removed`'s own comment: the queue
never drained a single row in its entire existence, so every "queued" answer was a promise that
could never be kept. Keeping tests for dead functionality would just re-certify the bug the next
time someone "fixed" a false test failure by re-wiring the queue back in — which is close to
literally what happened this same day.

**Replaced with 2 tests** covering what's still true post-removal: `row_key` stripped from the
response (still real), and the retrieve path returning an honest 410 instead of a fake queue
lookup (new behavior, now covered).

## abort-on-mismatch — now mandatory, not a one-off

`patch_utils.py` (was `zz_patch_utils.py` — renamed off the throwaway-script naming convention
since this is now permanent, required infrastructure) provides `safe_patch_workflow()`: every
future live patch to the gate OR the drainer (or anything else) must go through it. It:
- Computes the live/local node-name diff in BOTH directions (added and removed).
- Hard-aborts (raises, no "proceed anyway" path) unless the diff exactly equals what the caller
  explicitly expected going in.
- Verifies the post-patch live state matches the intended local state name-for-name before
  returning.

This directly closes the gap that caused the incident: the old ad-hoc patch scripts only checked
for unexpected ADDITIONS, never unexpected removals or a live workflow that had drifted since the
generator last ran. Any patch script written from here on imports this and calls it — hand-rolled
diff logic for a live production workflow is no longer acceptable practice on this project.
