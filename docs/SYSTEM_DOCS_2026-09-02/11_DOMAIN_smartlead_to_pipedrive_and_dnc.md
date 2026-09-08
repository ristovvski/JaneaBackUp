# Domain 2 — Smartlead → Pipedrive (+ DNC)

*Written for someone who has to keep this running without asking the person who built it.*
*State as read live from n8n on 2026-09-02.*

---

## 1. What this domain is for

Cold email goes out through **Smartlead**. This domain turns what happens to those emails — sent, replied, bounced, unsubscribed — into CRM records, Slack notifications, and forwarded emails to the right salesperson.

It is bigger and busier than the LinkedIn side because email has more ways to go wrong, and because **Smartlead does not reliably tell us what happened**. Most of the machinery here exists to work around that.

## 2. The pieces

| Piece | Where | Role |
|---|---|---|
| **WF-2 Smartlead Receiver** | n8n, ACTIVE, 174 nodes | does all the work |
| **WF-2S SENT Reconciler** | n8n, ACTIVE, every 15 min | **the primary source of "email was sent"** |
| **WF-2R REPLY Reconciler** | n8n, ACTIVE, every 15 min | recovers replies the webhook missed |
| **WF-2H Health & Digest** | n8n, ACTIVE, daily 07:15 | compares Smartlead volume against Pipedrive |
| OpenAI | external | reads and classifies each reply |
| Pipedrive, Slack | as in domain 1 | |

### The one thing to understand before anything else

**Smartlead never sends us a "sent" webhook.** WF-2S polls Smartlead's statistics every 15 minutes and *replays* each send into WF-2's own webhook as if it had arrived normally. In the last 19 days WF-2 ran 130 times; WF-2S and WF-2R ran 1,845 times each. **Almost everything in this domain arrives by replay, not by live webhook.** If WF-2S stops, cold-email leads simply stop appearing in Pipedrive, and nothing else will tell you.

## 3. The flow

### An email is sent
WF-2S notices it in Smartlead's statistics → replays it into WF-2 → WF-2 skips it if the campaign is a nurture campaign or if it is not the first email in the sequence → otherwise enriches the lead from Smartlead, finds or creates the organisation, person and lead in Pipedrive.

### Someone replies
The reply arrives (live webhook, or replayed by WF-2R within ~15 minutes) → WF-2 resolves the person and the lead → decides whether this is the first reply worth announcing and posts it to `#lead-processing` → **sends the reply text to an LLM to be classified** → writes the category back to Smartlead → then, depending on the category:
- **Do Not Contact** → unsubscribe the lead in Smartlead **and** put the DNC label on the Pipedrive lead;
- **Interested / Meeting Request / Not Interested / Information Request** → work out which human owns the sending inbox and **forward the thread to them**;
- anything else → no forward.

Finally it unions the lead labels and writes a reply activity.

### An email bounces
Resolve person and lead → write a bounce note on the lead → count it → ignore a repeat bounce for the same lead within the hour.

### Someone unsubscribes
Resolve person and lead → unsubscribe in Smartlead → apply the DNC label in Pipedrive.

## 4. The rules a human needs to know

**One switch turns all writing off.** `WRITE_MODE` in WF-2's CONFIG. Every outward call sits behind a gate checking it equals `live`. It has been live since 2026-08-10, and WF-2S raises an alarm if it is left non-live.

**Classification has a guardrail.** The LLM must return valid JSON, a known category, and confidence of at least **0.7**. If any of that fails, the category becomes `Uncategorized`, **Smartlead is left untouched**, and the reply is forwarded to a review address instead of a salesperson. That threshold was chosen from evidence, not taste.

**Forwarding is by inbox address, never by name.** There is a large explicit map from every sending-inbox address to an owner. An address that is not in the map raises an ops warning rather than guessing. If you add a sending inbox in Smartlead, **you must add it to that map** or its replies go to the default.

**Only the first email of a sequence creates CRM records.** Steps 2, 3, 4 of a sequence do not.

**Nurture campaigns are excluded** from the sent path.

**Bounces are not replies — but Smartlead's statistics say they are.** On the statistics endpoint a bounce is recorded as history type `REPLY`; there is no bounce type there. WF-2R therefore builds a bounce index first and excludes them, because a replayed event carries none of the markers the live webhook has. If that index is ever unreadable, bounces start being announced as genuine replies.

**Alerts are recorded on delivery.** Same rule as the LinkedIn side: the suppression key is written only after Slack confirms.

## 5. When something looks wrong

