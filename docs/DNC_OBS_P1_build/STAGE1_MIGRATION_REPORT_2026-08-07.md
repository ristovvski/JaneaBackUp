# STAGE 1 migration report — dnc_ledger → dnc_registry_dev

Additive migration of the existing, tested Phase-1 build (`DNC_OBS_P1_build/`) to serve today's
DNC BUILD task. Every Phase-1 column, workflow, and behavior is unchanged; new capability is
layered on top. **74/74 static tests pass** (63 original + 11 new), 2 deferred (R2/R3, unchanged,
pre-existing — no message-history endpoint on Smartlead).

## What changed

1. **Table renamed**: `dnc_ledger` → `dnc_registry_dev` (file: `datatables/dnc_registry_dev.schema.yaml`,
   was `dnc_ledger.schema.yaml`). All `dt_get`/`dt_upsert`/`dt_get_all`/`dt_update` helpers in
   `build_dnc.py` default to the new name; every generated workflow JSON now points at it.
2. **New columns** (all nullable/optional — old rows and old writers are unaffected):
   `reason`, `source_ref`, `also_flagged`, `date_precision`, `offboard_removable`,
   `expiry_review_pending`, `projections_state`.
3. **New library module** `subworkflows/lib/reason_v1.js` — reason-priority hierarchy, the
   reason→entry_type backward-compat mapping, collision merge (`reasonMergeV1`, preserves the
   losing signal in `also_flagged` rather than discarding it), and the reply_dnc/unknown-precision
   expiry override. Coexists with `merge_v1.js`; nothing in `merge_v1.js` was edited.
4. **`DNC__UpsertLedger__v1` extended**: if the caller passes `reason` (new intake path), `entry_type`
   is derived from it *before* `merge_v1`'s strength-based merge runs, so the existing
   never-downgrade guarantee holds for reason-driven writes too. If `reason` is absent (the existing
   `heyreach_reply_to_dnc_ledger` tee), behavior is byte-for-byte what it was before this migration.
5. **`dnc_expiry_job` extended**: a `expiry_review_pending` guard skips due-for-expiry rows that a
   human has deliberately frozen, and reports the skipped count in both the weekly digest and the
   dev-verbose summary. Rows without the flag (i.e. every row that existed before this migration)
   behave exactly as before.
6. **Alias table** created (`fixtures/source_ref_alias_table.json`) — Jim=Jim Ash, Mario=Mario
   Stalder, both `status: confirmed` per Nik's 2026-08-06 handoff. Applied at query time only
   (offboard resolution); never rewrites `source_ref` on existing rows.
7. **Pending manual seed row** tracked (`fixtures/pending_manual_seed_rows.json`) —
   pii-f59eb465@example.invalid, `reason=reply_dnc`/`entry_type=negative_reply`, from the London
   backfill handoff. Not written; queued for whenever seed WRITE is authorized.

## Spec deltas vs. today's original STAGE 1a wording

- **Table name**: original task said `dnc_registry_dev`; existing tested build used `dnc_ledger`.
  Resolved by owner decision (2026-08-07): extend+rename the existing build, not build fresh.
- **`reason` enum**: original wording listed `manual_sheet / reply_dnc / unsubscribe / offboard`.
  The actual People-DNC seed derivation (dry-run against real data) produced two more values not
  in that list — `client` and `manual_offboard_eligible` — because the real CSV data needed them
  (a 95-row "Client List" bucket, and a 23k-row salesperson-owned-connections bucket). Both are now
  first-class `reason` values with their own entry in `reason_to_entry_type_mapping`.
- **`entry_type` field**: original wording didn't mention it. It already existed in the tested
  Phase-1 schema as the *merge-strength* field. Rather than replace it with `reason` (which would
  have required rewriting `merge_v1.js` and every dependent test), `reason` was added *alongside*
  it, with `entry_type` derived from `reason` at write time. This is why the 63 original tests
  needed zero changes.
- **`reply_dnc` → `entry_type` mapping**: first drafted as `replied`, corrected to `negative_reply`
  after the paul.gilford handoff row explicitly specified `negative_reply` — reasoned through:
  `reply_dnc` is DNC-context by construction (a reply that didn't warrant suppression wouldn't be
  classified `reply_dnc` in the first place), so it should never map to the neutral `replied` tier.
- **`expiry_review_pending` default behavior**: initially assumed (by me, before the handoff) that
  a past-dated `expires_at` at seed time should *automatically* set this flag. Corrected per Nik's
  2026-08-06 decision: it's a **manual, deliberate** flag a human sets per-batch, default `false`.
  The Amsterdam-142 batch is the proof case — frozen, then explicitly unfrozen; they will seed with
  `expiry_review_pending=false` and expire normally once seed WRITE is authorized.
- **`projections_state` (pipedrive/smartlead/heyreach)**: column exists in the schema; no workflow
  reads or writes it yet. Populating it is Stage 2 (WF-4 Sheet intake) scope, not this migration —
  flagging explicitly so it isn't assumed to be live.

## Explicitly NOT done in this pass (by design, out of today's ask)

- WF-4 Sheet intake workflow itself (Stage 2).
- Any projections_state read/write logic (Pipedrive label / Smartlead block / HeyReach exclusion).
- Seed WRITE of any kind — the 23,838-row People-DNC batch, the paul.gilford row, and the
  Pipedrive/Smartlead-sourced portions of the unified seed are all still dry-run/pending.
- Renaming `heyreach_reply_to_dnc_ledger`'s workflow/file name — only the *table it points at*
  changed; the descriptive filename was left alone to limit blast radius (used elsewhere in
  evidence/task docs).

## Gate status (unchanged)

Seed WRITE still waits on: this migration (done) + the overnight Pipedrive resolution report
(pending — gated on flip stability, see `dnc-pipedrive-pull-gate` scheduled task) + your word, in
that order. Nothing in this pass touched Pipedrive, Smartlead, HeyReach, or n8n production.
