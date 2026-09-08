# DNC BUILD — Stage 2 (WF-4) build + 3 real bugs found/fixed in already-deployed code

**Status: DONE. WF-4 deployed inactive. All fixes live-verified.**

## What was asked
Owner: "Stage 2 (WF-4 Sheet intake) — GREEN to build... watch the sheet → normalize → CheckLedger
dedupe → UpsertLedger insert → NO projections yet." Sheet link provided:
https://docs.google.com/spreadsheets/d/10qCtWMwx3e_0YuT9AuSjuF_Q15mOj6EAGO-RTKRl2-o

## What happened
1. Read the sheet (publicly viewable, confirmed via CSV export): header row `linkedin_url, email,
   full_name, reason, added_by, notes`, 0 data rows. Verified n8n's exact `googleSheetsTrigger`
   node parameter shape from n8n source (`Row.resource.ts`-style research) rather than guessing —
   this project has a standing lesson about wrong node-parameter assumptions shipping silently.
2. While tracing what a real UpsertLedger insert would produce for WF-4's rows (to avoid building
   on top of an assumption I hadn't checked), found and fixed **3 real bugs in already-deployed
   production code**, none caused by this session's own recent work:
   - `decide_js`'s reason-merge overlay was gated on the CALLER having a `reason` — meaning any
     reason-less caller (the heyreach tee) touching an already-classified row would silently wipe
     its reason/source_ref/also_flagged/offboard_removable/date_precision/expiry_review_pending.
     Directly threatened the 23,839 rows just seeded. Fixed and live-verified via a two-call probe
     (insert-with-reason, then update-without-reason) confirming full preservation.
   - `owner_tag`/`projections_state` were never wired into `UP_VALUE` at all — UpsertLedger never
     wrote them, confirmed by the fact that the prior verification probe needed a bypass node just
     to prove the columns existed. Fixed: `projections_state` defaults on insert, carried forward
     (not reset) on update — caught a second bug live on the FIRST fix attempt (insert-only guard
     wasn't enough, `merge_v1`'s own record never carries this field forward on update).
   - `heyreach_reply_to_dnc_ledger` and `dnc_check_service`, as actually deployed, still referenced
     their subworkflow calls via an unresolved `REPLACE_<name>_ID` placeholder — would fail
     immediately the moment either was ever triggered. Neither had been (both inactive). Fixed at
     the `exec_wf()` helper level (new `WORKFLOW_IDS` dict, mirrors `TABLE_IDS`) and redeployed
     both in place.
3. Added regression-guard tests for all three to `dnc_contract_tests.js`. 43/43 pass, all suites
   green.
4. Built `dnc_wf4_sheet_intake` (16 nodes) per the exact spec: Google Sheets Trigger (rowAdded) →
   normalize/validate reason → CheckLedger (skip insert only on `result==='on_dnc'`, allowing
   legitimate reactivation for clean_with_history) → UpsertLedger insert → dev-mode Slack summary
   only. Deployed via API, id `bluGflKaUI3bGodQ`, confirmed inactive, round-tripped clean.

Full detail: [DNC_DEPLOYED_WORKFLOW_IDS.md](../DNC_OBS_P1_build/DNC_DEPLOYED_WORKFLOW_IDS.md).

## Judgment calls made without an explicit spec (flagging, not hiding)
- `source` for all WF-4 writes is a fixed tag `'manual_sheet'`, independent of the row's own
  `reason` value — `reason` carries the classification, `source` identifies the intake channel.
- `date_precision='derived'` for all sheet rows (they're live-dated, not backfilled/uncertain).
- `notes` has no registry column — surfaced only in the dev Slack summary, never persisted.
- `pollTimes` (`everyMinute`) was **not** independently verified against n8n source the way every
  other parameter shape in this build was — it's platform-injected for polling triggers, not in
  the node's own properties array. Worth a glance in the n8n UI.

## Next
- WF-4 needs a real `googleSheetsTriggerOAuth2Api` credential (not the same type as the regular
  Sheets node) before it can ever run, plus explicit activation — both still gated on the owner.
- Still owed from the same instruction: Pipedrive person-field creation (probe-first), Smartlead
  email→lead_id resolve for the 987 candidates, HeyReach RemoveFromCampaign re-verification.
