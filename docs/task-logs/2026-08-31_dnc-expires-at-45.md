# 2026-08-31 — the 45 active-but-expired DNC rows

Read-only. **No writes.** Artifact: `DNC_EXPIRY_45/resolve_45_artifact.json`, driver
`DNC_EXPIRY_45/resolve_45.py`.

## 3 first, because it was the blocking question: **they are NOT unprotected**

Nothing evaluates `expires_at` to decide protection. Grepped all 35 workflows.

`dnc_pre_add_gate / Classify Batch` — **ACTIVE**, the thing that actually blocks:

```js
const active = all.filter((r) => r.status === 'active');
if (active.length) {
  const p = pick(active);
  gate_result = 'BLOCKED';
  ...
} else {
  const p = pick(all);
  gate_result = 'CLEAN';
  reason = 'was ' + p.entry_type + ' until ' + (p.removed_at || p.expires_at || 'unknown') + ', currently clean';
}
```

`expires_at` appears **only** inside the human-readable `reason` string on the CLEAN path. It never
gates anything. Same shape in `DNC__CheckLedger__v1 / Report` (`on_dnc` decided by
`status === 'active'`) and `dnc_check_service / Format Reply` (display only).

Writers, not evaluators: `DNC__UpsertLedger__v1 / Decide` sets it on insert;
`dnc_projections_sweep / SL Mark Done` (ACTIVE) sets `expires_at: null` on `done:permanent`.

The only thing that would ever act on it is `dnc_expiry_job / Plan` — *"expires_at < now, active,
not untouchable"* → expire. **INACTIVE, 0 executions in retention.**

**There is no Clay/Supabase projection.** Zero hits for `clay` or `supabase` across all 35
workflows; `dnc_projections_sweep` covers pipedrive / smartlead / heyreach only.

So: not urgent. The 45 are protected today, by `status`.

## The mechanism, fully explained

`DNC__UpsertLedger__v1 / Decide`:

```js
function computeExpiry(entry_type, added_at, ttlMonths) {
  if (DNC_PERMANENT_TYPES[entry_type]) return null;   // explicit_opt_out / employee_connection
  if (entry_type === 'replied' || entry_type === 'negative_reply') return dncAddMonths(added_at, ttlMonths);
  return null;                                        // manual: permanent
}
```
with `ttlMonths: Number(cfg.ttl_months || 6)`.

All 45 are `entry_type = negative_reply`, `added_at = 2025-07-01` → +6 months = **2026-01-01**, and
all 45 carry exactly that one date. Deterministic, not drift.

**This is still happening.** `DNC__UpsertLedger__v1` is an inactive *workflow* but runs as a
sub-workflow — 5 executions on 2026-08-28, mode `integrated`. Every new `negative_reply`/`replied`
row is still given a 6-month TTL today.

## Blast radius — it is not 45, it is 1,353 on a rolling timer

Measured against the live registry (`dnc_escalation_detector` exec 39637, 11:00:18Z, 25,653 active
rows walked):

| | rows |
|---|---|
| active total | 25,653 |
| active **with** an `expires_at` | **1,353** |
| …already past | **45** ← the CSV, independently reproduced, incl. its 36 `reply_dnc` / 9 `meeting_dnc` split |
| …still in the future | **1,308** (1,139 `negative_reply`, 169 `replied`) |

The 1,308 become the same rows as their dates pass.

## 1 + 2. Resolution and classification — 45/45 resolved, 45/45 class (a)

Identity waterfall, never name-only: stored `pipedrive_person_id` **corroborated** against the
row's email or LinkedIn slug → email exact → LinkedIn slug → unresolvable.

* **45 resolved, 0 unresolvable, 0 uncorroborated stored ids** (4 by slug, 41 by email).

Strongest evidence per row:

| tier | rows |
|---|---|
| 1 — Smartlead `last_reply_at` (provider truth) | **37** |
| 3 — `meeting_dnc`, S2 sweep off the `5. Meeting` label ∪ Qualified Meeting Set stage | **4** |
| 4 — curated `reply_category` from the 2026-08-28 archived-responders export | **4** |
| 5 — Pipedrive label only | 0 |
| 6 — nothing | 0 |

* **(a) genuinely replied/met → protection must not expire: 45**
* **(b) contact-only leftovers that should have gone with the 7,486: 0.** None of the 45 is
  `event_contacted`; they are 36 `reply_dnc` + 9 `meeting_dnc`. They survived the 08-26 sweep
  **correctly** — the sweep retired contact-only rows, and these are engagement rows.
* **(c) unresolvable: 0**

Also: 2 open deals (Person-85e9fd80 p44193, Person-2acf2fbc p56722), 32 carry `3. Responded`, and
**0 carry a `DO NOT CONTACT` label** despite `projections_state.pipedrive = "done"` on every row —
worth a separate look, since "done" and "no label present" disagree.

### Caveats, stated rather than buried

* Lead lists come from `/v1/leads?person_id=`, which **cannot see archived leads**. 11 rows showed
  zero live leads; the search route found an archived lead for 10 of them, and the 11th (Dimitri
  Stelmakh) has an open deal instead — a lead→deal conversion removes the lead.
* Pipedrive reply **activities**: the check ran and found **0** across all 45. These are 2025
  contacts predating WF-1/WF-2, so our automations never wrote reply activities for them. Absence
  is not evidence of no reply.
* HeyReach not consulted — the workspace only holds data from 2026-07-13; absence would prove
  nothing.
* 4 rows have **no email at all** (LinkedIn-only) and rest entirely on the curated
  `reply_category`. They are the weakest of the 45.

## 4. Recommendation — null the field and retire the job, but the writer is the actual fix

**Option A, with a mandatory third step.**

1. `expires_at = null` on all **1,353** active rows carrying one — not just the 45. Nulling only
   the 45 leaves 1,308 rows that walk into the same state on their own schedule.
2. Retire `dnc_expiry_job` — **deactivate and preserve, do not delete** (the I-04 OOM workflow's
   deletion is why that rule exists). It is already inactive with zero executions; retiring it
   makes that intentional rather than incidental.
3. **Neuter `computeExpiry` in `DNC__UpsertLedger__v1`** so `replied`/`negative_reply` return
   `null` like every other type. Without this, steps 1 and 2 are cosmetic: the sub-workflow keeps
   minting 6-month TTLs on every new reply row, and the population rebuilds.

Why not "keep the field with a documented meaning": the 2026-08-26 ruling already replaced
time-based expiry with reason-based retention — *"only a RESPONSE creates a relationship worth
protecting"*. A TTL on exactly the rows that represent a response contradicts it. Keeping the
field would mean documenting a rule nobody intends to apply, which is how it survived this long.

Counts if fired: **1,353 row updates, 1 workflow deactivation, 1 code change.** Fully reversible —
the current `expires_at` values are recomputable from `added_at + 6 months`, and the 45 are
captured verbatim in the artifact.

No writes made. Awaiting the word.
