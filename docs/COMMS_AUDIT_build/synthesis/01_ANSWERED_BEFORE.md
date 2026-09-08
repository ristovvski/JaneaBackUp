# 01 — ANSWERED BEFORE

*Deliverable 1 of the communication audit. Built from `COMMS_AUDIT_build/ledger.json` (937 records: Slack R0001–R0415, meeting transcripts R0416–R0955, owner corrections R0956–R0958). Every line carries quote + date + source + record id.*

---

## 1. How to use this

Before asking a process question in a sync, search this file — if it is in §2, it has an answer on the record and the answer is quotable with a date.
Before saying (or accepting) "this was never communicated" or "I told you this", read §4 — claims in both directions are tested against the corpus there, not adjudicated.
Where a record is marked **[CONTESTED]**, two batches of evidence proposed different statuses; both readings are shown and neither is silently resolved (§5).

---

## 2. Answered questions, by subject area

Legend: **FULL** = a direct, unambiguous answer exists. **PARTIAL** = answered in part; what is still missing is stated. **NOT FOUND** = the corpus does not answer it — a first-class result, listed here so it is not re-searched.

### A. Labels & entity lifecycle (P1/P2)

**A1. What drives a label change?** — asked by Nik, 2026-07-17, `R0081`: *"Melisa does any automation changes labels ?"*
Answer, Melisa Draksler, 2026-07-17, dm-melisa, `R0082`: *"btw label is changed based on lh_campaign_stage for linkedin ... but i dont know for email"*. Fuller and earlier, on the record in the 2026-07-03 recorded 1:1 (`15_UNKNOWN_melisa-mykyta-1on1-workflow-review.txt`), `R0756`: *"based on this LH campaign stage in pipedrive it automatically when we have that stage invited it should assign label one quote ... because our entire reporting is based on those labels"*, and `R0759`: acceptance sets stage `accepted`, which *"label two is g[oing to be added]"*.
**PARTIAL** — the LinkedIn label chain (stage → label) is documented. The **email-side label mechanism is explicitly unknown to Melisa** and is not stated anywhere else in ingested material.

**A2. Which fields/labels must a lead carry to be usable and reportable?** — the question Nik would ask before any bulk write.
Answer, Melisa Draksler, 2026-07-27, `07_UNKNOWN_mykyta-melisa-1on1.txt`, `R0544`: *"we need to have organization. We need to have source, medium, marketing hypothesis, usually current position ... most important thing is label"*. Reportability gate, same meeting, `R0543`: *"we use labels for reporting purposes. And I saw that we have bunch of leads without label 1 ... those leads are not visible in our reports."* Event-name discipline, 2026-07-02, lead-generation-team, `R0340`: *"the Event Name field must always be filled in ... It cannot happen that one lead is labeled as 'HumanX 2026', another as 'HumanX - 2026' ... otherwise, Lilla's dashboard and reporting will break."*
**FULL** as a working field list. Missing: no single authoritative label dictionary exists anywhere in the corpus — the values are only ever named in passing.

**A3. When is a deal created, and how does the meeting label work?**
Answer, Melisa Draksler, 2026-08-18, dm-melisa, `R0164`: *"Deal is created only when meeting is qualified / Regarding label 5. - did they have meeting at the event or after? / If there is a voicenote in ai4 channel about meeting, then it's Slava's mistake / If there is no voicenote, meeting probably happened after event so sales person forgot to update"*.
**FULL — but only as of 2026-08-18.** No earlier statement of the meeting-label rule is found in ingested material. See §4/4 — this is the exact content of the disputed *"I told you when we add meeting label and how"* (`R0165`, same day). The nearest earlier record is 2026-06-22, lead-generation-team, `R0323`: *"when converting leads to deals (qualified meetings/opportunities) Sales people will still need to change BDR owner to me so that we don't break existing reports"* — which is an owner rule, not a label rule.

**A4. Where do next-scan dates live — Excel or Pipedrive?** — asked by Araks Grigoryan, 2026-06-01, `R0302`.
Answer, Melisa, 2026-06-01, `R0303`: *"Yes, you should remove them so that we only have them in Excel"* — **later reversed** by Melisa, 2026-06-22, `R0322`: *"you can start manually adding those next scan dates from the Excel file, and from now on, you will set next scan dates only in Pipedrive."*
**FULL**, with the rule change recorded as a pair. Current rule = Pipedrive only (`R0322`).

**A5. Can a wrong label change be undone?**
Answer, 2026-08-14, `02_UNKNOWN_heyreach-pipedrive-walkthrough.txt`, `R0497`: *"I had a case where Sergey by accident changed labels for like 2000 leads and we couldn't bring it back because there is no change log for labels for pipedrive and also support was not able to bring them back"* (restating the same incident class she raised on 2026-07-27, `R0551`).
**FULL, with an unresolved disagreement on the remedy**: Nik's position in the same conversation is that his own tooling's action log is the recovery path, not Pipedrive's. Both positions recorded; not merged.

### B. DNC (P6)

**B1. Who goes on the DNC list, and why?**
Answer, Melisa to the BDRs, 2026-08-14, lead-generation-team, `R0407`: *"Every lead is being added to DNC so that we don't reach out to them with new cold outreach campaign again but this does not have to do anything with your process."* Agreed two-party version, 2026-07-21, `08_UNKNOWN_mykyta-melisa-sergey-sync.txt`, `R0593` (AGREEMENT): *"whenever we get replies from any any campaigns we add those people to to do not contact list"*.
**FULL** at the principle level.

**B2. What are the DNC source layers?** — asked by Nik in the 2026-07-29 1:1.
Answer, Nik and Melisa, 2026-07-29, `06_UNKNOWN_mykyta-melisa-1on1.txt`, `R0524`: *"so now we have four layers connections. Hey Rich smart lead and the fourth one they are manual outreach. We serve [Surfe] ... Oh competitors also"* — i.e. (1) team LinkedIn connections, (2) HeyReach outreach, (3) Smartlead outreach, (4) manual/Surfe, (5) competitor companies.
**FULL** — this is the record that closes Nik's own 2026-07-21 scoping commitment `R0115` **[CONTESTED]**.

**B3. How many DNC lists are there and on what keys do they match?**
Answer, Melisa, 2026-06-29, `16_UNKNOWN_lead-scoring-sprint-planning.txt`, `R0790`: *"we have like four do not contact lists. We have do not contact list based on company domains, based on emails and based on LinkedIn profile"* — **says four, enumerates three**. Enforcement mechanism, Nik, 2026-08-11, `R0463`: *"I have everybody who is in not contact lists in data table in item [n8n]. So basically we don't reach out to those people"*; scale, 2026-08-14, `R0416`: *"we already added 2003 ... so 2200 people with DNC status ... Honestly I can't answer from where I took them"*.
**PARTIAL** — the count/enumeration mismatch is never reconciled in ingested material, and the provenance of the ~2,200 live entries is stated on the record as unreconstructable.
*Out-of-corpus:* `R0956` (**OUT-OF-CORPUS — owner correction, Nik, terminal, 2026-08-19; not in-corpus evidence**) records the current matching rule as LinkedIn **or** email, with a residual 1,019 persons having neither.

