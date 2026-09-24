# Item 4 — WF-1 early ack: what has to exist before it moves, and what I recommend instead

**Ack NOT moved. Nothing deployed for this item.** Agreed with the auditor's call, for a reason that
turned out to be different from the one stated — and the difference changes what to build.

## The auditor's hazard, corrected

> *"a processing failure before `DT Lead Claim Set` + a HeyReach retry = duplicate person and lead"*

The direction is right, the mechanism is not. Walking the create path:

```
PID Resolved → Deal Search → Lead Search (/v1/leads?person_id=…) → Lead Create Gate
   ├─[1] lead exists ────────────────────────────────▶ Select Existing Lead
   └─[0] no lead → Lead Claim Key → DT Lead Claim Get → Lead Claim Gate → IF Lead Claimed
                                                          ├─[0] claimed ▶ Select Existing Lead
                                                          └─[1] ───────▶ Create Lead
```

The claim row is **not** the only guard. `Lead Search` + `Lead Create Gate` is a real existence
check against Pipedrive, matching on the lead Campaign field (W1.0.11). The claim was added as a
*second*, durable layer for the cross-execution race the list read cannot see. So a duplicate needs
**both** guards to miss:

1. `Lead Search` misses the lead attempt 1 just created (read-after-write lag, worst exactly in the
   seconds after a create), **and**
2. the claim row is absent because attempt 1 died between `Create Lead` and `DT Lead Claim Set`.

Narrower than stated — but that conjunction is precisely the shape of "died immediately after
creating the lead", so the recommendation stands.

**And the person is a different story again.** `Person Create` hangs off
`Person Search Member → IF Member Verified[1]`, a resolver, not a claim. A replay re-runs the search
against a person who now carries the LinkedIn identity, so it adopts rather than duplicates. The
person half of the hazard is largely already handled.

## The thing that actually blocks the move — and it is not the lead claim

`Dedupe` sits at ingress, before every external write:

```js
const key = (body.correlation_id && body.correlation_id !== nil) ? body.correlation_id
          : [body.event_type, body.lead?.profile_url, body.timestamp, body.conversation_id].join('|');
const sd = $getWorkflowStaticData('global');
if (sd.seen[key]) return [];        // a repeat of the same event is DROPPED here
```

A HeyReach retry carries the same `correlation_id`, so **today a retry never reaches the create path
at all — it is dropped at the door.** Two consequences the plan has to face:

**(a) The dedupe store is staticData.** Same lost-update class as the four stores ported this week;
its dual-write to `wf_claims` (`DT Claim Seen`, key `S|<correlation_id>`) is already in place but the
node's own comment says *"staticData above is UNCHANGED and remains authoritative"*. Under a burst,
the map that suppresses retries is the one mechanism most exposed to being clobbered.

**(b) Suppression is not resumption.** Move the ack, let HeyReach retry, and `Dedupe` throws the
retry away — so the half-processed event stays half-processed and we have bought nothing except a
slower response. **A late ack is only worth having if a retry can resume**, and nothing in WF-1
resumes today.

That is the real ordering constraint, and it is invisible if you look only at the lead claim.

## Proposal, in the order I would build it

### 1. Port the dedupe store — do this regardless of the ack (small, same pattern as the four)

Promote the existing dual-write to authoritative: `DT Seen Get` before the decision, decide from the
row with a positive shape check, keep staticData as the write-only rollback copy. Fifth and last of
the WF-1/WF-2 staticData stores. Worth doing on its own merit: it is the store guarding against
duplicate *processing*, and it is currently the least durable thing in the receiver.

**Does not enable moving the ack.** It makes retry suppression reliable — which is the opposite of
what a late ack wants.

### 2. Two-phase claim — the actual enabler, and a real piece of work

`in_flight` before the first external write, `done` after the last; the read-gate treats `in_flight`
as claimed so a concurrent sibling is suppressed, and an `in_flight` older than N minutes is the
**replay signal** rather than a create signal. On that signal the recovery path must re-resolve from
truth (person by identity, lead by person+campaign) and *adopt* what exists instead of creating —
otherwise the resume is itself the duplicate.

Also needs `Dedupe` taught the difference between "same event, already finished" (drop) and "same
event, previous attempt died" (resume) — the two are one key today.

Nodes touched: `Dedupe`, `Lead Claim Key`, `Lead Claim Gate`, `DT Lead Claim Set`, plus a new
recovery branch. This is a structural change to a live receiver's hot path, with its own pre-post.

### 3. Then, and only then, move Respond to Webhook

Measured: p50 4.14 s, p99 5.29 s, max 6.04 s over 184 executions; ack currently at +0.00 s. The
open number is **HeyReach's webhook timeout**, which is not in our measurements. Take it from
HeyReach's documentation or a deliberately slow endpoint of our own — **never** by making production
WF-1 slow to find out. If the timeout is not comfortably above 6 s with margin, the move is off
regardless of items 1 and 2: a timeout looks like a failure and earns a retry, so a too-slow ack
manufactures the very retries we would then have to make safe.

## What I would actually recommend

**Keep the early ack, and build a WF-1 reconciler instead.**

The estate already has this exact shape solved once: WF-2R replays missed replies from provider
truth, on a schedule, off the hot path. A WF-1R that re-walks recent HeyReach events and reconciles
them against the CRM would cover the whole lost-execution class — crashes, OOMs, deploys mid-flight,
and the double-miss window above — without adding a resume protocol to a 138-node live receiver, and
without making the response time load-bearing.

Item 2's `in_flight` machinery would still be worth having eventually. But it buys retry safety for
a retry channel we do not currently need, whereas a reconciler buys recovery for failures we have
already had. Different cost, same coverage, and it fails soft.

**Sequencing if you want it anyway:** item 1 now (it is small and independently right), item 3's
timeout number established from documentation, item 2 as its own project with its own pre-post, and
the ack moved last — one change, one window, with the duplicate-lead count as the acceptance metric.
