# 2026-08-31 — Smartlead silence (read-only) + bounce detection (fix)

Two tasks from Nik, in order. Backups: `audit-artifacts/wf_backups_2026-08-31/`.

## TASK 1 — Smartlead silence: **(a) sending genuinely has not resumed.** Nothing is broken.

WF-2's last execution of any kind is `37558` at `2026-08-28T19:30:44Z`. That execution was **not
Smartlead traffic** — it was our own WF-2R replay (`__reconciled: true`,
`__reconciled_by: "WF-2R"`, from n8n's egress `4.182.88.118`, `axios/1.18.0`) and it was deduped
at `NoOp Duplicate`. The last genuine inbound was earlier the same day.

### (a) Sending — the answer

| | 3868449 Valids | 3868450 Catch-alls |
|---|---|---|
| status | ACTIVE | ACTIVE |
| `sent_count` | 48 | 37 |
| `campaign_lead_stats.total` | 48 | 37 |
| `notStarted` | 0 | 0 |
| `inprogress` | 46 | 36 |
| `drafted_count` | 138 (= 46 × 3) | 108 (= 36 × 3) |
| `bounce_count` | 1 | 0 |

* All 85 sends landed in **one 65-minute burst**: earliest `sent_time`
  `2026-08-28T11:02:35.708Z`, latest `2026-08-28T12:07:31.372Z`.
* **Zero stat rows exist with `sent_time` after that.** Not "after 19:30" — after 12:07.
* **Sequence step 2 has `delayInDays: 7`.** Step 1 went out 28 Aug, so step 2 is not due until
  **~4 Sep**. Steps 3 and 4 are +5 and +6 days after that.
* All **44 sending mailboxes are healthy**: `is_smtp_success` and `is_imap_success` true on every
  one, warmup ACTIVE, 20/day each (880/day of unused capacity). No SMTP or IMAP failure strings.

`drafted_count` being exactly `inprogress × 3` is the tell: every lead has had step 1 and is
waiting on the 7-day gap. There is nothing to deliver, so there is nothing to webhook.

### (b) Webhook subscriptions — **could not be verified, and that is not the same as "missing"**

`GET /campaigns/{id}/webhooks` returns `[]` for **every** campaign I asked, including
`3756410`, `3686187` and `3868449` which have all demonstrably delivered events into WF-2. So the
endpoint is uninformative here, not evidence of a missing subscription — Smartlead's per-campaign
webhook API does not reflect however these are actually configured. Verifying the destination URL,
active flag and event types needs the Smartlead UI, which I do not have. Reporting that plainly
rather than reading `[]` as zero. No delivery log or failure counter is exposed in the public API.

### (c) Our endpoint — not rejecting

n8n's webhook layer is serving normally on the same instance: `dnc_pre_add_gate` accepted and
answered a POST at `07:15:57Z`, minutes before this check, and every 15 minutes before that.
WF-2 is ACTIVE with its webhook registered. Nothing rejected anything.

### Gap quantification

Not applicable, and not because I skipped it: Smartlead created **0** stat rows after
`2026-08-28T12:07:31Z`, so there is no Smartlead-side event that Pipedrive should have received.
The gap is zero by construction, not by assumption.

**What to watch:** the real test is **~4 Sep**, when step 2 fires. If nothing reaches WF-2 that
day, the subscription question becomes live and needs the UI.

## TASK 2 — bounce detection: **deployed, 62 statics green**

### What was actually wrong

Smartlead delivers every bounce **twice**. Proved on Person-a9a7d542:

| exec | time (UTC) | `event_type` | bounce fields | Normalize | path |
|---|---|---|---|---|---|
| 35046 | 11:24:33 | `EMAIL_BOUNCE` | `is_bounced`, `is_sender_originated_bounce`, `bounce_message`, `bounce_reply_*` | `BOUNCED` | bounce branch, silent — correct |
| 35131 | 11:45:42 | `EMAIL_REPLY` | **none at all** | `REPLIED` | full reply path |

On the second copy `Body Lead Labels Union` computed
`__label_union = [cold, connected, RESPONDED]`. The PATCH was skipped **only** because
`__lead_id` was null. His lead was created 95 minutes later by the Finovate backfill.

### WF-2 — `d33b4c8a`, 161 → 164 nodes

Three independent signals in `Normalize`, any one wins, bounce is never a reply:

* **(a)** `/bounce/` on the event name — kept.
* **(b)** any bounce marker in the body regardless of `event_type`: `is_bounced`,
  `is_sender_originated_bounce`, `bounce_message`, and any `bounce_reply*` key with a non-empty
  value. (Those keys contain "reply" — reading them as *reply* evidence is the documented trap;
  reading them as *bounce* evidence is the point.)
* **(c)** recent-bounce memory keyed `email|campaign_id`, window
  `CONFIG.bounce_dup_window_sec = 3600`. **Scoped to reply-shaped events only** — a later
  sequence-step SENT to the same address is a legitimate send and must not be swallowed.

Signal (c) is the one that catches Smartlead's second copy: it carries no markers, so (a) and (b)
cannot see it.

New graph on the BOUNCED branch:
`Switch Event [BOUNCED] → IF Bounce Duplicate → { NoOp Bounce Duplicate | Bounce Counter → B Person Search }`

* Duplicates are dropped **silently** — no alert, no label, and no *second* activity.
* `Bounce Counter` keeps a per-day deliverability count bucketed by sending inbox and by
  recipient domain in static data, 30-day bounded. No Slack, no CRM write.
* `event_alias` is suppressed when we reclassify — otherwise `email_reply` vs canon
  `email_bounced` would fire `Ops Warn Event Alias` on every duplicate, re-creating the noise.

Two **second locks**, both currently unreachable, added so a future rewire cannot re-open the path:

* `First Reply Gate` — `__is_bounce` forces `__should_alert = false`, reason `bounce_no_alert`.
* `Body Lead Labels Union` — a bounce targets `[cold]` only. Not `responded` (Marci's Handover
  trigger), and not `connected` either: a bounce proves no human ever saw the message.

`lead_category` is used nowhere as a signal (92% miss rate), and there is a static asserting it.

### WF-2R — `7d31f745`, 23 → 25 nodes

**The spec as written could not be implemented**, and the reason matters. WF-2R polls
`/campaigns/{id}/leads-statistics`, which — verified across 501 rows / 7 campaigns — has:

* **no `is_bounced` field** (row keys: `created_at, email_lead_map_id, from, history,
  last_seq_num, lead_id, status, to`), and
* **no `BOUNCE` history type** (vocabulary is exactly `SENT` 1380, `REPLY` 41, `FORWARD` 13).

Kyle's bounce is recorded there as `history.type = "REPLY"`, 3 seconds after the SENT, sharing its
`stats_id`. So WF-2R has always been able to replay a bounce as a reply, and the live-webhook
detection cannot help a replay (no markers, and hours old, so the memory window has passed).

`is_bounced` lives on `/campaigns/{id}/statistics`, which joins back by `stats_id` — verified
exact on Kyle (`e08a9551-215f-417b-b821-30f8e754addc` on both endpoints). That endpoint accepts
`?email_status=bounced`, and its `total_stats` equals `analytics.bounce_count` on **7/7** campaigns
sampled (0, 0, 1, 5, 5, 6, 53), every row with `is_bounced === true`.

New: `IF Have Campaign → SL Bounced Stats → Bounced Stats Index → SL Leads Statistics →
Find New Replies`. `Find New Replies` drops REPLY entries matching a bounced `stats_id` **or** a
bounced address, counted as `__bounces_excluded`.

**Fails closed on purpose.** If the index cannot be *proved* complete (`rows >= total_stats`), the
cycle replays nothing and reports itself via `Idle Eval`. The two outcomes are not symmetric: a
reply held one cycle is recovered on the next (the seen-registry is written only for accepted
replays), whereas a bounce replayed as a reply writes `3. Responded` onto a dead mailbox and fires
Handover.

### WF-2S — `3865f8b3`, no graph change

WF-2S filters `history.type === 'SENT'` and emits `event_type: EMAIL_SENT`; it cannot produce a
reply, so requirement 2 is already satisfied there — stating that rather than adding unused code.
What it did need is a guard against a footgun WF-2's new signal (b) creates: because (b) is
absolute, enriching this envelope from a `/statistics` row later would reclassify **every**
reconciled SENT as a bounce and no lead would ever be created from one again. `Build SENT Payload`
now strips bounce keys explicitly rather than merely not adding them.

### Statics — 62/62

Run the **actual deployed jsCode** out of the patched workflow JSON inside a stub n8n environment
(`scratchpad/patch/statics_bounce.js`, `statics_wf2r.js`, `statics_wf2s.js`), with fixtures copied
from live payloads and live API responses, not invented.

* WF-2 31/31 — marker+REPLY → silent · duplicate → dropped · outside window → not a duplicate ·
  later SENT not swallowed · real reply unchanged and still alerts · bounce on an existing lead →
  no Responded, no Connected, no alert, no PATCH · counter buckets · `lead_category` alone is not
  a bounce.
* WF-2R 27/27 — index built and proved · bounce excluded, real reply survives · no bounces → both
  replay · three failure shapes all fail closed and all report · ordinary idle stays silent.
* WF-2S 4/4 — bounced address still replays as a real SENT, no marker can ride along.

## LIVE VERIFICATION — WF-2R, both paths

**Empty index** — exec `39334`, 07:45:21Z, campaign 3868450 (`bounce_count: 0`):
`SL Bounced Stats` returned `total_stats: 0`; index `ok=true complete=true total=0`;
`SL Leads Statistics` still scanned its 37 leads downstream, so inserting two nodes ahead of it
did not break its `$json.campaign_id` reference; `__bounce_index_blocked: false`; the cycle ended
at `NoOp Idle Clean` — silent, no new noise.

**Non-empty index** — exec `39342`, 08:00:21Z, campaign 3868449 (`bounce_count: 1`):

```
SL Bounced Stats     total_stats: 1
  row  stats_id      e08a9551-215f-417b-b821-30f8e754addc
       lead_email    pii-febd7426@example.invalid
       is_bounced    true
Bounced Stats Index  ok=true complete=true total=1
       __bounced_stats_ids   ["e08a9551-215f-417b-b821-30f8e754addc"]
       __bounced_emails      ["pii-febd7426@example.invalid"]
```

The index populates live with exactly the right row, and the `stats_id` is the same one the
`/leads-statistics` history entry carries — the join holds against the real API, not just the
fixture.

## OPEN

* **`__bounces_excluded` is still 0 on live data, and that is expected, not a pass.** On exec
  39342 both REPLY history entries (Kyle's bounce echo and Catheryn's real reply) were counted
  `__stale: 2` — they are ~3 days old against `lookback_minutes: 2880` (48h), and the cutoff check
  runs before the bounce filter. So the exclusion *counter* has not yet fired on real data; only
  the statics cover that arm. The index it depends on is proven.
* No live bounce will exist to exercise WF-2 end-to-end until Smartlead resumes sending (~4 Sep).