**B4. Are leads without a LinkedIn URL protected by DNC?**
Answer, Melisa, 2026-07-10, `12_UNKNOWN_trigger-campaigns-sprint-planning.txt`, `R0680`: *"we have some leads added by the sales team that don't have any. They only have maybe first name, last name and company name. They don't have LinkedIn URL ... we are actually not putting people on the not contact list if they don't hav[e it]"*. Recurs as the contact→deal path, 2026-08-14, `R0428`: *"Sometimes Tobi [Toby] creates just contact and then turns it to deal without lead option ... a lot of Toby's leads do not have LinkedIn profile or position or anything."*
**FULL — the answer is "no, they are silently never blocked."** The fix is not agreed: `R0429` leaves the design fork (Slack notification vs automatic enrichment on create) undecided and open.

**B5. Do we add a "do not contact" label in Pipedrive?** — proposed by Melisa, 2026-07-23, `R0120` **[CONTESTED]**: *"can we also send leads with DO NOT CONTACT to Pipedrive and add label Do not contact? but not send notification in Slack?"* — accepted verbally by Nik, re-raised and re-accepted 2026-07-27 (`R0542`).
Later narrowed, 2026-08-14, `R0498`: *"this label is supposed to be only added when leads respond to us. Do not contact me unsubscribe ... This is the only part where they should be."*
**PARTIAL / reversed in part** — DNC *suppression* stands; the Pipedrive *label* is now restricted to explicit unsubscribe requests. Nik's broader reading (`R0499`) did not prevail. See §4/13.

**B6. If a DNC-flagged person writes to us first, do we reply?**
Answer, 2026-08-14, dm-melisa, `R0159` (AGREEMENT): *"DNC protects them from our cold outreach, not from conversation ... yes, and we don't need notification about that"*.
**FULL.**

**B7. Does a DNC entry expire?**
Answer, Melisa proposal, 2026-07-21, `R0594`: *"maybe we would remove this person from the not contact list after one year or six months"* — delivered as designed, Nik, 2026-08-04, dm-melisa, `R0144`: *"TTL 6 months on reply-based entries, offboarding removes a leaver's [connections]"*.
**FULL.**

### C. Replies, alerts & notifications (P4/P12)

**C1. Which reply categories get forwarded to sales?** — asked by Nik, 2026-07-23, `R0119` **[CONTESTED]**.
Two answers, from the same person, four days apart: Melisa, 2026-07-21, `R0579`: *"only specifically categories like leads labels labeled with interested, not interested information request, they get sent to Slack and to pipedrive"* (three). Melisa, 2026-07-23, dm-melisa, `R0119`: Nik asks *"is this the exact set of categories that get forwarded to sales: Interested, Meeting Request, Not Interested, Information Request?"* — *"yes"* (four). Melisa again, 2026-07-27, `R0539`: *"only three categories are being forwarded"*.
**PARTIAL — the count is unresolved.** Do not treat either as settled; this is a one-line rulebook question for the next sync.

**C2. What happens to a reply the classifier is unsure about?**
Answer, Melisa, 2026-07-29, dm-melisa, `R0127`: *"it should be forwarded to me"*.
**FULL.**

**C3. Why do some replies never reach the salesperson, and what breaks downstream?**
Answer, Melisa, 2026-07-21, `R0580`: *"10% of cases are wrong. When people write some like a confusing email ... It gets categorized in the wrong way and email does not get forwarded to salesperson"*; blast radius, same meeting, `R0581`: *"if it's not forwarded to Noah, Noah will not respond. BDRs are not going to have notifications, [S]lava will not create ClickUp tasks for them and everything breaks."* Remedy shipped, Nik, 2026-08-04, `R0143`: *"their built-in AI, ~10% miscategorized ... Now: our own classifier with full context; confident replies → forwarded to the owner automatically; uncertain ones → routed to you"*.
**FULL.**

**C4. Do our own outbound replies sync into Pipedrive?**
Answer (email): Nik, 2026-07-31, gtm-engineering, `R0294`: *"if we reply in smartlead after receiving reply from lead it would auto synced into activity (in Pipedrive) ... And even if BDR replies to Lead's Reply"*. Answer (LinkedIn): Melisa, 2026-07-31, `R0384`: *"leads' replies are there, but our replies not"* — re-reported 2026-08-14 (`R0511`) and diagnosed there as missing functionality, with a patch + backfill promised (`R0512`, still open).
**PARTIAL** — email path stated as working; LinkedIn path is a known, still-unclosed gap.

**C5. Does HeyReach still deliver reply events while a campaign is paused?** — asked in the 2026-08-14 onboarding, `R0509`.
Nik's answer, same meeting: *"I think we receive replies ... I'm 90% sure ... It's a good question. If maybe I'm wrong, I will check it out"* — immediately contradicted by reported observation, `R0510`: *"we had a case where Stefan paused those two campaigns and while they were paused, we were not receiving any notifications about incoming replies."*
**NOT FOUND** — no reliable answer exists in ingested material. Rolled into Nik's open follow-up commitment `R0515`.

**C6. What happens when someone replies but never accepts the connection request?**
Answer, Melisa in the 2026-07-03 recorded 1:1, `R0767`: *"linked helper cannot capture reply ... It happens like maybe for three or three or four contacts per campaign. And right now we are dealing with this manually ... I just send this manually to Slava"*. Restated to the channel three days later, 2026-07-06, `R0345`.
**FULL** (including the frequency). See §4/3 — this is one of the claims that **supports** Melisa.

**C7. How is a silently missing notification detected today?**
Answer, Melisa, 2026-07-27, `R0536`: *"usually I open Toby's profile in Linked Helper so I can see entire inbox and I check for replies ... I didn't have any error message or anything."* Plus the report-time control, 2026-08-05, `R0489`: *"I compare number of people that we have in Smartlead, that we have in Linked Helper and I compare it with what we have in Pipedrive in reports before I show those reports. And this is how we spot problems."*
**FULL — and the answer is "manually, by one person."**

**C8. Can bot messages in the lead-processing channel be deleted?** — Nik, 2026-07-20, `R0104`. Answer, Melisa, `R0105`: *"nope / no such option"*. **FULL.**

### D. Meetings & events (P5)

**D1. How does a conference get approved, and who approves?**
Answer, Sergey, 2026-06 (`20_UNKNOWN_ai4-events-planning-team-call.txt`), `R0861`: *"there is a form ... this form is going to transform into a task ... it has a statuses of interested awaiting approval and approved. And Toby is the one who approves these"*.
**PARTIAL** — Sergey flags his own uncertainty on where the form actually lives.

