# Domain 1 — HeyReach → Pipedrive (+ DNC)

*Written for someone who has to keep this running without asking the person who built it.*
*State as read live from n8n on 2026-09-02.*

---

## 1. What this domain is for

We run LinkedIn outreach in **HeyReach**. The company runs on **Pipedrive**. This domain is the automatic bridge between them: every invite, acceptance, message and reply on LinkedIn becomes a person, a lead, an activity and — when it's a real reply — a Slack notification to the team.

If it stops, nothing breaks loudly. LinkedIn keeps working, the CRM just quietly stops learning about it, and Melisa stops being told when someone replies. **That is the failure to fear: silence that looks like calm.**

## 2. The pieces

| Piece | Where | Role |
|---|---|---|
| HeyReach campaigns | HeyReach | send the invites and messages |
| **WF-1 HeyReach Receiver** | n8n, ACTIVE | the whole bridge — 126 nodes, one workflow |
| Pipedrive | CRM | organisations, persons, leads, activities, labels |
| Slack `#lead-processing` (`C07LTD8UT70`) | Slack | where a reply is announced |
| Slack ops (`C0B8GCVNR5W`) | Slack | where problems are announced |
| WF-ERR | n8n | catches any crash |

There is **no reconciler for HeyReach**. If an event is lost, HeyReach's own retry (up to 5 times over 24 hours) is the only recovery.

## 3. The flow, in one paragraph

HeyReach posts an event to a private webhook URL. WF-1 rejects it if it has seen the same event in the last 48 hours. It reads the campaign name for an event marker, checks whether this campaign's lead was deliberately archived (if so it stops, silently), then finds or creates the organisation and the person, moves the person's stage forward if the event is a step up, finds or creates *one lead for this campaign*, adds the appropriate labels without ever removing any, and writes an activity. If the event was a reply, it decides whether this is the first reply worth announcing and posts it to `#lead-processing`.

## 4. The rules a human needs to know

**One lead per campaign.** A person in three campaigns gets three leads. The lead is matched on its **Campaign field**, never on its title — the title is a convention (`{campaign id} - {campaign name} - {name}`) and titles get edited.

**Stages only move forward.** Invited (1) → Accepted (2) → First follow-up sent (3) → Replied (4). A late-arriving older event cannot pull someone backwards.

**Labels are cumulative.** We add *Cold* and, on a reply, *3. Responded*. We never remove a label. If a label disappears, something else did it.

**"3. Responded" is a handover trigger.** Writing it hands a human a lead as warm. No automated event may set it without an engagement check — a bounce or an unsubscribe must never look like a reply. There is a linter rule enforcing this across the whole estate.

