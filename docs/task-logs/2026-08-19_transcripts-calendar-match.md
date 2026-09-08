# 2026-08-19 — Transcript ↔ Outlook calendar matching (22 split files)

Scope: MATCHING + INDEX UPDATE only. No structured-record extraction, no ledger, no Slack, no network.

## DONE
- Read `COMMS_AUDIT_build/transcripts/meeting_index.md`, then script-extracted speaker rosters, turn
  counts, timestamp spans, name mentions and date/day-name signals for all 22 split files in three
  bulk passes (no full reads of the long files).
- Matched all 22 files to calendar anchors. 7 CONFIRMED(calendar), 15 PROBABLE(calendar), 0 UNMATCHED.
- Rewrote `meeting_index.md` with matched anchor + date + confidence + participants (incl. new
  INFERRED(calendar) speaker resolutions) + topic summary + first line; preserved and annotated the
  pre-existing anomaly notes; added a full matching-reasoning section and the ordering cross-check.
- Ordering cross-check PASSES: dates monotonically non-increasing 01→22, no anchor used twice
  (21/22 deliberately share one), no cancelled-list entry used.
- Scratch working notes left at `COMMS_AUDIT_build/transcripts/_matching_notes.md` (disposable).

## Key load-bearing findings
- File 04 contains the only explicit date in the corpus: "So today is 11" → 2026-08-11. Everything
  else is derived from that plus the newest-first ordering constraint.
- Calendar anchor times read ~UTC while participants speak CEST (+2h). Proven twice independently
  (file 01 "meetings started at 10:30" vs the 08:30 anchor; file 04 books "1Pm" vs the 11:00 anchor).
  Anchor clock times were therefore used only for within-day ordering.
- Files 15 → 14 are back-to-back on the same Friday morning (07-03); file 15's closing "let's jump on
  another meeting" plus the HeyReach-credentials handoff is what fixes both dates.
- HeyReach integration landing Mon 2026-07-13 is a strong shared pivot: file 13 and file 12 both
  forecast it, file 10 opens on it being broken. Consistent with the known HeyReach start date.
- SPEAKER CORRECTION: in file 21 Speaker 1 = Sergey Cujba, Speaker 2 = Mykyta Krivosheya — the
  reverse of the previous index's tentative guess. File 22's name *pair* is therefore right; its
  per-turn boundaries are still unreliable.
- File 02's four generic speakers resolved via the 08-14 HeyReach onboarding roster:
  Sp1 = Mykyta (CONFIRMED), Sp2 = Melisa Draksler, Sp3/Sp4 = Araks Grigoryan / Lule Salihu
  (all INFERRED(calendar); 3 vs 4 not individually separable).

## PARTIAL / IMPROVABLE
- File 20 (5-person conference-support call) → 06-18 All-team is the weakest match: Toby, Mario and
  Jim are absent and Sergey distinguishes the call from the Sales&Marketing meeting. Flagged in the
  index; downgrading it to UNMATCHED would not disturb any other row.
- Files 06, 07, 15 are near-identical two-person Mykyta/Melisa-Draksler 1:1s whose dates rest mainly
  on the ordering constraint. If Nik can confirm any one, re-check the others.
- File 19's anchor ("Sync (Melisa)" 06-19) does not say *which* Melisa; assignment rests on content
  maturity (an 11,600-row table already built rules out the 05-29 alternative).
- Possibly-missing recordings worth chasing: **07-16 HeyReach Sync (Nik org) 09:00** (organised by
  Nik, three days after the integration landed — the most conspicuous gap) and **08-14 Task
  management (Mykyta/Stefan) 11:30** (file 01 confirms more 08-14 meetings happened).

## BLOCKED
- Nothing.
