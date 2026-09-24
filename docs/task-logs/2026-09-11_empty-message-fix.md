# 2026-09-11 — the empty-message fix (scope-limited)

Nik's scope correction mid-task: **only the empty-message fix, nothing else.** Everything else found
along the way is recorded here and left alone.

## Done

| | |
|---|---|
| WF-1 blank-reply gate + alert excerpt | `67fa96b0`, 140 nodes, statics 12/12 |
| Person-8768306e repair (1 record) | registry row 33166 tombstoned, `3. Responded` stripped, task closed, activity annotated — 8/8 verified |
| Removal path can carry a reason | `dnc_s4_retirement_removal` `50a7f964`, statics 8/8 |
| **WF-2 blank-body gate** | **`1349b4ee` → `613c487d`, 197 nodes, statics 11/11** |
| **Linter rule `reply_requires_nonblank_body`** | **self-test 12/12; ACTIVE findings 0** |

### WF-2 gate

```
Switch Event[1] (REPLIED) ─▶ Blank Body Gate ─[true]─▶ IF Nurture REPLIED, IF Unknown Marker
                                              └[false]▶ Blank Body Skipped   (terminal)
```

Cases as agreed: plain text / HTML-with-text / signature-only / quoted-original-only → **real**;
HTML that strips to nothing, `&nbsp;`-only, zero-width-only, empty, null → **blank**.

**The strip is the whole trick.** Measured on live execution 51511: a naive `<[^>]+>` strip leaves
`<style>` contents behind, so that reply's "text" began `P {margin-top:0;margin-bottom:0;}` — an
HTML-only empty reply would have looked like 2,887 characters of content. The gate removes the
BODIES of `<style>`/`<script>` first. A non-vacuity static pins it: the naive strip returns `true`
on the case the real one returns `false`.

**Stated honestly: WF-2 has ZERO observed blank bodies.** The guard is prophylactic, justified by
shape-matching WF-1, not by a measured WF-2 failure.

### I gated my own exception

I had left `IF Unknown Marker` ungated, arguing it warns about the campaign rather than the reply.
The linter flagged it — correctly, by the rule as written. Writing myself an exemption to make my
own rule pass is the wrong way round, so the wiring moved behind the gate. Coverage cost measured,
not asserted: `Switch Event[0]` (SENT) still feeds the marker check, so a mis-marked campaign still
warns on every send.

### Linter scope, stated

Exit code follows **ACTIVE** workflows only. `ARCHIVE__WF-1-DO NOT USE` is a frozen pre-fix snapshot
carrying 7 findings and would hold the rule red forever; a permanently failing gate gets ignored,
which is worse than a narrower one. Archived findings are still printed, never hidden.

## Found and PARKED — no action taken, per the scope correction

1. **`date_precision: 'unknown'` is hardcoded in both DNC build nodes** (WF-1 `M7 DNC Build Input`,
   WF-2 `DNC Build Input`). Via `reasonExpiryOverride('reply_dnc','unknown') → expires_at: null`,
   this single literal is why every reply-driven suppression is **permanent** rather than
   TTL-bounded. It is the most consequential constant found, and there is no sign it was ever a
   decision rather than a default.
2. **`owner_id` is one frozen person in both receivers** — WF-1 `CONFIG.melisa_user_id` (M6/M7
   Build, Person Create, Create Lead, Create Activity, M8 Task) and WF-2 `CONFIG.owner_id`, the same
   id 16340280. No per-campaign or per-sender mapping exists anywhere. Measured with the ordering
   proven: **623 of 722 new leads in 14 days** land on that owner, plus 1,336 activities.
3. **My own sweep was wrong first time.** v1 scanned only mutating nodes, reported "5 findings, all
   benign", and missed both known cases — in this estate the request body is assembled in a
   preceding Code node. v2 scans every node from which a mutating node is reachable and carries a
   self-check that fails loudly if it stops finding the two we already know about.
4. **`node_reference_resolves` is now red, and it is not ours.** Two unresolved `$('Name')`
   placeholders in **`WF-ICP-Score [DEV]`**, inactive, which appeared in the estate between this
   morning's dump (41 workflows) and this afternoon's (43). Left alone.

## Improvable — mine

* The first empty-reply census reported **342 of 342 empty (100%)**. Wrong twice over: the message
  lives in `recent_messages[]`, which I never opened, and `message_sent` was counted as a reply
  because its name contains MESSAGE. Corrected: **2 of 242**. A 100% rate is a symptom, not a
  finding, and I should have treated it as one immediately.
* The first owner measurement said "523 recent leads" from an unsorted `/v1/leads` read that
  returned rows from 2023–2025 and zero from this fortnight — the list-ordering trap, which is
  written down in the rulebook I maintain.
* A statics harness mocked `$json` where the node reads `$('Webhook').first().json.body`; all eight
  cases failed identically, which is what an unmocked accessor looks like.
