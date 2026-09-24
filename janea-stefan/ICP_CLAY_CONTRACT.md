# ICP scoring: the contract between n8n and Clay

What `WF-ICP-Score` sends to Clay, what it accepts back, and which Clay columns it depends on.
Everything below was read from the **live** workflow on 2026-09-24. Its nodes are byte-identical to
`icp-scoring/n8n/nodes/*.js` on `main`, so those files are the source of truth for the n8n side.

```
Pipedrive deal created ─> n8n Path A ──7 keys──> Clay table ICP_Engine
                                                    │ enrichment → classifiers → the score → the note
                                                    ▼
Pipedrive org + activity <── n8n Path B <──20 keys── Clay HTTP API column (the callback)
```

**Read this before the older ICP docs.** `icp-scoring/engine/clay_callback_column.md` still
describes the v6.0 callback, in which Clay sent classifier output and n8n computed the grade. Since
commit `a5ac404` (2026-09-17, "The table scores, n8n writes") **the table computes the grade** and n8n
only validates and writes it. Likewise `icp-scoring/engine/clay_formula.txt` is an ancestor of the
live score column, not a copy of it: it returns `final_score` and builds no note, while the live table
sends `final` and a finished `note`.

Which Clay primitive is live: the **table** `ICP_Engine`, fed by a Clay *table webhook source*. The
n8n CONFIG's Clay URL has that shape (`api.clay.com/v3/sources/webhook/…`). The Clay *Workflow* variant
in `icp-scoring/clay/` is not what n8n calls.

---

## Path A: n8n → Clay, exactly seven keys

`BuildClayRequest` POSTs this body to the table's webhook source. The URL is `clay_engine_url` in the
workflow's CONFIG. It is a credential (anyone holding it can inject rows), so it never appears in a
document or a Clay column.

| key | type | where n8n takes it from |
|---|---|---|
| `org_id` | integer | the deal's organization (a number on the wire, a string inside n8n) |
| `deal_id` | integer or `null` | the deal that triggered the run; `null` for a re-score outside a deal |
| `domain` | string, never null | the org's **Website URL** field reduced to its registrable domain: lowercase, no scheme, no `www.`, no path |
| `request_id` | string | n8n's correlation id for this run; it follows the row everywhere |
| `callback_url` | string | where the table must POST the result (Path B). It differs per n8n instance |
| `requested_at` | ISO timestamp | the table's "today" for days-open arithmetic on job postings |
| `model_version` | string | currently `"v6"` |

- **The table needs one input column per key, named exactly as above.** A key without a column is
  dropped by Clay silently.
- **No website, no Clay call.** If the Website URL is empty, is not a usable domain, or points at a
  directory such as linkedin.com, crunchbase.com or a Wix subdomain, nothing is sent. n8n writes
  `n/a - no website` on the organization and posts one activity asking for the field. No Clay credit
  is spent.
- There is no name lookup and no LinkedIn fallback. The domain is the only identifier.

## What the table must do with it

Enrich from `domain`, run the classifiers, compute the score, build the note, then POST the result to
`callback_url` in the row. n8n depends on **none** of the enrichment or classifier column names; it
reads only what the callback delivers. The table's internals can change freely as long as the
callback below stays exact.

## Path B: the callback column (Clay → n8n)

| setting | value |
|---|---|
| Type | HTTP API |
| Method | `POST` |
| URL | `{{callback_url}}`, the value Path A sent on this row, **never a literal** (DEV and production are different instances) |
| Headers | `Content-Type: application/json` and nothing else. There is no secret header: the n8n webhook has `authentication: none` and the URL is the control |
| Body | one formula column that returns the JSON object below (a text template turns numbers into strings, and Path B rejects strings where it expects types) |
| Run when | the score and the note have resolved on the row |

### The body: 20 keys, and nothing else

**Required (8).** The organization is not written without them.

| key | type and rule |
|---|---|
| `request_id` | non-empty string, echoed from the row's `request_id` column |
| `org_id` | integer ≥ 1, echoed, never quoted |
| `deal_id` | integer or `null`, echoed. It must be **present** even when null |
| `requested_at` | ISO timestamp, echoed |
| `final` | integer 0–100, or `null` |
| `grade` | `"A"`, `"B"`, `"C"` or `null` |
| `status` | `"scored"` or `"insufficient_data"` |
| `note` | non-empty string. Written to the Pipedrive activity **verbatim**. The field renders HTML: format with `<b>`, `<br>`, `<ul><li>`, never with `\n`, and never escape by hand (see `icp-scoring/engine/clay_note_format.md`) |

**Optional (12): the working.** They are recorded in the run summary but never used for a decision,
and each must be typed if present.