**D2. How much BDR/event capacity do we have?**
Answer, Melisa, 2026-06-02, dm-melisa, `R0010`: *"for BDR support we can only handle one event per BDR but for basic package (just launching campaigns), I'm not sure - probably 2-3 at the same time?"* Independently corroborated by Sergey, 2026-06, `R0864`: *"right now the estimate is that we might only have one BDR support, one sales executive for one conference"*.
**PARTIAL** — both speakers label it an estimate. No firm capacity rule exists in ingested material.

**D3. When can an event campaign start?**
Answer, Sergey, 2026-06, `R0862`: *"we might start a campaign for a conference two weeks before a conference or one week depending on when we're going to get access to a networking application"*. Ai4 specifics, Melisa, 2026-07-03, `R0752`: *"we will need to split like a list of qualified attendees ... across four campaigns. Two email campaigns for them and two LinkedIn campaigns ... we will get access to the networking app two or three weeks before"*.
**FULL.**

**D4. What is the event load after Ai4?**
Answer, Melisa, 2026-08-12, `03_UNKNOWN_event-campaign-outreach-planning.txt`, `R0449`: no event campaigns for two weeks; Finovate Fall outreach from end-August / 1 September (event ~15 Sept, ~2,000 attendees), then Biotech X (~2–3,000) and Money 20/20, then Health USA. Sergey is on vacation 1–14 September.
**FULL** as of 2026-08-12.

**D5. Where can we *not* do event outreach?**
Answer, Sergey, 2026-07-10, `R0669`: *"we have blacklisted the majority of Tier one conferences and some of those conferences have blacklisted everyone else ... they do not provide the list of attendees"*. Concrete live case, Melisa, 2026-08-07, `R0396`: *"QCon was approved with platinum support requested for Jim. But ... we already know there won't be an attendee list, and QCon doesn't allow cold outreach"*.
**FULL** on the rule; the QCon support-tier mismatch itself is still open.

### E. LinkedIn / HeyReach automation (P14/P15)

**E1. Why HeyReach rather than GetSales?**
Answer, 2026-07-03, `15_...workflow-review.txt`, `R0774` (AGREEMENT, both parties): build the HeyReach integration in parallel, keep LinkedHelper through the London sprint, then cut over *"to not have like period without any"* tooling. Nik's rationale in the same call: *"here is for example, is the most integrated tool in the market ... I vote for. Hey"*. Melisa's original objection is restated and explicitly set aside in the same conversation (`R0751`, `R0057`).
**FULL.**

**E2. What is the daily connection-request ceiling?** — asked by Melisa, 2026-07-17, `R0089`: *"btw max limit in heyreach is 40 connection requests per day? / we can't bypass that?"*
Answer, Nik, `R0090`: *"no / i never used more than 40 per day"*; confirmed as a platform cap in the 2026-08-14 onboarding, `R0505`: *"The biggest number of any action you see here is 40"*, presented as *"there is nothing we can do about it"*.
**FULL = 40/day.** Note the inconsistency: in the 2026-08-05 review Melisa states both *40 per day* and *"440 per profile"* (`R0490`); the 440 figure is unsupported elsewhere.

**E3. Can a running campaign be edited?**
Answer, Nik, 2026-07-17, `R0095`: *"When campaign is started the only possible thing we can do is to add more follow ups but nothing can be edited on the go ... its being fixed only if you duplicate campaign"*. Expanded 2026-08-14, `R0508`: *"You can edit delays but you can't remove any part of the campaign ... you just duplicate the campaign. It also checks the previous steps if they were executed for the person"*.
**FULL.**

**E4. How do we take a lead out of a running campaign?**
Answer, 2026-08-14 onboarding, `R0507`: pause the lead inside the campaign — **pause, not remove** — which cancels their un-executed steps. Confirmed by restatement in the room.
**FULL.**

**E5. Do the event/medium/hypothesis fields auto-populate for campaigns that are already running?**
Answer, Nik correcting a belief stated in the room, 2026-07-21, `R0587`: he is *"not [able] yet ... because I can[not] change the running campaign"* — the auto-population applies only to campaigns created after the change.
**FULL (negative).**

**E6. Does HeyReach show whether a lead sits in two campaigns?**
Answer after a live attempt, 2026-08-14, `R0513`: no such view; filtering the inbox by campaign and sender is the only option.
**FULL (negative).**

**E7. Are notifications instant?**
Answer, 2026-08-14, `R0518`: *"any automation that is on cloud right now they are not using stuff instantly so they are having delays always ... they are doing safety so some kind of safety batches"* — accepted by both sides as inherent.
**FULL.**

**E8. Do unaccepted invites get withdrawn automatically?** — asked 2026-08-14, `R0514`. Nik: *"I think there was ... Yeah, it should exist somewhere. But ... doesn't remember"*.
**NOT FOUND** in ingested material; rolled into `R0515` (open).

**E9. Can we hand-write to a subset mid-campaign and still get reply notifications?** — Melisa, 2026-07-03, `R0763`.
Answer, Nik, same call: *"It's manual work but it's possible ... you pause this campaign, you add the people ... You can't modify the campaign, but there is workaround"*, and reply notifications still fire.
**FULL, with a named regression accepted at decision time**: HeyReach has no known equivalent of LinkedHelper's per-contact *"skip this step"* control.

### F. Lead scoring & ICP (P10/P11)

**F1. What is `score` and what is `final score`?**
Answer, Nik, 2026-06-29, `16_...lead-scoring-sprint-planning.txt`, `R0776`: person-level `score` runs 0–110 and is the prioritisation field; `final score` is the company table's hiring-waterfall score. Composition of a maximum, `R0777`: *"110 here means they are hiring for AI ... hiring for software engineering or ... the person is active in LinkedIn and yes, that's the company is in the size 50 or 500"*. Hiring levels, `R0779`: 3 = AI roles, 2 = software-engineering but not AI.
**PARTIAL** — levels 0 and 1 are never described.

**F2. What is the ICP band rubric?**
Answer, Lilla Szabo, 2026-07-10, `11_UNKNOWN_pipedrive-automation-w-lilla-szabo.txt`, `R0641`: a composite additive rubric over six components — industry, stage maturity, company type, geography, revenue range, buying signal. State of the artifact, `R0642`: *"it says version 5 here ... It's still work in progress from Chrissy's ... we can't do it unless we have the finalized info on the scoring and the categories"*.
**PARTIAL and blocked** — the scope doc Lilla committed to (`R0645`) never appears in ingested material, and the whole automation is gated on it. Nik's own ask for sample data (`R0655`) was converted into that same undelivered commitment.

**F3. Are stealth / pre-seed companies in ICP?**
Answer, Sergey, 2026-07-14, `R0613`: they are out as of that date (*"they are not round A, they are not round B. They are precede and precede is like too small"*); Melisa proposed the line at Series B/C.
**PARTIAL** — the authoritative ICP deck Sergey promised the same day (`R0615`) is not delivered anywhere in ingested material, and his verbal effort split (`R0616`) does not add up.

