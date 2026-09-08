# Ai4 campaign rename migration - final report

**Date:** 2026-07-27  **Workflow:** WF-1 (n8n `2jdjKM2NJr473GdA`), release **W1.0.13.1**
**versionId at start:** `da23d080-a0e0-4126-81c0-0cca60908435` (95 nodes, active)
**versionId at end:** `da23d080-a0e0-4126-81c0-0cca60908435` (95 nodes, active) - **UNCHANGED, workflow never touched**

Pure Pipedrive data migration + one production-path smoke. No node edits, no deploy.

## Rename (verified byte-exact at the HeyReach source, both campaigns PAUSED per API)
| campaign.id | OLD name | NEW name |
|---|---|---|
| 512995 | `Ai4 2026 - Mario - LinkedIn` | `[Events Visiting] [Ai4 2026] - Mario - LinkedIn` |
| 513000 | `Ai4 2026 - Rune - LinkedIn` | `[Events Visiting] [Ai4 2026] - Rune - LinkedIn` |

## Pre-apply reconciliation (the 254 vs 639 question)

**No defect, no data loss.** The `254` was a correct count - for **2026-07-21 09:20 UTC**. Cumulative curve
over all 639 leads (sorted by `add_time`): 240 at 07-20 14:05 -> **254 at 07-21 09:20:21** -> 323 at 07-21
10:15 -> **639 at 07-27 11:29**. Six more days of sending added +385 leads. Mechanisms explicitly ruled out
with numbers: pagination cutoff (first page = 0 matches, Ai4 leads sort last), `archived_status` filter
(639 under every value), person-level count (619), owner filter (617/11/10/1), label filter (537/78/24).

| question | answer | numbers |
|---|---|---|
| leads carrying OLD names | **639** (Mario 318 + Rune 321) | two independent methods agreed: `Campaign` field exact-match AND title prefix |
| ~638 invites vs our leads | **1:1, no loss** | 617 created by the campaigns + 22 pre-existing leads that received Ai4 touches = 639 |
| sent-event outcomes (n8n history) | **420/420 lead_created**, 0 matched-existing, 0 errors | Rune 211, Mario 209; all 622 executions in window `status=success` |
| n8n retention depth | history starts **2026-07-20 13:43** (exec 10487) | the pre-retention cohort is exactly the **197** Phase D measured on 07-20 -> 197 + 420 + 22 = 639 |
| HeyReach `totalUsers` = 1164 | **audience, NOT sent** - do not compare to 639 | Mario 558 (428 inProgress / 107 finished / 9 failed / 16 stopped), Rune 606 (585/13/3/6), `pending` = 0 |
| daily send pace | even, no gaps | 68 / 72 / 78 / 83 / 80 / 83 / 72 / 81 per day (07-18 .. 07-27) |
| leads WITHOUT a Campaign value, held by Ai4 persons | **64 - all legacy, left untouched** | AI4 2025 x38, HumanX 2026 x7, AI Summit NYC x4, Trigger-based x3, Databricks/TechEx x2 each, 6 singles; `Final TEST` = 0; archived = 0; held by 60 persons; they predate the Campaign field (W1.0.11) |
| Ai4 persons' leads with a DIFFERENT campaign name | **0** | clean |

**Side finding for reporting (not a bug):** person-level count by `lh_campaign_name` gives **619** vs **639**
leads - the person field is last-touch always-overwrite (W1.0.11.1), so 20 people already moved to a later
campaign. **Campaign reach must be counted on LEADS, not on the person field.**

## Phase 2 - APPLY (639 leads / 104 persons, 0 errors)
| target | written |
|---|---|
| lead `Campaign` field | **639** |
| lead `title` (campaign segment only) | **639** |
| leads skipped (no change) | 0 |
| person Event name -> `Ai4 2026` | **100** |
| person Marketing Hypothesis -> `Events Visiting` | **82** |
| person Medium filled | **0** (nothing to fill) |
| persons skipped (already canonical) | **535** |
| **errors** | **0** |

