# DNC lookup in Supabase: how Clay asks "may we contact this person?"

Supersedes `SUPABASE_PROJECTION_build/README_STEFAN.md`, which still describes Phase 1 (empty
tables). Everything below was re-measured against the live project on 2026-09-24.

## What this is

A **read-only mirror** of the n8n DNC ledger in Supabase Postgres. Clay can look up DNC status here
without calling the n8n gate webhook for every row. n8n is the only writer: a delta pusher sends new
rows and a nightly reconcile repairs any drift. The mirror is never the source of truth. If it
disagrees with n8n, n8n is right.

| table | what one row is | live, 2026-09-24 |
|---|---|---|
| `dnc_registry` | one DNC **person** (identity) | 25,864 rows, 25,858 `active` |
| `dnc_domains` | one banned **company** domain: everyone at it is DNC | 1,373 rows |
| `dnc_registry_meta` | one sync run: when, how many rows, which job | freshness check, not a lookup |

Both tables use the same `status` convention. Only `active` blocks. A `removed` row was on the list
and has been cleared: it is tombstoned, not deleted, and it does **not** block.

## The recommended call: `dnc_check`

One call answers both questions: is the person on the list, and is their company on it.

```
POST https://<project-ref>.supabase.co/rest/v1/rpc/dnc_check
apikey: <publishable key>
Authorization: Bearer <publishable key>
Content-Type: application/json

{"p_linkedin_url": "https://www.linkedin.com/in/jane-doe", "p_email": "jane@acme.com"}
```

Either argument may be `null`. Send **both** whenever you have both. That is the point of the
function (see "Why not two Lookup columns" below).

The answer is **the pre-add gate's verdict**, field for field, so Clay and the gate can never
disagree about a person:

```json
{
  "gate_result": "BLOCKED",
  "reason": "negative_reply / campaign_reply",
  "registry_row_ref": 12345,
  "blocked": true,
  "block_reasons": ["person_dnc"],
  "identity": {"identity_key": "jane-doe", "linkedin_slug": "jane-doe",
               "linkedin_url_norm": "https://www.linkedin.com/in/jane-doe", "email_lc": "jane@acme.com"},
  "domain": "acme.com",
  "persons": [{"id": 12345, "identity_key": "jane@acme.com", "matched_by": "email", "status": "active",
               "reason": "...", "entry_type": "...", "source": "...", "reply_category": "...",
               "added_at": "...", "expires_at": null, "removed_at": null, "expired_but_active": false}],
  "company": null,
  "norm_v": "v1"
}
```

- **`gate_result`**: `OWN_TEAM`, `BLOCKED`, `UNRESOLVABLE` or `CLEAN`, decided in that order,
  exactly as the pre-add gate decides it:
  1. an `@janeasystems.com` email is `OWN_TEAM` (our own people, never in any list);
  2. an email whose domain is an active `dnc_domains` row is `BLOCKED`, reason `company_dnc / <domain>`;
  3. no usable LinkedIn URL or email is `UNRESOLVABLE` (it could not be checked, so it is not cleared);
  4. an active registry row for the person is `BLOCKED`, reason `<entry_type> / <source>` of the
     strongest row (`explicit_opt_out` > `negative_reply` > `replied` > `employee_connection` >
     `manual`, then the oldest);
  5. otherwise `CLEAN`, with reason `was <entry_type> until <date>, currently clean` if the person
     only has removed rows.
- **`blocked`**: `true` for `BLOCKED` and `OWN_TEAM`. Gate on it, but treat `UNRESOLVABLE` as
  "not checked", not as clean.
- **`block_reasons`**: every check that fired, not only the winning one: `own_team`, `company_dnc`,
  `person_dnc`.
- **`registry_row_ref`**: the id of the registry row that blocked (person blocks only).
- **`persons`**: every registry row this person could be filed under, with `matched_by` saying how
  it was found. Use `reason` / `entry_type` if you want to show why.
- **`expired_but_active`**: the row is past `expires_at` but still `active`. **It still blocks.**
  Whether an expired row should stop blocking is a policy decision for Nik. The function does not
  make it.

In Clay: an HTTP API column, `POST`, the URL above, body built from the lead's LinkedIn URL and
email columns, then a formula column reading `gate_result`.

### Status: written and tested, NOT deployed yet

`DNC_CHECK.sql` must be pasted into the Supabase **SQL editor** once. PostgREST cannot create
functions, and n8n's credential cannot either. Until then `rpc/dnc_check` answers
`404 PGRST202`. Checked live 2026-09-24:

- every column the function reads exists in the live tables
- the function has been executed in real Postgres 16 against the real schema file, with
  normalization identical to the production JavaScript on 28 documented cases and 600 fuzzed inputs
  (`test_dnc_check.mjs`)
- on 13 fixture inputs its verdict is identical to the gate's own classifier code (`Classify Batch`),
  run on the same rows; a deliberately broken copy of the function fails that comparison

After deploying, run `test_dnc_check_postgrest.mjs` with the publishable key. It proves that the
Clay key may call the function, that normalization matches, and that strangers are clean. Given a
known email, domain and LinkedIn URL from the table editor (environment variables, never committed),
it also proves blocking, the `company_dnc` reason, and that mangled forms of a LinkedIn URL resolve
to the same row.

## Why not two Lookup columns

The Phase 1 notes set up two Supabase Lookup columns:

1. `dnc_registry.identity_key` = a formula computing the identity key, and
2. `dnc_domains.domain` = the email domain.

The **company** lookup (2) is correct. The **person** lookup (1) misses people. `identity_key` is
"the LinkedIn slug if one resolves, otherwise the email". So a person who entered the registry by
**email** (a Smartlead reply, say) is keyed by that email. When Clay later sees the same person
**with** a LinkedIn URL, the formula produces the slug, and the lookup finds nothing.

Measured live: **408 active people are keyed by email with no LinkedIn on file.** Any of them can
come back through Clay with a LinkedIn URL and pass a single-key lookup unblocked. The n8n ledger
avoids this: `DNC__UpsertLedger__v1` looks up by LinkedIn **and** by email. `dnc_check` does the
same.

If you must use native Lookup columns anyway, you need **three** of them, and any `active` match
blocks:

| lookup | table.column | your value |
|---|---|---|
| person by LinkedIn | `dnc_registry.linkedin_url_norm` | `https://www.linkedin.com/in/` + slug |
| person by email | `dnc_registry.email_lc` | trimmed, lowercased email |
| company | `dnc_domains.domain` | everything after `@` in the lowercased email (no `www.` stripping: the gate does not strip it either) |

## Normalization

Your values must be byte-for-byte what `normalizeIdentityV1` produces. `NORMALIZATION_RULES.md`
has the algorithm and the worked examples. Its addendum lists four details that only the code
states. `dnc_check` does the normalization for you, which is another reason to prefer it.

## Read-only, by design

The publishable key (`sb_publishable_…`) can only **read** these tables. There is no insert, update
or delete policy for it (Row Level Security enforces this). `dnc_check` is `SECURITY INVOKER`, so it
reads through those same policies and grants nothing more. Corrections to the registry go through
the normal DNC process in n8n, never through a direct Supabase write.

## One gotcha in raw SQL

`"createdAt"` and `"updatedAt"` are camelCase, copied verbatim from n8n. In the SQL editor they need
double quotes. Clay's UI never hits this.
