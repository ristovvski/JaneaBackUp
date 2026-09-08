# DNC_CheckService gate — contract + policy (skeleton, 2026-08-14)

## What it is

The gate primitive is **`DNC__CheckLedger__v1`** (subworkflow id `kv7reJYAAgsOV33t`), already
deployed and already the thing every DNC lookup in this project calls — `dnc_check_service`'s
Slack `@mention` tool (workflow id `PViKUykLaDd7Xze1`) is its only caller today. It is read-only
toward the registry (`dnc_registry_dev`), makes no writes, and is safe to call from any number of
places concurrently.

## Contract (verified directly from the deployed subworkflow's code, not assumed)

**Call it via `n8n-nodes-base.executeWorkflow`, `mode: "each"`** (never `"once"` — see
`build_dnc.py`'s `exec_wf()` comment for why `"once"` silently drops every item past the first).

**Input** (one item per person to check):
```json
{ "linkedin_url": "https://www.linkedin.com/in/pii-33d9a963", "email": "someone@example.com" }
```
Either field alone is enough; both together is fine (LinkedIn is checked first, then email, then
the two hit-sets are merged and de-duplicated). Both are optional but at least one is expected —
if neither resolves to anything, the result is `usage_hint`, not an error.

**Known gap, not yet closed:** there is no direct "check by bare Pipedrive person id" path today
— only `linkedin_url`/`email` key the lookup. A caller that only has a `pipedrive_person_id` must
resolve an email/LinkedIn from Pipedrive first (e.g. `GET /api/v2/persons/{id}`) before calling the
gate. Worth closing before "person id" callers show up, but not blocking today's skeleton.

**Output** (one item):
| `result` | Meaning | Extra fields |
|---|---|---|
| `on_dnc` | **YES — in the registry, active.** | `entry_type`, `source`, `since`, `expires_at` (null = permanent), `duplicates_seen` |
| `clean` | **NO — never in the registry.** | — |
| `clean_with_history` | **NO now, but WAS on DNC before** (expired/removed). | `was_type`, `until` |
| `usage_hint` | Neither `linkedin_url` nor `email` normalized to anything checkable. | — |

`entry_type` is the "reason" a caller actually needs for a yes/no decision — one of
`explicit_opt_out` / `negative_reply` / `replied` / `employee_connection` / `manual`. Strongest
entry_type wins across duplicate rows (self-healing read, matches the write-side dedupe logic).

## The rule (§, per Melisa/Nik's ruling — 2026-08-14)

> **No automated path may add a person to a cold outbound campaign (Smartlead campaign-add,
> HeyReach campaign-add, or a Pipedrive automation that feeds one) without first calling
> `DNC__CheckLedger__v1` and confirming `result !== 'on_dnc'`.**

This is a gate on the *write* side of cold outreach, not a Pipedrive label check — the label
projection this project already built (and partially reversed, per Melisa's separate label-scope
ruling) is a **downstream signal for humans and Pipedrive-side filters**, not the enforcement
point. The registry (`dnc_registry_dev`) is the source of truth; this subworkflow is the only
sanctioned way to read it programmatically before an add-to-campaign action.

## Wired in today vs. not yet (explicit, per Nik: wiring is next week by design)

**Wired in today:** `dnc_check_service` (human-facing Slack lookup only — reactive, not a gate on
anything).

**NOT wired in yet** (this is the part "next week" covers — named here so it isn't a surprise
later):
- Whatever Make.com scenario(s) actually add leads to Smartlead/HeyReach cold campaigns (the Ai4
  lead-creation Make scenario and any sibling scenarios — see `make-lead-creation-defects` memory
  for the scenario ids already known from earlier work in this project).
- Any Zapier "Outreach infrastructure" Zap that could feed a cold campaign.
- Any future n8n workflow that creates cold-campaign adds directly.

Each of these is an *external* system (Make/Zapier) or a not-yet-built n8n path — wiring the check
into a Make.com scenario specifically means adding an HTTP-callable front door to this gate (an
n8n webhook wrapper around `DNC__CheckLedger__v1`, since Make can't call an n8n subworkflow
directly via `executeWorkflow`); wiring it into a future n8n workflow just means an `executeWorkflow`
call, no wrapper needed. Neither is built yet — that's next week's work, not today's.
