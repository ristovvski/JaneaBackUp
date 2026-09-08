# Click-list v2 — `dnc_registry_dev` real gaps only (functionally verified, not UI-eyeballed)

**What actually happened last round:** 12 of the 13 new columns landed fine (expires_at, removed_at,
removed_reason, correlation_id, norm_v, reason, source_ref, also_flagged, date_precision,
offboard_removable, expiry_review_pending, projections_state). But **all 10 of the ORIGINAL
columns are now gone** (identity_key, linkedin_url_norm, email_lc, full_name, pipedrive_person_id,
entry_type, source, owner_tag, reply_category, status), plus **`added_at` is still missing** too.
This matches a table that got recreated fresh rather than edited in place — the original columns
never got re-added, and `added_at` (first item on the old list) got missed the same way it did the
first time. Verified by direct functional probe (write attempt against the real table), not by
reading the UI's column list.

## Three traps — same as before, still the cause

1. **Clear the Name field before typing** (triple-click to select-all) — a stale name from a
   previous error carries over otherwise.
2. **Pause after picking the Type, before clicking "Add Column"** — confirm the Type field shows
   what you picked before submitting.
3. **One column at a time**, confirm each one landed (scroll right, or reopen the table) before
   starting the next.

## Add these 11 columns to `dnc_registry_dev`, in this order

| # | Column name | Type |
|---|---|---|
| 1 | `identity_key` | string |
| 2 | `linkedin_url_norm` | string |
| 3 | `email_lc` | string |
| 4 | `full_name` | string |
| 5 | `pipedrive_person_id` | **number** |
| 6 | `entry_type` | string |
| 7 | `source` | string |
| 8 | `owner_tag` | string |
| 9 | `reply_category` | string |
| 10 | `status` | string |
| 11 | `added_at` | **datetime** |

That's it — the other 12 columns (expires_at through projections_state) are confirmed present and
correctly typed, don't touch them.

## `dnc_domain_block_dev`

Confirmed it now exists (8 columns shown in the UI, matching 7 real + system `id`). Not yet
independently function-verified column-by-column the way `dnc_registry_dev` was — say the word if
you want that checked too before we rely on it.

## When done

Tell Code "done" — same as before, the next step is an automated round-trip test, no manual
checking needed on your end.
