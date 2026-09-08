# SPEC — atomic claims table. Tomorrow's build item 1.

**Paper.** Consolidates every ruling made tonight so the build does not have to re-derive them.
Scope: **WF-1's two stores first** (`seen`, `__alerted_v1`). WF-2's stores migrate next week.

---

## Why WF-1 first, and why an atomic store is the only option there

WF-2's race was closed by spacing because **we own its burst** — `Replay Into WF-2` is our node.
HeyReach delivers ~8 webhooks in 1.3s and **inbound cadence is not ours to control** (19.2% of
executions overlap a later finisher per the auditor; 30% over a longer window). Spacing is
unavailable to WF-1 as a mitigation, so the atomic store is not the better option — it is the only
one.

Sharpened by the **sparse-write asymmetry**: `seen` is written on *every* event, so a clobbered
entry is rewritten by the next one and self-heals. `__alerted_v1` is written only when an alert
fires — rarely — so a clobber is **permanent**. Same race, same workflow, opposite survivability.

## Schema — `wf_claims`

| column | type | notes |
|---|---|---|
| `claim_key` | string, **UNIQUE** | family-prefixed natural key |
| `family` | string | `dedupe` · `alert` · `forward` · `wf1_seen` |
| `workflow` | string | WF-1 / WF-2 — one table serves both |
| **`event_time`** | datetime | **the provider's instant**, from the dedupe key's trailing epoch-ms |
| **`replay_time`** | datetime, nullable | when *we* replayed it, if this row came from a reconciler |
| `claimed_at` | datetime | when the claim was written — rotation reads this |
| `evidence` | string | execution id + what proved success (`ok:true`, messageId, lead id) |

Prefixes: `D|` dedupe · `A|` alert · `F|` forward · `S|` WF-1 seen.

### The two clocks are separate columns, and both are load-bearing

Tonight's near-miss made this a constraint rather than a nicety. richard.spitz's row would carry:

```
event_time  2026-07-31T18:47:52Z   <- Smartlead actually sent it, 12 days earlier
replay_time 2026-08-12T14:32:38Z   <- WF-2S replayed it; the crashed execution's own timestamp
```

Reading only the second makes a **twelve-day-old backfill look like a fifteen-hour-old loss** — which
is exactly the wrong conclusion I was one command away from acting on. Rules:

* **all lookback and rotation logic reads `event_time`**, never `startedAt`, which n8n leaves NULL on
  some failures (it was null for spitz, and my first age check correctly refused to guess);
* `replay_time` distinguishes a live event from a backfill of an old one;
* a row with `replay_time` set and an `event_time` far in the past is a **backfill**, and must not be
  counted as a recent loss.

## Claim rules

**Write on verified success, never on transport acknowledgement.** WF-2's `Respond to Webhook` is
**node #2** — the 200 is returned before `CONFIG` even runs. Anything treating that 200 as proof
records success for work that has not started.

### Consumer-confirms (folds in the auditor's WF-2S finding — NOT a separate patch)

A producer (WF-2S / WF-2R / WF-1R) may claim a key **only when the same key is present in the
consumer's rows**. Transport ACK is not evidence.

```
producer claims  ⟺  EXISTS (claim_key = 'D|<key>', family = 'dedupe')
```

This kills the class §9b.0e names: safety is governed by the consumer's claim, **liveness by the
producer's** — and tonight the producer marked 32 events done on a 200 that preceded all work, then
one more (spitz) on a replay that crashed. Same root, three symptoms, one fix. Per §0 it is fixed as
a class, in this table, not patched a fourth time.

## Migration order

1. create the table; **dual-write** — staticData stays authoritative
2. run one day; **compare**. Divergence is the race, finally measurable rather than inferred
3. flip reads to the table, keep dual-write
4. stop writing staticData; keep it read-only one more day
5. delete

Each step is independently reversible. Step 2 is the one that must not be skipped — it is the only
point where the race is observable rather than theoretical.

## Explicitly NOT in scope

**Re-seeding WF-1's alert registry.** Dropped by Nik, and the reason must survive in the code or a
future session will helpfully restore it: the 50 → 3 drop was a **deliberate reset at 11:24Z on
2026-08-11**, releasing leads whose alerts only ever reached the ops channel. Those ~47 leads are
*meant* to alert once more into #lead-processing. Re-seeding them would re-mute exactly the people
Melisa is waiting to hear from — a §9b.0d violation reached by honest arithmetic. **The migration
must carry an exclusion list, and this is on it.**

## Statics before deploy

1. two concurrent claims, same key → exactly one row, second is a no-op (the whole point)
2. crashed execution → key **absent**, replay not suppressed
3. producer claim attempted with no consumer row → **refused** (consumer-confirms)
4. rotation reads `event_time`; a row with null `startedAt` still rotates correctly
5. backfill row (old `event_time`, recent `replay_time`) is not counted as a recent loss
6. dual-write parity: table and staticData agree on a quiet cycle
7. the exclusion list is honoured — the 47 released keys are not resurrected

## §0 scorecard after this lands (WF-1)

| internal class | after |
|---|---|
| staticData lost-update race | **closed** |
| claim-at-decision-time | closed by the P0-1b port riding on this |
| two-store liveness gap | **closed** — consumer-confirms |
| transport-ACK-as-success | **closed** |
| no reconciler | open until WF-1R |
| blindness flags without consumers | open (task #23) |
