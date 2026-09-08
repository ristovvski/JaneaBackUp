# 2026-08-19 — Comms audit, transcript batch B7 (files 14 + 15, both 2026-07-03)

Scope: Phase 2 extraction per `COMMS_AUDIT_build/communication_audit_brief.md`.
Output: `COMMS_AUDIT_build/_batches/B7.json` only. `ledger.json` / `ledger.md` read-only (cross-refs only), untouched.

## Done
- File 14 `14_UNKNOWN_team-sync.txt` (Sales Sprint Sync, 10:00, PROBABLE(calendar)) → 35 records R0716–R0750; written to B7.json before file 15 was opened (survival rule).
- File 15 `15_UNKNOWN_melisa-mykyta-1on1-workflow-review.txt` (LinkedIn automation sync, 09:30, CONFIRMED(calendar)) → 25 records R0751–R0775; B7.json rewritten with both.
- 60 records, ids R0716–R0775 (block fully used, no overflow). Types: 23 PROCESS FACT, 7 PROPOSAL, 7 DECISION, 6 ISSUE, 6 COMMITMENT, 4 QUESTION, 4 AGREEMENT, 3 CONCERN. Rulebook tags: P1, P2, P3, P4, P5, P7, P8, P10, P12, P14.
- 10 `ledger_updates` proposed (not applied): R0064, R0027, R0057, R0180, R0106, R0345, R0049, R0322, R0182, R0257.
- Validated: JSON parses, exact top-level shape, schema keys per record, id sequence/range, source = exact split filename, rulebook_part only on PROCESS FACT, every cross_ref resolves inside ledger.json or B7.

## Key findings
- Same-day reversal: 09:30 decision "buy one light seat" (R0775) superseded ~30 min later by HeyReach Growth trial bought by Sergey (R0740). Recorded as a pair, not merged.
- R0741: Melisa tells Sergey at 10:00 that she "explained the overall end to end process" — datable, third-party-witnessed, and its scope is boundable by file 15's actual content (LinkedHelper stages, labels, activity logging, notification path, nurture chain — not the meeting-label/deal rules disputed 08-18, R0165).
- R0756 (manual labeling / source channel) and R0767 (reply-without-accept gap) were stated in the 07-03 meeting *before* the Slack messages later framed as "I told you" (R0106, R0345).
- R0027 (HeyReach adoption) now has its explicit decision: R0774 + R0739 + R0257, all 2026-07-03.

## Improvable / open
- Index correction flagged: meeting_index.md row 14 calls the shared credentials "LinkedIn credentials"; they are HeyReach account credentials (matches R0257).
- One garbled passage deliberately left unrecorded: file 15 13:49 LinkedIn-URL-normalisation remark (gist clear, wording too corrupt to quote).
- London acceptance count differs across the same morning: 12 (09:30) vs ~15 (10:00) — flagged, not reconciled.
