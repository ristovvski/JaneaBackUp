-- ============================================================================
-- SUPABASE PROJECTION — Phase 1 (files only, no live write). Paste into the SQL Editor once.
--
-- Source of truth for every column/type/value below: a live, read-only dump of the real n8n
-- Data Table (dataTableId UOgKwlGsL28lX61O, project name "dnc_registry_dev"), 2026-09-09.
-- 33,138 total rows read (status isNotEmpty, i.e. every row — active AND removed/tombstoned).
-- Every one of the 26 columns below was actually observed; nothing here is guessed from memory.
--
-- Verified facts this script relies on:
--   - identity_key: 0 blank/null values across all 33,138 rows. Confirmed, not assumed — see
--     NORMALIZATION_RULES.md #5 for the one input shape that WOULD produce a blank key, and why
--     it never reaches this table (the caller intercepts it before the write).
--   - norm_v: every row is 'v1' (no v2 migration has happened yet).
--   - expires_at: null on every row observed today (2026-09-09) — recorded as an observed fact,
--     not a guarantee; do not assume this column is unused, just that it is currently empty.
--   - entry_type / reason / status / date_precision are text, NOT Postgres ENUMs and NOT
--     CHECK-constrained here on purpose: the n8n side is the source of truth for what values are
--     valid (see reason_v1.js's REASON_TO_ENTRY_TYPE), and a hardcoded CHECK here would silently
--     reject a future legitimate value during Phase 2's delta sync instead of just projecting it.
--     Currently observed values (informational only):
--       status:        active | removed
--       entry_type:    employee_connection | explicit_opt_out | manual | negative_reply | replied
--       reason:        client | event_contacted | manual_offboard_eligible | manual_sheet |
--                       meeting_dnc | reply_dnc | sales_personal_outreach | unsubscribe
--       date_precision: derived | unknown  (values observed; not exhaustive by design)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1) dnc_registry
-- ----------------------------------------------------------------------------
-- "id" mirrors the n8n Data Table's own row id 1:1 (useful for exact diffing in Phase 2's delta
-- pusher / nightly reconcile — a row that vanishes or changes id on the n8n side is a real signal,
-- not noise). identity_key gets its OWN UNIQUE constraint per the brief, separate from the
-- primary key, since it is the natural lookup key for Clay (never null, per the verified fact
-- above) while "id" stays the sync anchor.
--
-- "createdAt" / "updatedAt" are camelCase on purpose — that is the exact, verbatim n8n column
-- name (its Data Table system columns), and the brief asks for identical field names, not a
-- style pass. Postgres folds unquoted identifiers to lowercase, so these two are double-quoted
-- here and MUST be double-quoted in every future query too (Clay's Lookup config included) or
-- Postgres will look for "createdat"/"updatedat" and fail to find the column. This is called out
-- again in README_STEFAN.md so it isn't a silent trap.
CREATE TABLE IF NOT EXISTS dnc_registry (
  id                     bigint PRIMARY KEY,
  identity_key           text NOT NULL,
  norm_v                 text NOT NULL,
  linkedin_url_norm      text,
  email_lc               text,
  full_name              text,
  pipedrive_person_id    bigint,
  entry_type             text NOT NULL,
  reason                 text NOT NULL,
  source                 text NOT NULL,
  source_ref             text,
  source_signal          text,
  correlation_id         text NOT NULL,
  date_precision         text NOT NULL,
  expiry_review_pending  boolean NOT NULL DEFAULT false,
  offboard_removable     boolean NOT NULL DEFAULT false,
  also_flagged           text NOT NULL DEFAULT '[]',   -- JSON-encoded string, verbatim from n8n —
                                                        -- text, not jsonb, so Phase 2's straight
                                                        -- copy never needs a shape conversion.
  projections_state      text NOT NULL DEFAULT '{}',   -- same: JSON-encoded string, not jsonb.
  owner_tag              text,
  status                 text NOT NULL,
  added_at               timestamptz NOT NULL,
  removed_at             timestamptz,
  removed_reason         text,
  reply_category         text,
  expires_at             timestamptz,
  "createdAt"            timestamptz NOT NULL,
  "updatedAt"            timestamptz NOT NULL,

  CONSTRAINT dnc_registry_identity_key_key UNIQUE (identity_key)
);

COMMENT ON TABLE dnc_registry IS
  'Read-only projection of the n8n DNC ledger (dataTableId UOgKwlGsL28lX61O). Written ONLY by the '
  'Phase 2 sync job via the secret key, which bypasses RLS. Every other consumer (Clay, anon, '
  'authenticated) is read-only by policy, not just by convention — see the RLS section below.';
COMMENT ON COLUMN dnc_registry.identity_key IS
  'LinkedIn slug if a matchable /in/ URL was supplied, else the lowercased email. Never null for '
  'any row that made it into this table — see NORMALIZATION_RULES.md.';

CREATE INDEX IF NOT EXISTS dnc_registry_email_lc_idx ON dnc_registry (email_lc);
CREATE INDEX IF NOT EXISTS dnc_registry_linkedin_url_norm_idx ON dnc_registry (linkedin_url_norm);
CREATE INDEX IF NOT EXISTS dnc_registry_pipedrive_person_id_idx ON dnc_registry (pipedrive_person_id);
CREATE INDEX IF NOT EXISTS dnc_registry_status_idx ON dnc_registry (status);

-- ----------------------------------------------------------------------------
-- 2) dnc_registry_meta
-- ----------------------------------------------------------------------------
-- One row PER SYNC RUN, not a single overwritten status row — an append-only log, matching this
-- project's own established observability convention elsewhere (never silently discard history).
-- "the latest sync" is just `ORDER BY last_sync_at DESC LIMIT 1`; Phase 2's own writer decides the
-- exact cadence and what "source" values it uses (e.g. 'initial_load' | 'delta_push' |
-- 'nightly_reconcile').
CREATE TABLE IF NOT EXISTS dnc_registry_meta (
  id             bigserial PRIMARY KEY,
  last_sync_at   timestamptz NOT NULL,
  row_count      bigint NOT NULL,
  source         text NOT NULL,
  "createdAt"    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE dnc_registry_meta IS
  'Append-only sync-run log for dnc_registry. One row per sync (initial load / delta push / '
  'nightly reconcile) — read the latest with ORDER BY last_sync_at DESC LIMIT 1, never assume '
  'there is only one row.';

CREATE INDEX IF NOT EXISTS dnc_registry_meta_last_sync_at_idx ON dnc_registry_meta (last_sync_at DESC);

-- ----------------------------------------------------------------------------
-- 2b) dnc_domains — added 2026-09-09, Company DNC (banned domains, Clay export: 1,373 rows,
-- Created At / Updated At / Master Domain). A SEPARATE table from dnc_registry on purpose, not a
-- row inside it: a domain block is a different kind of thing from a person DNC entry (whole-company
-- scope, no identity_key-shaped value, no reply/entry_type lifecycle) — see the recommendation in
-- CREATE_DNC_DOMAINS_TABLE.md for the full reasoning on why the n8n side is a separate Data Table
-- too, never a "domain entry class" folded into dnc_registry_dev.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dnc_domains (
  domain      text PRIMARY KEY,   -- lowercased, no leading "www.", e.g. 'acme.com'
  added_at    timestamptz NOT NULL,
  source      text NOT NULL DEFAULT 'clay_company_dnc_import',
  reason      text,               -- nullable -- the source CSV carries none
  status      text NOT NULL DEFAULT 'active'
);

