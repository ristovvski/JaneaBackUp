# Melisa's ask — "didn't we target 7.5k? email+LinkedHelper=5913, why 1,200-1,600 missing?"

Read-only throughout. **Headline finding: neither 7,500 nor 5,913 matches what was ever actually
loaded into Smartlead/HeyReach for this sprint — the real, twice-independently-confirmed total is
2,174.** This reframes the question: the gap isn't 1,200-1,600 lost contacts inside a ~7.5k
population — it's that the sprint's outbound tools never held more than 2,174 people in the first
place, for either number.

## 1. What "7.5k" cannot be

I have **not found "7,500"/"7.5k" written anywhere** — not in Smartlead, not in HeyReach, not in
any file on disk. Both platforms were checked exhaustively:

**HeyReach** (account-wide, only 6 campaigns exist, period):
| Campaign | Status | List size (raw upload) | Campaign totalUsers |
|---|---|---|---|
| Mario - LinkedIn (512995) | IN_PROGRESS | 611 | 611 |
| Rune - LinkedIn (513000) | IN_PROGRESS | 656 | 656 |
| "Final TEST" / "Final test" (×2) | PAUSED | 1,344 each, list **"GTM People"** | — not Ai4-named |
| "TEST" / "TEST2" | FINISHED | 2 each | — dev tests |

The raw upload list size **exactly equals** the campaign's `totalUsers` for both real Ai4 campaigns
— there is no bigger hidden source list behind either one. **True LinkedIn ceiling: 1,267.**

**Smartlead** (117 campaigns account-wide, 7 contain "ai4" in the name, any status):
| Campaign | Status | total_leads |
|---|---|---|
| Rune-Catch-alls (3686193) | ACTIVE | 227 |
| Rune-Valids (3686187) | ACTIVE | 204 |
| Mario-Catch-alls (3686184) | ACTIVE | 206 |
| Mario-Valids (3686181) | ACTIVE | 254 |
| "[Events Visiting] AI4 2026 - Rune" (3756410) | ACTIVE | 16 |
| AI4 2025 - Catch-alls (2342850) | COMPLETED | 33 |
| AI4 2025 - Valids (2342830) | COMPLETED | 91 |

2026-cohort email total: **907**. (2025-cohort, out of scope for this sprint: 124.)

**Combined real Ai4-2026 outbound total: 1,267 (LinkedIn) + 907 (email) = 2,174.**

## 2. Cross-validated in Pipedrive, exactly

Persons with `Event name = "Ai4 2026"` (the field WF-1/WF-2 stamp from the campaign's own two-bracket
name, verified this session): **exactly 2,174.** This matches the Smartlead+HeyReach sum to the
digit — meaning **every single contact ever loaded into either outbound tool for this sprint has
already landed correctly in Pipedrive with the right tag.** Zero loss on this metric, for the current
2026 cohort specifically.

## 3. The 5,913 hunt — thorough, not exact

I could not derive 5,913 precisely and am reporting that honestly rather than forcing a match
(same discipline as the "372" derivation). What I tried, all on the fresh 56,626-person Pipedrive
scan:

| Filter | Result |
|---|---|
| `medium` ∈ {LinkedIn, eMail}, all-time | 50,417 |
| has a LinkedIn URL on file, all-time | 50,139 |
| `event_name = "Ai4 2026"` | 2,174 |
| `event_name` contains "ai4" (2025+2026) | 2,217 |
| lead/person `Campaign` field contains "ai4" | 4,675 |
| `medium` ∈ {LinkedIn, eMail}, added since 2026-06-01 | 6,692 |
| `medium` ∈ {LinkedIn, eMail}, added since 2026-07-01 | 6,248 |
| `medium` ∈ {LinkedIn, eMail}, added since campaign launch (07-18/19) | ~2,480 |

**Closest candidates: ~6,151-6,692**, all still off by 250-800, all requiring a date window I had to
guess (no exact match at any calendar-boundary cutoff I tried). None of these represent "email +
LinkedHelper" as a clean, sprint-scoped population the way `event_name="Ai4 2026"` does.

**My read:** 5,913 most likely comes from a **broader, not-sprint-scoped filter** — e.g. "everyone
ever sourced via LinkedIn or email, recent months" rather than "this specific Ai4 2026 sprint." If
that's right, comparing it against a 7.5k *sprint-specific* target is comparing two different
populations, which would fully explain why neither number reconciles against the campaign data.
**Recommend: get the actual filter/screenshot rather than continuing to guess** — I've exhausted the
reasonable derivations without a hit.

## 4. Your bucket framework, evaluated against real evidence

Real numbers, not assumptions:

- **(a) Uploaded but never contacted:** Doesn't quite fit as framed — the real issue is *upstream* of
  "uploaded but idle." Only 2,174 were ever uploaded to begin with, against a stated 7.5k target.
  Whatever the other ~5,300 were meant to be, they don't exist as campaign rows in either tool.
- **(b) Contacted but lost to Make (pre-restoration):** **Zero, for the current 2026 cohort** — the
  event_name cross-validation in §2 proves 100% of the 2,174 already carry the right Pipedrive tag.
  The "5,469 all-time missing" figure you're recalling is a *different, older, all-time* metric,
  already resolved for this batch by yesterday's backfill-300 (confirmed 0 remaining, this session).
- **(c) In Pipedrive but invisible to a field-based filter:** This is real and I already fixed a
  version of it — the 373-person Event-name/Hypothesis gap (separate report). If 5,913's filter
  happens to also key on those two fields, some of the gap would close automatically now.
- **(d) Dedupe (same human, both channels):** Measured directly: of the 2,174, **680 carry both a
  LinkedIn URL and `medium=eMail`** — real cross-channel overlap exists, but it does **not** inflate
  the 2,174 count (Pipedrive holds one record per person regardless), so dedupe doesn't explain a gap
  *below* 2,174 — if anything it would only matter for a population *larger* than 2,174.

**Verdict: your bet (mostly b + d) doesn't hold up against the evidence.** The dominant, provable
fact is structural: **the sprint's outbound reach (2,174) never came close to 7,500**, and (b) is
already a non-issue for the current cohort. (d) is real but small and doesn't explain a shortfall.

## 5. One-liner for Melisa
"Checked both tools end to end: HeyReach and Smartlead never held more than 2,174 people for this
sprint — 1,267 on LinkedIn, 907 on email — and every one of them is already correctly tagged in
Pipedrive, zero lost. That's the real ceiling; it doesn't match either 7.5k or 5,913, so one of those
two numbers is almost certainly scoped differently (a broader all-time count, not this specific
sprint) — can you send me the exact filter or screenshot behind the 5,913 so I can match it byte for
byte instead of guessing?"

## Status
Read-only, as scoped. Nothing written. Data: `sprint_persons_fields.json` (56,626 persons),
`sprint_full_totals.py`/`sprint_heyreach_lists.py` outputs (platform totals).
