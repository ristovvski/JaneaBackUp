# Stage 4 — The lead journey

*One person, from the moment they enter a campaign to the moment the system stops talking about
them. One path per provider. This is the spine of the deck.*

---

# Path A — LinkedIn (HeyReach)

## Before anything: does she belong in the campaign at all?

**Maria Okafor**, Head of Data at a mid-size insurer, is on a list someone built for a LinkedIn
campaign.

Before the list is loaded, it is sent to the gate: *may I contact these people?* The gate answers per
row against the do-not-contact registry — **clean**, **blocked**, **our own team**, or **cannot
identify**. Maria comes back clean, so she stays on the list.

> **This is a manual step.** Nothing forces it. If nobody asks the gate, nothing else in the LinkedIn
> path will stop a protected person being contacted.

## First touch — the invite

HeyReach sends Maria a connection request and immediately tells us. The bridge answers *"received"*
before it starts work, then:

- checks it has not already seen this exact event in the last 48 hours;
- canonicalises her LinkedIn URL so she can be matched later;
- reads the campaign name — `[Events Visiting] [Ai4 2026]` means she came from an event, and those
  two brackets become fields on her record;
- **asks whether this campaign's lead for Maria was archived.** If somebody archived it deliberately,
  everything stops here, silently: no lead, no activity, no label, no message;
- finds or creates her company, then finds her — by email, then LinkedIn URL, then HeyReach id, each
  verified so a loose match cannot bind the wrong person — or creates her;
- sets her stage to **Invited**;
- creates **one lead for this campaign**, titled by convention but matched on the campaign field;
- adds the **Cold** label and writes an activity.

Nobody is notified. An invite is not news.

## She accepts

Stage moves **Invited → Accepted**. Labels gain nothing new; the activity is written. Still no
notification — an acceptance is not a conversation.

**Stages only ever move forward.** If a delayed invite event arrives after the acceptance, it cannot
demote her.

## We send a message

Stage moves to **First follow-up sent**. Activity written. Still silent.

## She replies — the moment everything turns on

Four things now happen, in this order.

**1. Is this even a campaign conversation?** If the event carries no campaign, it is the exec's own
LinkedIn chat. The activity is still written so the history exists, and **nothing is posted
anywhere** — not the team channel, not alerts. Deliberate.

**2. Was her lead archived?** If so: silence, as before.

**3. Has she already been announced?** The system remembers, per person per campaign, whether a reply
was already announced — keyed on her Pipedrive person id, **never on her lead id**, because archiving
a lead would otherwise reset her suppression and her next message would look like a first reply.

Until this morning that memory lived inside the workflow, and two events arriving in the same second
could overwrite each other. It cost a real duplicate on 1 September. **As of today it lives in a
shared table**, so overlapping events cannot lose each other's claims.

**4. Announce, then record.** Melisa gets a message in `#lead-processing` with Maria's name, company,
the campaign, and a link to the lead. The "already announced" record is written **only after Slack
confirms it landed** — so a failed post cannot burn her single alert. And if the memory itself cannot
be read, the system **alerts anyway**: a duplicate is noise, a missed first reply is lost revenue.

In Pipedrive: her stage becomes **Replied**, the **3. Responded** label is added, and the reply text
is written as an activity.

## What lands in the do-not-contact registry

**Nothing.**

A LinkedIn reply does not reach the registry. The workflow written to do that has never run and
nothing calls it. So if Maria's reply had said *"please stop contacting me"*, the record of that
would be the CRM activity and whatever a human does next — nothing automatic.

**This is the largest gap in the LinkedIn path.**

## If she was already protected

Suppose Maria was on the registry — she replied to a cold email last year and a salesperson owns her.

- **If someone asked the gate:** she is returned **blocked**, with the reason, and never enters the
  campaign. The system worked.
- **If nobody asked:** she is invited. LinkedIn has no automatic suppression, and the hourly
  escalation detector only checks *Smartlead* campaigns — so nothing catches it. The first sign is
  Maria, or the salesperson who owns her, noticing.

---

# Path B — Cold email (Smartlead)

## Before anything: the same gate

Same call, same four answers. **Same manual step.**

## First touch — the email goes out

Here the path differs immediately, because **Smartlead does not tell us when it sends an email.**

Every 15 minutes a reconciler asks Smartlead which emails went out, and feeds each one into the
receiver as if Smartlead had told us. In 20 days the receiver was called 130 times by Smartlead and
**1,899 times** by its reconcilers. This is the normal path, not the fallback.

When the send arrives, the receiver:
- skips it if the campaign is a nurture campaign;
- skips it if it is not the **first** email of the sequence;
- enriches the lead from Smartlead if the payload was thin;
- finds or creates the company, the person and the lead.

Nobody is notified.

## Then one of four things happens

### 1. A real reply

The reply arrives live, or the reply reconciler replays it within ~15 minutes.

