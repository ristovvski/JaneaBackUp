# 2026-09-08 — Аудитор: CLOSE-OUT (six items) — status + §9f.2 pre-post

Files only, no Slack. **Four of the six items are production writes and are HELD** — see the
constitution note below. The two that are mine, plus both read-only halves, are DONE.

## Constitution note, once

This session's founding rule is *"permanently read-only… you find, you prove, you report. Fixes
belong to the owning sessions."* It is what made the independent findings possible ("you audited
none of today's incidents, which makes you the independent eye", 26 Aug). Items **1(fix), 2, 3, 6**
are deploys to live workflows and ~564 Pipedrive writes; if I execute them, nobody audits my
writes. So they are prepared to one-confirmation readiness below. Say the word and I fire, or hand
this file to the owning session — either works, but I am not deciding that silently.

| # | item | state |
|---|---|---|
| 1a | digest fix (remove dead `$('I04 Status')`) | **HELD** — patch specified below |
| 1b | linter rule for the class | **DONE** — written, self-tested 11/11, run on the estate |
| 2 | port `__auth_warn_at` to the claims table | **HELD** — design below |
| 3 | FIRE_PIPEDRIVE | **HELD** — pre-post below, count needs a fresh walk |
| 4 | duplicate-upsert alert count | **DONE** — answered, no defect |
| 5 | kill the I-04 cron + docs | **DONE** — deleted, README rewritten |
| 6a | move Respond-to-Webhook | **HELD — and I recommend NOT doing it yet**, see 6b |
| 6b | verify claim precedes external writes | **DONE — it does NOT.** This blocks 6a. |

---

## 1b. DONE — linter rule `node_reference_resolves`

`WF_LINTER/node_reference_resolves.js`. Self-test **11/11**, including a non-vacuity case.
Run against all 41 live workflows: **exactly one finding**

```
ACTIVE  dnc_morning_digest / No Match Count (code)  ->  $('I04 Status') MISSING
```

So yes — this class would have caught it, and it catches nothing else, which is the useful part.

Two bugs its own self-test found in my first version, both fixed: node parameters are read as JSON
so a **double-quoted** reference arrives escaped (`$(\"Name\")`) and was silently passed; and a
literal containing `+` is usually concatenation — the linter's own `Lint` node was a false finding.
Resolution now runs **before** the shape test, so a real node name with a plus (`Normalize + Prep`)
resolves correctly.

**Stated residual blind spot** (pinned by self-test 10b so it cannot drift): an *unresolved*
reference that also looks like concatenation lands in the informational `dynamic` bucket rather than
failing the run. Deliberate — the alternative fired on every plus-named node. Read the dynamic list
whenever a plus-named node is deleted.

## 1a. HELD — the digest patch

One line, in `dnc_morning_digest` node `No Match Count`:

```js
- const prev = $('I04 Status').first().json;
+ const prev = $input.first().json.__digest_ctx ?? {};   // or the node that now carries context
```

**I will not guess this one.** `I04 Status` used to supply the accumulating digest context, and the
3 Sep simplification removed the I-04 leg entirely. The correct replacement depends on what the
digest is now supposed to report — the README says it reports `CRM change log N events`. Two
candidate shapes: (a) read the context from the node that immediately precedes `No Match Count`,
(b) drop the `...prev` spread and return only the `no_match_*` fields, letting `Compose` assemble.
(b) is smaller and matches "the digest is a count, not a second copy of an alert". Whoever fires it
should pick with the digest's current contract in hand, then re-run the linter — it must exit 0.

## 2. HELD — auth-notice port (finish the set of four)

`Verify Secret` already implements once-per-`webhook_secret_warn_interval_sec` (default 3600 s) with
`sd.__auth_warn_at` / `sd.__auth_suppressed`. It fails because that state is in **staticData**,
which n8n persists as one whole object at execution end — a burst (135 WF-2 executions on 09-04)
all read the same stale timestamp and every one warns. Same lost-update class the 3 Sep port fixed
for the other three stores; this is the fourth.

