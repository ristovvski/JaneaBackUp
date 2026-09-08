# Domain 1 — HeyReach → Pipedrive (+ DNC)

*The LinkedIn side, end to end. Written so someone can fix it without Nik.*
*State read live 2026-09-03.*

---

## 1. What this is for

LinkedIn outreach runs in **HeyReach**. The company runs on **Pipedrive**. This domain is the
automatic bridge. If it stops, nothing breaks loudly: LinkedIn keeps sending, the CRM quietly stops
learning about it, and Melisa stops being told when someone replies.

**That is the failure to fear — silence that looks like calm.**

## 2. The pieces

| Piece | Role |
|---|---|
| HeyReach campaigns | send the invites and messages |
| **WF-1 HeyReach Receiver** (130 nodes, ACTIVE) | the entire bridge |
| Pipedrive | organisations, persons, leads, activities, labels |
| Slack `#lead-processing` | where a reply is announced |
| Slack ops / `#alerts` | where problems are announced |
| WF-ERR | catches any crash |
| A shared claims table | remembers which replies were already announced |

**There is no reconciler for HeyReach.** Nothing re-reads HeyReach to find what we missed.

## 3. The flow in one paragraph

HeyReach posts an event. WF-1 answers `{"ok": true}` immediately, then works. It rejects the event
if it has seen it in the last 48 hours, canonicalises the person's LinkedIn URL, reads the campaign
name for an event marker, and asks whether this campaign's lead was deliberately archived — if so it
stops, silently. Otherwise it finds or creates the company and the person, moves the person's stage
forward if the event is a step up, finds or creates **one lead for this campaign**, adds labels
without removing any, and writes an activity with the message text. If the event was a reply, it
decides whether this is the first reply worth announcing and posts it to `#lead-processing`.

## 4. The rules a human needs to know

**One lead per campaign.** A person in three campaigns has three leads. The match is on the lead's
**Campaign field** — never the title. Titles follow a convention (`{campaign id} - {campaign name} -
{name}`) and titles get edited.

**Stages only move forward.** Invited → Accepted → First follow-up sent → Replied. A late-arriving
older event cannot pull anyone backwards.

**Labels accumulate.** We add *Cold*, and *3. Responded* on a reply. We never remove one. **If a
label disappears, something else removed it.**

**Archived lead = ignore, in total silence.** No lead, no activity, no label, no message anywhere.
Somebody archived it on purpose. Detecting this needs a special search, because the ordinary lead
lists cannot see archived leads at all — and the match is confirmed by person id, never by name. If
that search itself fails, WF-1 deliberately does **not** block: a real reply must never be silenced
by a lookup we could not perform.

**A personal LinkedIn chat is never announced.** No campaign on the event means it is the exec's own
conversation. The CRM activity is still written so the history exists; nothing is posted anywhere.
This silence is deliberate and is written into the code as a ruling — do not "restore" it as a quiet
line somewhere.

**One alert per person per campaign, and only once Slack confirms it landed.** The memory key is the
Pipedrive person id, not the lead id — otherwise archiving a lead would reset that person's
suppression and their next message would be announced as a first reply. That is not hypothetical; it
happened.

**Event campaigns need two brackets** — `[Events Visiting] [Ai4 2026]`. One bracket, an empty second
one, or one over 60 characters, and the event fields are skipped and Slack warns, naming the
campaign. **Do not rename a live campaign mid-flight.**

**The follow-up task is off.** A different automation owns task creation.

## 5. The change made this morning, and why it matters

Until today, "have we already announced this reply?" was remembered **inside the workflow's own
memory**. That memory is saved as one whole object when a run finishes, so two runs that overlap
each load the same state and the last one to finish wins.

**It cost a real duplicate.** On 2026-09-01 at 20:50:27 three WF-1 runs started in the same second.
Two alerts were delivered but the memory went from 47 entries to 48 instead of 49 — one person's
record was overwritten — and she was announced again 27 hours later as a first reply.

**This is routine traffic, not an edge case.** HeyReach fans several events for a single message into
the same second: in the retained window there were **28 such groups, up to 5 events each, and 54
true overlaps**.

