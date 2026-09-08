# Stage 4 — Slide outline

**Session:** How the outreach-to-CRM system works
**Audience:** Melisa, Sergey, Stefan — business-fluent, not n8n-fluent
**Length:** 30–40 minutes, plus questions
**Rule for the deck:** no tool names on slides beyond HeyReach / Smartlead / Pipedrive / Slack, no workflow names, no node names, no code. Everything below is written so a slide can carry the sentence as-is.

---

## Section 0 — Frame (2 min, 2 slides)

### Slide 1 — Title
**"From an outreach message to a CRM record — how the machine actually works"**
Sub-line: *what runs by itself, what needs a person, and what to do when it looks wrong.*

### Slide 2 — Why we're here
Three sentences:
- You depend on this system daily, but only one person can currently explain it.
- Today you get the map, the failure signals, and the list of what is still open.
- Nothing here is a proposal — it is a description of what is running right now.

---

## Section 1 — The whole system in one picture (6 min, 3 slides)

### Slide 3 — The one-line version
> **Two outreach channels feed one CRM, one alerting channel, and one do-not-contact record — and a set of small watchdogs whose only job is to notice when that stops happening.**

### Slide 4 — The picture (one diagram, in words)
Left to right, four columns:

1. **We reach out** — LinkedIn (HeyReach) and cold email (Smartlead).
2. **Something happens** — invite accepted, message sent, reply, bounce, unsubscribe.
3. **The bridge** — takes each event, works out who the person is, finds or creates their record, moves them along the pipeline, records the conversation, and decides whether a human should be told.
4. **The result** — a person, a company, a lead and an activity in Pipedrive; a message in the team channel when someone actually replies; a forwarded email to the salesperson who owns that inbox.

Underneath, a fifth band across the whole width: **the watchdogs** — the jobs that check the bridge is still working and post one morning summary.

*Speaker note:* the bridge is two big automations, one per channel, plus about a dozen small ones. Twenty-one are running right now; another fifteen are built and switched off.

### Slide 5 — The five promises the system makes
1. **Every campaign event ends up in the CRM.**
2. **A real reply reaches a human, once — not twice, not never.**
3. **Nothing we do removes information.** Labels only accumulate; stages only move forward.
4. **A decision someone made by hand is respected.** If a lead was archived on purpose, the automation stays out of the way.
5. **Silence is never ambiguous.** Every daily job posts even when the news is "all fine", so a missing message means the job did not run.

*Speaker note:* promise 5 is the one to dwell on. It is why the channels look chatty.

---

## Section 2 — The four domains (14 min, 8 slides)

### Slide 6 — LinkedIn → CRM: what it does
Every invite, acceptance, message and reply becomes: the right company, the right person, **one lead per campaign**, an activity with the message text, and — for a reply — a notification to the team channel.

### Slide 7 — LinkedIn → CRM: the rules worth knowing
- **One lead per campaign.** Three campaigns, three leads. Matched on the campaign field, never on the lead title.
- **Stages only move forward.** A late event cannot pull someone backwards.
- **Archived means leave it alone.** No lead, no activity, no label, no message — total silence.
- **A personal LinkedIn chat is never announced.** The conversation is still recorded in the CRM; nobody is notified. That is deliberate.
- **One notification per person per campaign** — and it only counts as sent when Slack confirms it landed.
- **Event campaigns need their name formatted correctly** (`[Events Visiting] [Ai4 2026]`). Rename a live campaign and the event fields stop being filled — and you get told.

### Slide 8 — Email → CRM: what it does
Sent, replied, bounced, unsubscribed. Same CRM outcome, plus three things LinkedIn does not have:
- **every reply is read and classified** (interested, meeting request, not interested, information request, out of office, wrong person, do not contact, …);
- **forwardable replies are emailed to the salesperson who owns that sending inbox**;
- **a "do not contact" reply unsubscribes them immediately.**

### Slide 9 — Email → CRM: the one fact that explains everything else
> **The email tool does not tell us when it sends an email.**

