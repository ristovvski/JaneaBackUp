# 2026-09-24 — Аудитор: FULL HEALTH CHECK, last 7 days (2026-09-17 → 2026-09-24T07:50Z)

Read-only, no writes. Per-workflow walks throughout — never the unfiltered `/executions` list.

> **Note on the message I received:** it contained two blocks. The second (this health check) is
> mine. The **first** — "Chrissy's four points, execute": recreate a Pipedrive field, deploy a
> self-healing sweep, run an end-to-end on a live deal — is an **execute/deploy** task in the
> Clay/ICP workstream I have never audited, and it contradicts this block's own "no writes". I have
> not acted on it; it belongs to the executing session. Flagging rather than silently dropping it.

| # | item | verdict | the proving number |
|---|---|---|---|
| 1 | active workflows on schedule | **AMBER** | 17 failures — **16 are `WF-ICP-Score [DEV]`**, 1 production |
| 2 | DNC chain on real traffic | **AMBER** | 30 `reply_dnc`, **20/20 persons carry 686**; Supabase drift is the amber |
| 3 | Supabase 996 errors/hour (22 Sep) | **AMBER — cannot confirm** | pusher **2112/2112 success**, all `201`, 0 error items |
| 4 | alerts sanity | **AMBER** | 15 alerts / 15 people / 0 duplicates; **8 of 15** carry linkedin-as-website |
| 5 | digest | **AMBER** | 8/8 daily, posted `1790222419.400079`; **3 × n/a**, 0 UNREACHABLE |
| 6 | linter | **GREEN** | 3 reported, **all 3 are comment text** → 0 real findings |
| 7 | WF-1 org write guard | **RED** | 12 BioTechX executions reached the org branch, **6 ran `Org Create`** |

---

## Environment finding, before anything else

**The pinned CA bundle stopped verifying every host.** `win_ca_bundle.pem` (generated 2026-08-07)
raised `CERTIFICATE_VERIFY_FAILED` for **n8n, Pipedrive and Smartlead alike**, while all three verify
cleanly against the system trust store. `load_env.ps1` does **not** regenerate it (it loaded 12
variables and left the bundle untouched at its Aug-7 size and mtime) — so my memory note saying it
auto-regenerates is wrong and is corrected here.

I patched `I04_daily_diff/aud.py` to fall back to the system store on a cert-verify failure, with a
one-time stderr warning. Verification is **never disabled** — the fallback context still validates
the chain; a stale pinned bundle is a broken choice, not a safer one. *Any other session's scripts
using that bundle are currently failing the same way.*

## 1. Every active workflow — AMBER

