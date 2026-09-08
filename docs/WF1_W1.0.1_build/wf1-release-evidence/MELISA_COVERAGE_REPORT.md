# Are all the leads we contacted in Pipedrive?

**No — 5,469 of 42,039 contacted prospects are missing from Pipedrive (13%).**

_Read-only check, 2026-08-04 13:12 UTC, across all 107 campaigns that have ever sent. Nothing was
created, changed or deleted to produce this report._

## The numbers

| | count |
|---|---|
| campaigns that have sent at least one email | 107 |
| send events across them | 103677 |
| **unique prospects contacted** | **42039** |
| present in Pipedrive | 36570 |
| **missing from Pipedrive** | **5469 (13%)** |

Of the missing, **300** were contacted by one of the four current Ai4 campaigns; the other **5,169**
are on older campaigns only. (In the table below each prospect is counted under every campaign that
emailed them, so the Ai4 rows sum to 300. The CSV lists each person once, under the campaign that
contacted them *first* — which is why 6 of the 300 appear there under an older campaign.)

Full list with name, email, company, campaign and send date: `contacted_vs_pipedrive.csv`.

**Spot-check of the number:** 8 addresses sampled evenly across the missing list were re-queried
through Pipedrive's own person-search endpoint. All 8 came back absent — 0 disagreements — so the
13% is a real gap, not an artefact of how we matched addresses.

## Per campaign

