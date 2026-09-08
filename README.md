# Janea GTM automation — documentation

The written record of the Janea Systems go-to-market automation estate: what it is, how it behaves,
what has broken, and what was decided about it. Every document here was produced while building or
repairing the running system — nothing is aspirational.

**This repository is internal.** It contains prospect names and email addresses, internal Slack
audits, and operational runbooks. Read [SECURITY.md](SECURITY.md) before changing its visibility or
adding anything to it.

## The estate in one paragraph

Two webhook **receivers** turn provider events into CRM truth: **WF-1** for HeyReach (LinkedIn) and
**WF-2** for Smartlead (email). Each normalises an event, resolves or creates the person and the
campaign-scoped lead in **Pipedrive**, writes an activity, applies labels, and decides whether a
human should be told in Slack. Behind them sit **reconcilers** — WF-2S polls Smartlead statistics
because Smartlead never delivers `EMAIL_SENT` to us, and WF-2R replays missed replies — plus the
**DNC ledger**, the suppression registry every outbound list is supposed to be filtered against.
Shared state (alert de-duplication, SENT claims) lives in an n8n **data table**, not in workflow
staticData, because staticData persists as one object and overlapping executions overwrite each
other's work.

## Where to start

| If you want to… | Read |
|---|---|
| understand the whole system | [`docs/WF1_W1.0.1_build/wf1-system-reference.md`](docs/WF1_W1.0.1_build/wf1-system-reference.md) — the definitive reference |
| know the standing rules | [`docs/RULEBOOK.md`](docs/RULEBOOK.md) |
| understand the DNC registry | [`docs/dnc-architecture.md`](docs/dnc-architecture.md) |
| see what exists, stage by stage | [`docs/SYSTEM_DOCS_2026-09-02/`](docs/SYSTEM_DOCS_2026-09-02) |
| know how a class of bug keeps recurring | [`docs/CLASS_MAP_2026-09-02/`](docs/CLASS_MAP_2026-09-02) |
| find what happened on a given day | [`docs/task-logs/`](docs/task-logs) |
| know *why* a decision was made | [`chat-history/RULINGS_AND_INSTRUCTIONS.md`](chat-history/RULINGS_AND_INSTRUCTIONS.md) |
| browse everything | [`INDEX.md`](INDEX.md) |

## The two halves

**`docs/`** — 339 markdown documents, path-for-path as they were written. They cross-reference each
other by relative path, so the layout is deliberately unchanged; [`INDEX.md`](INDEX.md) provides the
grouping instead of a re-filing.

**`chat-history/`** — the working sessions that produced all of it, rendered readable. 35 sessions,
705 human instructions, from 2026-07-23 onward. Human turns are verbatim; assistant prose is kept;
tool calls are collapsed to one line each; tool results and model reasoning are dropped. The
chronological instruction log is the decision record — when a rule is disputed later, it settles
what was actually asked for, and when.

## The one lesson worth reading twice

The failure that keeps recurring in this estate is not the crash. It is the **write that reports
success while achieving nothing, or the wrong thing** — an HTTP 200 on an activity attached to the
wrong lead, an idempotency footer that Pipedrive's HTML note field silently emptied, a registry that
lost 113 claims to overlapping executions, 53 leads created with a null person because `$json` does
not survive an HTTP node. None of these raised an error. Every one was found only by re-deriving the
state that *should* exist and comparing. Several sections of the reference doc exist purely to name
these shapes so they are recognisable on sight.

## Conventions

* Dates are ISO, in the project's working calendar.
* A document describes what was **measured**, not what was expected. Where a number is an estimate,
  it says so.
* Task logs record four states: done / partial / blocked / improvable. Partial and blocked are not
  omitted to make a log look tidy.
