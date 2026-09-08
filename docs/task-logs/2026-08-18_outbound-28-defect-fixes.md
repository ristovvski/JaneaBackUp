# 2026-08-18 — #28 outbound logging: both read-back defects fixed (campaign 3686181)

Live state: 983 outbound activities on 3686181, correctly routed, canonically keyed.
**Re-run proof: `PLANNED 0 · already present 983`** — the backfill is now genuinely idempotent.

## DEFECT 1 — `stats_id` is not unique

I claimed email had "a REAL provider event id, no synthesised hash needed". Wrong.

```
campaign   SENT   collisions (lead,stats_id)   (lead,message_id)
3686181     985              9                        0
3686184     786             14                        4   <- byte-identical feed dupes
3686187     798              9                        0
3686193     878             19                        0
```

**`email_seq_number` was IDENTICAL across every collision** — so the proposed `stats_id|step` would
have fixed nothing. `stats_id|time` works. **`message_id` is better**, and the reason is the 4
remaining collisions in 3686184: one lead (`pii-55692c9e@example.invalid`) is returned twice by the feed, so its
4 sends appear twice with identical body, time and id. Collapsing those is *correct*; a time-based
key would have faithfully written each one twice.

**Canonical key, both paths: `O|SL|<message_id>`.** Static on the exact 9 collision cases: 5 shared
old keys → 3+3+3+3+2 entries → **all distinct**. Re-keyed all 983 written footers.

## THE ERROR I MADE WHILE FIXING IT — and how it surfaced

The re-key wrote message_id **with its RFC angle brackets**: `O|SL|<ea0a107e-…@domain>`.
**Pipedrive's note field is HTML.** It parsed `<…@domain>` as an unknown tag and stripped it. Every
one of the 983 notes silently became:

```
[key:O|SL|]
```

Not a weakened key — an **inverted** one: identical on every activity, so the next run would either
skip everything or duplicate everything depending which side you read.

**What caught it:** re-running the dry-run and seeing `already present: 0` where 983 was the only
sane answer. The write itself reported 983/983 success. Had I trusted the success counter and moved
on, the next campaign would have duplicated at scale.

Fixed: keys are stripped of `<>` before writing, in the repair *and* in the script. New rule worth
carrying: **any identifier written into a Pipedrive note must be HTML-safe — the note is not a
plain-text field.**

## DEFECT 2 — campaign-aware routing (I under-reported this one)

The resolver took `active[0]` instead of the campaign's lead. **121 activities across 31 people**
landed on the wrong lead — mostly the AI4 **2025** lead (2342830), some on HumanX leads.

**I first reported this as "1 lead".** That number came from counting leads whose *campaign field*
mismatched — which is blind to every Make-created lead, because **Make leaves the campaign field
empty**. The honest measure was never "what looks wrong in one field" but **"what does corrected
routing choose differently"** — and that is 121.

Fixed order: campaign-field match → title prefix `<campaign_id> - ` → single active lead → otherwise
**unroutable, never a guess**. An unrouted send is recoverable; a misrouted one is a lie on
someone's card.

Remediation: **moved** (PATCH `lead_id`), not re-created — re-creating leaves the original behind
and doubles the record. 121/121 moved, 0 failed, statics proved every move stays within one person,
60-sample readback all correct.

## STILL OPEN

* 1 unroutable lead (`pii-f38c7b54@example.invalid`, 2 sends) — person exists, no lead, no open deal. Left alone.
* 985 SENT vs 983 written reconciles exactly: 985 − 2 unroutable = 983.
* Remaining three campaigns + HeyReach side: **held** pending Melisa's card-readability verdict.
* Live path (webhook fast-path + 15-min poller) not yet deployed.

## THE PATTERN, THIRD TIME TODAY

Every one of these was a **write that reported success while achieving nothing or the wrong thing**:
the phantom staticData registry, the empty `[key:]` footers, the misrouted activities. In all three
the API said 200. **Only re-deriving the expected state and comparing found them.** A success
counter is not verification.
