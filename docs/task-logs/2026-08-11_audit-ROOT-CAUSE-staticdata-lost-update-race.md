# ROOT CAUSE — the missed claim is a staticData lost-update race, and it is losing 76 % of claims

Auditor session, read-only. Diagnosed 2026-08-11T15:0xZ from the three preserved executions plus a
full sweep of WF-2's retained executions. Evidence: `scratchpad/f1_claim_miss.py` /
`f1.log`, `f2_race_rate.py` / `f2.log` / `f2_race_rate.json`.

**It is not paired-item resolution, not the try/catch, and not item-count divergence.** All three of
your candidates are eliminated by the data. The defect is outside the node.

---

## 1. The three candidates are eliminated — the topology is byte-identical

| node | 15344 (worked) | 15345 (**failed**) | 15346 (worked) |
|---|---|---|---|
| runs of every node in the chain | 1 | 1 | 1 |
| `Classify Body` source | `Reply Alert#0` | `Reply Alert#0` | `Reply Alert#0` |
| `Classify Body` items/branch | `[1]` | `[1]` | `[1]` |
| `Classify Body` pairedItem | `{"item": 0}` | `{"item": 0}` | `{"item": 0}` |
| `Reply Alert` items | 1 | 1 | 1 |
| node-level error recorded | none | **none** | none |

`Classify Body` was reached via the **alert route** (`out[0]`) in all three — never the direct
`out[1]` route — with a single item and an intact `pairedItem` chain. `$('Reply Alert').item` had
nothing to be ambiguous about and nothing to throw on. The failing run is indistinguishable from the
working ones inside the workflow.

## 2. What actually differs: the executions overlapped

```
15344   start 14:48:19.814   stop 14:48:27.594     (7.8s)   no overlap        -> claim SURVIVED
15345   start 14:49:17.563   stop 14:49:23.827     (6.3s)   overlapped 15346  -> claim LOST
15346   start 14:49:22.603   stop 14:49:28.294     (5.7s)   last finisher     -> claim SURVIVED
```

**15346 started 1.224 s before 15345 finished.** And the registry size each execution *read* at its
own `First Reply Gate` proves the clobber directly:

```
15344  __alert_registry_size = 1     (fixture)                -> writes, persists 2
15345  __alert_registry_size = 2     (fixture + 15344)        -> writes, persists 3
15346  __alert_registry_size = 2     <-- NOT 3. It never saw 15345's write.
```

15346 loaded staticData at 14:49:22 while 15345 was still in flight, mutated its own stale copy, and
persisted it at 14:49:28 — **overwriting 15345's entire staticData object**, which had been persisted
at 14:49:23.

**The decisive corroboration: 15345 lost BOTH of its staticData writes.** Its dedupe key is also
missing:

```
15344  REPLIED|3686181|4214095893|1786459668000   present in wf2_seen  ✓
15345  REPLIED|3686184|4214186311|1786459724000   ABSENT               ✗
15346  REPLIED|3686193|4214248226|1786459732000   present               ✓
```

A guard on `$('Reply Alert').item.json.ok` could only have suppressed the alert claim. Losing the
dedupe claim too — written by a different node, `Reply CRM Done` — can only mean the whole object was
replaced. n8n persists `$getWorkflowStaticData('global')` **once, at execution end**, as a whole
object. There is no merge and no transaction. Concurrent executions are last-writer-wins.

## 3. Quantified: 42 of 55 claims lost, and 42/42 overlapped a later finisher

Swept every WF-2 execution from 2026-08-10 with start and stop times, took the dedupe key from each,
and checked survival against the live `wf2_seen`:

| | |
|---|---|
| executions that should have claimed | **55** |
| claim **missing** from `wf2_seen` | **42 (76 %)** |
| of those, overlapped a later-finishing execution | **42 of 42 (100 %)** |
| claims that survived *despite* overlap | 2 (`15293`, `15321`) — both the last finisher in their burst |

