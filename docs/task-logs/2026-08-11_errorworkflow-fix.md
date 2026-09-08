# DNC BUILD — errorWorkflow placeholder fix (found by the fix-owner/"Дежурный" session)

**Status: DONE. All 9 workflows fixed, tested, redeployed.**

## What was found
The fix-owner session audited error-handler wiring project-wide and found: 6 of my DNC workflows
carried the literal, never-substituted placeholder `settings.errorWorkflow =
"REPLACE_CORE__ErrorHandler_ID"` (`dnc_projections_sweep`, `smartlead_observability_readonly`,
`dnc_wf4_sheet_intake`, `dnc_check_service`, `heyreach_reply_to_dnc_ledger`, `dnc_expiry_job`), and
3 more had no `errorWorkflow` at all (`DNC__UpsertLedger__v1`, `DNC__CheckLedger__v1`,
`DNC__NormalizeIdentity__v1`). Same class of bug as every other never-substituted `REPLACE_`
placeholder found this build (Slack credential, subworkflow ids, auth mode) — all 9 workflows were
inactive so nothing had silently failed yet, but the moment any is ever activated, its failures
would produce no error-workflow notification at all.

They asked for explicit permission before touching my objects and offered to either do it
themselves (with read-back verification) or hand me the fix. Verified their finding against my own
local generated JSON first (`grep` confirmed the exact same 6+3 split) before acting.

## What happened
Fixed at the source rather than patching the 6 live deployments ad-hoc: `wf()` in `build_dnc.py`
(the one helper every workflow/subworkflow is built through) now sets
`settings.errorWorkflow = CORE_ERROR_HANDLER_ID` (`BbrXPABgOaaTJjD6`, the confirmed active WF-ERR
handler) by construction — this automatically covers the 3 subworkflows that never had the field
at all, not just the 6 with the bad placeholder. Removed the 6 now-redundant/wrong per-workflow
override lines. Added a regression-guard test that checks all 9 workflows explicitly (no
`REPLACE_` prefix, exact match on the real handler id). 52/52 tests pass. Redeployed all 9 via
settings-only PUTs (same `put_body`-style allowed-keys filtering used throughout this build),
confirmed via read-back on every one, all still inactive.

## Next
None — this was purely settings hygiene ahead of eventual activation. Answered their one open
question (should `smartlead_observability_readonly` point elsewhere) — no, WF-ERR uniformly for
all 9 is correct, no reason for a different handler on that one specifically.
