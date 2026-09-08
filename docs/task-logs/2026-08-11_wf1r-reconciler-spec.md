# SPEC — does WF-1 need its own reconciler (WF-1R)? Decision for tomorrow

Written 2026-08-11 night. **Spec only**; no build, no deploy. The port comes first, the net second —
that ordering is deliberate and argued below.

## The question

WF-2 has two nets: claim-after-success (P0-1b) so crashed events stay replayable, and WF-2S/WF-2R to
*actually* replay them. Tonight proved you need both — 32 events were unclaimed and still stranded
because nothing re-detected them (§9b.0e).

WF-1 has **neither**. Its `Dedupe` claims at decision time, and no reconciler exists.

## What changes with the P0-1b port alone

After the port, a crashed WF-1 execution leaves its key unclaimed. HeyReach will *not* re-deliver
the webhook, so nothing replays it automatically — but the event stops being permanently suppressed,
which means a manual or scheduled sweep *can* recover it. The port converts "silently lost" into
"recoverable if someone looks".

That is a real improvement and it is not sufficient on its own.

## Is a reconciler feasible? Yes — the read exists

`POST /api/public/inbox/GetConversationsV2` is proven readable (346 conversations, 1,221 messages
pulled tonight for the Melisa sweep). Each conversation carries `correspondentProfile`,
`lastMessageAt`, and a `messages[]` array where `sender == "CORRESPONDENT"` marks an inbound reply
with its `createdAt`. That is everything a reconciler needs to answer "did a reply arrive that we
never processed?"

`GET /campaign/GetAll` and `POST /stats/GetOverallStats` are also proven, so campaign scoping and
volume checks are available.

## Volume argument — the case for NOT building WF-1R yet

| | WF-2 (email) | WF-1 (LinkedIn) |
|---|---|---|
| events/day | hundreds (88 SENT in one wave today) | ~185 |
| burst shape | 20 concurrent replays | organic, 30% overlap |
| replies/day | handful | **0 today**, low single digits typically |
| existing net | WF-2S + WF-2R | none |

WF-2 needed reconcilers because its SENT volume made losses invisible in the noise and its replay
bursts *created* the crashes. WF-1's reply volume is small enough that a **daily gap check** — not a
15-minute reconciler — would surface a miss the same day.

## Recommendation

1. **Port P0-1b first** (agreed for the next deploy). It is the precondition: a reconciler cannot
   recover an event whose key was already burned at decision time.
2. **Do NOT build a full WF-1R immediately.** Instead extend the existing **WF-1H daily digest**
   with a gap line: conversations with an inbound `CORRESPONDENT` message in the last 24h that have
   **no** corresponding WF-1 execution. Same shape as the delta digest that caught the reply gap
   originally — cheap, and it makes the loss rate visible before we build machinery to fix a rate we
   have not measured.
3. **Decide on WF-1R after one week of that gap line.** If it reports zero, claim-after-success plus
   the digest is enough. If it reports misses, build WF-1R with WF-2R's proven shape (rotation
   cursor, `lookback_minutes` exceeding the longest plausible outage, claim-after-success on replay).

**Why this order:** tonight's lesson is that a net you have not measured the need for can itself
become the hazard — WF-2S's replay bursts caused the very crashes it then failed to recover. Adding
a second bursting replayer to WF-1 before knowing WF-1 loses anything would repeat that.

## If WF-1R is built later — non-negotiables carried from WF-2

* replay requests **spaced** (≥ one execution duration), never a burst — §9c.2d
* its producer store must be part of the atomic-claims migration from day one, or §9b.0e's
  two-store trap is recreated
* claim on **replay success**, and the gap check must read the provider (HeyReach), never our own
  executions — our executions prove what we did, never what arrived

## Open input needed from Nik

Whether LinkedIn replies are ever expected in volume (a new event campaign could change the numbers
overnight). The recommendation above assumes low single digits per day; if a campaign resume pushes
that to dozens, build WF-1R immediately rather than measuring first.
