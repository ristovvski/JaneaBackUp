# DNC BUILD — SEED WRITE Pass 1 (People-DNC + paul.gilford + company-domains)

**Status: DONE. PASS.**

## What was asked
Owner's explicit "SEED WRITE — GO" with a 5-point creation policy: no Pipedrive person creation
for creatable rows (identity fields alone carry the block); full rows w/ person_id for the 2,264
clean matches; the 64 ambiguous rows seed with reason intact + `projections_state.pipedrive=
held:ambiguous` + candidate person_ids in a side review file (not a seed blocker); write People-DNC
23,838 + paul.gilford + company-domains 1,373 in one pass with per-batch counts, then read-back
verify (100 random + 3 collision + all 142 Amsterdam + all 95 client); no projections fire this
pass (registry-only).

## What happened
1. Built `dnc_seed_build.py` — re-implements `merge_v1.js`/`reason_v1.js` semantics in Python
   (entry_type mapping, TTL=6mo expiry via computeExpiry + reasonExpiryOverride, owner_tag only for
   employee_connection rows, source-tag conventions) so every seeded row is indistinguishable from
   a real `UpsertLedger` insert. Cross-referenced the freshly-pulled Pipedrive index + resolution
   report from the prior task to apply the exact creation policy per row.
2. Validated on a 4-row real-data slice (one per category: offboard/client/creatable/ambiguous)
   before the full run. Caught and fixed a real bug this way: the seed-writer's Code node read
   `items[0].json.rows` but n8n's Webhook node nests the POST body under `.json.body`, not merged
   onto `.json` directly — fixed before touching the full 23,839+1,373 rows.
3. Ran the full write: 23,839 people rows (24×1000 batches) + 1,373 domain rows (2×1000 batches).
   **Zero mismatches** between sent and written on every single batch.
4. Read-back verified via a combined OR-filter `get` (100 random + 3 collision + paul.gilford +
   ALL reason=reply_dnc + ALL reason=client, category-filtered so the 142/95 checks are exhaustive,
   not sampled): 0 missing keys, 0 field mismatches across 22 checked fields, reply_dnc count 143
   (142 Amsterdam + paul.gilford, correct), client count 95/95. Domain table separately confirmed
   1,373/1,373.
5. All throwaway seed-writer/verify workflows deactivated + deleted; confirmed zero `zz_*`
   workflows remain in the instance.

Full writeup: [SEED_WRITE_REPORT_2026-08-11.md](../DNC_OBS_P1_build/SEED_WRITE_REPORT_2026-08-11.md).

## Improvable / judgment calls made without an explicit spec
- The registry `source` column's value convention (`onboarding_import:{owner}` / `smartlead_category`
  / `company_dnc_sheet:legacy_import`) was inferred from the schema yaml's own examples, not
  separately confirmed by the owner — low risk (it's an append/trace field, not identity or
  lifecycle-bearing) but worth a sanity glance.
- "3 named collision rows" for read-back was never pinned to specific identities anywhere in
  available files/memory — treated as 3 representative multi-collision samples instead. If the
  owner meant specific named people, say so and I'll re-verify those exact rows.

## Next
- Stage 2 (WF-4 Sheet intake) may now start — registry is populated.
- Projections (Pipedrive/Smartlead/HeyReach) did NOT fire this pass — separate gated step.
- 64 ambiguous rows await a lazy canonical-person decision (not urgent): `AMBIGUOUS_PERSON_REVIEW_2026-08-11.json`.
- Pass 2 (Pipedrive/Smartlead-sourced portions) still pending per the original sequencing.
