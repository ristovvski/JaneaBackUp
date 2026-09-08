# Legacy Systems Audit

**Commissioned by:** Sergey (quarterly-review grade) / Nik. **Presenter:** Nik, to Sergey and the founder.
**Window:** Feb 2025 → today, measured wherever retention allows; retention horizon stated per source, never extrapolated silently.

> **What was lost:** the legacy Make/Zapier stack lost track of most outbound activity for most of its operating life — 78.2% of all-time replies untraced in the CRM, 16.9% of contacted people never entered the CRM at all, 173 real prospects duplicated, and 409 days of team-visible notification silence across 108 separate blackout windows. **What class of causes:** not one bug but a handful of structural gaps — no CRM-record-creation automation until 2026-01-27, a four-zap Zapier swarm stripping the `Responded` label for an undetected ≈24-day stretch, and a Slack-alerting path with no self-monitoring. **What's now guarded:** the current n8n system creates CRM records at write time, writes labels as a union (never overwrite), carries a real-time reply-alert path, and the four wiper zaps are disabled (not deleted) with that gap tracked explicitly rather than assumed closed.

**Status:** All six sections landed and verified as of 2026-08-18. This is the final report, not a working draft — see the executive summary and evidence index below for full detail. The "after" figures in Section F marked [per Nik] are cited from the commissioning brief as-is — deliberately not "verified" by a loose title/keyword match against the bulk pull, since that's exactly the substring-blob-check failure mode this audit has been built to avoid.

---

## Executive summary

The old Make/Zapier system was not a smaller version of the current one — it was, for most of its life, barely connected to Pipedrive at all. Across the full measurable history:

- **78.2% of all replies (2,220 of 2,840 unique repliers) have no "responded" trace in Pipedrive** — either no CRM person exists at all (336), or a person exists but nothing ever marked the reply (1,884).
- **16.9% of everyone contacted (3,554 of 21,073) never got a Pipedrive record created at all** — concentrated almost entirely in campaigns run before the Make lead-creation automation existed (created 2026-01-27); campaigns from 2026 onward sit in the single digits.
- **173 real prospects have duplicate person records** (176 extra records) from the same name-vs-email attachment defect that produced the known 84885/86/87 case.
- **The #lead-processing channel went dark (≥24h, zero team-visible alert) 108 times, totaling 409 days over ~20 months** — 607 replies landed during those silences, meaning the team had no chance of seeing them in real time.
- Label-wipe: **not a flat rate — a bounded, dated window.** Four zaps collectively strip `Responded`→`[Cold, Connected]`; a separate fifth zap that used to re-add `Responded` (not a wiper itself) was killed 2026-08-05T11:28:42Z, making wipes permanent from that point on. The 11-wiped Aug 5-10 count sits entirely after that change. Per Zapier's own record, the four wipers ran undetected from 2026-07-17T15:56Z to their 2026-08-10T16:12Z disable — ≈24 days — while marked "closed," and their 2026-07-17 re-enable is unattributed in Zapier's record (`last_edited_by: null`). All four are now disabled (not deleted; one toggle from re-enabling).

The new system's contrast, from this week alone: 0 replies lost through a 32/32 storm-recovery event, 215 historically-orphaned London leads restored with full audit trail, 11 wiped labels caught and repaired, and — for the first time — the team gets a real-time alert when any of this happens at all.

---

## Section A — Lost replies (full history, all 117 campaigns)

**Method:** swept every Smartlead campaign's `leads-statistics` history (Sep 2024→today) for `REPLY`-type entries, matched each unique replied email against a bulk pull of all 56,883 Pipedrive persons / 57,856 leads, checked for the `3. Responded` label.

| | count | % of 2,840 |
|---|---|---|
| Traced (person + responded label found) | 620 | 21.8% |
| Person exists, never labeled responded | 1,884 | 66.3% |
| No Pipedrive person at all | 336 | 11.8% |
| **Total with no responded-label trace** | **2,220** | **78.2%** |

Loss rate by campaign family ranges from 39% (HumanX 2026, a recent campaign) to 100% (several 2024-era families) — see `evidence/section_a_first_numbers.json` for the full 46-family breakdown.