**F4. Where do MQL / SQL live in Pipedrive — which entity level, attribute or separate category?** — asked by Lilla Szabo, 2026-07-10, `R0650`, explicitly *"a question for both of you guys"*.
**NOT FOUND.** Nobody answered the question asked: Nik answered a different one (the automation mechanism, `R0651`), Sergey did not respond, Lilla routed it to Chrissy. MQL/SQL appears nowhere in the Slack corpus.

**F5. Which company value does qualification use when the person has changed employer?** — Melisa, 2026-06-29, `R0786`.
**PARTIAL** — Nik answers only for future runs (*"we can just use Org"*); the already-scored table's provenance is left unresolved. Sergey states the problem is recurring (`R0785`) and Nik's two remedial commitments (`R0787`) are unconfirmed.

### G. Capacity & inboxes

**G1. What is our daily email sending capacity?**
Two figures, one day apart, never reconciled: Nik, 2026-06-29, `R0040`: *"if we use only Toby's emails (which have 20+ emails per day limit) = ~400 emails per day"* — root cause is the 2026-06-29 decision `R0798`: *"we will only use use inboxes that are attached to Toby because Toby is going to be in London"*. Nik, 2026-06-30, gtm-engineering, `R0251`: *"our infra gives us ability to send 600 per day max"*. A third, per-inbox figure appears on 2026-07-08.
**PARTIAL — actively unreconciled.** Melisa's 2026-08-12 volume question (`R0453`) is still open against the same pair.

**G2. Why do inboxes have different limits and warm-up states?** — Nik, 2026-06-29, `R0041`.
Answer, Melisa, `R0042`: *"some inboxes are backup inboxes ... this is something you should have checked with Stefan before ... because some inboxes are for events and some for other campaigns"*.
**PARTIAL** — the technical *why* is never given. Same day, in the Sales Sprint Sync, Melisa describes the identical question as her own open item to *"double check with"* Stefan (`R0797`) — i.e. she did not hold the answer either.

**G3. Who tests deliverability / inbox placement?**
Answer, Sergey, 2026-06-16, `21_...ukrainian.txt`, `R0954`: *"we do check, but Stefan does all of it. So we, you know, blindly trust Stefan. We never looked ourselves at how he does it"* — Nik accepts and de-scopes it (*"if he is doing this, then okay for now"*).
**FULL — and the answer is an un-inspected single-person dependency.**

**G4. Under the cap, do first emails get priority over follow-ups?** — Melisa/Nik, 2026-07-23, `R0116`.
**PARTIAL** — send-order prioritisation was not possible under the fixed limit; the workaround adopted was adding the weekend as a sending day. The related 2026-07-03 decision `R0721` is to send the second message anyway: *"I would try sending a second prioritizing follow up ... because we already know that we don't have many replies from the first message"*.

### H. Roles & ownership (P8)

**H1. Who is the sales owner, who is the BDR owner?** — asked by Nik, 2026-06-02, `R0012`: *"if we handle replies what would be bdr doing"*.
Answer, Melisa, 2026-07-13, dm-melisa, `R0071`: *"Sales owner is a person whose email/LinkedIn account we used to send message to the lead ... BDR owner is assigned only when we get reply and it depends which bDR will support which event or person"*. Ownership-move rule, 2026-07-27, `R0555`: *"I'm not the owner. Like when we get reply, I'm no longer owner. I'm just owner for the ones who are still called [cold]"*. Correction procedure, 2026-08-17, `R0413`: *"go to the lead level and see who the real owner is and update it at the person level."*
**FULL** — answered 41 days after the question was asked.

**H2. Who built the lead-nurturing system / the n8n instance?**
Answer, Sergey, 2026-06-16, `R0946`: *"we have an agency. The guy's name is Andriy ... lives in Poland ... He built us that system ... if we want to change something in this workflow, we go to Andriy"*. Restated by Melisa 2026-07-03 (`R0065`) and 2026-07-23 (`R0117`).
**FULL** — and re-asked twice by Nik after being told. See §3/2.

**H3. What does "ownership" mean in practice?**
Answer, Sergey, 2026-08-05, `05_2026_process-bug-review.txt`, `R0482`: *"the goal and the task of the owner is bring it to the most effective state of things. But while it is not ideal, it is still a responsibility of an owner to make sure that the stuff works if something goes wrong"* — with a worked example of himself covering a ClickUp issue at 21:30. Two-way expectation, `R0492`: *"in ideal situation in nearest future you should see more than we see because you own it."*
**FULL — and answered differently by the two parties.** Nik's counter-position is recorded separately and not merged, `R0493`: *"when you go to developer you have something that you want to build and developer does this stuff ... I maybe can propose something better but I don't ex[pect to own all outbound processes]"*. Both stand.

**H4. Is the infrastructure ownership transfer finished?**
Answer, 2026-08-14, `01_UNKNOWN_dnc-and-migration-sync.txt`, `R0432` (AGREEMENT): Melisa — *"I'm just picking up bugs and reporting them to Mykyta and he's handling everything ... Right now I just need to report what's wrong and he takes care of it"*; Sergey — *"Sounds great to me"*.
**FULL as of 2026-08-14 — and re-opened four days later** by Sergey, 2026-08-18, infra-issues, `R0238`: *"we need a plan and a timeline to make sure that we have a reliable and predictable system that is owned by you ... the current setup shows signs of non-reliability"*. Both records stand against each other. See §3/4.

**H5. How is event work split between Nik and Stefan?**
Answer, 2026-08-14, `R0434` (DECISION, confirmed by Melisa and Sergey): *"for every event we are going to assign GTM engineer who's going to lead this campaign. He's going to be in charge of setting up campaign rescraping, list of attendees, updating messaging"* — one engineer owns an event campaign end to end. The alternative (Stefan prepares, Nik launches) was explicitly rejected, `R0436`.
**FULL as of 2026-08-14** — and note that on 2026-08-05 the two parties held it differently (`R0494`), which is why an actual messaging swap was missed (`R0476`).

**H6. How many hours does Stefan work for us?** — asked by Nik in the 2026-08-14 meeting.
Answer, Sergey, `R0441`: *"There is a monthly retainer ... depending on the intensiveness of the tasks, like he can be involved in like 50, 60 hours a month and then he can be involved in 20, 30 hours a month"*.
**FULL.**

**H7. Am I expected to attend sales/lead-review meetings?** — Sergey, 2026-06-03, `R0169`.
Answer, Melisa, 2026-06-03, `R0015`: *"when you get invites for meetings with the sales team or Sergey, you are supposed to attend them. When we will have meetings that are not relevant to lead gen, I will let you know so that you can skip them."* Reinforced by Sergey, 2026-07-16, `R0187`: *"attending meetings is also part of the performance of a member of a team"*.
**FULL.**

**H8. Who buys which subscription?** — Nik, 2026-06-30, `R0054`/`R0055`. Answers: LinkedIn — *"Toby"*; automation — *"Sergey"*. **FULL.**

