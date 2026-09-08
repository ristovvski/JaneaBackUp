# 2026-08-14 — Ganga tail: the fix worked, and it exposed a worse bug one layer down

Live: **WF-2 `510c4417`** (forward hotfix) · **WF-2R `dde01df7`** (23 nodes, this fix)
· WF-1 `9a6df1cd` · WF-2S `1ab4f83d`.

## DONE — item 5, the 19:39 pair, answered from the retained execs

Nik asked whether the deployed `Normalize` keyed CRM writes to **Andrea** or to Marie-Anne again.
Read, not assumed — two executions touch the thread:

| exec | when | build | `lead.email` | person written | outcome |
|---|---|---|---|---|---|
| 16265 | 08-13 16:38Z | **pre-fix** (no `__reply_class`) | marie-anne.ganga@ | none resolved | alerted team, forwarded |
| 16278 | 08-13 17:30Z | **post-fix** | **andrea.tassistro@** | **69696 (Andrea)** | suppressed, then crashed |

**The fix worked.** Person resolution went to Andrea, candidates `[69696]`, not to Marie-Anne. The
"person-side writes only for HER" line came from the pre-fix exec.

## FOUND — recovery had stopped meaning delivery

exec 16278 is not a re-arrival. It is a **WF-2R replay**, and the replay envelope carries no
`sl_lead_email`. So the classifier hit its explicit `ambiguous` branch and `First Reply Gate` fired
`suppressed_ambiguous`: **no alert, no forward** — on a reply Smartlead categorised `Interested`.

Two of my own fixes, deployed the same night, cancelling each other:

* P0-1b + WF-2R exist so a crashed reply is **recovered**.
* The Ganga gate silences anything whose identity it cannot verify.
* The replay envelope cannot carry identity — so **every recovered reply was silenced by
  construction**. Not a tuning issue; a structural one.

Structural, and measured that way — no inference from one case:

```
retained EMAIL_REPLY arrivals : 7
  live webhook   3   sl_lead_email present: 3/3
  WF-2R replay   4   sl_lead_email present: 0/4
```

## THE FIX — one field, in `Build REPLY Payload`

`to_email: row.lead_email` was already there: leads-statistics rows key on the lead, so WF-2R has
the address in hand. Added `sl_lead_email: row.lead_email` + `__identity_reconstructed: true`.

Worth stating because it is a trap for the next reader: **in the replay envelope `to_email` means
the LEAD**, the inverse of the live webhook where it means whoever hit reply. The two envelopes were
never the same shape.

Statics ran the **deployed** WF-2 `Normalize` against four envelopes, 5/5:

| case | class | |
|---|---|---|
| old replay envelope, no `sl_lead_email` | `ambiguous` | **reproduces the bug** |
| new replay envelope | `lead` | alerts normally |
| live third-party (Ganga) | `third_party` | no regression |
| live alias (jfarrar → joseph.farrar) | `alias` | no regression |

**Known and accepted limit:** a replay cannot detect a third party — the provider row records the
lead, not the human who typed. A replayed Ganga-type reply will alert **naming the lead**. That is
the right failure direction (a real lead, versus today's silence), and `__identity_reconstructed`
marks it so the observability pair can say so out loud rather than hiding it.

## CARRY TO NIK — a policy question I did not decide alone

`ambiguous` currently **suppresses** the team alert. Andrea's case is the argument against: a real
`Interested` reply went silent on a missing field. After this fix the replay population leaves that
class, but genuinely-missing-field arrivals remain. Suppressing on *absence of evidence* is an
INTERNAL failure class — the north star says that is the unacceptable one. My recommendation:
**ambiguous should alert, flagged "identity unverified"**; reserve silence for confirmed
`third_party`. Melisa/Nik's call, not mine.

## ANDREA IS STILL UNREPAIRED — and it is worse than the repair list said

Person 69696 exists, **0 leads**. Her `Interested` reply currently has: no alert, no forward, no
lead, no label, no activity. Already item 2 of task #27 (lead creation + label + activity +
Marie-Anne note); this raises its priority — it is the most valuable reply category we have, sitting
at zero.

## DONE — Nik's four follow-ups, same session

**1. `ambiguous` now ALERTS, flagged "identity unverified"** — WF-2 `268cfecf`. Nik ruled per §0:
a missing field is an INTERNAL failure class and must never eat a live Interested reply. Silence is
reserved for a CONFIRMED `third_party`, the one case with evidence rather than the absence of it.
Statics 4/4, including the pre-fix replay envelope asserting it now alerts **with** the flag
(`should_alert=True, identity_unverified=True`) where it returned `suppressed_ambiguous` before.

**2. Andrea repaired** — lead `76be46a0`, labels `cold + connected + responded`, activity `44140`.
Chose **direct CRM writes over a webhook replay**: a replay needs WF-2's staticData claim released,
and that store has already cost 113 claims to lost-update races — and it would still classify
`third_party` and not alert. Every body copied from WF-2's own node (`Body Lead Create` title
convention, `Body Lead Labels Union` triple, `Body Reply Activity` shape), so the result is what
WF-2 would have written. Read back after writing.

Two things the dry-run caught: a duplicate pre-flight on **both** the campaign field and the title
prefix (Make leaves the campaign field empty), and the quoted trail — this thread's attribution line
is **French** (`Le … a écrit :`), so an English-only pattern left 208 KB of quote in the note.
Trimmed to the 353 characters Marie-Anne actually wrote.

Team alert posted to `C07LTD8UT70`, marked as backfilled. It states plainly what Smartlead's
"Interested" actually contains: **a warm deferral to September**, not an active request.

**3. Reference doc** — new **§9b.0i** (same field name, different semantics per origin) with the
`to_email` / `sl_lead_email` table, plus a correction inside **§9b.0f**: I cited that rule in the
node comment to justify an alert gate failing CLOSED. Citing a standing rule is not applying it.

**4. WF-ERR IMPACT** — WF-ERR `126624c7`. Recoverability is a property of the **event type**, not
the workflow: `REPLIED` → WF-2R replays within ~15 min, `SENT` → WF-2S re-claims, anything else →
genuinely LOST. Unreadable event now says UNKNOWN rather than LOST. Checked the field's real
vocabulary first — Normalize emits `REPLIED`/`SENT`, **not** Smartlead's `EMAIL_REPLY`/`EMAIL_SENT`;
a map keyed on the provider's names would have silently fallen through to the blanket "LOST".

## PAUSED-CAMPAIGN CHECK — half answered, half still open

**The safety net is not blind.** WF-2R's `Pick Campaign` excludes only `ARCHIVED`/`DRAFTED` and runs
a hot/cold two-ring sweep, with a comment written for exactly this case: *"a campaign can receive
replies long after it stops SENDING, so ACTIVE-only would go blind."* 11 PAUSED + 1 STOPPED
campaigns are all in scan scope.

**Still open — whether the provider stops DELIVERING webhooks on pause.** My first probe read
`reply_time` / `lead_email` off raw `leads-statistics` rows and got "0 replies" everywhere. False
read: those keys do not exist — the rows carry `to` / `lead_id` / `history[]`, and replies live
inside `history`. Needs history parsing. Also noted: every paused campaign's `updated_at` is a
:00:20 bulk timestamp from the last few hours, so **`updated_at` is not the pause moment** and
Stefan's pause cannot be dated from it.

## NEXT

Rest of #27 (observability pair → Rachel/Joseph/Conrad alias repairs → alias claims) → the
paused-campaign delivery question → #26 P0-1b port → **#28 outbound-logging recon**, which Nik
sequenced after the Ganga tail and the port, and which must be born on the atomic claims table.