So we ask it, every fifteen minutes, and feed the answer back in as if it had told us. The same trick recovers replies that go missing.

In the last three weeks: the live channel fired **130 times**; the two catch-up jobs fired **1,845 times each**.

*Speaker note:* this is why there are so many moving parts on the email side, and why "the catch-up job stopped" is the single most important failure to notice. Also worth saying plainly: **a lost bounce or a lost unsubscribe is not recovered by anything.**

### Slide 10 — The do-not-contact record: what it is
A list of people we must not put into a cold campaign — **and the reason why**, because the reason is what lets us defend it and eventually retire it.

Reasons, strongest first: they explicitly opted out → they told us no → they replied → they booked a meeting → a salesperson owns them personally → they came in through an event → someone added them by hand.

**Entries no longer expire on a timer.** Since late August, retention is by reason, not by clock: a reply does not stop mattering after six months.

### Slide 11 — The do-not-contact record: how someone gets on it, and how we check
**Getting on it** — one component does all the writing, and refuses to merge two people who only look alike. When it cannot tell, it asks a human.

**Checking** — there is a service you can ask before loading a list: *may I contact these people?* It answers per row: clean / blocked / our own team / cannot identify. It is checked automatically every fifteen minutes to prove it still gives the right answers.

### Slide 12 — The do-not-contact record: the honest gap
Say it plainly:

> **The record is well maintained. It currently has no automatic effect on the sending tools.**

- The piece built to push it out to Pipedrive and the email tool **has not run in the last three weeks**, and its two switches are off.
- **There is no path to LinkedIn at all** — replies on LinkedIn never reach the record, and the record cannot reach HeyReach.
- What actually protects a campaign today: **someone remembering to ask the checking service**, plus an hourly detector that shouts if a listed person is found inside a live campaign. **That detects; it does not prevent.**

*Speaker note:* this is the most important slide in the deck. Do not soften it, and do not fix it live — bring it to the "still open" section with a proposed decision.

### Slide 13 — The safety net around all of it
- Every automation reports its failures to **one place**, in plain language, with a verdict: *delayed and will come back on its own* / *recoverable, wait one cycle* / *lost, repair by hand*.
- A **daily digest at 07:00** — volumes on both channels, CRM counts, do-not-contact counts, gate health, failures in the last 24 hours, and anything scheduled that did not run.
- A **daily conventions check** that reads every automation and reports only what changed.
- **Watchdogs watching each other:** the sent-catch-up watches the health digest, the reply-catch-up watches the sent-catch-up.

---

## Section 3 — What to do when something looks wrong (7 min, 4 slides)

### Slide 14 — The three signals, in order
1. **A message in ops** — something failed; the message says whether it will fix itself.
2. **No morning digest** — the daily job did not run. This is more serious than a bad number in the digest.
3. **A quiet channel on a busy day** — no reply notifications while campaigns are clearly sending. Silence is the failure mode to distrust.

### Slide 15 — The five questions to ask, in this order
1. **Is anything actually broken, or just late?** The failure message says which.
2. **Which channel?** LinkedIn or email — they fail differently.
3. **Did the CRM get it, and only the notification is missing?** Usually yes, and that is much less serious.
4. **Did the catch-up job run in the last fifteen minutes?** If yes, wait one cycle before doing anything by hand.
5. **Is anything scheduled overdue?** The morning digest answers this.

### Slide 16 — What fixes itself, and what does not
| Situation | Recovery |
|---|---|
| A LinkedIn event failed | **Comes back on its own** — the tool retries for 24 hours |
| An email send was missed | **Automatic** — the catch-up job re-claims it next cycle |
| A reply was missed | **Automatic** — recovered within ~15 minutes |
| A bounce or unsubscribe was missed | **Not recovered by anything** — manual repair |
| The daily digest did not post | **Not automatic** — someone has to look |

*Speaker note:* the recurring theme — **wait one cycle before hand-repairing anything.** Manual repair on top of an automatic one is how duplicates get created.

