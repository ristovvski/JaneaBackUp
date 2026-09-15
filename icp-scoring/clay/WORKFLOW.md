# `ICP_Engine` as a Clay **Workflow**

`engine/clay_table_spec.md` is the contract: what goes in, what comes out, what
each step has to satisfy. This file is how that contract is realized with the
Workflow primitive instead of a table — the node map, the model policy, and
every place the primitive could not express the spec the way it is written.

Everything here is built by `clay/build_workflow.mjs` from tracked sources: the
seven prompt files, the four schemas, `config/rubric_v5.json` and the
parity-tested Python scorer. The builder is idempotent (it matches nodes by
name), it sweeps away steps it used to create and no longer does, it verifies on
every run that the Python and prompts on the canvas are byte-identical to this
repository, and it **never publishes** — publishing is what takes the Path A
trigger live, and that is a human decision.

```
npm run clay:build -- --workflow wf_xxx
```

---

## Model policy

**OpenAI only, on the workspace's own key. No Clay-native models anywhere.**

| Role | Model |
|---|---|
| The seven classifiers, including activation state | `gpt-5.6-sol` |
| Website summarization | `gpt-5.6-terra` |

`gpt-5.6-luna`, every `claude-*` Claygent model and `gpt-5.4-nano` are excluded
by policy, and `clay/build_workflow.mjs` throws on any of them rather than
trusting the constant to stay right. **No node in this graph is
`nodeType: "agent"`** — see gap 1 for why that is forced rather than chosen.

### Temperature 0 is not available, and nothing here pretends otherwise

`clay_table_spec.md` §7 calls temperature 0 "non-negotiable: a score that changes
between runs cannot be audited or re-derived". The GPT-5.6 family refuses it:

```
HTTP 400 — Unsupported value: 'temperature' does not support 0 with this model.
           Only the default (1) value is supported.
```

Confirmed on Sol and Terra both. Sending the parameter fails the call outright,
so every request here omits it and pins `seed: 0` instead, and the output space
is closed by a strict JSON schema. `tests/static/clay_nodes.test.mjs` fails the
build if `"temperature"` reappears in a request body.

**This is weaker than temperature 0.** A seed is a best-effort determinism hint,
not a guarantee, and the o-series reasoning models on the same key do not accept
temperature either — so there is no OpenAI model available here that satisfies
the spec as written. Two runs of the same facts can differ. The mitigations that
remain are real but partial: a closed `select` domain for every categorical
value, `additionalProperties: false`, and a scorer that is pure and
parity-tested. The gap is open.

---

## The graph

| # | Node | Type | Concern |
|---|---|---|---|
| — | `Webhook` | trigger | Path A. Created inert; **not published**. |
| 01 | Prepare enrichment inputs | code | Read the webhook body; decide whether anything is worth enriching. |
| 02 | Gate — any identifier to enrich? | conditional | No domain and no LinkedIn ⇒ skip straight to 15, spending nothing. |
| 03 | Enrich company profile | tool | Firmographics from the LinkedIn company profile or the domain. |
| 04 | Resolve domain for enrichment | code | Everything downstream is keyed on a domain. Fill-if-empty only. |
| 05 | Gate — domain resolved? | conditional | LinkedIn-only and no website found ⇒ skip to 15. |
| 06 | Scrape site pages | tool | Runs once per URL over homepage, `/about`, `/product`, `/careers`. |
| 07 | Collect page text | code | Flatten four results into one labelled, capped block; detect soft 404s. |
| 08 | Build website summary request | code | The Terra request body. |
| 09 | Summarize website | tool · HTTP | One OpenAI call. |
| 10 | Read website summary | code | Unwrap the reply, or report honestly that there is none. |
| 11 | Enrich revenue and headcount | tool | Inferred revenue, total headcount, **engineering** headcount, funding stage. |
| 12 | Find financing events | tool | `last_round_date`, `last_round_usd`. |
| 13 | Find open engineering roles | tool | The three jobs facts, including open > 60 days. |
| 14 | Find recent news | tool | `news_last_12mo`, every item dated. |
| 15 | Build facts_json | code | The 26-key fact set. Nulls stay null. |
| 16 | Build classifier requests | code | Seven Sol request bodies, each with its own prompt and strict schema. |
| 17–23 | Classify … (7 nodes) | tool · HTTP | One component each, one call each. |
| 24 | Collect classifier outputs | code | Seven replies → the `components` object. |
| 25 | Score (ICP v5) | code | `engine/clay_score.py`, embedded verbatim. |
| 26 | Build icp.scored event | code | The exact body `icp_scored_event.schema.json` describes. |
| 27 | POST icp.scored to n8n Path B | tool | 3× on 5xx, never on 4xx. URL from the payload, never hardcoded. |

