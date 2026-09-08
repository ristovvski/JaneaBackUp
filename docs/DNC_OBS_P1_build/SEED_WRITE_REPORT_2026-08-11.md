# SEED WRITE Pass 1 — 2026-08-11

**Status: DONE. PASS on all read-back checks.** Executed per owner's explicit "SEED WRITE — GO"
with the creation policy specified in that message.

## What was written

| Table | Rows sent | Rows written | Batches |
|---|---:|---:|---:|
| `dnc_registry_dev` (People-DNC + paul.gilford) | 23,839 | **23,839** | 24 × 1,000 (last: 839) |
| `dnc_domain_block_dev` (company domains) | 1,373 | **1,373** | 2 × 1,000 (last: 373) |

Zero mismatches between sent and written on every batch. Full per-batch detail:
`fixtures/seed_write_report_people.json`, `fixtures/seed_write_report_domains.json`.

## Creation policy applied (people)

| Category | Count | Treatment |
|---|---:|---|
| Matched — clean single person | 2,264 (+1 not applicable, paul.gilford had none) | Full row, real `pipedrive_person_id`, email/full_name hydrated from the live Pipedrive record, `projections_state` all `pending`. |
| Matched — ambiguous (>1 live person) | 64 | `pipedrive_person_id=null`, `projections_state.pipedrive="held:ambiguous"`, reason/identity intact so the block holds regardless of which candidate is canonical. Candidate person_ids written to [AMBIGUOUS_PERSON_REVIEW_2026-08-11.json](AMBIGUOUS_PERSON_REVIEW_2026-08-11.json) — not a table column, not a seed blocker. |
| Creatable — no existing person | 21,511 (incl. paul.gilford — no Pipedrive person yet under that email) | `pipedrive_person_id=null`, `projections_state.pipedrive="skipped:no_person"`, `smartlead` = `pending` if an email was available else `skipped:no_email`, `heyreach="pending"`. **No person created.** |

No projection ever set to `done` in this pass — registry-only, exactly as specified. Row
construction logic (entry_type mapping, TTL/expiry via `computeExpiry` + `reasonExpiryOverride`,
owner_tag/source conventions) mirrors `merge_v1.js`/`reason_v1.js` exactly, so every seeded row is
indistinguishable from what a live `UpsertLedger` insert would have produced — see
`dnc_seed_build.py` for the full construction logic and rationale for each field, including two
judgment calls made without an explicit spec (documented inline: the `source` column's system-tag
convention, and treating "3 collision rows" as 3 representative multi-collision samples since no
specific 3 were named in this conversation).

## Read-back verification — PASS

One combined `get` (returnAll, `anyCondition` OR filter) fetched: 100 random rows + 3 collision
rows (`jurgen-schwanitz-8a66629`, `lindaolsson`, `alex-bilichenko-76ab2121`) + paul.gilford, **plus**
all rows matching `reason=reply_dnc` and `reason=client` (category-filtered, not enumerated by key,
so this is a true full-population check, not a sample of the 142/95).

| Check | Result |
|---|---|
| Sample keys requested but not found | **0 / 104** |
| Field-by-field mismatches (22 fields checked per row) | **0** |
| `reason=reply_dnc` rows found | **143** (142 Amsterdam-2025 + paul.gilford, both reply_dnc — correct, not a discrepancy) |
| `reason=client` rows found | **95 / 95** |
| Domain table: rows with `source=company_dnc_sheet:legacy_import` | **1,373 / 1,373** |

Full detail: `fixtures/seed_verify_report.json`.

## Housekeeping

All seed-writer and verification workflows (`zz_seed_writer_*`, `zz_seed_verify_*`) were
deactivated and deleted after use — confirmed zero `zz_*` workflows remain in the n8n instance.
Two Data Table upserts were also validated on a 4-row cross-category slice (real data, not
synthetic — offboard/client/creatable/ambiguous) before committing to the full run, with an
explicit read-back check, per this project's standing "never trust a write without reading it
back" discipline.

## Bug found + fixed during this pass

The bulk seed-writer workflow's Code node initially read `items[0].json.rows` — but n8n's Webhook
node nests the parsed POST body under `.body`, not merged onto `.json` directly. Fixed to
`items[0].json.body.rows` in `dnc_seed_write.py` before the first real write (caught on the 4-row
validation slice, not on production data).

## What's next

- Company-DNC domains and People-DNC registry rows are live. Stage 2 (WF-4 Sheet intake) may now
  begin, per the standing rule that its dedupe check needs a populated registry.
- Projections (Pipedrive labels for the 2,264 matched, Smartlead blocks, HeyReach exclusions) are a
  **separate, still-ungated** next step — none fired in this pass.
- The 64 ambiguous rows need a lazy human decision (pick canonical person, or confirm they're
  distinct people) — see `AMBIGUOUS_PERSON_REVIEW_2026-08-11.json`, not urgent, not a blocker.
- Pass 2 (Pipedrive/Smartlead-sourced portions) is still pending per the original sequencing.
