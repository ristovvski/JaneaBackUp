# Post-fire — WF-2 state port, WF-1 duplicate-lead guard, claims retention

**2026-09-03.** Everything in the pre-fire artifact is deployed. **Zero errored executions
estate-wide since the deploy.**

| | before | after | nodes |
|---|---|---|---|
| WF-2 Smartlead Receiver | `9c821fcc` | **`6a91be46`** | 174 → **188**, active |
| WF-1 HeyReach Receiver | `0c6fa377` | **`ca2ad957`** | 130 → **135**, active |
| WF-2R (throttle, earlier) | `7d31f745` | **`f1e4a6b6`** | 25, active |
| `dnc_claims_prune` | — | **`2590de95`** (new, `csGJbrHxEBnJdFfu`) | 10, active |

Backups of every pre-change definition are in `backups/`.

---

## 1. The migration — 105/105, verified by family

```
rows to write: 105  (from epoch 101, from ISO 4)
   wf2_alert    11
   wf2_seen     94
upsert returned: {"returned":105,"real_rows":105,"by_family":{"wf2_seen":94,"wf2_alert":11},
                  "not_real":0}
```

Migration ran **before** the code change, as agreed. `wf2_bounce_seen` was genuinely empty (that
store prunes to ≤24 h), not a failed read — the script refuses to run at all unless `staticData.
global` is a non-empty object.

**The four immortal entries are repaired.** Each kept its true instant and now carries a parsable
ISO timestamp, so all four expire on schedule instead of never:

| | claimed_at, as written |
|---|---|
| Nik Krivosheia (84885) | `2026-08-11T10:15:03.000Z` |
| Person-67ab0e3f (85307) | `2026-08-11T14:48:19.000Z` |
| Person-6cc71013 (83681) | `2026-08-11T14:49:17.000Z` |
| Person-b70358e4 (83769) | `2026-08-11T14:49:22.000Z` |

Nobody was wrongly suppressed at any point — the bug's first bite would have been ~2026-11-09.

---

## 2. The statics — five, and four of them proved LIVE

| # | Assertion | Result |
|---|---|---|
| 1 | concurrent executions, distinct keys → all persist | **LIVE PASS** — 6 overlapping executions → **6 rows** |
| 2 | same key twice → *already handled* | **LIVE PASS** — 4 overlapping executions on one key → **1 row** |
| 3 | redeploy → state survives | **LIVE PASS** — claim read back byte-identical across a PUT |
| 4 | table echoes input → fail open, never *already handled* | offline PASS |
| 5 | non-parsable `claimed_at` → UNKNOWN, reported, never retained | offline PASS |

37 offline assertions in `WF_SHARED/test_claims.js`, all green. Three of them run against **two
storage models side by side**, so the suite states what the port buys rather than only that the new
code works: replaying the 28 August commit order, **staticData keeps 1 of 4 claims and the table
keeps 4 of 4.**

The live half was run on a throwaway probe with the *same node configuration*, then deleted.

## 3. The prune

First live run: **63 rows deleted, 0 failed, 0 remaining.** 62 `wf1_seen` + 1 legacy `dedupe`,
all past 7 days. The **45 alert rows were correctly retained** under 90-day retention — which is
the whole point, and is what the port had silently dropped.

The read is bounded (`claimed_at < now-7d`): it looked at **108 rows, not the 670 in the table.**

**Its refusal is intact and is not softened.** If any row it reads has a `claimed_at` that will not
parse, the run throws and deletes nothing, naming the offending key. It also retains — loudly —
any family it does not have a retention for, rather than guessing.

Schedule: 06:35 daily. Manual: `POST /webhook/{{WEBHOOK_DNC_CLAIMS_PRUNE}}`.

---

## 4. What was actually built

**WF-2, +14 nodes.** More than the ~9 I estimated in the artifact; the extra came from the bounce
store needing its own read/verdict/claim rather than sharing the dedupe lookup.

- **Bounce memory.** The old `Normalize` is now `Normalize Parse`; a new node named `Normalize`
  applies the memory verdict from the table. Every `$('Normalize')` reference downstream still
  resolves, to the final node. The split patches exactly five published fields — `event`,
  `event_alias`, `__is_bounce`, `__bounce_signal`, `__bounce_duplicate` — because the memory does
  not merely tag the item, it **reclassifies the event** and reroutes the whole execution.
