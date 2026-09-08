# WF-1 HeyReach Receiver — W1.0.1 release report (F9–F12)

**Date:** 2026-07-12
**Base:** `WF-1 HeyReach Receiver - W1.0 patched.json` (88 nodes, inactive)
**Result:** `WF-1 HeyReach Receiver - W1.0.1 patched.json` (89 nodes, inactive)
**Status:** **25/25 static tests green** and **LIVE reply-path re-run 7/7 PASS with content assertions** (run-id `HRTest0712R3`, see §7.4) after **F12.1** fixed a critical defect that the first run's evaluator missed. W1.0.1 (incl. F12.1) deployed to WF-1 (89 nodes) which **remains INACTIVE**. Residual actions: admin must delete 20 leftover `HR Test` persons/orgs (§7.4.1), rotate secrets (§8); the test double `NNOVii5ImjFKDSM0` was **left published at the owner's request** (teardown deferred — see §7.4.1).

> **F12.1 (critical):** In the first run all four reply alerts posted the *literal* string `{{ $json.alert_text }}` — the `M7 Critical Slack` text field was missing the `=` expression prefix (same bug class F12 fixed in the warn nodes). The evaluator only checked delivery (`ok=true`), so it wrongly reported PASS. F12.1 adds the `=`, and the evaluator now asserts the **posted** `message.text` (rendered content + no `{{`). Verified by re-run (§7.4).

---

## 1. Live preflight (read-only, already performed)

| Check | Result |
|---|---|
| WF-1 (`2jdjKM2NJr473GdA`) active? | **false** |
| WF-1 node count | **75** — still the pristine baseline; W1.0 (F1–F8) was never deployed |
| WF-1 pinData present | true (will be stripped on W1.0.1 deploy) |
| Error workflow bound | `BbrXPABgOaaTJjD6` (WF-ERR) |
| Dangling `WF-1 TEST DOUBLE` | **none** |
| Other workflows | WF-0 Discovery, WF-ERR, "HeyReach — Phase 0 Payload Capture" — all inactive |

The instance is clean: nothing was left dangling by the previously-stopped run. `deploy` will jump the live WF-1 from the 75-node baseline directly to the 89-node W1.0.1 (F1–F12) — still inactive.

---

## 2. Per-fix diff summary

### F9 — Restore "Replied to invite" classification (node: `M7 Build`)
Replaced the hardcoded `const targetStage = 'Replied';` with the hybrid rule:
```js
const followUpRank = rank['First follow-up sent'] ?? 3;
const hasOutboundMessage = (Array.isArray(norm.msgs) ? norm.msgs : []).some(m => m && m.is_reply === false); // strict: undefined/null/missing is NOT outbound
const repliedToInvite = !norm.is_inmail && curRank < followUpRank && !hasOutboundMessage;
const targetStage = repliedToInvite ? 'Replied to invite' : 'Replied';
```
`targetRank = rank[targetStage] || 4` — both stages rank 4, so transition math is unchanged. No re-transition added (deferred to Melisa, see §8). `msgs` is referenced as `norm.msgs` inline to avoid the TDZ (it is declared later in the node).

