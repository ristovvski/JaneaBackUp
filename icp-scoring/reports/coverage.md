# Phase 0 — Pipedrive organization coverage audit

**Read-only.** This run issued only GET requests and made no writes of any kind.

- **Mode:** live
- **Scope:** FULL PASS over 21621 organizations via GET /api/v2/organizations, with custom field keys resolved via GET /v1/organizationFields. Read-only.
- **Organizations analysed:** 21621
- **add_time range:** 2020-04-11T03:39:37Z → 2026-09-09T13:01:33Z
- **Generated:** 2026-09-09T13:51:13.933Z

---

## 1. Can we identify an organization? (the Phase 1 gate)

`engine/normalize.mjs` `resolveIdentifier()` picks **domain → LinkedIn company URL → name**.
This is what Clay receives, so this table is the ceiling on enrichment quality.

| Signal | Orgs | Share | Meaning |
| --- | ---: | ---: | --- |
| Native `website` non-empty | 925 | 4.3% | a value is present |
| → of those, a **usable root domain** | 870 | 4.0% | survives normalization and is not an aggregator |
| Native `linkedin` non-empty | 909 | 4.2% | a value is present |
| → **usable LinkedIn company URL** (either field) | 938 | 4.3% | includes URLs recovered from the website field |
| **Neither** domain nor LinkedIn | 20658 | 95.5% | scored from name + HQ at low confidence (NEEDS_DECISION #5) |
| → of those, at least a usable name | 20644 | 95.5% | still scoreable |
| No usable name at all | 14 | 0.1% | not scoreable — cannot even be looked up |

**Read this before Tuesday.** 4.0% of organizations yield a usable root
domain. The other 96.0% reach Clay as a LinkedIn URL or as a bare
name, and a bare name is explicitly a low-confidence identifier. Since `revenue_range`,
`stage_maturity` and `company_type` all gate `insufficient_data`, expect a
substantial share of first-pass results to come back **Insufficient data** rather than graded.
That is the system working as specified, not a failure — but it is what the demo will show.

## 1b. What the legacy custom URL fields would add (NEEDS_DECISION #10)

Phase 1 reads only the **native** `website` and `linkedin`. FIELD_AUDIT.md
(2026-07-23) flagged four overlapping custom URL fields; the fill rates in §4
say they are far better populated. This is the union, measured:

| Identifier source | Orgs | Share |
| --- | ---: | ---: |
| Native `website` / `linkedin` only (what Phase 1 reads today) | 963 | 4.5% |
| **Adding the legacy custom fields** | 7703 | 35.6% |
| → organizations recoverable ONLY via a custom field | 6740 | 31.2% |

Per-field contribution (usable value present, may overlap):

| Custom field | Usable | Share |
| --- | ---: | ---: |
| `lh_linkedin_profile_url` | 5511 | 25.5% |
| `Website` | 4191 | 19.4% |
| `Website URL` | 1731 | 8.0% |
| `lh_website` | 1458 | 6.7% |
| `LinkedIn URL` | 1248 | 5.8% |

**This is the highest-leverage change available to Phase 1.** Reading the
custom fields as a fallback moves identifier coverage from
**4.5%** to **35.6%** —
6740 organizations that today reach Clay as a bare name
would arrive with a domain or a LinkedIn URL instead. Mechanically it is a
CONFIG list and three lines in `resolveIdentifier`. It is **NEEDS_DECISION**
because which of the overlapping fields is canonical, and what to do when two
disagree, is a data-ownership question.

## 2. Data-quality defects in the identifier fields

These are the ones that would silently corrupt a score rather than fail loudly.

| Defect | Count | Share | Why it matters |
| --- | ---: | ---: | --- |
| `website` holds a LinkedIn **company** URL | 49 | 0.2% | naive domain normalization yields `linkedin.com` → Clay enriches LinkedIn Corporation |
| `website` holds another LinkedIn URL (person/school) | 1 | 0.0% | same failure, and not recoverable as a company |
| `website` holds another aggregator/social host | 5 | 0.0% | enriches the platform, not the company |
| `website` unparseable | 0 | 0.0% | placeholder text, prose, or a malformed URL |
| `linkedin` is not a company URL | 11 | 0.1% | a person profile is not a company identifier |

### Sample: LinkedIn company URLs stored in `website`

| org id | name | website value |
|---|---|---|
| 21111 | Openlayer | `https://www.linkedin.com/company/openlayerco/` |
| 21114 | SponsorUnited | `https://www.linkedin.com/company/sponsorunited` |
| 21120 | Digital.ai | `https://www.linkedin.com/company/digitaldotai` |
| 21143 | Scout AI | `https://www.linkedin.com/company/draper-associates` |
| 21147 | Paramount+ | `https://www.linkedin.com/company/paramountco` |
| 21162 | Automotive Ventures | `https://www.linkedin.com/company/automotive-ventures` |
| 21181 | Trustible | `https://www.linkedin.com/company/trustible` |
| 21219 | PeopleReign | `https://www.linkedin.com/company/augerai` |

**Handled.** `resolveIdentifier()` tries `normalizeLinkedInCompanyUrl` on the website field
before treating it as a domain, so these are routed to the `linkedin` identifier kind instead of
collapsing to `linkedin.com`. Note that the sampled rows show the LinkedIn URL does not always
name the same company as the org record — that is a data problem no normalizer can fix, and a
reason to prefer the native `linkedin` field where both are present.


### Sample: aggregator hosts in `website`

| org id | name | website value |
|---|---|---|
| 576 | Google | `google.com` |
| 3904 | Google | `http://google.com/` |
| 15745 | Google BigQuery | `https://www.google.com/about/careers/applications/` |
| 16116 | Google DeepMind | `google.com` |
| 20506 | Mandiant | `https://cloud.google.com/security` |


## 3. Duplicate clusters

A duplicate cluster means two or more organization records that Phase 1 would score
**separately**, producing two grades for one company and two notes for one buyer.

| Clustering key | Clusters | Orgs in a cluster | Excess records |
| --- | ---: | ---: | ---: |
| Root domain (`normalizeDomain`) | 24 | 57 (0.3%) | 33 |
| Normalized name (`normalizeCompanyName`) | 1381 | 6202 (28.7%) | 4821 |

### Largest domain clusters

- **oracle.com** — 5 records: Oracle (#3903), Oracle (#7037), Oracle (#7043), Oracle (#7044), Oracle (#18374)
- **salesforce.com** — 4 records: Salesforce (#7572), Salesforce (#7573), Salesforce (#7574), Salesforce (#7575)
- **microsoft.com** — 3 records: Microsoft (#611), Microsoft (#2702), Microsoft (#16374)
- **amazon.com** — 3 records: Amazon (#847), Amazon Web Services (AWS) (#965), Amazon (#14800)
- **morganstanley.com** — 3 records: Morgan Stanley (#2866), Morgan Stanley (#9865), Morgan Stanley (#14487)
- **mastercard.com** — 3 records: Mastercard (#14377), Mastercard (#17705), Mastercard (#18554)
- **cisco.com** — 2 records: Cisco (#838), Cisco (#13449)
- **hpe.com** — 2 records: Hewlett Packard Enterprise (#890), Hewlett Packard Enterprise (#5545)
- **fidelity.com** — 2 records: Fidelity Investments (#1842), Fidelity Investments (#9326)
- **rbc.com** — 2 records: RBC (#1960), RBC (#10124)


### Largest normalized-name clusters

- **oracle** — 708 records: Oracle (#826), Oracle (#3537), Oracle (#3903), Oracle (#6432), Oracle (#6433), Oracle (#6434), …
- **adp** — 174 records: ADP (#4108), ADP (#4109), ADP (#4110), ADP (#4111), ADP (#4112), ADP (#4113), …
- **salesforce** — 148 records: Salesforce (#210), Salesforce (#7526), Salesforce (#7527), Salesforce (#7528), Salesforce (#7529), Salesforce (#7530), …
- **vmware** — 103 records: Vmware (#945), VMware (#3556), VMware (#8341), VMware (#8342), VMware (#8343), VMware (#8344), …
- **hewlett packard enterprise** — 99 records: Hewlett Packard Enterprise (#890), Hewlett Packard Enterprise (#5545), Hewlett Packard Enterprise (#5546), Hewlett Packard Enterprise (#5547), Hewlett Packard Enterprise (#5548), Hewlett Packard Enterprise (#5549), …
- **adobe** — 90 records: Adobe (#575), Adobe (#4019), Adobe (#4020), Adobe (#4021), Adobe (#4022), Adobe (#4023), …
- **cerner** — 89 records: Cerner Corporation (#4775), Cerner Corporation (#4777), Cerner Corporation (#4778), Cerner Corporation (#4779), Cerner Corporation (#4780), Cerner Corporation (#4781), …
- **sap north america** — 76 records: SAP North America (#7709), SAP North America (#7710), SAP North America (#7711), SAP North America (#7712), SAP North America (#7713), SAP North America (#7714), …
- **netapp** — 63 records: NetApp (#6240), NetApp (#6242), NetApp (#6243), NetApp (#6244), NetApp (#6245), NetApp (#6246), …
- **amdocs** — 60 records: Amdocs (#1448), Amdocs (#4349), Amdocs (#4350), Amdocs (#4351), Amdocs (#4352), Amdocs (#4353), …


**Out of Phase 1 by scope.** Dedup and org creation are explicitly not in this build. The audit
records the size of the problem so the decision to defer it is an informed one. The practical
consequence for the demo: a duplicated company can show two different grades, and the honest
answer to "why?" is "because there are two records."

## 4. Organizations already carrying an ICP field

Matched ICP-ish fields: `ICP Calculated`, `ICP Score`, `ICP Scored At`, `ICP Model Version`, `ICP Final`.
**0 organizations (0.0%) already carry a value in at least one.**
Those values were written by a human or a prior process. `ICP Final` is never touched;
`ICP Calculated` is overwritten only when the computed value differs.

### Custom-field fill rates in this scope

| Field | Type | Non-empty | Share |
| --- | --- | ---: | ---: |
| `Number of Employees` | double | 11414 | 52.8% |
| `Industry` | varchar | 9366 | 43.3% |
| `Company Revenue` | monetary | 9139 | 42.3% |
| `lh_linkedin_profile_url` | text | 5545 | 25.6% |
| `Website` | text | 4204 | 19.4% |
| `lh_company_id` | text | 3397 | 15.7% |
| `Website URL` | varchar | 1743 | 8.1% |
| `lh_website` | text | 1464 | 6.8% |
| `Company Phone` | phone | 1284 | 5.9% |
| `LinkedIn URL` | text | 1264 | 5.8% |
| `Linked web visitor` | varchar | 975 | 4.5% |
| `Latest web visit` | date | 906 | 4.2% |
| `Org Subscription ID` | varchar | 127 | 0.6% |
| `D-U-N-S Number` | double | 1 | 0.0% |
| `Unique Entity ID` | varchar | 1 | 0.0% |
| `CAGE Code` | varchar | 0 | 0.0% |
| `Company Description` | varchar | 0 | 0.0% |
| `lh_public_id` | text | 0 | 0.0% |
| `lh_industry` | text | 0 | 0.0% |
| `lh_headquarter_country` | text | 0 | 0.0% |
| `Source` | enum | 0 | 0.0% |
| `ICP Calculated` | enum | 0 | 0.0% |
| `ICP Score` | double | 0 | 0.0% |
| `ICP Scored At` | date | 0 | 0.0% |
| `ICP Model Version` | varchar | 0 | 0.0% |
| `ICP Final` | enum | 0 | 0.0% |

---

## Findings that change the build

1. **The native `website` field is not a clean domain source.** It is the field
   `resolveIdentifier()` reads first, and in this scope
   55
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
