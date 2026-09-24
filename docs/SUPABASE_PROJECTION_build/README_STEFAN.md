# DNC registry in Supabase — quick reference

## What this is

A read-only projection of the n8n DNC ledger into Supabase Postgres, so Clay can look up DNC
status without hitting the gate webhook per row. **Phase 1 only right now**: the tables exist and
are locked down, but they are empty — no data has been loaded yet. Phase 2 (initial load + keeping
it in sync) is a separate, later step.

## The tables

- **`dnc_registry`** — one row per DNC identity (a person). Look this up by **identity_key**.
- **`dnc_domains`** — one row per banned company domain (Company DNC, 1,373 domains from Clay).
  Look this up by **domain** (the part of an email after the `@`, lowercased, no `www.`).
- **`dnc_registry_meta`** — a log of sync runs (when the data was last refreshed, how many rows,
  which job did it). Useful for sanity-checking freshness, not something you look up per lead.

## Two lookups, not one

A lead can be blocked for either reason, so build both:
1. **Person lookup** — `dnc_registry.identity_key` = your identity-key formula column (see below).
2. **Company lookup** — `dnc_domains.domain` = the lead's email domain, lowercased, `www.` stripped
   if present. A match here means EVERYONE at that company is DNC, regardless of that specific
   person's own history — check this one even for someone with a clean person-level record.

Both tables use the same `status` convention (`active` vs `removed` — tombstoned, not deleted):
only an `active` match should block.

## The key column: `identity_key`

Every row's lookup key is **`identity_key`** — a single text column, `UNIQUE`, **never blank**.
It's either:
- a LinkedIn slug (e.g. `jane-doe`, from `linkedin.com/in/jane-doe`), if a matchable LinkedIn URL
  was on file, **or, only if that's not available**,
- a lowercased email address (e.g. `jane@acme.com`).

LinkedIn always wins when both are available — it is never "whichever you have," it's always
"LinkedIn if it resolves, otherwise email." Full algorithm + 5 verified worked examples are in
`NORMALIZATION_RULES.md` in this same folder — read that before building the formula column, since
your formula needs to produce the *exact same string* as this table's `identity_key` for a Lookup
to ever match.

**One gotcha worth knowing up front**: two columns (`"createdAt"` and `"updatedAt"`) are
camelCase, not snake_case like everything else — that's copied verbatim from the n8n source, not a
mistake. Postgres is case-sensitive for quoted identifiers, so if you ever query these two columns
directly in the SQL Editor, they need double quotes (`"createdAt"`) or Postgres will look for an
all-lowercase column that doesn't exist. You won't hit this through Clay's Lookup column UI, only
if you write raw SQL against the table.

## How to set up the Lookup in Clay

1. Add a formula column that computes the identity key for each of your rows, following
   `NORMALIZATION_RULES.md` exactly (not just eyeballing the 5 examples).
2. Add a Supabase Lookup column: table `dnc_registry`, match on `identity_key` = your formula
   column's output.
3. A match means that person is on the DNC list — check the `status` column too
   (`active` vs `removed`): a `removed` row means they were on the list before but have since been
   cleared (tombstoned, not deleted) — treat `removed` rows as **not currently DNC**, only `active`
   ones block.
4. `reason` / `entry_type` tell you *why* they're on the list, if you want to surface that.

## Read-only, by design

The key you have (`sb_publishable_…`) can only **read** from these two tables — there is no
insert/update/delete policy for it at all, on either table. This isn't a convention, it's enforced
at the database level (Row Level Security): even a malformed or malicious write attempt through
this key is structurally rejected, not just discouraged. Writes only ever happen server-side,
through the secret key, which isn't shared outside n8n's own credentials store.

If you ever need something written or corrected in the registry, that goes through the normal
`dnc_pre_add_gate` / registry process — not a direct Supabase write, which isn't possible with the
key you have anyway.

## Status right now

Phase 1 (this SQL + these docs) is ready to run for `dnc_registry`. `dnc_domains` also needs Nik to
create its n8n Data Table first (there's no verified table-creation API for this platform — every
table in this whole project has needed a human to create it once) before the 1,373-row import can
fire; the SQL table itself is ready regardless. Phase 2 — actually loading rows and keeping both
tables in sync — hasn't started yet; both tables will be empty until then.
