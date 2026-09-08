# Slack audit coverage map

| # | Source | Status | Oldest ts | Newest ts | Notes |
|---|--------|--------|-----------|-----------|-------|
| 1 | DM: Melisa Draksler | IN PROGRESS (background agent) | | | |
| 2 | DM: Sergey Cujba | **COMPLETE** | 2026-05-28 14:10:37 | 2026-08-14 14:25:47 | 485 messages (475 top-level + 10 thread replies) across 4 monthly files (2026-05/06/07/08.json). 4 pages walked to exhaustion, confirmed "no more messages available". 4 threads found, all expanded and confirmed fully paginated. Out-of-scope cross-refs noted (2 other DMs, #gtm-engineering, #lead-processing). **Cleanup: removed a stale first-pass scrape (bounded oldest=2026-06-01, wrong schema, missed 8 msgs back to 05-28) that the same agent had left behind in this dir before its correct full pass — deleted, only the correct monthly files + coverage_note.md remain.** **Flag for Phase 2: 2 messages (2026-06-09) contain plaintext n8n and Langfuse login credentials shared by Sergey in-DM — captured verbatim per raw-dump mandate, not used/tested.** |
| 3 | #infra-issues (C0BNNG436KW) | **COMPLETE** | 1786036810.746539 (2026-08-06, channel creation) | 1787054102.901069 (2026-08-18) | Single page (limit=100), tool confirmed "no more messages available" — entire channel history fits in one call. 1 thread found + expanded (ts 1786639250.010269, 5 replies, fully captured). Several forwarded-message cross-refs point at #lead-processing (C07LTD8UT70), which is OUT OF SCOPE for this audit (not one of the 5 named sources) — logged as cross-ref only, not scraped. |
| 4 | #gtm-engineering (C0B7MK9QQ9L) | **COMPLETE** | 2026-06-02 13:57:11 (channel creation) | 2026-08-18 14:07:02 | 244 messages (220 top-level + 24 thread replies) across 3 monthly files (2026-06/07/08.json). 3 pages walked to exhaustion, confirmed "no more messages available" at channel creation. 8 threads found, all 8 expanded and confirmed fully paginated. Out-of-scope cross-refs noted (SharePoint, Sheets, Claude.ai artifacts, GitHub repo, 4 in-channel reposts already captured natively). **Flag for Phase 2: 2 messages contain plaintext account credentials/invite codes (Apify, HeyReach) — captured verbatim per raw-dump mandate, marked with `note` field, nothing acted on.** |
| 5 | #lead-generation-team (C08LUQ02CTW) | IN PROGRESS (background agent) | | | |

## Blocker
`communication_audit_brief.md` has NOT yet been placed in the working folder (checked via glob at task start — not found). Phase 2 (typed-record extraction) cannot begin until it arrives. Phase 1 scraping proceeds independent of this.

## Priority order (per mission)
1. DM Melisa Draksler
2. DM Sergey Cujba
3. #infra-issues
4. #gtm-engineering
5. #lead-generation-team