**Archived lead = ignore.** If someone archived the campaign lead, the event passes through in total silence: no lead, no activity, no label, no post anywhere. Someone made that decision on purpose. *(Detecting this needs a special search — the ordinary lead endpoints cannot see archived leads at all. If the search itself fails, WF-1 deliberately does **not** block: a real reply must never be silenced by a lookup we couldn't perform.)*

**A personal LinkedIn chat is never announced.** If the event has no campaign, it's the exec's own conversation. The CRM activity is still written so the history exists; nothing is posted anywhere — not `#lead-processing`, not `#alerts`, not ops. This silence is deliberate; do not "restore" it as a quiet line somewhere.

**One alert per person per campaign, recorded on delivery.** The suppression key is the Pipedrive person id (or the canonical LinkedIn identity), and it is only written after Slack confirms the message landed in the team channel. Two consequences: a failed Slack post does not burn that person's only alert, and archiving a lead does not reset their suppression.

**Event campaigns need two brackets.** A campaign named `[Events Visiting] [Ai4 2026]` writes the person's Hypothesis and Event Name. One bracket, an empty second bracket, or one longer than 60 characters → the event fields are skipped and Slack warns, naming the campaign. **Do not rename live campaigns mid-flight.**

**The follow-up task is off.** `create_assignment_task: false` — a different automation owns task creation.

## 5. When something looks wrong

| What you see | What it usually is | What to do |
|---|---|---|
| A reply is in Pipedrive but nobody was told | suppression, or no campaign on the event | open the execution, read `__alert_reason`: `already_delivered`, `manual_conversation`, `first_alert`, `no_identity` |
| Two alerts for the same person | the person couldn't be identified at all — that path alerts on purpose rather than risk losing a first reply | look for `no_identity` |
| A duplicate lead appeared | the archived-lead probe couldn't be read, so it failed open | look for `probe_unreadable` |
| Nothing happened at all | duplicate within 48h, or the archived-lead rule | check the dedupe and the `__ar` block |
| `Event Marker Warn` in Slack | a campaign name lost its brackets | fix the name in HeyReach |
| Silence for hours on a working campaign | the webhook may be unregistered on the HeyReach side | check WF-1's execution list; if it is empty, the problem is upstream of n8n |

**The daily safety nets:** the morning digest (07:00) reports HeyReach volume in the last 24 hours, so a dead webhook shows up as a zero. WF-ERR posts any crash immediately, with the verdict *"DELAYED — HeyReach retries, the event should come back on its own"*.

## 6. Restarting and replaying

> **Corrected 2026-09-02.** This section previously said "do nothing first — HeyReach retries, so
> it's a delay, not a loss." That was taken from WF-ERR's verdict table, and the verdict was wrong.
> WF-1 answers `{"ok": true}` with HTTP 200 from the Webhook node **before any processing runs**, so
> HeyReach is told the event was accepted and will **not** retry a processing failure — its 5×/24h
> retry only covers a delivery failure (n8n unreachable, or a 5xx at the HTTP layer). WF-1 has no
> reconciler. WF-ERR's verdict has been changed to `LOST`.

- **A failed HeyReach event is LOST.** Nothing will re-deliver it, and nothing will replay it. Repair
  it by hand from the HeyReach inbox, using the campaign and profile URL in the failed execution.
  *(This is the one open design question in this domain: making WF-1 respond **after** processing
  would turn HeyReach's retry into a real safety net, at the cost of webhook latency. The 48-hour
  dedupe already handles the duplicate delivery that would come with it.)*
- **To replay by hand:** POST the same payload to the WF-1 webhook. Safe — the 48-hour dedupe rejects exact repeats, stages only move forward, labels only accumulate.
- **Do not** bulk-replay a campaign's history. Alerts would stay suppressed (fine) but activities would duplicate (not fine).
- **After changing Pipedrive fields or labels:** run `WF-0 - Discovery` by hand. It reads Pipedrive's field, label, user and activity-type definitions and produces the CONFIG block WF-1 depends on. Those long hex strings in CONFIG are Pipedrive field keys; if a field is recreated, its key changes and WF-1 silently writes nothing.

## 7. HeyReach and the DNC registry — the honest picture

**HeyReach replies do not reach the do-not-contact registry.** The workflow written to do that (`heyreach_reply_to_dnc_ledger`) has never run and nothing calls it.

**There is no HeyReach write path out of the registry either.** The projector (`dnc_projections_sweep`) can set a DNC field in Pipedrive and unsubscribe in Smartlead; for HeyReach it only *counts* what is pending. And the projector itself has not run in the last 19 days and has both its write switches off.

**What that means in practice.** For LinkedIn, "do not contact" is enforced by:
1. asking the gate (`dnc_pre_add_gate`) before loading a campaign list — a manual step someone has to remember;
2. the Pipedrive labels WF-1 maintains, which a human reads.

There is no automatic suppression inside HeyReach. **If someone tells us on LinkedIn to stop, the only thing that records it is the CRM activity and whatever a human does next.** That is the largest known gap in this domain and it should be on the "what's still open" slide.

## 8. Dependencies at a glance

```
HeyReach ──webhook──► WF-1 ──► Pipedrive (org, person, lead, activity, labels)
                       │
                       ├──► Slack #lead-processing   (reply alerts, on delivery)
                       ├──► Slack ops / #alerts      (problems only)
                       └──► WF-ERR                   (on crash)

WF-0 - Discovery ──(run by hand)──► the field keys WF-1's CONFIG holds

NOT connected:  WF-1 ──✗──► DNC registry
                DNC registry ──✗──► HeyReach
```