| campaign | status | contacted | in Pipedrive | missing | gap |
|---|---|---|---|---|---|
| Ag Tech - Catch-alls - USA | PAUSED | 742 | 3 | **739** | 100% |
| The AI Conference | COMPLETED | 366 | 31 | **335** | 92% |
| AWS Re:Invent - Non-Amazon contacts - Catch-all | COMPLETED | 348 | 17 | **331** | 95% |
| AWS Re:Invent - Non-Amazon contacts - Valids | COMPLETED | 334 | 17 | **317** | 95% |
| [Trigger-based Campaign] Newly Hired Heads of AI | COMPLETED | 2316 | 2087 | **229** | 10% |
| Ag Tech - Catch-alls - Europe | PAUSED | 229 | 2 | **227** | 99% |
| Other Ex-Microsoft Employees | COMPLETED | 185 | 0 | **185** | 100% |
| TechCrunch attendees - fups (valids) | COMPLETED | 251 | 83 | **168** | 67% |
| SuperComputing - Low Priority - Valids | COMPLETED | 158 | 11 | **147** | 93% |
| [Client Similarity] Luma-like companies - Mario | PAUSED | 2735 | 2599 | **136** | 5% |
| SuperComputing - Low Priority - Catch-all | COMPLETED | 133 | 9 | **124** | 93% |
| TechCrunch attendees - fups (catch-alls) | COMPLETED | 129 | 8 | **121** | 94% |
| [Sales Sprint] Sales Sprint 2026 – London – Valids | COMPLETED | 2244 | 2124 | **120** | 5% |
| Ex-Microsoft Engineering Leaders | COMPLETED | 117 | 2 | **115** | 98% |
| [Events Visiting] AI4 2025 - Valids | COMPLETED | 1373 | 1262 | **111** | 8% |
| [Exploratory] AWS S3 | PAUSED | 1127 | 1022 | **105** | 9% |
| TechCrunch Attendees | COMPLETED | 147 | 48 | **99** | 67% |
| SuperComputing - High Priority - Valids | COMPLETED | 111 | 14 | **97** | 87% |
| [Sales Sprint] Sales Sprint 2026 – London – Catch-alls | COMPLETED | 1863 | 1767 | **96** | 5% |
| [Credit Unions] Credit Unions – No AI Adoption – V2 | COMPLETED | 807 | 714 | **93** | 12% |
| [Events Visiting] AI4 2026 - Mario - Valids | ACTIVE | 254 | 167 | **87** | 34% |
| [Credit Unions] Credit Unions – No AI Adoption – V1 | COMPLETED | 804 | 719 | **85** | 11% |
| [Events Visiting] AI4 2025 - Catch-alls | COMPLETED | 984 | 902 | **82** | 8% |
| TechCrunch speakers | COMPLETED | 90 | 8 | **82** | 91% |
| TechCrunch speakers - fups | COMPLETED | 88 | 7 | **81** | 92% |
| [Events Visiting] AI4 2026 - Rune - Catch-alls | ACTIVE | 227 | 148 | **79** | 35% |
| [Events Visiting] AI4 2026 - Rune - Valids | ACTIVE | 204 | 134 | **70** | 34% |
| [Events Visiting] AI4 2026 - Mario - Catch-alls | ACTIVE | 206 | 142 | **64** | 31% |
| Industrial IoT - 7.2025 | COMPLETED | 886 | 827 | **59** | 7% |
| Voice & AI conference speakers | COMPLETED | 55 | 3 | **52** | 95% |
| SuperComputing - High Priority - Catch-alls - copy | COMPLETED | 56 | 8 | **48** | 86% |
| [Sales Sprint] Sales Sprint London | COMPLETED | 466 | 419 | **47** | 10% |
| (Outlook) Fintech AI case-base | COMPLETED | 592 | 546 | **46** | 8% |
| Microsoft Build 2025 - Valids | COMPLETED | 919 | 875 | **44** | 5% |
| Ag Tech - Catch-alls - APAC | COMPLETED | 40 | 0 | **40** | 100% |
| (Gmail + Mailreef) Fintech AI case-base | COMPLETED | 693 | 654 | **39** | 6% |
| [Sales Sprint] Sales Sprint 2026 - Switzerland | COMPLETED | 2749 | 2712 | **37** | 1% |
| [Events Visiting] ViVE 2026 - Valids | COMPLETED | 718 | 687 | **31** | 4% |
| ReWork AI in Finance - Valid | COMPLETED | 51 | 20 | **31** | 61% |
| Microsoft Build 2025 - Catch-alls | COMPLETED | 311 | 286 | **25** | 8% |
| Databricks Data + AI Summit 2025 - Catch-Alls | PAUSED | 550 | 527 | **23** | 4% |
| [Events Visiting] Money 20/20 2025 - Catch-alls | COMPLETED | 717 | 694 | **23** | 3% |
| ReWork AI in Finance - Catch-alls | COMPLETED | 38 | 15 | **23** | 61% |
| [Events Visiting] HumanX 2026 - CEO - Valids/Catch-alls | COMPLETED | 434 | 412 | **22** | 5% |
| [Events Visiting] AI Summit NYC 2025 - Valids | COMPLETED | 435 | 413 | **22** | 5% |
| [Events Visiting] HumanX 2026 - Catch-alls | COMPLETED | 282 | 260 | **22** | 8% |
| [Events Visiting] TechEx Americas 2026 - Catch-alls | COMPLETED | 360 | 338 | **22** | 6% |
| [Events Visiting] HumanX 2026 - Valids | COMPLETED | 380 | 360 | **20** | 5% |
| [Events Visiting] TechEx 2025 - Valids - Sergey Contacts | COMPLETED | 353 | 333 | **20** | 6% |
| AI Summit NYC - High Priority - Catch-alls | COMPLETED | 165 | 145 | **20** | 12% |
| [Client Similarity] Luma-like companies - Sergey | PAUSED | 346 | 326 | **20** | 6% |
| [SERP] Databricks Data + AI Summit 2025 - Later Campaign | COMPLETED | 168 | 148 | **20** | 12% |
| [Sales Sprint] European Sales Sprint 2026 - Munich and B | COMPLETED | 1159 | 1140 | **19** | 2% |
| [Events Visiting] TechEx 2025 - Catch-alls - Sergey Cont | COMPLETED | 338 | 320 | **18** | 5% |
| [Events Visiting] Money 20/20 2025 - Valids | COMPLETED | 816 | 799 | **17** | 2% |
| [Events Visiting] TechEx Americas 2026 - Valids | COMPLETED | 422 | 405 | **17** | 4% |
| ARM64 - Can | COMPLETED | 70 | 55 | **15** | 21% |
| AI Summit NYC - High Priority - Valids | COMPLETED | 163 | 149 | **14** | 9% |
| AI Summit NYC - Mid Priority - Catch-alls | COMPLETED | 75 | 61 | **14** | 19% |
| ARM Post Likers - Non-ARM campaign | COMPLETED | 17 | 3 | **14** | 82% |
| [Events Visiting] TechEx 2025 - Bendetto Contacts | COMPLETED | 279 | 266 | **13** | 5% |
| AI Summit - Valid | COMPLETED | 45 | 33 | **12** | 27% |
| [Events Visiting] ViVE 2026 - Catch-alls | COMPLETED | 318 | 307 | **11** | 3% |
| Microsoft Build 2025 - Mario Contacts - Valids  | COMPLETED | 254 | 243 | **11** | 4% |
| [Events Visiting] AI Summit NYC 2025 - Catch-alls | COMPLETED | 353 | 343 | **10** | 3% |
| Databricks Data + AI Summit 2025 - Valids  | PAUSED | 176 | 166 | **10** | 6% |
| AI Summit - Catch-alls | COMPLETED | 48 | 38 | **10** | 21% |
| NVIDIA GTC 2025 - High Priority - Valids | PAUSED | 499 | 490 | **9** | 2% |
| Microsoft Build 2025 - Mirza Contacts - Valids | COMPLETED | 286 | 277 | **9** | 3% |
| [Events Visiting] Microsoft Ignite 2025 - Valids | COMPLETED | 177 | 170 | **7** | 4% |
| AI Summit NYC - Mid Priority - Valids | COMPLETED | 117 | 110 | **7** | 6% |
| [Sales Sprint] European Sales Sprint 2025 - Valids | COMPLETED | 983 | 977 | **6** | 1% |
| NVIDIA GTC 2025 - High Priority - Attendees Batch 2 | COMPLETED | 265 | 259 | **6** | 2% |
| Microsoft Build 2025 - Bill Contacts - Valids  | COMPLETED | 224 | 218 | **6** | 3% |
| ReWork AI in Finance - Potential Attendees - Catch-alls | COMPLETED | 78 | 72 | **6** | 8% |
| Test Campaign | COMPLETED | 8 | 2 | **6** | 75% |
| NVIDIA GTC 2025 - Low Priority - Catch-alls | PAUSED | 201 | 196 | **5** | 2% |
| NVIDIA GTC 2025 - High Priority - Catch-alls | PAUSED | 168 | 163 | **5** | 3% |
| Microsoft Ignite  - Valid | COMPLETED | 301 | 296 | **5** | 2% |
| NVIDIA GTC - Bendetto Contacts - First 150 Contacts | COMPLETED | 350 | 346 | **4** | 1% |
| NVIDIA GTC 2025 - Low Priority - Valids | PAUSED | 359 | 355 | **4** | 1% |
| [Events Visiting] Web Summit 2025 - Valids - Sergey Cont | COMPLETED | 302 | 298 | **4** | 1% |
| [Events Visiting] ITEXPO 2026 - Catch-alls | COMPLETED | 58 | 54 | **4** | 7% |
| Test Campaign - copy - copy | COMPLETED | 5 | 1 | **4** | 80% |
| [Sales Sprint] European Sales Sprint 2025 - Catch-all | COMPLETED | 362 | 359 | **3** | 1% |
| Databricks Data + AI Summit 2025 - Later Campaign to Sco | COMPLETED | 121 | 118 | **3** | 2% |
| [Events Visiting] ITEXPO 2026 - Valids | COMPLETED | 115 | 113 | **2** | 2% |
| AI Summit NYC - Not Finished Contacts | COMPLETED | 127 | 125 | **2** | 2% |
| AI-case-based  | COMPLETED | 488 | 487 | **1** | 0% |
| [Events Visiting] Web Summit 2025 - Catch-alls - Sergey  | COMPLETED | 164 | 163 | **1** | 1% |
| [EVENT] Testing Auto Adding Hypothesis | COMPLETED | 1 | 0 | **1** | 100% |
| FUP 2 (Outlook) Fintech AI case-base | COMPLETED | 1592 | 1592 | **0** | 0% |
|  Fintech AI case-base - FUP 3 | COMPLETED | 1489 | 1489 | **0** | 0% |
| Ag Tech - Valids - USA | COMPLETED | 727 | 727 | **0** | 0% |
| FUP (Gmail + Mailreef) Fintech AI case-base | COMPLETED | 1190 | 1190 | **0** | 0% |
| Ag Tech - Valids - Europe | COMPLETED | 398 | 398 | **0** | 0% |
| FUP (Outlook) Fintech AI case-base | COMPLETED | 528 | 528 | **0** | 0% |
| AI Summit NYC - Post Conference Outreach - Valids | COMPLETED | 266 | 266 | **0** | 0% |
| AWS Re:Invent - Amazon-related contacts - Catch-all | COMPLETED | 310 | 310 | **0** | 0% |
| Microsoft Ignite  - Catch-alls | COMPLETED | 289 | 289 | **0** | 0% |
| AI Summit NYC - Post Conference Outreach - Catch-Alls | COMPLETED | 134 | 134 | **0** | 0% |
| Ag Tech - Valids - APAC | COMPLETED | 91 | 91 | **0** | 0% |
| VC Contacts - Batch 1 | COMPLETED | 95 | 95 | **0** | 0% |
| ReWork AI in Finance - Potential Attendees - Valids | COMPLETED | 36 | 36 | **0** | 0% |
| Lead Nurturing - Mario | COMPLETED | 8 | 8 | **0** | 0% |
| Test Campaign - copy | COMPLETED | 3 | 3 | **0** | 0% |
| [Lead Nurture] Sergey | COMPLETED | 1 | 1 | **0** | 0% |

