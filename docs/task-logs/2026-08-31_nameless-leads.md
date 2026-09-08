# 2026-08-31 — the 72 nameless campaign leads

Read-only investigation. Repair artifact built, **nothing written**. Statics 13/13.

## The premise was wrong in a way that matters

**It is not WF-1/HeyReach. All 72 are WF-2/Smartlead.**

| campaign | provider | leads seen | nameless |
|---|---|---|---|
| 3868449 Valids | Smartlead | 47 | **37** |
| 3868450 Catch-alls | Smartlead | 37 | **35** |
| 572715 LinkedIn | HeyReach | 100 (search cap) | **0** |

Every one of the 100 HeyReach leads sampled carries its person-name suffix. The 50-of-53 figure
from yesterday is real, and those leads are named — they were just truncated at 70 chars in my
own earlier print, which is what made them look bare.

## Root cause — and it was already fixed three days ago

`WF-2 / Body Lead Create`:
```js
const title = [n.campaign_id, n.campaign_name, n.lead.full_name]
  .filter(v => v !== null && v !== undefined && v !== '').map(String).join(' - ');
```
A null `full_name` silently degrades the title to `{id} - {campaign}`. It never fails, it just
produces a shorter string.

`full_name` was null because these are **WF-2S replays**. Exec 35281 (12:32:03Z), verbatim:
```
webhook body: to_name = None,  lead_data = None       <- /leads-statistics has no name field
SL Fetch Lead returned: first_name, last_name          <- the data WAS there
Apply Enrich published: __enriched.lead.full_name = None   <- and did not map it
Body Lead Create title: '3868449 - [Events Visiting] [FinovateFall 2026] - Noah - Valids'
Body Person Create name: 'pii-fcce19b7@example.invalid'   <- the 215-name violation, same cause
```

`Apply Enrich` gained its name mapping on 2026-08-28 (its own comment cites Person-8bb29b7c and the
215-name rule). The boundary is razor-sharp:

```
nameless leads: 2026-08-28T11:30:05.618Z .. 12:32:45.594Z   (72)
next leads:     12:32:55 Person-d86d9627 · 12:33:05 Oban MacTavish · 12:33:15 William Hess   (named)
nameless created after the fix: 0
```

Five seconds. Those three named leads are the ones Nik posted as "WIRE PROOF: PASS" at 15:51 IDT.
So there is no live leak: the fix is in, proven on real traffic, and this is history only.

**The requested fix (3) is therefore already built.** `Apply Enrich` is not the pattern to copy —
it was the broken thing, and copying it into WF-1 would be work against a defect WF-1 does not
have.

## HeyReach field path — confirmed, not assumed

`POST /api/public/campaign/GetLeadsFromCampaign` → `items[].linkedInUserProfile`, carrying
`firstName` / `lastName` (**no** `fullName`), plus `emailAddress`, `companyName`, `position`,
`profileUrl`. Sample: `firstName: 'Tiffany'`, `lastName: 'Garrett, AAP'`. This is already the path
WF-1 reads, which is why its leads are named. No change proposed.

## The 1 sent-without-lead in 3868449 — Person-ab3144af

`pii-a2fe030c@example.invalid`, person **59327**, sent `2026-08-28T11:44:55.937Z`.

Two independent causes stacked:

1. **His SENT never reached WF-2.** An exhaustive pass over all 81 WF-2 executions of 08-28
   (75 SENT / 5 REPLIED / 1 BOUNCED, 76 distinct addresses, 0 unreadable) finds no execution for
   him. Seven of the 48 sends in that campaign are in the same position:
   `pii-a2fe030c@example.invalid · pii-bbb5022c@example.invalid · pii-8e4fcd65@example.invalid ·
   pii-ea47ffcd@example.invalid · pii-951c6903@example.invalid · pii-6d68509f@example.invalid · pii-7b0d2c5b@example.invalid`
2. **The 08-28 backfill repaired six of the seven and skipped him**, because its guard was
   *"person has no lead"* rather than *"person has no lead for THIS campaign"*. He already held
   `88bee220 — 2548814 - [Events Visiting] Money 20/20 2025 - Valids - Person-ab3144af` from
   2025-10-16. That is the lead-per-campaign rule (W1.0.11) being violated from the other side.

He has no open deal, so nothing blocks creating his campaign lead. Not bundled into this fire.

## Artifact — `nameless_lead_repair.py`

Dry-run by default; writes only with `--fire --i-have-niks-word`.

```
found 72 · repairable 72 · blocked 0 · persons also needing rename 0
writes if fired: 72 lead-title PATCHes, 0 person renames
reversible: every current_title is recorded in the artifact; replaying restores prior state
```

Names come from **Smartlead provider truth** (`/leads?email=`) for all 72 — not one falls back to
the Pipedrive person name, and none is derived from an address. Guards: search-saturation abort
before trusting the set, 429 retry with backoff, and a post-fire **independent re-scan** that
proves the class is empty rather than that our own rows went through.

`nameless_lead_repair_artifact.json` holds the full 72-row plan.

## Statics — 13/13

`test_nameless_lead_repair.py` imports the real `choose_name` (no reimplementation) and pins the
order of trust and, above all, the refusal: provider truth → real Pipedrive name → **refuse**.
Three email-shaped names are asserted to be refused with a reason, not silently skipped.

## Limitation worth recording

The digest's nameless check iterates **active Smartlead campaigns only**. A HeyReach equivalent
would not be caught by it today. It found this class because the class happens to be Smartlead.