**H9. Can the sales team add contacts to nurturing themselves?**
Answer, Melisa, 2026-07-16, `R0361`: *"sales team members shouldn't add contacts to lead nurturing on their own as they don't know how it works ... You can still add them as you understand process"* (to the BDRs). Entry checklist: `R0307` + `R0363`.
**FULL.**

### I. Reporting (P9)

**I1. How much detail should an internal report or decision doc carry?** — asked by Nik in the 2026-08-11 weekly.
Answer, Sergey, `R0469`: a layered structure — a short executive layer, then linked detail. Accepted in the meeting.
**FULL.**

**I2. What breaks reporting?**
Answers: identical campaign naming across LinkedIn / Smartlead / Pipedrive is an invariant — Melisa, 2026-06-29, `R0793`: *"If we have two different naming conventions, people break the reports"*. Event Name spelling — `R0340`. No label = invisible in reports — `R0543`. And the rule that bans delete-and-reimport as a repair method, 2026-07-27, `R0554`: *"it would break reporting because they are also looking at the date created ... if you import all the leads at once, it will just populate that when the lead was created"*.
**FULL.**

**I3. Why does Event name exist separately from campaign name?** — Nik, 2026-07-27: *"so the event name is just a garbage field, right?"*
Answer, Melisa, `R0561`: *"No event name is connected to dashboards. Event name is like field for the ... Lila's [Lilla's] dashboard"* — it is the only field that unifies in-person, introduction and campaign-sourced leads for one event.
**FULL.**

**I4. Can I get access to reporting and to how it is produced?** — Nik, 2026-07-18, dm-melisa, `R0098`: *"I want access to reporting and how its being made"*.
**NOT FOUND — never answered through 2026-08-18.** The broader access theme resurfaces 2026-08-04 (`R0148`) where Melisa explains she herself lacks full access (*"I'm here for almost 3 years and I don't have access to everything ... I can't help you with this"*), without addressing the specific ask.

### J. Tooling & change management (P13/P14)

**J1. What is the protocol for announcing changes to shared live infrastructure, and for reporting status?** — Sergey, 2026-06-26, dm-sergey, `R0180` **[CONTESTED]**.
Answered in substance, three times, in meetings: 2026-07-03, `R0750` — the transparency norm, with Nik agreeing *"Yeah, guys, definitely"*; 2026-07-10, `R0668` — *"we can get together ... on some weekly or bi weekly things where you're going to be presenting what's happening, what's on your table, what's delayed"*, with Nik owning the ClickUp entries; 2026-07-21, `R0595` — *"please put them in ClickUp so we are aligned on what should we expect when"*. Absence/coverage half agreed 2026-08-05, `R0483`.
**PARTIAL** — the principle is stated repeatedly and accepted; no channel, cadence or artifact was ever fixed in writing. Nik's own request for a final call (`R0193`, 2026-07-27) **[CONTESTED]** was deferred a third time. Related asks still open in both directions: Melisa→Nik `R0093`/`R0139`, Nik→Melisa `R0126`.

**J2. Who owns the n8n account, and where must production run?**
Answer, Sergey, 2026-08-11, `R0465`: *"All of this has to be moved to something that is owned by [Janea]systems.com email ... it's going to be an [n8n] instance for [Janea] Systems.com"*. Context: the single-admin-seat problem, 2026-07-30, `R0289` — Nik completed a plan upgrade by logging in with Melisa's credentials.
**FULL as a requirement; no date or target account is set** anywhere in ingested material.

**J3. What is the LinkedIn keyword tool Stefan runs?** — Nik, 2026-07-14, `R0602`.
Answer, Sergey, `R0603`: describes the function (keyword tracking across LinkedIn posts → enrich the posters/likers/commenters) but not the identity: *"I don't know where did he get it or if they build it or anything. Like I don't know."* Nik notes overlap with Trigify.
**PARTIAL** — as of that meeting neither the director nor the incoming infrastructure owner can name or locate a tool already in the GTM stack.

**J4. Where does the Task Assignment automation live?** — Nik, 2026-07-17, `R0076`. Answer, Melisa, `R0077`: *"Task assignment is in pipdrive"*. **FULL.**

**J5. What is the AI/token cost position?** — Sergey, 2026-07-28 (`R0198`) and 2026-08-11 (`R0466`).
Answers: Nik's model routing, 2026-07-28, `R0199`: *"I use Fable only to orchestrate ... As an executor right now is Opus 5"*. Cost item verbally closed by Sergey on 2026-08-11 on the basis that Nik's personal plan covers current spend.
**PARTIAL** — no per-run cost measurement and no cost ceiling or control mechanism exists for when the Clay/Claude table reaches production. Related: the 2026-06-25 pre-qualification estimate `R0823` (~$50–70 for ~20k rows) was an estimate, never measured.

---

## 3. Answered, then re-asked

Both dates, both record ids, and who re-asked. Nik's own re-asks are listed with the same rigour as everyone else's.

**3/1 — Ownership of the nurturing workflow (offered twice, misattributed once).**
Offered first by **Sergey**, 2026-06-16, `21_...ukrainian.txt`, `R0949`: *"if you feel you could take over the work on this whole workflow ... that would be great, because then we do it in-house completely"* — accepted by Nik, sequenced behind the sprint. **Melisa independently asked for the same thing 14 days later**, 2026-06-30, dm-melisa, `R0061`: *"I would like you to own that lead nurturing sytem as guy who built it is not very reliable and smart"*. Two separate owners asked; the earlier ask carries the in-house rationale.

**3/2 — Who built lead nurturing. Re-asked twice by Nik.**
2026-06-16, `R0948`: Nik attributes it to Stefan; Sergey corrects him on the spot — *"Lead nurturing was not made by Stefan. Lead nurturing was made for us by Andriy"* (detail at `R0946`). Nik then asked **Melisa** the same question on **2026-07-03** (`R0065`) and again on **2026-07-23** (`R0117`: *"Can you remind me who set up the n8n itself"*). The fact was stated early and did not stick because nothing was written down. Nik's own 2026-06-16 request to Sergey to re-explain a previously discussed idea (`R0943`) is the same pattern in the same call.

**3/3 — The reporting / change-announcement protocol. Re-asked by Sergey and by Nik. [CONTESTED — `R0180`, `R0193`]**
Asked by **Sergey** 2026-06-26 (`R0180`); answered in substance by Sergey himself 2026-07-03 (`R0750`), 2026-07-10 (`R0668`) and 2026-07-21 (`R0595`); raised again by **Sergey** 2026-07-17 (`R0190`/`R0191`) with a Monday sync promised; that sync was **skipped** on 2026-07-27 when neither party recalled its purpose (`R0192`: *"I don't even remember what it was for ... maybe let's skip it then"*); re-asked the same day by **Nik** (`R0193`) and deferred a third time; half-answered 2026-08-05 (`R0483`); still no written protocol as of 2026-08-18.

