# Domain 2 — Smartlead → Pipedrive (+ DNC)

*The cold-email side, end to end. Written so someone can fix it without Nik.*
*State read live 2026-09-03.*

---

## 1. What this is for

Cold email goes out through **Smartlead**. This domain turns what happens to those emails — sent,
replied, bounced, unsubscribed — into CRM records, Slack notifications, and forwarded emails to the
right salesperson.

It is bigger than the LinkedIn side for one reason above all others:

> **Smartlead does not tell us when it sends an email.**

Most of the machinery here exists to work around that.

## 2. The pieces

| Piece | Role |
|---|---|
| **WF-2 Smartlead Receiver** (174 nodes) | does all the work |
| **WF-2S SENT Reconciler** (every 15 min) | **the primary source of "an email went out"** |
| **WF-2R REPLY Reconciler** (every 15 min) | recovers replies the webhook missed |
| **WF-2H Health & Digest** (daily 07:15) | compares Smartlead volume against Pipedrive |
| OpenAI | reads and classifies every reply |
| Pipedrive, Slack | as in domain 1 |

**The number that explains the shape:** in 20 days WF-2 ran **130** times; the two reconcilers ran
**1,899** times each. Almost everything arrives by replay, not by live webhook. **If WF-2S stops,
cold-email leads simply stop appearing in Pipedrive and nothing else will tell you.**

## 3. The flow

**An email is sent.** WF-2S notices it in Smartlead's statistics and replays it into WF-2 → WF-2
skips nurture campaigns and anything that is not the first email of the sequence → otherwise enriches
the lead, then finds or creates company, person and lead.

**Someone replies.** The reply arrives live, or WF-2R replays it within ~15 minutes → WF-2 resolves
and verifies the person and the lead → decides whether to announce it and posts to
`#lead-processing` → **sends the reply text to an LLM to be classified** → writes the category back
to Smartlead → then, by category:
- **do not contact** → unsubscribe in Smartlead **and** label the lead;
- **interested / meeting request / not interested / information request** → work out who owns that
  sending inbox and **forward them the thread**;
- anything else → no forward.
Finally it unions the labels and writes the reply activity.

**An email bounces.** Resolve person and lead → write a bounce note → count it → ignore a repeat for
the same lead within the hour. **A bounce never alerts anyone.**

**Someone unsubscribes.** Resolve person and lead → unsubscribe in Smartlead → apply the
do-not-contact labels.

## 4. The rules a human needs to know

**One switch stops all writing.** `WRITE_MODE`. Fourteen separate writes check it. Anything but
`live` makes the whole workflow a dry run. WF-2S raises an alarm if it is left that way.

**A bounce is never a reply — and Smartlead sends every bounce twice.** The second copy arrives
about twenty minutes later shaped exactly like a reply, carrying **not one** bounce field. On one
named lead the second copy ran the entire reply path, posted to `#lead-processing`, and computed a
label set containing *3. Responded* — which is the trigger for the handover automation. It was saved
only because that person had no lead yet.

Three independent signals now catch it, any one of which wins:
1. the event name says bounce;
2. the body carries any bounce marker — including the `bounce_reply_*` fields, which are bounce
   metadata that merely contain the word "reply";
3. the same address and campaign already bounced within the hour — applied only to reply-shaped
   events, so a later legitimate send is never swallowed.

Smartlead's own category is deliberately **not** a signal: it is empty on 11 of 12 real bounces.

**Who replied is not who the lead is.** The reply payload has two addresses: whoever replied, and
the campaign lead. Reading the first as the lead once made WF-2 adopt a stranger on a threaded
reply — the real lead got no label and no activity, and an alert named someone who was never a lead.
Every reply is now classed **lead / alias / third-party / ambiguous**, and alias only counts within
the same email domain.

**An unverified identity still alerts; a confirmed third party does not.** The earlier "stay quiet
when unsure" reading was wrong about which direction is safe — it ate a genuine *Interested* reply. A
missing identity field is an internal failure, and an internal failure must never eat a live reply.
The doubt is stated in the alert instead.

**Out-of-office never alerts, and never burns the alert slot.** Judged on Smartlead's own category,
which is available long before our classifier and independent of it — so an LLM outage cannot leak
auto-replies into the channel. When the human returns and replies for real, it still counts as their
first.

**Only the first email of a sequence creates CRM records.** Steps 2, 3 and 4 do not. Nurture
campaigns are excluded entirely.

**Classification has a guardrail.** Invalid JSON, an unknown category, or confidence below **0.7** →
category `Uncategorized`, **Smartlead is left untouched**, and the reply goes to a review address
rather than to a salesperson. Nobody should have to trust a classifier that just said it was unsure.

**Forwarding is by inbox address, never by name.** A large explicit map of every sending inbox to an
owner. An unknown inbox still forwards — to a default — and tells ops. **If you add a sending inbox
in Smartlead, add it to that map**, or its replies go to the default.

