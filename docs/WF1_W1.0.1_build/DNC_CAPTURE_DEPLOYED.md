# DNC reply capture — live in both receivers (2026-09-03)

**Ruling (Nik):** everyone who replies to any of our campaigns goes to **DNC active**. I raised that
`reply_dnc → negative_reply` also suppresses positive repliers; the rule was reaffirmed in full and
is built as ruled.

| | |
|---|---|
| WF-2 Smartlead Receiver | `5d4a5c97` · 191 nodes |
| WF-1 HeyReach Receiver | `1f64e121` · 138 nodes |

## Shape — inline, one path per receiver, no bridge workflow

```
WF-2:  First Reply Gate ──▶ DNC Reply Gate ──▶ DNC Build Input ──▶ DNC Upsert Call
WF-1:  M7 Alert Key     ──▶ M7 DNC Reply Gate ─▶ M7 DNC Build Input ─▶ M7 DNC Upsert Call
```
Both call `DNC__UpsertLedger__v1` (`RolYGL3J2CNg6Yp3`) via `executeWorkflow` `mode: each` — the same
node shape and input contract as the only prior caller (S4). `heyreach_reply_to_dnc_ledger` was NOT
wired; the write is inline, as instructed.

## Reason mapping (both channels)

| signal | reason | entry_type | lifetime |
|---|---|---|---|
| explicit stop phrase | `unsubscribe` | `explicit_opt_out` | permanent |
| any other genuine reply | `reply_dnc` | `negative_reply` | permanent — `date_precision:'unknown'` triggers `reasonExpiryOverride` → `expires_at = null` |

Both reasons are legal in `REASON_TO_ENTRY_TYPE`. `negative_reply` is **not** a reason — it is the
entry_type `reply_dnc` maps to; passing it as a reason throws.

## Never written — existing locks reused, not re-derived

| | WF-2 | WF-1 |
|---|---|---|
| OOO / auto-reply | `__ooo` from First Reply Gate | n/a (HeyReach has no categories) |
| bounce | `event !== 'REPLIED'` | non-reply events excluded |
| non-campaign chat | campaign attribution required | `__manual_thread !== true` |

## Fire-and-forget

Both `Upsert Call` nodes are `onError: continueRegularOutput` on a dedicated branch teed off an
existing node. A ledger failure cannot fail or delay a reply, an alert, a label, or a CRM write.

## Statics — 11/11, class level

```
WF-2 campaign reply        -> WRITES
WF-2 OOO                   -> never written
WF-2 bounce                -> never written
WF-2 non-campaign          -> never written
WF-2 normal reply          -> reason=reply_dnc, category from Smartlead ('Interested')
WF-2 explicit stop         -> reason=unsubscribe
WF-1 campaign reply        -> WRITES
WF-1 manual chat           -> never written (regression)
WF-1 non-reply event       -> never written
WF-1 reply                 -> reply_dnc + named placeholder category
same reply twice           -> identical correlation_id (idempotent via UpsertLedger)
```

## Two things to know

**1. WF-2 never wrote the ledger before.** The briefing said its unsubscribe branch already did;
it does not — that branch calls Smartlead's `/leads/{id}/unsubscribe` and writes a Pipedrive label.
WF-2 had **zero** `executeWorkflow` nodes. This is the first ledger write in both receivers, built
from the sub-workflow's contract rather than copied from an existing one.

**2. WF-1 sends `reply_category: 'linkedin_reply_uncategorised'`.** The ledger throws on `reply_dnc`
without a category — a guard added after the 116-row gap. HeyReach has no categories at all: no
classifier, no sentiment, nothing in Normalize. The placeholder is deliberately named so these rows
stay findable if a LinkedIn classifier is added later. WF-2 sends Smartlead's real category and only
falls back to `email_reply_uncategorised` if one is absent.

## S1 / S2 status change

The hand-fired S1/S2 workflows are now **backfill tools only, not the capture path**. Live capture is
inline in both receivers. Anything S1/S2 finds from here on is history, not an ongoing gap.

## Outstanding

**Live proof on the next real reply on each channel** — not yet observed. Until then this is
statics-green and deploy-clean, not proven.