**47 workflows, 25 active** (was 41/21 on 9 Sep). **Zero auto-deactivations.**
Every scheduled workflow met its cadence over 7 days: WF-2R 703 · WF-2S 704 · gate 704 · gate
monitor 711 · s3 watcher 711 · supabase delta pusher 2112 (288/day) · projections sweep 176 (hourly)
· escalation detector 184 (hourly) · digest / linter / claims prune / i04 prune / nightly reconcile /
WF-2H 8 each (daily) · s2 7 (daily, today's 08:00 not yet due at 07:50Z).

**17 failed executions**, and the split matters:

| workflow | n | cause |
|---|---|---|
| `WF-ICP-Score [DEV]` | **16** | 5 × `Could not find the data table: 'icp_audit'` · 4 × FailLoudly `missing request_id/org_id/deal_id` · 3 × `Dedupe B` "Unknown error [line 95]" · 2 × FailLoudly `unknown top-level key "callback_url"` · 1 × `the organization was not written to` · 1 × `POST activity error` |
| `dnc_escalation_detector` | **1** | exec `62959`, 19 Sep 18:00 — **`synchronization error: result count changed during pagination`** |

So **one** production failure in seven days. The other sixteen are the `[DEV]` ICP workflow — which
is the same workstream as the message's first block, and it is failing on a **missing data table
(`icp_audit`)**, exactly the class that bit `dnc_gate_queue` on 26 Aug.

Five active workflows ran zero times — `dnc_archived_responders_import`, `dnc_intent_vs_reality`,
`dnc_s1_responded_to_dnc`, `dnc_s4_retirement_removal`, `dnc_supabase_initial_load`. All are
webhook- or one-shot-triggered, so silence is the expected state, not a miss.

*One caveat on my own method:* my gap detector flagged "59 gaps, worst 10.3h" on WF-1 and similar on
the I-04 receiver and WF-ERR. Those are **event-driven**, so a gap is a quiet period, not a missed
schedule. Ignore that column for anything webhook-triggered.

## 2. DNC chain on real traffic — AMBER (the chain is green; Supabase is not)

**Registry leg — GREEN, zero misses.** 201 UpsertLedger executions in 7 days:
88 `sales_personal_outreach` · 83 `meeting_dnc` · **30 `reply_dnc`**.
Both channels present: **26 email · 4 LinkedIn**. All 30 carry a `pipedrive_person_id`
(20 distinct persons — the rest are repeat upserts on the same people).

**Pipedrive 686 leg — GREEN. 20 of 20 persons carry `DNC Status = 686` today. No misses to name.**

**Supabase leg — AMBER, and it is a treadmill, not a trend.** Nightly reconcile drift:

```
17 Sep 469 · 18 Sep 502 · 19 Sep 501 · 20 Sep 539 · 21 Sep 502 · 22 Sep 505 · 23 Sep 499 · 24 Sep 500
n8n_total 25,858 → 25,946   supabase_total 25,772 → 25,864   extra_in_supabase 0 (every night)
```

The #alerts post each night says *"found drift, **healed from n8n (source of truth)** … healed by
upsert"*. So ~500 rows are healed **every night and ~500 are back the next night**. That is not a
drift converging to zero — it is a recurring re-drift that the nightly job papers over. Supabase
also sits a steady ~82 rows behind n8n. **469 last week → 500 now: marginally worse, and the heal is
not sticking.**

Freshness itself is fine: today's digest reports *"Supabase mirror: 25864 rows · age 5 min ·
reachable"* — inside the 6-minute requirement.

## 3. The 996 errors/hour on 22 Sep — AMBER, I cannot confirm either way

**From every angle visible in n8n the Supabase write path is healthy**, on 22 Sep and today:

* `dnc_supabase_delta_pusher` ran **288 times on 22 Sep** and **2112 times over 7 days — all
  `success`**, no node-level failures at all.
* Sampling six executions from 22 Sep and six from today and reading *inside* them: every one
  returns HTTP **`201`** with **zero** error-shaped items.

**But I cannot see Supabase itself** — there is no `SUPABASE_URL` / key in `.env`, so PostgREST logs
and server-side error counts are outside my reach. A figure of 996/hour did not come from n8n, so
I can name neither the caller nor the path, and I will not call it "resolved" on the strength of a
clean view from the only side I can see. *Worth noting the number's shape: 996 is suspiciously close
to the PostgREST **1000-row response cap** already on record — if the count came from a paginated
read rather than the pusher, that is where I would look first.*

## 4. Alerts sanity — AMBER

**`#lead-processing`, 7 days: 15 alerts, 15 distinct people, zero duplicates, zero "no lead".**

:warning: **linkedin-as-website is present — 8 of 15** carry `Company website:
https://www.linkedin.com/company/…` (Andres Arango, Stefan Lukianov, Person-45978193, Tom Williams,
Person-58dfa505, Person-726ffe11, Person-4cd5e7c8, Person-3fa711ad). The **last** one is 22 Sep
03:28; the newest alert in the window — Person-63a406cb, 23 Sep 07:44 — uses the correct label
**`Company LinkedIn:`** instead. So a fix appears to have landed between those two timestamps, but
there is **exactly one post-fix sample**, which is suggestive, not proof. One more BioTechX alert
will settle it.

**`#alerts`, 7 days: 9 messages, two unresolved themes.** Eight nightly Supabase drift warnings
(item 2) and one `NOT ARMED` (21 Sep 14:30) — `CONFIG.webhook_secret_sha256` is **still null**, so
the secret has been unarmed for at least 16 days; the once-per-day rule is holding (1 post in 7 days,
"+1 more suppressed").

*Observation, not a finding:* 17 failures produced 17 WF-ERR invocations but **no error posts in
`#alerts`** — WF-ERR's posts land in `#niks-channel`, so nothing is lost, but if `#alerts` is meant
to be the single pane for failures, it is not currently receiving them.

## 5. Digest — AMBER

**8/8 days, every one `success`.** Today: exec `68402`, posted `ok: true`, channel `C0BTP6VHP1B`,
ts `1790222419.400079`.

**Zero `UNREACHABLE`.** But **3 × `n/a`**, and they are the same two faults I named on 9 Sep,
15 days unfixed:

* `INTEGRITY sent-without-lead 3917998:n/a 3917997:n/a` — the upstream `PD Campaign Leads` call
  fails with `querystring must have required property 'term'`. A **code** fault, not a permission.
* `no-match n/a` — `conversations.history` on the ops channel, needs `channels:history` (public) or
  `groups:history` (private) **plus bot membership**. A **scope** fault.

The DNC line is fully populated and now carries the Supabase mirror status, which is new and good.

## 6. Linter — GREEN (and a defect in my own rule)

Run on all 47 live workflows: **3 unresolved references reported, all in `WF-ICP-Score [DEV]`** —
`$('Name')` ×2 and `$('X')`. I read them before reporting, and **all three are inside comments**:

```js
// to come from the webhook node itself. $('Name') throws when that node is not
// `$('X')` throws when X is not connected upstream and each path has only
```

So **zero real findings**, and nothing new on any production workflow. **The rule has a defect: it
scans `JSON.stringify(parameters)`, which includes comment text inside `jsCode`.** It needs a
comment-stripping pass before matching, otherwise every code node that *documents* the reference
pattern becomes a false positive — which is precisely how a linter loses its readers.

## 7. WF-1 org write guard — RED, no wire-proof; the opposite is on the wire

I scanned 92 WF-1 executions; **12 reached the org branch, and every one of the 12 is BioTechX**:

| what ran | n |
|---|---|
| `Org Search → IF Org Found → **Org Create** → Org From Create` | **6** |
| `Org Search → IF Org Found → Org From Search` (reused an existing org) | 5 |
| `Org None` (no company on the lead) | 1 |

So on 19–20 Sep WF-1 **created six organisations** from BioTechX leads (execs `63029`, `63055`,
`63061`, `63068`, `63836`, `63842`). I also could not find any node in WF-1 that looks like an
explicit org-write guard — the org branch is gated only by `IF Company`.

**Correction to my own first pass, because it nearly became a false green:** the first five BioTechX
executions I sampled showed "org nodes: NONE", which looks like a guard holding. They were **M7
(reply-path)** executions that never approach the org branch at all — `Org Search` hangs off
`IF Company` on the invite/sent path. Absence of an org write on a path that never had one is not
evidence of anything.

**What I need to turn this from RED into a verdict:** the guard's intended contract. If it was meant
to stop WF-1 creating organisations from HeyReach data, the wire says it is **not holding**. If it
was meant to stop something narrower — overwriting an existing `org_id` on a person, say — then
`Org Create` is expected and this is green. I cannot tell which from the workflow alone.

---

## Needs action, ranked

1. **RED — WF-1 created 6 organisations on BioTechX leads (19–20 Sep).** Name the guard's contract,
   then either the guard is missing or these six are expected. Execs listed above.
2. **AMBER — the Supabase nightly heal is a treadmill.** ~500 rows healed each night, ~500 back the
   next. Fix the delta pusher's coverage rather than continuing to heal; the current pattern hides a
   standing 82-row shortfall behind a nightly green.
3. **AMBER — `WF-ICP-Score [DEV]` has a missing data table `icp_audit`** and 16 failures in 7 days.
   Same class as `dnc_gate_queue`. It is `[DEV]`, but it is **active** and its failures are the only
   thing in the estate's error budget.
4. **AMBER — digest `n/a` is 15 days old.** One code fix (`term`) + one scope grant
   (`channels:history`/`groups:history` + membership). Both were specified on 9 Sep.
5. **AMBER — the webhook secret is still null**, 16+ days. The alert is correct and the dedupe holds;
   the fix is to arm it.
6. **P3 — one production pagination race**: `dnc_escalation_detector` exec `62959`,
   *"result count changed during pagination"*. Single occurrence, but it is a read that can return a
   short list silently.
7. **P3 — my linter needs comment stripping** before its findings can be trusted at face value.
8. **P3 — the CA bundle** is stale estate-wide; regenerate `win_ca_bundle.pem` or drop the pin.

## Artifacts

`audit-artifacts/health_7d_20260924.json` — per-workflow counts, the 17 failure causes, the drift
series, the chain rows, the org-branch executions, the digest text.
