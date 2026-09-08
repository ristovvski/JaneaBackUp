# Melisa's two reported failures — verified against the wire, 2026-08-11T10:50Z

Auditor session, read-only. Both complaints are **substantially correct**. Every miss maps to a
known defect; **no UNKNOWN**. Evidence: `scratchpad/c1_hr_pause.json`, `c2_replies.json`,
`c4_melisa.json` (+ Phase 1/2 sets).

**Note on window:** this session has crossed midnight. "Now" is **2026-08-11T10:50Z**; Melisa's
"last 4 days" = Aug 7 → Aug 11, which is the window used below.

---

## 1. LinkedIn follow-ups — WHEN it stopped, and WHY

### Cause: not LinkedIn auth. The accounts are healthy.

`/li_account/GetAll` — 4 accounts, all of them:

| id | account | `isActive` | `authIsValid` | `isValidNavigator` | `activeCampaigns` |
|---|---|---|---|---|---|
| 226601 | Rune Jensen | **false** | **true** | true | 0 |
| 226606 | Mario Stalder | **false** | **true** | true | 0 |
| 224434 | Sergey Cujba | **false** | **true** | true | 0 |
| 225130 | Melisa Draksler | **false** | **true** | true | 0 |

**`authIsValid: true` on all four — LinkedIn-side auth expiry is ruled out by the wire.** Navigator
sessions are valid too. `isActive:false` with `activeCampaigns:0` is the *consequence* of both
campaigns sitting in `PAUSED`, not a login failure. HeyReach exposes **no `pausedAt` / `deactivatedAt`
field** on either object, so *who* paused it is not provable from the API — but nothing was broken.

### When: outbound stopped 2026-08-06T23:31:12Z. Two independent clocks agree.

| clock | last connection request sent | last follow-up message sent | activity 08-07 → 08-11 |
|---|---|---|---|
| HeyReach `byDayStats` | 513000: 08-06 (40/day) · 512995: 08-05 (25) | 513000: 08-06 (15) · 512995: 08-06 (11) | **zero `connectionsSent`, zero `messagesSent`** |
| WF-1 webhook deliveries | **2026-08-06T10:09:15.525Z** | **2026-08-06T23:31:12.844Z** | **zero of either event type** |

The 40/day pattern is the account's daily cap; Aug 6 ran its quota out at 10:09Z and then nothing
followed. **Melisa's "dead since Aug 6" is exactly right — the pause was effective from
2026-08-07T00:00Z.**

### Her screenshot anchor (Rune → Matt, Daikin Innovation Lab, Aug 7 07:26) — NOT corroborated

- **No `connection_request_sent` event exists after 2026-08-06T10:09:15.525Z**, and `byDayStats`
  records **zero** `connectionsSent` on 08-07 for both campaigns. WF-1 was up and processing replies
  on 08-07/08/09, so this is not a receiver gap.
- **No Daikin profile appears in the inbox** (346 conversations walked). The only "Matt" is
  **Person-7462fd6b — Openlayer**, inbound 2026-07-31T16:32:11Z.

So the Aug 7 07:26 item is **not a send our surfaces recorded.** Most likely a *scheduled/next-step*
time or a local-time rendering in the HeyReach UI. **Please get the screenshot from Nik** — one look
at which column it is settles it. I am not going to guess in a message that reaches Melisa.

### The stranded queue — three numbers, because "the queue" is ambiguous

| definition | number | source |
|---|---|---|
| **Connections ACCEPTED since the last send, never followed up** | **2** | WF-1 clock: `connection_request_accepted` 2026-08-07T15:55:50.580Z and 2026-08-09T04:06:46.252Z. `byDayStats` agrees (513000: 1 on 08-07, 1 on 08-09; 512995: 0) |
| **Leads frozen mid-sequence** (next step will never fire while paused) | **1,039** | `progressStats.totalUsersInProgress`: 596 (513000) + 443 (512995) |
| Accepted-but-unmessaged over campaign lifetime (approx.) | **~38** | 513000: 110 accepted vs 94 `messagesSent`; 512995: 89 vs 67. Approximate — `messagesSent` can count several messages to one lead |

**The number Melisa is asking for is 2.** The number that matters for restarting is **1,039**.

