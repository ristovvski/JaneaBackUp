# Stage 2A — the two receivers, the reconcilers, and the error handler

Read from the live API on 2026-09-03, including the code inside every Code node.
Node names appear only where there is no other way to point at a thing.

Covered: **WF-1**, **WF-2**, **WF-2S**, **WF-2R**, **WF-2H**, **WF-ERR**.
The DNC registry, the gate, the capture sources and the ops jobs are in Stage 2B.

---

# WF-1 HeyReach Receiver

`2jdjKM2NJr473GdA` · ACTIVE · **130 nodes** · versionId `7e3e86cf` · 458 runs in 20 days, 0 errors

> Changed this morning by the concurrent session (126 → 130 nodes): the alert-delivery registry
> moved out of workflow memory into a shared table. Described as it now stands.

## Purpose
LinkedIn outreach happens in HeyReach; the business runs on Pipedrive. Without this, somebody would
watch HeyReach and retype every invite, acceptance and reply into the CRM. It serves Melisa first —
she owns the leads and receives the reply alerts — and the sales team second, because their pipeline
is only accurate while this runs.

## Trigger and inputs
A private webhook HeyReach calls on every campaign event. Each call carries one event: the person
(name, company, title, LinkedIn URL, HeyReach member id), the campaign, the sending inbox, the
conversation id, and the recent message history. Four events are handled:

| HeyReach event | Internally | Meaning |
|---|---|---|
| `connection_request_sent` | Invited | we sent a connection request |
| `connection_request_accepted` | M5 | they accepted |
| `message_sent` | M6 | we sent a message in the thread |
| `every_message_reply_received` | **M7** | **they replied** |

Anything else falls to a no-op. **The webhook answers `{"ok": true}` with HTTP 200 before any
processing begins** — that one fact drives the whole recovery story below.

## Step by step
1. **Reject a repeat.** A 48-hour memory keyed on HeyReach's correlation id, or, when that is the
   all-zeros placeholder, on event type + profile URL + timestamp + conversation.
2. **Normalise the person** — lower-case and canonicalise the LinkedIn URL, extract the profile slug.
3. **Read the campaign name for an event marker.** `[Events Visiting] [Ai4 2026]` sets the person's
   Hypothesis and Event Name.
4. **Ask whether this campaign's lead was archived.** A dedicated archived-visible search runs
   before anything else.
5. **Find or create the company**, by name.
6. **Find the person** — by email, then LinkedIn URL, then HeyReach member/public id, each with a
   verification step so a loose match cannot bind the wrong person. Create only if genuinely new.
7. **Move the person's stage forward**, never backward.
8. **Find or create the lead — one per campaign.**
9. **Union the lead's labels** and **write an activity** with the message or reply text.
10. **On a reply, decide whether to announce it**, and post to the replies channel.

## Systems touched, and what it writes
| System | Writes |
|---|---|
| Pipedrive | creates organisations, persons, leads; patches person stage + LinkedIn/company/campaign/event fields; patches lead labels; creates activities for messages and replies |
| Slack | reply announcements to the team channel; warnings to ops and alerts channels |
| n8n data table `euyostwJYfJefItC` | two kinds of claim row: the duplicate-guard, and **as of today** the alert-delivery registry |
| HeyReach | **nothing — read-only from our side** |
| The DNC registry | **nothing.** WF-1 never writes it |

## Business rules encoded
- **One lead per campaign.** Matched on the lead's Campaign field equalling the HeyReach campaign
  name — *never* on the title. The title is a convention (`{campaign id} - {campaign name} -
  {full name}`) and titles get edited by hand.
- **Stages only move forward.** Invited 1 → Accepted 2 → First follow-up sent 3 → Replied 4. A write
  happens only when the incoming rank beats the current one, so a late event cannot demote anyone.
- **"Replied to invite" vs "Replied"** is decided by whether we had already sent an outbound message
  in that thread — determined strictly, so a missing flag counts as *not* outbound.
- **Labels accumulate, never removed.** Rank ≥1 adds *Cold*; rank ≥4 adds *3. Responded*.
- **Archived lead = ignore, silently.** No lead, no activity, no label, no post anywhere. Someone
  archived it deliberately. Detecting this needs an archived-visible search, because the ordinary
  lead-list endpoints cannot see archived leads at all — and the match is confirmed **by person id**,
  never by name, because the search is term-based. *If the probe itself cannot be read, it
  deliberately does **not** block* — a real reply must never be silenced by a lookup that failed.
