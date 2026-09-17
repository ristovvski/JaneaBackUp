# /review-spec — WF-ICP-Score

Reviewed `n8n/spec/WF-ICP-Score.yaml` against `references/checklists.md`
(spec-review checklist), the SKILL.md invariants, and the golden example's
build checklist.

**Verdict: PASS with 4 findings.** Three are `NEEDS_DECISION` items already
listed in §11 of the build task and implemented at their stated defaults. One
(F1) is a spec change I made during review and it is reflected in the YAML.

`/build-dev` is blocked on Nik's sign-off of this document.

---

## Checklist

| # | Item | Result | Where |
|---|---|---|---|
| 1 | Business rules complete (enrollment, dedupe, verification, skip conditions) | **PASS** | 8 rules under `business_rules`; the skip condition is the three-part org gate |
| 2 | All identifiers present (correlation id, provider ids written back) | **PASS** | `request_id` minted on Path A, echoed by Clay, on every artefact. No provider id needs writing back — Clay holds no durable id we depend on |
| 3 | No provider capability conflicts | **PASS** | see *Capability checks* below |
| 4 | Duplicate / re-enrollment risk addressed | **PASS** | three independent layers under `idempotency`, each justified |
| 5 | Rate-limit risk vs stated volume acceptable | **PASS** | see *Volume* below |
| 6 | Error handling and stop conditions defined | **PASS** | `error_policy`, plus the explicit "malformed event throws, never skips" |
| 7 | Required CRM fields specified | **PASS** | `field_mappings`, resolved from `config/pipedrive_fields.json` |
| 8 | Slack routing correct | **PASS** | one channel from CONFIG, `per_error_only`, DEV channel in DEV |
| 9 | Unsubscribe / DNC handling present | **N/A, justified** | see *DNC* below |

### Invariants (hard fails)

| Invariant | Result |
|---|---|
| No secrets in workflow JSON or Code nodes | **PASS** — `security` names the four credentials by name only; static test greps the export |
| Never publish to production autonomously | **PASS** — `deployment_target: dev`, `active: false`, `/publish` untouched |
| External writes idempotent and duplicate-protected | **PASS** — finding F1 closed the one gap |
| Preserve unsubscribe / DNC state | **N/A** — this workflow sends nothing to a person |
| Never invent an n8n parameter | **PASS** — two `NEEDS_DOC_EVIDENCE` items resolved by fetching the docs; see below |

---

## Findings

### F1 — Path B had no dedupe key. **Fixed in the spec.**

The graph in §8.2 puts `Dedupe` on both paths, but §8.1 specified only one
idempotency key, `pipedrive:deal:{deal_id}:{event_id}` — which is a Path A
shape. Path A's `event_id` is `meta.id` from the Pipedrive envelope; a Clay
callback has no such field, so Path B's Dedupe would have keyed on `undefined`
and dropped **every** callback after the first.

That is not a small bug: it would have looked like "scoring works once and then
stops", intermittently, only in production volumes.

Resolved by giving Path B its own key, `clay:scored:{request_id}:{event_id}`,
and adding `event_id` to `icp_scored_event.schema.json` as a required field with
`minLength: 8`. Clay's row-run id fills it. Because the schema requires it, a
Clay column misconfiguration fails validation at the boundary rather than
silently poisoning the ledger.

**Also caught:** the key must not include `meta.attempt`. Pipedrive increments
`attempt` on every retry, so a key containing it treats each retry of one event
as a new event — the exact opposite of dedupe. Recorded as a note in the spec
and asserted by the replay fixture, whose only difference from the original is
`attempt: 1 -> 2`.

### F2 — `NEEDS_DECISION #3`: geography "network reach". Default implemented.

The signed rubric qualifies geography 10 and 7 with "within network reach" /
"with network coverage". No enrichment fact expresses network reach, so the
classifier scores by region alone. Recorded in three places so it cannot be
forgotten: `config/rubric_v6.json` (`geography_rule_deviation`), the geography
prompt (a blockquote instructing the classifier not to infer coverage), and a
contract test asserting the config note names the decision.

Changing it later means adding a `network_reach` fact to the enrichment schema
and one clause to the geography prompt — not a rebuild.

### F3 — `NEEDS_DECISION #2`: `ICP Calculated` is unguarded against rep edits. Honor system.

Nothing stops a rep overwriting `ICP Calculated`; the next re-score silently
reverts it, up to 180 days later. The default is the honor system, and
`ICP Final` exists as the field a rep is *meant* to edit.

A `NOTE_WATCHDOG` comment marks the exact place a `change.organization` webhook
would attach if the honor system does not hold. It is a comment, not dead code.

### F4 — `NEEDS_DECISION #7`: Google Sheets as the audit store.

A 31-column append per scoring run. Sheets is fine at Phase 1 volume and wrong
at scale (append quotas, no query, 10M-cell ceiling). The node is one append
behind a CONFIG-held sheet id, so moving to Postgres or a Data Table is a node
swap, not a redesign. Flagged rather than pre-solved.

---

## Capability checks

