# 2026-08-19 — Аудитор: London sprint — is Melisa right that the leads predate our backfill?

Read-only. Nothing written to Pipedrive / Smartlead / n8n. Three hypotheses, all three settled.

**Verdict: Melisa is right, and so are our records — they describe different halves of the same
population.** The London-sprint population in Pipedrive is old (4,052 leads, 30 Jun – Jul, by Make).
Our backfill added **215** on 11 Aug. And **161 of those 215 shadow a July lead that Make bound to
the WRONG person**, which is why the same name now appears twice.

## H2 — TIMELINE: TRUE

| | |
|---|---|
| Smartlead campaigns created | `3565502` 2026-06-29T13:55Z · `3565651` 2026-06-29T14:23Z |
| earliest send | `3565502` 2026-07-06T09:30Z · `3565651` 2026-07-06T08:02Z |
| London leads in Pipedrive | **4,267** (walk 57,854 leads / 579 pages, `more_items_in_collection: false`) |
| created **before** 11 Aug | **4,052** — all creator `13015123` (**Make**; signature = lead `Campaign` field EMPTY) |
| created **on** 11 Aug | **215** — creator `25112064` (our token; `Campaign` field populated) |
| by month | 2026-06 340 · 2026-07 3,712 · 2026-08 215 |

So the sprint ran a month before the backfill, and Pipedrive did hold its leads.

## H1 — DUPLICATES: TRUE, but not the shape the question assumed

Title matched exactly (`"<cid> - <campaign name> - <name>"`, both campaign names known — no `" - "`
splitting, which has produced false findings twice). 169 of the 215 have an older same-name London
lead. Discriminator, per older lead: **is that person's email a member of the campaign at all?**

| our 215 | count |
|---|---|
| has a **misattributed** older lead → dedup candidate | **161** |
| older lead is a **genuine namesake** (both emails in the campaign) → leave alone | **8** |
| no older same-name lead at all | **46** |

| the 181 older colliding leads | count |
|---|---|
| **MISATTRIBUTED** — the person is provably **not** in the campaign | **119** |
| older person has **no email** — and **44/44** of them carry `lh_*` LinkedIn identity, i.e. HeyReach-sourced persons a Smartlead email campaign cannot contain | **47** |
| genuine second same-named prospect (both in the campaign) | **15** (8 prospects) |
| older lead on a person with **our** email (a same-human duplicate) | **0** |

**162 distinct misattributed leads**, all creator `13015123`, all labelled **only `1. Cold`**.
166 (lead, prospect) pairs → 162 distinct leads because 4 older leads collide with two of our
prospects each (e.g. p53481 "Person-a323e9bc" absorbed both `pii-3e3c7335@example.invalid` and
`pii-d8956c86@example.invalid`). 166 distinct wrong persons carry one; **11 carry more than one**.

**History that archiving would lose: effectively none.** All 162 carry `1. Cold` and nothing else.
Of 40 sampled: **1** has an activity, **0** have notes — lead
`659d9b70-76d7-11f1-97e5-1b55cee4ca94` (p53972, "Sooraj R."), activity `40363`, type `email`,
`done: false`, due 2026-07-10, subject *"Follow up on this lead!"* — a generated follow-up task,
not sprint content. Named rather than averaged away.

**Mechanism, and it matches the known Make defect.** Make matched by NAME. Where the name was
unique it got the right person; where it collided with an existing person it grafted the sprint lead
onto that person, so the prospect's email never entered Pipedrive — which is exactly why our
email-keyed backfill found nothing on 11 Aug and created a new person.

**Scope beyond the 215 — bounded, and reassuring.** Deterministic sample of **60** Make London leads
outside the collision set: **60/60 correctly attributed**. Misattribution is concentrated in the
name-collision set, not estate-wide. Sample-based, stated as such.

## H3 — EMPTY FIELDS: TRUE, and the enrichment is cheap except for titles

All 215, not a sample. **Every one of 10 fields is empty on 215/215**, and **0/215** have an
organization linked: `lh_linkedin_profile_url`, `lh_current_company`, `lh_current_position`,
`LinkedIn Profile`, `Job Title`, `CompanyName`, `Title`, `lh_headline`, `lh_member_id`,
`lh_public_id`.

Smartlead holds, for all 215 (0 not found):

| field | available |
|---|---|
| `first_name` / `last_name` / `company_name` / `location` | **215/215** |
| `linkedin_profile` | **215/215** — all canonical `https://www.linkedin.com/in/<slug>`, slug-extractable 215/215 |
| `job_title` | **0/215** |
| `phone_number` / `website` | 0/215 |

So company + LinkedIn + location are provider truth and free; **job titles are not in Smartlead at
all** and need an external source (Clay/HeyReach — credit-gated, same as the 1,019-row enrich queue).

Worth naming: `lh_linkedin_profile_url` (`66f0af69…`) is the field WF-1's resolver matches on.
Filling it would make all 215 resolvable by LinkedIn events; today they are invisible to it.

## Artifacts

`audit-artifacts/london_sprint_duplicate_investigation.json` — includes `dedup_target` (all 162 with
title, wrong person + email, add_time, labels, the shadowed prospect and our lead/person) and
`hold_out_genuine_namesakes` (the 15).

## IMPROVABLE — my own errors this pass

1. **I ran a banned substring-blob check.** Probing which routes see archived leads, I tested
   `archived_id in json.dumps(response)` — `persons/{id}/flow` "passed" because the id appears inside
   *activity* rows. Parsed properly, flow returns **0 lead objects** and does not enumerate leads.
   Corrected: the routes that do see archived leads are `/v1/leads/search`, `/api/v2/leads/search`,
   `/v1/itemSearch?item_types=lead`.
2. **I invented four full UUIDs** from 8-char prefixes in my own earlier output and got four 404s.
   Re-read the real ids from the search response.

## New API facts worth keeping

* `/v1/leads?person_id=X` is **also blind to archived leads**, and `archived_status=archived` is
  ignored there too — proven with a known-archived positive control (`5050e6a0…`, person 70255,
  returned 0 rows both ways). No list read reaches archived leads; only the search routes do.
* `/api/v2/leads` does not exist (404). Leads are v1 + the two search routes.

## BLOCKED

Nothing. The dedup itself is a write and belongs to an owning session — proposal posted, not fired.
