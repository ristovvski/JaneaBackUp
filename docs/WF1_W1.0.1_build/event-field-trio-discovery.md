# Discovery: event-field trio (Event name / Medium / Marketing Hypothesis) - who fills them + vocabulary

**READ-ONLY.** Production WF-1 W1.0.11.1 (versionId 2b9eeda0). No changes made. Date 2026-07-20/21.
Anchor: person 83244 "Person-45bca53f", lead "512995 - Ai4 2026 - Mario - LinkedIn - Person-45bca53f".

## 1. Field table (all three are PERSON fields, all varchar / free text)
| field | entity | key | type | vocabulary (de-facto) |
|---|---|---|---|---|
| **Event name** | person | `ab5540d2ca45905dfb1434c0fe4971cc5790de3f` | varchar | `"{Event} {Year}"`, no brackets. e.g. Ai4 2026 (220), HumanX 2026 (46), TechEx North America 2026 (42), Pharma USA 2026, ITEXPO 2026, ViVE 2026, eMerge Americas 2026... Only ~423 persons populated (event-visiting cohort only). Casing drift: ViVE vs ViVe. |
| **Medium** | person | `961698945b0329b367da11916a94f10ff7ba71fe` | varchar | eMail (1962), **LinkedIn (824)**, Event App (39), In Person (12 / "In person" 3), typo "LinkedIm" (1). WF-1 writes this (W1.0.11). |
| **Marketing Hypothesis** | person | `8bdae1a91272e92b335e9e99f668cde659b6daae` | varchar | **Sales Sprint (2330)**, **Events Visiting (405)** + casing drift "Events visiting" (47) / "Event Visiting" / "Event visiting"; plus bracket-derived one-offs: Trigger-based Campaign, Events Non-Visiting, Lead Nurture, AI Case Based, SRPP, Exploratory. One value had a non-breaking space ("Sales Sprint"). |

(Sample: 3000 most-recently-updated persons. None of the three is an enum - all free text, so casing/format is not enforced.)

**Our Medium write matches exactly.** WF-1 writes `"LinkedIn"` (capital L, capital I) - identical to the 824-record house value. The only mismatch in the whole base is a single manual typo "LinkedIm".

## 2. Person-45bca53f timeline (person 83244)
| event | timestamp (UTC) | source |
|---|---|---|
| person + lead created (connection_request_sent), Medium='LinkedIn' set | 2026-07-20 **13:50:42** | WF-1 (post-resume; W1.0.11 convention title + Campaign field) |
| lead labels | [cold] only - **NOT replied** | - |
| person last update (Event name='Ai4 2026' + Hypothesis='Events Visiting' present) | 2026-07-20 **20:38:58** | NOT WF-1 (we never write these) - ~6h49m after creation, evening UTC |

Note: a duplicate older "Person-45bca53f" (person 50174, 2025, lead "Person-45bca53f | Progress Lead") also exists - member_id/two-Lule dedup class, unrelated to this question.

Ed is **not replied** yet his trio is fully populated, and the fill landed **~7h after** WF-1 created him - not seconds-after (not a reactive Zap), not at his event time.

## 3. Replied vs NOT-replied (40 Ai4-2026 persons sampled)
| group | n | Event name filled | Hypothesis filled | distinct values |
|---|---|---|---|---|
| REPLIED | 2 | 2/2 | 2/2 | Ai4 2026 / Events Visiting |
| NOT-REPLIED | 38 | 38/38 | 38/38 | Ai4 2026 / Events Visiting |

**100% filled regardless of reply status; values perfectly uniform.** Timing across the sample: person add->update gap was **>2h for all 40** (min 5.45h, median 30.6h, max 50.9h; ZERO within 60s, ZERO within 2h), and last-update **clusters at ~20:00 UTC** (36/40). (update_time is last-write; our own Phase-D medium backfill touched these earlier the same day, so the exact 20:00 cluster is the writer re-running after us - but breadth + uniformity are independent of that.)

## 4. Verdict: AUTOMATION (broad, scheduled batch) - NOT Silva's per-reply manual step
Three independent signals converge:
1. **Breadth** - painted on ALL Ai4 leads (replied + not), not only replied/processed ones.
2. **Uniformity** - 40/40 byte-identical "Ai4 2026" / "Events Visiting" (a human would drift in casing/format; this cohort has none).
3. **Timing** - hours after creation, never seconds-after, clustered in a daily evening window - a scheduled batch, not a reactive Zap and not WF-1's per-event writes.

**Best guess who:** a marketing-ops automation (Zap or scheduled tool, same family/owner as the campaign-assignment + labeling automation - Melisa/Marci) that **derives Event name + Marketing Hypothesis from the campaign-name convention**. Evidence for the derivation: campaign/lead names carry a bracketed prefix that maps 1:1 to the Hypothesis field -
- `[Events Visiting] HumanX 2026 - Catch-alls` -> Hypothesis "Events Visiting", Event "HumanX 2026"
- `[Trigger-based Campaign] Newly Hired Heads of AI` -> Hypothesis "Trigger-based Campaign"
and those exact bracket strings appear verbatim as Marketing Hypothesis values in the base.

Melisa mentioned a Silva manual human-in-the-loop step on the call; the data says the **trio specifically is automated** (broad + uniform + batched). Silva's manual step is likely something else (responded-labeling / QA / curation), or Silva curates/triggers the batch - but he is not hand-typing the trio per replied lead.

## 5. Bonus - Smartlead/email leads
- **Marketing Hypothesis for email leads = "Sales Sprint"**, stamped **at creation** (add->update gap ~0s; 46 of 48 sampled within 60s) - i.e. the Smartlead/Clay import pipeline sets Medium="eMail" + Hypothesis="Sales Sprint" as an import-time default, a DIFFERENT mechanism from the event-batch trio-painter.
- Email sprint leads have **Event name mostly empty** (16/81) - consistent (they are not event-visiting).
- Example campaign name carrying the bracketed hypothesis convention: **`[Events Visiting] AI4 2025 - Catch-alls`** (and `[Trigger-based Campaign] Newly Hired Heads of AI`).

## 6. Implications - what a future WF-1 event-field writer must match
- **Vocabulary:** Event name = title-case `"{Event} {Year}"`, no brackets (e.g. `Ai4 2026`); Marketing Hypothesis canonical = `Events Visiting` (capital V - avoid the "Events visiting" drift); Medium `LinkedIn` (already matches). All free-text, so we must self-enforce exact casing.
- **Shared ownership:** these fields already have an automated writer (the event-batch trio-painter). If WF-1 starts writing Event name / Hypothesis, we'd be co-writing with it - so we must either (a) write byte-identical values it would produce (so its later batch is a no-op, no flip-flop), or (b) agree ownership with Melisa/Marci the way we did for Medium (W1.0.11). Because the batch overwrites hours later, mismatched values would churn.
- Deriving them ourselves is feasible from data WF-1 already has: campaign.name -> the "[Hypothesis] Event Year" convention gives both Event name and Marketing Hypothesis. (Note the current Ai4 HeyReach campaign names are `Ai4 2026 - Mario/Rune - LinkedIn`, which do NOT carry the bracket - so the batch is mapping via list/campaign metadata, not only the raw name; confirm the source before replicating.)
