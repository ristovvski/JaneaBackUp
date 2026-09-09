# ICP v5 auto-scoring — Phase 1

Scores the Pipedrive **Organization** behind every newly created deal against
the Janea ICP v5 composite rubric, and writes the result back as five
organization fields, one explanatory note and one audit row.

```
Pipedrive deal.create ──▶ n8n WF-ICP-Score (Path A) ──▶ Clay ICP_Engine
                                                            │
                                                     7 classifiers
                                                     + score formula
                                                            │
  Pipedrive ◀── 5 fields + 1 note + 1 audit row ◀── n8n (Path B)
```

Architecture: `ICP_Scoring_Architecture_v2_1.md`. Build task: §-numbered
references throughout this repo point at it. Rubric numbers: only ever
`config/rubric_v5.json`.

---

## Quick start

```bash
npm install
npm test          # unit + contract + static + golden       (no credentials needed)
npm run proof     # remove 3 behaviours, prove the tests catch them
```

`npm test` is green offline. Nothing in it touches Pipedrive, Clay, n8n, Slack
or the Anthropic API.

---

## What lives where

| Path | What it is |
|---|---|
| `config/rubric_v5.json` | **The single source of truth for every scoring number.** Weights, thresholds, level definitions, the 17 verticals, multipliers, windows. |
| `config/pipedrive_fields.json` | Field keys and enum option ids. Written by `pipedrive_create_fields`. |
| `engine/scoring.mjs` | The deterministic scorer. Pure. S1–S12. |
| `engine/normalize.mjs` | Domain / LinkedIn / company-name normalization and identifier resolution. |
| `engine/prompts/*.md` | The seven classifier prompts + shared preamble. **Generated** from the rubric. |
| `engine/schemas/*.json` | The three boundary contracts. |
| `engine/clay_formula.txt` | The Clay formula column. **Generated**, and parity-tested against `scoring.mjs`. |
| `engine/clay_table_spec.md` | The 36 columns Nik clicks into Clay. |
| `n8n/spec/` | The factory spec and its `/review-spec` findings. |
| `n8n/nodes/` | Code-node sources, extracted 1:1. What the tests run. |
| `n8n/workflows/` | The exported DEV workflow. Built by the patcher, never hand-edited. |
| `n8n/patch/` | The deterministic patcher and its validator. |
| `scripts/` | Generators and the three Pipedrive scripts. |
| `reports/` | The Phase 0 coverage audit and the discriminating-test proof. |
| `RUNBOOK.md` | Operate, debug, roll back. Slack alert glossary. |
| `REPORT.md` | What was built, what was not, every flagged decision. |

---

## Generated files — do not hand-edit

Four artefacts are derived from `config/rubric_v5.json` (and, for CONFIG, from
`config/pipedrive_fields.json`). A contract or static test fails if any of them
is stale, so a forgotten regeneration is caught by `npm test` rather than by a
wrong grade in Pipedrive.

| Command | Writes |
|---|---|
| `npm run gen:prompts` | `engine/prompts/*.md` |
| `npm run gen:formula` | `engine/clay_formula.txt` |
| `npm run gen:config`  | `n8n/nodes/CONFIG.json` |
| `npm run gen:nodes`   | `n8n/nodes/BuildClayRequest.js`, `n8n/nodes/ParseScored.js` |
| `node n8n/patch/patch.mjs` | `n8n/workflows/WF-ICP-Score.dev.json`, `api-payload.json` |

**Changing a scoring number is one edit** to `config/rubric_v5.json`, then:

```bash
npm run gen:prompts && npm run gen:formula && npm run gen:config && npm run gen:nodes
node n8n/patch/patch.mjs
npm test
```

An n8n Code node cannot `import`, so `BuildClayRequest` and `ParseScored` carry
spliced-in copies of `engine/normalize.mjs` and the parity-tested scoring body.
That is why they are generated: a hand-maintained copy of tested logic is how
wrong grades ship.

---

## Test suites

| Suite | Command | What it proves |
|---|---|---|
| unit | `npm run test:unit` | S1–S12 and the normalization table |
| contract | `npm run test:contract` | fixtures match the schemas; prompts carry the rubric text byte for byte; Clay and the engine agree on 500 inputs |
| static | `npm run test:static` | the exported workflow is safe and deployable; the real Code-node sources behave |
| golden | `npm run test:golden` | Akuvo = A; Microsoft, Merck ≠ A |
| live | `npm run live` | the DEV workflow end to end, asserting execution truth |

`npm run live` needs a DEV n8n, the Pipedrive webhook registered, and Nik's
Clay table. It prints its own prerequisites and exits if any are missing.

### The golden set runs on SYNTHETIC facts today

`tests/golden/facts/SYNTHETIC_*.json` are hand-authored and say so, in the
filename and in the body. They prove the **harness** works, not the
classifiers. Every run prints that distinction. Replace them with facts
captured from real Clay runs before treating a golden grade as validation; the
harness **skips** — never passes — an account with no captured facts.

---

## Running the Pipedrive scripts

All three read `PIPEDRIVE_API_TOKEN` from the environment. None writes a
credential to a file, puts one in a URL, or logs one.

With a local `.env`, Node reads it natively — no wrapper needed:
`node --env-file=/path/to/.env scripts/<script>.mjs`. See RUNBOOK.md
"Supplying credentials" for the least-privilege set and why a remote session
cannot see your local file.

```bash
# Phase 0 audit — READ ONLY, GETs only
PIPEDRIVE_API_TOKEN=... npm run audit:coverage
node scripts/pipedrive_audit_coverage.mjs --pages ./pd-pages   # from saved pages, no token

# Create the five organization fields — idempotent
PIPEDRIVE_API_TOKEN=... node scripts/pipedrive_create_fields.mjs --dry-run
PIPEDRIVE_API_TOKEN=... npm run pipedrive:fields
npm run gen:config && node n8n/patch/patch.mjs   # always regenerate after this

# Register the deal.create webhook — idempotent, refuses an unauthenticated endpoint
ICP_DEV_WEBHOOK_URL=https://... \
ICP_WEBHOOK_BASIC_USER=... ICP_WEBHOOK_BASIC_PASSWORD=... \
PIPEDRIVE_API_TOKEN=... npm run pipedrive:webhook
```

---

## Invariants this repo enforces mechanically

Not aspirations — each is a failing test if broken.

1. **No secrets anywhere in the repo or the workflow JSON.** Credentials by
   name only. The four environment-specific values reach CONFIG from `$env`.
2. **`active: false` in every export.** DEV project only. `/publish` is
   human-gated and untouched.
3. **Every Pipedrive write is idempotent.** Three layers: the dedupe ledger
   (duplicate delivery), the 180-day/model gate (duplicate scoring run), the
   write gates (duplicate write).
4. **`ICP Final` is never read and never written.** The patch builders check
   `CONFIG.fields_never_write` and throw rather than silently omitting.
5. **No invented API field or node parameter.** Where the docs are silent, the
   code emits `NEEDS_DOC_EVIDENCE` and stops. See `REPORT.md`.

---

## Not in Phase 1

Slack `/icp`, approve/override buttons, the manual calculator, dedup and org
creation, Clay-side campaign scoring, and production deploy. See `REPORT.md`
for the full scope boundary and why each is out.
