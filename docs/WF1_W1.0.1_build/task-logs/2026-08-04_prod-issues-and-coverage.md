# Task log — 2026-08-04 — two production issues + Melisa's coverage check

**Scope as given:** (1) Make lead-creation failure — verify Stefan's required-field diagnosis
read-only, quantify the hole, check the example lead and Slava's manual creations, confirm WF-2
immunity, prepare a dry-run backfill. (2) Double forwards — reconcile our forwards against the
complaint window, and prove zero forwards since the window closed. Then (3) a coverage report
answering "are all leads we contacted now in Pipedrive?" across every campaign.

**Mode:** read-only throughout. No Make scenario, hook, campaign or account setting touched. WF-1
stays `e28d282b`, WF-2 stays in shadow. The only files written are evidence/report/script files.

---

## What was done, and what it proves

### Issue 2 — double forwards (this was taken first: a gate breach would be the most serious finding)

- Audited **all 267 retained WF-2 executions**. **Zero forwards and zero writes of any kind after
  the window closed at 2026-08-03T08:58:51Z.** The WRITE_MODE gate holds — P1 closed negative.
- Cause of the doubling **confirmed**: Make's *active* scenario 8557478 (the reply-label scenario)
  contains **14 hardcoded `POST /campaigns/{id}/forward-email` calls**, one per owner. Ours + theirs
  = two copies.
- The obvious suspect was wrong: `Janea Auto-Forward Automation` (3277897) is **inactive, zero log
  entries ever, last edited 2025-01-22**. Anyone asking "is Auto-Forward off?" gets a true answer to
  the wrong question. The forwarding lives inside a scenario whose name says "update lead with
  responded label".
- Evidence is sub-second alignment between Make runs and our executions (5 pairs), with a natural
  control: Make's 08-03T16:54:53Z run had **no** twin because we were already back in shadow → one
  copy. That control is what turns correlation into cause.

### Issue 1 — lead creation

- **Stefan's required-field diagnosis is disproved.** Of 115 person fields, the only
  `mandatory_flag: true` ones are Pipedrive's own built-in read-only fields (`edit_flag: false`).
  All 11 custom fields Make writes — including both suspects, `lh_linkedin_profile_url` and
  `LinkedIn Profile` — are not required. **Nothing needs un-requiring**, so the action item that was
  queued for Marci/Melisa is unnecessary.
- The hole is real and larger than the framing: **891 Ai4 prospects contacted, 300 (34%) have no
  Pipedrive person**, loss uniform 18–43% every hour (so not an outage or rate-limit spike).
- **Three defects found** in scenario 8557031, in order of harm:
  1. Persons are matched **by NAME** (`exact_match`, `limit 1`) → 58 prospects have leads attached to
     a *different human* (`pii-9e8228ef@example.invalid` → person at `pii-9f60732e@example.invalid`). Live corruption,
     growing every run. Same antipattern W1.0.11 banned for us.
  2. Modules 16/29/2/18 all carry **`builtin:Ignore`** → 40/40 runs log as *successful* while people
     vanish. This is why nobody could diagnose it: the design discards the evidence.
  3. Module 28's regex `\[([^\]]+)\]` with **`continueWhenNoRes: false`** → a campaign name without
     square brackets silently switches lead creation off entirely.
- Example lead `74e0d0b0-8ddf-11f1` confirmed: Person-6b93835c, person 84958, created by Slava
  2026-08-01T19:30:30Z — a day after we forwarded his reply.
- WF-2 immunity **cited, not asserted**: static B4 (empty-omit) and B27-3 / B27-11 (resolution by
  verified email, never name — so defect 1 cannot happen to us by construction).
- Backfill written, dry-run clean, **never executed**: 300 would be created, 810 empty custom fields
  omitted, 0 already present on per-row email re-verification. Gated on `WRITE_MODE=live`.

### Coverage report (Melisa)

- All **107** campaigns that ever sent, 103,677 send events → **42,039 unique prospects contacted,
  5,469 missing (13%)**.
- The distribution is the finding: a set of older lists is missing **almost entirely**
  (Ag Tech Catch-alls USA 739/742, Other Ex-Microsoft 185/185) while `Ag Tech - Valids - USA` is
  727/727 present and 16 campaigns are at 0%. That reads as **whole lists emailed but never loaded**,
  not a trickle of failures — a different problem from the Ai4 defect.

---

## Partially solved / unconfirmed — do not read these as settled

- **242 of the 300 Ai4 prospects have neither a person nor a lead**, so the flow died before the
  router — but **which module** is unconfirmed. I will not name one without the artifact.
- **The near-100% gaps on older campaigns are undiagnosed.** I observed the pattern (catch-all lists
  consistently worse) and deliberately did not theorise a cause. They predate the current automation
  and were outside this task's scope.
