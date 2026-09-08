# WF-1 "HeyReach Receiver" — System Reference

*Definitive team-facing reference. Assembled from a fresh GET of the live production workflow + the audit repo. Last updated 2026-07-17.*

- **Workflow:** WF-1 "HeyReach Receiver" · n8n id `2jdjKM2NJr473GdA`
- **Live state:** **W1.0.9**, versionId `a1237a60-7d66-4b33-8b2f-25a16dc012b9`, **ACTIVE**, **93 nodes**
- **Error workflow:** `BbrXPABgOaaTJjD6` (WF-ERR Error Handler → posts to Slack on any failed execution)
- **Production webhook path:** `{{WEBHOOK_WF1_HEYREACH_RECEIVER}}`

---

## 1. What it is
WF-1 ingests **HeyReach** LinkedIn-outreach webhooks and maintains the corresponding **Pipedrive** records (person, organization, lead), posts a **Slack** alert on prospect replies, and logs **activities**. It is the single source of truth for HeyReach→Pipedrive sync. It supersedes an earlier swarm of Zapier automations (all now disabled — see Incident ledger): WF-1 covers everything they did, strictly better (union-safe labels, reply alerts, activity logging, message-first detection, error isolation).

Design spine: one webhook entry → `Dedupe` → `Normalize` → `Switch` on `event_type` → one of four branches. Every entity write is guarded; the reply branch posts its alert **before** any CRM write so a downstream failure never silences the human notification.

## 2. Event map
`Switch` routes on the normalized `event` (from `event_type`):

| Switch out | event_type | branch head | purpose |
|---|---|---|---|
| 0 | `connection_request_sent` | `IF Company` (M-sent path) | create/resolve org+person+lead; invite activity; stage→Invited |
| 1 | `connection_request_accepted` | `M5 IF Email Present` | resolve person; stage→Accepted; labels [cold,connected]; connected_at |
| 2 | `message_sent` | `M6 IF Email Present` | our outbound follow-up; message activity; message-first warn if no stage |
| 3 | `every_message_reply_received` | `M7 IF Email Present` | **the reply** — alert + stage→Replied[ to invite] + labels all 3 + reply activity (+ M8 task gate) |
| 4 | *(any other)* | `NoOp` | ignored (e.g. `message_reply_received` is a no-op sibling of the `every_*` event) |

**Classification (F9, in M7 Build):** a reply is `Replied to invite` when `!is_inmail && currentRank < FirstFollowUpRank(3) && no outbound message present`; otherwise `Replied`. InMail always → `Replied`.

