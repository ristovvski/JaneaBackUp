# Clay `ICP_Engine` — build order

Companion to `clay_table_spec.md`. That file is the **contract** (what each column
must hold). This one is the **order to click**, written against the table as it
actually exists, and arranged so the cheapest, highest-signal work comes first.

**State as of 2026-09-15 11:41 UTC**, read via `clay tables columns get`:

| | |
|---|---|
| Table | `ICP_Engine` · `t_0tlelmmWmfDwaQypyXG` · workbook *Chrissy's ICP* · workspace 332169 |
| Created | 2026-09-15T11:37:34Z |
| Columns | **3 of 36** — `Webhook` (source), `Created At`, `Updated At` (both system) |
| Rows | 1 — the connectivity test |
| Credits | 99,210 — not a constraint |

**Nothing downstream of the webhook exists yet.** No enrichment, no `facts_json`,
no `cls_*`, no `score_json`, no `post_to_n8n`.

---

## What is already proven

The webhook source works and parses our payload into addressable subfields. All
twelve keys `BuildClayRequest` sends arrived and are visible in Cell details:

```
Domain            akuvo.com                Request Id       CONNECTIVITY-TEST-…
Org Id            0                        Callback Url     https://…/webhook/icp-b-…
Deal Id           null   ← null preserved  Company Name     CONNECTIVITY TEST — delete this row
Hq State          Colorado                 Linkedin Url     https://www.linkedin.com/company/akuvo
Hq Country        United States            Model Version    v5
Identifier Kind   domain                   Identifier Value akuvo.com
```

`Deal Id` arriving as `null` rather than absent is the thing to notice: the
classifiers are instructed to read null as "enrichment did not find it", and that
distinction only survives because the request sends nulls explicitly.

Reference these as `Webhook.<Name>` (or whatever token Clay's editor inserts when
you click the field — that token is UI syntax and is deliberately not guessed at
here; see NEEDS_DOC_EVIDENCE #1 in REPORT.md).

---

## Phase 1 — the loop, with zero enrichment credits

**Build this first.** It closes Pipedrive → n8n → Clay → n8n → Pipedrive without
spending a single enrichment or AI credit, because every column is a formula or
an HTTP call over data the webhook already delivered.

| # | Column | Type | Notes |
|---|---|---|---|
| 1 | `facts_json` | formula | Build the `enrichment_facts.schema.json` object from `Webhook.*`. Every enrichment key present and **`null`** — that is a valid fact set, and the schema allows all-nulls. |
| 2 | `cls_*` ×7 | **skip for now** | Phase 3. |
| 3 | `score_json` | formula | Paste `engine/clay_formula.txt` STEP 3 unchanged. With all classifier values null it returns `status: "insufficient_data"`, `grade: null` — which is **correct**, not a failure. |
| 4 | `post_to_n8n` | HTTP API | POST the `icp.scored` event to `Callback Url`. Header `X-Clay-Secret`. Retry 3× on 5xx, never on 4xx. |

Run one row through and Pipedrive gets `ICP Calculated = Insufficient data`, a
note whose Missing line lists every absent fact, and an audit row. **That is the
whole pipeline working end to end** — it just has nothing to score on yet.

> **Demo shortcut.** Hand-type plausible values into a few `facts_json` inputs for
> one row (revenue, funding stage, headcount) and Phase 1 alone produces a real
> **ICP A** with a full note. It exercises the identical formula and the identical
> n8n path; only the enrichment is manual. Cheapest possible proof the rubric
> works on live infrastructure.

## Phase 2 — enrichment (credits)

The 16 columns in `clay_table_spec.md` §5, waterfall **LinkedIn → website →
Apollo → fallback → PredictLeads/LinkedIn Jobs → news**. Then rewire `facts_json`
to read them instead of nulls.

Two that carry more weight than their size suggests:

- **`eng_roles_open_60d_plus`** — the strongest available proxy for a documented
  capacity gap, and `stage_maturity` leans on it.
- **`news_last_12mo`** — every item needs a **date**, because `activation_state`
  cannot return `Contracting` without one, and `Contracting` zeroes the score.

## Phase 3 — the seven classifiers (credits)

One AI column per component, **never one column returning all seven** — a single
bad component should fail and retry alone.

Each: **`_preamble.md` + the component prompt + `facts_json`**, temperature **0**,
structured output against `classifier_output.schema.json`, **no web access** (the
preamble forbids browsing; removing the capability makes it true rather than
requested).

| Column | Prompt |
|---|---|
| `cls_industry` | `industry_vertical.md` |
| `cls_stage` | `stage_maturity.md` |
| `cls_type` | `company_type.md` |
| `cls_geo` | `geography.md` |
| `cls_revenue` | `revenue_range.md` |
| `cls_activation` | `activation_state.md` |
| `cls_buying` | `buying_signal.md` |

Then rewire `score_json`'s STEP 1 bindings to the seven columns and STEP 2's three
`facts_summary` bindings to `facts_json`.

---

## After each phase

```bash
clay tables columns list t_0tlelmmWmfDwaQypyXG      # what exists now
clay tables rows list   t_0tlelmmWmfDwaQypyXG --limit 1
clay credits balance
```

The n8n side needs no change between phases: `ParseScored` validates whatever
arrives and recomputes the score independently, so a half-built table produces
`Insufficient data` rather than a wrong grade.

## Housekeeping

Delete row 1, `CONNECTIVITY TEST — delete this row`, once Phase 1 is verified.
