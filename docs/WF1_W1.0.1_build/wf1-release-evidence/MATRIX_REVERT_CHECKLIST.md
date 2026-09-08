# FULL-MATRIX WINDOW — REVERT CHECKLIST (armed 2026-07-30, before any change)

If the session dies, the window is abandoned, or anything looks wrong: run these in order. Every
item is one edit + one rebuild + one deploy. Nothing here needs investigation first.

## Pre-window state (captured BEFORE the window opened — this is what "reverted" means)

| setting | pre-window value |
|---|---|
| WF-2 `WRITE_MODE` | `shadow` |
| WF-2 `forward_owner_map.Chrissy` | `chrissy@janeasystems.com` |
| WF-2 `forward_review_address` | `melisa@janeasystems.com` |
| WF-2 `slack_channel_replies` | `C0B8GCVNR5W` (unchanged during window) |
| WF-2 versionId | `ab1ef090-971e-4aa1-b038-69e70c9bc6f2` |
| WF-2S `campaign_allowlist` | `[]` |
| WF-2S versionId | `320ce9e2-4968-403f-9038-830b5f9819a3` |
| WF-2H versionId | `58e066c1-64cc-4213-9371-84a2134b7f26` |
| WF-ERR versionId | `9949e6e4-bf81-4210-be35-99bbb7501775` |
| WF-1 versionId | `da23d080-a0e0-4126-81c0-0cca60908435` (NEVER touched) |

## Revert steps

1. **`build_wf2.py`** — `"WRITE_MODE": "live"` -> `"shadow"`
2. **`build_wf2.py`** — `"Chrissy": "pii-c61c7d08@example.invalid"` -> `"chrissy@janeasystems.com"`
3. **`build_wf2.py`** — `"forward_review_address": "pii-c61c7d08@example.invalid"` -> `"melisa@janeasystems.com"`
4. **`build_wf2s.py`** — `"campaign_allowlist": [ ...matrix ids... ]` -> `[]`
5. Rebuild **without** `--allow-live`:
   `python build_wf2.py "WF-2 Smartlead Receiver - built.json"` (must succeed with no flag — that
   proves WRITE_MODE really is back to shadow) and `python build_wf2s.py wf1-release-evidence/wf2s-built.json`
6. Suites with the DEFAULT expectation (no `WF2_EXPECT_MODE`): `node --test wf2_static_contract_tests.js`
   and `node wf2s_static_contract_tests.js`
7. Deploy under the window rule: pause WF-2S -> PUT WF-2 -> PUT WF-2S -> verify WF-2 webhook 200 ->
   unpause WF-2S
8. Pause + delete every matrix campaign (ids in `MATRIX_MANIFEST.json`)
9. Delete test trails — ours AND Make's — for every matrix lead: activities, leads, persons, orgs.
   Organic writes from the window REMAIN (identify by lead email not in the manifest).
10. Re-verify: `WRITE_MODE=shadow`, allowlist `[]`, Chrissy + review address restored, WF-1 versionId
    unchanged, all five workflows active.

## Hard rules for the window

* WF-1 is never touched.
* Organic events that arrive during the window are processed LIVE and their writes STAY.
* No campaign outside the manifest is touched.
* If WF-2 stops answering 200, do not unpause WF-2S — replays would 404 and be marked lost.
