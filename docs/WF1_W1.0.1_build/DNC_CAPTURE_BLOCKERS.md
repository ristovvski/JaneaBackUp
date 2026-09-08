# DNC reply-capture — three blocking findings before any code

Read-only recon done. **Nothing built.** Three premises in the envelope do not hold, and the third
would actively harm the pipeline if shipped as written.

## 1. WF-2 does NOT already write the ledger

> *"WF-2's unsubscribe branch already writes… same sub-workflow, same merge rules"*

It does not. Measured:

* WF-2 contains **no reference** to `RolYGL3J2CNg6Yp3` (`DNC__UpsertLedger__v1`).
* WF-2 has **zero `executeWorkflow` nodes** — it cannot call a sub-workflow at all today.
* Its DNC branch is `IF DNC → Body SL Unsubscribe → Gate SL Unsubscribe → SL Unsubscribe`, which
  calls **Smartlead's** `/leads/{id}/unsubscribe`, plus `U Lead DNC Label` which writes a **Pipedrive
  label**. Neither touches the registry.

**Estate-wide, the only caller of UpsertLedger is `ARCHIVE__dnc_s4_event_populations`** — inactive,
and renamed `ARCHIVE__` by someone since I last read it.

So there is no existing pattern to copy. This is the **first** inline ledger write in either
receiver, in both. That changes it from "mirror WF-2 into WF-1" to "build it twice, from the
sub-workflow's contract" — doable, but it is a different job than briefed and worth knowing before
the clock is spent.

## 2. `negative_reply` is an entry_type, not a reason

The ledger validates reasons against a fixed map and **throws** on anything else:

```js
REASON_TO_ENTRY_TYPE = {
  client:                   'explicit_opt_out',
  unsubscribe:              'explicit_opt_out',
  meeting_dnc:              'replied',
  reply_dnc:                'negative_reply',      // <-- reply_dnc IS the negative tier
  sales_personal_outreach:  'manual',
  manual_offboard_eligible: 'employee_connection',
  event_contacted:          'manual',
  manual_sheet:             'manual',
  offboard:                 'manual'
}
```

`"reason reply_dnc for a normal reply, negative_reply if the classifier says negative"` conflates the
two layers: **`reply_dnc` already maps to `negative_reply`**. Passing `negative_reply` as a *reason*
throws `DNC upsert: invalid reason`.

## 3. ⚠️ The mapping as written would suppress everyone who replies positively

This is the one I will not ship without a word.

`reply_dnc → entry_type negative_reply` is a **suppression tier**. The instruction *"ANY genuine
reply enters the registry… reason reply_dnc for a normal reply"* therefore registers **every
replier — including "yes, let's meet" — as a negative reply**, which is what the registry exists to
stop us contacting.

Finovate alone would put Kyle-class positive repliers into DNC. That is a projection onto real
prospects, and reversing it means finding and deleting rows after the fact.

**What I think was meant**, and can fire immediately on a word:

| signal | reason | entry_type | effect |
|---|---|---|---|
| message asks to stop | `unsubscribe` | `explicit_opt_out` | permanent, correct |
| classifier says negative | `reply_dnc` | `negative_reply` | suppression, correct |
| a normal / positive reply | **`meeting_dnc`** | `replied` | *"they engaged with us"* — TTL-bounded, **not** an opt-out |

`meeting_dnc → 'replied'` is documented in the sub-workflow's own comments as the
*engaged-with-us, not an opt-out* tier, explicitly TTL-bounded rather than permanent. That is the
only legal reason that means "this person replied" without asserting they refused us.

## 4. And WF-1 cannot satisfy `reply_dnc` at all today

The ledger throws:
```js
if (s.reason === 'reply_dnc' && !s.reply_category)
  throw new Error('DNC upsert: reply_dnc requires reply_category …')
```
**WF-1 has no `reply_category`, no classifier, and no sentiment signal** — verified: the strings
`reply_category`, `sentiment`, `negative`, `is_dnc`, `unsubscrib` appear nowhere in WF-1, and
`Normalize` does not emit a category. WF-2 has the whole classifier chain (`LLM Classify`,
`Classify Parse`, `IF DNC`); WF-1 has none of it.

So on the LinkedIn side, **every `reply_dnc` write would throw on arrival**. WF-1 can legally write
`unsubscribe` (if we detect a stop request in the text) or `meeting_dnc`, but not `reply_dnc`,
until it gains a classifier or we supply a category from the message body.

## What I need — one line each

1. **Confirm the reason mapping** in §3 (normal reply → `meeting_dnc`, not `reply_dnc`). This is the
   one that risks real prospects.
2. **WF-1 negative detection**: accept that LinkedIn writes `meeting_dnc` for every genuine reply
   and `unsubscribe` only on an explicit stop phrase — **or** authorise wiring WF-2's classifier into
   WF-1, which is a larger job than this envelope.

Everything else — the inline placement in both receivers, fire-and-forget with `onError: continue`,
reuse of the existing OOO / bounce / non-campaign locks, idempotency via UpsertLedger, and the
class-level statics — is understood and ready to build the moment those two are settled.
