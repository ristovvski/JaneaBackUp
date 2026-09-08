# Stage 2 (part 1) — Receivers, reconcilers and the error handler

Read live from the n8n API on 2026-09-02. Every rule quoted below is in the deployed definition, not in a design doc.

Covered here: **WF-1**, **WF-2**, **WF-2S**, **WF-2R**, **WF-2H**, **WF-ERR**.
Part 2 (`02_STAGE2_DNC_AND_OPS.md`) covers the DNC registry, the gate, the capture sources and the daily/ops jobs.

---

## WF-1 HeyReach Receiver

`2jdjKM2NJr473GdA` · ACTIVE · 126 nodes · versionId `cec8f544` · last updated 2026-08-31

### Purpose
LinkedIn outreach happens in HeyReach; the business runs on Pipedrive. WF-1 is the bridge. Without it, someone would have to watch HeyReach and hand-copy every invite, acceptance and reply into the CRM. It serves Melisa first (she owns the leads and gets the reply alerts) and the sales team second (their pipeline is only accurate because this runs).

### Trigger and inputs
A HeyReach webhook, `POST /webhook/{{WEBHOOK_WF1_HEYREACH_RECEIVER}}`. Each call carries one event: the person, the campaign, the sender inbox, the conversation id, and the recent message history. Four event types are handled:

| HeyReach event | Internal name | Meaning |
|---|---|---|
| `connection_request_sent` | Invited | we sent a connection request |
| `connection_request_accepted` | M5 / Accepted | they accepted |
| `message_sent` | M6 | we sent a message in the thread |
| `every_message_reply_received` | M7 | **they replied** |

Anything else falls through to a no-op.

### What it does, step by step
1. **Refuses to process the same event twice.** A 48-hour memory keyed on HeyReach's correlation id (or, when that is the all-zeros placeholder, on event type + profile URL + timestamp + conversation).
2. **Normalises the person.** Lower-cases and canonicalises the LinkedIn URL, extracts the profile slug.
3. **Reads the campaign name for an event marker.** A campaign named `[Events Visiting] [Ai4 2026]` means "this person came from an event"; the two brackets become the person's Hypothesis and Event Name fields. One bracket, or a second bracket that is empty or longer than 60 characters, is treated as a naming mistake: the event fields are skipped and Slack gets a warning naming the campaign.
4. **Checks whether this campaign's lead was archived.** Before anything else it searches Pipedrive for an archived lead for this campaign and person. If it finds one, the whole event passes through silently — no lead, no activity, no label, no alert. Someone archived that lead on purpose.
5. **Finds or creates the organisation**, by company name.
6. **Finds the person** — by email, then by LinkedIn URL, then by HeyReach member id / public id (with a verification step so a loose match cannot bind the wrong person). Creates them if genuinely new.
7. **Moves the person's stage forward, never backward.** Stages are ranked Invited 1 → Accepted 2 → First follow-up sent 3 → Replied 4. A write only happens if the incoming stage outranks the current one.
8. **Finds or creates the lead — one lead per campaign.** The match is on the lead's Campaign field equalling the HeyReach campaign name; the title is written as `{campaign id} - {campaign name} - {full name}`, but the title is never what the match is made on.
9. **Unions the lead labels.** Labels are only ever added, never removed: rank ≥1 adds *Cold*, rank ≥4 adds *3. Responded*.
10. **Writes an activity** recording the message or reply, with the reply text (attachments and voice notes get a placeholder instead of an empty note).
11. **On a reply, decides whether to announce it** (below), and posts to the replies channel `C07LTD8UT70`.

### Systems it touches
Pipedrive (organisations, persons, leads, activities — v2 for persons/orgs/activities, v1 for leads), Slack (`C07LTD8UT70` replies, `C0B8GCVNR5W` ops, `C0BTUHSSM3K` alerts), one n8n data table (`euyostwJYfJefItC`) used as a dedupe claim log. It does **not** talk to Smartlead, HeyReach's API, or the DNC registry.

### Business rules encoded in it
- **Archived lead = ignore.** Detection requires an archived-visible search route; the ordinary lead-list endpoints cannot see archived leads at all.
- **A personal LinkedIn chat is never announced.** If the event has no campaign, it is the exec's own conversation: the CRM activity is still written so the history exists, and nothing is posted anywhere. This silence is deliberate.
- **One alert per person per campaign, and only on delivery.** The suppression key is the Pipedrive person id (falling back to the canonical LinkedIn identity), never the lead id — archiving a lead must not reset someone's alert suppression. The key is recorded *after* Slack confirms the post landed in the team channel, so a failed post cannot burn a lead's only alert. Entries expire after 90 days.
- **Labels are cumulative.** Never removed by us.
- **The follow-up task is switched off** (`create_assignment_task: false`) — another automation owns task creation.
- **"Replied to invite" vs "Replied"** is decided by whether we had sent an outbound message in the thread yet.

