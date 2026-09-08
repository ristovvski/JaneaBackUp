# 05 — CONCERNS REGISTER

*Deliverable #5 of the communication audit (`communication_audit_brief.md`). Built programmatically from `COMMS_AUDIT_build/ledger.json` — 937 records, 62 typed `CONCERN` plus concern-shaped `ISSUE` / `QUESTION` / `PROPOSAL` records recovered by sweep. Corpus: 5 Slack sources (#gtm-engineering, #infra-issues, #lead-generation-team, DM Sergey, DM Melisa) + 21 recorded meetings. Cut-off for all "days open" figures: **2026-08-19**.*

---

## 1. How to read this

Every entry carries a verbatim quote, a date, a source and a record id; nothing here is asserted without a receipt. **"No evidence it was addressed in ingested material"** is not the same as "not addressed" — unrecorded calls, un-audited channels and anything after 2026-08-18 are outside the corpus, so an item can be open here and closed in reality.

The register's argument is *lead time*: for each worry that came true, how many days ran between the warning and the event. A long lead time is a process finding about how warnings travel, not a verdict on any person — vindication is not competence and being surprised is not negligence. Nik's unheeded warnings and the warnings Nik did not act on are written the same way.

Where two records disagree, both are kept side by side and neither is smoothed. 14 ledger records carry `status_contested: true`; those are flagged **[CONTESTED]** with both readings and left for the owner to resolve (§6). Owner corrections (R0956–R0958) are marked **OUT-OF-CORPUS** and are never cited as in-corpus evidence.

---

## 2. Concerns that MATERIALIZED

Twelve worry→event chains where the corpus contains both the warning and the event that proved it out.

---

### M1 · "Another automation rewrites mine" — 21 days
**Warning** — Nik, 2026-07-21, meeting `08_UNKNOWN_mykyta-melisa-sergey-sync.txt`, **R0586** (date_confidence PROBABLE(calendar)):
> *[Melisa] you fixed that problem with reply labels, right? / [Nik] No, because. Because another automation rewrites mine and I don't want. I can't change anything that you are running right now*

Melisa states the operational consequence in the same exchange: *"Slava does not know that he needs to process incoming replies ... he filters out only the ones that responded labels ... that could be the reason why yesterday we didn't have anything in ClickUp."*

**Event** — Nik, 2026-08-11, #infra-issues, **R0218**:
> *old Zapier automations were silently wiping "3. Responded" / "4. Positive Reply" labels off leads whenever certain person-fields updated. 11 leads were affected since Aug 5 ... All automations responsible are off, all 11 leads restored to their exact previous labels.*

**Lead time: 21 days.** The mechanism was named on 07-21 and root-caused on 08-11. The intervening block was stated in the warning itself — Nik would not modify automations Melisa was running live, and no third party was asked to. Status now `resolved`.

---

### M2 · Change-management rules → the Aug 5–11 alert blackout — 15 days to the event, 21 to detection
**Warning A** — Melisa Draksler, 2026-07-21, `08_UNKNOWN_mykyta-melisa-sergey-sync.txt`, **R0577** (P13; the clearest change-management rule anywhere in the corpus):
> *we shouldn't do it on Fridays ... any big change needs to be pushed into production at the beginning of the week so that we have time to work on it so that it's not like, you know, midnight calls and stuff breaking on the go. And we also need to notify everyone that automation is going to be paused, that incoming replies will not be forwarded, that notifications are not going to be sent to Slack during that time*

**Warning B**, same meeting — Melisa, **R0571**:
> *we shouldn't do this while we are running AI for [Ai4] campaign because if we will touch it during campaign, like it will break the workflow ... if something breaks and we don't get labels, leads do not get created. We don't get notifications about people who replied. It creates like extreme overload and manual work*

**Warning C**, four days earlier and from two directions — Melisa, 2026-07-17, dm-melisa, **R0093**: *"but you need to warn me about stuff like this"*; and Sergey the same evening, dm-sergey, **R0190**: *"Неприпустимо комусь одному щось вмикати вимикати або змінювати не вирівнявшись з іншими"* ("it is unacceptable for one person to turn something on/off or change it without aligning with others").

**Event** — Nik, 2026-08-11, #infra-issues, **R0215**:
> *The notifications to #lead-processing were historically sent by an old Zapier automation. On Aug 5 at 13:28 we switched that automation off as part of shutting down the legacy stack ... What we didn't know then: it was also the only thing posting reply notifications to the team channel ... So from Aug 5 the channel went dark*

**Lead time: 15 days** (07-21 → the 08-05 switch-off), **21 days** to detection on 08-11 — the channel was dark for 6 days inside a live Ai4 follow-up period.

**Verification note, stated plainly because it changes the finding:** 2026-08-05 was a **Wednesday**. The clause that was crossed is the *advance-notification* clause, not the no-Friday clause — the corpus shows Nik announcing a Friday cut-over (**R0495**, 2026-08-05, `05_2026_process-bug-review.txt`: *"on Friday I really expect to stop using the old one and start using the new"*) while the legacy notification automation was in fact disabled the same Wednesday, 13:28. R0495's status records exactly this: *"the legacy stack was in fact being switched off the same day as this meeting ... rather than on the Friday cut-over Nik describes, and that early switch-off is what caused the Aug 5–11 reply-notification blackout."* The mid-week timing followed R0577's first clause; the pause was not announced, which is the clause that failed. A scheduled-window mechanism had also been agreed in the same 07-21 meeting (**R0578**, Sergey: *"Stop the campaign for 30 minutes. You're doing your stuff, testing it"*) and was not used for this change.

---

### M3 · Sending-capacity arithmetic → the coverage shortfall — 8 days
**Warning** — Melisa Draksler, 2026-06-30, dm-melisa, **R0052**:
> *since our sending limit is 400 per day and we have 7.5k, how we are going to make sure that we cover as many people as possible before July 27? ... Even if we would send emails every day, it would take 19 days to send just the first one*

**Root cause, one day earlier** — Melisa, 2026-06-29, `16_UNKNOWN_lead-scoring-sprint-planning.txt`, **R0798** (DECISION, active):
> *we will only use use inboxes that are attached to Toby because Toby is going to be in London*

with the capacity consequence stated by Nik the same day (**R0040**, dm-melisa: *"if we use only Toby's emails (which have 20+ emails per day limit) = ~400 emails per day"*) and the reason his infrastructure was small stated by Melisa the next (**R0053**: *"Toby didn't attend any events for almost a year and half so we didn't expand his infra"*).