The memory now lives in a shared table where each claim is written independently, so two runs cannot
overwrite each other. Two properties were kept deliberately: the claim is written **after** Slack
confirms delivery, not when the decision is made; and if the table cannot be read the workflow
**alerts anyway** — a duplicate is noise, a missed first reply is lost revenue.

## 6. When something looks wrong

| What you see | Usually | How to check |
|---|---|---|
| Reply in Pipedrive, no Slack alert | suppression, or the event had no campaign | the run records a reason: `already_delivered`, `manual_conversation`, `first_alert`, `no_identity`, `dt_unavailable_fail_open` |
| Same person announced twice | the fail-open path — we could not read the memory | reason `dt_unavailable_fail_open` or `no_identity` |
| A duplicate lead appeared | the archived-lead check could not be read | the probe result is on the run |
| Nothing happened at all | duplicate inside 48 h, or the archived-lead rule | both are recorded |
| `Event Marker Warn` in Slack | a campaign lost its brackets | fix the name in HeyReach |
| Quiet channel on a busy day | the webhook may be unregistered at HeyReach | WF-1's run list is empty; the morning digest's HeyReach volume reads zero |

**The daily safety nets:** the morning digest reports HeyReach volume for the last 24 hours, so a
dead webhook shows up as a zero. WF-ERR posts any crash immediately.

## 7. Recovery — the important part

> **A failed HeyReach event is LOST.**

WF-1 answers `200` before it processes. HeyReach's documented retry — 5 times over 24 hours — fires
only on a **non-2xx** response, which we never give once processing has begun. And there is no
reconciler.

- **Repair by hand** from the HeyReach inbox, using the campaign and profile URL on the failed run.
- **Re-firing one payload is safe.** The 48-hour duplicate guard rejects exact repeats, stages only
  move forward, labels only accumulate.
- **Do not bulk-replay a campaign's history.** Alerts stay suppressed (fine); activities duplicate
  (not fine).
- **After any Pipedrive field or label change, run `WF-0 - Discovery` by hand.** Those long hex
  strings in WF-1's settings are Pipedrive field keys. Recreate a field and its key changes — and
  WF-1 silently stops writing that field. `WF-0 - Discovery` never appears in an execution list and
  is easy to mistake for dead. It is not.

**The open design question:** should WF-1 answer *after* processing instead? That would make
HeyReach's retry a real safety net. It costs webhook latency and invites duplicate delivery — which
the 48-hour guard already handles. Worth deciding rather than inheriting.

## 8. LinkedIn and the do-not-contact list — the honest picture

**LinkedIn replies do not reach the do-not-contact registry.** The workflow written to do it,
`heyreach_reply_to_dnc_ledger`, has never run and nothing calls it. It is still there, inactive,
un-archived — the un-built bridge.

**And there is no path in the other direction either.** The projector can set a do-not-contact field
in Pipedrive and unsubscribe someone in Smartlead. For HeyReach it only *counts* what is pending;
there is no write path at all.

So for LinkedIn, "do not contact" is enforced by exactly two things:
1. **asking the gate before loading a campaign list** — a manual step someone has to remember;
2. **the Pipedrive labels WF-1 maintains**, which a human reads.

**If someone tells us on LinkedIn to stop, the only record is the CRM activity and whatever a human
does next.** That is the largest gap in this domain and it belongs on the "still open" slide.

## 9. One thing to check before the presentation

On the reply path, WF-1 picks the lead **whose Campaign field matches** when writing the activity,
and the **newest non-archived lead** when computing labels. For a person in one campaign these are
the same record. For a person in two, they need not be — so the activity and the labels could land
on different leads. Both selections are in the live code today. It is a suspected defect, not a
confirmed one; it needs one targeted check against a real two-campaign person.

## 10. The map

```
HeyReach ──webhook──► WF-1 ──► Pipedrive (org, person, lead, activity, labels)
                       │
                       ├──► Slack #lead-processing   (reply alerts, after delivery confirmed)
                       ├──► Slack ops / #alerts      (problems only)
                       ├──► claims table             (duplicate guard + alert memory)
                       └──► WF-ERR                   (on crash)

WF-0 - Discovery ──(run by hand)──► the Pipedrive field keys WF-1 depends on

NOT connected:   WF-1 ──✗──► DNC registry
                 DNC registry ──✗──► HeyReach
```
