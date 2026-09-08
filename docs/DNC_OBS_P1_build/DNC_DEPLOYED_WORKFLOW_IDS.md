# DNC Phase-1 + STAGE-1 workflows — deployed to n8n

Imported via `deploy_dnc_workflows.py` (mirrors `WF1_W1.0.1_build/deploy_wf2r.py`'s pattern: create
via `POST /api/v1/workflows`, re-GET, diff jsCode/connections/node-count field-by-field). All 7
round-tripped clean, all created **INACTIVE**. Activation waits on owner's word.

**Redeployed 2026-08-10** (superseding the 2026-08-07 IDs below the line) after the zz_probe_ live
verification caught two real bugs that had shipped since Build 2 without anyone noticing, because
no static test had ever executed a real n8n instance:

1. **`dataTableId` mode `"name"` doesn't resolve when a workflow runs as a subworkflow** (Execute
   Workflow → executeWorkflowTrigger) — only when a workflow runs from its own trigger. UpsertLedger
   and CheckLedger ALWAYS run as subworkflows in production, so this would have broken 100% of real
   traffic. Fixed in `build_dnc.py` via a `TABLE_IDS` dict — any table with a known real id is now
   referenced by `mode:"id"`, never `mode:"name"`.
2. **The `dt_upsert` node never set `filters.conditions`** — n8n's upsert operation throws "At least
   one condition is required" without it; `matchingColumns` alone does not satisfy this. Fixed to
   derive `filters.conditions` from `matching` + `value_map` automatically.
