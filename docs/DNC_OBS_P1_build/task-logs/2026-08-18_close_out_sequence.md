# DNC Phase-1 close-out sequence — 2026-08-18

## Status: done

## What happened, in order

1. **Label reversal — fired live.** Auditor's fresh baseline (green, bracketed clean) → Nik's
   word → fired. Candidate set: `reversal_target_1975.json` (auditor's frozen 1,977 minus the 2
   explicit opt-outs, Person-82f6ebe9 + Person-b7b67214). Result: 1,966 stripped, 9 already-correct
   (legit no-ops, a human had already hand-stripped them), 0 anomalies. Final labelled count: 7
   survivors (4 baseline + Martinets + Braden + Chapman) — matches the auditor's expected grade
   exactly.
   - **Bug found and fixed live, mid-fire**: `R Patch Lead Labels`' raw HTTP response overwrote
     the item's `{outcome, lead_id}` context, so `R Combine` couldn't see real successes and
     reported "0 stripped, done" after the first 100-item chunk — even though those 100 writes
     had already succeeded correctly (verified directly). Fixed with a paired-item restore node
     (`R Confirm Strip`), redeployed, resumed from offset 100 (no reprocessing needed).
   - **Also fixed**: `R Get Lead By Id`'s error output was unwired (silent-failure-gap class);
     now wired to a `fetch_error` outcome, tallied and named.
   - Added `live_exclusion_ids` support for last-minute drift the auditor names at re-anchor.

2. **S1 (Responded → DNC) — fired live.** 1,715 candidates (Pipedrive "3. Responded" label scan),
   886 written (`reason=reply_dnc`, `reply_category=unclassified`), 829 skipped (no email/
   LinkedIn). Smartlead any-campaign-history + HeyReach union (the real "120" delta) NOT done —
   named gap, scoped as fast-follow.

3. **S2 (Meeting → DNC) — dry-run then fired live.** 541 candidates (auditor's
   `r3_s2_persons.json`: label "5. Meeting" 304 ∪ deal stage "Qualified Meeting Set" 246, overlap
   9), 351 written (`reason=meeting_dnc`), 190 skipped no-identity.
   - **Bug found and fixed** (same class as the reversal's, different node): `S1/S2 Write
     Barrier` used `runOnceForAllItems` + a static return, collapsing every real identity-bearing
     item down to 1 before the count. Writes were always correct (mode:each fans out upstream);
     only `matches_this_chunk` was wrong on every chunk. Fixed on both S1 and S2, redeployed.
   - **Bug found and fixed**: `DNC__UpsertLedger__v1` was never redeployed after `meeting_dnc` was
     added to `reason_v1.js` earlier today — live subworkflow rejected every S2 write with
     "invalid reason meeting_dnc" until redeployed.
   - Bonus check (Nik): Person-6b93835c, Person-cec152be expected in scope, aren't — Pipedrive
     currently shows neither with the label or a deal. Label/stage human-lag, flagged for Melisa.

4. **Fast-follows:**
   - HeyReach reclassification of the 116 `reply_dnc` rows: only 3/116 have any HeyReach
     conversation at all (113 don't), none contain opt-out language. All 116 are tagged
     `Amsterdam 2025 Reply` (an email import) — HeyReach isn't the right source for most of them.
     Result written to `fixtures/reply_dnc_116_heyreach_reclassification_result.json`. A
     Smartlead-side check is the real fast-follow; not done today, scoped separately.
   - Detector nurture exemption: confirmed already deployed and correct (7 verified
     `@janeasystems.com`-sender campaigns excluded).

5. **S3 watcher "1 polls/day" report — diagnosed and fixed.** Neither the 15-min poll schedule
   nor the counter logic was wrong (confirmed live: mid-day `pollsToday` was correctly at 30). The
   heartbeat fired at `00:05` — 5 minutes after the counter resets for the new day — so it always
   read "1" before the other ~95 polls of the day ever happened. Moved to `23:55` (reports the
   day's real total right before rollover). Redeployed.

6. **EOD summary posted to #ops** (Slack, `C0B8GCVNR5W`) — per-scenario counts, reversal final
   state, detector status (corrected the "7 runs/day" assumption to the real 24/day hourly
   cadence), gate status, and both flags (Melisa's label-lag, the HeyReach-scope finding).

## Bugs found and fixed today (6 total, all same-session)

1. Reversal: `R Patch Lead Labels` HTTP response overwrote outcome context (reporting only,
   writes correct).
2. Reversal: `R Get Lead By Id` error output unwired (silent-failure-gap class).
3. S1/S2: `Write Barrier` collapsed N items to 1 (reporting only, writes correct).
4. S2: `DNC__UpsertLedger__v1` never redeployed after `meeting_dnc` was added (real write
   failures until fixed).
5. S4: Smartlead STOPPED-status leads render "undefined" in the skip report (cosmetic, fixed
   with a `campaign_lead_map_id` fallback).
6. S3: heartbeat fires at the wrong time of day relative to the counter it reads (reporting only).

None of these caused data loss or incorrect registry writes — all six were reporting/deploy-drift
bugs, not correctness bugs in the underlying upsert/strip logic itself. Every fix is tested (84
static contract tests, all green) and redeployed.

## Not done today (named gaps, not surprises)

- S1's full Smartlead any-campaign-history + HeyReach reply union (the real "120" delta).
- The 116 reply_dnc HeyReach reclassification found the wrong channel; a Smartlead-side check is
  the real fast-follow.
- Gate wiring into Make/Zapier cold-campaign-add paths — next week by design.