- **A personal LinkedIn chat is never announced.** No campaign on the event means it is the exec's
  own conversation: the CRM activity is still written so the history exists, and nothing is posted
  anywhere. The code records the ruling explicitly — *"NOWHERE… do not restore it as a quiet line
  somewhere on the assumption it was an oversight."*
- **One alert per person per campaign, claimed only after delivery.** The key is the Pipedrive person
  id, falling back to the canonical LinkedIn identity — **never the lead id**, because archiving a
  lead would otherwise reset that lead's own suppression. Legacy lead-keyed entries are still
  honoured on read so the change re-announced nothing.
- **The registry now lives in a shared table, not in workflow memory** (today's change). The reason
  is recorded in the code: *three WF-1 executions inside one second on 2026-09-01 20:50:27, two
  alerts delivered, the registry went 47 → 48 instead of 49, and one person's key was lost — she was
  announced again 27 hours later as a first alert.* HeyReach fans several events for one message into
  the same second: **28 such groups, maximum 5, and 54 true overlaps** in the retained window. This
  is routine traffic, not an edge case.
- **A hit in that table is only a hit if it looks like a stored row.** The data-table error shape is
  non-uniform — some operations return an error object, others echo the input item back unchanged,
  and the echoed item carries the key. Checking "did a row come back" would read an outage as
  "already delivered" and silence a real first reply.
- **Alert gates fail open.** If the lookup is broken, alert anyway: *a duplicate is noise, a missed
  first reply is lost revenue.*
- **The follow-up task is off** — a different automation owns task creation.
- **Event campaigns need two brackets.** One bracket, an empty second bracket, or one longer than 60
  characters skips the event fields and warns in Slack, naming the campaign.

## Failure modes — and what they look like
| What you see | What it is | How to tell |
|---|---|---|
| Reply in Pipedrive, no Slack alert | suppression, or the event had no campaign | the execution records a reason: `already_delivered`, `manual_conversation`, `first_alert`, `no_identity`, `dt_unavailable_fail_open` |
| The same person announced twice | either the fail-open path, or (before today) the workflow-memory race | reason `no_identity` or `dt_unavailable_fail_open` |
| A duplicate lead appears | the archived-lead probe could not be read, so it failed open | the probe result is recorded on the item |
| Labels on one lead, activity on another | **suspected live defect** — see below | compare the two lead ids in the execution |
| Nothing happened at all | duplicate inside 48 h, or the archived-lead rule | both are recorded on the item |
| `Event Marker Warn` in Slack | a campaign was renamed and lost its brackets | the warning names the campaign |
| Silence on a busy day | the webhook may be unregistered at HeyReach | WF-1's execution list is empty; the morning digest's HeyReach volume shows zero |

**The suspected defect, stated plainly:** on the reply path the workflow picks the lead **whose
Campaign field matches** when building the activity, and the **newest non-archived lead** when
computing labels. Under one-lead-per-campaign those are usually the same record; for a person in two
campaigns they are not. Both selections are still in the live code. Worth a targeted check against a
real two-campaign person before the presentation.

## Recovery — and what must not be retried
**A failed WF-1 event is LOST.** The webhook returns 200 before processing, so HeyReach is told the
event was accepted; its documented 5×/24 h retry only fires on a **non-2xx** response, which we never
give after a processing failure. There is no reconciler for HeyReach.

- **Repair by hand** from the HeyReach inbox, using the campaign and profile URL in the failed run.
- **Re-firing one payload is safe**: the 48-hour dedupe rejects exact repeats, stages only move
  forward, labels only accumulate.
- **Do not bulk-replay a campaign's history.** Alerts would stay suppressed (fine), but activities
  would duplicate (not fine).
- **After any Pipedrive field or label change, run `WF-0 - Discovery` by hand.** The long hex strings
  in WF-1's settings are Pipedrive field keys; recreate a field and its key changes, and WF-1
  silently stops writing that field.

## Dependencies
Needs: HeyReach's webhook registration, Pipedrive, Slack, the claims table, and `WF-0 - Discovery`
for its field keys. Needed by: nothing calls WF-1; it is the source. Reports failures to WF-ERR.

---

# WF-2 Smartlead Receiver

`jp7rum9Z0YDJkQWv` · ACTIVE · 174 nodes · versionId `9c821fcc` · 130 runs in 20 days, 0 errors

## Purpose
The cold-email counterpart to WF-1, and larger because email has failure modes LinkedIn does not:
bounces, unsubscribes, auto-replies, wrong-person replies, and replies that need reading before
anyone is interrupted.

## Trigger and inputs
Webhook `{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}`, answering 200 before processing. Four canonical events after translation:
**SENT, REPLIED, BOUNCED, UNSUB**. **Most traffic is not live** — 130 runs against 1,899 reconciler
cycles; the reconcilers replay into this same webhook and stamp the event as reconciled so the two
sources stay distinguishable.

## Step by step
1. **Authenticate**, and warn on a bad secret (rate-limited).
2. **Translate the payload** into one internal shape — every field treated as optional.
3. **Decide bounce or not** (below), then **de-duplicate**, then branch on the event.
4. **SENT** → skip nurture campaigns; skip anything that is not the first email of the sequence;
   enrich from Smartlead if the payload was thin; resolve or create company, person and lead.
5. **REPLIED** → resolve and verify the person; resolve the lead; decide whether to announce;
   **classify the reply with an LLM**; write the category back to Smartlead; if it is a stop
   request, unsubscribe in Smartlead; if it is forwardable, forward the thread to the owner of that
   sending inbox; union the labels; write the reply activity.
6. **BOUNCED** → resolve person and lead, write a bounce note, count it, suppress repeats inside an
   hour. **Never alerts.**
7. **UNSUB** → resolve person and lead, unsubscribe in Smartlead, apply the do-not-contact labels.

## Systems touched, and what it writes
| System | Writes |
|---|---|
| Pipedrive | organisations, persons, leads; lead labels; reply activities; bounce notes |
| Smartlead | reply category; **unsubscribe**; forward-email |
| OpenAI | reply classification (read-only inference) |
| Slack | replies channel, ops warnings, telemetry |
| The DNC registry | **nothing.** WF-2 marks people in Pipedrive and Smartlead directly and writes no registry row |

## Business rules encoded
- **One switch stops all writing.** `WRITE_MODE` gates fourteen separate writes; anything but `live`
  turns the whole workflow into a dry run. It has been live since 2026-08-10, and WF-2S raises an
  alarm if it is left otherwise.
- **A bounce is never a reply, and Smartlead sends every bounce twice.** The second copy arrives
  ~20 minutes later shaped exactly like a reply, carrying **not one** bounce field. Proven on one
  named lead: the second copy ran the entire reply path, posted to the replies channel, and computed
  a label set containing *3. Responded* — the Handover trigger. It was saved only because that
  person had no lead yet. Three independent signals now catch it, any one of which wins:
  **(a)** the event name says bounce; **(b)** the body carries any bounce marker — including the
  `bounce_reply_*` fields, which are bounce metadata that merely contain the word "reply";
  **(c)** the same address and campaign already bounced within the hour, applied only to
  reply-shaped events so a later legitimate send is never swallowed.
  Smartlead's own category is deliberately **not** a signal — it is empty on 11 of 12 real bounces.
- **Who replied is not who the lead is.** `to_email` is whoever replied; `sl_lead_email` is the
  campaign lead. Reading the first as the lead once made WF-2 adopt a stranger on a threaded reply:
  the real lead got no label and no activity, and an alert named someone who was never a lead. Each
  reply is now classed **lead / alias / third_party / ambiguous** — alias only within the same
  domain.
- **An unverified identity alerts; a confirmed third party does not.** The earlier "stay quiet when
  unsure" reading was wrong about which direction is safe — it ate a genuine *Interested* reply. A
  missing identity field is an internal failure, and an internal failure must never eat a live reply;
  the doubt is stated in the alert body instead.
- **Out-of-office never alerts and never burns the alert slot.** Judged on Smartlead's own category,
  available long before our classifier and independent of it, so an LLM outage cannot leak
  auto-replies. Unknown category means treat it as a real reply.
- **Bounces never alert** — enforced twice, once by routing and once by a second lock at the alert
  gate, *"so that a future rewire cannot quietly re-open the path"*.
- **Only the first email of a sequence creates CRM records**; nurture campaigns are excluded entirely.
- **Classification has a guardrail.** Invalid JSON, an unknown category, or confidence below **0.7**
  → `Uncategorized`, **Smartlead is left untouched**, and the reply goes to a review address rather
  than to a salesperson — *"nobody should have to trust a classifier that just told us it was
  unsure."*
- **Forwarding is by inbox address, never by name.** A large explicit map of sending inboxes → owner
  → email. An unknown inbox still forwards, to a default, and tells ops.
- **Labels: one PATCH, truthful pair.** Since 2026-09-02 both label paths derive their target set
  from one shared function: explicit stop → *Responded + DO NOT CONTACT*; negative reply →
  *Responded + Disqualified*; genuine interest → *Responded*; out-of-office → no *Responded*;
  bounce → *Cold* only. The suppressing label must be in the **same** PATCH, or the handover
  automation fires in the gap.
- **De-duplication keys on the instant, not the string.** The same reply arrived as
  `…+00:00` from the webhook and `….000Z` from a replay — identical moment, two keys, and in live
  mode that is a double forward and a double activity.
- **The duplicate claim is written at the success terminals, not on arrival.** Claiming up front made
  a crashed run permanently unreplayable, because the 48-hour dedupe memory outlives the reconciler's
  48-hour lookback.

## Failure modes
| What you see | What it is |
|---|---|
| No new cold-email leads today | WF-2S is not running or its rotation is stuck — not a WF-2 fault |
| Reply in the CRM, nobody told | first-reply suppression, out-of-office, third-party, or a failed Slack post |
| Reply forwarded to the wrong person | the sending inbox is missing from the map; ops gets `Unknown Inbox` |
| Everything `Uncategorized` | OpenAI failing or low confidence; replies still reach the review address |
| A bounce announced as a reply | all three bounce signals missed it — the one case to escalate immediately |
| Person created with no company | the real sent payload carries no lead data and enrichment did not run |
| Workflow deactivated itself | out-of-memory, usually a large replay burst |

## Recovery — and what must not be retried
**WF-2 answers 200 before it processes, so Smartlead never retries. Recovery is ours and depends on
the event type:**

| Lost event | Recovery |
|---|---|
| **SENT** | automatic — WF-2S re-claims it next cycle |
| **REPLIED** | automatic — WF-2R replays within ~15 minutes |
| **BOUNCED** | **none** |
| **UNSUB** | **none** |

For a sent or a reply, **wait one cycle and read the reconciler's next report before repairing by
hand** — manual repair on top of an automatic one is how duplicates are made.

Replaying by hand: the replay envelope is shaped **inversely** to the live webhook — `to_email`
carries the lead, and the lead's address must also be supplied as `sl_lead_email` or the lead cannot
be identified. Getting this wrong is silent: the replay succeeds and nothing happens.

**Never replay ~100 items at once.** A burst that size has exhausted the instance's memory before.
The reconcilers cap themselves at 20 per run; respect the same cap by hand.

## Dependencies
Fed by Smartlead and by both reconcilers. Watched by WF-2S. Uses the shared label engine. Reports to
WF-ERR. Calls no sub-workflow — in particular, **it does not call the registry writer**.

---

# WF-2S Smartlead SENT Reconciler

`6Y92ryBwYoy6z0Jx` · ACTIVE · 24 nodes · every 15 min · 1,899 runs, 1 error

## Purpose
**Smartlead never sends us the "email was sent" webhook.** This is therefore not a safety net — it
is the *primary* source of SENT events. Every cold-email lead in Pipedrive exists because this ran.

## Trigger, inputs, and what it does
A 15-minute schedule. Each cycle handles **one** campaign, then pages its lead statistics, keeps
`SENT` history entries inside a 3-hour lookback, drops anything already claimed, sorts oldest-first,
takes at most **20**, looks each lead up, and **replays a synthetic sent event into WF-2's webhook**.
It marks a send seen **only after WF-2 accepted the replay**. It then reports, and separately checks
that WF-2H has succeeded in 48 hours and that WF-2 is still in live write mode.

## Business rules
- **One campaign per cycle**, because n8n's pagination emits one item per page and an index-zip
  across a multi-campaign fan-out cannot work.
- **Resume beats rotation**, so an oversized campaign's walk always completes; after five
  consecutive unfinished rounds it declares itself stuck and names the unscanned range.
- **Hot/cold rotation** — active campaigns three cycles for every one non-active; campaigns older
  than 180 days are dropped from the cold ring, and the count that was excluded is reported.
- **An unparseable campaign list throws** rather than reporting "idle" — refusing to call a failed
  read an empty one.
- **Claim after success**, always.
- **20 per run** deliberately caps the burst.

## Failure modes and recovery
The one error in the window was a **60-second step timeout** on the campaign-picking step — n8n's
per-step limit, not a logic fault. A stuck walk is reported with its offset range. Silent
under-scan is the danger: the statistics endpoint defaults to the oldest rows, so any change to the
paging can make it report idle while sends pile up.

Recovery is to let it run — the next cycle re-claims anything unconfirmed. Forcing a rescan means
clearing its memory, which will re-replay everything inside the lookback; shorten the lookback first.

## Dependencies
Writes into WF-2. Watches WF-2H and WF-2's write mode. Watched by WF-2R.

---

# WF-2R Smartlead REPLY Reconciler

`U8Bb7Pdq7S6nzYPa` · ACTIVE · 25 nodes · every 15 min · 1,899 runs, 1 error

## Purpose
Recovers replies the live webhook missed. Built after an outage in which replies were lost with no
way to get them back.

## What it does differently from WF-2S
- **48-hour lookback** rather than 3 — a missed reply matters more than a missed send.
- **It builds a bounce index first.** The statistics endpoint records a bounce as history type
  `REPLY`; there is no bounce type there. Without the index every bounce would replay as a genuine
  reply — and a replayed event carries none of the bounce markers the live webhook has, so WF-2's
  own defences cannot help.
- **A hard floor date** stops it ever raking up ancient history.
- Alerts if WF-2S has not succeeded in 90 minutes.

## Failure modes and recovery
Its one error was also a **60-second step timeout**, on the reply-scanning step. If the bounce index
is unusable it says so on the item rather than proceeding blind. Same self-healing recovery as
WF-2S.

## Dependencies
Writes into WF-2. Watches WF-2S. Nothing watches it — the one gap in the mutual-watch arrangement.

---

# WF-2H Health & Digest

`nK3yIOqRcBearV8s` · ACTIVE · 9 nodes · daily 07:15 · 20 runs

## Purpose
A once-a-day check that what Smartlead thinks it sent matches what arrived in Pipedrive, plus a
data-quality read on the leads created in the last 24 hours.

## What it does
Reads active Smartlead campaigns and their statistics, reads the most recent 500 Pipedrive leads —
newest-first and explicitly including archived ones — and posts a comparison: volume each side, and
how many new leads carry the expected Campaign / Hypothesis / Medium fields and labels.

## Business rules, failure modes, recovery
It reports a **comparison, not a reconciliation** — it will not tell you *which* lead is missing. Its
500-lead read is a horizon, so a very high-volume day pushes older leads out of view. It cannot
observe its own failure, which is why **WF-2S watches it**; the code says it *"errored on every run
of its life and only a manual sweep noticed."* Recomputed from scratch each run, so a missed day is
late, not lost.

## Dependencies
Watched by WF-2S. **This is the workflow WF-2S guards — not the retired I-04 summary.**

---

# WF-ERR Error Handler

`BbrXPABgOaaTJjD6` · ACTIVE · 12 nodes · error trigger · 184 runs

## Purpose
One place where every failure in the estate surfaces, in language an operator can act on. 34 of the
40 workflows name it as their error workflow.

## What it does
Fetches the failed run in full; builds a report naming the workflow, the node, and whether that node
was a **write**; classifies the failure against five known classes — paired-item defect,
out-of-memory, upstream 5xx, auth, bad request — each with a written action; asks an LLM only when
the class is unknown; **suppresses bursts** within a 15-minute window, carrying forward the count it
swallowed so the next message says how many were hidden; posts once.

## The most useful thing in the estate: its recovery verdicts
| Failing workflow | Verdict shown to the operator |
|---|---|
| **WF-1** | **LOST** — no reconciler covers HeyReach; repair by hand from the inbox *(corrected 2026-09-02; it previously said the event would come back on its own)* |
| WF-2, event REPLIED | RECOVERABLE — WF-2R replays within ~15 min |
| WF-2, event SENT | RECOVERABLE — WF-2S re-claims next cycle |
| WF-2, any other event | **LOST** — no reconciler covers it |
| WF-2S | SAFE — next cycle re-claims |
| WF-2H | DELAYED — the digest is just late |

## Failure modes
It cannot report a run that never started, and it cannot see a workflow n8n auto-deactivated after
repeated crashes. **Silence from WF-ERR is not proof of health** — that is what the morning digest's
missed-schedule line is for.

## Dependencies
Every workflow except `WF-0 - Discovery` and the pre-WF-1 capture scaffolding.
