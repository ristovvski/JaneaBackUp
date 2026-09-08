# 2026-09-03 — WF-2 state port, WF-1 duplicate-lead guard, claims retention

**Task:** port WF-2's three staticData stores to the atomic claims table (Nik's plan A), fix the
immortal-entry prune rather than just migrating it, fold in WF-1's duplicate-lead guard, sweep the
remaining stores with measured exposure, and add a linter rule for unbounded state.
Gate: §9f.2 pre-post with the migration count → Nik's word → fire. Fired on his GO.

**Output:** `WF2_STATE_PORT_2026-09-03/` (artifact, post-fire, builders, migration, backups, nodes),
`WF_SHARED/claims.js` + `test_claims.js`, `WF_LINTER/static_retention_bound.js`.

---

## DONE

- **WF-2R throttle first**, as instructed: `batchInterval 10000`. `7d31f745` → `f1e4a6b6`.
- **Exposure measured, not projected.** Found the real overlap window (28 Aug 11:45:42–11:46:16):
  four executions, all four mutating the same object, the one that started first finishing last and
  overwriting the other three. Also corrected my own earlier framing — staticData is ONE object
  persisted whole, so an overlap loses an entire execution's delta across every key, not one key.
- **Migration 105/105** (94 `wf2_seen`, 11 `wf2_alert`, 0 `wf2_bounce`), before the code change.
  101 values from epoch, 4 from ISO, zero refused. The four ex-ISO entries keep their true instants.
- **Deployed:** WF-2 174→188 nodes (`6a91be46`), WF-1 130→135 (`ca2ad957`), `dnc_claims_prune`
  (new, `2590de95`). Zero errored executions estate-wide since.
- **Five statics, four proven LIVE** — 6 overlapping executions → 6 rows; 4 on one key → 1 row;
  a claim survived a redeploy byte-identical. 37 offline assertions green.
- **Prune first run: 63 deleted, 0 failed**, 45 alert rows correctly retained at 90 days.
- **Linter rule** `static_retention_bound.js`, PASS, and proven non-vacuous (fails without its one
  declared acceptance).
- **`wf2_bounce_counter` chased**: not broken, already 30-day bounded, simply never executed —
  its feeder is the deduplicated-bounce path and no bounce has reached it.

## PARTIAL

- **The ported paths have not run in production.** WF-2 has had no traffic since 1 Sep 18:01. The
  live evidence proves the mechanism under real concurrency, not these two graphs under real
  events. I declined to fabricate webhook traffic: WF-2 is `WRITE_MODE: live` and synthetic events
  would create real Pipedrive activities, Slack posts and possibly a forward. Flagged for Nik.
- **The node count was under-estimated** in the pre-fire artifact (~9 → 14). The bounce store needed
  its own read/verdict/claim instead of sharing the dedupe lookup. Said so in the post-fire.

## BLOCKED

Nothing.

## IMPROVABLE

- **The claim is get-then-upsert, which narrows the race, it does not serialise it.** What it
  actually buys is durability across executions. Stated honestly in the WF-1 guard's comment and in
  the artifact; worth revisiting if n8n ever exposes a conditional insert.
- **`Body SL Forward Email` now depends on `Dedupe` having prefetched the `F|` key.** One more
  cross-node data dependency in a 188-node workflow. It falls back to staticData, but it is a
  coupling that did not exist before.
- **Nothing watches `dnc_claims_prune`.** If it silently stops, the table grows again and the only
  symptom is size. That is precisely how the bound got lost the first time.
- Four Code nodes in WF-2 now read a dataTable result as `$json`. That pattern is proven live
  (WF-1's `M7 Alert Gate` since this morning) but it is implicit, and a future insert between the
  read and the reader would break it with no error.

## Two mistakes worth keeping

1. **I nearly recorded a fiction as accepted fact.** My new linter flagged `by_inbox`/`by_domain`
   as unbounded stores. They are locals inside a bucket that is already rotated. I had written both
   into the "accepted unbounded" list, with reasons, before chasing the bounce counter revealed
   they were not stores at all. The detector matched a *shape*, not a fact.
2. **The Bash heredoc ate backslashes twice more**, once producing an empty regex alternation that
   hung the linter in an infinite loop. Both memories about this existed; I used heredocs anyway.
   Memory updated with the ~8 KB truncation limit as well.
