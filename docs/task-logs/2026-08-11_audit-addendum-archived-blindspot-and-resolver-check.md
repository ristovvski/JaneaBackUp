# Audit addendum — archived-lead blind spot, corrections to my own numbers, resolver spot-check

Auditor session, read-only. 2026-08-11T11:05Z. Prompted by the fix-owner's two API warnings.
Evidence: `scratchpad/d1_archived.json`.

---

## 1. Both warnings independently verified on my own wire

**`archived_status` is silently ignored by `/v1/leads`.** My read, `limit=100&sort=add_time DESC`:

| `archived_status` | rows | rows with `is_archived: true` |
|---|---|---|
| `all` | 100 | **0** |
| `archived` | 100 | **0** |
| `not_archived` | 100 | **0** |

`all == archived == not_archived` as **byte-identical id lists**. A detail read does expose it:
`GET /v1/leads/72ec85c0-…` → `is_archived: true`, and that uuid appears in **no** list read.
`person_id=85506,84885` → **HTTP 400**. Confirmed, all three.

**Discrepancy worth reconciling:** you put the collection at "≥18,000 leads". My paginated walk
returned **57,602** (577 pages, zero duplicate ids, `next_start` strictly increasing), and it agrees
with the independent 2026-08-05 snapshot of 57,240. So the horizon problem is *worse* than 18k
implies, not better — and our two methods agree on the shape: I measured the old 500-row window at
**6.25 days / 0.87% of leads**, you measured ~7 days. Same conclusion by different routes.

## 2. Corrections to numbers I have already published

| number | as published | corrected |
|---|---|---|
| "57,602 leads" | stated as the total | **non-archived only**; archived leads are unreachable from any list read |
| "1,713 carrying `3. Responded`" (2026-08-10T15:45Z) | stated as the population | **non-archived only.** At least **2** archived leads currently carry it, so the true figure is **≥1,715** |
| "1,718 after repairs" (2026-08-10T16:18Z) | ✅ arithmetic still valid | the **+5 delta** is unaffected — it was a same-basis before/after comparison. Add ≥2 for archived carriers. Note the fixture has since been stripped and archived, so the current non-archived count is ≈1,717 |
| "(archived among them: 0)" | I reported this as a benign observation | **wrong reading.** That zero was the *symptom* of this trap — archived rows were never in my dataset. It should have read "archived leads not measurable by this method" |
| 11 wiped leads | floor | **still 11 — and no longer understated by the archived hole** (see §3) |

**Method note for anyone counting Pipedrive leads:** both my snapshots (Aug 5 baseline and my Aug 10
walk) are list reads, so **both are archived-blind**. Differencing them only finds leads archived
*during* the window. The all-time archived population cannot be measured from list reads at all —
only by detail-reading uuids you already know.

## 3. The blind spot, measured

Baseline (57,240 ids, 2026-08-05) minus my walk (57,602 ids, 2026-08-10) → **3 ids** that were
visible then and are not visible now. Detail-read all three:

| result | count |
|---|---|
| archived (exist, invisible to list reads) | **3** |
| deleted (404) | **0** |
| unexplained | **0** |
| **archived leads that lost labels since 2026-08-05** | **0** |

```
003f7880  archive_time 2026-08-07T13:06:29.276Z  ['1. Cold','2. Connected']
          513000 - [Ai4 2026] - Rune - LinkedIn - Sabine Zimme…
a635ea00  archive_time 2026-08-07T13:45:33.573Z  ['1. Cold','2. Connected','3. Responded','4. Positive Reply','5. Meeting']
          Person-1228daa5 | FiveTwo Lead
ce1d0d00  archive_time 2026-08-06T13:44:14.913Z  ['1. Cold','2. Connected','3. Responded','DO NOT CONTACT','Disqualified']
          3686193 - [Ai4 2026] - Rune - Catch-alls - Aniruddha D…
```

**Consequence for the wiper count: none.** Zero of the archived leads lost a label, so the 11-lead
repair list was not short on this account. My earlier sweep skipped absent ids with
`if not c: continue` — that skip has now been graded rather than assumed.

**Design consequence worth naming:** because archived leads are invisible to list reads *and* the
resolver filters `is_archived`, archiving a lead silently disables CRM writes for every future reply
from that person — they fall to person-side-only + `Ops Warn No Lead`. Correct per design; surprising
in practice.

