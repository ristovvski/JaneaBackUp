# R1 — reply backfill, DRY-RUN (zero writes). Awaiting word before live.

Contract read live from WF-2 `versionId e9242d0a` — not re-invented. Verified by graph traversal
that `IF Forwardable`'s FALSE branch still reaches `Lead Labels Union` → `Reply Activity`, so
non-forwardable replies (Out Of Office, Wrong Person) correctly still get labels + activity, and
only the *forward* is category-gated.

Artifact: `r1_reply_backfill_dryrun.json` · script `r1_reply_backfill.py` (same code path runs live
with `DRY_RUN=0`; `ONLY=<email>` runs a single case).

## Planned writes

| # | reply | lead | category | label union | activity | forward |
|---|---|---|---|---|---|---|
| 1 | pii-567b1851@example.invalid 16:55 | f6e3dd60 | **Interested** (SL) | already has all 3 | yes | → mario@janeasystems.com |
| 2 | pii-567b1851@example.invalid 17:15 | f6e3dd60 | **Interested** (SL) | already has all 3 | yes | → mario@janeasystems.com |
| 3 | pii-7b1c0e1a@example.invalid 19:10 | **none — create** | Not Interested (SL) | +2 after create | yes | → mario@janeasystems.com |
| 4 | pii-67425a37@example.invalid 15:10 | bea15530 | Out Of Office (SL) | +2 | yes | skip (not forwardable) |
| 5 | pii-b02b50cf@example.invalid 16:15 | 40aeb410 | Out Of Office (SL) | +2 | yes | skip |
| 6 | **pii-6f8f48e5@example.invalid 16:31** | cd5c3cc0 | **Interested** (SL) | already has all 3 | yes | **→ rune@janeasystems.com** |
| 7 | pii-135b4c7b@example.invalid 16:38 | 0a28f1e0 | **Sender Originated Bounce** (classified 0.99) | +2 ⚠ | yes | skip |
| 8 | pii-90ec4caf@example.invalid 16:38 | 020bb320 | Out Of Office (SL) | +2 | yes | skip |
| 9 | pii-06275333@example.invalid 17:04 | 95c2d010 | Out Of Office (SL) | +2 | yes | skip |
| 10 | pii-280f963f@example.invalid 06:08 | ce1d0d00 | Wrong Person (SL) | +2 | yes | skip |

**Live totals** (dry-run prints 9 activities / 6 unions because john.teuber's lead doesn't exist
yet — it gets both once created): 1 lead created · 1 Smartlead category · **7** label unions ·
**10** reply activities · **4** forwards · 6 forwards correctly skipped.

## Things the dry-run surfaced that change the picture

1. **pii-6f8f48e5@example.invalid is hotter than jonathan.brum.** Its reply is literally **"How about
   5pm?"** — Person-de82a469, Head of Computational Drug Design at Deerfield, proposing a meeting time
   for AI4. Smartlead has it as `Interested`. It never reached Rune and it is **2 days stale**.
   It was invisible to my earlier sweep because `/statistics.reply_time` omitted it — exactly the
   under-reporting that made the correct endpoint choice matter.
2. **pii-135b4c7b@example.invalid is not a reply at all — it is a bounce.** "Address not found … the address
   couldn't be found". Classified `Sender Originated Bounce` at 0.99 confidence. See decision D2.
3. **All 10 leads resolved by `title_prefix`, none by `campaign_field`** — every one of these leads
   has an empty lead Campaign field. That is Make's known lead-creation defect, confirmed again at
   100% incidence on this sample.
4. **Handover guard baseline: 0 open activities** across all touched leads right now. The reply
   activity is written `done: true`, so it does not itself satisfy "has a next activity" —
   **expect up to 7 auto-created Handovers** (one per lead newly receiving `3. Responded`;
   jonathan.brum and hwang already carry it and should not re-trigger). Per the C2 rule these get
   marked done with a "historical backfill" note, and the actual count is reported after the run.

## Decisions I need your word on

**D1 — go/no-go on the plan above as written.**

**D2 — pii-135b4c7b@example.invalid (the bounce).** WF-2 routes bounces down its own branch (`Bounce Note`),
never the reply branch, so labelling a bounced address `3. Responded` would be a contract
violation and would mark a dead address as engaged. **My recommendation: for mrudu, write the
Smartlead category (9) and a bounce note only — no `3. Responded` label, and exclude it from the
reply count.** That drops label unions from 7 to 6. Say the word if you'd rather keep it uniform.

**D3 — jonathan.brum forwards twice.** Two reply events on one lead → WF-2's contract forwards
each, so Mario gets two emails, the second being "Sounds good, thank you Mario". I'll follow the
contract unless you'd prefer one forward per lead (the latest reply only).

**D4 — Slack reply alerts.** WF-2 also posts a `Reply Alert` to `C0B8GCVNR5W` per first reply.
I've left it **out** of this plan — 7 alerts about two-day-old replies would read as a live burst.
Say if you want them posted (or posted as a single consolidated digest instead).

## Not touched

Event Name / Marketing Hypothesis fields — untouched, as instructed. Duplicate forensics — not
mine. All writes here are confined to the replies domain: lead labels, reply activities, one lead
creation, one Smartlead category, four forwards.
