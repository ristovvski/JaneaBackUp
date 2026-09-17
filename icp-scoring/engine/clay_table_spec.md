# Clay table `ICP_Engine` — build spec

Clay is built by hand in the UI. This is the exact column list, in order, with
types, sources and the contract each column has to satisfy. Everything that can
be tested offline lives elsewhere in this repo and is referenced below.

**Model version:** v6 · **Rows:** one per scoring request (not one per company —
a re-score creates a new row, so the history is preserved).

> **Provider choice is Nik's.** This spec fixes the *column contract* — name,
> type, nullability, and what the downstream formula expects. It deliberately
> does not fix the vendor for most columns. NEEDS_DECISION #9 default: Apollo is
> primary for revenue and funding; every other provider is a named slot.

---

## Source: Clay Webhook

The table is fed by a **Clay Webhook source**, not by a list import. n8n Path A
POSTs one JSON body per request. This is what makes ad-hoc scoring possible for
a company from a salesperson's own network rather than only batch enrichment
(the hard requirement from the 2026-07-10 scoping call).

Webhook body from n8n (`BuildClayRequest`):

```json
{
  "org_id":        10001,
  "deal_id":       55001,
  "domain":        "akuvo.com",
  "request_id":    "req-icp-0001",
  "callback_url":  "<n8n Path B webhook URL, from CONFIG>",
  "requested_at":  "2026-09-18T10:42:00Z",
  "model_version": "v6"
}
```

**Seven keys, and there is never an eighth.** `domain` is the ONE identifier.
It is already normalized by `engine/normalize.mjs` in n8n — lowercase, no
scheme, no `www.`, no path — so Clay never has to agree with n8n about what a
domain is, and it is never null: an organization whose Pipedrive **Website URL**
is empty, unparseable, or a directory (linkedin.com, crunchbase.com, a Wix
subdomain) is **not sent to this table at all**. n8n writes
`n/a - no website` on the organization and posts one activity asking for the
field; nothing is enriched and no credit is spent.

`org_id` and `deal_id` cross as **numbers**, because a column that is sometimes
`2695` and sometimes `"2695"` joins against nothing. `deal_id` may be null.
`requested_at` is the table's "today" for days-open arithmetic on job postings,
and it is what the Contracting guard measures evidence age against.

**Removed in v6.1**, and the columns should be deleted from the table rather
than left to arrive empty: `identifier_kind`, `identifier_value`,
`linkedin_url`, `company_name`, `hq_state`, `hq_country`. The first two
expressed "score this row from a company NAME", which the pipeline can no
longer do; the last four existed to make a name lookup land on the right
company of that name. With no name lookup there is nothing to disambiguate, and
the LinkedIn URL, the company name and the HQ pair are now **outputs** the table
discovers from the domain like any other fact.

---

## Columns, in order

### 1 — `request_id`  ·  text  ·  from webhook

The n8n correlation id. Carried through every artefact: the Clay row, the
`icp.scored` event, the Pipedrive note, the audit row and every Slack alert.
This is the one value that lets you follow a single scoring decision end to end.

### 2 — `org_id`, `deal_id`  ·  text  ·  from webhook

Pipedrive ids as **strings**. `deal_id` may be null (a re-score triggered
outside a deal). `org_id` is never null.

### 3 — `domain`  ·  text  ·  from webhook

The one identifier, and the one input every enrichment column starts from.
Never null. NEEDS_DECISION #5 is closed by Nik's ruling: an organization with
no usable Website URL is **not scored**, it is sent back to a human with the
one field it needs — so there is no name lookup, no LinkedIn fallback, and no
low-confidence guess at which of six companies with the same name was meant.

### 4 — `linkedin_url`, `company_name`, `hq_country`, `hq_state`  ·  text  ·  enrichment

**Outputs, not inputs.** In v6.0 these were seeded from the webhook and filled
in where null; the webhook no longer sends them, so they are discovered from
`domain` like any other fact. Nothing downstream may treat them as a second
identifier.

### 5 — Enrichment

Waterfall order, stopping at the first non-null:
**LinkedIn → website scrape → Apollo (primary) → fallback provider →
PredictLeads / LinkedIn Jobs → news.**

| Column | Type | Provider slot | Contract |
|---|---|---|---|
| `li_headcount` | integer | LinkedIn | ≥ 0 or null. Total, not engineering. |
| `li_industry` | text | LinkedIn | LinkedIn's own industry string, verbatim. Not mapped to a Janea vertical here — that is the classifier's job. |
| `li_description` | text | LinkedIn | The company's own description of itself. |
| `li_founded` | integer | LinkedIn | Year, ≥ 1800, or null. |
| `li_hq` | text | LinkedIn | Free-text HQ line. |
| `website_summary` | text | website scrape | **homepage + `/about` + `/product` + `/careers`**, summarized. All four pages: `/careers` is where capacity pressure shows and `/product` is where software-native vs software-dependent shows. Say which pages were reachable. |
| `revenue_estimate_usd` | number | Apollo (primary) | USD, ≥ 0, or null. **Never derived from headcount** — see the classifier prompt. |
| `revenue_source` | text | — | Which provider produced the estimate. Non-null whenever `revenue_estimate_usd` is non-null. |
| `funding_stage` | text | Apollo / fallback | e.g. `Series B`, `Public`, `Bootstrapped`. |
| `last_round_date` | date | Apollo / fallback | ISO 8601 or null. |
| `last_round_usd` | number | Apollo / fallback | USD or null. |
| `open_eng_roles_count` | integer | PredictLeads / LinkedIn Jobs | Engineering roles open now. |
| `eng_roles_open_60d_plus` | integer | PredictLeads / LinkedIn Jobs | Open **> 60 days**. The strongest available proxy for a documented capacity gap; the stage classifier leans on it. |
| `senior_eng_roles` | integer | PredictLeads / LinkedIn Jobs | Staff / principal / lead / head-of level. |
| `eng_headcount_estimate` | integer | LinkedIn / Apollo | Engineering headcount, or null. |
| `news_last_12mo` | JSON array | news provider | `[{ date, headline, source?, url? }]`. **Every item must carry a date** — `activation_state` cannot return `Contracting` without one, and an empty array `[]` is meaningful (we looked, nothing found) where null is not (we did not look). |

