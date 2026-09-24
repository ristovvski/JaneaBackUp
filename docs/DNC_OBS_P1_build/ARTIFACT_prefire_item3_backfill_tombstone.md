# Pre-fire artifact — item 3 of Nik's 2026-09-15 GO: backfill 4 missed repliers, tombstone 2 false positives

## Part A — backfill (via `dnc_archived_responders_import`, the correct caller-facing path to
`DNC__UpsertLedger__v1`, not a raw table write)

Found by the Smartlead+HeyReach completeness sweep in the full DNC audit: 4 genuine HeyReach
replies since 2026-09-01, confirmed campaign members (LinkedIn id match against
`[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn`'s real membership list), never entered
the registry — they predate the capture window this audit traced closely (all landed 2026-09-01/02,
before this session's own close tracking started).

| Name | LinkedIn | Reply time(s) | reason | reply_category |
|---|---|---|---|---|
| Person-054b9bef | linkedin.com/in/pii-732f4f86 | 2026-09-01 15:56, 16:08 | reply_dnc | linkedin_reply_uncategorised |
| Burak Aksar, PhD | linkedin.com/in/pii-74a1f082 | 2026-09-01 18:41 | reply_dnc | linkedin_reply_uncategorised |
| Person-19f1d00c | ACoAAAPMYF4B8rRIDJe3h0RtJytJPvdHoCcIMAk (raw URN — HeyReach returned this instead of a vanity slug) | 2026-09-01 20:11, 09-02 16:42 | reply_dnc | linkedin_reply_uncategorised |
| Person-58accf5a, CRPC®, CPRC | linkedin.com/in/pii-9857e430 | 2026-09-01 20:32, 09-02 23:03 | reply_dnc | linkedin_reply_uncategorised |

`source_ref`: `[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn` for all 4 (matches the real
campaign). `source`: `campaign_reply`. `added_at`: the FIRST reply timestamp for each (matches how
every other reply_dnc row in this window is dated). None currently in the registry under any
identity — direct check before firing (below).

## Part B — tombstone (direct, identity-matched `status=removed` update — no generic caller-facing
"tombstone with custom reason" tool exists yet in this project; modeled on
`dnc_s4_retirement_removal`'s own internal `Update Row` node, single-row eq-match, same shape,
different reason string)

| Name | Registry id | identity_key | Current | New |
|---|---|---|---|---|
| Person-d9409383 | 33141 | pii-d56d390e@example.invalid | status=active, reason=reply_dnc | status=removed, removed_reason=`false_reply_ooo` |
| Person-b27663e9 | 33142 | pii-140009b7@example.invalid | status=active, reason=reply_dnc | status=removed, removed_reason=`false_reply_mailbox_inactive` |

Evidence (from the full audit's Smartlead message-history read): Martinez's reply body is a pure
out-of-office auto-reply ("I am currently out of the office and will return on 9/14... contact
Client Relations at 619-876-5074"), Smartlead's own classifier tagged it `Out Of Office`. Spence's
reply reads as an automated mailbox-inactive notice ("This email account is no longer active. You
can forward your request to Mike Burgio..."), Smartlead tagged `No Longer Working There`. Nik's
word on Spence: "auto mailbox-inactive: I'd tombstone" — treated as the decision.

Verified via direct Pipedrive API just now: **neither has had their 686 field written yet**
(both still `None` live) — chunk 1 of the projections sweep (item 1) didn't reach them, they were
in the 135-row remainder. Tombstoning now, before the sweep's next automatic fire, means the
`status==='active'` guard added in item 1 will correctly exclude both from ever getting a wrongful
Pipedrive DNC-field write — no reverse/undo needed.

## Plan

1. Fire `dnc_archived_responders_import` with `dry_run:true` first (validation only), read the
   response.
2. Fire with `dry_run:false`. Known risk (not fixed today, out of scope for this GO): the
   workflow's own `Merge Outcomes` node is a 3-input `Merge(append)` fed by UpsertLedger's three
   disconnected terminal paths — the same fan-in shape as item 1's bug. All 4 rows are brand-new
   identities, so all 4 are expected to land on exactly ONE of those three inputs (the success
   path), which is the specific case proven unreliable this session. The actual registry WRITE
   happens inside `Call UpsertLedger`, before this Merge, so a hung/failed HTTP response would NOT
   mean the writes failed — post-verify reads the registry directly regardless of what the HTTP
   response says, per this project's standing "never trust the workflow's own success claim"
   discipline.
3. Tombstone Martinez + Spence via a single targeted probe workflow (two `dt_update` calls,
   `id eq <row id>`, deployed/fired/deleted immediately, same throwaway pattern used throughout
   this audit for reads).
4. Post-verify: re-read all 6 rows directly from the registry.
