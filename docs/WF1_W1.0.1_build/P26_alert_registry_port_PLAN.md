# #26 — Port the alert-delivery registry off staticData (P0-1b port)

**Status: read-only. Nothing deployed, nothing migrated. §9f.2 pre-post at the bottom.**

## 1. The class sweep — WF-1 is where it surfaced, not the scope

Every workflow in the estate that touches `$getWorkflowStaticData`, with **measured** concurrency
rather than assumed exposure. "Can it run in parallel" is a property of the trigger; "does it" is a
property of the traffic, and only the second one loses data.

| workflow | trigger | stores | same-second groups | max/sec | true overlaps | verdict |
|---|---|---|---|---|---|---|
| **WF-1 HeyReach Receiver** | webhook | `__alerted_v1`, `seen` | **28** | **5** | **54** | **PORT — 15% of runs share a second** |
| **WF-2 Smartlead Receiver** | webhook | `__alert_delivered`, `wf2_seen`, `wf2_bounce_seen`, `wf2_bounce_counter`, `__auth_*`, `__event_aliases_seen` | 0 | 1 | **1** | **PORT — exposure is real but rare** |
| dnc_escalation_detector | webhook-ish | `hitsToday`, `runsToday`, `statDate` | 0 | 1 | 0 | no exposure |
| dnc_projections_sweep | — | `lastSmartleadSnapshot` | 0 | 1 | 0 | no exposure (0 executions retained) |
| WF-2S SENT Reconciler | schedule | `__sent_seen_v2`, `__resume_sent`, `__tick_sent` | 0 | 1 | 0 | serial |
| WF-2R REPLY Reconciler | schedule | `__reply_seen_v1`, `__resume`, `__tick` | 0 | 1 | 0 | serial |
| WF-ERR | errorTrigger | `__burst` | — | — | 0 | serial |
| dnc_i04_daily_summary · dnc_pre_add_gate_monitor · dnc_s3_creation_watcher · dnc_wf_linter · dnc_i04_weekly | schedule | counters/watermarks | 0 | 1 | 0 | serial |

**Scope: WF-1 and WF-2 only.** Everything else is schedule-driven and serialised; porting them would
be motion without risk reduction. If a scheduled job ever overruns its interval it joins this list —
`true_overlaps` is the number to watch, and it is 0 for all of them today.

**WF-1's own `seen` store is already dual-written** to the claims table (`DT Claim Seen`,
`family: wf1_seen`). This port does for `__alerted_v1` what was already done for `seen`.

## 2. What actually broke (recap, proven)

```
20:50:27  exec 41222  Carla    first_alert  POSTED   read size 47
20:50:27  exec 41223  P85787   first_alert  POSTED   read size 47
20:50:27  exec 41224  P85951   already_delivered     read size 47
next reading (Sep 2 02:24)                            size 48   <-- should be 49
```
Two deliveries, one surviving write. `$getWorkflowStaticData` persists the **whole object** at
execution end; last writer wins. Carla's key was re-added 27 hours later by her second alert.

Across the retained window: 29 delivered alerts, 29 `first_alert` decisions, **1 duplicated key** —
about 3%, i.e. one duplicate every few days, indefinitely.

## 3. The port

**Target: the existing claims table `euyostwJYfJefItC`.** dataTable creation is UI-only — there is
no REST endpoint — so the alert registry shares the table and is separated by `family`, exactly as
`wf1_seen` already is.

Row shape (unchanged from the proven `DT Claim Seen` mapping):
```
claim_key   P85942|572715          <- key form already correct, unchanged
family      wf1_alert              <- new family, isolates it from wf1_seen
workflow    WF-1
event_time  <reply timestamp>
claimed_at  <ISO now>
evidence    exec:<id> alert-delivered
```

**Node changes — 4 added, 2 modified:**

