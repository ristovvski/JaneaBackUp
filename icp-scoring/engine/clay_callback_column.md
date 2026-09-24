# Clay → n8n Path B: the callback HTTP column

The last column in the ICP table. It POSTs one scored event per row to n8n
Path B, which validates it and writes it to Pipedrive. **The table scores; n8n
does no arithmetic** (since `a5ac404`, 17 Sep).

`engine/validate_event.mjs` is the contract as code, and it is spliced verbatim
into the `ParseScored` node — so what rejects a row here is the same source its
unit tests exercise. `engine/schemas/icp_scored_event.schema.json` is the same
contract as JSON Schema.

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

That is the whole body: a formula column returning the object below. A text
template interpolating `{{column}}` references produces **strings**, and Path B
rejects strings where it expects types — `"org_id": "22586"` is a rejected
row, and a blank column interpolated into `"deal_id": ` is not JSON at all.
A formula column controls the types; a text template cannot.

---

## What `icp_event_json` must return

The live Intellistack row (org 22586, 17 Sep), verbatim except the note, which
is cut short here — its format is [`clay_note_format.md`](clay_note_format.md):

```json
{
  "request_id":   "req-7be8d908-0355-4573-8d3b-9ed3bc85a090",
  "org_id":       22586,
  "deal_id":      2277,
  "requested_at": "2026-09-17T14:21:29.036+00:00",
  "final":        62,
  "grade":        "B",
  "status":       "scored",
  "note":         "<b>ICP B (62/100) · confidence medium</b><br><br>…",

  "composite":                78,
  "multiplier":               0.8,
  "final_without_activation": 78,
  "industry_level":  7,
  "stage_level":     3,
  "type_level":      10,
  "geo_level":       10,
  "revenue_level":   10,
  "activation_used":    "Stable",
  "confidence_overall": "medium",
  "tier2_candidate":    false,
  "flags":              []
}
```

**The first eight keys are required. The rest are the working** — optional,
typed when present, carried into the run summary and never into a decision.
**Any other key rejects the row**: a column the table starts sending that n8n
does not know about is a contract change, and it should be loud.

The four identity keys — `request_id`, `org_id`, `deal_id`, `requested_at` —
are the values **Path A sent on this row**, echoed back unchanged. Dropping them
is the one failure the table can cause on its own (22 Sep: a note edit took all
four with it, and every row was rejected until they were restored).

---

## Types, exactly

| key | type | rule |
|---|---|---|
| `request_id` | string | non-empty; the dedupe key |
| `org_id` | integer | ≥ 1 — it becomes the PATCH's URL segment, so `"22586"` is refused |
| `deal_id` | integer or `null` | present always; `null` is legal for a re-score outside a deal |
| `requested_at` | string | the ISO timestamp Path A sent |
| `final` | integer 0–100, or `null` | |
| `grade` | `"A"` · `"B"` · `"C"`, or `null` | |
| `status` | `"scored"` · `"insufficient_data"` | `"scored"` with a null `final` or `grade` is refused — it would write a grade-shaped blank |
| `note` | string | non-empty; written to the activity **verbatim**, HTML |
| `composite`, `multiplier`, `final_without_activation` | number or `null` | optional |
| `industry_level` … `revenue_level` | `0` · `3` · `7` · `10`, or `null` | optional |
| `activation_used` | `Accelerating` · `Transitioning` · `Stable` · `Contracting`, or `null` | optional |
| `confidence_overall` | `high` · `medium` · `low`, or `null` | optional |
| `tier2_candidate` | boolean or `null` | optional |
| `flags` | array of strings, or `null` | optional |

---

## What Path B does with it

1. **`Dedupe B`** — keys on `request_id` (sharpened by `event_id` when there is
   one). A row with no `request_id` is not deduped — it passes through unkeyed,
   and validation refuses it with the reason, rather than dying unexplained.
2. **`ParseScored`** — validates the whole payload and lists **every** problem
   at once, so a table wrong in four places is fixed in one pass.
3. **Pipedrive** — `Auto-ICP Score` (`"62 - B"`, or `"n/a - insufficient data"`)
   and `Auto-ICP Scored At`, written together in one PATCH or not at all; then
   one activity carrying `note` verbatim. An unchanged value writes no PATCH but
   still posts the activity.

A rejected row touches no field: one Slack alert naming every problem, one
"ICP scoring failed" activity when the org id is recoverable, and a red
execution so WF-ERR reports it too.

---

## Proof this doc is right

`tests/static/callback_column.test.mjs` pulls the JSON example out of this file
and runs it through `validateEvent()` — clean — and checks the required and
optional lists above against `REQUIRED_TOP` and `OPTIONAL_TOP` in the
validator. If the contract moves and this file does not, the suite goes red.
