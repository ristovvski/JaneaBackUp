# Merge notes — obligations raised by batch agents (apply when merging _batches/*.json into ledger.json)

Ledger backup before any merge: `COMMS_AUDIT_build/ledger.json.bak-415` (415 records, R0001-R0415).

## ID block allocation
| Batch | Files | Block | Status |
|---|---|---|---|
| B1 | 01, 03 | R0416-R0455 | done (40 used, block full) |
| B2 | 04, 05 | R0456-R0495 | done (40 used, block full) |
| B3 | 02, 06 | R0496-R0535 | done (40 used, block full) |
| B4 | 07, 08, 09 | R0536-R0595 | running |
| B5 | 10, 11 | R0596-R0655 | running |
| B6 | 12, 13 | R0656-R0715 | launched |
| B7 | 14, 15 | R0716-R0775 | launched |
| B8 | 16, 18 | R0776-R0835 | pending |
| B9 | 17, 19, 20 | R0836-R0895 | pending |
| B10 | 21 | R0896-R0955 | pending |
| — | 22 | (none) | HELD as duplicate-of-21, pending Nik's keep/discard call |

NOTE: B1/B2/B3 each consumed their full 40-id block and had to consolidate weaker records.
B4+ were given 60-id blocks. Gaps in id sequence are expected and acceptable.

## Index corrections to fold into meeting_index.md
- (B1) file 03: the unstable LinkedIn account discussed is **Jim's**, not Mario's.
- (B1) file 03: the Mykyta/Stefan work split that file 03 defers was in fact settled in file 01.
- (B2) file 05 date: independent corroboration found — Nik's "today I'm a zombie man" matches
  dm-sergey R0206 dated 2026-08-05. Consider upgrading 05 from PROBABLE -> CONFIRMED(corroborated).

## Corrections to EARLIER ledger records (beyond each batch's own ledger_updates)
- (B2) R0205 / R0206 were marked "postponed then never revisited" — WRONG. R0483 (file 04, 08-11)
  is an explicit multi-party agreement on the communication protocol. Fix both statuses.
- (B2) R0180 / R0193 move from OPEN/deferred to **partially-answered** by R0483.

## Deferred tagging work
- (B3) 12 rulebook-relevant DECISION/AGREEMENT/ISSUE/PROPOSAL records in B3 have suggested
  rulebook parts listed in B3.json `notes` — parent should apply those tags at merge
  (schema keeps rulebook_part on PROCESS FACT/DEFINITION only, so decide whether to widen it).

## Contradiction pairs to preserve as pairs (never merge)
- Ownership definition: R0482 (Sergey, 08-05) vs R0493 (Nik) — root of the ownership thread.
- Ownership closure: R0432 (closed satisfactorily 08-14) vs R0238 (Sergey reopens as reliability demand 08-18).
- Bus factor: R0447 (Melisa concern) vs R0448 (Sergey "ready to be only with one person"), R0449 (Nik capacity) supports Melisa.
- Ai4 34% sync loss: R0132 (Make class defect, 08-04) vs R0488 (Melisa: one-campaign empty-LI-URL, 08-05).
- Double Slack notifications: Nik "years old" vs Melisa "started with HeyReach" (R0486).
- DNC label semantics: only explicit opt-outs (Speaker 2) vs everyone contacted via campaigns (Nik) — the 2,000-lead bulk-label incident sits on this gap.
- Paused-campaign replies: Nik 90% sure webhooks still fire vs team observation of no notifications (R0509/R0510).
- Capacity: R0040 "~400/day" vs R0251 "600/day" (from Slack, still unresolved).

## Nik's own unconfirmed items surfaced so far (for OPEN_ITEMS, listed first per brief)
- R0476: "I did not check if Stefan updated the message" (own admission).
- R0512: outbound-message sync patch + backfill — unconfirmed.
- R0515: three researched answers promised to BDRs — unconfirmed.
- R0531: client-contact "review status" design — unconfirmed.
- R0495: expected legacy cut-over "on Friday"; R0215 places Zapier shutdown same day as the meeting
  = origin of the Aug 5-11 alert blackout.

