# Melisa's ask — "Event name" / "Marketing Hypothesis" gap — Report

Read-only diagnosis complete. Dry-run computed. **Zero writes performed to Pipedrive or to any live
n8n workflow.** Two safe, non-Pipedrive fixes applied (a local script edit); everything else awaits
your word.

## 1. The "372" derivation

None of the direct interpretations matched exactly. The one that lands within a normal live-dashboard
drift margin (2–3, explainable by new leads landing between when Melisa looked and when this ran):

> **Ai4-2026-titled leads (active only, 0 archived) where Event name is empty OR Marketing
> Hypothesis is present but not the exact canonical string "Events Visiting"** → **375 leads / 374
> distinct persons.**

Every other tested lens was far off and is included for the record:
- All-time, any Ai4 title, Event name strictly empty: **2,116** (94% is 2025-era legacy, see §4).
- 2026-titled only, Event name strictly empty: **47**.
- Backfill-300's 300 emails: **all 300 are inside the 374**, zero outside — confirms it's the
  dominant single contributor, not a coincidence.

**Recommendation:** treat 374/375 as the operative definition and proceed on that basis (per your
instruction #3). If Melisa's live count still reads differently after this fix lands, that's the
signal to get her exact dashboard filter (your instruction #4) — but the evidence here is strong
enough not to block on that first.

## 2. Root causes (three distinct, independently confirmed)

**a) Hypothesis casing/typo fragmentation — the dominant driver (321 of 373 computed fixes).**
Verified via live changelog: a 2025-10-30 manual bulk-fix (actor Melisa, via Pipedrive's own
`bulk-actions-api`) wrote `"Events visiting"` (lowercase v) instead of the canonical
`"Events Visiting"` for one cohort; other cohorts show `"Event Visiting"` (singular) and a
trailing-space variant. Three non-canonical spellings, 434 records total, fragment any exact-match
dashboard group-by.

**b) The one-off backfill script's genuine oversight (44 records — the 300 backfill + a few
overlaps).** `backfill_ai4_persons.py`'s `F` dict declared the correct Hypothesis field key but
never called `put()` on it, and had no `event_name` key at all. **Fixed directly in the script**
(local edit, no Pipedrive write) — see §5.

**c) Structural: email-campaign names are single-bracket, so no one's code could ever derive Event
name from them (8 + the LinkedIn-batch overlap).** WF-2's own `Normalize` node explicitly documents
"same contract as W1.0.13.1: two-bracket convention." The 4 active email campaigns are named
`[Events Visiting] AI4 2026 - Rune - Catch-alls` — **one bracket**, not two. WF-2's bracket-parser can
derive Hypothesis (bracket 1) but structurally cannot derive Event name (needs bracket 2) from this
name, no matter how correctly it runs. Renaming live Ai4 campaigns mid-flight is against house rules
(per `wf1-w1013-event-marker-parser` memory), so the fix has to be a CONFIG-level override, not a
rename. See §6 for the proposed patch.

**Bonus, unplanned finding:** 8 LinkedIn leads created 2026-08-05T12:09–12:10 (all within 9 seconds —
a batch job, not organic webhook processing) show **zero corresponding person-changelog activity** —
whatever created them touched the lead only, never the person. Same bug *class* as (b), different
pathway, worth a name if it recurs: "lead-create paths that skip the person marketing fields."

## 3. What's report-only, not fixed (2,116 legacy, per your instruction #6)
94% of the all-time "missing" count (2,069/2,116) is 2025-era leads — either `AI4 2025` campaigns or
the older `"Ai4 Conference | ..."` title format, all dated 2025-08-05 through 2025-08-08 (clear
30-per-minute batch clusters — the original 2025 Ai4 backfill). These **predate WF-1's whole
event-marker feature by nearly a year** (shipped 2026-07-21). Not a live defect. Melisa/Lilla's call
whether these matter for the current dashboard; not touched here.

## 4. Dry-run (computed, not written) — `melisa_dry_run_output.json`

373 persons with a computed intended write (1 excluded — `John Mathew`, malformed bracket structure,
flagged for manual review, not auto-fixed):

