# Auditor spot-check #2 — P0-1b claim-after-success, on WF-2 `838274f4`

Read-only. Swept 2026-08-11T12:46Z–12:52Z. Target: `versionId 838274f4-01d3-44db-a062-25fe0638e9d1`,
149 nodes, deployed `2026-08-11T12:42:24.957Z`, `versionCounter 517`.

**VERDICT: P0-1b PASSES.** 4 of 6 checks pass outright, 1 partial, 1 fails.
Two items outstanding before this is closed: **Marine's key is still claimed**, and **the alert path
did not execute on this version**.

| # | assertion | verdict |
|---|---|---|
| 1 | `Dedupe` no longer claims | **PASS** |
| 2 | failed run leaves no key → replay not suppressed | **PASS structurally · NOT EXERCISED live** |
| 3 | successful run leaves the key → replay suppressed | **PASS — proven live** |
| 4 | Marine's key released | **FAIL — still present** |
| 5 | alert regression (`alert_text`, `__alert_delivered`) | **PARTIAL — static only** |
| 6 | `ce1a8355` / `\|\| -1` fold-in | **PARTIAL PASS** |

---

## 1. `Dedupe` no longer claims — PASS

`Dedupe` retains exactly one write, and it is not the claim:

```js
if (n.event === 'SENT' && !firstSentSeen) store.wf2_seen[sentKey] = nowSec;   // S|campaign|lead
```

That is the first-SENT sequence memo on a different key, and the code says so. `duplicate` is still
computed and `__dedupe_key` still emitted; only the claim left.

The claim now lives on **eight terminals** — the four new nodes plus four pre-existing ones I checked
by grepping every node for a `wf2_seen[...] =` write:

`Claim SENT` · `Claim Bounce` · `Claim Unsub` · `Claim Nurture` *(new, 145→149 nodes)*
`Reply CRM Done` · `NoOp Nurture SENT` · `NoOp Repeat SENT` · `NoOp Lead Exists` *(pre-existing)*

**The reply path is covered** — via `Reply CRM Done`, which is what mattered for Marine. And the claim
nodes assert a real success signal rather than reachability:

```js
const __ok = (() => { try { return ($json.success === true || ($json.data && $json.data.id)); } catch (e) { return false; } })();
```

with the onError nuance called out in the node's own comment ("Bounce Note carries
onError: continueRegularOutput — claiming on reachability would claim on failure"). That is the right
distinction and it is the one that would have been easy to get wrong.

## 2. A failed run leaves no key — PASS by construction, not yet by experiment

No pre-terminal path retains a claim write, so a crash before a terminal cannot register the key.
But **no failure has been fired on `838274f4`**, so this is proven by reading the graph, not by
observing a crash-then-replay. Stated as such rather than banked.

## 3. A successful run claims — PASS, proven live

Exec **15239**, `2026-08-11T12:46:19.936Z → 12:46:33.529Z`, `status: success`, real Smartlead webhook
(`__reconciled: false`):

```
[Dedupe]  __dedupe_key = REPLIED|3686187|4306240392|1786452347000   __duplicate = false
wf2_seen  REPLIED|3686187|4306240392|1786452347000 -> 1786452393  (= 2026-08-11T12:46:33Z)
```

The claim timestamp equals the execution's **stop** time, not its start — the write happened at the
terminal, after the work. That is the property P0-1b was for, and it is now on the wire.

**Outcome check on the Smartlead wire, independent of n8n:**

```
2026-08-11T12:45:47Z  REPLY    stats 284d27db-8dd6-4117-b1ec-b93485483150
2026-08-11T12:46:32Z  FORWARD  stats 284d27db-8dd6-4117-b1ec-b93485483150
```

Exactly one reply, exactly one forward. `SL Forward Email → ok: true`.

## 4. Marine's key — FAIL, still claimed

```
REPLIED|3686184|4214180591|1786375820000  ->  1786375857  (2026-08-10T15:30:57Z)
```

Still in `wf2_seen` as of 12:47Z, ~21 hours after the crash that registered it.

