# 2026-09-11 — the blank-body gate was wrong. Reverted, and here is what the wire says

Nik checked the HeyReach inbox: Person-8768306e DID reply at 03:34 — an attachment with no text.
My diagnosis ("accept artefact") was wrong, my gate suppressed a real responder, and my repair
removed a legitimate DNC row and a legitimate `3. Responded`.

## Done, in safety order

| | |
|---|---|
| **WF-1 gate DISABLED** | `758a7d27`, `Switch[3] → M7 IF Email Present` direct, gate nodes kept + marked disabled |
| **WF-2 gate DISABLED** | `79439533`, `Switch Event[1] → IF Nurture REPLIED, IF Unknown Marker` direct |
| **Repair REVERTED** | row 33166 → `status: active`, `removed_at: null`; labels `1. Cold, 3. Responded, 2. Connected`; activity note back to its original 15 chars. 4/4 verified |

The alert excerpt (`Reply: …`) **stays** — it is the thing that would have shown `[empty message]`
in the channel on day one.

Un-tombstoning needed a one-shot driver: **the retirement workflow only removes; there is no
reactivate path.** Worth knowing before the next correction.

## What the wire actually says

**The webhook carries no type field at all.** Complete union of every leaf across all three Heath
executions — message objects have exactly `creation_time`, `is_reply`, `message`. No
`message_type`, no `attachments`, no `media`.

So `M7 Build.render()` reads `m.message_type` — **a key this webhook has never sent.** Its
`[attachment]` and `[voice note]` branches have never fired, in any execution, ever.

**The inbox API DOES have a marker.** `GetConversationsV2` message objects carry
`body, createdAt, isInMail, isVoiceNote, postLink, subject, transcript, audioDurationMs, sender`,
and the conversation carries **`lastMessageType`**. Sampled 600+ conversations:

| | |
|---|---|
| `lastMessageType: TEXT` | 597 |
| `lastMessageType: ATTACHMENT` | **5** (Person-2b5dc16e, Person-451d4581, Person-989d19e8, Person-ef117af9, Person-1d8a04fb) |
| last message text empty | 3 — Heath, Nelson, Cailong |

Two of the three empty-text conversations are marked `ATTACHMENT`. The marker works and is
populated when an attachment exists.

## The conflict I cannot resolve, and will not resolve in my own favour

**Heath's conversation reads `lastMessageType: 'TEXT'`, `body: ''`, `isVoiceNote: false`,
`postLink: null`, `transcript: null`** — in both the filtered and unfiltered listings. On the API's
own evidence his message is an empty TEXT message, not an attachment, while the UI shows
"Attachment(s)".

I was confident about this exact person once today and was wrong, so I am not adjudicating it.
Either the UI labels any empty-body message "Attachment(s)", or `lastMessageType` is wrong for this
row. Only the UI can settle it.

## What it means for the gate, either way

**The gate as built could never have worked.** It reads the webhook, and the webhook has no marker.
It would have suppressed Heath *and* Nelson *and* Cailong — two of them confirmed attachments.

A gate that consults the inbox API on the empty-body path is buildable (one extra call, on 2 events
in 242). But **it would still have suppressed Heath**, because the API says TEXT for him. So if the
UI reading is right, no gate reachable from our data is safe.

**Recommendation: no gate.** Let empty-body replies alert, with `Reply: [empty message]` in the
body — which is already live — and let a human open the inbox. That hands the ambiguity to the one
surface that can actually see it.

## Improvable — mine, and this one cost a real prospect

1. **My attachment static used `message_type: 'ATTACHMENT'`, a field I copied from `render()`
   rather than from a payload.** Green statics certified a shape HeyReach does not send. The rule
   "verify shapes before fixtures" is in my own memory and I broke it on the case it was written for.
2. **I diagnosed from a coincidence.** Accept and reply arriving in the same millisecond, and a
   reply 0.5 s after our message, read as an artefact. It was a fast human. A 1-in-242 anomaly
   deserved the inbox check *before* the gate, not after.
3. **I shipped a suppression on a population of one.** The fix removed a class of alert on the
   evidence of a single event I had not confirmed with the provider's own UI.

---

# Addendum — conversation verified, repair re-applied (same day)

Nik opened the conversation itself rather than the list: **Heath's bubble is empty** — no rendered
attachment, no file, no voice note — stamped the same minute as Noah's invite. It is the accept
surfacing as a reply. `"Attachment(s)"` is HeyReach's **list caption for any textless message**, not
evidence of a file.

That makes the API evidence coherent rather than contradictory: `lastMessageType: 'TEXT'` was
**correct**, because it is a textless TEXT message. The marker is trustworthy — two of the five
`ATTACHMENT` conversations really do carry files. The misleading surface was the list label.
RULEBOOK T3 has been corrected; the earlier version implied the API was unreliable and that was
wrong.

## Done

| | |
|---|---|
| Heath repair **re-applied**, 8/8 verified | row 33166 tombstoned `false_reply_empty_body`; `3. Responded` stripped (`1. Cold`, `2. Connected` stay); handover task already closed; activity 46415 kept, prefixed `[false reply — empty accept artefact]` |
| Wording, both receivers, both surfaces | `Reply: [no text — manually check the inbox; could be an attachment or an empty connection-accept]` — WF-1 `0477b125`, WF-2 `8a34ec8e`, statics 10/10 |
| Gates | stay **off**, nodes kept disabled in place |
| `M6 Build` | closed, unchanged — Noah's message is real text, so that path was never this case |

The re-apply carries a guard: it refuses to overwrite the rollback baseline unless the CRM is
actually back at the state that file records. Running a repair twice around a revert is exactly how
a rollback file gets quietly replaced with an in-between state.

## What this thread actually established

The human-check loop ran end to end and worked: alert with the placeholder → inbox opened → decided
→ record corrected. That is the design, and it beat both of my attempts to resolve the ambiguity in
code. The first gate suppressed a real responder on a synthetic fixture; the second would have been
built on a UI caption. **Neither would have been necessary if the alert had quoted the message from
the start** — which is the one change out of all of this that is unambiguously right.

I was wrong, then right, then wrong about being wrong. The thing that settled it was neither
reasoning nor an API: it was a person looking at the conversation.
