# Ai4 campaign rename migration - DRY RUN (Phase 1)

Generated 2026-07-27T14:04:01.268534+00:00 | prod versionId at start `da23d080-a0e0-4126-81c0-0cca60908435` (workflow untouched)

## Rename (verified byte-exact at the HeyReach source)
| campaign.id | OLD name (in leads today) | NEW name (in webhooks from now) |
|---|---|---|
| 512995 | `Ai4 2026 - Mario - LinkedIn` | `[Events Visiting] [Ai4 2026] - Mario - LinkedIn` |
| 513000 | `Ai4 2026 - Rune - LinkedIn` | `[Events Visiting] [Ai4 2026] - Rune - LinkedIn` |

## Scope
- leads scanned: **56554**; matched OLD name: **639**; already NEW: 0
  - 513000 (Ai4 2026 - Rune - LinkedIn): **321** leads
  - 512995 (Ai4 2026 - Mario - LinkedIn): **318** leads
- distinct persons: **639** (1:1 with leads; none spans both campaigns)
- archived leads in scope: **0**

## Per-LEAD change (exactly two fields)
- `Campaign` custom field: OLD -> NEW (639 leads)
- `title`: **campaign segment only** (639 leads). Person-name tail preserved verbatim.
- Untouched: labels, owner, archive state, activities, stage-adjacent fields.

Example:
```
lead c83b7780-e3de-11ef-8054-5799e8b6d1a7
  campaign: Ai4 2026 - Mario - LinkedIn
         -> [Events Visiting] [Ai4 2026] - Mario - LinkedIn
  title   : 512995 - Ai4 2026 - Mario - LinkedIn - Person-553c1289
         -> 512995 - [Events Visiting] [Ai4 2026] - Mario - LinkedIn - Person-553c1289
```

### Title strategy note (16 leads)
The spec formula would rebuild the title from the CURRENT Pipedrive person name, which for these
leads differs from the name already in the title - several would be regressions (lowercasing,
truncation, re-flipping a known identity collision). We therefore replace ONLY the campaign segment.

| lead | tail KEPT (surgical) | tail the formula would write |
|---|---|---|
| `75bbaf50...` | `Person-58c91089` | `Liam Loftus` |
| `827f0f70...` | `Maik Taro Wehmeyer` | `Maik Taro` |
| `91a35350...` | `Anoop D.` | `Anoop Dawar` |
| `43ebda10...` | `Person-5045203f` | `Dr. Tanvi` |
| `1bb1e390...` | `Person-16e15a0a` | `aneta zytniewska-ubrych` |
| `8269a2f0...` | `Person-88068b06` | `Fei Fei` |
| `17a685c0...` | `Sarah 🎯` | `Sarah Ghirardo` |
| `5fdf5ca0...` | `Person-bae7a4a9` | `Person-bae7a4a9 ` |
| `8b27e3f0...` | `Karan Y.` | `Karan Yaramada` |
| `9ecb8cd0...` | `Person-9a12ded3` | `BHARGAV GUNDABOLU` |
| `2cfc0070...` | `Jatin Trivedi (JT)` | `Jatin Trivedi` |
| `48ccd220...` | `Person-d78c8352` | `MICHAEL ABISA` |
| `ac428d40...` | `Bobby McKenzie, PhD` | `Bobby McKenzie` |
| `5b748430...` | `Person-8eb1eac3` | `ASHISH BHATNAGAR` |
| `2f747b70...` | `Debojyoti Dutta` | `Debojyoti (Debo) Dutta` |
| `f06a4250...` | `Daniel León` | `Daniel LeÃ³n` |

## Per-PERSON change (trio only)
- Event name -> `Ai4 2026`: **100** persons change (92 were empty)
- Marketing Hypothesis -> `Events Visiting`: **82** persons change (71 were empty)
- Medium: `608` already `LinkedIn`; `0` empty->fill; **`31` non-empty & different -> NOT touched (flagged)**

### Prior attribution that WOULD BE OVERWRITTEN (last-touch per Melisa) - please confirm
**Event name (8 persons lose a different, valid event):**

| person | name | from | to |
|---|---|---|---|
| 68731 | Person-0a51d197 | `HumanX 2026` | `Ai4 2026` |
| 68788 | Person-87cabe7b | `HumanX 2026` | `Ai4 2026` |
| 68841 | Person-a12ff73b | `HumanX 2026` | `Ai4 2026` |
| 66181 | Anoop Dawar | `ViVE 2026` | `Ai4 2026` |
| 69827 | Person-a7ba40b9 | `HumanX 2026` | `Ai4 2026` |
| 69850 | Person-ccb5ea6b | `HumanX 2026` | `Ai4 2026` |
| 74809 | Person-6dad4597 | `TechEx Americas 2026` | `Ai4 2026` |
| 69316 | Daniel LeÃ³n | `HumanX 2026` | `Ai4 2026` |

**Marketing Hypothesis (4 persons):**

| person | name | from | to |
|---|---|---|---|
| 62988 | Person-7fa35234 | `Trigger-based Campaign` | `Events Visiting` |
| 64531 | Person-84df1b50 | `Ai4 2026 - Mario - LinkedIn` | `Events Visiting` |
| 34624 | Person-c26ca3a5 | `AI Case Based` | `Events Visiting` |
| 63942 | Debojyoti (Debo) Dutta | `Trigger-based Campaign` | `Events Visiting` |

## Anomalies
| type | count | handling |
|---|---|---|
| medium_non_empty_different | 31 | NOT touched (30x `eMail`, 1x `eMail `) - flagged for Nik |
| lead_without_person | 0 | - |
| person_in_both_campaigns | 0 | - |
| archived_lead_in_scope | 0 | - |
| campaign value matching neither old name | 0 (filter is exact-match) | - |

## Rollback recipe
Every `cur_campaign` / `cur_title` / `cur_event` / `cur_hyp` / `cur_medium` is preserved in
`ai4-rename-migration-DRY.json`; the apply step additionally appends a per-entity BEFORE/AFTER
line to `ai4-rename-migration-CHECKPOINT.jsonl`.

## STOP - awaiting Nik's "apply"
