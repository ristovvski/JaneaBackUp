# 02 — OPEN ITEMS

Deliverable #2 of the communication audit (see `communication_audit_brief.md`).
Source: `COMMS_AUDIT_build/ledger.json` — 937 records (Slack R0001–R0415; meeting transcripts R0416–R0955; owner corrections R0956–R0958).
Clock: all "open for N days" figures are relative to **2026-08-19**.

## How to read this document

- **Every item carries** record id · date · source · verbatim quote. Where a quote is a meeting transcript it is marked with the split filename.
- **"No evidence of delivery in ingested material" ≠ "not delivered."** The corpus covers five Slack surfaces and 21 meeting transcripts. It does **not** cover unrecorded calls, WhatsApp, ClickUp comments, Pipedrive notes, email, or Fireflies-untranscribed meetings. Where the ledger only shows absence of confirmation, this document says so in those words. Where a party stated non-delivery themselves, it says "stated as not delivered."
- **[CONTESTED]** marks the 14 records carrying `status_contested: true` — two extraction batches proposed conflicting readings, the newer evidence was applied, and the older reading is preserved. Both readings are shown. **These are not resolved here; the owner resolves them.**
- **OUT-OF-CORPUS** marks records R0956–R0958 (owner corrections supplied in terminal on 2026-08-19, not Slack or transcript quotes). They are never cited as in-corpus evidence.
- Nik's own items are listed **first** in every section, per owner instruction. Within each group, items are sorted by **consequence**, not date; the reason each item is consequential is stated.
- Owner attribution follows the ledger's `participants` field. Transcript speaker mappings marked INFERRED in the ledger are reproduced with that caveat.

---

## 0. THE SINGLE MOST TIME-SENSITIVE ITEM — Sergey's outstanding ask (R0238)

**2026-08-18 · #infra-issues · Sergey Cujba · open 1 day at cutoff · [record R0238, DECISION, status "active — plan partially materialised 2026-08-11"]**

> "we need a plan and a timeline to make sure that we have a reliable and predictable system that is owned by you, @Mykyta Kryvosheia, and it's your task to tell us what you need for this ... the current setup shows signs of non-reliability and this is not good"

Sequence, stated plainly and without interpretation of intent:

1. **2026-08-17**, three items were reported in the same channel by Melisa Draksler and left open in the ledger:
   - **R0228** — "this lead replied 12 days ago (Aug 5) ... notification about his reply was sent again yesterday. Also, in Pipedrive we can see only messages that he sent, and not Mario's messages that were sent manually - this is a big issue for us because we need to have the entire communication visible in Pipedrive." Status: open, no resolution in ingested material.
   - **R0229** — "Person-7267ff83 is an old lead from 6 months ago, and he's currently in the deal stage. For some reason, our system created his record again and assigned him to me. Bugs like this are going to affect our reports, so please make sure you fix this!" Status: open.
   - **R0231** — "Also, another issue: Number of leads from Sales sprint have been created with really weird names:" Status: open.
   - **R0230** (Sergey, same day): "We need to make sure that the reason is also found out" — a root-cause expectation attached to R0229. Status: unclear.
2. **2026-08-17**, Nik: **R0232** — "Will process everything tomorrow guys". Ledger status: *superseded* — the next day's only visible follow-up was blanket, not per-item.
3. **2026-08-18**, Nik's two responses to R0238:
   - **R0239** — "no problem i will give taskto Melissa for several hours ... it will help a lot". Ledger status: open — "delegates the response to Melisa rather than directly telling Sergey what he needs, per R0238's explicit ask."
   - **R0240** — **"Won't post reports just consider everything fixed"**. Ledger status: open — "does not supply the plan/timeline Sergey explicitly asked for in R0238, and does not individually confirm resolution of R0228/R0229/R0230/R0231; this is the most recent message in the channel as of ingestion."

**What makes it consequential:** the ask is from the director, it is the newest open item in the corpus, it is addressed to Nik by name, and the response on record neither names the three then-open issues nor supplies a plan or a timeline. Three named bugs remain in "open" status in the ledger with no per-item resolution recorded.

**Cross-cutting note the corpus itself flags:** four days before R0238, at the 2026-08-14 ownership meeting, **R0432** (AGREEMENT, `01_UNKNOWN_dnc-and-migration-sync.txt`) records Melisa stating the ownership transfer is in a good state — "Right now I just need to report what's wrong and he takes care of it" — and Sergey answering "Sounds great to me." The ledger already flags that R0432 and R0238 "sit against each other." Both stand; neither is merged.

---

## A. QUESTIONS ASKED AND NEVER ANSWERED

18 QUESTION records carry an open/never-answered status. Grouped below by **who owes the answer**, with Nik's own unanswered questions first per owner instruction.

**Top three by consequence in this section:** R0650 (MQL/SQL data model — rulebook-blocking, 40 days), R0473 (ownership boundary definition — the item Sergey re-opened as R0238, 8 days), R0313 (BDR process gap open 72 days, affects live daily work).

### A.1 — Questions **Nik** asked that are still unanswered

| id | date | days open | asked of | quote (verbatim, abridged) |
|---|---|---|---|---|
| R0098 | 2026-07-18 · dm-melisa | 32 | Melisa | "I want access to reporting and how its being made" |
| R0162 | 2026-08-14 · dm-melisa | 5 | Melisa | "you mentioned some other labels disappeared from leads. Can you send me 2-3 specific examples (lead names or links)? We keep full before/after snapshots, so we can check exactly what happened to each" |
| R0193 | 2026-07-27 · dm-sergey | 23 | Sergey | "we need to finally decide on this - do you want me to 1. put it all in ClickUp 2. I don't know what sync is needed, that's up to you when/how 3. or will it sit in the backlog" (orig. Ukrainian) |

- **R0098** — *consequential because* it is an access dependency, not a preference: it recurs a fortnight later as **R0148** (2026-08-04, CONCERN, status open), where Nik states "either i get admin access to everything outbound team uses either its again 'Hey person xyz go to yzd and ask to give blablabla'" and Melisa replies "I'm here for almost 3 years and I don't have access to everything because this is how things work in bigger companies and I can't help you with this." The specific reporting-access ask is never granted or refused in ingested material.
- **R0162** — *consequential because* it is the evidence request underpinning a disputed label-loss claim; without the 2–3 examples the dispute cannot be closed from either side. No answer found in ingested material.
- **R0193 — [CONTESTED]** — *consequential because* it is a direct request for a decision from the director on how Nik reports work, and it is the third airing of the same question (see §E).
  - **Applied reading:** "OPEN - still unresolved; the 2026-08-14 meeting settles ownership scope (R0432) but records no reporting/communication protocol."
  - **Earlier reading preserved:** "OPEN — Sergey: 'yes, we can discuss this too in one of the upcoming syncs' — third deferral of the same reporting-protocol question (06-26 R0180, 07-17 R0191/R0192, now again), never resolved in ingested material."
  - A third proposed reading in `update_history` (batch B4): the ClickUp half was already answered on 2026-07-21 by **R0595** ("please put them in ClickUp so we are aligned on what should we expect when"), six days *before* the question was re-asked; the sync-cadence and backlog halves remain open.

Also owed to Nik, recorded as a commitment rather than a question: **R0446** (2026-08-14, `01_UNKNOWN_dnc-and-migration-sync.txt`) — Nik asked whether the reply-labelling migration improved accuracy ("Did we have an improvement? That's a question"); Melisa: "Maybe I'll take a look and let you know." No result in ingested material. Nik states in the same exchange: "Honestly I did not check the right labels or not." Listed again in §B.3.

### A.2 — Questions **Nik** owes an answer to

- **R0509** · 2026-08-14 · `02_UNKNOWN_heyreach-pipedrive-walkthrough.txt` · 5 days · asked by Speaker 2 (unidentified; ledger notes roster suggests Araks Grigoryan / Lule Salihu / Melisa Draksler — mapping unconfirmed).
  > "is this like sending schedule? ... Or it's also like when campaign in general is active and is checking for example for people who accepted, people who replied" / "So if the campaign is not active, it will not check for replies."
  Nik: "No, I think we receive replies ... I'm 90% sure ... It's a good question. If maybe I'm wrong, I will check it out guys and give you the answer in the same chat."
  Status: partially-answered at explicitly 90% confidence, **contradicted by observed behaviour in R0510**. *Consequential because* if HeyReach does not emit reply webhooks while a campaign is paused, replies are silently lost — and the answer given to the BDRs is the optimistic one.
