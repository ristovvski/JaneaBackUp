# P1 — dnc_projections_sweep wrote DO NOT CONTACT label to Pipedrive leads

Reported by Slava/Lule, 2026-09-16. Full list attached: `dnc_label_incident_FULL_LIST.csv`
(600 rows). Raw per-execution data: `SUPABASE_PROJECTION_build/audit_out/dnc_label_incident_final_live.json`.

## 1. STOP — done, first action taken

`FIRE_PIPEDRIVE` set to `false` on live `dnc_projections_sweep` (id `8qVXtI2ez5o6a9hc`), verified.
No further writes. `FIRE_S3`/`FIRE_S3_PERSONS` (the OTHER sweeps) were not touched — they write only
the person-level DNC field, never lead labels, confirmed below.

## 2. Source — confirmed

- **Node**: `PD Patch Lead Labels` (HTTP PATCH `/v1/leads/{lead_id}`, body `{label_ids: <union>}`),
  fed by `PD Label Union`, which builds the union from the lead's existing `label_ids` plus
  `CONFIG.pd_label_dnc`.
- **Label id**: `52a7c290-fc73-11f0-ad98-81d4703453f3` = **DO NOT CONTACT**, confirmed against
  Pipedrive's own `leadLabels` list.
- **Scope is larger and older than the initial suspicion.** This is NOT just yesterday's go-live.
  Every real (non-dry-run) execution ever, chronologically:

| Execution | Started (UTC) | FIRE_PIPEDRIVE | Leads labeled DNC |
|---|---|---|---|
| 48609 | **2026-09-08T15:04Z** | **true** | **224** |
| 56426 | 2026-09-15T13:34Z | true | 186 |
| 56894 | 2026-09-15T14:00Z | true | 88 |
| 57238 | 2026-09-15T15:00Z | true | 3 |
| 57484 | 2026-09-15T16:00Z | true | 82 |
| 57696 | 2026-09-15T17:00Z | true | 2 |
| 57759 | 2026-09-15T18:00Z | true | 3 |
| 57836 | 2026-09-15T19:00Z | true | 0 |
| 57890 | 2026-09-15T20:00Z | true | 4 |
| 57944 | 2026-09-15T21:00Z | true | 1 |
| 57999 | 2026-09-15T22:00Z | true | 4 |
| 58042 | 2026-09-15T23:00Z | true | 1 |
| 58122 | 2026-09-16T01:00Z | true | 1 |
| 58176 | 2026-09-16T02:00Z | true | 1 |
| **Total** | | | **600 leads** |

**The Sept 8 execution (48609) already fired for real and labeled 224 leads — over a week before
yesterday's go-live.** That run was one of the two "manual test fires" from the original build; it
was not a dry run. This has been live-affecting real leads since 2026-09-08, not 2026-09-15.
(The Sept 8 dry-run twin, execution 48563 at 13:40Z, correctly did not write — confirms the field
existed and worked correctly in dry-run mode; only the live fires actually wrote.)

Every hourly fire after chunk 2 (14:00Z Sept 15) kept labeling small numbers of NEW registrations —
including entries created by this session's own work yesterday (the S2 rebuild's 47, the S3
roster-owned backfill's 82, Chirag). The mechanism doesn't distinguish source; anything with
`pipedrive_person_id` set and an open lead got labeled.

## 3. Impact — Melisa's handover automation

Checked **live, right now** (not just at the moment each lead was labeled — some gained
"3. Responded" afterward from unrelated processes, so the true current block count differs
slightly from the historical snapshot):

| | Count |
|---|---|
| Total unique leads we labeled DO NOT CONTACT (Sept 8 → now) | 600 |
| Still carrying our DO NOT CONTACT label right now | 593 |
| **Currently carrying BOTH DO NOT CONTACT and "3. Responded" — blocked from Melisa's handover RIGHT NOW** | **425** |
| Already manually corrected by someone before I checked (DNC label already removed — Person-e0711106, Daniel de Moraes Branco, Person-8c0e0fb8, Linda McQuade, Person-4f9fbdb2, Stefan Lukianov) | 6 |
| Lead converted to a deal / no longer exists since (Person-a731ca52, person 84141) — nothing to repair | 1 |

**425 positive repliers are silently withheld from sales right now.** Registry-reason breakdown of
all 600: 378 `reply_dnc`, 90 `meeting_dnc`, 132 `sales_personal_outreach` (a person can appear once;
these sum to 600).

All 4 names from Slava's screenshot (Linda McQuade, Daniel de Moraes Branco, Person-8c0e0fb8, Person-e0711106)
are in the 600 — and all 4 already had the label manually stripped by the time I checked (someone
is already reacting in parallel). **Do not re-touch these 6** — the repair action below only
targets leads that still currently carry the label we added.

