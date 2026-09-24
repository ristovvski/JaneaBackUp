# Pre-fire artifact — P1 FIX: remove dnc_projections_sweep's label-write branch

Item 4 (first half) of Nik's 2026-09-16 P1 instructions: "FIX: remove the label branch from the
sweep entirely (field write only), regression static: sweep never touches label_ids."
Incident: task-logs/2026-09-16_P1_dnc_projections_sweep-label-incident.md.

## What's changing

Structural patch to live `dnc_projections_sweep` (id `8qVXtI2ez5o6a9hc`). Removes the entire
lead-label write path built before the field-only ruling existed:

- **Removed (9 nodes)**: `PD Get Leads By Person`, `PD Classify`, `PD Has Open Lead?`,
  `PD Get Lead For Labels`, `PD Label Union`, `PD Patch Lead Labels`, `PD Mark Done (with lead)`,
  `PD Merge Write Errors`, `PD Mark Done (no lead)` (renamed, see below).
- **Added (1 node)**: `PD Mark Done` — the rename target for `PD Mark Done (no lead)`, now the
  only Mark Done node since there's no more with-lead/no-lead fork (the field write never needed
  the lead at all).
- **Changed (3 nodes)**: `CONFIG` (the `pd_label_dnc` field, holding the DO NOT CONTACT label id,
  is gone entirely), `PD Aggregate` (rewritten — one flat `rows` list, no more
  `with_open_lead`/`without_open_lead` split), `Combine Summaries` (Slack text + JSON note field
  now say "field write only", no more open-lead counts).

After this patch the workflow's only Pipedrive write is `PD Write DNC Field` — a PATCH to
`/api/v2/persons/{id}` setting the DNC Status custom field. No node anywhere calls
`/v1/leads`, references `label_ids`, or references the DO NOT CONTACT label id
(`52a7c290-fc73-11f0-ad98-81d4703453f3`).

## Risk

None from this patch itself. `FIRE_PIPEDRIVE` has been `false` live since the STOP action (first
thing done this incident) and stays untouched by this patch (structural node/connection swap only,
`safe_patch_workflow` doesn't touch CONFIG's FIRE_PIPEDRIVE value — verified below it's still
`False` pre- and post-patch). This does not require "Nik's word" the way the REPAIR phase does —
it's a pure bug removal, not a data-affecting write.

## Verification done before this deploy

- 110/110 contract tests pass, including a new explicit regression-static test ("P1 2026-09-16:
  dnc_projections_sweep NEVER touches Pipedrive lead labels, field write only") asserting: no
  `label_ids` anywhere in the workflow JSON, no reference to the DNC label id, no node name
  suggesting a reintroduced lead/label touch, and every Pipedrive HTTP call targets only
  `/api/v2/persons/`.
- Both WF_LINTER rules clean against the rebuilt local workflow: `prev_read_matches_direct_ancestor`
  (0 stale reads, 0 ambiguous) and `node_reference_resolves` (0 unresolved, 0 dynamic).
- Live diff (`zz_patch_projections_sweep_p1_fix.py`, dry run) matches this artifact's stated
  add/remove/change sets exactly — no unexpected drift since local was last generated.

## Plan

1. `python zz_patch_projections_sweep_p1_fix.py --apply` — `safe_patch_workflow` aborts if the live
   diff no longer matches the expected sets above (it re-checks at apply time, not just dry-run
   time).
2. Script re-verifies post-patch: `FIRE_PIPEDRIVE` still `False`, no `label_ids` string and no DNC
   label id string anywhere in the live workflow JSON.
3. Report back to Nik with the result before starting any REPAIR work — REPAIR stays explicitly
   gated behind his word regardless of this deploy's outcome.