## Still-open questions for Nik (asked, unanswered)
1. File 22 — keep as reference artifact or discard? (garbled duplicate of 21)
2. File 19 — matched to "06-19 Sync (Melisa)" but transcript speaker is Melisa **Bahonjic**,
   not Melisa Draksler. If that calendar entry was with Draksler, the match is wrong.
3. File 20 — weakest match (All-team 06-18, but Toby/Mario/Jim absent). Drop to UNMATCHED?
4. Likely-missing transcripts: 07-16 HeyReach Sync (Nik org), 08-14 Task management (Mykyta/Stefan).

---

## B4 additions (files 07, 08, 09) — 60 records R0536-R0595, block full

- **File 09 = ZERO records** (correct restraint: phonetic gibberish, non-English audio mis-transcribed).
  One legible fragment logged in B4.json notes as observation only, NOT a record.
  RECOMMENDATION for Nik: re-transcribe file 09's source audio with Ukrainian/Russian selected.
- R0566 (07-21) is now the **earliest ingested ownership-handover statement**, predating the
  07-23 Slack asks (R0273/R0286) — update those two records' "earliest evidence" framing.
- **R0193 correction, cuts toward Nik**: Sergey answered the ClickUp half on 07-21 (R0595),
  six days BEFORE Nik re-asked on 07-27 and was deferred. Prime ANSWERED_BEFORE material.
- R0119 contested: forwarded-category count is three in both meetings vs four in Slack.

### New contradiction pairs from B4 (preserve as pairs)
- Handover scope: R0573 (Melisa, 07-21: monitor-and-learn, **explicitly not a rebuild**) +
  R0588 (migration window = **after Ai4**) vs what actually happened 08-04/08-05
  (rebuild + switch-off DURING Ai4).
- R0577 (Melisa, 07-21): full change-management rule set stated verbatim — no Friday deploys,
  pre-notify everyone — vs the Friday 08-05 Zapier cutover that caused the Aug 5-11 alert
  blackout (R0215, R0495). Rule was stated out loud, then crossed.
- R0586 (Nik, 07-21): flags "another automation rewrites mine" — THREE WEEKS before the
  Zapier label-stripping root cause was identified (R0218). Early warning, not acted on.

### Unverified claim to flag (not in Slack corpus at all)
- R0556/R0557: a rumoured Karol-led **Zoho CRM migration**. Appears nowhere in the Slack record.
  Worth asking Nik whether this is real — it would materially affect the rulebook if true.

### More of Nik's own loose ends (OPEN_ITEMS, listed first per brief)
- R0549, R0583, R0546, R0585 (see B4.json for detail).

---

## B5 additions (files 10, 11) — 60 records R0596-R0655, block full

