# 2026-08-11 — Finding 4: reply-side lead resolution could only see 7 days of leads

Owner: fix-owner session. Authorized: "FINDING 4 FIX — GO NOW, ahead of P0-1b."
Live: WF-2 `jp7rum9Z0YDJkQWv` versionId **cd318c57**, 145 nodes, active. Pollers paused/unpaused
around every PUT; all three PUTs via `n8n_deploy_util.put_body`.

## DONE

**The defect, restated correctly.** `R Lead List` read `/v1/leads?limit=500&sort=add_time DESC` with
no pagination. That page spans **2026-08-11 → 2026-08-04**; the collection is **≥18,000 leads**.
So ~97% of the CRM was invisible to reply-side lead resolution — silently, on every reply.

Wire evidence:
* **23 of the last 34** reply executions reaching `Lead Resolve` returned `__no_lead`, **every one**
  carrying `__leads_page_saturated: True`. The blindness flag was computed correctly and never read.
* Three sampled victims have **live** leads outside the window, all added 2026-07-21:
  `pii-4acbb413@example.invalid` → `95d4bfd0`, `pii-840d936c@example.invalid` → `df711600`,
  `pii-ebd365bc@example.invalid` → `b8c00640`. Their reply-side CRM updates were dropped.

**The fix (W1.0.18).** Pagination on `R Lead List` iterating **candidate persons**: one
`?person_id=<candidate>` request per entry in `__person_candidates`, cap 10. `Lead Resolve` unions
the responses. Every B27 rule is byte-identical — candidate-set membership, campaign-field match,
title-prefix fallback, oldest-wins provisional, person adoption. 8/8 statics **execute the real
node body**, including the original spec's case (4 duplicates, lead on the 4th → found + adopted)
and a 429-truncation case. No graph change, no fan-out, 1 request in the common case.

**Two corrections I owe on my own earlier reporting:**
1. The "unexplained page absence" I asked to log as a Pipedrive anomaly **was not an anomaly**. The
   fixture lead `72ec85c0` is **archived**, and `Lead Resolve` filters archived leads by design — so
   `lead=None` in the P0-1 live proof was *correct behaviour*. The 4 REDs there were not this defect.
2. I reported "≥6,000 live leads, 92% invisible". 6,000 was **my walk loop's cap**, not the end of
   the data — a measurement artifact stated as a finding. Correct: **≥18,000, ~97%**.

**Platform facts established on the wire** (all in `wf1-system-reference.md` §9b / §9b.0a / §9c.3):
* `archived_status` is **silently ignored** by `/v1/leads` — `all` / `archived` / `not_archived`
  return byte-identical id sets, zero archived rows. Archived leads are unreachable from any list read.
* `person_id=A,B` and repeated `person_id=` → **HTTP 400**. One request covers one person.
* n8n's pagination option is a **fixedCollection**: the value lives at
  `options.pagination.pagination.{…}`. Writing it one level shallower survives the PUT, reads back
  as a populated object, and is **silently ignored**. Cost me one wasted deploy; caught only because
  the read-back asserted `maxRequests == 30` instead of `if options.pagination:`.
* **Pagination expressions CAN reference other nodes** (`$('X').first().json`) — proven by WF-2S
  `SL Statistics` and WF-2R `SL Leads Statistics`, both live. This is what made the fix possible
  inside one node, after I had wrongly called the original spec structurally impossible.

## PARTIAL

**Not yet wire-proven.** The statics prove the body; only a real reply proves the pagination. The
next genuine reply should show `__lead_candidates_read` ≥ 1 and `__lead_read_errors: 0`. I did not
manufacture one: replaying a real prospect's reply through WF-2 would fire a real forward and real
CRM writes on a real person. Waiting for the wave is the honest instrument.

**Offset-walk version shipped and was replaced within the hour** (5fbd32d5 → cd318c57). It passed
10/10 statics and was not wrong, but 30 pages × 500 rows *per reply* is the same pattern that
rate-limited the token during evidence gathering, and its 15,000-row cap cannot be shown to be
exhaustive against a collection larger than that. Both intermediate versions are behaviourally
safe; neither is live.

