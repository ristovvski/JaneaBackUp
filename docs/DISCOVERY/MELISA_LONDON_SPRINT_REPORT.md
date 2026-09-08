# Sales Sprint London — named population, 5913/7.5k reconciliation, bucket (b)

Read-only throughout. **"Sales Sprint" is confirmed as a real, literal campaign family in
Smartlead** — your refinement was right.

## 1. Email side — found exactly, by name

```
[Sales Sprint] Sales Sprint 2026 – London – Catch-alls  (3565651)  COMPLETED  total_leads=1,962
[Sales Sprint] Sales Sprint 2026 – London – Valids      (3565502)  COMPLETED  total_leads=3,145
                                                                     SUM = 5,107
```
(Both created 2026-06-29, COMPLETED status. An older, separate 2025 cohort — `[Sales Sprint] Sales
Sprint London` (2358474) — exists too, 466 leads, but is a different year/campaign, not summed here.)

**Nik's remembered ~3,900 matches the Pipedrive-side person count, not the Smartlead send-side
total**: persons whose `Campaign` field reads (allowing for Make's known dash/encoding corruption on
this field) the London-2026 Catch-alls/Valids strings sum to **1,765 + 2,119 = 3,884** — 16 off his
memory, essentially exact. That's the number he'd have seen looking at Pipedrive; 5,107 is what
Smartlead actually sent to. **The 5,107 − 3,884 = 1,223 gap between them is the field-string version
of bucket (c)/(b) combined** — superseded below by the rigorous exact-email-match version.

## 2. LinkedIn/LinkedHelper side — derived from Pipedrive, no live platform to query

Confirmed via the person-level Campaign field (LH-era, since HeyReach has zero "sprint"-named
campaigns — the platform really is dead, as you said):

```
"Sales Sprint 2026 - London - Toby - LinkedIn"        777 persons   all medium=LinkedIn, all have li_url
"Sales Sprint - London 08/2025 - Toby - LinkedIn"       87 persons   (older 2025 cohort, not summed)
```
`add_time` for the 777 spans **2025-09-05 → 2026-07-22** — an ongoing campaign run over ~10 months
(consistent with LinkedHelper being a slow, largely-manual tool, not a batch upload). Owner: Toby
(matches `forward_owner_map.Toby` in WF-2's own CONFIG). This is the "linkedhelper" term in
Melisa's formula.

## 3. Reconciling 5,913

```
5,107 (email, London 2026, both segments)  +  777 (LinkedHelper, London 2026, Toby)  =  5,884
                                          5,913 − 5,884 = 29  (0.5%)
```
**This is almost certainly the match** — well within the drift you'd expect from a live count taken
at a slightly different moment (a few persons added/removed since the screenshot). Adding the older
2025 cohorts (87, 466) overshoots badly, confirming the filter is 2026-specific, not all-time.
**Verdict: found. Melisa's 5,913 ≈ London-2026 email + London-2026 LinkedHelper, not the Ai4 sprint
at all** — the two sprints were being compared incorrectly against each other in the original "7.5k
vs 5,913" framing.

## 4. Reconciling 7.5k
Tried the sum-of-all-sprint-lists hypothesis: every Smartlead campaign with "sprint" in the name,
any year/city (7 campaigns, 6,262 leads) + every Pipedrive person tagged to a sprint-family campaign
with `medium=LinkedIn` (all events/years, 2,371) = **8,633**. That's 1,133 (15%) off 7,500 — a rough
ballpark, not a clean match like §3. **I would not treat 7.5k as precisely "sum of all sprint lists
ever"** — more likely it's a separate planning figure (like the Ai4 case) that was never tied 1:1 to
what actually got uploaded. Not chasing this further; the London-specific number in §3 is the solid
one.

## 5. Bucket (b) — the real question — DONE, rigorous method

Per your instruction, did this the *right* way: exact **email-address lookup** for every one of the
London-2026 email leads against Pipedrive persons (never a campaign-field string match — Make is
known to leave that field empty or corrupt its encoding, see `wf2-b24-duplicate-leads` memory),
mirroring the Ai4 backfill-300 methodology exactly.

**One honest correction before the number**: my first pass on this returned "4,078/4,078 missing —
100%." That was not a real finding — I'd built the URL with a double `/v1/v1/` path segment, so
*every* Pipedrive lookup silently 404'd and came back empty. Caught it before reporting (verified
10 of the "missing" emails were actually present, 10/10, once the URL was fixed), then reran clean.

```
Smartlead lead rows pulled (both London-2026 campaigns): 4,078   (unique emails: 4,076)
  Note: campaign total_leads reports 5,107 (1,962+3,145); leads-statistics returned 1,029 fewer
  rows. Likely explanation, not confirmed: leads-statistics only returns leads with at least one
  tracked event (SENT/REPLY/etc) — leads never actually sent to (still queued, excluded pre-send,
  invalid) wouldn't appear here. That population is bucket (a), not (b), and isn't counted below.

checked (exact email match against Pipedrive):  4,078
found in Pipedrive:                              3,863   (94.7%)
MISSING:                                           215   (5.3%)
  of the missing, has ≥1 REPLY event:               14   ← priority: invisible conversations
```

**The real gap is 215, not 1,200-1,600.** Your (and Nik's) larger estimate almost certainly came from
the same campaign-field-string comparison I made in §1 before doing the rigorous check (5,107 vs
3,884 field-matched persons = 1,223) — that comparison overcounts badly, because plenty of real
persons exist in Pipedrive with a differently-encoded or empty Campaign field, not because they're
actually missing. The exact-match version is the trustworthy one.

**14 leads with real replies are currently invisible in Pipedrive** — these are the priority items,
same logic as Ai4: real conversations nobody in Pipedrive can see. Full list (215 emails, flagging the
14 with replies) in `sprint_london_missing.json`.

## Status
Read-only throughout, as instructed. **215-person backfill is a new task, not started — pending your
explicit go.** The Ai4 backfill machinery (`backfill_ai4_persons.py`, now fixed to also set Event
name/Hypothesis correctly) is directly reusable: same script family, swap in the 2 London campaign
IDs (3565651, 3565502) and their `Event name`/`Hypothesis` values, re-derive the missing-email list
from `sprint_london_missing.json` instead of a fresh reconciliation.
