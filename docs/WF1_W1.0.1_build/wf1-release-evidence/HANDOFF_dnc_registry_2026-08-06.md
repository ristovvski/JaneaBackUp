# Handoff to the dnc_registry_dev owner session ("Zapier MCP access")

Not written by this session — no confirmed API path to Data Tables on this n8n instance, and this
table is mid-migration under active ownership elsewhere. Per the stated rule: cross-session writes
to one table from two owners is how registries fork. Three items, relayed verbatim from Nik via the
user in this session:

## 1. Alias pairs — CONFIRMED, activate
- `"Jim"` = `"Jim Ash"`
- `"Mario"` = `"Mario Stalder"`
Flip status: unconfirmed → confirmed, in the alias table (canonical_ref → [variants]). Offboard
resolution through aliases is unblocked once these are live.

## 2. Amsterdam-142 — UNFREEZE
The frozen-TTL flag comes off this batch. They seed as expired-per-TTL; the normal expiry sweep
should treat them as any other expired row from here on: contactable again, projections removed
(label off / unblock) when the sweep runs. **Registry rows stay as history (status=expired) —
nothing deleted.** This directly concerns the `expiry_review_pending` guard your session was
building specifically to prevent the 06:00 sweep from touching these 142 rows — Nik's decision is
that the guard should no longer apply to this batch; whatever state currently protects them should
be lifted so the normal lifecycle resumes.

## 3. New DNC row — pii-f59eb465@example.invalid
From the London Sales Sprint 2026 backfill (this session, 2026-08-06):
```
add: pii-f59eb465@example.invalid
reason: reply_dnc (negative sentiment reply, Smartlead category "Not Interested")
entry_type: negative_reply  (per your reason_to_entry_type_mapping)
TTL: 6 months from add_time
source_ref: london_backfill_2026-08-06
```
Full context: `DISCOVERY/london_backfill_dryrun_v2_output.json` (row with
`treatment: not_interested_labeled_no_forward_dnc_flagged`).

---
*Written by the DNC/Melisa-sprint-reconciliation session, 2026-08-06. No table writes attempted.*
