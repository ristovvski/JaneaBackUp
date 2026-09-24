# Pre-fire artifact — dnc_morning_digest Gate Health reference fix (item 2 of Nik's 2026-09-15 GO)

## What's changing

One node, one line. `Gate Health` (live workflow `qJKfR602wV9yfFrj`) currently reads:
`const prev = $('DNC Removed Agg').first().json;`

Changing to:
`const prev = $('Supabase Mirror Agg').first().json;`

## Why (root cause, traced from real execution data, not guessed)

Walked the full chain from `Gate Monitor Last` to `No Match Count` using execution 55858's actual
`runData` (2026-09-15T04:00Z, the first real post-Supabase-patch run, the one that posted
`Supabase mirror: UNREACHABLE`): every node in that 12-node chain correctly named-references its
own immediate code-node ancestor across the HTTP-node hops between them — except `Gate Health`,
which still points at `DNC Removed Agg`. The 2026-09-14 Supabase-mirror patch spliced 3 new nodes
(`Supabase Mirror Check` → `Supabase Meta Check` → `Supabase Mirror Agg`) between `DNC Removed Agg`
and `Gate Monitor Last`, but never updated `Gate Health`'s reference to point at the new true
predecessor. Confirmed live: `Supabase Mirror Agg` itself computed the correct values that
execution (`supabase_reachable: true, supabase_rows: 25733, supabase_age_min: 0`) — they were just
silently dropped one hop later at `Gate Health`, and every node after it (including `Compose`)
never saw them again.

## Verification plan (no safe way to manually re-fire — digest has only a daily cron trigger, no
webhook; n8n's public API returned 405 on a manual-execute attempt, confirmed)

1. Apply the 1-line patch.
2. **Offline replay**: extract `Gate Health`'s real recorded inputs from execution 55858
   (`$input.first().json` — the Gate Monitor Last HTTP response — and `Supabase Mirror Agg`'s real
   recorded output from the SAME execution) and run the FIXED jsCode against them in Node,
   confirming the output object now carries `supabase_reachable`/`supabase_rows`/
   `supabase_age_min` forward correctly. This uses real production data, not a synthetic fixture.
3. Natural confirmation: tomorrow's 2026-09-16 04:00Z digest post should show a real Supabase row
   count and no `UNREACHABLE`/`DRY RUN` — worth a manual check.
