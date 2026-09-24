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
