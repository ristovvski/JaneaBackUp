# 2026-09-09 — Аудитор: window-2 pre-post + three follow-ups

Read-only, files only. **Three of the four premises turned out to be wrong in a way that changes
what should be done** — those are up front. The window-2 pre-post is at the bottom, with one slot
deliberately empty.

---

## 3. staticData drop — NOT reader-free. Do not drop the data alone.

I set out to confirm "zero readers" and the answer is **no**, but not in the way it first looked.
My own intermediate verdict was RED; the code says something more precise.

**Writers — six, all live:** `Claim SENT`, `Claim Bounce`, `Claim Unsub`, `Claim Nurture`,
`Reply CRM Done`, plus the forward key (`store.wf2_seen['F|' + __k] = …`). So the 3 Sep port did not
remove the staticData write; it added the claims table beside it.

**But `Dedupe` itself says which one is authoritative**, in its own comments and code:

```js
const store = $getWorkflowStaticData('global');
// … the claims table is the source of truth now, and the arithmetic is unchanged.
const __rows = __raw.filter(r => r.family === 'wf2_seen' && r.claimed_at …)   // ← claims table
const duplicate = __lookupBroken
  ? Object.prototype.hasOwnProperty.call(store.wf2_seen, key)                 // ← staticData
  : …                                                                          //   ONLY on fallback
if (n.event === 'SENT' && !firstSentSeen) store.wf2_seen[sentKey] = nowSec;   // rollback copy
__forward_claimed: __lookupBroken ? !!(store.wf2_seen || {})[dk.__forward_key] // ← fallback again
```

So: **the claims table is the read path; staticData is a rollback copy plus a fail-open fallback
that is consulted only when `__lookupBroken` is true.** `Bounce Counter` also opens staticData, but
for a different key (`wf2_bounce_counter`) that has never been written — consistent with the 3 Sep
finding that its feeder never fires.

**Therefore:**
* Dropping the 28 keys is **harmless on the normal path** — nothing reads them while the claims
  lookup works.
* Dropping them **alone leaves a live fallback pointing at an empty object.** If the claims lookup
  ever breaks after the drop, `Dedupe` reads `{}`, every event looks new, and WF-2 re-processes —
  duplicate forwards and activities. Today that branch is a genuine safety net; emptied, it becomes
  a silent duplicate-generator.
* **Drop the data and the fallback in the same change, or keep both.** If you want the fallback gone,
  the `__lookupBroken` branch should fail *closed* (skip and alert) rather than read staticData.

Verdict: **AMBER — not the clean "inert, zero readers" the plan assumed.** The 28 keys are inert in
the sense that nothing normal reads them, and live in the sense that six nodes still write them and
one node still falls back to them.

## 2. Digest n/a — one is a Slack scope, the other is NOT. Two different fixes.

**`no-match n/a` — yes, a scope.** `No Match Count` consumes `Ops Channel History`, which is
`GET https://slack.com/api/conversations.history` with `channel = CONFIG.ops_channel =
C0B8GCVNR5W`, `limit 200`, `oldest = window start`. What to grant the bot:

| need | scope |
|---|---|
| read history of a **public** channel | `channels:history` |
| read history of a **private** channel | `groups:history` |
| (both cases) the bot must also **be a member** of `C0B8GCVNR5W` | — |

`C0B8GCVNR5W` is the ops channel. Grant the one matching its type — and check membership first,
because a bot with the scope but outside the channel gets the same `not_in_channel` failure and the
node reports it identically. The node already degrades correctly: it sets
`__nomatch_readable: false` and carries the reason, which is why the digest posts instead of dying.

**`INTEGRITY sent-without-lead n/a` — NOT a scope. It is a broken Pipedrive call.**
`Integrity`'s upstream is `PD Campaign Leads`, and in today's run that node returned:

```
NodeApiError: "Bad request - please check your parameters"
description: querystring must have required property 'term'
```

A Pipedrive **search** call is being made without its required `term` parameter, so it 400s for
every campaign — which is exactly why all four read `n/a` (`3917998`, `3917997`, `3868450`,
`3868449`). No grant will fix this; it needs the query corrected (supply `term`, or switch to a
list/filter endpoint that does not require one).

**On the inline-reason request:** both nodes already *carry* the reason
(`__nomatch_error`, `readable: false`) — it is `Compose` that flattens them to a bare `n/a`. So the
change is one line in `Compose`, not in the two producers: render
`n/a — <reason>` when `readable === false`. Cheap, and it would have told you on day one that these
are two different faults.

## 4. Active count — 21 is right, and it matches the docs. The stale number is the total.

**The documented count is 21, not 20.** `SYSTEM_DOCS_2026-09-02/00_STAGE1_INVENTORY.md:17` and
`FULL_REPORT_2026-09-02.md:10` both read *"36 workflows — **21 ACTIVE**, 15 inactive"*. Live today:
**41 total, 21 active.** So the active count has not drifted at all and there is nothing to fix
there — the "documented 20" is not in the documents I can find.

The real drift is the **total: 36 → 41**. Four are attributable to 3 Sep:

| workflow | created | active |
|---|---|---|
| `zz_migrate_wf1_alert_registry` | 2026-09-03T08:26:48 | no |
| `zz_verify_wf1_alert_registry` | 2026-09-03T08:27:43 | no |
| `dnc_i04_event_log_prune` | 2026-09-03T08:44:49 | **yes** |
| `dnc_claims_prune` | 2026-09-03T12:44:41 | **yes** |