Design, matching the ported three:

* claims table `euyostwJYfJefItC`, one row keyed **`wf2_auth_notice`**
* value `{mode, last_posted_date, suppressed_since_last}`
* emit **iff** `mode != stored.mode` **OR** `today != stored.last_posted_date` — a state-change rule
  with a daily heartbeat. Atomic claim, so concurrency cannot defeat it (this is the whole point).
* severity split: `unconfigured` (traffic **accepted**) → once/day + on change.
  `missing` / `invalid` (a **DROP**) → every time; someone posting without the secret is not noise.
* carry `suppressed_since_last` into the daily post — the count is the actionable number.
* one **closing** post when the mode leaves `unconfigured`, so the channel shows resolution.

The alert is factually correct today: `CONFIG.webhook_secret_sha256 = null`. Setting it ends the
notice legitimately and is the real fix; the port stops the flood in the meantime.

## 3. HELD — §9f.2 PRE-POST for FIRE_PIPEDRIVE

**What will change:** person field `9c018b74…` (`DNC Status`) set to option **686** (`dnc_active`)
for registry rows that are enforceable against a Pipedrive person and not yet projected. Nothing
else — no labels, no leads, no Smartlead.

**How many records — NOT restatable from the 2 Sep number.** The ~564 was measured on 2 Sep
(≈19% of ~2,950 checkable, CI 13–27%). Six days have passed and I cannot confirm it today:

* `dnc_projections_sweep` CONFIG live: `MODE="dev"`, `FIRE_PIPEDRIVE=false`, `FIRE_SMARTLEAD=false`
* the workflow has **never executed** — 0 in retention, so no prior partial run to reconcile against
* the DNC-686 population is confirmed only to **2,261 (27–28 Aug)** because the snapshot job stopped
* the registry itself is **not readable** — the n8n data-table API is still 404 on four route shapes

**So the pre-post is incomplete by one number, and that is the thing to fix before firing.** Getting
it: run the sweep with `MODE="dev"` / `FIRE_PIPEDRIVE=false` — it is built to count without writing
— and post its dry-run count. Firing on a six-day-old estimate would breach the rule that a §9f.2
pre-post states the *current* count.

**Discipline for the fire** (unchanged from the projection precedent): fresh baseline of the 686
population bracketed around the run · chunks of 250 (`pd_chunk_size`) · per-record guard re-checked
at write time · post-verify = re-walk the 686 population and assert
`after − before == rows_written`, plus the label set still equals the 7 expected survivors.

**Reversible:** the baseline holds every prior value, so a rollback is a replay of it.

## 4. DONE — duplicate upserts are harmless, and the 3-Sep fix DID cover the alert path

Registry upserts in the window, per identity: `pii-dbea4ef2@example.invalid` **3**,
`pii-e52036b4@example.invalid` **3**, `pii-96a6af07@example.invalid` **2**, `pii-2ecee7a2@example.invalid` **2**,
`pii-8d03a357@example.invalid` **2**, five others 1 each.

Slack alerts in `#lead-processing`, 3–8 Sep: **9 alerts, one per person, zero duplicates.**
Pierce: 3 upserts → **1** alert. Yener: 2 → **1**.

Three identities had a registry row and **no** alert — `alanchan`, `vpatwari`, `eran`. I checked
whether that was a miss, and it is not: the wire shows those exact WF-1 executions running
`M7 Alert Key → M7 DT Alert Get → M7 Alert Gate → M7 IF Should Alert → **M7 Alert Suppressed**`,
with no `M7 DT Alert Claim` write. The alert claim already existed, so the gate suppressed
deliberately. The alerted case (pierce, exec 47448) runs the other branch through
`M7 Critical Slack → M7 IF Alert Delivered → M7 DT Alert Claim`.

**Verdict: nobody got 2+ alerts. The duplicate upserts are harmless re-processing — the registry
upsert is idempotent and simply is not gated by the alert claim, by design.** Noted, nothing to fix.

