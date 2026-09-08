# Sales Sprint London - CSV vs Pipedrive coverage (READ-ONLY scouting)

Date 2026-07-27. Source: `People-Testing-export-1785168478447.csv` (Clay "UK Tech Leadership Roles",
6770 rows). Email key: `Custom Waterfall` (6770/6770 filled). Matched by email, exact, lower+trim
normalized on both sides, against ALL emails each Pipedrive person carries.
**No writes of any kind. No dry-run file. This pass only decides whether/what to patch.**

## 1. Coverage funnel
| stage | count |
|---|---|
| CSV rows | 6770 |
| distinct emails | 6753 (17 duplicated) |
| Pipedrive persons scanned / distinct emails indexed | 55695 / 44368 |
| **matched rows** | **3957** |
| **matched persons** | **3942** |
| **NOT found in Pipedrive** | **2813 rows (41.6%)** |
| persons matched by 2+ CSV rows | 15 |

**Only ~58% of the source list reached Pipedrive.** The 2813 unmatched are presumably rows that never
passed the validation/qualification gates into Smartlead - worth confirming with Melisa before anyone
treats the CSV as the campaign's population.

## 2. Who the matched are
| cohort (person `lh_campaign_name`) | persons |
|---|---|
| **contains "Sales Sprint"** | **3918 (99.4%)** |
| `[Trigger-based Campaign] Newly Hired Heads of AI` | 17 |
| singles: Microsoft Ignite 2024, Web Summit 2025, Client Similarity Luma-like, Edge AI AgTech, Databricks 2025, Microsoft Build 2025, SuperComputing 2024 | 7 |
| **empty** | **0** |

Owners: **Melisa Bahonjic (16340280) 3908**, Toby (17703023) 31, Sergey Cujba (21037002) 3.
The match is clean - the matched set IS the sprint cohort, not a random overlap.

## 3. Field-gap profile (of 3942 matched persons)
| field | key | EMPTY | would be filled from CSV |
|---|---|---|---|
| `lh_current_position` | `ab15ebd7...` | **3883 (98.5%)** | 3883 (CSV `Job Title` 6770/6770) |
| `Title` (mirror) | `0b72db8f...` | **3898 (98.9%)** | 3898 |
| `LinkedIn Title` (mirror) | `f8edcb01...` | **3940 (99.9%)** | 3940 |
| `LinkedIn Location` | `db219a0b...` | **3919 (99.4%)** | 3919 (CSV `Location` 6770/6770) |
| `org_id` (org link) | - | **3915 (99.3%)** | see section 4 |
| `lh_current_company` | `5a282f55...` | 3 (0.1%) | 3 |
| `LinkedIn Profile` | `b59a7d0a...` | 3 (0.1%) | 3 |
| `lh_linkedin_profile_url` | `66f0af69...` | **0 (0.0%)** | 0 |

**Shape of the future patch:** it is a *titles + location + org-link* job. Company and LinkedIn URL are
already ~100% populated (the Smartlead/Clay import fills those), so there is nothing to gain there.
Note the raw "would-fill" counters in the JSON are row-based (3957) so a couple exceed the per-person
EMPTY count; the per-person numbers above are the actionable ones.

**Ownership caveat:** `lh_current_position` (`ab15ebd7`) and `lh_current_company` (`5a282f55`) are the
SAME keys WF-1 uses as `CONFIG.fields.position` / `.company` and already fills fill-if-empty (R2). A patch
here co-writes with WF-1 - no conflict while both are fill-if-empty, but the field is shared.

## 4. Org landscape (3915 persons / 3930 rows with empty `org_id`)
| | count |
|---|---|
| distinct `Cleaned Company Name` | **1822** |
| already in Pipedrive by exact (normalized) name -> would **LINK** | **517** |
| of those, **ambiguous** (2+ orgs share the name) | **118** |
| not in Pipedrive -> would need **CREATE** | **1305** |
(Pipedrive orgs scanned: 20686.)

Two decisions this forces: (a) **1305 new organizations** is a material change to the org table - Nik/Melisa
should want that before we do it; (b) the **118 ambiguous names** must not be linked blindly, or people get
attached to the wrong company - they need a disambiguation rule (domain match) or manual review.

## 5. Dirt
| item | count |
|---|---|
| duplicate emails inside the CSV | 17 (17 extra rows) |
| persons matched by 2+ CSV rows | 15 |
| CSV `Job Title` CONFLICTS with a non-empty Pipedrive value | **14** |

Fill-if-empty would not touch those 14, but they are visible drift worth knowing:
- person 53746: PD `Vice President - Data Lead` vs CSV `Vice President - Global Data & AI Lead`
- person 53483: PD `VP of Engineering` vs CSV `Chief Technology Officer`
- person 53584: PD `CTO and Group Technology Lead` vs CSV `Group Chief Technology Officer`
- person 78908: PD `Engineering Manager` vs CSV `Software Engineering Manager`
- person 80094: PD `Lecturer in Computer Science` vs CSV `Engineering Manager`

## 6. Five sample rows end-to-end
| CSV row | title @ company | matched person | campaign | EMPTY |
|---|---|---|---|---|
| Person-7d4b5acd | Director of Engineering @ Stream | [78803](https://janeasystems.pipedrive.com/person/78803) | `[Sales Sprint] Sales Sprint 2026 - London - Valids` | position, Title, LinkedIn Title, Location, org_id |
| Person-41a01164 | Director of Engineering @ hyperexponential | [79855](https://janeasystems.pipedrive.com/person/79855) | ... Valids | same 5 |
| Person-e28f785d | Director of Engineering @ Seccl | [79817](https://janeasystems.pipedrive.com/person/79817) | ... Valids | same 5 |
| Oskar Pearson | Director of Engineering @ On the Beach | [78826](https://janeasystems.pipedrive.com/person/78826) | ... Catch-alls | same 5 |
| Person-22c157b3 | Head of Data and Analytics @ Fundment | [79870](https://janeasystems.pipedrive.com/person/79870) | ... Valids | same 5 |

## Verdict for the patch decision
- **Worth patching:** the three title fields (~3.9k each) and LinkedIn Location (~3.9k) - cheap,
  fill-if-empty, no ownership fight, immediate reporting value.
- **Needs a decision first:** org linking. 517 links are safe-ish minus the 118 ambiguous; 1305 creations
  are a data-shaping call, not a technical one.
- **Do not assume the CSV = the campaign:** 2813 of 6770 rows have no Pipedrive person at all.
- Nothing here required or performed a single write.