### F10 — Failure-isolated critical reply alert; de-duplicated tail; separate warn terminals
New nodes and rewiring on the `every_message_reply_received` branch:
- **NEW `M7 Reply Context`** (Code, `runOnceForEachItem`) — depends **only** on `$('CONFIG')` + `$('Normalize')`. Emits `reply_text`, `is_inmail`, `campaign_name`, `sender_name`, `full_name`, `position`, `company_name`, `linkedin_url` (`norm.lead.url`), and `alert_text` (escaped, see F12). Reply-render logic duplicated from M7 Build.
- **NEW `M7 Critical Slack`** — cloned from `M8 Slack` (same credential `Slack account 3`, typeVersion 2.3, channel from CONFIG), text `{{ $json.alert_text }}`, **`onError: continueRegularOutput`** so a Slack outage cannot block CRM processing.
- **Rewire (front):** `Switch[3] → M7 Reply Context → M7 Critical Slack → M7 IF Email Present`. The alert now fires before any resolver/CRM write.
- **Removed** `M8 Slack Text` and `M8 Slack` (the alert moved, not duplicated). New tail terminals: `M8 IF Transition(true) → M8 IF Lead ID(true) → M8 Task` (end); `M8 IF Transition(false)` = terminal; `M8 Task` = terminal.
- **Separate warn terminals:** `M7 Slack Warn` is now the unknown-person terminal only (fed by `M7 IF URL Found(false)`); **NEW `M7 No Lead Warn`** is the no-lead terminal (fed by `M7 IF Lead ID(false)`, `M7 IF Reply Activity Lead(false)`, `M8 IF Lead ID(false)`), text `⚠️ WF-1: {event} — person resolved but no lead found for person {person_id}; CRM write skipped (reply alert already sent)`.
- **Graph invariants asserted statically:** no cycles; the unknown-person path contains no `M7 Build` reference; `M7 Critical Slack` is reachable from Switch output 3 through Normalize-only dependencies.

### F11 — Remove `require('crypto')` from `Dedupe`
Replaced the sha256 fallback with an import-free deterministic key (adds `conversation_id` entropy); staticData store + 48h prune unchanged:
```js
const key = (body.correlation_id && body.correlation_id !== nil)
  ? body.correlation_id
  : [body.event_type || '', body.lead?.profile_url || '', body.timestamp || '', body.conversation_id || ''].join('|');
```
Removes the `NODE_FUNCTION_ALLOW_BUILTIN` deployment dependency.

### F12 — Slack mrkdwn escaping for user-originated strings
`escapeSlack(v){ String(v ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }` applied to all user fields in `M7 Reply Context` (reply_text, full_name, position, company_name, campaign_name, sender_name, linkedin_url) and to the profile URL in `M5/M6/M7 Slack Warn`. **Also fixed a latent bug**: the W1.0 warn `text` expressions used single braces (`={ … }`, from an f-string), which n8n would not evaluate; they are now proper `={{ … }}` expressions. `M7 Slack Warn` was additionally reduced to Normalize-only (no `M7 Build` reference) to satisfy the F10.6 unknown-person-path invariant. `Lead Resp Invalid` carries no user-originated text, so nothing to escape.

---

## 3. Static tests — 24/24 green

14 original W1.0 tests (unchanged, still pass) + 10 new for F9–F12:
- **T8a–d** classifier matrix: invite-reply → `Replied to invite`; at `First follow-up sent`/outbound present → `Replied`; InMail without outbound → `Replied`; message missing `is_reply` is NOT outbound → `Replied to invite`.
- `M7 Reply Context` renders reply text + placeholders and escapes `& < >` (fed `<@U123> & <https://x|y>`; asserts `&amp;`/`&lt;@U123&gt;`, no live mention/link token).
- F11 Dedupe: no `require()`, `conversation_id` participates in the key.
- Tail: `M8 Slack`/`M8 Slack Text` absent; `M8 Task` non-retried POST terminal.
- Critical-alert wiring + continue-on-fail; Reply Context uses only CONFIG/Normalize.
- Graph: no cycles; unknown-person terminal is `M7 Slack Warn` with no `M7 Build` reference.

The 14 original tests also still pass against the W1.0 base (no regression).

---

## 4. Artifacts (regenerated & checksummed)

All under `WF1_release_pack_W1.0.1/` (see `CHECKSUMS.sha256`, verified with `sha256sum -c` → all OK):
- `WF-1 HeyReach Receiver - W1.0.1 patched.json` (89 nodes, inactive)
- `WF-1 HeyReach Receiver - W1.0.1 api-payload.json` (name/nodes/connections/settings only)
- `patch_wf1_w101.py` — deterministic W1.0 → W1.0.1 (byte-identical on re-run; validates F9–F12 + F10.6 graph invariants)
- `wf1_static_contract_tests.js` — 24 tests
- `wf1_n8n_release_runner.py` — updated evaluators (T4/T7) + new T8 / T-F10 + fixtures + mid-suite lead-delete
- `build_wf1_audit_repo_w101.py`, `WF1_W1.0.1_AUDIT_REPO.bundle` — audit history
- `WF1_example_fixtures_W1.0.1/` — T8a–d classifier fixtures + carried-forward T4 + manifest
- `STATIC_TEST_RESULTS.txt`, `RELEASE_MANIFEST.json`, `WF1_GIT_LOG.txt`, `CHECKSUMS.sha256`