**3/4 — Ownership scope of the outreach infrastructure. Asked and re-opened five times.**
Earliest full articulation, **Sergey**, 2026-07-21, `R0566`. Re-asked in Slack 2026-07-23 by Sergey (`R0273` **[CONTESTED]**, `R0286` **[CONTESTED]**); Nik commits 2026-07-23 (`R0276` **[CONTESTED]**: *"from Monday i can replace all Melissa's actions"*); re-asked by Melisa and Sergey 2026-08-04 (`R0141`, `R0204`); **re-opened by Sergey** 2026-08-11 (`R0473`: *"What exactly do you own, [Nik]?"* — deferred to Friday); **closed** 2026-08-14 (`R0432`); **re-opened again by Sergey** 2026-08-18 (`R0238`).

**3/5 — Reply-forwarding category count. Asked by Nik after it had already been stated.**
Stated by Melisa 2026-07-21 (`R0579`, three categories); Nik asked for confirmation 2026-07-23 (`R0119` **[CONTESTED]**) and was told *"yes"* to a four-item list; Melisa said *"only three"* again on 2026-07-27 (`R0539`). Unresolved.

**3/6 — Post-event DNC update. Recurred four times. [CONTESTED — `R0026`, `R0034`]**
2026-06-25 (`R0026`: *"I need to update our DNC as we had 2 events recently and I forgot"*) → 2026-06-29 (`R0034`: *"we need to update DNC / FUCK / i forgot again"*) → stated a third time in the 2026-06-29 sync (`R0791`) → still outstanding 2026-08-11 (`R0464`, Ai4 responders not yet added). Systemic fix stated as landing 2026-08-14 (`R0416`).

**3/7 — DNC label in Pipedrive. Proposed twice by Melisa. [CONTESTED — `R0120`]**
2026-07-23 Slack (`R0120`, accepted verbally) → re-raised 2026-07-27 in the 1:1 (`R0542`, accepted again) → delivered 2026-08-04 (`R0144`) → the label half narrowed on 2026-08-14 (`R0498`).

**3/8 — Outdated tasks on a lead that closed as a deal. Asked by two BDRs, never answered.**
Lule Salihu, 2026-06-08, `R0313`; Araks Grigoryan on the adjacent case, 2026-06-23, `R0326`. The August review effort (`R0398`–`R0401`) covers the topic operationally but never answers either question. Still open.

**3/9 — Nurture leads with no reply. Asked by Lule, deferred, then acted on unilaterally.**
Lule, 2026-07-31, `R0386`; Sergey proposed a mass templated follow-up but deferred the decision — *"it's a great question, let's discuss this on our next sync"*. Three weeks later Lule proposes exactly that approach herself, 2026-08-18, `R0415` — **the last message in the ingested Slack corpus, with no response**.

**3/10 — The 7.5k sales-sprint target. Re-asked by Nik, source never found.**
Melisa, 2026-06-30, `R0052`: *"since our sending limit is 400 per day and we have 7.5k"*. Nik, 2026-08-06, `R0150`: *"The 7.5k target I couldn't locate as an actual loaded list anywhere — if you remember where it comes from, send it"*. His reconstruction (5,913) is independently corroborated by the 2026-07-08 in-meeting counts. The 7.5k figure has no traceable origin in ingested material.

---

## 4. "I told you" claims tested against the record