| node | change |
|---|---|
| `M7 Alert Key` *(new, code)* | computes `__alert_key` + `__legacy_key` + `__manual_thread`, lifted verbatim out of the gate |
| `M7 DT Alert Get` *(new, dataTable get)* | `matchType: anyCondition`, two `eq` conditions — current key **and** legacy L-form. One query, not two-plus-Merge: an append Merge is not a barrier (9c/dataTable notes) |
| `M7 Alert Gate` *(modified)* | decides from the dataTable result instead of `sd.__alerted_v1`; keeps `manual_conversation`, `no_identity`, legacy-key honouring |
| `M7 IF Alert Delivered` *(new, IF)* | `ok === true && channel === C07LTD8UT70` — the delivery test moved out of Labels Compute, unchanged in meaning |
| `M7 DT Alert Claim` *(new, dataTable upsert)* | writes the row **only** after proven delivery |
| `M7 Labels Compute` *(modified)* | the staticData write block is **removed** — no dual store |

**Ordering is the whole point:** the claim is written *after* the Slack post succeeds, never at
decision time. A failed post must not burn the lead's only alert — that rule predates this port and
survives it.

**Fail direction on a dataTable hiccup:** `M7 DT Alert Get` is `onError: continueRegularOutput`, and
an unreadable registry **fails OPEN** (alerts, reason `dt_unavailable_fail_open`). That is 9b.0f:
a duplicate is noise, a missed first reply is lost revenue. It is flagged so the telemetry can count
how often it happens.

**No dual-write, no transition period.** Keeping both stores would recreate the two-store problem
(9b.0e): "not in staticData" and "not in the table" would be different facts. Migration then cutover.

## 4. Migration — §9f.2 PRE-POST

**What will change:** insert the existing delivery registry into the claims table as `wf1_alert`
rows. No workflow behaviour changes until the node edit deploys in the same window.

**How many records:** **53 keys** currently in `__alerted_v1` (40 `L`-form legacy, 13 `P`-form).

**Why it must happen before the gate edit:** if the table is empty when the new gate goes live,
*every* lead reads as `first_alert` and the next reply to any of 53 people re-announces. Migration
first, deploy second, in one window.

**Example rows (old → new):**
```
staticData  "P85942|572715": "2026-09-02T23:55:27.155Z"
  -> row    claim_key=P85942|572715   family=wf1_alert  claimed_at=2026-09-02T23:55:27.155Z
             evidence=migrated:staticData __alerted_v1

staticData  "L8694ea30-a30b-11f1-8297-bb888c95b31f|572715": "2026-08-31T…"
  -> row    claim_key=L8694ea30-…|572715  family=wf1_alert  (legacy L-form, honoured on read)
```

**Artifact:** `alert_registry_migration.json` — every key, its timestamp, its form.

**Guards:** upsert (re-running adds nothing); read back every key; the staticData copy is left in
place untouched as the rollback, and only removed once the ported gate is wire-proven.

## 5. Statics (class-level, as required)

1. three concurrent executions, **distinct** keys → all three rows persist (the case that lost Carla)
2. same key twice → second reads `already_delivered`
3. legacy `L`-form key present, current `P`-form absent → `already_delivered_legacy_lead_key`
4. dataTable unavailable → `dt_unavailable_fail_open`, alert **sent**
5. manual conversation → `manual_conversation`, no lookup, no claim (regression)
6. Slack post fails → **no claim written**, lead can still alert next time
7. redeploy the workflow → rows survive (staticData would not)

Statics 1 and 7 are the ones staticData cannot pass; they are the point of the exercise.

## 6. Then WF-2

Same shape, `family: wf2_alert`, against `__alert_delivered`. Lower urgency — **1 observed overlap
in 130 executions** versus WF-1's 54 — but the same defect, and it is cheaper to do while the
pattern is fresh than to rediscover it from a duplicate in Melisa's channel.

## 7. Linter

New rule to add to `dnc_wf_linter`: **flag any webhook-triggered workflow that writes
`$getWorkflowStaticData`.** That is the whole class, stated as a check rather than a memory.

---
**AWAITING: word on the 53-key migration.** Nothing runs until then.
