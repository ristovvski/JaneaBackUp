# Auditor: WF-1 staticData race — measured. Plus a retraction on `__alerted_v1`.

Read-only. 2026-08-12. Evidence: `scratchpad/k1_wf1_race.json`, `k1.log`.
Feeds tomorrow's WF-1 build (P0-1b port · spacing · WF-1R).

---

## RETRACTION — the `__alerted_v1` 50→3 drop was NOT race loss

I attributed it to the race. **It was the sanctioned rebuild** (11:24Z, Nik's ruling: alerts that went
only to the ops channel count as undelivered, so those leads were deliberately un-muted). Verified
rather than accepted — the three survivors are exactly the three alerting executions since the reset,
and all three were delivered **to the team channel**:

| registry key | exec | alert channel | ok | ts |
|---|---|---|---|---|
| `L4d245410-…\|512995` @ 15:38:56.460Z | 15414 (15:38:53.815Z) | **C07LTD8UT70 (TEAM)** | true | 1786462736.358699 |
| `L909b8aa0-…\|512995` @ 00:00:26.124Z | 15754 (00:00:23.408Z) | **C07LTD8UT70 (TEAM)** | true | 1786492826.021379 |
| `L653919e0-…\|512995` @ 14:51:38.247Z | 15938 (14:51:35.523Z) | **C07LTD8UT70 (TEAM)** | true | 1786546298.145509 |

Three registry entries, three alerting executions, each entry stamped ~3s after its execution start,
each alert delivered to the team channel with `ok:true`. **3-for-3 confirmed.** The retained entries are
exactly the delivered ones; the removed ones are the ops-only ones. That is a selective, principled
rebuild, not a wipe — and my "clean-cut shape" reading was wrong about the cause.

I also cleared the alternative before blaming the race, and should have kept going: the 90-day prune is
correct (`const t = Date.parse(reg[k])` on ISO values, deletes only at >90 days), so 9-day-old entries
were never at risk. Having eliminated the prune I jumped to the race instead of asking whether a human
had done it deliberately. **A registry that shrinks is not evidence of a bug until you have ruled out an
operator.**

## One half survives fully, one half survives with a caveat — the distinction matters

**Survives untouched: the 19.2 % structural overlap and the 15/15 correlation.** These are measured from
execution timestamps and store contents, and the retraction does not touch them.

**Survives as reasoning, not as a measured instance: the sparse-write asymmetry.** I inferred that
asymmetry *from* the 50→3 observation. With that observation reassigned to the rebuild, **WF-1 no longer
provides an observed instance of it.** The argument still holds on its own terms —

> a store written once per *event* partially self-heals, because the next execution re-adds its own key;
> a store written once per *lead ever* cannot, because nothing ever re-writes a lost entry

— and it is still supported by WF-2, where `__alert_delivered` sat at **0 rows** while `wf2_seen` kept
accumulating. But it is now a mechanism argument plus WF-2 evidence, **not** a WF-1 measurement. Saying
it "survives untouched" would overstate what I can show. The design conclusion is unchanged; the
evidential weight behind it is one instance lighter.

## The measurement that stands

| | |
|---|---|
| executions retained | 1,440 |
| **overlapping a later finisher (exposed population)** | **276 — 19.2 %** |
| duration | median **3.0 s**, p90 3.6 s, max 63.6 s |
| testable inside the 48 h `seen` TTL | 42 |
| **claims lost** | **15** |
| **of those, overlapped a later finisher** | **15 / 15 (100 %)** |
| claims lost with **no** overlap | **0** |

The two HeyReach bursts, unedited:

```
15211 F  15212 F  15213 F  15214 F  15215 F  15216 TRUE  15217 F  15218 F    8 execs in 1.3 s
15220 F  15221 F  15222 F  15223 F  15224 F  15225 F     15226 F  15227 TRUE 8 execs in 1.3 s
```

7 of 8 lost per burst; in each the sole survivor is the one execution with no later-finishing overlap.
Every isolated execution (`message_sent`, minutes apart) kept its claim. Same shape as WF-2's 42/42.

**Scope caveat, stated rather than buried:** the survival test is only valid inside the 48 h `seen` TTL
(42 executions) — older keys are legitimately rotated and would read as false losses. The 19.2 % figure
is the exposure measure and is computed across all 1,440.

## Implications for tomorrow's build

1. **Do not port the WF-2 claim design onto staticData.** WF-1's exposure is 19.2 % at today's low
   volume; during Ai4 it ran 165 executions/day.
2. **Spacing cannot fix inbound.** Median execution is 3.0 s, so any two events inside ~3 s collide —
   and HeyReach delivered 8 accepts in 1.3 s, twice in one minute. We do not control when their webhook
   fires. Spacing is a mitigation for *our* replay bursts (WF-2S), not for a provider's delivery.
3. **The structural fixes are a concurrency guard (one execution in flight, queue the rest) or an
   atomic-upsert store** — which is what the DNC chunk cursor already does in a data table.
4. **WF-1R inherits the hazard** if its claim store is staticData.
5. **Prefer per-event keys over per-entity keys where the semantics allow it** — an event-keyed store
   degrades gracefully under this failure mode, an entity-keyed registry does not. That is the design
   consequence of the asymmetry above, and it holds whether or not WF-1 supplied an instance of it.
