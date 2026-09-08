# 2026-08-11 — WF-1 gate twin + alert policy (Melisa's answer)

Owner: fix-owner session. Decisions: Melisa (one-alert-per-lead stays), Nik ("first alert" = first
DELIVERED TO THE TEAM CHANNEL; an alert nobody saw was not an alert).

Live after this package: **WF-1 `72056581`** (110 nodes) · **WF-2 `8adf3431`** (145 nodes).

## DONE — items 1, 2, 5 (WF-1)

**Gate twin completed.** This morning's `f7be310f` had already removed label-based suppression from
the alert decision and moved the claim out of the gate into `M7 Labels Compute` on Slack `ok:true`.
What was missing was the CHANNEL condition, now added: the claim fires only on
`ok === true && channel === C07LTD8UT70`.

The team-channel id is **pinned as a constant, not read from `CONFIG.slack_channel_replies`**. They
are equal today but mean different things: if replies were ever pointed back at ops, a
config-derived check would silently start treating ops posts as delivery and re-mute everyone. The
rule is about the team seeing it, not about wherever config currently points.

**8/8 statics, executing the real body** — team post claims; ops-only post does not; `ok:false`
does not; suppressed path (alert node never ran) neither claims nor throws; no alert key claims
nothing; idempotent on an existing key; and the original's own no-lead path still returns
`__invalid` while still claiming. Two of those cases exist only because the strict mock refused to
invent nodes: the wrapped original reads `CONFIG` / `M7 Person Get` / `M7 Build` / `M7 Lead Get`
and returns a bare **object**, not an array — a permissive mock would have "passed" while testing
nothing.

**Registry rebuilt from delivery evidence: 50 → 0**, `staticData.seen` preserved, verified on
read-back. Rebuilt rather than merged: all 50 entries were written by the OLD gate at DECISION
time, which is exactly the claim shape Nik's rule rejects.

**Seeding walk — full population, 1,399 executions, 2026-07-23 → today, 0 unreadable:**

| classification | count | notes |
|---|---|---|
| `unclassified_no_alert_nodes` | 1,249 | non-reply events; no gate/alert nodes ran |
| `delivered_ops_or_other` | 99 | **all 99 to `C0B8GCVNR5W`**, 40 distinct alert keys |
| `suppressed` | 51 | 40 `already_alerted`, **11 `responded_label`** |
| delivered to TEAM | **0** | — |

Of the 50 removed keys: 40 alerted only to ops, 25 suppressed-only (sets overlap),
**0 unexplained**. **50 leads become eligible for one real team-channel alert on their next reply**
— Person-cee23a2f and the 6 repliers are inside that set. The 11 `responded_label` suppressions are
the label gate, removed from the decision this morning.

## DONE — items 3, 4 (WF-2, one window, deployed while traffic was zero)

* `CONFIG.slack_channel_replies` `C0B8GCVNR5W` → `C07LTD8UT70`. Exactly two nodes move —
  `Reply Alert`, `Nurture Alert` — and all **eight** `Ops Warn` nodes stay on ops, asserted by node
  wiring before and after the PUT, with a guard that aborts if an `Ops Warn` node ever reads
  `slack_channel_replies`.
* The auditor's `|| 0` finding, confirmed exactly as described: **`R Lead List` was the one branch
  with no `__person_id` fallback** (the three added in 4c had it). Unified. And `|| 0` → `|| -1`
  on all four: `person_id=0` reads as a query for person zero, whereas -1 cannot be a Pipedrive
  person id, so a degenerate read is unambiguous in the URL and the logs.

## CORRECTION I OWE ON MY OWN REPORTING

I told Nik "WF-1 has been posting to the team channel all along" and called the brief's premise
wrong. **I was wrong; the brief was right.** I read WF-1's *current* `CONFIG.slack_channel_replies`
(`C07LTD8UT70`) and inferred historical behaviour from it. The wire says otherwise: all 99 ok:true
alerts went to ops, through 2026-08-09 — the CONFIG switch happened during Monday's routing work,
after essentially all of that history. Config describes now; only executions describe then.

## NOT DONE — carried to Nik

**The auditor's "explicit unresolved branch" is not built.** A real branch needs an IF node in
front of four HTTP nodes — graph surgery on the wave path, i.e. P0-1b's gate class, not a config
edit. I also did **not** add a `__lead_read_unresolved` flag, because §9b.0b (set today) forbids
emitting a blindness flag with no consumer. Nothing is hidden meanwhile: the degenerate case is
visible as `__lead_candidates_read` plus a literal `person_id=-1` in the request.

## BLOCKED — item 6, and the sequence

**P0-1b is still at its gate**, not in flight as the brief assumed: Nik's condition was "deploy
after an observed clean wave hour", and there has been **zero SENT traffic since 11:05Z**. Watcher
`blocd1m8t` is alive, waiting for the first SENT and then 60 minutes past it.

Item 6's live verification therefore has not run. When the first real reply lands I will hand Nik
the permalink — **but not as "#lead-processing's first ever message"**: that claim is unsafe. It
would be the first WF-2 reply alert to land there, but the channel has prior history (this
engagement opened by investigating a burst of posts in it), and WF-1's own alerts went to ops, not
nowhere. I will state exactly what it is.
