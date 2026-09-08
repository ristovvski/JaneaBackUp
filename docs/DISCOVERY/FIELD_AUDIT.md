# Pipedrive Field Audit (VERIFIED via API sampling, 2026-07-23)

Usage % = share of sampled recent records where the field is non-empty. Samples: person 500,
organization 300, deal 500, lead 500 (sorted newest first). Pre-does Melisa's manual audit.
Suspected owner inferred from name/prefix + WF-1 system reference; **confirm on the call.**

Legend for owner: **WF-1** (HeyReach→Pipedrive sync) · **LH** (`lh_*` = LinkedHelper/legacy import) ·
**Sales** (deal pipeline) · **Memurai** (product line) · **?** (unknown).

## Person — 115 fields (72 custom)
| Field | Type | Usage | Suspected owner | Merge / note |
|---|---|---|---|---|
| lh_linkedin_profile_url | text | **99.4%** | WF-1 | canonical LinkedIn key (WF-1 `fields.li_url`) |
| lh_campaign_name | text | 99.2% | WF-1 | person campaign (always-overwrite, W1.0.11.1) |
| Source | enum | 99.2% | WF-1 | create-only (446 Cold Outreach) |
| Medium | varchar | 99.2% | WF-1 | ="LinkedIn" |
| Marketing Hypothesis | varchar | 99.2% | WF-1 | event trio |
| lh_current_company | text | 91.6% | WF-1/LH | |
| **LinkedIn Profile** | varchar | 65.4% | LH/? | **MERGE → lh_linkedin_profile_url** (duplicate LinkedIn URL field) |
| lh_current_position | text | 54.6% | WF-1/LH | |
| Event name | varchar | 54.6% | WF-1 | event trio (W1.0.13) |
| LH_campaign_stage | text | 34.0% | LH | legacy stage; WF-1 uses Pipedrive stages instead |
| lh_public_id / lh_member_id | text/double | 33.8% | WF-1 | HeyReach ids |
| **Title** vs **LinkedIn Title** | varchar/text | 28.0% / 28.0% | ?/LH | **MERGE candidates** (two title fields) |
| **52 custom fields at 0.0%** | — | 0% | mixed | **cleanup/merge surface** ↓ |

Zero-usage person custom fields (52) incl.: Role, Team, Business Group, Introduced by, Website,
Sales Owner - Email, Internal Owner, Janea Owner, Outreach List, Seek Referral, Referral Made,
lh_note, lh_action_name, LinkedIn Degree, Seniority, Company Linkedin, Person State/City/Country,
Location, Latitude/Longitude of Location, … → prime candidates to archive or consolidate.

## Organization — 59 fields (21 custom) — low usage overall
| Field | Type | Usage | Note |
|---|---|---|---|
| lh_linkedin_profile_url | text | 22.7% | company LinkedIn |
| **Website / LinkedIn URL / lh_website / Website URL** | text/varchar | 20.7 / 18.0 / 17.7 / 17.7% | **4 overlapping URL fields → merge** |
| lh_company_id / Industry | text/varchar | 3.0% | |
| Number of Employees | double | 1.3% | |
| 13 custom fields at 0.0% | — | 0% | CAGE Code, D-U-N-S, Unique Entity ID, Company Description/Revenue/Phone, lh_public_id, lh_industry, lh_headquarter_country, Linked web visitor… |

## Deal — 91 fields (43 custom) — sales pipeline
| Field | Type | Usage | Suspected owner |
|---|---|---|---|
| BDR owner | enum | 53.8% | Sales |
| Qualified meeting bonus | enum | 45.2% | Sales |
| Opportunity type | set/enum | 45.0% | Sales |
| Specialized offerings | set | 44.8% | Sales |
| Memurai Order ID / Contract Duration / Period-PO / Billing/Support Contact / Revenue type / Workshops / Memurai Contract Terms | mixed | 26–34% | Sales / **Memurai** |
| Value for Janea Systems, **Campaign** | text/varchar | 0.0% | — (deal `Campaign` unused; the LEAD `Campaign` is the live one) |

## Lead — 74 fields (43 custom)
| Field | Type | Usage | Suspected owner | Note |
|---|---|---|---|---|
| Opportunity type | enum | 59.4% | Sales | |
| **Campaign** | varchar | **32.6%** | **WF-1** | WF-1 `fields.lead_campaign` — lead-per-campaign key (live) |
| BDR owner | enum | 0.2% | Sales | |
| 40 custom fields at 0.0% | — | 0% | Sales/Memurai | deal-oriented fields also attached to the lead object but unused on leads |

## Headline takeaways for Melisa
1. **Merge candidates (person):** `LinkedIn Profile` → `lh_linkedin_profile_url`; `Title` ↔ `LinkedIn Title`.
2. **Merge candidates (org):** collapse `Website` / `Website URL` / `LinkedIn URL` / `lh_website`.
3. **Cleanup surface:** 52 (person) + 13 (org) + 40 (lead) custom fields at 0% usage — archive/retire
   after confirming no automation writes them (Make/Zaps could write low-frequency fields the sample
   missed — verify before deleting).
4. **Live WF-1 fields confirmed at ~99%** (person: lh_linkedin_profile_url, lh_campaign_name, Source,
   Medium, Marketing Hypothesis) — do not touch; they're load-bearing.
5. Sampling caveat: a 0% in a 300–500 recent-record sample means "rare/unused recently," not
   "provably never written." Confirm against a Make/Zap field-writer list before any deletion.
