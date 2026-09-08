# Stage 5 — Slide outline

**Audience:** Melisa (GTM lead), Sergey (sales/strategy), Stefan (external consultant, no Pipedrive
access). Business-fluent, not n8n-fluent.
**Length:** 30–40 minutes plus questions. **24 slides.**

**Rules for the deck:** no workflow names, no node names, no jargon. The only proper nouns allowed
are HeyReach, Smartlead, Pipedrive, Slack and OpenAI. One idea per slide. Speaker notes carry the
numbers so the slides do not have to.

---

## Section 1 — What the system does end to end (6 min · slides 1–5)

### Slide 1 — Title
**"From an outreach message to a CRM record"**
*Sub-line: what runs by itself, what needs a person, and what to do when it looks wrong.*

> **Notes.** Set the frame in three sentences: you depend on this daily; today you get the map, the
> failure signals and the open decisions; nothing here is a proposal, it is a description of what is
> running right now. Say that the numbers were read out of the live system this morning, not
> remembered.

### Slide 2 — The one-line version
> **Two outreach channels feed one CRM, one alerting channel, and one do-not-contact list — plus a
> set of small watchdogs whose only job is to notice when that stops happening.**

> **Notes.** Resist detail here. The whole deck is this sentence, unpacked.

### Slide 3 — The picture *(one diagram, four columns and a band underneath)*
1. **We reach out** — LinkedIn and cold email.
2. **Something happens** — accepted, replied, bounced, unsubscribed.
3. **The bridge** — works out who the person is, creates or finds their record, moves them along,
   records the conversation, decides whether to tell a human.
4. **The result** — a person, a company, a lead and an activity in the CRM; a message in the team
   channel when someone really replies; an email forwarded to the right salesperson.

Underneath, a band across all four: **the watchdogs.**

> **Notes.** Twenty automations run this. Two do the bridging; the rest watch. Today twelve more
> were archived, so everything still switched on has actually run in the last three weeks — that is
> deliberate and new.

### Slide 4 — The five promises
1. Every campaign event ends up in the CRM.
2. A real reply reaches a human **once** — not twice, not never.
3. Nothing we do removes information: labels only accumulate, stages only move forward.
4. A decision a person made by hand is respected — archive a lead and the automation stays out of
   the way.
5. **Silence is never ambiguous.** Every daily job posts even when the news is "all fine", so a
   missing message means the job did not run.

> **Notes.** Dwell on promise 5 — it is why the channels look chatty, and it is the single habit that
> makes the rest trustworthy.

### Slide 5 — What is *not* automatic
- Nothing decides who goes into a campaign.
- Nothing writes to the do-not-contact list from either outreach channel.
- Nothing reads a LinkedIn reply for meaning.

> **Notes.** Say this early. It prevents every "but surely it…" question later, and it sets up
> sections 3 and 6.

---

## Section 2 — The two channels (9 min · slides 6–11)

### Slide 6 — LinkedIn: what happens
Invite → accepted → message → reply. Each becomes the right company, the right person, **one lead per
campaign**, an activity — and for a reply, a notification.

> **Notes.** One lead per campaign is the rule people trip over: the same person in three campaigns
> has three leads, matched on the campaign field, never on the title. Titles get edited.

### Slide 7 — LinkedIn: the four rules worth knowing
- Stages only move forward.
- Labels only accumulate — **if a label disappears, something else removed it.**
- **Archived means leave it alone** — no lead, no activity, no message.
- A personal LinkedIn chat is never announced; the conversation is still recorded.

> **Notes.** The archived rule was bought by a real incident: a lead existed, archived, the ordinary
> lookup could not see archived leads, and the system reported "no lead" and nearly created a
> duplicate.

### Slide 8 — Email: the fact that explains everything else
> **The email tool does not tell us when it sends an email.**

So we ask it every 15 minutes and feed the answer back in as if it had told us.

**In the last three weeks: 130 live messages from the tool. 1,899 catch-up cycles.**

> **Notes.** This is the slide people remember. It also explains why "the catch-up job stopped" is
> the most important failure to notice on the email side.

### Slide 9 — Email: what we do that LinkedIn does not
- **Every reply is read and categorised** — interested, meeting, not interested, do not contact, out
  of office, wrong person…
- **Forwardable replies are emailed to the salesperson who owns that inbox.**
- **A "stop contacting me" unsubscribes them immediately.**
- **A bounce and an out-of-office never notify anyone**, and never use up the person's one
  notification.