COMMENT ON TABLE dnc_domains IS
  'Read-only projection of the n8n company-domain blocklist. Same read-only-by-RLS contract as '
  'dnc_registry — see the policy section below. domain is lowercased with any leading "www." '
  'stripped at import time (see NORMALIZATION_RULES.md); free-mail domains (gmail.com etc.) are '
  'REJECTED at n8n import time, never even reaching this table — one such row would block '
  'thousands of real prospects.';

CREATE INDEX IF NOT EXISTS dnc_domains_status_idx ON dnc_domains (status);

ALTER TABLE dnc_domains ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "read for anon/authenticated" ON dnc_domains;
CREATE POLICY "read for anon/authenticated" ON dnc_domains
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- No INSERT/UPDATE/DELETE policy here either — same reasoning as dnc_registry above.

-- ----------------------------------------------------------------------------
-- 3) Row Level Security — dnc_registry / dnc_registry_meta
-- ----------------------------------------------------------------------------
-- RLS default-denies everything once enabled unless a policy explicitly allows it. We add ONE
-- policy (SELECT, for anon + authenticated) and deliberately no INSERT/UPDATE/DELETE policy on
-- either table — so the publishable key (anon/authenticated role) can read but structurally
-- cannot write, insert, or delete, no matter what request it sends. The secret key's service_role
-- BYPASSES RLS entirely by design (this is Supabase/Postgres platform behavior, not something this
-- script configures) — that is how Phase 2's server-side delta pusher will still be able to write
-- despite there being no write policy here.

ALTER TABLE dnc_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE dnc_registry_meta ENABLE ROW LEVEL SECURITY;

-- DROP + CREATE, not a bare CREATE: Postgres has no "CREATE POLICY IF NOT EXISTS", so a second
-- paste of this script (re-running after a partial failure, say) would otherwise error out here
-- even though everything above it is safely idempotent.
DROP POLICY IF EXISTS "read for anon/authenticated" ON dnc_registry;
CREATE POLICY "read for anon/authenticated" ON dnc_registry
  FOR SELECT
  TO anon, authenticated
  USING (true);

DROP POLICY IF EXISTS "read for anon/authenticated" ON dnc_registry_meta;
CREATE POLICY "read for anon/authenticated" ON dnc_registry_meta
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- No CREATE POLICY for INSERT/UPDATE/DELETE on either table, on either role — intentional. Do not
-- add one "to make Clay writes work"; Clay should never write to this table at all (see README).

-- ----------------------------------------------------------------------------
-- End of Phase 1. Phase 2 (initial load + delta pusher + nightly reconcile) is a separate script,
-- not run yet — waiting on Nik's word per the brief.
-- ----------------------------------------------------------------------------
