# Janea GTM automation — the estate, documented and operable

The written record and the operating code of the Janea Systems go-to-market automation estate: what
it is, how it behaves, what has broken, what was decided about it, and the scripts that change it.

**New operator? Start here, in this order:**

1. [`README_OPERATOR.md`](README_OPERATOR.md) — what to check every morning, how to read an
   execution, how to deploy a change, the never-list, where each secret lives.
2. [`ACCESS_MAP.md`](ACCESS_MAP.md) — every system, the role you need, and what you cannot diagnose
   without each one.
3. [`SECURITY.md`](SECURITY.md) — what was removed from this repository and why. Read it before
   adding anything. The whole history was rewritten on 2026-09-25; nothing sensitive is reachable
   from any branch.

## The estate in one paragraph

Two webhook **receivers** turn provider events into CRM truth: **WF-1** for HeyReach (LinkedIn) and
**WF-2** for Smartlead (email). Each normalises an event, resolves or creates the person and the
campaign-scoped lead in **Pipedrive**, writes an activity, applies labels, decides whether the team
should be alerted in Slack, and files the replier in the **DNC registry**. **Reconcilers** recover what
the webhooks miss (Smartlead never sends us its SENT events). Shared state lives in an n8n **data
table**, never in workflow staticData. The DNC registry is mirrored into **Supabase**. Company **ICP
scoring** (Phase 1, DEV) lives in [`icp-scoring/`](icp-scoring).

## Layout

| path | what |
|---|---|
| `docs/` | every document **and script** from the working directory, path-for-path — the definitive reference is `docs/WF1_W1.0.1_build/wf1-system-reference.md`, the rules are `docs/RULEBOOK.md`, daily history is `docs/task-logs/` |
| `chat-history/RULINGS_AND_INSTRUCTIONS.md` | every human instruction, chronological and verbatim — the decision record |
| `icp-scoring/` | the ICP scoring engine, contracts, n8n nodes, statics and golden set |
| `ops/` | operational scripts — `heyreach_webhook_scope.mjs` **must be run after every new HeyReach campaign** |
| [`INDEX.md`](INDEX.md) | every document, grouped |

Paths under `docs/` mirror the working directory exactly because the documents cross-reference each
other by relative path.

## The one lesson worth reading twice

The failure that keeps recurring here is not the crash. It is the **write that reports success while
achieving nothing, or the wrong thing** — an HTTP 200 on an activity attached to the wrong lead, a
registry that lost claims to overlapping executions, a dry run that announced "chunk done", a verifier
that called 47 empty commits clean. None raised an error. Each was found only by re-deriving what
*should* exist and comparing. When you change something, the acceptance test is a read-back of the
real record, and every test suite must include a case the old code fails.

## Conventions

* A document states what was **measured**. Where a number is an estimate, it says so.
* Task logs record done / partial / blocked / improvable. Partial and blocked are never omitted.
* People in these documents appear as `Person-<h8>` / `pii-<h8>@example.invalid`; see `SECURITY.md`.