- 6 ledger_updates: R0275 -> delivered late (transcript supplies a previously unrecorded
  Tue 07-21 due date for Nik's trigger estimates, chased 07-23); cross-ref adds on
  R0272, R0290, R0115, R0014, R0143.

### New contradiction / lapsed-decision pairs from B5
- **R0617: decision lapsed in 9 days.** Sergey ruled (Melisa assenting) that the DNC list is
  built BEFORE trigger campaigns. Observed sequence inverts it, and Sergey's own 07-23 Slack
  asks to parallelise. Record the rule, the inversion, and Sergey's own reversal as a chain.
- File 10's "integration incident" framing is THIN: the opening "everything is falling apart"
  complaint is never diagnosed or named in the meeting; Nik's 55:31 "should be working properly"
  is the contradicting later statement. Do not let the dramatic opening imply a diagnosed incident.
- R0648/R0649: Lilla raised wrong-company + model-unsure failure modes, then dropped her
  human-in-the-loop position on an unmeasured "reliable enough" assurance. Both sides recorded.

### NEW OPEN ITEM — definitional gap never closed anywhere in the corpus
- **R0650: MQL vs SQL data model.** Lilla asked Sergey directly (07-10); he did not answer.
  The terms MQL/SQL appear NOWHERE in R0001-R0415 (the entire Slack corpus). This is a genuine
  never-answered definitional question -> belongs in OPEN_ITEMS and in rulebook P10
  (field dictionary) as a question the corpus does NOT answer, i.e. it needs Melisa/Sergey time.

---

## B7 additions (files 14, 15) — 60 records R0716-R0775, block full

- 10 ledger_updates: R0064 -> delivered (the 07-02 promised LinkedIn call IS file 15);
  R0027 -> explicit HeyReach adoption decision now dated 07-03; R0057 -> concern explicitly
  disposed of; R0180 -> partially-answered (Sergey's estimate/transparency norm + Nik's explicit
  yes, but STILL no mechanism); cross_ref adds on R0106, R0345, R0049, R0322, R0182, R0257.

### *** HEADLINE FINDING — the "I told you" question, adjudicated by evidence, both directions ***
- **R0741** — Melisa's 07-03 claim to Sergey "I explained the overall end to end process" is now
  datable AND boundable against the actual recording of that walkthrough (file 15):
    - DID cover: LinkedHelper stages, labels, activity logging, notifications, nurture chain.
    - Did NOT cover: the meeting-label / deal rules — i.e. exactly what is disputed on 08-18 in
      R0165 ("I told you when we add the meeting label and how").
  => The GENERAL claim is well-founded; the SPECIFIC 08-18 claim is not supported by this recording.
  This is the core ANSWERED_BEFORE / "I told you" material. Present neutrally, both halves together.
- Cutting the other way (supports Melisa): **R0756** (manual label/source-channel maintenance) and
  **R0767** (reply-without-accept gap, ~3-4 per campaign) were BOTH stated aloud in the 07-03
  recorded walkthrough, BEFORE the Slack messages later framed as "I told you"
  (R0106 on 07-20, R0345 on 07-06). Those specific claims ARE supported.

### New contradiction pair from B7 (rule reversed inside 30 minutes, same day)
- R0775 (Melisa, 07-03 09:30): buy ONE LIGHT seat, test on Sergey's profile
  -> superseded at 10:00 by R0740 (Sergey registers HeyReach **Growth** trial), on exactly the
  API-capacity caveat Nik had attached. Keep as a pair; note 15 precedes 14 within the day.

### Index correction
- Row 14: the "LinkedIn credentials" referenced are actually **HeyReach** credentials
  (consistent with the 07-03 entry in slack_audit/redactions.md).

---

## B6 additions (files 12, 13) — 60 records R0656-R0715, block full

- 7 ledger_updates: R0180 + R0036 (Sergey states an align-before-you-change + ClickUp reporting
  protocol on 07-10 — substantive PARTIAL answer to the standing comms-protocol gap, but never
  written down, then re-deferred 07-17 and 07-27); R0068 (provenance for the Toby-connections
  export, requested 07-10 after Nik flagged it agreed-but-never-started); R0251 (third capacity
  data point); R0150 + R0052 (in-meeting counts ~1,500 sent + 3,300/1,200 uncontacted corroborate
  the ~5,900 population and further undermine the 7.5k target); R0009 (BDR follow-ups moved to
  Melisa, Sergey agreeing).

### CAPACITY CONTRADICTION — narrowed, NOT settled (do not present as resolved)
- Third data point, file 13, 07-08, Nik 25:54: "Okay, I've made like 50, 25 per day. That's going
  to be our biggest number we can send per inbox." => a per-INBOX daily max, self-corrected
  mid-sentence (50 -> 25), so NO single number is asserted. 20-25/inbox is arithmetically
  consistent with R0040 (~400/day across Toby's inboxes) but no inbox COUNT is ever stated.
  Conclusion: R0040 vs R0251 conflict is narrowed, still unresolved. Say so plainly.
- **TRAP — do not merge:** Sergey's other "400" (400 LinkedIn requests -> 40 connections ->
  3-5 meetings) is a TWO-WEEK LINKEDIN volume, not daily email capacity. Keep separate from R0040.

### New systemic finding (rulebook P6 / P11)
- DNC coverage hole stated 07-10: suppression matches on **LinkedIn profile URL**, so leads with
  no LI URL are **silently never blocked**. Predates Nik's DNC scoping commitment (R0115) by 11 days.
  This is a defect in the suppression logic itself, not a process lapse.

### Unresolved meeting-internal contradiction (record both ways)
- Melisa's temporary-presence sprint rule vs Sergey's later "I'm here around, living here" variant.

### Flagged for NIK's explicit rulebook wording — deliberately not judged by the agent
- The sponsorship-intent framing used toward event organizers.
- The attendee-scraping "workarounds at scale" exchange.
(Both are policy calls for the owner, not the auditor. Present as quoted passages needing a ruling.)

### Housekeeping
- B6 wrote no task-log file. Per the standing task-log rule, the PARENT session must write
  task-logs/2026-08-19_<slug>.md covering this whole comms-audit run at merge time.

---

## OWNER CORRECTION — 2026-08-19 (Nik, in terminal) — DNC coverage hole

*** SUPERSEDES the B6 finding above. Apply at merge; do NOT delete the earlier record. ***

- The B6 note said DNC suppression matches on **LinkedIn profile URL only**, so leads without one
  are silently never blocked. That is an OVERSTATEMENT of the actual system.
- CORRECTED, authoritative, per the owner on 2026-08-19:
    - The current system matches on **LinkedIn OR email**.
    - The residual gap is therefore only persons with **NEITHER** identifier: **1,019 persons**.
    - An **enrichment fix is IN FLIGHT** as of 2026-08-19.
- Handling per brief discipline (later evidence supersedes; contradictions kept as pairs, never merged):
    - KEEP the 07-10 transcript record as-is — it is what was actually said in that meeting,
      and the fact that the understanding was narrower then is itself evidence.
    - ADD a new record carrying this correction, cross-referenced to it, marked as the later
      and authoritative state.
    - Mark the earlier record's status as superseded-by-<new id>.
- PROVENANCE FLAG: this correction comes from the owner directly in the terminal, NOT from the
  Slack or transcript corpus. Source must read "owner correction (Nik, terminal) 2026-08-19"
  so it is never mistaken for an in-corpus quote. Reserve **R0956+** for owner corrections
  (B10 occupies up to R0955).
- Knock-on: the DNC records this touches (R0022, R0026, R0034, R0043, R0115, R0120, R0617, and the
  B6 DNC record) should cross-ref the correction so the rulebook P6 section states the CURRENT
  system, with the 07-10 understanding shown as historical.
- Also note for the rulebook: "1,019 persons with neither identifier" is a measured figure as of
  2026-08-19 — date-stamp it, since it will move as enrichment lands.

---

## B9 additions (files 17, 19, 20) — 39 records R0836-R0874 (R0875-R0895 unused, correctly not padded)

- 3 ledger_updates: R0010 (Sergey independently corroborates the one-BDR-per-conference ceiling,
  06-18), R0019 (event-capacity concern raised AGAIN and deferred, not resolved), R0016 (ClickUp
  access-assumed-by-onboarding recurred for Lule and Araks).

### Zoho rumour — NOT supported
- File 17 has ZERO mentions of Zoho / CRM migration / Pipedrive. Karol's self-stated remit is
  content, pitch decks, website project (R0837). Evidence AGAINST the 07-21 rumour (R0556/R0557),
  though not disproof. Karol appears nowhere in R0001-R0415 either.
- File 17's real content: his LinkedIn thought-leadership AI-agent proposal (R0838), previously
  declined by an agency, + 3 commitments, none verifiable in ingested material.

### File 19 — DISPUTED anchor ownership stands, date supported
- Date SUPPORTED: call closes "Have a great weekend / See you Monday"; 2026-06-19 was a Friday;
  content maturity fits mid-June.
- Anchor OWNER unresolved: Melisa **Bahonjic** speaks with full GTM authority (owns prior sprint
  results, directs Nik's task routing, tracks his ClickUp onboarding tasks). So "the 06-19 Sync was
  with Bahonjic" is at least as plausible as a mis-match to Draksler's meeting.
- HANDLING: keep date_confidence DISPUTED; attribute nothing to Draksler. STILL NEEDS NIK'S CALL.
- TRANSCRIPTION BLOCKER: the token "janeasystems" appears 11x in file 19 ONLY, standing in for BOTH
  Clay AND an unidentified male colleague. It blocks a clean read of the Jim-escalation rule (R0857).
  Flag R0857 as partially-unreadable rather than asserting the rule.

### File 20 — DOWNGRADED (parent decision, 2026-08-19)
- Match is genuinely weak: NO date/weekday/"today" signal anywhere, and Toby/Mario/Jim are
  EXPLICITLY absent (not merely silent). June is supported (Rune onboarded "in the last month",
  Ai4 ~7 weeks out); the specific 06-18 All-team anchor is not.
- DECISION APPLIED: set file 20 to **month-level "2026-06", anchor UNMATCHED**, date_confidence
  WEAK/month-only — consistent with Nik's own standing instruction that unmatched files stay UNKNOWN.
  Do not keep the 06-18 All-team label. Reversible if Nik prefers the original.
- Despite the weak date, file 20 is the batch's RICHEST P5 source: prior-edition Ai4 baseline
  (104 positive replies, 27 meetings for Mario, 8-10 quality meetings/person/day) and the
  end-of-2025 closure of the Nvidia/Microsoft networking apps. Keep all of it.

### *** RULEBOOK TAXONOMY GAP — structural, needs a new part ***
- P1-P15 has NO home for **outreach-messaging / copy policy**, which records R0850-R0852 keep
  producing (and B10's outreach-sequence review will produce more).
- RECOMMEND proposing **P16 = outreach messaging & copy policy** to Nik. Until he rules, tag such
  records rulebook_part: null and list them under a "no rulebook home" heading so they are not lost.

---

## B8 additions (files 16, 18) — 60 records R0776-R0835, block full

- 10 ledger_updates: R0032, R0033, R0039, R0026, R0034, R0042, R0040, R0014, R0037, R0119.

### *** R0032 / R0033 DEADLINE DISPUTE — direct evidentiary result. FRAME CAREFULLY. ***
- File 16 IS the 06-29 meeting (the date Melisa/Sergey say the deadline was communicated
  to Nik "multiple times").
- Full-text search of file 16 for deadline / "end of last week" / "multiple times" / "told you" /
  "pointed out" => **NOTHING**. Sergey is present for the entire call and never raises timing.
- What the meeting LITERALLY shows is closer to the opposite framing (R0800):
  Nik: "Do you want to launch this today?" / Melisa: "Yeah, ideally I think we could launch this
  today, but ... we first need to finish filtering".
- Nearest adjacent evidence, file 18 (06-25), R0824: Sergey "so we can really launch like this week"
  + Melisa "we can launch campaign tomorrow probably" / "if we want to start this week"
  => SHARED INTENT, not phrased as an instruction to Nik, not the firm deadline attributed to Sergey.
- *** REQUIRED FRAMING: this is ABSENCE OF EVIDENCE in the two recorded meetings from the disputed
  window — NOT disproof. The deadline may have been conveyed in an unrecorded call or in a channel
  outside the five audited sources. Do NOT adjudicate. State what the recordings do and do not
  contain, and stop there. This is what keeps the finding usable in front of Melisa rather than
  reading as an accusation. ***

### Other high-value B8 finds
- **R0798 closes the capacity causal loop**: the 06-29 decision to use ONLY Toby's inboxes is the
  ORIGIN of the ~400/day shortfall threaded through R0040 / R0053 / R0251.
- **R0826 vs R0816** — same-meeting contradiction on whether the outreach spec document exists:
  Sergey assumes it does; Melisa: "No, we don't have that." Keep as a pair.
- **R0827 / R0828** — full PRE-migration integration topology: LinkedHelper native -> Pipedrive,
  Make = Smartlead only, Zapier = labels on stage change, Pipedrive Automations = tasks.
  Dense P14 / P2 rulebook material.
- **R0819** — Nik asked for formal responsibility on 06-25, ~4 weeks before the 07-21 ownership
  kick-off, and received NO explicit yes. Relevant to the whole ownership thread's origin.

### Change pairs flagged (never merge)
- Per-company cap: 20-25 (06-25) -> 2 (06-29).
- Toby LinkedIn cap: 600 -> 800.
- HeyReach "not possible" (Melisa, Feb) vs the integration actually landing 07-13.

### Index corrections
- File 16's timestamp reset is **00:00**, not 00:53 (00:53 belongs to file 19). Fix the index's
  boundary-method note.
- Files 16 AND 18 both now have same-day Slack corroboration => both upgradeable from
  PROBABLE to **CONFIRMED(corroborated)**.

---

## CORRECTIONS TO THESE MERGE NOTES (2026-08-19) — errors found during synthesis

*** These correct MY OWN earlier entries above. The earlier text is left in place for audit trail
but is WRONG where contradicted here. ***

1. **"Friday 08-05 cutover" is WRONG.** 2026-08-05 was a **WEDNESDAY** (verified programmatically).
   - The clause of R0577 actually crossed by the 08-05 Zapier cutover is the **advance-notification**
     clause, NOT a no-Friday-deploys clause.
   - Nik's "Friday" in R0495 referred to his EXPECTATION of the cutover date; the actual Zapier
     shutdown happened the same day as the 08-05 meeting.
   - The finding stands (rule stated aloud 07-21, then crossed, causing the Aug 5-11 alert blackout);
     only the weekday claim was false. Corrections were sent to the two synthesis agents mid-flight.
   - VERIFIED WEEKDAYS — do not infer: 08-05 Wed · 08-11 Tue · 08-14 Fri · 08-18 Tue · 07-21 Tue ·
     06-29 Mon · 06-19 Fri. (06-19 Fri corroborates file 19's "See you Monday" close.)

2. **Bus-factor concern is R0443, NOT R0447.** R0447 is a separate concern from the same meeting
   about the cost of repeated verbal explanation — and it MATERIALIZED 9 DAYS BEFORE it was raised
   (R0490), which is a finding in its own right, not a lead-time.

3. **R0236 cannot be cited as an early warning** for the misses it appears to predict — it
   POST-DATES them. Lead time for that chain must be measured from Sergey's earlier R0358.

4. **R0012 is ANSWERED** (by R0071, 41 days later) — not "deferred to a call and never resolved"
   as an earlier batch and my own summary stated.

### Longest intervals found (from the concerns register)
- Warning -> materialization: **50 days** (R0026 06-25 "I forgot the DNC update" -> the 08-14
  ~2,000-lead label event, R0496).
- Standing-protocol question R0180 runs **53 days** to its last recurrence (R0165, 08-18).
- Longest UNDETECTED-defect window: **~90-120 days** (R0106, LinkedHelper auto-labeling broken
  since ~April, discovered July).

5. **Bus-factor record IDs in these notes were WRONG.** Verified during synthesis:
   - correct trio = **R0443** (Melisa, bus factor) / **R0444** (Sergey, "ready to be only with one
     person") / **R0445** (Nik, capacity limit).
   - **R0447** is an UNRELATED concern (the cost of repeated verbal onboarding/explanation), which
     separately materialized 9 days BEFORE it was raised (R0490).
   - Every earlier reference in these notes to "R0447/R0448/R0449 = bus factor" is wrong; the
     synthesis deliverable 04_CONTRADICTIONS.md carries the corrected ids.

6. **DNC label semantics is a THREE-WAY spread, not a pair** (all within 08-11 to 08-14):
   R0456 (broad) / R0498 (narrow, label-scoped) / R0499 (Nik) / R0407 (Slack, "every lead") / R0424.
   The ~2,000-lead label incident (R0496/R0497) sits on the **list-vs-label seam**, and there is
   **no Pipedrive label change log** — so the mislabelling cannot be audited or reversed from
   Pipedrive itself. That last point is operationally the most important consequence in the corpus.

7. **Six contradiction pairs these notes MISSED** (now in 04_CONTRADICTIONS.md):
   R0569 vs R0570 (is the handover actually relieving Melisa's burden?) · R0596 vs R0627
   (integration "not working" vs "should be working", same meeting, 55 min apart) · R0494
   (Nik/Stefan Ai4 split held differently by each, never adjudicated) · R0559 (field-overwrite
   belief contradicted with evidence, patched same day) · R0690 vs R0691 (sprint temporary-presence
   rule vs Sergey's always-here variant) · **R0037 vs R0810** (Nik declines ClickUp tracking in the
   DM and lets it pass unopposed in the meeting the SAME DAY — cuts toward Nik).

### Lesson for any continuation
Batch agents' *summaries* drifted on record ids in at least two places (bus factor, and the R0447
mix-up) while their JSON was correct. Verify ids against ledger.json before quoting them; do not
trust a prose receipt as the source of truth.
