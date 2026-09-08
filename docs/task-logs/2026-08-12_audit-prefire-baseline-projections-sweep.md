# Verifier: PRE-FIRE baseline for `dnc_projections_sweep` — captured 2026-08-12T12:44Z

Auditor session, read-only. Captured **before** the bulk window opens, deliberately, so these reads
do not contend with the sweep's ~2,264 calls. Evidence: `scratchpad/g1_prefire.json`,
`g2_sl_unsub.json`, `g3_blocked.json`.

**One item needs a decision before the fire: the `623` figure matches nothing measurable in
Smartlead.** Details in §4. Everything else is baselined and ready.

---

## 1. Gate read-back (as asked)

```
workflow   8qVXtI2ez5o6a9hc  dnc_projections_sweep
versionId  99082f37-4d35-4e9b-923c-61d205b81e41
updatedAt  2026-08-11T13:19:54.845Z
active     FALSE
nodes      35        errorWorkflow  BbrXPABgOaaTJjD6   (real, not the placeholder)

MODE              = dev
FIRE_PIPEDRIVE    = false
FIRE_SMARTLEAD    = false
alert_channel     = C0B8GCVNR5W
dev_channel_guard = C0B8GCVNR5W      (matches -> Send Guard will not throw)
pd_field_key      = 9c018b7406ebc481b9c108a487f76c4d09f91c9b
pd_active_option  = 686
pd_label_dnc      = 52a7c290-fc73-11f0-ad98-81d4703453f3
```

**Two consequences of this state, stated because they change what "fire" means:**

1. The workflow is **inactive**. It is webhook-triggered, so its production webhook is not serving —
   it cannot fire at all until it is activated.
2. With `FIRE_PIPEDRIVE=false` and `FIRE_SMARTLEAD=false`, activating and firing it produces the
   ~2,264 Pipedrive **reads** and **zero writes**. That matches your own plan ("fire after dry-run
   counts reproduce through the sweep itself vs the known baseline"), so it is probably intended — but
   if this run is meant to write, both flags have to flip, and that flip is what I would want to
   read back immediately before and after.

## 2. What the sweep writes, resolved to names

| identifier | resolves to |
|---|---|
| person field `9c018b7406eb…` | **'DNC Status'** (enum) |
| option `686` | **'dnc_active'** |
| lead label `52a7c290-fc7…` | **'DO NOT CONTACT'** |

## 3. Pipedrive baseline — well-posed, exact

Full walk, 579 pages, 0 duplicate ids:

| | |
|---|---|
| non-archived leads | **57,847** |
| leads carrying **'DO NOT CONTACT'** now | **5** |
| exact id set of those 5 | saved in `g1_prefire.json` |

So the post-run delta is large and unambiguous: expect `5 + (leads belonging to the 2,264 matched
persons)`. I will diff the **id set**, not just the count, so a lead that gains the label and a lead
that loses one are distinguishable.

Standing caveat, unchanged: `archived_status` is silently ignored by `/v1/leads`, so this is the
**non-archived** population. `PD Get Leads By Person` enumerates with a list read (archived-blind)
while `PD Get Lead For Labels` uses a detail read (archived-visible) — a lead can therefore be
invisible to enumeration but writable by the patch step. Treat 2,264 as a floor.

*Side observation:* leads went 57,602 (Aug 10) → **57,847** (+245) in two days, which is consistent
with the patched WF-2S SENT path now creating leads. P0-2's fix is visible in the counts.

## 4. Smartlead baseline — and why `623` does not reconcile

All 117 campaigns walked, 0 errors, 22,327 lead rows:

| metric | value |
|---|---|
| `lead.is_unsubscribed = true` — **rows** | 55 |
| `lead.is_unsubscribed = true` — **unique emails** | **55** |
| `status = BLOCKED` — rows | 1,655 |
| `status = BLOCKED` — **unique emails** | **1,650** |
| **sweep's stated baseline** | **623** |

**623 matches none of them** — not rows, not unique emails, in either metric (Δ −568 against
unsubscribed, Δ +1,027 against blocked). Deduplication does not explain the gap either: blocked rows
1,655 → 1,650 unique, so there is almost no cross-campaign duplication to collapse.

There is no readable global block-list endpoint to check against: `/leads/global-block-list`,
`/leads/blocklist` and `/leads/blocked` all return **400** (route exists, not GET-able), and
`/global-block-list` / `/blocklist` return 404.

**So `623` looks like a registry-side target (a DNC-ledger count), not a Smartlead state.** If that is
right, "confirm counts vs 623" is not a Smartlead reconciliation and I should not report it as one.
Please confirm which quantity 623 is before the fire, and I will reconcile against the correct one.

**A substantive design question that falls out of this.** `SL Unsubscribe` POSTs
`/leads/{lead_id}/unsubscribe`, which moves `lead.is_unsubscribed` — the **55** column. But
suppression in this account today is overwhelmingly `BLOCKED` (**1,650**), which is what a global
block list looks like reflected per campaign-lead. If BLOCKED is what actually prevents sending, then
per-campaign unsubscribing 987 leads may not deliver equivalent suppression, and a lead unsubscribed
in campaign A could still be mailed from campaign B. I cannot settle this read-only because the block
list is not GET-able — but it is worth settling before 987 writes go out, not after.

## 5. Correction to my own first pass

My first Smartlead pass scoped to `status in (ACTIVE, PAUSED)` and returned `unsubscribed: 0` across
11 campaigns. Both halves of that were wrong to publish as-is:

- **All five Ai4 campaigns are now `COMPLETED`** (3686181 / 84 / 87 / 93 and 3756410 — they were
  PAUSED on Aug 10), so the filter silently excluded exactly the campaigns that matter.
- A uniform zero is also the signature of reading a field that does not exist, so I validated the
  extraction against a known-true positive control before trusting it: fixture lead `4306240392`
  returns `lead.is_unsubscribed = true`, `status = BLOCKED`,
  `unsubscribed_client_id_map {"0": "2026-08-11T13:15:59.229917+00:00"}` — matching the `UNSUB|…`
  claim at 13:16:06Z. The field name was right; the scope was not. §4 supersedes it.

## 6. What I will do post-run

1. Re-read the gate flags and versionId — confirm what state the sweep was actually in when it fired.
2. Re-walk all leads and **diff the 'DO NOT CONTACT' id set** against the 5 captured here: gained,
   lost, and unchanged, by id.
3. Count persons whose changelog shows a write to `9c018b7406eb…` inside the window, with actor and
   timestamp — this needs no pre-baseline and attributes the writes independently of the sweep's own
   reporting.
4. Re-walk Smartlead and re-count both `is_unsubscribed` and `BLOCKED`, unique and by row.
5. Reconcile against 2,264 / 987 / and whichever quantity 623 turns out to be.
6. Report any lead that **lost** a label during the window — the wiper signature — since a bulk label
   patch is exactly the condition under which that would hide.
