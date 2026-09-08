# 2026-08-19 — COMMS audit Phase 2, batch B5 (transcript extraction)

## done
- Read brief + `transcripts/meeting_index.md`; read `ledger.json` meta + targeted cross-ref records (read-only, never written).
- Extracted `10_UNKNOWN_team-sync-integration-incident.txt` (2026-07-14, Trigger campaign sync) → 40 records R0596–R0635; wrote `COMMS_AUDIT_build/_batches/B5.json` before touching file 2 (survival rule honoured).
- Extracted `11_UNKNOWN_pipedrive-automation-w-lilla-szabo.txt` (2026-07-10, ICP scoping) → 20 records R0636–R0655; rewrote B5.json with both files.
- 6 `ledger_updates` proposed (R0272, R0275, R0290, R0115, R0014, R0143). ledger.json / ledger.md untouched.
- Validated: JSON parses, 60 records, ids strictly ascending inside R0596–R0655, exact record shape, rulebook_part only on PROCESS FACT / DEFINITION.

## partial
- `R0596` "Integration is not working" — referent never stated in the transcript; recorded as undiagnosed rather than guessed at (HeyReach is the plausible but unproven referent).
- `R0621` (Sergey posting Mike's ClickUp item to Slack) left `unconfirmed` — no matching Slack message in the ingested corpus.

## blocked
- Nothing. Both files were fully legible apart from three fragments at the tail of file 11 (19:47–23:45), skipped.

## improvable
- Files 10 and 11 both hinge on documents that never appear in the corpus (Sergey's ICP deck R0615, Chrissy's ICP definition R0639, Lilla's scope doc R0645). If those artifacts exist outside Slack/transcripts, ingesting them would close several OPEN items at once.
- `R0650` (MQL vs SQL: which entity level, attribute or category?) is OPEN corpus-wide — a genuine rulebook-session question, not something the history answers.