**Event** — Melisa, 2026-07-08, `13_UNKNOWN_team-sync.txt`, **R0695**: the sprint is mid-flight with roughly **1,500 emails sent and ~4,500 contacts still uncontacted** across the two London campaigns (*"This Sprint is not going as we planned, so I'm struggling ... our acceptance rates are on LinkedIn are 10%"*). The arithmetic held.

**Lead time: 8 days** to the mid-sprint measurement; **37 days** to the written reconstruction on 2026-08-06 (**R0391**, #lead-generation-team, Melisa: *"we reached out to 5,913 people for Sales Sprint London, but in Pipedrive, it's only visible 4.7k"*; **R0150**, dm-melisa, Nik: *"The 7.5k target I couldn't locate as an actual loaded list anywhere"*).

**Partially addressed at the plan level, not at the outcome level:** the same-day decision **R0051** (2026-06-30, Melisa + Nik: *"cool we'll send at least 2 messages"*) capped the sequence to fit the capacity. The coverage gap still occurred, and the "7.5k" figure the concern was measured against was never traced to a loaded list (R0150, R0052 status).

---

### M4 · Bus factor and the cost of verbal-only knowledge → tested by the ownership handover
**Warning A (documentation cost)** — all three participants, 2026-08-14, `01_UNKNOWN_dnc-and-migration-sync.txt`, **R0447**:
> *[Nik] we don't have a real really good way of presenting information for those cases ... in notion I always had ... everything described that person just goes through / [Melisa] imagine me explaining entire lead generation infrastructure and how we attend events and everything to salespeople. Every salesperson across like four or five [sessions] / [Sergey] We needed to onboard four sales people during the last two or three months*

**Warning B (bus factor proper)** — Melisa Draksler, same meeting, **R0443**:
> *our conversation about hiring Mykyta started as we do not want to depend on one person. And what happens if we ditch Stefan and we have only Mykyta? ... I do not want to be in a position where something breaks in the middle of weekend and we don't have Mykyta anywhere ... and it's on me*

Sergey states the opposite position in the same exchange (**R0444**, PROCESS FACT): *"As a business, we need to take these risks ... We want to be ready for a situation when something happens where we are ready to be only with one person and with a bunch of automations ... We're going to stop campaigns if needed."* Both retained; not merged.

**Verification note:** the task framing assigned the bus-factor concern to R0447. As ingested, R0447 is the *repeated-verbal-explanation cost* concern (all three speakers) and **R0443** is the bus-factor concern (Melisa, same meeting, same date). Both are placed here.

**The handover** — proposed by Sergey 2026-07-23, #gtm-engineering, **R0286** *[CONTESTED]* (*"Somebody has to own all of this ... Mykyta if you can be the owner, that would be great"*), closed as an explicit multi-party agreement 2026-08-14, **R0432** (Melisa: *"I'm just picking up bugs and reporting them to Mykyta and he's handling everything"* / Sergey: *"Sounds great to me"*).

**Events that tested it, both before the concern was formally stated:**
- 2026-08-05, `05_2026_process-bug-review.txt`, **R0490** — Melisa, not onboarded on the tool that replaced the one she used for reporting, could not answer how many connection requests remained, which blocked a live routing decision on 44 Ai4 contacts: *"I'm in a position where I don't know based on hay reach how many connection requests we still have to send ... I have 44 new people on the list and we are not sure whether we will be able to send them connection requests today and tomorrow"* — **9 days before R0443 was raised**.
- 2026-08-14, `02_UNKNOWN_heyreach-pipedrive-walkthrough.txt`, **R0521** (speaker unidentified; roster suggests one of Araks / Lule / Melisa D — mapping unconfirmed): *"Hopefully we will be able to do more stuff on our own without pulling your sleeve."* No written HeyReach runbook is evidenced as following that session.
- 2026-07-27, #lead-generation-team, **R0376** — *"we lost the only access to Toby's profile and he's now in London"*; resolved in ~36 minutes, but the single-renewal-owner pattern was not addressed.

**Lead time: negative (−9 days).** The failure mode is recorded *before* the concern that describes it. This is the one entry in the register where the warning followed the event rather than preceding it, and it is the reason the still-open item (§4, row 3) is scored on closure evidence rather than on lead time. What would close it is already written down: **R0478** (2026-08-11, Melisa: *"it's also important to onboard Stefan on this so that he's aware how everything works in case something breaks while you are away ... just so that not everything is on one person"*) and **R0126** (2026-07-29, *"Please make sure that Stefan is also aware of all changes"*) — both still `open`.

---

### M5 · "I forgot the DNC update" → the 2026-08-14 label incident — 4 days, then 50
**Warning** — Melisa Draksler, 2026-06-25, dm-melisa, **R0026** *[CONTESTED]*:
> *Hey, I almost forgot - I need to update our DNC as we had 2 events recently and I forgot. So before we launch sales sprint campaign, we will need to check it again*

**First recurrence, 4 days later** — Melisa, 2026-06-29, dm-melisa, **R0034** *[CONTESTED]*:
> *we need to update DNC / FUCK / i forgot again*

(A third statement of the same gap falls in the same five-day window, in the 06-29 Sales Sprint Sync — R0034's update_history, B8, referencing R0791.)

**Still outstanding 47 days later** — 2026-08-11, `04_UNKNOWN_dnc-alignment-integration-review.txt`, **R0464**: *"[Melisa] leads that we received for AI4 ... Are they already added to the net contact list or we need to add them? / [Nik] I don't need to add them. I think it's not done yet. I will make it."*

**Event, 50 days later** — 2026-08-14, `02_UNKNOWN_heyreach-pipedrive-walkthrough.txt` (08:30), **R0496**:
> *Speaker 2 (01:06): "I just realized that label do not contact was added to 2000 leads in Pipedrive." / (01:30) "No, you added to existing leads that are in different stages. You added this do not contact label. And the problem is that other labels that we had for some leads disappeared." / Speaker 3 (02:39): "that's what I noticed today." / Speaker 1 (02:25, Nik): "I think I will check it out. I'm not sure."*

The reversal ran the same day (**R0163**, dm-melisa: *"the automated reversal is about to do the whole population in one pass with full audit trail. Can she pause label edits for ~20 minutes? / Ask her yourself"*), colliding with a BDR manually removing the same labels. **R0162** (Nik's request for 2–3 specific examples of the other labels that disappeared) is `OPEN — no answer found in ingested material`.

**Lead time: 4 days to the first recurrence, 50 days from the first warning to the automated catch-up landing as a 2,000-lead label event.** Note the direction of travel: the *manual* forgetting (R0026/R0034) is what the automation was built to remove, and the automated pass then produced a different failure of the same family. Melisa states the reason it matters in the same meeting (**R0497**): *"there is no change log for labels for pipedrive and also support was not able to bring them back"*; Nik's counter-position, retained: *"It has no history in pipedrive. Maybe, but it has history in my cloud code because I know every action it does."*

The systemic fix is claimed the same day (**R0416**: registry live, ~2,200 blocked, Surfe-created leads auto-blocked; **R0418**: backfill of Ai4/London/sales-sprint repliers *"gonna be landing today"*) with **no post-meeting confirmation in ingested material**, and with Nik on record that the provenance of the existing 2,200 entries is not reconstructable (*"Honestly I can't answer from where I took them"*).

---

### M6 · LinkedHelper auto-labeling broken ~3–4 months before it reached Nik
**Event and disclosure in one message** — Melisa Draksler, 2026-07-20, dm-melisa, **R0106**:
> *yes, I told you that right now we need to update them manually? ... they used to have label 1.cold but something went off so for the last 3-4montjs we update it manually*

**Silent-breakage window: ~90–120 days** (Melisa's own "3–4 months", i.e. breakage from roughly April 2026 to the 07-20 exchange). This is the longest undetected-defect window in the corpus. It is a different measure from lead time — no one warned that it *would* break; it had already been broken and papered over by hand.

**In-corpus lead time on the disclosure itself: 17 days.** The same manual-labeling gap is on record from Melisa 17 days earlier, in a recorded session — 2026-07-03, `15_UNKNOWN_melisa-mykyta-1on1-workflow-review.txt`, **R0756**: *"based on this LH campaign stage in pipedrive ... it should assign label one [1.cold] ... This is something that's. That we are manually updating."* R0756's own status flags that the transcript does not make unambiguous whether the manual part was the label, the source channel, or both — so this is placed as *stated on 07-03*, not as *unambiguously communicated on 07-03*.

**Recurrence, on a different label, 29 days later** — 2026-08-18, dm-melisa, **R0165**: *"You are not asking me! Do you know that bunch of these thing are done manually? I told you when we add meeting label and how / I'm not the one who's adding it"*, alongside **R0164** where the meeting-label rules are finally written out. R0165 remains `open` as of the last ingested message.

Related, and part of why manual fields fail: Nik, 2026-07-10, `11_UNKNOWN_pipedrive-automation-w-lilla-szabo.txt`, **R0654**: *"if it's a deal of creating, just filling one, one field. Yeah, it's bad that person doesn't do it unfortunately"* — corroborated by **R0389** (372 Ai4 leads with no Event name) and by Melisa's **R0528** (*"they will forget. They will Forget. They'll forget 100%"*).

---

### M7 · "Melisa has enough of headache not to watch for everything" → four misses she caught anyway — 21 to 29 days
**Warning** — Sergey Cujba, 2026-07-16, #lead-generation-team, **R0358**:
> *Engineering leader at Amazon… This is a critical issue to me ... And Melisa has enough of headache not to watch for everything to be done in the right way*

**Restated by Sergey a month later** — 2026-08-18, #infra-issues, **R0236**:
> *The structural issue is that if Melisa doesn't notice something, it creates mess ... And how do we know if she missed something like 1500 leads marked mistakenly...*

**Verification note:** R0236 is dated 2026-08-18, *after* the misses below. It is therefore recorded as the sharpest **restatement** of the concern, and the lead time is measured from R0358 (07-16), which is the earliest same-class formulation in the corpus. Melisa's own earlier versions: **R0265** (2026-07-09, #gtm-engineering: *"please keep an eye on Smartlead for such things as I have a lot of tasks and meetings so I'm struggling to keep up with everything"*) and **R0069** (2026-07-13, dm-melisa: *"we need to have system in place to manage it as I can't keep up with everything"*).

**Events — each detected by Melisa or a BDR, not by a monitor:**
| Date | id | What was missed | Lead time from R0358 |
|---|---|---|---|
| 2026-08-06 | **R0389** | *"372 leads from AI4 do not have the Event name field - and that field is crucial for Lilla's dashboard that management is using"* | 21 d |
| 2026-08-06 | **R0391** | *"we reached out to 5,913 people ... in Pipedrive, it's only visible 4.7k"* (~1,200 contacts) | 21 d |
| 2026-08-11 | **R0472** | *"some of the leads ... did not receive follow up, they were not sent to Slack, they were not processed by Slava, their responses were not captured"* | 26 d |
| 2026-08-14 | **R0496** | DNC label on ~2,000 leads / other labels gone — *"that's what I noticed today"* (BDR) | 29 d |

Sergey's follow-through commitment (**R0359**, same day: *"I'll get back with an update on how we should approach making sure that all the things than must be taken care of are actually taken care of"*) is `open`; the closest later candidate (**R0401**, 2026-08-11) landed only as a ClickUp checklist item, and the ledger explicitly marks the link as plausible, not confirmed.

---

### M8 · "Labels just get deleted and we can't bring them back" — 15 days, with the cause reattributed **[both readings retained]**
**Warning** — Melisa Draksler, 2026-07-27, `07_UNKNOWN_mykyta-melisa-1on1.txt`, **R0551** (status: `materialized, and later attributed to a different cause`):
> *we had two cases where I was actually filtering out leads and they just got updated for no reason. Like some random like lead lead labels got deleted and we couldn't bring them back. Even support told me that they cannot bring it back ... whenever you need to do something with pipedrive they are unpredictable*

**Event** — 2026-08-11, **R0218** (the Zapier label-stripper, see M1).

**Lead time: 15 days.** Two readings of the same symptom class are retained and not merged: R0551 (earlier, 07-27) attributes it to Pipedrive itself being unpredictable with no restore path; R0218 (later, 08-11) attributes it to legacy Zapier automations stripping labels on person-field updates. The 08-14 statement **R0497** repeats the vendor reading (*"no change log for labels for pipedrive"*) three days after the automation reading landed — i.e. the corrected cause had not propagated.

---

### M9 · HeyReach batched-message logging → a reply that reached nobody — 20 to 25 days
**Warning** — Melisa Draksler, 2026-07-17, dm-melisa, **R0083**:
> *heyreach can send messages in batch ... if they are sent with very short amount of time between them ... result is that we don't log both messages - only one*

**Commitment the same day** — Nik, **R0084**: *"but i will have time to fix it"* — status `open`.

**Events** — 2026-08-06, #lead-generation-team, **R0392** (Melisa: *"probably there was an error from Heyreach or something for this lead"*), answered with a manual workaround only (**R0393**, Nik: *"you can manually add the message / as a workaround"*); then 2026-08-11, **R0472** (the silently missed HeyReach cohort, M7 above).

**Lead time: 20 days** to the first recurrence, **25 days** to the compound failure. The defect class — a failure that produces no error — is the same one documented for LinkedHelper reply detection on 2026-07-27 (**R0121** *[CONTESTED]*, *"we received reply for Toby but notification didn't come to slack ... it was not an error, it was in the 'successfully processed' bucket"*) and observed again 2026-08-14 (**R0510**, *"Stefan paused those two campaigns and while they were paused, we were not receiving any notifications about incoming replies"*).

---

### M10 · DNC cannot match people without a LinkedIn URL — 35 days to re-ask, 40 to measurement
**Warning** — Melisa Draksler, 2026-07-10, `12_UNKNOWN_trigger-campaigns-sprint-planning.txt`, **R0680**:
> *right now we have like a situation in pipedrive where we have some leads added by the sales team ... They only have maybe first name, last name and company name. They don't have LinkedIn URL ... And when we discussed this with Stefan, we realized that we are actually not putting people on the not contact list if they don't have LinkedIn a profile URL*

(The matching key itself is on record from 2026-06-29, **R0043**, Nik: *"Li for DNC"*.)

**Re-asked 35 days later, still unmechanised** — 2026-08-14, `01_UNKNOWN_dnc-and-migration-sync.txt`, **R0425** (`partially-answered`): *"Do we have like some plan B or fallback ... when they create contact but this contact does not have LH LinkedIn profile URL so we are not able to add them ... Do we get some kind of notification that like hey, we have a lead new lead created but it cannot be added to the not contact list"*

**Measurement, 40 days later — OUT-OF-CORPUS** — **R0956** (owner correction, Nik, terminal, 2026-08-19; `PROVENANCE: OUT-OF-CORPUS — never cite as in-corpus evidence`):
> *current system matches LinkedIn OR email; residual gap = persons with neither (1,019), enrichment fix in flight as of 08-19*

**Lead time: 40 days**, and the concern is **still open in residual form** (§4, row 1). The matching rule has widened from LinkedIn-only to LinkedIn-**OR**-email, which narrows R0680's gap but does not close it: 1,019 persons carry neither identifier as of 2026-08-19.

---

### M11 · Melisa's capacity warning → materialized inside the meeting — 1 to 5 days, then 0
**Warnings** — **R0265** (2026-07-09), **R0069** (2026-07-13), quoted in M7.

**Event** — 2026-07-14, `10_UNKNOWN_team-sync-integration-incident.txt`, **R0596**:
> *Everything is falling apart. Like I came back. I got like hundreds of messages. Everyone have some questions. Integration is not working. I need to prepare messages for Toby. I need to prepare table for Toby. I need to prepare idea for Trigger campaigns. Like I'm all over the place.*

**Lead time: 5 days from R0265, 1 day from R0069.** In the same meeting the concern **R0597** (*"it's just one of these days that are getting more and more ... I have like 25 things for this"*) **materialized inside the session, 0 days**: the trigger-campaign hypothesis document was not prepared, the effort was re-sequenced, and Sergey offered to take the formalisation (*"this is something that I can help with if needed"*).

Which integration was broken is **never stated anywhere in that transcript** and the topic is not returned to — recorded as a gap, not as an unnamed incident. The escalation continued on 2026-08-04 (**R0140**, Melisa: *"I'm working 12 hours a day and idea behind hiring you and BDRs was to fix that so that I can work just 8"*) and Nik voiced the mirror-image version a week before it (2026-07-27, **R0558**: *"I just can't do like everything, you know ... We need to discuss this stuff"*).

---

### M12 · Divergent enrichment standards between GTM engineers
**Warning** — Sergey Cujba with Nik, 2026-08-14, `01_UNKNOWN_dnc-and-migration-sync.txt`, **R0437**:
> *[Sergey] it's going to look like we have different standards of enrichment between go to market engineers ... this is something that we should avoid ... there should be a moment in time where we are aligning on the tool set / [Nik] it's gonna be one way for me, it's gonna be one way for Melisa, it's gonna be one way for Sergey and one [for] Stefan ... how would we manage this stuff?*

**Already materialized when raised** — the divergence had produced concrete incidents before this date: the Nik/Stefan messaging-swap collision on 2026-08-11 (**R0476**: *"I did not check if Stefan updated the message. The message was not updated"*), the disputed Ai4 scraping ownership on 2026-08-05 (**R0494**, `OPEN`: Melisa states *"We agreed that Stefan is going to do it"*, Nik asks *"who does scraping for this event?"*), and the paused-campaign / un-updated-messaging exchange of 2026-08-11 (**R0155**, `open`, disputed recall). Divergent standards were then **accepted deliberately for now** (R0437 status, R0439). Sergey had raised the identical alignment gap twice before: **R0180** *[CONTESTED]* (2026-06-26) and **R0190** (2026-07-17).

**Lead time: none to measure — the concern trails its own materializations by up to 9 days.** Recorded here because the register's job includes showing where a worry arrives *after* the evidence.

---

## 3. Concerns ADDRESSED — and concerns DISPOSED OF

Two different things, kept apart on purpose. **Addressed** = a fix, ruling or decision landed. **Disposed of** = someone asserted it was fine, or the raiser set it aside. *An assurance is not a fix.*

### 3a. ADDRESSED (a fix or ruling landed) — 6

| Concern | Raised | What resolved it |
|---|---|---|
| **R0013** (Nik, 2026-06-02, dm-melisa): *"you have no company level qualification / at all / i think thats bad"* | 06-02 | **R0014** *[CONTESTED]* same day, Melisa: *"We have company qualification - so in order to calculate final score, we use Job title qualification and Company qualification"* — the premise was factually corrected. |
| **R0366** (Melisa, 2026-07-22, #lead-generation-team): *"this guy removed Toby as connection as soon as we sent this message, it's worth to also review cases like this and try to find patterns we should avoid"* | 07-22 | **R0367** (2026-07-23, DECISION, active): *"we should avoid rewriting their CV in messages as it looks very strange ... add such feedback to your Claude projects/chat so that it can understand which patterns it should avoid"* — both BDRs confirmed compliance the same day. |
| **R0728** (Melisa, 2026-07-03, `14_UNKNOWN_team-sync.txt`): *"I'm not sure if he's going to have enough bandwidth or. We should assign this conference to Stefan"* | 07-03 | Two same-meeting decisions: **R0729** (Ai4 conference table to Stefan) and **R0730** (Karol's initiative capped: *"If it takes like I don't know up to 20% of your time, I think that it should be okay"*). |
| **R0158** (Melisa, 2026-08-11, dm-melisa) — communication-style feedback | 08-11 | Nik: *"ok i will consider it"*. Recorded as addressed per the ledger; the same feedback category recurs from Sergey on 2026-08-12 (**R0210**), so the acknowledgement did not end the topic. |
| **R0459** (Sergey, 2026-08-11): *"the tasks are piling up as like in progress and we are not closing them"* | 08-11 | Addressed within the meeting — ClickUp statuses and due dates reviewed item by item. |
| **R0034 / R0026** DNC-forgetting (M5) | 06-25/06-29 | **Partially addressed**: systemic registry claimed live 2026-08-14 (**R0416**, **R0418**) — *delivery not confirmed in ingested material*, and the 2,200 existing entries have no reconstructable provenance. Counted in *materialized*, listed here for the fix trail only. |

Also partially addressed, with the residue named: **R0552** (Melisa, 2026-07-27, blast-radius of a bulk Pipedrive patch on a CRM shared with Marci's team) — handled in-meeting *only* by agreeing a filter (**R0553**), and the bulk patch itself was then deprioritised (*"for now I think we have like other priorities"*), so the shared-instance exposure is unchanged.

### 3b. DISPOSED OF (asserted fine, or set aside by the raiser) — 8

**Closed on an assurance:**

1. **R0057 → R0751 — HeyReach vendor distrust, dropped on a capability assurance.** Melisa, 2026-06-30, dm-melisa: *"they also have the worst customer support ... this is why I don't trust them."* Restated with named causes on 2026-07-03 (`15_...workflow-review.txt`, **R0751**: *"they were like super not interested to give any information ... they're just not interested in smaller companies"*) and then accepted anyway because Nik holds the API documentation: *"I just feel you don't need them at all ... Maybe they suck at support but they not suck at the integration."* **Nothing about vendor support changed** — the exposure was re-routed onto one person's documentation. The HeyReach defect stream that followed (R0083, R0384, R0392, R0472, R0510, R0511) is the same surface the concern named.
2. **R0648 → R0649 — human-in-the-loop dropped on an unmeasured "reliable enough".** Lilla Szabo, 2026-07-10, `11_UNKNOWN_pipedrive-automation-w-lilla-szabo.txt`: *"I would leave the calculation itself like the calculator bit still for the salesperson. Because ... if like the AI finds the wrong company, then it's tricky to like revert that, isn't it? ... if the AI system finds the wrong company or is unsure of something, then it might come up with like an inaccurate ICP band."* Nik, same session (**R0649**): *"I think it's gonna be reliable enough ... I think sales guy would be on the same level of understanding as 5.6. At least that's my view."* Lilla withdrew the position (*"Okay. Because that. If that can work reliably. That sounds really good."*). **No accuracy target, sample, evaluation method, confidence threshold, unsure-case handling, review path or reversal path was offered or requested.** The wrong-person/wrong-company error class is live elsewhere in the corpus (mis-targeted London-sprint contacts, **R0704**; ~10% reply miscategorisation, **R0580**). Status: `open and unmitigated`. **Disposition ≠ mitigation.**
3. **R0466 — LLM token cost, closed verbally.** Sergey, 2026-08-11: *"Did you count like how much tokens it uses just to make sure that it is justified"* → *"This question is close for me"*, on the basis of Nik's *"right now I don't have this problem because my plan covers the stuff"*. Still missing: per-run cost measurement and any ceiling for production.

**Set aside by the person who raised it:**

4. **R0600** (Sergey, 2026-07-14) — unsolicited-email complaint risk from healthcare organisations via Luma; Sergey downgraded it himself (*"it's just one small thing"*), Melisa answered on relevance rather than on the complaint risk, no mitigation agreed.
5. **R0905** (Sergey, 2026-06-16) — switching the offered topic between follow-ups may confuse the lead; *"але це, скоріше, знаєш, така менша проблема"* ("that is rather a smaller problem"). No action.
6. **R0904** (Sergey, 2026-06-16) — distrust of free-form LLM copy, resting on a **September 2024** test that Sergey himself flags as possibly out of date. Nik conceded the specific line only (*"Ні, я згоден. Треба більш конкретно"*). The general question was not retested.
7. **R0922** (Sergey, 2026-06-16) — dependence on Andriy's Apollo access as a vendor-retention lever; explicitly deferred (*"я на зараз просто тобі накиду інформацію ... а потім будемо вирішувати"*). No decision.
8. **R0947** (Sergey, 2026-06-16) — that taking the enrichment workflow in-house may read as a threat to its owner; mitigation agreed only as *"краще зробити все максимально м'яко"* ("better to do everything as softly as possible"). Nik's counter (build a private copy) was not endorsed. The same worry recurs in Nik's own words five weeks later — **R0195**, 2026-07-23 (*"it might look as a 'threat' to him that we want to take this over"*). **Attribution flag:** R0195's `participants` field names Sergey Cujba, while R0947's cross-reference note describes the same line as Nik's. The ledger is internally inconsistent here; not resolved in this deliverable.

---

## 4. Concerns STILL OPEN — sorted by operational risk

Days open counted to **2026-08-19**. "What would close it" is drawn from what the corpus itself already proposes wherever possible.

| # | Worry (quote, abridged) | Raised by | Date | Days open | What would close it |
|---|---|---|---|---|---|
| 1 | **DNC residual gap.** *"we are actually not putting people on the not contact list if they don't have LinkedIn a profile URL"* — **R0680**; re-asked as *"Do we have like some plan B or fallback ... when they create contact but this contact does not have LH LinkedIn profile URL"* — **R0425** (`partially-answered`) | Melisa Draksler | 2026-07-10 | **40** | Matching now runs LinkedIn **OR** email; residual = **1,019 persons with neither identifier**, enrichment fix in flight as of 2026-08-19 — **R0956, OUT-OF-CORPUS (owner correction, not a corpus quote)**. Closes when the enrichment lands, the residual count is re-measured, and the *notify-on-unblockable-lead* mechanism R0425 asked for exists. Compliance-facing, hence rank 1. |
| 2 | **Deliverability never inspected — "blindly trust Stefan".** *"перевіряємо, але це все робить Стефан ... Ми не дивилися самі, як він це робить ... в це ми не лізли"* ("we do check, but Stefan does all of it — we never looked ourselves at how he does it ... we did not get into that") — **R0954** | Nik asked; Sergey Cujba answered | 2026-06-16 | **64** | One inbox-placement/deliverability review the team can see, with the method documented. Marked `answered-by-Sergey in the same turn` and de-scoped by Nik (*"Якщо він цим займається, тоді поки окей"*) — an answer, not an inspection. It is the un-inspected dependency behind later inbox/campaign incidents (R0042, R0126, R0147). |
| 3 | **Single point of dependency / bus factor.** *"I do not want to be in a position where something breaks in the middle of weekend and we don't have Mykyta anywhere ... and it's on me"* — **R0443**; *"not everything is on one person. Because that was the scenario that we wanted to avoid previously"* — **R0478** | Melisa Draksler | 2026-08-14 (concern) / 2026-08-11 (ask) | **5 / 8** | Stefan onboarded, the technical document written, Melisa added to the failure-report channels — all three named in **R0478** and `open`; also **R0126** (2026-07-29, *"Please make sure that Stefan is also aware of all changes"*, `open`, still an active ask on 08-05 and 08-11). Directly contested by Sergey's position **R0444** (accept the risk, pause campaigns), so closing it needs a ruling first, not just delivery. |
| 4 | **Silent-failure class: nothing tells us when something didn't happen.** *"how do we know if she missed something like 1500 leads marked mistakenly..."* — **R0236**; *"I see a potential risk of creating systematic problems along with automations that will cause too many cycles of issue detection and resolution"* — **R0233** | Sergey Cujba | 2026-08-18 | **1** (class open since 07-16, **34 d**, R0358) | The monitoring commitment already exists — **R0141** (2026-08-04, Nik: *"I will create AUTOMATED system running on schedule to check daily weekly ... if everything is in place"*, Melisa: *"That's okay with me but you need to create documentation about the workflow and onboard Stefan on it"*). Closes when that check runs, alerts, and is seen by someone other than its author. Open members of the class: **R0084** (HeyReach batch logging), **R0121** *[CONTESTED]*, **R0510**, **R0472**, **R0162**. |
| 5 | **Change-management protocol for shared live infrastructure.** *"but you need to warn me about stuff like this"* — **R0093**; *"Неприпустимо комусь одному щось вмикати вимикати або змінювати не вирівнявшись з іншими"* — **R0190**; *"Mykyta, can you please let me know such things in advance?"* — **R0139** | Melisa Draksler + Sergey Cujba (independently, same evening) | 2026-07-17 / 2026-08-04 | **33 / 15** | R0577's rules written down and applied as a checklist (mid-week window, advance notice of the pause and its consequences, scheduled test window per R0578). The framing question **R0180** *[CONTESTED]* is `partially-answered-by-R0483` — the advance-notice principle was agreed 2026-08-05; the *"how do you communicate what you are working on"* half remains open, still unresolved at the last ingested message (**R0165**, 2026-08-18 — **53 days** after R0180). |
| 6 | **Ownership fragmentation / single admin seat.** *"I can't add you as admin as on this plan there can be only one admin / and I don't have option to transfer it"* — **R0289**; *"It seems like Melisa is an owner"* blocking a time-sensitive n8n upgrade — **R0201**; *"either i get admin access to everything outbound team uses either its again 'Hey person xyz go to yzd and ask to give blablabla'"* — **R0148** | Nik, Sergey Cujba, Melisa Draksler | 2026-07-30 / 2026-07-30 / 2026-08-04 | **20 / 20 / 15** | An access and billing-ownership map per tool with a named owner and a second seat. R0289 was resolved in the moment by Nik logging in with Melisa's credentials (*"you have my credentials"*); **R0208** (2026-08-10) is the same pattern on a Slack channel, resolved by accident (*"nah i can do it too / for some reason / but i was not able previously"*). Melisa's position on the general ask stands unanswered: *"I'm here for almost 3 years and I don't have access to everything because this is how things work in bigger companies"* (R0148). Also **R0376**: sole renewal owner, no expiry alerting. |
| 7 | **Manual LinkedIn messages don't sync — and the fix was tabled.** *"It seems like it doesn't sync messages that aren't part of a campaign (manually sent messages) - unless there is a reply after. So we still need to use Surfe"* — **R0293**; the underlying pain **R0291** (*"we have so much trouble trying to make sure that our SEs synchronize their conversations on LinkedIn with Pipedrive"*) | Melisa Draksler (definition) / Sergey Cujba (issue) | 2026-07-31 | **19** | The automation proposal **R0292** (Sergey: *"What if this is possible to automate... Like, using Claude Cowork project that is shared and regularly launched on SEs' machines ... It's not urgent, but let's discuss this on our next sync"*) is `deferred — Sergey himself tabled it; no decision found in ingested material through 2026-08-18`. Closes with a decision at a sync, either way. The adjacent defect **R0384 → R0511** (*"the lead replies were synced ... But our replies not"*) is a `recurred` sync gap on the same surface. |
| 8 | **Nik/Stefan division of labour undefined.** *"maybe it would be good to schedule another like a short call to discuss how we are going to divide tasks across you and Stefan"* — **R0477** (`open/deferred`); the concrete cost: **R0476** (messaging step never swapped, each assumed the other) and **R0494** (`OPEN`, disputed scraping ownership) | Melisa Draksler | 2026-08-11 | **8** | The call Melisa asked for, plus a filled GTM column in the shared event-support calendar (**R0395**, created 08-07, GTM column empty pending exactly this split). |
| 9 | **What "ownership" means is held differently by the parties.** *"My ownership is building and maintaining ... Guys, I'm not the manager here ... And I'm not the owner of all of the outbound processes"* — **R0493** (Nik), against **R0482/R0492** (Melisa and Sergey expect the owner to run campaigns, notice gaps, set priorities) | Nik / Melisa Draksler / Sergey Cujba | 2026-08-05 | **14** | A written scope. Note the tension the ledger itself flags: ownership was declared closed on 2026-08-14 (**R0432**) and re-opened as a reliability demand four days later (**R0238**, 2026-08-18). |
| 10 | **Repeated verbal explanation of the whole system, no artefact.** *"imagine me explaining entire lead generation infrastructure ... Every salesperson across like four or five [sessions]"* — **R0447**; *"Hopefully we will be able to do more stuff on our own without pulling your sleeve"* — **R0521** | Nik + Melisa Draksler + Sergey Cujba | 2026-08-14 | **5** | A documentation owner and a date — neither was assigned in that meeting. Standing asks: **R0141**, **R0204** (*"it is also critical to take over the ownership so Melisa doesn't need to think about whether something is done"*), **R0478**. Onboarding confusion was independently reported by two other people on 2026-06 (**R0867**, Chrissy Winkler + Rune Jensen: *"half the time I'm like, wait, which one does what again?"* — ≥50 days, no owner assigned). |
| 11 | **Cross-campaign contact collision.** *"as we will have Trigger based campaigns ... event campaigns, people will do their personal outreach ... We will need to make sure that like we are not reaching out to the same people at the same moment"* — **R0618** | Melisa Draksler | 2026-07-14 | **36** | A dedup / contact-frequency rule across trigger, event and personal campaigns. None is agreed anywhere in the corpus; the DNC workstream that was meant to gate it (**R0617**) was overtaken. |
| 12 | **LinkedIn account instability with no plan B.** *"his account is currently unpredictable because he's running campaigns from his LinkedIn ... they detect that you're using a LinkedIn account on multiple devices at the same time, they kick you out. So we should definitely have some like a plan B"* — **R0452** | Melisa Draksler | 2026-08-12 | **7** | A defined plan B before September LinkedIn outreach. Related standing constraint, still unmitigated: **R0789** (*"if you add 100 engineering managers to LinkedIn, LinkedIn will notice that you are reaching out to only one job title and they will detect this. This happened to Web Summit"*, 2026-06-29, **51 d**). |
| 13 | **Shared-proxy coupling across DICloak / LinkedHelper / HeyReach.** *"this is huge problem for us ... we need to use same proxy for DICloak, LinkedHelper and Heyreach ... so if you change this one, I need to change all of them"* — **R0080** | Melisa Draksler | 2026-07-17 | **33** | A change procedure for the shared proxy layer (which is also the coupling that made R0376's access loss a multi-tool reconnect). |
| 14 | **Capacity: events vs sprints vs BDR availability.** *"the problem around event packages is how many events we can support at the same time"* — **R0019**; *"BDRs cannot support event and Sprint and multiple people at the same time"* — **R0811**; *"we will have just one BDR during that time"* — **R0689**; *"I'm working 12 hours a day"* — **R0140**; evening-hours expectations — **R0205** | Melisa Draksler; Sergey Cujba (R0205) | 2026-06-02 → 2026-08-04 | **78 / 51 / 40 / 15 / 15** | The 2–3 month BDR-support calendar deferred at R0864/R0865 (session with Toby/Mario/Jim, not evidenced anywhere in ingested material), plus conference on-call hours — agreed in principle at **R0483** (2026-08-05) but *"no conference on-call hours were actually set here"*. |
| 15 | **Rumoured Zoho migration would invalidate the integration layer being built.** *"they started talking something about that we will switch to Zoho like in a couple of months ... most of the tools that we use don't have like integration with Zoho"* — **R0556** | Melisa Draksler + Nik | 2026-07-27 | **23** | A yes/no from Sergey/Karol. **NOT FOUND anywhere in the ingested Slack corpus** — this meeting is the only ingested mention, so treat the rumour's status as unverified rather than as a live plan. |
| 16 | **Chrissy/Jim self-serve request displacing the GTM roadmap.** *"this is something that might intervene and prevent us from moving our things forward ... this is something that is definitely going to be put as the highest priority"* — **R0748**; and Jim's uncoordinated campaigns — **R0744** (*"he runs like seven campaigns and he's not adding those people to pipedrive ... we don't have visibility"*), **R0858** | Sergey Cujba; Melisa Bahonjić (R0858) | 2026-07-03 / 2026-06-19 | **47 / 61** | An explicit priority call plus the sanctioned micro-environment Sergey floated. No owner or date was assigned in that meeting. *(R0858 is Melisa **Bahonjić**, the previous GTM role-holder — a different person from Melisa Draksler.)* |
| 17 | **One Clay account shared.** *"i have no idea why you are using one account for clay with this subscription its just not comfortable"* — **R0018** | Nik | 2026-06-02 | **78** | A seat decision. Oldest still-open concern in the register. |
| 18 | **Instruction-recall disputes have no shared record.** *"but end of the last week i did not hear this deadline ... we need to be more precise on this matter / it should be stored somewhere"* — **R0033** **[CONTESTED]** | Nik | 2026-06-29 | **51** | A written decision log. Recurs as a pattern six times (R0032/R0033, R0075, R0111, R0128, R0155, R0165) and is the audit's own reason for existing. **Not resolvable from the corpus:** R0032 states the deadline was communicated, R0033 states it was not; both meetings inside the disputed window are ingested and neither records a deadline being stated (R0824, R0800) — absence of evidence, not disproof. |

**Lower-tier open items** (recorded, no separate row): **R0262** (Nik, 07-07, *"i am more worried about number of positive replies"*, 43 d); **R0285** (Nik, 07-23, *"We need to switch from Chaos between all of them to one transparent system"*, 27 d, anticipates R0238); **R0420** (Melisa, 08-14, nurture-vs-escalation-detector interference; Melisa's interim check was declined in favour of a promised patch, 5 d); **R0467** (Melisa, 08-11, trigger-campaign due dates under-buffered; Sergey argued five focused days is realistic, no buffer added, 8 d); **R0528** (Melisa, 07-29, sales-team discipline cannot be a design dependency, 21 d); **R0570** (Melisa, 07-21, *"I really don't want to touch it"* re the Smartlead integration — the corpus shows the opposite happened by 08-04, R0143/R0144, 29 d); **R0671** / **R0813** (Melisa, one-day events and weak markets; raised, not acted on, 40 / 51 d); **R0801** (ramping reply volume, answered but never turned into a rule, 51 d); **R0853** (Melisa Bahonjić, 06-19, expectation pressure on Toby's first sprint, 61 d); **R0929** (Nik, 06-16, *"я не бачив вашої СІП [ICP], я так, по-своєму, просто вкинув"* — UK-sprint filters built without having seen the team's ICP; 64 d); **R0195** / **R0922** (vendor-dependency on Andriy; see §3b item 8 for the attribution flag).

---

## 5. Concerns raised by whom

Counts over the 62 typed `CONCERN` records. Descriptive only — this shows **who is watching which failure mode**, not who is right. Ten records have two or three raisers and are listed as joint.

| Raiser | Sole-authored | Joint | What their concerns cluster around |
|---|---|---|---|
| **Melisa Draksler** (GTM lead) | 28 | 6 | Operational blast radius and her own load: data/label integrity (R0551, R0552), platform and vendor unpredictability (R0057/R0751, R0080, R0550), sequencing and capacity (R0019, R0689, R0811, R0813), the *"they will forget"* discipline problem (R0528), and coordination-notice (R0093, R0139, R0140). She raises the most concerns and detects the most incidents. |
| **Sergey Cujba** (director) | 12 | 3 | Structural and reputational: detection and predictability (R0233, R0236, R0358), alignment on the shared toolset (R0190, R0437), external perception and vendor relationships (R0195, R0600, R0922, R0947), and outreach-copy credibility (R0900, R0904, R0905). His concerns are about the system's shape rather than any single incident. |
| **Nik** (GTM engineer) | 8 | 7 | Inputs he is missing and interference with what he builds: undocumented definitions (R0929, R0033), competing automations (R0586 — typed ISSUE, the register's longest-running vindicated warning), access and tooling (R0018, R0148), his own capacity (R0558), outcome quality (R0262, R0285), and manual-entry dependence (R0654). |
| **Melisa Bahonjić** (previous GTM role, departed ~July 2026) | 2 | — | Expectation management and coordination friction around individual stakeholders (R0853, R0858). A **different person** from Melisa Draksler. |
| **Lilla Szabo** | 1 | — | Automation correctness and reversibility (R0648) — the only concern in the corpus that asks for a human-review path. |
| **Chrissy Winkler + Rune Jensen** | — | 1 | Onboarding legibility across systems (R0867) — the only concern from outside the GTM/eng core. |
| Unidentified speaker | 1 | — | R0521 (roster suggests one of Araks Grigoryan / Lule Salihu / Melisa Draksler — **mapping unconfirmed**). |

Joint groupings: Nik+Melisa D+Sergey ×4 (R0447, R0490, R0493, R0467), Sergey+Nik ×2 (R0205, R0437), Nik+Melisa D ×2 (R0148, R0556), Melisa D+Sergey ×1 (R0801).

---

## 6. [CONTESTED] records

14 ledger records carry `status_contested: true` — conflicting extraction readings, with the newest reading applied to the `status` field and the earlier reading preserved in `update_history`. **The owner resolves these from the deliverables; they are not resolved here.** Nine appear in this register:

| id | Applied (newest) reading | Earlier reading(s) in `update_history` |
|---|---|---|
| **R0026** (§2 M5) | `recurred — post-event DNC update still outstanding on 2026-08-11 (see R0464)` (B2, evidence 08-11) | `recurred (see R0034, and R0791 - stated again in the 06-29 Sales Sprint Sync, making three occurrences inside five days)` (B8, evidence 06-29) |
| **R0034** (§2 M5) | `recurred; systemic fix stated as landing 2026-08-14 (R0416, R0418)` (B1, evidence 08-14) | (B2, 08-11) `recurred — same post-event DNC gap observed again 2026-08-11`; (B8, 06-29) `recurred (same failure mode as R0026, 4 days earlier; also stated in the same day's Sales Sprint Sync, R0791, with the manual Pipedrive-export-to-Stefan process described)` |
| **R0033** (§4 row 18) | `still open - directly contradicts R0032's claim that the deadline was communicated; ingested material does not resolve which account is correct` (B8) | Prior reading not preserved as a status entry; the second history entry (B10) adds cross-ref **R0955** — *on 2026-06-16 Nik explicitly asked Sergey to set a sprint-launch deadline and was given only "the earlier the better"* |
| **R0014** (§3a) | `stated — corrects R0013's premise` | (B8, evidence 06-29) `stated - corrects R0013's premise. Later qualified: on 06-29 Melisa asked which company value the completed company qualification actually used when a person's employer had changed (R0786) and got no answer for the already-scored table.` The applied field is the shorter of the two — the discrepancy is left as found. |
| **R0115** (§2 M5, DNC scope) | `delivered - the scoping session itself is now on record: the 2026-07-29 Melisa/Nik 1:1 enumerates the DNC source layers (R0524) and settles the sales-team intake mechanism` (B3) | (B2, 08-11) `partially-delivered; scope formalised 2026-08-11 (see R0461, R0462)`; (B5) cross-ref addition tying DNC scope to the 07-14 trigger-campaign precondition |
| **R0120** (DNC label proposal) | `accepted (verbally) 2026-07-23, then partially reversed - on 2026-08-14 the Pipedrive 'do not contact' LABEL half was ruled out (R0498, R0500) while DNC suppression itself stayed` (B3) | (B4, 07-27) `accepted - re-raised by Melisa in the 07-27 1:1 (R0542) and accepted verbally again by Nik; implementation reported 2026-08-04 (R0144)` |
| **R0121** (§2 M9, §4 row 4) | `open — recurring reply-detection gap, worked around by manual re-run` | (B4, 07-27) `open - mechanism explained in the same-day 1:1 (R0536): detection is a manual Linked Helper inbox vs Slack comparison, the failure produces no error` |
| **R0180** (§4 row 5) | `partially-answered-by-R0483 (2026-08-05) — advance-notice/coverage principle stated and mutually accepted; the wider 'how do you report what you are working on' protocol remains OPEN` (B2) | (B6, 07-10) `partially-answered 2026-07-10 ... then re-asked and deferred twice more (R0190/R0191 07-17, R0193 07-27) - still unresolved through 2026-08-18`; (B7, 07-03) `partially-answered - Sergey states the norm ... Nik agrees explicitly ... Still no channel, cadence or artefact defined`; (B10, 06-16) early-evidence note |
| **R0286** (§2 M4, the handover) | `accepted - explicitly closed at the 2026-08-14 ownership meeting (R0432)` (B1) | (B4, 07-27) `accepted-in-practice - preceded by Sergey's fuller verbal statement of the same ownership scope in the 2026-07-21 GTM team sync (R0566), where Nik accepts the transfer verbally` |

The remaining five contested records are not cited in this register: **R0009** (BDR roster / Nik's role), **R0119** (which reply categories get forwarded to sales), **R0193** (Sergey's ClickUp/reporting question), **R0273** (trigger-campaign status request), **R0276** (Nik's *"from Monday i can replace all Melissa's actions"* commitment).

---

## 7. Coverage caveats for this register

- Corpus = 5 Slack sources + 21 recorded meetings; the last ingested Slack message is **2026-08-18** and the 2026-08-19 GTM sync that several items defer to is **not** in the corpus. Every "still open" status therefore means *open as of the last ingested evidence*, not *open today*.
- **R0956–R0958 are owner corrections supplied in terminal, marked OUT-OF-CORPUS** in the ledger and never used here as in-corpus evidence. R0956 supplies the only measurement of the DNC residual gap (§4 row 1).
- Transcript speaker attribution is inferred in places (R0496/R0497/R0521 carry `mapping unconfirmed`; R0900–R0954 are `Sergey Cujba (inferred: Speaker 1)` / `Mykyta Krivosheya (inferred: Speaker 2)`). Those attributions are reproduced with their confidence markers, not upgraded.
- Meeting dates carrying `PROBABLE(calendar)` (including **R0586** and **R0577**, both 2026-07-21) are calendar-derived; lead times built on them carry that uncertainty.
- One internal inconsistency is flagged and left unresolved: **R0195**'s participant attribution (§3b item 8).
