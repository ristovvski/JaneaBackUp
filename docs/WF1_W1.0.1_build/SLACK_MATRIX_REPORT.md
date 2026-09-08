# WF-1 W1.0.6 — Final Slack Message Matrix (live, content-asserted)

**Date:** 2026-07-15. **Target:** production WF-1 **W1.0.6** (versionId `717155de-654b-4a9e-b29d-f51465d489a7`, 90 nodes) — **READ-ONLY** (untouched; versionId unchanged at end). All firing on fresh double `ZsM9eizW79ZDBphA` (errorWorkflow `BbrXPABgOaaTJjD6` bound on create — verified, not dropped). No defect found → no deploy.

**Result: 11/11 PASS.** Every Slack-posting path fired and its posted `message.text` asserted verbatim (from the Slack node's execution output).

> Note on two expected representations: Slack stores emoji as shortcodes in `message.text` (`💬`→`:speech_balloon:`, `⚠️`→`:warning:`, `🚨`→`:rotating_light:`; the channel renders them back to the emoji), and n8n appends an `_Automated with this <…|n8n workflow>_` footer link to **every** post. Both accounted for in assertions.

## Matrix
| # | Slack node | case | exec | verdict | posted `message.text` (body; n8n footer omitted) |
|---|---|---|---|---|---|
| S1 | *(silence)* | sent(new,+msg)→accepted | 10003, 10004 | **PASS** | *no post* — zero Slack output from both success executions |
| S2 | M7 Critical Slack | reply, lead exists | 10006 | **PASS** | `:speech_balloon: HR smx-s2 (CTO @ S2 Corp) · SMX · via Sergey Cujba — <…/leads/inbox/4ed7efb0-…\|Open lead> · <…/in/smx-s2\|LinkedIn>` |
| S3 | M7 Critical Slack **+** M7 No Lead Warn | reply, person no lead | 10008 | **PASS** | `:speech_balloon: HR smx-s3 (COO @ S3 Corp) · … — no lead · <…/person/82137\|Open person> · <…\|LinkedIn>` **and** `:warning: WF-1: every_message_reply_received — person resolved but no lead found for person 82137; CRM write skipped (reply alert already sent)` |
| S4 | M7 Slack Warn | reply, unknown person | 10009 | **PASS** | `:speech_balloon: HR smx-s4-unknown (X @ S4 Corp) · … — :warning: not in Pipedrive · <…/in/smx-s4-unknown\|LinkedIn>` — one post, one link (LinkedIn), no Pipedrive link |
| S5 | M5 Slack Warn | accepted, person no lead | 10011 | **PASS** | `:warning: WF-1: connection_request_accepted — person resolved but no lead found for person 82138; write skipped` |
| S6 | M6 Slack Warn | message_sent, person no lead | 10013 | **PASS** | `:warning: WF-1: message_sent — person resolved but no lead found for person 82139; write skipped` (person has stage Invited → **not** message-first) |
| S7 | M6 Message First Warn | message_sent, known person, no stage | 10014 | **PASS** | `:warning: WF-1: message-first flow detected — message_sent for person 82140 (HR SMX S7) with no invite history. Stage semantics may not apply; review campaign type.` — only this post; M6 Activity ran (flow continued); `message_first=true` |
| S8 | M7 Critical Slack (R5) | reply, empty position AND company | 10016 | **PASS** | `:speech_balloon: HR smx-s8 · SMX · via Sergey Cujba — <…/leads/inbox/89b44bb0-…\|Open lead> · <…/in/smx-s8\|LinkedIn>` — **no parenthetical** (no `( @ )`, no `()`) |
| S9 | WF-ERR Slack | **expected-error** garbage payload | 10017→10018 | **PASS** | `:rotating_light: WF-1 error` / `Workflow: WF-1 TEST DOUBLE SLACKMATRIX` / `Failed node: Person Create` / `Error: Bad request - please check your parameters` / `Execution: <https://…/executions/10017>` — all four parts present |
| S10 | *(silence/dedupe)* | exact replay of S2 payload | 10019 | **PASS** | *no post* — ran only `Webhook→Respond→CONFIG→Dedupe`; Dedupe emitted **0 items**; dropped |
| — | Lead Resp Invalid | sent-path malformed lead-search resp | *STATIC* | **PASS** | `=⚠️ WF-1: unexpected lead response shape — stopped` — proper `=` expression, no `{{`, not payload-triggerable (real Pipedrive returns valid shapes) → **STATIC-VERIFIED** |

## Suite-global guards
- **Zero unexpected error executions:** of **16** executions on the double, exactly **1** errored (10017 = S9, the only expected error); the other 15 succeeded. Guard: **PASS**. (Runner hardened: `wf1_n8n_release_runner.py` now fails the whole suite on any `status=error` outside an `--expected-error-tests` allowlist.)
- **No `{{` in any posted text:** **PASS** across all posts (incl. the rendered WF-ERR message — its `{{ }}` evaluate because the field starts with `=`).
- **S1 & S10 silence proven, not assumed:** both produced zero Slack-node outputs; S10's execution trace shows nothing ran past `Dedupe`.

## Dedupe drop evidence (S10)
Replay of S2's exact payload → exec 10019, nodes-run = `[Webhook, Respond to Webhook, CONFIG, Dedupe]`, Dedupe output branch item-count = `[0]`. Distinct exec from S2 (10006). The drop itself proves `staticData` persisted the S2 dedupe key across executions on the double.

## Cleanup / integrity
- Deleted: 7 persons (82135–82141, `is_deleted=true`), 6 orgs (20989–20994), 7 leads, 11 activities. Manual S7 person+lead included.
- Double `ZsM9eizW79ZDBphA` torn down → **0 doubles remain**.
- **Production WF-1 untouched:** `active=true`, 90 nodes, versionId `717155de-654b-4a9e-b29d-f51465d489a7` (unchanged at start and end).
