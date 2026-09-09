# Phase 0 — Pipedrive organization coverage audit

**Read-only.** This run issued only GET requests and made no writes of any kind.

- **Mode:** pages
- **Scope:** SAMPLE of 2000 organizations from 4 saved getOrganizations page(s) in `/tmp/claude-0/-home-user-Janea/382d731f-1221-5b02-af27-c8f60b31eea5/scratchpad/pd`, newest-first by add_time. Custom field keys are NOT resolved to names in this mode (that needs GET /api/v2/organizationFields, which needs a token).
- **Organizations analysed:** 2000
- **add_time range:** 2026-05-02T03:28:19Z → 2026-09-08T22:23:53Z
- **Generated:** 2026-09-09T09:01:29.420Z

---

## 1. Can we identify an organization? (the Phase 1 gate)

`engine/normalize.mjs` `resolveIdentifier()` picks **domain → LinkedIn company URL → name**.
This is what Clay receives, so this table is the ceiling on enrichment quality.

| Signal | Orgs | Share | Meaning |
| --- | ---: | ---: | --- |
| Native `website` non-empty | 441 | 22.1% | a value is present |
| → of those, a **usable root domain** | 392 | 19.6% | survives normalization and is not an aggregator |
| Native `linkedin` non-empty | 418 | 20.9% | a value is present |
| → **usable LinkedIn company URL** (either field) | 451 | 22.6% | includes URLs recovered from the website field |
| **Neither** domain nor LinkedIn | 1537 | 76.8% | scored from name + HQ at low confidence (NEEDS_DECISION #5) |
| → of those, at least a usable name | 1537 | 76.8% | still scoreable |
| No usable name at all | 0 | 0.0% | not scoreable — cannot even be looked up |

**Read this before Tuesday.** 19.6% of organizations yield a usable root
domain. The other 80.4% reach Clay as a LinkedIn URL or as a bare
name, and a bare name is explicitly a low-confidence identifier. Since `revenue_range`,
`stage_maturity` and `company_type` all gate `insufficient_data`, expect a
substantial share of first-pass results to come back **Insufficient data** rather than graded.
That is the system working as specified, not a failure — but it is what the demo will show.

## 2. Data-quality defects in the identifier fields

These are the ones that would silently corrupt a score rather than fail loudly.

| Defect | Count | Share | Why it matters |
| --- | ---: | ---: | --- |
| `website` holds a LinkedIn **company** URL | 48 | 2.4% | naive domain normalization yields `linkedin.com` → Clay enriches LinkedIn Corporation |
| `website` holds another LinkedIn URL (person/school) | 0 | 0.0% | same failure, and not recoverable as a company |
| `website` holds another aggregator/social host | 1 | 0.1% | enriches the platform, not the company |
| `website` unparseable | 0 | 0.0% | placeholder text, prose, or a malformed URL |
| `linkedin` is not a company URL | 6 | 0.3% | a person profile is not a company identifier |

### Sample: LinkedIn company URLs stored in `website`

| org id | name | website value |
|---|---|---|
| 22386 | Massachusetts Biotechnology Council | `https://www.linkedin.com/company/concertai` |
| 22383 | Potato | `https://www.linkedin.com/company/science-exchange` |
| 22367 | CapeStart, Inc | `https://www.linkedin.com/company/cape-start` |
| 22364 | OmicsBank | `https://www.linkedin.com/company/phablecare` |
| 22353 | ThirdPartyIQ | `https://www.linkedin.com/company/360factors` |
| 22348 | Plexo | `https://www.linkedin.com/company/archwayfinance/` |
| 22341 | Vertice AI | `https://www.linkedin.com/company/verticeai` |
| 22331 | Stoa | `https://www.linkedin.com/company/ekstasy` |

**Handled.** `resolveIdentifier()` tries `normalizeLinkedInCompanyUrl` on the website field
before treating it as a domain, so these are routed to the `linkedin` identifier kind instead of
collapsing to `linkedin.com`. Note that the sampled rows show the LinkedIn URL does not always
name the same company as the org record — that is a data problem no normalizer can fix, and a
reason to prefer the native `linkedin` field where both are present.


### Sample: aggregator hosts in `website`

| org id | name | website value |
|---|---|---|
| 20506 | Mandiant | `https://cloud.google.com/security` |


## 3. Duplicate clusters

A duplicate cluster means two or more organization records that Phase 1 would score
**separately**, producing two grades for one company and two notes for one buyer.

| Clustering key | Clusters | Orgs in a cluster | Excess records |
| --- | ---: | ---: | ---: |
| Root domain (`normalizeDomain`) | 1 | 2 (0.1%) | 1 |
| Normalized name (`normalizeCompanyName`) | 23 | 49 (2.5%) | 26 |

> **Sample caveat, and it is a big one.** Duplicate detection on a sample
> systematically *undercounts*: for two records of one company to be seen as a pair, both must fall
> inside the sample. On a 2000-record slice of a larger collection the true cluster count is
> materially higher than the figure above. Treat these numbers as a floor, and re-run in live mode
> for the real count.

### Largest domain clusters

- **mymetasoftware.com** — 2 records: myMeta (#20467), myMeta Software (#20398)


### Largest normalized-name clusters

- **sumersports** — 5 records: Sumersports (#21730), Sumersports (#20686), Sumersports (#20685), Sumersports (#20684), Sumersports (#20683)
- **stmicroelectronics** — 2 records: STMicroelectronics (#22194), STMicroelectronics (#22167)
- **altamont technical services** — 2 records: Altamont Technical Services (#22177), Altamont TEchnical Services (#20515)
- **kbr** — 2 records: KBR, Inc. (#22112), KBR (#21313)
- **corelation** — 2 records: Corelation, Inc. (#22072), Corelation (#21915)
- **magnet forensics** — 2 records: Magnet Forensics (#22055), Magnet Forensics (#21474)
- **fico** — 2 records: FICO (#21998), FICO® (#21309)
- **norstella** — 2 records: Norstella (#21987), Norstella (#21377)
- **veracity insurance solutions** — 2 records: Veracity Insurance Solutions (#21836), Veracity Insurance Solutions, LLC (#21130)
- **accumetrics** — 2 records: Accumetrics (#21736), Accumetrics Limited (#21674)


**Out of Phase 1 by scope.** Dedup and org creation are explicitly not in this build. The audit
records the size of the problem so the decision to defer it is an informed one. The practical
consequence for the demo: a duplicated company can show two different grades, and the honest
answer to "why?" is "because there are two records."

## 4. Organizations already carrying an ICP field

**Not determinable in `pages` mode.** Matching a field by *name* needs `GET /api/v2/organizationFields`, which needs `PIPEDRIVE_API_TOKEN`. Re-run in live mode to answer this. What the sample does show is the per-key fill rate below.

### Custom-field fill rates in this scope

| Field key | Name | Non-empty | Share |
| --- | --- | ---: | ---: |
| `7dc680a381ed…` | _(needs a token to resolve)_ | 110 | 5.5% |

---

## Findings that change the build

1. **The native `website` field is not a clean domain source.** It is the field
   `resolveIdentifier()` reads first, and in this scope
   49
   record(s) hold something that is not the company's own domain. `resolveIdentifier()` handles
   this by trying the LinkedIn parse first and rejecting aggregator hosts — without that, those
   organizations would be enriched as LinkedIn, Facebook or Google.
2. **`docs/DISCOVERY/FIELD_AUDIT.md` (2026-07-23) found four overlapping custom URL fields** on
   organizations — `Website`, `LinkedIn URL`, `lh_website`, `Website URL` — at 20.7 / 18.0 /
   17.7 / 17.7% fill. Phase 1 reads only the **native** `website` and `linkedin` fields.
   If the native fields are emptier than those custom fields, identifier coverage improves by
   reading the custom fields as a fallback. That is a one-line CONFIG addition, and it is
   **NEEDS_DECISION**: which of the four is canonical is a data-ownership question, not a
   technical one.
3. **Duplicates are real and out of scope.** See §3.

## How to re-run

```bash
# Full audit (read-only; needs a token with read access to organizations)
PIPEDRIVE_API_TOKEN=... npm run audit:coverage

# From saved MCP pages, no token needed
node scripts/pipedrive_audit_coverage.mjs --pages ./pd-pages
```
