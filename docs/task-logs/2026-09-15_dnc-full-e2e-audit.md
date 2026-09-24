# DNC full end-to-end audit — n8n registry → Pipedrive 686 → Supabase (1 Sep → 15 Sep 2026)

Read-only, real traffic. No writes to any table; one live test call against `dnc_pre_add_gate`
(a classification-only endpoint) and 3 throwaway probe workflows (deployed, fired, deleted) to
read Supabase/n8n data directly. Full raw dumps in `SUPABASE_PROJECTION_build/audit_out/`.

## Headline

Registry↔Supabase plumbing (the thing built this week) is clean: exact row-count match, 0 field
mismatches, queue depth 0, gate blocking correctly. **The gap is upstream**: three Pipedrive-facing
DNC writers have effectively never run at production scale, so a large share of what correctly
enters the n8n registry never reaches Pipedrive's DNC field or the CRM label/lifecycle side at all.

| # | Workflow | Live status | Real executions ever | Root cause |
|---|---|---|---|---|
| 1 | `dnc_projections_sweep` (id `8qVXtI2ez5o6a9hc`) — writes Pipedrive custom field "DNC Status" (key `9c018b7406ebc481b9c108a487f76c4d09f91c9b`, option **686**) + labels | active=true, **webhook-trigger only, no schedule, no caller anywhere in the estate** (47 workflows scanned, 0 referrers) | 2, both manual test fires 2026-09-08 | Never wired to a cron or a caller after being built 2026-08-11 |
| 2 | `dnc_s2_meeting_to_dnc` (meetings → `meeting_dnc`) | **inactive** | 1, a one-time backfill 2026-08-18 against a frozen 2026-08-14 snapshot | Never turned on / scheduled after the backfill |
| 3 | `dnc_s3_creation_watcher` (sales-owned → `sales_personal_outreach`) | active, cron every 15 min, all runs succeed | continuous | Polls **only** `GET /v1/leads?sort=add_time desc&limit=100` — never `/v1/persons`. Roster-owned **persons with no lead record** are structurally invisible to it. Confirmed: 84/144 of the found misses have no lead at all. (`poll_limit=100` window currently spans ~2.7 days of org-wide lead creation — not the binding constraint.) |

`PD Merge Write Paths` inside #1 (Merge "append", 3 inputs, fed by 3 converging per-item outcome
branches) is the same unreliable fan-in shape flagged earlier this session
([[n8n-multi-input-node-fires-per-branch]]) — secondary risk once #1 is actually scheduled; not
yet exercised at real volume so unverified at scale.

**None of these three have been touched.** Per project standing protocol, no live changes without
Nik's explicit GO — this log only reports.

## Bonus finding: today's digest patch has a wiring bug

`dnc_morning_digest`'s 2026-09-14 Supabase-mirror patch fired for the first time today
(exec 55858, 2026-09-15T04:00Z) and posted `Supabase mirror: UNREACHABLE` — even though Supabase is
fully healthy (confirmed: 25,733 rows, synced within seconds). Traced live:
- `Supabase Mirror Check` and `Supabase Meta Check` both succeeded (200, real data).
- `Supabase Mirror Agg` correctly computed `supabase_reachable=true, supabase_rows=25733,
  supabase_age_min=0`.
- But `No Match Count` (further down the same accumulator chain, which everything including
  `Compose` ultimately reads) rebuilds its object from **`$('Changelog Count').first().json`** — a
  named reference hardcoded during the 2026-09-03 simplification, predating today's patch. The
  three new Supabase nodes were spliced into the direct-wire chain *after* `Changelog Count` but
  `No Match Count` never reads the direct wire, so their output is silently dropped before
  `Compose` ever sees it.