Line endings normalized to LF; the deterministic rebuild is byte-identical.

---

## 5. Git audit trail

Continuous history (bundle clones cleanly; final `wf1.json` byte-matches the release):
```
ea62a86 chore: regenerate release artifacts
cc5f07d F12: Slack mrkdwn escaping for all user-originated strings
ca0df83 F11: remove require('crypto') from Dedupe (import-free deterministic key)
a200ae7 F10: critical reply alert before CRM writes; de-duplicate tail alert; separate warn terminals
08fa5c0 F9: restore Replied-to-invite classification (hybrid rule) in M7 Build
694931a chore: remove pins and stale connection records   (W1.0)
… F1–F8, baseline
```

---

## 6. Deviations from the task text

- **F10 "M7 Slack Warn text unchanged":** the W1.0 warn text referenced `$('M7 Build')` and used non-evaluating single braces. Because F10.6 requires the unknown-person path to carry no `M7 Build` reference (and F12 requires escaping + a working expression), `M7 Slack Warn` was rewritten to a Normalize-only, escaped, double-brace expression. Semantically identical for the unknown-person case it now exclusively serves.

---

## 7. LIVE acceptance — run 1 (run-id `HRTest0712`) — **VERDICT SUPERSEDED, see §7.4**

> ⚠️ This run reported 11/11 PASS but the verdict was **overturned**: the reply alerts posted literal `{{ $json.alert_text }}` (delivery `ok=true`, content garbage). Kept below for the audit trail; the authoritative result is the F12.1 re-run in §7.4.


Sequence run via the runner (env-only secrets): `preflight --run-static` → `deploy --apply` → `create-double --publish --apply` → `run-suite --melisa-warned --confirm-synthetic-side-effects` → evidence review → `cleanup-pipedrive` (dry, then `--apply`) → `teardown --delete --apply`.

- **deploy:** WF-1 PUT to W1.0.1, re-GET node-level verify **passed**, `active=false` (versionId `4b71b43b…` → `c40047d4…`).
- **test double:** `WF-1 TEST DOUBLE HRTest0712` (`q35d4IvWttJZDiyP`), path `hr-test-hrtest0712-9bd5a4ee`, published in project `57BsS5BV36DRX0Cw`; **deleted at teardown** (0 doubles remain).
- **WF-1 remained INACTIVE throughout** (final: `active=false`, 89 nodes).
- Slack alerts delivered to `niks-channel` (`C0B8GCVNR5W`) — every reply test shows `ok=true`.

| Test | Exec | Result | Evidence |
|---|---|---|---|
| T1 new sent (email) | 9909 | **PASS** | person+lead+activity created once |
| T2 exact replay | 9910 | **PASS** | Dedupe drop, no writes |
| T3 fresh-ts repeat | 9911 | **PASS** | existing lead selected, activity, no dup, no warn |
| T4 first reply | 9912 | **PASS** | critical alert first, text `💬 Reply from HR Test … Person 4 …`, Slack `ok`, reply activity `40594`, task `40595`; **M8 Slack absent** |
| T5 late accepted | 9913 | **PASS** | stays replied/responded, connected_at filled |
| T6 empty email | 9914 | **PASS** | email search skipped, URL path, no `emails[]` |
| T7 unknown person | 9915 | **PASS** | **critical alert w/ actual reply text** ("Unknown-profile test reply"), `M7 Slack Warn` fired, **zero Pipedrive writes** |
| T8-setup / T8 | 9916 / 9917 | **PASS** | reply-to-invite → **`Replied to invite`**, transition, responded label, task `40600` |
| T-F10-setup / T-F10 | 9918 / 9919 | **PASS** | lead `418ba6f0…` deleted mid-suite (HTTP 200), critical alert delivered, `M7 No Lead Warn` fired, **zero lead/activity/task** |