> **Mandatory framing — read before using this section.** *Absence in the ingested corpus is NOT disproof. The five audited Slack sources (#gtm-engineering, #infra-issues, #lead-generation-team, DM with Sergey, DM with Melisa) plus 21 recorded meetings do not cover unrecorded calls, huddles, WhatsApp, the Ai4 channel, DMs with other people, or in-person conversation. "Not found" here means exactly that — not found in the material this audit ingested. This section does not adjudicate blame and is not evidence of anyone's good or bad faith.*

### 4/1 — KEY CASE. Melisa, 2026-07-03: *"I explained the overall end to end process"* — `R0741`

Claim, stated to Sergey in the team sync, `14_UNKNOWN_team-sync.txt`, `R0741`: *"we aligned. I explained the overall end to end process like in what happens in Slack what happens in pipedrive when every stage happen when every stage changes. So he has all the information"*.

This claim is **datable and boundable**, because the session it refers to is itself in the corpus: the 09:30 1:1 of the same day, `15_UNKNOWN_melisa-mykyta-1on1-workflow-review.txt` (scheduled by Melisa the day before, `R0064`, delivered).

**Both halves, together:**

- **The general claim is well-founded.** That recording does cover an end-to-end walkthrough: LinkedHelper campaign stages and the invite step (`R0753`, `R0755`, `R0761`), the stage→label chain and source-channel expectations (`R0756`, `R0759`), Pipedrive activity logging of outbound messages (`R0760`), the task + labels + Slack notification fired by a stage change to *replied* (`R0765`), and the nurture chain by preferred medium (`R0772`).
- **The specific claim later disputed is not supported by that recording.** The **meeting-label and deal rules** — precisely what is contested on 2026-08-18 (`R0165`: *"I told you when we add meeting label and how"*) — do **not** appear in file 15, nor anywhere else in ingested material before 2026-08-18. The first statement of them in the corpus is `R0164`, the same day as the dispute.

**Result:** general end-to-end walkthrough claim — **SUPPORTED**. Specific meeting-label claim of 2026-08-18 — **NOT FOUND in the ingested corpus**, including in the recording the general claim rests on.

### 4/2 — SUPPORTED. Melisa, 2026-07-20: *"I told you that right now we need to update them manually"* — `R0106`

`R0106`: *"yes, I told you that right now we need to update them manually? ... they used to have label 1.cold but something went off so for the last 3-4montjs we update it manually"*.
**Supported by the recording, 17 days earlier.** 2026-07-03, `R0756`: the label/source-channel chain is described and Melisa says in the same breath *"This is something that's. That we are manually updating"*. **SUPPORTED.** (The transcript does not disambiguate whether the manual part was the label, the source channel, or both — so the manual-update fact is supported; the exact field is not pinned.)

### 4/3 — SUPPORTED. Melisa, 2026-07-06: the replied-but-not-accepted gap — `R0345`

`R0345` (to the channel): *"contacts who reply but do not accept the connection request will not be updated in Slack/Pipedrive so now when you have access to Toby's profile, you should check messages and let Slava know that he needs to process them"*.
**Stated aloud to Nik three days earlier**, 2026-07-03, `R0767`: *"linked helper cannot capture reply ... It happens like maybe for three or three or four contacts per campaign ... I just send this manually to Slava"*. **SUPPORTED, with a quantified frequency.**

### 4/4 — NOT FOUND (see 4/1). Melisa, 2026-08-18: *"I told you when we add meeting label and how"* — `R0165`

Full quote, `R0165`: *"yes, you should be involved and I think we should go through these questions together. You are not asking me! Do you know that bunch of these thing are done manually? I told you when we add meeting label and how"* — Nik: *"I'm not the one who's adding it"*.
No earlier statement of the meeting-label rule is found in the five Slack sources or the 21 recorded meetings. Nearest adjacent record: `R0323`, 2026-06-22, lead-generation-team — a BDR-owner rule for lead→deal conversion, not a label rule. **NOT FOUND in the ingested corpus** — and note the framing above: unrecorded conversation is outside this audit's reach.

### 4/5 — NOT FOUND. Melisa, 2026-06-29: the sprint launch deadline — `R0032` **[CONTESTED, with `R0033`]**

Claim, `R0032`: *"you knew that we needed to launch campaign until the end of last week ... Sergey told me that he told you about the deadline when you started discussing sales sprint and I also pointed out couple of times"*. Nik's contemporaneous denial, `R0033`: *"end of the last week i did not hear this deadline ... we need to be more precise on this matter / it should be stored somewhere"*.
Corpus result: the two meetings inside the disputed window contain **no deadline statement of any kind** — 2026-06-25 (`R0824`: the launch is discussed prospectively) and 2026-06-29 (`R0800`: *"Do you want to launch this today?"*). And 13 days earlier, 2026-06-16, `R0955`, **Nik asked Sergey to set a launch deadline and was given only "the earlier the better"**. **NOT FOUND** in ingested material. Both records stand; not merged.

### 4/6 — SUPPORTED (and conceded). Melisa, 2026-08-03: *"I shared this document before we started campaigns"* — `R0128`

`R0128`: *"Mykyta, I shared this document before we started campaigns / Check the dates / You received full messaging on July 17"* — the record shows **Nik conceding** that the material had in fact been provided on the date cited. **SUPPORTED.** This is the one instance of this pattern in the corpus that resolves cleanly.

### 4/7 — PARTLY SUPPORTED. Melisa, 2026-07-21: *"I told you that Slava is doing that"* — `R0111`

`R0111`: *"Hey, good morning! I told you that Slava is doing that ... i remember (but not who's doing that :DD) - i did a patch so nobody need to do that anymore"*.
The **fact** that a manual update process existed is on the record twice before this (2026-07-03 `R0756`; 2026-07-20 `R0106`). The **owner** — that Slava performed it — is not found stated before this message; the nearest earlier records give Slava a different task (`R0003`, 2026-06-01, AI research tables; `R0345`, 2026-07-06, processing unaccepted repliers). Nik's reply concedes the fact and denies recall of the owner. **PARTLY SUPPORTED: the process yes, the owner not found.**

### 4/8 — PARTLY SUPPORTED, both sides. Melisa, 2026-08-05: *"I told you three, four times ... double notifications"* — `R0486`

`R0486`: *"I told you three, four times that we started getting double notifications on Slack and sales guys asked me about this ... And today you told me that this is the problem that we had for years. And we didn't have this problem for years. This problem happened when we transferred to Hayreach"*.
- **Melisa's frequency claim: PARTLY SUPPORTED.** One dated report appears in the ingested corpus — 2026-08-04, dm-melisa, `R0137`: *"There is also a problem with double Slack notification. Can you fix that as well?"* The other instances are not in the ingested channels.
- **Nik's counter-claim ("the problem we had for years"): NOT SUPPORTED**, and cut against by his own analysis the day before: `R0137` attributes all 21 duplicate notifications to a single old Zapier automation, and `R0135` attributes the double *forwards* to his own parallel-run test window (*"during our test window (Jul 31 – Aug 3 morning) the new system ran in parallel with Make, so every reply was forwarded twice"*). Both causes are recent, which is closer to Melisa's reading than to his.

### 4/9 — NOT TESTABLE. Melisa, 2026-08-05: *"I sent this to AI4 chat ... everybody knew"* — `R0494`

`R0494`: *"We agreed that Stefan is going to do it ... I sent this to AI4 chat that we are rescraping list of attendees every single day ... everybody knew"*.
The Ai4 channel is **not one of the five ingested Slack sources**. This claim cannot be tested either way from this corpus. What the corpus does show is that the Nik/Stefan division of labour was genuinely held differently by the parties on that date (`R0494` status: OPEN) and was only settled nine days later (`R0434`, 2026-08-14).

### 4/10 — NOT FOUND. Melisa, 2026-08-14: *"like I mentioned on Monday"* — `R0405`

`R0405` (to Lule): *"Yes, like I mentioned on Monday - that campaign was executed via LinkedHelper and we no longer use LinkedHelper so data is not being sent to Pipedrive"*.
The underlying fact is very well established (`R0027`, `R0774`, `R0293`). The specific Monday statement is not found in the ingested channel traffic; the corpus contains no evidence that Lule had received or retained it. **NOT FOUND** — an instruction-delivery gap, not a factual dispute.

### 4/11 — NOT FOUND either way. Melisa, 2026-07-17: *"Told you to test it just from Sergey's"* — `R0075`

`R0075`: *"you also launched campaign from my profile? / Told you to test it just from Sergey's"* — Nik: *"i don't get what you try to say by this screenshot"*, then *"cmon mine is ok its just to test"*. No prior instruction on which profile to test from is found in ingested material. **NOT FOUND.**

### 4/12 — NOT FOUND. Nik, 2026-08-11: *"you said / Stefan will do that"* — `R0155`

Nik's own recall claim, `R0155`: *"why campaign is on paused / and no message was updated / you said / Stefan will do that"* — Melisa neither confirms nor denies and redirects (*"This is a question that should be asked in group chat"*). No such instruction is found in ingested material. What the corpus does show, from the same day's meeting, is Nik stating plainly that he did not check: `R0476`: *"I did not check if Stefan updated the message. The message was not updated. So basically I had to check it"*, with Melisa stating the corrective rule (whoever sets up the campaign and loads the leads owns its messaging updates). **NOT FOUND** — and Nik's own non-verification is on the record.

### 4/13 — PARTLY SUPPORTED. Nik, 2026-08-14: *"We had agreed on it"* (DNC scope) — `R0499`

`R0499`: *"We had do not contact list for people who we contacted via campaigns. Right. We had agreed on it. So basically if leads exist in smart lead, for example or high hey Rich campaign, we asked him do not contact list."*
- The **DNC-list half is supported**: 2026-07-21, `R0593`, is an explicit two-party agreement that any campaign reply puts the person on the DNC list.
- The **Pipedrive-label half is not agreed anywhere**, and Melisa's narrower rule (`R0498`) is the one that prevails in the meeting. **PARTLY SUPPORTED.**

### 4/14 — NOT SUPPORTED (Nik's own overclaim, corrected same day). Nik, 2026-06-26 — `R0179`

`R0179`: Sergey — *"did you communicate this to Melisa?"* / Nik — *"Sure ... that everything is ready"* / Sergey — *"where did you do this because she says that you didn't send her anything"* / Nik — *"Ah sorry i did not say that all tables are ... My fault ... I partially run enrichments that's why i said all's ready"*. **NOT SUPPORTED; withdrawn by Nik the same day**, after Sergey cross-checked in real time.

### 4/15 — Reverse case, worth knowing. Melisa, 2026-08-11: *"I don't remember that we talked about starting anything on it"* — `R0470`

`R0470`: Sergey names a ClickUp item — *"the table that we have in our nurturing system"* — and Melisa replies *"Yeah, I know but I don't remember that we talked about starting anything on it"*; Sergey: *"We didn't start"*. A work item sat on the shared board marked *In Progress* that the process owner did not recognise as agreed. Same class of gap as the "I told you" thread, running in the opposite direction: **the tracker is not itself evidence of alignment**.

---

## 5. Contested statuses touching this deliverable

14 ledger records carry `status_contested: true` — different ingestion batches proposed conflicting statuses, the newest evidence was applied, and the full history sits in each record's `update_history`. Per owner instruction they are presented **as contested**, not silently resolved. Records marked **[CONTESTED]** above are listed here with both readings.

| Record | Subject | Reading now applied | Competing reading | Where it appears above |
|---|---|---|---|---|
| `R0009` 06-02 | BDR role definition (P8) | *stated*, plus: acted on 2026-07-08 — Melisa took post-connection follow-up messaging **away from** the BDRs for the London sprint, Sergey agreeing, scoped to that sprint | plain *stated* — a June preference of Melisa's, never a reassignment | §2 H (role boundaries) |
| `R0014` 06-02 | Final score = job-title + company qualification (P10) | *stated*; **later qualified** — on 06-29 Melisa asked which company value the completed qualification used (`R0786`) and got no answer for the already-scored table | *stated*, corrects `R0013`, no open follow-on | §2 F1, F5 |
| `R0026` 06-25 | Post-event DNC update forgotten | *recurred* — still outstanding 2026-08-11 (`R0464`) | *recurred* against `R0034` only (two occurrences, June) | §3/6 |
| `R0033` 06-29 | Nik: *"i did not hear this deadline"* | still open; two in-window transcripts record **no deadline** (`R0824`, `R0800`); plus `R0955` (06-16, no date given) | still open, with no meeting evidence either way | §4/5 |
| `R0034` 06-29 | *"we need to update DNC / i forgot again"* | *recurred*; systemic fix stated as landing 2026-08-14 (`R0416`, `R0418`) | *recurred* — same failure mode as `R0026`, no fix in view | §3/6 |
| `R0115` 07-21 | Nik's DNC scoping commitment | **delivered** — the scoping session is on record (2026-07-29 1:1: `R0524` layers, `R0526`/`R0527` intake) | *partially delivered* — registry built but self-serve scope and offboarding automation still in progress | §2 B2 |
| `R0119` 07-23 | Forwarded reply categories | **contested count** — three in `R0579` (07-21) and `R0539` (07-27) vs four here | *stated* — the four-item set Melisa confirmed | §2 C1, §3/5 |
| `R0120` 07-23 | Pipedrive "do not contact" label | accepted verbally, then **partially reversed** 2026-08-14 (`R0498`, `R0500`) — suppression stays, label narrowed | accepted, and delivered 2026-08-04 (`R0144`) | §2 B5, §3/7 |
| `R0121` 07-27 | Reply arrived, no Slack notification | *open* — recurring reply-detection gap, worked around by manual re-run; detection method documented (`R0536`); same silent class as `R0510` | *open*, single incident | §2 C5, C7 |
| `R0180` 06-26 | Sergey's reporting-protocol question | **partially answered** by `R0483` (08-05) on the absence/coverage half; the wider protocol still OPEN | fully OPEN — deferred repeatedly, never resolved (with a 07-03/07-10 partial answer noted in other batches) | §2 J1, §3/3 |
| `R0193` 07-27 | Nik: ClickUp vs sync vs backlog — decide | **OPEN** — 08-14 settled ownership scope (`R0432`) but recorded no reporting protocol | *partially answered* — the ClickUp half was answered 07-21 by Sergey (`R0595`); cadence and backlog halves open | §2 J1, §3/3 |
| `R0273` 07-23 | Sergey's three-part status ask | **answered-in-part**; ownership boundary still OPEN as of 08-11 (`R0473`) | *answered* — and no longer the earliest instance: the same ask was put and answered 07-21 (`R0566`, `R0576`, `R0595`) | §3/4 |
| `R0276` 07-23 | Nik: *"from Monday i can replace all Melissa's actions"* | **delivered** — confirmed at the 08-14 ownership meeting (`R0432`) | *overdue/unclear* — scope still disputed 08-05 (`R0482` vs `R0493`) and undefined 08-11 (`R0473`) | §2 H4, §3/4 |
| `R0286` 07-23 | *"Somebody has to own all of this"* | **accepted** — explicitly closed at the 08-14 meeting (`R0432`) | *accepted-in-practice* — Nik engaged with specifics without an explicit yes; the verbal accept came 07-21 (`R0566`) | §2 H4, §3/4 |

---

## 6. Discipline notes for anyone using this file

- **Out-of-corpus records.** `R0956`, `R0957`, `R0958` are owner corrections supplied by Nik in terminal on 2026-08-19. They are cited in this file **only** as `OUT-OF-CORPUS` (see §2 B3) and are never in-corpus evidence.
- **One person stating something is not agreement.** Where a record is typed AGREEMENT (`R0774`, `R0593`, `R0432`, `R0479`, `R0159`, `R0483`, `R0141`, `R0204`) an explicit multi-party yes exists in the text. Everything else typed PROCESS FACT / DEFINITION is *stated by one person*, however senior.
- **Contradictions are kept as pairs, never smoothed.** `R0303`↔`R0322` (scan dates), `R0040`↔`R0251` (send capacity), `R0119`↔`R0579`/`R0539` (category count), `R0482`/`R0492`↔`R0493` (what ownership means), `R0498`↔`R0499` (DNC label scope), `R0509`↔`R0510` (paused-campaign replies), `R0432`↔`R0238` (is the transfer closed).
- **Where Nik dropped something, it says so**: §4/12 (did not verify the messaging swap), §4/14 (premature "everything is ready"), §3/2 (re-asked a known answer twice), §2 B3 (`R0416`: DNC entry provenance not reconstructable), §2 C5 (a 90%-confidence answer given in an onboarding session and contradicted minutes later), and `R0515`/`R0512` — three questions promised a researched answer on 2026-08-14 with no follow-up found in ingested material.
- **Coverage limits.** Slack: dm-melisa, dm-sergey, #gtm-engineering, #lead-generation-team (all through 2026-08-18); #infra-issues exists only from 2026-08-06. Transcripts: 21 files, 2026-06-16 → 2026-08-14 (file 09 yielded 0 records; file 19's date rests on an owner ruling; file 20 is month-only). Not covered: the Ai4 channel, WhatsApp, DMs with anyone other than Melisa and Sergey, and every unrecorded call. Conclusions here are provisional to that boundary.
