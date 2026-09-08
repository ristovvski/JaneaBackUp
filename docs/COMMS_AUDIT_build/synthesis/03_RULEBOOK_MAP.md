# DELIVERABLE 3 — PROCESS FACTS → RULEBOOK MAP

**Source:** `COMMS_AUDIT_build/ledger.json` (937 records; Slack R0001–R0415, meeting transcripts R0416–R0955, owner corrections R0956–R0958).
**Basis:** ingested material only — dm-melisa, dm-sergey, #gtm-engineering, #infra-issues, #lead-generation-team (through 2026-08-18) and 21 meeting transcripts (2026-06-16 → 2026-08-14). Conclusions are provisional to that corpus.
**Compiled:** 2026-08-20.

## How to read this

Every line carries **quote + date + source + record id**. Lines are written as rulebook prose so they can be pasted into the rulebook as "current understanding" and still make sense standalone.

- **"stated by X"** = one person said it. That is *not* an agreed rule.
- **"agreed by X and Y"** = an AGREEMENT record, i.e. an explicit multi-party yes.
- **[MEETING-ONLY]** = the rule was stated in a meeting and appears nowhere in Slack. These are the "everyone assumes, nobody wrote it down" lines.
- **[CONTESTED]** = two people hold different versions of the same rule *concurrently*, or the ledger record carries `status_contested: true` (14 records: R0009, R0014, R0026, R0033, R0034, R0115, R0119, R0120, R0121, R0180, R0193, R0273, R0276, R0286 — conflicting extraction readings, newest applied, full history in `update_history`). Both versions are given. **The owner resolves these; no winner is picked here.**
- **[OUT-OF-CORPUS]** = owner correction supplied in terminal 2026-08-19 (R0956, R0957, R0958). Never cite as in-corpus evidence.
- Superseded rules are shown as **earlier → later + date of change**, never merged.
- Meeting-file shorthand: `file NN (topic, date)`. Speaker mapping in `02_heyreach-pipedrive-walkthrough` is **unconfirmed** for Speakers 2/3/4 (roster suggests Araks Grigoryan / Lule Salihu / Melisa Draksler); lines from that file are attributed as spoken.
- **Weekdays are only stated where independently verified** (2026-06-19 Fri · 06-29 Mon · 07-21 Tue · 08-05 **Wed** · 08-11 Tue · 08-14 Fri · 08-18 Tue). No weekday is inferred from a date anywhere in this document.
- Two Melisas: **Melisa Draksler** (GTM lead) and **Melisa Bahonjić** (previous GTM role, departed ~July 2026, owner of record on the 215 London leads — R0957, OUT-OF-CORPUS). They are never interchangeable.

---

# P1 — Label dictionary

### Current understanding

- **Labels are unified across all three Pipedrive levels (person, lead, deal).** — DECISION by Melisa Draksler, 2026-07-02, #lead-generation-team (R0339): "In collaboration with Marci and Lilla, we've introduced a new labeling system that is now unified across all three levels (person, lead, and deal)."
- **The label chain is driven off the LinkedIn-tool campaign-stage field.** Stage `invited` → label `1. Cold`. — stated by Melisa Draksler, 2026-07-03, file 15 (Melisa/Nik workflow review) (R0756): "based on this LH campaign stage in pipedrive it automatically when we have that stage invited it should assign label one quote so that we know that this person was … added because our entire reporting is based on those labels". Confirmed in Slack for LinkedIn only — stated by Melisa Draksler, 2026-07-17, dm-melisa (R0082): "btw label is changed based on lh_campaign_stage for linkedin … but i dont know for email".
- **Acceptance of a connection request sets stage `accepted`, which adds label `2. Connected`.** — stated by Melisa Draksler with Nik confirming the HeyReach equivalent (native accept webhook), 2026-07-03, file 15 (R0759).
- **The canonical stage vocabulary is: Invited, accepted, replied to invite, follow up received, replied to follow up.** — DEFINITION by Melisa Draksler, 2026-06-29, dm-melisa (R0047): "because automations are driven by lh_campaign_stage field … Invited, accepted, replied to invite, follow up received, replied to follow up".
- **On the email channel, `connected` is attached together with `replied`, because there is no "connect" event in email.** — stated by Melisa Draksler with Nik, 2026-07-17, dm-melisa (R0088): "also - for smartlead leads connected gets attached with replied … because you cant just connect in email".
- **A lead without label `1. Cold` is invisible to reporting.** — stated by Melisa Draksler, 2026-07-27, file 07 (Melisa/Nik 1:1) (R0543): "we use labels for reporting purposes. And I saw that we have bunch of leads without label 1 called [1. Cold], which means that those leads are not visible in our reports."
- **Label discipline matters because labels are the filtering mechanism; a wrong label breaks downstream systems.** — stated in file 02 (HeyReach/Pipedrive walkthrough), 2026-08-14 (R0501): "this label should not be there, okay. Because we use those labels to filter out stuff and it also interferes with the literature system." ("literature system" is most plausibly a transcription of *nurture* system; not asserted.)
- **A deal is created only when a meeting is qualified.** — DEFINITION by Melisa Draksler with Nik, 2026-08-18, dm-melisa (R0164).
- **Meeting-label diagnosis rule:** if there is a voicenote in the Ai4 channel about a meeting, a missing meeting label is Slava's miss; if there is no voicenote, the meeting probably happened after the event and the sales person forgot to update. — DEFINITION by Melisa Draksler, 2026-08-18, dm-melisa (R0164): "If there is a voicenote in ai4 channel about meeting, then it's Slava's mistake / If there is no voicenote, meeting probably happened after event so sales person forgot to update".
- **Self-driven / salesperson-run campaigns must land in Pipedrive as *personal outreach*, never as cold outreach.** — stated by Melisa Draksler, 2026-07-03, file 14 (team sync) (R0745). [MEETING-ONLY]
- **Cold-outreach source channel is expected on BOTH the lead and the person level.** — stated by Melisa Draksler, 2026-07-03, file 15 (R0756): "it should be like a signed source channel called outreach. And ideally also on the personal level it also should be like cold outreach". [MEETING-ONLY]
- **The bracketed prefix in a campaign name is what is written to Pipedrive as the Marketing Hypothesis.** — stated by Melisa Draksler, 2026-06-29, file 16 (lead-scoring sprint planning) (R0792): "you could see in the name of each campaign that we have something in brackets and this is what it's being sent to pipedrive as the marketing hypothesis".
- **Campaign-name convention (sales sprint), verbatim example:** `[Sales Sprint] Sales Sprint 2026 – London – Valids` / `… – Catch-alls`. — stated by Melisa Draksler, 2026-06-29, dm-melisa (R0039).
- **Campaign-name convention (events), two-bracket form:** `[Events Visiting] [Event name Year] - Name(s) of sender(s) - Linkedin`, with the second bracket carrying the event name exactly as it must appear in reports. — DECISION stated by Nik, 2026-07-21, dm-melisa (R0112). **Note: no explicit confirmation from Melisa on this structure is present in ingested material.**
- **The Event Name field must always be filled and spelled canonically** — one spelling per event, or Lilla's dashboard breaks. — stated by Melisa Draksler, 2026-07-02, #lead-generation-team (R0340): "It cannot happen that one lead is labeled as \"HumanX 2026\", another as \"HumanX - 2026\", another as \"HumanX 26\" … otherwise, Lilla's dashboard and reporting will break." Violated and repaired 2026-08-06: 372 Ai4 leads had no Event name (R0389), root-caused to a 2025 bulk edit's inconsistent spelling; ~373 records fixed; **~2,000 older 2025-era gaps explicitly left out of scope pending a separate decision** (R0149).
- **When clearing outdated tasks, next scan dates and lead-nurturing labels are deleted together.** — DECISION by Melisa Draksler, 2026-06-23, #lead-generation-team (R0325).
- **The Pipedrive `do not contact` LABEL is not the same thing as DNC-list membership.** See P6 — the label rule is contested there.

### Superseded / historical

- **Automatic `1. Cold` labeling → manual labeling (change ~April 2026).** Earlier: labels were added automatically off stage changes (R0756, R0047). Later: "they used to have label 1.cold but something went off so for the last 3-4montjs we update it manually" — Melisa Draksler, 2026-07-20, dm-melisa (R0106). Melisa frames this as previously communicated ("yes, I told you that right now we need to update them manually?"); the same manual gap is restated in-meeting on 2026-07-03 (R0756) and 2026-07-27 (R0543).
- **Labels overwritten by a second live automation (07-21) → root-caused (08-11).** Earlier reading: "another automation rewrites mine and I don't want. I can't change anything that you are running right now" — Nik, 2026-07-21, file 08 (R0586). Later, dated root cause: old Zapier automations were silently wiping `3. Responded` / `4. Positive Reply` on person-field updates; 11 leads affected since Aug 5, all restored — Nik, 2026-08-11, #infra-issues (R0218).

### Contested

- **[CONTESTED] Pipedrive `do not contact` label — narrow vs broad.** Narrow: "this label is supposed to be only added when leads respond to us. Do not contact me unsubscribe … This is the only part where they should be" (file 02, 2026-08-14, R0498). Broad, minutes earlier in the same call: "We had do not contact list for people who we contacted via campaigns. Right. We had agreed on it" — Nik (R0499). Settled *for the label only* the same day: AGREEMENT — the label is removed from the bulk-labelled population while the DNC-active property stays (R0500). The narrow version prevailed in the room; the broad version was Nik's stated prior understanding, accepted verbally in Slack on 2026-07-23 (R0120).
- **[CONTESTED, ledger flag] R0120** (2026-07-23, Melisa: "can we also send leads with DO NOT CONTACT to Pipedrive and add label Do not contact? but not send notification in Slack?") — accepted verbally, then partially reversed 2026-08-14 (R0498/R0500). Two extraction readings on record.

### Not answered by the corpus

1. What is the **complete label list** with definitions (`1. Cold`, `2. Connected`, `3. Responded`, `4. Positive Reply`, `5. Meeting`, `Lead Nurturing`, `Do not contact`, …)? No single enumeration exists anywhere in ingested material.
2. **Who adds the meeting label, and on what trigger** (voicenote posted? meeting marked in Pipedrive? deal created?) — R0164 gives only the *diagnosis* rule, not the assignment rule.
3. On the **email channel, which automation sets which label** — Melisa explicitly did not know: "but i dont know for email" (R0082).
4. Is a label ever **removed**, or are labels cumulative? Nothing in the corpus states a removal rule (the only removals on record were defects — R0218, R0496).
5. What happens to the **~2,000 pre-2026 records with no Event name** (R0149) — in scope or permanently out?

---

# P2 — Entity lifecycle

### Current understanding

- **The campaign-stage field is the pivot of the whole integration.** Label automation and Slack notifications both key off stage transitions. — stated by Melisa Draksler, 2026-06-25, file 18 (team sync with Nik) (R0828): "after every step we are changing LH campaign stage from invited to accepted to replied … That's like the most important part of integration". [MEETING-ONLY]
- **Reply-check gating:** before each automated message the tool checks for an existing reply. A reply to the invite sets `replied to invite` and suppresses the follow-up; otherwise the follow-up sends and the stage becomes `first follow up`; a reply to a follow-up stops the sequence. — stated by Melisa Draksler with Nik, 2026-07-03, file 15 (R0761). [MEETING-ONLY]
- **Lead ownership moves off Melisa on reply.** She owns only still-cold leads, which is what makes `owner` a usable filter for separating GTM leads from the memory team's. — stated by Melisa Draksler, 2026-07-27, file 07 (R0555): "I'm not the owner. Like when we get reply, I'm no longer owner. I'm just owner for the ones who are still called [cold]". [MEETING-ONLY]
- **On conversion to a deal, the sales person changes the BDR owner to Melisa** so existing reports do not break. — stated by Melisa Draksler, 2026-06-22, #lead-generation-team (R0323).
- **Lead value is set by the sales executive after the meeting happens.** — stated by Melisa Draksler, 2026-07-03, file 14 (R0726). [MEETING-ONLY]
- **Disqualification rule:** if you are sure a lead is not relevant, disqualify immediately; if in doubt, discuss in the chat. — stated by Sergey Cujba, 2026-06-05, #lead-generation-team (R0310).
- **Outdated-task handling:** if there is no visible evidence the outdated task was completed, add a note in the spreadsheet describing what the Sales Executive should do; if the lead is disqualified / not interested / archived, simply close the task. — stated by Melisa Draksler, 2026-06-03, #lead-generation-team (R0308).
- **A new lead is created for every new connection request, even for a person contacted in an earlier campaign, and the campaign-name field is always changed.** — DECISION by Melisa Draksler, 2026-07-20, dm-melisa (R0107).
- **One campaign per person.** Two campaigns for the same person re-create leads and corrupt reports. — DECISION by Melisa Draksler, 2026-07-17, dm-melisa (R0096): "Lets just go with one campaign per person".
- **HeyReach lead states (definition arrived at collaboratively, not pre-documented):** `pending` = person is not in the campaign right now, no sequence steps sent (i.e. connection request sent); a reply marks the lead `finished`. — file 02, 2026-08-14 (R0506).
- **To take a lead out of a running HeyReach campaign you PAUSE, not remove;** pausing cancels the lead's un-executed steps. — file 02, 2026-08-14 (R0507): "So it's called pause and not remove."

### Superseded / historical

- None demonstrably changed within the corpus for this part.

### Not answered by the corpus

