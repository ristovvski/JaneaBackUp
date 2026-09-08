# DNC BUILD — functional verification of dnc_registry_dev + dnc_domain_block_dev columns

**Status: DONE — both tables PASS.**

## What was asked
After Nik's second column-add pass, run the full zz_probe_ functional round-trip on
`dnc_registry_dev` (all 23 columns through UpsertLedger → CheckLedger → delete) and the same
treatment on `dnc_domain_block_dev`. Report PASS or exact gaps.

## Result

- **dnc_registry_dev**: 23/23 columns confirmed via full round-trip (UpsertLedger insert →
  direct-set remaining cols → CheckLedger read-back → Diff → delete). Delete was independently
  confirmed with a second probe: a `get` filtered on the probe's `identity_key` returned zero rows,
  and a `lastNode`-mode probe returned n8n's own "No item to return was found" — hard proof the row
  is actually gone, not just that the delete node reported success.
- **dnc_domain_block_dev**: 7/7 columns confirmed via write-probe schema-diff in a single round, no
  gaps.

No residual probe rows or workflows left in either case.

## Bug found + fixed (probe-script only, not production)
The probe's delete node used `"operation": "delete"`. n8n's actual internal value for that
operation is `"deleteRows"` (verified from n8n source: `Row.resource.ts` registers
`deleteRows.FIELD = 'deleteRows'`, and `"delete"` isn't a recognized value at all — hence the
generic "Cannot read properties of undefined (reading 'execute')" crash, not a clear error
message). Fixed in `zz_probe_build_and_run.py`. Confirmed via `grep` that no production workflow in
`build_dnc.py` performs a delete operation, so this never affected production and no
regression-guard static test was added.

## Improvable
- If a future production workflow ever needs to delete Data Table rows, remember the operation
  value is `deleteRows`, not `delete` — add a static regression test for it at that time (same
  pattern as the two other real bugs this build already guards against: `mode:name` in
  subworkflows, and `dt_upsert` missing `filters.conditions`).

## Next
Statics (76/76) already green from the prior migration; seed WRITE remains gated on the user's
explicit go-ahead plus the overnight Pipedrive resolution report — nothing here changes that gate.
