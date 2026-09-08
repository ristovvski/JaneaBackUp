# Reply-gap investigation — "reply exists but digest showed 0"

**Trigger case:** Ashwin/Person-6f447c29 `<pii-280f963f@example.invalid>` → `pii-72aef0b6@example.invalid`,
campaign `[Events Visiting] AI4 2026 - Rune - Catch-alls` (3686193), Wrong Person class.
**Date:** 2026-08-06. **Mode:** read-only throughout. No fix deployed.

---

## Step 1 — Smartlead: the reply is real

Confirmed on three independent Smartlead surfaces:

| surface | evidence |
|---|---|
| `/campaigns/3686193/statistics` | seq 3 row, `reply_time = 2026-08-05T06:08:38.000Z`, `lead_category = "Wrong Person"` |
| `/leads?email=pii-280f963f@example.invalid` | `lead_campaign_data[0].last_reply_at = 2026-08-05T06:08:38+00:00`, `lead_category_id = 7` |
| `/campaigns/3686193/leads/4214227144/message-history` | inbound message `from: pii-280f963f@example.invalid`, after 3 SENT steps |

`lead_category_id 7` maps to `Wrong Person` in WF-2's own `category_map` — matches the reported
"I am not Aniruddha" content. **The reply exists. 06:08:38Z is exact.**

## Step 2 — WF-2: no execution fired, because WF-2 was still dead

n8n execution record for WF-2 (`jp7rum9Z0YDJkQWv`) around the event:

```
2026-08-04T14:30:25.417Z  crashed  13391   <- OOM crash cluster #1
2026-08-04T14:30:27.170Z  crashed  13396
                                            <<< 973-minute gap, ZERO executions of any status
2026-08-05T06:42:59.041Z  success  13549   <- first execution back (my own probe, see below)
2026-08-05T07:00:12.467Z  crashed  13552   <- OOM crash cluster #2
2026-08-05T07:00:13.441Z  crashed  13555
2026-08-05T09:03:05.924Z  success  13579   (probe)
2026-08-05T10:57:16.514Z  success  13661   (probe)
```

Executions within ±30 min of 06:08:38Z: **0**. The reply landed 16h into the dead window and
**34 minutes before** WF-2 came back.

An inactive n8n workflow's production webhook returns 404 and creates **no execution record at
all**. So this is not "an execution that failed" — there is nothing to retry, nothing to inspect,
and no error anywhere in n8n. The event was dropped at the door.

### The gap, named

**WF-2S is SENT-only.** It reconciles Smartlead campaign statistics for SENT events over a
lookback window. It has no equivalent mechanism for REPLY events. SENT events lost to an outage
are recoverable by the stats-poll reconciler; **reply events lost to an outage have no recovery
path whatsoever.** This is the cause here, and it is a structural hole, not a one-off.

### Verification note on the post-recovery executions

13549 / 13579 / 13661 all show `user-agent: Python-urllib/3.12`, `cf-connecting-ip 91.217.61.179`,
`cf-ipcountry: UA` — they are **my own probes**, not Smartlead traffic. They ran `Verify Secret →
Normalize → Dedupe` and produced zero Shadow Log rows.

Consequence: **there is no positive control.** Smartlead sent nothing on 08-05/08-06 (SENT counts
below), so no real reply has traversed the WF-2 webhook since recovery. "Replies work again" is
currently **unproven**, not proven.

```
Smartlead events per day, all 4 campaigns
2026-08-03   SENT 3     REPLY 1
2026-08-04   SENT 836   REPLY 10
2026-08-05   SENT 0     REPLY 1     <- Ashwin
2026-08-06   SENT 0     REPLY 0
```

## Step 3 — why the digest said 0

`c1_daily_reports.py:142`:

```python
reply_execs = set(e["_exec"] for e in ent
                  if str(e.get("event", "")).lower().startswith(("repl",)))
...
wf2_report.append({... "replies": len(reply_execs), ...})
```

`ent` is built exclusively from **WF-2 execution payloads** — entries emitted by WF-2's own
`Shadow Log` node (`c1_daily_reports.py:127-136`). So the figure is:

> "how many replies **we processed**"

not

> "how many replies **exist**".

When the webhook never delivers, there is no execution, no Shadow Log row, and the digest prints
`replies: 0` — **truthfully reporting our own processing, and structurally incapable of noticing
that anything was missed.** The digest is honest and blind at the same time. A total outage and a
genuinely quiet day render identically.

### Proposed fix (NOT deployed — awaiting your word)

Count both sides and publish the delta:

```
Replies (24h) — Rune-Catch-alls:  Smartlead 4  |  WF-2 processed 1  |  DELTA 3  ⚠
```

Design points that the evidence forces:

