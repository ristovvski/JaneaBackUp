# 2026-08-13 — Reply identity (Ganga case): the lead is not whoever replied

Live at hold: **WF-2 `bc3dc2f5`** (149 nodes, active) · WF-1 `9a6df1cd` (111, dual-write running)
· WF-2S `1ab4f83d` · WF-2R `c765c1fb`.

## DONE — root fix deployed, 7/7 statics

**The defect, one line** (`Normalize:103`):
```js
email: mail(pick(b.to_email, ld.email, b.email)),
```
`to_email` is *whoever hit reply*. `sl_lead_email` — the campaign lead — sat in the payload unused.
On a threaded reply WF-2 adopted the wrong human: person search missed, no lead resolved, the REAL
lead got no label and no activity, and an alert fired naming someone who was never a lead.

Person-36e26da4 (exec 16265) replied on **Person-7267ff83's** thread. She is not a Smartlead lead
and has zero Pipedrive persons. WF-2 alerted the team channel about her and forwarded.

**Deployed:**
| node | change |
|---|---|
| `Normalize` | `lead.email` := `sl_lead_email`; emits `__reply_class`, `__reply_from` |
| `First Reply Gate` | suppress team alert for `third_party` **and** `ambiguous`; reason `suppressed_<class>` |
| `Body SL Forward Email` | skip forward when the sending mailbox IS the owner's real inbox |

**Classification** (computed once, so gate / forward / CRM cannot disagree):
`lead` · `alias` (same domain REQUIRED + local-part relation) · `third_party` · `ambiguous`
(missing field — explicit branch, never a silent default).

## THE SWEEP — 4 of 92 retained EMAIL_REPLY events, and 3 were misdiagnosed

| when | real lead | replied from | verdict |
|---|---|---|---|
| 07-31 15:30 | pii-6e4e8b43@example.invalid | kevin.conrad.morales@… | **alias** |
| 07-31 15:53 | pii-1011b46b@example.invalid | jfarrar@… | **alias** |
| 07-31 17:00 | pii-399e6070@example.invalid | ravery@… | **alias** |
| 08-13 16:38 | pii-eb7de9be@example.invalid | pii-10d2dcec@example.invalid | **third_party** |

Three of four are the same person's alternate address. The originally-specified rule
(`sender != lead → suppress`) would have silenced all three. The alias test (same domain +
containment or initial+surname) rescues them and still catches Marie-Anne — same domain, unrelated
name. **25 of 92 are `ambiguous`** (a field missing), which is why that branch is explicit rather
than defaulted.

> **CORRECTION (2026-08-14).** I called those three *"genuine lead replies"* without reading the
> bodies. **All three are out-of-office autoresponders** — "I am currently out of the office and
> will return on August 10th", "I will be out of the office from Jul 27 to Jul 31", "out of the
> office for the remainder of 7/31". The alias *identity* finding stands (they are the same human
> under a second address, and the alias test is what attributes them correctly), but the claim that
> the strict rule would have "silenced three genuine replies" is wrong: there was nothing warm to
> silence. What actually rescues a genuine alias reply remains unproven — n=0 in this sample.
>
> This mattered practically. The repair queued from this table said "→ `3. Responded` + reply
> activity". Executing it as written would have manufactured **three false warm signals** in
> Melisa's queue, which is the exact outcome the OOO gate was built to prevent. Repaired instead as
> activity-only, labels untouched (verified `responded=no` on all three afterwards).
>
> Lesson, and it is the day's pattern again: **a classification is not a reading.** `alias` answers
> *who sent it*, never *whether it is worth anything* — and I let the first answer stand in for the
> second.

## THE FORWARD RECON — it is load-bearing, not redundant

```
sending mailboxes declared : 710  across 203 distinct domains
  IS the owner's real inbox (forward = duplicate) :  14
  lookalike sending domain  (forward = bridge)    : 696
```
15 owners, one real `@janeasystems.com` inbox each. **Ganga is one of the 14** — `from_email` was
`mario@janeasystems.com`, his real box, which is why Melisa saw the mail natively and our forward
duplicated it. Every other reply lands in a sending-domain box the human does not read.

Rule, computed from CONFIG, applied to ALL replies:
```
duplicate  ⟺  forward_owner_map[ forward_inbox_map[sender_inbox] ] === sender_inbox
```
**It can only remove duplicates, never a bridge** — which is what made it safe to ship before the
open process question below.

## TWO DEFECTS OF MINE THE STATICS CAUGHT

1. The classifier computed `__reply_class` but **never attached it to the emitted object**. Every
   consumer would have read `undefined` and silently taken the `lead` branch — the package would
   have deployed, verified clean, and changed nothing.
2. The first gate patch did three paren-balancing replaces on a nested ternary and produced invalid
   JS. Replaced the whole block verbatim instead. **Do not surgically edit nested ternaries.**

## NOT DONE — tomorrow, in this order

1. **Observability pair** (+2 nodes: IF + Slack → telemetry): three-class line, plus the note text in
   `Body Reply Activity` carrying the Smartlead reply category, plus a `Test`-owner note.
   **This is the §9b.0b gap and it is open right now** — suppressions currently happen with no line
   explaining them. Behaviourally correct, not yet observable.
2. **Four repairs** through the fixed pipeline, wire-verified: Rachel / Joseph / Conrad →
   `3. Responded` + reply activity (live missed replies from Jul 31). Andrea → person 69696 has
   **0 leads**, so lead creation + label + activity + the Marie-Anne note (London-backfill shape).
3. **Alias claims keyed to the real lead**, so one-per-lead holds across alternate addresses.
4. Standing queue: `wf1_seen` first-row check · WF-ERR routing · P0-1b port on the observation data.

## CLOSED — Nik answered the mailbox question

**Nobody ever checks the sending-domain inboxes.** So the forward rule as deployed is FINAL: bridge
for all 696, duplicates removed only for the 14 that are an owner's real inbox. Not sent to Melisa.

**What that makes the forward:** for ~98% of sending mailboxes it is the **only** path from a
prospect's reply to a human being. Not a convenience, not a notification — the delivery mechanism
itself. See §9e in the reference doc.

Still noted: `forward_owner_map.Test → melisa@janeasystems.com` — a test owner pointing at a real
person's inbox. A telemetry note fires if that path is ever taken (item 1c).
