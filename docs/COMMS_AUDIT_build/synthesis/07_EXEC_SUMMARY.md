# EXEC SUMMARY — communication audit, 2026-05-28 → 2026-08-18

**Corpus:** 3,558 Slack messages across 5 sources + 21 recorded meetings → **937 typed records**, every one carrying a verbatim quote, date, source and status.

**Read this as patterns, not persons.** Every pattern below is instantiated by all three principals. Nothing here is a verdict on anyone; the ledger records what was said, by whom, when, and what happened to it.

**Standing limit on every claim:** this audit covers five Slack sources and 21 recorded meetings. It does **not** cover unrecorded calls, huddles, or channels outside those five. Wherever this document says "never answered" or "not found", it means *not present in the ingested corpus* — never *proof it did not happen*.

---

## Pattern 1 — Rules get stated, then lost

Not disputed rules. *Agreed* rules that stopped operating, mostly without anyone noticing.

- **9 rules were stated aloud in meetings and never written anywhere in Slack.** The clearest: Melisa's change-management rule set (R0577, 07-21), including advance notification before changes. Its advance-notification clause was crossed by the 08-05 Zapier cutover, producing the **Aug 5–11 reply-alert blackout** (R0215, R0495). *(08-05 was a Wednesday; the separate no-Friday-deploys clause was not the one crossed.)*
- **12 rules demonstrably changed**, and the audit records for each whether the change was ever announced. Most were not. One reversed **within 30 minutes**: a HeyReach light seat agreed at 09:30 (R0775) became a Growth trial by 10:00 the same day (R0740).
- **Decisions lapse in days.** Sergey ruled — with Melisa's explicit assent — that the DNC list is built *before* trigger campaigns (R0617). Nine days later Sergey's own Slack message asked to parallelise them.
- **The handover was scoped, then didn't happen as scoped.** Agreed 07-21 as monitor-and-learn, explicitly *not* a rebuild (R0573), with migration *after* Ai4 (R0588). What happened on 08-04/05 was a rebuild and switch-off during Ai4.
- **Defects survive because nothing watches them.** LinkedHelper auto-labeling was silently broken **~90–120 days** before discovery (R0106). The DNC-update step was forgotten twice in four days (R0026 → R0034); 50 days later the ~2,000-lead label event landed (R0496).

**What this costs:** 12 raised concerns later materialized. The longest warning-to-event gap was **50 days** — time that was available and unused.

---

## Pattern 2 — Questions get answered, then re-asked

In **both** directions, with evidence on both sides. 15 "I told you"-type claims were tested against the record; **5 were Nik's own**.

- **Toward Nik:** Sergey answered the ClickUp/reporting question on 07-21 (R0595) — *six days before* Nik re-asked it and was deferred (R0193). Sergey had already offered Nik ownership of the nurturing workflow on 06-16 (R0949), two weeks before Melisa did (R0061); Nik misattributed it to Stefan and re-asked twice (R0065, R0117). Nik's own recall claim at R0155 is **not found** in the corpus, and at R0476 he concedes he never verified whether Stefan updated the messaging.
- **Toward Melisa:** two things she was later accused of not communicating — the manual-labeling requirement (R0756) and the replied-but-never-accepted gap (R0767) — **were stated aloud** in the 07-03 recorded walkthrough, *before* the Slack messages framed as "I told you" (R0345 07-06, R0106 07-20). Those claims are supported.
- **The mechanism that kills items is deferral.** R0180 (Sergey asks Nik how he will communicate status, 06-26) → deferred → R0190 → R0192 (a Monday sync skipped because neither party remembered its purpose) → R0193 (Nik re-asks, deferred a third time) → R0165 (08-18). **53 days.** In that entire chain there is exactly **one** explicit multi-party agreement — R0483, 08-11: announce absence in advance and name a cover.

### The two sensitive cases — required framing