1. **The Smartlead side must come from `/campaigns/{id}/leads-statistics` → `history[]` entries
   with `type == "REPLY"` — not from `/campaigns/{id}/statistics.reply_time`.** Measured on this
   window: `statistics.reply_time` yields **8** replies, `leads-statistics history[]` yields
   **12**. The former collapses repeat replies onto one row per sequence step and additionally
   missed two first-replies outright (`pii-6f8f48e5@example.invalid`, `pii-135b4c7b@example.invalid`). Building the
   "source of truth" number from the obvious endpoint would under-report by 33% and hide exactly
   the kind of gap this alarm exists to catch.
2. **Delta > 0 is an alarm, not a stat line** — it should be visually flagged and, ideally, posted
   to ops rather than folded into the routine digest body.
3. **Delta = 0 with Smartlead = 0 is not "green"** — it is "nothing to measure". Today's numbers
   would show `0 | 0 | 0` and look perfect while the reply path remains untested. The digest
   should say `no traffic — path unverified` for that case rather than a reassuring zero.
4. Cheap and worth adding at the same time: a line for **last real (non-probe) inbound webhook
   received**. Today that would read `2026-08-04T14:15Z` — 45 hours ago — which is the single most
   informative number available right now.

## Step 4 — full 48/72h sweep: every reply vs. what WF-2 processed

Window 2026-08-03T11:24Z → 2026-08-06T11:24Z, all 4 email campaigns. Truth-set = union of both
Smartlead reply surfaces (12 REPLY events across 10 distinct leads). Processed-set parsed from
WF-2 `Shadow Log` rows — the same source the digest counts, so "processed" means exactly what the
digest means.

| reply time (UTC) | campaign | lead | class | WF-2 |
|---|---|---|---|---|
| 2026-08-03T16:54:19 | Mario-Valids | pii-0ddf11ef@example.invalid | Meeting Request | processed |
| 2026-08-04T06:22:35 | Mario-Valids | pii-0ddf11ef@example.invalid | (2nd reply) | processed |
| 2026-08-04T15:10:03 | Rune-Catch-alls | pii-67425a37@example.invalid | Out Of Office | **MISSING** |
| 2026-08-04T16:15:03 | Mario-Valids | pii-b02b50cf@example.invalid | Out Of Office | **MISSING** |
| 2026-08-04T16:31:45 | Rune-Catch-alls | pii-6f8f48e5@example.invalid | — | **MISSING** |
| 2026-08-04T16:38:45 | Rune-Valids | pii-135b4c7b@example.invalid | — | **MISSING** |
| 2026-08-04T16:38:45 | Mario-Catch-alls | pii-90ec4caf@example.invalid | Out Of Office | **MISSING** |
| 2026-08-04T16:55:41 | Mario-Valids | pii-567b1851@example.invalid | Interested | **MISSING** |
| 2026-08-04T17:04:26 | Mario-Catch-alls | pii-06275333@example.invalid | Out Of Office | **MISSING** |
| 2026-08-04T17:15:19 | Mario-Valids | pii-567b1851@example.invalid | (2nd reply) | **MISSING** |
| 2026-08-04T19:10:59 | Mario-Valids | pii-7b1c0e1a@example.invalid | Not Interested | **MISSING** |
| 2026-08-05T06:08:38 | Rune-Catch-alls | pii-280f963f@example.invalid | **Wrong Person** | **MISSING** |

**12 replies exist. WF-2 processed 2. 10 missing — and the boundary is exact:**

| zone (vs. the dead window) | replies | missing |
|---|---|---|
| before 2026-08-04T14:30:27Z | 2 | 0 |
| inside dead window | 10 | **10** |
| after 2026-08-05T06:42:59Z | 0 | 0 |

Every single miss is inside the outage and every reply outside it was processed. That clean split
is the strongest available evidence that the cause is the outage rather than a reply-path logic
defect — while also being the reason the "after" row is empty and the path stays unproven.

## Step 5 — what Make actually did (this contradicts the brief)

Make scenario **8557478** `New_If Campaign gets a response, update lead with "responded" label` —
`isActive: true`, `scheduling.type: "immediately"`, `hookId: 3819933`. It is **instant/webhook
triggered**, so its run count equals webhook deliveries received. Log pulled complete for the
window (59 entries spanning 2026-07-03 → 2026-08-04).

Runs in the last 72h: **4 total.**

```
2026-08-03T16:54:53Z  ops=19    <-> richard.spitz reply 16:54:19  (+34s)
2026-08-04T16:56:12Z  ops=21    <-> jonathan.brum reply 16:55:41  (+31s)
2026-08-04T19:11:33Z  ops=19    <-> john.teuber   reply 19:10:59  (+34s)
2026-08-04T22:01:15Z  ops=16    <-> no reply in either Smartlead surface at that time (unexplained)
```

**There is no Make run at or after 2026-08-05T06:08:38Z. Make's most recent run of any kind is
2026-08-04T22:01:15Z — 37 hours ago. Make did not process the Ashwin reply either.**

Independent confirmation from the CRM side — Pipedrive lead labels for each affected lead:

