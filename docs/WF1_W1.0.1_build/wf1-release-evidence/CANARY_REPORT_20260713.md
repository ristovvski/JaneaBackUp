# WF-1 canary verification — 2026-07-13 (read-only)

Production WF-1 (`2jdjKM2NJr473GdA`) is **ACTIVE**. This verifies the 9 production `mode=webhook` executions since activation (ids 9936–9944). The `mode=manual` runs from 07-06→07-08 are pre-activation build noise, excluded.

## 1. Execution table (webhook mode)

| exec | time (UTC) | event_type | status | Switch out | branch / terminal |
|---|---|---|---|---|---|
| 9936 | 11:40 | campaign_completed | success | 4 | fallback → **NoOp** |
| 9937 | 11:45 | message_reply_received | success | 4 | fallback → **NoOp** |
| 9938 | 11:46 | message_reply_received | success | 4 | fallback → **NoOp** |
| 9939 | 11:49 | message_reply_received | success | **3** | reply → M7 Slack Warn (unknown person) ⚠ misrouted |
| 9940 | 11:51 | every_message_reply_received | success | **4** | fallback → **NoOp** ⚠ misrouted (reply lost) |
| 9941 | 11:58 | connection_request_sent | success | 0 | sent → Create Activity |
| 9942 | 11:59 | connection_request_accepted | success | 1 | accepted → M5 Lead Patch |
| 9943 | 12:01 | every_message_reply_received | success | **4** | fallback → **NoOp** ⚠ misrouted (reply lost) |
| 9944 | 12:07 | every_message_reply_received | success | 3 | reply → M8 Task ✓ |

All 9 executions finished `success`; no `error`/`failed` status, so no WF-ERR alerts expected or found.

## 2. Root-cause of the routing anomalies (the key finding)

Identical `event_type` strings routed **differently** across executions (verified by character codes — byte-identical inputs):
- `every_message_reply_received` → out3 in 9944 but → out4 (NoOp) in 9940 & 9943.
- `message_reply_received` → out3 in 9939 but → out4 (NoOp) in 9937 & 9938.

A static string-equals Switch cannot do this on identical input. Explanation confirmed by diffing the live workflow against the shipped W1.0.1 artifact: **only `Switch.parameters` drifted** (all 88 other nodes + connections + settings still match byte-for-byte), and WF-1's `versionId` changed repeatedly during the window (`050a717c` → `88c5a8cf` → `411564f0`). **The Switch was being edited in the n8n editor while the canary was being fired** — so different fires hit different Switch configs.

Current deployed Switch is **semantically correct** (out0–3 = `$json.event` equals the four branch events; fallback=extra). The only residual diff from the shipped artifact is cosmetic: `renameFallbackOutput: "fallback "` (trailing space) vs `"fallback"`. So the routing is correct *now*, but the canary evidence is **contaminated by mid-run edits** and cannot stand as a clean verification.

## 3. Coverage vs the 6 registered webhooks

| event | fired? | expected route | verdict |
|---|---|---|---|
| connection_request_sent | 1× (9941) | sent branch | **PASS** |
| connection_request_accepted | 1× (9942) | accepted branch | **PASS** |
| message_sent | **0×** | message_sent branch | **NOT FIRED** — test never fired or delivery failed |
| every_message_reply_received | 3× | reply branch | **MIXED** — 9944 PASS; 9940 & 9943 wrongly → NoOp |
| message_reply_received | 3× | NoOp | **MIXED** — 9937/9938 PASS; 9939 wrongly → reply branch |
| campaign_completed | 1× (9936) | NoOp | **PASS** |

## 4. Per-branch assertions

