# DNC Registry Architecture

**Status:** Reconstructed from the "DNC" Claude Code session transcript (`session_id local_c03cd306-aab9-40ec-9078-e906a580b848`, cwd `C:\Users\User\Desktop\Нова папка`, 1154 messages), because `dnc-architecture.md` did not exist on disk and the architecture had only been hashed out conversationally. Cross-checked against the actual shipped artifacts in `DNC_OBS_P1_build\` (which the chat itself produced, so it is first-party evidence, not an independent corroboration).

**IMPORTANT — scope correction found during reconstruction:** several concepts the reconstruction brief expected to find here (a three-tier `li_url_canon → email → member_id` waterfall, an "oldest-wins" dedupe rule, a `projections_state` machine for Pipedrive/Smartlead/HeyReach, a WF-4 Google Sheet intake flow, a Clay enrichment contract, a `campaign_event_map`-driven Event/Hypothesis convention, and an offboard action with a dry-run-mandatory rule) were **not found anywhere in this session's transcript**, despite a targeted search. Some of these terms *do* exist verbatim in a **different** session in the same workspace — **"Heyrech + Pipedrive"** (`session_id local_d95fa015-f8d2-4128-b442-79a12a52b9b0`) — which is a separate conversation from the one this task named as the source. See "Open questions / gaps" at the end. Everything in the body of this document below is what the named "DNC" session actually contains.

**Second pass, 2026-08-07:** the "Heyrech + Pipedrive" session (title as stored; local jsonl file `818a9f5f-f995-4659-a429-2ec467b3a170.jsonl`, ~5065 messages) was mined directly (grepped on disk, not paged through the summarized event API) for the same 8 items. Full results are folded into §9 below and into "Open questions / gaps." Headline: `member_id` fallback and the "B27 rule" are both **definitively WF-1/WF-2 person-resolver concepts, not DNC** (exact quotes in §9.1–9.2) — the scope correction above is now doubly confirmed, from the source session itself rather than a search snippet. But that session also turns out to contain **a third, separate, unbuilt DNC design** (a "DNC BUILD" task referencing a task file `task-dnc-phase-ab.md` that was never found on disk) which is materially different from `DNC_OBS_P1_build` and was never carried past initial discovery — see §9.3.

---

## 1. What this session actually built

The "DNC" session is a **Claude Code Brief → Spec → Build** pipeline (per the `n8n-workflow-factory` skill) for a **Phase 1 DNC suppression ledger + Smartlead read-only observability** package, followed by a separate **AS-IS infrastructure discovery** run, and then (a distinct, unrelated topic interleaved in the same session) WF-1/WF-2 duplicate-forensics and Pipedrive field-hygiene work for Melisa — the latter is explicitly out of scope for this document per the task brief.

Everything Phase-1-DNC-related was written to `DNC_OBS_P1_build\` on disk:

```
DNC_OBS_P1_build/
  BUILD_LOG.md, TEST_REPORT.md, PUBLISH_RUNBOOK.md, run_all_tests.js, build_dnc.py
  datatables/        dnc_ledger.schema.yaml, obs_state.schema.yaml, CREATE_DATATABLES.md
  subworkflows/      DNC__NormalizeIdentity__v1, DNC__UpsertLedger__v1, DNC__CheckLedger__v1
                      + lib/normalize_v1.js, lib/merge_v1.js, lib/expire_v1.js, lib/obs_v1.js
                      + NORMALIZATION_V1.md, tests/dnc_contract_tests.js
  workflows/         heyreach_reply_to_dnc_ledger/  (Build 3, "1.1")
                      dnc_expiry_job/                (Build 4, "1.3")
                      smartlead_observability_readonly/ (Build 5, "1.4")
                      dnc_check_service/             (Build 6, "1.2")
  fixtures/          heyreach/*.json, smartlead/*.json, ledger_seeds.json
```

Nothing was published; prod WF-1 was never touched; every write path stayed inside DEV-style file artifacts (`active:false` in every workflow JSON). This is the **current, most-amended state** of the design — the schema files above already have the amendments baked in (e.g. `norm_v` is present in `dnc_ledger.schema.yaml` even though the spec pack that started the session didn't mention it).

---

## 2. Registry data model — `dnc_ledger`

Source: `DNC_OBS_P1_build\datatables\dnc_ledger.schema.yaml`, matching the spec pack's §0 plus the amendments below.

Platform constraint that shapes everything: **n8n Data Tables support only `String | Number | Boolean | Date` column types — no enum, no unique constraint, no index, and the row filter only has `Equals / Not Equals / >,>=,<,<= / Is Empty / Is Not Empty` (no `Contains`)**. So every "enum" or "unique" in the spec is enforced in **workflow code**, not the table. This was verified against `docs.n8n.io/build/work-with-data/data-tables` and the n8n GitHub source (`packages/nodes-base/nodes/DataTable/`), not guessed (the build's brief has an invariant against inventing node parameters).

| Column | n8n type | Notes |
|---|---|---|
| `identity_key` | String, required | `= linkedin_slug` if present, else `email_lc`. **Not the full URL** — the bare `/in/{slug}` slug (or lowercased email). Uniqueness enforced in code (Upsert matches `identity_key Equals` before insert). |
| `linkedin_url_norm` | String, nullable | `https://www.linkedin.com/in/{slug}`, lowercased, no query/fragment/trailing slash. Waterfall lookup key #1. |
| `email_lc` | String, nullable | trimmed + lowercased. Waterfall lookup key #2. |
| `full_name` | String, nullable | |
| `pipedrive_person_id` | Number, nullable | **Read-only in Phase 1** — resolved upstream by WF-1; no new Pipedrive writes from this ledger. |
| `entry_type` | String (enum-in-code) | domain `explicit_opt_out \| negative_reply \| replied \| employee_connection \| manual`. Strength order: `explicit_opt_out > negative_reply > replied > employee_connection > manual`. Upsert keeps the strongest value; **never downgraded**. |
| `source` | String, required | `heyreach_reply \| smartlead_category \| pipedrive_personal \| onboarding_import:{owner} \| manual:{user}`. Multiple sources are **appended** (comma-joined, de-duped) on upsert, never overwritten. |
| `owner_tag` | String, nullable | `employee_connection` only — whose LinkedIn connections these are (the **offboarding removal key**: Phase 2's offboarding job removes rows by `owner_tag`, not by reply history). |
| `reply_category` | String, nullable | |
| `status` | String (enum-in-code) | domain `active \| expired \| removed`, default `active`. Soft-delete model — **rows are never hard-deleted** (audit trail). Only `status=active` counts as "on DNC." |
| `added_at` | Date, required | |
| `expires_at` | Date, nullable | null = permanent. `explicit_opt_out` & `employee_connection` are permanent (null); `replied`/`negative_reply` = `added_at + TTL` (CONFIG, default 6 months). |
| `removed_at` | Date, nullable | |
| `removed_reason` | String, nullable | e.g. `dedup_self_heal` (see §5). |
| `correlation_id` | String, required | inherited from the caller (e.g. WF-1's correlation_id) for cross-system trace. |
| `norm_v` | String | **Added by amendment 1** (see §4) — every writer stamps the normalization-ruleset version it used. |

Storage note: ~300–400 B/row; 50 MB default cap ⇒ 100k+ rows (historical peak ~15k) — no cap change needed now; raise via `N8N_DATA_TABLES_MAX_SIZE_BYTES` if it ever nears the limit. Structural growth escape hatch: move storage behind a `dnc.check`/`dnc.upsert` contract to Postgres — the contract, not the table, is the abstraction boundary.

**Lifecycle policy** (enforced by `DNC__UpsertLedger__v1` on write + `dnc_expiry_job` daily):
- `explicit_opt_out` → permanent, never auto-expires or downgrades.
- `negative_reply` → expires in `DNC_TTL_MONTHS` (CONFIG, default 6). *(TTL of 6 months was resolved by Mykyta on a 23 Jul call, per the spec pack.)*
- `replied` → same TTL; **upgradeable to `explicit_opt_out`, never downgradeable**.
- `employee_connection` → `permanent_until_offboarding_event` (Phase 1 does not build the offboarding trigger itself — see §7 Phase 2 backlog).
- `manual` → permanent unless an explicit `expires_at` is supplied upstream.

**Deletion policy:** soft only (`status = removed | expired`). Never hard-delete.

### `obs_state` (companion table, Smartlead observability)

Source: `DNC_OBS_P1_build\datatables\obs_state.schema.yaml`. Not in the original spec (§0 only defined `dnc_ledger`) — designed during the build from workflow 1.4's one-line `state:` note. Single flexible key/value row model keyed by `state_key` (Equals-match + Upsert), columns: `state_key, state_type (watermark|seen_reply|pending_forward|alert_dedupe|counter|digest), campaign_id?, str_value?, num_value?, expires_at?, updated_at`. This table is the **only** thing the Smartlead observability workflow writes — everything else it does is `GET`.

---

## 3. Naming rules and the `zz_probe_` verification-rule exception

**Standing rule (stated repeatedly across the session):** discovery/verification work must be **ABSOLUTE READ-ONLY** — GET/list operations only, **zero writes, zero probes that create objects** — because AI4 (the live conference campaign) is running and nothing may risk touching it.

**Amendment 5** carves out a narrow exception to that rule, named the `zz_probe_` exception. The transcript's own wording, verbatim, from the "NEW PRIORITY RUN — Discovery: AS-IS infrastructure map" message:

> "ABSOLUTE READ-ONLY: GET/list operations on every system, zero writes, zero probes that create objects (AI4 is live). **The zz_probe_ exception from Amendment 5 applies to n8n /datatables only.**"

Scope, exactly as stated: **n8n `/datatables` only** — i.e. Amendment 5 permits creating a probe object (presumably named with a `zz_probe_` prefix so it's identifiable and disposable) against n8n's Data Tables API specifically, as a way to verify Data Table support/behavior without guessing — but grants **no** such exception for Smartlead, Pipedrive, or HeyReach, which stayed strictly read-only throughout.

**In practice, Amendment 5's probe was never exercised**, because the AS-IS map run found `GET /datatables` returning **404** on prod n8n's public API — the endpoint doesn't exist there, so there was nothing to probe against. The build log records this outcome directly:

> "Amendment 5's probe is **not applicable** — prod's public API has no `/datatables` endpoint (404), so a `zz_probe_` create/delete cannot run there; data-table support must be checked in the UI (Q10)." — `DISCOVERY\IMPACT_ON_PHASE1.md`

**The full original definition of Amendment 5 (what exactly the probe object looks like, who authorized it, when) is not present anywhere in this transcript** — see Open Questions.

---

## 4. Amendment history

Numbering in the transcript is **not globally sequential across the whole session** — Amendments 1–4 are one batch (all defined together, in the message that authorized Builds 2–6), and Amendment 5 is a later, single addition referenced only once, with its full text never recovered. There is no Amendment 6 anywhere in this transcript (searched explicitly; no hits).

### Amendments 1–4 (from "Build 2–6 batched run" authorization; user message, 2026-07-23)

The user's own framing: *"Build 1 is approved by the architect with 4 amendments (below)... Standing amendments — apply to every build."*

| # | What it changed | Status |
|---|---|---|
| **1** | `dnc_ledger` gets a `norm_v` (String) column. Build 2 freezes normalization logic in writing as v1; **every writer stamps `norm_v`, every reader may not "improve" the rules silently** — a rule change is a v2, requiring a deliberate migration/backfill, keeping v1 rows matchable. | **ACCEPTED and implemented.** Present in the shipped schema; drift-tested (`dnc_contract_tests.js` proves every Code node embeds `lib/normalize_v1.js` verbatim). |
| **2** | Duplicate tolerance, because the table has no unique constraint: `CheckLedger` **reads** dup-tolerant (returns strongest-`entry_type`-wins across however many rows share an identity); `UpsertLedger` **self-heals** duplicates it encounters (merges onto the strongest/earliest row, soft-removes the extras). The *physical* dedup pass explicitly lives in Build 4 (the expiry job), not in Build 2. | **ACCEPTED and implemented.** Build 2 report; Build 4's "duplicate self-heal pass (amendment 2 hook)" is its designated home — ambiguous ties (identical `added_at`) are skipped and counted (`skipped_ambiguous`) rather than mis-targeted, per `BUILD_LOG.md`. |
| **3** | "Safety lives in the JSON": every workflow carries CONFIG `MODE=dev` and a **send-guard that hard-fails unless the target Slack channel == `C0BFE6KAN8J`**. The `MODE=prod` flip is a `/publish`-time runbook step, not something the build does. In `MODE=dev`, verbose per-run summaries to that channel are explicitly *welcome* (they double as smoke-test evidence) — Melisa's no-happy-path-noise rule is scoped to only apply to `MODE=prod` targets. | **ACCEPTED and implemented** in all six shipped workflows (Send Guard node + `MODE` CONFIG value, test-verified). |
| **4** | Every workflow gets a **smoke checklist**: import → pin fixture → manual run → expected node-by-node outputs, written for a human running it in the n8n UI. | **ACCEPTED and implemented** — one `SMOKE.md` per workflow, all six present. |

### Amendment 5 — the `zz_probe_` exception (see §3)

- **Status: ACCEPTED in principle, but never actually exercised** — the one system it applied to (n8n `/datatables`) turned out not to expose the endpoint it would have probed (404), so the amendment was moot in practice for this run.
- Introduced (per the transcript's own back-reference) in "the previous review message" — a message that granted **three numbered follow-ups** after the Builds 2–6 batch completed. The transcript names them only as:
  - **follow-up #1** = "multi-campaign 5.1" (extending the single-campaign Smartlead-observability workflow, informally called "Build 5.1" by the assistant in its own prior turn — this "5.1" is a *build* number, not a sub-amendment of Amendment 5; the two numbers are coincidental, not nested) → **POSTPONED** ("until the map is reviewed").
  - **follow-up #2** = a "fail-loud schema guard" → **NOT EXECUTED** in this run, but its design is stated concretely: "a top-of-workflow Code node that hard-fails if the returned row is missing required columns incl. `norm_v`" (`DISCOVERY\IMPACT_ON_PHASE1.md`), targeted at `DNC__UpsertLedger__v1`/`CheckLedger`, gated on resolving Q10 (data-table support on prod) first.
  - **follow-up #3** = Amendment 5 (the `zz_probe_` exception) → **executed-but-moot**, as above.

### No Amendment 6 or later found
Explicit searches for "Amendment 6" and beyond across this session returned no hits.

---

## 5. Identity resolution — the "safe waterfall" and canonicalization rules

The user's own name for this in the spec pack: **"Mykyta's 'safe waterfall'."** Frozen as v1 in `DNC_OBS_P1_build\subworkflows\NORMALIZATION_V1.md` (canonical code: `lib/normalize_v1.js`, embedded verbatim in every `DNC__*_v1` Code node, drift-checked by static tests).

**This is a two-tier waterfall — LinkedIn URL, then email. There is no third "member_id" fallback tier anywhere in this session's design** (see Open Questions — a `member_id` fallback concept does exist, but in a different session).

1. **Normalize both identifiers first**, per the rules below.
2. **Match by `linkedin_url_norm`** (exact `Equals` — the platform has no `Contains` operator, so this had to be an exact-match design from the start).
3. **Else match by `email_lc`** (exact `Equals`).
4. **If both identifiers are present and they resolve to DIFFERENT rows/persons → CONFLICT: no write, alert to the ops Slack channel with both records; a human resolves.** This is a hard rule, not a default — the build's static tests explicitly cover `conflicting_identifiers_alert_no_write`.

### LinkedIn canonicalization (v1, frozen)
1. `trim`, then **lowercase** the whole URL.
2. Extract the slug via `/\/in\/([^/?#]+)/` — everything after `/in/`, stopped at the first `/`, `?`, or `#` (strips query, fragment, trailing path).
3. **Percent-decode** the slug (guarded `decodeURIComponent`).
4. Strip trailing slashes; trim.
5. Canonical form: `https://www.linkedin.com/in/{slug}`.
6. **Non-`/in/` URLs** (company pages, school pages, Sales Navigator links, bare handles — anything without `/in/`) → `linkedin_unmatchable = true`, no `linkedin_url_norm` is produced; the caller routes these to conflict/alert rather than guessing an identity.
7. `identity_key` uses the bare `linkedin_slug`, **not** the full canonical URL.

### Email canonicalization (v1, frozen)
- `trim` + **lowercase** only.
- Minimal shape check: must contain `@` with a `.` after it, else `email_lc = null` + an `email_shape_invalid` note (junk is never stored as an identity).
- **Explicitly NO plus-tag stripping and NO dot-stripping in v1** — and the rationale is documented as a conscious choice, not an oversight: dot-insensitivity and `+tag` folding are Gmail-specific; applying them globally would merge genuinely distinct addresses on other providers. In a **suppression** ledger, a false merge is the dangerous direction — it can wrongly suppress (or wrongly clear) a real person, or silently collapse two different people into one row. Under-merging (two rows, both still correctly suppressed) is recoverable; over-merging is not. A v2 with provider-aware canonicalization is left open, contingent on evidence of a real duplicate-identity problem plus a backfill plan.

### `identity_key` derivation
`linkedin_slug` if LinkedIn is matchable, **else** `email_lc`, **else** `null`. A `null` identity_key means the input is unusable: `UpsertLedger` routes it to conflict/alert, `CheckLedger` returns a usage hint.

### Merge / duplicate-tolerance rules ("amendment 2")
- **Conflict** (both identifiers present, matchable, but pointing at different identities) → no write, alert; human resolves.
- **Strongest wins**, not "oldest wins": `explicit_opt_out > negative_reply > replied > employee_connection > manual`. `entry_type` is **monotonic** — never downgraded.
- **Source append**: incoming `source` is unioned into the existing comma-list, de-duplicated.
- **Fill-if-empty** for other identity/enrichment fields — existing non-empty values are preserved, never blanked.
- **`expires_at` recompute** per lifecycle policy on every merge (see §2).
- **Reactivation**: a new event on an `expired`/`removed` row re-suppresses it (`status=active`, **fresh `added_at`**) — i.e. reactivation resets the clock; it does not simply flip status back on the old timestamp.
- **Idempotency mechanism**: `added_at` is preserved on active rows, so `expires_at` is a pure function of `(added_at, entry_type, ttl)`. A replayed event therefore produces an identical row and the merge action is `noop` — this **is** the idempotency guarantee; no separate seen-event marker is required for correctness (though a `heyreach:{reply_event_id}:dnc` key is still carried for audit/trace).
- **Physical duplicate self-heal** (>1 row sharing a resolved identity, e.g. from races or pre-v1 data): handled in `dnc_expiry_job` (Build 4) — merges onto the strongest/earliest row, soft-removes the extras with `removed_reason='dedup_self_heal'`; ties on identical `added_at` are **skipped and counted** (`skipped_ambiguous`) rather than arbitrarily resolved.

**On "oldest-wins": not found as a general rule in this session.** "Earliest" appears only as one tie-breaking input alongside "strongest" when self-healing physical duplicates (Build 4), not as the primary merge rule (which is strength-of-`entry_type`-based). A distinct, generically-named "oldest-wins" rule (attributed to "WF-2's B27 rule") was found — but in the **other** session ("Heyrech + Pipedrive"), applied to a different problem (lead dedup), not this ledger. See Open Questions.

**No "DEL-filter" / soft-deleted-person handling was found anywhere in this session.**

---

## 6. Read/write posture toward Pipedrive, Smartlead, and HeyReach in Phase 1

There is **no `projections_state` machine** (`pending|done|skipped:<why>|failed:<err>`) anywhere in this session — that concept, and the framing of "three projections" (Pipedrive DNC label / Smartlead global block / HeyReach exclusion) as write targets with state tracking, does not appear in this transcript. What the session actually specifies for Phase 1 is much narrower, and entirely read-oriented except for the ledger itself:

- **Pipedrive**: **read-only** — `pipedrive_person_id` is resolved *upstream* by WF-1 and merely carried into the ledger row; Phase 1 makes **no new Pipedrive writes**. (A DNC→Pipedrive label write is listed only as an unbuilt **Phase 2** backlog item, `pipedrive_personal_outreach_to_dnc` — see §7 — with no label-projection or state-machine semantics specified for it.)
- **Smartlead**: **read-only**, absolute, test-enforced. `smartlead_observability_readonly` (Build 5) issues only `GET` calls (`leads-statistics`, `fetch-categories`); every write it performs targets `obs_state`, never a Smartlead endpoint. This is asserted in the build's own review checklist and proven by a static test that every `httpRequest` node is a `GET`. (A "Smartlead global block" write is, again, only a **Phase 2** backlog item, `smartlead_dnc_category_to_ledger`, blocked on the Smartlead webhook freeze during AI4, and again with no state-machine semantics specified.)
- **HeyReach**: HeyReach is the **source** of the one live write path — `heyreach_reply_to_dnc_ledger` (Build 3) is a standalone Execute-Workflow "tee" off WF-1's reply branch, consuming WF-1's already-normalized `reply_received` canonical event and calling `UpsertLedger`. It never touches HeyReach itself (no "HeyReach exclusion" write exists in Phase 1). The AS-IS discovery run later confirmed the wiring reality: **HeyReach → n8n WF-1 → Pipedrive** is a verified live path; nothing in Phase 1 writes back into HeyReach.
- The **only object Phase 1 code writes anywhere live** (once published) is the `dnc_ledger` table itself (and `obs_state` for observability bookkeeping) — no read-back verification step against Pipedrive/Smartlead/HeyReach is specified, because Phase 1 makes no writes to those three systems to verify.

If a `pending|done|skipped|failed` projection-state model is wanted, it was not designed in this session and would need to be specified fresh for whichever Phase 2 backlog item(s) actually write DNC state into Pipedrive/Smartlead/HeyReach.

---

## 7. Phase 2 backlog (specified but explicitly not built in Phase 1)

From the original spec pack (still the most recent statement of these items — nothing later in the session revised them):

```yaml
- smartlead_dnc_category_to_ledger:
    trigger: smartlead webhook lead_category = do_not_contact
    actions: ledger upsert (explicit_opt_out, permanent) + Pipedrive DNC mark; NO Slack (explicit ask)
    blocked_by: Smartlead webhook freeze until AI4 ends

- pipedrive_personal_outreach_to_dnc:
    trigger: salesperson adds person via single canonical field (lh_linkedin_profile_url)
    actions: enrich person → ledger upsert → remove from active campaigns/event lists
    open_risk: HeyReach RemoveFromCampaign historically killed reply webhooks for that lead —
      re-verify (inbox API?) before wiring auto-removal. NEEDS_DOC_EVIDENCE.

- onboarding_connections_import:
    trigger: manual (CSV export of new hire's LinkedIn connections)
    actions: bulk ledger upsert, entry_type=employee_connection, owner_tag={name}

- offboarding_connections_removal:
    trigger: manual (person leaves)
    actions: status=removed for owner_tag={name} AND entry_type=employee_connection only;
      reply-based entries for same people stay (the Bill/Ken/Mirza/Andreas 15k lesson)

- enrollment_gate (contract, not workflow):
    dnc.check(identity) wired into every enroll path — HeyReach now, Smartlead post-AI4.
    Recipe-1 guard "no unsubscribed leads" reads this ledger.
```

Notes on precision, since the reconstruction brief specifically asked about an offboard "dry-run-mandatory" rule: **no dry-run-mandatory rule is stated for `offboarding_connections_removal` anywhere in this session.** The only safety property specified for it is scope precision — it removes rows by `owner_tag` + `entry_type=employee_connection` **only**, explicitly preserving reply-based entries for the same people, referencing an internal cautionary precedent ("the Bill/Ken/Mirza/Andreas 15k lesson") whose details are not further explained in this transcript.

**No "Clay enrichment contract," no "WF-4," and no "Google Sheet intake flow" appear anywhere in this session** — see Open Questions.

---

## 8. Other load-bearing findings from this session

- **`GET /datatables` returns 404 on prod n8n's public API.** This was flagged as "the single biggest Phase-1 risk the map surfaced" — it means Data Table module/version support cannot be confirmed via API at all, and the entire ledger storage layer needs a UI/`n8n --version` check before publish, with the Postgres-behind-contract escape hatch as the fallback if Data Tables aren't available/enabled on prod.
- **Smartlead has zero native webhook subscriptions** (all 114 campaigns return `[]`) — confirming the observability design's choice to poll rather than subscribe, and meaning the still-undocumented reply→categorization pipeline that reaches Pipedrive today runs through some other mechanism entirely (Make, most likely, per the one confirmed Pipedrive webhook, but this is explicitly reported as unverified/hearsay for the Smartlead side).
- **R4 (`pipeline_delta`) as originally built was wrong and was corrected during the AS-IS map run**: it compared *all* Smartlead replies against Pipedrive creations, but only Smartlead's **forwardable** categories (Interested / Not Interested / Information Request, per Melisa) ever produce a Pipedrive record. Corrected formula: `R4 fires when forwardable_new − pipeline_created > r4_delta_threshold` (not `all_replies − categorized`). A related **category-name matching bug** was found in the same pass: real Smartlead category names are Title Case with spaces (`"Not Interested"`), but the shipped code's `forwardable` set used snake_case (`"not_interested"`), which would silently collapse `forwardable_new` to ~0.
- **Publishing gate:** nothing in Phase 1 is live. `/publish` — including attaching the Build 3 tee to prod WF-1 — is explicitly human-gated: quiet window, start of week, rollback `versionId` recorded, per the house release protocol this workspace already uses for WF-1.

---

## 9. Second-session findings — "Heyrech + Pipedrive" (mined 2026-08-07)

Method: the session's transcript file was located on disk (`C:\Users\User\.claude\projects\C--Users-User-Desktop-----------\818a9f5f-f995-4659-a429-2ec467b3a170.jsonl`, confirmed by grepping for a unique string from that session — a personal email address used in a live test — which hit 108 times) and grepped directly for each of the 8 target terms, then the full user/assistant text around every hit was extracted. This is exhaustive for this file — every occurrence of every search term was located and read, not sampled.

### 9.1 `member_id` fallback — WF-1's own resolver, NOT DNC (CONFIRMED, not applicable to DNC)

Verbatim, from the user's own go-ahead: *"GO — three items from the WF-1 audit: 1. W1.0.15 — member_id/public_id fallback in WF-1's person resolver (first cut into the frozen workflow, justified: 20 live cases, the URN class is permanent HeyReach behavior)."* Shipped as **W1.0.16** (98→110 nodes, versionId `5525eba3`), because W1.0.15 was already taken by an unrelated alert gate. Purpose: HeyReach sometimes emits an opaque `ACoAA…` URN instead of a vanity slug; WF-1 already stores `member_id`/`public_id` on the person but its resolver didn't fall back to them, so those 20 cases risked minting duplicate persons. Measured before building: CRM-stored `member_id` equals HeyReach's `linkedin_id` 16/16; searching `custom_fields` by value (not key) carries 0 wrong-field risk across 1,223 production keys. This is the exact same fallback documented in the user's own memory note `wf1-w1016-resolver-fallback.md`. **It is exclusively about WF-1's HeyReach→Pipedrive person resolver. It has no connection to the DNC ledger's identity waterfall** — the DNC BUILD task found in §9.3 doesn't mention `member_id` at all.

### 9.2 "B27 rule" / "oldest-wins" — WF-2's duplicate-*person* picker, NOT DNC (CONFIRMED, not applicable to DNC)

B27 is a WF-2 static-test-ID for a fix to `B Lead Ctx`/`U Lead Ctx`/`Person Pick`/`R Person Pick`: when a Pipedrive person-search-by-email returns multiple candidates (real duplicate person records, e.g. a known "Person-45bca53f" duplicate), the four lead-reads used to previously take `items[0]` with no verification. The fix: all candidates are emitted email-verified, oldest first; the matcher finds which candidate already holds this campaign's lead and **adopts that lead's `person_id`**; if no candidate has a lead, the oldest candidate stands. Verbatim: *"Refusing on ambiguity would be wrong: in the sent branch, falling through means `Person Create` — creating a third duplicate. Deterministic oldest-wins (WF-2's B27 rule) is correct here."* This is WF-2's SENT-branch lead/person-creation dedup, proven live against real duplicate-triggering replays (exec 12439: lead adopted from a different duplicate than the provisional). **It is not a rule about the DNC ledger.** It resolves *which Pipedrive person record* a new lead/reply should attach to when Pipedrive search returns >1 person for the same email — a different problem from the DNC ledger's identity-merge rule (which is strength-of-`entry_type`-wins, per §5 above).

### 9.3 A third, separate, never-completed DNC design ("DNC BUILD" / `task-dnc-phase-ab.md`)

This session contains its own DNC build directive, issued twice verbatim by the user (once retried after an API error):

> "DNC BUILD — proceed with task-dnc-phase-ab.md (the full task file) with these owner amendments:
> 1. Registry = n8n Data Tables (first Phase A check: availability on this instance — if the module is missing, STOP with options).
> 2. WF-2 integration: ONE added node behind the existing DNC gate (Mark DNC path) — upsert into the registry (source=smartlead_dnc, TTL=lifetime) when the DNC branch fires. WRITE_MODE-gated like every write. Same for UNSUBSCRIBED path. Statics + mutants. This is the only WF-2 change — deploy respecting the deploy-window rule.
> 3. WF-1 (HeyReach): NOT touched. Reply-based DNC entries (Melisa's "every replier goes to DNC") come from the WF-D1 daily batch reading Pipedrive responded-persons across BOTH channels — zero risk to the frozen stable workflow. If shadow-era ever demands real-time from WF-1, that's a separate W1.0.15 decision.
> 4. Everything else per the task file: Phase A discovery (Clay tabs inventory — coordinate the export with Nik, SL Block List API, HeyReach lists API, sales Sheet input), Phase B build (registry schema people+company, seed import with dry-run, WF-D1 batch, WF-D2 Sheet→registry→Clay-roundtrip→Pipedrive sync, WF-D4 TTL, WF-D5 dnc-check endpoint, projections).
> Sequencing: Phase A fully read-only first → STOP for Nik → then B. WF-2 node addition lands with Phase B, not before."

Critical facts about this thread:
- **`task-dnc-phase-ab.md` was never found on disk** — the assistant said so directly ("`task-dnc-phase-ab.md` is not on disk anywhere — I don't have the full task file, only your amendments"), so the full spec behind this directive does not exist anywhere findable, only the paraphrase above.
- **It uses `WF-D1`/`WF-D2`/`WF-D4`/`WF-D5` workflow numbering** — not "WF-4" — for a registry (people+company schema), a daily reply-batch, a **Sheet→registry→Clay-roundtrip→Pipedrive sync**, a TTL job, and a `dnc-check` endpoint, plus a bare, unelaborated word "**projections**" at the very end of the Phase B list — no `pending|done|skipped|failed` state machine or any elaboration of what "projections" means is given anywhere; the task was interrupted before Phase B design was ever reached.
- **This is a different, unbuilt design from `DNC_OBS_P1_build`** (the one documented in §1–§8, from the "DNC" session). The assistant itself, on starting this task, went and read `DNC_OBS_P1_build`'s files and its memory note as prior context — confirming the two are related-but-distinct efforts on the same overall problem, not the same build.
- **The task was abandoned mid-Phase-A and never resumed.** Sequence: Phase A discovery ran (Data Table `/datatables` 404 reconfirmed; then a **live throwaway probe was actually built and deployed** — a real workflow with an `n8n-nodes-base.dataTable` node, to test runtime capability directly rather than guessing from the UI — but its webhook never registered; a controlled swap to a plain Code node showed the *same* failure, so the dataTable node was cleared as the cause and something else entirely was blocking new-webhook registration; an active-workflow-cap hypothesis was also disproved; the assistant stopped debugging n8n's registration behavior as out of scope and restored/deleted the probe). Credentials check found Smartlead/HeyReach/Pipedrive available but **no Clay or Sheets credentials** ("those parts need Nik, as the task file anticipated"). HeyReach was found fully read-only-readable (4 lists, 6 campaigns, 4 LinkedIn accounts). Smartlead's block-list path returned nothing documented. Then the assistant hit a server-side `API Error: 529 Overloaded` twice in a row, replied "No response requested" both times, and **the user's very next message pivoted to an unrelated "HEALTH CHECK" task** — the DNC BUILD thread is never mentioned again anywhere else in this session (confirmed: exactly 2 hits for "DNC BUILD" and for "task-dnc-phase-ab" in the whole transcript, both from the same twice-sent message).
- **No answer exists in this session for what the registry schema, WF-D1/D2/D4/D5 workflows, the Clay-roundtrip contract, or "projections" actually are** — the task never got past the initial read-only credential/API-shape check.

### 9.4 An existing, already-live DNC mechanism in production WF-2 (separate from `DNC_OBS_P1_build`)

Independent of both DNC efforts above, this session's own FULL-MATRIX LIVE TEST spec (T9) describes a DNC path that **already exists in shipped WF-2**, pre-dating the DNC BUILD request entirely — item 2 of the DNC BUILD amendments even calls it "the existing DNC gate": *"T9 DNC-shaped reply ('Remove me from your list, do not contact') → DNC category → SL unsubscribe called → Pipedrive DNC label → NO forward, NO alert (silence assert) → registry row IF the DNC-registry node landed."* And T12: *"unsubscribe event (click the unsubscribe link in the test email) → DNC procedure minus classification, silent."* The Pipedrive label write happens through a node literally named `U Lead DNC Label` (seen inside a "Lead Labels Union" node). This is **production WF-2's own DNC-classification branch** (Smartlead unsubscribe call + Pipedrive DNC label, silent, no forward/alert) — a live mechanism distinct from, and pre-existing relative to, the unpublished `DNC_OBS_P1_build` ledger and the never-completed `task-dnc-phase-ab.md` registry. Neither of the two DNC design efforts documented in this file appears to touch or replace it; whether it was ever meant to be superseded by the new registry is not stated anywhere in either session.

### 9.5 Soft-deleted persons / "DEL discipline" — confirmed general, not DNC-specific

`is_deleted` / "soft-deleted persons" appear 23 times in this session, all tied to the general Pipedrive-person-search hygiene rule used across WF-1, WF-2, and the LinkedIn follow-up blast — referred to informally as **"B19/DEL discipline"** (e.g., the LI-blast spec: *"exclude anyone on the DNC label, and exclude soft-deleted persons (B19/DEL discipline)"*). The underlying fact, stated twice: **`persons/search` returns soft-deleted records and carries no `is_deleted` field at all** — the flag only exists on the full person object, not the search-result shape — so any code that trusts the search response for liveness is structurally unable to detect a soft-deleted match; this bit the W1.0.16 build (found by live acceptance, not statics) and was logged as an open, unfixed exposure. **No "DEL-filter" concept scoped to the DNC ledger or DNC registry search exists anywhere in this session** — it is a generic Pipedrive-search gotcha reused by several unrelated builders, not a DNC design element.

### 9.6 Remaining terms — confirmed absent from this session too

- **`projections_state` (or any `pending|done|skipped|failed` state machine):** zero hits for the term; the bare word "projections" appears exactly twice, both inside the same twice-sent DNC BUILD message (§9.3), completely unelaborated.
- **"WF-4":** zero hits. This session's unbuilt DNC design uses `WF-D1/D2/D4/D5` naming instead (§9.3) — a different scheme, not "WF-4."
- **A Google Sheet intake flow:** no literal "Google Sheet" hit, but the DNC BUILD task does specify a "sales Sheet input" (Phase A) and a "`WF-D2 Sheet→registry→Clay-roundtrip→Pipedrive sync`" (Phase B) — i.e., the *concept* exists as an unbuilt line item in this third design, under different naming, with zero implementation detail (no column contract, no trigger, nothing) because the task was abandoned before Phase B.
- **A Clay enrichment contract** (`li_url → name/company/title/email`, "no email is not an error"): not found. "Clay" appears 33 times total, but every DNC-relevant occurrence is either the unbuilt "Clay tabs inventory" / "Clay-roundtrip" line items in §9.3, or the explicit statement that **no Clay credentials were available in this session** ("those parts need Nik"). No field-level contract is ever specified.
- **An offboard action with a dry-run-mandatory rule:** zero hits for "offboard" (checked case-insensitively) anywhere in this session.
- **Amendment 5, Amendment 6+, or a "previous review message" introducing follow-ups #1/#2/#3:** zero hits for "Amendment 5" or any higher-numbered Amendment. The word "amendments" (lowercase, plural) appears only twice in this session, both referring to unrelated things: (a) a prior-context summary's "Phase A/B amendments" for the OpenAI/classifier WF-2 build, and (b) the DNC BUILD task's own "owner amendments" 1–4 quoted in §9.3 — a different, non-overlapping numbering scheme from the DNC session's Amendments 1–5. The one `zz_probe`-adjacent thing found here is unrelated to Amendment 5's text: it's the assistant `cat`-ing the *other* session's own memory note (`dnc-obs-phase1-build.md`, which itself says *"Amendment-5 zz_probe NOT usable (endpoint absent)"*) as background reading before starting Phase A — not a new/independent mention. Separately, this session's own Phase A did build and run a real throwaway `dataTable`-node probe workflow (§9.3) to test webhook/runtime behavior directly — similar *in spirit* to what Amendment 5's exception was for, but never named `zz_probe_`, never tied to "Amendment 5," and testing a different thing (webhook registration, not row create/delete) — so it should not be treated as the missing text of Amendment 5.

---

## Open questions / gaps found during reconstruction

- **Amendment 5's full original text is not in this transcript.** Only its *scope* is quoted verbatim ("The zz_probe_ exception from Amendment 5 applies to n8n /datatables only") and its *practical outcome* (moot, because `/datatables` 404s on prod). What the probe object itself would have looked like (payload, exact `zz_probe_` naming convention beyond the prefix, who/what created and disposed of it) is never spelled out anywhere in this session.

- **The "previous review message" that introduced follow-ups #1/#2/#3 (and, within it, Amendment 5) does not appear anywhere in this session's transcript.** The only trace of it is the user's own back-reference: *"From the previous review message: follow-up #2 (fail-loud schema guard) and #3 (Amendment 5) may still be executed in this run; follow-up #1 (multi-campaign 5.1) is POSTPONED until the map is reviewed."* I paged the entire session (all 1154 messages, oldest to newest) and searched specifically for "Amendment 5," "fail-loud schema guard," and "4 amendments" — each returns exactly one hit, always this same reference or the original 4-amendments batch message. This session has a documented precedent for exactly this situation: later in the same session, the user relays a "WF-3 gray-zone" decision that the assistant searches for across *all* sessions and confirms doesn't exist anywhere — concluding it was decided in a call, not a Claude session. The Amendment-5 review message is very plausibly the same kind of out-of-band (call/Slack/in-person) decision, never typed into any session. **Recommend confirming with the architect directly whether a written version of this review exists anywhere outside Claude Code sessions.**

- **No Amendment 6 (or higher) exists in this transcript.** If the build-order task that triggered this reconstruction implies amendments beyond 5, they were not made in this session.

- **RESOLVED (2nd pass): the person-resolution waterfall in this session is two-tier only (`linkedin_url_norm → email_lc`, conflict-not-fallback on mismatch), and there is definitively no third `member_id` fallback tier anywhere in the DNC design.** The "Heyrech + Pipedrive" session was mined directly (full transcript grepped on disk, every hit read) and confirms `member_id`/`public_id` fallback is **W1.0.16, a WF-1 HeyReach→Pipedrive person-resolver fix** (98→110 nodes, versionId `5525eba3`), built to handle HeyReach's opaque `ACoAA…` URN class — a problem specific to LinkedIn-connection ingestion, with no reference to the DNC ledger anywhere in that thread. See §9.1. This is no longer an open question about *where* the term lives — it's confirmed to not be part of any DNC identity design in either session, including the third, unbuilt DNC design found in §9.3 (which also never mentions `member_id`).

- **RESOLVED (2nd pass): no "oldest-wins" dedupe rule exists for the DNC ledger in either session.** "WF-2's B27 rule" is confirmed (full quote in §9.2) to be a Pipedrive **person-record** dedup fix for WF-2's SENT branch — when email-search returns multiple duplicate person records, the oldest candidate is adopted (or the lead-holding candidate, if one already has this campaign's lead) — proven live against real duplicate-triggering replays. It has nothing to do with DNC-ledger row merging. Confirmed absent from both sessions as a DNC-ledger rule.

- **Confirmed absent from both sessions: no "DEL-filter" concept scoped to the DNC ledger/registry.** What *does* exist, confirmed in the second session (§9.5), is a generic Pipedrive-search hygiene rule informally called "B19/DEL discipline": `persons/search` returns soft-deleted person records and the search-result shape carries no `is_deleted` field at all (only the full person object does), so any code trusting the search response for liveness can silently match a deleted person. This bit the W1.0.16 build and is logged there as an open, unfixed exposure — reused across WF-1, WF-2, and the LinkedIn follow-up blast, but never written as a DNC-ledger design element in either session.

- **Confirmed absent from both sessions: no `projections_state` machine (`pending|done|skipped:<why>|failed:<err>`) for Pipedrive/Smartlead/HeyReach.** The second session's own separate, unbuilt DNC design (§9.3, the "DNC BUILD"/`task-dnc-phase-ab.md` task) ends its Phase B item list with the bare, unelaborated word "projections" and nothing else — no state values, no schema, no code. The task was interrupted (a server error, then the user moved to an unrelated task) before Phase B was ever designed, so this was never actually specified, in either session, and would need to be authored fresh.

- **Partially resolved: no "WF-4" exists in either session, but a Google-Sheet-shaped intake step and a Clay round-trip step DO exist as unbuilt line items in the second session's separate DNC design (§9.3).** That design uses `WF-D1/D2/D4/D5` naming (not "WF-4") and specifies, without any further detail, a "sales Sheet input" (Phase A) and a "`WF-D2 Sheet→registry→Clay-roundtrip→Pipedrive sync`" (Phase B). No column contract, no trigger, no field mapping (`li_url → name/company/title/email`), and no "no-email-is-not-an-error" rule is stated anywhere — the assistant explicitly noted it had no Clay or Sheets credentials available and that "those parts need Nik." The underlying `task-dnc-phase-ab.md` task file that would presumably contain the real contract **was never found on disk** in that session either. So: the *concept* is confirmed to exist (under different naming, in a third, incomplete design), but the *contract* the brief was looking for is confirmed absent from both sessions.

- **Confirmed absent from both sessions: no `campaign_event_map` usage tied to the DNC ledger's Event/Hypothesis fields.** The term appears in the second session too (a code snippet: `camFallback = (cfg.campaign_event_map || {})[campIdStr]`), and it is, again, the WF-2 Normalize-node Event/Hypothesis CONFIG fallback for Melisa's person-field backfill — the exact same unrelated usage already documented from the "DNC" session, not a DNC-ledger mechanism, in either session.

- **Confirmed absent from both sessions: no dry-run-mandatory rule for an offboard action, and no "offboard" term at all in the second session** (checked case-insensitively, zero hits). The only offboarding-flavored safety property found anywhere remains the DNC-session's scope-precision rule for `offboarding_connections_removal` (§7).

- **Confirmed absent from both sessions: no Amendment 5 text, no Amendment 6+, and no "previous review message" introducing follow-ups #1/#2/#3.** The second session's own uses of the word "amendments" are unrelated: WF-2/classifier build amendments, and the separate DNC design's own "owner amendments" 1–4 (§9.3) — a different, non-overlapping numbering scheme. The only Amendment-5/`zz_probe_`-adjacent text found there is the assistant reading the *other* session's own memory note as background (which itself just repeats "Amendment-5 zz_probe NOT usable"), not an independent source. Note for context, not as an answer: the second session's own Phase A **did** build and run a real throwaway `n8n-nodes-base.dataTable` probe workflow to test runtime behavior directly (§9.3) — similar in spirit to what Amendment 5's exception was for, but testing webhook registration rather than row create/delete, never named `zz_probe_`, and never tied to "Amendment 5" — so it should not be read as the amendment's missing text, just as a structurally similar, independently-motivated probe.

- **New from the second session, not in the original brief: production WF-2 already has a live, pre-existing DNC mechanism** (§9.4) — a "DNC gate"/"Mark DNC path" branch that, on a DNC-classified reply, calls Smartlead's unsubscribe endpoint and writes a Pipedrive DNC label (node `U Lead DNC Label`) silently (no forward, no alert). This is separate from both `DNC_OBS_P1_build` (§1–8) and the unbuilt `task-dnc-phase-ab.md` registry (§9.3). Neither DNC effort documented in this file states whether it's meant to replace this existing mechanism or sit alongside it — recommend asking the architect directly.

- **New from the second session, not in the original brief: a third, separate, unbuilt DNC design exists** (§9.3) — a "DNC BUILD" task referencing `task-dnc-phase-ab.md`, a task file that was never found on disk in either session. It specifies `WF-D1/D2/D4/D5` workflows (daily reply-batch, Sheet/Clay/Pipedrive sync, TTL job, `dnc-check` endpoint) and was abandoned mid-Phase-A-discovery after a server error interrupted it, never resumed. Its relationship to `DNC_OBS_P1_build` (which came first as tested/shipped file artifacts) is not stated in either session — recommend confirming with the architect which design, if either, is meant to actually ship.

- **Prod n8n's Data Table support remains unverified** (`GET /datatables` → 404 on the public API, reconfirmed independently in the second session's own Phase A run) — this blocks confirming whether either ledger design can even be created as specified on the real prod instance.