Three design choices worth stating, because none is forced:

**The two gates are what make the name-only case free.** A request with no domain
and no LinkedIn URL reaches node 15 with every enrichment input unset and still
scores — at low confidence, from name and HQ, which is `NEEDS_DECISION #5`'s
stated default. It spends zero enrichment credits doing it, because no provider
node is ever reached.

**Every provider node runs in list mode over a one-element list.** Not for
fan-out — for survivability. See gap 2.

**The seven classifiers run in series, not in parallel.** Each is still its own
node and its own HTTP call, so a single bad component fails and retries alone —
the property `clay_table_spec.md` §7 actually asks for. Chaining them costs
latency and buys a guarantee: node 25 is activated exactly once, and therefore
exactly one `icp.scored` event is POSTed per request. A seven-way fan-in would
have made that depend on undocumented join semantics.

---

## Where the Workflow primitive could not express the spec

Each of these is a measured gap, not a preference. Nothing was approximated
silently.

### 1. A code node has no network access at all

This is the one that shaped the graph. In the Clay **node runtime**:

- `urllib` is not importable — `ModuleNotFoundError`;
- `context.call_tool` does not exist — `AttributeError: 'TransitionContext'
  object has no attribute 'call_tool'`.

So a code node cannot call OpenAI, and an OpenAI-only model policy means every
LLM step is an `http-api-v2` tool node with a code node either side to build the
body and read the reply. Eight LLM calls become twenty-four nodes' worth of
concern spread over sixteen. The upside is real, though: the request is ours, so
`response_format` carries a genuine strict JSON schema (gap 5).

**`clay workflows code test` is a different, more permissive sandbox.** There,
`urllib`, `datetime` and `context.call_tool` all work. Code that passes
`code test` can still fail on the canvas. Treat it as a syntax check, not a
preview.

### 2. A tool node has no continue-on-error except through list mode

Found the hard way: a full run died at the Apollo node with
`Tool execution failed with status: ERROR — {"error":"Invalid access
credentials."}` and **the entire run failed** — no classifiers, no score, no
event. In the table version that same failure leaves one column empty and the
row scores anyway.

There is no `continueOnFail`, `onError`, `failureMode` or `optional` field on a
node; all four are rejected as unrecognized keys. The only tolerance setting
that exists is `listFailureMode: "ignore_errors"`, and it is a **list-mode**
setting. So every provider node runs in list mode over a one-element list: the
call is still made exactly once, and what the list buys is that a *partial*
failure is survivable.

**It is not a complete fix.** When 100% of a list's entries fail, the node still
fails and the run still stops — measured. A provider that is entirely down will
still take the run with it. This is a workaround wearing a feature's clothes; if
Clay adds a real per-node error policy, the one-element lists should go.

The cost of it is the output shape: a list-mode node's results are an array at
`$.results`, so downstream reads `$.results[0].<field>` rather than
`$.result.<field>`.

### 3. The code-node runtime has a restricted module allow-list

Importable: `json`, `time`, `math`, `re`, `os`, `sys`, `collections`,
`itertools`, `functools`, `random`, `operator`, `copy`, `textwrap`, `typing`.

`ModuleNotFoundError`: **`datetime`**, `urllib`, `calendar`, `hashlib`, `uuid`,
`decimal`, `statistics`, `string`, `base64`.