**Caveat, stated not hidden:** this pass uses label evidence only. An activity-note check (did a reply-activity get logged even without the label?) was not run at full scale — it would only move some of the 1,884 from "lost" to "traced but unlabeled," never the other direction. Evidence: `evidence/section_a_first_numbers.json`, raw sweep `evidence/section_ab_raw_sweep.jsonl`.

## Section B — Missing persons/leads (contacted vs. created, per campaign)

**Method:** same sweep as Section A, `contacted` = at least one `SENT` history entry; `created` = a Pipedrive person exists for that email. Zero additional API calls — same walk, per instruction.

- **21,073 unique people contacted, all campaigns, all history.**
- **3,554 (16.9%) never got a Pipedrive person created at all.**
- The pattern is sharp and dates cleanly: campaigns created Oct-Dec 2024 (Ag Tech, AWS Re:Invent non-Amazon, SuperComputing, TechCrunch fups) are 87-100% missing. Campaigns from 2026 (ViVE, Databricks, Microsoft Build) are 4-8% missing. The dividing line lines up with when Make's lead-creation scenario (8557031) was actually built — **2026-01-27** — not a gradual improvement, a step change.

Evidence: `evidence/section_b_first_numbers.json` (full per-campaign table, 117 rows).

## Section C — Duplicates (name-vs-email attachment class)

