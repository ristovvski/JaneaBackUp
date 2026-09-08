# Create the `i04_event_log` Data Table

Part of the I-04 redesign (event-driven lite, replacing the nightly full walk as the primary
detector — Nik's call, 2026-08-26): a Pipedrive-native webhook appends one row per lead/person
change here; the daily summary reads this instead of diffing two full-estate snapshots.

**In the target n8n project: Data Tables → Create data table**, name it exactly `i04_event_log`,
add these columns:

| column | n8n type | notes |
|---|---|---|
| `event_id` | String | unique row key, `"<object_type>:<object_id>:<received_at>"` |
| `received_at` | Date | when n8n got the webhook call |
| `event_action` | String | `added`/`updated`/`deleted`/`merged`/`unknown` -- best-effort, see below |
| `object_type` | String | `lead` or `person` (only these two are subscribed) |
| `object_id` | String | the lead (uuid) or person (numeric) id |
| `raw_json` | String | the FULL raw webhook body, verbatim, unparsed |
| `top_level_keys` | String | comma-joined top-level keys of the raw body -- shape-confirmation aid |

## Why store the raw body, not a parsed diff

Registering a real Pipedrive webhook subscription today revealed the account is on **webhook
format v2.0** (confirmed from the subscription-creation response: `"version": "2.0"`), not the
classic v1 `{meta, current, previous, event}` shape this project assumed going in. No real event
arrived during the 90s observation window to confirm the ACTUAL v2 field layout live. Rather than
guess field names (the exact class of bug this project has hit before — custom_fields nesting,
envelope wrapping, bare-number vs. object fields) or force a synthetic mutation on a real
production lead just to see one payload, the receiver stores the **raw, unparsed body** every
time. Nothing is ever lost regardless of shape surprises, and the daily summary step -- which is
far easier to iterate on than a live webhook receiver -- does the actual field extraction, with
enough real logged payloads to get it right before it needs to be perfect. `top_level_keys` is
there specifically so the first few real rows are inspectable at a glance without downloading the
full raw JSON.

## Once created

Nothing else to configure. Referenced by `dnc_i04_event_receiver` (write) and
`dnc_i04_daily_summary` (read) once both are built.
