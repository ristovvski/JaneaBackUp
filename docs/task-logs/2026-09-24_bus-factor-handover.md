# 2026-09-24 — bus-factor handover: the repo a second operator can take over

**Built locally, verified, NOT pushed.** The push is a force-push of `main` plus deletion of two
branches, which is irreversible for anyone who has fetched — it is held for Nik's explicit go.

## Done

| item | state |
|---|---|
| 1 SYNC | 1,227 project files (docs **and code**) mirrored onto the clean history; export gate passes |
| 2 ICP merge | ICP branch's 45 commits are the base of the new `main`; zero secret fragments anywhere in history |
| 3 PII | 415 files touched (84 webhook/credential, 363 person data); raw transcripts removed from every commit; mapping local-only |
| 4 README_OPERATOR.md | written from the live estate |
| 5 ACCESS_MAP.md | written; Pipedrive gap spelled out |
| purge request | draft at `gtm_docs_export/GITHUB_PURGE_REQUEST_DRAFT.md`, for Nik to send after the push |

Local branch `handover-main`: 49 commits (47 rewritten + sync + operator docs), 1,377 files.

## What GitHub holds today — found, and partly mine

**No `.env` credential value is on GitHub.** But **both production receiver webhook paths are, on
`main` itself** — in 11 and 12 blobs, and in **all 50** pre-rewrite commits, including my own two from
9-08. My 9-08 export gate only redacted the `/webhook/<path>` form; every *bare* mention — inventory
tables, class maps, prose — went straight through. An earlier force-push of `main` (by someone else,
before today) rewrote those two commits but did not remove them either.

So cleaning the tree would not have protected a new collaborator: `git log -p` reaches every commit.
The whole history was rewritten.

## How the scrub is built — from truth, not string shape

* **Webhook paths:** the 28 paths actually **registered on n8n**, read live. This is what proved the
  ICP branch's `icp-scored-clay-dev` / `wf-akuvo-001` hits are synthetic test fixtures on fake hosts
  (not registered) and must not be touched, and that the ICP DEV endpoints carry random tokens the
  ICP docs had already elided. Matched bare, anywhere.
* **Names:** 242 prospects, from our own repair maps / populations / task logs plus a list of people
  named only in prose. Team names and internal addresses kept on purpose.
* **`scrub.sed` did not exist** anywhere — not on this machine, not on either branch. Built from the
  rules above. **It cannot be committed:** its match patterns *are* the secrets. Same for the PII salt
  and mapping.

## The acceptance test and its floor

`verify_history.py` scans every blob, commit message and **path** reachable from a ref for seven
things and exits 0 only if all are zero. `selftest_verifier.py` feeds each check a positive and a
negative: **17/17**. On the final `handover-main`: **CLEAN** across 49 commits and 1,471 blobs.

ICP suite: **168/181 on both the original branch and the scrubbed tree, identical failure set** — the
scrub introduces zero failures. The **13 failures are pre-existing** on the ICP branch as pushed.

## Improvable — mine, and several would have been serious

1. **The first rewrite produced 47 EMPTY commits, and the first verifier called them clean.**
   `update-index --index-info` printed "Ignoring path" for every entry and **exited 0** — Python's
   text-mode stdin on Windows had turned `\n` into `\r\n`, so every path arrived as `name\r`. My
   wrapper only failed on non-zero exit codes. Had this been pushed, `main` would have been wiped.
   Caught only because "unique blobs: 0" looked wrong. Both the rewrite and the verifier now carry a
   non-vacuity floor.
2. **My own guard then miscounted.** Without `-z`, git quotes non-ASCII paths, and `startswith()`
   missed the 7 Cyrillic-named transcripts. The rewrite was right; the guard was wrong.
3. **A filename leaked a webhook path** — a task log named after a workflow whose webhook path is its
   kebab-case name. Contents were scrubbed; paths never were. The gate found it only because INDEX.md
   listed the file. The sync now renames and relinks, and the gate checks paths.
4. **The scrub broke an ICP test**: `https://user:pw@acme.io` matched as an email. Fixed with one
   shared rule used by both scrub and gate — two copies of it had already disagreed once.
5. My 9-08 gate — the origin of the leak. It was built on a URL shape instead of on the list of
   paths that exist.

## Decisions for Nik

1. **GO on the push:** force-push `handover-main` → `origin/main`, delete both `claude/*` branches.
2. Then send the purge request.
3. The 13 pre-existing ICP test failures — the cloud session's to look at.
4. `docs/COMMS_AUDIT_build/` keeps its Slack audit, which quotes colleagues. Pseudonymization covers
   prospects, not colleagues. Keep, or drop from history too?

## Second envelope (same day): branches, Stefan package, git identity

**Done**
- BRANCHES: GitHub has **2** `claude/*` branches, not 63 (see report table). Nothing deleted.
- GIT IDENTITY: `gtm-docs/.git/config` → `Claude (prod duty session) <noreply@anthropic.com>` (repo-local;
  global config untouched). History rewrite remaps only the 4 commits made under the wrong
  "Mykyta Kryvonos" identity; 27 "Mykyta"/"Mykyta Krivosheia" commits left alone pending Nik (REMAP_EXTRA).