**sent (9941) — PASS.** org `20937` (Test Company Name), person `81504` (Person-5e07d3f5), lead `2c710980-7eb2-11f1-a2e6-dda0d579f035`, activity `40646`. Person Create returned 2xx. **member_id numeric-guard held**: payload `lead.id = "TestId"` (string); the stored member_id custom field on person 81504 is `null` — the guard silently omitted it (had "TestId" reached the numeric Pipedrive field, Create would have 400'd).

**accepted (9942) — PASS.** Resolved the existing person `81504` by email, stage patch + label read-modify-write executed through M5 Lead Patch on lead `2c710980…`, no errors.

**message_sent — NOT TESTED** (0 executions).

**reply (9944) — PASS (mechanics).** Correctly routed to the reply branch. `M7 Reply Context.reply_text = "[voice note]"` (the last `is_reply:true` message was `message_type: Voice` with empty body → placeholder, correct). Critical alert posted **before** the resolver nodes (`Switch → M7 Reply Context → M7 Critical Slack → M7 IF Email Present → …`); posted `message.text` = `:speech_balloon: Reply from Person-5e07d3f5 (CEO at Test @ Test Company Name) … > [voice note] …` with **no `{{`**. Full chain ran to M8 Task; reply activity `40650`, task `40651` created; person stage advanced to **`Replied to invite`** (F9 classifier verified live). 

**reply quote rendering — VERIFIED with real text.** Exec 9939 (misrouted here from `message_reply_received`) carried a real reply `"Oh Hey"`; the critical alert rendered `> Oh Hey` correctly (no `{{`). So the earlier "quote rendering unverified until a real reply" caveat is now cleared — though the person wasn't in Pipedrive yet at 11:49, so it correctly ended at the unknown-person warn.

## 5. Dedupe / staticData

All 9 webhook executions ran past Dedupe (Normalize emitted 1 item each) — **no duplicate press produced a dropped execution**, so the dedupe drop path and cross-execution staticData persistence are **still not evidenced on the live workflow**. (The three `every_message_reply_received` fires were not identical enough — or carried distinct correlation ids/timestamps — to collide.) Persistence remains unproven in production.

## 6. Error scan

No canary execution errored. (Pre-activation `mode=manual` errors 9864/9870/9871/9877/9879/9884/9892–9895 are old build-time runs, not part of the canary.)

## 7. Pipedrive residue (for Nik — do NOT auto-delete; token can't delete persons/orgs)

One synthetic identity, reused across sent/accepted/reply:
- organization `20937` — "Test Company Name"
- person `81504` — "Person-5e07d3f5" (stage now `Replied to invite`, label responded)
- lead `2c710980-7eb2-11f1-a2e6-dda0d579f035`
- activities `40646` (invite sent), `40650` (reply activity), `40651` (Melisa task)

## 8. Verdict — **NO-GO** for live invites (Sergey)

Per-event: sent **PASS**, accepted **PASS**, campaign_completed **PASS**, message_sent **NOT FIRED**, every_message_reply_received **MIXED (fail)**, message_reply_received **MIXED (fail)**.

**NO-GO reasons:**
1. **Real replies were lost to NoOp.** `every_message_reply_received` reached NoOp in 2 of 3 fires — the exact "reply silently dropped" failure the whole reply-alert design exists to prevent.
2. **Wrong event processed as a reply.** `message_reply_received` (should be NoOp) reached the reply branch once.
3. **The live production workflow was being edited during the canary** (Switch drift + versionId churn), so no fire is a trustworthy verification, and WF-1 currently differs from the verified W1.0.1 artifact.
4. **message_sent never fired** — that branch is unverified in production.

**To reach GO:**
1. Stop editing WF-1 in the editor; freeze it. (Optionally re-deploy the clean W1.0.1 Switch to erase even the cosmetic trailing-space drift and re-anchor to the verified artifact.)
2. Confirm the Switch matches the verified artifact (it now does semantically).
3. Re-fire all six webhooks **once each** against the frozen version and confirm deterministic routing — especially **message_sent** (never fired) and **every_message_reply_received → reply** (must never fall to NoOp), and that **message_reply_received / campaign_completed → NoOp**.
4. Ideally one real reply through an already-resolved person to confirm the full reply→CRM→alert chain on a known lead.

The engine itself is sound — when routed correctly (9941/9942/9944) every branch behaved exactly as designed, alerts rendered, and the F9 classifier produced `Replied to invite` live. The blocker is operational (live-editing during test) + a coverage gap (message_sent), not a defect in the W1.0.1 logic.
