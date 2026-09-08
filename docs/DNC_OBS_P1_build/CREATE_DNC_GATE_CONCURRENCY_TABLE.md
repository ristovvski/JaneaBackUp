# Create the `dnc_gate_concurrency` Data Table

Second incident today (Clay per-row HTTP column fired hundreds of concurrent single-row calls at
`dnc_pre_add_gate`, workers died mid-execution, n8n auto-deactivated the workflow again). This
table backs a self-healing in-flight cap so a burst degrades to fast `429`s instead of taking the
instance down. **In the target n8n project: Data Tables → Create data table**, name it exactly
`dnc_gate_concurrency`, add these 2 columns:

| column | n8n type | notes |
|---|---|---|
| `lock_id` | String | always the literal `"gate"` — one sentinel row, the row key |
| `entries_json` | String | JSON array of `{exec_id, started_at}` for in-flight requests |

## Not blocking

The gate is built to fail OPEN on any error reading/writing this table (missing table included) —
every request just proceeds as "not busy" until it exists. Deploying now is safe; this is the next
hardening step, not a prerequisite. Once created, the cap actually takes effect (max 5 concurrent
requests; anything past that gets an immediate `429` with a "batch your rows into one call"
message instead of piling onto an already-strained instance).
