# 2026-09-02 — n8n estate documentation (Stages 1–4)

**Task:** READ-ONLY inspection of the live n8n instance; produce an inventory, per-workflow detail,
four domain docs and a slide outline, as source material for a presentation and the documentation.
Explicit constraint: read live workflow definitions from n8n, do not rely on chat history, task
logs or memory.

**Access used:** `GET /api/v1/workflows` (36 workflows, full definitions incl. nodes/connections)
and `GET /api/v1/executions` (per-workflow walk, up to 12 pages of 250 each). No writes, no
activations, no deploys. `GET /api/v1/data-tables` → 404 (not exposed), `GET /api/v1/projects` → 403.

**Output:** `SYSTEM_DOCS_2026-09-02/` — README + 7 documents.

---

## DONE

- **Stage 1** — inventory of all 36 workflows (21 active / 15 inactive, 1,090 nodes): name, id,
  state, node count, trigger type, last execution, run count, one-line purpose. Delivered first,
  as asked. Includes dead-looking / duplicate / unexplained flags and 12 named questions.
- **Stage 2** — per-workflow detail in two files (receivers+reconcilers; DNC+ops). All 21 active
  plus UpsertLedger, CheckLedger, NormalizeIdentity, the gate drainer, expiry, S4 populations,
  I-04 weekly, and the remaining inactive tools. Eight headings each as specified.
- **Stage 3** — four domain docs: HeyReach→PD+DNC, Smartlead→PD+DNC, the DNC registry, and n8n
  conventions + 22 traps (15 linter rules read out of the deployed Code node, plus B16–B22).
- **Stage 4** — 23-slide outline, ~39 min, with timings, speaker notes, cut list and two handouts.

### Findings that were not previously written down anywhere I read

1. **`dnc_projections_sweep`: 0 executions in retention AND `FIRE_PIPEDRIVE`/`FIRE_SMARTLEAD` both
   `false`.** The DNC registry has no automatic outward effect on Pipedrive, Smartlead or HeyReach.
2. **The gate's over-50-row path is a dead end** — enqueues into `dnc_gate_queue`, drainer is
   inactive and has never run, and the monitor's own code says the table does not exist. Callers
   get `{"queued": N}` and never an answer. Nothing alerts.
3. **Only `FIRE_S3` is true**; S1, S2, S4, S3-backfill and label-reversal are all dry-run.
4. **WF-1 selects the lead two different ways on the reply path** — `M7 Build` matches on the lead
   Campaign field, `M7 Labels Compute` takes the newest non-archived lead. Possible mismatch
   between where the activity lands and where the labels land.
5. **Retention horizon measured, not assumed:** oldest execution anywhere = 2026-08-14T01:15Z
   (~19 days), consistent across all high-volume workflows.
6. **Linter rules are R01–R14 + R16; R15 does not exist** in the deployed code or the repo copy,
   while `RULEBOOK.md` claims 16 rules.
7. **WF-1 is the only workflow still carrying `settings.timeSavedMode`** — the key the public PUT
   API rejects.
8. **`smartlead_observability_readonly` still holds the literal placeholder**
   `campaign_id: "REPLACE_WITH_AI4_CAMPAIGN_ID"`.
9. **WF-2 ran 130× vs 1,845× for each reconciler** — nearly all Smartlead traffic is replay.
10. **`dnc_i04_daily_summary` has 5 errored executions**, latest 2026-08-31T05:30, on the daily
    trigger itself (not the idle-guard).

---

## PARTIAL

- **Data-table existence and contents were not verifiable.** The n8n public API returns 404 for
  data tables. Every claim about `dnc_gate_queue` not existing rests on a code comment in
  `dnc_pre_add_gate_monitor` dated 2026-08-31, plus the drainer's zero executions. Flagged for UI
  confirmation in three places.
- **The 5 `dnc_i04_daily_summary` failures were counted but not opened.** I have the timestamps and
  execution ids in `exec_summary.json`; I did not fetch `?includeData=true` for each.
- **Execution counts for `dnc_pre_add_gate` and `DNC__UpsertLedger__v1` hit the 12-page cap** and
  are reported as `3000+` rather than exact.
- **Slack channel names** are taken from code comments (`#lead-processing`, `#gtm-telemetry`,
  `#alerts`); I did not query Slack to confirm the id→name mapping for `C0BTP6VHP1B` and
  `C0BFE6KAN8J`.

## BLOCKED

- Nothing blocked the deliverables. The two API 404/403s (data-tables, projects) narrowed evidence
  but did not stop any stage.

## IMPROVABLE

- **The WF-1 lead-selection discrepancy (finding 4) deserves a targeted check** against a real
  execution where a person has leads in two campaigns. That is a read-only query and would either
  confirm a live defect or close the question.
- **A pattern sweep for the same discrepancy** (`selectLead` implemented twice with different rules
  inside one workflow) would fit as a linter rule — this is exactly the R-E "class not instance"
  discipline.
- **The four copies of the identity normaliser** (sub-workflow + inlined in UpsertLedger,
  CheckLedger, the gate) and the byte-identical `Classify Batch` in gate/drainer are drift waiting
  to happen; a build-time embed like `build_rules.py` already does for `AR Decide` would fix it.
- **`WF-1-DO NOT USE` still has a reachable webhook path.** Renaming is doing all the safety work.

## Working files (scratchpad, not in the project)

`workflows_raw.json`, `execs_raw.json`, `exec_summary.json`, `digest.txt`, `code/` (539 extracted
Code/Set/HTTP/Switch node payloads), and the four fetch scripts.