- STEFAN PACKAGE `janea-stefan/` (8 files, in commit B of handover-main): README, README_OPERATOR,
  ACCESS_MAP, SUPABASE_LOOKUP (new; replaces the stale Phase-1 README_STEFAN), NORMALIZATION_RULES
  (+ addendum: 4 code-vs-prose details; prospect name in example 5 replaced by "Jane Roe"),
  DNC_CHECK.sql, test_dnc_check.mjs, test_dnc_check_postgrest.mjs.
- DNC_CHECK.sql: `dnc_check(p_linkedin_url, p_email)` → person by slug OR email + company domain.
  PGlite (Postgres 16.4) vs real schema file: 12/12, parity with normalize_v1.js 28 cases + 600 fuzz.
- PostgREST, live (via n8n "Supabase account" credential, throwaway probe workflow, deleted):
  every column the function reads exists (bad column → 400, non-vacuous); registry 25,864 rows /
  25,858 active; domains 1,373; **408 active people keyed by email with no LinkedIn** (the
  population the single identity_key Lookup can miss); `rpc/dnc_check` → 404 PGRST202 = NOT DEPLOYED.
- handover-main rebuilt: 49 commits, 1,389 files; verify_history CLEAN (now with check 1b);
  selftest 26/26; clobber 0/0; ICP tests 168/181 with a failure set identical to the original branch.

**Found (serious, fixed before any push)**
- A live **Supabase publishable key** was in chat-history/RULINGS (a pasted RLS-test curl). It was
  never in .env, so the exact-value gate could not see it; the ICP scanner's `bearer` rule did.
  Not on GitHub (0 commits on any remote ref). Fix: KEY_RULES in handover_scrub (sb_publishable_ /
  sb_secret_ / JWT shapes) + gate check 1b; proved the check fires on the pre-fix branch.
- The pseudonymizer was hashing SYNTHETIC fixtures (jane-doe, Jane@Acme.com…) — broke the DNC tests
  and garbled the worked examples, including the copy already in handover-main. Fix: enumerated
  SYNTHETIC_EMAILS / SYNTHETIC_SLUGS + shared is_pii_slug() used by scrub AND gate.
- ICP scanner's 1,099 findings classified (classify_scanner_hits.py, local): 27 distinct 40-hex =
  all live Pipedrive field keys; 188 UUIDs = n8n versionIds/node ids, lead ids, label ids, Clay
  public package ids, session path segments, Smartlead stats ids; webhook URLs = placeholders.
  One credential total (the Supabase key).

**Blocked**
- Deploying DNC_CHECK.sql needs the Supabase SQL editor (Nik or Stefan). Then run
  probe_dnc_check_live.py (ours) and test_dnc_check_postgrest.mjs (Clay key).
- Push / branch deletion / filter-repo: waiting for Nik's branch list and GO.

**Improvable**
- Bash heredoc ate backslashes 3 more times this segment (known trap) — each caught by a syntax
  error or a probe, but writing Python patches through Edit/`chr(92)` from the start avoids it.
- A generic secret gate built from .env values alone is blind to anything pasted; shape rules
  have to run beside it.

## Third envelope: backup first, nothing deleted

- "63 branches" does not match Nkriv/Janea: `git ls-remote` = 3 heads (main + 2 claude/*), no
  `git-init-…` branch. No local repo has more than 4 refs. So step 3 had no target; nothing deleted.
- BACKUP: `janea-full-backup-2026-09-24.bundle` (5,741,603 bytes, sha256 199e1e7b…1e35) in the project
  folder (outside the repo), `git bundle create --all` after a fresh fetch. Holds the pre-rewrite
  old main 9f0fa3d, which is NOT on GitHub (only gtm-docs and Documents/GitHub/Janea have it).
  Restore test: clone --mirror into scratchpad, fsck --full clean, 6/6 refs identical by sha+name,
  every GitHub ref present, 99/99 commits reachable; temp clone deleted. Copy sent to Nik.
- MERGE (no rewrite): `gtm_docs_export/build_merge_main.py` → merge-main = M (merge --no-ff ICP tip
  into main; main was its ancestor, 0 commits lost) + A (scrub/pseudonymize tree = handover-main~1)
  + B (ops docs + janea-stefan tree = handover-main). Pushed fast-forward: main 93af79e → 95da8f4.
  904 new blobs all clean; history under M still dirty (was already on GitHub).
- Collision: the DNC session messaged that Nik gave it the same push, arriving right after mine.
  Told it main had moved and to stack on 95da8f4; I push nothing more.
- Still pending: filter-repo (after branch cleanup, from a verified bundle); ICP session's keep list;
  DNC_CHECK.sql deploy; REMAP of the 27 "Mykyta" commits (only matters for the rewrite now).

## Close-out (Nik)
- Keep `claude/icp-scoring-…` (lands via the ICP session's PR). `dreamy-wozniak` pending the DNC
  session's answer on whether 0c37555 is its pre-squash root.
- filter-repo postponed: only after both PRs land, a verified bundle exists, and Stefan has cloned.
- This session is done on the repo; the DNC session owns further pushes.
