# 2026-09-08 — Аудитор: STATUS RECOVERY (5 days without operator eyes, 3 → 8 Sep)

Read-only. No writes anywhere. Files only, no Slack post (per the ask).
Artifact: `audit-artifacts/status_recovery_20260908.json`.

## Headline

**5,592 executions in the window, 5 failures — all five the same morning-digest break, once a day.
Zero auto-deactivations. No data loss found. And one thing nobody asked about: the I-04 snapshot job
has been dead since 28 Aug.**

## 1. Morning digest — it fired every day and died before posting

`dnc_morning_digest` (`qJKfR602wV9yfFrj`) is **ACTIVE**, 40 nodes, versionId `491f65b8`, updated
2026-09-03T08:53:14. It fired at 04:00Z **every day**:

| day | result |
|---|---|
| 3 Sep | success, lastNode `Post Digest` — the last post |
| 4–8 Sep | **error**, all five identical, lastNode `No Match Count` |

Error: `Cannot assign to read only property 'name' of object 'Error: Referenced node doesn't exist'`.
Cause, from the node's own code, line 3: `const prev = $('I04 Status').first().json;` — **`I04 Status`
was removed in the 3 Sep I-04 simplification**; the digest now has zero nodes whose name contains
"I04" or "Status". Digest edited 08:53:14, `ARCHIVE__` renames at 09:08 — the node went, the
reference stayed. `No Match Count` reaches `Compose → Send Guard → Post Digest`, so the break sits
**upstream of the post**: five digests lost.

**WF-ERR DID surface all five** — one invocation per failure (`43367`, `46127`, `46669`, `47190`,
`48082`), each of which ran its `WF-ERR Slack` node. The premise in the ask is wrong: detection
worked, five alerts were posted, nobody read the channel. The gap is attention, not instrumentation.

## 2. Failures since 3 Sep — five, one cause, no deactivations

Nothing else in the estate failed for six days. Zero auto-deactivations: 11 inactive workflows are
the deliberate `ARCHIVE__`/`zz_` renames of 3 Sep, the rest are long-standing sub-workflows or
deprecated paths. `DNC__UpsertLedger__v1` is inactive **by design** — it is a sub-workflow, and it
ran 27 times.

The six active workflows with zero executions (`dnc_projections_sweep`, `dnc_s1`, `dnc_s2`, `dnc_s4`,
`dnc_archived_responders_import`, `dnc_intent_vs_reality`) are **all webhook-triggered only** — their
silence is the expected state, not a failure. Volume: 09-03 878 · 09-04 2,646 · 09-05 541 ·
09-06 518 · 09-07 759 · 09-08 250.

## 3. Finovate step 2 — the 3-Sep deploys hold, with one premise correction and one open item

Step-2 sends in window: **137** (3868449: 76, 3868450: 61) — matches "~120".

⚠️ **Correction:** Smartlead shows only **one** reply on the two Finovate campaigns since 4 Sep —
**Person-f5f25c02**, `pii-96a6af07@example.invalid`, 2026-09-04T23:41:03, category *Meeting Request*. The
`reply_dnc` rows on 5–8 Sep are LinkedIn replies from **other** campaigns.

**(a) Both channels wired, both fired.** `WF-2 / DNC Upsert Call` and `WF-1 / M7 DNC Upsert Call`
both target `RolYGL3J2CNg6Yp3`. 27 upserts: 19 `reply_dnc` + 8 `sales_personal_outreach`; by feeder
**17 reply_dnc from WF-1 (LinkedIn), 2 from WF-2 (email)**. The Finovate reply got its row at
**23:41:49 — 46 s after the reply**. (The dedicated `heyreach_reply_to_dnc_ledger` is inactive and
has never run; LinkedIn goes through WF-1 directly.) Registry rows are proven from the UpsertLedger
executions on the wire — the n8n data-table API is still 404.

**(b) Duplication exists; alert-once is UNTESTED.** 5 of 10 identities were upserted more than once:
`pii-dbea4ef2@example.invalid` ×3, `pii-e52036b4@example.invalid` ×3, `pii-2ecee7a2@example.invalid` ×2,
`pii-8d03a357@example.invalid` ×2, `pii-96a6af07@example.invalid` ×2. Upsert is idempotent so the rows are correct,
but each repeat is a separate WF-1/WF-2 pass. I did not count Slack posts per person, so **"alerts
once per person" is not proven** — that is the one open item, and the check is: count reply-alert
posts per person for 4–8 Sep against those five identities.