Campaign detail: `513000` Rune — 656 users, 596 in progress, 47 finished, 5 failed, 9 manually
stopped. `512995` Mario — 611 users, 443 in progress, 143 finished, 10 failed, 17 manually stopped.
Both started 2026-07-18.

---

## 2. Replies Aug 7 → now — graded per reply

### Table 1 — LinkedIn (HeyReach inbox: 9 inbound messages, 7 people)

| # | when (UTC) | who | WF-1 delivery | CRM state now | Slack | attribution |
|---|---|---|---|---|---|---|
| 1 | 08-07 01:09:19 | Person-a731ca52 | `every_message_reply_received` | `0b2b9880` Cold·Connected·**Responded** | none | per-lead alert registry (by design) |
| 2 | 08-07 15:36:15 | Malachi Bierstein | both names | `7f91e3b0` Cold·Connected·**Responded**·Disqualified — **repaired 08-11 09:49:20Z** | **ok:true → `C0B8GCVNR5W`** ts `1786118154.035349` | **wiper** (label wiped 08-07, repaired today) + **wrong channel** |
| 3 | 08-07 19:53:21 | Mallikarjuna Mudigonda | `every_…` | `079cb2a0` Cold·Connected·**Responded** | none | alert registry |
| 4 | 08-08 02:42:07 | **Person-0ee7dfb2** | **`message_reply_received` only → NoOp, NO CRM write** | `ac5dda00` Cold·Connected·**Responded**·Disqualified·NOT INTERESTED (backfilled 08-10, triaged 08-11 08:55:53Z) | none | **Vaughn class** — event-name gap, 2% rate; closed by backfill |
| 5 | 08-08 18:17:27 | Person-cee23a2f | `every_…` | `9779a200` Cold·Connected·**Responded**·Positive Reply | none | alert registry (already alerted 2026-08-05T14:10:18Z) |
| 6 | 08-09 03:40:06 | Person-c9bb6bd1 | both names | `d01a4d90` Cold·Connected·**Responded**·Disqualified — **repaired 08-11 09:47:26Z** | **ok:true → `C0B8GCVNR5W`** ts `1786248408.635579` | **wiper** (wiped 08-09, repaired today) + **wrong channel** |
| 7 | 08-09 21:22:33 | Person-f4bb4705 | `every_…` | `90f2abf0` Cold·Connected·**Responded** | none | alert registry |
| 8 | 08-09 21:22:49 | Person-f4bb4705 (2nd msg) | `every_…` | same lead | none | alert registry |
| 9 | **08-11 05:03:20** | Person-cee23a2f | `every_…` — exec **15097** | activity **44000** created (`LinkedIn reply — [Ai4 2026] - Rune`), labels computed | **suppressed** — path ended `M7 Alert Gate → M7 IF Should Alert → M7 Alert Suppressed`; **no post to any channel** | alert registry; **this was the first WF-1 reply after the channel switch, so the switch is STILL unproven** |

**CRM: 8 of 9 wrote. Slack: 2 of 9 posted — both to the ops channel, zero to `#lead-processing`.**

### Table 2 — Email (Smartlead `leads-statistics history[]`, all 117 campaigns walked)

16 REPLY/FORWARD events in the window. Replies only:

| when (UTC) | lead | organic? | outcome | attribution |
|---|---|---|---|---|
| 08-07 08:11:00 | `pii-c61c7d08@example.invalid` | fixture | forwarded 08:12:03 | test traffic |
| 08-10 12:36:29 / 12:50:55 / 14:38:22 / 14:52:51 / 15:03:18 | fixture ×5 | fixture | 6 forwards (1 pre-kill Make duplicate) | test traffic |
| **08-10 15:30:20** | **pii-6389984a@example.invalid** | **YES — the only organic email reply in 5 days** | **LOST**: no forward, no CRM write, no team alert | **P0-1** (`Body Reply Alert` ReferenceError) — **fixed 08-10 16:06Z, verified 08-11 10:15Z** |
| 08-11 10:14:32 | fixture | fixture | forwarded 10:15:15Z, **`Reply Alert ok:true`** ts `1786443306.928119` | the P0-1 verification fire |

### Attribution roll-up — "already fixed" vs "new hole"