**Method:** checked the actual 84885/86/87 precedent before assuming its shape (it's 4 person records sharing one email — a flip-day test fixture, not organic data) — that fixed the real signature to look for: **the same email attached to more than one Pipedrive person record.**

- **173 real-prospect duplicate clusters, 176 extra person records.** This is the honest headline number.
- Separated out (not blended in): 21 clusters / 37 extra records that are internal/test accounts (@janeasystems.com, @memurai.com, "test"/"newsletter subscriber" name patterns), and the known flip-day fixture (84885/86/87/85506, 3 extra records) excluded entirely.
- Lead-per-campaign violations (same person, 2+ leads for one campaign): **1 pair found, 1 extra lead** — the W1.0.11 convention is holding well; this defect is essentially closed for leads even though the historical person-duplicate backlog remains.

Count only, per instruction — no merges performed. Evidence: `evidence/section_c_first_numbers.json`.

## Section D — Label-wipe: a bounded window, not a flat rate

**Correction folded in verbatim from the ops session ("Дежурный (прод)").** The mechanism is not one zap — my earlier framing naming `274318213` alone was wrong and has been corrected in memory. It's **four zaps collectively writing the same absolute label set `{1. Cold, 2. Connected}`**, verbatim titles (character-exact, from a live Zapier pull, not paraphrased):

| Zap ID | Title |
|---|---|
| `274357463` | "Add "Connected" label to lead if LH response is received" |
| `274354645` | "Add "Cold" label to lead if LH connection request is sent" |
| `274318213` | "Make.com replacement for LH connection already exists - put connected tag in lead" |
| `274316027` | "Make.com replacement for LH connection accepted - put connected tag in lead" |

Naming only one in this report would have gone wrong the moment any of the other three re-enabled — confirmed via a live Zapier read (not memory): all four were **disabled since 2026-08-10, not deleted, one toggle from re-enabling** (paused within 32 seconds of each other, 2026-08-10T16:11:53Z-16:12:25Z; state `is_configured:true`).

**A fifth zap, listed separately because it is not a wiper — it's the re-adder whose shutdown is the mechanism change:** `274357187`, titled **"Add "Responded" label to lead if LH response is received"**, used to re-add `Responded` after the four above stripped it. It was turned **OFF 2026-08-05T11:28:42Z**. That's the pivot the rest of this section turns on:
- **Before 2026-08-05T11:28:42Z:** wipes were **partly self-healing** — `274357187` sometimes raced the strip and re-added the label.
- **After that date:** wipes are **permanent** — nothing left in the swarm re-adds `Responded`.

**We proved 11 wiped in the Aug 5-10 window** (full retention, cited in the brief) — that number sits entirely in the *permanent* regime, after the 08-05 mechanism change. It is not extrapolated backward into a flat historical rate, and it will not be — no Zapier Platform API credential exists in any session to pull real run-history (Zapier-MCP is action-execution-only, no history-read surface), so there is no data to extrapolate from even if we wanted to.

**Honest attribution bound, stated not hidden:** nobody has opened the four wiper zaps' step configs — Zapier's step editor forces an unsaved draft state the moment it's opened, too risky to do for a read. Attribution of *what they do* rests on **zap titles + the observed terminal label set**, not confirmed step-level logic. Separately, attribution of *who re-enabled them* is a real gap, not an assumption we're filling in: Zapier's own record shows `274357187` (the re-adder) has an attributed editor (`mykyta@`), but **all four wiper zaps return `last_edited_by: null`** — the 2026-07-17 re-enable is **unattributed in Zapier's record**, full stop.

**The unnoticed fact, worth stating plainly to Sergey:** per Zapier's own record, all four wiper zaps' `last_live_at` = **2026-07-17T15:56Z**, and they were disabled **2026-08-10T16:12Z** — a citable, exact unnoticed interval of **2026-07-17T15:56Z → 2026-08-10T16:12Z, ≈24 days**, while the internal incident record still said "CLOSED & VERIFIED" from an earlier same-day 2026-07-17 disable.

**Section D ships as:** *"measured through the Aug 5-10 window (11 wiped, permanent-regime), remainder in progress"* — a bounded, dated, mechanism-aware statement, not a rate.

## Section E — Notification dark windows vs. reply volume

**Method:** reused the existing full-history #lead-processing harvest (1,641 messages, 2024-12-19→2026-08-05, pulled for the earlier duplicate-forensics task — same data, no reason to re-pull) plus a fresh extension to today. Found gaps between consecutive channel messages, cross-referenced against Section A's reply timestamps.

- **108 dark windows (≥24h, zero team-visible message), totaling 409 days over ~20 months.**
- **607 replies landed during a dark window** — zero chance of real-time visibility.
- The single worst window: **Jan 23 → Mar 11, 2025, 46.7 days straight silent, 62 replies inside it.**

Evidence: `evidence/section_e_first_numbers.json`.

## Section F — Before / after

| | Before (legacy) | After (this week, wire numbers) |
|---|---|---|
| Reply loss | 78.2% of all-history replies untraced (Section A) | 0 lost — 32/32 storm-recovery event [per Nik] |
| Missing CRM records | 16.9% of all-history contacts (3,554), concentrated pre-2026-01-27 (Section B) | 215 historically-orphaned London leads restored, full per-row read-back verified |
| Duplicates | 173 real-prospect duplicate clusters, uncorrected backlog (Section C) | New defect class effectively closed (1 lead-per-campaign violation found, live); backlog fix is a separate, not-yet-taken decision |
| Label damage | Four-zap swarm, ran undetected 2026-07-17T15:56Z→08-10T16:12Z (≈24 days), permanent since the 08-05 self-heal zap was killed; now disabled, not deleted (Section D) | 11 wiped labels caught and repaired this week |
| Notification gaps | 108 dark windows, 409 days silent, 607 replies missed (Section E) | First real-time team alerts firing on the new system |

---

## Evidence index

- `evidence/step0_retention_recon.json` — per-source retention horizons (n8n ~19d, Make ~30d floating, Zapier inaccessible from here, Smartlead 2024-09+, HeyReach 2026-07-13+, Pipedrive 2020+)
- `evidence/section_ab_raw_sweep.jsonl` — raw per-campaign Smartlead sweep (117 campaigns)
- `evidence/bulk_persons.jsonl`, `evidence/bulk_leads.jsonl` — full Pipedrive bulk pull (56,883 / 57,856 records)
- `evidence/section_a_first_numbers.json`, `section_b_first_numbers.json`, `section_c_first_numbers.json`, `section_e_first_numbers.json`
- Ops channel posts: real-time section landings, timestamped, in `#C0B8GCVNR5W`
