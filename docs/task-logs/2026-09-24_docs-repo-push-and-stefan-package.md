# Docs repo: branch question, push to main via PR, janea-stefan completion — 2026-09-24

## 1. Is 0c37555 the pre-squash root this session created? — **No**

- This session (the DNC session) never ran a git command against the repo before today; its whole
  transcript has zero git/repo tool calls before 2026-09-24 14:52Z.
- `0c37555` is a parentless root authored 2026-09-15 13:01 **+0000**. Every commit made from this
  machine carries **+0300**; `claude/<adjective>-<id>` is the branch pattern cloud sessions create.
- Its tree is an older export: it differs from `origin/main`'s root in 45 files.
- Per the rule given ("if no → keep until read"): **kept**. Note the prod session's finding: it holds
  secrets (webhook paths) in 18 files, so keeping it keeps those readable on GitHub.

## 2. Push to main — **partial**

- The prod session had already fast-forwarded `main` 93af79e → 95da8f4 (ICP merge `d73a13c`, scrub +
  pseudonymize `9676be2`, runbook + janea-stefan `95da8f4`), with a restore-tested bundle first
  (`janea-full-backup-2026-09-24.bundle`). No force-push, nothing deleted. So **the ICP branch is
  already merged into main**: the ICP session's own PR would be empty and must not merge ICP again.
- My stacked branch built before I knew that was deleted (local only, never pushed).
- **Found on main: `SECURITY.md` and `chat-history/README.md` state the history was rewritten and the
  transcripts "removed from the whole history". False on main**: the history under `d73a13c` still
  carries the webhook paths and 35 raw session transcripts. Corrected in the sources
  (`gtm_docs_export/handover_docs/SECURITY.md`, `README.md`, `handover_sync.py`) and in this PR.
  Until the history rewrite runs, the repo must not be shared with anyone new.
- `verify_history.py --new-since <base> <ref>`: the PR gate (tip tree in full + every blob and commit
  message the PR adds). Positive control: over the ICP branch's own commits it reports DIRTY.

### Mistake caught by the prod session
My first re-sync used a worktree **inside** the project root; the mirror walked its own output and
recursed (431 levels, 116k files, 1.76 GB). Killed, worktree removed (robocopy mirror-delete for the
long paths), nothing committed or pushed. `handover_sync.py` now excludes its output worktree by name
and refuses any source file under it; the re-run's worktree is outside the root.

## 3. janea-stefan — **done except the live test (blocked on deploy)**

- `DNC_CHECK.sql` now returns **the pre-add gate's verdict**, field for field (`gate_result` OWN_TEAM /
  BLOCKED / UNRESOLVABLE / CLEAN, same precedence, `company_dnc / <domain>`, strongest-row pick,
  `registry_row_ref`). Domain taken exactly as the gate takes it (the old version stripped `www.`,
  the gate does not).
- Offline (PGlite, Postgres 16.4, real schema): **19/19**, including parity with the gate's own
  `Classify Batch` code on 13 inputs. Mutation test: reintroducing the `www.` strip and swapping two
  strength ranks turns 3 checks red.
- `test_dnc_check_postgrest.mjs` updated to the new contract; runs Dimitri (row 31310, active), a
  banned domain (`100programmers.com`, active), a guaranteed-clean identity, and five mangled forms
  of a known LinkedIn URL. Fixtures verified against today's Supabase dump; they live in a local
  scratch file, never the repo.
- **Blocked**: `rpc/dnc_check` → `404 PGRST202`, not deployed. No DDL path from here (no DB password,
  no Supabase access token; PostgREST cannot create functions). Needs one paste into the Supabase SQL
  editor, then the live test is one command.
- `ICP_CLAY_CONTRACT.md` written from the live workflow (nodes byte-identical to the repo):
  - Path A = 7 keys (`org_id, deal_id, domain, request_id, callback_url, requested_at, model_version`).
  - Path B = 20 keys (8 required, 12 optional, nothing else) since `a5ac404` "The table scores, n8n
    writes"; `engine/clay_callback_column.md` in the repo describes the older v6.0 contract.
  - Live failures documented: 16-key callbacks (ids missing) and 23-key callbacks (all 7 Path A keys
    echoed) both rejected; 20-key accepted since 22 Sep 12:14.
  - **Formula text not read**: Clay CLI 0.8.1 is refused by Clay (needs ≥ 1.3.0) and both CLI session
    and API key belong to another workspace. Behavioural proof instead: all 15 accepted live callbacks
    recompute exactly under rubric v6 (grades A/B, Stable/Accelerating observed; C, insufficient,
    Transitioning, Contracting not seen live).
  - **Found**: `icp-scoring/config/rubric_v6.json` — the generators' declared source — has never been
    committed on any branch; 20 files reference it. Values survive in `CONFIG.json` / `clay_score.py`.
- `NORMALIZATION_RULES.md` was already in the package (prod session's commit B).

## 4. Backup
The prod session's bundle predates its push but contains every parent of 95da8f4. A fresh bundle is
taken after this PR lands and before anything is deleted. Nothing was deleted by this session except
its own never-pushed local branch and its own runaway worktree.

## Improvable
- Deploy `DNC_CHECK.sql`, then run the live test (one command).
- Commit `rubric_v6.json` (ICP session's domain).
- Export the live Clay score/callback formula text into `icp-scoring/engine/`.
- History rewrite (filter-repo) before any collaborator is added.