| lead | `3. Responded`? | lead `update_time` | handled? |
|---|---|---|---|
| richard.spitz (control, pre-outage) | yes | 2026-08-03T18:36:42Z (after reply) | **yes** |
| jonathan.brum | yes | 2026-08-05T08:11:04Z (after reply) | **yes** |
| hwang | yes | 2026-07-21T20:38:19Z (**before** reply) | no — label predates this reply |
| lauren.desalvo | no — `1. Cold` only | before reply | no |
| stephen.bostwick (2 leads) | no — `1. Cold` only | before reply | no |
| mrudu | no — `1. Cold` only | before reply | no |
| tim.riley | no — `1. Cold` only | before reply | no |
| nitin.tikku | no — `1. Cold` only | before reply | no |
| john.teuber | **person has 0 leads** | — | no — Make ran but had no lead to label |
| **adeshpande (Ashwin)** | **no — `1. Cold` only** | 2026-07-21T18:48:46Z, before reply | **no** |

Corroborating: `jonathan.brum` person #83648 has a changelog row `org_id` at 2026-08-04T16:56:15Z
with `change_source = api`, `user_agent = Make/production` — hard proof Make handled that one.
Ashwin's person #83606 has **zero changes of any kind after the reply**.

### Verdict on step 5

**The premise "Make handled it meanwhile, so nothing is lost for the business" is false.**

- Of 10 distinct leads that replied in the window, **1** got automated responded-handling
  (jonathan.brum, by Make).
- **8 leads sit at `1. Cold` with a real reply against them**, including an `Interested`-class and
  a `Not Interested`-class reply.
- `john.teuber` exposes a second, independent defect: Make fired but the person has **no lead at
  all**, so there was nothing to label — the known Make lead-creation defect class, not an
  outage symptom.
- **Ashwin's reply is unhandled by every system: no WF-2 execution, no Make run, no Pipedrive
  change, no responded label, no forward.** A "wrong person" signal on a Netflix contact is
  sitting only in the Smartlead inbox.

Make was **never a safety net during this outage** — it depends on the same Smartlead webhook
delivery that WF-2 depends on, and it received only 3 of the 12 reply events. The redundancy
assumed in the flip plan does not exist.

---

## What this means for Friday's flip

1. **The flip checklist's "Make stays ON as the safety net" assumption is disproven.** Make
   received 3 of 12 reply webhooks in this window. Running both systems in parallel does not make
   reply handling redundant — both consume the same fragile delivery and both go blind together.
2. **The reply path is currently unverified end-to-end.** Zero real Smartlead traffic has reached
   WF-2 since 2026-08-04T14:15Z. Flipping on an untested path is exactly the "gated path is
   unproven until it runs ungated" trap. A flip pre-check should require **≥1 real inbound reply
   observed end-to-end post-recovery**, not just green statics.
3. **The OOM ceiling remains the top flip blocker, and its blast radius is now measured**, not
   theoretical: 16.2 hours dead, 10 replies permanently lost, no recovery path. The same instance
   hosts WF-1 in live production.
4. **A reply reconciler is missing.** WF-2S covers SENT; nothing covers REPLY. Until that exists,
   any WF-2 outage silently destroys reply events. This belongs on the checklist as a
   pre-flip item, not a post-flip nice-to-have.
5. **The digest cannot be trusted as an outage detector in its current form** and should not be
   used as the flip-day health signal until it shows Smartlead-vs-processed with a delta.
6. **Backfill decision needed (not taken):** 8 leads carry unhandled replies from 2026-08-04/05,
   one of them `Interested`. That is a business-visible queue, separate from the flip.

## Open items / limits of this investigation

- Make's per-run bundle detail is **not reachable via the API** (`/scenarios/{id}/logs/{execId}`
  and `/scenarios/{id}/executions/{execId}` both fail; `/dlqs` rejects the org-level call and
  404s at scenario level). Run-to-lead attribution above is by timestamp correlation plus
  Pipedrive `Make/production` changelog evidence, which is strong but not the same as reading the
  bundle. The 2026-08-04T22:01:15Z run remains unattributed.
- `pg[limit]=100` on Make's `/logs` silently returns an empty list; 50 works. Paged at 50.
- No post-recovery real reply exists, so the reply path's health after recovery is untested.

## Artifacts

- `ashwin_sweep_v3.py` / `.out.log` / `wf1-release-evidence/ashwin_sweep_v3.json` — 72h sweep,
  parsed cross-reference, zone classification
- `ashwin_control_and_make.py` / `.out.log` / `...json` — post-recovery control, SENT volume,
  Make scenario inventory + run history
- `ashwin_verify_v4.py` / `.out.log` — dual-source reply truth-set, post-recovery execution
  node-level inspection
- `ashwin_verify_v5.py` / `.out.log` / `...json` — Make trigger type + full log span, Pipedrive
  person changelog impact
- `ashwin_verify_v6.py` / `.out.log` / `...json` — lead-label business impact
- superseded: `ashwin_wf2_deadwindow_sweep_v2.py` (used a substring-over-blob cross-reference;
  v3 reproduces its result with parsed fields)
