# Clay → n8n Path B: the callback HTTP column

The last column in the `ICP_Engine` table. It POSTs one `icp.scored` event per
row to n8n Path B, which validates it, scores it, and writes the grade to
Pipedrive.

`engine/schemas/icp_scored_event.schema.json` is the contract; this file is how
to express it in Clay. `engine/validate_event.mjs` is the same constraints as
code, and it is spliced verbatim into the `ParseScored` node — so what rejects a
row here is the same source its unit tests exercise.

---

## Authentication: there is none, and that is the design

**Path B validates no secret and reads no header.** The n8n webhook node is
`authentication: "none"`. Clay must send **no** `X-Clay-Secret`, no bearer
token, no signature — there is nothing on the other end that would look at one.

The control is the **URL**: an unguessable n8n webhook path, delivered to the
table as `callback_url` on every request rather than typed into a Clay column.
That was the owner's ruling, and the reasoning holds: a shared secret would
have had to live as a literal in a Clay column's config, which is a worse place
for one than nowhere. `Content-Type: application/json` is the only header that
matters.

If that ever changes, it changes in both places at once — the n8n webhook node
gets a credential AND Clay gets the header. n8n treats `authentication` set
with no credential attached as a hard 500 on every delivery, so half the change
is worse than none of it.

---

## Column config

| | |
|---|---|
| **Type** | HTTP API |
| **Method** | `POST` |
| **URL** | `{{callback_url}}` — the value n8n sent on this row, never a literal |
| **Headers** | `Content-Type: application/json` — and nothing else |
| **Body** | JSON, below |
| **Run when** | every classifier column on the row has resolved |

The URL comes from the row because DEV and production are different n8n
instances with different paths. A literal here means every DEV row calls
production the day someone copies the table.

---

## The body: send ONE formula column

```
{{icp_event_json}}
```

That is the whole body. Build `icp_event_json` as a formula column that returns
the object below, exactly the way `facts_json` is built
(`engine/clay_facts_formula.txt`).

**This is not a style preference.** Interpolating sixty `{{column}}` references
into a JSON text body produces **strings**, and Path B rejects strings where it
expects types — every one of these is a rejected row:

| what arrives | what Path B says |
|---|---|
| `"org_id": "22586"` | `org_id must be a positive integer` |
| `"level": "7"` | `level must be null or one of [0,3,7,10]` |
| `"evidence": "hiring 11 eng roles"` | `evidence must be an array` |
| `"employees": ""` | `employees has the wrong type` |
| `"deal_id": ` (blank column) | not JSON at all — the POST fails before n8n sees it |

A formula column controls the types. A text template cannot.

---

## What `icp_event_json` must return

Every key below is **required** unless marked optional. `additionalProperties`
is false at the top level, inside `cls_all`, inside each component, inside
`engineering_hiring` and inside `apollo_summary` — **an extra key rejects the
whole row**, by design: a column the table starts sending that n8n does not know
about is a contract change, and it should be loud.

