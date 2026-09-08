# DNC BUILD — dnc_projections_sweep: built, deployed, real bugs found and fixed via live run

**Status: code fixed, tested (49/49), redeployed, left INACTIVE. Re-run PAUSED — Pipedrive API
budget rule now in effect (auditor's Melisa-facing investigation has priority; no bulk Pipedrive
jobs until it posts).**

## What was asked
GREEN to build the three dry-run sweep branches (one workflow), plus gated live-write code for
Smartlead (fire after dry-run counts reproduce through the sweep itself vs the known 623 baseline)
and Pipedrive (write option id 686, lead-label secondary, bring the open-lead-vs-none split).
Live-write FIRING stays gated on the owner's word per channel.

## What happened
1. Built `dnc_projections_sweep` (35 nodes): Pipedrive branch (dry-run open-lead split + gated
   live-write), Smartlead branch (dry-run resolve + gated live-write), HeyReach branch (count-only,
   no write path at all, per the standing park decision). `FIRE_PIPEDRIVE`/`FIRE_SMARTLEAD` default
   `false`; verified by walking the actual connection graph that the 3 write operations are
   structurally unreachable with both false — not just believed, checked.
2. Needed real credentials to actually run the dry-run counting branches. Discovered n8n's public
   API supports credential *creation* (unlike listing) — created two `httpQueryAuth` credentials
   directly rather than embedding raw secrets in any file.
3. **Found and fixed a real, previously-shipped bug while verifying those credentials**:
   `httpQueryAuth` is a generic credential type: n8n only wires it up under
   `authentication: "genericCredentialType"`, not the `"predefinedCredentialType"` mode this
   codebase had used since Build 1. That mode silently sends the request unauthenticated. Checked
   the blast radius: `smartlead_observability_readonly` (the only other user of this pattern) has
   **zero executions in its entire history** — never actually run, so no past report anywhere
   relied on the broken path. Separately confirmed Smartlead itself rejects unauthenticated
   requests cleanly (401 JSON), so this would never have produced silently-hollow data even if it
   had run.
4. Fixed my own trigger mistake (subworkflow trigger instead of a webhook) before ever firing.
5. Fired the sweep for real (with the owner's go-ahead). Two fires; both eventually resolved to
   `status: error` after 5-7 minutes each — but investigation showed they'd actually run the
   **entire** sweep successfully; only the final Slack post failed (`channel_not_found`, unrelated
   to the sweep logic — first real execution of this exact Slack-node pattern anywhere in the
   project, so untested until now).
6. Pulled the real `Combine Summaries` output from both executions — they agreed with each other
   exactly, but the numbers were clearly wrong (Pipedrive eligible=1, Smartlead eligible=1, expected
   ~2264/~987). Traced node-by-node and found **two distinct, real bugs, both freshly introduced in
   this build**:
   - No throttling on the Pipedrive/Smartlead HTTP nodes → **85% and ~80% request failure rates**
     from rate-limiting (429s) once ~2,264 and ~987 calls went out back-to-back with zero spacing.
     **Correction, 2026-08-11**: the fix-owner ("Дежурный") session later reported it independently
     exhausted the shared Pipedrive rate limit ~10:30-11:00Z gathering evidence for a WF-2 defect —
     that window exactly overlaps both sweep executions (10:32-10:37Z, 10:36-10:43Z). So the 85%
     Pipedrive failure rate was likely mostly/entirely THEIR concurrent load, not (or not only) this
     sweep's missing throttle. The Smartlead failure rate (~80%) is unaffected by that overlap since
     that's a different API — the missing-throttle diagnosis stands as-is for that one. The
     throttling fix below is kept regardless of attribution: it's a correctness improvement (a good
     shared-budget citizen) independent of what actually caused this specific run's failures.
   - `PD Classify`, `SL Classify`, `PD Label Union` were generated via `code_node()`, which
     hardcodes `mode: "runOnceForAllItems"` — but the JS was written assuming per-item execution
     (`$json` = current item, `.item.json` = paired upstream item). Under all-items mode this
     silently collapsed hundreds of items down to 1. Root-caused precisely by tracing item counts
     through every node in the execution's own `runData`.
7. Fixed both: added `code_node_per_item()` (mode `runOnceForEachItem`, with the three affected JS
   blocks corrected to return a bare `{ json }` object instead of an array — the required shape for
   that mode, verified against n8n's own Code node source), and added `batching: {batch: {batchSize:
   1, batchInterval: 400/350}}` to both HTTP helpers (the exact remedy n8n's own 429 error message
   names). Added 2 more regression-guard tests. **49/49 pass.** Redeployed the corrected definition,
   left inactive.

Full detail: [PROJECTIONS_PASS_PLAN_2026-08-11.md](../DNC_OBS_P1_build/PROJECTIONS_PASS_PLAN_2026-08-11.md).

## Why the re-run is paused, not done
Mid-diagnosis, the owner set an API budget rule: an auditor's Melisa-facing investigation has
priority on Pipedrive reads right now; no bulk Pipedrive jobs from anyone else until it posts.
Re-running the sweep fires ~2,264 Pipedrive calls in its very first branch — so it stays paused
until that clears, then gets announced ("taking Pipedrive for ~N minutes, ~M calls") before firing,
per the new standing rule.

## Fourth fix: the Slack reporting path itself
Both prior fires' only failure was the final Slack post (`channel_not_found` on `C0BFE6KAN8J`,
the historical default every DNC workflow uses) — the owner confirmed the real ops channel is
`C0B8GCVNR5W` and asked for it fixed before the re-fire, "so the sweep's first clean execution
also proves its own reporting path." Made this additive, not global: `SEND_GUARD_JS` now reads its
expected channel from `cfg.dev_channel_guard || 'C0BFE6KAN8J'` instead of a hardcoded literal; only
`dnc_projections_sweep`'s own CONFIG sets `alert_channel`/`dev_channel_guard` to `C0B8GCVNR5W` —
every other workflow keeps validating against the historical default, confirmed by a new
regression test that checks all of them explicitly. 51/51 tests pass. Redeployed, still inactive.

## Cross-session coordination note
The fix-owner ("Дежурный") session reported independently exhausting the shared Pipedrive rate
limit ~10:30-11:00Z for a WF-2 defect investigation — overlapping both sweep fires exactly, which
is the likely real cause of the 85% Pipedrive failure rate (corrected above). They also shared two
verified platform facts: `archived_status` is silently ignored by `/v1/leads` (archived leads
invisible from any list read, including this sweep's `person_id=` reads — documented in
PROJECTIONS_PASS_PLAN as a real undercounting caveat on `with_open_lead`), and a 500-row
`/v1/leads` page is only ~7 days of a ≥18k-row collection (doesn't affect this sweep, which never
does unfiltered bulk reads). Tried to reply via `SendMessage` to acknowledge and confirm my own
Pipedrive footprint is currently zero/paused — both attempts failed (`SendMessage` can't reach
agents outside my own spawned team) — so the ack went to the owner directly to relay if needed.

## Next
- Wait for the auditor's report to post.
- Announce the bulk window, then re-fire the sweep once more to get real, correct counts.
- Cross-check Smartlead's real count against 623 as originally asked.
- Still no live writes anywhere — both FIRE gates stay false until the owner says otherwise, per
  channel.