1. The **authoritative state machine**: which stage values exist on the HeyReach path (the vocabulary in R0047 is LinkedHelper's), and what each maps to in Pipedrive.
2. **Archive vs disqualify vs "not interested"** — three terms are used (R0308, R0310, R0593) with no definitions and no statement of which is terminal.
3. Who sets **lead value**, on what scale, and by when — R0726 says the sales executive after the meeting; R0379 shows BDRs already tiering follow-ups by "high / medium / low value" with no defined bands.
4. What is the lifecycle of a lead that **replies but never accepts** (R0345 says it is never updated in Slack/Pipedrive) — is there a state for it at all?
5. Does the lead **ever return to cold**, e.g. after the 6-month DNC TTL expires (R0144/R0594)?

---

# P3 — Creation paths

### Current understanding

- **Surfe is the sanctioned lead-creation path for sales people**, because its field mapping is pre-set; manual creation and CSV import are the paths that produce unusable records. — stated by Melisa Draksler, 2026-07-21, file 08 (Nik/Melisa/Sergey sync) (R0591): "I managed to somehow bypass this problem by introducing Surf[e] … But if they create manually or if they import the list then we have problem". [MEETING-ONLY]
- **The creating account does not identify the owner.** Melisa creates leads on a salesperson's behalf, and Slava creates leads manually (e.g. introductions). — stated by Melisa Draksler, 2026-08-14, file 01 (DNC & migration sync) (R0426).
- **Sending the connection request is itself the Pipedrive creation event**, and the Pipedrive automations are bound to Melisa's personal Pipedrive account, so she becomes lead owner and person owner by default. Melisa flagged that a new integration would most likely also run on her API key and explicitly left the choice to Nik. — stated by Melisa Draksler, 2026-07-03, file 15 (R0753). [MEETING-ONLY]
- **LinkedIn add-list gate:** a Clay text field "Are we adding to Linkedin?" = Yes controls who is added to LinkedIn campaigns. — stated by Nik, 2026-07-17, dm-melisa (R0094); the shared list is the artefact of record (R0260, 2026-07-06, where a mistaken accusation was retracted after Nik showed it).
- **Sourcing pipeline order of operations (people table, as built 2026-06-16):** People-DNC check → domain lookup into the companies table → Relevant/Irrelevant verdict (competitor or government-related = irrelevant) → title qualification. People-DNC and company-DNC are **separate checks in the same pipeline**. — stated by Nik, 2026-06-16, file 21 (R0934).
- **Company deduplication by normalised URL** exists to avoid paying twice for enrichment, not to dedupe leads. — stated by Nik, 2026-06-16, file 21 (R0913).
- **Intended funnel shape:** deliberately wide title filter at the top, then an LLM leader-relevance layer over the LinkedIn profile, keeping roughly 10–20%. — stated by Sergey Cujba, 2026-06-16, file 21 (R0932).
- **Trigger-based campaign, definition that prevailed:** an evergreen campaign continuously topped up with newly-qualifying contacts (e.g. people under 3 months in a target title) — distinct from signal monitoring on an existing list. — DEFINITION by Melisa Draksler, 2026-07-29, file 06 (R0532). The two men had been describing different things for several minutes before this was separated.
- **Design constraint on trigger campaigns:** signal originality and monthly volume trade off; only generic signals (funding rounds, open job posts) reach thousands of contacts per month. — stated by Melisa Draksler, 2026-07-14, file 10 (R0598).
- **ICP scoring must be reachable ad hoc by an individual salesperson** for a company out of their own network, not only as a batch enrichment path — this is what rules out a Clay-only, list-driven implementation. — stated by Lilla Szabo, 2026-07-10, file 11 (R0643).
- **Precedent build (manual):** the "newly hired heads of AI" campaign was built by exporting 6-month job-change data, filtering to relevant titles, enriching, then splitting messaging by promoted vs joined-a-new-company. — stated by Melisa Draksler, 2026-07-10, file 12 (R0678).

### Superseded / historical

- **Company-level DNC removal at the top of the sourcing table (as built 06-16) → person-level filtering (Sergey's ruling, same call).** See the P6 chain — the mechanic lives in P3 (R0914 → R0916), the rule lives in P6.

### Not answered by the corpus

1. **Which Pipedrive account / API key** should own automation-created leads and persons going forward — Melisa explicitly left it open ("this is up to you also to investigate and propose your solution", R0753).
2. Is there a **notification or fallback when a manually-created contact cannot be processed** (no LinkedIn URL)? Melisa asked exactly this on 2026-08-14 and got no mechanism, only a design step (R0425).
3. What is the **required-field contract at creation time** for each path (Surfe / manual / CSV / automation)? Melisa's field set (R0544) is a list, not a validated contract.
4. Who owns **campaign content** for trigger campaigns (Nik / Melisa / Sergey)? Asked by Sergey 2026-07-10 and not answered: "honestly I don't know who is going to own what in these situations" (R0663).

---

# P4 — Replies / alerts

### Current understanding

- **Only specific reply categories are forwarded to sales.** The set is deliberately narrow so automated replies, unsubscribes and out-of-office never reach Slack. — DEFINITION by Melisa Draksler, 2026-07-21, file 08 (R0579). **The category count is contested — see below.**
- **A reply we are unsure how to categorise is forwarded to Melisa.** — DEFINITION, Nik asking / Melisa Draksler answering, 2026-07-29, dm-melisa (R0127): "it should be forwarded to me".
- **A single missed forward is a full-funnel failure.** — stated by Melisa Draksler, 2026-07-21, file 08 (R0581): "if it's not forwarded to Noah, Noah will not respond. BDRs are not going to have notifications, [S]lava will not create ClickUp tasks for them and everything breaks. We have lead that we will not respond to". [MEETING-ONLY]
- **Reply classification now runs in-house (n8n), not on Smartlead's built-in AI.** Confident replies are forwarded to the owner automatically; uncertain ones are routed to Melisa for a decision. — stated by Nik, 2026-08-04, dm-melisa (R0143); design intent stated 2026-07-29, file 06 (R0522); proposal accepted in principle by Melisa 2026-07-27 with the explicit ranking "of course we want to improve it … but it's not that huge issue" (R0540).
- **Outbound messaging is logged as a Pipedrive activity on the PERSON record** (not the lead); LinkedHelper and GetSales both did this and the requirement is tool-independent. — stated by Melisa Draksler with Nik, 2026-07-03, file 15 (R0760); same rule stated in Slack 2026-06-29 (R0049: "messaging needs to be sent as activity to pipedrive record").
- **Email replies sent from Smartlead auto-sync into Pipedrive as activities, including BDR replies to a lead's reply.** — stated by Nik, 2026-07-31, #gtm-engineering (R0294).
- **HeyReach's automatic LinkedIn→Pipedrive sync covers campaign messages with a reply only.** Manual out-of-campaign messages still require Surfe. — DEFINITION by Melisa Draksler, 2026-07-31, #gtm-engineering (R0293).
- **Contacts who reply but never accept the connection request are NOT updated in Slack/Pipedrive** — a known gap requiring a manual inbox check. — stated by Melisa Draksler, 2026-07-06, #lead-generation-team (R0345).
- **If you open a message directly from a LinkedIn profile, mark it unread** so the SE does not miss it. — DECISION by Sergey Cujba, 2026-07-16, #lead-generation-team (R0360); Lule confirmed the same day she had not known the option existed.
- **Replies from a colleague inside a lead's email thread must not be misattributed or alerted on.** — stated by Nik as delivered 2026-08-13, file 01, 2026-08-14 (R0417): "We don't want to get notifications for such cases". No independent confirmation of the fix in ingested material.
- **Smartlead's own delivery of sent-events is not trusted:** a platform bug (sent-events not delivered to second subscriptions, proven with 4 tests) is worked around by a polling fallback. — stated by Nik, 2026-08-04, dm-melisa (R0136).
- **A DNC-flagged lead who writes to us first is answered normally.** — AGREEMENT, Nik and Melisa Draksler, 2026-08-14, dm-melisa (R0159): "DNC protects them from our cold outreach, not from conversation … yes, and we don't need notification about that".

### Superseded / historical

- **Smartlead native auto-labelling (until ~2026-08-04) → in-house n8n classifier.** Earlier: Smartlead's built-in AI, ~10% miscategorised ("wrong person" class) → email not forwarded, no Slack, lead lost (R0143, quoting the prior state; the ~10% figure was stated by Melisa on 2026-07-21, R0580). Later: own classifier with full context, confident→auto-forward, uncertain→Melisa (R0143, 2026-08-04).
- **Reply notifications via legacy Zapier (until 2026-08-05 13:28) → direct posting to #lead-processing (2026-08-11).** The old Zap was switched off as part of shutting down the legacy stack; it turned out to be the only thing posting reply notifications to the team channel, "so from Aug 5 the channel went dark" — Nik, 2026-08-11, #infra-issues (R0215).
- **Detection of a silently-failed reply notification: manual inbox-vs-Slack comparison (07-27) → automated self-check on campaign activity (08-11), still not covering Pipedrive.** Earlier: "usually I open Toby's profile in Linked Helper so I can see entire inbox and I check for replies … I didn't have any error message or anything" — Melisa Draksler, 2026-07-27, file 07 (R0536). Later: see P12 (R0475).

### Contested

- **[CONTESTED] How many reply categories are forwarded — three or four.** Four, in Slack: "is this the exact set of categories that get forwarded to sales: Interested, Meeting Request, Not Interested, Information Request? / yes" — Melisa Draksler, 2026-07-23, dm-melisa (R0119; ledger `status_contested: true`). Three, in meetings, both before and after: "interested, not interested information request" (2026-07-21, file 08, R0579) and "only three categories are being forwarded" (2026-07-27, file 07, R0539). Two meeting statements say three, one Slack statement says four. **Unresolved.**
- **[CONTESTED] Can email replies be logged as Pipedrive activities?** No: "Emails are not being. It's not possible to. To put them in pipedrive … because we have like 500 mailboxes and we cannot be. You can only connect two mailboxes to Pipedrive per person" — Melisa Draksler, 2026-07-21, file 08 (R0584). Yes: "Pipedrive allows to log messages. I am logging them right now via API … it doesn't matter if it's going to be smartly or not" — Nik, same meeting (R0585). Melisa's reply: "You can check it, but we couldn't find like maybe something has changed because we worked on that like a year ago." Nik parked it in his backlog; nothing in the corpus settles it.
- **[CONTESTED, ledger flag] R0121** (2026-07-27, reply received for Toby with no Slack notification, "it was not an error, it was in the 'successfully processed' bucket") — two extraction readings; the silent-failure class recurs on HeyReach (R0212, R0510).

### Not answered by the corpus

1. **The definitive forwarded-category list** (three or four) and the exact name of each category as it must be set in the tool.
2. Do **Smartlead-side category labels survive the n8n cutover**? Melisa asked (R0541, 2026-07-27) because she filters on that field, which is also "the trigger for forwarding"; Nik answered "Yes, why not?" then immediately qualified "I need to check … documentation". No confirmation exists.
3. Does HeyReach **emit reply webhooks while a campaign is paused**? Answered at 90% confidence and explicitly unverified (R0509), and contradicted by observed behaviour (R0510, campaigns paused by Stefan → no reply notifications).
4. **Are our own outbound LinkedIn messages synced to Pipedrive, and will history be backfilled?** Defect re-confirmed 2026-08-14 (R0511), patch + backfill promised with feasibility explicitly unconfirmed (R0512), no confirmation in corpus.
5. What is the **acceptable classifier error rate**, and who reviews the "uncertain" queue when Melisa is away?

---

# P5 — Meetings / events

### Current understanding

- **Messaging is changed for every single event**, because the same people attend multiple events. — stated by Melisa Draksler, 2026-05-29, dm-melisa (R0002).
- **Event support tiers exist and are described by worked example**: either the sales executive manages replies themselves, or a BDR handles replies (precedents: Sergey's sales sprint; Jim at TechEx North America). BDR support is described as "fairly new". — stated by Sergey Cujba, 2026-06 (weak date; anchor unmatched), file 20 (Ai4 events planning) (R0863).
- **BDR capacity ceiling: one event per BDR** — flagged as an estimate by both people who stated it. Melisa Draksler, 2026-06-02, dm-melisa (R0010): "for BDR support we can only handle one event per BDR but for basic package (just launching campaigns) … probably 2-3 at the same time?"; independently Sergey Cujba, 2026-06, file 20 (R0864): "right now the estimate is that we might only have one BDR support, one sales executive for one conference".
- **Conference intake process:** sales-exec form → ClickUp task → statuses `interested` / `awaiting approval` / `approved`; approver is Toby; the workflow is meant to notify everyone involved in preparation. — stated by Sergey Cujba, 2026-06, file 20 (R0861). Sergey flagged his own uncertainty on where the form lives and on Melisa's co-authorship.
- **A shared calendar now tracks approved events with assigned BDR(s) and the responsible GTM engineer.** — stated by Melisa Draksler, 2026-08-07, #lead-generation-team (R0395). The Mykyta/Stefan split the GTM-Support column depends on was explicitly still unresolved at that date.
- **One GTM engineer owns an event campaign end to end** — setup, re-scraping, attendee list, messaging updates on schedule — while Melisa retains contact filtering and channel assignment. — DECISION stated by Melisa Draksler and confirmed by Sergey Cujba, 2026-08-14, file 01 (R0434, with the ownership boundary at R0433).
- **Campaign start is gated on networking-app access**, giving a one-to-two-week runway rather than a fixed lead time. — stated by Sergey Cujba, 2026-06, file 20 (R0862); restated for Ai4: "we will get access to the networking application around two or three weeks before the event" — Melisa Draksler, 2026-07-03, file 14 (R0727).
- **Attendee lists must be re-scraped 4–5 times before an event.** — stated by Melisa Draksler, 2026-07-21, file 08 (R0572).
- **Event campaigns are split per attending sales executive and per channel.** For Ai4 (Rune + Mario): four campaigns — two email, two LinkedIn. — stated by Melisa Draksler, 2026-07-03, file 15 (R0752).
- **Post-reply event research:** on a reply, Slava puts the person into the AI research table; everything is scraped and an AI summary is written into the Pipedrive record so the salesperson can prepare. — stated by Melisa Draksler, 2026-06-01, dm-melisa (R0003).
- **Sales sprint ≠ event outreach.** A sprint's hypothesis is "Sales sprint" and sprints have no Event Name field, because a sprint is not an event. — DEFINITION by Melisa Draksler, 2026-07-20, dm-melisa (R0100).
- **Sprint definition (working):** a sprint means travelling meaningfully beyond one's own city, and the term is internal only — prospects only ever see an in-person visit offer. — DEFINITION, Nik and Melisa Draksler, 2026-06-29, file 16 (R0812).
- **Sprint judging baseline:** bookings arrive close to the on-the-ground dates, so a near-empty day-one schedule is normal; ~7 meetings is the acceptable floor, 14–16 was achieved in Germany. — stated by Sergey Cujba, 2026-06-29, file 16 (R0808). Per-person on-site ceiling: 7–10 (realistically 8–10) quality meetings per day — Sergey, file 20 (R0872).
- **Tier-1 conference access has largely closed.** Most Tier-1 conferences are internally blacklisted; the remainder withhold attendee lists or prohibit unsolicited outreach unless the company sponsors — the stated rationale for moving to Tier-2. — stated by Sergey Cujba, 2026-07-10, file 12 (R0669). Access to networking apps at Microsoft/Nvidia-class events closed at the end of 2025 (R0873).
- **Support tier must match what is actually deliverable at the event.** Example: QCon approved with platinum support, but no attendee list and no cold outreach allowed → set to Silver (speakers only), BDR support off, pending alignment with Chrissy and Jim. — ISSUE/decision by Melisa Draksler, 2026-08-07, #lead-generation-team (R0396) — **still open**.
- **Event/DNC cross-check workaround:** a Clay view cross-references event attendees against team connections; the list is exported manually and sent to the attending salesperson. Cold outreach is suppressed; personal outreach is the salesperson's call. Done for Ai4. — stated by Melisa Draksler, 2026-07-29, file 06 (R0530).

### Superseded / historical

- **Ai4 as a single-attendee event → two attendees.** "Mario had already tapped that one … And now we've decided to send a couple of people. So Runa is also going to join" — because the previous edition was overwhelming for one person (file 20, R0869). Ai4 2026: Las Vegas, Aug 4–6, ~400 speakers.

### Contested

- No concurrent two-person disagreement isolated for this part. Note the **capacity figures are estimates by two people who both said so** (R0010, R0864) — record them as estimates, not as a rule.

### Not answered by the corpus

1. What exactly does each **support tier (basic / silver / gold / platinum)** include and exclude? Only worked examples exist (R0863, R0396), never a definition.
2. **Who decides the support tier**, and can it be downgraded after approval (as Melisa did unilaterally for QCon, R0396)?
3 **How is event capacity allocated across sales executives' mailboxes and LinkedIn accounts** when several events overlap? Asked by Melisa 2026-08-12 and left OPEN — "no decisions to make right now" (R0450).
4. What is the **minimum runway** below which a campaign is not launched at all? R0862/R0870 both flag "tight" with no rule attached.
5. Is the **AI-research-summary step** mandatory for every event reply, and who does it now that ownership moved (R0003 assigns it to Slava)?

---

# P6 — DNC (do not contact)

### Current understanding

- **[OUT-OF-CORPUS] The current system matches on LinkedIn OR email.** The residual gap is persons with **neither** identifier — 1,019 as of 2026-08-19, a figure that will move as enrichment lands; the enrichment fix is in flight. — owner correction, Nik, terminal, 2026-08-19 (R0956). *Supplied by the owner, not a Slack or transcript quote — never cite as in-corpus evidence.*
- **DNC is a universal post-outreach suppression list**, applied to every contacted lead; it is not a signal about lead quality, conduct, or BDR process. — DEFINITION by Melisa Draksler, 2026-08-14, #lead-generation-team (R0407): "Every lead is being added to DNC so that we don't reach out to them with new cold outreach campaign again but this does not have to do anything with your process."
- **Broadest stated scope:** not only people who said "do not contact me", but also everyone who responded and everyone who had a meeting with us — because they will be followed up via BDRs / lead nurturing / personally instead. — DEFINITION by Melisa Draksler, 2026-08-11, file 04 (DNC alignment) (R0456).
- **Any campaign reply puts the person on the DNC list for campaign outreach; the follow-up decision (nurture vs disqualify-and-archive) stays human.** — **AGREEMENT, Nik and Melisa Draksler**, 2026-07-21, file 08 (R0593).
- **Only repliers/accepters enter the registry — not everyone who merely received a connection request.** — DECISION by Melisa Draksler, acknowledged by Nik, 2026-08-14, file 01 (R0424): "you are going to add only the ones who … replied or accepted … the most important part is just to capture the ones who replied".
- **DNC source layers (scope agreed in the 07-29 1:1):** (1) team LinkedIn connections, (2) HeyReach outreach, (3) Smartlead outreach, (4) manual/Surfe outreach, plus (5) competitor companies auto-flagged by the Clay AI categorisation, deduplicated across sources. — stated by Nik with Melisa Draksler, 2026-07-29, file 06 (R0524). This is the scoping deliverable promised in Slack on 2026-07-21 (R0115).
- **Reply-based DNC entries carry a 6-month TTL, and offboarding removes a leaver's connections in one action.** — proposal by Melisa Draksler, 2026-07-21, file 08 (R0594: "after one year or six months … if they change company like maybe it makes sense to reactivate them"), shipped at the shorter end per Nik, 2026-08-04, dm-melisa (R0144).
- **Enforcement mechanism:** the blocked population lives in an n8n data table and campaign sending excludes it. — stated by Nik, 2026-08-11, file 04 (R0463): "I have everybody who is in not contact lists in data table in item [n8n]. So basically we don't reach out to those people." Registry live at ~2,200 blocked people on 2026-08-14, with Surfe-created leads auto-blocked (R0416). **Nik stated on the record that the provenance of those 2,200 entries is not reconstructable: "Honestly I can't answer from where I took them".**
- **An escalation detector alerts if anyone in the registry appears in a live campaign — alert only, it does not block or remove.** — stated by Nik, 2026-08-14, file 01 (R0419).
- **Domain-level exclusions are a separate layer and stay:** non-profit, government-related and university domains are excluded before enrichment. — **AGREEMENT, Sergey Cujba and Nik**, 2026-06-16, file 21 (R0919), mechanism at R0915. This layer is explicitly independent of the person-level narrowing.
- **The only automatic DNC *write* in the sourcing table is competitor-driven:** classification = Competitor drops the company into the competitors list. — stated by Nik, 2026-06-16, file 21 (R0924).
- **DNC suppression does not block conversation.** If a DNC-flagged lead writes to us, the team replies normally and no notification is needed. — AGREEMENT, Nik and Melisa Draksler, 2026-08-14, dm-melisa (R0159).
- **Lead-nurturing carve-out:** DNC-listed people must NOT be unsubscribed in Smartlead, because nurture runs through Smartlead on the sales executives' real mailboxes. — DEFINITION, Nik and Melisa Draksler, 2026-08-12, dm-melisa (R0160): "OH but wait- they are not unsubcribed in smartlead because we run lead nurturing via smartlead".
- **Phase split:** DNC phase 1 covers the existing internal/CRM processes only; salespeople's own-tool outreach is deferred to phase 2, and in the interim the sales team is told marking disqualify / do-not-contact in Pipedrive is their own responsibility. — DECISION by Sergey Cujba, 2026-08-11, file 04 (R0461); closing procedure agreed three-party (Melisa supplies 3–4 scenarios, Nik implements, result presented to the whole team) — AGREEMENT (R0462).

### 2026-08-26 addendum — final DNC definition ruling (post-corpus, not an R#### citation)

The registry drifted past the 2026-08-11 "broadest stated scope" bullet above (contacted-but-
never-replied entries, via S4/event_contacted, entered as if contact alone were sufficient).
Melisa's ruling, 2026-08-26, `#niks-channel` (this session, not the ingested corpus — cited
plainly rather than with a fabricated R#### code):

> "Our pool of potential customers is limited; real case — Ai4 last-year non-responders were
> re-contacted this year and some replied. Event contact must not block re-approach; only a
> RESPONSE creates a relationship worth protecting." — Melisa Draksler, 2026-08-26

**Final DNC definition (supersedes the 2026-08-11 "broadest stated scope" bullet where they
conflict): replied + meetings + sales-created/Surfe + ALL imported connections + explicit
opt-outs. Nothing contact-only.**

- "ALL imported connections" is deliberate, not a narrowing: Melisa's explicit ruling, same
  thread, confirmed the 24,201-row `employee_connection/manual_offboard_eligible` bucket (the
  bulk 2026-08-07 seed import, one sub-population per sales rep — Jim, Toby, Mario, Noah
  Keimach, Rune, Mario Stalder, Matt Carothers, Benedetto, Mike CEO, Sergey Cujba, + smaller)
  stays protected in full: **"all connections are in DNC" — no depth filtering.**
- Removed under this ruling, 2026-08-26 (tombstoned, `removed_reason:
  rule_change_2026-08-26_melisa`, reversible): 7,138 `event_contacted`-only rows (S4) + 348
  `manual_sheet` legacy-import rows with no reply/meeting/sales-relationship evidence = 7,486
  total. Full recon, classification, and per-class counts: `DNC_OBS_P1_build/task-logs/
  2026-08-26_registry-compliance-audit.md` and `2026-08-26_s4-retirement.md` (repo:
  `Нова папка/task-logs/`).
- Open, separate thread (not part of this ruling): ~324 archived-and-responded leads Melisa
  flagged as an S1 blind spot (Pipedrive list/filter reads are archived-blind, verified live) —
  pending a UI export before they can be added. See `2026-08-26_archived-responders.md`.

### Superseded / historical — the person-level vs company-level chain

This chain is worth laying out in full because the same rule was stated, dropped, re-derived, scoped and only then enforced.

1. **2026-06-16 — as built, company-level.** "if I see the company is on the list, we remove it right away. It is all in a formula" — Nik, file 21 (R0914). Nik's account is that company-level exclusion was the pre-existing team logic he had reproduced: "then the logic needs to be re-shared, because the one you had before was like that" (R0917).
2. **2026-06-16 — Sergey rules for person level.** "sometimes it is better for us to do do-not-contact at person level … a company being on the do-not-contact list does not automatically mean we do not want to reach people from that company … if there is a notional Microsoft, there are thousands of people in Microsoft … we want to filter out only the people" — DECISION by Sergey Cujba, file 21 (R0916). **Status: a stated preference, explicitly pending confirmation from Melisa.**
3. **2026-06-16 — Sergey commits to confirm with Melisa.** "this will need to be clarified with Melisa … but a shame, Melisa will only be back day after tomorrow" (R0918). **No evidence anywhere in ingested material that he did.** Effectively dropped for ~6 weeks.
4. **2026-07-29 — Melisa re-derives the same rule independently**, from the Microsoft Build case: "we had this case where we put Microsoft and Merck on the not contact list like on a domain level. And then … where like 60% of attendees are Microsoft people. Like I realized that that was bad idea … it makes sense only to maybe exclude them on a profile level, not on a company level." She adds the size-dependent refinement: domain level is still right for small client companies (<100 employees, where we are connected with the most important people) — DECISION, file 06 (R0529).
5. **2026-08-11 — formally scoped** into phase 1 / phase 2 with an agreed closing procedure (R0456, R0461, R0462).
6. **2026-08-14 — enforced only after the incident.** "I just realized that label do not contact was added to 2000 leads in Pipedrive … you added to existing leads that are in different stages … and the problem is that other labels that we had for some leads disappeared" (R0496); settled the same day by removing the label while keeping DNC suppression (R0500), with an automated reversal pass run by Nik.

**Also superseded:**

- **DNC matching on LinkedIn-URL only (2026-07-10) → LinkedIn OR email (current).** Earlier, and stated as a known gap: "we have some leads added by the sales team that don't have any. They only have maybe first name, last name and company name. They don't have LinkedIn URL … we realized that we are actually not putting people on the not contact list if they don't have LinkedIn a profile" — file 12, 2026-07-10 (R0680), with the remedy proposed as export → Clay enrichment → DNC (R0681). Later: **[OUT-OF-CORPUS]** matching on LinkedIn OR email, residual gap = neither identifier, 1,019 persons as of 2026-08-19 (R0956). **The 07-10 understanding is HISTORICAL, not wrong-at-the-time — keep both.**
- **Manual DNC maintenance (pre-automation) → automated registry.** Earlier: Melisa exported Surfe-created contacts monthly/fortnightly and sent them to Stefan to load into the Clay DNC list, plus a connections export requested from every new sales hire — stated by Melisa Draksler, 2026-07-29, file 06 (R0525). Nik was unaware of the two-year-old Surfe creation path until that conversation. Later: automated registry with auto-block on Surfe creation (R0416, 2026-08-14).
- **"DNC list before trigger campaigns" (2026-07-14) → parallelisation asked for by the same person (2026-07-23).** Earlier: "maybe before we move to this stage we need to deal with the do not contact regularly updated list … So we build this first and then move to the Trigger campaigns" — Sergey Cujba, file 10, with Melisa's assent "We can do it actually. Yeah." (R0617). Later, nine days on, Sergey himself asks "if it's possible to parallelize these items" (R0273, 2026-07-23) — and in the observed sequence the trigger-campaign hypothesis list, effort estimates and voting all proceeded first (R0272, R0275, R0290) while DNC scope-gathering was still being opened as fresh work on 07-21 (R0115).

### Contested

- **[CONTESTED] Pipedrive `do not contact` LABEL scope** — narrow (repliers who asked never to be contacted) vs broad (everyone we contacted via campaigns). Both in file 02, 2026-08-14, minutes apart: R0498 vs R0499; label question settled by R0500, list question not. See P1.
- **[CONTESTED] How many DNC lists exist — three or four.** "we have like four do not contact lists. We have do not contact list based on company domains, based on emails and based on LinkedIn profile" — Melisa Draksler, 2026-06-29, file 16 (R0790). She says four and enumerates three. Unresolved.
- **[CONTESTED, ledger flags] R0026 / R0034** — the recurring "I forgot to update the DNC after an event" failure (2026-06-25 and 06-29, third occurrence 06-29 in file 16 at R0791), still outstanding on 2026-08-11 (R0464) and stated as systemically fixed on 2026-08-14 (R0416/R0418). Multiple extraction readings on record.
- **[CONTESTED, ledger flag] R0115** — whether the 07-21 "gather scope for DNC list management" commitment is delivered (the 07-29 scoping session, R0524) or partially delivered (self-serve registry and offboarding automation not confirmed). Both readings on record.

### Not answered by the corpus

1. **What is the DNC rule for a person with neither LinkedIn URL nor email** (1,019 persons per R0956)? Enrichment is in flight; the *policy* — block by name+company, or accept the gap — is not stated anywhere.
2. **Where is the person/company threshold?** R0529 gives "large accounts → person level, small client companies → domain level" with <100 employees as an illustration, never as a rule. What is the number?
3. **What are the 3–4 scenarios Melisa was to supply** under R0462? They do not appear in ingested material.
4. **Provenance of the ~2,200 initial registry entries** (R0416) — do they need re-derivation, or is the population accepted as-is?
5. **Phase 2 (salespeople's own-tool outreach):** who owns it, when, and what is the interim control beyond "it's your responsibility" (R0461)?
6. **What happens at TTL expiry** — is a 6-month-old reply-based entry automatically reactivated into cold outreach, and does anyone review it?
7. **Is the escalation detector's alert-only design accepted permanently** (R0419), or should it block?

---

# P7 — Nurture

### Current understanding

- **Entry checklist for lead nurturing** (before recommending a lead): an Organization is attached; lead dismissal status set correctly; the LEAD NURTURING label added; all open tasks and activities closed. — stated by Melisa Draksler, 2026-06-03, #lead-generation-team (R0307). Expanded 2026-07-16: "All contacts need to have synced conversations, emails, and have all fields in Pipedrive … + note/context" (R0363), and "assign BDR owner to each of them and add linkedin url, link organization, set next scan date" (R0344, 2026-07-06).
- **Entry is the lead dismissal status `lead nurturing` plus the required fields plus a next scan date.** The scan is an n8n workflow that reads Pipedrive at person level on the scan date, enriches through one specific Clay table (which Melisa flagged as unstable), and on a signal creates a ClickUp task carrying a system-generated message with CRM context, scan results and identified signals. — stated by Melisa Draksler, 2026-07-03, file 15 (R0770). [MEETING-ONLY]
- **Scan-date fields (`last scan` / `next scan`) live on the Pipedrive PERSON record.** — same record (R0770); consistent with the later of the two scan-date rules (R0322), not the earlier (R0303).
- **Nurture is scan-date driven, not signal driven** — a human enters the next scan date and the system waits for it. The target design is an external trigger firing automatically. — stated by Nik and Sergey Cujba, 2026-06-16, file 21 (R0944).
- **Approval chain (inside ClickUp):** system-generated message → BDR rewrite stored as "message by BDR" → status `sales executive approval needed` → sales executive edits and approves → `approved by sales executive`. — stated by Melisa Draksler, 2026-07-03, file 15 (R0771). Sergey's fuller version adds an automatic send after ~2 days of no response (2026-06-16, file 21, R0953). [MEETING-ONLY]
- **Delivery splits by preferred medium:** email-preferred leads are pushed automatically into that salesperson's own Smartlead nurture campaign and sent from the main janeasystems.com domain (the lead is already warm); LinkedIn-origin leads are copied out of ClickUp and sent by hand from the salesperson's profile — which is exactly why LinkedIn nurture replies raise no notification. — stated by Melisa Draksler, 2026-07-03, file 15 (R0772). [MEETING-ONLY]
- **Send path, end to end:** ClickUp approval → owner-specific Smartlead nurturing campaign → sent from the janeasystems.com mailbox by a BDR on the salesperson's behalf. Nurtured people are simultaneously on the DNC list. — stated by Melisa Draksler, 2026-08-14, file 01 (R0421).
- **Sales team members must not add contacts to lead nurturing on their own** — they do not know the prerequisites. BDRs may. — DECISION by Melisa Draksler, 2026-07-16, #lead-generation-team (R0361).
- **Before adding a next scan date, close all outdated tasks.** — stated by Melisa Draksler, 2026-07-24, #lead-generation-team (R0372).
- **Two known blind spots in the nurture mechanic:** (a) a BDR-set scan date means changes between scans go unseen; (b) coverage is partial because senior people do not add their contacts. — stated by Melisa Draksler, 2026-07-29, file 06 (R0534).
- **Nurture follow-up personalisation is tiered by lead value:** high and medium value get personalised messages, low value gets something generic. — stated by Lule Salihu, 2026-07-30, #lead-generation-team (R0379).
- **Sergey's standing personal exception:** he does not send nurturing messages to most Ukrainian contacts, preferring occasional in-person meetings. — DECISION by Sergey Cujba, 2026-06-23, #lead-generation-team (R0328).
- **A reaction counts as consent to share material.** — DEFINITION by Sergey Cujba, 2026-07-31, #lead-generation-team (R0382): "Alexandre just reacted, so let's consider this as consent."
- **Automated field-completeness policing exists:** a bot ("Blake") flags nurturing records missing required fields, and BDRs must fix the record and schedule another scan date. — stated by Melisa Draksler, 2026-07-27, #lead-generation-team (R0377).

### Superseded / historical

- **Next scan dates in Excel only (2026-06-01) → Pipedrive only (2026-06-22).** Earlier: "Yes, you should remove them so that we only have them in Excel" — Melisa Draksler, #lead-generation-team (R0303, answering R0302). Later, and the current rule: "you can start manually adding those next scan dates from the Excel file, and from now on, you will set next scan dates only in Pipedrive" — DECISION by Melisa Draksler, 2026-06-22 (R0322). Do not smooth these into one line; BDRs were told the opposite thing three weeks apart.
- **BDR message approval by call (before ~2026-07-03) → BDRs hold full LinkedIn profile access.** "previously they didn't have that … they need to connect on a call with sales executive. They needed to approve message and then they needed to send everything manually. That was like a bottleneck" — Melisa Draksler, file 14 (R0738).

### Contested

- No concurrent competing versions isolated. **Two live undecided items:**
  - *Semi-automated nurturing notification channel* — Melisa confirmed the concept but explicitly deferred the mechanics ("not sure if we should check the signal and send it in Slack or add it as a note in Pipedrive or just send a ClickUp task") to the next BDR sync; not resolved in ingested material (R0374, Lule Salihu, 2026-07-24).
  - *Templated mass follow-up for non-replying nurture leads* — Sergey proposed the approach but deferred the decision to "our next sync" (R0386, 2026-07-31); Lule appears to act on exactly that idea three weeks later, still without a captured decision, in **the last message of the entire ingested Slack corpus** (R0415, 2026-08-18, no response).

### Not answered by the corpus

1. **What is a "signal"** for nurture purposes — the enumerated list of signal types the scan looks for. Never stated.
2. **What happens to nurture leads who never reply** — removed, re-scanned, templated follow-up? Asked 2026-07-31 (R0386), acted on unilaterally 2026-08-18 (R0415), never decided.
3. **May nurture follow-ups be sent through HeyReach automation, or must they be manual?** Asked directly by Lule 2026-08-12 and never answered (R0404 — Melisa's reply redirected).
4. **Who owns the scan-date discipline** now that ownership moved — and what is the rule when a BDR leaves a lead with no next scan date (R0414, also OPEN)?
5. **The notification requirement for LinkedIn nurture replies** (R0743 target design, R0772 explains why it does not exist) — is it in scope, and on whom?
6. **Reset rule when a trigger fires:** Sergey flagged that a trigger firing must notify and reset the next scan date (R0953). Never specified.

---

# P8 — Human roles

### Current understanding

- **Role split at hire:** BDRs = Lule and Araks; Nik is the GTM engineer. Melisa handles follow-ups for high-value leads who accepted but did not reply. — stated by Melisa Draksler, 2026-06-02, dm-melisa (R0009) — **[CONTESTED, ledger flag]**, see below.
- **Rationale for the GTM-engineer role:** the founder (Alexis) and CEO (Mike) had been asking for trigger/intent-based campaigns for three to four quarters; the hire exists to deliver those and to free Melisa's time for templates and hypotheses while the technical layer is owned by an engineer. — stated by Sergey Cujba, 2026-07-08, file 13 (R0714). The clearest statement of role rationale in the corpus. [MEETING-ONLY]
- **Ownership definition (director's):** "Ownership is when someone is responsible for something to be happening that has to be happening." Transfer mechanism = shadowing calls on Melisa's daily checks. — stated by Sergey Cujba, 2026-07-21, file 08 (R0575). Scope as stated: "the ownership of the infrastructure … Automations, workflows, the tools, how they're set, the chats in Slack, everything … Melissa and me would be the stakeholders" (R0566, earliest full articulation, 2026-07-21). [MEETING-ONLY]
- **Ownership boundary as finally drawn:** "infrastructure" excludes campaign execution, contact filtering and pre-qualification, which stay with Melisa together with the sales executives. — DEFINITION, 2026-08-14, file 01 (R0433): "filtering contacts for campaigns and stuff like that … that's still on me … That's like campaign execution."
- **Ownership transfer declared complete 2026-08-14** — AGREEMENT: Melisa states she now only reports bugs and Nik handles everything; Sergey accepts ("Sounds great to me") (R0432). **Flag: four days later Sergey re-opens the same subject as a reliability demand asking for a plan and a timeline (R0238, 2026-08-18).**
- **What a successful handover removes from Melisa:** the per-reply manual verification, not the integration itself. — stated by Melisa Draksler, 2026-07-21, file 08 (R0574): "I don't need to check if the labels are added correctly and all that stuff … I open every single response to see whether it was forwarded or not."
- **Sales owner vs BDR owner:** the sales owner is the person whose email/LinkedIn account was used to send the message; the BDR owner is assigned only on reply, and depends on which BDR supports which event or person. — DEFINITION by Melisa Draksler, 2026-07-13, dm-melisa (R0071).
- **BDR owner is self-assigned in Pipedrive** for all leads a BDR handles (nurturing + events). — stated by Melisa Draksler, 2026-06-01, #lead-generation-team (R0299).
- **Ownership correction happens at the PERSON level, not the lead level.** — stated by Melisa Draksler, 2026-08-17, #lead-generation-team (R0413).
- **Slava is the lead processor:** on a positive reply he re-owns the lead to the correct salesperson, applies outcome labels, fills fields, and attaches the AI research summary. Melisa named this whole set as automation candidates. — stated by Melisa Draksler, 2026-07-03, file 15 (R0754); "Slava is the one who's processing leads and he's the one who needs to check if something is missing" (R0145, 2026-08-04). Interim manual rule while LinkedHelper wound down: whoever sees the reply adds the `responded` label, Slava does the rest (R0538, 2026-07-27).
- **Stefan is the historical out-of-hours / urgent responder and must be kept current on every change.** He is an external consultant and structurally cannot hold Pipedrive access (contract/privacy constraint) — the stated reason an internal GTM engineer was hired and given full access. — stated by Melisa Draksler, 2026-08-05, file 05 (R0484). Stefan's terms: monthly retainer, no fixed hours (~20–60 h/month), two months' notice both ways (Sergey Cujba, 2026-08-14, file 01, R0441 — answering a question neither Nik nor Melisa could answer). Stefan built the Smartlead-side automations and the ~50-mailboxes-per-executive email routing system (R0582).
- **Andriy (external, Poland) built the lead-nurturing n8n workflow, and every change goes through him.** — stated by Sergey Cujba, 2026-06-16, file 21 (R0946); independently by Melisa 2026-07-03 (R0065) and again 2026-07-23 (R0117).
- **ICP definition is owned by Chrissy;** Lilla Szabo is a temporary stand-in and expects handover. — stated by Sergey Cujba (R0639) and Lilla Szabo (R0653), 2026-07-10, file 11. The specification the automation depends on therefore has no continuous owner.
- **Out-of-scope requests are refused and redirected:** "on any request outside of the scope outlined in that message - please say that you can't do it because Melisa and Sergey are not aware of it, and ask to send that request in sales-marketing" — DECISION by Sergey Cujba, 2026-06-26, #lead-generation-team (R0330). Same pattern instructed earlier for Jim's ad-hoc asks (Melisa Bahonjić, 2026-06-19, file 19, R0857).
- **Attendance is part of performance:** meeting invites from the sales team or Sergey are to be attended (Melisa Draksler, 2026-06-03, dm-melisa, R0015); "attending meetings is also part of the performance of a member of a team … same goes to attenting regular meetings like sales&marketing by-weekly syncs, having an actual schedule in calendar" (Sergey Cujba, 2026-07-16, dm-sergey, R0187). Days off go in Bamboo for Sergey (R0025).
- **HeyReach role model:** Sergey owns the workspace, Nik owns the integration layer (webhooks/API → n8n), BDRs hold member role and are restricted from integrations. — stated in file 02, 2026-08-14 (R0516). The sales team is deliberately excluded: "if we give sales team access to heyreach, they will mess up everything" (R0157, Melisa Draksler, 2026-08-11, dm-melisa).
- **Why tool/self-service expectations are not placed on sales executives:** lead-gen is not in the hiring loop for those roles, and the function's remit is defined as supporting whoever is hired. — stated by Melisa Draksler, 2026-08-05, file 05 (R0481).
- **[OUT-OF-CORPUS] Melisa Bahonjić is a real, separate person** — previous GTM role, gone by ~July 2026, owner of record on the 215 London leads (R0957, owner correction 2026-08-19).

### Superseded / historical

- **Handover scoped as monitor-and-learn (2026-07-21) → executed as a wholesale rebuild (by 2026-08-04).** Earlier: "the transfer of ownership right now would be in the scope of making sure that things are working right, monitoring the situation … And then as soon as we have time to optimize something … somewhere in the future" — Sergey Cujba with Melisa Draksler, file 08 (R0573); Melisa's version: "ownership in this case would be for Nikita to learn how everything works". Later: both reply paths rebuilt from scratch (R0143/R0144, 2026-08-04), documentation for the two new workflows delivered 2026-08-07 (R0296). **No ingested record shows this scope decision being formally revisited.**
- **Post-connection follow-up messaging: BDRs → Melisa (London sprint only).** "I would like to take follow ups to those who connected on myself because they are not doing a good job" — Melisa Draksler, with Sergey explicitly agreeing and scoping it to that sprint ("For this particular situation"), 2026-07-08, file 13 (R0701).
- **Daily Pipedrive data-quality check: Melisa → Nik (2026-07-27).** COMMITMENT: "I'm gonna be doing it right now from. From this moment. I'm gonna be checking" (R0546). Later evidence is mixed: on 2026-08-06 the 372 missing Event names were surfaced by Melisa (R0389), not by Nik's check — though Nik then root-caused and fixed them (R0149).

### Contested

- **[CONTESTED] What the owner is expected to do — bring or receive.** Sergey: "it should be two sided process … in ideal situation in nearest future you should see more than we see because you own it. And you would get back to us saying like these are the things that I noticed are not well" — 2026-08-05, file 05 (R0492). The ledger records this as directly contradicted by Nik's own model of the role (R0493). Both stand.
- **[CONTESTED] Bus-factor mitigation: second person vs accepted downtime.** Melisa raised the single-point-of-failure concern (R0443); Sergey's position, stated in the same exchange: "As a business, we need to take these risks … We want to be ready for a situation when something happens where we are ready to be only with one person and with a bunch of automations … We're going to stop campaigns if needed" (R0444, 2026-08-14, file 01). Nik's capacity statement sits against it: infra + several event campaigns + new automations + issue-fixing "is not possible at all" for one person (R0445).
- **[CONTESTED] Whether the ownership transfer is closed.** Closed: AGREEMENT R0432 (2026-08-14). Open: Sergey's "we need a plan and a timeline to make sure that we have a reliable and predictable system … the current setup shows signs of non-reliability" (R0238, 2026-08-18). Also OPEN four days earlier: "What exactly do you own, [Nik]?" with Sergey noting he could not remember which area Nik had previously excluded (R0473, 2026-08-11).
- **[CONTESTED, ledger flags] R0009** (BDR role scope — two readings, including the 07-08 removal of follow-up messaging from BDRs), **R0276** ("from Monday i can replace all Melissa's actions" — delivered per R0432 vs overdue/unclear per the 08-05/08-11 disputes), **R0286** (ownership proposal accepted-in-practice vs explicitly closed), **R0273** (status ask answered vs answered-in-part).
- **[CONTESTED, ledger flag] R0180 / R0193** — the standing "how do you communicate what you are working on" protocol: partially answered by the 08-05 advance-notice principle (R0483) vs still OPEN. Deferred three times (2026-06-26, 2026-07-17, 2026-07-27) and never written down.

### Not answered by the corpus

1. **A written role/ownership matrix.** Every version in the corpus is verbal (R0566, R0575, R0433, R0432) and the boundary was still being disputed on 2026-08-11 (R0473).
2. **Who covers when Nik is unavailable**, in hours and in scope? The principle was agreed (announce absence, name cover — R0483) and never operationalised; Stefan is the de facto answer but has no Pipedrive access (R0484).
3. **Does Stefan get onboarded onto the new workflows, by whom and when?** Melisa's ask (R0126, 2026-07-29) is still open on 2026-08-05 (R0484) and 2026-08-11 (R0478).
4. **What is the split of campaign builds between Mykyta and Stefan?** Named as unresolved on 2026-08-07 (R0395), deferred on 2026-08-12 (R0455), answered only as a principle on 2026-08-14 (R0434) — no per-event assignment rule.
5. **Who owns MQL/SQL and ICP-band definitions** after Lilla hands back to Chrissy (R0653)?
6. **What is the reporting cadence and channel** for Nik's status (ClickUp / sync / backlog)? Nik asked for a ruling in three numbered options and was deferred (R0193).

---

# P9 — Reports

### Current understanding

- **Label presence is the gate for reportability.** Leads without label `1. Cold` do not appear in reports at all. — stated by Melisa Draksler, 2026-07-27, file 07 (R0543).
- **Identical campaign naming across LinkedIn, Smartlead and Pipedrive is a reporting invariant.** — stated by Melisa Draksler, 2026-06-29, file 16 (R0793): "they need to be same on … the LinkedIn level and the Pipedrive level and the smart lead level so that everything is visible in. In dashboards. If we have two different naming conventions, people break the reports."
- **Pre-publication reconciliation is the detection control for lead-sync loss:** Melisa compares counts in Smartlead + LinkedHelper against Pipedrive before showing any report. — stated by Melisa Draksler, 2026-08-05, file 05 (R0489): "this is how we spot problems. I didn't do it this time because we had so many other problems every day, like 10 new problems" — which is why the 34% Ai4 gap surfaced late.
- **Manual data-quality method being handed over:** sort Pipedrive leads newest-first and eyeball the required fields. — stated by Melisa Draksler, 2026-07-27, file 07 (R0547). No automated check existed at that date.
- **Report/decision-document format is layered:** a very short executive layer, a link into detail, and the actionable product on top. Declared the standing default for presenting work. — stated by Sergey Cujba and assented to by Nik, 2026-08-11, file 04 (R0469). Melisa added the precedent for hypothesis voting: a Sergey-led walkthrough plus a Miro board where sales add ideas and vote blind to each other's input.
- **Outdated-task triage:** read the message history to establish state, then either close the task or ask the lead owner. — stated by Sergey Cujba, 2026-06-06, #lead-generation-team (R0312).
- **Finding which sequence step produced replies is manual inspection** — Smartlead per-campaign replies, or the reply thread on the Pipedrive record. No report or dashboard exists for this. — stated by Sergey Cujba, 2026-06-16, file 21 (R0910).
- **Escalation duty on data defects:** "if you see something like this, you need to report it to BDRs and Slava so that they can see what happened and fix it because management is looking at our performance every day" — DECISION by Melisa Draksler, 2026-08-18, dm-melisa (R0167).
- **Handover-queue transparency norm (example):** unusual queue depth is announced with a cause breakdown rather than left to be discovered — 19 open handover tasks, 6 from recovered outage replies, rest normal accumulation. — stated by Nik, 2026-08-06, dm-melisa (R0151).

### Superseded / historical

- **Manual pre-publication reconciliation (Melisa) → automated scheduled checks (Nik, from 2026-08-04).** AGREEMENT: "I will create AUTOMATED system running on schedule to check daily weekly or idk how many times per X period of time if everything is in place / That's okay with me but you need to create documentation about the workflow and onboard Stefan on it" (R0141, 2026-08-04). The automated version does **not** cover Pipedrive-side manual actions — see P12 (R0475).

### Not answered by the corpus

1. **Which dashboards exist, who owns each, and which fields each one depends on.** Only fragments are on record (Lilla's event dashboard depends on Event Name — R0340/R0561 — and on source channel — R0544).
2. **Nik has never been given access to reporting.** "I want access to reporting and how its being made" — Nik, 2026-07-18, dm-melisa (R0098): **OPEN, never answered through 2026-08-18.**
3. **What is the reporting cadence and audience** for GTM-engineering work (weekly? bi-weekly? to whom)? Sergey described it verbally (R0668) and it was never written down.
4. **Is there an agreed definition of "reply rate" / "acceptance rate"** and the denominators used? Figures are quoted throughout (10% acceptance, 41% verified email, 104 positive replies) with no stated definitions.
5. **Who reconciles counts now** that the manual pre-publication check has moved (R0489 → R0141)?

---

# P10 — Field dictionary

### Current understanding

- **Required-field set for a usable lead:** organization, source, medium, marketing hypothesis, usually current position, both `lh current company` and organization on the contact level, and campaign name. The two load-bearing ones are **label** (without it the lead is invisible) and **source channel** (Lilla's dashboard uses it). — stated by Melisa Draksler, 2026-07-27, file 07 (R0544).
- **Lead score composition:** the final score sums Job-title qualification and Company qualification. — stated by Melisa Draksler, 2026-06-02, dm-melisa (R0014) — **[CONTESTED, ledger flag]**. The company-qualification model traces back to Sergey; Nik rebuilt it from Sergey's version for the UK sprint (R0175, 2026-06-11).
- **Two distinct score fields:** person-level `score` (range 0–110, the prioritisation field) and `final score` (the company table's hiring-waterfall score). Melisa read the wrong one first — the naming is a live source of confusion. — DEFINITION by Nik, 2026-06-29, file 16 (R0776).
- **A maximum (110) score = AI hiring signal + software-engineering hiring signal + person active on LinkedIn + company size inside the 50–500 band.** Individual weights were not stated. — stated by Nik, 2026-06-29, file 16 (R0777). Hiring-signal levels: 3 = hiring for AI/AI-software roles, 2 = hiring for software engineering but not AI; levels 0 and 1 were never described (R0779).
- **Company classification values (UK sprint table, 2026-06-16):** Software-Centric / Software-Dependent / Competitor / Software-Integrated. Where the model is not confident, a second, more expensive web-research call runs and the smarter call wins. — DEFINITION by Nik, file 21 (R0923).
- **ICP-fit model (Lilla/Chrissy):** a composite additive rubric over six components — industry, stage maturity, company type, geography, revenue range, buying signal. Hidden per-option scores are summed and mapped to band A / B / C = strong / moderate / low fit. **Only the band, not the numeric score, is intended to reach Pipedrive.** Distinct from the existing 0–110 lead score, which scores people, not company ICP fit. — DEFINITION by Lilla Szabo, 2026-07-10, file 11 (R0641).
- **Event Name exists separately from campaign name** because it is the only field unifying in-person, introduction-sourced and campaign-sourced event leads for Lilla's dashboard. — DEFINITION by Melisa Draksler answering Nik ("so the event name is just a garbage field, right?" — "No"), 2026-07-27, file 07 (R0561).
- **Non-event campaigns must not carry an Event Name.** — DEFINITION, Melisa Draksler and Nik, 2026-08-06, dm-melisa (R0152): "not every campaign will be related to events / so other non-event campaign can't have that field".
- **Campaign personalisation fields:** use `Cleaned Company name`, not Org or raw Company Name. — stated by Melisa Draksler with Nik, 2026-06-29, dm-melisa (R0044). In LinkedHelper the `name` variable is pulled from the profile, not the CSV input, unless mapped (R0046).
- **Invite-step payload:** name, email (used as identifier), profile URL, current company, position, member ID and public ID (both used as identifiers), plus the constant campaign-stage value `invited`. Melisa flagged her own uncertainty about the identifier design ("I just followed like Linked Helper guidelines"). — stated by Melisa Draksler, 2026-07-03, file 15 (R0755).
- **Alert payload rules:** drop the InMail marker and `reply_text`; include a link to the Pipedrive lead record. — DECISION by Melisa Draksler, 2026-07-15, dm-melisa (R0072).
- **Pipedrive source values were changed** by Melisa together with Lilla and Marci — announced to Nik and Sergey only, with the sales team not yet informed. — stated by Melisa Draksler, 2026-07-03, file 14 (R0746).
- **Any Pipedrive field, standard or custom, can be populated by the automation.** The binding constraint is specification detail and effort, not feasibility. — stated by Sergey Cujba (R0637) and Nik (R0638), 2026-07-10, file 11.
- **Why old person records are field-incomplete:** in Pipedrive's early years there was no process and different fields, plus salespeople creating people without a last name. — stated by Melisa Draksler, 2026-07-10, file 12 (R0682).
- **Field sprawl is a live blocker:** ~100 custom fields, ~31 outreach-related, and five competing LinkedIn-URL fields, which is why a single reliable DNC export is not possible. Melisa cannot clean it up (no admin rights); it would need Marci. — ISSUE by Melisa Draksler, 2026-07-21, file 08 (R0590) — **open**.
- **Lead title format** (example approved despite admitted uncertainty about the leading number for HeyReach-sourced leads): `510736 - Ai4 2026 - Rune - LinkedIn - Person-3426894b`; "This first number is usually Smartlead campaign number … So i dont know whats in this case … Ok looks good" — Melisa Draksler, 2026-07-20, dm-melisa (R0103).
- **Targeting matrix by headcount (Sergey's, as applied):** 11–50 → C-level tech and C-level top; 51–200 → C-level tech, engineering-driven product managers, engineering managers; 500–5000 → engineering managers only. A very senior person at a very large company should score "maybe", not "yes" ("CTO from Meta is not going to be our potential client"). Sergey flagged his own top-band choice as "a bold move". — stated by Sergey Cujba, 2026-06-25, file 18 (R0822).
- **Qualification requires verdict = yes at BOTH person and company level, and the filter is applied at person level.** — DECISION by Melisa Draksler, explicitly confirmed by Sergey ("Yeah"), 2026-06-29, file 16 (R0782).
- **Toby's approved targeting pointers:** headcount 50–500; prioritise companies hiring for software engineering and AI-related roles; prioritise contacts who posted on LinkedIn in the last 30–60 days. — DECISION relayed by Nik, 2026-06-26, #gtm-engineering (R0246); the 50–500 band applied as a hard pre-filter at Sergey's request (R0778).
- **Open-to-work is an exclusion in prequalification.** — **AGREEMENT, Sergey Cujba and Nik**, 2026-06-16, file 21 (R0936). *No record in ingested material of the exclusion actually being implemented.*

### Superseded / historical

- **Next scan date: Excel-only (2026-06-01, R0303) → Pipedrive-only (2026-06-22, R0322).** Full detail under P7. The person-level `last scan` / `next scan` fields described on 2026-07-03 (R0770) are consistent with the later rule.
- **Per-company contact cap: ~20–25 (2026-06-25) → 2 (or 3) (2026-06-29).** Earlier, DECISION at the 06-25 GTM sync: per-company limit raised to 50 for the pre-qualification stage so nobody is discarded before scoring, then a per-company cap of ~20–25 applied when selecting who is actually contacted, replacing a previous blind 10-per-company pick — "Let's go with 50 for now … this is not a limit for sending. It's a limit for pre qualification / I think that 20 is going to be sweet spot" (R0821). Later, AGREEMENT four days on: "maybe we should reduce like to have two people per company / Yeah, very good idea … Would it be three or two?" — Melisa proposing, Sergey endorsing, Nik building it as a count column, **the exact cap (2 or 3) left to be tuned** (R0783, 2026-06-29).
- **Company-qualification input field.** Melisa asked on 2026-06-29 which company value the already-completed company qualification actually used when a person's employer had changed; Nik answered only about going forward ("we can just use Org") and promised to re-check. The scored table's provenance was left unresolved (R0786).

### Contested / UNRESOLVED numbers

- **[UNRESOLVED — do not reconcile] Sending capacity.** Three data points, never reconciled:
  - **~400 emails/day** — "also general capacity if we use only Toby's emails (which have 20+ emails per day limit ) = ~400 emails per day" — Nik, 2026-06-29, dm-melisa (R0040). Origin: the 06-29 decision to use only Toby's inboxes because he would be in London (R0798), and Toby's infra had not been expanded in ~18 months (R0053).
  - **600/day** — "our infra gives us ability to send 600 per day max" — Nik, 2026-06-30, #gtm-engineering (R0251).
  - **A per-inbox figure, self-corrected mid-sentence** — "Okay, I've made like 50, 25 per day. That's going to be our biggest number we can send per inbox. So that's it" — Nik, 2026-07-08, file 13 (R0711). A per-inbox cap of 20–25 is arithmetically consistent with ~400/day on Toby's inboxes, but no inbox count was stated, so it narrows nothing.
  - A fourth, from 2026-06-16: "we can send around a thousand-something a day" against ~11,000 sourced people — Sergey Cujba, file 21 (R0933), with the mailbox count asked and not answered.
  - **TRAP — keep separate:** Sergey's *other* "400" is **400 LinkedIn connection requests over the sprint window**, not daily email capacity: "if we send reach outreach to 400 people, we might potentially get 40 connections and out of 40 connection … at least 3, 5 meetings" — 2026-07-08, file 13 (R0698).
- **[CONTESTED, ledger flag] R0014** — the score composition line carries two extraction readings (the ICP-band rubric of 2026-07-10 as successor; and the 06-29 unanswered question about which company value was used).
- **[CONTESTED] Toby's LinkedIn campaign ceiling: 600 vs 800.** "we only can add maybe maximum of 600 people" — Melisa Draksler, 2026-06-25, file 18 (R0825). Four days later, AGREEMENT with all three present: "we need around 800 contacts for LinkedIn campaign … We can send 800 connection requests", with ~8,000 to email — 2026-06-29, file 16 (R0784). The 800 figure is the later one; **no reconciliation is visible in the corpus.**
- **[CONTESTED] ICP boundary.** Melisa proposed the line at Series B and C ("Maybe that's the line"); Sergey narrowed it to Series B/C companies that are hiring multiple engineers, and declared stealth/pre-seed out of ICP as of 2026-07-14 — while naming Toby and Chrissy, not GTM, as the ICP gatekeepers (R0613). Sergey's effort split for the new ICP was stated vaguely and self-inconsistently ("60 or 70% … 30% … 10% on. I do not remember very clearly") and the authoritative document was never shared (R0616, R0615).

### Not answered by the corpus

1. **MQL vs SQL has no definition anywhere in the corpus.** Asked of Nik *and* Sergey by Lilla Szabo on 2026-07-10 — "we should also at some point add the distinction between marketing qualified leads and sales qualified leads into pipedrive … Which, which level? Or should we try to add this like, as an attribute or more like as a, like a separate category?" (R0650). Nik answered a different question (the automation mechanism, R0651); Sergey, though addressed directly ("a question for both of you guys"), did not respond at all; Lilla routed it away. **MQL/SQL appears nowhere in the ingested Slack corpus. Headline P10 gap.**
2. **What is the real sending capacity**, per inbox, per sales executive, and in total? Three figures, no reconciliation (above). Also unresolved for trigger campaigns: "what kind of volume we can expect for each hypothesis … 500 people or 2,000 or 5,000" — OPEN (R0453, 2026-08-12).
3. **Which of the five LinkedIn-URL fields is canonical**, and who consolidates the ~100 custom fields (R0590)?
4. **The per-option scores behind the ICP band rubric** — the rubric was "version 5, still work in progress" on 2026-07-10 and the scope doc was never delivered (R0642, R0645).
5. **Score levels 0 and 1** of the hiring signal (R0779), and the per-component weights behind 110 (R0777).
6. **Whether the open-to-work exclusion was ever implemented** (R0936).

---

# P11 — Invariants

### Current understanding

- **CANDIDATE INVARIANT: every lead that is not disqualified must have an active task or nurturing mode on.** — DECISION by Sergey Cujba, 2026-06-09, #lead-generation-team (R0318), stated as a standing rule. **Dated violation on record:** 372 Ai4 leads with no Event Name and missing Marketing Hypothesis, reported publicly by Melisa Draksler on 2026-08-06 (R0389) — a direct recurrence of the field invariant she herself had stated in the same channel a month earlier (R0340); and 5,913 people reached out to for Sales Sprint London against only ~4.7k visible in Pipedrive (R0391, 2026-08-06), explained as ~1,200 contacts lost to the same Make defect class, with the original 7.5k target figure still untraced.
- **INVARIANT: lead creation date is consumed by company dashboards, so delete-and-reimport is not a permitted repair method.** — stated by Melisa Draksler, 2026-07-27, file 07 (R0554): "it would break reporting because they are also looking at the date created … if you import all the leads at once, it will just populate that when the lead was created."
- **INVARIANT: single channel per contact within a sprint.** A contact in the LinkedIn campaign is excluded from the email campaign. — DECISION by Melisa Draksler, acknowledged by Nik, 2026-06-29, file 16 (R0799): "we do not want to reach out to them on both channels."
- **INVARIANT: lead nurturing requires a LinkedIn profile URL.** "Lead nurturing is based on LinkedIn profile URL - if we don't have it, we cannot scan them" — Melisa Draksler, 2026-07-06, #lead-generation-team (R0346).
- **INVARIANT: the Pipedrive-side contract survives any tool migration.** Fields sent, stage changes, label automation and Slack notifications must be preserved unchanged; only the LinkedIn tool is replaced. — DECISION by Sergey Cujba, 2026-06-25, file 18 (R0829); acceptance criteria for any LinkedIn tool at R0816.
- **Platform ceiling: 40 actions per day per LinkedIn sender**, presented as hard ("there is nothing we can do about it"); settings can be bulk-applied across accounts. — stated by Nik, 2026-08-14, file 02 (R0505). Nik's own practice: "i never used more than 40 per day" (R0090, 2026-07-17).
- **Campaign structure is immutable once started.** Follow-ups can be added and message text and delays edited, but steps cannot be removed; duplicating the campaign is the accepted workaround and it respects already-executed steps. — DEFINITION by Nik, 2026-07-17, dm-melisa (R0095) and file 02, 2026-08-14 (R0508). Consequence: field auto-population (event/medium/hypothesis) applies only to campaigns created after the change, never to running ones (R0587, 2026-07-21).
- **LinkedIn sequences are acceptance-timed:** the follow-up shifts up to three times depending on when the person accepts. — stated by Melisa Draksler, 2026-07-23, #lead-generation-team (R0369).
- **Delayed acceptance on a stopped campaign is expected behaviour, not a bug.** — resolved ISSUE, Melisa Draksler / Araks Grigoryan, 2026-08-17, #lead-generation-team (R0410): "we didn't send any connection requests, but these guys accepted them just now. It makes sense to send follow-ups to them."
- **Do not send another message to leads who already received 3–4 sprint messages with no reply.** — DECISION by Melisa Draksler, 2026-07-30, #lead-generation-team (R0378). Paired operational rule: check when a person connected so this week's accepters do not get an immediate second follow-up, and set a task to follow up on Tuesday (R0380).
- **Always test the proxy connection before login.** — stated by Melisa Draksler, 2026-06-30, #lead-generation-team (R0338).
- **Sales-sprint psychological premise (Melisa's rule):** temporary presence is what makes the outreach work, so a sprint must target a location where the salesperson does *not* live, and saturated hubs (New York, London, San Francisco) are excluded. — stated by Melisa Draksler, 2026-07-10, file 12 (R0690), with prior evidence from a two-year New York attempt that did not work. **Contradicted in the same meeting by Sergey's always-there variant, which is the later statement and was left unresolved.**

### Superseded / historical

- **ICP boundary: stealth/pre-seed in → out (2026-07-14).** "Right now we can definitely pre qualify companies before we decide to reach out to them … They are not round A, they are not round B. They are precede and precede is like too small" — Sergey Cujba, file 10 (R0613).

### Contested

- **[CONTESTED] Sprint location rule.** Melisa: a sprint only works where the salesperson does not live; saturated hubs excluded (R0690, 2026-07-10). Sergey, same meeting, later: an always-present variant (recorded in the ledger as the later statement, left unresolved). Related live case: "Jim asked me like if we can run a sales sprint for him for San Francisco. And I told you right away, like New York, London, San Francisco, these are the parts of the world where every single…" (R0692, same meeting).
- **[CONTESTED] Toby's LinkedIn ceiling 600 vs 800** — see P10.

### Not answered by the corpus

1. **Is R0318 actually an invariant the system should enforce** ("every non-disqualified lead has an active task or nurturing mode on"), and if so — what is the automated check, and what happens when it fails? It was stated once, in June, and violated at scale in August without anyone citing it.
2. **What is the authoritative invariant list** that the monitoring should assert? Nik's automated checks cover Smartlead/HeyReach campaign activity only (R0475).
3. **Is the sprint-location rule Melisa's or Sergey's?** A sprint has already been requested for an excluded hub (R0692).
4. **What is the maximum number of touches per contact** across channels and campaigns? R0378 gives an ad-hoc "3–4 then stop" for one sprint; there is no standing rule.
5. **Does the single-channel-per-contact rule (R0799) apply beyond the London sprint** — to events, where the same person may be in both an email and a LinkedIn event campaign (R0752)?

---

# P12 — Notifications

### Current understanding

- **A stage change to `replied` fires three things:** a Pipedrive task "Assign this lead to a sales executive" owned by Melisa; the labels `responded` and `connected` on the lead; and the Slack incoming-lead notification — produced by a Pipedrive automation plus a Zapier automation, not by the LinkedIn tool. — stated by Melisa Draksler, 2026-07-03, file 15 (R0765). [MEETING-ONLY] (The Zapier half was switched off 2026-08-05 — see P4/P14.)
- **#infra-issues is the cross-tool issue intake channel.** "Guys - any issue related to Pipedrive, Heyreach, Smartlead, Zapier, Make, Surfe or anything else - please post it here." — Nik, 2026-08-06, #infra-issues (R0211). Origin: Nik's proposal the same day (R0394), accepted by Sergey ("Let's try to handle it this way"); Melisa's own response to the proposal is not captured in ingested material.
- **A dedicated Slack channel exists for lead-nurturing replies only.** — DECISION, Nik and Melisa Draksler, 2026-07-24, #lead-generation-team (R0371): "You want to create dedicated Slack channel for replies? / yes, but only for lead nurturing replies".
- **Backfilled alerts are legitimate and are always marked as such.** "Backfilled alerts only appear when we repair something that was missed, and they're always marked 'backfilled' like this one." — DEFINITION by Nik, 2026-08-14, #infra-issues (R0227).
- **A quiet channel is the expected steady state.** After the reply-alert rebuild: "That single post you see at 16:09 (my test address) IS the new system working — I fired it deliberately as the end-to-end proof. The channel will stay quiet until leads actually reply" — Nik, 2026-08-11, #infra-issues (R0220).
- **The DNC escalation detector is alert-only** and does not block or remove anyone (R0419) — see P6.
- **Cloud LinkedIn automation batches and delays actions and reply notifications by design; nothing is instant.** Accepted by both sides as inherent, and given as part of the justification for keeping DICloak. — file 02, 2026-08-14 (R0518).
- **Missing field values are surfaced by an in-channel bot ("Blake") and must be fixed plus re-scanned.** — stated by Melisa Draksler, 2026-07-27, #lead-generation-team (R0377).
- **Bot messages in the lead-processing channel cannot be deleted** — "nope / no such option" (Melisa Draksler, 2026-07-20, dm-melisa, R0105).
- **Under LinkedHelper, notifications required a manual refresh after replies arrived** — "We received 2 replies so I need to refresh it so that notifications get sent" (Melisa Draksler, 2026-07-21, dm-melisa, R0113).

### Superseded / historical

- **Reply notifications: legacy Zapier → direct posting (2026-08-05 → 2026-08-11).** See P4 (R0215). The channel was dark for six days and nobody noticed until 2026-08-10 (R0212).
- **Duplicate Slack notifications → resolved.** All 21 duplicates came from one old Zap ("LinkedHelper outreach response"), switched off 2026-08-05 11:28 (R0137).
- **Detection of notification failures: manual (Melisa's inbox-vs-Slack comparison, R0536) → automated self-check on campaign activity (2026-08-11).** **Explicit boundary of the new coverage:** "it's only for the campaigns right now … I know what's happening all the time in within smart lead and heritage [HeyReach] campaigns. But when somebody goes to pipedrive and do anything, anything, anything, I'm not, I don't follow it right now" — Nik, 2026-08-11, file 04 (R0475). This is why CRM-side omissions still surface through Melisa (R0474).

### Contested

- No concurrent competing rule isolated. **Open mechanics:** the notification channel for semi-automated nurturing signals (Slack vs Pipedrive note vs ClickUp task) was explicitly deferred and never decided (R0374, 2026-07-24).

### Not answered by the corpus

1. **The full notification inventory:** which events produce a Slack post, in which channel, to whom, and which system emits it. Only fragments exist (R0765, R0211, R0371, R0227).
2. **Who is on the hook when a channel goes silent?** The 2026-08-05→08-10 dark window was caught by Melisa, not by monitoring (R0212/R0215). No silence-detection rule exists.
3. **Should Pipedrive-side manual actions be monitored** (the stated gap in R0475), and by what mechanism?
4. **Does a paused campaign still deliver reply notifications?** (R0509 vs R0510 — see P4.)
5. **What alert volume is acceptable**, and is there a de-duplication / rate rule beyond the ad-hoc fixes (R0137, R0417)?

---

# P13 — Change management

### Current understanding

- **[MEETING-ONLY — the prime "everyone assumes, nobody wrote it down" case] Melisa's full change-management rule set:** no Friday deploys; any big change goes into production at the beginning of the week so there is time to work on it; and everyone must be notified in advance that automation will be paused, that incoming replies will not be forwarded, and that notifications will not be sent to Slack during that window. — stated by Melisa Draksler, 2026-07-21, file 08 (R0577): "we shouldn't do it on Fridays … any big change needs to be pushed into production at the beginning of the week so that we have time to work on it so that it's not like, you know, midnight calls and stuff breaking on the go. And we also need to notify everyone that automation is going to be paused, that incoming replies will not be forwarded, that notifications are not going to be sent to Slack during that time." **This rule appears nowhere in Slack.** It is a multi-clause rule, and precision matters about which clause was crossed:
  - **The clause crossed was ADVANCE NOTIFICATION.** The legacy Zapier notification automation was switched off on **2026-08-05 (a Wednesday)** with no notification that reply forwarding and Slack notifications would stop; the channel then went dark, undetected until 2026-08-10 (R0215, R0212).
  - **The no-Friday-deploys clause was NOT crossed by that cutover** — 2026-08-05 was mid-week, and the "beginning of the week" clause is arguably satisfied. Do not read a Friday deploy into this incident.
  - Nik's use of the word "Friday" in the 2026-08-05 meeting was his *expectation* of when the legacy cutover would happen — "on Friday I really expect to stop using the old one and start using the new" (R0495) — while the actual Zapier shutdown occurred the same day as that meeting, 2026-08-05 at 13:28. The two must not be conflated.
- **[MEETING-ONLY] Align before you change (Sergey's protocol, stated 2026-07-10):** as owner, you drive the work; before starting an optimisation you either ask in chat or book a 15–30 minute slot, or wait for the nearest GTM-engineering sync. — stated by Sergey Cujba, file 12 (R0667). This predates by one week the 2026-07-17 incident in which Nik disabled Melisa's live workflows without warning ("but you need to warn me about stuff like this" — R0093). **Never written down as a protocol.**
- **[MEETING-ONLY] Reporting protocol (Sergey's, same meeting):** Nik owns the ClickUp entries (task, start date, due date), decomposes big items into granular ones, and presents status — in progress / delayed / when ready — at a weekly or bi-weekly sync. — stated by Sergey Cujba, 2026-07-10, file 12 (R0668). In substance this answers the question he asked on 2026-06-26 (R0180); it was never captured, and the same question was re-asked and deferred twice more (R0190/R0191 on 07-17, R0193 on 07-27).
- **The GTM-engineering ClickUp list is the tracking surface.** Created live in the 2026-07-10 meeting under the Outbound Lead Generation space with statuses Not started / In progress / Completed, tasks carrying start and due dates and Nik as assignee, and Sergey pinning it to his favourites for monitoring. — stated three-party, file 12 (R0664); initial backlog at R0665.
- **Timeline discipline:** "when you understand at least approximately how the timeline is going to look like for both of these tasks, please put them in ClickUp so we are aligned on what should we expect when" — COMMITMENT, Sergey Cujba to Nik, 2026-07-21, file 08 (R0595). Still open: no ClickUp timeline for the ownership transfer or the DNC list is confirmed anywhere in ingested material.
- **Messaging changes on a sales sprint require the owning sales executive's approval.** — stated and confirmed, 2026-07-08, file 13 (R0699): "[Nik] Do I get it right? If you want to implement some messaging changes, we should always coordinate it with Toby. Right? / [Melisa] Yeah". Nik asked for a rule and was given one explicitly — a clean rulebook line.
- **Integration is not "done" at code-complete.** A small test review / test campaign is expected before dependent work starts; the next task's start date was pushed for exactly this reason. — stated and agreed, Melisa Draksler and Nik, 2026-07-10, file 12 (R0666).
- **Parallel workflow building is refused on quality grounds.** "I don't imagine building workflows in parallel at least with quality … you need to control the process of how its being built and how its being integrated into current system and continuously do checks to not shut down everything what is running in the background" — Nik, 2026-07-23, #gtm-engineering (R0279).
- **Schedule shared work in advance** — "please schedule time for this in advance" (Sergey Cujba, 2026-07-14, #gtm-engineering, R0270); team-sync times are quoted in CET (R0297).
- **Issue intake protocol, BDR→Nik:** post issues and improvement ideas in the shared channel and Nik patches. — stated by Nik, 2026-08-14, file 02 (R0520). Note the asymmetry: a channel-based intake exists BDR→Nik, while **no equivalent Nik→Melisa change-announcement protocol is agreed anywhere in ingested material**.
- **Nik's own diagnosis of the change-management failure mode:** "No documentation + any changes of the processes + when someone does manual issues ----> patch + changes" and "When every case is getting resolved ---> patch made for the future situation ----> behaviour changes" — 2026-08-18, #infra-issues (R0234, R0235).
- **Rebuilds are produced with Claude Code doing node-level construction under Nik's orchestration and review**, with chains reused between workflows. **No review or approval step involving Melisa or Sergey is described.** — stated by Nik, 2026-07-29, file 06 (R0523).
- **Documentation route chosen (2026-06-25):** screen-share walkthrough sessions recorded with Fireflies, the transcript turned into a draft specification which Melisa then corrects. — AGREEMENT, Sergey Cujba and Melisa Draksler with Nik assenting, file 18 (R0830). Documentation lives in **SharePoint**, with links added to related ClickUp tasks; Notion is not used (R0153, 2026-08-06).
- **Change-communication scope statement (example of the right level of detail):** "No — existing campaigns are not affected at all. The switch changes only what happens after Smartlead does its job: who processes the replies and writes them into Pipedrive" — Nik answering Melisa's "Is it going to affect existing campaigns?", 2026-08-07, dm-melisa (R0154).

### Superseded / historical

- **Migration window agreed as "after Ai4" (2026-07-21) → executed during Ai4 (2026-08-04/05).** Earlier, DECISION with all three present: "[Melisa] So maybe we can plan those changes after AI4 / [Nik] I saw this timeline and it seems like the best one to make transfers for everything" (R0588). Ai4 ran 2026-08-04 to 08-06; the new Smartlead/LinkedIn workflows went live and the legacy Zapier automations were switched off on 08-04/08-05 (R0143/R0144, R0215, R0137). **No ingested record shows the window being renegotiated.**
- **Refactoring-style incremental transition (proposed 2026-07-21) → wholesale rebuild (executed by 2026-08-04).** Sergey proposed incremental refactoring "while there are some campaigns in flights" (R0576), accepted verbally by Nik; execution rebuilt both reply paths from scratch — the pattern Melisa had asked against (R0570).
- **Test-window mechanism agreed but never scheduled.** "Stop the campaign for 30 minutes. You're doing your stuff, testing it … But it's risky. We need a quick way to roll back if something doesn't work" — Sergey Cujba, 2026-07-21, file 08 (R0578), accepted in the room. **No ingested material records a scheduled pause window or a rollback plan actually being agreed or executed.** Melisa's answer on why no quiet window exists: attendee lists are re-scraped 4–5 times pre-event, follow-ups go out on the weekend before, and a sprint runs concurrently (R0572).

### Contested

- **[CONTESTED] Whether a CRM migration is coming at all.** Melisa, 2026-07-27, file 07 (R0556): "they started talking like Chrissy and Sergey and Carol [Karol], they started talking something about that we will switch to Zoho like in a couple of months … I just don't think that Zoho is a good solution for us"; Nik: "that's gonna be then that I gonna need to replace stuff with her reach with smart lead with everything". They agreed to raise it with Sergey (AGREEMENT R0557) — **and the Zoho migration appears in no ingested Slack channel or DM at all.** Karol's own account of his remit on 2026-06-25 mentions content, pitch decks and the website project, with no CRM responsibility (R0837).
- **[CONTESTED] Was the 06-29 sprint launch deadline ever communicated?** R0032 says yes, R0033 (Nik) says "but end of the last week i did not hear this deadline … it should be stored somewhere". Two meetings inside the disputed window (file 18, 06-25 and file 16, 06-29) are ingested and **neither records the deadline being stated** (R0824, R0800); on 2026-06-16 Nik had asked for a launch deadline and got only "the earlier the better" (R0955). **[ledger flag on R0033]** — ingested material does not resolve which account is correct.

### Not answered by the corpus

1. **Is Melisa's change-management rule set (R0577) the standing policy?** It was stated once, in a meeting, and never written down or acknowledged in Slack. This is the single highest-value line in this part.
2. **What is the change-announcement protocol Nik→Melisa/BDRs** — channel, lead time, content? Proposed by Nik 2026-06-29 (R0036) and ignored as a mechanism; the reverse direction has one (R0520).
3. **What is the rollback plan** for a live-stack change, and who authorises a pause window (R0578)?
4. **Is there a review or approval gate** on AI-generated workflow changes before they touch production (R0523 describes none)?
5. **Is a Zoho/CRM migration real, and on what timeline?** (R0556/R0557 — never raised in any ingested Slack channel.)
6. **Who signs off a deploy during an active event window** (the R0588 rule was crossed without a recorded renegotiation)?

---

# P14 — Deployment mapping

### Current understanding — PRE-migration topology (baseline, 2026-06-25)

- **The full pre-migration topology, stated in one turn:** Linked Helper writes to Pipedrive through its own **native integration**; **Make** covers Smartlead only; **Zapier's sole job** is attaching labels when the Linked Helper stage changes; **Pipedrive Automations** create tasks when specific fields change. — stated by Melisa Draksler, 2026-06-25, file 18 (R0827): "for make is just for smart Lead linked. Helper has native integration with pipedrive … the only thing that we are automating through Zapier are the labels and these like when we change the stage, this label gets attached to the lead. This is the only part … automatic task creation that's done by pipedrive Automations." [MEETING-ONLY — **this is the pre-migration baseline the later Zapier label-stripping incidents sit on top of**]
- **The pivot of that topology is the campaign-stage field**; label automation and Slack notifications both key off stage transitions, which Melisa named "the most important part of integration". — 2026-06-25, file 18 (R0828).
- **Sergey believed this was already documented** — "It's all described in some document as far as I understand" (R0816) — which Melisa contradicted later in the same meeting (R0827).
- **Legacy inventory to be replaced: five workflows** — four Zapier automations plus one Make scenario. — stated by Nik, 2026-07-21, file 08 (R0568). Independently consistent with what was later found live: the notification Zap switched off 2026-08-05 (R0215), the duplicate-notification Zap switched off the same day (R0137), the label-stripping Zaps found 2026-08-11 (R0218), and the Make Ai4 person-creation scenario still in the loop 2026-08-04 (R0132).

### Current understanding — POST-migration state

- **Pipedrive sync runs through the in-house n8n integration; HeyReach's native CRM export and native enrichment are deliberately not used.** Enrichment happens in Clay before campaign setup. — stated by Nik, 2026-08-14, file 02 (R0519): "Export to CRM. It's not there yet and I wouldn't even do it because I don't see a reason to do it. We have already system in place which is connected to our CRM to pipe drive."
- **HeyReach replaced LinkedHelper; LinkedHelper is deprecated and its campaigns are managed manually.** — stated by Melisa Draksler, 2026-08-14, #lead-generation-team (R0405): "that campaign was executed via LinkedHelper and we no longer use LinkedHelper so data is not being sent to Pipedrive and you need to manage it manually when we receive new reply or when they accept invite." Cutover rule agreed 2026-07-27: LinkedHelper stays live until the London sprint's trailing replies dry up (~2 weeks), then is shut down (AGREEMENT R0537); build-in-parallel-then-cut-over agreed 2026-07-03 (AGREEMENT R0774).
- **DICloak stays in use alongside HeyReach** — manual connection requests, message edits and live reply visibility are not possible in HeyReach. — **AGREEMENT (multi-party), file 02, 2026-08-14 (R0517)**. DICloak also lets BDRs use Sales Navigator from Melisa's or a sales member's profile (R0335, 2026-06-30).
- **LinkedIn conversation tracking is scoped deliberately:** track only conversations started from HeyReach, to avoid exposing private messages — reversed on the spot for accounts whose earlier campaigns must stay visible to the BDRs. — DECISION executed live, file 02, 2026-08-14 (R0503).
- **Nik holds API-level access across the stack** (Make, Zapier, Pipedrive, HeyReach, Smartlead), which he presents as the basis for tracing any defect and for automated checks. — stated by Nik, 2026-08-05, file 05 (R0487). Note the tension with Melisa's 2026-08-04 statement that full admin access across everything the outbound team uses is not obtainable (R0148); the claim here is API access to the systems he runs, not admin on every tool.
- **Access is provisioned by credential-sharing in DMs/channels, not per-user accounts** — n8n and Langfuse (R0172, 2026-06-09), Apify (R0242), HeyReach (R0257), and Melisa sharing her own n8n login (R0118). Onboarding a salesperson's LinkedIn account into HeyReach requires logging in as them with their credentials, with the owner on the phone to confirm; **Melisa holds and distributes the salespeople's credentials** (R0629, 2026-07-14).
- **Proxy/profile rules:** do not touch Toby's, Sergey's, Mario's or Rune's profiles even though they are on old proxies; for Noah, Matt, Jim and Chrissy, create the profile, add their proxy, open the instance and log in. — stated by Melisa Draksler, 2026-08-11, dm-melisa (R0156). IPv6 proxies are not accepted by HeyReach; residential is the industry standard (R0091).
- **Run automation during our hours, not the sales team's**, because LinkedIn detects simultaneous multi-device usage. — stated by Melisa Draksler, 2026-07-20, dm-melisa (R0101).
- **Documentation lives in SharePoint** (links in ClickUp tasks); the pre-existing reference is the "Outbound infra document" (R0048, R0153).
- **Tooling decisions on record:** Apify Starter approved for real-time LinkedIn/Sales-Navigator scraping at ~$0.004/profile in place of Clay's non-real-time integration, ~$100/mo cap set by Nik (DECISION, Nik and Sergey Cujba, 2026-06-11, dm-sergey, R0176); Apollo used for company enrichment over Clay's native Enrich Company on cost and field coverage (R0920); commercial trigger-signal vendors rejected on price and signal saturation in favour of building in-house (**three-party AGREEMENT**, 2026-07-10, file 12, R0656); Crunchbase and Serper no longer used (R0008, R0007).
- **Sales Navigator: enterprise plan, ~10 seats held by the sales team;** per-seat InMail allowance observed on Toby's account is 50 credits/month accruing to a 150 cap (R0717).
- **Nik's own model routing:** Fable orchestrates (architecture / thinking / planning), Opus 5 executes; "if something can be done with Claude Cowork, Claude Code, Claude Dispatch i always route it there" (R0199, 2026-07-28, dm-sergey).
- **Scraping ceilings:** 2,000 per batch, max 5,000/day to avoid account blacklisting — which is why a 70,000-match Sales Navigator set became a ~30,000 working list; and a Clay table holds a maximum of 50,000 rows (R0820, 2026-06-25).
- **Email-finding waterfall expanded from 3–4 providers to 13**, giving 41% verified-email coverage against a recalled prior baseline of ~30% or less (comparison from memory, not measured) — R0802, 2026-06-29.

### Superseded / historical

- **HeyReach light seat (2026-07-03, 09:30) → HeyReach Growth trial (2026-07-03, 10:00, same day).** Earlier, in the 1:1: "I will buy one light one seat for start so that you can. And we will use Sergey's profile as an experiment" — Melisa Draksler, file 15 (R0775), with Nik already raising the caveat "We also would need to take a look at the possibilities with one seat … If everything is all right with one seat and API." Later, ~30 minutes on in the 10:00 team sync: "Melissa suggested to us to buy one seat and try but I don't. We need to check for sure if I gonna be able to have all the capacity for API hooks … if it's not possible for one seat we should buy grows … Should I go for the growth plan / It's gross" — DECISION, Sergey Cujba and Nik, file 14 (R0740). **The "test on Sergey's profile" element survives; the one-light-seat and buy-it-yourself elements do not — Sergey buys it, not Melisa.**
- **HeyReach rejected (~February 2026) → HeyReach adopted (2026-07-13).** The earlier assessment: only 2–3 basic Pipedrive fields, no automatic lead/person creation on connection request (manual push required), and no support for the nurturing loop; HeyReach itself said it was not possible and would not guarantee an n8n/Make workaround — stated by Melisa Draksler, 2026-06-25, file 18 (R0817). Recorded as the prior assessment, not silently superseded: the integration was in fact built and landed 2026-07-13.
- **GetSales free trial (2026-06-30, R0056; transition "already underway" per a BDR on 2026-06-08, R0316) → HeyReach.** Nik's HeyReach proposal is dated 2026-06-24 (R0027) and he was named responsible for the migration on 2026-06-25 (R0844).
- **Two concurrent LinkedIn campaigns required manual profile-switching every few hours under LinkedHelper** — the operational cost the migration removed (R0628, 2026-07-14).
- **n8n cloud → self-hosted upgrade decision** (R0194, 2026-07-24: "i just don't understand why we have cloud subscription when we can have full control of n8n since its self hosted and pay much less").

### Contested

- **[CONTESTED] Was the HeyReach integration working on 2026-07-14?** Melisa at 00:02 of that meeting: "Integration is not working" (R0596). Nik at 55:31 of the same meeting: "It should be in place already. It should be working properly" (R0627). Neither reconciles the two and no one asks which integration Melisa meant; the integration had been expected functional the day before. Both retained.
- **[CONTESTED] Nik's access position.** "right now I have the full ownership of everything. Like every part of the API calls for make, for the [Zapier], for Pipedrive, for [HeyReach], for smart lead, for anything" — Nik, 2026-08-05 (R0487) vs "either i get admin access to everything outbound team uses either its again 'Hey person xyz go to yzd and ask to give blablabla'" — Nik, 2026-08-04, with Melisa answering "I'm here for almost 3 years and I don't have access to everything because this is how things work in bigger companies" (R0148, open).
- **[UNRESOLVED] Sending capacity (400 / 600 / per-inbox / ~1,000)** — full treatment in P10. Sergey's operating principle for trigger campaigns explicitly does not touch it: many low-maintenance campaigns run in parallel and are pruned only once sending capacity becomes the binding constraint (R0679).

### Not answered by the corpus

1. **A current system diagram.** No post-migration equivalent of R0827 exists anywhere in the corpus — the only complete topology statement on record is the pre-migration one.
2. **What remains live in Zapier, Make and Pipedrive Automations today?** R0568 counted five legacy workflows; four are accounted for by name (R0215, R0137, R0218, R0132) — the inventory was never closed out.
3. **Where does n8n run, and who owns the instance?** Sergey raised it on 2026-08-11 ("I see that the notifications are going through your email and this is … your instance of [n8n]. All of this has to be…", R0465) — no resolution in the corpus.
4. **What is Stefan's LinkedIn keyword-tracking tool**, where did it come from, and does it duplicate Trigify? Neither the director nor the incoming owner could name it (R0602/R0603, 2026-07-14).
5. **Who owns subscription renewals and expiry alerting?** The single-point-of-failure exposed on 2026-07-27 (sole access to Toby's profile lost, Sergey the only renewal owner, no expiry alerting — R0376) was not addressed in ingested material.
6. **Token/credit cost ceilings for production Clay+Claude runs.** Sergey closed the question verbally on the basis that Nik's personal plan covers current spend; no per-run measurement and no cost ceiling exist (R0466).

---

# P15 — Edge cases

### Current understanding

- **Pipedrive keeps no change log for labels, and support cannot restore them.** A prior incident wiped labels on ~2,000 leads with no recovery. — stated in file 02, 2026-08-14 (R0497): "I had a case where Sergey by accident changed labels for like 2000 leads and we couldn't bring it back because there is no change log for labels for pipedrive and also support was not able to bring them back … we need to be extra careful to not change labels by any means." Nik's counter-position: his own tooling's action log (before/after snapshots) is the recovery path, not Pipedrive.
- **Campaign structure is immutable after creation; duplicate-the-campaign is the sanctioned workaround** and it respects already-executed steps. Connection-acceptance delay must be set to ~30 days. — file 02, 2026-08-14 (R0508).
- **HeyReach exposes no multi-campaign membership view for a lead;** filtering the inbox by campaign and sender is the only available approach. — answered in the negative after a live attempt, file 02 (R0513); Nik qualified his own reliability here ("I'm using it only for API purposes. 90 of the cases").
- **Field auto-population applies only to campaigns created after the change**, never to running ones. — correction of a mistaken belief in the room, Nik to Melisa Draksler, 2026-07-21, file 08 (R0587). The residual gap surfaced on 2026-08-06 as 372 Ai4 leads missing Event Name (R0389/R0149).
- **Bulk API patches must be filtered to our own records.** Pipedrive is shared with Marci and the memory team, who use other fields; the agreed filter is owner = Melisa/Sergey, or records carrying an LH campaign name, or records with the specific fields missing. — CONCERN by Melisa Draksler, 2026-07-27, file 07 (R0552) — the blast-radius question was addressed only by agreeing that filter.
- **"LinkedIn Member" on a profile means the person deleted their profile or blocked us.** — ISSUE by Araks Grigoryan, 2026-07-23, #lead-generation-team (R0368) — **open; no resolution or explanation found in ingested material.**
- **A wrong LinkedIn URL on a person record produces a wrong personalisation variable.** Resolved case: the wrong person's profile link was attached, forwarded to Stefan. — R0375, 2026-07-24.
- **Delayed acceptance on a stopped campaign** is expected behaviour (R0410) — see P11; the accepted response is the generic in-the-area template (P16, R0411).
- **A meeting that happened informally, after a recorded no-show/decline**, breaks follow-up logic. — ISSUE, Melisa Draksler / Araks Grigoryan, 2026-08-17, #lead-generation-team (R0408): "lead mentioned that they met at AI4, but our message says they didn't have a chance to meet" — resolved as "I checked with Rune and he actually met Brian".
- **Legacy backlog items are kept in the unified trigger-hypothesis list partly for authorship reasons.** The ClickUp "outbound hypothesis" backlog dates from 2024 and mixes genuine trigger signals with items that are not trigger campaigns at all; Sergey's stated reason for keeping them: "most likely he's not going to be happy seeing that we did not take this into account" (R0622, 2026-07-14).
- **Scraping ceilings and the ~30,000 list cap** — see P14 (R0820).

### Superseded / historical

- **Label wipes attributed to Pipedrive (07-27) → attributed to legacy Zapier automations (08-11).** Earlier: "we had two cases where I was actually filtering out leads and they just got updated for no reason … there is no backup for that … whenever you need to do something with pipedrive they are unpredictable" — Melisa Draksler, file 07 (R0551). Later, same symptom class, different cause: old Zapier automations silently stripping `3. Responded` / `4. Positive Reply` on person-field updates; 11 leads affected since Aug 5, all restored (R0218). **Both retained: R0551 is earlier and blames the vendor, R0218 is later and blames the legacy automation layer.**

### Contested

- **[CONTESTED] Is there a recovery path for wiped labels?** No (R0497, file 02). Yes, via our own before/after snapshots (Nik, same exchange; and R0162, 2026-08-14, dm-melisa: "We keep full before/after snapshots, so we can check exactly what happened to each" — **that request for 2–3 specific examples was never answered**).

### Not answered by the corpus

1. **What is the sanctioned repair procedure for a bad bulk write** — snapshot restore, manual, or accepted loss? R0497 vs R0162 disagree and R0162's evidence request went unanswered.
2. **Is a connection request withdrawn automatically if never accepted?** Asked in the 08-14 walkthrough, not answered, rolled into a follow-up ("it should exist somewhere. But … Nikita doesn't remember") — R0514, still OPEN.
3. **What is done about "LinkedIn Member" / blocked-us profiles** (R0368) — disqualify, DNC, or leave?
4. **The deal-closed outdated-task case:** "what should we do if there's a task outdated on a lead that is closed as a deal is created" — asked by Lule Salihu 2026-06-08, **never answered through 2026-08-18** (R0313); a related retrospective question is also OPEN (R0326).
5. **What is the rule when the same person appears in two concurrent event campaigns** (no multi-campaign view exists — R0513)?

---

# P16 — Outreach messaging & copy policy *(new part, authorised by owner ruling 2026-08-19)*

### Current understanding

- **Exact dates improve replies.** "in 80% of positive replies they mention which day works for them … and if you don't add exact time period, it makes communication worse" — Melisa Draksler, 2026-06-30, dm-melisa (R0059). This is the heuristic the London sprint copy was built on: "let's stay on I'll be in {{city}} from 27–31 July and thought I'd reach out" (R0058, DECISION, 2026-06-30, launched same day, subject "In London from July 27 to 31").
- **The highest-reply step of a sprint sequence is the email sent on, or two days before, the day the salesperson is on the ground** ("hey, I'm already in location"). — stated by Sergey Cujba, attributing the observation to Melisa and confirming it from his own Switzerland sprint, 2026-06-16, file 21 (R0908).
- **Email 2 is the one that gets replies, and is likely the first email that actually reaches the primary inbox** (email 1 often lands in a suspicious folder or spam). Therefore email 2 must read as a continuation of email 1 while still working as the first message the person sees. — stated by Sergey Cujba, attributing the observation to Melisa, 2026-06-16, file 21 (R0906). **The only deliverability-related copy rule stated on that call.**
- **Follow-ups are sent as empty-thread replies under the previous email.** — stated by Nik as standing practice, unopposed by Sergey, 2026-06-16, file 21 (R0911).
- **Templated copy is materially cheaper to ship than customised copy, because the sending identity is the head of sales.** With templates a campaign launches easily in the salesperson's name; with customised messages 20–30 messages must be reviewed together with him before sending, so the copy must be "as flawless as possible". — stated by Sergey Cujba, 2026-06-16, file 21 (R0907).
- **Approval-cost rule applied in practice:** for the UK sprint, go with one simple message that Toby will not need long to approve, deliberately unpersonalised, because "customized messages and personalized messages is something that is going to take time and we do not have it". — DECISION, 2026-06-25, file 18 (R0824).
- **Engineering profiles dislike flattery; pragmatic framing works better, "especially in Europe".** Sergey's objection to the "came across your profile" compliment opener, and his replacement pattern — "given that your work includes this and this" — plus the tone heuristic "in Europe they like pragmatism and a kind of respectful coldness". — CONCERN and stated heuristic, 2026-06-16, file 21 (R0900, R0902). Nik did not defend the line; it was folded into his rework commitment (R0940).
- **Free-form LLM copy is distrusted; give the model the positioning vocabulary and keep the variable space small.** Sergey's evidence is a September 2024 test he himself flagged as possibly out of date: "when you hand a fairly big chunk of email/message text over to the LLM … I imagine myself in the lead's place. What makes your take useful to me? … just give a person with engineering background something to catch on to and pick at. He will do it" (R0904). Related, no explicit ruling recorded: adding pitch decks to the model's context so it can connect relevance to key positioning points — "Elite Engineering Talent … PhD-level or 10x engineers" (R0901).
- **AI-written personalisation has a prior negative result on record** — "that was cold outreach … we sent email saying let's talk if you're interested. We had no replies at all — where we tried to do personalisation specifically through AI … our hypothesis was that people quite quickly saw it was AI-generated and did not react" — Sergey Cujba, 2026-06-16, file 21 (R0898). No measurement is cited; the "no replies at all" figure is from memory.
- **New copy is A/B-tested against the road-tested sequence, not substituted for it.** "for sales sprints our messages are, you could say, road-tested … but the messages that went well for Germany and well for Switzerland - we can test via A/B" — Sergey Cujba, 2026-06-16, file 21 (R0896); the same principle as an explicit two-party AGREEMENT with Melisa Bahonjić a few days later on a 500–1,000 contact slice, with Nik adding "You can even do like, I don't know, ABC test" (R0852, 2026-06-19, file 19). **No record in ingested material of whether either A/B was actually run or measured.**
- **Marketing-flavoured copy collapses reply rates.** "whenever it seems like anything marketing related, like reply rates drop to zero" — **Melisa Bahonjić** (not Melisa Draksler), from her own prior sprints, 2026-06-19, file 19 (R0851). She was explicitly unhappy with the existing Switzerland template and happier with the Germany one.
- **Nik's three-step personalisation design (presented as an example template):** (1) read the person's profile, map what they have done to our experience, and offer a friendly coffee with personalisation; (2) research what would be interesting for them to discuss given their position and what is trending in their industry; (3) the industry-topic email. — stated by Nik, 2026-06-19, file 19 (R0850). The per-lead industry-topic idea was accepted in principle and its wording rejected: "I like the idea itself. I would only work on the formulation" — Sergey asking for it to be more templated (R0903).
- **Do not rewrite the prospect's CV back at them.** "I think we should avoid rewriting their CV in messages as it looks very strange … add such feedback to your Claude projects/chat so that it can understand which patterns it should avoid" — DECISION by Melisa Draksler, 2026-07-23, #lead-generation-team (R0367); both BDRs confirmed compliance the same day.
- **Every message gets a final fine-tuning pass through Claude.** — DECISION by Melisa Draksler, 2026-07-31, #lead-generation-team (R0381): "Let's please make it a habit".
- **Approved template for delayed-acceptance follow-ups:** "Let it be something generic like 'I'll be in the area nearest months, so would be glad to meet in person when I'm back in [city]'" — DECISION by Sergey Cujba, 2026-08-17, #lead-generation-team (R0411).
- **Follow-up personalisation tiers by lead value:** high and medium value get personalised messages, low value gets something generic. — stated by Lule Salihu, 2026-07-30, #lead-generation-team (R0379).
- **Sprint sequence depth:** at least two emails per contact, matching Switzerland and Germany. — DECISION by Melisa Draksler, 2026-06-30, dm-melisa (R0051), restated as an agreement in #gtm-engineering the same day (R0254: "I think 2 emails will work because we also sent 2 for Germany and Switzerland").
- **Messaging changes on a sprint require the owning sales executive's approval** — see P13 (R0699).
- **A/B result on the LinkedIn connection note (2026-07-08):** revert to the Toby-approved message *with* a note (drop the blank-request variant) and accept ~10% acceptance as workable for the UK, on the reasoning "if we send … outreach to 400 people, we might potentially get 40 connections and out of 40 … at least 3, 5 meetings" — DECISION by Sergey Cujba, file 13 (R0698). **NB: this 400 is LinkedIn connection requests, not daily email capacity — see the P10 trap.**
- **For London, the automated first message was switched off and every accepted contact got a hand-written message** (only ~12 accepted, all high value). — DECISION, in force for the London sprint, 2026-07-03, file 15 (R0762). The decision predates the meeting ("we decided") and no author is named.
- **Four approved connection-request note templates** were running on the London/UK LinkedIn campaign, described as quite similar. — stated by Melisa Draksler, 2026-07-03, file 14 (R0723).
- **Sender persona must not change mid-thread.** Adding a sender persona pulls the sales executive into the thread (sprint inboxes forward to the individual executive), and switching sender mid-thread is stated to lose ~90% of replies — "especially when it comes to like engineering leaders". This is why extra mailboxes were rejected for the London sprint. — stated by Melisa Draksler, 2026-07-08, file 13 (R0697).

### Two passages awaiting an explicit owner ruling

The extraction deliberately declined to judge these. They are reproduced as quoted passages, with no editorial position, because the rulebook will have to state a policy either way.

1. **Sponsorship-intent framing used toward event organisers.** Melisa Draksler's existing practice for organiser outreach, endorsed in the room (Sergey: "Very good point. Very good point."; Nik: "That's cool. I agree."), 2026-07-10, file 12 (R0672): *"The way how I usually do it is that I reach out to them and I tell them that our management is interested in attending this specific event. But in order for us to get budget approval from the board, we need to have details about audience segmentation, access to the list of attendees and the networking gap and how many days before we will get access … I sometimes like to play dirty. So I mentioned like, oh, this is …"* — This is the only description in the corpus of how organiser outreach is framed. **Needs an explicit policy wording.**
2. **Attendee-scraping "workarounds at scale".** Same meeting, 2026-07-10, file 12 (R0676). Technical feasibility is explicitly separated from permission: *"[Nik] for those that have an app, for those that have a login of one website … we can scrape. I mean even tier ones … even if they don't allow scraping, you can scrape them if they have like an app or some possibility of logging / [Melisa] they also provide you like with the banner that says that they are not allowing scraping and reaching out with other attendees … they can basically like not let you in the [event]"* — with Sergey adding *"We can try to find some workarounds in this and if we can do this potentially at scale, I think that we definitely should try"*. **No decision or boundary was set in the meeting.** Related context: most Tier-1 conferences prohibit unsolicited outreach unless the company sponsors (R0669), and QCon was down-tiered precisely because it "doesn't allow cold outreach" (R0396).

### Superseded / historical

- **Blank LinkedIn connection request → connection request with the Toby-approved note (2026-07-08).** R0698 above.
- **Automated first message on the London LinkedIn campaign → hand-written message to every accepter (by 2026-07-03).** R0762 above.
- **Personalised AI-generated sprint copy proposed (2026-06-16) → accepted only as a scoped A/B, with three changes required** (drop the flattery opener, less free-form LLM text, more templating): "I am completely and fully open to experiments … but to try in the format of tests" — Sergey Cujba on Nik's proposal (R0897), rework commitment at R0940. **Partially delivered:** the re-transcription happened and the title-list expansion appears done by 2026-06-25; there is no evidence in ingested material of the point-by-point walk-back of the copy feedback, and the Thursday 2026-06-18 follow-up meeting the two agreed on does not exist in the calendar or transcript corpus.

### Contested

- No concurrent two-person disagreement on copy policy isolated. Note the **unmeasured basis** of most rules in this part: R0898 ("no replies at all") and R0904 (a September 2024 test) are both explicitly from memory; R0851 and R0902 are personal experience; R0906 and R0908 are Sergey relaying Melisa's observations. None is backed by a measurement in the corpus, and the only method stated for checking which template earned replies is manual inspection in Smartlead or Pipedrive (R0910).

### Not answered by the corpus

1. **Is the sponsorship-intent framing (R0672) sanctioned, and in what words?** It is currently standing practice with no written policy.
2. **What is the boundary on attendee scraping** where an event prohibits it (R0676)? Sergey invited "workarounds … at scale" and no line was drawn.
3. **Who approves outreach copy, at what stage, for which channels** — the sales executive is named for sprints (R0699), and Melisa/Sergey for structure, but there is no rule for event or trigger campaigns.
4. **Was any A/B ever run and measured** (R0852, R0896, R0709)? No result appears anywhere in the corpus.
5. **What is the standing position on AI-generated personalisation** given one negative memory (R0898) and one out-of-date test (R0904)? Templated-with-variables vs generated is decided ad hoc per campaign.
6. **Are pitch-deck / positioning materials allowed into the model's context** for copy generation (R0901, no explicit accept/reject)?
7. **How many touches, over what window, per contact per channel** — and does a person who was in a sprint campaign get a later event campaign?

---

# PRIORITY LIST — the 10 rulebook questions most worth Melisa's and Sergey's time

Chosen by operational risk (what breaks, how silently, and how expensively), not by how often they were asked.

| # | Question | Owner | Why it is worth their time |
|---|---|---|---|
| 1 | **Is Melisa's change-management rule set the standing policy?** (no Friday deploys, big changes at start of week, pre-notify everyone that automation is paused / replies not forwarded / Slack silent) — R0577, meeting-only, 2026-07-21 | Melisa + Sergey | The single clearest rule in the corpus exists only as one turn in one meeting, and its **advance-notification clause** was crossed by the 2026-08-05 (Wednesday) Zapier cutover; the reply channel then went dark, undetected until 08-10 (R0215). The no-Friday clause was not the one crossed. |
| 2 | **What is the DNC rule for a person with neither LinkedIn URL nor email** (1,019 persons, R0956) — block on name+company, or accept the gap? | Melisa | Every DNC failure mode on record ends in contacting someone we promised not to; the identifier gap is the one hole enrichment may not close. |
| 3 | **What is the real sending capacity** — per inbox, per sales executive, in total? 400 (R0040) vs 600 (R0251) vs a self-corrected per-inbox 20–25 (R0711) vs ~1,000 (R0933) | Melisa + Sergey | Every campaign plan and every event runway is sized off a number nobody can state; the London sprint's 34% shortfall was argued against a 7.5k target that was never traceable (R0052/R0150). |
| 4 | **Define MQL vs SQL** — entity level, attribute vs category | Sergey (+ Chrissy) | Asked of Nik *and* Sergey on 2026-07-10 and answered by nobody (R0650); absent anywhere in the Slack corpus. Reporting and the ICP-band work both sit on top of it. |
| 5 | **Write the ownership matrix** — what "infrastructure" includes and excludes, and who covers when Nik is out | Sergey + Melisa | Declared closed on 08-14 (R0432) and re-opened as a reliability demand on 08-18 (R0238); the boundary was still disputed on 08-11 (R0473). Bus-factor position (R0444) contradicts Nik's capacity statement (R0445). |
| 6 | **Confirm the forwarded reply-category set — three or four**, with exact category names | Melisa | A wrong category means the reply is never forwarded, no Slack post, no ClickUp task, no answer to the lead (R0581). One Slack answer says four (R0119), two meetings say three (R0579, R0539). |
| 7 | **Publish the label dictionary and state who adds the meeting label, on what trigger** | Melisa | No complete label list exists; labels gate reportability (R0543) and have no Pipedrive change log (R0497). Melisa's "I told you when we add the meeting label and how" is precisely this line. |
| 8 | **Rule the two P16 passages**: the sponsorship-intent framing toward organisers (R0672) and the attendee-scraping "workarounds at scale" exchange (R0676) | Sergey + Melisa | Both are current practice or invited practice with no written policy, and the sanction on record is removal from the event (R0676) — the only reputational-risk item in the map. |
| 9 | **Set the change-announcement protocol Nik→Melisa/BDRs** (channel, lead time, content) and the rollback/pause-window authority | Sergey | The reverse direction has a channel (R0520); this direction was proposed and ignored (R0036), deferred three times (R0180, R0191, R0193), and its absence caused the 07-17 workflow shutdown (R0093) and the 08-05 dark channel. |
| 10 | **Is R0318 an enforced invariant** ("every non-disqualified lead has an active task or nurturing mode on") — and what asserts it? | Sergey (stated it) + Melisa | Stated once in June as a standing rule, violated at scale in August (R0389, R0391), and never cited in either incident. Nik's monitoring explicitly does not cover Pipedrive-side state (R0475). |

**Runners-up** (high value, lower blast radius): the per-company contact cap — 2, 3 or 20–25 (R0783 vs R0821); whether a Zoho/CRM migration is real (R0556/R0557, absent from all Slack); who owns subscription renewals and expiry alerting (R0376); the "deal-closed outdated task" case open since 2026-06-08 (R0313); and Nik's still-unanswered request for reporting access (R0098).

---

*End of deliverable 3. Companion deliverables: 01_ANSWERED_BEFORE, 02_OPEN_ITEMS, 04_CONTRADICTIONS_AND_CHANGES, 05_CONCERNS_REGISTER, 06_COVERAGE_MAP, 07_EXEC_SUMMARY.*