## DONE — 4c: SENT / BOUNCE / UNSUB (authorized by Nik, landed pre-wave)

Live **versionId `ce1a8355`**, 145 nodes, active. `Lead List` / `B Lead List` / `U Lead List` are
person-scoped like R; `Lead Select` / `B Lead Select` / `U Lead Select` union the candidate
responses. **24/24 statics**, eight per branch, each executing the real node body.

**One branch was not like the others, and it was the dangerous one.** `B Lead List` ← `B Lead Ctx`
and `U Lead List` ← `U Lead Ctx` are direct inputs that already emit `__person_candidates`, so
their pagination expressions can name them safely. SENT's `Lead List` ← `IF Have Person Id` ←
`Person Id Final`, which emits only `__person_id`; its candidates live in `Person Pick`, several
hops back and **not on every path** (the create-person route bypasses it). A pagination expression
naming a node that did not execute **throws**, and unlike `Lead Select`'s `try/catch` an expression
has nowhere to catch it — with `onError: continueRegularOutput` that throw becomes an empty read,
which `Lead Select` reads as "no existing lead" and the branch **creates a duplicate**. Strictly
worse than the bug. Fix: `Person Id Final` (already reading `Person Pick` in a try/catch) now
carries `__person_candidates` forward, and SENT's expression names *it* — always executed. Fallback
for a freshly created person is `__person_id`, which is correct: a new person has no leads.

## DONE — P0-1b statics (built, NOT deployed, correctly gated)

`build_p01b_claim_after_success.py`, **24/24 pass**, nothing written. Deploy stays gated on the
auditor's spot-check availability **and** a clean first wave hour.

Re-deriving the graph against `ce1a8355` instead of trusting `P01B_DESIGN.md` **caught a flaw in my
own design**: `Bounce Note` (httpRequest) and `Nurture Alert` (slack) both carry
`onError: continueRegularOutput` — they continue when the write *fails*. Claiming on reachability
would have claimed on failure: event lost **and** failure invisible. The claim nodes now inspect the
response (`$json.ok === true` for Slack, `success`/`data.id` for Pipedrive). Slack is the sharp
case — failure in the body with HTTP 200, the shape that hid 25 failed posts for eleven days.

Also closed a hole in my own statics: the four IIFE-wrapped inline sites were originally only
*printed* ("N lines, wrapped"), which proves nothing — the same shape that let a syntax-valid but
broken `Body Reply Alert` ship. They are now executed, and each wrapped body is compared against
the unwrapped original's output, so the wrap is *shown* to be behaviour-preserving.

`Ops Warn Unknown Event` does not claim, per Nik. Net change when it deploys: +4 nodes,
+4 connections (145 → 149).

## API BUDGET — complied, coordinated

Nik's rule (auditor has Pipedrive priority until it reports; everyone else single-record only;
announce bulk windows *before* starting; the wave's own traffic exempt and sacred) is recorded in
the reference doc as **§9b.0c**. Messages sent to the Хранитель/DNC session (superseding my earlier
"tonight, ~18k rows" plan — now double-gated on the wave *and* the auditor's report, announced
first) and to the Аудитор session (telling it that it has priority so it does not self-throttle,
plus the two platform traps that could silently corrupt a Melisa-facing count).

Everything since has been n8n-API and local-static work only — zero bulk Pipedrive reads.

## REGRESSION I INTRODUCED, AND FIXED — the candidate off-by-one (W1.0.19, `1f3410dd`)

The person-scoped pagination shipped with `completeExpression = $pageCount >= (cands.length - 1)`.
n8n evaluates that AFTER each response with `$pageCount` already incremented, so it stops **one
candidate short**. It only bites when there are duplicate persons — exactly the case B27 exists for.

Live proof, exec 15239 (the second fixture reply):

```
__person_candidates      [84885, 84886, 84887, 85506]
R Lead List emitted      3 items  =>  3 requests    <- 85506 NEVER QUERIED
__lead_candidates_read   3
__lead_read_errors       0
__leads_page_saturated   True
__no_lead                True
```

