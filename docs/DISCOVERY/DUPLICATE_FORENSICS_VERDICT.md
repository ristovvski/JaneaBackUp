# Duplicate Forensics — #lead-processing (C07LTD8UT70) — VERDICT

Read-only throughout. Full harvest: 1,641 bot/app records, 2024-12-19 → 2026-08-05 (true beginning
of the channel, confirmed by Slack's own "no more messages" response). Reporting window per scope
cut: **2026-06-05 → 2026-08-05** (covers the duplicate Zap's active life, WF-1's era, and the kill).
Timeline chart: `lead_processing_duplicates_timeline.html` (published artifact).

## Taxonomy

### Class A — Zap 274357187, one-write-two-posts (13 of 21 tight pairs) — **DEAD**
A single WF-1 Pipedrive write (one PATCH burst, one timestamp) produced two near-identical Slack
posts from "Zapier Bot," typically 0.1–0.9s apart. Every instance traces to actor `25112064` (WF-1's
own API token), `change_source=api` — never Make, never a human, never a second automation. The
duplication happened between Pipedrive's webhook delivery and the Zap's Slack-post action, not in the
CRM write itself. **In operator terms: WF-1 did its job correctly once; the notification bot said it
twice.** Root cause died the moment the Zap was disabled — no code fix was needed on our side.

### Class B — Zap 274357187, two-writes-two-posts (8 of 21 tight pairs) — **DEAD (same kill)**
Same Zap, same actor (WF-1), but here WF-1 itself made **two separate Pipedrive writes about one
second apart** for what a human would call a single reply event — not a re-run, a real pattern in
WF-1's own reply-handling logic. Each write is a genuine Pipedrive "Person updated" event, so each
correctly triggered the Zap once — the Zap behaved exactly as built; WF-1's two-step write pattern is
what created two triggerable events. **Operator terms: this is a real fact about how WF-1 saves a
reply (two small updates instead of one), not a bug — but ANY other automation that watches Person
Updated for these people would double-fire the same way.** Also died with the kill (the Zap was the
only consumer producing a visible symptom), but the underlying two-write pattern is still live in
WF-1 and worth knowing about if a new Person-Updated watcher is ever added.

**Both classes, combined evidence:** 21/21 tight pairs, 21/21 attributed to WF-1 as sole trigger
source, **zero occurrences after 2026-08-05T11:28:42Z** (the kill). Weekly counts: W29=4, W30=2,
W31=7, W32=8, then zero. This is the closing evidence for Melisa's report.

### Class C — Make/"Lilla Szabo," near-instant duplicate (2 of 394 posts, all-time) — **DORMANT, not "never"**
Correcting "today's sample said no duplicates ever": across the full 394-post history, **two
byte-identical duplicate posts exist** — Jose/Cyber Trek (2025-10-17, 0.18s apart) and Giovanni/AMROS
(2026-04-20, 6.6s apart). Both predate the reporting window by months, and zero have recurred since.
**Operator terms: Make's notifier has duplicated exactly twice in its whole history, both a long time
ago, and hasn't done it again since** — real, but rare and currently inactive. Not the same mechanism
as Class A/B (no Pipedrive-changelog cross-check was run on these two, since they're outside the
active-investigation window; flagging for awareness, not urgent action).

### Class D — "Dealbot by Pipedrive," native-integration burst (11 posts, Dec 2024–Jan 2025) — **DEAD, pre-dates WF-1**
A third, previously undocumented notifier — Pipedrive's own native Slack integration — posted
"Responded Lead" notifications for about a month, including one burst of 5 near-identical posts in
~3 minutes, then went silent. This predates WF-1 entirely and has never resumed. **Operator terms: an
old, retired notification path from before the current system existed — no action needed, mentioned
for completeness since it's a real historical duplicate-notification source nobody had named.**

### Not a duplicate class — 1 near pair (2min–24h), 1 far repeat (>24h)
A lead can legitimately reply twice, weeks apart (e.g. Person-0f138f6a: two Make posts 13 days apart, same
lead, genuinely two separate reply events). These are correctly excluded from the duplicate count.

## Full ledger
`dup_ledger_output.json` (tight/near/far pairs with timestamps + Slack permalinks) and
`changelog_diagnosis.json` (per-pair Pipedrive changelog classification) are the underlying data for
every claim above.

## Zapier run-history cross-check — not yet done
The Zapier-MCP has no connected account; connect link surfaced to the owner for Nik:
`https://mcp.zapier.com/api/v1/connect-auth/ZapierManagerCLIAPI?accountId=15803035`. Once connected,
run-history could confirm Class A/B at the Zapier-execution level directly rather than inferring it
from Pipedrive-side timing — worth doing to fully close the loop, but the Pipedrive-changelog method
already gives high-confidence attribution (100% single-actor, sub-second/1-second timing signatures
consistent across all 21 cases) without it.
