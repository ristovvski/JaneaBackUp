# Task log — 2026-08-05 — "LinkedHelper outreach response" burst investigation

**What was asked:** Melisa flagged a burst of "LinkedHelper outreach response" Slack posts across
old campaigns (eMerge Americas 2026, Pharma USA 2026, ITEXPO 2026), 7 leads, and attributed it to
Nik's work. Find the true trigger chain, read-only, name who/what actually updated those persons.

## What was done, and what it proves

- **The burst is not recent.** All 7 Slack posts (found via `slack_search_public_and_private`,
  matching the exact leads) fired 2026-05-29T17:15-17:19 UTC — a single ~4-minute window, over two
  months before Melisa's question. This reframes the whole task: not "what's happening now" but
  "what happened once, a long time ago."
- **Discovered and verified a real capability this project had wrongly ruled out**:
  `/v1/persons/{id}/changelog` and `/v1/persons/{id}/flow` both work and return field-level history
  with `change_source`, `change_source_user_agent`, `actor_user_id`, `is_bulk_update_flag`. Earlier
  project memory asserted Pipedrive exposes no update-authorship via API at all — wrong, corrected in
  `wf1-parallel-automation-clobber.md`.
- **Proved the mechanism airtight, 7 for 7.** Every lead's changelog shows a write to
  `f016efd8791291c591c1d49440018ab0bd23384d` (WF-1's `stage` field, confirmed unique to WF-1) landing
  7-26 seconds before its Slack post — the same relay-latency signature already proven for the Jigar
  case earlier today. `change_source:"api"`, `user_agent:"axios/0.27.2"` (a Node.js HTTP client, not
  a browser) on all 7, `actor_user_id` = Melisa's shared service account, not a human.
- **Ruled out the alternative explanations the user asked to check**, with actual evidence rather
  than assertion: my own session (trivially — didn't exist on 2026-05-29); n8n execution logs (tried;
  retention doesn't reach back that far — a real, permanent gap, stated as such rather than glossed
  over); human edit, bulk edit, Clay/Smartlead/other-integration (all would leave a different
  fingerprint than what's actually there — confirmed by finding a genuine contrasting example: the
  same person, person 73743, has a separate later entry from 2026-06-01 with `change_source:"app"`
  and a real Chrome user-agent — an actual human edit, unrelated to this burst, which is what proves
  the distinction in this data is real and not just my assumption).

## Partially answered — stated honestly, not overclaimed

The user's point 4 asked whether the zap's filter is "so loose it fires on ANY person update." I did
NOT prove this. What's proven: it fires reliably (7/7) on WF-1's reply-type stage transitions on
these old campaigns. What's not tested: whether it would fire identically on invite/accept-type
writes for the same old campaigns — no same-day counter-example was available. Earlier today's
separate check (C5, on current Ai4 campaigns) found the sibling zaps' behavior on invite/accept
events inconsistent, which doesn't resolve the question either way. Reported as an open point, not
folded into the verdict as if it were settled.

## Blocked

- n8n execution retention (~161h max observed for WF-2) cannot reach back to 2026-05-29 (over 2
  months). No execution-level evidence for that date exists anywhere in this stack; the changelog is
  the only surviving record, and it happened to be sufficient.

## What can be improved

- The wrong "Pipedrive has no changelog API" belief was carried in project memory for weeks and
  shaped how the original May-17 ghost investigation was diagnosed (it used timing-correlation
  workarounds instead of direct authorship data, because direct authorship was believed unavailable).
  Worth a retroactive look at whether the lead-level equivalent (`/v1/leads/{id}/changelog` or
  similar) also exists — not tested this pass, and if it does, some of the harder parts of the
  original ghost diagnosis could have been answered directly instead of inferred.
- This confirms and strengthens, rather than changes, this morning's decision to kill 274357187 —
  worth noting that the same evidence source (person changelog) would have let me kill it with this
  level of confidence hours earlier, if I'd tested the endpoint before resorting to the Jigar/Slack
  timing-correlation method.

## Deliverable

`wf1-release-evidence/BURST_INVESTIGATION_2026-05-29.md` — timeline table, verdict, and a ready-to-
send paragraph for Nik to give Melisa.
