# Archive pass — 2026-09-03

**Rule applied: deactivate, rename with an `ARCHIVE__` prefix, never delete.** Every workflow's exact
pre-change definition is in `backups/`, so both the rename and the deactivation are reversible from
a file.

**12 archived · 0 deleted · 0 KEEP-list workflows touched.**
Estate: 40 workflows, **22 active → 20 active**.

---

## Before → after

| Was | Name before | Archived as | Nodes | Why |
|---|---|---|---:|---|
| off | `smartlead_observability_readonly` | `ARCHIVE__smartlead_observability_readonly` | 18 | Never finished — its campaign id is still the literal placeholder text. Superseded by WF-2S/WF-2R, which poll Smartlead with better claim semantics. |
| off | `WF-1-DO NOT USE` | `ARCHIVE__WF-1-DO NOT USE` | 89 | Previous generation of WF-1. **Webhook path neutralised** — see below. |
| off | `HeyReach — Phase 0 Payload Capture` | `ARCHIVE__HeyReach — Phase 0 Payload Capture` | 3 | Pre-WF-1 scaffolding: acknowledge the webhook, record the payload shape. |
| off | `DNC__NormalizeIdentity__v1` | `ARCHIVE__DNC__NormalizeIdentity__v1` | 2 | Nothing calls it; the same logic is inlined in the registry writer, its read-only twin, and the gate. |
| off | `dnc_gate_queue_drainer` | `ARCHIVE__dnc_gate_queue_drainer` | 6 | The gate no longer queues anything — the queue path was removed on 2026-09-02. |
| off | `dnc_expiry_job` | `ARCHIVE__dnc_expiry_job` | 17 | Deliberately retired when time-based expiry was killed (2026-08-31). |
| off | `dnc_expiry_null_oneshot` | `ARCHIVE__dnc_expiry_null_oneshot` | 5 | One-shot: removed `expires_at` from every registry row on 2026-08-31. |
| off | `dnc_s4_event_populations` | `ARCHIVE__dnc_s4_event_populations` | 24 | One-shot bulk campaign load, run once on 2026-08-14 (148 runs). |
| **ACTIVE** | `dnc_label_reversal` | `ARCHIVE__dnc_label_reversal` | 20 | One-shot repair tool, last used 2026-08-14. |
| **ACTIVE** | `dnc_s3_surfe_backfill` | `ARCHIVE__dnc_s3_surfe_backfill` | 18 | One-shot historical backfill; **never run**, but was ACTIVE with a reachable webhook. |
| off | `dnc_i04_daily_summary` | `ARCHIVE__dnc_i04_daily_summary` | 18 | Retired earlier today — I-04 became a change log (rulebook R-G). |
| off | `dnc_i04_weekly_reconciliation` | `ARCHIVE__dnc_i04_weekly_reconciliation` | 53 | Retired earlier today; never ran once, and its full-estate walk is the out-of-memory shape. |

## Kept, deliberately — not archived

| Workflow | State | Why it stays |
|---|---|---|
| `WF-0 - Discovery` | inactive | Hand-run whenever Pipedrive fields change; it produces the field keys both receivers depend on. Load-bearing despite never appearing in an execution list. |
| `DNC__CheckLedger__v1` | inactive | Superseded but harmless read-only twin. |
| `dnc_check_service` | inactive | Built, never switched on — wanted for Stefan. |
| `dnc_s1_responded_to_dnc` | ACTIVE | Hand-fired capture source, still needed. |
| `dnc_s2_meeting_to_dnc` | ACTIVE | Hand-fired capture source, still needed. |
| `dnc_projections_sweep` | ACTIVE | ACTIVE with zero runs, but it is being fired today. |

## The one structural change: `WF-1-DO NOT USE`

Its webhook path was `hr-test-hrtest0712r2-e89986b7` — still defined, and one reactivation away from
being reachable. It is now **`{{WEBHOOK_ARCHIVED_DO_NOT_USE_2026_09_03}}`**, so the old URL 404s even if somebody
switches the workflow back on.

**The webhook node itself was kept.** Other nodes in that 89-node graph reference it by name;
deleting it would damage an artifact whose whole purpose is to be readable later. Neutralising the
path achieves "cannot be reached" without that cost.

## Safety checks run before anything was written

1. **Reference check** — every one of the 40 workflows was searched for each candidate's id.
   **Zero references.** The script refuses to archive anything another workflow still points at.
2. **Name check** — each candidate's live name had to match exactly, so a rename by the concurrent
   session would have stopped the run rather than archiving the wrong thing.
3. **Backup** — written before any write.
4. **Readback** — every workflow re-read after the write and asserted to be both renamed and
   inactive.
5. **KEEP list** — re-verified present and unchanged afterwards.

## How to bring one back

1. Rename it back (drop the `ARCHIVE__` prefix).
2. For `WF-1-DO NOT USE` only, restore its webhook path from `backups/` if you actually want it
   reachable — think twice.
3. Reactivate.
4. If it is one of the four one-shot tools, read
   [`../ONE_SHOT_TOOLS.md`](../ONE_SHOT_TOOLS.md) first — they all default to dry-run for a reason.

Or restore the whole definition from `backups/<name>__<id>.json` with a PUT to the same id,
stripping `availableInMCP` from `settings` first.

## What this changes about the estate's shape

Before: 22 active workflows, of which **two were ACTIVE with zero runs in 20 days** and one had a
live-but-unused webhook path.
After: **20 active workflows, and every one of them has run in the last 20 days except
`dnc_projections_sweep`** — which is active on purpose, because it is being fired today.

That is the useful property to keep: *if a workflow is active and has not run, either it is about to
be, or it should be archived.*