**(c) Green on the case available.** Yener → person **p86064**, name **"Person-f5f25c02"** (provider
name, not the email local part), **one** lead `073fd900` titled
`3868450 - [Events Visiting] [FinovateFall 2026] - Noah - Catch…`, person added 2026-09-01 (so
pre-reply, not created by it). LinkedIn-only repliers carry `pipedrive_person_id` in the upsert input
(86030 Person-e4afd4b4, 84492 Person-451d4581) — person-linked at the registry level too.

## 4. In-flight work, as of now

* **WF-2 staticData port — FIRED, MIGRATED, and now PROVEN LIVE.** 105/105 rows on 3 Sep
  (94 `wf2_seen`, 11 `wf2_alert`, 0 `wf2_bounce`); WF-2 174→188 nodes. The 3 Sep log's PARTIAL was
  *"the ported paths have not run in production"* — **closed**: WF-2 ran **142** times in the window
  (135 on 09-04, 7 on 09-07), all success, zero errors; `dnc_claims_prune` 7/7 success.
* **FIRE_PIPEDRIVE — NOT fired; the ~564-row backlog is still outstanding.**
  `dnc_projections_sweep` CONFIG live: `MODE="dev"`, `FIRE_PIPEDRIVE=false`, `FIRE_SMARTLEAD=false`,
  and the workflow has **never executed**. DNC field-686: 2,262 (20 Aug) → 2,261 (27 & 28 Aug).
* **FIRE_SMARTLEAD — not fired**, flag false; the 2 Sep scope decision is still open.
* **WF-1 early-ack — DONE and measured.** `Respond to Webhook` present, `responseMode:
  responseNode`; ack fires at **+0.00 s** in 8/8 sampled executions (node exec 4–6 ms). Wall time
  over 184 executions: min 0.62 s · p50 4.14 s · p90 4.63 s · p99 5.29 s · max 6.04 s · none >10 s.
  WF-1 is now 138 nodes, versionId `1f64e121`.

## 5. "secret NOT ARMED" — the rate limit already exists and concurrency defeats it

Emitter: **WF-2 / `Ops Warn Bad Secret`**. `Verify Secret` already implements once-per-
`webhook_secret_warn_interval_sec` (**default 3600 s**) with `sd.__auth_warn_at` and
`sd.__auth_suppressed`. **It fails because that state is in `staticData`**, which n8n persists as one
whole object at execution end — so a burst (135 WF-2 executions on 09-04) all read the same stale
timestamp and every one warns. Same lost-update class the 3 Sep port fixed for WF-2's three *other*
stores; this one was not ported. The alert is also **factually correct**:
`CONFIG.webhook_secret_sha256 = null`.

Proposed state-change rule: move the notice state to the claims table `euyostwJYfJefItC`, one row
`wf2_auth_notice` `{mode, last_posted_date, suppressed_since_last}`; emit **iff mode changed OR the
date changed** (atomic claim, so concurrency cannot defeat it); split severities — `unconfigured`
(traffic accepted) once/day + on change, `missing`/`invalid` (a DROP) every time; carry the
suppressed count into the daily post; emit one closing post when the mode clears. Root fix that ends
it legitimately: set `webhook_secret_sha256`.

## PARTIAL

* §3(b) alert-per-person dedupe — not counted, named above with the exact check.
* Registry rows cannot be read directly (no n8n data-table API); proven from UpsertLedger executions.
* Today's DNC field-686 population needs a fresh full walk (see below).

## IMPROVABLE — four of my own, all caught before publication

1. My UpsertLedger caller listing showed only WF-2; **WF-1's `M7 DNC Upsert Call` targets the same
   sub-workflow** and was missed — correcting it is what makes the "both channels" answer provable.
2. My campaign-membership check compared **string ids against integer ids**, so Yener was reported
   as not-Finovate when 3868450 *is* Finovate.
3. That same check returned **empty** campaign lists for 9 of 10 identities — a lookup failure, not
   evidence of non-membership; not treated as a zero.
4. Two inline shell regexes failed on escaping (one printed "0 reads", one raised) — recomputed from
   files instead of trusting the empty result.

## NOT ASKED, BIGGEST FINDING — P1

**The I-04 daily snapshot job has been dead since 28 Aug.** `audit-artifacts/snapshots/` ends at
`pd_2026-08-28`; nothing for 29 Aug – 8 Sep. Archived leads are invisible to every Pipedrive list
read, so a departure is only detectable against an id set persisted **before** it left — **eleven
days of lead departures are now permanently unmeasurable**, precisely the failure mode the I-04
README names. It is a local Claude scheduled task (runs only while the app is open), not an n8n
workflow, so nothing in the estate would ever report its absence.