**The 06-29 deadline dispute (R0032 vs R0033).** File 16 *is* the 06-29 meeting. It contains no mention of a deadline, and Sergey is present throughout without raising timing; what it shows is Nik asking *"Do you want to launch this today?"* (R0800). On 06-16 Nik had asked for a launch deadline and received only *"the earlier the better"* (R0955). **Across the recorded corpus the deadline is not shown being communicated — and that is absence of evidence, not disproof.** No verdict is offered on who is right.

**The "I told you" adjudication (R0741).** Melisa's 07-03 claim that she "explained the overall end to end process" is bounded against the actual recording: it **did** cover LinkedHelper stages, labels, activity logging, notifications, the nurture chain. It **did not** cover the meeting-label/deal rules disputed on 08-18. The general claim is well-founded; that specific one is unsupported by that recording. Notably, the **first statement of the meeting-label rule anywhere in the corpus is R0164 — the same day as the dispute.**

---

## Pattern 3 — Load-bearing words were never defined

Every escalation in this corpus runs through a word nobody pinned down.

| Word | State | Consequence |
|---|---|---|
| **ownership** | Sergey's definition (R0482, 08-05) and Nik's build-maintain-propose definition (R0493) were never reconciled; still undefined 08-11 (R0473); "closed" 08-14 without borders; reopened as a reliability demand 08-18 (R0238) | the longest-running dispute in the corpus, and it is definitional, not personal |
| **do not contact** | a **three-way** spread inside 08-11 → 08-14: broad (R0456), label-scoped (R0498), Nik's (R0499), "every lead" (R0407) | ~2,000 leads mislabelled on the list-vs-label seam — **and Pipedrive keeps no label change log, so it cannot be audited or reversed there** |
| **capacity** | four live figures: ~400/day (R0040), 600/day (R0251), per-inbox 20–25 self-corrected mid-sentence (07-08), ~1,000 | sprint planning has no agreed denominator |
| **MQL / SQL** | Lilla asked Sergey directly on 07-10 (R0650). Unanswered. The terms appear **nowhere** in all 415 Slack records | the lead model has no shared vocabulary |
| **reply category count** | three (two meetings) vs four (Slack) — R0119 / R0539 / R0579 | routing rules disagree with themselves |

---

## The state of the ledger, plainly

- **88 of 131 commitments** are not plainly delivered. **Nik holds 40+** — the largest single block, grouped in `02_OPEN_ITEMS.md` by kind rather than as one undifferentiated list.
- **18 questions** remain unanswered; the two BDR questions have been open **72 and 57 days**.
- **15 proposals** received no response — including **the last message in the entire corpus** (R0415, 08-18 14:23), a BDR nurture-policy change. Nobody replied, so **the policy is now set by default.**
- **Most time-sensitive:** Sergey's 08-18 request for a plan and timeline (R0238) was answered only by *"Won't post reports just consider everything fixed"* (R0240), while R0228 / R0229 / R0231 were still open by name.
- **14 records carry contested status** — different readings of the same evidence. They are surfaced as `[CONTESTED]` with both readings throughout, for the owner to resolve.

---

## Three things worth doing before anything else

1. **Define ownership in writing** — scope, boundaries, and who covers when Nik is out. It is the root of Pattern 3 and of the 08-14 → 08-18 whiplash.
2. **Answer R0238 with an actual plan and timeline**, naming R0228 / R0229 / R0231. It is yesterday's ask from the director and the one item guaranteed to resurface.
3. **Ratify or discard R0577 as standing policy.** Nine rules currently live only in meeting audio. Writing down one rule set — the change-management one — would have prevented the corpus's most expensive incident.

---

*Full evidence: `01_ANSWERED_BEFORE.md` · `02_OPEN_ITEMS.md` · `03_RULEBOOK_MAP.md` (P1–P16) · `04_CONTRADICTIONS.md` · `05_CONCERNS.md` · `06_COVERAGE_MAP.md`. Ledger: `ledger.json` / `ledger.md`. Provenance note: records R0956–R0958 are owner corrections supplied in terminal on 2026-08-19 and are marked OUT-OF-CORPUS — authoritative about the present system, never citable as something Melisa or Sergey said.*
