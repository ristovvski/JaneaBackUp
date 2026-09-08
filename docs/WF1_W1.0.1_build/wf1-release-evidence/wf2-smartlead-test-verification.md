# WF-2 - verification against the real Smartlead test payload (exec 11602)

Fired from Smartlead's own webhook Test button, Association = Account Level, event "Email Reply".
Execution `11602`, status **success**. This is the first Smartlead-originated request the endpoint
has ever received, so everything below is measured, not inferred.

## Checklist

| check | result |
|---|---|
| execution arrived | **yes** - 11602, 07:43:36Z |
| authenticity path | `mode=unconfigured, ok=true` - accepted as designed; warn suppressed (inside the 1h throttle, already fired 07:31) |
| source hint captured | `3.27.18.70 / axios/0.19.2` - real Smartlead sender |
| Normalize populated | **fully** - see below |
| Shadow Log recorded intent | **yes** - 1 entry (`Reply Alert`) |
| real writes | **ZERO** - no write node ran at all |
| ops post identity | `ok=true, channel=C0B8GCVNR5W, bot=Smarlead, app_id=A0BLETEHYBF` - the WF-2 app |
| lead resolution | no person, no lead -> `__no_lead: true` -> `Ops Warn No Lead`. Correct: `pii-ef1d7dcd@example.invalid` is Smartlead's fixture, not a real prospect |
| marker parser | campaign "Link insertion" has no bracket -> all marker fields inert (M9), no false warn |

## Normalize output vs the real payload

```
event            REPLIED          <- from raw_event "email_reply"
campaign_id      100              campaign_name "Link insertion"
sl_lead_id       121              <- from sl_email_lead_id   (B15 fix proven on real data)
sl_lead_map_id   1221             <- from sl_email_lead_map_id
sl_app_url       https://app.smartlead.ai/app/master-inbox?leadMap=123
sender_inbox     pii-41cc012d@example.invalid
lead.email       pii-ef1d7dcd@example.invalid     lead.full_name "Support Test"
reply.subject    "Proposal for Collaboration - smartlead.ai"
reply.message_id <pii-2795c4f6@example.invalid>     reply.stats_id "id"
reply.received_at NULL            <- see F2
hypothesis/event_name/marker_unknown  all null, is_nurture false
```

## Findings

### F1 - `event_type` is `EMAIL_REPLY`, not `EMAIL_REPLIED`. My stated constant was wrong.

I listed the four event types in the registration instructions as "verified from real payloads".
For the reply event that was **wrong**: those came from the Make blueprint sample, whose reply
scenario fires on `LEAD_CATEGORY_UPDATED`, and I filled the gap with an assumption.

It worked only because the discriminator matches on `/repl/` rather than an exact string, so
`email_reply` still routed to REPLIED. The defensive design absorbed my error - but it was an error,
and this test is exactly why it was worth firing. The other three remain unconfirmed by observation
(`EMAIL_SENT`, `EMAIL_BOUNCED`, `LEAD_UNSUBSCRIBED`); the regexes are equally loose
(`first.*sent|email.?sent`, `bounce`, `unsub`), so the same tolerance applies.

### F2 - `time_replied` is not in the `received_at` alias list

The payload carries `time_replied`; my aliases are `reply_time / received_at / timestamp`, so
`reply.received_at` came out null. Cosmetic today (the top-level `timestamp` is populated from
`event_timestamp` and is what the activity uses), but it is a real mapping gap.

### F3 - `from_email` on a reply IS our sending inbox. The open question is answered, favourably.

`from_email = pii-41cc012d@example.invalid` (Smartlead's stand-in for the sending inbox) while the prospect
is in `to_email` / `sl_lead_email` / `leadCorrespondence.replyReceivedFrom`. So the worry raised by
Smartlead's doc sample - that replies might put the lead's address in `from_email` - does **not**
hold for real reply events. Forward-owner resolution via `sender_inbox` is sound, and the
campaign-based fallback resolver stays design-only as agreed.

Caveat worth keeping: this is a fixture inbox, so it is not in `forward_inbox_map`. On organic
traffic the inbox will be a real `toby@...` address and should resolve; `Ops Warn Unknown Inbox`
remains the signal if it does not.

### F4 - the payload's `app_url` and `sl_email_lead_map_id` DISAGREE

`app_url` says `leadMap=123` while `sl_email_lead_map_id` is `1221`. Smartlead's test fixture is
internally inconsistent. Harmless here, and it vindicates the decision to prefer the payload's own
`app_url` over a constructed link: on organic traffic the harness's given-vs-constructed check will
show whether they agree in reality.

### F5 - NEW: Smartlead ships its own category on reply events

The payload contains **`reply_category: "Interested"`** (plus `reply_source: "CAMPAIGN"`). We are not
reading it. That is potentially significant for flip item 1: it offers a zero-cost category signal
while `classify_enabled` is false, either as the primary source or as a fallback the LLM overrides.
Not wired - raising it as a decision, since it changes what the classifier is *for*.

### F6 - **B20: in shadow mode the chain stops at the first gated write.** This blocks the phase.

`Shadow Log` is a terminal node. The gate routes `false` into it, so processing ends there. In this
execution only **one** intent was recorded (`Reply Alert`); the label union, reply activity, SL
category and forward intents were never even computed - `Classify Body` and everything downstream
never ran.

Consequence: **the shadow window cannot compare what WF-2 would have done beyond the first write on
each path.** The diff harness has almost nothing to align, which is most of the point of Phase D.

Fix (not yet applied - it is a topology change): give each write triple a pass-through `Skip <X>`
node on the gate's false branch, wired both to `Shadow Log` (record) and to the same downstream node
the live write feeds. Live behaviour is untouched; shadow traverses the whole graph and logs every
intent. Cost is ~14 nodes plus statics asserting that every gate's false branch continues the chain -
which is also the invariant whose absence let this through.

### F7 - B22: the person-verify GET fires even when nothing was resolved

`R Person Verify` ran with `__person_id` null, requesting `/api/v2/persons/0` and erroring
(swallowed by `continueRegularOutput`, and `Verify Apply` short-circuits correctly). Harmless, but it
contradicts what I said - "one extra GET per **successful** resolve" - and wastes a call on every
no-match event. Fix: gate the verify behind the person-found check.

## Verdict

**The wiring is proven end-to-end.** Registration -> account-level delivery -> our URL -> authenticity
path -> Normalize -> person/lead resolution -> Shadow Log -> ops warning under the correct new Slack
identity, with **zero writes**. Every layer was exercised by a real Smartlead request.

**The shadow phase is not yet able to produce its deliverable**, for two independent reasons:
1. **F6/B20** - only the first intent per path is recorded. Must be fixed before the window means
   anything.
2. **No organic traffic** - the four ACTIVE campaigns last sent 2026-07-22. Replies to the 764
   already-sent emails can still arrive; new sends cannot until someone resumes them.