```json
{
  "request_id":    "req-icp-0001",
  "org_id":        22586,
  "deal_id":       2273,
  "requested_at":  "2026-09-17T13:07:02.750+00:00",
  "domain":        "intellistack.com",
  "model_version": "v6",

  "resolved": {
    "domain":       "intellistack.com",
    "linkedin_url": "https://www.linkedin.com/company/intellistack",
    "website":      "https://www.intellistack.com/"
  },

  "cls_all": {
    "engineering_hiring": {
      "total_open":           18,
      "eng_open":             11,
      "eng_open_60d_plus":    4,
      "dates_available":      true,
      "leader_titles":        ["VP Engineering"],
      "eng_titles_with_days": ["Senior Backend Engineer (74d)"],
      "eng_open_ratio":       0.61,
      "eng_headcount":        50
    },

    "industry_vertical": {
      "value":          "FinTech",
      "evidence":       ["website_summary: lending decisioning for credit unions"],
      "confidence":     "high",
      "missing_inputs": []
    },

    "company_type": {
      "level":          10,
      "evidence":       ["li_description: software platform"],
      "confidence":     "high",
      "missing_inputs": []
    },

    "stage_maturity": {
      "level":          7,
      "evidence":       ["eng_roles_open_60d_plus: 4"],
      "confidence":     "medium",
      "missing_inputs": []
    },

    "activation_state": {
      "value":                     "Accelerating",
      "activation_evidence_dated": "apollo.headcount_6mo_growth: 0.22",
      "evidence":                  ["apollo headcount up 22% over six months"],
      "confidence":                "medium",
      "missing_inputs":            []
    },

    "geography": {
      "level":    10,
      "evidence": ["apollo.country: United States"]
    },

    "revenue_range": {
      "level":             7,
      "revenue_band_used": "$10M-$25M",
      "revenue_source":    "apollo_revenue",
      "evidence":          ["apollo.annual_revenue: 18000000"],
      "confidence":        "medium",
      "missing_inputs":    []
    },

    "buying_signal": {
      "level":    7,
      "evidence": ["11 engineering roles open, 4 over 60 days"]
    },

    "conflict_note": null
  },

  "apollo_summary": {
    "employees":                 260,
    "eng_headcount":             50,
    "country":                   "United States",
    "state":                     "Indiana",
    "founded_year":              2006,
    "last_round_date":           "2025-09-01",
    "headcount_6mo_growth":      0.22,
    "headcount_12mo_growth":     0.35,
    "publicly_traded_symbol":    null,
    "owned_by_organization_id":  null
  }
}
```

### Where each value comes from

| key | source |
|---|---|
| `request_id`, `org_id`, `deal_id`, `requested_at`, `domain` | echoed from the **webhook input columns** — the same four keys Path A sent, plus `requested_at`. Not re-derived. |
| `model_version` | the literal string `"v6"`. Anything else is rejected. |
| `resolved.*` | enrichment. All three may be null; the object and its three keys may not be missing. |
| `cls_all.engineering_hiring` | the jobs columns. |
| the six classifiers | one AI column each, each returning its object. |
| `apollo_summary` | the Apollo columns. |

`deal_id` is the one optional top-level key. Omit it or send `null`; do not send
`""`.

---

## Types, exactly

- **`org_id`** — integer, `>= 1`. Never quoted.
- **`deal_id`** — integer or `null`.
- **`level`** — one of `0`, `3`, `7`, `10`, or `null`. Numbers, not strings.
  There is no `5`.
- **`confidence`** — `"high"`, `"medium"` or `"low"`. Required on
  `industry_vertical`, `company_type`, `stage_maturity`, `activation_state`,
  `revenue_range`. Optional on `geography` and `buying_signal`; if present it
  must still be one of the three.
- **`missing_inputs`** — array of strings. Required on the same five as
  `confidence`, optional on `geography` and `buying_signal`. Empty array when
  nothing is missing — **not** `null`.
- **`evidence`** — array of strings on **every** component, max 20 items. `[]`
  when there is none. A bare string is rejected.
- **`activation_state.value`** — `"Accelerating"`, `"Transitioning"`,
  `"Stable"`, `"Contracting"` or `null`. Exact spelling and capitalisation.
- **`activation_evidence_dated`** — a **citation string**, not a boolean:
  the evidence item the state rests on, e.g.
  `"apollo.funding_events[0].date: 2025-09-01"`. n8n reads a date out of it and
  asks whether it names a layoff or a hiring freeze.
- **counts** (`total_open`, `eng_open`, `eng_open_60d_plus`, `eng_headcount`,
  `employees`) — integer or `null`. **`null` and `0` are opposite facts**: null
  means the provider returned nothing, `0` means it returned nothing open.
  Sending `0` for both is how `stage_maturity` went wrong on Akuvo.