### 6 — `facts_json`  ·  formula

Builds the object defined by `engine/schemas/enrichment_facts.schema.json` from
columns 4–5. Rules:

- **Nulls are kept as null.** Never coerce to `0`, `""` or `"unknown"`. The
  classifiers are instructed to read null as "enrichment did not find it", and
  that distinction is the difference between `Insufficient data` and a wrong
  score.
- `additionalProperties` is `false` in the schema: adding an enrichment column
  means adding it to the schema too, or the row fails validation.
- Every key in the schema's `required` list is present, even when null.

### 7 — The seven classifiers  ·  AI (Claude, structured output, temperature 0)

| Column | Component | Prompt |
|---|---|---|
| `cls_industry` | `industry_vertical` | `_preamble.md` + `industry_vertical.md` |
| `cls_stage` | `stage_maturity` | `_preamble.md` + `stage_maturity.md` |
| `cls_type` | `company_type` | `_preamble.md` + `company_type.md` |
| `cls_geo` | `geography` | `_preamble.md` + `geography.md` |
| `cls_revenue` | `revenue_range` | `_preamble.md` + `revenue_range.md` |
| `cls_activation` | `activation_state` | `_preamble.md` + `activation_state.md` |
| `cls_buying` | `buying_signal` | `_preamble.md` + `buying_signal.md` |

Each prompt is assembled as **`_preamble.md` + the component prompt +
`facts_json`**, in that order. Every output is validated against
`engine/schemas/classifier_output.schema.json`, which closes `value` per
component: a level classifier cannot return `"FinTech"` and the vertical
classifier cannot return `10`.

Settings, all seven identical:

- **Temperature 0.** Non-negotiable: a score that changes between runs cannot be
  audited or re-derived.
- **Structured output** against the schema. Not "return JSON" in the prompt and
  hope.
- **No web access, no tools.** The preamble forbids browsing; removing the
  capability makes it true rather than requested.
- One component per call. Seven calls, not one call returning seven answers —
  so a single bad component fails alone and is retried alone.

The prompt files are **generated** from `config/rubric_v5.json`
(`npm run gen:prompts`) and `tests/contract/prompts.test.mjs` fails if a level
definition in a prompt differs from config by a single byte. When the rubric
changes, regenerate and re-paste all seven.

### 8 — `score_json`  ·  formula

`engine/clay_formula.txt` over the seven `cls_` columns. That file is generated
from `config/rubric_v5.json` and `tests/contract/clay_parity.test.mjs` asserts
it returns deep-equal output to `engine/scoring.mjs` on 500+ generated inputs.

Follow the three pasteable steps in `clay_formula.txt`. Only the seven column
bindings in STEP 1 and the three `facts_summary` bindings in STEP 2 are
hand-edited; STEP 3 is pasted unchanged.

### 9 — `post_to_n8n`  ·  HTTP API

POST the `icp.scored` event to the n8n Path B webhook.

| Setting | Value |
|---|---|
| Method | `POST` |
| URL | the `callback_url` sent with the webhook body (never hardcoded) |
| Body | `engine/schemas/icp_scored_event.schema.json` |
| Header | `X-Clay-Secret: <from Clay's secret store>` |
| Retry | **3× on 5xx** |
| Retry | **never on 4xx** |

Why no retry on 4xx: a 4xx is n8n rejecting the event as malformed or
unauthorized. Retrying cannot fix either, and each retry burns a Clay credit and
delays the row. A 4xx must surface in Clay as a failed row so it gets looked at.

Why 3× on 5xx: n8n restarting or a transient DEV outage. n8n Path B dedupes on
`event_id`, so a retry that actually did land the first time writes nothing the
second time — the retry is safe precisely because of that dedupe.

**The secret lives in Clay's secret store.** Not in the column config, not in
this file, not in any workflow JSON. `tests/static/workflow_review.test.mjs`
greps the exported workflow for secret-shaped strings.

---

## Column-count summary

| Group | Columns |
|---|---|
| Webhook passthrough (1–4) | 10 |
| Enrichment (5) | 16 |
| `facts_json` (6) | 1 |
| Classifiers (7) | 7 |
| `score_json` (8) | 1 |
| `post_to_n8n` (9) | 1 |
| **Total** | **36** |

---

## What this table does NOT do

- **It does not create or dedupe organizations.** The trigger fires on an org
  that already exists in Pipedrive. Out of Phase 1.
- **It does not write to Pipedrive.** Clay produces numbers; n8n owns every
  write, so there is exactly one writer and idempotency is enforceable in one
  place.
- **It does not read or write `ICP Final`.** That field is the human's.
- **It does not score campaigns.** Melisa's campaign path is a separate table,
  out of Phase 1.
- **It does not compose the note.** The note template (§8.3) is built in n8n, so
  user-visible copy lives in one place.