Full execution JSON per test preserved under `wf1-release-evidence/live-HRTest0712/`.

### 7.1 Deploy-compatibility fixes made to the runner during the live run
The Public API on this n8n Cloud instance is stricter than the W1.0 runner assumed; three real fixes were applied (and are in the shipped runner):
1. **`settings` allowlist** — PUT/POST reject UI-only keys (`timeSavedMode`, `availableInMCP`); the payload builder now sends only API-accepted settings (preserves `errorWorkflow`, `executionOrder`, `callerPolicy`).
2. **`projectId` not in POST body** — the double is created then placed via the transfer endpoint; here it was already created in the correct project (`57Bs…`), so no transfer was needed.
3. TLS: `requests` needed the Windows-trusted CA bundle (a TLS-inspecting proxy sits in front); handled via `REQUESTS_CA_BUNDLE`.

### 7.2 Cleanup outcome (partial — action required)
- **Deleted (HTTP 200):** 8 activities (`40592,40593,40594,40595,40597,40598,40600,40602`) and 4 leads (`1a6d4f10…, 2fa1eda0…, 37fc2470…, 418ba6f0…`).
- **NOT deleted — token lacks permission (HTTP 403 on v1 and v2):** 4 persons and 4 orgs, all `HR Test HRTest0712 …`. **An admin must delete these manually:**
  - persons: `81294` (Person 4), `81295` (Person 5), `81296` (Person 8), `81297` (Person F10)
  - orgs: `20920` (Company 4), `20921` (Company 5), `20922` (Company 8), `20923` (Company F10)
  - Their leads/activities are already gone, so they are inert `HR Test` records.

### 7.3 Production WF-1 pinData
The Public API cannot clear the baseline `pinData` (PUT rejects a `pinData` body key). WF-1 still reports `hasPinData=true`. This is **cosmetic/safe** — pinData only affects manual editor runs, not production webhook executions — and it clears when Nik re-imports the rotated workflow via the editor. Flagged below.

---

## 7.4 F12.1 fix + authoritative re-run (run-id `HRTest0712R3`) — 7/7 PASS

**Fix:** `M7 Critical Slack` text `{{ $json.alert_text }}` → `={{ $json.alert_text }}` (git commit `F12.1`). Audited every Slack text field: `M5/M6/M7 Slack Warn`, `M7 No Lead Warn` already had `={{…}}`; `Lead Resp Invalid` is a brace-free literal; **WF-ERR Slack** is a valid `=`-prefixed template (`=🚨 …{{ … }}`) and renders correctly — no change. **Evaluator hardening:** Slack assertions now read the posted `message.text` and require (a) the rendered reply-alert prefix (`💬`/`:speech_balloon:`), (b) the actual reply text present, (c) **no `{{`**; plus a suite-global guard that fails any test where any Slack node posted `{{`. Static suite adds the `={{`-prefix rule (25/25).

Deploy: only diff was `M7 Critical Slack`, PUT verified, WF-1 `active=false` (versionId `050a717c`). Fresh double `NNOVii5ImjFKDSM0`.

| Test | Exec | Result | Posted `message.text` (footer trimmed) |
|---|---|---|---|
| T1 new sent | 9927 | **PASS** | person+lead+activity created once |
| T4 first reply | 9928 | **PASS** | `:speech_balloon: Reply from HR Test HRTest0712R3 Person 4 (Synthetic Test Engineer @ … Company 4) / Campaign: … · via Person-87a2e116 / &gt; HR Test actual reply text HRTest0712R3 / LinkedIn: <…/person-4>` — reply activity + task, responded label |
| T7 unknown person | 9929 | **PASS** | critical alert with `&gt; Unknown-profile test reply`; warn `:warning: WF-1: every_message_reply_received for unknown person <…/unknown> — skipped`; **zero Pipedrive writes** |
| T8-setup / T8 | 9930 / 9931 | **PASS** | `&gt; HR Test reply-to-invite HRTest0712R3`; classifier → **`Replied to invite`**, responded, task |
| T-F10-setup / T-F10 | 9932 / 9933 | **PASS** | lead `c9352ae0…` deleted mid-suite (HTTP 200); critical alert delivered; no-lead warn `:warning: WF-1: … — person resolved but no lead found for person 81303; CRM write skipped (reply alert already sent)`; **zero lead/activity/task** |

