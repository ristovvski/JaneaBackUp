# Auditor: evidence for the Smartlead projection redesign — mechanisms (a) (b) (c)

Read-only, no writes. 2026-08-12T13:5xZ. Answers the three candidate mechanisms with docs + wire, and
states plainly what cannot be settled without a send.

**Headline: (b) via client scoping is DEAD — this account has no clients. (a) is the only mechanism
that can distinguish cold from nurture, and it is the one we control.**

**UPDATE 2026-08-12, Gmail experiment — (c) is now SETTLED, and worse than I framed it.** Global
unsubscribe blocks the lead at **ADD time**, silently: the add call returns `ok:true` and no lead
lands, and `ignore_unsubscribe_list` does not override it. See §(c-resolved) below. The 623-unsubscribe
would have made 538 repliers **permanently un-addable to any campaign including nurture, with no
visible error anywhere**. The freeze is retroactively hard-proven on the wire.

---

## (b) Scoped suppression that doesn't kill conversations

**Client-level scoping is not available.** `GET /api/v1/client` returns `[]` — zero clients. Both
mechanisms carry a client dimension (`unsubscribed_client_id_map: {"0": …}`, block-list rows
`client_id: null`), but with no clients defined there is nothing to scope to. Creating clients to
partition cold from nurture is a structural change to the account, not a config flip.

**Campaign-level scoping DOES exist and is documented:**
`POST /api/v1/campaigns/{campaign_id}/leads/{lead_id}/unsubscribe` — *"unsubscribe a lead from a
specific campaign only (not globally)"*, as distinct from the global form the sweep currently uses.

So a scoped mechanism exists at campaign granularity: suppress in the cold campaigns, leave nurture
campaigns untouched. Its limitation is that it is per-campaign and therefore says nothing about
**future** cold campaigns — which is precisely the gap (a) closes.

## (c) Does a block-list entry kill existing conversations? — UNPROVEN. Do not add the 288.

Documented behaviour (help centre): blocked addresses "will no longer receive messages from your
campaigns", plus **automatic exclusion from new lead uploads**. That second clause is significant — the
block list is already a provider-side pre-add guard.

**What the docs do NOT say**, verified by reading them rather than assuming: nothing about replies,
nothing about master-inbox conversations, nothing about in-progress nurture sequences. The DNC help
article is a 404. So the provider does not document the answer to Nik's question.

**Wire evidence I do have, and exactly what it proves.** The fixture lead
(`pii-c61c7d08@example.invalid`, SL lead 4306240392) was **globally unsubscribed at 2026-08-11T13:15:59Z**.
Afterwards:

| observation | value |
|---|---|
| campaign status | `BLOCKED` |
| **a FORWARD succeeded at 2026-08-11T13:45:56Z** | **30 minutes after the unsubscribe** |
| `message-history` retrievable | **yes — 21 items** |
| reply history intact | yes, all 8 prior replies still present |

**What this proves:** an unsubscribed/BLOCKED lead is still fully processable — WF-2 handled it, the
forward-email API call still succeeded, and the entire conversation record remains readable. Nothing
about unsubscription broke our pipeline or destroyed history.

**What this does NOT prove, and I want to be exact about it:** the forward-email call delivers to *our
own* mailbox (`rune@janeasystems.com`), not to the lead. So it is **not** evidence that we can still
email the lead. Whether a nurture send or a master-inbox reply reaches a globally-unsubscribed lead
cannot be determined from any read — it requires actually sending.

