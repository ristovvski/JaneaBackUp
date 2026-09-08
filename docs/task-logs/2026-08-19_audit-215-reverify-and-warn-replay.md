# 2026-08-19 — Аудитор: 215-name repair re-verified (drift), + pre-fix warns replayed through the new resolver

Read-only throughout. Nothing written to Pipedrive / Smartlead / n8n. Task given by Nik in the
terminal; #agent-inbox deliberately not opened (standing rule: the channel is not touched at all).

## DONE

### 1. 215-name repair — re-verified 28h after the write. GREEN, four lines.

The 18 Aug 15:41 verdict (thread `1787052341.792469`, msg `1787056906.919999`) already proved the
repair **landed**. The open question was whether it **held** — these persons sit under
always-overwrite automations (WF-1 W1.0.11.1, Make name-matching, the Zapier folder). So line 1 is
now per-id against the recorded `old -> new`, not a changelog count.

Fresh walk 2026-08-19 11:45:31Z → 11:54:22Z: **56,890 persons** (569 pages, cursor exhausted) ·
**4,267 London leads** (579 pages, `more_items_in_collection: false`).

| line | result |
|---|---|
| 1. all 215 still carry the repaired name | **215/215 held**, 0 drifted, 0 absent |
| 2. name == email local-part anywhere in the London population | **0** of 4,248 persons (4,204 testable, 44 no email) |
| 3. lead title ends with person name | **0** genuine mismatches of 4,267; 3 case-only, none in the 215 |
| 4. post-repair writes on the 215 | **0** name-family writes after each person's own repair row; **0** writes of any field by any actor ≠ u25112064 |

Repair window, from its own changelog rows: `2026-08-18 11:33:08 → 11:37:22`.

The 3 case-only titles are unchanged from yesterday and pre-existing provider casing:
`b0f77860` p35819 Person-fd447aa8 · `47641250` p69158 richard owen · `d7d2e540` p50592 DAVID RICE.

### 2. Pre-fix warns replayed through the new resolver — no recovery sweep exists to run.

Corpus from the three deployed warn wordings in WF-1 `2jdjKM2NJr473GdA`, then confirmed
workspace-wide that no warn of these shapes was ever posted outside #niks-channel:
`for unknown person` (M5/M6) 11 · `not in Pipedrive` (M7, pre-14-Aug) 5 · `no match found` (M7,
post-fix) 2 = **18**.

Each replayed through the resolver **as deployed** (slug extraction → `persons/search`
`exact_match=false` → verify a returned person carries an LH value whose slug equals ours, reading
`custom_fields` as a flat array), plus an independent oracle: a slug index over the 50,165 censused
`linkedin_lh` values.

* **15 synthetic fixtures** — `hr-test-*`, `smx-s4-unknown`, `l15p-unknown`,
  `acoaa-w1016-urn-acceptance`. All true absences. 2 are `/company/` URLs where the resolver cannot
  build a key at all — correct, a company URL is not a person.
* **1 real pre-fix warn — Person-9979a87c → RESOLVES NOW** (1 hit, verification true, 1 census match).
  The fix demonstrably works, and he was repaired on 14 Aug.
* **2 post-fix live warns** — Jatin Yadav (already established a true absence) and today's 14:41
  Person-6cc0ad5a.

Recoverable backlog = **one person, already repaired**. No sweep.

## IMPROVABLE — two of my own errors, both caught before publication

1. **Line 4 first reported a false 171.** My cutoff was `11:33:59`, which sits *inside* the repair's
   own 4-minute write window, so it counted the repair as post-repair drift. Correct test is a
   **per-person** cutoff (that person's own repair row), not a run-level one. Same family as
   yesterday's `" - "` split artefact: window-vs-pairing.
2. **The ACoAA hypothesis died on contact, and I nearly shipped it as a finding.** Today's Mikey
   Hirt warn carries a member-URN URL (`/in/acoaacnuulcbikt…`) and 660/50,165 (1.32%) stored LH
   values are URN-form, so I expected a second unfixable miss class (URN ↔ vanity slug is not a
   string transformation). Test: lowercased stored URN of p42369 → **1 hit, Jacob Choi**. URN
   matching works case-insensitively; **hypothesis withdrawn**. Person-6cc0ad5a is a true absence —
   0 persons named Person-6cc0ad5a, 0 LH slug matches, `Bright Data` exists as org 14423 with no such
   person under it.

## PARTIAL / RESIDUAL

* The genuine **cross-form** case — provider sends a URN while Pipedrive holds the vanity slug, or
  the reverse — still cannot be bridged by normalisation. **No live instance observed**, so it is
  stated, not counted as exposure.
* Warn-corpus completeness rests on Slack exact-phrase search over bot messages (the three wordings
  were read out of the deployed node code, not guessed). n8n's ~19-day retention cannot corroborate
  the July warns.

## BLOCKED

Nothing.

## Artifacts

* `audit-artifacts/name_repair_reverify_20260819.json`
* `audit-artifacts/warn_replay_prefix_resolver.json`
* prior: `name_repair_verification.json`, `name_repair_changelog_215.json`,
  `linkedin_lh_format_census.json`

## Estate note (unchanged, still someone's to pick up)

WF-1 live is `da2bbe5f` / **112 nodes** (updated 2026-08-18 09:47Z) — my memory baseline said
W1.0.16 = `5525eba3` / 110 nodes, so there has been a further deploy since.
`zz_probe_verify_ttl_null2` was reported deactivated on 18 Aug by Хранитель.
