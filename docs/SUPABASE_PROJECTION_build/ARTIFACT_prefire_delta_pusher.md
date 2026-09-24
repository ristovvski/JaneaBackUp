# Phase 2 — delta pusher (claims-table queue) — §9f.2 pre-post artifact

Дата: 2026-09-14. Files built, logic-tested locally (36/36 across both new test files + 105/105
on the existing DNC contract suite), plus one live isolated mechanism check. **Nothing deployed,
nothing live yet.**

## Scope (per your instruction: minimal)

Only `DNC__UpsertLedger__v1` (the shared subworkflow) gets claim-enqueue logic added. Direct
writers that bypass it — `dnc_expiry_job`, `dnc_s4_retirement_removal`, `dnc_projections_sweep`,
`dnc_label_reversal` — are **not** touched. Their changes reach Supabase only via the nightly
reconcile (not yet built), so there's up to a 24h lag for removals/expiry/projection-state updates.
New-row creation and split-identity soft-remove (the two things UpsertLedger itself writes) get
near-real-time sync, typically within one `dnc_supabase_delta_pusher` cycle (10 min).

## What's built

**Enqueue side** (`DNC_OBS_P1_build/build_dnc.py`, regenerated `subworkflows/DNC__UpsertLedger__v1.json`,
14 → 16 nodes):
- `Upsert Ledger Row` → **`Enqueue Supabase Delta`** → `Has Tombstone?` (unchanged downstream).
- `Tombstone Split-Identity Row` → **`Enqueue Supabase Delta (Tombstone)`** (new dead-end leaf,
  same style as other terminal side-effect nodes in this file).
- Both enqueue nodes write to the shared claims table (`euyostwJYfJefItC`, family
  `supabase_delta_registry`), `onError: continueErrorOutput` — **a failed claim-enqueue can never
  block or fail the real DNC write it's chained after**, verified structurally (both output
  branches route to the same next node).
- This is a NEW use of that shared table's semantics: presence = pending push (not "already
  handled" like its other families) — deliberately not added to `dnc_claims_prune`'s retention
  allowlist, so a claim that fails to push stays visible for investigation rather than silently
  expiring.

**Consumer** (`SUPABASE_PROJECTION_build/build_supabase_sync.py`, new
`workflows/dnc_supabase_delta_pusher/dnc_supabase_delta_pusher.json`, 15 nodes): cron (10 min) +
manual webhook (`{{WEBHOOK_DNC_SUPABASE_DELTA_PUSHER}}`, same dual-trigger convention as `dnc_claims_prune`).
Per cycle: reads all pending claims → for each, re-fetches the row's CURRENT state from
`dnc_registry_dev` fresh (not the claim's stale snapshot) → upserts to Supabase → **deletes the
claim only on successful push** (a failed push leaves the claim for the next cycle). Logs one
`dnc_registry_meta` row (`source: 'delta_push:dnc_registry'`) only when it actually pushed
something (a cycle that found nothing pending logs nothing, avoiding meta-table bloat for a job
that runs every 10 minutes).

## Two real bugs caught before deploy (not in production this time)

1. **Item-count mismatch on the read side**: joining "every claim" against "every row actually
   found" can't rely on 1:1 pairedItem inference once some rows aren't found (0..N found vs. N
   claims). Fixed by making the join explicit (`Build Push Item`, keyed lookup by id), restoring
   exact N-claims-in/N-items-out — same root class as the 2026-09-09→09-14 gate latency incident,
   caught here at build time via local tests instead of live.
2. **`runOnceForEachItem` array-wrap bug**: three new per-item code nodes initially returned
   `[{ json: {...} }]` instead of the required bare `{ json: {...} }`. This is the EXACT same class
   of bug as the 2026-08-11 "PD Classify" incident (330-in/1-out) already documented in this
   codebase — caught this time via a live isolated probe (`probe_paired_item.py`, deployed +
   fired + deleted, no real table touched) before it ever reached a real workflow.

## Live-verified (isolated, no real data touched)

- `predefinedCredentialType` + `supabaseApi` auth: confirmed working (Phase 2 step 1).
- **New this step**: `$('AncestorNode').item.json.field` correctly resolves PER-ITEM even through
  a node that completely replaces `$json` (simulating the HTTP upsert call) — 3 synthetic items
  (A/B/C) recovered in the correct order through a throwaway 7-node probe workflow, deployed, fired
  once, deleted. This is the exact mechanism `Delete Claim`/`Mark Pushed`/`Mark Push Failed` depend
  on to know which claim they're finishing, after the HTTP call has overwritten `$json`.

## What's NOT yet verified live

- An actual claim flowing end-to-end through the real `DNC__UpsertLedger__v1` → real claims table
  → real `dnc_supabase_delta_pusher` → real Supabase write → real claim deletion. Everything
  upstream of "deploy" has been tested in isolation; the full real chain has not fired once.

## Fire plan, pending your word

1. Deploy `DNC__UpsertLedger__v1` via `safe_patch_workflow()` (expect: 2 nodes added, 0 removed, 0
   param changes on existing nodes besides the new connections) — **this is a live production
   subworkflow used by every S1-S4/event-population/meeting/label writer**, so I'd like explicit
   confirmation before this specific patch, separate from the delta-pusher deploy itself.
2. Deploy `dnc_supabase_delta_pusher` (brand new workflow, INACTIVE at first — cron not yet
   running).
3. Fire ONE real write through `DNC__UpsertLedger__v1` (a low-stakes test row, or wait for the
   next organic write) and confirm a claim appears in the claims table.
4. Manually fire `dnc_supabase_delta_pusher` via its webhook (not the cron yet) and confirm: the
   claim is gone, the row exists in Supabase with the right fields, and `dnc_registry_meta` got a
   `delta_push:dnc_registry` row.
5. Only then activate the cron trigger for real, steady-state operation.

Nothing above fires without your go-ahead.