**The safe experiment exists and should be run before the 288:** send one nurture-style message to the
fixture address (Nik's own gmail, already unsubscribed and already blocked) and observe whether
Smartlead accepts and delivers it. That is a single write to a throwaway internal address and it
settles the question that no amount of reading will. Testing it on anyone in the 288 is not acceptable.

## (c-resolved) — Gmail experiment, Outcome B-strong. SETTLED, and by a different mechanism than I predicted.

**Result:** a globally-unsubscribed lead is blocked at **ADD time**. The add call returns **`ok:true`
and no lead lands**. `ignore_unsubscribe_list` does **not** override it. Nurture in Smartlead works by
enrolling a lead in a campaign, so an unsubscribed lead cannot be enrolled in a nurture campaign at
all — and the failure is invisible at the call site.

**Retroactive impact of the projection we froze:** the 623-unsubscribe would have made **538 repliers
permanently un-addable to any campaign, cold or nurture, with no visible error anywhere in the stack.**
Not "hard to reverse" — un-addable, silently, forever, via an API with no documented resubscribe.

**I have to own that my proposed experiment would have missed this.** I framed the open question as
*"can we still send to / reply to an unsubscribed lead?"* and proposed a **send** test. The decisive
mechanism was an **add** block. A send test against an existing thread could plausibly have come back
"works" and read as reassurance, while the mechanism that actually severs nurture sat one API call
away, untested. The lesson is not "test on the fixture" — I had that right — it is **probe the
mechanism the requirement depends on, not the one the metaphor suggests.** "Suppression" made me think
about delivery; enrolment was the load-bearing operation.

**Still open, and now much lower stakes:** whether an in-thread master-inbox reply to an unsubscribed
lead is delivered. If it is, existing conversations survive while new enrolment is impossible — worth
knowing for the redesign, but it no longer changes the freeze decision.

**Consequence for the 288:** unchanged and reinforced. Do not add them to the block list until the same
add-time question is answered for block-list entries specifically. The docs already state block-list
entries cause "automatic exclusion from new lead uploads", which is add-time exclusion by description —
so the presumption is now that block-listing produces the *same* un-addable outcome. That is acceptable
only for a population we will never want to contact again by any channel.

**Additional risk specific to the 288.** They are "not found in Smartlead", so suppressing them means
adding **domains or addresses that have no lead record**. Domain entries have collateral scope by
construction: one entry blocks every address at that domain, including colleagues we may be actively
nurturing. Note the current list is deliberately conservative about this — `microsoft.com`,
`nvidia.com`, `amazon.com`, `google.com`, `ibm.com` are **not** domain-blocked despite carrying 69, 43,
121, 57 and 24 individually-blocked addresses respectively. Only competitor-shaped domains
(`accenture.com`, `deloitte.com`, `cognizant.com`, `impact.com`) are blocked wholesale. Adding domains
for the 288 would break that pattern and should be an explicit decision, per domain, not a bulk projection.

## (a) Pre-add registry check — the only mechanism that can tell cold from nurture

Neither provider mechanism knows the difference between a cold campaign and a nurture campaign. Our
layer does. Assessment:

- **Enforceable:** every campaign add we perform runs through n8n, and the estate is small and fully
  enumerable (I have verified 18–19 workflows, 6 active, against an expected-state table twice).
- **Correct by construction for the actual requirement:** "never enter these people into COLD
  campaigns" is a decision about *which campaign* a lead is being added to — the only place that
  information exists is at the add site.
- **Covers future campaigns**, which campaign-scoped unsubscribe does not.
- **Reversible**: a registry row can be corrected; a global unsubscribe cannot.
- **Known gap to design for:** it is only as good as its coverage of add paths. Any add performed
  outside n8n — a CSV upload in the Smartlead UI, a Clay/Make path, a manual add — bypasses it. That
  is where the block list's "automatic exclusion from new lead uploads" is genuinely complementary:
  provider-side for UI/CSV adds, our-side for programmatic adds. Belt and braces, with the block list
  used **only** for populations where conversation-severing is acceptable.

**Recommended shape, for Nik's decision:** (a) as the primary control; campaign-scoped unsubscribe for
existing cold campaigns if immediate suppression is wanted; global unsubscribe and block-list entries
reserved for the §3 population (verbatim hard opt-outs and seed offboards) **after** Melisa's
per-category word and **after** the fixture send-test settles (c).

## Accepted: review-protocol addition

Added to my protocol, and it generalises past this incident:

> **Any projection design must state which OTHER uses of the same provider it could break.** A provider
> is not a single-purpose channel. Smartlead is cold outbound **and** nurturing **and** the sales
> executives' real mailboxes. Before a projection is approved, the design must enumerate every use of
> that provider and say what the projection does to each.

I would add a second clause from the same root cause, because the near-miss was not only about scope:

> **For any irreversible projection, name the reversal procedure before the go.** If there is no
> reversal, that fact belongs in the go/no-go, not in a footnote. The one-way door was findable a day
> early because the question "how do we undo this?" had no answer.

### Third clause, from the Gmail experiment — filed under the irreversible-projection protocol

> **A 2xx is not an outcome. Read back the object.** Smartlead's campaign-add returns `ok:true` for an
> add that silently did not happen. Every add-call must verify lead presence afterwards; every
> projection must assert the projected state, not the call's status code.

This is the **fourth** instance of the same class in this audit, which is why it belongs in the house
rules rather than in one workflow's notes:

| # | claimed success | actual outcome |
|---|---|---|
| 1 | n8n execution `success` | `Reply Alert` returned `{"error":"invalid syntax"}` — 11 days of alerts never sent |
| 2 | WF-2S reported `__idle: true` (healthy) | structurally blind; 176 SENT events unseen |
| 3 | staticData claim written by the node | clobbered by an overlapping execution — 42 of 55 claims lost |
| 4 | Smartlead add returns `ok:true` | no lead lands; unsubscribed leads silently un-addable |

The generalisation that covers all four: **never accept a system's self-report as evidence of its own
effect.** Verify from the other side — the provider's object, the CRM record, the Slack wire, the
persisted store. That is the whole method of this audit, and each of the four was found by applying it
rather than by reasoning about the code.

**Reversal note for the record (Pipedrive, per Nik):** field 686 clearable, label removable by id-set —
which is exactly why Pipedrive goes first. Documented here so the protocol has a worked example of a
projection that *passes* the reversal test, not only ones that fail it.

## Status of my other work

- **Pipedrive FIRE: unaffected, and my post-run protocol stands** — baseline captured pre-fire
  (57,847 non-archived leads, 5 carrying 'DO NOT CONTACT', exact id set saved), id-set diff plus
  label-loss watch ready. Sequencing as ruled: Pipedrive window, my post-run, then anything Smartlead.
- **The 623×4,024 no-op cross-reference is now moot for its original purpose** (there is no Smartlead
  write to no-op against). The matcher and the block-list index remain built and validated if the §3
  subset needs the same treatment on a smaller population.
- **Still open from my side, unrelated to this freeze:** `SL Mark Done` does not implement the
  permanence rule (writes only `projections_state`), and the registry TTL-null sweep risks keying on
  Smartlead-side CSV labels that the registry may not carry.