| cause | replies affected | status |
|---|---|---|
| WF-1 per-lead alert registry (`__alerted_v1`, one alert per lead ever) | **6 of 9 LinkedIn** | **by design** — and the single biggest reason Melisa sees nothing. Needs a product decision, not a fix |
| Channel misrouting (alerts land in `C0B8GCVNR5W`) | 2 of 9 | switch deployed 08-10 10:32Z, **still unproven**; email alerts not switched at all |
| Vaughn-class event-name gap | 1 of 9 | known, 2% of profiles, backfilled |
| Label wiper (Zaps) | 2 of 9 (Malachi, Lucas) | **zaps off 08-10 16:11–16:12Z; both leads repaired 08-11 09:47–09:49Z** |
| P0-1 `Body Reply Alert` crash | 1 email (Marine) | **fixed + verified on the wire** |
| **UNKNOWN** | **0** | — |

---

## 3. The dark window — confirming Melisa's anchor

**`#lead-processing` (C07LTD8UT70) has been dark from 2026-08-05T11:14:25Z to now — 6 days.**

- Last post of any kind: Zapier Bot, 2026-08-05T11:14:25Z (Person-e1593f4e) — **14 minutes before**
  zap `274357187`, the only Slack-posting zap, was paused at 2026-08-05T11:28:42Z by
  `mykyta@janeasystems.com`. Her anchor matches the wire exactly.
- **Zero n8n posts, ever.** The n8n bot joined the channel only on 2026-08-10T11:06:14Z.
- Re-read at 2026-08-11T10:50Z: **still empty.** WF-1's config is correct
  (`slack_channel_replies = C07LTD8UT70`), but the only reply since the switch was alert-suppressed
  (row 9 above), so nothing has exercised it.
- **Email alerts are still not switched:** WF-2 uses `slack_channel_replies = C0B8GCVNR5W`, and
  `slack_channel_replies_at_flip = C07LTD8UT70` is read by no node.

---

## 4. State changes since the Phase 2 report (18 h)

| item | then (08-10 16:30Z) | now (08-11 10:50Z) |
|---|---|---|
| P0-1 `Body Reply Alert` | deployed, unproven | **VERIFIED** — exec 15193, `Reply Alert ok:true` ts `1786443306.928119`, forward on the Smartlead wire 10:15:15Z, `__alert_delivered` registry now 1 row |
| **P0-1b dedupe claim-after-success** | not shipped | **STILL NOT SHIPPED** — `if (!duplicate) store.wf2_seen[key] = nowSec` present at versionId `70e3ec4e` (10:34:52Z) |
| Marine's dedupe key | stuck | **still stuck** in `wf2_seen`; 48 h TTL expires ≈ 2026-08-12T15:30Z |
| P0-2 WF-2S | blind (oldest-500 `/statistics`) | **PATCHED 06:34:03Z** — now reads `/campaigns/{id}/leads-statistics`, paginates (`__pages: 5`), `__sent_seen_v2` **1 → 15 rows**, and delivered **9 real SENT events** at 08:17:16–19Z (nvidia, netflix, aa.com, deque, …) |
| Ai4 campaigns | all 4 PAUSED | **all 4 ACTIVE again**; 3756410 now COMPLETED |
| Fixture lead `72ec85c0` | Responded, live | **Responded stripped, archived** (09:45:31Z) |
| Fixture Handover 43974 | open in Melisa's queue | **done=True** |
| Smartlead fixture lead | not suppressed | **still `is_unsubscribed: false`, still in campaign 3686187 — which is ACTIVE again** |
| Estate | 16 workflows | **19** — see below |

### New workflows (all created 2026-08-11) — two wiring items, no corruption risk today

- **`dnc_projections_sweep` (8qVXtI2ez5o6a9hc) — ACTIVE, 35 nodes, created 10:32:27Z.** Contains
  `PD Write DNC Field`, `PD Patch Lead Labels`, `SL Unsubscribe`. **Safe as configured:**
  `MODE=dev`, `FIRE_PIPEDRIVE=false`, `FIRE_SMARTLEAD=false` gate both write branches, and
  `Send Guard` hard-fails if dev posts outside the test channel. **`PD Label Union` genuinely
  unions** (reads `label_ids`, appends the DNC label if absent) — the correct pattern, and the
  opposite of what the Zaps did.