## Two patterns worth seeing

**1. The gap is not spread evenly — a set of older lists is missing almost entirely.**

| campaign | contacted | missing | gap |
|---|---|---|---|
| Ag Tech - Catch-alls - USA | 742 | 739 | 100% |
| Other Ex-Microsoft Employees | 185 | 185 | 100% |
| Ag Tech - Catch-alls - APAC | 40 | 40 | 100% |
| Ex-Microsoft Engineering Leaders | 117 | 115 | 98% |
| AWS Re:Invent - Non-Amazon - Catch-all | 348 | 331 | 95% |
| Voice & AI conference speakers | 55 | 52 | 95% |

Meanwhile `Ag Tech - Valids - USA` is 727/727 present and 16 other campaigns are at 0% missing. So
these look like **whole lists that were emailed but never loaded into Pipedrive**, rather than a
trickle of individual failures. Catch-all lists are consistently the worse half. We have not
established why — it predates the current automation and we did not investigate the older lists in
this pass. Worth a decision on whether those contacts matter enough to import.

**2. The four live Ai4 campaigns sit at 31–35%,** which is the failure we diagnosed this week and
the one that is still active. Details in `PROD_ISSUES_2026-08-04.md`.

## Hand-patching so far

**Pipedrive does not expose who created a *person* through its API** — not on `/v1/persons`, not on
`/api/v2/persons`, and `include_fields=creator_user_id` is rejected outright. So "how many persons
did Slava add by hand" is not answerable from the API; only the UI changelog holds it. We are not
going to put a number on it that we cannot support. (This is the same limitation that misled the
earlier label-clobber investigation.)

*Leads* do carry a creator. Since 2026-08-01, 164 leads were created:

| created by | leads |
|---|---|
| our automation (API token) | 160 |
| Marci Csomor | 2 |
| Slava Kraievskyi | **1** |
| Jim Ash | 1 |

Slava's one is `Person-6b93835c | Trillion.com lead` (person 84958, 2026-08-01T19:30:30Z) — created a day
after Marc replied to us, because no lead existed for him. That is the hand-patching pattern, and at
one lead it is clearly not keeping up with a 5,469-person gap.

## Reminder: the fix is waiting on you

The backfill for the Ai4 gap is written, dry-run clean and **has never been run** — it needs your go. It creates one person per missing prospect, re-checking each address immediately before writing so nothing is duplicated:

```
would create : 300
skipped      : 0 (already present on re-verify)
DRY RUN COMPLETE - nothing was written.
```

Separately, **58 prospects already have a lead attached to the wrong person** — the current automation matches people by *name*, so e.g. our email to `pii-9e8228ef@example.invalid` landed on a Person-b0e89e97 at `pii-9f60732e@example.invalid`. Those need a human decision (merge vs re-point) per row: `mis_attached_leads.csv`. Fixing the name-matching is what stops the gap growing; the backfill only cleans up what already happened.

