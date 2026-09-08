# WF-2 defect log - B7 to B14 (found in Phase C, all fixed)

Every entry has a static test that fails against the pre-fix build. Proof:
`wf2-discrimination-proof.txt` (23 mutants, all caught). Suite: 129 tests, 0 failures.

Ordered by how badly it would have hurt.

## B14 - `__skip` was computed by six bodies and enforced by NOTHING

Six write bodies computed `__skip`; no gate, IF, or expression ever read it. Every "skip path" in
the design was decorative metadata.

This **retracts an assurance I gave**: Nik asked to lock "with an EMPTY `category_map` the SL
Category node must be provably unreachable-as-write", and I reported it locked. Test K1 only
asserted that the *body* set `__skip: true` - the POST would still have fired with
`category_id: null`. The same held for a no-lead reply (`PATCH /v1/leads/undefined`), a
nothing-to-change person patch, and the bounce/DNC label writes.

Fix: the gate is the single enforcement point -
`WRITE_MODE === 'live' && $json.__skip !== true`. Skipped writes fall through to `Shadow Log`,
exactly like shadowed ones. Locked by SK1-SK5; K1 was reworded to stop overclaiming.

## B9 - malformed URLs on 23 of 24 HTTP nodes

URLs were built as `base + "={{ path }}"`. An n8n expression field carries ONE leading `=` and text
outside `{{ }}` is literal, so the second `=` was welded into the URL:
`https://api.pipedrive.com` + `=` + `/api/v2/persons`. Every Pipedrive and Smartlead call would
have 404'd. Locked by URL1 (evaluates the template as n8n does) and URL2; the factory now refuses
to build the shape at all.

## B11 - Normalize read an empty payload on EVERY event

Spine is `Webhook -> Respond -> CONFIG -> Normalize`, so Normalize's `$json` is CONFIG's output.
It read `$json.body`, which does not exist there - every field came out empty. Found by reading a
live execution, not by testing: **the static harness fed `{ body: payload }` as `$json`, encoding
the same wrong assumption**. Fix: `$('Webhook').item.json.body`. The harness now models the real
topology, which is why reverting this fix fails 40 tests instead of 0. Locked by NZ1/NZ2.

## B12 - `$json` does not survive an HTTP node, so the label union degenerated

`Body Lead Labels Union` is fed from `SL Forward Email` (HTTP) and from `Mark DNC` (which spread an
HTTP ack). `__lead_labels` was therefore `undefined`, `existing` became `[]`, and the UNION
collapsed into Make's absolute set - **silently dropping manually added labels on the forward and
DNC paths**, the exact bug the union exists to prevent. `Body Reply Activity` likewise lost
`__lead_id` and `__summary` after the labels PATCH.

Fix: context is recovered from the node that OWNS it, by name (`Merge Reply Ctx`, `Lead Resolve`,
`Mark DNC`, `U Mark DNC`, `U Lead Select`), with `$json` as an override only. Locked by UC1-UC5,
which feed an API ack as `$json` the way the node really receives it.

## B7 - no authentication on any HTTP node

All 24 sent only `Content-Type`; every call would 401. `anthropic-version` was missing too.
Pipedrive is now bound to the credential production WF-1 uses (`HnyULgvDdYp0lIkB`). The Smartlead
credential was created via the API (`httpQueryAuth` "Smartlead API", `YXf5ez4pxDNd2g2B`).
Anthropic is deferred - see `classify_enabled`. Locked by AU1-AU5, and the builder prints a
DEPLOY GATE listing any node whose credential is missing.

## B10 - every run answered 500

The webhook lacked `responseMode: "responseNode"` while a Respond node existed, so n8n aborted
each execution with "Unused Respond to Webhook node found". Smartlead disables an endpoint after 5
failures, so this was an outage waiting for the first event. Now matches WF-1: respond first, then
do the CRM work. Locked by WH1/WH2.

## B8 - three Smartlead contract errors

1. `SL Fetch Lead` called `/campaigns/{cid}/leads?email=`, a verified **400**. Correct: `/leads?email=`.
2. `Apply Enrich` resolved `data[0] ?? [0] ?? data ?? {}`, which yields `{}` against the real flat
   response - enrichment was silently dead on every SENT event.
3. `Pick Last Message` took the last history entry, so a follow-up landing after the prospect's
   reply would have made us forward **our own** outbound email. Now anchors on the last `REPLY`.

Locked by SC1-SC5, with recorded live responses as fixtures.

## B13 - the no-lead reply path attempted writes with a null id

A reply whose lead cannot be resolved walked the whole CRM chain and issued
`PATCH /v1/leads/undefined` -> 400 -> the execution errored, which also killed the `Ops Warn No
Lead` post that should have told a human. Confirmed on the live double (execution 11540). Fixed via
B14's gate plus a lead-id requirement in the labels body. Locked by SK4/SK5.

## Harness lessons applied

- A static test is only as good as its fixture's fidelity to the real node input (B11, B12).
- Assert the *evaluated* artifact, not the raw string that looks plausible (B9).
- Body-level intent is not enforcement; assert the graph can't do the thing (B14).
- A mutant must assert that it actually applied - mutant 20 silently stopped matching when the
  code it targeted changed, and reported a false pass until the guard was added.