*(One intermediate worry of mine, recorded because it nearly became a finding: I first checked for an
earlier **registry** row for those three and found none, which looked like three unnotified
first-time replies. The alert claim and the DNC registry are different keys — an alert claim can
exist from an earlier event in the same conversation without a registry row.)*

## 5. DONE — I-04 cron killed, docs rewritten

Deleted scheduled task `i04-daily-diff`; `SKILL.md` left on disk, 11 run sessions archived.
`I04_daily_diff/README.md` rewritten: what was killed, why, what replaces it (nothing —
`dnc_i04_event_receiver`, ≈215 events/day, is the surviving leg), and what that costs.

**Correction to the premise:** it did **not** die with the laptop. The task was still **enabled**
and its `lastRunAt` was **2026-09-08T08:45:50Z**, minutes before this review, while the newest
snapshot on disk is `pd_2026-08-28`. The cron was firing and the work was silently producing
nothing — worse than not running, because the schedule looked healthy. That strengthens the call to
kill it rather than weakens it, and it is the argument for n8n as the host if departure detection is
ever wanted back: a local cron has no error path anyone reads.

## 6. 6b DONE — and it BLOCKS 6a

WF-1: 138 nodes, versionId `1f64e121`. `Respond to Webhook` sits **immediately after the Webhook
node** (its only ancestor), so all **22** external writes are downstream of the ack today — the ack
is genuinely early, and the measurement fits (p50 4.14 s, p99 5.29 s, max 6.04 s over 184
executions; ack itself at **+0.00 s**, node exec 4–6 ms).

**But the claim does not precede the external writes.** WF-1's claim nodes all target
`euyostwJYfJefItC` — `DT Claim Seen`, `M7 DT Alert Claim`, `DT Lead Claim Set` — and
`DT Lead Claim Set` is **downstream of `Create Lead` and `Person Create`**. That is
claim-after-success, the P0-1b design, chosen deliberately because claiming before success made a
half-processed reply unreplayable.

**So moving the ack after processing is not safe as-is.** The hazard is narrow and nameable: first
attempt runs `Person Create` / `Create Lead`, then fails **before** `DT Lead Claim Set` → the retry's
read-gate (`DT Lead Claim Get → Lead Claim Gate → IF Lead Claimed`) finds no claim → it creates a
**duplicate person and lead**. HeyReach retrying 5×/24h turns that one window into up to five
duplicates, on the exact object class this project has already had to de-duplicate twice.

**What makes 6a safe** (pick one, then move the ack):
1. **Two-phase claim** — write the claim row *before* the first external write with
   `status: in_flight`, flip it to `done` at the end. The read-gate treats `in_flight` as claimed,
   so a retry is suppressed; a stale `in_flight` older than N minutes is the replay signal. This
   keeps P0-1b's property (a half-processed event is still identifiable) *and* makes retries safe.
2. **Provider-event-id idempotency** — claim on HeyReach's own event id at ingress, before anything.
   Cheapest if every event carries a stable id; WF-1's own M7 path already builds `M7 Alert Key`, so
   the pattern exists.

Either is a real change with its own pre-post. **Recommendation: do not move Respond-to-Webhook
until one of them is in.** The current early ack is not a defect — it is what is keeping retries from
duplicating.

---

## Artifacts

* `WF_LINTER/node_reference_resolves.js` — the rule, 11/11 self-test, 1 finding on the estate
* `I04_daily_diff/README.md` — rewritten (item 5)
* `audit-artifacts/status_recovery_20260908.json` — yesterday's evidence base, still current

## IMPROVABLE — mine, this pass

1. **Patched a file through a bash heredoc and the escaping ate the regex block** — the assertion
   caught it, but my own memory has this exact trap written down. Rewrote the file with the editor.
2. **First linter version matched single quotes only**, so every double-quoted node reference would
   have passed. Its own self-test caught it before it ever ran on the estate.
3. **First ordering check reported "0 claim nodes"** and I nearly wrote that WF-1 has no
   idempotency at all. It has three; they are simply not upstream. Enumerating the dataTable nodes
   directly is what corrected it.
