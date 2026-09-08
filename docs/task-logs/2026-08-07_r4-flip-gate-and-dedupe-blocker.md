# 2026-08-07 — R4 flip gate PASSED, and it uncovered a flip blocker

## Done — R4 gate: 4/4

Controlled lead `pii-c61c7d08@example.invalid` (id `4306240392`) added to campaign 3686187 on 2026-08-06
16:17Z; send fired 16:56:56Z from `pii-95552f54@example.invalid`; Nik replied; Smartlead recorded it
**2026-08-07T08:11:00Z**.

| stage | evidence | verdict |
|---|---|---|
| 1 Smartlead recorded the reply | 818-byte body, "Sounds interesting, tell me more" | PASS |
| 2 WF-2R polled 3686187 and replayed | exec 14115 08:45:03Z, ring=hot, batch=1, `accepted` | PASS |
| 3 WF-2 executed and shadow-logged | exec 14116, `REPLIED`, 55 nodes, 4 shadow rows | PASS |
| 4 claim-after-success held | `marked=1 failed=0 store=1` | PASS |

Classifier: **Information Request, confidence 0.87**. Forward resolution:
`pii-95552f54@example.invalid` → owner **Rune** → `rune@janeasystems.com`. `WRITE_MODE=shadow`
throughout — computed, logged, nothing sent. The reply path is proven end to end.

Delta digest flipped from `0|0|0 — path unverified` to **`1 | 1 | 0 — matched`**.

## The blocker this found — my own, and it would have hit at flip

Making the digest's "last real inbound webhook" line replay-aware revealed that **Smartlead's reply
webhook is working**: it delivered a genuine event at **08:11:55Z, 55 seconds after the reply**
(UA `axios/0.19.2`, distinct from WF-2R's `axios/1.18.0`). So WF-2 saw this reply twice.

WF-2's Dedupe key is `event|campaign_id|sl_lead_id|timestamp`, joined from **raw strings** — so it
compares formatting, not time:

```
exec 14110  genuine webhook  REPLIED|3686187|4306240392|2026-08-07T08:11:00+00:00
exec 14116  WF-2R replay     REPLIED|3686187|4306240392|2026-08-07T08:11:00.000Z
                                                        ^^^ same instant, different string
```

`duplicate=False` on the second. Both ran in shadow, so **nothing was written** — but in
`WRITE_MODE=live` this reply would be **forwarded twice and activity-logged twice**. That is the
same double-forward class already blocking the flip on Make's side, and I introduced it by adding
a second delivery path.

**Fix prepared, NOT deployed** (`patch_wf2_dedupe_canon.py`): key on `Date.parse` epoch ms with a
raw-string fallback for unparseable values. Verified locally — the two observed formats collapse to
one key, a genuinely different reply stays distinct, unparseable degrades to today's behaviour.
One expression, one node; store name, event, campaign_id and sl_lead_id untouched so existing
claims stay valid. Needs the owner's word: it edits live production WF-2.

## Consequence worth stating plainly

**WF-2R's premise narrowed.** Smartlead's webhook delivers replies fine; the 2026-08-04/05 loss was
WF-2 being *down*, not Smartlead failing. WF-2R is an outage-recovery net, not a primary path — and
while WF-2 is in shadow it is harmless, but it must not be active when WF-2 goes live until the
dedupe fix lands.

## Improvable

The digest's probe filter keyed on user-agent, and WF-2R's replay shares Smartlead's axios UA — so
for one run the reconciler's own replays would have kept "last real inbound webhook" permanently
fresh even if Smartlead's delivery were dead: exactly the blindness the line exists to remove. Now
keyed on Normalize's `__reconciled` stamp, with replays reported separately. Third digest
correction today; each was caught before it could mislead, but the pattern is that a metric which
*looks* healthy needs an adversarial read before it ships.