### Known failure modes
| Symptom | Cause | Diagnosis |
|---|---|---|
| A reply appears in Pipedrive but no Slack alert | suppression fired, or the event had no campaign | check `__alert_reason` in the execution: `already_delivered`, `manual_conversation`, `first_alert`, `no_identity` |
| Two alerts for the same person | the person could not be resolved at all (`no_identity` path fails open on purpose) | look for `no_identity` in the alert gate output |
| Labels applied to a different lead than the activity | **suspected defect** — the reply builder picks the lead whose Campaign field matches; the label step picks the *newest non-archived* lead instead. With one lead per campaign these can differ. See the questions list. |
| Nothing happens at all | duplicate suppression, or the archived-lead rule | the dedupe memory is 48h; the archived probe result is in `__ar` |
| Event Marker Warn in Slack | a campaign was renamed and no longer has two valid brackets | fix the campaign name in HeyReach; do not rename live campaigns mid-flight |

### How to safely restart or replay
There is no replayer for HeyReach. **HeyReach itself retries a failed webhook up to 5 times over 24 hours**, so a single failure usually self-heals — WF-ERR says so explicitly in its verdict table. If it does not: re-firing the same payload by hand is safe, because the dedupe memory will reject an exact repeat within 48 hours and the stage/label logic only ever moves forward. Do **not** re-run a whole campaign's history; the alert gate would announce nothing (suppression holds) but activities would duplicate.

### Dependencies
Feeds Pipedrive and Slack. Depends on WF-0 - Discovery for the field-hash constants in CONFIG. Reports failures to WF-ERR. Nothing else calls it, and it calls no other workflow.

---

## WF-2 Smartlead Receiver

`jp7rum9Z0YDJkQWv` · ACTIVE · 174 nodes · versionId `8cee9f06` · last updated 2026-08-31

### Purpose
The cold-email equivalent of WF-1, and the larger of the two because email has more failure modes than LinkedIn: bounces, unsubscribes, out-of-office, wrong-person, and replies that need reading before anyone is bothered.

### Trigger and inputs
Webhook `POST /webhook/{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}`. Four canonical events after normalisation: **SENT**, **REPLIED**, **BOUNCED**, **UNSUB**. Most traffic arrives not from Smartlead directly but as a **replay from WF-2S / WF-2R** (see the flag in Stage 1: 130 live executions vs 1,845 reconciler cycles).

### What it does, step by step
1. **Authenticates the call** and warns (rate-limited) on a bad secret.
2. **Normalises** the payload into a single shape, and **watches for unknown event aliases** — a new Smartlead event name posts an ops warning rather than being silently dropped.
3. **De-duplicates** on a 48-hour window.
4. **SENT:** if it is a nurture campaign, stop. If it is not the first email in the sequence, stop. Otherwise enrich the lead from Smartlead if the payload was thin, resolve or create the organisation, person and lead in Pipedrive, and record the send.
5. **REPLIED:** resolve the person and the lead, then
   - decide whether this is the **first reply worth announcing**, and if so post to the replies channel;
   - **classify the reply body with an LLM** (GPT, JSON-only response, minimum confidence 0.7) into one of ten categories;
   - write the category back to Smartlead;
   - if the classification says do-not-contact → unsubscribe the lead in Smartlead and apply the DNC label in Pipedrive;
   - if the category is forwardable (Interested, Meeting Request, Not Interested, Information Request) → work out which human owns that sending inbox and forward the thread to them;
   - union the lead labels and write a reply activity.
6. **BOUNCED:** resolve person and lead, write a bounce note, count it, and suppress duplicate bounces within an hour.
7. **UNSUB:** resolve person and lead, unsubscribe in Smartlead, apply the DNC label.

### Systems it touches
Smartlead (lead fetch, category write, unsubscribe, forward-email, message history), Pipedrive (orgs, persons, leads, activities, labels), OpenAI (classification), Slack (replies `C07LTD8UT70`, ops `C0B8GCVNR5W`, telemetry `C0BQM1X9ZUY`, alerts `C0BTUHSSM3K`).

### Business rules encoded in it
- **Every outward write is behind a `Gate …` node** that checks `WRITE_MODE === 'live'`. Flipping one CONFIG value turns the whole workflow into a dry run. It has been live since 2026-08-10.
- **Classification guardrail:** invalid JSON, an unknown category, or confidence below 0.7 → category `Uncategorized`, Smartlead is left untouched, and the reply is forwarded to a review address instead of an owner.
- **Do-not-contact is automatic** (`dnc_auto: true`) — a reply classified as DNC unsubscribes the lead in Smartlead and labels the Pipedrive lead. **Note: this does not write a row in the DNC registry.** See the domain doc; these are two different things today.
- **Forwarding is address-driven, not name-driven.** A large explicit map of sending-inbox addresses → owner name → owner email. An unknown inbox posts an ops warning rather than guessing.
- **Nurture campaigns are excluded** from the SENT path by campaign marker.
- **Only the first email of a sequence creates CRM records** — later steps in the same sequence do not.
- **Alerts are recorded on delivery, not on decision** — same rule as WF-1.