| Question | Answer | Evidence |
|---|---|---|
| Does a Pipedrive v2 webhook support `deal.added`? | No such action. It is `event_action=create` on `event_object=deal`. | `developers.pipedrive.com/docs/api/v1/Webhooks` — event_action ∈ create, change, delete, * |
| Can the Pipedrive webhook endpoint be authenticated? | **Yes**, HTTP basic auth on the subscription: `http_auth_user`, `http_auth_password`. This closes the one gap the golden example flags against the factory default ("endpoint auth relies on an unguessable path"). | same page |
| What does the v2 envelope look like? | `meta` + `data` + `previous`; `previous` is `null` on create; `meta.id` is the triggering event's id. | `pipedrive.readme.io/docs/guide-for-webhooks-v2` |
| Field name gotcha | `meta.is_bulk_edit`, **not** `is_bulk_update`. The fixtures use the documented name. | same page |
| How are org custom fields created? | `POST /api/v2/organizationFields`, body `field_name` (**not** `name`), `field_type`, and for enums `options: [{label}]`. | `developers.pipedrive.com/docs/api/v1/OrganizationFields` |
| Are enum option ids in the create response? | **Undocumented.** §8.2 requires writing enums by option id, so `create_fields` reads `options[].id` back and fails with `NEEDS_DOC_EVIDENCE` if absent rather than guessing. | same page — "The documentation doesn't explicitly state whether response options include numeric IDs" |
| Webhook create parameters | `subscription_url`, `event_action`, `event_object`, **`name`** all required; `version` optional, `'1.0'`\|`'2.0'`, default `'2.0'`. | Webhooks page |

Two Pipedrive gotchas from the golden example that apply here:

- **Persons are v2 with a `custom_fields` object; leads are v1 with top-level
  hashed keys.** Organizations are v2, so the org patch nests custom fields
  under `custom_fields`. Confirmed against a live read: an org returns
  `custom_fields: { "<40-hex>": value }` alongside native `website`, `linkedin`,
  `industry`, `annual_revenue`, `employee_count`.
- **Clear a varchar custom field with `null`, not `""`.** Relevant to
  `ICP Score` on the `insufficient_data` path: the score must be *absent*, and
  the patch builder omits the key rather than sending `""`.

---

## Volume

Phase 0 measured 2,000 organizations created between 2026-05-02 and 2026-09-08
— roughly **15 new organizations a day**, and deals are created at a similar or
lower rate.

| Path | Calls per event | Budget concern |
|---|---|---|
| A | 1 GET org, 1 POST Clay | none |
| B | 1 GET org, ≤1 PATCH org, 1 POST note, 1 Sheets append | none |

At ~15 events/day this is well inside any Pipedrive token budget. Backoff on
429 honouring `retry-after` is specified anyway, because a backfill would
change the arithmetic and a backfill is exactly the thing someone runs without
re-reading the spec.

**Anomaly gate.** If Path A ever sees more than a configured number of events
in an hour (CONFIG `max_events_per_hour`), it posts one Slack warn as a
non-blocking tee and keeps processing. A bulk import creating thousands of
deals would otherwise fan out into thousands of Clay credits before anyone
noticed. This is the golden example's anomaly-gate discipline applied to the
trigger rather than to a data migration.

---

## DNC — why "not applicable" is the right answer here

The factory checklist requires unsubscribe/DNC handling on every workflow, and
the SKILL.md invariant is that suppression is global and permanent. This
workflow:

- sends nothing to any person — no email, no LinkedIn message, no sequence
  enrolment;
- writes only to the **organization** record, plus one internal note and one
  internal audit row;
- reads no person record at all.

So there is no channel for suppression to protect. Scoring a suppressed
company's ICP fit is an internal analytical act, not contact.

**One thing worth saying out loud:** a DNC'd company still gets scored, and its
grade still appears in Pipedrive. If a rep reads "ICP A" as "go contact them",
the DNC lives one object away in the person record. That is a reporting concern
for the Slack `/icp` phase (out of Phase 1), not a reason to skip scoring here.
Recorded so the next phase inherits the question rather than rediscovering it.

---

## Deviations from the factory defaults, stated

| Default | What this workflow does | Why |
|---|---|---|
| Provider-agnostic adapter subworkflows | Direct Pipedrive calls, CONFIG-centralized | The golden example's own conclusion for a single-provider stack. Adapters earn their cost at the second CRM |
| One trigger per workflow | Two webhook nodes in one workflow | Path B needs Path A's CONFIG, dedupe ledger and field keys, and `$getWorkflowStaticData` is workflow-scoped. Splitting them would need an external ledger for no benefit |
| `CORE__IdempotencyGuard` + Data Table ledger | Code node + TTL'd static data | Golden example: simpler, no extra infrastructure, proven. The org-level gate is the durable layer, so a static-data reset degrades to one extra scoring run, not a double write |
| Alert-before-writes | Followed: the error branch alerts **before** the Error patch | If marking the org as Errored also fails, the human ping must still have gone out. `Slack alert error` sits between `BuildErrorPatch` and the write gate with `continueOnFail: true`, and is the only allow-listed `continueOnFail` in the workflow |

---

## What a reviewer should push back on

Three things I would question if I were signing this off:

1. **The 180-day window is doing two jobs.** It is both "the score is stale" and
   "the rubric may have moved". The model-version check already covers the
   second, so 180 days is purely a freshness policy — and a company's stage can
   change in a quarter. `NEEDS_DECISION #4` default is implemented; if the
   answer is 90 days, it is a one-line CONFIG change.

2. **`insufficient_data` will be common.** Phase 0 says 76.8% of organizations
   reach Clay as a bare name. `revenue_range`, `stage_maturity` and
   `company_type` all gate `insufficient_data`, so a large share of first-pass
   results will not carry a grade. The system is behaving as specified. Whether
   that is *acceptable* is a business call, and it is better made before Tuesday
   than during it.

3. **The note is a note, not an Activity** (`NEEDS_DECISION #1`). A note is
   invisible in an activity feed and does not appear in reporting. If the point
   is for a rep to *notice* the score, an Activity would land harder. The
   default is implemented; the swap is one node.
