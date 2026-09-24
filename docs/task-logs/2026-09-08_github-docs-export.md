# 2026-09-08 — the chat, as documentation, in GitHub

**Ask:** «Нам нужно перенести чат в виде документации в github», with the remote supplied mid-task:
`https://github.com/Nkriv/Janea.git`, branch `main`.

**Result:** pushed. `Nkriv/Janea` @ `5d77f10`, 381 files, verified private.

## Done

* **Chat rendered as documentation.** All 35 session transcripts in this project (~92 MB of JSONL)
  rendered to 4.8 MB of markdown by `gtm_docs_export/extract_chat.py`, in two tiers:
  * `chat-history/RULINGS_AND_INSTRUCTIONS.md` — every human turn, all 705 of them, chronological
    and verbatim, each stamped with session and time. This is the decision record.
  * `chat-history/sessions/*.md` — the readable transcript per session. Human turns in full,
    assistant prose in full, every tool call collapsed to one line, tool *results* dropped.
* **Every document carried over.** 339 markdown files, path-for-path. Paths were deliberately not
  reorganised: the corpus cross-references itself by relative path, so a tidier tree would break
  every internal link. `INDEX.md` groups all 339 thematically instead (verified: 341 entries, no
  duplicates, nothing on disk missing from the index).
* **Front matter written for a reader who has never seen the stack** — `README.md` (the estate in a
  paragraph, a where-to-start table, and the one recurring lesson), `SECURITY.md`, `.gitignore`
  (markdown-only by default), `.gitattributes` (LF, so the next commit is not 339 files of CRLF).
* **Secret gate, fail-closed, run over the staged tree** — asserts no `.env` value survives
  (literal match, not pattern-guessing) and no unredacted `/webhook/` path survives. It blocked the
  first build, correctly:
  * a **live Smartlead API key**, pasted into a session on 2026-07-23, present in two chat files;
  * `/webhook/dnc-projections-swe…`, an endpoint that appears **only** in chat history and in no
    document — caught by the default-redact rule, which is why unknown endpoints are redacted
    rather than passed through.
* **Webhook paths replaced with named placeholders** (7 distinct, 17 occurrences). The path is the
  only authentication those endpoints hold; anyone with the Smartlead receiver's path can inject
  fabricated reply events — creating leads, writing activities, firing alerts, entering people into
  DNC. It has been ruled the exposed WF-1 secrets will not be rotated, which makes a copy in git
  history worse, not more acceptable: history is not retractable by editing a file later.
* **Visibility checked before and after the push**, anonymously — 404 both times, so the repository
  is not world-readable. This mattered: the corpus carries prospect names, addresses and LinkedIn
  URLs, plus internal Slack audits quoting colleagues.

## Improvable

* **Rotate the Smartlead API key.** It is scrubbed here, but it is still live in Smartlead and it
  sat in a local transcript in plaintext. The scrub protects the repository, not the key.
* **Re-run is not incremental.** `extract_chat.py` + `build_docs_repo.py` regenerate both trees, so
  every rebuild rewrites this session's transcript file and shows a diff. Fine for a periodic
  refresh; it would be noise as a per-commit hook.
* **Code is excluded by scope, not by risk** — `*.py` deployment tooling (the `p_*.py` deploy
  scripts, the linter, `deal_guard.py`) is arguably the more useful half of the estate for whoever
  maintains it next. One word adds it; it was left out because the ask was documentation.
* Two 2026-08-10 sessions share a title, and the two Slack-audit sessions are titled in Russian.
  The first filename scheme collapsed both pairs — an ASCII-only slug reduces a Cyrillic title to
  the empty string — and silently overwrote two whole sessions. Caught by diffing rendered session
  ids against the transcripts on disk rather than trusting the "35 sessions rendered" count. Names
  now carry the session id.

## Not done

* **No CI, no link checker.** 339 documents with relative cross-references, and nothing verifies
  they resolve after the copy. Worth a one-file GitHub Action if the repo is going to be maintained
  rather than archived.
* **No pruning.** Superseded documents (the `RULES_ARCHIVED_IGNORE/` set, ten `WF1_release_pack_*`
  generations of the same reference doc) went in as they stand. Deciding what is history and what is
  current is a judgement call about the estate, not about the export.