> **Notes.** The confidence floor is 0.7. Below it the reply is marked uncategorised, the sending
> tool is left untouched, and it goes to a review address — nobody should have to trust a classifier
> that just said it was unsure.

### Slide 10 — The trap we pay for on the email side
> **The email tool sends every bounce twice — and the second copy looks exactly like a reply.**

It once posted a bounce to the team channel and nearly marked a dead mailbox as an engaged lead.
**Three independent checks now catch it.**

> **Notes.** Worth telling as a story; it makes the case for the watchdogs better than any diagram.
> The tool's own category is useless here — empty on 11 of 12 real bounces.

### Slide 11 — What actually reaches a human
| Event | Who hears about it |
|---|---|
| Invite, acceptance, message sent | nobody |
| **A real reply** | **the team channel, once** |
| An interesting reply | **also emailed to the salesperson who owns that inbox** |
| Out of office | nobody |
| Bounce | nobody |
| Unsubscribe | nobody |
| Something broken | ops channel |

> **Notes.** "Once" is load-bearing: the record of having told someone is written only after Slack
> confirms it landed, so a failed message never silently uses up a person's one notification.

---

## Section 3 — The do-not-contact list (7 min · slides 12–15)

### Slide 12 — What the list is
People we must not put into a cold campaign — **and the reason why.**

**On it:** they replied · they booked a meeting · a salesperson owns them · imported LinkedIn
connections · explicit opt-outs.
**Not on it:** "we emailed them once". Contact alone is not a relationship.

> **Notes.** Entries no longer expire on a timer. A six-month countdown on someone who replied said
> the reply stops mattering — which is backwards. Retention is by reason, retired by a human.

### Slide 13 — How to check a list before sending  ← *the practical slide*
**Send the list to the checking service. It answers per person:**

**clean** · **blocked** (with the reason) · **our own team** · **cannot identify**

Up to 500 people per request, answered immediately. It only reads — ask as often as you like.
It is health-checked every 15 minutes with a question whose answer is known.

> **Notes.** This is the one thing the audience can *do*. Make sure Stefan leaves knowing it exists.
> Then say the uncomfortable part: **asking is manual. Nothing forces it.**

### Slide 14 — The honest gap, and what changes today
- Neither outreach channel writes to the list. It is filled from the CRM side.
- Until today the list had **no automatic effect** on the sending tools.
- **Today that starts changing:** ~564 people are being marked in the CRM now, and unsubscribes in
  the email tool follow for those who replied and declined or booked a meeting.
- **For LinkedIn there is still no automatic path in either direction.**

> **Notes.** Be plain. We measured it: of the people on the list who have an email address, **62%
> were still contactable in the email tool** — about 1,000 people, and four in five of them had
> replied and declined or booked a meeting. That is what is being fixed today.

### Slide 15 — The number that reframes the list
> **About 88% of the list is a LinkedIn URL and nothing else.**

No email, no CRM record. Those people cannot be marked in the CRM and cannot be unsubscribed from
the email tool — and there is no LinkedIn path at all.

> **Notes.** So today's fix is right *and* it touches roughly 6% of the list. The other 88% is a
> record, not a control. That is a separate and bigger decision — it belongs in "still open", not
> here. Reassuring counterpoint: the list's own bookkeeping never lied. We are running a backlog, not
> repairing corruption.

---

## Section 4 — When something looks wrong (7 min · slides 16–19)

### Slide 16 — The three signals, in order
1. **A message in the ops channel** — something failed, and the message says whether it fixes itself.
2. **No morning summary** — the daily job did not run. More serious than a bad number *in* it.
3. **A quiet team channel on a busy day** — campaigns are sending and nobody is replying? Distrust
   the silence.

### Slide 17 — Which channel says what
| Channel | What it means |
|---|---|
| **#lead-processing** | a real person really replied — act on it |
| **ops** | something broke, or a decision is needed |
| **#alerts** | the two bridges shouting about a specific event |
| **telemetry** | routine progress and dry-run chatter — safe to skim |
| **the daily digest** | the morning "is the machine fine?" post |

> **Notes.** The split is deliberate: routine noise never lands where person-level news lands.

### Slide 18 — What fixes itself, and what does not
| Situation | Recovery |
|---|---|
| A LinkedIn event failed | **Nothing. It is gone — repair by hand from the LinkedIn inbox** |
| An email send was missed | automatic, next 15-minute cycle |
| A reply was missed | automatic, within ~15 minutes |
| A bounce or unsubscribe was missed | **nothing recovers it** |
| No morning summary | nobody is coming — go and look |