- **`dates_available`** — boolean or null. `false` is how the table says it
  could not tell how long a role had been open.
- **`eng_open_ratio`** — number or null, `>= 0`.
- **`headcount_6mo_growth`** — number or null, and **load-bearing**: it is the
  first test the Contracting guard applies. A decimal fraction, so a 15% fall is
  `-0.15`.
- **`owned_by_organization_id`** — string, integer or null.
- **nulls** — literal `null`. Never `""`, never `"null"`, never `"unknown"`.

---

## `industry_vertical.value`: the 17 strings, verbatim

n8n maps the name to a level through the rubric. A name that is not on this
list scores **0** for the industry component and raises an `unknown_vertical`
flag — it is not an error, but it is a 15-weight component reading zero, so the
spelling matters.

| vertical | level |
|---|---|
| `FinTech` | 10 |
| `HealthTech / MedTech` | 10 |
| `Enterprise Tech / Hyperscalers` | 10 |
| `SportsTech` | 7 |
| `Analytics / ML` | 7 |
| `Data Platform SaaS` | 7 |
| `SaaS — Other` | 7 |
| `Pharma / Life Sciences` | 7 |
| `Manufacturing tech / Industrial IoT` | 3 |
| `ClimaTech` | 3 |
| `EdTech` | 0 |
| `LegalTech` | 0 |
| `Government / Public Sector` | 0 |
| `Pure Hardware / Consumer Electronics` | 0 |
| `Telecom / 5G Infrastructure` | 0 |
| `E-commerce / Retail Tech` | 0 |
| `Pre-product Startups` | 0 |

`SaaS — Other` uses an **em dash** (—), not a hyphen. `"Horizontal B2B
Software"` is **not** a vertical on this list; a classifier that emits it scores
the industry component at zero.

---

## There is no `what_they_sell`

It is not in the event contract, and the top level is `additionalProperties:
false` — so sending it **rejects the whole row** with
`unknown top-level key "what_they_sell"`.

If the table has such a column, it belongs on the **input** side of the
`industry_vertical` classifier, as part of the evidence that produces
`value: "FinTech"`. Its content can also ride along inside
`industry_vertical.evidence[]`, which is an array of free-text strings and is
the right home for "what this company actually sells" as a human-readable
justification.

The same goes for any other column the table grows: the ONLY keys that may
appear beyond those listed above are five ignored provenance keys —
`event`, `event_id`, `emitted_at`, `clay_table`, `clay_row_url`. `event_id`
is worth sending: it sharpens Path B's dedupe key.

---

## What Path B does with it

1. **`Dedupe B`** — drops a redelivery on `request_id` + `event_id`.
2. **`ParseScored`** — validates the whole payload and lists **every** problem
   at once, so a table that is wrong in four places is fixed in one pass rather
   than four. On any problem the row does not reach Pipedrive: a wrong grade in
   the CRM is worse than a loud failure.
3. **`Score`** — applies the rubric. The table sends **no score**; there is one
   implementation of the rubric in the delivery path and it is this node.
4. **Pipedrive** — two organization fields, written together
   (`Auto-ICP Score` = `"56 - B"`, `Auto-ICP Scored At`), and one activity.
   Nothing else on the record is touched.

A rejected row lands on the error branch: one Slack alert and one activity
saying the run failed, and the organization is left untouched.

---

## Proof this body is right

The example above is not illustrative. Run through the real thing:

```
validateEvent()                     CLEAN
icp_scored_event.schema.json        CLEAN
Dedupe B -> ParseScored -> Score     composite 85 x 1.00 -> 85  A  scored
                                     activation Accelerating -> Accelerating, guard not applied
                                     levels {industries 10, stage 7, type 10, geo 10, revenue 7, buying 7}
```

Paste it into a test row's formula column and Pipedrive should read
`Auto-ICP Score = "85 - A"`.
