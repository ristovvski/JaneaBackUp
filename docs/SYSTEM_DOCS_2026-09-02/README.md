# System documentation — read live from n8n, 2026-09-02

> **⚠ SUPERSEDED IN PART — 2026-09-03: the I-04 simplification.**
> `dnc_i04_daily_summary` and `dnc_i04_weekly_reconciliation` were retired (deactivated and
> preserved). `dnc_i04_event_receiver` stays as a silent change log, and a new
> `dnc_i04_event_log_prune` keeps 90 days. The morning digest no longer reports I-04 status; it
> reports `CRM change log N events`. Tables `i04_snapshots` and `i04_walk_staging` are now orphaned
> and are referenced by name — do not build on them.
> Detail: [`I04_SIMPLIFY_2026-09-03/REPORT.md`](../I04_SIMPLIFY_2026-09-03/REPORT.md) · rule R-G in `RULEBOOK.md`.



Source of truth for everything in this folder: the live workflow definitions and execution log of
`https://janea-systems-2025.app.n8n.cloud`, read read-only via `GET /api/v1/workflows` and
`GET /api/v1/executions` on 2026-09-02 (~07:00Z). No writes, no deploys, no activations.
Chat history, task logs and prior notes were not used as sources; where a statement comes from the
project rulebook rather than from n8n, the document says so.

| File | What it is | Who it's for |
|---|---|---|
| [00_STAGE1_INVENTORY.md](00_STAGE1_INVENTORY.md) | All 36 workflows: state, nodes, trigger, last run, one-line purpose. Flags: dead-looking, duplicates, and 12 open questions. | you, building the deck |
| [01_STAGE2_RECEIVERS_AND_RECONCILERS.md](01_STAGE2_RECEIVERS_AND_RECONCILERS.md) | Per-workflow detail: WF-1, WF-2, WF-2S, WF-2R, WF-2H, WF-ERR | whoever maintains the bridges |
| [02_STAGE2_DNC_AND_OPS.md](02_STAGE2_DNC_AND_OPS.md) | Per-workflow detail: the gate, the ledger, S1–S4, projections, escalation, I-04, digest, linter | whoever maintains the DNC side |
| [10_DOMAIN_heyreach_to_pipedrive_and_dnc.md](10_DOMAIN_heyreach_to_pipedrive_and_dnc.md) | Domain 1 — LinkedIn → CRM | a new operator |
| [11_DOMAIN_smartlead_to_pipedrive_and_dnc.md](11_DOMAIN_smartlead_to_pipedrive_and_dnc.md) | Domain 2 — cold email → CRM | a new operator |
| [12_DOMAIN_dnc_registry.md](12_DOMAIN_dnc_registry.md) | Domain 3 — the do-not-contact record | a new operator |
| [13_DOMAIN_n8n_conventions_and_traps.md](13_DOMAIN_n8n_conventions_and_traps.md) | Domain 4 — conventions and the 22 traps we have paid for | whoever changes a workflow next |
| [20_SLIDE_OUTLINE.md](20_SLIDE_OUTLINE.md) | 23 slides, ~39 minutes, for Melisa / Sergey / Stefan | you, presenting |

## The three things to read first

1. **The do-not-contact record has no automatic effect on the sending tools right now.** The
   projector has zero executions in the retention window and both of its write switches are off.
   → `12_DOMAIN_dnc_registry.md` §6.
2. **The gate silently swallows batches over 50 rows.** Keep batches at or under 50.
   → `02_STAGE2_DNC_AND_OPS.md`, first section.
3. **Almost all cold-email traffic arrives by catch-up replay, not by live webhook** (130 live runs
   vs 1,845 reconciler cycles in 19 days), and a lost bounce or unsubscribe is not recovered by
   anything. → `11_DOMAIN_smartlead_to_pipedrive_and_dnc.md` §6.

## Caveats on the evidence

- **Execution history is a rolling ~19-day window** — the oldest execution retained anywhere is
  2026-08-14T01:15Z. "No executions" means "not since 14 Aug", never "never ran".
- **n8n's public API does not expose data tables**, so no statement about a table's existence or
  contents could be verified directly. Where a claim about a table comes from a code comment, the
  document says so and asks for UI confirmation.
- Two execution counts hit the paging cap (`dnc_pre_add_gate`, `DNC__UpsertLedger__v1`); both are
  reported as `3000+`.