### Known failure modes
| Symptom | Cause | Diagnosis |
|---|---|---|
| A reply reached Pipedrive but nobody was told | first-reply gate suppressed it, or the Slack post failed | the alert-delivery registry is only written on `ok: true`; check the execution |
| Reply forwarded to the wrong person | the sending inbox is not in the forward map | look for `Ops Warn Unknown Inbox`; the map lives entirely in CONFIG |
| Everything classified `Uncategorized` | OpenAI error, or confidence below threshold | `__classify_ok: false` on the item; `Ops Warn Classify` fires |
| Person created with a missing company | the real SENT payload carries no lead data and enrichment did not run | this is the "B16" class — the enriched copy must be read, not the raw one |
| Bounce announced as a reply | Smartlead records bounces as history type `REPLY` on the stats endpoint | the reconciler keeps a bounce index to prevent exactly this |

### How to safely restart or replay
**WF-2 answers 200 before it processes, so Smartlead never retries.** Recovery is ours:
- a lost **REPLIED** is recovered by WF-2R within ~15 minutes — it only marks a reply as seen after WF-2 accepts the replay;
- a lost **SENT** is recovered by WF-2S on its next 15-minute cycle, same claim-after-success rule;
- a lost **BOUNCED** or **UNSUB** is **not** recovered by anything. There is no reconciler for those two event types.

To replay by hand, POST the same envelope to the webhook. Be aware the replay envelope is shaped **inversely** to the live webhook: on a replay, `to_email` is the lead and the lead's address must also be sent as `sl_lead_email`, or WF-2 will not identify the lead.

**Do not replay ~100 items in one burst.** A burst of that size has previously exhausted the instance's memory and left the workflow deactivated.

### Dependencies
Fed by Smartlead and by WF-2S / WF-2R. Watched by WF-2S (which alerts if WF-2 is left in a non-live write mode). Reports to WF-ERR. Calls no sub-workflow.

---

## WF-2S Smartlead SENT Reconciler

`6Y92ryBwYoy6z0Jx` · ACTIVE · 24 nodes · every 15 minutes

### Purpose
**Smartlead never sends us the "email was sent" webhook.** WF-2S is therefore not a safety net — it is the *primary* source of SENT events, and every cold-email lead in Pipedrive exists because this job ran.

### Trigger and inputs
A 15-minute schedule. Each cycle picks **one** campaign (hot campaigns three cycles for every cold one; a campaign older than 180 days counts as cold) and pages its lead statistics, 100 rows a page, up to 35 pages.

