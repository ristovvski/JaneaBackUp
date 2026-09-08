# People-DNC Pipedrive resolution report — 2026-08-11

**Read-only. Zero Pipedrive writes. Zero persons created.** Run under an explicit gate override
("Gate override for the PULL only") during a quiet paused window, ahead of the sentinel-gated
overnight schedule — the SEED WRITE gate itself is unchanged and still pending.

## What ran

1. **Phase A** (`dnc_pull_pipedrive_persons.py`, full run, not `--sanity`): bulk-pulled all
   Pipedrive persons once via `/api/v2/persons`, throttled (0.3s/page, 500/page), checkpointed and
   resumable. Completed clean, no interruption — **56,657 persons pulled**, indexed by
   `li_url_canon`, `email_lc`, and `member_id` (live and soft-deleted tracked separately per the
   B19/DEL discipline).
2. **Phase B** (`dnc_resolve_people_dnc.py`): pure in-memory resolve of the 23,838-row People-DNC
   seed preview against that index. Zero API calls.

## Resolution counts

| Category | Count | % of total |
|---|---:|---:|
| **Total seed rows** | 23,838 | 100% |
| **Matched — clean, single live person** | 2,264 | 9.5% |
| **Matched — needs review (ambiguous, multiple persons under one identity)** | 64 | 0.3% |
| **Matched — only a soft-deleted person** (none found) | 0 | 0% |
| **Creatable — no existing person found** | 21,510 | 90.2% |

`2,264 + 64 + 21,510 = 23,838` — reconciles exactly against the seed.

### Creatable rows, by reason

| Reason | Count |
|---|---:|
| manual_offboard_eligible | 21,269 |
| manual_sheet | 123 |
| client | 93 |
| reply_dnc | 25 |

### Needs-review detail (64 rows)

All 64 are `matched_ambiguous_multi_person: true` — an identity_key resolved to **more than one**
live Pipedrive person. These are NOT included in the clean-matched count and should not be
auto-merged; each needs a human pick of which person record is canonical (or both are legitimately
distinct people who happen to share a normalized LinkedIn slug — collision, not necessarily
duplication). Full list with all `person_ids` per identity is in
`fixtures/people_dnc_resolution_report.json` under `results.matched` where `ambiguous: true`.

## Full detail

Raw per-row detail (all 23,838 rows, matched/ambiguous/creatable, with identity_key, reason, and
matched person_ids) is at `fixtures/people_dnc_resolution_report.json`.

## Gate status — unchanged

Per the standing SEED WRITE gate: **migration done ✅ + this resolution report ✅ + owner's
explicit word ⏳ (pending)** — in that exact order, nothing else has changed. This report does not
itself authorize any write. The `dnc-pipedrive-pull-gate` scheduled watcher has been **disabled**
(it would otherwise have re-run this same pull+resolve overnight once the flip sentinel posts,
duplicating this work) — re-enable it only if this manual run needs to be redone for some reason.
