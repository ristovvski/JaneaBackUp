# Independent audit PHASE 2 — full stack, 2026-08-10, window closes 16:30Z

Auditor session. Read-only throughout. Own tooling, own walks; other sessions' reports were read
only to know what was *claimed*. Authority: HeyReach / Smartlead / Pipedrive / Slack / Zapier / Make
API > n8n raw execution data > any session's report.

Evidence: `scratchpad/b1_registries.json`, `b3_hr_full.json`, `b4_wf1_delivery.json`,
`b5_drift.json`, `b6_verify.json`, `b7_vaughn.json` (+ Phase 1's `a1`–`a8`).

---

## Executive summary

**Phase 2 closed 5 surfaces and answered the open P0 question in the negative: WF-1 is healthy.**
Today's zero WF-1 executions are correct — both HeyReach LinkedIn campaigns are PAUSED and HeyReach
recorded **zero events today** (0 inbound, 0 outbound). Not a dead receiver.

**14 new anomalies, 1 high, and one that should hold the sentinel on its own: the team's reply
notifications have been dark for 5 days and the flip made it worse, not better.** Plus a correction
to my own Phase 1 attribution, and a correction to a prior session's retention assumption that
under-scoped the wiper sweep by 12 days.

**Fix verification: 4 of 8 checks PASS, 1 FAIL-equivalent (P0-1b not shipped), 3 NOT-YET.
Sentinel: still blocked.**

| # | Sev | Finding | § |
|---|---|---|---|
| 1 | **High** | `#lead-processing` has had **zero** reply notifications since 2026-08-05T11:14:25Z; n8n has **never** posted there; after the flip WF-2 routes reply alerts to Nik's private ops channel | §3 |
| 2 | Medium | A **test fixture** notification reached `#lead-processing` on 2026-08-07T08:11:56Z ("Person-6d3f690f Test") — corrects my Phase 1 "no test content reached the team channel", which covered today only | §3 |
| 3 | Medium | **Phase 1 attribution correction:** `axios/1.18.0 \| u24599218` is n8n's own Pipedrive-credential fingerprint, not a third party's. The wiper trigger is still not n8n (no execution ran in those seconds) but the actor is *unidentified*, not "pii-0bd328cb@example.invalid's scanner" | §2 |
| 4 | Medium | **Prior-session retention error:** WF-1 retains **1,398** executions back to 2026-07-23, not "~250 back to 2026-08-05". The label-wiper sweep declared 12 days UNKNOWN that were fully readable | §1 |
| 5 | Medium | 7 DNC workflows carry `errorWorkflow: "REPLACE_CORE__Erro…"` — a **placeholder string**, not a workflow id. Errors will route nowhere the day DNC goes live | §2 |
| 6 | Medium | **WF-ERR itself has no `errorWorkflow`** — if the error handler fails, nothing reports it | §2 |
| 7 | Medium | 127 WF-2 **crashed** executions in retention, in 4 bursts; most with `nodes_run=0` and `startedAt=null` — accepted webhook deliveries dropped whole (OOM signature) | §2 |
| 8 | Low | Vaughn class quantified: **1 of 50 replying profiles (2.0%)** arrived only as `message_reply_received` → NoOp, no CRM write. Already backfilled today | §1c |
| 9 | Low | **WF-1's "gaps: 0" is wrong at the delivery level** (1 of 51 profiles), right at the outcome level (0) | §1e |
| 10 | Low | `#lead-processing` shows **9 duplicated** Zapier notification pairs (identical text and timestamp) | §3 |
| 11 | Low | WF-2S `__sent_seen_v2` contains exactly **1 row — the test fixture's** stats_id. The only SENT event ever replayed, in the system's history, is synthetic | §4 |
| 12 | Low | WF-2S `__sent_seen` (v1) holds **125 poisoned rows** from 2026-07-29, never pruned | §4 |
| 13 | Low | 4 HeyReach test campaigns still present (`Final TEST`, `Final test`, `TEST2`, `TEST`) | §4 |
| 14 | Info | Drift: campaign 3756410 has 16 Smartlead sends and **1** Pipedrive lead — P0-2 visible in the counts | §5 |

---

## §1 HeyReach / WF-1 — VERDICT: **quiet day, receiver healthy. Not a P0.**

**1a. Inbox truth.** `POST /inbox/GetConversationsV2`, my own client.
Walk proof: **345 of totalCount=345** conversations, 4 pages, offsets strictly increasing, zero
duplicate ids, **zero conversations whose `messages` array was shorter than `totalMessages`** (so no
silent truncation).

| day | inbound (replies) | outbound | WF-1 executions |
|---|---|---|---|
| 2026-08-03 | 11 | 51 | 125 |
| 2026-08-04 | 23 | 131 | 167 |
| 2026-08-05 | 43 | 111 | 156 |
| 2026-08-06 | 17 | 109 | 121 |
| 2026-08-07 | 3 | 5 | 5 |
| 2026-08-08 | 2 | 4 | 2 |
| 2026-08-09 | 3 | 4 | 4 |
| **2026-08-10** | **0** | **0** | **0** |

Totals: 196 inbound / 997 outbound messages across all time; 102 / 415 in the 7-day window.

**1d. The verdict on today's zero.** HeyReach `/campaign/GetAll`: 6 campaigns, **all PAUSED or
FINISHED** — including both production ones, `512995` ([Ai4] Mario - LinkedIn) and `513000`
([Ai4] Rune - LinkedIn). Zero HeyReach events today ⇒ zero WF-1 executions is **correct behaviour**,
not a dead receiver. The channel has been winding down since Ai4 ended (outbound fell from 109 on
Aug 6 to 4–5/day from Aug 7). **No loss, no P0.** The suspected P0 is closed as a non-finding.

**1b. Per-delivery CRM behaviour** (485 executions in the 7-day window, each read from raw runData).
Event mix: `connection_request_sent` 185 · `connection_request_accepted` 94 ·
`every_message_reply_received` 89 · `message_sent` 77 · `message_reply_received` 40.
Processed replies wrote through the full M7 chain — `M7 Person Search Email|URL`, `M7 Lead Get`,
`M7 Labels Compute`, `M7 Lead Patch`, `M7 Person Patch`, `M7 Reply Activity`, `M8 IF Transition` —
in 4 stable shapes. **39 `M7 Critical Slack` posts returned `ok:true`, all to `C0B8GCVNR5W`.**
Not one WF-1 post went to `C07LTD8UT70` in 7 days (see §3).

**1c. The Vaughn class, measured.** HeyReach delivers a reply under two names; WF-1's `Switch` has a
branch for `every_message_reply_received` and routes `message_reply_received` to `NoOp`. That is only
safe if every reply also arrives under the first name.

- NoOp-only deliveries: **46 of 485 (9.5%)** — all 40 `message_reply_received` plus 6 `message_sent`.
- Grouped per replying profile (50 distinct): **39 arrived under both names** (NoOp correct),
  **10 only as `every_message_reply_received`** (processed), **1 only as `message_reply_received`**.
- **Delivery-gap rate: 1/50 = 2.0%.** The one case is Person-0ee7dfb2
  (`https://www.linkedin.com/in/pii-bf2efff7`, delivery 2026-08-08T02:52:06Z, reply 02:42:07.557Z,
  `noop_only=True`) — i.e. the original Vaughn incident is the *only* instance in 7 days, and it was
  backfilled today (lead `ac5dda00` gained Connected + Responded at 10:50:58Z, activities 43970/43971).

So the class is real but rare. The NoOp branch is not itself the bug — the bug is that there is no
detector for "a reply arrived under only the one event name".

**1e. "gaps: 0" re-derived independently.** HeyReach inbound (7d) → 51 distinct replying profiles.
WF-1 received a reply delivery for **50**. One gap: `https://www.linkedin.com/in/pii-8e47bb7b`
(2 inbound messages 2026-08-03T16:58:09Z / 16:58:27Z, no WF-1 reply delivery in the window).
**Outcome check, which is what matters:** his lead `4833b670-899f-11f1-aecb-b98793bd5480` currently
carries `['1. Cold','2. Connected','3. Responded']`, written by the earlier 2026-08-02T16:26:45Z
delivery. So: **1 delivery gap, 0 outcome gaps.** WF-1's "gaps: 0" is defensible as an outcome
statement and wrong as a delivery statement — worth making explicit in the digest, because the two
diverge exactly where follow-up messages in an existing conversation are concerned.

**Finding 4 (method correction for another session).** WF-1 retains **1,398 executions back to
2026-07-23T16:26:05Z**. `t4_label_wiper_sweep.py` states "n8n retains ~250 WF-1 executions
(currently back to 2026-08-05)" and reports everything earlier as UNKNOWN. The sweep can be re-run
over 12 additional days at no cost, and should be — its "2 confirmed wipes" was bounded by that
wrong assumption, not by retention.

---

## §2 n8n estate — VERDICT: **matches the expected table exactly; two wiring defects**

16 workflows, **16/16 agree with the expected state table** (6 active: WF-1, WF-2, WF-2S, WF-2R,
WF-2H, WF-ERR; 10 inactive: 7 DNC/observability + 3 legacy). **No unexpected workflow.**

Schedules match config: WF-2S and WF-2R `minutesInterval: 15`; WF-2H daily 07:15; (inactive)
`dnc_expiry_job` cron `0 6 * * *`; (inactive) `smartlead_observability_readonly` 30 min.

**Error-workflow wiring:**
- All 6 active workflows except WF-ERR point at `BbrXPABgOaaTJjD6` (WF-ERR). ✅
- **WF-ERR has no `errorWorkflow`** — the error path has no backstop. If WF-ERR throws, the failure
  is silent. (Finding 6.)
- **The 7 DNC/observability workflows carry `errorWorkflow: "REPLACE_CORE__Erro…"` — a placeholder
  string, not a workflow id.** Harmless while inactive; a landmine on the day DNC is activated.
  (Finding 5.)

**Non-success executions, full retention (3,411 executions):** 147 total.

| workflow / status | count | assessment |
|---|---|---|
| WF-2 crashed | 127 | 4 bursts: 2026-07-29 17:45–18:00, 07-30 09:45, 08-04 14:15–14:30, 08-05 07:00. Sampled: `nodes_run=0` with `startedAt=null` for most (the instance died before persisting anything); one (11813) ran 47 nodes and died at `Skip Lead Create` — a SENT-path replay. Consistent with the recorded OOM replay-burst incident. **Each is an accepted webhook delivery dropped whole.** (Finding 7) |
| WF-2 error | 10 | 9 historical (2026-07-29/31) + **14966 = today's P0-1** |
| WF-2S crashed / error | 5 / 1 | same bursts |
| DNC__UpsertLedger__v1 error | 2 | today's probe runs, schema drift, `mode: integrated`, inactive workflow |
| WF-1 crashed | 1 | 2026-07-30T09:46:01Z, inside an OOM burst |
| WF-2H error | 1 | 2026-07-30T07:15:36Z digest |

**Everything is accounted for: today's only unexplained-at-Phase-1 error was 14966 (P0-1); the DNC
pair are test probes; the remaining 144 belong to the historical OOM bursts.**

---

## §3 Slack wire — VERDICT: **FAIL. The team channel is dark and the flip pointed reply alerts away from it.**

**`C0B8GCVNR5W` (#niks-channel), today, complete from 07:15Z:** every bot post maps to a known
intent — WF-2H digest (07:15Z), unknown-event + unarmed-secret warnings (11:01Z), no-matching-lead
warning (12:37Z), write-mode alarms (13:45/14:00/14:15/14:30Z), WF-2S-stale watchdog (14:15:29Z,
`ts 1786371329.821239`), the one successful reply alert (15:04:03Z), the WF-ERR crash post (15:31:04Z).
**No unexplained post. No expected-but-absent post** other than the two silently-failed reply alerts
already recorded in Phase 1. Two posts with **empty text** at 13:16:01Z and 14:45:06Z — the exact
timestamps of the dedupe-replay executions, which ran no Slack node; still unexplained by any node
path I can see, so it is something posting a blank body rather than a suppressed message. (Finding 10)

**`C07LTD8UT70` (#lead-processing) — the important one:**

- **Zero n8n posts, ever.** The channel contains only Zapier Bot notices, Lilla Szabo's "New
  'Responded' Lead Label in Pipedrive!" notices, and join events.
- The n8n Slack bot (`U0BLBUP50FM`) **joined the channel today at 11:06:14Z** — 34 minutes *after*
  WF-1's reply-channel switch was deployed (10:32:16Z). Any WF-1 reply in that window would have
  failed with `not_in_channel`. None arrived, so no loss — but the ordering was backwards.
- **Last reply notification of any kind: 2026-08-05T11:14:25Z** (Zapier Bot, Person-e1593f4e).
  That is 14 minutes before zap `274357187` — the only Slack-posting zap — was paused at
  **2026-08-05T11:28:42Z**. The two facts line up exactly.
- **Last genuine email-reply notice: 2026-08-04T22:11:35Z** (Person-a8907c02 / Retool).
- **Last notice of any kind: 2026-08-07T08:11:56Z — and it was the test fixture** ("Name: Flip,
  Company: Person-6d3f690f Test", lead `d6d4a9a0-91b7-11f1-9fbf-770fb43b481a`). (Finding 2 — this
  corrects my Phase 1 sentence "No test content reached `#lead-processing`", which was scoped to
  today and should have said so.)
- **Net effect (Finding 1, High):** for 5 days nobody has been notified in the team channel about a
  reply from either channel. WF-1 posts to the ops channel (39 × `ok:true`, all `C0B8GCVNR5W`), and
  WF-2's reply alerts also go to the ops channel because `slack_channel_replies = C0B8GCVNR5W` while
  `slack_channel_replies_at_flip = C07LTD8UT70` is read by no node. **The flip moved email-reply
  notification from a team channel into one person's ops channel, silently.** Deleting the vestigial
  key (tonight's hygiene item) would erase the only trace of the original intent — make that a
  decision, not a cleanup.

**Ops noise in `C07LTD8UT70`: none.** That part of the claim holds.

---

## §4 Registries & ledgers — read directly from `staticData` (available on `GET /workflows/{id}`)

| store | rows | state |
|---|---|---|
| WF-2 `wf2_seen` | 7 | 5 fixture replies + 1 probe + **Marine: `REPLIED\|3686184\|4214180591\|1786375820000` claimed at 15:30:57Z** — one second after the crash began. **Claim-before-work proven from the store itself, not inferred.** |
| WF-2 `__alert_delivered` | **0** | The new delivery-registry gate has never recorded a delivery. Deployed 15:10:44Z; no reply has completed since. |
| WF-2 `__auth_suppressed` / `__auth_warn_at` | 4 / 14:39:08Z | unarmed-secret warning suppression — consistent with the 4 warnings observed |
| WF-2S `__sent_seen_v2` | **1** | `284d27db-8dd6-4117-b1ec-b93485483150` → 2026-08-06T16:56:56.071Z — **the test fixture's** stats_id, and the newest row of 3686187's blind page. The only SENT event ever successfully replayed is synthetic. (Finding 11) |
| WF-2S `__sent_seen` (v1) | 125 | all stamped 2026-07-29T17:45–18:00 — the keys the v2 rewrite abandoned, never pruned (Finding 12) |
| WF-2S `__wf2_live_since` | — | `2026-08-10T11:45:14.041Z` — the authoritative flip stamp |
| WF-2S `__prev_active_ids` | 1 | `['3756410']` — it has already observed tonight's campaign pause |
| WF-2R `__reply_seen_v1` | 4 | keyed on **message-id** (`M\|<…>`), a different key space from WF-2's — which is why replay+dedupe interoperate. Holds 3 fixture replies + 1 from Aug 7. The 14:52:51Z and 15:03:18Z replies and Marine are **not yet** claimed: WF-2R sweeps 1 campaign/cycle (`__rr_cursor=5`, `__tick=389`, hot sweep ≈1.7 h), so it will replay them and WF-2 will dedupe all three away — correct for two, the loss for Marine |
| WF-1 `seen` | 4 | last 2026-08-09T22:11Z — matches its last execution |
| WF-1 `__alerted_v1` | 50 | per-lead alert registry, keyed `L<lead-uuid>\|<campaign>` |
| WF-ERR `__burst` | 1 | `jp7rum9Z0YDJkQWv\|Body Reply Alert → {count: 1, suppressed: 0}` — the crash alert fired once and suppressed nothing, so no hidden repeat crashes |

**Orphan claims: none.** Every row in every store maps to an event I independently observed on the
Smartlead or HeyReach wire.

**DNC tables: NOT auditable.** `/data-tables` and `/dataTables` return 404 on the public API, so
pre-seed row counts and probe residue could not be inventoried. Stated as a coverage limit, not as
"clean".

---

## §5 Cross-system drift map — baseline for the DNC-seed / London-backfill day

Smartlead leads = rows returned by `leads-statistics` (leads that have been sent to).
Pipedrive counts use the `{campaign_id} - ` title convention only, so they are a floor.

| campaign | Smartlead leads | Smartlead send rows | Pipedrive leads (prefix) | drift | Smartlead status now |
|---|---|---|---|---|---|
| 3686181 Mario Valids | 254 | 806 | 274 | +20 | PAUSED |
| 3686184 Mario Catch-alls | 206 | 633 | 215 | +9 | PAUSED |
| 3686187 Rune Valids | 205 | 662 | 219 | +14 | PAUSED |
| 3686193 Rune Catch-alls | 227 | 716 | 240 | +13 | PAUSED |
| **3756410 AI4 2026 - Rune** | **16** | **16** | **1** | **−15** | **ACTIVE** |

The +9…+20 drift is expected (Pipedrive holds leads not yet sent to). **The −15 on 3756410 is
P0-2 visible in the counts**: the newest campaign has 16 sends and one Pipedrive lead, because
nothing has created leads from SENT events since Make was switched off.

HeyReach: 6 campaigns — `513000` PAUSED, `512995` PAUSED, plus 4 test campaigns
(`510736 Final TEST`, `510448 Final test`, `506813 TEST2`, `505075 TEST`) PAUSED/FINISHED
(Finding 13). Pipedrive total: 57,602 leads, **1,718** carrying `3. Responded` (see §6).

---

## §6 Verification of tonight's fixes — **4 PASS, 1 not shipped, 3 not yet**

Swept 16:18Z–16:30Z, independently, from raw sources.

| check | verdict | evidence |
|---|---|---|
| P0-1 `Body Reply Alert` declares `alert_text` | **PASS** | WF-2 `versionId 838ceb52-3f26-4550-84cb-aab0149975dc`, `updatedAt 2026-08-10T16:06:15.221Z`; declaration present |
| P0-1 **proven on a live reply** | **NOT PROVEN** | zero replies since 15:30:20Z. And the campaigns are now paused, so waiting will never prove it — see the blocker below |
| P0-1b dedupe claim-after-success | **NOT SHIPPED** | `Dedupe` still contains `if (!duplicate) store.wf2_seen[key] = nowSec;`. The dispatch said "same deploy"; it is not in `838ceb52` |
| Marine's key released | **STILL PRESENT** | `wf2_seen['REPLIED\|3686184\|4214180591\|1786375820000']` = 1786375857 |
| P0-3 all 5 label-writing zaps OFF | **PASS** | read back via Zapier Manager: `274357463` off 16:11:53Z · `274354645` off 16:12:06Z · `274318213` off 16:12:16Z · `274316027` off 16:12:25Z · `274357187` off since 2026-08-05T11:28:42Z |
| P0-3 the 11 wiped leads restored | **PASS** | 11/11 match their target label sets exactly, re-read live |
| P0-3 arithmetic cross-check | **PASS** | `3. Responded` population re-walked over all 57,602 leads: **1,718 = 1,713 + 5**, exactly the 5 leads that regained it. No collateral label writes |
| P0-3 kill-then-repair ordering | **PASS** | zaps off 16:11:53–16:12:25Z, repairs verified 16:18Z — ordering respected |
| P0-2 four Ai4 campaigns paused | **PASS** | Smartlead: 3686181/84/87/93 = PAUSED; only 3756410 ACTIVE. WF-2S `__prev_active_ids` already reflects it |
| P0-2 WF-2S sees today's rows | **UNCHANGED (expected)** | exec 14973 @16:15:12Z: `{"__idle": true, "considered": 2016, "stale": 2016, "already": 0}`; `__sent_seen_v2` still 1 row. Patch is tomorrow's work |
| fixture Handover 43974 | **NOT YET** | `done=False`, `due 2026-08-13`, `user_id 16340280` — still in Melisa's queue |
| fixture lead Responded stripped | **NOT YET** | `72ec85c0` labels `['1. Cold','2. Connected','3. Responded']`, `update_time 15:04:12.800Z` |
| fixture SL lead suppressed | **NOT YET** | `is_unsubscribed=false`, still mapped to campaign 3686187 |
| new WF-2 errors since the fix | **none** | latest 30 WF-2 executions: only 14966 (the known P0) plus historical crashes |

---

## SENTINEL: still blocked. Five reasons, in order.

1. **P0-1b was not shipped.** Until `Dedupe` claims after success, every crashed event is still
   permanently unreplayable — the exact mechanism that made Marine unrecoverable. The hotfix removed
   *this* crash; it did not remove the class.
2. **P0-1 is deployed but unproven, and pausing the campaigns removed the traffic that would prove
   it.** This is the same shape as the failure being fixed: `45637e70` was also deployed clean and
   also passed statics. It needs a **controlled fixture reply** through the live webhook — assert
   `Reply Alert → ok:true` and a message present via the Slack API — not "wait for the next reply".
3. **Marine's dedupe key is still claimed**, so even a correct replay is suppressed. Releasing that
   one key is part of the recovery, whatever is decided about her OOO content.
4. **Fixture hygiene is open** — the Handover is still sitting in Melisa's queue for Wednesday, and
   the fixture lead still carries `3. Responded` (it is one of the 1,718).
5. **The team channel is dark (Finding 1).** "The system works" cannot be signed off while no reply
   from either channel has reached `#lead-processing` for 5 days and the flip's own config key for
   that routing is dead. This is a decision, not a bug — but it belongs in the EOD before the
   sentinel, not after.

I will re-run §6 on demand. What would flip it to a pass: P0-1b shipped and read back, a controlled
fixture reply proving the alert on the Slack wire, Marine's key released, the three fixture items
closed, and an explicit decision recorded on the reply-notification channel.

---

## Coverage limits (Phase 2)

1. n8n **data tables** are not readable via the public API — DNC ledger/domain-block rows
   uninventoried (§4 asked for this; it cannot be answered from the API).
2. n8n exposes **no version history** (`/versions`, `/history` 404; `versionCounter` null on every
   workflow) — deploy spans remain reconstructed from backups + `updatedAt` + cadence.
3. Zapier **task history** was not opened (only `Find Zap`, a read action, is enabled; enabling more
   would change the user's MCP configuration). Per-step field mappings remain unread.
4. HeyReach **accepts/invites** were counted from conversation messages, not from a dedicated
   activity endpoint; `connection_request_accepted` counts come from WF-1's own deliveries (94 in 7d).
5. The 127 crashed executions were **sampled** (4), not each read; most carry no runData at all.
6. Window closes **2026-08-10T16:30Z**. Sends were still arriving from campaign 3756410 at 15:54Z;
   anything after 16:30Z is outside both phases.