Why it still matters even though it will rotate out: `dedupe_max_age_sec` is 48 h, so `Dedupe`'s
rotation deletes it at ≈ **2026-08-12T15:30:57Z** — and WF-2R's `lookback_minutes` is also 48 h
(2880). **The key becomes replayable at the same moment the event ages out of the reconciler's
reach**, so it never becomes automatically recoverable. Release it explicitly, or Marine stays a
manual item. (Her content is an OOO autoresponder, so the manual action is small — but it should be a
decision, not an expiry.)

## 5. Alert regression — PARTIAL, static only

- `Body Reply Alert` **declares `alert_text`** on `838274f4`. ✅ (static read)
- `__alert_delivered` exists and holds one row: `{"84885": 1786443307}` (stamped 10:15:07Z, from the
  earlier fire on `70e3ec4e`). ✅

**But the verification fire did not exercise the alert path.** Exec 15239 took:

```
First Reply Gate -> __should_alert: false, __alert_reason: "already_delivered", __alert_key: "84885"
path: ... First Reply Gate > IF Should Alert > Classify Body ...   (no Body Reply Alert, no Reply Alert)
```

The gate is working exactly as designed — `__lead_id` is null (the fixture lead is archived), so the
registry key fell back to person `84885`, which was already delivered at 10:15:07Z. One alert per
person, correctly suppressed.

The consequence is that **`Body Reply Alert` has not run on this version.** A static declaration check
is precisely what `45637e70` passed yesterday before dying at runtime, so I am not counting it.

**To close it:** either fire from an address whose resolved person/lead is not in
`__alert_delivered`, or clear `__alert_delivered["84885"]` and re-fire, or set
`flags.alert_every_reply = true` for one fire. Any of the three exercises the node; none needs a new
deploy.

## 6. `ce1a8355` / `|| -1` fold-in — PARTIAL PASS

**Fixed:** all four reads (`Lead List`, `R Lead List`, `B Lead List`, `U Lead List`) now carry the
`__person_id` fallback — `R Lead List`'s omission, which was the substantive half of my finding, is
closed. Person-scoped pagination confirmed: `updateAParameterInEachRequest`, `maxRequests: 10`,
`requestInterval: 150`, `limitPagesFetched: true`.

**Unchanged:** I tested the sentinel. `person_id=-1` → **HTTP 400**, identical to `person_id=0`
(and to `''` / `null`). It fails closed — no unfiltered page, no stranger's lead can match — but with
`onError: continueRegularOutput` the degenerate case is still a **silently-empty read**,
indistinguishable from "this person has no lead". The sentinel value changed; the failure mode did
not. Low severity now that the fallback exists (the sentinel is only reachable when both
`__person_candidates` and `__person_id` are absent), but it is not resolved.

## New signal from the first live exercise of the new resolver

`Lead Resolve` reported **`__leads_page_saturated: true`** on exec 15239, and the definition has been
correctly rewritten for person-scoping:

```js
const saturated = cand.length ? ((__pages.length - __errs) < cand.length) : false;
```

With 4 candidates (`84885, 84886, 84887, 85506`) and `maxRequests: 10`, `saturated: true` means
**fewer than 4 candidate reads succeeded** — i.e. at least one candidate was never successfully read.
`R Lead List` returned `rows: 0, success: true` on the item I could see.

So either a candidate read genuinely failed and is being swallowed by
`onError: continueRegularOutput`, or the page-count arithmetic over-reports when a candidate has zero
leads (n8n may emit one merged item rather than one per empty page). **The flag is doing its job by
firing; nobody has resolved which of the two it is.** On this fire it changed nothing — the fixture's
lead is archived, so `__no_lead: true` was correct either way — but on a real reply it is the
difference between "no lead exists" and "we failed to look". Worth one execution's worth of
attention before real volume.

---

## What I would still hold the sentinel on

1. **Marine's key** (item 4) — release or explicitly decide the manual path.
2. **The alert path unproven on `838274f4`** (item 5) — one fire, no deploy needed.
3. The saturation signal above — diagnose, don't leave ambiguous.

Everything else about P0-1b is clean, and the design decision (assert a success signal, not
reachability) is the right one.