- **`zz_probe_cred_verify2` (IwoVtg6YtDhuvKug) — ACTIVE probe, 3 nodes.** A test artifact left live.
- `dnc_wf4_sheet_intake` (bluGflKaUI3bGodQ) — inactive, Google-Sheets trigger.
- **All three carry `errorWorkflow: "REPLACE_CORE__ErrorHandler_ID"` — the placeholder string, not a
  workflow id.** Exactly the Phase 2 §2 landmine, now on an ACTIVE workflow that can patch labels and
  unsubscribe people. Fix before either FIRE flag is ever flipped.

---

## 5. Melisa-ready summary

> **What was broken**
>
> 1. **LinkedIn outreach stopped after Aug 6.** Both campaigns were paused; the last connection
>    request went out 2026-08-06T10:09Z and the last follow-up message 23:31Z that evening. This was
>    **not** a LinkedIn login problem — all four sender accounts still have valid LinkedIn and Sales
>    Navigator sessions. **2 people accepted a connection after that and never got a follow-up**, and
>    **1,039 leads are sitting mid-sequence** waiting for a next step that cannot fire while the
>    campaigns are paused.
> 2. **Replies did reach Pipedrive — but almost none reached Slack.** Of the 9 LinkedIn replies since
>    Aug 7, **8 were written to the CRM correctly**. Only **2 produced a Slack notification, and both
>    went to an ops channel, not `#lead-processing`** — which has had **no reply notification since
>    Aug 5, 11:14Z**, when the Zap that used to post them was switched off. So the CRM was mostly
>    fine; the notification path was dark. That is why it looked like replies vanished.
> 3. **One email reply was genuinely lost** — Person-d05f9f74 (Airgas), Aug 10 15:30Z. A code defect
>    deployed 20 minutes earlier killed the whole reply path. It was an out-of-office autoresponder,
>    so nothing was actually missed commercially, but the mechanism would have destroyed a real one.
>
> **What is already fixed**
> - The reply-path crash: fixed Aug 10 16:06Z and **proven end-to-end** Aug 11 10:15Z (alert posted,
>   forward sent).
> - The label wiper that was quietly stripping "3. Responded"/"4. Positive Reply": the four Zapier
>   automations responsible were switched off Aug 10 16:11Z, and **all 11 affected leads — including
>   Malachi Bierstein and Person-c9bb6bd1 — were repaired Aug 11 09:47–09:49Z.**
> - The blind SENT pipeline (why new sends were not creating Pipedrive leads): patched Aug 11 06:34Z;
>   real send events started flowing at 08:17Z.
> - Person-0ee7dfb2's missed reply: backfilled Aug 10.
>
> **What is being repaired / decided today**
> - **Restarting LinkedIn**: 2 accepted connections need a follow-up now; 1,039 frozen leads resume
>   when the campaigns are un-paused.
> - **Where reply alerts should land.** WF-1 is pointed at `#lead-processing` but has not yet had a
>   reply that wasn't suppressed, and **email alerts still go to the ops channel**. Also: WF-1 sends
>   **one alert per lead, ever** — six of the nine replies were suppressed by that rule alone. That is
>   a deliberate design choice and it needs a decision, not a bug fix.
> - One test lead is still sitting in a live Smartlead campaign and should be suppressed.
>
> **Nothing in her report was unexplained.** Every miss maps to a known, identified defect.

---

## Coverage limits

1. HeyReach exposes no `pausedAt` / `deactivatedAt`, so the pause **actor** is not provable — only
   its effective time (2026-08-07T00:00Z) and that auth was never the cause.
2. Melisa's screenshot was not seen. The "Aug 7 07:26" send is contradicted by both clocks; identify
   the field before answering her on that specific point.
3. Pipedrive returned sustained `429 Too many requests` during this sweep (other sessions are writing
   heavily); every affected read was retried with backoff, and Vaughn's lead needed a second pass.
   Nothing was reported from a failed read.
4. n8n data tables remain unreadable via the public API — DNC ledger rows still uninventoried.
5. Window closes 2026-08-11T10:50Z. WF-2 was redeployed at 10:34:52Z, three seconds before one of my
   reads; anything after that is outside this report.