Two new actives balanced by the 3 Sep `ARCHIVE__` deactivations, hence 21 → 21. The fifth is not
attributable from `createdAt`: the 2 Sep inventory appears to have undercounted by one.

**I did not edit `SYSTEM_DOCS_2026-09-02/`** — it is a dated snapshot, and rewriting it to today's
numbers would falsify the record rather than fix it. What is needed is a fresh inventory pass;
flagging that rather than back-dating it.

**The 21 active, named:** WF-1 HeyReach Receiver · WF-2 Smartlead Receiver · WF-2H Health & Digest ·
WF-2R Smartlead REPLY Reconciler · WF-2S Smartlead SENT Reconciler · WF-ERR Error Handler ·
dnc_archived_responders_import · dnc_claims_prune · dnc_escalation_detector ·
dnc_i04_event_log_prune · dnc_i04_event_receiver · dnc_intent_vs_reality · dnc_morning_digest ·
dnc_pre_add_gate · dnc_pre_add_gate_monitor · dnc_projections_sweep · dnc_s1_responded_to_dnc ·
dnc_s2_meeting_to_dnc · dnc_s3_creation_watcher · dnc_s4_retirement_removal · dnc_wf_linter.

---

# 1. §9f.2 PRE-POST — FIRE_PIPEDRIVE window 2

**What will change:** person field `9c018b7406ebc481b9c108a487f76c4d09f91c9b` (`DNC Status`) set to
option **686** (`dnc_active`), plus the lead-label union on the subset that has a lead. Nothing else
— no Smartlead (`FIRE_SMARTLEAD` stays `false`), no lead creation, no other field.

**How many records: `____` — THIS SLOT IS DELIBERATELY EMPTY.**
Window 1's own Dev Summary reported **330 remaining** (exec `48563`: *"chunk 10/12 done · 250
processed (224 labels, 26 field-only) · 330 remaining · 0 errors"*). That number is **20 hours old**
and the registry has grown since — 19 `reply_dnc` upserts landed between 8 Sep 09:00Z and this
morning. So the pre-post is not complete until the dev count is re-run.

**The gate you asked for:** run `dnc_projections_sweep` with `MODE="dev"` / `FIRE_PIPEDRIVE=false`
and it must read **exactly 330**. If it reads more, the backlog grew and the number in this post is
the new one; if it reads fewer, something else projected in between and that needs explaining before
anything fires. Either way, **the count in the pre-post must be the count the dev run just
produced** — not 330 carried forward.

*Why the dev run is safe:* all 8 write-capable nodes in that workflow have a fire gate upstream
(`FIRE_PIPEDRIVE?` / `FIRE_SMARTLEAD?` / `MODE == dev?`), both flags are real **booleans** in CONFIG
(not the strings `"false"`), and the gate IFs test with a boolean-true operator. Window 1 proved it
empirically: exec `48563` ran the count and `PD Write DNC Field`, `PD Patch Lead Labels`,
`SL Unsubscribe` **did not run**.

:warning: One latent hazard worth stating once: those IFs use `typeValidation: "loose"`. The gate is
safe today *because* the CONFIG values are booleans. If anyone ever disarms by typing the **string**
`"false"`, loose validation may coerce a non-empty string to true and the gate would open. Flip the
flag as a boolean in both directions.

**The four post-verify assertions (unchanged from window 1):**
1. **Per-id, not per-count** — every person in the fired chunk reads `DNC Status = 686` on a fresh
   read. Window 1's equivalent: 20/20 sampled still 686 today, zero reverted.
2. **Bracketed delta** — the 686 population before and after the run, with the bracket taken around
   the write window; `after − before` must equal rows written exactly.
3. **DNC lead-label set unchanged** — still exactly the 7 expected survivors, **by id**, not by count.
4. **Zero collateral** — no other label and no other field changed on the touched persons or leads.

**Named acceptance case:** `pii-9b2ca0d1@example.invalid`, person **p85878**, lead `98176190`. Registered
`reply_dnc` at 2026-09-08T12:58:22Z — **62 s after her reply** — and still `DNC Status = None` with
no DNC label. She is the live instance of *registered ≠ enforced*. **Window 2 is correct only if
p85878 comes out of it carrying 686.** If she does not, the chunk selection is skipping recent
registrations and window 3 will not close the channel either.

**Discipline:** chunks of 250 (`pd_chunk_size`) · per-record guard re-checked at write time ·
fresh baseline bracketed around the run · re-arm and disarm as a boolean · disarm immediately after,
as window 1 did (`FIRE_PIPEDRIVE` back to `false`, confirmed at 15:21:17Z).

**Reversible:** the pre-write baseline holds every prior value, so a rollback is a replay of it.

**Window 3:** after window 2, remaining should be ≈ `330 − chunk` plus anything registered in
between. The channel is closed only when a dev count reads **0** — and that assertion belongs in
window 3's post-verify, not this one.

---

## Status of the four

| # | item | state |
|---|---|---|
| 1 | window 2 | **pre-post written, count slot empty — needs the dev run, then your confirmation** |
| 2 | digest n/a | **diagnosed: 1 scope grant + 1 code fix (not one cause)** — changes HELD |
| 3 | staticData drop | **do not drop alone** — the fallback must go in the same change; HELD |
| 4 | active count | **closed: 21 is correct and documented; the total 36→41 is what is stale** |

## IMPROVABLE — mine

* I called item 3 **RED** ("live writes, don't drop") before reading `Dedupe` to the end. The writes
  are real but the reads are fallback-only, which is a materially different verdict. Corrected before
  it reached this file — but it is the second time this week that a first-pass verdict on WF-2's
  internals needed the code read properly.
