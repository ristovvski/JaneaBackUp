# COVERAGE_MAP — what was ingested, what is missing, which conclusions are provisional

As of 2026-08-19. Every conclusion in the other synthesis documents is bounded by this page.
Per the brief: conclusions are stated as "based on ingested material", never as complete.

## Slack — all five sources paged to exhaustion, threads expanded

| Source | Period ingested | Messages | Records | IDs | Exhaustion |
|---|---|---|---|---|---|
| DM — Melisa Draksler | 2026-05-28 → 08-18 | 2,231 | 167 | R0001–R0167 | both ends confirmed |
| DM — Sergey Cujba | 2026-05-28 → 08-14 | 485 | 43 | R0168–R0210 | both ends confirmed |
| #infra-issues | 2026-08-06 → 08-18 | 62 | 30 | R0211–R0240 | full channel (created 08-06) |
| #gtm-engineering | 2026-06-02 → 08-18 | 244 | 58 | R0241–R0298 | full channel (created 06-02) |
| #lead-generation-team | 2026-06-01 → 08-18 | 536 | 117 | R0299–R0415 | full audit window |
| **Total** | | **3,558** | **415** | | |

Both DMs begin 2026-05-28 — earlier than the original 06-01 audit window, recovered during reconciliation.
Quiet periods verified as genuine, not scrape gaps: dm-melisa 06-30→07-02 (Melisa at a hospital appointment), dm-sergey 05-28→06-03.

## Meeting transcripts — 21 of 22 extracted

Source: `ALL_TRANSCRIPTS_raw.txt` (724,985 bytes), split on backward timestamp jumps >5 min, byte-exact against source.
Calendar-anchored against Nik's Outlook. The corpus is **reverse-chronological** (file 01 = newest).
Records R0416–R0955 (519). ID gaps are expected — each batch held a reserved block, none padded.

7 dates CONFIRMED(calendar) · 4 upgraded to CONFIRMED(corroborated) · 1 CONFIRMED(owner) · rest PROBABLE(calendar) · 1 month-only.
Calendar times read ~UTC while participants speak CEST (+2h) — times used only for within-day ordering.

### Files with reduced confidence or zero yield
| File | Status | Effect on conclusions |
|---|---|---|
| 09 (Nik↔Sergey, 07-21) | **0 records** — non-English audio mis-transcribed as phonetic English | that meeting is effectively unaudited; re-transcribe with UK/RU selected to recover it |
| 19 (Melisa Bahonjić 1:1, 06-19) | date CONFIRMED(owner); attributed to **Melisa Bahonjić**, a separate person from Draksler (owner ruling 2026-08-19) | nothing here is evidence about Draksler |
| 19 | token "janeasystems" appears 11× standing in for both Clay and an unidentified colleague | the Jim-escalation rule (R0857) is only partially readable |
| 20 (event planning) | **downgraded to month-only `2026-06`, anchor UNMATCHED** — no date signal, and Toby/Mario/Jim explicitly absent | its content is sound; its date cannot carry supersession arguments |
| 22 | **DISCARDED** by owner ruling (garbled duplicate of 21); file retained in `transcripts/_quarantine/` for provenance | none — 21 is the intelligible version of the same call |

## Known gaps — conclusions touching these are provisional

1. **Two calendar anchors have no transcript.** 07-16 HeyReach Sync (Nik-organised, three days after the integration landed) and 08-14 Task management (Mykyta/Stefan). The first is the conspicuous one: the integration's own review meeting is unaudited.
2. **File 09 unusable** — one 07-21 Nik↔Sergey conversation contributes nothing.
3. **Unrecorded conversations are invisible.** Huddles, calls without Fireflies, and corridor conversations leave no trace. This is the single most important limit on every "never answered" and "not found" claim in these deliverables — including the deadline dispute.
4. **Channels outside the audited five are not covered.** Cross-references were seen pointing into #lead-processing (C07LTD8UT70), C0BDZ128HHP, C0BEMRTPSKY, and #sales-marketing (C079Z9RK50U); none were fetched.
5. **#infra-issues only exists from 08-06** and #gtm-engineering from 06-02 — infrastructure discussion before those dates lives in the DMs or nowhere.
6. **lead-generation-team raw file boundaries were lost** to a concurrent session's overwrite; surviving monthly files were used. Top-level counts reconcile exactly (472), so content is believed intact, but the original per-range files are gone.
7. **The channel predates the audit window** (#lead-generation-team runs back to 2025-04 with an ~8-month silence); only 2026-06-01 onward was ingested, per scope.

## Data-integrity events during the audit

- A **second concurrent session** wrote into the same output folders and twice deleted files mid-run. Both DM folders were reconciled by deduplicating on Slack `ts`; this session's version was authoritative on overlap, and the other session's exclusive pre-window messages were converted and marked `origin: other-session dump`. Originals are in `slack_audit/raw/_quarantine/`, not deleted.
- Overlap comparison found **2 genuine user-attribution disagreements** and **12 text-swaps between adjacent near-simultaneous messages** in dm-melisa — logged in that folder's `coverage.md`. All other differences were cosmetic.
- **23 pasted credentials** were redacted in place across 12 files as `[REDACTED:<service>]`; inventory in `slack_audit/redactions.md` (service + date + source, never values).

## Provenance classes — do not mix

- **In-corpus**: Slack messages and meeting transcripts. Quotable as evidence.
- **OUT-OF-CORPUS**: owner corrections R0956–R0958, supplied by Nik in terminal on 2026-08-19. Authoritative about the present system, but **never citable as something Melisa or Sergey said**. Each carries a `provenance` field.
- **Derived**: permalinks in #infra-issues raw dumps were constructed from timestamps, not returned by the API.

## Contested statuses

14 records carry `status_contested: true` — different extraction batches proposed conflicting statuses for the same record. Newest evidence was applied; every proposal is retained in that record's `update_history`. Per owner instruction they are surfaced **AS CONTESTED** throughout these deliverables rather than resolved.
