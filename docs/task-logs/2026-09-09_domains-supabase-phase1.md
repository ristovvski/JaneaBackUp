# Company DNC domains — Supabase Phase 1 addition + n8n side

Дата: 2026-09-09.

## Done
- CSV ingested (`Company-DNC-Copy-of-Default-view-export-1788946008479.csv`): 1,386 raw rows → 1,373
  distinct domains after lowercase/strip-www/dedupe (13 same-day duplicate entries, earliest
  Created At kept). **Matches expected 1,373 exactly.** 0 blank, 0 free-mail hits, 0 www-prefixed
  rows in the source itself.
- `dnc_domains` added to `SUPABASE_PROJECTION_build/dnc_registry_phase1.sql`: separate table (not a
  registry entry class — see recommendation below), same RLS contract (read-only for anon/
  authenticated, no write policy at all).
- **Recommendation, written up in `DNC_DOMAINS_build/CREATE_DNC_DOMAINS_TABLE.md`**: separate n8n
  Data Table, not a domain-entry class inside `dnc_registry_dev` — semantic mismatch (whole-company
  scope vs. person lifecycle), collision risk with identity_key structurally eliminated (not just
  unlikely) by using a separate namespace, different lookup shape, and symmetry with the Supabase
  side.
- Free-mail rejection list built into the import prep (`DNC_DOMAINS_build/prep_domains_import.py`)
  — 0 hits in this batch, but a standing safeguard for future re-imports.
- Import driver (`dnc_domains_import`, dry_run-default) written, ready to deploy the moment the
  table exists.
- Gate learns domains: see `task-logs/2026-09-09_gate-domain-block-and-incident.md` for the full
  story (deployed live, fail-open, a real incident found and fixed along the way).
- README updated for Stefan: two lookups (person by identity_key, company by domain), both
  active-only, `dnc_domains` status noted as blocked on table creation.

## Дополнение: FIRED, 2026-09-09 (table created, id corrected, imported, verified)

- Table created by Nik. First id given (`CUkoLQxUxRuS1Lod`) genuinely didn't resolve (confirmed
  live in total isolation) — corrected id (`ai4ZiOGqzuJHRYLB`) confirmed live before any write.
- Found + fixed 2 real bugs before/during the fire: (1) an empty-but-working `dnc_domains` table
  produced 0 items with no error, which silently killed the whole gate chain since
  `Get Domain Blocklist` is now a true ancestor of `Get Registry Match` — fixed with
  `alwaysOutputData: true`, regression test added; (2) `patch_utils.py` itself only diffed
  `parameters`, missing that `alwaysOutputData`/`onError` are top-level node fields — fixed to
  compare the whole node.
- Dry-run (1,373, 0 rejected) → live fire (1,373 processed, chunked 500) → independent post-verify
  (table read back: 1,373 total, 1,373 active, 5 spot-checked domains match exactly).
- Live gate test against a real banned domain (`100programmers.com`) confirms correct
  `BLOCKED, reason: company_dnc / <domain>` classification.
- **Noted anomaly (not caused by this work)**: `Get Registry Match (Batch)` — a pre-existing,
  unrelated person-registry lookup node — showed a sharp, clearly-recovering slowdown right after
  the 1,373-row import (78s → 48s → 34s → 32s → 28.5s across consecutive calls). The domain-block
  code itself stayed fast (32-85ms) throughout. Very likely transient I/O contention on n8n's
  shared data-table storage after a large write burst, not a regression in anything touched here —
  flagged for Nik to re-check later today.

## Improvable
- Confirm `Get Registry Match (Batch)` latency is back to its normal ~1-2s baseline later today.
