# One-shot tool workflows — deactivated, safe to delete

Throwaway n8n workflows created for a single migration/probe. They are **deactivated, not deleted**,
so the run that used them stays auditable. They accumulate silently otherwise — `zz_probe_verify_ttl_null2`
sat ACTIVE for weeks before the auditor caught it, which is why this list exists.

**Rule:** anything added here is deleted deliberately on or after its stated date, by a human, after
confirming its queue is empty and no executions are pending (the orphan protocol). Nothing on this
list should ever be re-activated.

| id | name | created | purpose | state | safe to delete after |
|---|---|---|---|---|---|
| `8rzE33eH6OjoB9q6` | `zz_migrate_wf1_alert_registry` | 2026-09-03 | one-shot: wrote the 53 `wf1_alert` rows into claims table `euyostwJYfJefItC` (no dataTable REST exists, so the write had to run inside n8n) | **deactivated** | 2026-10-01 — keep until the ported gate is wire-proven and the staticData rollback copy is dropped |
| `yBqfnnmGj9MEnSvG` | `zz_verify_wf1_alert_registry` | 2026-09-03 | one-shot: per-key verification of the same migration (53 asked / 53 found / 0 missing) — proved the "50 rows" read-back was a page cap, not a loss | **deactivated** | 2026-10-01 — same window as above |
| `H3p3w1S2mvg4qmiu` | `zz_probe_verify_ttl_null2` | ~2026-08 | TTL-null probe from the DNC workstream; flagged ACTIVE by the auditor on 2026-08-18 | **owned by the DNC session** — confirm deactivated before deleting | on the DNC session's word |

## Why they are not deleted immediately

Two of the three are the only record of *how* a migration was performed. The artifacts
(`alert_registry_migration.json`) say what was written; the workflow says how. Until the ported gate
is proven on a live multi-event second, that pair is the rollback story, not clutter.

## Adding to this list

Any workflow named `zz_*` must land here the day it is created, with its delete-after date set at
creation. A one-shot tool with no expiry is an orphan that has not been noticed yet.
