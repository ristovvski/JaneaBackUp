# Supabase Phase 2 — step 1: chunked initial load

Дата: 2026-09-14. GO from Nik after the credential/grant setup + read-only probes confirmed green.

## Done

- Deployed `dnc_supabase_initial_load` live in n8n (id `bRlYiFITIiBz0B2U`): one chunk (≤500 rows)
  per webhook call, `dry_run` defaults true and structurally gates BOTH real-write paths (chunk
  upsert AND the `dnc_registry_meta` finalize insert) — 15/15 local logic tests passed before firing
  anything.
- Auth: `predefinedCredentialType` + `nodeCredentialType: supabaseApi`, credential id
  `u6wyGnYC71Sr1KgT` ("Supabase account").
- Write mechanism: real PostgREST upsert (`POST .../rest/v1/<table>?on_conflict=<pk>`,
  `Prefer: resolution=merge-duplicates`), `on_conflict=id` for `dnc_registry`,
  `on_conflict=domain` for `dnc_domains`.
- Dry pass first (confirmed 52 chunks / 3 chunks, all `ok:true`, zero writes — independently
  verified all three Supabase tables still empty afterward), then live fire: `dnc_registry`
  (25,729 rows, 52 chunks) → `dnc_domains` (1,373 rows, 3 chunks) → one `finalize:true` call per
  table logging to the shared `dnc_registry_meta` (`source: 'initial_load:dnc_registry'` /
  `'initial_load:dnc_domains'`, approved shared-table design).

## Post-verify (all 4 checks Nik asked for)

1. **Counts**: `dnc_registry` n8n=25,729 / Supabase=25,729 (exact match). `dnc_domains`
   n8n=1,373 / Supabase=1,373 (exact match).
2. **50-row registry sample**: field-by-field, 0 mismatches (after fixing my own verification
   script's timestamp-format false positives — see Improvable).
3. **All 1,373 domains**: field-by-field, 0 missing, 0 extra, 0 mismatches (after paginating
   around Supabase/PostgREST's default 1000-row response cap — see Improvable).
4. **RLS proof**: Nik ran a POST against `dnc_registry` with the anon/publishable key →
   `401 Unauthorized`, `{"code":"42501", ..., "message":"permission denied for table dnc_registry"}`.
   Independently confirmed the test row (`id: 999999999`) never landed (`select` by that id
   returns `[]`).

## Improvable (my own verification-script bugs, not data problems — worth remembering)

- n8n's HTTP Request node (typeVersion 4.2) "full response" option is NOT `options.fullResponse`
  (silently ignored, no error — just returns the parsed/auto-detected body with no wrapper). The
  real path is `options.response.response.fullResponse`. Saved to memory.
- Supabase/PostgREST enforces a default `max-rows` (1000) server-side cap on any single response,
  regardless of the client's own `?limit=` value — my first domains-compare pull silently came
  back with only 1,000 of 1,373 rows, which looked exactly like 373 real "missing" rows until I
  paginated with `offset=`/`limit=`. Saved to memory.
- A first (overly heavy) version of the post-verify workflow returned the full 25,729-row registry
  TWICE in one n8n execution and triggered transient 502/503s from the n8n API for a few minutes.
  Redesigned to fetch the n8n side exactly once (kept client-side in Python) and keep every
  Supabase-side call small.

## Next

Delta pusher (claims-table queue, never staticData) → nightly reconcile for both tables → digest
line. Pre-post artifact before each, per standing instruction.
