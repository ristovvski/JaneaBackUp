# RUNBOOK — WF-ICP-Score

Operate, debug, roll back. Written for whoever is on call, not for whoever
built it.

---

## Table of contents

- [First-time setup](#first-time-setup)
- [Slack alert glossary](#slack-alert-glossary)
- [Debugging: start here](#debugging-start-here)
- [Symptom → cause](#symptom--cause)
- [Changing a scoring number](#changing-a-scoring-number)
- [Rolling back](#rolling-back)
- [Turning it off](#turning-it-off)
- [What this workflow will never do](#what-this-workflow-will-never-do)

---

## First-time setup

In this order. Steps 1–3 are read-only or idempotent; nothing before step 5
sends a single deal through.

### Supplying credentials

Every script reads its credentials from the **environment** — never from a file
in this repo, never from a command-line argument (which would land in your
shell history), never from a URL.

If you keep a local `.env`, Node reads it natively; no wrapper and no code
change:

```bash
node --env-file=/path/to/.env scripts/pipedrive_create_fields.mjs --dry-run
node --env-file=/path/to/.env scripts/pipedrive_audit_coverage.mjs
node --env-file=/path/to/.env tests/live/dev_e2e.mjs
```

`.env` is in `.gitignore`. Keep it there.

> **Least privilege.** This build needs exactly two secrets:
> `PIPEDRIVE_API_TOKEN` and, for the DEV import and the live suite,
> `N8N_API_KEY` (+ `N8N_BASE_URL`). It never touches Smartlead, HeyReach,
> Make or OpenAI. If your `.env` is the shared outreach-stack one, prefer a
> trimmed copy holding only those keys — the classifiers run on Claude, so an
> `OPENAI_API_KEY` in scope here buys nothing and risks something.

> **A remote Claude Code session cannot see your local `.env`.** The container
> is cloned fresh from git, and `.env` is untracked by design. To run these
> from a web session, set the values as **environment variables on the remote
> environment** instead of uploading the file — see
> <https://code.claude.com/docs/en/claude-code-on-the-web>. Uploading or
> pasting the file puts live production keys into a stored transcript.

### 1. Phase 0 audit (read-only)

```bash
PIPEDRIVE_API_TOKEN=... npm run audit:coverage
```

Read `reports/coverage.md` before anything else. It tells you what share of
organizations can be identified at all, which sets the ceiling on everything
downstream.

### 2. Create the organization fields

```bash
PIPEDRIVE_API_TOKEN=... node scripts/pipedrive_create_fields.mjs --dry-run   # look first
PIPEDRIVE_API_TOKEN=... npm run pipedrive:fields
npm run gen:config
node n8n/patch/patch.mjs
npm test
```

A second run must report **"0 created, 5 found"**. If it reports anything else,
somebody renamed a field — matching is by name.

`gen:config` and the patcher are not optional here: until they run, the
workflow still carries the placeholder field keys and would write to nothing.

### 3. Credentials in the DEV n8n project

Five, by name. Values are never in this repo.

| Credential | Type | Holds |
|---|---|---|
| `pipedrive_main` | Pipedrive API | the API token for org GET/PATCH and note POST |
| `icp_webhook_basic` | HTTP Basic Auth | the user/password Pipedrive will send to Path A |
| `clay_webhook_secret` | HTTP Header Auth | name `X-Clay-Secret`, value the shared secret |
| `slack_ops` | Slack API | posting to the ops channel |
| `gsheets_audit` | Google Sheets OAuth2 | appending to `ICP_Audit` |

### 4. Environment variables on the n8n instance

CONFIG reads these four at runtime. A Clay webhook URL is an unguessable
endpoint — treat it as a secret.

```
ICP_CLAY_WEBHOOK_URL    the Clay ICP_Engine webhook source URL
ICP_CLAY_CALLBACK_URL   the Path B webhook URL (what Clay posts back to)
ICP_AUDIT_SHEET_ID      the ICP_Audit spreadsheet id
ICP_SLACK_CHANNEL       the channel id, e.g. the id of #gtm-ops-dev
```

> **If `$env` returns nothing**, the instance has
> `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`. CONFIG will produce `undefined` for all
> four and the Clay POST will fail with an invalid URL. Set it to `false`, or
> move the four values into a credential.

### 5. Import the workflow

```bash
# via the n8n UI: Import from File -> n8n/workflows/WF-ICP-Score.dev.json
# or via the API, which takes only the four writable keys:
curl -X POST "$N8N_API_URL/workflows" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" -H 'content-type: application/json' \
  --data @n8n/workflows/api-payload.json
```

The export is `active: false`. **Arming it is a human act.** Confirm on import:

- [ ] the Google Sheets node's column mapping is `autoMapInputData` and the
      `ICP_Audit` header row matches `BuildAuditRow`'s 31 columns, in order
- [ ] every node shows a green credential, none shows "credential not found"
- [ ] both webhook nodes show their authentication set
- [ ] `settings.errorWorkflow` resolves to the real WF-ERR (the export carries
      the name `WF-ERR`; n8n may want the id)

### 6. Create the audit sheet

A spreadsheet named `ICP_Audit` with a tab `ICP_Audit`, whose header row is
exactly `BuildAuditRow`'s columns in order:

```
ts, request_id, execution_id, trigger, deal_id, org_id, identifier_kind,
identifier_value, model_version, industry_vertical, industry_level, stage_level,
type_level, geo_level, revenue_level, buying_level, activation_state, multiplier,
composite, final, final_without_activation, grade, status, confidence_overall,
tier2_candidate, flags, missing_inputs, evidence_json, patch_written, note_id, error
```

Order matters: `autoMapInputData` matches by header name, and a column present
in the node but missing from the sheet is silently dropped.

### 7. Register the Pipedrive webhook

```bash
ICP_DEV_WEBHOOK_URL="<Path A production URL>" \
ICP_WEBHOOK_BASIC_USER=... ICP_WEBHOOK_BASIC_PASSWORD=... \
PIPEDRIVE_API_TOKEN=... npm run pipedrive:webhook
```

Use the same user/password as the `icp_webhook_basic` credential. The script
refuses to register an unauthenticated endpoint unless you pass
`--allow-unauthenticated`.

### 8. Live e2e

```bash
npm run live      # prints its own prerequisites and exits if any are missing
```

---

## Slack alert glossary

Two messages, both in the channel `ICP_SLACK_CHANNEL` points at. Every one
carries `execution_id` — that is how you find the run.

### 🚨 `ICP scoring failed`

```
:rotating_light: ICP scoring failed. org_id=<id> request_id=<id>
execution_id=<id> error=<Name>: <message>
```

Posted from the error branch, **before** the org is marked. What the error name
tells you:

| Error name | Meaning | What to do |
|---|---|---|
| `IcpMalformedEvent` | Clay posted something that failed the schema check, or a callback arrived without `request_id`/`event_id`. | Open the Clay row. Usually a renamed column or an edited `post_to_n8n` body. The alert message lists every violation. |
| `IcpUnknownPayload` | A body matched neither the Pipedrive envelope nor the Clay callback. | Both endpoints are authenticated, so this is a real caller. Check whether a second webhook subscription points here. |
| `IcpNoIdentifier` | The org has no website, no LinkedIn URL **and** no usable name. | Nothing to enrich from. Fix the org record. |
| `IcpMissingOptionId` | `CONFIG.opt_icp_calculated` has a `null` id. | `pipedrive_create_fields` has not been run, or was run and `gen:config` was not. Re-run both, rebuild, re-import. |
| `IcpUnmappedGrade` | A grade with no label in `grade_labels`. | Rubric edited without regenerating CONFIG. |
| `IcpForbiddenWrite` | A patch tried to include `ICP Final`. | A code change broke invariant 4. Do not work around it. |
| `IcpAuditColumnMissing` | `BuildAuditRow` lost a column. | Reconcile the node against the sheet header. |

If the alert arrives but **no** `Error` appears on the organization, the PATCH
also failed. That is why the alert comes first. Look for a second failure from
WF-ERR.

### ⚠️ `ICP scoring trigger volume is unusually high`

```
:warning: ICP scoring trigger volume is unusually high: <n> events this hour
(limit <max>). A bulk import can burn Clay credits fast.
execution_id=<id> request_id=<dedupe key>
```

The anomaly gate. **Non-blocking** — processing continues. Normal volume is
~15 deals/day (Phase 0 measured 2,000 organizations over four months), so this
firing means a bulk import or a loop. Decide whether to let it run; to stop it,
deactivate the workflow (below) — the deals stay, and they will be scored when
you reactivate, because the org-level gate is durable.

Threshold: `CONFIG.max_events_per_hour`, currently **200**.

---

## Debugging: start here

Every artefact carries `request_id`. One search finds the whole story.

```
1. Slack alert            -> execution_id and request_id
2. n8n execution list     -> filter by execution_id, open it, read the node outputs
3. the ICP_Audit sheet    -> filter by request_id: one row per Path B run
4. the Pipedrive note     -> the footer carries "request_id <id>"
5. the Clay row           -> request_id is column 1
```

The `error` column of the audit row is the fastest read: it carries
`duplicate`, `rate_exceeded:<n>/h`, and `clay_score_drift:<detail>`.

---

## Symptom → cause

### Deals are created but nothing happens

- Is the workflow **active**? The export ships `active: false` on purpose.
- Is the webhook registered? `node scripts/pipedrive_register_webhook.mjs --list`.
- Is it pointing at the **production** URL of the webhook node, not the test URL?
- Check the n8n execution list for failed runs — a basic-auth mismatch shows as
  a 403 with no execution at all.

### An organization shows `Insufficient data`

Usually correct, not a bug. `stage_maturity`, `revenue_range` and
`company_type` each gate it, and Phase 0 found **76.8%** of organizations reach
Clay as a bare name. Read the note's `Missing / low confidence:` line — it
names the facts the classifiers wanted. The fix is enrichment coverage, not
scoring.

### An organization shows `Error`

See the alert glossary. Once fixed, it re-scores on the next deal:
`Error` is deliberately **not** counted as a fresh score
(`CONFIG.rescore_on_error_or_insufficient`), so a transient outage cannot
freeze an account out of scoring for 180 days.

### The score looks wrong

1. Open the note. It shows every component level, the level text, the evidence,
   the multiplier and the arithmetic. Nine times in ten the classifier is
   defensible and the *facts* are wrong.
2. Check the audit row's `flags` column:
   - `unknown_vertical` — the classifier returned a vertical outside the 17
   - `contracting_without_dated_evidence` — an undated Contracting was downgraded
   - `clay_score_drift` — **Clay and n8n disagreed** (see below)
   - `tier2_candidate` — over $500M revenue, over 1,000 headcount, or type 7
3. Re-derive it: the note carries every input, and `engine/scoring.mjs` is pure.

### `clay_score_drift` in the flags

Clay's `score_json` column disagreed with n8n's independent recompute. **n8n's
value was written** — it is the one with 500 parity cases behind it. The Clay
formula column is stale:

```bash
npm run gen:formula        # regenerate from the current rubric
# then re-paste the STEP 3 block from engine/clay_formula.txt into the column
```

The audit row's `error` column carries the exact field-by-field difference.

### An organization was scored twice

It should not be, and the audit row will say which layer let it through.
Two records for one company is the likelier cause: Phase 0 found 23
normalized-name clusters in a 2,000-organization sample, including
**Sumersports five times**. Dedup is out of Phase 1 scope — two records get two
grades, correctly, because they are two organizations as far as Pipedrive is
concerned.

### A rep's edit to `ICP Calculated` disappeared

Expected (NEEDS_DECISION #2, honor system). `ICP Calculated` is the system's
field; `ICP Final` is the human's, and the system never touches it. A
`NOTE_WATCHDOG` comment in `BuildOrgPatch.js` marks where a
`change.organization` watchdog would attach if the honor system does not hold.

### Duplicate notes on one organization

Should be impossible: `POST note` has `retryOnFail: false`, a Path B duplicate
skips the note, and an empty patch skips it too. If it happens, check whether
two n8n instances hold the same webhook path.

---

## Changing a scoring number

Every number lives in `config/rubric_v5.json`.

```bash
$EDITOR config/rubric_v5.json
npm run gen:prompts && npm run gen:formula && npm run gen:config && npm run gen:nodes
node n8n/patch/patch.mjs
npm test
```

Then, because two of the four consumers are outside this repo:

1. Re-paste the seven prompts into the Clay AI columns.
2. Re-paste `engine/clay_formula.txt` STEP 3 into `score_json`.
3. Re-import the workflow into DEV.

**Bump `model_version`** if the change alters scores. Every organization scored
on the old version then re-scores automatically on its next deal, because the
gate compares versions as well as dates. Leaving the version alone after a
scoring change leaves a Pipedrive full of scores from two different rubrics
with nothing to tell them apart.

---

## Rolling back

The workflow is a build artefact, so rollback is a rebuild.

```bash
git log --oneline -- icp-scoring/n8n/workflows/WF-ICP-Score.dev.json
git checkout <sha> -- icp-scoring/
npm test
node n8n/patch/patch.mjs --check     # confirms the export matches its sources
# re-import into DEV
```

Before any re-import, record the current `versionId` from n8n so you can get
back. The Pipedrive **data** is not rolled back by any of this: a wrong grade
already written stays until the next scoring run overwrites it.

---

## Turning it off

| How | Effect |
|---|---|
| Deactivate in n8n | Both paths stop. In-flight Clay rows will POST to Path B and get a 404. |
| Delete the Pipedrive webhook | Path A stops; Path B still accepts callbacks. The cleaner stop. |
| Pause the Clay table | Path A still fires and POSTs; no callbacks come back. Organizations stay unscored, no `Error`. |

To stop scoring **without** losing work: delete the Pipedrive webhook and let
the in-flight Clay rows finish. No organization is left half-written, because
the writes all happen in one Path B execution.

```bash
node scripts/pipedrive_register_webhook.mjs --list
curl -X DELETE -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  https://api.pipedrive.com/api/v1/webhooks/<id>
```

---

## What this workflow will never do

Worth knowing before you go looking for a bug that is a design decision.

- **Never write `ICP Final`.** It is the human's field.
- **Never read `ICP Final`** as scoring input.
- **Never create or merge an organization.** It scores what exists.
- **Never contact anyone.** No email, no LinkedIn, no sequence. A DNC'd
  company still gets scored — that is an internal analytical act, not contact.
- **Never write the same value twice.** An unchanged value produces an empty
  patch and no API call.
- **Never publish to production.** `/publish` is human-gated and this repo
  does not implement it.
