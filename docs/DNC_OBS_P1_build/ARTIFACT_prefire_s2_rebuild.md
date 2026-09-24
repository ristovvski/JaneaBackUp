# Pre-fire artifact — S2 rebuild (Nik's 2026-09-15 GO, follow-up to item 4)

## What's changing

Full replacement of `dnc_s2_meeting_to_dnc` (live id `E0oTTvHHQ0hVTNDD`), not an extension of the
old design. Diff: **add** 7 nodes (`Daily Timer`, `S2 Get Recent Label Leads`,
`S2 Classify Label Signals`, `S2 Get Recent Stage Deals`, `S2 Classify Stage Signals`,
`S2 Aggregate Candidates`, `S2 Split Candidates`), **remove** 4 (`S2 Classify`, `S2 Limit Chunk`,
`S2 Merge Identity Paths`, `S2 Write Barrier` — the old frozen-list consumer and its Merge),
**change** 4 (`CONFIG` — new live-query fields replace `person_ids`/`offset`; `S2 Build Upsert
Input`/`S2 Combine` — rewritten for the new signal shape; `S2 Send Guard` — a stale channel-default
drift fix that comes along for free, same direction/cause as item 1's). `Webhook` and
`S2 Call UpsertLedger` are unchanged (the webhook stays as a no-payload supervised-fire trigger;
UpsertLedger is called exactly the same way as before).

## Confirmed live before building (not assumed)

- Lead label "5. Meeting" id: `35edf580-d19e-11ef-935e-7d712003f1b4`.
- Pipeline "Janea Systems Consulting" = id 8; stage "Qualified Meeting Set" = id 54 (the pipeline's
  own entry stage).
- `v1/leads` and `v1/deals` both support `sort=update_time DESC` correctly (spot-checked ordering,
  not assumed) and a single-call `limit=500` (no native multi-page pagination needed — avoids that
  mode's own item-per-page fan-out risk entirely). Measured: ~400 leads sorted by update_time DESC
  covers the last 24h of real update volume on this instance today — 500 leaves headroom; the
  `possibly_truncated` flag in the report is the safety net if that ever stops holding, not a
  silent assumption.
- `deal.person_id` is a nested object (`{value, name, ...}`); `lead.person_id` is a bare id — both
  confirmed against real records (deal 2267 / Chirag R Shah).
- `lead.update_time` arrives as ISO8601+Z; `deal.update_time` arrives as a bare space-separated UTC
  string with no timezone marker — confirmed against real records from both endpoints in the same
  session. Both classifiers normalize via a shared `tsToIso()` helper.
- No Pipedrive-side filter exists for "has label X" on leads, and v2 leads is 404 on this instance
  (matches project memory) — client-side filtering after a bounded fetch is the only option; this
  will re-see leads that already had the label from a prior day (any unrelated field update bumps
  `update_time` too), which is harmless because the identity-based upsert is already idempotent —
  documented as a deliberate trade-off, not hidden.

## Fan-in: eliminated by design, not patched (Nik: "fix the flagged fan-in before scheduling")

No `Merge` node exists anywhere in the new build. `S2 Aggregate Candidates` runs exactly once per
execution, before any per-item split, and fans OUT directly to both the split and `S2 Combine` —
the same proven pattern used for `dnc_projections_sweep`'s `PD Aggregate` earlier today. The two
signal branches are hand-sequenced (label fully classified before the deal fetch starts), matching
the nightly reconcile's own proven fix for "a small, fixed number of branches." 110/110 contract
tests passing, including a new structural test that explicitly asserts no Merge node exists, and a
new statics test exercising all 5 of Nik's required cases directly against the real aggregation
code (label-only → 1 candidate; stage-only → 1 candidate; both → 2 candidate entries but 1 distinct
person and `both_signal_people=1`; neither → 0; reason-strength no-downgrade re-asserted against
`reason_v1.js`'s own tested logic, which this workflow relies on rather than reimplements).

## Dedup mechanism (Nik: "one row, both signals in also_flagged")

Deliberately NOT a pre-merged single record. `DNC__UpsertLedger__v1`'s own merge logic
(`reason_v1.js`'s `reasonMergeV1`) resets `also_flagged` to `[]` on a fresh insert regardless of
what a caller supplies — a hand-built merged record could never populate it correctly on a brand-
new person. Instead, a dual-signal person gets TWO entries in the flat candidate list (kept, not
deduped away), each with its own `source_ref` (`'5. Meeting label'` / `'Qualified Meeting Set
stage'`). n8n processes a Split Out's items sequentially, never concurrently, so both calls land on
the SAME identity — reason ties (both `meeting_dnc`, no downgrade) but `source_ref` differs, which
is exactly the condition `reasonMergeV1` checks to append to `also_flagged`. This is the identical,
already-proven mechanism from earlier today (Chirag R Shah's `meeting_dnc` + S3/Surfe signal via
two separate calls, landed in `also_flagged` correctly on the first try) — reused, not reinvented.
Registry upsert-by-identity means the outcome is still exactly one row either way.

## Plan

1. Deploy structurally via `safe_patch_workflow` (add 7 / remove 4 / change 4, all as diffed and
   verified above).
2. Dry-run fire via the new `dnc_fire_s2_daily.py` (webhook, no payload, `FIRE_S2` stays `false` —
   the workflow's default, unchanged by this patch) — watch `S2 Combine`'s real output against
   today's actual Pipedrive data.
3. Flip `FIRE_S2: false → true` as a separate live-only CONFIG patch (same convention as every
   other FIRE flag this session).
4. Fire for real, supervised, via the same script.
5. Post-verify: read back whatever rows actually got written directly from the registry — not
   trusted from the Slack summary or the HTTP response.