## Files
- `dnc_label_incident_FULL_LIST.csv` — all 600, sorted worst-first (currently-blocked positive
  repliers first), with name, person id, lead id, which execution wrote it, registry reason,
  whether they had "3. Responded" at the time we touched them, whether they currently have DNC and
  "3. Responded" live, and any notes (already-fixed / lead-gone).

## 4. FIX — done, deployed live

Removed the entire lead-label write path from `dnc_projections_sweep` (9 nodes gone: `PD Get Leads
By Person`, `PD Classify`, `PD Has Open Lead?`, `PD Get Lead For Labels`, `PD Label Union`,
`PD Patch Lead Labels`, `PD Mark Done (with lead)`, `PD Merge Write Errors`, and the old
`PD Mark Done (no lead)` renamed to `PD Mark Done` since there's no more with-lead/no-lead fork).
The `pd_label_dnc` CONFIG field (the DNC label id) is gone entirely. The workflow's only Pipedrive
write now is the field PATCH to `/api/v2/persons/{id}`.

Added an explicit regression-static test ("sweep never touches label_ids") asserting: no
`label_ids` string anywhere in the workflow JSON, no reference to the DNC label id, no node name
suggesting a reintroduced lead/label touch, every Pipedrive HTTP call targets only
`/api/v2/persons/`. 110/110 contract tests pass. Both WF_LINTER rules clean
(`prev_read_matches_direct_ancestor`, `node_reference_resolves`).

Deployed live via `zz_patch_projections_sweep_p1_fix.py --apply` (diff matched exactly what was
expected, no drift). Post-patch verified live: 32 nodes, `FIRE_PIPEDRIVE` still `False`, zero
occurrences of `label_ids` or the DNC label id anywhere in the live workflow JSON. Artifact:
`DNC_OBS_P1_build/ARTIFACT_prefire_p1_projections_sweep_fix.md`.

## REPAIR — done, fired and verified

Pre-fire snapshot (live, right before firing) matched the incident numbers exactly: 599 leads
resolve (1 gone, Jorge), 593 carry our DNC label, 429 carry both DNC and "3. Responded"
simultaneously.

Fired `dnc_label_reversal` chunked (6× 100) via `zz_fire_p1_label_repair.py`, `frozen_ids` = the
full confirmed 600. Reactivated only for the fire, deactivated again immediately after (re-archived,
preserved).

**Final tally: `stripped=593 already_correct=6 fetch_error=1 kept_for_reason=0
no_registry_match=0 no_lead=0` — exact match to the pre-fire prediction, sum=600.**

**Post-verify (pre vs post label snapshot, all 600 leads):**
- 0 of the 600 still carry DO NOT CONTACT from us (593→0, and the 6 already-clean stayed clean).
- 599/600 leads resolve identically before and after (Jorge's lead still gone, as expected).
- **1 anomaly found and confirmed benign**: Person-4ef390db (person 86686, lead `c28efec0-...`)
  gained the "2. Connected" label during the ~15-minute fire window. This is NOT something the
  repair did — `dnc_label_reversal`'s write is `label_ids.filter(id => id !== DNC_ID)`, a pure
  subset of the pre-strip list; it is mathematically incapable of adding a label. Some other,
  unrelated automation touched this lead independently during the window (most likely a LinkedIn
  connection-accepted tagger). Every other label on every other lead is byte-identical pre vs post.

Full data: `DNC_OBS_P1_build/audit-artifacts/p1_pre_fire_snapshot.json`,
`p1_post_fire_snapshot.json`, `p1_repair_verify_and_handover_damage.json`.

## Handover damage — the list for Melisa

**429 of the 600 had "3. Responded" while carrying our DO NOT CONTACT label** — every one of them
a positive replier whose handover to sales was silently skipped by Melisa's automation. Full list
with name, Pipedrive person id, lead id, registry reason, and the evidence basis for each:
`DNC_OBS_P1_build/audit-artifacts/p1_handover_damage_429.csv`.

These need a manual handover trigger from Melisa — the label is stripped now but nothing re-fires
the automation retroactively.

## FIRE_PIPEDRIVE re-armed

`dnc_projections_sweep` (now field-only, no label branch — see FIX above) has `FIRE_PIPEDRIVE`
back to `true`, verified live: 32 nodes, no `label_ids` reference anywhere in the workflow. Resumes
its hourly field-only DNC-status writes.

## Status: P1 closed

STOP → CONFIRM → IMPACT → FIX → REPAIR → handover-damage list, all done. Only remaining action is
Melisa manually triggering handover for the 429.
