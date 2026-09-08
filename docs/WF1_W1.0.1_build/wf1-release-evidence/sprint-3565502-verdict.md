# Campaign 3565502 - "the missing 2000": diagnosis (READ-ONLY, no fixes)

Date 2026-07-27. Source: `leads-campaign-3565502.csv` (2227 rows) + Pipedrive (55695 persons /
56555 leads scanned) + n8n. **No writes of any kind.**

## VERDICT: there is no pipeline hole. It is a reporting / field-mapping gap.

The premise "Pipedrive holds ~17 sprint persons" is off by ~2 orders of magnitude. Delivery worked.

| what was feared | what the data shows |
|---|---|
| ~2000 leads lost | **2105 of 2227 CSV rows (94.5%) exist as Pipedrive persons** |
| replies lost | **94 of 99 repliers (95%) exist** |
| Make scenario off | **3493 persons created Jun30-Jul20 with Medium=eMail, ALL Sales Sprint London** |
| no leads created | **2218 leads titled `3565502 - [Sales Sprint] Sales Sprint 2026 - London - Valids`** (vs 2225 sent) |
| | 40/40 sampled campaign persons have a lead |

### Root cause of the "~17"
**Sprint leads carry the campaign ONLY in the lead title - the lead `Campaign` custom field
(`1cd81dfc...`) is EMPTY on all of them.** That field was introduced by us in W1.0.11 (2026-07-20) for the
HeyReach/LinkedIn path; the Make scenario predates it and does not write it. So any filter, saved view or
report keyed on the lead **Campaign field** returns ~nothing for the entire email side - which is exactly
the shape of a "17".

Second aggravating factor - **invisible-character dirt** in campaign names, which breaks literal matching:
- **non-breaking space inside the marker**: `[Sales\xa0Sprint]` in SIX distinct variants (~5570 persons:
  2689 Switzerland + 1128 Munich/Berlin + 975 European-2025-Valids + 417 Sales Sprint London +
  359 European-2025-Catch-all + 2 singles). A literal `[Sales Sprint]` match misses all of them.
- **en-dash** (U+2013) as separator in the London names (2119 + 1765 + 1).
- stray double / nbsp spaces before hyphens (`Switzerland 2026  - Sergey`, `Germany 2026\xa0 -`).
An ASCII-hyphen filter would return 7923 of 11808 - a different miscount, but the same class of trap.

## 1. Smartlead webhooks - BLOCKED, cannot execute
`SMARTLEAD_API_KEY` is not in the environment (only N8N / Pipedrive / HeyReach) and was never supplied in
this session, so `GET /webhooks` could not be called. **Cheapest confirmation path:** add
`$env:SMARTLEAD_API_KEY = "..."` to the scratchpad env file, then one call lists every webhook with URL,
user/campaign association, event map and `is_active`, and shows which one points at Make
(hook.*.make.com, the 3819669/3819933 territory).
**Note this is now a hygiene check, not the hole hunt** - delivery is already proven by the data above.
It is still worth doing to explain the residual 122 (5.5%) and to confirm nothing is silently disabled.

## 2. Make-scenario output timeline (persons created with Medium=eMail)
Window 2026-06-30 .. 2026-07-20: **3493 persons**, campaign split
**1811 `... - London - Valids` + 1682 `... - London - Catch-alls`** (100% Sales Sprint, nothing else).
Per day: 327 / 363 / 282 / 364 (Jun30-Jul03), then 24 / 240 / 544 / 243 / 59 / 503 / 199 / 345
(Jul08-Jul17). Gaps fall on weekends (Jul 04-05, 11-12, 18-19). **The scenario was not off and did not
stall.** Campaign sending itself ran Jun30 -> Jul27 (2225 sends; peaks 290/299 on Jul20-21).

## 3. The 99 repliers
| set | rows | in Pipedrive | missing |
|---|---|---|---|
| repliers (`got_reply=true`) | 99 | **94** | 5 |
| **Meeting Request** | 2 | **2** | **0** |
| **Do Not Contact** | 3 | **3** | **0** |
| **Not Interested** | 6 | **5** | **1** |

All 94 present repliers sit under `[Sales Sprint] Sales Sprint 2026 - London - Valids` - attribution is correct.
The 5 missing are benign categories: 4x `Out Of Office` (Person-1dc76f4b / The MDU, Person-3010bd1e / Capital
Dynamics, Person-5252ba5e / Marshmallow, James Good / Oxford Economics) + 1x `No Longer Working There`
(Person-16c2a219 / Heathrow). **The only substantive loss is 1 `Not Interested`.**
Campaign CSV context: `lead_status` 2117 COMPLETED / 83 INPROGRESS / 27 BLOCKED; 50 bounced;
`lead_category` filled on 124 (71 Out Of Office, 24 Sender Originated Bounce, 15 No Longer Working There,
6 Not Interested, 3 Do Not Contact, 3 Wrong Person, 2 Meeting Request).

## 4. Sizing
- **Repair backfill: ~122 persons**, not ~2000 (of which 5 repliers, incl. 1 `Not Interested`). Hours, not a project.
- **Optional, and a decision not a bugfix:** stamp the lead `Campaign` field on the ~9687 existing sprint
  leads (2218 for 3565502 alone) if we want ONE lead-keyed reporting model across LinkedIn and email.
  Today the two paths disagree: WF-1 leads carry the Campaign field, Make leads carry it only in the title.
- **Reporting correction:** our earlier guidance "count campaign reach on LEADS, not on the person field"
  holds for the WF-1/LinkedIn path only. For the email path a Campaign-field-keyed lead count returns ~0.
  Any unified dashboard must either parse the lead title or use the person field for the email side.

## Reframed WF-2 case
"We are losing 2000 leads" is not supported - nothing was lost. The honest and stronger argument:
the email path lives in Make with no versioning, no tests, no rollback and no reconciliation, which is why
this question took a full day of forensic reconstruction to answer, and why a naming/field mismatch
(Campaign field never written, nbsp inside the marker) silently misreported an entire channel for weeks.
That is a maintainability and observability case, not a data-loss case.
