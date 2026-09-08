# Auditor spot-check #2 — FINAL. Five assertions against WF-2 `1f3410dd`: **ALL GREEN**

Read-only. Swept 2026-08-11T13:13Z–13:20Z. Target `versionId 1f3410dd-c3e3-4d74-bb61-cfacb44056e5`,
149 nodes, active, deployed 13:06:03.921Z.

| # | assertion | verdict | evidence |
|---|---|---|---|
| 1 | `Dedupe` no longer claims | **GREEN** | no `if (!duplicate) store.wf2_seen[key]=` in the node; only the `S\|campaign\|lead` sequence memo remains. 8 claim terminals found by grepping every node: `Claim SENT/Bounce/Unsub/Nurture` + `Reply CRM Done`, `NoOp Nurture SENT`, `NoOp Repeat SENT`, `NoOp Lead Exists` |
| 2 | failed run leaves no key → replayable | **GREEN (structural)** | no claim write on any pre-terminal path; strengthened by the new `__no_lead === false` guard. Not exercised by a live crash — stated, not banked |
| 3 | successful run claims → replay suppressed | **GREEN (live)** | exec 15243: `REPLIED\|3686187\|4306240392\|1786453747000` claimed at 13:09:54 = the execution's **stop** time. Yesterday's 3× replay-suppression evidence stands |
| 4 | Marine's key released | **GREEN** | `REPLIED\|3686184\|4214180591\|1786375820000` absent from `wf2_seen` (15 rows, verified 13:17Z) |
| 5 | alert regression | **GREEN (live, wire-confirmed)** | see below |
| + | `ce1a8355` / `\|\| -1` / pagination fold-in | **GREEN** | `__leads_page_saturated: false`, `__lead_read_errors: 0`, all four candidate reads succeeded |

## Assertion 5, in full — the first n8n post ever to reach the team channel

exec **15243**, `13:09:39.779Z → 13:09:54.330Z`, success:

```
Lead Resolve      __lead_id 72ec85c0-…  __lead_how campaign_field  __no_lead false
                  __person_id 85506  __leads_page_saturated false  __lead_read_errors 0
First Reply Gate  __should_alert true  __alert_reason first_reply  __alert_key 72ec85c0-…
Body Reply Alert  executed, no error          <-- the node that killed Marine's reply
Reply Alert       ok:true  channel C07LTD8UT70  ts 1786453783.613469
SL Forward Email  ok:true      Lead Labels Union success:true      Reply Activity success:true
```

**Confirmed on the Slack wire independently of n8n** (Slack API read of C07LTD8UT70): the message is
present, 2026-08-11 16:09:43 IDT = 13:09:43Z, ts `1786453783.613469`.
Permalink matches yours: `…/archives/C07LTD8UT70/p1786453783613469`.

This closes **Phase-2 Finding 1** (the team channel had received zero reply notifications since
2026-08-05T11:14:25Z and no n8n post ever). It is now non-zero, on the wire, with a permalink.

Your off-by-one diagnosis is confirmed and is better than either hypothesis I offered: the
`completeExpression` evaluated with `$pageCount` already incremented queried 3 of 4 candidates and
skipped **85506 — the one holding the lead**. That is exactly what my `__leads_page_saturated: true`
signal on exec 15239 was reporting. Agreed that statics could not have caught it: the defect lived in
the pagination expression, which has no existence outside runtime. Worth writing down as a class —
**expression-only logic is invisible to body-level statics**, the same shape as the `alert_text`
outage.

---

## NEW FINDING (mine, not one of the five) — the no-lead guard opened a duplicate-forward path

**Severity: high. Does not invalidate P0-1b. Should be closed before the night queue runs unattended.**

The `Reply CRM Done` guard is correct about what it fixes and wrong about what absorbs the fallout:

```js
// If Lead Resolve cannot be read at all we do NOT claim: an unnecessary replay is recoverable
// (dedupe and existence checks absorb it), a wrongly-claimed event is not.
```

The CRM writes are absorbed — label union is idempotent, activity creation is gated. **The forward is
not.** From yesterday's audit, the *only* mechanism that prevented a second forward was the dedupe
claim: that is precisely what "dedupe proven 3×" measured — three replays, zero `FORWARD` events on
the Smartlead wire, because the key was claimed.

So: **a reply that resolves no lead now forwards on every WF-2R replay inside the 48 h lookback.**

There is already a live specimen:

```
12:45:47Z  REPLY   fixture 4306240392   exec 15239 -> __no_lead: true
12:46:32Z  FORWARD (sent to rune@janeasystems.com)
key REPLIED|3686187|4306240392|1786452347000  -> RELEASED, and cannot be re-claimed (no lead)
```

WF-2R sweeps one campaign per cycle (hot ring ≈1.7 h). When 3686187 comes round with that reply still
inside lookback, WF-2 will see `__duplicate: false` and forward it again. No duplicate has appeared
yet — the wire shows 2 replies / 2 forwards, 1:1 — so this is pending, not yet realised.

**Population at risk is not an edge case:** persons with no lead at all (project history: ~34 % of Ai4
prospects have no person), plus persons whose lead is **archived** — and archived leads are invisible
to every list read, so the resolver cannot see them by construction.

**Suggested shape:** claim a separate forward key (e.g. `F|<dedupe_key>`) on `SL Forward Email`
`ok:true`, and gate `Gate SL Forward Email` on its absence. A replay then retries the CRM writes it
still owes and never re-sends the forward. That keeps both properties instead of trading one for the
other.

**Immediate item:** the 12:45:47 specimen will duplicate-forward to `rune@` unless its key is claimed
manually or the forward gate lands first.

---

## Answer to your question: **No — I need no more live runs on 72ec85c0. Re-archive it.**

All five assertions are green; assertion 5 was the only one that needed the lead live, and exec 15243
proved it end to end. Nothing else in my queue touches that lead.

One condition, because re-archiving is a one-way door for this fixture: an archived lead makes every
future fixture reply a `__no_lead: true` case, which under the new guard never claims. **After
re-archiving, do not fire further fixture replies until the forward-idempotency gap above is closed** —
each one would become a duplicate-forward generator on WF-2R's sweeps rather than a clean test.

## Sentinel

**Your stated gate is met: my five are green.** The duplicate-forward finding is new and is Nik's call,
not mine — but it is worth one sentence in the decision, because the night queue is exactly the window
in which nobody is watching duplicate forwards leave the building. My recommendation: send the
sentinel, and either close the forward gate before the night queue starts or accept and monitor it
with the specimen above as the canary.

## Still open from my side (unchanged, none blocking the five)

- Smartlead fixture lead `4306240392`: an `UNSUB|3686187|4306240392|1786454160310` claim appeared at
  13:16:06Z, so the unsubscribe looks to have fired — I have not re-read the lead to confirm
  `is_unsubscribed` flipped.
- `zz_probe_cred_verify2` ACTIVE, and `REPLACE_CORE__ErrorHandler_ID` placeholder on the three
  workflows created today (one of them, `dnc_projections_sweep`, ACTIVE with `PD Patch Lead Labels`
  and `SL Unsubscribe`, currently gated by `MODE=dev` + both FIRE flags false).
- Marine's replay has **not** landed yet: her wire still shows only `SENT 15:30:17Z` + `REPLY 15:30:20Z`
  and no `FORWARD`. I will grade it when it appears.
