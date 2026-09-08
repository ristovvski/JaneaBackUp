# Auditor: the predicted duplicate forward HAPPENED — plus verification of the relayed wiring fix

Read-only. Swept 2026-08-11T13:54Z. Companion to `2026-08-11_audit-spotcheck2-FINAL-five-green.md`,
where this was flagged as a pending risk ~35 minutes earlier.

## 1. Relayed claims — all three CONFIRMED

**Error-handler wiring, 9/9.** Zero placeholders remain across all 18 workflows. Exactly nine were
rewritten at 13:19:50–13:19:54Z, all now `errorWorkflow = BbrXPABgOaaTJjD6`:
`DNC__CheckLedger__v1` · `DNC__NormalizeIdentity__v1` · `DNC__UpsertLedger__v1` ·
`dnc_check_service` · `dnc_expiry_job` · `dnc_projections_sweep` · `dnc_wf4_sheet_intake` ·
`heyreach_reply_to_dnc_ledger` · `smartlead_observability_readonly`. Count matches the claim exactly.

**`smartlead_observability_readonly` → WF-ERR.** Confirmed.

**Fixture.** Smartlead lead `4306240392` is now `is_unsubscribed: true`. Pipedrive lead `72ec85c0`
remains un-archived (`archive_time: null`, 4 labels) — noted as Nik's to manage, not a finding.
`zz_probe_cred_verify2` is **gone** (19 → 18 workflows). `dnc_projections_sweep` is now **inactive**.

**Regeneration regression check — CLEAN.** This was my specific worry: a generator that rewrites a
workflow can reset its CONFIG safety flags to template defaults. It did not.

```
MODE = "dev"   FIRE_PIPEDRIVE = false   FIRE_SMARTLEAD = false
alert_channel = "C0B8GCVNR5W"   dev_channel_guard = "C0B8GCVNR5W"   -> Send Guard will NOT throw
PD Label Union still reads existing label_ids and pushes (unions, does not overwrite)
```

The `Send Guard` was additionally made configurable (`cfg.dev_channel_guard || 'C0BFE6KAN8J'`) and the
new key matches `alert_channel`, so the channel change is consistent rather than a latent throw.

Unchanged and pre-existing, not regressions: `WF-ERR` itself, `WF-0 - Discovery` and
`HeyReach — Phase 0 Payload Capture` carry no `errorWorkflow`. Two are dormant legacy; WF-ERR's own
missing backstop is the Phase-2 finding, still open.

## 2. THE DUPLICATE FORWARD IS REALISED — Smartlead wire

Fixture lead `4306240392`: **4 replies, 5 forwards.** The extra has no reply of its own:

```
2026-08-11T12:45:47Z  REPLY
2026-08-11T12:46:32Z  FORWARD
2026-08-11T13:09:07Z  REPLY
2026-08-11T13:09:52Z  FORWARD
2026-08-11T13:45:56Z  FORWARD   <-- no reply. duplicate.
```

Two executions fired in the same second and make a controlled demonstration of the exact mechanism:

| exec | started | event ts | `__duplicate` | lead | forward node ran |
|---|---|---|---|---|---|
| **15252** | 13:45:45.223Z | **12:45:47** | **false** | resolved `72ec85c0` | **YES → the 13:45:56Z forward** |
| 15251 | 13:45:45.025Z | 13:09:07 | true | — | no |

Both are `__reconciled: true` WF-2R replays. The 13:09 event was **claimed** at its original run, so its
replay was suppressed — dedupe working. The 12:45:47 event resolved **no lead** at its original run
(exec 15239), so under the new `__no_lead === false` guard it was never claimed; its key was released;
the replay therefore saw `__duplicate: false` and **re-sent the forward**.

`F|…` forward-idempotency keys: **absent** from `wf2_seen` — nothing else gates the forward.

**Impact: one duplicate forward of test content to `rune@janeasystems.com`.** Low harm.

**The bound was luck, not design.** It stopped at two forwards only because the lead became resolvable
between the two runs, so the replay finally claimed. Had the lead stayed archived, every WF-2R sweep
inside the 48 h lookback would have re-forwarded and none would ever have claimed — unbounded.

Recommendation unchanged, now evidence-backed rather than predicted: claim `F|<dedupe_key>` on
`SL Forward Email` `ok:true` and gate `Gate SL Forward Email` on its absence. A replay then retries the
CRM writes it still owes and never re-sends the forward.

## 3. Marine — replay still has not landed

Lead `4214180591` wire is unchanged: `SENT 2026-08-10T15:30:17Z`, `REPLY 15:30:20Z`, **0 forwards**.
Her key is released and her lead `da6fce30` is not archived, so when WF-2R's ring reaches 3686184 the
replay should resolve a lead, forward once, and claim. I will grade it when it appears — that is the
labelled item the EOD is waiting on.

## 4. Sentinel

My five assertions remain **green**. This finding is not one of them, and the harm so far is a single
internal test message. It does strengthen the case for closing the forward gate before the night queue
runs unattended — that window is precisely when a duplicate forward reaches a prospect with nobody
watching — but the call is Nik's, not mine.
