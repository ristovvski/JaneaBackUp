# Normalization v1 (FROZEN)

`norm_v = "v1"`. Every ledger writer stamps `norm_v` on the row. Readers must **not** silently
"improve" matching rules — a rule change is a **v2**: bump `norm_v`, migrate/backfill deliberately,
and keep v1 rows matchable. Canonical implementation: [`lib/normalize_v1.js`](lib/normalize_v1.js)
(embedded verbatim in every `DNC__*_v1` Code node; drift-checked by `tests/dnc_contract_tests.js`).

## LinkedIn
1. `trim`, then **lowercase** the whole URL.
2. Extract the slug via `/\/in\/([^/?#]+)/` — everything after `/in/`, stopped at the first
   `/`, `?`, or `#` (this **strips query, fragment, and trailing path**).
3. **Percent-decode** the slug (`decodeURIComponent`, guarded).
4. Strip trailing slashes; trim.
5. Canonical form: `https://www.linkedin.com/in/{slug}`.
6. **Non-`/in/` URLs** (company, school, sales-navigator, bare handles, anything without `/in/`) →
   `linkedin_unmatchable = true`, no `linkedin_url_norm`. The caller routes these to
   conflict/alert rather than guessing an identity.

`linkedin_slug` is the bare `{slug}`; `identity_key` uses the slug (not the full URL).

## Email
- `trim` + **lowercase** only.
- Minimal shape check: must contain `@` with a `.` after it, else `email_lc = null` +
  `email_shape_invalid` note (don't store junk as an identity).
- **NO plus-tag stripping, NO dot stripping in v1.** Rationale (documented so v2 is a conscious
  choice): provider-specific canonicalization is unsafe as a *merge* key.
  - Dot-insensitivity and `+tag` are **Gmail-specific**; applying them globally would merge
    genuinely distinct addresses on other providers.
  - A false merge in a **suppression** ledger is the dangerous direction: it would suppress /
    reveal-as-DNC a person who never opted out (or collapse two real people into one row).
  - Under-merging is recoverable (two rows, both correctly suppressed); over-merging is not.
  So v1 treats the address as an opaque lowercased string. If evidence later shows a real
  duplicate-identity problem, v2 can add *provider-aware* canonicalization with a backfill plan.

## identity_key
`linkedin_slug` if LinkedIn is matchable, else `email_lc`, else `null`. A `null` identity_key means
the input is unusable → UpsertLedger routes to conflict/alert; CheckLedger returns a usage hint.

## Duplicate tolerance (amendment 2)
No unique constraint exists on the table, so two rows can share an identity (races, imports,
pre-v1 data). Therefore:
- **CheckLedger** reads *all* rows for an identity and reports **strongest-entry_type-wins**.
- **UpsertLedger**, whenever it encounters >1 row for the resolved identity, **self-heals**:
  merges onto the strongest/earliest "primary" and soft-removes the extras
  (`status=removed`, `removed_reason='dedup_self_heal'`).

## Merge rules (v1) — see [`lib/merge_v1.js`](lib/merge_v1.js)
- **Conflict**: both identifiers present & matchable but resolving to different identities →
  **no write** + alert. Human resolves.
- **Strongest wins**: `explicit_opt_out > negative_reply > replied > employee_connection > manual`.
  `entry_type` is monotonic — **never downgraded** (explicit_opt_out is never weakened).
- **Source append**: incoming `source` unioned into the existing comma-list, de-duped.
- **Fill-if-empty** for identity/enrichment fields (existing non-empty values preserved).
- **expires_at recompute** per lifecycle: `explicit_opt_out`/`employee_connection` → `null`
  (permanent); `replied`/`negative_reply` → `added_at + DNC_TTL_MONTHS` (CONFIG, default **6**);
  `manual` → permanent unless an explicit expiry is supplied upstream.
- **Reactivation**: a new event on an `expired`/`removed` row re-suppresses (`status=active`,
  fresh `added_at`).
- **Idempotency**: `added_at` is preserved on active rows, so `expires_at` is a pure function of
  `(added_at, entry_type, ttl)` → a replayed event produces an identical row ⇒ `action='noop'`.
  This is the idempotency mechanism (no separate seen-marker needed for correctness).