**Labels: the truthful pair, in one write.** Since 2026-09-02 both label paths use one shared
function:

| The reply says | The lead gets |
|---|---|
| explicit stop, or an unsubscribe | Cold + Connected + **3. Responded** + **DO NOT CONTACT** |
| not interested / wrong person / no longer there | Cold + Connected + **3. Responded** + **Disqualified** |
| interested / meeting / information request | Cold + Connected + **3. Responded** |
| out of office | Cold + Connected — **no Responded** |
| bounce | Cold — **no Responded, no Connected** |

The suppressing label must be in the **same** write as *3. Responded*, because the handover
automation fires on labels: if *Responded* landed alone first, the handover would fire in the gap.

## 5. When something looks wrong

| What you see | Usually |
|---|---|
| No new cold-email leads today | WF-2S is not running, or its campaign rotation is stuck — not a WF-2 fault |
| Replies in the CRM, nobody told | first-reply suppression, out-of-office, third-party, or a failed Slack post |
| A reply forwarded to the wrong person | the sending inbox is missing from the map — ops gets `Unknown Inbox` |
| Everything `Uncategorized` | OpenAI failing or confidence low. Replies still reach the review address; nothing is lost |
| **A bounce announced as a reply** | all three bounce signals missed it — **escalate immediately** |
| A person created with no company | the real sent payload carries no lead data and enrichment did not run |
| The workflow deactivated itself | out-of-memory, usually a large replay burst |

**The daily safety nets:** WF-2H at 07:15 compares Smartlead volume against Pipedrive; the morning
digest at 07:00 reports the same volumes plus an "emails sent with no lead" line. WF-2S watches
WF-2H; WF-2R watches WF-2S; WF-2S watches WF-2's write mode. **The watchers watch each other on
purpose** — the one gap is that nothing watches WF-2R.

## 6. Recovery — read this before touching anything

**WF-2 answers `200` before it processes. Smartlead never retries.** Recovery is entirely ours and
depends on the event:

| Lost event | Recovery |
|---|---|
| **SENT** | automatic — WF-2S re-claims it next cycle |
| **REPLIED** | automatic — WF-2R replays within ~15 minutes |
| **BOUNCED** | **none** |
| **UNSUB** | **none** |

For a sent or a reply: **wait one cycle and read the reconciler's next report before repairing by
hand.** Manual repair on top of an automatic one is how duplicates are made.

**If you replay by hand,** the replay envelope is shaped **inversely** to the live webhook: the
"to" address carries the *lead*, and the lead's address must also be supplied in the lead-email
field or the lead cannot be identified. Getting this wrong is silent — the replay succeeds and
nothing happens.

**Never replay ~100 items at once.** A burst that size has exhausted the instance's memory before
and left a workflow switched off. The reconcilers cap themselves at 20 per run; respect the same cap
by hand.

## 7. Email and the do-not-contact list

There are **two mechanisms**, and until today they did not meet.

**A. What WF-2 does now (working).** A reply classified as do-not-contact → unsubscribe in Smartlead
+ the do-not-contact label in Pipedrive. Immediate and effective for that person, in those two
tools. **It writes no registry row**, so the registry does not know about it.

**B. The registry's own route (starting today).** Rows are written by the capture sources, and
`dnc_projections_sweep` pushes them outward. **The Pipedrive leg is approved and being fired today —
about 564 rows. The Smartlead leg is approved for negative-reply and meeting rows only, pending the
exact list.**

**What protects a campaign in the meantime:**
1. asking the gate before loading a list — if whoever builds it remembers;
2. the hourly escalation detector, which cross-checks live cold campaigns against the registry and
   shouts if a protected person is in one. **It detects; it does not prevent.**

**Irreversibility.** A Smartlead unsubscribe cannot be undone through the API. Treat the Smartlead
leg as a one-way door: confirm the list first, and read back afterwards — a Smartlead call can
report success on something that did not happen.

## 8. The map

```
Smartlead ──(rarely)──► WF-2 webhook
Smartlead ◄──poll──── WF-2S ──replay──► WF-2      (SENT: the main path, 1,899 cycles)
Smartlead ◄──poll──── WF-2R ──replay──► WF-2      (REPLIED: recovery)

WF-2 ──► Pipedrive (org, person, lead, activity, labels)
     ├─► Smartlead (category, unsubscribe, forward)
     ├─► OpenAI    (classification)
     ├─► Slack     #lead-processing / ops / #alerts / #gtm-telemetry
     └─► WF-ERR    (on crash)

WF-2S ──watches──► WF-2H and WF-2's write mode
WF-2R ──watches──► WF-2S              (nothing watches WF-2R)

WF-2 ──✗──► DNC registry              (it labels and unsubscribes directly)
DNC registry ──► Smartlead            (via the projector — Pipedrive leg firing today)
```
