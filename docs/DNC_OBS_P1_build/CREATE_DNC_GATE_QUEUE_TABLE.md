# Create the `dnc_gate_queue` Data Table

Blocking for gate v3 (hybrid queue mode) to actually function — no verified API for Data Table
creation exists on this instance (checked again live just now: `POST /api/v1/data-tables` → 404),
same situation as every other table in this project. UI is the only path.

Also serves as the **crash-safe ingress log** (auditor's P1 fix, 2026-08-26): every submitted
identity is written here the moment it's normalized, before any lookup/classification happens —
so a crash mid-request still leaves an enumerable record of exactly who was in that request. One
table, two jobs (queue storage + ingress durability), not two tables.

**In the target n8n project: Data Tables → Create data table**, name it exactly `dnc_gate_queue`,
add these columns:

| column | n8n type | notes |
|---|---|---|
| `row_key` | String | the row's `identity_key` (email/LinkedIn-normalized) — row key, upsert matches on this |
| `batch_id` | String | the execution id that submitted this row |
| `status` | String | `"received"` (logged at ingress) → `"pending"` (queued, not yet drained) → `"done"` (classified, sync or drained) |
| `payload_json` | String | the normalized row (email, linkedin_url, label, li_key, em_key, norm, row_index) |
| `submitted_at` | Date | when the row was first logged |
| `result_json` | String | `{gate_result, reason, registry_row_ref, identity_key}` once done |
| `completed_at` | Date | when `result_json` was written |

## Once created

Share this table's URL from the Data Tables UI (same as `i04_log`) and I'll switch
`GATE_QUEUE_TABLE`/`GATE_QUEUE_TABLE_NAME` in `build_dnc.py` from `mode:"name"` to the real id —
`mode:"name"` has failed twice in one day on this instance and needs the same by-id fix before
anything writes to it for real. Until that's done: ingress logging, queue enqueue, and retrieval
all fail open or fail clean (verified live) — no crash, but also no actual durability yet.