- **Trigger delivery**: 8557031 last ran 2026-07-31T08:45:51Z while Ai4 kept sending to 19:53:26Z —
  ~850 send events, zero runs. Those were follow-up steps to already-contacted leads, so they add no
  new names to the 300, but the delivery gap itself is unexplained.
- **Persons added by hand is not measurable** (see blockers). Reported as a limitation, not a number.

## What blocked me

| blocker | consequence |
|---|---|
| Make `GET /dlqs` rejects every parameter combination our token can send (HTTP 400 `Expected required property / Expected integer`) | the verbatim Pipedrive rejection text for the 242 is unavailable; that hop stays unconfirmed |
| Make `GET /scenarios/{id}/logs/{executionId}` and `/bundles` both 400 (`Validation failed for 1 parameter(s)`) | no per-module bundle detail, so the Ignore handlers' swallowed errors cannot be recovered from the API at all |
| Smartlead `/campaigns/{id}/webhooks` returns `[]` for every campaign, `/webhook` is 404 | cannot verify from the API whether Make's webhook is still registered, even though both scenarios demonstrably receive reply events |
| **Pipedrive exposes no person-creator field** — absent on `/v1/persons` and `/api/v2/persons`, and `include_fields=creator_user_id` is rejected | "how many persons did Slava patch by hand" is unanswerable from the API; only the UI changelog holds it |
| The 300-person backfill and the 58-lead repair need Melisa/Marci's go | both prepared, neither run |
| Gmail relay of the two misrouted review forwards (`pii-cc63be0d@example.invalid`, `pii-f38c7b54@example.invalid`) is Nik's action | I cannot see his inbox; still open |

## Mistakes I made and corrected — worth knowing because two nearly reached you

1. **I nearly reported the wrong mechanism.** My hypothesis was that Make's create-person branch was
   unreachable (search returns zero bundles → router never fires). The test refuted it: **525
   persons were created at send time**. Had I written the report one step earlier it would have been
   confidently wrong. The route-0 test existed only because I asked "what would disprove this".
2. **`creator_user_id` silently fell back to `owner_id`.** My earlier statement "87 of the newest 100
   persons created by Melisa" was owners, not creators — Pipedrive returns no creator for persons at
   all. Corrected in the coverage report; the generator script now carries a comment so a re-run
   cannot reproduce it. Same class as the label-clobber lesson: `creator_id` ≠ author.
3. **I nearly blamed our own live window.** Make went silent 2m21s after the window opened — an
   uncomfortable coincidence I took seriously. Checking first-send dates killed it: **0 of the 300
   were first contacted after that cut**; the gap is older and chronic. Coincidence, not causation.
4. Minor: `MAKE_ZONE` holds the bare zone (`eu2`), not a hostname. `Select-Object -Last N` buffers a
   whole pipeline, so a long background run gives no interim progress — pipe to a file instead.

## What can be improved

- **Fix defect 1 before the backfill.** The backfill cleans up history; the name-matching keeps
  producing corruption every run. Cleaning first and fixing later means doing it twice.
- **The `Ignore` handlers are the real problem.** Three defects hid behind them for weeks. Any
  scenario that swallows errors is unobservable by construction — this is the same argument that
  produced WF-ERR on our side, and it applies to Make's scenarios verbatim.
- **Defect 3 deserves a guard, not a rule.** "Never rename a campaign without brackets" is a promise,
  and a promise is not a control — the same lesson as the WRITE_MODE-expiry watchdog. A cheap check
  that alerts when an active campaign's name stops matching the bracket contract would be real.
- **Decide forwarding ownership before the WF-2 flip.** Router 82 off, or our forward stays gated.
  Currently on the flip checklist as a blocker.
- **The 5,169 older missing prospects need a business decision**, not engineering: import them or
  accept the gap. Worth asking Melisa explicitly rather than leaving it implied in a table.
- Reconciliation took ~40 minutes of API pagination. If it is going to be asked repeatedly, the
  sent-lists should be cached to disk with an incremental refresh.

## Files produced

| file | what it is |
|---|---|
| `wf1-release-evidence/PROD_ISSUES_2026-08-04.md` | team-facing report for Stefan/Melisa/Marci |
| `wf1-release-evidence/MELISA_COVERAGE_REPORT.md` | Melisa's one-line answer + per-campaign table |
| `wf1-release-evidence/contacted_vs_pipedrive.csv` | 5,469 missing prospects, all campaigns |
| `wf1-release-evidence/ai4_missing_persons.jsonl` | 300 Ai4 missing — the backfill's only input |
| `wf1-release-evidence/mis_attached_leads.csv` | 100 lead rows on wrong persons, action per row |
| `backfill_ai4_persons.py` | dry-run clean, gated on `WRITE_MODE=live` |
| `reconcile_all_campaigns.py` | the all-campaign reconciliation |
| `wf1-system-reference.md` §9 | Make cohabitant entry added to the incident ledger |
