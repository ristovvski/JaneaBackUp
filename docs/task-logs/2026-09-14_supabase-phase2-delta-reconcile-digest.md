# Supabase Phase 2 — delta pusher, nightly reconcile, digest line

Дата: 2026-09-14. All three pieces built, tested, deployed live, and fixed after two real bugs
caught in live testing (not in production use — everything below was caught before real organic
traffic exercised the broken paths, except the delta pusher which briefly had the bug live for a
short window with zero real claims processed through it in that state).

## Delta pusher (`dnc_supabase_delta_pusher`, live, id `xpmOzZn1oKOVoiTD`)

- Enqueue side: `DNC__UpsertLedger__v1` patched live (14→16 nodes) to write a claim to the shared
  claims table (`euyostwJYfJefItC`, family `supabase_delta_registry`) after every real write,
  fire-and-forget (`continueErrorOutput` — a failed claim-enqueue can never block the real DNC
  write). Along the way, found and fixed a real, PRE-EXISTING, unrelated drift: the live `Decide`
  node already had Melisa/Nik's 2026-08-26/08-31 "expiry is dead" ruling applied directly in
  production, but the generator (`merge_v1.js`) and 4 tests still had the old TTL logic — synced
  the generator to match live, fixed the 4 stale tests.
- Consumer: cron (5 min, tightened from an initial 10 min to structurally guarantee the "≤6 min"
  SLA) + manual webhook. Drains claims, re-fetches the row's CURRENT state, upserts, deletes the
  claim only on success.
- **Bug #1 found live**: `Build Report` was fed by THREE converging branches (skipped-not-found /
  pushed / push-failed) as three direct wires. A single-claim test looked correct; a deliberately
  MIXED 2-claim batch (one found, one not) proved `Build Report` fired TWICE, each seeing only its
  own partial slice (`claims_seen:1` instead of `2`). Fixed using this project's own proven
  precedent (`dnc_projections_sweep`'s "PD Merge Write Paths"): a `Merge("append", numberInputs:3)`
  node with each branch on its OWN dedicated input index, collapsing to one real aggregation.
  Confirmed fixed live with the same mixed-batch test (`claims_seen:2, pushed:1,
  skipped_missing_row:1`, single firing).
- Resilience static (Nik's ask): broken-URL DEV copy → push fails → claim survives
  (`pushed:0, failed:1`) → real pusher fired → claim deleted, row upserted, meta row logged
  (`pushed:1, failed:0`). Confirmed end-to-end.

## Nightly reconcile (`dnc_supabase_nightly_reconcile`, new, live, id `GgZCHdTt1Mr4sT9Y`)

- Cron `20 6 * * *` + manual webhook. Per table: read n8n's full table once (safe, done many times
  this session), paginate Supabase at 1,000/page (PostgREST's own cap forces this), field-by-field
  diff (timestamp-format-aware), heal drift by upserting FROM n8n only (never deletes Supabase
  extras), one meta row per table, one Slack line to **#alerts (`C0BTUHSSM3K`, confirmed by Nik —
  distinct from ops/#niks-channel)** only if total drift ≠ 0.
- **Bug #2 found live**: `Report <table>` was only reachable through `Upsert Corrections`, which
  never runs at all when there's zero drift (0 chunks = a per-item node simply doesn't execute).
  The very first manual run (clean tables, 0 drift both sides — exactly the expected, common case)
  silently never reached `Combine Reports`/the alert check/meta-logging at all. Fixed by wiring
  `Report` directly off `Diff` (which always runs exactly once).
- **Bug #3 found live, same root cause as bug #1 but on the READ side**: `Diff <table>` was fed by
  BOTH `Get N8N <table>` (always executes) AND `Fetch Page <table>` (the real Supabase data) as two
  direct wires — fired twice per table, one firing misreading n8n's own rows as Supabase rows.
  Cascaded into `Combine Reports` firing 4× (2×2) and quadruple-inserting meta rows. Fixed by
  restructuring to a strictly linear, single-incoming-wire chain per table (a new
  "Swallow N8N Read" node keeps `Get N8N` a true ancestor for the diff's named-ref read without its
  bulk output ever becoming a second live input), and sequencing the two tables one after another
  instead of running them in parallel (so `Combine Reports` has exactly one direct predecessor).
- Confirmed fixed live: `Diff`/`Combine Reports`/etc. all ran exactly once, correct combined result
  (`total_drift: 0`, matching the initial load's already-verified-clean state), exactly 2 new meta
  rows landed.

## Digest line (patch to live `dnc_morning_digest`, 40→43 nodes)

Folded into the existing `*DNC*` line (not a new bullet — the digest is capped at 12 lines):
`Supabase mirror: N rows · age N min · reachable`. Red if unreachable/paused (new) or gate FAILING
(existing, preserved); amber if reachable but >60 min stale (new) or `dnc_active` unreadable
(existing, preserved). Two new read-only checks, both `continueErrorOutput`. Patched using the
project's own established pattern for this exact workflow
(`I04_SIMPLIFY_2026-09-03/patch_morning_digest.py`'s discipline: fetch live, backup, defensive
already-patched-or-original assertion, integrity checks, dry-run-first). Applied live; next
scheduled digest post will carry the real numbers.

## New generalized lesson (memory)

Both bug #1 and bug #3 are the SAME underlying n8n behavior: any node fed by more than one
DISTINCT upstream source (or even one IF node's own two branches, when the batch is genuinely
mixed) fires once PER ARRIVING BRANCH, not once after merging — this generalizes the project's
existing "Merge append not a barrier" finding beyond literal Merge nodes. The actual fix (also
newly confirmed) is a `Merge("append")` node with each branch on its OWN dedicated input index —
not avoiding Merge, just never letting two sources share one input index. Saved to memory:
`n8n-multi-input-node-fires-per-branch.md`, with a correction appended to the older
`n8n-merge-append-not-barrier.md`.

## Still outstanding

Watching for 3 organic `DNC__UpsertLedger__v1` writes to confirm the enqueue→push cycle end-to-end
under real traffic (not just synthetic test claims) — none landed yet as of this write-up, will
report separately when confirmed. Tomorrow's 04:00Z digest post should carry a real Supabase mirror
row count, not `n/a` — worth a manual check once it fires.