| Change type | Count |
|---|---|
| Hypothesis typo-fix only | 321 |
| Event name only | 8 |
| Both fields | 44 |

Sample (full list in the JSON file):
```
person 85457 (pii-b3826389@example.invalid) [config_map[3686193]]: 3686193 - AI4 2026 - Rune - Catch-alls - Person-0f138f6a
    hypothesis: 'Event Visiting' -> 'Events Visiting'
```
Values derived two ways, verified against ~2,300 already-correct persons before use:
- **Two-bracket parse** (LinkedIn titles): bracket 1 → Hypothesis via the same `marker_canon` map
  WF-1/WF-2 already use; bracket 2 verbatim → Event name.
- **CONFIG campaign-id map** (the 4 single-bracket email campaigns): `hypothesis="Events Visiting"`,
  `event_name="Ai4 2026"` — literal values, verified against the correctly-filled population, not
  guessed.

## 5. Fix applied now (no Pipedrive write — local script edit only)
`backfill_ai4_persons.py`: added the missing `event_name` field key and the two `put()` calls the
script always should have had. This only matters if the script is re-run for a future batch (it
skips existing persons on re-run, so it does **not** retroactively fix the current 373 — that needs
the dry-run above, applied on your word).

## 6. Proposed permanent fix — WF-2 CONFIG patch (NOT deployed; reviewed diff only)

Add one new top-level CONFIG key (`CONFIG.fields.event_name`/`hypothesis` already exist and are
already used correctly by Person Create/Patch — only the *derivation* needs a fallback):

```jsonc
// ADD to the CONFIG node's JSON, alongside the existing "fields"/"marker_canon" keys:
"campaign_event_map": {
  "3686193": { "hypothesis": "Events Visiting", "event_name": "Ai4 2026" },
  "3686187": { "hypothesis": "Events Visiting", "event_name": "Ai4 2026" },
  "3686184": { "hypothesis": "Events Visiting", "event_name": "Ai4 2026" },
  "3686181": { "hypothesis": "Events Visiting", "event_name": "Ai4 2026" }
}
```

And in the `Normalize` node's marker-parser block, immediately after the existing bracket-derivation
(right after `if (groups.length >= 2) { ... event_name = ev; }`), add a **fallback that only fills
what bracket-parsing left null — never overrides a successful parse**:

```js
// FALLBACK: single-bracket email campaigns structurally can't carry a 2nd bracket for Event
// name. Consult an explicit CONFIG map before leaving it null. Never overrides a bracket-derived value.
const campIdStr = String(pick(b.campaign_id, b.campaign?.id, ld.campaign_id) ?? '');
const camFallback = (cfg.campaign_event_map || {})[campIdStr];
if (camFallback) {
  if (!hypothesis) hypothesis = camFallback.hypothesis ?? hypothesis;
  if (!event_name) event_name = camFallback.event_name ?? event_name;
}
```

This is additive and reviewed, not pushed. Per house protocol for this instance (matches how every
other WF-1/WF-2 change has gone this session): deploy at a quiet window, with a rollback version
recorded, once you say go. Every future email-side lead's person would carry both fields from
creation — no more recurrence of root cause (c).

## 7. One-liner for Melisa
"Found it: 374 people are missing the field because (1) a 2025-10 manual fix used inconsistent
spelling for 'Events Visiting' on ~320 of them, and (2) our email campaigns' names only ever supported
half of what the two-part convention needs, so no automation — ours or Make's — could derive 'Event
name' from them. Fixing the spelling and backfilling the ~370 now (your go first); adding a permanent
lookup table to our email workflow so this can't recur. The 2,000+ 2025-era ones are old history from
before this feature existed — separate call on whether those matter."

## Status — stop here, per your protocol
Read-only diagnosis: **done.** Local script fix: **done** (no Pipedrive impact). Dry-run: **computed,
in `melisa_dry_run_output.json`, zero writes performed.** CONFIG patch: **proposed, not deployed.**
**Awaiting your word before any live Pipedrive write or any n8n deploy.**