> **Notes.** The recurring instruction: **wait one cycle before repairing by hand.** Manual repair on
> top of automatic repair is how duplicates are made. And correct the old belief out loud if it comes
> up — we used to think LinkedIn events came back on their own. They do not; the guidance said so
> until yesterday and it was wrong.

### Slide 19 — Two things never to do
1. **Never replay a hundred things at once.** It has taken the whole system down twice — once this
   week, while we were building the thing designed to avoid it.
2. **Never bulk-unsubscribe without confirming the list.** Unsubscribing cannot be undone.

---

## Section 5 — What is manual, and why (5 min · slides 20–21)

### Slide 20 — Manual on purpose
| Step | Why it stays manual |
|---|---|
| Deciding whether two look-alike records are the same person | merging two different real people is a data incident — the system refuses and asks |
| Retiring someone from the list | removing a protection is a business decision |
| Promoting an ambiguous reply to "explicit opt-out" | phrase-matching got this wrong: most matches were **our own** wording quoted back inside the reply. First pass said 45; the truth was 10 |
| Turning any bulk write on | everything ships switched off and is fired once in dry-run first |

### Slide 21 — Manual by omission *(i.e. it probably should not be)*
| Step | Consequence today |
|---|---|
| Remembering to check a list before sending | it is the only preventive control we have |
| Filing "replied" and "booked a meeting" people onto the list | both routes exist and are switched off; someone fires them by hand |
| Anything at all connecting LinkedIn to the list | no automatic path exists in either direction |

> **Notes.** Of the ways a person can get onto the list, **exactly one runs by itself** — the watcher
> that spots leads a salesperson created by hand.

---

## Section 6 — What is still open (5 min · slides 22–24)

### Slide 22 — The three decisions
1. **LinkedIn and the do-not-contact list — no path either way.** Everything else in this deck has an
   answer; this one does not. *(Proposal: run the same reply-reading on LinkedIn replies, or accept
   that LinkedIn opt-outs are handled by a human and say so.)*
2. **Should the "replied" and "booked a meeting" routes run automatically?** *(Proposal: a small
   scheduled feeder, since both populations are label-driven and the live watcher cannot see them.)*
3. **The 88% of the list that is LinkedIn-only.** *(Proposal: decide whether it is a control or an
   archive; if a control, it needs enrichment, and that is a budget question.)*

### Slide 23 — The known holes, stated plainly
- **A missed bounce or unsubscribe is gone** — no catch-up covers those two.
- **The one automatic route onto the list sees only the newest hundred leads**, and only leads — a
  person created without a lead is invisible to it.
- **We now keep a change log, not a change report.** We can answer "who changed this and when" for
  90 days, but nothing watches for bulk changes any more. That was a deliberate trade this morning.
- **Our own history is about three weeks.** Anything older must come from the CRM or the email tool.

### Slide 24 — What good looks like in 30 days
- The do-not-contact list has an automatic effect on **both** sending tools.
- Every route onto the list either runs on a schedule or is archived.
- LinkedIn has an answer, even if the answer is "a human does this".
- **Someone other than Nik has followed the "when something looks wrong" page through a real
  incident.**

> **Notes.** Close on the last one. The deck's real purpose is that the system stops having a single
> point of human failure.

---

## Timing

| Section | Slides | Min |
|---|---|---|
| What the system does | 1–5 | 6 |
| The two channels | 6–11 | 9 |
| The do-not-contact list | 12–15 | 7 |
| When something looks wrong | 16–19 | 7 |
| What is manual | 20–21 | 5 |
| What is still open | 22–24 | 5 |
| **Total** | **24** | **~39** |

**Cut first if short:** slide 7 (fold into 6) and slide 21.
**Never cut:** 8, 13, 14, 18, 22.

## Handouts — print, do not project

1. **"When something looks wrong"** — slides 16–19 on one page.
2. **"How to check a list before sending"** — slide 13, with the request format and the four answers.

## Two things to have ready for questions

- **Stefan has no Pipedrive access.** Slides 11 and 13 are the two he can act on; the checking
  service is the one tool that could be given to him safely, since it only reads.
- **If asked "how do you know any of this is true?"** — every number in the deck was read out of the
  live system on the morning of 3 September, and the do-not-contact figures come from a sample of
  1,000 of 25,653 records checked against the actual state of Pipedrive and the email tool.
