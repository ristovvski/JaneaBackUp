# Presentation source material — read live from n8n, 2026-09-03

Everything here was read from the live n8n API on 2026-09-03 (08:20Z–10:25Z), including the code
inside all 944 nodes. Chat history, task logs and earlier reports were not used as sources; where a
statement comes from the project rulebook rather than the code, the document says so.

**Audience for the output:** Melisa (GTM lead), Sergey (sales/strategy), Stefan (external consultant,
no Pipedrive access).

| Stage | File | What it is |
|---|---|---|
| 1 | [STAGE1_INVENTORY.md](STAGE1_INVENTORY.md) | every workflow: state, nodes, trigger, last run, one-line purpose · flags · 10 questions · §E concurrency · §F the I-04 change · §G the archive pass |
| 2A | [STAGE2A_RECEIVERS_AND_RECONCILERS.md](STAGE2A_RECEIVERS_AND_RECONCILERS.md) | per-workflow detail: the two bridges, the three catch-up jobs, the error handler |
| 2B | [STAGE2B_DNC_AND_OPS.md](STAGE2B_DNC_AND_OPS.md) | per-workflow detail: the gate, the registry writer, the capture sources, the projector, the ops jobs |
| 3.1 | [STAGE3_DOC1_heyreach.md](STAGE3_DOC1_heyreach.md) | LinkedIn → CRM + DNC, end to end |
| 3.2 | [STAGE3_DOC2_smartlead.md](STAGE3_DOC2_smartlead.md) | cold email → CRM + DNC, end to end |
| 3.3 | [STAGE3_DOC3_dnc_registry.md](STAGE3_DOC3_dnc_registry.md) | the do-not-contact list: definition, capture, gate, projections, measurements |
| 3.4 | [STAGE3_DOC4_conventions_and_traps.md](STAGE3_DOC4_conventions_and_traps.md) | conventions, and all 24 traps with the incident that bought each |
| 4 | [STAGE4_LEAD_JOURNEY.md](STAGE4_LEAD_JOURNEY.md) | **the spine of the deck** — one person's journey, one path per provider |
| 5 | [STAGE5_SLIDE_OUTLINE.md](STAGE5_SLIDE_OUTLINE.md) | 24 slides, ~39 min, with speaker notes, cut list and two handouts |

## Related, from the same day

- [`../I04_SIMPLIFY_2026-09-03/REPORT.md`](../I04_SIMPLIFY_2026-09-03/REPORT.md) — I-04 became a change log
- [`../ARCHIVE_2026-09-03/REPORT.md`](../ARCHIVE_2026-09-03/REPORT.md) — 12 workflows archived, 0 deleted
- [`../ONE_SHOT_TOOLS.md`](../ONE_SHOT_TOOLS.md) — the four hand-fired tools, with delete-after dates
- [`../RULEBOOK.md`](../RULEBOOK.md) — standing rules, each with the incident that bought it

## The five numbers to carry into the room

| | |
|---|---|
| Estate | **40 workflows, 20 active, 944 nodes** — every active one has run in the last 20 days except the projector, which is being fired today |
| Cold email | **130 live events vs 1,899 catch-up cycles** in 20 days |
| Do-not-contact list | **25,653 rows**, of which **88% have neither an email nor a CRM record** |
| Exposure being closed today | **62%** of the list's email-bearing rows were still contactable — about **1,000 people** |
| CRM change log | **215 events/day**, ~62 MB at 90 days, prune a no-op until **24 Nov** |

## Caveats on the evidence

- **Execution history is a rolling ~20 days** — the oldest execution retained anywhere is
  2026-08-14 13:30Z. "Never" means "not since 14 August".
- **n8n's public API does not expose data tables**, so table contents were measured by running
  read-only workflows, not by querying directly. Each was deleted afterwards.
- **A concurrent session was editing WF-1 throughout.** Every movement is logged in Stage 1 §E; the
  last check at 10:25Z showed no movement since 09:09Z.
