# 2026-08-28 — WF-1: personal chats stop announcing (campaign-origin gate)

Live: **WF-1 `120dd7d1`**, 112 nodes, active.
Melisa, verbatim: *"We shouldn't get notifications about personal chats (lead not from campaigns)"*.

## THE TWO REPORTS WERE BOTH MISDIAGNOSED IN THE ENVELOPE — and identically

Person-b0fb1597 (26 Aug) and Person-7cb57cf4 (27 Aug) were each described as a **matcher miss** that
**created a new lead**. Neither was true:

| | Ken | Josh |
|---|---|---|
| `M7 Person Search URL` | items=1 → **85761** | items=1 → **85519** |
| existing lead | created 12 Aug **by Noah** | person resolves under name / slug / URL |
| what fired | reply alert | reply alert |
| `campaign` | `null` | `null` |
| alert key | `…|nocamp` | `…|nocamp` |

The 14-Aug slug fix works. `Open lead` is the **hyperlink label** in every WF-1 reply alert — not a
claim that anything was created. Nothing was created; labels went 0→2 correctly and the reply
activity was written.

**The real class: replies inside MANUAL HeyReach inbox threads** — an exec's own conversations,
which carry no campaign. WF-1 already labelled them (`|nocamp` in the key) and alerted anyway.

## THE NUMBER THAT JUSTIFIED THE FIX

```
#lead-processing, last 14 days: 11 alerts delivered
   campaign-sourced   :  6
   MANUAL (no campaign):  5   = 45% of the channel
      Person-7cb57cf4 · Person-c1b92fbb · Person-9979a87c · Person-b0fb1597 · Person-8d8b92ff
```

## WHY I DECLINED THE SPECIFIED "known-person gate"

The envelope asked for: *person resolves to existing pid → no alert*. **All 6 legitimate campaign
alerts also resolve a person** — resolving one is how the alert gets its lead link at all. That gate
suppresses **11 of 11** and deletes the feature. Ken and Josh were both *known*; being known is not
what made them noise. Campaign origin is the property that separates the classes, and it is
sufficient for both reported cases. Reported before building rather than shipping a guard that would
have silenced everything.

## THE CHANGE — one condition, alert branch only

```js
const __manual_thread = !(n.campaign && (n.campaign.id ?? n.campaign.name));
if (__manual_thread) { should = false; reason = 'manual_conversation'; }
```
Placed **before** the `!key` fail-open on purpose: that fail-open protects campaign replies from
being lost and must not resurrect a personal chat that also lacks identity.

**Labels and the reply activity are untouched** — they hang off `M7 Labels Compute → M7 Lead Patch`
and `M7 Reply Activity`. A personal chat is still recorded silently. The system logs; it stops
announcing.

## VERIFICATION

Statics 5/5, then **wire proof against six REAL executions** replayed through the deployed body:

```
campaign:Person-090ff619        alert -> alert          (unchanged)
campaign:Person-1183eeff    alert -> alert          (unchanged)
campaign:Person-ec2fedcf     alert -> alert          (unchanged)
manual:Person-7cb57cf4      alert -> manual_conversation
manual:Person-9979a87c      alert -> manual_conversation
manual:Person-c1b92fbb       alert -> manual_conversation
```

## PROCESS NOTE — this was the second hit of an open item

Ken was diagnosed on 26 Aug and **not deployed**: I parked it on a product question (silence vs
route quietly) and waited. Josh arrived the next day through the same hole. **Parking a fix on an
optional refinement is a decision to keep shipping the bug.** The uncontroversial half — stop
posting personal chats to the campaign channel — needed no decision at all.

## OPEN

* Where manual-thread replies should surface instead (#niks-channel / telemetry / nowhere) — still
  Melisa's call, but no longer blocking, since they are silent now.
* Weekly per-exec "connections without CRM person" list stays as planned; that class is real,
  neither Ken nor Josh was a member of it.