85506 is the person holding the fixture lead. Not index lag (a re-read at the same moment returned
it), not the `|| -1` path (candidates populated). My own statics could not have caught this: they
执行 the `Lead Resolve` body against mocked pages, and the defect lives in the **pagination
expression**, which only exists at runtime. Statics proved the body; only the wire proved the loop.

**The saturation flag caught my bug.** `__leads_page_saturated: True` because 3 read < 4 candidates.
The sensor worked exactly as designed — and it reached Nik only as a generic "no matching lead"
warning, because that flag still has no consumer (§9b.0b). Sensor good, wiring to a human absent.

Fix: `>= cands.length` on all four list nodes. Safe under either n8n semantic — worst case is one
extra request with `person_id=-1`, which matches nothing.

## SECOND DESIGN ERROR THE SAME RUN EXPOSED — P0-1b claimed a half-processed event

Exec 15239 reached `Reply CRM Done` and claimed its dedupe key **while `__no_lead` was true** —
person-side writes only, no lead work done. "Reached a success terminal" and "did the work" are not
the same thing, which is the identical confusion P0-1b was built to fix, one level up. A half-
processed reply was made unreplayable for 48h.

Guard added: claim only when `__no_lead === false`; if `Lead Resolve` cannot be read at all, do
**not** claim — an unnecessary replay is absorbed by dedupe and existence checks, a wrongly-claimed
event is lost. 4/4 statics execute the real body, including the exec-15239 case.

## KEY RELEASES (staticData via PUT, same window)

* `wf2_seen` 15 → 13: released the fixture specimen `REPLIED|3686187|4306240392|1786452347000` and
  **Marine** `REPLIED|3686184|4214180591|1786375820000` (auditor assertion 4 — dedupe TTL and WF-2R
  lookback are both 48h, so they expire together and the event never self-recovers).
* `__alert_delivered` 1 → 0: released `'84885'`. Checked for other dupe-set ghosts as asked — the
  registry held exactly one entry, so it is now empty.

**Expected consequence, stated in advance:** Marine's event (2026-08-10T15:30:20Z, ~21h old, inside
WF-2R's 48h lookback) will be replayed on WF-2R's next cycle, producing a real forward and CRM
writes for pii-6389984a@example.invalid, and — post channel switch — an alert into C07LTD8UT70.

## BLOCKED / NEEDS NIK'S WORD

*(RESOLVED — Nik authorized it; see "DONE — 4c" above. Original entry kept for the record.)*

**The same defect exists on three more branches — SENT, bounce, unsub — and SENT is the wave path.**
`Lead List`, `B Lead List`, `U Lead List` all carry the identical URL, and `Lead Select`,
`B Lead Select`, `U Lead Select` all carry the identical `const leads = ($json.data ?? []) || [];`
and `>= 500` saturation. `Lead List` → `Lead Select` is the SENT branch's *"does a lead already
exist?"* check — so a lead older than seven days is invisible and the branch **creates a second
one**. That is a standing mechanism for the B24 duplicate-lead problem, and it fires on every wave.

Not deployed: authorization was for `R Lead List` / `Lead Resolve`, and this touches the send path.
The change is mechanically identical and the anchors are byte-identical, so it is one word away.

## IMPROVABLE

* **I exhausted the Pipedrive rate limit** gathering this evidence (429 on every page, backoff
  exhausted) despite the standing instruction to share the API budget with Хранитель's projections.
  The duplicate-lead quantification (`(person, campaign)` groups with >1 lead, split by whether the
  duplicate appeared >7 days after the original) is written and unrun for that reason. It is the
  number that sizes the SENT-side decision.
* One of my probes returned "0 leads walked" and reported it as a clean empty result — the exact
  empty-vs-unrun confusion in §9b. Fixed to raise on failure, but it shipped in a probe first.
* `__leads_page_saturated` was emitted truthfully on all 23 failing executions and nobody consumed
  it. Worth a digest line: a blindness flag nobody reads is not a safety net.
