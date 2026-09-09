# Clay table `ICP_Engine` — build spec

Clay is built by hand in the UI. This is the exact column list, in order, with
types, sources and the contract each column has to satisfy. Everything that can
be tested offline lives elsewhere in this repo and is referenced below.

**Model version:** v5 · **Rows:** one per scoring request (not one per company —
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
  "request_id":       "req-icp-0001",
  "org_id":           "10001",
  "deal_id":          "55001",
  "identifier_kind":  "domain",
  "identifier_value": "akuvo.com",
  "domain":           "akuvo.com",
  "linkedin_url":     "https://www.linkedin.com/company/akuvo",
  "company_name":     "Akuvo",
  "hq_country":       "United States",
  "hq_state":         "Colorado",
  "model_version":    "v5",
  "callback_url":     "<n8n Path B webhook URL, from CONFIG>"
}
```

`identifier_value` is already normalized by `engine/normalize.mjs` in n8n, so
Clay never has to agree with n8n about what a domain is. A null field is sent as
`null`, never omitted and never `""`.

---

## Columns, in order

### 1 — `request_id`  ·  text  ·  from webhook

The n8n correlation id. Carried through every artefact: the Clay row, the
`icp.scored` event, the Pipedrive note, the audit row and every Slack alert.
This is the one value that lets you follow a single scoring decision end to end.

### 2 — `org_id`, `deal_id`  ·  text  ·  from webhook

Pipedrive ids as **strings**. `deal_id` may be null (a re-score triggered
outside a deal). `org_id` is never null.

### 3 — `identifier_kind`, `identifier_value`  ·  text  ·  from webhook

`identifier_kind` ∈ `domain` | `linkedin` | `name`, in that priority order.
`name` means the org had neither a website nor a LinkedIn company URL:
NEEDS_DECISION #5 default is to score it anyway, from name + HQ, at low
confidence — never `Insufficient data` on a missing identifier alone.

### 4 — `domain`, `linkedin_url`, `company_name`, `hq_country`, `hq_state`  ·  text  ·  webhook + enrichment fallback

Seeded from the webhook. Where the webhook value is null, an enrichment column
may fill it (LinkedIn company lookup by domain, or a domain lookup by company
name). **Fill-if-empty only** — never overwrite a value n8n sent, because n8n's
value came from Pipedrive and Pipedrive is where a human typed it.

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
