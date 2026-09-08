# W1.0.11 - Phase D: Ai4 retro-backfill plan (DRY-RUN - awaiting Nik's go)

Read-only analysis, 2026-07-20. W1.0.11 is already DEPLOYED + live-verified in production
(versionId 1e199edc-340d-4be8-a4d5-abe43de97b3f). This backfill is MANDATORY before the two
Ai4 campaigns resume, so that resumed touches attach to the existing campaign lead instead of
creating a duplicate. NOTHING has been written - this is the plan only.

## Why it's needed
W1.0.11 selects a person's lead by matching the lead's "Campaign" field to campaign.name.
The Ai4 leads WF-1 created BEFORE W1.0.11 have an empty Campaign field, so on resume the
campaign-match would miss them and create a second (duplicate) lead. Backfilling the Campaign
field (plus the new title convention and medium) makes the resumed campaign land on the right lead.

## How the target set was derived (authoritative)
Scanned 255 WF-1 executions from 2026-07-18 onward. Campaign traffic in the window:
132 "Ai4 2026 - Mario - LinkedIn" + 122 "Ai4 2026 - Rune - LinkedIn" (+1 "Final TEST").
Per execution I recorded whether WF-1 CREATED a lead (Create Lead ran) or SELECTED a
pre-existing one:

  bucket                                     execs   meaning                          in backfill?
  Created a lead for an Ai4 campaign         197     the campaign's own leads         YES - these 197
  Selected a pre-existing (non-Ai4) lead      29     Ai4 touch hit an older lead      No - Slava/Phase A
  No lead (unknown / no-lead reply)            6     M6 unknown / no-lead path        No
  errors                                        0

The 29 "selected" are the wrong-landing class (Phase A documented a sample of 3 persons /
7 events); W1.0.11 does NOT auto-move those - they remain Slava's manual decision.

## The 197 backfill targets (clean - zero anomalies)
- 99 Mario + 98 Rune, 197 distinct persons (each has exactly one Ai4 created lead).
- 0 persons with >1 lead in the same campaign (no ambiguous campaign-match after backfill).
- 0 persons spanning both campaigns.
- 0 leads already carry a Campaign field (all empty, as expected pre-W1.0.11).
- 0 archived / missing / deleted.

Per lead the backfill writes (idempotent - only changes what differs; medium is fill-if-empty).
DRY-validated against live Pipedrive (197 title, 197 Campaign, 196 medium, 0 skipped, 0 errors):
- Campaign field  <- the exact campaign.name        (197 leads, all currently empty)
- title           <- "{campaign.id} - {campaign.name} - {full_name}"   (197 leads; matches what W1.0.11 emits on resume)
- medium          <- "LinkedIn" only if empty        (196 leads; 1 already set -> left as-is)

### Sample before -> after
  Mario  lead 0a31a1f0...  person 83159
    Campaign: (empty) -> 'Ai4 2026 - Mario - LinkedIn'
    title   : 'Person-8c5eb980 - Theta Lake'
           -> '512995 - Ai4 2026 - Mario - LinkedIn - Person-8c5eb980'
    medium  : (empty) -> 'LinkedIn'

  Rune   lead ea315760...  person 83158
    Campaign: (empty) -> 'Ai4 2026 - Rune - LinkedIn'
    title   : 'Person-1edb7c8c - Amazon'
           -> '513000 - Ai4 2026 - Rune - LinkedIn - Person-1edb7c8c'
    medium  : (empty) -> 'LinkedIn'

(Mario campaign.id = 512995, Rune campaign.id = 513000 - HeyReach's numeric ids.)

## Apply mechanics (ready, NOT run)
- Lead: single v1 PATCH /v1/leads/{id} setting title + Campaign custom-field key (no label/archive
  change, so the split-PATCH 403 issue does not apply here).
- Medium: v2 PATCH /api/v2/persons/{id} custom_fields - only when currently empty.
- Idempotent + fully audited to wf1-release-evidence/phaseD-apply-APPLIED.json.

## DECISION NEEDED FROM NIK
Reply to approve applying the backfill to these 197 Ai4 leads (Campaign field + title + medium-fill).
On your word I run it, verify, then proceed to Phase E (prod smoke) and emit READY-TO-RESUME.
Until then nothing is written.