- **R0514** · 2026-08-14 · same file · 5 days · asked by Speaker 4 (unidentified, same caveat).
  > "if they don't accept do we withdraw it automatically? Is there such a functionality or we don't do anything."
  Nik: "it should exist somewhere. But what Nikita doesn't remember if so I gonna just put you a message." Status: OPEN, rolled into commitment **R0515**.
- **R0273 — [CONTESTED]** · 2026-07-23 · #gtm-engineering · 27 days · Sergey.
  > "please let us know the current status with: trigger-based campaign estimates / your estimates on a timeline to take over the ownership of running the outreach infra ... / your estimate on a timeline to deal with the DNC list, and if it's possible to parallelize these items"
  - **Applied reading:** "answered-in-part; ownership boundary still OPEN as of 2026-08-11 (see R0473)."
  - **Earlier reading preserved:** "answered — earliest ingested instance of the ownership-handover ask."
  - Third reading in history (B4): both scope and parallelisation were put and answered two days earlier in the 2026-07-21 GTM sync (R0566/R0576/R0595), so this Slack ask is not the earliest instance.
- **R0180 — [CONTESTED]** · 2026-06-26 · dm-sergey · 54 days · Sergey.
  > "what's your take on how do you communicate about what you are working on, what will be ready when, and how do you let everyone know that something is done ... no need to answer this right now, but we will need to align on this when you are back"
  - **Applied reading:** "partially-answered-by-R0483 (2026-08-05) — advance-notice/coverage principle stated and mutually accepted; the wider 'how do you report what you are working on' protocol remains OPEN."
  - **Earlier reading preserved:** "OPEN — deferred by Sergey to a later alignment that is not confirmed anywhere in ingested material."
  - Two further readings in history: partially answered in substance on 2026-07-10 (R0668: ClickUp entries with start/due dates, decomposition, align-before-implement, weekly/bi-weekly status presentation) and on 2026-07-03 (R0750, Nik assenting "Yeah, guys, definitely") — in both cases **never written down**, which the ledger gives as the reason for the later re-asks.
  - *Consequential because* this is the root of the recurring "I told you / you are not asking me" friction the audit exists to settle, and it is the oldest still-live protocol question in the corpus.
- **R0414** · 2026-08-17 · #lead-generation-team · 2 days · Araks Grigoryan and Lule Salihu.
  > "And can we remove you from an assignee on ClickUp? / Sure, will do that, can we also add me and Araks on each lead as a BDR owner (also update the next scan date if there's none there)"
  Status: OPEN, no answer in ingested material (the file ends the next day on an unrelated thread). *Consequential because* it is an ownership-field change on live leads, requested two days before the cutoff and still unacknowledged.
- **R0937** · 2026-06-16 · `21_UNKNOWN_outreach-sequence-review-ukrainian.txt` · 64 days · Sergey (inferred: Speaker 1).
  > "I wonder whether there is Job Function data here ... in Sales Navigator we have which function a person performs ... one could potentially filter by function or use it as a prequalification factor. Because ... if you give an agent absolutely everything that is here, it starts coughing" (orig. Ukrainian)
  Status: partially-answered — the agent-degradation worry was addressed by Nik's trimming formula (R0938); the specific question (does a Job Function field exist in the Apify data, could it be a prequalification factor) is never answered on the call.

### A.3 — Questions **Melisa Draksler** owes an answer to

- **R0404** · 2026-08-12 · #lead-generation-team · 7 days · Lule Salihu.
  > "Can we then send the messages through the automation in HeyReach, or we need to do it manually?"
  Status: OPEN — "never directly answered; Melisa's reply ('But those contacts already received at least 2 follow ups, right?') redirects to a different point rather than answering automation-vs-manual." *Consequential because* it is the operational precondition for the September nurture plan that surfaces six days later as **R0415** (§C) — the BDRs proceeded without a ruling.
- **R0350** · 2026-07-09 · #lead-generation-team · 41 days · Lule Salihu.
  > "For the connected ones that we've sent the 2nd follow up already. When would be the next step (timing wise) to send a third follow up"
  Status: OPEN — **evidence gap, not confirmed silence:** the thread is marked "3 replies (latest: 2026-07-09 12:02:33 IDT)" but the reply content was not captured in the scraped file. This may well have been answered; the corpus cannot say.
- **R0098 / R0162 / R0446** — see §A.1.

### A.4 — Questions **Sergey Cujba** owes an answer to

- **R0473** · 2026-08-11 · `04_UNKNOWN_dnc-alignment-integration-review.txt` · 8 days · raised by Sergey, answer owed jointly by Sergey and Nik.
  > [Sergey 41:36–43:10] "I think we should still get aligned on what do we mean by this ownership ... This is everything that Melissa owns still. And Melissa needs to pay her attention to see whether everything is done or not ... What exactly do you own, [Nik]?" / [Nik 42:10] "Right now I currently, I'm currently responsible for any campaigns" / [Sergey 42:17] "this is a very broad definition of what is owned ... I just want to make sure that we have clear definition of where are the borders of the responsibilities"
  Status: OPEN at end of meeting, explicitly deferred to the Friday 2026-08-14 meeting (R0479). The ledger also records that Sergey recalls Nik saying at a previous meeting that some area "is not there" in his responsibility but cannot remember which — **so the disputed boundary itself is unrecorded**. *Consequential because* this is the definitional question underneath R0238; the 08-14 meeting closed ownership *in principle* (R0432) without producing the boundary list Sergey asked for.