- **Who actually replied?** The payload has two addresses: whoever replied, and the campaign lead.
  They are not always the same person — a colleague can reply on the thread. Each reply is classed
  **lead**, **alias** (same domain, same person), **third party**, or **ambiguous**. A confirmed
  third party is not announced. An **ambiguous** one *is* — a missing identity field is our failure,
  and our failure must never eat a live reply.
- **Announce it.** Melisa gets it in `#lead-processing`, once per person.
- **Read it.** The reply text goes to an LLM, which returns a category and a confidence. **Below 0.7,
  or unparseable, it becomes `Uncategorized`, Smartlead is left untouched, and the reply is forwarded
  to a review address instead of a salesperson.**
- **Write the category back** to Smartlead.
- **Forward it to a human** if the category is forwardable — to whoever owns that sending inbox,
  looked up by address, never by name. An unknown inbox still forwards to a default and tells ops.
- **Label the lead — in one write, truthfully:**

  | The reply says | Labels written together |
  |---|---|
  | stop contacting me | Cold + Connected + **3. Responded** + **DO NOT CONTACT** |
  | not interested / wrong person / no longer here | Cold + Connected + **3. Responded** + **Disqualified** |
  | interested / meeting / tell me more | Cold + Connected + **3. Responded** |

  Both labels must land **in the same write**. The handover automation fires on labels: if
  *Responded* arrived first and the suppressing label a moment later, a human would be handed an
  opt-out as a warm lead in the gap.
- **Write the reply activity.**

### 2. An out-of-office

Judged on Smartlead's own category, before our classifier and independent of it — so an LLM outage
cannot leak auto-replies into the team channel.

**Nobody is notified. No *Responded* label.** The lead gets Cold + Connected: an autoreply proves the
mailbox is live, not that a human answered. **And it does not burn her single alert** — when she
returns and replies for real, that still counts as her first.

### 3. A bounce

**A bounce never notifies anyone.** The lead gets **Cold only** — no *Connected*, no *Responded*,
because a bounce proves the opposite of engagement: no human ever saw the message. A note is written
on the lead, and the bounce is counted per sending inbox and per recipient domain, because one bounce
is noise and a rising rate is the signal.

**The trap worth knowing:** Smartlead delivers every bounce **twice**, and the second copy is shaped
exactly like a reply, with not one bounce field on it. It once ran the whole reply path — posted to
the team channel and computed a label set containing *3. Responded*. Three independent checks now
catch it.

### 4. An unsubscribe

They clicked unsubscribe. That is a deliberate human act and an explicit stop request, so the lead
gets **Cold + Connected + 3. Responded + DO NOT CONTACT**, in one write. Smartlead is told to
unsubscribe them. Nobody is notified — there is nothing for a human to do.

## What lands in the do-not-contact registry

**Also nothing** — and this surprises people.

The email path marks someone in **Pipedrive** (the label) and in **Smartlead** (the unsubscribe)
directly and immediately. It writes **no registry row**. So the registry does not know that this
person opted out, and anything reading the registry — the gate, the hourly detector — will not see
it.

The registry is filled from a different direction: **the creation watcher**, which spots leads a
salesperson created by hand or that came from Surfe, plus hand-fired imports.

## If she was already protected

- **If someone asked the gate:** blocked, never loaded, done.
- **If nobody asked:** she gets the email — but here, unlike LinkedIn, there is a second line of
  defence. **Every hour**, the escalation detector cross-checks live cold campaigns against the
  registry and shouts in ops if a protected person is sitting in one. It **detects; it does not
  prevent**, and it reads at most 500 leads per campaign — saying so when a campaign is bigger.
- **From today there is a third line:** the projector is pushing registry rows outward — the
  Pipedrive field and label for about 564 people now, and Smartlead unsubscribes for the
  negative-reply and meeting rows once the exact list is confirmed. Once that runs, a protected
  person is unsubscribed in Smartlead itself and cannot be sent to at all.

---

# The two paths side by side

| | **LinkedIn** | **Cold email** |
|---|---|---|
| How the first touch reaches us | HeyReach tells us | **we have to ask, every 15 minutes** |
| Reply read and categorised | no — a reply is a reply | **yes, by an LLM, with a confidence floor** |
| Reply forwarded to a salesperson | no | **yes, by sending inbox** |
| Bounces | n/a | never announced; never labelled *Responded* |
| Out-of-office | n/a | never announced; alert slot preserved |
| Opt-out handled automatically | **no** | yes — unsubscribed and labelled |
| Writes to the do-not-contact registry | **no** | **no** |
| Protected person caught after the fact | **nothing checks** | hourly detector |
| A lost event comes back | **no — it is gone** | sent and replied: yes. bounce and unsubscribe: no |

## The three sentences to say out loud

1. **Both channels notify a human once, on the first real reply, and only after Slack confirms it
   landed.**
2. **Neither channel writes to the do-not-contact registry** — the registry is fed from the CRM side,
   and until today it had no automatic effect on the sending tools.
3. **A lost LinkedIn event is lost.** Cold email recovers sends and replies automatically; bounces
   and unsubscribes it does not.