Perfect correlation, no counter-examples. The losses cluster in three bursts of ~20 concurrent
executions (`15257–15276`, `15292–15311`, `15318–15337`) — WF-2S replay waves, `max_per_run: 20`,
each firing 20 separate webhook calls that each spawn their own WF-2 execution.

Current store contents show the damage: **7 `SENT|` keys and 8 `S|` memos survive out of 84 SENT
executions.**

## 4. Scoping — and a prediction of mine that was wrong

**Exposed** (many concurrent executions writing one store):
- WF-2 `wf2_seen` — the dedupe claim. **This is the P0-1b claim you shipped today**; it is lost under
  burst at 76 %.
- WF-2 `__alert_delivered` — the one-alert-per-lead gate. The reported symptom.
- WF-2 `F|<dedupe_key>` forward-claims — shipped today, same store, same race. The 20 seeded entries
  are safe only until the next burst.

**Not exposed** — and I checked rather than assumed, because I expected the opposite:
- WF-2S `__sent_seen_v2`: **75 rows and growing** (1 → 15 → 75 across today). One execution per
  15-minute cycle means no concurrent writer, so its own claims hold.
- **I predicted the SENT backfill would loop forever on lost claims. It does not.** Zero
  `(campaign, lead)` pairs recur across the 84 SENT executions in the ledger — WF-2S's own store
  prevents the re-push even though WF-2's copy of the claim was clobbered. So the lost `SENT|` keys
  are largely harmless in practice. Stating this plainly because it materially lowers the blast
  radius, and because the inference I published in the previous note would otherwise stand uncorrected.
- WF-2R `__reply_seen_v1`: same single-execution-per-cycle shape, so also safe.

**Unmeasured:** WF-1's `seen` and `__alerted_v1`. WF-1 is webhook-per-event and HeyReach delivers in
bursts (185 `connection_request_sent` in a single day), so it has the same shape as WF-2. Worth the
same test before anyone relies on `__alerted_v1`.

## 5. Consequences, ranked

1. **The one-alert-per-lead rule leaks duplicates** — the reported symptom. A lead whose alert claim
   was clobbered will alert again on its next reply as a "first". The safety argument "we suppress
   only on proven delivery" holds; the *persistence* of that proof does not.
2. **Duplicate forwards.** A lost reply claim makes the event replayable, and WF-2R will replay it.
   This is a second, independent route to the duplicate forward already observed on the wire at
   13:45:56Z (that one came from the `__no_lead` guard). This route needs only two replies finishing
   within one execution duration of each other — three OOOs arrived within 63 s today.
3. Lost `SENT|` claims — benign in practice, see §4.

You are right that it is the exact mirror of today's other lesson, and right that the favourable
outcome here (an OOO not burning a slot) is coincidence. The mechanism would equally have dropped a
Meeting Request's claim.

## 6. Options (yours to choose — I am not implementing)

1. **Serialise WF-2.** A per-workflow concurrency limit of 1, or route the replay bursts through a
   queue. This removes the race outright rather than narrowing it. Cost: latency during bursts, which
   for a reply pipeline is irrelevant.
2. **Space the replays.** WF-2S already has a `requestInterval` concept; spacing its 20 webhook calls
   by more than one execution duration (~8 s) would stop the bursts overlapping at all. Cheap, and it
   also removes the OOM-burst risk already on record.
3. **Move claims off staticData** to a store with atomic upsert — the n8n data tables already in use
   for DNC would do, keyed on the dedupe key. Removes the whole class permanently.
4. **Make the highest-harm action idempotent at the provider.** A deterministic dedupe token on the
   Smartlead forward call means a second forward is rejected regardless of local state. This is the
   only option that survives a total loss of local bookkeeping, and it is the one I would want in
   place before the night queue.

(1) + (4) together would close both the symptom and the worst consequence.

## 7. One thing to re-check afterwards

`__alert_delivered` currently holds 1 entry (the fixture). The three OOO slots were released, so the
registry is no longer evidence of anything — after a fix, the check is a burst of ≥2 concurrent
replies and then confirming **every** one of their keys is present, not just the last finisher's.