| What you see | What it usually is | What to do |
|---|---|---|
| No new cold-email leads in Pipedrive today | WF-2S is not running, or its campaign rotation is stuck | check WF-2S's last execution and its Slack report; a "stuck" report names the unscanned offset range |
| Replies land in Pipedrive but nobody is told | first-reply suppression, or Slack post failed | check the execution's alert-gate output |
| A reply went to the wrong person | the sending inbox is missing from the forward map | look for `Ops Warn Unknown Inbox`; fix CONFIG, not the node |
| Everything is `Uncategorized` | OpenAI is failing or confidence is low | `Ops Warn Classify` fires; replies still reach the review address, nothing is lost |
| A bounce was announced as a reply | the bounce index was unusable in that cycle | WF-2R reports `__bounce_index_ok` / `__bounce_index_complete` |
| Person created with no company | the real sent payload has no lead data and enrichment did not run | known class; the enriched copy must be read, not the raw payload |
| WF-2 deactivated itself | an out-of-memory event, usually a large replay burst | reactivate, then check burst size before replaying anything |

**The daily safety nets:** WF-2H at 07:15 compares Smartlead volume against Pipedrive and reports how many new leads carry the expected fields; the morning digest at 07:00 reports the same volumes plus an "emails sent with no lead" integrity line. WF-2S watches WF-2H; WF-2R watches WF-2S; WF-2S watches WF-2's write mode. The watchers watch each other on purpose.

## 6. Restarting and replaying — read this before touching anything

**WF-2 answers `200` before it processes. Smartlead never retries.** Recovery is entirely ours, and it depends on the event type:

| Lost event | Recovery |
|---|---|
| **SENT** | automatic — WF-2S re-claims it next cycle (it only marks a send seen after WF-2 accepted it) |
| **REPLIED** | automatic — WF-2R replays within ~15 minutes, same claim-after-success rule |
| **BOUNCED** | **none** — no reconciler covers it |
| **UNSUB** | **none** — no reconciler covers it |

So: for a sent or a reply, **wait one cycle and check the reconciler's next report before hand-repairing anything.** For a bounce or an unsubscribe, the event is gone and the repair is manual.

**If you replay by hand**, note that the replay envelope is shaped **inversely** to the live webhook: `to_email` carries the *lead's* address (on a live webhook it is whoever replied), and the lead's address must also be sent as `sl_lead_email` or WF-2 cannot identify the lead. Getting this wrong is silent — the replay succeeds and nothing happens.

**Never replay ~100 items in one burst.** A burst that size has exhausted the instance's memory before and left the workflow deactivated. WF-2S and WF-2R are capped at 20 per run for exactly this reason; respect the same cap by hand.

## 7. Smartlead and the DNC registry — the honest picture

There are **two separate mechanisms** and they are not connected:

**A. What WF-2 does today (working).** A reply classified as do-not-contact → unsubscribe in Smartlead + DNC label on the Pipedrive lead. Immediate, automatic, and effective for that one person in that one tool. **It writes no row in the DNC registry**, so the registry does not know about it and neither does anything reading the registry.

**B. What the registry does (dormant).** Rows are written by the capture sources, and `dnc_projections_sweep` is supposed to push them out — including unsubscribing the person in Smartlead. That sweep has **not run in the last 19 days and has both write switches set to `false`**.

**What actually protects a Smartlead campaign today:**
1. `dnc_pre_add_gate` — if whoever builds the list remembers to ask it;
2. `dnc_escalation_detector` — hourly, cross-checks live cold campaigns against the registry and shouts if someone on the list is in a sending campaign. **This detects after the fact; it does not prevent.**

**Irreversibility warning.** A Smartlead unsubscribe cannot be undone through the API. Treat any bulk unsubscribe as a one-way door: confirm the candidate list before firing, and read back afterwards — a Smartlead "add lead" call can report success on an add that silently did not happen for an unsubscribed lead.

## 8. Dependencies at a glance

```
Smartlead ──(rarely)──► WF-2 webhook
Smartlead ◄──poll──── WF-2S ──replay──► WF-2 webhook      (SENT: the main path)
Smartlead ◄──poll──── WF-2R ──replay──► WF-2 webhook      (REPLIED: recovery)

WF-2 ──► Pipedrive (org, person, lead, activity, labels, DNC label)
     ├─► Smartlead (category, unsubscribe, forward email)
     ├─► OpenAI    (reply classification)
     ├─► Slack     #lead-processing / ops / #alerts / #gtm-telemetry
     └─► WF-ERR    (on crash)

WF-2S ──watches──► WF-2H, WF-2 write mode
WF-2R ──watches──► WF-2S

NOT connected:  WF-2 ──✗──► DNC registry
                DNC registry ──✗(dormant)──► Smartlead
```
