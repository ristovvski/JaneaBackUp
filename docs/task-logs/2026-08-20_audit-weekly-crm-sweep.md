# 2026-08-20 — Аудитор: WEEKLY CRM SWEEP (window 13 Aug → 20 Aug 11:06Z)

Read-only. Pipedrive API only. Nothing written anywhere. This is the I-04 prototype.

**Headline: the week's verified writes hold up. 7 findings, none of them a corruption; the two that
matter are an orphan duplicate person and an archival wave nobody reported.**

## Evidence base

Fresh full walks: **56,894 persons** (569 pages, cursor exhausted) · **57,695 leads** (577 pages) ·
yesterday's lead walk 57,854 for the diff · `/v1/recents` since 13 Aug **2,313 rows** ·
`/api/v2/activities?updated_since` **1,308** (filter proven against a control) · **162** individual
archived-lead detail reads · **655** person changelogs for actor attribution.

## Per section

| § | checked | found |
|---|---|---|
| 1 cross-write collisions | 2,762 persons in the touch map, 207 touched by ≥2 ops, max overlap 2, 20 sampled end-to-end | **0** |
| 2 label sanity | DNC set, 57,852 leads diffed vs the 14 Aug baseline, 5 OOO-class activities | **0** |
| 3 orphans & danglers | 1,308 activities, 162 archived leads read individually, lead walk diff | **2** |
| 4 FIRE_S3 first day | 13 new persons, field-686 population, all actors attributed | **1** |
| 5 duplicate regression | 13 new persons against a 56,894-person email + slug index | **1** |
| 6 human-side | 655 persons, every change row attributed, 0 unknown actors | **0** |
| 7 catch-all | reconciliation, impossible values, hygiene, enrichment completeness | **3** |

### §1 — coherent
All 20 most-touched records (all in the 215, all also shadow-archived by the dedup): exactly 1 live
lead, exactly 1 live London lead, 0 activities referencing a dead lead, all three enrichment fields
set. Nothing in the estate was touched by more than 2 of the week's operations.

### §2 — clean, and the OOO gate is verified from the CRM side
DNC = **exactly 7**, byte-identical to the expected survivor set; 0 unexpected; 0 among the 162
archived. One lead gained `3. Responded` since the baseline — `68f06100…` (Person-090ff619, Ai4 512995) —
and it is a **genuine** reply at 2026-08-20T00:49, which also produced a handover task. 0 lost
Responded. 8 other label changes, all singletons, all organic. The 3 auto-replies of 14 Aug produced
activities `44155/44156/44157` carrying *"No 'responded' label: nobody has actually read the
message"*, and their leads still hold only `1. Cold` — **and all three were alias cases**
(`jfarrar@` → `joseph.farrar@`), so the alias gate fired too.

### §3 — two findings
* **The dedup orphaned nothing.** 0 activities point into the 162; only 1 of them ever carried an
  activity (`40363`, the generated task I named pre-fire).
* **FINDING (P2) — an unreported archival wave.** 6 activities now dangle on leads archived
  *outside* the 162: five event leads archived **14 Aug 12:44–13:53** (NVIDIA/Person-96ef111e,
  Ai4/Person-afff98fe, ITExpo/Person-63318601, ViVe, HUMANX/Person-90613b61) and one on
  **18 Aug 06:14:58** (`76be46a0…`, HumanX 2026 Valids, person 69696) carrying task **44141**
  *"Assign this lead to a sales exec!"* — created 14 Aug, still not done, now invisible.
  The full size of that wave is **not enumerable**: archived leads are invisible to every list read,
  so only the ones that left an activity behind are detectable.
* 133 person-only activities: **111 are Lule's manual "Send personalized post-event follow up
  message" tasks** (17 Aug) — legitimate; 21 are HeyReach conversation activities (Noah 16, Mario 5).
* 0 leads changed person. 0 deals reference an archived lead (the 12 non-live `origin_id`s are
  Marketplace **app** ids and a web-form id, not lead pointers).

### §4 — one open flag
**0 field-686 projections** since the flip, and the 686 population is still exactly **2,262**, none
touched this week. So **no automation write leaked through** — confirmed. But 5 of the 13 new persons
are genuine roster-human creations: **85766** Tom Debevoise (Leadjet, Jim Ash) · **85767** Maria
Donosova (Leadjet, Noah) · **85769** Person-1a7d5710 (Leadjet, Chrissy) · **85772** Person-ea6fcf66
(leads-graphql + UI, Slava/Melisa) · **85774** Aileen Gordon (UI, Toby). None projected.
**I cannot close this half**: n8n exposes no data-tables API route (404 on `/data-tables`,
`/dataTables`, `/data-table`), so the registry is unreadable from my seat.

### §5 — one finding
**FINDING (P2) — orphan duplicate person.** `p85764` and `p85765`, both *Santosh Lamani*,
same email `pii-4586392a@example.invalid`, created **1 second apart** (07:29:46 / 07:29:47), both by
`api|axios/1.7.8|u13015123` (website form). p85764 holds the lead; **p85765 has zero leads**.
0 duplicate LinkedIn slugs among new persons. Estate context: 204 duplicate emails, 363 duplicate slugs.

### §6 — facts, no damage
**47 owner reassignments, every one off Melisa** (u16340280): → Sergey 20, Rune 11, Mario 8, Toby 5,
Jim Ash 1, plus Mario→Rune and Slava→Rune. Done by **Lule (21)** and **Slava (26)**, all through the
UI. Human UI edits: Lule 214 · Slava 33 · Mario 6 · Toby 2 · Jim Ash 2 · Marci 1 · Araks 1.
Bulk >20: Lule's `Next Scan Date` (56/43/33 on 17–19 Aug) and `Last Scan Date` (23).
**Weekend: 4 rows, all our automation token** (WF-1 stage progression on p84914, Sunday 16 Aug) —
zero human weekend edits. One human rename: Slava, `Person-b21193f6` → `TADAHIKO (Mark) YANAGISAWA`.
0 unknown actors.

### §7 — three
Reconciliation closes exactly: 57,854 − 162 + 3 = **57,695** walked; London 4,267 → 4,105 = −162.
0 genuine future timestamps. The 215 enrichment: `lh_linkedin_profile_url` **215/215**,
`lh_current_company` **215/215**, `LinkedIn Location` **215/215**, `lh_current_position` 0/215
(expected — Smartlead has no titles), **`LinkedIn Profile` (b59a7d0a) 0/215** (a decision, not a
defect). Hygiene: 62 leads with no person, **1,254 leads with no label** (incl. Person-ea6fcf66's),
56 activities attached to nothing — all recurring internal meetings, pre-existing.

## IMPROVABLE — four of my own errors, all caught before publication

1. **3 "future timestamp" leads** — my own string comparison bug (`'2026-08-20T07:16'` vs
   `'2026-08-20 11:06'`, `T` > space). All three are simply today's. Withdrawn.
2. **"8× duplicate activity writes on p85517"** — killed by hashing the note bodies: 8 distinct
   hashes, one activity per conversation message.
3. **"the backfill mis-routed 133 activities to persons"** — 111 are Lule's manual tasks.
4. **Retyped a truncated 8-char lead id into a full UUID** → 404. Every id in this sweep is now read
   from the data, never retyped. Second occurrence of this in two days.

## Artifacts

`audit-artifacts/weekly_sweep_20260819.json` — per-section checked/found, every id, the needs-action
list, and the I-04 daily/weekly split.

## BLOCKED

The registry half of §4 — no n8n data-tables API. Everything else completed.