- Fix (not yet applied): point `No Match Count`'s `prev` read at whatever node is now last before
  it in the direct-wire chain (`Supabase Mirror Agg`'s eventual successor), not at `Changelog
  Count`. Needs Nik's word before patching, same as the three sweeps above.

## Rule-by-rule

### Rule 1 — Replied (Smartlead + HeyReach), since 1 Sep

Registry: 69 rows, reason=`reply_dnc`, all sourced from 4 event campaigns (FinovateFall-Noah,
BioTechX Boston-Mario, Ai4-Rune, Ai4-Mario). Ground truth (Smartlead: swept all 97
historically-active campaigns; HeyReach: swept all 836 conversations, cross-referenced against
actual campaign membership to exclude 37 unrelated organic/inbound LinkedIn messages):
73 genuine replies. 686 field checked directly against live Pipedrive for all 69.

| Status | Count |
|---|---|
| Genuine replies found (Smartlead + HeyReach) | 73 |
| → in n8n registry | 69 |
| → in Supabase (mirrors registry 1:1, confirmed) | 69 |
| → Pipedrive 686 field actually set | **1** (Person-451d4581 only) |
| **Missing from registry entirely** | **4** |

**Named misses (stopped at Layer 0 — never reached the registry):**
| Name | Identity | Campaign | Reply time(s) |
|---|---|---|---|
| Person-054b9bef | linkedin.com/in/pii-732f4f86 | FinovateFall 2026 - Noah - LinkedIn | 2026-09-01 15:56, 16:08 |
| Burak Aksar, PhD | linkedin.com/in/pii-74a1f082 | FinovateFall 2026 - Noah - LinkedIn | 2026-09-01 18:41 |
| Person-19f1d00c | (SLC Corp, CEO) | FinovateFall 2026 - Noah - LinkedIn | 2026-09-01 20:11, 09-02 16:42 |
| Person-58accf5a, CRPC®, CPRC | linkedin.com/in/pii-9857e430 | FinovateFall 2026 - Noah - LinkedIn | 2026-09-01 20:32, 09-02 23:03 |

All 4 are on 2026-09-01/02 — the first two days of the window; worth a separate trace of WF-1/M7's
reply-detection step for that specific period if it recurs.

**Named misses (registered correctly, but stopped at Layer 2 — Pipedrive 686 never written):**
all 68 of the 69 registry rows except Person-451d4581, including the 4 cases you named directly
(Ben Leeds — pid 86593, Person-d86d9627 — pid 85878, Person-f5f25c02 — pid 86064, Jim McCarthy — pid
86510: all confirmed UNSET live). Full list: `audit_out/since_sep1_reply_dnc.jsonl`.

**Reverse-check — 2 quality issues found sitting IN the registry:**
| Name | Row | Issue |
|---|---|---|
| Person-8768306e | heath-tarbert-b2140a15 | Self-corrected already: status=removed, removed_reason=false_reply_empty_body. Not a live issue. |
| Person-d9409383 | pii-d56d390e@example.invalid, 2026-09-09 | **Confirmed false positive, still active.** Reply body is a pure out-of-office auto-reply ("I am currently out of the office... contact Client Relations at 619-876-5074"). Smartlead's own classifier tagged it `Out Of Office`; it still landed in `reply_dnc`. |
| Person-b27663e9 | pii-140009b7@example.invalid, 2026-09-09 | **Borderline, still active.** Reply reads as an automated mailbox-inactive notice ("This email account is no longer active..."), Smartlead tagged `No Longer Working There`, not a live human reply. |

### Rule 2 — Meetings (label "5. Meeting" ∪ deal stage "Qualified Meeting Set", Janea Systems
Consulting pipeline), since 1 Sep

Registry: **0** rows, reason=`meeting_dnc`. Root cause: **`dnc_s2_meeting_to_dnc` is inactive**,
last (only) run was a one-time backfill 2026-08-18 against an 2026-08-14 snapshot — nothing has
been evaluated for meetings since. At least one real, named miss found:

| Name | Pipedrive id | Evidence |
|---|---|---|
| Chirag R Shah | person 86650 | Added 2026-09-14 via a Surfe-sourced deal owned by Jim Ash, deal sitting in **Qualified Meeting Set** stage. Double-miss: qualifies for both Rule 2 (meeting_dnc) and Rule 3 (sales_personal_outreach, Surfe signal) — in registry under neither. |

A full Rule-2 sweep (every label-5/stage-change since 1 Sep, not just the ones incidentally caught
chasing Rule 3) was not exhaustively completed — the inactive workflow is itself sufficient proof
of a systemic gap; treat the true miss count as "≥1, likely more."

### Rule 3 — Sales-owned (Toby/Mario/Jim/Noah/Rune/Matt/Chrissy/Person-f55206df as creator-or-owner;
Melisa/Slava as creator only), since 1 Sep

Registry: 10 rows, reason=`sales_personal_outreach` (Noah ×7, Slava ×2, Jim Ash ×1).

Roster check: "Matt", "Chrissy", "Person-f55206df" do **not** appear as owner/creator on any Pipedrive
lead touched since 1 Sep — can't confirm or deny they exist as Pipedrive users at all, just zero
activity in-window under those names. Worth a direct user-list check outside this audit.

Ground truth (persons owned by Toby/Jim Ash/Mario/Noah/Rune since 1 Sep, leads
created-or-owned by the same + creator-only Melisa/Slava):

| Owner | Persons since 9/1 | Leads since 9/1 (creator or owner match) |
|---|---|---|
| Toby | 0 | 0 |
| Jim Ash | 2 | (Person-64ef02e6, above) |
| Mario Stalder | 44 | — |
| Noah Keimach | 108 | — |
| Rune Jensen | 0 (persons) | 11 (all Rune, all leads) |
| Melisa (creator-only) | not checkable — Pipedrive `getPersons` has no creator field | 0 (all her lead ownership is automation/API-attributed, correctly excluded) |
| Slava (creator-only) | not checkable (same reason) | 2, both already in the known-10 |

154 unique roster-touched persons/leads found since 1 Sep. Cross-checked against the full n8n
registry (not just the known-10) to separate real gaps from records already correctly DNC'd under
a stronger reason:

| | Count |
|---|---|
| Already in registry (10, reason=sales_personal_outreach) | 10 |
| Already in registry under a **different, stronger** reason (mostly reply_dnc — these are event-campaign prospects nominally owned by the campaign rep, not a coverage gap) | 60 |
| **In Pipedrive, owned by the roster, in NO registry row at all** | **84** |

Full 84-name list: `person_misses.csv` (all 144 raw, cross-reference the "already covered" column)
in the scratchpad — reproduced in `audit_out/` is not yet copied there, ask if you want it moved.

**Caveat, read before acting on the 84**: `dnc_s3_creation_watcher`'s "owned by" criterion, if
implemented against raw Pipedrive ownership, cannot distinguish a rep's genuine personal 1:1
outreach from a rep being the nominal Pipedrive owner of a bulk event-campaign prospect who simply
hasn't replied yet (which is how the 60 "already covered via reply_dnc" group got their ownership
too). Org ids on the 84 mostly fall in the same continuous 21xxx–22xxx range as the known
event-campaign imports, which is circumstantial evidence several of the 84 may be the same
category (imported prospects, not personal adds) rather than true S3 misses. **Chirag R Shah
(86650) is the one unambiguous case** — explicit Surfe signal, no event-campaign involvement. The
rest need a human or a source/channel-id check before being treated as confirmed misses, not just
a scheduling fix.

### Rule 4 — Explicit opt-outs (stop/unsubscribe), since 1 Sep

Registry: 0 rows, reason=`unsubscribe`. Ground truth: **0 miss.** Smartlead: 55 unsubscribed leads
total, all dated May 2025 or earlier except one 2026-08-06 case (before the window) — zero since 1
Sep. HeyReach: regex-swept all 208 genuine replies since 1 Sep for stop/remove-me language — 3
keyword hits, all false positives ("stop by our booth"/"stop by #112", event-networking language).
Clean.

### Rule 5 — Domains

- 20-domain sample: all 20 present in both n8n `dnc_domains` and Supabase `dnc_domains`.
- Full compare (not just the sample): n8n 1,373 = Supabase 1,373, 0 missing, 0 extra either
  direction.
- Live gate call: POST `{{WEBHOOK_DNC_PRE_ADD_GATE}}` with a banned-domain test email
  (`@100programmers.com`, a real row in `dnc_domains`) → `BLOCKED, reason: company_dnc /
  100programmers.com`, 121 ms. Confirms the gate itself, independent of the projection/registry
  question above, is healthy.

## Reverse check — anything in the registry since 1 Sep that shouldn't be

Reviewed all 79 rows individually (small enough to check by hand, not sampled). Findings already
covered above: Person-d9409383 (OOO, still active — should be removed/downgraded) and Person-b27663e9
(borderline auto-reply, still active — needs a judgment call). No event_contacted, manual_sheet, or
null-reason rows in the window (0 each) — no seed/backfill-path contamination this cycle. No
website-form/Memurai-class leads found (meeting_dnc is empty this window so that specific class
didn't have an opportunity to appear; worth re-checking once #2 above is fixed and starts writing
real rows).

## Layer consistency

| Check | Result |
|---|---|
| n8n `dnc_registry` active count | 25,731 |
| Supabase `dnc_registry` active count | 25,731 — **MATCH** |
| n8n / Supabase total rows | 25,734 / 25,734 — **MATCH** |
| 100-row field-by-field sample | 0 missing, 0 field mismatches |
| n8n / Supabase `dnc_domains` | 1,373 / 1,373 — **MATCH**, 0 missing/extra |
| Delta-pusher claims queue depth (family `supabase_delta_registry`) | **0** — pusher keeping up |
| Last nightly reconcile (06:20Z today) | 0 drift both tables (25,733 registry / 1,373 domains logged — the 1-row gap vs the live 25,734 total is just the ~15 min between the 06:20 reconcile and this audit's later pull, not a real mismatch) |

## Latency

- Gate call: 121 ms (well inside the fixed budget from the 2026-09-14 incident).
- Delta pusher: continuous 5-min cycles, `row_count:1` per cycle in the recent window, queue depth
  0 — confirms it is keeping up in real time. The 3 organic UpsertLedger→Supabase cycles tracked
  earlier this session (Ben Leeds, Person-3e1cc65f, Person-24893d0f) were each independently confirmed
  ≤6 min end-to-end; a 4th (Person-c8f2fbf3, sales_personal_outreach) has also landed since.

## Bottom line for Nik

The Supabase mirror (this week's build) is solid — nothing wrong there. The real exposure is that
**Pipedrive itself has been effectively blind to new DNC entries since this system's Pipedrive-side
writers were built**: the 686 field writer has never been scheduled, the meeting detector has never
been turned on, and the sales-owned watcher only ever looks at Leads, missing person-only records
entirely. Registry coverage (the n8n/Supabase layer) is comprehensive and accurate; Pipedrive
enforcement of it is not. None of the three workflows have been touched — this is a report, not a
fix, pending your word on scheduling/activating them (and on the digest wiring bug separately).
