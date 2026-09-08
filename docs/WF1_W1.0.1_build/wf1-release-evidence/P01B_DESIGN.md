# P0-1b — per-branch claim-after-success for WF-2's Dedupe

**Status: DESIGNED, NOT DEPLOYED.** Deploy gated on the auditor's independent spot-check (#2:
"assert the claim key is absent from static data after a deliberately failed run, i.e. a replay is
*not* suppressed"). Graph re-derived against live WF-2 `c0ca9eda` before writing this.

## The defect

`Dedupe`, line 21:
```js
if (!duplicate) store.wf2_seen[key] = nowSec;
```
The claim is written **before any work happens**. If the execution then crashes, the event is
permanently unreplayable: `dedupe_max_age_sec` (48h) ≥ WF-2R's `lookback_minutes` (48h), so it ages
out of the reconciler's reach while still being suppressed by the store.

Proven by exec 14966 (Marine's OOO, 15:30:55Z): crashed on the broken `Body Reply Alert`, claim
already written, event unrecoverable by the reconciler that exists precisely to recover it.

## Why this is not a one-line move

```
nodes reachable from EVERY Switch Event branch: NONE
```

There is no single claim point. Worse, **terminal ≠ success**: on the REPLIED branch
`Reply CRM Done` is success and `Ops Warn No Lead` is failure, and both are terminal. Claiming at a
warning terminal would silently discard the event forever — converting a visible failure into an
invisible one, which is the opposite of the fix.

### Terminals per branch, classified

| branch | SUCCESS terminals (claim here) | FAILURE / ambiguous (never claim) |
|---|---|---|
| SENT | `Lead Create`ᴴ, `NoOp Lead Exists`, `NoOp Nurture SENT`, `NoOp Repeat SENT` | `Ops Warn Deleted Person`, `Shadow Log`, `NoOp Person Live` |
| REPLIED | `Reply CRM Done`, `Nurture Alert`ˢ | `Ops Warn Classify`, `Ops Warn No Lead`, `Ops Warn Unknown Inbox`, `Ops Warn Deleted Person`, `Shadow Log`, `NoOp Person Live` |
| BOUNCED | `Bounce Note`ᴴ | `Shadow Log` |
| UNSUB | `U Lead DNC Label`ᴴ | `Shadow Log` |
| UNKNOWN_EVENT | — (see open question) | `Ops Warn Unknown Event` |
| marker check | `NoOp Marker OK` | `Ops Warn Unknown Marker` |

ᴴ = httpRequest node · ˢ = Slack node — **neither can carry code**, which is the structural problem.

## The change

1. **`Dedupe` stops writing.** It keeps computing `key` and `__duplicate` and keeps emitting
   `__dedupe_key` (it already does), plus the existing age-rotation. One line removed.
2. **Four new Code nodes** carry the claim, one per success terminal that cannot hold code:
   `Claim SENT` (after `Lead Create`), `Claim Bounce` (after `Bounce Note`),
   `Claim Unsub` (after `U Lead DNC Label`), `Claim Nurture` (after `Nurture Alert`).
3. **Four existing Code nodes** get the claim appended via the proven IIFE-wrap (original logic
   untouched, builder try/caught): `NoOp Lead Exists`, `NoOp Nurture SENT`, `NoOp Repeat SENT`,
   `Reply CRM Done`.

Claim body, identical everywhere:
```js
try {
  const k = $('Dedupe').item.json.__dedupe_key;
  if (k) { const sd = $getWorkflowStaticData('global');
           (sd.wf2_seen = sd.wf2_seen || {})[k] = Math.floor(Date.now() / 1000); }
} catch (e) { /* not on this branch */ }
```

## Cost, stated plainly

**+4 nodes and +4 connections on a live production workflow.** That is graph surgery, not a config
edit — the thing deliberately avoided all day. It is also unavoidable: three success terminals are
httpRequest nodes and one is a Slack node, none of which can execute code.

## DESIGN CHANGE after re-deriving against `ce1a8355` (2026-08-11)

Re-reading the graph rather than trusting this document caught a flaw in it. **Two of the four
success terminals swallow their own errors:**

```
Bounce Note      [httpRequest]  onError = continueRegularOutput
Nurture Alert    [slack]        onError = continueRegularOutput
```

They continue when the write **fails**. A claim node that fires merely because it was *reached*
would therefore claim on failure — the event is silently lost **and** the failure stays invisible,
which is strictly worse than the bug being fixed. Slack is the sharper case: it reports failure in
the *body* (`ok: false`) with HTTP 200, the exact shape that hid 25 failed posts for eleven days.

So the standalone claim nodes **inspect the response** instead of their own reachability:

| node | after | condition |
|---|---|---|
| `Claim SENT` | `Lead Create` | `$json.data && $json.data.id` |
| `Claim Bounce` | `Bounce Note` | `$json.success === true \|\| ($json.data && $json.data.id)` |
| `Claim Unsub` | `U Lead DNC Label` | `$json.success === true \|\| ($json.data && $json.data.id)` |
| `Claim Nurture` | `Nurture Alert` | `$json.ok === true` |

Generalised: **"terminal" and "reached" are both weaker than "succeeded".** Any claim-after-success
must name the evidence of success, and a node with `onError: continueRegularOutput` upstream makes
reachability worthless as that evidence.

## Statics required before deploy

1. crashed run → key **absent** from `wf2_seen`, replay **not** suppressed *(auditor spot-check #2)*
2. successful SENT with new lead → key present after `Claim SENT`
3. successful SENT with existing lead → key present after `NoOp Lead Exists`
4. successful REPLIED → key present after `Reply CRM Done`
5. REPLIED ending at `Ops Warn No Lead` → key **absent** (failure must stay replayable)
6. BOUNCED / UNSUB → key present at their claim nodes
7. duplicate detection still works when the key **is** present
8. age-rotation still prunes

## Open question for the owner

**`Ops Warn Unknown Event` — claim or not?** An unknown event type will never process, so leaving
it unclaimed means WF-2R re-replays it every cycle for 48h. Claiming it suppresses a genuine
"we don't understand this" signal. Recommendation: **do not claim**; the ops warning fires each
time, which is noisy but honest, and unknown events are rare. Cheap to reverse either way.

## Risk if this ships wrong

Claiming too early → events silently lost (today's defect, unchanged).
Claiming on a failure path → events silently lost **and** the failure invisible.
Not claiming on a success path → duplicate processing, i.e. double forwards — the thing the flip
spent all day eliminating.

All three are silent. That is why this one wants independent eyes before it goes live.