T2/T3/T5/T6 skipped (untouched by F12.1; green in run 1). Verbatim full texts (with n8n footer) in `wf1-release-evidence/live-HRTest0712R3/*-execution.json`.

### 7.4.1 Cleanup + admin list (all three runs)
- **Deleted via API (HTTP 200):** all leads and activities from runs `HRTest0712`, `HRTest0712R2`, `HRTest0712R3`.
- **NOT deletable with this token (403 on persons/orgs) — admin must delete (all `HR Test HRTest0712* …`, leads/activities already gone → inert):**
  - persons: `81294, 81295, 81296, 81297, 81298, 81299, 81300, 81301, 81302, 81303`
  - orgs: `20920, 20921, 20922, 20923, 20924, 20925, 20926, 20927, 20928, 20929`
- **Test double `NNOVii5ImjFKDSM0`** (`WF-1 TEST DOUBLE HRTest0712R2`) — **left published at the owner's request**; its webhook `hr-test-hrtest0712r2-e89986b7` is live until torn down. To remove later: `python wf1_n8n_release_runner.py teardown --delete --apply --state wf1-release-evidence/test-double-state-HRTest0712R2.json`. (Run-1 double `q35d4IvWttJZDiyP` was already deleted.)

---

## 8. Reminders / hand-off

**For Nik**
- **Rotate the webhook secret / n8n API key / Pipedrive token** — the webhook path/token is still in the export, and the n8n + Pipedrive credentials were shared in chat this session; treat all as exposed.
- **After rotation, re-export the api-payload.** The current `WF-1 HeyReach Receiver - W1.0.1 api-payload.json` embeds the OLD webhook path; deploying it after rotation would restore the old path. Regenerate the payload from the rotated workflow before any future deploy.
- WF-1 stays **inactive**; only Nik activates it manually after green live evidence.
- **Clear WF-1 pinData** (Public API can't; re-import the rotated workflow via the editor, or unpin manually) — §7.3.
- **Delete 20 leftover `HR Test` records** the token couldn't (403; full list in §7.4.1): persons `81294–81303`, orgs `20920–20929`. Use an admin token / the Pipedrive UI. Their leads/activities are already deleted.

**Pre-warn Melisa** before the live suite: `HR Test` reply leads will get the `Responded` label → her production Zapier will ping her. Chosen mitigation: one-line heads-up (do not touch her Zap).

**Melisa questions pending (5 business + 3 operational):**
1. Should `Replied to invite` ever re-transition to `Replied` once a follow-up is later sent? (ranks are equal by design today — no re-transition.)
2. Is `message_sent` always the first follow-up, or can it be an initial direct message / invite note? (affects the F9 discriminator.)
3. `channel_id` / source semantics for source-aware Lead selection when a person has multiple active leads (Q6).
4. `Cold Outreach` Person-level source field — exact Pipedrive field key + option ID.
5. Existing-Person enrichment: first-campaign (set-once) vs last-campaign (overwrite) vs both.
6. (ops) Slack destination at cutover — keep `niks-channel` or move to a shared GTM channel (CONFIG one-liner + `/invite` bot).
7. (ops) Fate of Melisa's Zapier at cutover (keep vs replace with native task automation).
8. (ops) Durable dedupe (Postgres event ledger) vs accept staticData residual concurrency risk.

**Out of scope (unchanged from W1.0R queue):** person-level Cold Outreach, existing-person enrichment, `/sales/` identity, upsert-on-reply, campaign-aware lead provenance, durable Postgres dedupe.
