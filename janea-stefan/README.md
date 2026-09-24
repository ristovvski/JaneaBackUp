# janea-stefan: the second-operator package

Read in this order:

| # | file | what it gives you |
|---|---|---|
| 1 | `README_OPERATOR.md` | what runs, what to check every morning, how a change is deployed, what never to do |
| 2 | `ACCESS_MAP.md` | every system, the role you need in it, and the checklist Nik works through to grant it |
| 3 | `SUPABASE_LOOKUP.md` | the DNC mirror, and how Clay asks "may we contact this person?" |
| 4 | `NORMALIZATION_RULES.md` | the exact identity algorithm (frozen v1), plus what only the code says |
| 5 | `DNC_CHECK.sql` | the one-call DNC check. It returns the pre-add gate's own verdict (`OWN_TEAM` / `BLOCKED` / `UNRESOLVABLE` / `CLEAN`, same reasons, same row). Paste it into the Supabase SQL editor once; it is not deployed yet |
| 6 | `test_dnc_check.mjs` | runs `DNC_CHECK.sql` in real Postgres (PGlite) against the real schema, and against the gate's own classifier code when that is available: `npm i @electric-sql/pglite@0.2 && node test_dnc_check.mjs` |
| 7 | `test_dnc_check_postgrest.mjs` | the same checks against the deployed function, with the Clay key |
| 8 | `ICP_CLAY_CONTRACT.md` | ICP scoring: the seven keys n8n sends Clay, the callback column and the twenty keys it must return, what the live score formula provably computes, and the Clay columns n8n depends on |

`README_OPERATOR.md` and `ACCESS_MAP.md` are copies of the files at the repository root. The root
copies are the maintained ones.

**No credentials are in this folder, or anywhere in the repository.** Where a document needs one,
it names the n8n credential or `.env` key, never the value. You receive keys from Nik directly.