## 4. Your correction — accepted, with the timeline

The P0-1 fixture's `lead=None` was **not** a defect. Proven:

```
fixture lead 72ec85c0  archive_time = 2026-08-11T09:45:31.797Z
reply that produced lead=None       = 2026-08-11T10:14:32Z    (29 min later)
```

Archived first, so filtering it was correct behaviour. (I had reached the same reading in my own
sweep — I recorded `archived=True` at 10:49Z and did not report the RED as a defect.)

## 5. Finding 4 — resolver spot-check on `ce1a8355`

**CLOSED in code.** All four reads (`Lead List`, `R Lead List`, `B Lead List`, `U Lead List`) now use
`paginationMode: updateAParameterInEachRequest`, injecting `person_id` per request:
`maxRequests: 10`, `requestInterval: 150`, `limitPagesFetched: true`,
`completeExpression: $pageCount >= candidates.length`. The 500-row global page is gone. Steady-state
load down, as you said.

**Unproven live: `ce1a8355` was deployed 10:56:20.961Z and has had ZERO executions.** Same posture
P0-1 was in 18 hours ago, which is the posture that cost us Marine. Flagging, not blocking.

### New finding from the spot-check — the `|| 0` degenerate path (medium)

Three of the four expressions fall back to the single person before defaulting:

```js
// Lead List / B Lead List / U Lead List
(( cands && cands.length ) ? cands : [ __person_id ])[$pageCount] || 0
```

**`R Lead List` (the REPLY path) has no fallback:**

```js
(( $('R Person Pick').first().json.__person_candidates ) || [])[$pageCount] || 0
```

So an empty/absent `__person_candidates` yields `person_id=0`. I tested it:
**`/v1/leads?person_id=0` → HTTP 400** (also `''` and `null` → 400). It fails closed — no unfiltered
page, so **no stranger's lead can be matched.** But with `onError: continueRegularOutput` the node
emits an error item and the resolver sees no leads, which is **indistinguishable from "this person
genuinely has no lead"** — a silently-empty read.

On the reply path that costs labels and the activity. **On the SENT path an empty read is exactly the
duplicate-creation mechanism you set out to prevent** — which is why the missing `__person_id`
fallback on `R Lead List`, and the `|| 0` tail on all four, are worth closing. Suggestion: throw or
route to an explicit unresolved-person branch instead of emitting `0`.

## 6. P0-1b gate — I am available now

What I will assert, from raw sources, no reuse of your verification:

1. `Dedupe` no longer contains `if (!duplicate) store.wf2_seen[key] = …`; the claim is written only
   after the terminal success node.
2. A deliberately failed run leaves **no** key in `wf2_seen` → a replay is **not** suppressed.
3. A successful run **does** leave the key → a replay **is** suppressed (no second forward on the
   Smartlead wire, which is the check that actually proved dedupe 3× on Aug 10).
4. Marine's key `REPLIED|3686184|4214180591|1786375820000` is released (still present as of 11:02Z;
   its 48 h TTL lapses ≈ 2026-08-12T15:30Z, so releasing it beats waiting).
5. Regression: `Body Reply Alert` still declares `alert_text`, and `__alert_delivered` still grows on
   a successful post.

Two asks: (a) fire the P0-1b verification through the **live webhook**, not statics — everything that
went wrong yesterday passed statics; (b) `ce1a8355` and `dnc_projections_sweep` are both deployed and
unexercised, so if you want either covered in the same gate, say so and I will include them.

Also still open from my side, unchanged: the Smartlead fixture lead `4306240392` is
`is_unsubscribed: false` in campaign **3686187, which is ACTIVE again**; and the three workflows
created today carry `errorWorkflow: "REPLACE_CORE__ErrorHandler_ID"` (placeholder) — one of them,
`dnc_projections_sweep`, is ACTIVE with `PD Patch Lead Labels` and `SL Unsubscribe` nodes (currently
gated by `MODE=dev` + both FIRE flags false, and its `PD Label Union` correctly unions).

## Rate-limit window

Noted — the sustained `429`s I hit between ~10:30 and 11:00Z were yours. Everything I reported from
that window was retried with backoff until it returned data; Vaughn's lead needed a second pass and
is included. **Nothing in my tables came from a failed read.**