3. (Bonus, unblocking #1's verification) The Slack credential placeholder (`id: "REPLACE_ME"`) is
   pre-execution-checked by n8n across the WHOLE workflow, even branches the run won't take — so it
   blocked every UpsertLedger call, including a plain insert that never touches Slack. Now baked
   into `build_dnc.py` as the real credential (`F9CCCbTx8KB5b2OO`, "Smartlead Slack", confirmed live
   via WF-2H Health & Digest).

Both bugs now have regression-guard static tests (`dnc_contract_tests.js`) so they can't silently
ship again. **76/76 tests pass.**

| Workflow | n8n id | nodes | status |
|---|---|---|---|
| DNC__NormalizeIdentity__v1 | K2M1Z0m1gKX6LdFI | 2 | clean |
| DNC__UpsertLedger__v1 | RolYGL3J2CNg6Yp3 | 11 | clean |
| DNC__CheckLedger__v1 | kv7reJYAAgsOV33t | 5 | clean |
| heyreach_reply_to_dnc_ledger | YgufwSg1EAJaT0ra | 7 | clean |
| dnc_expiry_job | alpy9rsunqnFwQml | 17 | clean |
| smartlead_observability_readonly | XWtxUzBgNJuguJlg | 18 | clean |
| dnc_check_service | PViKUykLaDd7Xze1 | 7 | clean |

`dnc_registry_dev` real table id: `UOgKwlGsL28lX61O` (Personal project `57BsS5BV36DRX0Cw`).

**Functional verification — FINAL, 2026-08-10 (both tables PASS, via direct probe, not the UI):**

- `dnc_registry_dev`: full round-trip (Webhook → Build Payload → **UpsertLedger** → direct-set 4
  cols → **CheckLedger** → Diff → delete → Respond) confirmed all **23/23 columns** present and
  round-trip correct via CheckLedger read-back. Delete was independently confirmed to actually
  remove the row (separate get-probe found 0 matching rows afterward, and a `lastNode`-mode probe
  returned n8n's own "No item to return was found" — the strongest available proof of zero rows).
  Probe workflow deleted, no residual rows left.
- `dnc_domain_block_dev`: write-probe schema-diff confirmed all **7/7 columns** valid in one round
  (`added_at, correlation_id, domain, removed_at, removed_reason, source, status`). No residual
  rows (probe uses a non-matching filter, so the update is a no-op by design).

**Bug found + fixed during this verification pass:** the probe's delete node used
`"operation": "delete"`, but n8n's Data Table node's actual parameter value for that operation is
`"deleteRows"` (confirmed from n8n source — `Row.resource.ts` registers it as
`deleteRows.FIELD = 'deleteRows'`; `"delete"` isn't a recognized value, hence the generic
"Cannot read properties of undefined (reading 'execute')" crash). This only affected the
throwaway `zz_probe_build_and_run.py` script — no production workflow in `build_dnc.py` performs a
delete operation, so no regression-guard test was needed in `dnc_contract_tests.js`.

`CLICKLIST_FOR_NIK_2026-08-07.md` is now fully resolved — no remaining column gaps on either table.

## 2026-08-11 — Stage 2 (WF-4) build + two more real bugs found and fixed in-place

Building WF-4 required tracing exactly what a live UpsertLedger insert would write, which surfaced
two more real, previously-undiscovered gaps in already-deployed code (neither had caused visible
damage yet only because every affected workflow has stayed inactive per the standing policy):

1. **`decide_js`'s reason-merge overlay was gated on `ctx.incoming.reason`** — a reason-less caller
   (e.g. the heyreach tee) touching a row that already had `reason` set would silently write
   `undefined` for reason/source_ref/also_flagged/offboard_removable/date_precision/
   expiry_review_pending, WIPING the classification on the very next live event to touch any of
   the 23,839 just-seeded rows. Fixed: the overlay now always runs when `d.record` exists;
   `reasonMergeV1(existingSignal, null)` already correctly preserves the existing signal (that path
   was simply never being reached). Live-verified via `zz_probe_reason_preservation.py`: insert
   with `reason=manual_offboard_eligible` → second call with NO reason (simulating heyreach) →
   reason/source_ref/owner_tag/offboard_removable/date_precision/expiry_review_pending/
   projections_state all confirmed preserved, `source` correctly appended, `entry_type` never
   downgraded.
2. **`owner_tag` and `projections_state` were never wired into `UP_VALUE`** at all — confirmed by
   the fact that the 2026-08-10 functional-verification probe needed a "Direct-set remaining 4
   cols" bypass node just to prove the *columns* existed; UpsertLedger itself never wrote them.
   Fixed: `projections_state` now defaults to `{pipedrive:pending,smartlead:pending,heyreach:
   pending}` on a true insert, and is carried forward unchanged from the primary row on any
   update (never reset — `merge_v1`'s own merged-record object doesn't carry this field, so an
   insert-only guard alone was insufficient, caught by the live probe on the first attempt).
   `owner_tag` is recomputed from the final merged `reason` on every write, `null` unless
   `reason === 'manual_offboard_eligible'`.
3. **Bonus, found while building WF-4's own subworkflow calls**: `heyreach_reply_to_dnc_ledger` and
   `dnc_check_service`, as actually deployed, still referenced `DNC__UpsertLedger__v1`/
   `DNC__CheckLedger__v1` via the literal unresolved placeholder `mode:"list"` +
   `value:"REPLACE_<name>_ID"` — never substituted after the 2026-08-10 redeploy. Both would have
   failed immediately with "workflow not found" the moment either was ever triggered; neither had
   been (both confirmed `active:false`). Fixed at the `exec_wf()` helper level via a new
   `WORKFLOW_IDS` dict (mirrors `TABLE_IDS`) — every known-deployed subworkflow is now referenced
   by `mode:"id"`, and both live workflows were redeployed in place with the corrected reference.

All three now have regression-guard tests in `dnc_contract_tests.js`. **43/43 subworkflow-suite
tests pass, all suites green (`node run_all_tests.js`).**

| Workflow | n8n id | nodes | status |
|---|---|---|---|
| dnc_wf4_sheet_intake | bluGflKaUI3bGodQ | 16 | clean, **inactive**, needs a real `googleSheetsTriggerOAuth2Api` credential before it can ever run |

`dnc_wf4_sheet_intake`: watches https://docs.google.com/spreadsheets/d/10qCtWMwx3e_0YuT9AuSjuF_Q15mOj6EAGO-RTKRl2-o
(tab "Sheet1", gid=0; header row `linkedin_url, email, full_name, reason, added_by, notes`,
confirmed via public CSV export, 0 data rows at build time) → normalize + validate `reason` domain
(unrecognized/blank → `manual_sheet`) → **CheckLedger** dedupe (skip only if `result==='on_dnc'`;
`clean`/`clean_with_history` proceed, allowing legitimate reactivation) → **UpsertLedger** insert
(`source='manual_sheet'` fixed tag, `date_precision='derived'` since sheet rows are live-dated, not
backfilled) → dev-mode Slack summary only, **no projections fired**. `notes` has no registry column
so it's surfaced only in the dev summary, never persisted. Round-tripped clean (16/16 nodes match).

**Still needed before this can ever run**: a real n8n credential of type
`googleSheetsTriggerOAuth2Api` (NOT the same credential type as the regular Google Sheets
read/write node) bound to the trigger node, replacing the `REPLACE_ME` placeholder — and the
workflow must be explicitly activated, per the standing policy, only on the owner's word.
`pollTimes` was set to `everyMinute` as a reasonable default; unlike every other node in this file,
this specific parameter shape was **not** independently verified against n8n source (it's injected
by the platform for polling-type triggers, not in the node's own `properties` array) — worth a
glance in the n8n UI before relying on it.

---
### Superseded 2026-08-07 ids (deleted, do not use)
DNC__NormalizeIdentity__v1=sjaplWXbbCADQ14O · DNC__UpsertLedger__v1=gD9aBaNjwslZMD0S ·
DNC__CheckLedger__v1=EVjVAYIGPeRQbWx5 · heyreach_reply_to_dnc_ledger=oBdAvYkZPasRAdSS ·
dnc_expiry_job=PTgZQFFsFVunC8Mp · smartlead_observability_readonly=eBzMD5f2bkm972HT ·
dnc_check_service=FKFpKNUE6sanWnc3

Not yet imported into n8n: `dnc_pull_pipedrive_persons.py` / `dnc_resolve_people_dnc.py` (those are
standalone Python scripts, not n8n workflows — no import needed, they run via the scheduled task).