### What it does
1. Picks the campaign — resuming an unfinished walk before starting a new one.
2. Reads each lead's history and keeps entries of type `SENT` inside a 3-hour lookback.
3. Drops anything already claimed (keyed on Smartlead's `stats_id`).
4. Sorts oldest-first, takes at most **20 per run**, looks up each lead's full record, and **replays a synthetic `EMAIL_SENT` into WF-2's webhook**.
5. Marks a send as seen **only after WF-2 accepted it**.
6. Posts a report, and separately checks that WF-2H has run in the last 48 hours and that WF-2 is still in `live` write mode.

### Business rules
- **Claim-after-success.** Nothing is marked seen unless the replay succeeded — this is what makes a crash safe.
- **Continuation, not truncation.** A cycle that cannot finish a campaign records where it stopped; the next cycle resumes from exactly there. After 5 consecutive unfinished rounds it declares itself stuck and names the unscanned range.
- **20 per run** deliberately caps the burst size.

### Known failure modes
- **Silent under-scan.** The Smartlead statistics endpoint defaults to the *oldest* rows; this workflow pages explicitly, but any change to its paging can make it report "idle" while sends pile up. A cycle that reports idle every time for hours on an active campaign is the signal.
- **Stuck walk** — reported explicitly with the offset range.
- **Replay burst → out-of-memory.** The instance has been taken down by a large replay burst before; that is why `max_per_run` is 20.

### How to restart
Just let it run — the next cycle re-claims anything unconfirmed. If you must force a rescan, the claim memory is in the workflow's static data; clearing it will re-replay everything inside the lookback window, so shorten `lookback_minutes` first.

### Dependencies
Writes into WF-2. Watches WF-2H and WF-2's write mode. Watched by WF-2R.

---

## WF-2R Smartlead REPLY Reconciler

`U8Bb7Pdq7S6nzYPa` · ACTIVE · 25 nodes · every 15 minutes

### Purpose
Recovers replies the live webhook missed. Built after an outage during which replies were lost with no way to get them back.

### Trigger and inputs
15-minute schedule, one campaign per cycle, same rotation and resume logic as WF-2S. Lookback is **48 hours** (much wider than the SENT job's 3 hours, because a missed reply matters more than a missed send).

### What it does
1. Builds a **bounce index** first, from campaign statistics.
2. Pages the campaign's lead statistics for reply events.
3. **Excludes bounces.** The statistics endpoint records a bounce as history type `REPLY` — there is no bounce type there — so without the index every bounce would replay into WF-2 as a genuine reply. A replayed event carries none of the bounce markers the live webhook has, so this index is the only defence.
4. Ignores anything before a hard floor date (`2026-08-06T13:50Z`) so it can never rake up ancient history.
5. Replays at most 20 per run into WF-2 as synthetic `EMAIL_REPLY`, marking each seen only after acceptance.
6. Reports, and alerts if WF-2S has not succeeded in 90 minutes.

### Business rules
- **The replay envelope is inverted** relative to the live webhook: `to_email` carries the lead, and `sl_lead_email` must be set or WF-2 cannot identify the lead. This exact omission silenced every recovered reply until it was found.
- Bounce exclusion is mandatory, and the index must be both readable and complete before it is trusted.

### Known failure modes
- **Recovered replies that go nowhere** — the envelope-identity defect above.
- **Bounces announced as replies** — if the bounce index is unusable, the code knows it (`__bounce_index_ok`, `__bounce_index_complete`) and should say so.
- **Idle-noisy** warnings when a campaign returns nothing for a long time.

### How to restart
Same as WF-2S: it is self-healing by design. Widening `lookback_minutes` re-examines older replies; the `ignore_replies_before` floor stops it going too far.

### Dependencies
Writes into WF-2. Watches WF-2S. Watched by nothing.

---

## WF-2H Health & Digest

`nK3yIOqRcBearV8s` · ACTIVE · 9 nodes · daily 07:15

### Purpose
A once-a-day sanity check that what Smartlead thinks it sent matches what Pipedrive received, plus a data-quality read on the leads created in the last 24 hours.

### What it does
Reads active Smartlead campaigns and their statistics, reads the most recent 500 Pipedrive leads (sorted newest-first, and explicitly including archived ones), and posts a comparison to the ops channel: volume on each side, and how many new leads carry the expected Campaign / Hypothesis / Medium fields and the expected labels.

### Known failure modes
Its numbers are a *comparison*, not a reconciliation — it will not tell you *which* lead is missing. Because it reads only 500 leads, a very high-volume day can push older leads out of its window.

### How to restart
It recomputes from scratch each run; a missed day is simply late, nothing is lost.

### Dependencies
Watched by WF-2S (stale after 48 hours).

---

## WF-ERR Error Handler

`BbrXPABgOaaTJjD6` · ACTIVE · 12 nodes · error trigger

### Purpose
One place where every failure in the instance surfaces, in language an operator can act on. 34 of the 36 workflows name it as their error workflow.

### What it does
1. Fetches the failed execution in full.
2. Builds a report: which workflow, which node, whether the failing node was a **write** node (it keeps an explicit list — Person Create, Lead Create, SL Unsubscribe, Reply Activity, Replay Into WF-2, and others), and what the recovery verdict is for that source.
3. **Classifies the failure** against five known classes: paired-item defect, out-of-memory, upstream 5xx, auth, bad request — each with a written "what to do".
4. If the class is unknown, asks an LLM for a one-paragraph read.
5. **Suppresses bursts** within a 15-minute window so one storm is one message.
6. Posts to the ops channel.

### The recovery verdicts it encodes — this is the single most useful table in the estate
| Failing workflow | What happens to the lost event |
|---|---|
| WF-1 HeyReach receiver | **DELAYED** — HeyReach retries up to 5× over 24h, the event should come back on its own |
| WF-2, event = REPLIED | **RECOVERABLE** — WF-2R replays it within ~15 min; check its next report before hand-repairing |
| WF-2, event = SENT | **RECOVERABLE** — WF-2S re-claims it next cycle |
| WF-2, any other event | **LOST** — no reconciler covers it; it will not be delivered again |
| WF-2S | **SAFE** — next cycle re-claims |
| WF-2H | **DELAYED** — the digest is just late |

### Known failure modes
It cannot report on an execution that never started, and it cannot see a workflow that n8n auto-deactivated. Silence from WF-ERR is not proof of health.

### Dependencies
Every workflow except `WF-0 - Discovery` and `HeyReach — Phase 0 Payload Capture`.
