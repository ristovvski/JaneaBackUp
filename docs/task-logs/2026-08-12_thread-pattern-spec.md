# SPEC — thread pattern for error alerts. Paper only; build with fresh eyes.

Nik's requirement: the ops channel gets **ONE summary line per incident window**; the full
WHAT/IMPACT/ACTION per event goes into the **thread** under it. Same node, same cause, within 15
minutes = one parent + N thread replies. In his words: *"wanna see tech details → click to expand."*

Target shape:

```
🔴 WF-2 Person Search failed · 3 SENT events (kiewit, pacificlife, mighty.capital) · recoverable via WF-2S
   └ thread reply 1: WHAT / IMPACT / ACTION for kiewit + execution link
   └ thread reply 2: … pacificlife
   └ thread reply 3: … mighty.capital
```

## Why this is not a text change

Slack threading needs the **parent message's `ts`**, returned only when the parent is posted. So the
second event in a window must find the first one's `ts` and post *under* it. That requires shared
state keyed by the incident window — and state shared between concurrent executions is exactly what
this estate has spent two days getting wrong.

**The parent-ts store MUST be the atomic claims table, never staticData.** Under the staticData
race, two concurrent failures would each read "no parent yet", each post a parent, and the second
would clobber the first's ts — producing the duplicate parents the pattern exists to prevent, plus
orphaned replies. This is the same last-writer-wins that lost 113 claims, wearing a cosmetic
disguise. **Therefore: build this AFTER the atomic table exists.** It is a consumer of that work,
not a parallel track.

## Incident key

```
incident_key = <workflow> | <failing node> | <cause class> | <floor(now / 15min)>
```

* **cause class**, not the raw message — "429 rate limit", "validation failed", "timeout". Raw
  messages carry ids and would split one incident into N singletons.
* the **15-minute bucket floor** rather than "within 15 minutes of the first", so two executions
  cannot disagree about which window they are in. A sliding window needs consensus; a floor needs
  none.

Bucket edges split a genuine burst occasionally. Accepted: the alternative is a sliding window that
requires the exact agreement the race denies us.

## Flow

1. Alert path computes `incident_key`.
2. **Atomic upsert** into the claims table: `INSERT … ON CONFLICT DO NOTHING`, returning whether
   this execution won.
3. **Winner** → post the parent summary → write its `ts` back against the key.
4. **Loser** → read the key's `ts` → post as `thread_ts`.
5. Loser finds no `ts` yet (winner still in flight) → **short bounded retry, then post standalone.**
   A visible orphan beats a swallowed alert; §9b.0f says alert paths fail OPEN.

## Parent summary content

The parent must be readable *without* opening the thread — it is what Nik sees at a glance:

```
🔴 <workflow> <node> failed · N <event type> events (<up to 3 identities>) · <recoverability>
```

`recoverability` is the sentence that decides whether he acts tonight: "recoverable via WF-2S",
"replayable — unclaimed", or "**NOT self-recovering — needs key release**". Tonight's 32 would have
read the third, and that is exactly the line whose absence made them look fine.

## Counting problem, stated honestly

The parent says "3 events" but is posted when the *first* arrives. Options:

* **A. Count-up edits** — parent is edited as each event arrives (`chat.update`). Accurate, needs
  the parent ts (already held) plus an update call per event.
* **B. Deferred parent** — hold events for the window, post one complete summary at the end. Most
  accurate, worst latency: nobody hears about a live incident for up to 15 minutes. **Rejected** —
  an incident alert that arrives late is the failure mode we started from.
* **C. Parent says "1+"** and the thread carries the truth. Cheapest, least useful at a glance.

**Recommendation: A.** The parent stays accurate and immediate, and the edit path reuses the ts we
already store.

## What this does NOT fix

Alert *volume* from a single cause is reduced; it does not reduce **causes**. Tonight the ops channel
was unreadable because 32 executions failed, not because each posted separately. Threading makes an
incident legible — §0 makes it not happen. This is presentation, and it should be built after the
class-elimination work, not instead of it.

## Build order

1. atomic claims table exists (tomorrow's item 1)
2. incident_key + upsert + parent/child routing on **WF-2's** ops warns first — highest volume,
   already migrated
3. WF-1 once its table lands
4. count-up edits last, after parent/child is proven

## Statics before deploy

1. two concurrent failures, same key → exactly ONE parent, one threaded reply
2. two failures, different cause classes → two parents
3. bucket boundary crossed → two parents (accepted behaviour, asserted so it is not a surprise)
4. winner's ts missing when the loser reads → standalone post, never a swallow
5. parent text is readable alone — assert the recoverability clause is present
6. Slack returns ok:false on the parent → loser must NOT thread onto a ts that does not exist
