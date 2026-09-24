-- ============================================================================
-- dnc_domains — standalone (same table already included in dnc_registry_phase1.sql, extracted
-- here for a separate paste). Company DNC: banned domains, Clay export (Created At / Updated At /
-- Master Domain), 1,373 rows after clean/dedupe. Same RLS pattern as dnc_registry: read-only for
-- anon/authenticated, no write policy at all (writes only via the secret key, which bypasses RLS).
-- ============================================================================

CREATE TABLE IF NOT EXISTS dnc_domains (
  domain      text PRIMARY KEY,   -- lowercased, no leading "www.", e.g. 'acme.com'
  added_at    timestamptz NOT NULL,
  source      text NOT NULL DEFAULT 'clay_company_dnc_import',
  reason      text,               -- nullable -- the source CSV carries none
  status      text NOT NULL DEFAULT 'active'
);

COMMENT ON TABLE dnc_domains IS
  'Read-only projection of the n8n company-domain blocklist. Same read-only-by-RLS contract as '
  'dnc_registry. domain is lowercased with any leading "www." stripped at import time; free-mail '
  'domains (gmail.com etc.) are REJECTED at n8n import time, never even reaching this table -- '
  'one such row would block thousands of real prospects.';

CREATE INDEX IF NOT EXISTS dnc_domains_status_idx ON dnc_domains (status);

ALTER TABLE dnc_domains ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "read for anon/authenticated" ON dnc_domains;
CREATE POLICY "read for anon/authenticated" ON dnc_domains
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- No INSERT/UPDATE/DELETE policy -- intentional, same as dnc_registry.