### Slide 17 — Two things never to do
1. **Never bulk-replay.** Replaying ~100 items at once has taken the whole system down before and left an automation switched off. The catch-up jobs deliberately do twenty at a time.
2. **Never bulk-unsubscribe without confirming the list first.** Unsubscribing in the email tool cannot be undone.

---

## Section 4 — What is manual, and why (5 min, 3 slides)

### Slide 18 — Manual on purpose
| Manual step | Why it stays manual |
|---|---|
| Deciding whether two look-alike records are the same person | Merging two different real people is a data-integrity incident. The system refuses and asks. |
| Retiring someone from the do-not-contact record | Removing a protection is a business decision, not an automatic one. |
| Promoting an ambiguous reply to "explicit opt-out" | Phrase-matching got this wrong: most matches were **our own** wording quoted back inside the reply. First pass said 45; the truth was 10. Nothing is auto-promoted now. |
| Turning any bulk write on | Everything ships switched off and is fired once in dry-run first. |

### Slide 19 — Manual by omission (i.e. it should probably be automatic)
| Manual step | Consequence today |
|---|---|
| Remembering to ask the checking service before loading a list | It is the only preventive control we have |
| Filing "responded" and "booked a meeting" people onto the record | Those two capture routes are built but switched off — someone fires them by hand |
| Anything at all to do with LinkedIn and do-not-contact | No automatic path exists in either direction |
| Pushing the record out to the sending tools | Built, switched off, has not run in three weeks |

### Slide 20 — Where a person is genuinely required
Reading the ten ambiguous replies. Deciding whether an event campaign name is right before it goes live. Deciding who owns a newly added sending inbox. Deciding when a relationship has ended.

*Speaker note:* these four are not automation gaps. They are judgement, and the system is built to route them to a person rather than guess.

---

## Section 5 — What is still open (5 min, 3 slides)

### Slide 21 — The three decisions I need from you
1. **Do we turn the do-not-contact projections on?** Today the record has no automatic effect on the sending tools. Turning it on is a one-way door for the email half — an unsubscribe cannot be undone. *(Recommendation: yes, Pipedrive half first, in small batches, with a read-back.)*
2. **Do the "responded" and "meeting" capture routes get switched on and scheduled?** Right now only one of the four routes runs by itself, and it only sees hand-created and Surfe leads.
3. **What do we do about LinkedIn and do-not-contact?** There is no path in either direction. Everything else in this deck has an answer; this one does not.

### Slide 22 — The known holes, stated plainly
- **Lists over 50 people sent to the checking service get an answer that never arrives.** Batches must stay at or under 50 until it is fixed. *(Being verified.)*
- **A missed bounce or unsubscribe is gone.** No catch-up job covers those two.
- **The one route that runs by itself only sees the newest hundred leads**, and only leads — a person created without a lead is invisible to it.
- **The weekly full CRM sweep is switched off.** We have daily change detection only, which cannot see anything the CRM does not notify us about.
- **Our own history only goes back about three weeks.** Anything older has to come from the CRM or the email tool.

### Slide 23 — What good looks like in 30 days
- The do-not-contact record has an automatic effect on at least one sending tool.
- Every capture route either runs on a schedule or is deleted.
- The over-50 dead end is closed.
- Someone other than me has followed the "when something looks wrong" page end to end, on a real incident.

---

## Timing summary

| Section | Slides | Minutes |
|---|---|---|
| Frame | 1–2 | 2 |
| The whole system | 3–5 | 6 |
| The four domains | 6–13 | 14 |
| When something looks wrong | 14–17 | 7 |
| What is manual | 18–20 | 5 |
| What is still open | 21–23 | 5 |
| **Total** | **23** | **~39** |

Cut first if short on time: slide 7 (compress into 6) and slide 20. Never cut slides 12, 16, 17 or 21.

---

## Handouts

Put two one-pagers on the table rather than in the deck:
1. **"When something looks wrong"** — slides 14–17 as a single printed page.
2. **"Who to tell, and what fixes itself"** — the recovery table plus the two never-dos.