So the two date windows the rubric needs — news inside 12 months, an engineering
role open more than 60 days — are computed from integer day counts
(`_days_from_civil`, exact for every proleptic Gregorian date, verified against
Python's own `datetime` over ~11,000 dates spanning 1860–2079), and ISO 8601
stamps are formatted from `time.gmtime()`.
`tests/static/clay_nodes.test.mjs` fails the build on an import outside the
allow-list, via the AST rather than a regex.

### 4. Code nodes run Python, not JavaScript

`engine/clay_formula.txt` is JavaScript, generated from `config/rubric_v5.json`
and asserted deep-equal to `engine/scoring.mjs` over the golden fixtures and 500
generated inputs. It **cannot be pasted byte-for-byte** into a code node.

The port is `engine/clay_score.py`, generated from the same config, and
`tests/contract/python_parity.test.mjs` runs both implementations over 500
generated inputs, every vertical, every grade boundary and all five Clay
fixtures, and deep-compares. **Behaviour is proven identical; the bytes are not
the same bytes.** `tests/contract/clay_capture.test.mjs` goes further and
re-scores every live capture through the JavaScript engine, demanding the same
object back.

### 5. The classifier schema had to be re-derived for strict mode — and came out stronger

`engine/schemas/classifier_output.schema.json` is draft-07 and is not accepted
by OpenAI structured outputs, which supports a restricted subset: no `oneOf`
(use `anyOf`), no `if`/`then`/`allOf`, no `maxItems`/`maxLength`/`minimum`, every
property in `required`, `additionalProperties: false` everywhere.

`scripts/gen_openai_schemas.mjs` derives one strict schema per component from
the canonical schema plus the rubric, with `value` already closed to that
component's domain — stronger than the canonical schema, because the model
cannot emit a value from another component's domain at all.
`tests/contract/openai_schemas.test.mjs` asserts the derived schemas accept
**exactly** what the canonical schema accepts, with one documented exception:

| Canonical | Strict mode | How it is held |
|---|---|---|
| `evidence`: at most 6 items, each ≤ 200 chars | not expressible | stated in the prompt; node 24 truncates rather than trusting |
| `Contracting` requires `evidence_dated_within_months` (`if`/`then`) | not expressible | always required, may be null; `engine/scoring.mjs` S9 independently downgrades an undated `Contracting` and flags it |

Note what this gap *closed*. A Clay agent node's `outputSchema` is a flat map of
`string | number | boolean | email | url | select` — no array type, no nullable
number — so under the Claygent design `evidence` and `missing_inputs` had to
travel as JSON-encoded strings and a level as a `select` containing the literal
`"null"`. Under OpenAI strict mode they are real arrays and a real
number-or-null. The OpenAI-only policy made the contract cleaner, not dirtier.

### 6. No schema validation at the node boundary

The table spec validates every classifier output against
`classifier_output.schema.json` at the column. Strict mode guarantees the reply
matches the schema it was given, which covers most of it, but Clay itself
validates nothing — a failed or unparseable call is caught in node 24, which
renders it as `value: null`, `confidence: "low"` and a `missing_inputs` entry
naming the failure, so the scorer gates on it exactly as it would on an honest
"I could not tell".

### 7. The OpenAI key has nowhere to live in Clay — so it travels with the request

Clay has no CLI-reachable secret store, and a code node cannot read an
environment variable (`os.environ` is empty). With gap 1, that leaves one way to
run an OpenAI-only policy without committing a credential: **`openai_api_key`
travels in the Path A webhook payload**, from n8n's credential store, and the
tool nodes reference it as `Bearer {{openai_api_key}}`.

**This is a change to the Path A contract** — a thirteenth key on
`clay_table_spec.md`'s twelve — and it is flagged here rather than slipped in.
What it buys: nothing in this repository, nothing in a node's static config.
What it costs: the key appears in Clay run inputs for the life of the run
record. If that is not acceptable, the alternative is pasting it into each
node's `Authorization` header in the Clay UI, which trades run-record exposure
for node-config exposure. There is no third option inside Clay today.

### 8. The `X-Clay-Secret` value has the same problem

`clay_table_spec.md` §9 puts the Path B shared secret in Clay's secret store.
Same absence, and unlike the OpenAI key this one is not in the payload, so node
27 carries the literal `SET_IN_CLAY_UI`. Deliberate: the alternative was a real
secret in a file in this repository. Set it in the UI before Path B is anything
but a DEV target.

### 9. `nodes update` with `inputSchema` silently reverts `code`

Measured 2026-09-15. Updating a code node's `inputSchema` in a call that does
not also carry `code` reverts that node's `code` to its previous value — and
reports success:

```
$ clay workflows nodes update <wf> <node> --input '{"inputSchema": {...}}'
  appliedUpdates: [{"field":"inputSchema","success":true}]
$ clay workflows nodes get <wf> <node> | jq -r .node.code
  ...the PREVIOUS code...
```

The most dangerous item on this list, because the graph still validates and the
run still succeeds — it just runs last week's logic. The builder sends body and
wiring in one call, and pass 3 reads every node back and diffs it against this
repository. That read-back is the only actual proof.

### 10. The graph summary omits a trigger's canvas node id

`graph get` lists each trigger's `id` and `triggerType` but not its
`workflowNodeId`, which is what `incomingEdges` needs. Reading
`triggers[0].workflowNodeId` off the summary yields `undefined`, so a naive
re-run creates a *second* trigger — and since a trigger may have only one
outgoing edge, the first is orphaned and `graph validate` fails with
`trigger_not_connected`. The builder reads the node id back with `triggers get`.

### 11. `responseTimeout` has an undocumented ceiling, and overshooting it fails opaquely

`http-api-v2` accepts `responseTimeout: 120000` at save time without complaint.
The call then fails at run time with `ERROR_ACTION_RUNTIME_ERROR`, no HTTP
status and empty outputs — the same error text a malformed body produces, which
sent the first debugging pass at the request body rather than at the parameter.
90000 works, 120000 does not; the ceiling is somewhere between. Every OpenAI
node here uses 90s.

The general lesson, which cost two runs: an `http-api-v2` failure reports
nothing about *why*. Reproducing the node's exact inputs through
`clay workflows actions test` is the only way to see the real error, and it is
worth doing before re-running a graph.

### 12. A tool node's `inputSchema` is replaced by the action's own on save

Pins written onto a tool node's `inputSchema` are normalized away and replaced
by the action's parameter schema. They survive only as long as
`inputMappingConfig` references them by name, which is why every tool node here
maps its inputs through `inputMappingConfig`.

### 13. No documented accessor for the run id inside a code node

`event_id` is specified as the Clay row-run id and is the Path B dedupe key. A
code node's `context` exposes no run id; it appears only inside the private
`context._callback_url`. Node 26 reads it defensively and falls back to
`req-<request_id>`, which is unique per scoring request and dedupes exactly as
well.

### 14. The four website pages are guessed, not discovered

`clay_table_spec.md` §5 names homepage, `/about`, `/product` and `/careers`.
Node 04 constructs those four URLs from the domain, which is right often enough
to be useful and wrong often enough to matter: AKUVO's about page is not at
`/about`, and that URL returns a **soft 404** — HTTP 200, full site chrome, and
"The page can't be found" in the body. Reported as reachable, it would reach the
summarizer as though the company had said something.

Node 07 detects the common soft-404 phrasings and reports such a page
unreachable, which is the truth. The better fix, and the first thing worth doing
in the UI: `scrape-website` already returns `links[]` from the homepage, so a
node could pick the real about/product/careers URLs from the site's own
navigation instead of guessing. That costs one extra hop and was left out of
this build rather than added untested.

---

## Provider notes

- **Apollo is unusable in this workspace.** `apollo-oauth-*` reports one
  connected account, but calling one returns `{"error":"Invalid access
  credentials."}`. `NEEDS_DECISION #9`'s default named Apollo as primary for
  revenue; node 11 uses People Data Labs instead, which covers the same ground
  and adds `employee_count_by_role.engineering` — `eng_headcount_estimate`
  directly, rather than by inference. Reconnecting Apollo is a UI action; the
  builder has no opinion either way beyond which action node 11 points at.
- **Revenue often arrives as a band, not a number.** The company-profile lookup
  answers `"10M-25M"`. `enrichment_facts.schema.json` types
  `revenue_estimate_usd` as number-or-null and closes `additionalProperties`, so
  the band is reduced to its midpoint and the raw text is carried in
  `revenue_source` — which every classifier is told to cite by key. A reviewer
  reading an evidence line sees exactly how precise the number behind a grade
  is. This is not the headcount-derived revenue the prompt forbids; it is the
  provider's own estimate, expressed less precisely than a scalar.
- **"Found nothing" and "never asked" are different facts**, and the jobs and
  news providers echo the domain on a clean no-data result. That echo is the
  ran-signal, so an empty window becomes `0` / `[]` rather than null.
- **Run analysis is disabled for this workspace**, so `clay workflows analysis`
  — the one surface that reports per-node credits — answers `auth_forbidden`.
  Per-step credits here were measured with `clay workflows actions test`, whose
  `metadata.upfrontCreditUsage` is exact.

---

## What none of this changes

The `icp.scored` event POSTed to n8n Path B is byte-compatible with
`engine/schemas/icp_scored_event.schema.json`. Every number in it comes from
`config/rubric_v5.json` through a scorer that is parity-tested against
`engine/scoring.mjs`, and `tests/contract/clay_capture.test.mjs` re-derives the
score of every live capture to prove it. `ICP Final` is neither read nor
written. No secret is in any file here.
