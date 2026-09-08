# DNC BUILD — FIRE_SMARTLEAD evidence artifact + block-list contradiction settled

**Status: both of Nik's gates addressed. FIRE_SMARTLEAD still awaits the auditor's ~20-sample spot-
check on the evidence CSV. FIRE_PIPEDRIVE is Nik's separate, independent call.**

## 1. 623-id evidence artifact
Built without any redundant new API calls where avoidable: 543 of 623 pulled straight from
execution 15913's cached `runData` (identity_key↔email mapping from `SL Filter Pending`, campaigns
from the raw `SL Resolve By Email` responses already fetched). Only the 80 retry-resolved rows
needed fresh calls (single-record scale, 1.0s spacing) since the retry script hadn't captured
campaign data. `reason` for all 623 came from the local registry payload, zero API calls.

Result: `SMARTLEAD_623_EVIDENCE_2026-08-12.csv`, 623 rows, **zero unmapped against the registry**.
Columns: identity_key, registry_reason, matched_email, smartlead_lead_id, smartlead_campaigns,
source_run. Reason distribution: manual_offboard_eligible 454, manual_sheet 131, reply_dnc 38.
Sent to the owner for the auditor's spot-check.

## 2. Block-list contradiction — settled on the wire, not by re-reading docs
Tested `POST /leads/add-domain-block-list` on a throwaway RFC-2606 `.invalid` fixture domain
(guaranteed never a real registrable domain — chosen specifically so this couldn't affect anyone
real regardless of outcome). Result: `200 {"uploadCount":1,"totalDomainAdded":1}`, confirmed
persisted via `GET /leads/get-domain-block-list` (entry appeared newest-first, `source: "API"`,
sitting above thousands of real Smartlead-bounce-detection entries). The endpoint is real and
works exactly as documented — the earlier 400 finding was very likely a wrong query param or
endpoint path, not evidence the resource doesn't exist. No delete/remove endpoint found after 3
reasonable probes (clean 404s) — left as-is since the fixture domain can never be real.

## Design consequence (owner's call, already applied to the plan doc)
Live-write branch, when it eventually builds, is two mechanisms not one: `unsubscribe` for the 623
resolved leads (proven global), `add-domain-block-list` for the never-a-lead population (can't
unsubscribe a lead that doesn't exist, but can pre-block the address). Mid-sequence suppression
behavior for the block-list path stays an open, deferred question — doesn't gate Friday since the
623 population uses the already-proven `unsubscribe` mechanism regardless.

## Next
Auditor's spot-check on the CSV → Nik's GO/no-go on FIRE_SMARTLEAD. FIRE_PIPEDRIVE is separate and
independent, gated on the auditor's own post-run protocol confirming the dry-run set
(2,264 floor / 1,978 with-lead / 286 without) — Nik indicated that one is likely to land first.
