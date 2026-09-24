# Supabase nightly reconcile — 469 "healed" rows investigation (READ-ONLY)

Status: **done** (investigation only, no changes made, per instruction).

## Headline correction: nothing was actually healed

The premise "nightly reconcile healed 469 drifted rows" is **false**. The reconcile's own Slack
alert unconditionally says `"healed by upsert"` whenever `drifted_count > 0` — it never checks
whether the write actually succeeded. It didn't.

`Upsert Corrections Registry` (the node that writes healed rows back to Supabase) failed
**completely**, for the **last two consecutive nights**:

| Reconcile run | drifted_count | Upsert result |
|---|---|---|
| 2026-09-15 06:20 (exec 55942) | 0 | clean, no drift |
| 2026-09-16 06:20 (exec 58347) | 453 | **FAILED — 0 rows written** |
| 2026-09-17 06:20 (exec 60082) | 469 | **FAILED — 0 rows written** |

**Root cause**: 469 drifted rows get POSTed to Supabase as ONE array-insert (chunk size 500, 469 <
500 → single chunk). Postgres/PostgREST array-inserts are atomic — one invalid row fails the
*entire* batch. 86 of the 469 rows have `correlation_id: null`, and Supabase's `dnc_registry` table
has a `NOT NULL` constraint on that column:

```
NodeApiError: null value in column "correlation_id" of relation "dnc_registry" violates not-null constraint
```

This has never been visible because **the error output is wired to a dead end** (`upsert_name:
{"main": [[], []]}` in `build_supabase_sync.py`) — no Slack alert, no meta-log entry, nothing.
The nightly Slack message and the `dnc_registry_meta` row both get written unconditionally
downstream of `Diff`, not downstream of the actual upsert result.

**Consequence**: live Supabase `dnc_registry` is still 25,772 rows, n8n is 25,858 — the same 86-row
gap that existed before last night's "heal," confirmed via a fresh probe just now. Drift is
*growing* (453 → 469, +16 in 24h from the sweep's continuing hourly writes), not healing.

## 1. Classification of the 469

**86 rows — never reached Supabase at all** (missing entirely, not a field mismatch). All have
`correlation_id: null`.
- **82 rows**: `source=pipedrive_personal`, `reason=sales_personal_outreach`, `entry_type=manual`,
  all `createdAt=2026-09-15`. Matches the S3 roster-owned 111-person backfill's "82 written fresh"
  subset from 2026-09-15 — the batch where `dnc_archived_responders_import` failed to auto-resolve
  a Pipedrive person id and was corrected with a direct, person-id-matched patch.
- **4 rows**: `source=campaign_reply`, `reason=reply_dnc`, `entry_type=negative_reply`,
  `source_ref="[Events Visiting] [FinovateFall 2026] - Noah - LinkedIn"`, all
  `createdAt=2026-09-15`. Matches the "4 missed repliers" backfilled from the FinovateFall event.

**383 rows — exist in Supabase, field(s) differ:**
- **381 rows**: only `projections_state` (+ `updatedAt`) differ. `updatedAt` timestamps cluster at
  2026-09-15 13:00–14:00 (343/381) with a long tail into 09-16/09-17 — exactly matches
  `dnc_projections_sweep`'s hourly execution history (56426@13:34, 56894@14:00, etc.).
- **2 rows** (Person-d9409383, Person-b27663e9): `status`/`removed_at`/`removed_reason` (+`updatedAt`)
  differ. Custom `removed_reason` values (`false_reply_ooo`, `false_reply_mailbox_inactive`) and an
  untouched original `correlation_id` (`wf2_reply:3868450:...`) rule out both
  `dnc_s4_retirement_removal` (hardcoded reason string) and UpsertLedger (would rewrite every
  field) — this was a targeted direct field patch. Matches the "tombstone 2 false positives" item
  from the 2026-09-15 "GO, in order" work.

## 2. Direct-write paths vs UpsertLedger — bypass audit

`DNC__UpsertLedger__v1` is the **only** subworkflow with a `dt_claim_enqueue` call (its main upsert
and its tombstone/split-identity path). Every workflow that reaches it via `executeWorkflow`
(S1, S2, S3, S3-persons, S3B, S4, WF4 sheet intake, `dnc_archived_responders_import`) gets the
enqueue automatically — **confirmed not a bypass** for the S2 rebuild's first fire, and for the
*normal* `dnc_archived_responders_import` path.

Confirmed bypasses (direct `dt_update`/`dt_upsert` to `dnc_registry_dev`, zero `dt_claim_enqueue`
anywhere in the workflow):

| Path | Bypass? | Cadence | Caused last night's drift? |
|---|---|---|---|
| `dnc_projections_sweep` — `PD Mark Done`, `PD Mark Write Error`, `SL Mark Done` | **Yes** | Hourly (`FIRE_PIPEDRIVE`, re-armed live yesterday) | **Yes — 381/469 (81%)** |
| `dnc_expiry_job` — `Update -> expired`, `Update -> removed (dedup)` | **Yes** | Daily 06:00 | No (not this batch's signature), but latent |
| `dnc_s4_retirement_removal` — `Update Row` | **Yes** | Manual/webhook | No (reason string doesn't match), but latent |
| `dnc_label_reversal` | No — doesn't touch `dnc_registry_dev` at all (Pipedrive-only write) | — | No |
| Ad-hoc direct Python patches (this session's own one-off corrections, not a generated workflow) | **Yes**, structurally — a raw API call, not an n8n execution | One-off | **Yes — 86/469 (18%) + the 2 status-change rows** |

**Fix, if you want it** (not applied — read-only per instruction): route
`dnc_projections_sweep`'s Mark Done nodes and `dnc_expiry_job`'s expire/dedup nodes through
UpsertLedger, or add a `dt_claim_enqueue` call directly after each. Separately — and probably more
urgent — the Upsert Corrections write needs per-row error visibility (wire its error output
somewhere, and/or chunk finer than 500 so one bad row doesn't sink a whole night's heal), and every
future one-off backfill/patch script should set `correlation_id` and/or explicitly call the
delta-push claim mechanism.

## 3. Pusher health

Fully healthy. `dnc_supabase_delta_pusher` (id `xpmOzZn1oKOVoiTD`), active, ticking every 5 minutes
exactly as scheduled. **800/800 executions succeeded**, zero failures, covering its full history
back to first deploy (2026-09-14T12:30) through now. Current claims queue depth: **1** (near-empty,
steady state). The pusher was never the problem — it faithfully drains whatever gets enqueued; the
469 rows never had a claim to drain because they never went through a path that creates one.
