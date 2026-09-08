# WF-1R SPEC — re-cut against §0. Supersedes the 2026-08-11 draft.

**Paper only.** Feeds tomorrow's build order: atomic table → P0-1b port onto it → WF-1R inheriting.

---

## What changed, and why the earlier draft was wrong

The 2026-08-11 draft recommended: *"do NOT build WF-1R immediately; add a daily gap line, measure
for a week, build only if it reports misses."* Measure-before-building was defensible engineering
and it is **superseded by §0**:

> even external failures must never LOSE events — only delay them, with reconcilers draining the
> backlog when the provider recovers.

That makes a reconciler a **property of the design, not a response to a measured loss rate**. If
WF-1 has no way to re-detect what it dropped, then a HeyReach outage — or any crash during one —
loses events permanently, and no measurement is needed to know that. The gap line measures *how
often* we are hurt; §0 says the exposure itself is unacceptable.

**End state is mandatory. Only the timing is negotiable.** The gap line survives, demoted from
decision-gate to instrumentation.

## The constraint that decides the shape

**WF-1 cannot be fixed the way WF-2 was.** WF-2's race closed because we own its burst — `Replay
Into WF-2` is our node and now spaces at 10s. HeyReach delivers ~8 webhooks in 1.3s and **inbound
cadence is not ours to control** (auditor: 19.2% of executions overlap a later finisher; my longer
window: 30%). Spacing is simply unavailable as a mitigation.

So for WF-1 the atomic store is not the better option, it is the only one — which is why tomorrow's
order puts the table first and the P0-1b port second, landing **on** the table rather than on
staticData.

## Non-negotiables inherited by WF-1R

1. **Claim store = the atomic table from day one.** Never staticData. WF-1R must not be born with
   the defect its sibling is being migrated out of.
2. **Producer store included from day one.** §9b.0e: "unclaimed" governs safety, the producer store
   governs *liveness*. WF-2S's `__sent_seen_v2` stranded 32 events because only the consumer side
   was fixed. WF-1R's own seen-store lives in the same table, or the trap is rebuilt.
3. **Replays SPACED and CHUNKED.** Spacing (≥ one execution duration) defeats the race and the rate
   limit; chunking defeats the OOM. These are independent failures — the DNC sweep's monolithic
   2,264-item execution died of memory with no rate limit involved. A spaced-but-monolithic replayer
   is still an OOM vector.
4. **Claim on replay SUCCESS**, never on having sent the replay.
5. **The gap check reads the PROVIDER.** HeyReach `GetConversationsV2` is proven readable (346
   conversations, 1,221 messages). Our executions prove what we did, never what arrived.
6. **Every blindness flag ships with a consumer** (§9b.0b).

## Design

**Trigger:** schedule, 15 min, matching WF-2R.

**Detection:** `GetConversationsV2`, paginated, filtered to inbound messages
(`sender == "CORRESPONDENT"`) with `createdAt` inside `lookback_minutes`. For each, the claim key is
the conversation id + message `createdAt` — HeyReach exposes no per-message id, and that pair is
stable.

**Reconcile:** key present in the claims table ⇒ already processed, skip. Absent ⇒ replay into
WF-1's webhook.

**Replay:** chunked at `max_per_run` (start 10, lower than WF-2S's 20 given the OOM history), spaced
`replay_interval_ms` ≥ 10s, claim written **after** WF-1 accepts.

**lookback_minutes:** 2880 (48h), matching WF-2R, and it must exceed the longest plausible outage.
The validator that WF-2R carries — asserting lookback exceeds a recorded worst case — comes along.

## Sequencing recommendation

Build WF-1R **after** the table and the P0-1b port, not before. Not because its need is unproven —
§0 settles that — but because a reconciler whose claim store is still racy would strand events on
its first bad day, which is precisely tonight's lesson. The dependency is technical, not
evidentiary.

**Interim, from the moment the port lands:** the WF-1H gap line ships as instrumentation. It answers
"is anything being dropped today" while WF-1R is built, and afterwards it becomes WF-1R's own
verification — a gap line that stays at zero is how you know the reconciler works.

## §0 scorecard for WF-1, after the full package

| internal class | after table + port + WF-1R |
|---|---|
| staticData lost-update race | **closed** — atomic upsert, no read-modify-write |
| claim-at-decision-time | **closed** — P0-1b port |
| two-store liveness gap | **closed** — producer store in the same table |
| no reconciler (event loss on crash/outage) | **closed** — WF-1R |
| burst-induced OOM | **closed** — chunked replay |
| blindness flags without consumers | open until the gap line has a digest consumer |

Target is zero. This package takes WF-1 from five open classes to one.

## Open question for Nik — unchanged from the first draft

Whether LinkedIn replies are ever expected in volume. The design above assumes low single digits per
day. A new event campaign could change that overnight, and it would raise `max_per_run` and lower
`lookback_minutes` rather than change the shape.