- **R0453** · 2026-08-12 · `03_UNKNOWN_event-campaign-outreach-planning.txt` · 7 days · asked by Melisa.
  > "we also still don't know about trigger based campaigns. Like what kind of volume we can expect for each hypothesis. Like is it going to be 500 people in the, in the campaign or 2,000 or 5,000"
  Status: OPEN — deferred, not answered: Sergey "we're going to get to know I guess when we start to filter out potential audience." *Consequential because* it is the input to an unreconciled capacity pair the ledger flags: **R0040** (~400 emails/day using Toby's mailboxes) vs **R0251** (600/day for the whole infrastructure).
- **R0450** · 2026-08-12 · same file · 7 days · asked by Melisa, owed jointly by Sergey and Melisa.
  > "it's also a matter of question whose mailboxes are we going to use and how we are going to basically divide that across four sales executives ..."
  Status: OPEN — no allocation decided; Sergey closes with "no decisions to make right now"; Nik's only reply, "Okay. The answer is clear", does not answer it. *Consequential because* September event campaigns cannot be built without a mailbox/LinkedIn allocation.
- **R0650** — see §D (definitional, addressed to Sergey directly, no response at all).

### A.5 — Questions owed by others / with no assigned owner

- **R0313** · 2026-06-08 · #lead-generation-team · **72 days** · Lule Salihu → owner not assigned in corpus (process question, Melisa is the process owner of record).
  > "what should we do if there's a task outdated on a lead that is closed as a deal is created. In this case, do we check the history on the deal record or how is the process we should follow in these cases"
  Status: OPEN — "still no direct answer through 2026-08-18; the August outdated-tasks review effort (R0398-R0401) covers the general topic operationally ... but never addresses this specific deal-closed sub-case in ingested material."
- **R0326** · 2026-06-23 · #lead-generation-team · **57 days** · Araks Grigoryan → same.
  > "do we need to bring back those outdated tasks that were created? Cause we closed them before adding to nurturing"
  Status: OPEN — no answer found in ingested material; same caveat as R0313.
  Both are *consequential because* they are daily-work blockers for the two BDRs, they are the two oldest unanswered questions in the corpus, and both are rulebook material (P2 entity lifecycle / P8 human roles) — see §F.
- **R0856** · 2026-06-19 · `19_UNKNOWN_mykyta-melisa-bahonjic-1on1.txt` · 61 days · **Melisa Bahonjić** (a different person from Melisa Draksler; see R0957, OUT-OF-CORPUS).
  > "we will have AI4 in August, but we still need to decide how we are going to move with that one. Are we going to use like Stefan? Because Rune and Mario are going to attend the same event. So we need to launch like campaigns on behalf of both of them. So we'll see."
  Status: answered later, in a different thread and by other people (R0085/R0086 on 2026-07-17; two-sender arrangement reflected in R0071). No answer given on the call. Recorded for completeness; the asker departed the GTM role ~July 2026.

### A.6 — One asymmetry worth stating

The task brief listed **R0012** ("if we handle replies what would be bdr doing", 2026-06-02, dm-melisa, Nik) as an item deferred to a call. **The ledger does not support the deferral note:** R0012's status is *answered-by-R0071* — Melisa's 2026-07-13 definition ("BDR owner is assigned only when we get reply and it depends which bDR will support which event or person ... for ai4, one BDR will support Rune, other Mario"). The gap is real but is a **latency** gap, not a never-answered one: **41 days** between question and answer, and the answer arrived in a DM rather than in the channel where the BDRs work.

---

## B. COMMITMENTS STILL OPEN, BY OWNER

131 COMMITMENT records; 88 carry a status other than plain "delivered". Status vocabulary used below, per the brief:
**open** (promised, no confirmation of delivery in ingested material) · **overdue** (a stated date passed) · **dropped-silently** (no further mention anywhere, or the owner stated it lapsed) · **delivered-late** (delivered after a chase or after the stated date) · **partially-delivered** (part landed, part did not).

**Top three by consequence in this section:** R0240 (§0 — the plan Sergey asked for), R0515 + R0512 (three answers and a sync patch owed to the BDRs who are running live campaigns on the assumption they are handled), R0918 (Sergey's person-vs-company DNC question left with no owner for ~6 weeks; a company-level application later wiped ~2,000 Pipedrive leads' labels).

### B.1 — Nik's commitments (listed first, per owner instruction)

**B.1.a — Time-critical / directly downstream of live work**

| id | date | days | status | promise (verbatim, abridged) | evidence of partial delivery |
|---|---|---|---|---|---|
| R0240 | 08-18 | 1 | open | "Won't post reports just consider everything fixed" | none; see §0 |
| R0239 | 08-18 | 1 | open | "no problem i will give taskto Melissa for several hours ... it will help a lot" | none; delegates rather than answers R0238 |
| R0232 | 08-17 | 2 | superseded | "Will process everything tomorrow guys" | next-day follow-up was blanket (R0240), not per-item |
| R0515 | 08-14 | 5 | open | "I just gonna answer all the questions that left in chat and I mean there are three already ... I gonna answer those questions with research" / "I will follow up on those that you already raised" | none found; the three items are R0509, R0514 and the R0512 question. No follow-up post in the ingested Slack channels |
| R0512 | 08-14 | 5 | open | "it's gonna be a fast patch. I'm gonna patch it and I also gonna backfill those ... I'm thinking I would be able to backfill the message but I am not 100% sure right now" | none; two deliverables (sync our own outbound LinkedIn messages into Pipedrive; backfill historical), feasibility of the backfill explicitly unconfirmed by Nik himself |
| R0418 | 08-14 | 5 | open | "today gonna be landing I gonna backfill every from AI for [Ai4] campaigns in Regent Street ... also every[one] who replied to any campaign and everyone who had a meeting goes to registry is going to be also deployed today" | deployment claimed for the day of the meeting; no post-meeting confirmation in ingested material |
| R0464 | 08-11 | 8 | open | [Melisa] "leads that we received for AI4 ... Are they already added to the net [DNC] contact list?" / [Nik] "I don't need to add them. I think it's not done yet. I will make it" | discussed again three days later (R0418); no completion confirmed |
| R0422 | 08-14 | 5 | open | "To be honest. I will patch it ... I just gonna patch it and I don't need to do anything again" (DNC-in-campaign detector to ignore lead-nurturing campaigns) | none |
| R0429 | 08-14 | 5 | open | "I just gonna take some session with my friends AI and we're gonna discuss how ... things can be implemented ... and afterwards I'm gonna send this information to you ... you're gonna approve it or not" | none; the design fork (Slack notification vs automatic enrichment on create) was left undecided in the meeting |
| R0423 | 08-14 | 5 | open | "I got Jim almost got Jim's credentials to also whenever he adds some person to campaign ... to sync it with pipe drive ... And add those people to DNC list" | credentials "almost" obtained at time of speaking; scope narrowed by Melisa in the same exchange |
| R0146 | 08-05 | 14 | open | "switching email reply processing to the new workflow today in a quiet window ... let me know if you give green light" → rescheduled by Melisa to Friday | "Friday's switch is on track" (R0151); **no confirmation the cutover completed** anywhere through 2026-08-18 |

*Why this block is consequential:* every item either (a) is the response Sergey asked for, (b) is owed to the two BDRs running live outreach, or (c) concerns DNC/deliverability, where a miss contacts someone who must not be contacted.

**B.1.b — Ownership, documentation and handover**

- **R0478** · 08-11 · 8 days · **open**. Melisa: "it's also important to onboard Stefan on this so that he's aware how everything works in case something breaks while you are away ... And also those channels where you get reports about stuff breaking. It would be ideal if you could also add me to those chats ... so that not everything is on one person." Nik: "I'm gonna onboard him, give him some documentation ... afterwards he gonna be able to maybe use [Claude] code as well." Neither part confirmed delivered; the pre-existing short LinkedIn-automation documents are agreed in the meeting to be too thin. **Melisa's parallel ask to be added to the failure-report channels gets no explicit answer in the transcript.** Related: **R0126** (Melisa/Nik, 07-29, open — "Please make sure that Stefan is also aware of all changes"), still an active ask on 08-05 (R0484) and 08-11.
- **R0595** · 07-21 · 29 days · **open**. Sergey: "Mikita, when you understand at least approximately how the timeline is going to look like for both of these tasks, please put them in ClickUp so we are aligned on what should we expect when." No ClickUp timeline for the ownership transfer or the DNC list is confirmed anywhere in ingested material. *Consequential because* it is simultaneously the answer to R0193 and an unmet instruction.
- **R0546** · 07-27 · 23 days · **partially delivered / open**. Nik takes over the daily Pipedrive data-quality check: "I'm gonna be doing it right now from. From this moment. I'm gonna be checking"; Melisa: "you need to check every day if something is like, are we sending all the fields that we need to send to Pipe Drive?" Mixed later evidence: on 2026-08-06 the 372 Ai4 leads missing Event name were surfaced by **Melisa** in #lead-generation-team (R0389), not by the daily check — though Nik then root-caused and fixed them (R0149).
- **R0583** · 07-21 · 29 days · **unclear**. "I'm gonna have one call. Maybe with you, maybe with Stefan. With Stefan for sure." No ingested record confirms a Stefan handover call; on 2026-08-04 Nik was still asking for Stefan to be added to Slack (R0203).
- **R0460** · 08-11 · 8 days · **open**. "I can do even much broader audit if you want to see how it was working before and how many errors, problems, etc. We had ... I will do it very soon. I gonna give you this, provide you with this report." Sergey: "I think that we should put this as a task." No timeline set, no ClickUp entry recorded in the transcript; the audit window was left undecided.
- **R0038** · 06-29 · 51 days · **open, unverifiable from the corpus**. "i will put down things in slack channel i created for myself" — a private channel is outside the ingested surfaces, so the corpus can neither confirm nor deny.
- **R0029** · 06-26 · 54 days · **open**. "We will migrate without any problems i promise" — the LinkedIn migration was still being worked through at end of that batch (R0060/R0062).
- **R0188** · 07-16 · 34 days · **open**. "in any case i will be at next one and not go anywhere ... i will attend all of those" — no explicit confirmation of full compliance in ingested material.
- **R0166** · 08-18 · 1 day · **open, in progress**. "i will take ALL transcripts from beginning of the work here / And hopefully answer all i need" — this audit is that work.

**B.1.c — Data-quality and design items with no confirmation**

- **R0549** · 07-27 · 23 days · **open**. "I will, I will update them ... I can update them in smartly [Smartlead]" — missing job title / organization / LH current company for London sprint leads. The confirmed later backfill (R0149, 08-06) covers Event name and Hypothesis, **not** these fields.
- **R0531** · 07-29 · 21 days · **open (no decision)**. "those people ... we can just make some kind of structure when we don't exclude them but we send them for some review ... So those should be like separate status" / "let me think about this case. Maybe I can come up with something better than we have in place and afterwards discuss it." Deferred by mutual consent (Melisa: "Okay. This is not like urgent thing"); no return to it in ingested material, and no such "review" status appears in any later description of the registry (R0144, R0161).
- **R0295** · 07-31 · 19 days · **open**. "I see the problem will tell you solution later" — the Surfe / manual-LinkedIn-message sync gap; no delivered solution in ingested material through 08-18. Note this is the same class of gap Melisa reports as R0228 on 08-17.
- **R0705** · 07-08 · 42 days · **open**. "I know the workaround for this. So basically for any next campaign I gonna fix it" (wrong-company enrichment). Sergey attached an explicit expectation: "even if it's two or three cases, we need a way to first defend it and second demonstrate that we have found a way to adjust and to prevent these things for the future." No confirmation the fix was implemented or verified. Related open item **R0258** (07-06, fix explicitly deferred "next time").
- **R0787** · 06-29 · 51 days · **open (two parts)**. "if this scrape LinkedIn gives actual results I will check it once more ... I will think how to make it work for future instances to not have this problem afterwards" — (a) verify the scraped `Org` field is current, (b) build the re-qualification layer Sergey asked for and Melisa refined. Neither confirmed.
- **R0768** · 07-03 · 47 days · **open**. "After this call I'm gonna be able to relook all at the API documentation and get ... if it's gonna be possible to change the labels and do the stuff without being connected. I think yes." Nik declined to answer in-meeting ("I don't remember the payload"); no answer appears in the batch.
- **R0742** · 07-03 · 47 days · **open**. Assigned by Melisa in Sergey's presence: "He also needs to do some research on pipedrive API and on ClickUp side regarding lead nurturing system." Nik neither accepts nor refuses verbally in the file.
- **R0831** · 06-25 · 55 days · **open, both directions**. Nik: "I can just take a look again. There are a lot of things I've looked into but yeah, I just gonna look again" (re-read the lead-processing requirements document before the walkthrough); Melisa's reciprocal item: "if there is any other document indicator should review please send it to him." Neither confirmed.
- **R0848** · 06-19 · 61 days · **open**. "there are some little changes I need to implement. I just don't remember them. I have audio transcript ... I'm gonna have it on Monday ... And then on Monday we're going to be able to just take a look at the finished table." No confirmation the calibrated table was reviewed that Monday.
- **R0356** · 07-15 · 35 days · **open**. "Will use more advanced model next time" — no confirmation of follow-through.
- Smaller Slack promises, all **open (no confirmation of delivery in ingested material)**: **R0248** (06-27, "Yes we will i gonna spend some time tmrw"), **R0259** (07-06, "i wll make a fix"), **R0267** (07-09, "I will check which provider gives those"), **R0277** (07-23, "3. You will have it by tmrw's morning"), **R0282** (07-23, "ok i will put those, i already created all of the tasks"), **R0084** (07-17, "but i will have time to fix it" — the ledger notes HeyReach follow-up/notification/reply-capture misses were still occurring on 08-11, R0472).
- **R0630** · 07-14 · 36 days · **open as of the meeting**. Melisa: "Mario and Rune are the main priority"; Nik: "Right, right, right. Okay. We're gonna find some time" (connect their accounts to HeyReach).
- **R0646** · 07-10 · 40 days · **open, no evidence of delivery**. To Lilla Szabo: "I'm answered like in an hour maybe something like this. I'm gonna research a bit and I'm gonna give you the answer." No such estimate appears in ingested material. Mitigating context recorded in the ledger: the counterparty's own dependency (R0645) was never delivered either, so the estimate may have been overtaken rather than forgotten.
- **R0842** · 06-25 · 55 days · **open, conditional**. To Person-a2ef1b69: "definitely send me, please, your. Your block scheme. I'm gonna take a look again ... and we're gonna be working on it, I think soon, hopefully." Conditional on R0840, which was also never confirmed delivered.
- **R0735** · 07-03 · 47 days · **open**. "Let me take a look at the stuff we discussed with Melissa and ping you afterwards with some date ... I don't want to just mislead you." No date given in the meeting; probably the same commitment as **R0182** (dm-sergey, same day: "I've gathered documentation ... Will ping you with estimates on Monday"), also open — no later message confirms the Monday estimates were sent.
- **R0564** · 07-27 · 23 days · **partially delivered**. "I just. I want us to migrate so much from this zapier and make." Legacy layer still live afterwards: old Zapier notification automation switched off 08-05 (R0215), old Zapier automations found stripping labels 08-11 (R0218), Make's Ai4 person-creation scenario still in the loop 08-04 (R0132).
- **R0592** · 07-21 · **partially delivered**. Master DNC registry with automated population and label reversal was running by mid-August; the full committed scope was not.

**B.1.d — Dropped, and disclosed as dropped by Nik himself**

- **R0713** · 07-08 · 42 days · **dropped-silently (self-disclosed)**. "Honestly I promised him [Karol] the plan but I had to fix campaign and to do this stuff. So basically I don't even know what's going to be the timeline for this ... I going to tell you when I have something." Sergey accepted the deprioritisation in the same breath, so the item lapsed rather than being tracked. No further mention of Karol's plan in ingested material.
- **R0659** · 07-10 · 40 days · **overdue, self-disclosed at the time**. "Did we have some movement in terms of reaching out to Toby's connections or should I do something to like make to start moving with this ... we did agree on this, but ... I did not like proceed with any further steps." Unblocked in the same call by Melisa requesting the export; outcome three days later was negative — only 12 usable contacts, because Toby's ~4k connections were already on DNC (R0068).

**B.1.e — Delivered-late and superseded (closed; recorded for symmetry)**

- **R0623 / R0275** · committed 07-14 for Tuesday 07-21, chased by Sergey 07-23 (R0273), delivered 07-23 — **delivered-late** (trigger-campaign effort estimates; Sergey closed the meeting with "the action item is on Mykyta. Mykyta. Please keep us posted").
- **R0138** · 08-04 · **delivered-late after a chase**. Melisa: "Btw did you change messaging in HeyReach?" / Nik: "Not yet but it was scheduled for 18:30 my time" / Melisa: "Its 8:12 AM PDT / Event already started" / Nik: "Ok i will change it rn".
- **R0662** · 07-10 · **delivered around the stated window** ("the latest date I will deliver it is going to be Wednesday ... let's just be oriented on Monday"); HeyReach treated as live from Mon 07-13. The ledger flags this as a *candidate* origin of the "deadline for heyreach transfer was until Wednesday" Melisa cites in the 08-05 dispute (R0147) — possible, not established.
- **R0213** · 08-10 · **superseded** ("Today will be switch made"; the root-cause fix landed 08-11, not same-day).
- **R0502** · 08-14 · **delivered same day** (label investigation; Slack R0163 shows the reversal pass with full audit trail).
- **R0562** · 07-27 · **delivered same day** (Event name added to the auto-populated set, R0123); the manual catch-up for existing records was handed to Slava (R0563 — see §B.3).
- **R0276 — [CONTESTED]** · 07-23 · "2. I will take of it very soon - from Monday i can replace all Melissa's actions."
  - **Applied reading:** "delivered - confirmed by R0432 (2026-08-14)."
  - **Earlier reading preserved:** "overdue/unclear — no confirmation of a Monday takeover found in ingested material; dm-melisa R0141 (08-04) and dm-sergey R0238 (08-18) show the ownership handover still being negotiated as an open ask weeks later."
- **R0115 — [CONTESTED]** · 07-21 · DNC scope gathering.
  - **Applied reading:** "delivered - the scoping session itself is now on record: the 2026-07-29 Melisa/Nik 1:1 enumerates the DNC source layers (R0524) and settles the sales-team intake mechanism (R0526 rejected / R0527 agreed)."
  - **Earlier reading preserved:** "substantially delivered by batch C: master DNC registry built, a 623-person Smartlead-unsubscribe pass designed and sanity-checked (R0144, R0160), a lead-nurturing carve-out identified before go-live."

### B.2 — Melisa Draksler's commitments

**Consequential first** — these are the process-knowledge deliverables the rulebook depends on:

- **R0028** · 06-26 · 54 days · **open**. "I will send you written explanation, share some docs and if needed I can also record Loom video." Channel-side echo the same week: **R0249** (06-26, #gtm-engineering) — "I really didn't have time to work on video/documentation today ... I will do my best to provide it on Monday." Neither confirmed delivered.
- **R0804** · 06-29 · 51 days · **open, self-acknowledged**. "I still owe you, like, the details and video and explanation of how it's supposed to work" (existing Smartlead/Pipedrive integration and nurturing setup). No delivery visible in ingested material.
- **R0373** · 07-24 · 26 days · **open**. "For handling tasks in Pipedrive, I will cover that process in the Pipedrive Guidelines document (another one to write next week)." *Consequential because* this is exactly the document that would answer R0313 and R0326 (§F).
- **R0446** · 08-14 · 5 days · **open**. "Maybe I'll take a look and let you know" (verify the reply-labelling migration improved accuracy). Also listed in §A.1 as a question Nik is owed.
- **R0126** · 07-29 · 21 days · **open (joint with Nik)**. "Please make sure that Stefan is also aware of all changes / Because he also has some processes in his place that you and I are maybe not aware of." Still an active ask on 08-05 (R0484) and 08-11 (R0478).
- **R0791** · 06-29 · 51 days · **open**. "I need to tell Stefan to add to do not contact list new contacts because I didn't have time ... We will probably need to rerun this do not contact list checkup before we add people to the campaign." The ledger notes this is the **third recorded occurrence of the same DNC-update lapse inside five days** — R0026 (06-25) and R0034 (06-29, same day: "we need to update DNC / FUCK / i forgot again"). Both R0026 and R0034 are **[CONTESTED]**: applied readings link them forward to the systemic fix (R0416/R0418, 08-14) and to the still-outstanding post-event update on 08-11 (R0464); the earlier readings recorded them simply as a recurrence of each other. *Consequential because* it is the one failure mode in the corpus with an external-contact consequence.
- **R0797** · 06-29 · 51 days · **open**. "I need to check with Stefan because I think he has some inboxes that he's using for, for events and some that he's using for other campaigns." Stated twice in the meeting. The ledger records the adjacency without merging it: in DM the same day (R0042) Melisa told Nik the inbox-purpose question "is something you should have checked with Stefan before," while in the meeting she describes it as her own open item.
- **R0781** · 06-29 · 51 days · **stated as not delivered (joint with Sergey's ask)**. Sergey asked her to review the unusually high share of "verdict yes" rows; Melisa in-meeting: "I didn't have time. I really didn't have time. I'm also behind with the LinkedIn stuff." The list proceeded toward launch without the manual review; her only substitute was "from this it looks okay."
- **R0110** · 07-20 · 30 days · **open**. "I will also send you my credentials for DICloak and new proxies so that you can connect them + to heyreach + connect accounts of sales guys." No confirmation of delivery.
- **R0017** · 06-02 · **78 days** · **open**. "Regarding Sales Nav - Toby is an admin so I need to tell him to send you invite." Oldest unconfirmed commitment in the corpus.
- **R0035** · 06-29 · 51 days · **open**. "Stefan will be able to add them in about 4 hours." No confirmation.
- **R0397** · 08-07 · 12 days · **open**. "I'll update you once we have a plan." No update through 08-18.
- **R0244** · 06-23 · 57 days · **open**. "I will schedule some time for us and you let me know tomorrow if you will still be away." **R0263** · 07-07 · 43 days · **open**. "I will schedule a sync for us for tomorrow but please review our campaign ... as current situation is really bad." Neither scheduled sync is confirmed in ingested material.
- **R0563** · 07-27 · 23 days · **unclear / not verified**. "I can just tell Slava to update it because he still needs to update like other things" — on 08-06 Melisa reports 372 Ai4 leads still missing Event name and Marketing Hypothesis (R0389), consistent with this manual catch-up not having covered that population.
- **R0631 / R0632** · 07-14 · 36 days · **open as of the meeting**. "Okay, good stuff. I will prepare then messaging." / "We received access to network app today for AI4 so I need to push on that with Stefan." Ai4 campaigns did run in August, which is consistent with delivery of R0631 but is not direct confirmation.
- **R0747** · 07-03 · 47 days · **open**. "So I need to tell this to sales team" (the Pipedrive source change). No confirmation in the file.
- **R0835** · 06-25 · 55 days · **open, explicitly deprioritised**. Handover of the conference/event enrichment Clay table — "this is also going to be one of your tasks that I will hand it over but this is not like, this is not very urgent." The table is described as partially broken on the scraping side.
- **R0305** · 06-03 · 77 days · **open then superseded**. "Thanks, but I will send it to Andriy today as I also need to add a few things" (see R0304, R0321).

### B.3 — Sergey Cujba's commitments

- **R0918** · 06-16 · **64 days** · **dropped, then materialised as an incident**. "this will need to be clarified with Melisa, but as far as I remember ... but a shame, Melisa will only be back day after tomorrow. I don't know whether she will answer this question" (orig. Ukrainian) — the person-level-vs-company-level DNC question. Nothing in ingested material shows the question being put to Melisa in June. Melisa raises the same problem herself on 07-29 (R0529); it is scoped on 08-11 (R0456/R0461); and **a company-level application wipes ~2,000 Pipedrive leads' labels on 08-14 (R0496)**. Effectively dropped for ~6 weeks. *Consequential because* it is the clearest case in the corpus of a deferred definitional question later producing a measurable data incident.
- **R0615** · 07-14 · 36 days · **open, with its own unused escalation path**. "There is a deck that I will share with you. If not today, tomorrow. Melissa, if I'm not doing this for nearest couple of days, please get back to me in the GTM engineering channel and I will share that presentation." No ICP deck appears anywhere in ingested material, and the escalation instruction is not recorded as having been used.
- **R0359** · 07-16 · 34 days · **open**. "I'll get back with an update on how we should approach making sure that all the things than must be taken care of are actually taken care of." No update through end of July. A month later **R0401** (08-11, same channel, same speaker) proposes formalizing the BDR sync — subject matter matches closely but the text never ties the two together, so this is a **plausible, not confirmed** follow-through, and that proposal itself landed only accepted-in-part.
- **R0451** · 08-12 · 7 days · **open, dated**. "we are about to finalize the voting for triggered campaigns most likely until the end of this month, like ideally until the end of the next week ... ideally we should start running them and testing them during September ... Triggered campaigns, three, four of them ideally." *Consequential because* the stated deadline (~2026-08-22) falls days after this audit's cutoff and gates September campaign build.
- **R0442** · 08-14 · 5 days · **open**. "let's have this question raised every one or two months so we know and reassess our position about what would be the state of things when we need to seriously consider parting ways with Stefan ... it's not about let's part ways with Stefan today." No scheduled mechanism, owner or artifact named beyond Sergey saying he will raise it.
- **R0440** · 08-14 · 5 days · **open, reciprocal (Melisa + Sergey + Chrissy)**. Melisa: "it would be good to know like if you can give us a heads up when you hear from Chrissy about the new ICP system"; Sergey: "Please mention this in the chat between you, me and Chrissy saying that we have a dependency." No confirmation either side happened.
- **R0674 / R0675** · 07-10 · 40 days · **open pair**. Sergey to hand Nik Slava's events spreadsheet ("There is a spreadsheet from Slava that he has shared with me"); Nik to review it and report back ("Give me the list and I'm gonna review"). Melisa confirms the set is not in Clay yet. Neither half confirmed. Nik's half is blocked on Sergey's.
- **R0807** · 06-29 · 51 days · **open (three items routed to Slava/Mario)**. "I'll ask Slava just right away now ... I can assign this to Slava as well ... let's think about August in the United States as well and maybe suggest this to Mario. I will ask Slava about this as well." No confirmation of any of the three.
- **R0658** · 07-10 · 40 days · **open**. The Berlin stealth-startup contact — "she's going to share it with me so we can make an estimation for them and they're going to potentially consider us as the third agency." No further mention of the contact, the requirements doc or the estimate anywhere in ingested material.
- **R0749** · 07-03 · 47 days · **open**. "we are going to get back to them with the estimation on how much time would it take, how much money is going to cost" — owner Sergey ("I will try to do my best"), no date.
- **R0803** · 06-29 · 51 days · **open, deferred by the proposer**. The valid-email-share benchmark against previous conference/sales-sprint tables, to be run by Nik — "it's not for now ... something that we can take a look after afterwards." No evidence the benchmark was produced.
- **R0871** · 2026-06 (date confidence: WEAK, month-only, anchor UNMATCHED) · **open**. "we will need to get back to the discussion about the conferences and support when Toby and Mario and Jim can join ... either next week on sales and marketing meeting or ... I will try to find some 30 minutes." Assented to by Rune ("Okay, great") and Chrissy ("Sounds good"); no record of such a session anywhere. Conference-support scoping is still being argued in August (R0396, R0205), consistent with the deferral never closing.
- **R0621** · 07-14 · 36 days · **unconfirmed**. "It's in my list with Mike ... I will just put this in our slap [Slack] chat. So it's incorporated as well." No separate Sergey message carrying Mike's campaign idea appears in ingested Slack.
- **Delivered, for balance:** R0739 (HeyReach subscription and credentials, same day, corroborated by R0257), R0694 (the Tuesday 07-14 trigger-campaign sync did happen), R0624 (voting round happened, closed 07-30 with 12 hypotheses — later than the "next week Friday" stated), R0952 (**delivered in substance, later than implied** — the next-projects conversation happened on 07-10/07-14, not in June).

### B.4 — Others' commitments

- **Lilla Szabo — R0645** · 07-10 · 40 days · **open, and gating**. "I'll prepare a scope, like a scope doc, get it signed off by Chrissy ... I'll get the scope doc to you as soon as possible." No ICP scope document appears anywhere in ingested material, **and the whole Pipedrive ICP automation is gated on it** — including Nik's own R0646. Deliberately conditioned on Chrissy's sign-off, so the delay is not attributable to Lilla alone.
- **Person-a2ef1b69 — R0840 / R0841** · 06-25 · 55 days · **open**. "I will share it with you, these documents ... I'm sending over to you all the information and the documents that I prepared" / "I will have a call later with Sergey, so I will mention that it's possible to create it." Neither confirmed; Karol, Miro and this initiative are absent from the entire Slack corpus. Nik's dependent commitment is R0842.
- **Melisa Bahonjić — R0859** · 06-19 · 61 days · **open**. "I will check the table and let you know what I think ... I will send you like, some invite for Monday." Blocked in part by an unresolved Clay login (R0854); no record of the feedback or the Monday session. (Melisa **Bahonjić** is a different person from Melisa **Draksler** — see R0957, **OUT-OF-CORPUS**.)
- **Joint (Nik + Melisa + Sergey) — R0491** · 08-05 · 14 days · **partially delivered**. HeyReach onboarding was scheduled and a walkthrough is on record 08-14; the automated daily/weekly reporting digest Nik offered was conditional on Melisa specifying her reporting expectations, and no specification appears. **R0495** · 08-05 · **partially delivered / superseded in timing**.

---

## C. PROPOSALS THAT GOT NO RESPONSE

15 PROPOSAL records carry an ignored / no-response status. Operationally, silence here means **the status quo persisted by default** — no one rejected these, and no one owns them.

**Most consequential in this section: R0415** — see C.4.

### C.1 — Nik's proposals that got no response

- **R0036** · 2026-06-29 · dm-melisa · 51 days. "Let's do it in the way i propose - whenever we discuss any matter that 100% has to be done you say or Sergey i put it and we are good."
  Status: "ignored as a mechanism, but answered in substance on 2026-07-10 by Sergey's stated align-before-you-change + ClickUp ownership protocol (B6); **still never written down**."
  *Operational meaning:* the "what counts as a committed item" mechanism was never agreed, which is the same gap as R0180/R0193 (§E). Nik's proposal and Sergey's later different mechanism both exist; neither is documented.
- **R0585** · 2026-07-21 · `08_UNKNOWN_mykyta-melisa-sergey-sync.txt` · 29 days. "if it's possible to make activities. I mean put messages from LinkedIn in activities ... Pipedrive allows to log messages. I am logging them right now via API ... Basically it's going to be in backlog."
  Status: ignored/parked — the counter-claim to R0584 is neither tested nor rejected; Nik parked it in his own backlog and it does not reappear.
  *Operational meaning:* the capability that would have addressed Melisa's 08-17 complaint (R0228: "in Pipedrive we can see only messages that he sent, and not Mario's messages") was raised 27 days earlier, parked, and never revisited. It resurfaces as commitment R0512 on 08-14.
- **R0074** · 2026-07-16 · dm-melisa · 34 days. "i recommend you also to increase number of steps for events / it works 100%." Status: ignored, no response found in ingested material.
- **R0264** · 2026-07-07 · #gtm-engineering · 43 days. "I think more boxes, also we can try another messaging" — offered into the low-reply-rate thread (R0261/R0262). Status: ignored. *Operational meaning:* the reply-rate problem stayed open; capacity and messaging were both later re-litigated.
- **R0733** · 2026-07-03 · `14_UNKNOWN_team-sync.txt` · 47 days. Multi-mailbox / "our team gonna be there" tactic — **rejected for London** by Melisa ("This is also something to think about. But yeah I wouldn't for now. I wouldn't risk it"), then **re-raised by Nik for Ai4 in the same meeting** ("You should use every email we have and afterwards just say that those people, those two gonna be attending ... I think nobody gonna care about it") and **ignored on the second airing**. Both airings recorded; recorded here because the second one received no ruling either way.
- For completeness, one of Nik's proposals initially logged as unanswered is now **accepted**: **R0818** (06-25, HeyReach over GetSales) — "accepted as the direction," with the explicit adoption traced to the 07-03 1:1 (R0774) and the subscription registered the same day (R0739, R0257). Nik gave no answer to Melisa's blocking objections beyond a comparative one.

### C.2 — Melisa Draksler's proposals that got no response

- **R0438** · 2026-08-14 · `01_UNKNOWN_dnc-and-migration-sync.txt` · 5 days. "Maybe we can use AI4 to compare for Makita to build like a new enrichment event table and then put those exact same contacts from AI4 and see what kind of results we would get ... we know that 20% of people are going to be with score 6 or higher."
  Status: ignored — no response from Sergey or Nik; the conversation moved to the Chrissy ICP dependency. *Operational meaning:* the only concrete A/B design for validating the new enrichment against a known cohort has no owner.
- **R0693** · 2026-07-10 · `12_UNKNOWN_trigger-campaigns-sprint-planning.txt` · 40 days. Local/networking campaigns per salesperson city, and the underlying question of whether salespeople should be geographically restricted at all ("Even though Toby mentioned that we are not restricting salespeople on locations. Maybe we should").
  Status: ignored — "Sergey's next turn is 'Got it. Okay, I'm having another call right now with Andriy' and he closes the meeting"; not written into the ClickUp list.
- **R0601** · 2026-07-14 · `10_UNKNOWN_team-sync-integration-incident.txt` · 36 days. The pharma/AI-drug-discovery partnership signal was **accepted in principle** (Sergey: "Yeah, very good idea"); the embedded sub-proposal to buy an Endpoints News subscription ("Of course I don't have subscription but we can purchase it. It's not super expensive") **got no response from anyone** and is not returned to. *Operational meaning:* the signal source for one accepted trigger hypothesis was never procured.

### C.3 — Sergey Cujba's proposals that got no response

- **R0640** · 2026-07-10 · `11_UNKNOWN_pipedrive-automation-w-lilla-szabo.txt` · 40 days. The 2.5-year historical ICP backfill: "take a look at all the leads that we have generated over last two and a half years and gather all of that information for them and compare them with the icp."
  Status: no response and no owner — "Lilla immediately scoped the ask the other way ... and Nik estimated only the forward-looking case. The 2.5-year historical backfill is therefore proposed by the director and silently dropped in the same meeting." *Consequential because* it was dropped in the room, by re-scoping rather than by decision.
- **R0250** · 2026-06-29 · #gtm-engineering · 51 days. Success-story database + an agent that reacts to new files, scans leads with conversation context and drafts nurture messages. Status: ignored — reactions only, no reply or follow-up.
- **R0241** · 2026-06-03 · #gtm-engineering · **77 days**. Forwarded from Toby Rawlinson — the BigSet tool for the incomplete-data problem ("Likely would solve the problem"). Status: ignored, no reply or follow-up. *Note:* this is a proposal that originated with a sales exec and reached the engineering channel; the corpus records no evaluation.
- **R0271** · 2026-07-14 · #gtm-engineering · 36 days. "An idea from Mike / Low priority campaign idea - target engineering companies that are looking to leverage AI to improve their engineering productivity." Status: ignored — submitted as explicitly low priority. Related: **R0621** (Sergey's own commitment to post Mike's idea) is unconfirmed.

### C.4 — Others' proposals that got no response

- **R0415** · **2026-08-18 14:23 IDT** · #lead-generation-team · Lule Salihu · **open 1 day at cutoff — and it is the last message in the entire ingested Slack corpus.**
  > "after discussing with the team and with all the new events starting/coming in September we thought it would be best to change the plan considering the connected leads (both High and Medium) have all received personalized messages so maybe we can send a more templated follow up ... sorry for confusions but we had to prioritize tasks."
  Status: ignored (no response) as of end of ingested material. The ledger links it to **R0386** (2026-07-31, Lule: "leads that are in lead nurturing pipeline with no replies ... what do we do with them?"), where Sergey proposed exactly this templated-follow-up approach but deferred the firm decision: "it's a great question, let's discuss this on our next sync."
  **Operational meaning, stated plainly:** the BDR team announced a change to nurture messaging policy for connected High and Medium leads, tied to September events, and received no ruling from Nik, Melisa or Sergey before the corpus ends. In the absence of a response the team's stated plan is what will run. The related mechanism question (**R0404**, automation vs manual) is also unanswered. This is the most consequential silence in the corpus because it is recent, it is about outbound copy going to real prospects, and the corpus shows the same question deferred once already.
- **R0320** · 2026-06-16 · #lead-generation-team · Araks Grigoryan · 64 days. "This post came up to my feed about having a QR on the back of a t-shirt during expo, maybe it can be a good idea?" Status: ignored — an "eyes" reaction only. Low operational consequence; included because the pattern of BDR suggestions receiving reactions but no replies recurs (see also R0415, R0313, R0326, R0414).

### C.5 — Adjacent: proposals parked by their own proposer

Not "ignored" but functionally in the same place — recorded here so they are not lost: **R0292** (07-31, Sergey: "This waits until our next sync", no decision through 08-18), **R0708** (07-08, Nik's AI-generated messages — "deferred / conditionally rejected"), **R0766** (07-03, Nik's Zapier/Make removal demo — "that's for the future"), **R0780** and **R0788** (06-29, seniority/lead-engineer scoring refinements — deferred with no owner and no date; graduate/internship postings therefore still count toward the hiring score), **R0477** (08-11, Melisa's proposed Nik/Stefan split call — open/deferred, and the split was still being deferred the next day), **R0865** (06, the 2–3-month BDR-support calendar — supported by Lule, deferred by Sergey to the session in R0871 that never happened), **R0531** (Nik's review-status design — deferred by mutual consent).

---

## D. NEVER-ANSWERED DEFINITIONAL QUESTIONS (RULEBOOK-BLOCKING)

These are prominent because the Process Rulebook cannot be filled without them, and because the corpus shows no one holds the answer.

### D.1 — MQL vs SQL: the data model was asked for once and never answered

**R0650** · 2026-07-10 · `11_UNKNOWN_pipedrive-automation-w-lilla-szabo.txt` · **40 days** · Lilla Szabo, addressed explicitly to Sergey and Nik together.

> "we should also at some point add the distinction between marketing qualified leads and sales qualified leads into pipedrive. And it's a question for both of you guys, like, from your prior experience, what do you see as like the best way to add that? Which, which level? Or should we try to add this like, as an attribute or more like as a, like a separate category?"

Ledger status, verbatim: "OPEN - the question actually asked (which entity level, and attribute vs separate category) was never answered by anyone. Nik answered a different question, the automation mechanism (R0651); **Sergey, though addressed directly ('a question for both of you guys'), did not respond at all**; Lilla then routed it away ('that's ultimately I think for you guys and Chrissy to talk about'). MQL/SQL does not appear anywhere in the ingested Slack corpus (R0001-R0415)."

Independent verification for this deliverable: a full-ledger scan for `MQL` / "marketing qualified" / "sales qualified" returns **five records only** — R0014 (06-02, the company+job-title score components, dm-melisa), R0143 (08-04, reply classification, dm-melisa), and R0650/R0651/R0652, all three from this single 07-10 meeting. **The terms appear in no Slack record at all.** Related: **R0651** was "accepted in principle by Lilla ... and then deferred to Chrissy without an owner or a next step," and **R0652** records Nik's mechanism answer ("we can just insert one more node which gonna ... populate this field. Okay. Sales qualified lead").

*Why this blocks the rulebook:* P2 (entity lifecycle), P10 (field dictionary) and P9 (reports) all depend on whether MQL/SQL is a field on an existing entity or a separate category. No decision exists to record, from anyone.

### D.2 — The reply categories forwarded to sales: three or four? **[CONTESTED]**

**R0119** · 2026-07-23 · dm-melisa · 27 days.
> Nik: "is this the exact set of categories that get forwarded to sales: Interested, Meeting Request, Not Interested, Information Request?" / Melisa: "yes"

- **Applied reading (contested):** "Melisa names three forwarded categories in the 2026-07-21 sync (**R0579**: interested, not interested, information request) and says 'only three' again on 07-27 (**R0539**); this 07-23 Slack answer lists four, including Meeting Request. **Count unresolved.**"
- **Earlier reading preserved:** "stated" (i.e. the four-category set taken as confirmed).

*Why this blocks the rulebook:* it is a P1/P4 primitive — whether "Meeting Request" is a forwarded category determines whether a whole class of replies reaches a salesperson. The corpus contains a documented "yes" to four and two statements of three, ten days apart, from the same person. **Not resolved here.**

### D.3 — "Ownership": the boundaries were never enumerated

**R0473** (§A.4) asked for the borders of responsibility and was deferred to 2026-08-14. What the 08-14 meeting produced was **R0432** — a mutual statement that the transfer is working in practice ("I just need to report what's wrong and he takes care of it" / "Sounds great to me") — not the definition. Four days later **R0238** re-opens it as a reliability demand. Sergey also states he cannot recall which area Nik had previously said was outside his responsibility, so **the disputed boundary is nowhere on record**. P8 (human roles) cannot be filled from the corpus.

### D.4 — Send capacity: two numbers, never reconciled

**R0040** (~400 emails/day using Toby's mailboxes) vs **R0251** (600/day for the whole infrastructure), with **R0453** (§A.4) asking for per-hypothesis volumes and receiving a deferral. The ledger flags the pair as unreconciled. P11 (invariants) is affected.

---

## E. ITEMS DEFERRED TO A MEETING THAT THEN DIDN'T COVER THEM

This is the mechanism finding: in this corpus, **items rarely die by rejection — they die by deferral to a session that either doesn't happen, or happens and covers something else.** The instances below are all in the ledger; nothing is inferred beyond what each status states.

### E.1 — The reporting-protocol chain: deferred four times over 54 days

| step | date | record | what happened |
|---|---|---|---|
| 1 | 2026-06-26 | **R0180** **[CONTESTED]** | Sergey asks how Nik communicates what he is working on and when things are done — "no need to answer this right now, but we will need to align on this when you are back" |
| 2 | 2026-06-29 | **R0036** (ignored) | Nik proposes a mechanism ("whenever we discuss any matter that 100% has to be done you say or Sergey i put it and we are good"). No acceptance. Companion commitment **R0038** ("i will put down things in slack channel i created for myself") is unverifiable from the corpus |
| 3 | 2026-07-03 | **R0750** | Sergey states the norm in a meeting ("transparent and as precise as possible with the estimations ... letting everyone know beforehand"); Nik assents ("Yeah, guys, definitely"). Never written down |
| 4 | 2026-07-10 | **R0668** | Sergey states the mechanism in substance (ClickUp task with start/due dates, decomposition, align-before-implement, weekly/bi-weekly status presentation). Never written down |
| 5 | 2026-07-17 | **R0190 / R0191** | Sergey re-raises the identical toolset-coordination concern ("it's unacceptable for one person to turn something on/off or change it without aligning with others"); Nik proposes an approval-then-act rule; Sergey agrees in principle but **defers finalising to a Monday sync** |
| 6 | 2026-07-20 → 07-27 | **R0192** | The Monday sync is postponed once, then **skipped outright**: "ugh I don't even remember what it was for ... maybe let's skip it then, since we've already discussed everything [over text]". No protocol recorded |
| 7 | 2026-07-27 | **R0193** **[CONTESTED]** | Nik asks for a final decision (ClickUp / sync / backlog); Sergey: "yes, we can discuss this too in one of the upcoming syncs" — **third deferral** |
| 8 | 2026-07-21 (predating step 7) | **R0595** | Sergey had already given a dated instruction on the ClickUp half — "please put them in ClickUp so we are aligned on what should we expect when" — which remains an **open commitment** with no confirmed ClickUp timeline |
| 9 | 2026-08-05 | **R0483** | The absence/coverage half is settled and mutually accepted (this is why R0180/R0193 are contested) |
| 10 | 2026-08-14 | **R0432 / R0437** | The ownership meeting settles ownership *in practice* but records **no reporting protocol**; Sergey re-raises toolset alignment as a future item |

**R0192 deserves separate emphasis:** it is the clearest single instance in the corpus of the failure mode — a sync created specifically to close a protocol gap was skipped because neither party could remember what it was for, and the gap it was meant to close is still open at the cutoff.

### E.2 — Ownership definition: deferred to 08-14, and 08-14 covered something else

**R0473** (08-11, deferred) → **R0479** (08-11, AGREEMENT, *delivered* — the Friday meeting was booked and all three assented) → **R0432** (08-14, ownership closed in principle) → **R0238** (08-18, re-opened as a reliability demand with a request for a plan and timeline). The meeting happened; the deferred item did not get its answer. Also deferred into that same meeting and **settled** there: the Nik/Stefan task split (**R0477** 08-11 → **R0455** 08-12 → R0434/R0436 on 08-14) — so the mechanism is not uniformly lossy; the difference is that the split was on the agenda by name.

### E.3 — Nurture policy: deferred to "next sync", then acted on unilaterally

**R0386** (07-31, Lule asks what to do with non-replying nurture leads; Sergey proposes a mass templated follow-up but defers: "let's discuss this on our next sync") → **R0404** (08-12, Lule asks the mechanism question, redirected, unanswered) → **R0415** (08-18, the team announces its own plan; no response). Three weeks, one deferral, no captured decision, and a policy now set by default.

### E.4 — Events and BDR capacity: deferred to a session that is absent from the corpus

**R0019** (06-02, CONCERN, open — "the problem around event packages is how many events we can support at the same time") → **R0864/R0865** (06, capacity "we do not know yet"; Lule supports a 2–3-month BDR-support calendar) → **R0871** (Sergey defers to a session with Toby, Mario and Jim; assented to by Rune and Chrissy) → **no such session appears in the transcript index or in Slack**, and conference-support scoping is still being argued in August (R0396, R0205).

### E.5 — Other deferrals with no closure in the corpus

- **R0458 / R0461** (08-11): salespeople running their own campaigns (Jim adding ~200 people/week with no visibility) — explicitly deferred to a DNC "phase 2", with the sales team told in the interim that marking disqualified contacts is their own responsibility. **R0619** (07-14) had already stated that DNC must eventually cover five salespeople's self-run campaigns.
- **R0688** (07-10): the US sales sprint — "two answers offered and neither adopted."
- **R0860** (06): which conferences the new sales executive attends — partially answered, "everyone is listing their conferences of interest in ClickUp" with no decision mechanism.
- **R0922** (06-16): whether Stefan's enrichment tooling can be centrally accessed — Sergey explicitly defers ("I'll just dump information on you now ... and then we'll decide").
- **R0194** (07-24): n8n self-hosting — cloud upgraded for now, migration deferred to an unspecified date. (Compare **R0468**, the company-owned-n8n requirement from 08-11.)
- **R0803** (06-29), **R0780/R0788** (06-29), **R0292** (07-31), **R0766** (07-03) — deferred by their own proposers, no owner, no date (see §C.5).

---

## F. STILL-OPEN BDR QUESTIONS

Confirmed unanswered across the whole corpus, and consequential because they concern work the BDRs do every day:

- **R0313** · 2026-06-08 · #lead-generation-team · Lule Salihu · **open 72 days** (the oldest open question in the corpus).
  > "what should we do if there's a task outdated on a lead that is closed as a deal is created. In this case, do we check the history on the deal record or how is the process we should follow in these cases"
- **R0326** · 2026-06-23 · #lead-generation-team · Araks Grigoryan · **open 57 days**.
  > "do we need to bring back those outdated tasks that were created? Cause we closed them before adding to nurturing"

Both statuses note the same caveat: the August outdated-tasks review (R0398–R0401) addressed the topic **operationally** — a review spreadsheet and a proposal to formalize the BDR sync — but **neither the deal-closed sub-case nor the retrospective reopen question is addressed anywhere in ingested material**. The document that would answer them is Melisa's promised Pipedrive Guidelines (**R0373**, open 26 days).

Also open and owed to the same two people: **R0414** (2 days, ClickUp assignee / BDR-owner field change), **R0404** (7 days, automation vs manual), **R0350** (41 days — evidence gap: the thread had three uncaptured replies), and the three walkthrough questions rolled into **R0515** (R0509, R0514, and the R0512 question — 5 days).

---

## G. [CONTESTED] REGISTER — all 14 records, for owner resolution

Wherever these appear above, both readings are shown. Newest evidence is the applied status; full history is in each record's `update_history`.

| id | type | date | the contest, in one line |
|---|---|---|---|
| R0009 | PROCESS FACT | 06-02 | BDR roster / Melisa handling high-value follow-ups — status unchanged ("stated") in both batches |
| R0014 | PROCESS FACT | 06-02 | Company + job-title qualification components — status unchanged ("stated — corrects R0013's premise") |
| R0026 | ISSUE | 06-25 | DNC post-event update: "recurred (see R0034)" vs "recurred — still outstanding on 2026-08-11 (R0464)" |
| R0033 | CONCERN | 06-29 | Whether a launch deadline was ever communicated: contradicts R0032; two meetings inside the disputed window (06-25 file 18, 06-29 file 16) record **no** deadline being stated. Unresolved either way |
| R0034 | ISSUE | 06-29 | Same DNC lapse: "recurred (same failure mode as R0026)" vs "recurred; systemic fix stated as landing 08-14 (R0416/R0418)" |
| R0115 | COMMITMENT | 07-21 | DNC scope gathering: "substantially delivered by batch C" vs "delivered — the 07-29 scoping session is now on record" |
| R0119 | DEFINITION | 07-23 | Forwarded reply categories: **four** (this record) vs **three** (R0579 07-21, R0539 07-27). See §D.2 |
| R0120 | PROPOSAL | 07-23 | DNC leads to Pipedrive with a label, no Slack notification: "accepted (verbally), no confirmation of implementation" vs "accepted then **partially reversed** — the Pipedrive 'do not contact' label half ruled out 08-14 (R0498/R0500), suppression itself retained" |
| R0121 | ISSUE | 07-27 | Reply-detection gap worked around by manual re-run — status unchanged ("open") |
| R0180 | QUESTION | 06-26 | Reporting protocol: "OPEN, deferred" vs "partially-answered-by-R0483, mechanism half still OPEN". See §A.2, §E.1 |
| R0193 | QUESTION | 07-27 | ClickUp / sync / backlog decision: "OPEN, third deferral" vs "OPEN, ownership settled 08-14 but no protocol" vs (history) "ClickUp half answered by R0595 on 07-21". See §A.1 |
| R0273 | QUESTION | 07-23 | Sergey's three-part status ask: "answered" vs "answered-in-part, ownership boundary still OPEN (R0473)" vs (history) "not the earliest instance — 07-21 sync answered it first" |
| R0276 | COMMITMENT | 07-23 | Nik replacing Melisa's manual actions: "overdue/unclear" vs "delivered — confirmed by R0432" |
| R0286 | PROPOSAL | 07-23 | Ownership acceptance: "accepted-in-practice, no explicit verbal yes" vs "accepted — explicitly closed at the 08-14 meeting (R0432)" |

---

## H. EVIDENCE LIMITS — what this document cannot tell you

Per the brief, conclusions here are **provisional as of the ledger's coverage** (`coverage_map`, and deliverable 06):

1. **Ingested:** dm-melisa (05-28 → 08-18), dm-sergey (05-28 → 08-18), #infra-issues (08-06 → 08-18 only), #gtm-engineering (06-02 → 08-18), #lead-generation-team (06-01 → 08-18), and 21 of 22 meeting transcript splits (2026-06-16 → 2026-08-14).
2. **Not ingested, therefore invisible here:** ClickUp tasks and comments, Pipedrive notes/activities, email, WhatsApp (explicitly referenced as a live channel in R0203), any Slack channel other than the five above (including the private channel in R0038), untranscribed or unrecorded calls, and anything after 2026-08-18. A commitment shown as "open" may have been delivered in any of those places.
3. **#infra-issues coverage starts 2026-08-06** — earlier infrastructure escalations, if any, are not in scope.
4. **Known degraded records:** transcript file 09 yielded zero records (non-English audio mis-transcribed); file 20 is downgraded to **month-only** date confidence with an UNMATCHED calendar anchor (affects R0860, R0864, R0865, R0871); file 22 was discarded as a garbled duplicate of file 21 (**R0958**, OUT-OF-CORPUS); several `02_UNKNOWN_heyreach-pipedrive-walkthrough.txt` speakers are unidentified (affects who is owed the answers in R0509 and R0514).
5. **R0956–R0958 are OUT-OF-CORPUS** owner corrections dated 2026-08-19, supplied in terminal. They are cited above only as identity/provenance rulings (notably R0957: Melisa **Bahonjić** is a separate real person from Melisa **Draksler**), never as evidence that something was said in Slack or in a meeting.
6. **The date arithmetic assumes the cutoff is the whole story.** Where a stated deadline falls after 2026-08-18 (R0451, ~08-22 for trigger-hypothesis voting), this document reports the commitment, not its outcome.