- **Dedupe.** `Dedupe Key` lifts the key arithmetic out so the lookup can run first; one
  `anyCondition` read fetches all three key shapes at once (event claim, first-SENT memo, and the
  `F|` forward claim that `Body SL Forward Email` used to read separately).
- **Ten claim terminals, one claim node.** All ten write the same key under their own guard, so
  they publish `__wf2_claim` and share `IF Claim Ready → DT Claim Dedupe` instead of getting ten
  dataTable nodes each.
- **Alert registry.** `Alert Key` + `DT Alert Get` before `First Reply Gate`; `IF Alert Delivered
  → DT Alert Claim` after `Classify Body`, so the claim still happens only on `ok === true`.

**WF-1, +5 nodes.** `Lead Create Gate[0] → Lead Claim Key → DT Lead Claim Get → Lead Claim Gate →
IF Lead Claimed`, whose true output goes to the existing-lead path and whose false output creates.
`DT Lead Claim Set` claims after `Create Lead` returns.

**Every staticData write is still in place as the rollback copy.** Only the *decisions* moved. When
the table cannot be read, each gate falls back to the staticData answer rather than losing the
protection — so a table outage degrades to today's behaviour instead of to no behaviour.

---

## 5. What is NOT proven yet, plainly

**The ported paths have not executed in production.** WF-2 has had no traffic since 2026-09-01
18:01, and WF-1 last ran at 12:09, before the deploy. So the live evidence above proves the
*mechanism* under real concurrency; it does not yet prove *these two graphs* under real events.

**I did not inject synthetic traffic to manufacture the proof.** WF-2's CONFIG is
`WRITE_MODE: live`, so a fabricated webhook would create real Pipedrive activities, real Slack
posts and possibly a real forward. That is your call to make, not mine. If you want the in-WF-2
overlap proved today rather than on the next organic burst, say so and I will run a controlled
pair of events and clean up after them.

What I can say without qualification: the graph is coherent (every connection resolves, no
duplicate node names or ids), all 19 touched Code nodes pass a syntax check, and nothing in the
estate has errored since the deploy.

---

## 6. `wf2_bounce_counter` — chased, and it is not what it looked like

The store is absent because **the node has never run**, not because it is broken. `Bounce Counter`
is reachable (`IF Bounce Duplicate → Bounce Counter → B Person Search`), its code is correct, and
it is **already bounded** — 30 days of `by_day` buckets, oldest dropped first.

Its feeder is the *deduplicated bounce* path. The one bounce in the retained window — Kyle
Strougo, 28 August — went down the **reply** path instead, which is the bug the BOUNCE LOCK was
added to stop. So the counter's emptiness is consistent with "no bounce has reached the bounce
branch since the counter was added", and there is nothing to fix in it.

**This also caught a defect in my own new linter** (§7).

---

## 7. The linter rule — and the false positive it nearly recorded as fact

New: `WF_LINTER/static_retention_bound.js` — *every state store has a retention bound.* It covers
both kinds: staticData collections (bounded = a rotation in the same workflow) and data tables
(bounded = **some** workflow in the estate deletes from it, since the prune lives separately).

It is not a vacuous pass — remove the one declared acceptance and it **fails**.

Two categories are declared rather than silently ignored:

- **Permanent by design:** the DNC ledger `UOgKwlGsL28lX61O`. A do-not-contact record must outlive
  everything; expiring one would re-open contact with someone who asked us to stop.
- **Accepted unbounded (your call, recorded):** `__event_aliases_seen`. One key per unseen
  Smartlead event name; worst case a duplicate ops warning.

**The false positive.** The first version flagged `by_inbox` and `by_domain` as unbounded stores.
They are neither unbounded nor stores — they are locals inside the day bucket that the 30-day
rotation already deletes. Its rule was "anything matching `<x>.<key>[…] =`", which is a shape, not
a fact. I had already written both into the accepted list with reasons before chasing the bounce
counter showed me they were fiction. The detector now only counts keys hung off a variable bound
to `$getWorkflowStaticData(...)`.

*A static that invents stores is worse than no static* — the accepted list is where invented
findings would have become permanent.

(The same file also hung the linter once, from a regex assembled by string concatenation with
escaped backslashes. It uses regex literals now.)

---

## 8. Rollback

Restore from `backups/WF-2__pre_state_port.json`, `backups/WF-1__pre_state_port.json`,
`backups/WF-2R__pre_throttle.json`. The staticData stores were never touched and remain
authoritative for the old code; the 105 migrated rows go inert and age out under the prune.
`dnc_claims_prune` can be deactivated on its own without touching either receiver.
