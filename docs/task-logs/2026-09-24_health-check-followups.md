# Health-check follow-ups (5 items) — 2026-09-24

## 1. Supabase drift — DONE except one held data write

**The premise was off in two places.**
- Not a treadmill of healed rows re-drifting: the same ~418 rows had **never** healed. Every night
  since 09-16 the first 500-row upsert chunk contained 82 rows with null `correlation_id` +
  `date_precision` (both NOT NULL in Supabase); PostgREST array inserts are atomic, so the whole
  chunk was rejected while the Slack alert said "healed by upsert". Only the small tail chunk on
  >500 nights ever landed. 09-23 and 09-24 healed **zero**.
- S2 and S3-persons are **not** direct writers — both go through UpsertLedger, which enqueues. A
  scan of all 47 live workflows found the only *active* bypasses: `dnc_projections_sweep` (PD Mark
  Done, PD Mark Write Error, SL Mark Done) and `dnc_s4_retirement_removal` (Update Row).
  `dnc_expiry_job` is archived/inactive live.

**The "996 errors"**: not the reconcile. Its 26 paginated reads are all 2xx (0 error items, both
tables, two nights checked); it makes one failing upsert a day. The source is the delta pusher:
82 permanently stuck claims × 12 cycles/hour (984/h now), all rejected on the same NOT NULL.

**Root cause of the 82**: `dnc_archived_responders_import` is the only UpsertLedger caller that
passes rows through without setting `correlation_id`/`date_precision` (executions 56877 @13:54,
57306–57390 @15:28–15:29 on 09-15). Every S1–S4/WF-4 caller sets both.

Deployed (all via `safe_patch_workflow`, dry-run first):
- `dnc_projections_sweep`: 3 enqueue nodes after the registry writers, keyed on the id of the row
  the update returned. Live CONFIG kept byte-identical (`FIRE_PIPEDRIVE` stays true).
- `dnc_s4_retirement_removal`: enqueue after Update Row. **The generator was stale** — live had an
  out-of-band 09-11 edit (caller-supplied `removed_reason`); backported into `build_dnc.py` first
  so the deploy didn't revert it. This also corrects my 09-17 report: the Martinez/Spence tombstones
  *did* go through this workflow.
- `dnc_archived_responders_import`: defaults `correlation_id`/`date_precision`.
- `dnc_expiry_job` generator only (live archived): enqueue added so a redeploy can't regress.
- `dnc_supabase_nightly_reconcile`: rows violating a Supabase NOT NULL are set aside and named;
  upsert outcome is tallied and reported (healed / FAILED / unhealable); drifted rows are named and
  grouped by changed-column signature (points at the writer). Chain kept strictly linear.
- Static guard: every registry write in every generated workflow must feed a
  `supabase_delta_registry` enqueue (`dnc_contract_tests.js`, 112/112). Reconcile logic 31/31.

Verified: manual reconcile run 68619 healed 417, failed 0, unhealable 82 (alert names them).
Independent re-pull + re-diff: all 25,864 Supabase rows match n8n; remaining drift = exactly the 82.
Sweep enqueue nodes are deployed but **not yet exercised live** (Mark Done fires ~1 run in 40).

**HELD for Nik's word**: `SUPABASE_PROJECTION_build/zz_fire_backfill_unhealable_82.py`
(`CLEARED_TO_FIRE = False`) sets `correlation_id` + `date_precision` on the 82 rows, conditioned on
correlation_id still being empty. That unsticks the 82 pusher claims (ends ~984 errors/hour) and
empties the reconcile's unhealable list. Plan: `audit_out/unhealable_82_backfill_plan.json`.

## 2. Digest — DONE (first live proof: tomorrow 04:00)
- INTEGRITY n/a: `PD Campaign Leads` ran once on PD Volume's accumulator item (no `campaign_name`)
  → Pipedrive 400 `querystring must have required property 'term'`; Integrity zipped 1 response vs 2
  campaigns. New `Integrity Campaigns` node emits one item per campaign (term = campaign id, tested
  equal to name search: 9/9 and 15/15 leads).
- no-match n/a: `conversations.history` → `missing_scope` (token has only `chat:write`). Scope
  change needs a Slack-admin reinstall, so the line and its two nodes were dropped.
- Replay against this morning's real data: INTEGRITY `3917998:0 3917997:0`, zero n/a lines.

## 3. Org guard — no gap
The six numbers are **n8n execution ids**, not org ids (hence Pipedrive 404). Those executions
created orgs 22629–22634; none holds linkedin.com in `website` (5 empty, Zlick Labs = zlick.co with
LinkedIn correctly in the LinkedIn fields). The guard is in the live Org Create body (09-22 16:35).
Noted, not fixed: 5 other orgs from the same pre-guard window still carry a linkedin.com website —
22615 Sironax, 22621 RNA NanoBiotics, 22622 Sunthetics, 22624 Partnology, 22626 Enrich Biosystems.

## 4. Linter — DONE
String/template/regex-aware comment stripper in `lint_rules.js` (the single embedded source), used
by every rule entry point incl. the standalone rules. Estate-wide before/after: exactly the 3
reported false positives removed (`node_reference_resolves`: WF-ICP-Score Dedupe, Dedupe B,
BuildErrorContext — all `$('Name')`/`$('X')` inside comments) + 1 on the linter's own node; nothing
new surfaced. 60/60 linter statics, all self-tests pass. Live `dnc_wf_linter` patched (Lint node
only), its 207 remembered findings preserved.

## 5. CA bundle — DONE; WF-ICP-Score — already resolved
- Root cause: Avast Web/Mail Shield intercepts TLS and re-signs every host with its own root; the
  root changed after the bundle was exported (07 Aug). Fresh export (174 certs) verifies n8n,
  Supabase, Pipedrive. Old bundle kept as `win_ca_bundle.pem.stale-2026-08-07`.
- Both shared helpers now self-heal: `load_env.ps1` (PowerShell) and the existing user-site
  `usercustomize.py` hook (every Python process under the project — the path Python-only sessions
  actually take). Same rule in both: stale = Windows trusts a cert the bundle lacks; heal = append
  the missing ones and warn once. Union writes mean the two converge. Proven by restoring the
  07-Aug bundle: Python healed once (11 certs), then both silent, all three hosts verify.
  Backups: `usercustomize.py.bak-2026-09-24`, `win_ca_bundle.pem.stale-2026-08-07`.
- WF-ICP-Score: `Append audit row` was already removed in the 09-22 edit; last `icp_audit` failure
  09-17 12:19 (6 in retention, not 16/week). The 09-22 errors are a dev-session burst of malformed
  Clay callbacks rejected by `FailLoudly`; none since.