Per campaign: Mario `512995` 318 leads / 49 persons; Rune `513000` 321 leads / 55 persons.

**Title strategy:** replaced ONLY the campaign-name segment, preserving the person-name tail verbatim.
The spec formula (rebuild from the current Pipedrive person name) would have rewritten the name on 16
leads, several as regressions - e.g. `Person-16e15a0a` -> `aneta zytniewska-ubrych`,
`Maik Taro Wehmeyer` -> `Maik Taro`, `Person-88068b06` -> `Fei Fei`, and it would have re-flipped the known
`Person-58c91089` / `Liam Loftus` identity collision. Formula variants kept in the plan as `new_title_formula`.

**Flags (untouched by design):** 31 persons whose `Medium` is non-empty and different (30x `eMail`,
1x `eMail ` with a trailing space) - fill-if-empty means we never stomp them.
**Approved overwrites applied:** 8 persons lost a different prior event (`HumanX 2026` x6, `ViVE 2026`,
`TechEx Americas 2026`) and 4 lost a prior hypothesis (`Trigger-based Campaign` x2, `AI Case Based`,
plus one junk value `Ai4 2026 - Mario - LinkedIn` that sat in the hypothesis field) - per Melisa's
explicit last-touch ask.

## Verification
- **Re-query by OLD names -> 0 rows** (full re-scan of all leads) OK
- 10 random leads re-GET: all carry the NEW name + migrated title OK
- 10 random persons re-GET: all `event='Ai4 2026' hyp='Events Visiting' medium='LinkedIn'` OK
- **Idempotency:** re-run produced **0 writes** (743 entities short-circuited by checkpoint; the remaining
  535 persons re-GET'd and confirmed already-canonical)
- **Rollback recipe:** `ai4-rename-migration-DRY.json` (every `cur_*` value) +
  `ai4-rename-migration-CHECKPOINT.jsonl` (per-entity BEFORE/AFTER for all 743 writes)

## Phase 3 - production-path smoke (real webhook, NEW Mario name verbatim)
| step | exec | result |
|---|---|---|
| `connection_request_sent` | **11311** | one lead created; `Campaign` = NEW name; title `512995 - [Events Visiting] [Ai4 2026] - Mario - LinkedIn - WF1 SMK142936 Person`; labels `[cold]`; **trio AT COLD**: `Ai4 2026` / `Events Visiting` / `LinkedIn` |
| `every_message_reply_received` | **11312** | matched the SAME lead (no duplicate); reply activity written; alert -> **C0B8GCVNR5W**, zero to `C07LTD8UT70`; `M7 Labels Compute` = `[cold, responded]` (event-truth) |
| control on migrated data | - | real lead `c83b7780...` -> NEW name + `512995 - [Events Visiting] [Ai4 2026] - Mario - LinkedIn - Person-553c1289` |
| cleanup | - | lead 404, person `is_deleted=true`, org 21464 deleted, activities 42540 + 42541 + **42542 (Melisa handover task)** deleted; 0 alive activities remain |

**One assertion failed, and it was my test's fault, not the product's.** The final Pipedrive label set showed
`connected` alongside `cold, responded`. Execution-truth proves WF-1 computed exactly `[cold, responded]`;
the extra label came from the known accepted sprint reply-Zap (fires on stage-contains-`Repl`). My check
asserted on final state of a field shared with a co-writer instead of on execution-truth - the exact lesson
already recorded after W1.0.11. **New observation:** the Zap landed in **under 4 seconds**, not the ~90s
previously documented - worth updating the incident note.

## Addendum - person `lh_campaign_name` OLD -> NEW (persons only, no lead writes)

**Why it was needed:** the person campaign field is last-touch always-overwrite (W1.0.11.1), so it
self-heals on the next event - but **cold-only persons never get another event**, which would have left
Melisa's person-level exports permanently split between old and new campaign names. Spotted by Nik
(example: Person-82b68718 still carrying `Ai4 2026 - Mario - LinkedIn`).

Rule (diff-only, value-based rename cross-checked against each person's own lead campaign):
`Ai4 2026 - Mario - LinkedIn` -> `[Events Visiting] [Ai4 2026] - Mario - LinkedIn`, same for Rune;
already-new = skip; anything else = skip + flag (never guessed).

| outcome | count |
|---|---|
| **renamed** | **619** (Mario `512995` 309 + Rune `513000` 310) |
| already NEW (idempotent skip) | 0 |
| skipped + flagged (field holds a different campaign) | 20 |
| skipped (field empty) | 0 |
| value-based target disagreeing with the lead's campaign | 0 |
| **errors** | **0** |

**Verification:** 10 random persons re-GET -> all carry the NEW name; **base-wide persons still holding an
OLD Ai4 campaign name = 0**. Person-82b68718 now fully consistent: person `lh_campaign_name` =
`[Events Visiting] [Ai4 2026] - Mario - LinkedIn`, Event `Ai4 2026`, Hypothesis `Events Visiting`,
Medium `LinkedIn`, and his lead carries the NEW name + migrated title.
Checkpoint: `ai4-person-campaign-CHECKPOINT.jsonl` (per-person BEFORE/AFTER).

**"2 dual-campaign persons" do not exist in the data:** 639 leads map to 639 distinct persons, strictly
1:1, and no Ai4 person holds a lead with any other campaign name. The most-recent-lead rule is
implemented anyway, so the case is handled if it ever arises.

### OPEN DECISION for Nik - the 20 flagged persons
Their **leads are correctly attributed** (Ai4 2026, NEW name), but their person field still holds an
**older** event - `[Events Visiting] AI4 2025 - Valids/Catch-alls` x7+, `SuperComputing & The AI Summit 2024`,
`NVIDIA GTC 2025 - Low Priority - Valids`, `[Events Visiting] Money 20/20 2025 - Valids`,
`TechEx North America 2026 - Jim - LinkedIn`, and one `[Events Visiting] AI4 2026 - Valids` (that one is the
**email-side** Smartlead campaign). Root cause: the person campaign field only became always-overwrite in
W1.0.11.1 (2026-07-21 06:01); before that it was fill-if-empty, so an existing non-empty value was never
replaced. These are therefore **stale fill-if-empty-era values, not fresher last-touch values.**

They were correctly out of scope for this rename (they do not equal the OLD Ai4 name) and were left
untouched, because changing them is an **attribution change, not a rename** - for several of these people the
prior event is genuine (they really were at AI4 2025 / Money 20/20), and for one the last touch came from an
email campaign. Consequence if left as-is: those 20 appear under their older event in person-level exports
(their leads still count correctly, and leads are the authoritative source for campaign reach).
Options: (a) leave as-is; (b) set all 20 to the Ai4 2026 NEW name (matches what their next event would do);
(c) only those whose prior value is a non-event campaign. Awaiting Nik's call - same diff-only+checkpoint pass.

## Artifacts
`wf1-release-evidence/`: `ai4-rename-migration-DRY.{json,md}`, `ai4-rename-migration-APPLIED.json`,
`ai4-rename-migration-CHECKPOINT.jsonl`, `ai4-reconciliation-part1.json`, `ai4-reconciliation-part2.json`,
`ai4-reconciliation-dates.json`, `ai4-reconciliation-254probe.json`, `ai4-reconciliation-when254.json`,
`ai4-rename-smoke-SMK142936.json`, `ai4-person-campaign-{DRY,APPLIED}.json`,
`ai4-person-campaign-CHECKPOINT.jsonl`

## Totals written across the whole migration
| target | writes |
|---|---|
| leads (`Campaign` + `title`) | 639 + 639 |
| persons (Event name / Hypothesis / Medium) | 100 + 82 + 0 |
| persons (`lh_campaign_name` rename) | 619 |
| **errors** | **0** |
| workflow changes | **none** (versionId identical at start and end) |

## READY - resume the campaigns
