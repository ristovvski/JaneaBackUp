# 2026-08-06 — R1: backfill of replies lost to the 2026-08-04/05 WF-2 outage

Owner-authorised live run (dry-run → explicit GO with answers D1–D4). Writes confined to the
replies domain. Event Name / Marketing Hypothesis untouched; duplicate forensics not touched.

Artifacts: `r1_reply_backfill.py`, `r1_verify_after.py`, `r1_close_handovers.py`,
`wf1-release-evidence/r1_reply_backfill_{dryrun,live}.json`, `r1_verify_after.json`,
`r1_handovers.json`, `R1_BACKFILL_DRYRUN.md`.
Slack: https://janea.slack.com/archives/C0B8GCVNR5W/p1786022808436359

## Done

**22 live writes, 0 failures.** Contract read from live WF-2 `versionId e9242d0a` rather than
re-derived; verified by graph traversal that `IF Forwardable`'s FALSE branch still reaches
`Lead Labels Union → Reply Activity`, so non-forwardable replies correctly still get labels and
activity and only the forward is category-gated.

- 1 lead created (`pii-7b1c0e1a@example.invalid` → `de68f400`) — Make's known lead-creation defect
- 1 Smartlead category (mrudu → 9, Sender Originated Bounce, classified 0.99)
- 6 label unions (cumulative; cold+connected+responded), 3 leads already carried all three
- 9 reply activities + 1 bounce note, each carrying the full reply text
- **4 forwards, all `ok:true`**: hwang→rune, brum×2→mario, teuber→mario
- Independently re-verified from a cold read: 9/9 non-bounce leads carry `3. Responded` + a reply
  activity; the bounce carries a bounce note and NO responded label; Smartlead categories correct.

**Business value recovered:** `pii-6f8f48e5@example.invalid` replied **"How about 5pm?"** — Person-de82a469,
Head of Computational Drug Design at Deerfield, proposing an AI4 meeting time. Two days stale,
now with Rune.

## Partial

**Handover guard — the agreed rule does not work against this automation.** Closing an
auto-created Handover **regenerates a new one within ~3 seconds**. Proven, not inferred: all 6
closes at 13:25:46–48Z produced replacements at 13:25:49–50Z, same `creator_user_id 25112064`.
Stopped after one round rather than looping. End state: 6 open Handovers, one per affected lead —
which is exactly the state these leads would have been in had the replies processed on time, so
leaving them open is defensible. **Needs an owner decision** (leave / delete instead of close /
disable the automation for backfills).

## Improvable — a real error caught mid-run

`/v1/activities?lead_id=<uuid>` returns `data: null` for lead-attached activities. It does not
error — it silently reports **zero**. Only `/api/v2/activities?lead_id=` filters correctly.

Consequences:
1. My first post-write verification reported "reply activity missing" on all 10 leads. Those
   writes were fine — the read was wrong. Caught by fetching an activity by id directly instead of
   believing the aggregate.
2. The in-run Handover baseline ("0 open activities") and the in-run post-write sweep
   ("0 newly created") were **both false**, from the same bug. The real numbers were 3 pre-existing
   and 6 new. Only the delayed re-check with v2 surfaced them.
3. **`c2_handover_guard_check.py` uses the same v1 call** — the C2 Handover guard was very likely
   blind for the same reason. Worth re-running with v2 before trusting its earlier result.

Same family as `no-substring-blob-checks` and `verify-shapes-before-fixtures`: an endpoint that
answers plausibly instead of erroring. The tell was a 100%-uniform negative — every lead reporting
zero activities right after 22 successful writes.

## Not done

R2 (WF-2R reply reconciler) and R3 (delta digest) — both still due before Friday.