## 3. CONFIG reference (Set node `CONFIG`, raw JSON)
| key | value / meaning |
|---|---|
| `fields.stage` | `f016efd8791291c591c1d49440018ab0bd23384d` |
| `fields.member_id` | `010fc51128116e8c73ae2b33fd52fd4537451f2b` (numeric HeyReach lead id) |
| `fields.public_id` | `2339d1c7a7cda05651dff68ff82b2d56b20e241d` (LinkedIn slug) |
| `fields.li_url` | `66f0af69bec838dc3f90bb3f16c7d6087d8dbb20` ("lh_linkedin_profile_url" — person search key) |
| `fields.company` | `5a282f55e910cceeb960969460b8409b4c10d623` |
| `fields.position` | `ab15ebd797c66ac010e47e543b7ec0226694d12b` |
| `fields.campaign` | `86157bb49563191c17b4dc62580525f84417524c` |
| `fields.summary` | `f2a9a07d15d2890e45add72d8e86c76dcf080e51` |
| `fields.connected_at` | `b03b86666936a46f063dfff6a922ef884fdefac4` (date) |
| `fields.conversation` | `f5c577e4f48daff068e577105897f5f44fb0072f` |
| `fields.source` | `6070ae31f09228f95048b0f68982b1cd4d3a684a` (person Source enum) |
| `fields.person_location` | `db219a0b68aa164d0aed1f7791687c5ae788b7ae` ("LinkedIn Location", varchar) — **W1.0.8** |
| `org_website_field` | `website` (standard org field) — **W1.0.8** |
| `labels.cold / connected / responded` | `a6d359b0-…` / `ca698a50-…` / `c9d4b550-…` (lead label uuids) |
| `ourLabels` | the three milestone label ids above |
| `stageRank` | Invited 1, Accepted 2, First follow-up sent 3, Replied to invite 4, Replied 4 |
| `source_value` | `446` (Cold Outreach enum option) |
| `melisa_user_id` | `16340280` (lead/activity owner) |
| `activity_type_msg` | `linkedin_messaging` |
| `lead_channel` / `lead_channel_id_value` | `578` / `HeyReach` |
| `slack_channel` | `C0B8GCVNR5W` (niks-channel) — **change the alert channel here** |
| `pipedrive_base` | `https://janeasystems.pipedrive.com` |
| `create_assignment_task` | **`false`** — our M8 assignment task is OFF (Melisa's automation owns tasks). Flip to re-enable in W1.1. |

## 4. Proven invariants (enforced by static tests + live acceptance)
- **Union labels (W1.0.7) + event-truth (W1.0.9):** M5/M7 Labels Compute write `union(existing, targetSet)` — **never removes**, foreign-label-safe; `M{5,7} IF Labels Changed` skip empty PATCHes. `effectiveRank = max(currentRank, incomingRank)`. **Event-truth targetSets differ by node:** `M7` (reply) contributes **{cold, responded} only — a reply NEVER implies `connected`**; `M5` (accepted) contributes **{cold, connected}**. So `connected` means an *actual accepted connection*, never a reply. Union preserves any pre-existing `connected` (from a real earlier accept). Net end-states: reply-without-accept → `[cold, responded]`; sent→accepted→reply → all three; reply→late-accept → `[cold, responded]` then `[cold, connected, responded]`.
- **Forward-only stage:** stage never downgrades (rank-gated in every patch builder).
- **Fill-if-empty enrichment (R2):** existing persons get blank fields filled, non-empty never overwritten (company/position/campaign/li_url/public_id/member_id/**location**).
- **Create-only:** person Source (446) and org `website` are set on create only.
- **Alert-before-writes (F10):** M7 Critical Slack posts before any reply-branch CRM write (continue-on-fail) — a write failure never suppresses the human alert.
- **Empty-value hygiene:** empty custom fields stripped (R4); empty activity `note` omitted (W1.0.6, avoids Pipedrive 400); empty `( @ )` parenthetical omitted (R5).
- **Dedupe:** import-free deterministic key over correlation_id+conversation_id+event (F11); duplicate deliveries drop with zero downstream.
- **Verified link formats (W1.0.5):** every Pipedrive URL is `/leads/inbox/{uuid}` (lead) or `/person/{int}` (no-lead fallback); no `/search?term=`.
- **No node fails silently:** all entity-creating POSTs `retryOnFail=false` (F7); errors propagate to WF-ERR.

## 5. Slack message catalog (8 posting nodes)
| node | when | shape |
|---|---|---|
| `M7 Critical Slack` | reply, person found | `💬 {name}{( pos @ co)} · {campaign} · via {sender} — <…/leads/inbox/{id}\|Open lead> · <li\|LinkedIn>` (no-lead → `no lead · <…/person/{id}\|Open person>`) |
| `M7 Slack Warn` | reply, unknown person | `💬 {name}… — ⚠️ not in Pipedrive · <li\|LinkedIn>` (no Pipedrive link) |
| `M7 No Lead Warn` | reply, person but no lead | `⚠️ WF-1: {event} — person resolved but no lead found for person {id}; CRM write skipped (reply alert already sent)` |
| `M5 Slack Warn` | accepted, no lead / unknown | `⚠️ WF-1: {event} — … no lead found … write skipped` |
| `M6 Slack Warn` | message_sent, no lead / unknown | `⚠️ WF-1: message_sent — … no lead found … write skipped` |
| `M6 Message First Warn` | message_sent, known person, no stage | `⚠️ WF-1: message-first flow detected — message_sent for person {id} ({name}) with no invite history…` |
| `Lead Resp Invalid` | sent path, malformed lead-search response | `⚠️ WF-1: unexpected lead response shape — stopped` (static; not payload-triggerable) |
| `WF-ERR Slack` (error wf) | any execution error | `🚨 WF-1 error / Workflow / Failed node / Error / Execution:<url>` |
Notes: emoji are stored by Slack as shortcodes (`:speech_balloon:` etc.); every post carries an n8n "_Automated with this…_" footer link. Success paths (sent, accepted) are **silent** by design.

## 6. Lifecycle table — "what happens when" (16 scenarios, live-verified end states)
| scenario | end state |
|---|---|
| invite sent, WITH note | Invited; org+website; lead [cold]; invite activity w/ note; silent |
| invite sent, NO note | as above, invite activity w/o note; exec green |
| sent → accepted | Accepted; [cold, connected]; connected_at; silent |
| sent → accepted → reply | Replied to invite; all 3 labels; 💬 Open-lead alert; reply activity; Melisa handover task; our task OFF |
| reply WITHOUT accepting | Replied to invite; **[cold, responded]** — NO `connected` (event-truth W1.0.9: connect never implied by a reply); alert; reply activity |
| reply BEFORE accepted (out-of-order) | after reply **[cold, responded]**; after the late accept **[cold, connected, responded]** + connected_at; stage stays Replied to invite (forward-only) |
| sent → accepted → message_sent → reply | Replied; message + reply activities distinct; all 3 |
| message-first (no invite ever) | message-first warn; flow continues |
| multi-message burst (2+ trailing replies) | ONE reply activity, note = all lines joined oldest→newest; alert = last line only |
| second reply next day | 2nd reply activity appended; stage stays; no new transition/our-task; alert re-posts |
| InMail reply (no connection) | classified `Replied`; alert w/o "InMail" marker; activity written |
| duplicate delivery | dropped at Dedupe; zero posts/writes |
| sparse profile (no company/pos/loc) | person created (blanks omitted); **no org**; lead created; alert has no parenthetical |
| prospect already in CRM, no lead | existing person resolved (no dup); lead created; blanks fill, non-empty preserved |
| unknown person replies | one "not in Pipedrive" line, LinkedIn only; zero CRM writes |
| lead manually deleted, then reply | 💬 Open-person fallback + no-lead ops warn; stage advances; zero lead writes |

## 7. Ops runbook
- **Deploy protocol (active prod):** backup GET → `POST /deactivate` → `PUT /workflows/{id}` (send only `name,nodes,connections,settings`; prune settings to the API-writable allowlist) → `POST /activate` → node-level verify (diff live vs artifact → "DIFFS none"). Always deterministic patcher + static tests + fresh-double live suite first.
- **CONFIG flags:** `create_assignment_task` (false = our task off; flip true to re-enable in W1.1). All field keys/labels/ranks live in CONFIG — no hardcoding elsewhere.
- **Move the alert channel:** set `CONFIG.slack_channel` to the new channel id (one-liner PUT) **and** `/invite` the n8n Slack bot to that channel. No node rewiring.
- **Key rotation order:** regenerate Pipedrive key → update the n8n Pipedrive credential → smoke-test (GET /users/me 200) → deploy nothing. (n8n & our scripts read the token from env/credential.)
- **403 on lead PATCH:** Pipedrive rejects a **combined** `is_archived` + `label_ids` PATCH → **split into two PATCH calls** (unarchive first, then labels).
- **Melisa handover dependency:** Melisa's Pipedrive automation "Assign this lead to a sales exec!" creates a `handover`-type activity on the `responded` label. It is the **sole task source** (our M8 task is off). Keep it ON. It only READS labels.
- **Test doubles:** clone the api-payload to a new workflow with a fresh webhook path, bind `settings.errorWorkflow = BbrXPABgOaaTJjD6`, fire synthetics, then teardown (delete workflow purges its executions). Always end with 0 doubles and assert prod versionId unchanged.

## 8. Release ledger (W1.0 → W1.0.8)
| release | summary |
|---|---|
| baseline → F1–F13 | contract alignment, lead-selection unification, effective-rank labels, guarded writes, retries off, reply activity, alert-before-writes, Dedupe crypto-free, Slack escaping, F12.1 evaluate-alert fix, F13 Code-built bodies (omit null org_id) |
| R1–R6 | person Source=446 create-only; fill-if-empty enrichment; message-first warn; strip empty custom fields; alert cosmetics; regression suite |
| W1.0.4 | compact reply alert + Pipedrive deep link; alert built in M7 Build; CONFIG.pipedrive_base |
| W1.0.5 | verified link formats (`/leads/inbox/`, `/person/`); removed `/search?term=` |
| W1.0.6 | omit empty activity `note` (fixes Pipedrive v2 400 "note too short" on no-message invites) |
| W1.0.7 | **cumulative union labels** + skip-empty-PATCH gates; **assignment-task kill-switch** (`create_assignment_task=false`, M8 Task retained) |
| W1.0.8 | org `website`←company_url (create-only); person LinkedIn Location←lead.location (create + fill-if-empty); multi-reply `reply_note` (all trailing replies joined) |
| W1.0.9 | **event-truth labels** — M7 (reply) targetSet drops the rank≥2 `connected` push → reply contributes `[cold, responded]` only; `connected` now set solely by an actual accepted (M5). Union/skip-PATCH/Create Lead `[cold]` untouched; no retro-removal of existing sets |

Audit repo: `WF1_W1.0.3_AUDIT_REPO` (one commit per fix/release, reproducible fixed timestamps); bundles `WF1_W1.0.{1,3,4,5,6,7,8}_AUDIT_REPO.bundle`.

## 9. Incident ledger
- **E1/E2** — Create Lead invalid JSON when org null (inline template) → fixed by F13 (Code-built body omits org_id).
- **Empty-string custom fields → Pipedrive 400** → R4 strip.
- **Empty activity note → 400** ("note too short") on no-message invites → W1.0.6 omit-empty-note.
- **F12.1** — critical Slack posted literal `{{ }}` (missing `=` prefix) → fixed; evaluators now assert posted `message.text`.
- **👻 THE GHOST (label-clobber) — FINAL, CORRECTED ATTRIBUTION:** Leads intermittently lost `responded` (reverted to `[cold, connected]`) seconds-to-minutes after WF-1's correct reply write (victims incl. Kamil, Evamarija, matrix L6). **Root cause: a swarm of FIVE label-writing Zaps under _Marci Csomor_ (marcell@janeasystems.com), her Pipedrive connection — NOT Nik's account.** Zap ids: `274354645` ([Cold] on sent), `274357463` + `274316027` ([Connected,Cold] on accepted), `274357187` ([Responded,Connected,Cold] on reply — published v8 wrote WITHOUT Responded; the draft adding it was never published), `274318213` (saved-filter → [Connected,Cold] — the prime +16–35s responded-wiper). All write **absolute label sets (replace semantics)**; racing each other explains the intermittency and the D2 5-minute false-negative. **Corrections to earlier findings:** (a) the "under account `25112064`" inference was WRONG — that read the lead `creator_id`, which is *ours* because WF-1 creates the leads; Pipedrive does not expose per-update authorship via API (only the UI changelog does). (b) The Pipedrive key rotation was **irrelevant** to the ghost (their token, not ours) — kept as hygiene only. **Resolution:** Nik/Marci disabled all five Zaps 2026-07-17; verified by a 15-minute production control shot (L6-class, out-of-order) — clobber absent. Evamarija's lead was repaired (unarchived + responded union-added + reply activity note fixed). **Lessons:** intermittent multi-writer swarms need **long** traps (a 5-min single-lead trap gives false-negatives); `creator_id` ≠ update-author.

## 10. W1.1+ backlog (parked)
- **Provenance / ownership** of HeyReach leads vs other sources (was the Q0/B6 item).
- **Auto-assign** — flip `create_assignment_task=true` and finish the M8 assignment task (replacing/coexisting with Melisa's handover — decide ownership).
- **member_id resolver + the two-Lule merge** — dedupe persons sharing a LinkedIn member id.
- **Alert channel move** — `CONFIG.slack_channel` + bot `/invite` when the team picks the channel.
- **Existing-org website enrichment** — fill-if-empty org `website` on resolve (W1.0.8 shipped create-only only).
- **1373 sales-URL conversion** — normalize `/sales/lead/…` (Sales Navigator) profile URLs to public `/in/…` form.
- **Zapier org hygiene** — inventory/retire the remaining Zap org and any old-token consumers (Clay HTTP columns / Trigify logging / test scripts) now that WF-1 is authoritative.
