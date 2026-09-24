# Identity normalization rules — for Clay's formula column

This is the exact algorithm behind `identity_key` in `dnc_registry` (source: `normalizeIdentityV1`
in `DNC_OBS_P1_build/subworkflows/lib/normalize_v1.js`, frozen as v1 — every row in the table
carries `norm_v = 'v1'`). All 5 worked examples below were run through the real function, not
hand-traced — copy them verbatim into a test to confirm Clay's formula matches byte-for-byte.

## The algorithm, in order

**Step 1 — try LinkedIn first.** If a `linkedin_url` is present:
1. Lowercase the entire URL string.
2. Find `/in/` in it. **If `/in/` is not present at all** (company pages, school pages, Sales
   Navigator links, bare handles, anything else) — LinkedIn is unmatchable. Skip straight to Step 2
   (email); the LinkedIn value contributes nothing, even though it was supplied.
3. If `/in/` is present, take everything after it up to the next `/`, `?`, or `#` — whichever comes
   first.
4. Strip trailing slash(es) from that piece.
5. URL-percent-decode it (e.g. `%c3%a9` → `é`).
6. Strip trailing slash(es) again (yes, the real code does this twice — once before decoding, once
   after; mirror both steps, don't collapse them into one).
7. If the result is an empty string after all that, LinkedIn is unmatchable — go to Step 2.
8. Otherwise this is the **LinkedIn slug**. The canonical URL is
   `https://www.linkedin.com/in/` + slug. **The slug is the identity_key. Stop here — do not also
   look at email.**

**Step 2 — email, only if Step 1 didn't produce a slug.**
1. Trim whitespace, lowercase the whole address.
2. It must contain `@` (not as the very first character) and a `.` somewhere after the `@`. If not,
   the email is invalid and contributes nothing.
3. Otherwise this is `email_lc` — trim + lowercase **only**. No plus-tag stripping, no dot removal.
   `email_lc` is the identity_key.

**Step 3 — neither resolved.** `identity_key` is `null`. This input never reaches `dnc_registry` —
the caller (`DNC__UpsertLedger__v1`) intercepts an unresolvable identity before ever writing a row.
This is why `identity_key` is NULL-free across all 33,138 rows in the live table today, verified
directly, not assumed.

## 5 worked examples (verified against the real function)

| # | Input | linkedin_url_norm | email_lc | **identity_key** |
|---|---|---|---|---|
| 1 | `linkedin_url: "HTTPS://WWW.LinkedIn.com/in/Jane-Doe/?utm_source=x&utm_medium=y"` | `https://www.linkedin.com/in/jane-doe` | — | **`jane-doe`** |
| 2 | `linkedin_url: "https://www.linkedin.com/in/Andr%C3%A9-Martin/"` | `https://www.linkedin.com/in/andré-martin` | — | **`andré-martin`** |
| 3 | `email: "  John.SMITH+sales@Example.COM  "` | — | `john.smith+sales@example.com` | **`john.smith+sales@example.com`** |
| 4 | `linkedin_url: "https://www.linkedin.com/company/acme-corp"`, `email: "Jane@Acme.com"` | `null` (not an `/in/` URL — unmatchable) | `jane@acme.com` | **`jane@acme.com`** |
| 5 | `full_name: "Lule Salihu"` only, no email, no linkedin_url | `null` | `null` | **`null`** — never written to the table |

Notes on the examples:
- **#1** — the case-insensitivity, trailing slash, and query-string stripping all happen in one
  pass; the query string (`?utm_source=x&utm_medium=y`) is discarded because the slug extraction
  stops at the first `?`.
- **#2** — percent-decoding happens AFTER lowercasing, so a raw `%C3%A9` (uppercase hex digits, as
  many exports produce) still decodes correctly — percent-encoding hex digits are case-insensitive,
  lowercasing the letters around them doesn't break the decode.
- **#3** — this is deliberate, not a gap: v1 does **not** strip `+sales` or normalize dots in the
  local part, because doing so risks merging two genuinely different people's DNC status under one
  key (a false-merge risk, judged worse than the false-split risk of leaving plus-tags alone).
- **#4** — the important nuance: even though BOTH a `linkedin_url` and an `email` were supplied,
  LinkedIn contributes *nothing* once it's judged unmatchable — it is not merely deprioritized, it
  is dropped, and email becomes the sole key.
- **#5** — this is the boundary case that explains the "never blank" guarantee: it isn't that the
  normalizer refuses to return null, it's that nothing with a null identity_key ever reaches this
  table in the first place.

## For Stefan's Clay formula column

Mirror the algorithm above step-by-step, not just the 5 examples — a formula that only special-cases
these 5 inputs will diverge on the next real row. In particular: LinkedIn always wins over email
when it resolves (never compute "prefer whichever is present"), and the double trailing-slash-strip
in Step 1 is not a typo to simplify away.
