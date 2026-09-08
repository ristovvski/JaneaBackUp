# 2026-08-31 — expiry killed, all three steps

Fired on Nik's GO. Artifacts in `DNC_EXPIRY_KILL/`.

## Rulebook entry

**Time-based expiry is retired. Retention is reason-based.**

Melisa's 2026-08-26 ruling replaced time-based expiry with reason-based retention: the registry
keeps replies, meetings, sales-created/Surfe, employee connections and explicit opt-outs, and
retires rows whose only reason was contact. A six-month TTL on `replied` / `negative_reply`
applied to precisely the rows that represent a response — it said the response stops mattering
after six months, which is the opposite of *"only a RESPONSE creates a relationship worth
protecting"*. The field is now null everywhere and nothing writes it.

## Step 1 — 1,353 rows nulled

**§9f.2 artifact first**: `DNC_EXPIRY_KILL/expires_at_snapshot.json` records every row's current
`expires_at` verbatim (id, identity_key, added_at, entry_type, reason, status, value, past/future).
Reversible two ways — replay the artifact, or recompute `added_at + 6 months` for
`replied`/`negative_reply`.

Source: `dnc_escalation_detector` exec 39637 (11:00:18Z), 25,653 active rows walked.
**1,353 carried an `expires_at`** — 45 past, 1,308 future; 1,184 `negative_reply`, 169 `replied`;
**0 rows lacked an id**, so every target could be addressed exactly.

Writer: `dnc_expiry_null_oneshot` — webhook-triggered, secret-gated, **id-targeted**. It does not
read the registry and decide for itself what to null; the caller supplies the exact id list from
the snapshot, so what was written is exactly what was recorded as reversible. Matching on the
row's own `id`, table by `mode:"id"`, never by name.

* **Canary first**: one row (8901, `cfalcken`, past-dated) → `asked 1, confirmed_null 1, failed 0`.
  The Tally node's check is *positive* — it asserts the response is a real row carrying an
  `identity_key` with `expires_at` now null, rather than testing for the absence of `.error`
  (dataTable failures do not reliably produce one).
* **Then 14 chunks of ≤100** — the documented OOM threshold on this instance is ~100 items.

```
chunk    0.. 100 … chunk 1300..1352
TOTAL (excl canary): asked 1352  confirmed_null 1352  failed 0
grand total incl canary: 1353 of 1353
```

Endpoint **deactivated immediately** after the run and confirmed closed (`POST` → HTTP 404).
Preserved, not deleted.

### Post-verify — clean

Independent reader: `dnc_escalation_detector` exec **39680**, 12:00:18Z, unmodified, the same
hourly walk the estate already runs. Deliberately not a verifier written by the hand that did the
writing.

```
active rows walked                                 25,653
active rows carrying a non-null expires_at              0
snapshot rows still present & active            1353 / 1353
  of those, still carrying a value                      0
  no longer in the active set                           0
status histogram of the active set          {'active': 25653}
```

The active total is **identical before and after** (25,653), and all 1,353 touched rows are still
present and still `active` — so nulling the field removed nothing and deactivated nothing. That is
the check that matters: the write changed one column and only that column.

## Step 2 — `dnc_expiry_job` deactivated and PRESERVED

`active: false`, **all 17 nodes still present**. Never deleted — the I-04 OOM workflow's deletion
is why that rule exists. It was already inactive with zero executions in retention; this makes it
intentional rather than incidental.

## Step 3 — `computeExpiry` neutered

`DNC__UpsertLedger__v1 / Decide`, versionId `f5b99244` (was `afe96bab`, backed up to
`upsert_backup.json`).

```js
function computeExpiry(entry_type, added_at, ttlMonths) {
  // EXPIRY IS DEAD (Nik, 2026-08-31). Every entry_type is permanent …
  return null;
}
```

All three call sites and the `record`/`merged` shape are untouched — only the policy inside
changes, so Amendment 3's `reasonExpiryOverride` still runs and still agrees. `ttlMonths` is left
in the signature so no call site had to move.

This mattered because **UpsertLedger is an inactive workflow that is nonetheless live**: it runs as
a sub-workflow (5 executions on 2026-08-28, mode `integrated`). Without step 3 the other two steps
were cosmetic and the population would have rebuilt.

### Static — 11/11, written at CLASS level

`test_no_expiry.js` runs the **actual `Decide` code** out of the workflow JSON.

* the case that mattered: a new `negative_reply` row is written with `expires_at: null`, still
  `active`, `added_at` still stamped
* class level: **every** entry_type — `negative_reply`, `replied`, `explicit_opt_out`,
  `employee_connection`, `manual` — yields null
* the TTL path is gone from the source, not merely unreachable; `computeExpiry` still exists and
  is still called; the rationale is recorded next to the code

**Control**: the same static run against the pre-patch definition **fails 5 of 11**, which is what
makes it a test rather than a decoration. Re-run against the definition read back from the API
after deploy: 11/11.

## The corrected check — DNC Status field, not a lead label

My earlier flag ("0 of the 45 carry a DO NOT CONTACT label, yet projections_state.pipedrive says
done") was wrong: we never write that label. `projections_state.pipedrive = "done"` means the
person's **DNC Status** field.

Resolved it properly: field id **9180**, key `9c018b7406ebc481b9c108a487f76c4d09f91c9b`, type enum,
options **686 = `dnc_active`**, 687 = `dnc_expired`.

**All 45 persons carry 686 / `dnc_active`. 45/45, no exceptions.** The projection is real and
correct. `dnc_status_686_check.json`.

Worth noting for later: option **687 `dnc_expired` now has no writer at all** — it was the expiry
job's output state. Nothing sets it and nothing should; it can be retired from the field whenever
someone is in there.
