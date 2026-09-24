# Pre-fire artifact — S3 roster-owned backfill (Nik's 2026-09-15 GO: "roster-owned means protected")

## Policy change

Nik: "no distinction needed — Surfe-sourced or personal, roster-owned means protected... no source
check." This supersedes the 2026-08-19/08-20 "creator not owner" ruling that the existing S3 leads
watcher and the earlier report-only persons extension were both built around — owner ∈ roster is
now sufficient on its own, no creator/lead/channel corroboration required.

## Source list: 111 candidates (10 "ambiguous" Noah/Surfe + 101 campaign-import EVT, excluding the
32 already-reply_dnc "KNOWN" ones from the full audit's evidence table)

Hand-extracted from the evidence agent's report, counts cross-checked before touching anything:
44 Mario-EVT + 57 Noah-EVT = 101 (matches the agent's own "101 EVT" total exactly); + 10
Noah-Surfe = 111 total. Saved to `SUPABASE_PROJECTION_build/s3_persons_backfill_ids.py` with
assertions on every count.

## Live verification (before writing anything) — a real, useful finding, not just due diligence

Fetched all 111 directly from Pipedrive against a fresh registry pull (not the evidence agent's
now-hours-old snapshot). **29 of 111 are already in the registry**:

- **All 10 "ambiguous" Surfe people are already `sales_personal_outreach`, `active`.** Not written
  by anything today — the ORIGINAL, unmodified `dnc_s3_creation_watcher` (leads path, still running
  on its normal 15-min schedule with `FIRE_S3=true` this whole time) caught them legitimately on
  its own: the evidence agent's own report already noted these 10 have `creator_id` = Noah's own
  Pipedrive user id on their associated lead — which satisfies even the STRICTER original
  creator-based rule, not just the new looser owner-based one. So "write all 10" was already true
  by the time I checked; nothing to do for them.
- 16 of the EVT people are now `reply_dnc` (organic replies landed since the evidence agent ran).
- 3 are now `meeting_dnc` (today's S2 rebuild fire — Person-b66505b6, Person-a3b5622e, Person-67becab1).

**82 genuinely need a fresh write.** All 82 resolved with a usable identity (LinkedIn for all 82;
28 also have email). Saved to `SUPABASE_PROJECTION_build/audit_out/s3_backfill_resolved.json`.

## Plan

Fire the 82 through `dnc_archived_responders_import` (dry-run then real), in chunks of ~20 —
smaller than my earlier 4-person test, purely for manageable blast radius and easier verification,
not because chunk size changes the tool's own known residual risk (its `Merge Outcomes` node is
the same 3-input fan-in shape flagged earlier this session; every item in this batch is expected to
route through the single "success" branch since none are currently registered, which is exactly the
single-populated-branch case proven unreliable elsewhere — not fixed here, out of scope for this
ask; the actual registry write happens before that Merge regardless, so post-verify reads the
registry directly, never trusted from the HTTP response). `reason=sales_personal_outreach`,
`source=pipedrive_personal`, `source_ref=<owner name>`, `source_signal` set per kind (`surfe` for
the Surfe-sourced ones — none remain in this batch — `creator` is not applicable here since none of
these 82 satisfy the creator rule, so left unset/omitted, matching the schema's own definition:
`source_signal` is specifically about which S3 trigger signal fired, and "owner-only, Nik's new
rule" isn't one of the three enumerated values (`creator`/`surfe`/`both`) — leaving it null rather
than mislabeling is the honest choice).

Post-verify: read all 82 back from the registry directly after firing.
