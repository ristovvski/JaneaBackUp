# dnc_domains — n8n Data Table spec + architecture recommendation

## Recommendation: a separate Data Table, NOT a "domain entry class" inside `dnc_registry_dev`

**Use a new, separate table.** Reasoning:

1. **Semantic mismatch.** A person DNC row means "don't contact this specific human" and carries a
   whole lifecycle this concept doesn't need: `entry_type`/`reason` (STRENGTH ladder, merge-without-
   downgrade), `reply_category`, `expiry_review_pending`, TTL expiry via `computeExpiry()`. A domain
   block means "don't contact anyone at this whole company," permanently, with none of that — forcing
   it into the person schema means either leaving a dozen columns meaningless on every domain row, or
   inventing a new `entry_type` that the STRENGTH ladder (`explicit_opt_out:5 ... manual:1`) and the
   merge/reactivation logic in `merge_v1.js` were never designed to reason about.
2. **Collision risk, structurally eliminated, not just unlikely.** `identity_key` is always either a
   LinkedIn slug or an `email_lc` (which always contains `@`, per `normalizeIdentityV1`). A bare
   domain string like `acme.com` can never collide with an `email_lc`-shaped key (no `@`), and would
   only collide with a LinkedIn slug in the vanishingly rare case someone's vanity URL happened to
   literally be a company domain string — not impossible, but avoidable entirely by using a separate
   table instead of "avoidable in practice." A separate table makes the collision question moot by
   construction, which is what "must never collide" should mean for something this consequential (one
   bad row blocks thousands of real prospects).
3. **Different lookup shape.** The gate needs to ask "is `<email's domain>` in the banned list?" — a
   substring-after-`@` lookup against a domain table, not an identity_key match. Folding this into
   `dnc_registry_dev` wouldn't simplify that lookup at all; it would just make the SAME query harder
   to write correctly (now needs to also filter `entry_type = 'company_domain'` to avoid matching a
   person row by accident).
4. **Symmetry with the Supabase side**, which already got its own separate `dnc_domains` table in the
   same Phase 1 script for exactly reasons 1–3. Keeping the n8n source-of-truth shape 1:1 with its
   own projection means Phase 2's sync logic stays a straight per-table copy, not a filter-and-split.

## Table spec (create via the n8n UI, same as every other table this project has needed —
there is no verified table-creation API; a human has to do this step)

**Table name**: `dnc_domains`

| Column | Type | Notes |
|---|---|---|
| `domain` | String | lowercased, no leading `www.` — e.g. `acme.com`. Treat as the natural key (one row per domain); the import script below already dedupes before writing, so this table should never receive a duplicate write in practice — but there is no enforced-unique constraint available on this platform any more than there is elsewhere in this project, so the import script's own dedupe is the real guarantee, not the column. |
| `added_at` | Date | when the domain entered the blocklist |
| `source` | String | `'clay_company_dnc_import'` for this batch; leaves room for a future manual-add source |
| `reason` | String | nullable — the CSV carries none |
| `status` | String | `'active'` \| `'removed'` — same tombstone convention as `dnc_registry_dev`, never a hard delete |

Once created, its real table id needs to replace the `mode:"name"` placeholder in the import script
and in the gate — `mode:"name"` has proven unreliable from API-created workflows on this instance
every time it's been tried (i04_snapshots, dnc_gate_queue, and others) — get the id from the table's
own UI URL, same as always.

## Free-mail rejection (built into the import, not a one-time check)

The 1,373-row batch happens to contain zero free-mail domains today (verified directly against the
whole file), but the import script rejects them anyway as a standing safeguard — a future manual
addition or a re-export that picks one up would otherwise silently block every prospect on that
provider. Rejected list (checked at import time, logged and skipped, never silently dropped):

```
gmail.com, googlemail.com, outlook.com, hotmail.com, live.com, msn.com,
yahoo.com, ymail.com, aol.com, icloud.com, me.com, mac.com,
protonmail.com, proton.me, pm.me, gmx.com, gmx.net, mail.com, zoho.com,
yandex.com, yandex.ru, qq.com, 163.com, 126.com, naver.com, web.de,
inbox.com, fastmail.com, hey.com, tutanota.com, rocketmail.com
```

## Import batch — verified against the real CSV

- Source: `Company-DNC-Copy-of-Default-view-export-1788946008479.csv` (Clay export, columns
  `Created At` / `Updated At` / `Master Domain`).
- 1,386 raw rows → 1,373 distinct domains after lowercase + strip-`www.` + dedupe (13 domains
  appeared twice in the raw export, same-day double-entries; the earliest `Created At` per domain
  is kept as `added_at`). **1,373 matches the expected count exactly.**
- 0 blank/malformed domains, 0 free-mail hits, 0 `www.`-prefixed or uppercase rows in the source
  (the normalization steps are defensive for future imports, not corrections needed on this one).
- Ready-to-fire payload prepared in `import_domains.py` in this folder — blocked only on the table
  existing (needs its real id substituted first).
