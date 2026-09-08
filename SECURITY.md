# What is in here, what was kept out, and what must not change

## This repository must stay private

It contains, unavoidably, real data about real people:

* **Prospect names, email addresses and LinkedIn URLs** throughout the task logs, repair maps and
  incident write-ups — the specific rows are the evidence, so they cannot be anonymised without
  destroying the audit trail.
* **Internal Slack audits** — `docs/COMMS_AUDIT_build/` and `docs/slack_audit/` quote colleagues'
  messages and DMs.
* **Operational runbooks** — how to retire registry rows, how to fire a projection.

Making it public would publish all three. Anonymous access was verified as closed at the time of the
first push; verify it again before granting access to anyone outside the team.

## Redacted on the way in

n8n webhook paths are replaced with readable placeholders:

| placeholder | endpoint |
|---|---|
| `{{WEBHOOK_WF1_HEYREACH_RECEIVER}}` | WF-1, the HeyReach receiver |
| `{{WEBHOOK_WF2_SMARTLEAD_RECEIVER}}` | WF-2, the Smartlead receiver |
| `{{WEBHOOK_I04_PIPEDRIVE_EVENTS}}` | I-04 Pipedrive event intake |
| `{{WEBHOOK_DNC_S4_RETIREMENT}}` | DNC row retirement / removal |
| `{{WEBHOOK_DNC_ARCHIVED_IMPORT}}` | archived-responder import |
| `{{WEBHOOK_DNC_INTENT_CHECK}}` | DNC intent-vs-reality check |
| `{{WEBHOOK_DNC_CLAIMS_PRUNE}}` | claims-table prune |

**Why:** an n8n webhook path is the only authentication those endpoints have. Anyone holding the
Smartlead receiver's path can inject fabricated reply events into the pipeline — creating leads,
writing activities, firing Slack alerts, and entering people into the DNC registry. The path *is*
the credential. It has been ruled that the exposed WF-1 secrets will not be rotated, which makes a
durable copy of them in a git history worse rather than more acceptable: git history is not
retractable by editing a file later.

The real values live in n8n and in the local `.env`. Resolve a placeholder there when you need it.

## Scrubbed out of the chat history

Any value present in the local `.env` is replaced with `{{SECRET:<KEY>}}` wherever it appears. This
is not theoretical: **a live Smartlead API key was pasted into a session on 2026-07-23** and appears
in two chat files. It is scrubbed in this repository — and it is still live in Smartlead, so it
should be rotated there regardless of what this repository contains.

One webhook path (`dnc-projections-swe…`) appears only in the chat history and in no document; the
default-redact rule caught it. That is the reason the rule redacts unknown endpoints instead of
passing them through.

## Never committed

| kind | reason |
|---|---|
| `*.py`, `*.ps1` | deployment tooling, not documentation. Excluded by scope, not by risk — one word adds it. |
| `*.json` | workflow exports and API captures: credential *references*, live webhook paths, raw prospect payloads. |
| `*.log`, `*.out` | run output. |
| `.env`, `*.pem`, `*.key`, `*.crt` | credentials and the CA bundle. |
| tool results in the chat history | raw API responses — the bulk of the bytes and the likeliest carrier of both secrets and unfiltered personal data. |
| model reasoning in the chat history | not documentation. |

`.gitignore` enforces all of it, so a careless `git add .` cannot sweep a workflow backup in.

## The gate that runs before every commit

`gtm_docs_export/build_docs_repo.py` fails closed. Before anything is staged it asserts:

1. **No `.env` secret value** appears anywhere in the tree — checked by literal match against every
   value in `.env` longer than 12 characters, not by pattern-guessing.
2. **No unredacted webhook path** survives — any `/webhook/<path>` not in the placeholder table is
   replaced with `{{WEBHOOK_REDACTED}}` rather than passed through, so an endpoint added later is
   redacted by default instead of leaking by omission.

If either check fails, nothing is committed.

## If a secret does reach the history

Rewriting history is the only real remedy — the file edit is not enough, the blob stays reachable.
Rotate first, rewrite second, and assume the value is compromised from the moment it was pushed.
