# What is in here, what was removed, and what must not change

## This repository must stay private

It holds operational runbooks, internal Slack audits that quote colleagues, and the code that writes
to the CRM. Personal data about prospects has been pseudonymized (below), but the documents still
describe real campaigns and real companies. Do not change its visibility.

## Removed from the ENTIRE history, not just the current tree

A collaborator can read every commit, so cleaning only the latest one protects nothing. On
2026-09-24 every commit was rewritten blob by blob, and the rewritten history is what `main` now is.

**Credentials and callable endpoints**

| what | replaced with |
|---|---|
| any value from the local `.env` | `{{SECRET:<KEY>}}` |
| every webhook path **registered on our n8n** (28, read from the live instance), wherever it appears — bare, in a table, or inside a URL | `{{WEBHOOK_<NAME>}}` |

An n8n webhook path is the only authentication its endpoint has: holding the Smartlead receiver's
path is enough to inject fabricated reply events, create leads, fire alerts and write DNC rows.

**Why this had to be redone.** The 9-08 export only redacted the `/webhook/<path>` form. Every *bare*
mention of the two production receiver paths — in inventory tables, prose, class maps — went through,
and sat on `main` in 11 and 12 blobs until this rewrite. The rule is now built from the list of paths
n8n actually serves, and it matches the path itself, not a URL shape.

**People**

| what | replaced with |
|---|---|
| external email addresses | `pii-<h8>@example.invalid` |
| `linkedin.com/in/<slug>` | `linkedin.com/in/pii-<h8>` |
| 242 prospect names found in our own repair maps, populations and task logs | `Person-<h8>` |

Tokens are an HMAC over a salt that exists only on the operator's machine: the same person is the same
token everywhere, but a token cannot be reversed from the repository. **Team names and internal
addresses are kept on purpose** — a runbook has to be able to say who to ask.

**Stated residual:** names are found from structured records we hold plus a list of people named only
in prose. A prospect mentioned only in free text, and absent from both, would not be matched. The
list is re-built from the whole tree on every export, so the residual shrinks as records are added —
it does not reach zero by construction.

**Removed outright**

* `chat-history/sessions/` — the raw working-session transcripts, from every commit. They were bulk
  person data by nature: every prospect ever discussed, in context, with company and title, and still
  re-identifiable after pseudonymization. The decision record
  (`chat-history/RULINGS_AND_INSTRUCTIONS.md`) stays, cleaned.
* all `*.json` from the project mirror — workflow exports, API captures, repair maps, populations,
  fixtures with real people. `icp-scoring/` keeps its own reviewed JSON (configuration and a golden
  set of companies).

## Never committed

| kind | why |
|---|---|
| `.env`, `*.pem`, `*.key`, `*.crt` | credentials |
| `scrub.sed`, `_pii*`, `_live_webhook*`, `_rewrite_commit_map*` | each contains exactly what the scrub removes — the secrets are the sed patterns, the salt and mapping reverse the pseudonyms, the commit map names the dirty SHAs |
| `gtm_docs_export/` | where all of the above live, on the operator's machine |

`.gitignore` enforces every line of this table.

## The gate

`gtm_docs_export/verify_history.py <ref>` scans **every blob and every commit message reachable from
the ref** for six things — `.env` values, registered webhook paths, callable host+`/webhook` URLs,
external emails, LinkedIn profiles, prospect names — and exits 0 only if all six are zero.

It refuses a vacuous pass: a history with no blobs, or an empty tip, is reported as a **failure**.
That floor exists because the first run of the rewrite produced 47 commits with empty trees and the
first version of the verifier called them clean. Its own self-test (`selftest_verifier.py`) feeds
each check a positive and a negative, 15/15.

## If a secret does reach the history

Editing the file is not enough — the blob stays reachable. Rotate the secret, rewrite the history,
force-push, and ask GitHub Support to purge cached views and orphaned objects. Treat the value as
compromised from the moment it was pushed.
