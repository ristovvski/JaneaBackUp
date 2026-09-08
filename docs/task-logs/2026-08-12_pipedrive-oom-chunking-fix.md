# DNC BUILD — Pipedrive sweep OOM incident: root cause, chunking fix, resumed fire

**Status: fix built, tested (56/56), deployed, reactivated. Chunk 1 (execution 15958) fired and
in progress under the new chunked design. No further concurrent fires.**

## Root cause (confirmed via includeData=true on all three crashed executions)
All three (15943, 15944, 15951) returned identical `WorkflowCrashedError: "Workflow did not finish,
possible out-of-memory issue"`. Confirmed instance-wide health was NOT affected — every other
workflow (WF-2R, the core error handler, other pollers) kept succeeding straight through the crash
window; this was isolated to my own triple-concurrent fire of this one workflow, each holding the
full ~2,264-row pending population (read phase via `PD Get Leads By Person`, and for two of the
three, the write phase too) in memory at once. Node progression at crash time showed graduated depth
(15951 died before any write node; 15944 reached the field write; 15943 reached the label-union
write), consistent with genuine memory pressure rather than a logic bug.

## Idempotency, confirmed against the live deployed node bodies (not memory)
- `PD Write DNC Field`: `PATCH .../persons/{id}` body sets `custom_fields[pd_field_key] =
  pd_active_option` — an absolute SET, not an increment/append. Re-running with the same value is a
  no-op in effect.
- `PD Label Union`: reads existing `label_ids`, only pushes the DNC label if not already present.
  Re-running when already unioned is a no-op.
- `PD Filter Pending`: excludes any row whose `projections_state.pipedrive` is already `done`. This
  is itself the natural, durable, externally-visible resumability mechanism — no separate cursor
  artifact needed; a row's own state in `dnc_registry_dev` IS the cursor.

Conclusion: whatever partial state the three crashed executions left behind, re-running the sweep
is safe and will not double-write or diverge — it will simply skip whatever already succeeded.

## Fix: chunking, built into the generator (not a live-only patch)
Added `PD Limit Chunk` (`build_dnc.py`) directly after `PD Filter Pending`, before the first heavy
per-item HTTP call (`PD Get Leads By Person` — which runs even in dry-run mode, before any FIRE
flag is checked). It slices the pending set down to `pd_chunk_size` (new CONFIG key, default `250`,
within the owner-directed 200-300 range) and carries `total_pending_before_chunk` /
`chunk_size` through to `PD Classify` → `PD Aggregate`, so the dev Slack summary now reports
`chunk_processed` and `remaining_after_chunk` per fire instead of implying the whole population
was covered in one shot.

This bounds **every** execution (read phase and write phase alike) to at most `pd_chunk_size` rows,
regardless of how many concurrent fires happen to land — reducing blast radius even if a concurrency
mistake like today's recurs, on top of directly fixing the OOM's root trigger (the monolithic
~2,264-item single execution).

`PD Classify`'s per-item upstream reference was updated from `$('PD Filter Pending').item.json` to
`$('PD Limit Chunk').item.json` — required for correct `pairedItem` resolution now that a node sits
between them; a stale reference would have silently broken per-item lookups.

## Verification before touching the live instance
- Regenerated all 9 workflows via `build_dnc.py` — `dnc_projections_sweep` went 35→36 nodes as
  expected (the one new node).
- Ran the full contract suite: **56/56 passed** (54 pre-existing + 2 new regression tests covering
  the chunk node's config-driven size, the rewired connections, the `PD Classify` upstream-reference
  fix, and the aggregate's new `chunk_processed`/`remaining_after_chunk` fields).

## Deployment sequence (same discipline as the original fire)
1. PUT the regenerated workflow to the live instance (`8qVXtI2ez5o6a9hc`) with `FIRE_PIPEDRIVE`
   re-applied to `true` as a live patch on top of the generator's safe `false` default (never baked
   into the generator itself) — `FIRE_SMARTLEAD` asserted still `false` before the PUT.
   New versionId: `70cb947e-83c5-4e19-a3df-eb4a2fb27da6`.
2. Reactivated the workflow (crash had left it `active: false`).
3. Confirmed zero running executions before firing (`status=running` query, empty).
4. Fired once. Client got a Cloudflare `524` (proxy-level timeout, not a workflow failure) after
   ~125s — did **not** re-fire on that signal this time; instead looked up the actual execution by
   ID (`15958`, started 16:09:28 UTC) and confirmed exactly one execution exists, no duplicates.
5. Polling execution `15958` specifically (not the general "any new execution" list) until it
   reaches a terminal status, before firing chunk 2.

## Next
Once 15958 finishes clean: check `remaining_after_chunk` from its `Combine Summaries` output, and if
>0, fire the next chunk — one at a time, confirmed-complete before the next, until
`remaining_after_chunk` reaches 0. No concurrent fires. Per Nik's window rule: one full reconciliation
report to the auditor after the ENTIRE population is done, not per chunk. `FIRE_SMARTLEAD` untouched
throughout.