| key | type |
|---|---|
| `composite`, `multiplier`, `final_without_activation` | number or `null` |
| `industry_level`, `stage_level`, `type_level`, `geo_level`, `revenue_level` | one of `0, 3, 7, 10`, or `null` |
| `activation_used` | `"Accelerating"`, `"Transitioning"`, `"Stable"` or `"Contracting"` |
| `confidence_overall` | `"high"`, `"medium"` or `"low"` |
| `tier2_candidate` | boolean |
| `flags` | array of strings |

**Any other key rejects the whole callback.** One cross-field rule applies: `status: "scored"` with a
`null` `final` or `grade` is refused, because a grade-shaped blank on a rep's record is the worst
thing this workflow could write.

### What went wrong live, and what each failure looked like

| callbacks | what the table sent | what n8n said |
|---|---|---|
| 17 Sep; 22 Sep 11:37–12:06 (executions 65816–65859) | 16 keys: the score, but none of the four echoed ids | `missing "request_id"; missing "org_id"; missing "deal_id"; missing "requested_at"` |
| 22 Sep 12:14 (65862, 65863) | 23 keys: all seven Path A keys echoed back | `unknown top-level key "callback_url"; unknown top-level key "domain"; unknown top-level key "model_version"` |
| since 22 Sep 12:14 (65866 onwards) | the 20 keys above | accepted and written |

Echo exactly **four** Path A keys (`request_id`, `org_id`, `deal_id`, `requested_at`), not all seven.
A rejected callback ends the execution red, posts one Slack alert listing every problem, posts one
failure activity, leaves the organization untouched, and releases the dedupe key so a corrected
redelivery is not dropped as a duplicate.

### What Path B writes

- Organization, two fields together: `Auto-ICP Score` = `"<final> - <grade>"` (e.g. `"62 - B"`) and
  `Auto-ICP Scored At`. `Sales Rep ICP Score` is never touched. The PATCH is skipped when nothing
  changed.
- One activity per run, with the note verbatim, linked to both the organization and the deal.

---

## The score ("ICP Calculations")

The only implementation of the rubric in the delivery path is the table's score column. n8n checks
none of the arithmetic.

**The formula text in Clay has not been read.** From this machine, the Clay CLI is rejected by Clay
(version 0.8.1; Clay now requires ≥ 1.3.0), and both the CLI session and the API key belong to a
different Clay workspace than the Janea one that holds `ICP_Engine`. The text lives only in Clay;
exporting it into `icp-scoring/engine/` is an owner action.

**What the live formula provably computes.** Every accepted callback from 17 to 22 September (15
callbacks, 3 organizations) was recomputed from its own levels, and `composite`, `multiplier`,
`final`, `final_without_activation` and `grade` all match the v6 rubric exactly:

```
composite = ( 15·industry + 25·stage + 25·revenue + 25·company_type + 10·geography + 0·buying_signal ) / 10
multiplier: Accelerating 1 · Transitioning 0.95 · Stable 0.8 · Contracting 0
final     = round-half-up( composite × multiplier )        e.g. 92.5 × 1 → 93
grade     = A if final ≥ 75, B if final ≥ 55, else C       null when status = insufficient_data
```

Coverage is stated, not assumed. The live sample contains grades A and B, and activation states
Stable and Accelerating. Grade C, `insufficient_data`, Transitioning and Contracting have not occurred
live, so for those cases the formula is untested in production.

**The v6 rubric's source file is not in git.** `icp-scoring/config/rubric_v6.json` is the declared
source of the generators and of the live CONFIG (`_sources` says so), and twenty files on `main`
reference it, but it has never been committed on any branch; only `rubric_v5.json` is tracked. The v6
values survive embedded in the generated `icp-scoring/n8n/nodes/CONFIG.json` and
`icp-scoring/engine/clay_score.py`, and those are what the numbers above were checked against. Until
the file is committed, the generators cannot be re-run from a clean clone.

The industry map is spelling-sensitive: `SaaS — Other` takes an **em dash**, and a vertical spelled
differently scores 0.

---

## Clay columns n8n depends on

| column | direction | why |
|---|---|---|
| `org_id`, `deal_id`, `domain`, `request_id`, `callback_url`, `requested_at`, `model_version` | in (webhook) | Path A lands here; a missing column drops the key silently |
| the score column ("ICP Calculations") | internal | produces `final`, `grade`, `status` and the working |
| the note column | internal | produces `note`; format per `icp-scoring/engine/clay_note_format.md` |
| the callback body formula column | out | assembles the 20 keys: the four echoed ids, the score's outputs, the note |
| the callback HTTP API column | out | POSTs that body to `{{callback_url}}` |

Everything else in the table (enrichment, classifiers, facts) is internal to Clay: n8n neither reads
nor names it.
