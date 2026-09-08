# Projections Pass — design plan (NOT executed, for review only)

Goal: push DNC status from `dnc_registry_dev` out to Pipedrive, Smartlead, and HeyReach, as its
own reviewed step, separate from Stage 2 (WF-4). Every channel gets a dry-run count pass before
any live write is even built, let alone fired. This document is the plan; nothing in it has run.

## Architecture: retry-scan, not inline

`projections_state`'s own schema note already commits to this shape (written 2026-08-07, before
any of this logic existed): *"Drives Stage 2's retry-only-missing-projections behavior — idempotent
by construction (a projection already done|skipped is never re-attempted; only pending/failed are
retried)."* So the projection pass is a **periodic/manual sweep workflow**, not something wired
inline into `UpsertLedger`'s insert path:

1. Query `dnc_registry_dev` for rows where `projections_state.<channel>` is `pending` (or
   `failed:*`, for retry).
2. For each row+channel, check eligibility (below).
3. **Dry-run mode**: count what *would* happen, per channel, per outcome bucket. Zero external
   API calls, zero writes to the registry.
4. **Live mode** (separate future gate, not part of this plan's approval): actually call the
   external API, then update `projections_state.<channel>` to `done` or `failed:<err>`.

This means WF-4's own inserts also land as `pending` and simply wait for the next sweep — matching
the instruction that WF-4 itself fires no projections.

## Per-channel plan

### 1. Pipedrive — labels for the 2,264 matched persons

**Status: no reusable write mechanism exists today.** Research finding: the only Pipedrive
person-level custom fields in this codebase are LinkedIn URL and member_id (read-only, used for
matching). The only *existing* Pipedrive write anywhere in this stack is WF-2's `PATCH
/v1/leads/{lid}` label union (`build_wf2_branches.py`) — but that's a **lead**-level label, and our
2,264 are **persons**, not necessarily leads. Applying the lead-label mechanism would silently
under-cover: a matched person with no open lead gets nothing written.

**RESOLVED 2026-08-11 — owner decided: create the field.** Done, via `POST /api/v2/personFields`
(verified first with a `zz_probe_` field, confirmed it round-tripped and deleted cleanly, then
created the real one — same discipline as every Data Table probe in this project):

- Field name: **DNC Status**, type `enum` (single-select). `field_code` (the key used to read/write
  this field on a person record): `9c018b7406ebc481b9c108a487f76c4d09f91c9b`. v1 numeric id (for
  any v1-only calls, e.g. delete): `9180`.
- Options: `dnc_active` → option id `686`, `dnc_expired` → option id `687`. Pipedrive stores the
  **option id**, not the label string, on the person record — the future live-write branch must
  write `686`/`687`, not `"dnc_active"`/`"dnc_expired"`.
- Lead-label write (existing WF-2 mechanism, label id `52a7c290-fc73-11f0-ad98-81d4703453f3`) stays
  as the **secondary** projection wherever an open lead exists — this new field is primary/person-
  level coverage, the label is a belt-and-suspenders add-on, not a replacement.
- **Correction 2026-08-11, then a correction to the correction (fix-owner session's cross-check):**
  `archived_status` is silently ignored by `/v1/leads` — archived leads are unreachable from any
  list read, including the person-scoped `?person_id=` form this sweep uses. My first pass called
  this an undercount on `with_open_lead`. That was wrong, and the fix-owner session caught it: an
  archived lead is **not** an open lead, so reporting a person whose only lead is archived as
  `without_open_lead` is *correct*, not a miss — `with_open_lead` exists purely to gate whether the
  secondary lead-label projection has a live lead to attach to, and an archived lead has nothing
  live to attach a label to either. The real undercount archived-invisibility causes is a
  *different* question — "has this person ever had a lead" / "was ever worked" — someone contacted
  then archived looks identical to someone never touched. That distinction doesn't feed anything in
  this sweep (nothing here infers contact history from lead absence), so it's noted for awareness,
  not treated as a defect in `with_open_lead` itself. For a specific person, `GET /v1/leads/{uuid}`
  (single-record) does return `is_archived`, unlike list reads. The 7-day/500-row-page cap remains
  correctly ruled out — this sweep never does an unfiltered bulk `/v1/leads` list read.

**Dry-run count (buildable today, no decision needed to COUNT):** of the 2,264 matched persons,
how many have at least one associated Pipedrive lead (label mechanism would reach them) vs. none
(would need the new-field approach). This number should be in hand before the owner picks a
mechanism — I can pull it from the already-cached `pipedrive_persons_index.json` pull plus one
additional read-only `/persons/{id}` or `/leads` sweep.

### 2. Smartlead — global block where email exists

**Status: a proven mechanism exists and is live in WF-2 today** — `POST
/leads/{lid}/unsubscribe` (empty body), described in-code as "global suppression, prevents
re-adding." Auth pattern (httpQueryAuth, api_key) is already bound and working.

**Gap to close before build:** our registry stores `email_lc`, not a Smartlead `lead_id`. The
unsubscribe call is lead-scoped, so each email needs resolving to its Smartlead lead_id(s) first
(a person can be a lead in more than one campaign). Plan: reuse the existing Smartlead
leads-statistics/lookup pattern already used elsewhere in this project (with the known
list-ordering trap already documented — never trust default pagination/ordering for this) to
resolve `email_lc → [lead_id, ...]` before the unsubscribe call, then unsubscribe every resolved
lead_id for that email.

**RESOLVED 2026-08-11 — real dry-run counts, via `GET /leads?email=` (read-only, 987 calls, zero
writes):**

| Outcome | Count |
|---|---:|
| Total candidates (matched person + real email) | 987 |
| Resolve to a real Smartlead lead, real pending action | **623** |
| Resolve to a lead already unsubscribed (no-op) | 6 |
| No matching lead found in Smartlead at all | 358 |
| Errors | 0 |

So the live-write branch, when built, has **623** real unsubscribe calls to make — not 987. The 358
"not found" rows never entered Smartlead at all (never emailed), so there's nothing to suppress
there; they're still fully covered by the registry-level block regardless. Full per-row detail:
`fixtures/smartlead_resolve_report.json`.

**Reproduced exactly, 2026-08-12, via the real sweep (execution 15913 + a targeted retry, not the
standalone script) — 623/6/358, digit for digit.** The sweep's first attempt got 543/6/288 with
150 candidates failing on a network-level `ETIMEDOUT` to Cloudflare (confirmed not a 429, not a
code bug via `PD Get Leads By Person` reporting zero errors and zero rate-limit hits in the same
run). Retried exactly those 150 with wider spacing (1.2s) and got zero errors, closing the gap to
exactly 623/6/358. Full per-row evidence artifact, extended per the auditor's requested columns
(match method, registry email_lc as stored vs. Smartlead's own stored email, last-sent/last-reply
rollup per lead): `SMARTLEAD_623_EVIDENCE_2026-08-12.csv` (sent to the owner for the auditor's
stratified-20 + random-5 spot-check before `FIRE_SMARTLEAD` flips — zero rows unmapped against the
registry, all 623 `match_method=exact`, no case/whitespace mismatches found).

**Cross-signal worth the auditor's attention, not treated as a defect**: 538 of the 623 (86%) have
a `last_reply_at` on file in Smartlead, but only 38 of the 623 are `registry_reason=reply_dnc` —
meaning ~500 rows entering the registry for an unrelated reason (mostly
`manual_offboard_eligible`, LinkedIn-connection-derived) separately also replied to Smartlead
outreach at some point. Not investigated further here — flagged for the 623×4,024 cross-reference,
since it's exactly the kind of overlap that cross-reference is designed to surface.

## Four buckets, defined precisely (so post-run reconciliation is well-posed)

- **6, already-unsubscribed**: registry candidates (matched person + real email) whose resolved
  Smartlead lead already has `is_unsubscribed: true` — a no-op if `FIRE_SMARTLEAD` fires, not a
  pending write.
- **358, not-found**: registry candidates whose email has no matching lead in Smartlead at all
  (`GET /leads?email=` returns no `id`) — never emailed by Smartlead under this address; covered by
  `add-domain-block-list`, not `unsubscribe`, if that branch is ever built.
- **1,978, with-lead** (Pipedrive branch): of the 2,264 Pass-1-matched persons, those with at least
  one **non-archived** lead reachable via `GET /v1/leads?person_id=` — eligible for the secondary
  lead-label write in addition to the person-field write.
- **286, without-lead** (Pipedrive branch): the remaining Pass-1-matched persons — either no lead
  exists, or their only lead is archived (invisible to this read) — eligible for the person-field
  write only, by design, not a gap.

## Registry rule check: "unsubscribe-sourced entries = PERMANENT" — partially already true, one
real gap found

- **Already correct**: `reason=unsubscribe` (and `client`) map to `entry_type=explicit_opt_out`,
  which `merge_v1.js`'s `DNC_PERMANENT_TYPES` already treats as permanent (`expires_at=null`).
  Verified against the actual seeded data: all 95 `client` rows carry `expires_at=null`; nothing in
  the current seed used `reason=unsubscribe` specifically, but the mapping is identical to `client`
  so the same guarantee holds.
- **Real gap, not yet built**: nothing makes a row's `expires_at` permanent *as a consequence of*
  this project's own Smartlead unsubscribe action. `SL Mark Done`'s write only touches
  `projections_state`, never `expires_at` (checked directly in `build_dnc.py`). Concretely: 38 of
  the 623 about-to-be-unsubscribed rows are `reply_dnc`, which carries a real 6-month TTL
  (`expires_at` populated, not null). Once we perform a Smartlead-side global unsubscribe — itself
  irreversible per Smartlead's own docs — our own registry would still show that person's entry
  *expiring* in a few months, silently disagreeing with the external system's permanent state. This
  needs a decision (does a successful `smartlead:done` unsubscribe write force `expires_at=null`
  regardless of the row's own reason/entry_type?) before the live-write branch's `SL Mark Done`
  step is finalized — flagged, not yet fixed, since `FIRE_SMARTLEAD` hasn't flipped.

## For Melisa's doc: `reply_dnc`'s opt-out-vs-not-interested split

`reply_dnc` currently lumps together two semantically different replies under one reason and one
TTL: an explicit "please remove me" (arguably as permanent as `unsubscribe`) and a soft "not
interested" decline (genuinely time-bound — paul.gilford's own seeded row is exactly this case,
`smartlead_category: "Not Interested"`, correctly on the standard 6-month TTL). Right now both get
the same `negative_reply` entry_type and the same TTL regardless of which one actually happened.
Worth asking Melisa's doc whether `reply_category`/Smartlead's own reply-classification should
split these into two different reasons (or gate the permanent-vs-TTL choice), rather than
continuing to treat every reply-derived DNC entry as equally time-bound.

**Design split confirmed by the owner, 2026-08-12** — the live-write branch is not one mechanism,
it's two, matched to what each population actually has:
- **The 623 resolved leads → `POST /leads/{lid}/unsubscribe`** (proven global in scope, confirmed
  directly against Smartlead's own official API reference: "unsubscribes the lead globally across
  all campaigns... affects all current and future campaigns," irreversible via API). This is
  already the exact endpoint wired into the sweep's gated `SL Unsubscribe` node.
- **The 358 never-a-lead emails (288 confirmed `not_found` + some overlap) → `POST
  /leads/add-domain-block-list`**, a genuinely separate mechanism (works on raw email/domain
  strings, no lead_id required at all) — settles a contradiction between two independent findings
  (one session found this endpoint documented; another found it 400s and doubted it existed).
  **Verified live 2026-08-12** on a throwaway RFC-2606 `.invalid` fixture domain (never a real
  registrable domain): `POST` → `200 {"uploadCount":1,"totalDomainAdded":1}`, confirmed persisted
  via the read endpoint (`GET /leads/get-domain-block-list`, sorted newest-first, `source: "API"`).
  The earlier 400 was very likely a wrong query param or endpoint, not evidence the resource
  doesn't exist. **No delete/remove endpoint found** after 3 reasonable probes (all clean 404s, not
  auth errors) — consistent with this API's general "no undo" posture elsewhere. Harmless here
  since the fixture domain can never be real.
- **Open, deferred (doesn't block Friday per the owner)**: does blocking a domain/email this way
  stop someone *already mid-sequence* in an active campaign, or only prevent future additions? Not
  yet verified — the 623 resolved-lead population uses the proven-global `unsubscribe` regardless,
  so this only matters for the 358 never-a-lead population, none of whom can be mid-sequence by
  definition (they were never a lead in the first place).

## REDESIGN, 2026-08-12 — everything above this line is superseded, kept for the record

Melisa surfaced a fact that changes the whole channel: **lead nurturing runs through Smartlead
too** — sales executives' real mailboxes are connected there, and ongoing conversations with
repliers happen via Smartlead. A global unsubscribe (or, it turns out, even the scoped
`add-domain-block-list`/per-campaign `pause` alternatives investigated below) risks severing our
own nurturing channel to exactly the warmest population — 538 of the 623 resolved leads are
repliers. The one-way door (`unsubscribe` is explicitly non-undoable via API) was about to close
on the wrong mechanism for the wrong population.

**What "replier → DNC" actually means**: never cold-outreach again. It does **not** mean
account-level Smartlead suppression, because Smartlead is also the nurturing/conversation channel.
The registry's own DNC semantics were always correct; only the *projection* design (push DNC status
out as a Smartlead-side suppression) was wrong for this provider.

**Mechanism found and ruled out anyway**: Smartlead does have a genuine per-campaign `pause`
(`POST /campaigns/{campaign_id}/leads/{lead_id}/pause`), explicitly documented as not touching
other campaigns and explicitly recommended for "a lead replied via another channel... should not
receive further follow-ups in that campaign" — on the surface, exactly the nurturing-preserving
tool this problem seemed to need. **Ruled out anyway, per the owner**: the redesign retires *all*
Smartlead-side writes for the general population, not just the ones proven riskiest — enforcement
moves entirely to a layer we control.

### The new design: registry-check-before-cold-add, not a provider-side sweep

1. **The gate is OUR layer, not the provider's.** Every campaign-add path (existing WF-1/WF-2, a
   future WF-3, any bulk add) checks the registry *before* adding a lead to a **cold** campaign.
   Nurturing adds are exempt by design — this is enforceable because every real add path in this
   ecosystem already runs through our own n8n workflows.
2. **`SL Unsubscribe` retired for the general population.** The only candidates for a true
   account-level unsubscribe are explicit hard opt-outs ("do not contact me," verbatim) and
   possibly the seed-CSV offboard population — pending Melisa's explicit per-category word. **Zero
   Smartlead unsubscribe writes until she gives it.**
3. **The 288 never-a-lead population + `add-domain-block-list`: same freeze.** A block-list entry
   might *also* be able to block nurturing sends, not just cold ones — unverified. No entry beyond
   the one `.invalid` fixture already added (confirmed harmless: never a real domain) until this is
   answered. The 4 dead-address re-add executed just before this freeze landed was checked
   retroactively — none of those 4 addresses were ever a Smartlead lead at all, so there was no
   conversation to sever; no remediation needed there.
4. **What `FIRE_SMARTLEAD` becomes**: probably nothing. The Smartlead branch of the sweep shrinks
   to a **read-side report** — who's in the registry AND currently in a cold campaign right now —
   an escalation list for a human to manually move to nurturing. Zero writes required for this
   scope.
5. **Reviewer's note, added to the standing review protocol per the owner**: any future projection
   design must state which *other* uses of the same provider it could break. Smartlead is not only
   outbound cold — it's nurturing *and* SE mailboxes. This near-miss is the reason that check exists
   now.

### Empirical confirmation, 2026-08-12 — Gmail experiment closes the loop

The redesign above was risk reasoning before any live evidence existed. Nik authorized one live
probe to settle it: take `pii-c61c7d08@example.invalid` (Nik's own fixture, globally unsubscribed since
2026-08-11), add it to a nurture-style/test campaign (Smartlead's own "Test Campaign", id 1244339)
via API with `ignore_unsubscribe_list: true`, and see whether one send goes out.

**Result: the add itself silently dies.** `POST /campaigns/{id}/leads` returned `ok:true,
upload_count:1, already_added_to_campaign:0, unsubscribed_leads:[]` — reporting a clean, fresh
success — but the campaign's lead list never changed; the fixture never appeared. Isolated with a
control (a fresh, never-unsubscribed throwaway address, identical call shape): that one landed
immediately, lead count +1, status `STARTED`. Same endpoint, same override flag — only the
unsubscribe status differed. No send was ever possible, so there was nothing to check in Nik's
inbox.

**This is Outcome B, stronger than the B originally framed**: global unsubscribe doesn't just stop
future sends within campaigns already holding the lead — it silently blocks the lead from being
*added* to any new campaign at all, and the one override flag that exists specifically to bypass
unsubscribe suppression (`ignore_unsubscribe_list`) does not work at the add stage. Had the original
global-unsubscribe-for-623-repliers design fired, all 538 repliers would have become permanently
un-addable in Smartlead in *any* campaign, nurture included — with no visible error anywhere telling
anyone why. This makes the freeze not just the cautious call but the empirically correct one.

**Two house rules recorded from this, filed under the irreversible-projection protocol:**
1. **Smartlead add-calls must read back lead presence.** `ok:true` / `upload_count:1` on
   `POST /campaigns/{id}/leads` is not confirmation the lead landed — it can report success on an
   add that silently didn't happen (observed here specifically for globally-unsubscribed leads).
   Any future add-based mechanism (registry-check gate's escalation moves, campaign backfills, etc.)
   must re-fetch `GET /campaigns/{id}/leads` (or the global `GET /leads?email=`) after an add and
   confirm the lead is actually present before treating the write as done.
2. **The reversal-procedure rule is vindicated with wire evidence, not just risk reasoning.** Any
   projection mechanism documented elsewhere as "irreversible via API" should be treated as capable
   of silent, undocumented side effects beyond the one advertised (here: blocking future adds
   account-wide, not just future sends) — the redesign's blanket "no Smartlead-side write for the
   general population" stance should be the default going forward for this provider, not
   case-by-case re-litigated per mechanism.

Test-campaign state fully reverted after the probe: control lead deleted, sequence delay restored
to its original `delay_in_days: 1`, campaign status restored to `STOPPED`. Fixture's own record
untouched — still globally unsubscribed, still on its original one campaign only.

Pipedrive is unaffected by any of this — field write + label add are both reversible, carry no
send-path semantics, and that GO proceeds independently on the auditor's post-run protocol.

### 3. HeyReach — exclusion mechanism

**RESOLVED 2026-08-11 — reoriented per owner direction, most of it answered:**

- **Global blocklist/"Do not contact" list: does NOT exist.** Confirmed directly on HeyReach's own
  roadmap (status `🛠 Planned` since 2023-06-11, never built) and independently via a third-party
  comprehensive API audit — no such endpoint in the documented or undocumented surface. This exits
  the design entirely, as anticipated.
- **Per-lead pause: real, found, live-verified.** `POST /campaign/StopLeadInCampaign`
  (`{campaignId, leadUrl}`, discovered via validation-error probing — undocumented anywhere).
  Executed for real on a consented fixture lead: campaign status and all 69 other leads in the
  same campaign were unaffected, only the targeted lead's status changed (`Pending`→`Paused`).
  Surgical and scoped exactly as needed for a per-person DNC action.
  **Reversibility unconfirmed via API** (no resume/unpause endpoint found after probing ~10
  plausible names) — may require a manual UI step, or "pause is a one-way door via our automation."
- **Whether pause blocks inbound reply webhooks: still unknown, PARKED — resolves on the first
  live paused-lead reply, zero-cost, no probe needed.** The original confound (all 4 sender
  accounts inactive, no campaign IN_PROGRESS) has partially lifted: as of 2026-08-11 two real
  campaigns are back `IN_PROGRESS` with live, syncing sender accounts (Rune Jensen, Mario Stalder —
  both `isActive: true`). Nik's fixture lead sits in a *different* campaign (510448, still PAUSED,
  sender Sergey Cujba still inactive) — **explicitly not being reactivated for this probe**, per
  the owner. Instead: the question now resolves naturally the first time ANY lead in a live,
  syncing campaign is paused and that lead replies — whether that pause comes from (a) this very
  projection branch, once it eventually fires for real, pausing its first real lead in a live
  campaign, or (b) the team manually pausing a lead in Rune's/Mario's campaigns for any other
  reason. Either way, that lead's first reply after being paused IS the verdict — no dedicated
  fixture test required. **The HeyReach projection branch's go/no-go inherits this condition**: it
  cannot go live until a paused-lead reply has actually been observed landing in
  `/inbox/GetConversationsV2` (or observed NOT landing, which would kill the mechanism outright).

**Verdict**: still open, pending that retest. If replies do land while paused → per-lead pause is a
viable projection mechanism (with the resume caveat above). If they don't → HeyReach DNC stays
intake-guard-only at the WF-1/WF-3 layer, which the owner has already said is an acceptable v1.

## Dry-run methodology (applies to all three)

- One sweep workflow per channel (or one workflow, three branches — cheaper to build, easier to
  review independently as one branch each).
- Each branch: `dnc_registry_dev` get (filter `projections_state` contains the channel's pending
  marker — since the row-filter engine has no "Contains" operator, this means fetching return-all
  candidate rows by a broader filter, e.g. `pipedrive_person_id is not empty` for the Pipedrive
  branch, `email_lc is not empty` for Smartlead, `linkedin_url_norm is not empty` for HeyReach, then
  parsing `projections_state` JSON in code to confirm the channel is actually `pending`).
- Bucket results: `would_write` / `already_done_or_skipped` (shouldn't happen if the filter is
  right, but count it as a canary) / `ineligible` (missing the field the channel needs) /
  `needs_owner_decision` (Pipedrive's lead-vs-person gap).
- Zero external API calls in dry-run mode — count-only, using data already in the registry plus
  (for Pipedrive/Smartlead resolution counts) the already-cached Pipedrive person index and a
  read-only Smartlead lookup.
- Output: a per-channel counts report, same shape as `SEED_WRITE_REPORT_2026-08-11.md` and
  `PIPEDRIVE_RESOLUTION_REPORT_2026-08-11.md` — brought back for review before any live-write branch
  is even written, let alone run.

## Sequencing recommendation

1. Smartlead first — proven mechanism, clear eligibility (987 known), lowest risk.
2. Pipedrive second — needs one owner decision (new person field vs. lead-label coverage gap)
   before the live branch can be designed; dry-run counts can be produced either way.
3. HeyReach last — no proven mechanism, a documented webhook-breaking risk attached to the most
   obvious API shape. Needs its own explicit go/no-go after re-verifying that risk, independent of
   the other two channels' approval.

Nothing above has been built or run. Next step on my side, if this shape looks right: build the
three dry-run branches and bring back the actual counts — still no live writes at that point.
