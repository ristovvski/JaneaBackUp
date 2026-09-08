# Build 1 — Create the `dnc_ledger` + `obs_state` Data Tables

Two n8n Data Tables underpin every DNC/observability workflow. Schemas:
- [`dnc_ledger.schema.yaml`](dnc_ledger.schema.yaml) — the suppression ledger.
- [`obs_state.schema.yaml`](obs_state.schema.yaml) — observability state for WF 1.4.

Prereq: n8n **≥ 1.113** with `N8N_ENABLED_MODULES=data-table`. If your target n8n lacks the
Data Tables UI section, the module isn't enabled / version is too old — resolve that first.

---

## Platform facts that shape the whole build (verified 2026-07-23, docs.n8n.io)

| Fact | Consequence |
|---|---|
| Column types = **String, Number, Boolean, Date** only | `enum`/`unique` don't exist → enforced in workflow code |
| **No** unique constraint / index | `identity_key` / `state_key` uniqueness = Upsert-on-Equals + lookup-before-insert |
| Row operators: Equals, Not Equals, >, >=, <, <=, Is Empty, Is Not Empty | **No `Contains`** → match only on pre-normalized exact keys |
| Multi-condition combine: **Any (OR) / All (AND)** | conflict + waterfall logic built from these |
| Node ops: Insert, Update, Delete, Get, **Upsert**, If Row Exists, If Row Does Not Exist | Upsert is atomic but naive → rich merge (strongest type, append source) stays in code |
| Default cap **50 MB**, `N8N_DATA_TABLES_MAX_SIZE_BYTES` | fine for 100k+ rows; raise only if needed |
| Scope = **project** | create both tables in the SAME project the workflows live in |
| `/datatables` REST API exists | creation *can* be scripted, but see "API note" below |

## Create via UI (primary, safe method)

For each table, in the target project: **Data Tables → Create data table**, name it exactly
(`dnc_ledger`, then `obs_state`), then **Add Column** for every column in the schema file, setting
the n8n type from the `n8n_type:` field. Do **not** add the system columns (`id`, `createdAt`,
`updatedAt`) — n8n manages those.

Order doesn't matter functionally; adding them in schema order keeps the UI readable.

### `dnc_ledger` columns (16)
`identity_key`(String) · `linkedin_url_norm`(String) · `email_lc`(String) · `full_name`(String) ·
`pipedrive_person_id`(Number) · `entry_type`(String) · `source`(String) · `owner_tag`(String) ·
`reply_category`(String) · `status`(String) · `added_at`(Date) · `expires_at`(Date) ·
`removed_at`(Date) · `removed_reason`(String) · `correlation_id`(String)

### `obs_state` columns (7)
`state_key`(String) · `state_type`(String) · `campaign_id`(String) · `str_value`(String) ·
`num_value`(Number) · `expires_at`(Date) · `updated_at`(Date)

## API note (why I'm not shipping a create-table script)

The `/datatables` endpoint exists, but I have **not** verified the exact request body field names /
column-type token strings for your n8n version. Per factory invariant #5 (never invent node/API
parameter names), I will not emit a script that guesses them. If you want table creation automated,
confirm the payload shape in your DEV n8n (**Settings → n8n API**, or the API playground) and I'll
generate a verified script. For two tables, the UI is faster and risk-free.

---

## Enforced-in-code contract (what Build 2 must implement, since the table can't)

1. **Uniqueness** — before Insert, `If Row Exists` / `Get` on the key (`identity_key` or `state_key`)
   with **Equals**; Update the found row instead of inserting a duplicate.
2. **Enum domains** — validate `entry_type` ∈ {explicit_opt_out, negative_reply, replied,
   employee_connection, manual} and `status` ∈ {active, expired, removed} in the Normalize/validate
   step; reject/flag anything else.
3. **Strength order** — `explicit_opt_out > negative_reply > replied > employee_connection > manual`;
   Upsert keeps the max. Never downgrade.
4. **Source append** — union the incoming `source` into the existing comma-list, de-duped.
5. **Exact-match only** — all lookups use normalized keys with Equals (no substring matching exists).

## Seed rows for the test matrix (created in Build/fixtures step, listed here for reference)

Per the brief's fixtures list, `dnc_ledger` gets seeded (in DEV, or via an Insert fixture) with:
- **active explicit_opt_out** — permanent, `expires_at` null, `status=active`.
- **expiring replied** — `entry_type=replied`, `expires_at = tomorrow`, `status=active`
  (drives dnc_expiry_job "due row expires" + check-service "active" cases).
- **removed row** — `status=removed`, `removed_at`/`removed_reason` set
  (drives check-service "reported as clean with history").

Exact JSON for these lands with the fixtures (task: Fixtures + test matrix), so the seed and the
tests version together.

---

## Status
Build 1 delivered as schema definitions + this creation runbook. Creating the live tables is a UI
step in your chosen n8n project (I can't reach your instance). **Next: Build 2** — the three reusable
DNC subworkflows (`DNC__NormalizeIdentity__v1`, `DNC__UpsertLedger__v1`, `DNC__CheckLedger__v1`) that
turn the "enforced-in-code contract" above into actual nodes.
