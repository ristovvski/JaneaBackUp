# Make org inventory (READ-ONLY, first use of the Make API token)

Date 2026-07-28. Base `https://eu2.make.com/api/v2`, auth `Authorization: Token ...`.
**GET only - no writes, no toggles, no blueprint edits.** Webhook URLs are treated as secrets and are
redacted here and in the raw artifact (`make-org-inventory-raw.json`); the token lives in the scratchpad
env file only.

## LIVE FINDING FIRST - the "email sent" scenario has been silent since 2026-07-25 10:11
Scenario **8557031** (`New_If new email is sent in SmartLead, create Lead in PipeDrive`) is **active**, its
hook **3819669** is **enabled with queue 0**, DLQ 0 - yet its **last execution is 2026-07-25T10:11:09Z**.
Campaign 3565502 kept sending after that: **61 emails on 07-26 and 162 on 07-27** (plus part of 07-25).
Those sends produced **zero** scenario runs.

| scenario | last run | runs per day (recent) |
|---|---|---|
| 8557031 email-sent -> create Lead | **2026-07-25 10:11** (3 days silent) | 07-23: 58, 07-24: 101, 07-25: 41, **07-26: 0, 07-27: 0, 07-28: 0** |
| 8557478 reply -> responded label | **2026-07-28 09:28 (today)** | still firing normally (43 runs 06-30..07-28) |

So the **reply** path is alive and the **email-sent** path is not. DLQ is empty for both, and the hook queue
is 0, so events were not queued-and-failed - **they never arrived**. That points at the Smartlead side
(webhook for the "email sent" event disabled / unassociated from this campaign / deleted), which is exactly
what the still-blocked `GET /webhooks` on Smartlead would confirm. This also explains part of the 122
missing persons found in the campaign-3565502 coverage pass.

## 1. Organization / teams
| org id | name | zone | teams |
|---|---|---|---|
| 2262681 | Janea Systems, Inc. | eu2.make.com | 1 |

| team id | name |
|---|---|
| **897194** | **Janea Systems Ops** |

**There is no "Outreach infrastructure"-class team** - a single team holds everything (ops, finance,
outreach). Finding for the handover doc: no separation between GTM automation and back-office automation.

## 2. Scenarios - 21 total, EXACTLY TWO active (as expected)
| id | name | active | hook | scheduling | last edit | ops |
|---|---|---|---|---|---|---|
| **8557031** | New_If new email is sent in SmartLead, create Lead in PipeDrive | **YES** | **3819669** | immediately (max 100/min) | 2026-07-01 | 28479 |
| **8557478** | New_If Campaign gets a response, update lead with "responded" label | **YES** | **3819933** | immediately (max 100/min) | 2026-07-03 | 767 |

The other 19 are all `isActive=false`, `isPaused=false`:

| id | name | scheduling | note |
|---|---|---|---|
| 2925596 | If new email is sent in SmartLead, create Lead in PipeDrive | immediately | **v1 twin** of 8557031, hook 1371125 |
| 2925894 | If Campaign gets a response, update lead with "responded" label | immediately | **v1 twin** of 8557478, hook 1371255 |
| 2942831 | Inactive - If LH_connected is filled in, update lead with "connected" label | immediately | hook 1371240 |
| 2943799 | Inactive - If LH_connected is filled in already when outreach is sent... | daily 10:43 | |
| 6181829 | **Update Missing Parametars in Pipedrive** | every 900s | **field-painter-sounding, OFF since 2025-07-08** |
| 6348570 | Autorun Janea AI Clay Table | every 900s | off since 2025-07-18 |
| 4514911 | Sales Conference Duplicate Checker | every 43200s | |
| 4737761 | clickup user id checker (keep it turned off) | every 60s | |
| 4745901 / 4745706 | Integration Microsoft 365 (Outlook) / (Outlook + Excel) | 900s / daily 08:00 | |
| 3277897 | Janea Auto-Forward Automation | immediately | hook 1541476 |
| 2723467 / 2723350 / 2723142 | Memurai QBO invoice / Sub ID / Order ID | immediately | hooks 1286539 / 1286505 / 1286258 |
| 2385827 | Memurai Webform Quote Request Responder | 900s | |
| 2722825 / 2722554 | PO ends in 1 / 2 months notification | daily 14:00 | |
| 2680665 | Schedule Resource Allocation Email to HoED | weekly Fri 08:00 | |
| 2719998 | Send email to MikeW if new SCALE List is created | immediately | hook 1285058 |

**Our "nightly trio painter is NOT a Make scenario" conclusion HOLDS.** Scheduled scenarios exist, but
**every single one is inactive**, and none of them logged a run. There is no active scheduled scenario in
this org, so the nightly Event-name/Hypothesis painter comes from outside Make (Slava's bulk edit or
another tool) - consistent with the earlier forensic verdict.

## 3. Hooks - 17 total, all `enabled=true`
| hook id | name | -> scenario | scenario active | queue |
|---|---|---|---|---|
| **3819669** | **Smartlead webhook v.2** | **8557031** | YES | 0 |
| **3819933** | **Smartlead campaign response webhook v.2** | **8557478** | YES | 0 |
| 1371125 | Smartlead webhook | 2925596 | **no** | 0 |
| 1371255 | Smartlead campaign response webhook | 2925894 | **no** | 0 |
| 1371240 | Pipedrive webhook | 2942831 | **no** | 0 |
| 1541476 | New Auto Forward Webhook | 3277897 | no | 0 |
| 1285058 | Marci ClickUp Connection | 2719998 | no | 0 |
| 1286258 / 1286505 / 1286539 | My Deal webhook (x3) | 2723142 / 2723350 / 2723467 | no | 0 |
| 1139567 | Memurai Quote ClickUp Form | **none** | - | 0 |
| 1286611 | Bamboo time off webhook | **none** | - | 0 |
| 1378975 | **My Person webhook** | **none** | - | 0 |
| 1514535 | Auto Forward Webhook | **none** | - | 0 |
| 2017492 | From PowerAutomate | **none** | - | 0 |
| 3273347 | **Clay webhook** | **none** | - | 0 |
| 3837133 | **My Tasks webhook** | **none** | - | 0 |

Both expected bindings confirmed: **3819669 -> 8557031** and **3819933 -> 8557478**, both enabled, queue 0.

**Findings to flag:**
1. **Three OLD Smartlead/Pipedrive hooks are still ENABLED but point at INACTIVE scenarios** (1371125,
   1371255, 1371240). If Smartlead still holds any v1 URL, those deliveries are accepted and then go
   nowhere. This is a plausible silent-drop path and a cheap thing to clean up.
2. **Seven enabled hooks are orphaned** (`scenarioId=None`), two of them Pipedrive-facing by name
   (`My Person webhook`, `My Tasks webhook`) plus `Clay webhook` and `From PowerAutomate`. Live endpoints
   accepting POSTs into nothing.

## 4. Connections - 14 (the credentials map)
| id | name | app | label | expiry |
|---|---|---|---|---|
| 3557251 | My Pipedrive OAuth connection | `pipedrive-auth` | Pipedrive OAuth | **2026-09-26** |
| 4401140 | My Smart Lead AI connection | `smartleadai` | Smart Lead AI | - |
| 3557016 | My Slack (user) connection | `slack2` | Slack (user) | - |
| 11938895 | My Slack (user) connection - Lilla | `slack2` | Slack (user) | - |
| 4094476 | My Google connection | `google` | Google | - |
| 11962513 | My Google connection - Lilla | `google` | Google | - |
| 3568515 | My Microsoft connection | `azure` | Microsoft | - |
| 6996589 | My Microsoft connection (Lilla) | `azure` | Microsoft | - |
| 3568964 / 5441614 | My Microsoft SMTP/IMAP OAuth connection (x2) | `microsoft-smtp-imap` | Microsoft SMTP/IMAP OAuth | - |
| 3565069 | ChatGPT API connection | `openai-gpt-3` | OpenAI | - |
| 3567841 | My BambooHR OpenID connection | `bamboohr3` | BambooHR OAuth2 | - |
| 4089563 | My ClickUp connection | `clickup2` | ClickUp | - |
| 4133497 | My QuickBooks connection | `quickbooks` | QuickBooks (Legacy) | - |

Notes for the handover doc: **the Pipedrive OAuth connection is the only one with an expiry - 2026-09-26.**
If it lapses, both live scenarios stop writing to Pipedrive. No Sheets connection exists (Google generic
OAuth covers it). Smartlead is a native `smartleadai` connection, not raw HTTP. Duplicated
personal connections (own + "Lilla") for Slack / Google / Microsoft - a person-dependency to note.

## 5. Executions / DLQ baseline (shadow-phase diff baseline)
| scenario | DLQ (dlqCount / allDlqCount) | total operations | last run |
|---|---|---|---|
| 8557031 email-sent | **0 / 0** | 28479 | 2026-07-25 10:11 |
| 8557478 reply | **0 / 0** | 767 | 2026-07-28 09:28 |

`GET /dlqs?teamId=` returns **400** (endpoint wants different params); the counters above come straight
from the scenario objects, which is authoritative enough: **no incomplete executions parked anywhere.**
Log sample: all fetched runs `status=1` (success), `type=auto`; email-sent ~6 ops / ~1.5 s per run,
reply ~19-21 ops / ~9-11 s per run.
Org usage (30 d, sizes only): ~1750-2300 operations/day, ~2.5-3.4 MB data transfer/day.
`GET /analytics/{org}` -> **402 "For Analytics feature upgrade your plan"** - analytics endpoint not
available on this plan; the usage endpoint is the substitute.

## 6. Smartlead side (added 2026-07-28, key now available) - READ-ONLY

**`GET /webhooks` does not exist in the Smartlead API.** `/api/v1/webhooks`, `/api/v1/webhooks/` and
`/api/v1/user/webhooks` all return **404**. Webhooks are only addressable per campaign:
`GET /api/v1/campaigns/{id}/webhooks`. So the originally requested "list ALL webhooks" call is structurally
impossible via the API - a finding in itself for the handover doc.

**All 116 campaigns return `[]` - zero campaign-scoped webhooks.** Verified against raw response bodies
(not a parsing artifact) for both the completed sprint campaign 3565502 and an ACTIVE Ai4 email campaign.

Yet Make scenario 8557478 (reply) **ran today at 09:28**, so a live delivery path exists. Conclusion:
**the webhooks are configured at ACCOUNT/USER level in the Smartlead UI**, which this API version does not
expose. That is the only configuration consistent with "no campaign hooks" + "reply events still arriving".

### Campaign inventory: 116 total - 98 COMPLETED, 11 PAUSED, **4 ACTIVE**, 3 DRAFTED
| id | name | status | updated |
|---|---|---|---|
| 3565502 | `[Sales Sprint] Sales Sprint 2026 - London - Valids` | **COMPLETED** | 2026-07-28 10:30 |
| 3565651 | `[Sales Sprint] Sales Sprint 2026 - London - Catch-alls` | **COMPLETED** | 2026-07-27 22:00 |
| **3686181** | `[Events Visiting] AI4 2026 - Mario - Valids` | **ACTIVE** | 2026-07-28 07:00 |
| **3686184** | `[Events Visiting] AI4 2026 - Mario - Catch-alls` | **ACTIVE** | 2026-07-28 07:00 |
| **3686187** | `[Events Visiting] AI4 2026 - Rune - Valids` | **ACTIVE** | 2026-07-28 07:00 |
| **3686193** | `[Events Visiting] AI4 2026 - Rune - Catch-alls` | **ACTIVE** | 2026-07-28 07:00 |

The 4 active ones were created 2026-07-19, run Mon-Fri 07:00-17:00 America/Los_Angeles, max 10000 leads/day.

**Two consequences:**
1. **The sprint campaign only completed today** (3565502 updated 07-28 10:30), so it really was sending on
   07-26 and 07-27 - which confirms the email-sent scenario gap is real, not an artifact of the campaign
   having ended.
2. **Ai4 2026 now runs on TWO channels in parallel** - LinkedIn (HeyReach -> WF-1) and email
   (Smartlead -> Make). That corrects one point in the rename-migration addendum: the person holding
   `[Events Visiting] AI4 2026 - Valids` (person 51045) is not a stale fill-if-empty leftover but a
   **currently live email-campaign touch** - further justification for having left those 20 flagged persons
   untouched rather than overwriting them to the LinkedIn campaign name.

## Cheapest next confirmations
1. ~~Smartlead `GET /webhooks`~~ - **DONE, and the endpoint does not exist**; all 116 campaigns have zero
   campaign-scoped webhooks, so the live config is account-level and **UI-only**. The remaining check is
   therefore manual: **Smartlead UI -> Settings -> Webhooks** - read the account-level webhook list, its
   event map (is the "email sent"/`EMAIL_SENT` event still enabled?), its target URL (v.2 hook 3819669 vs a
   stale v1 URL), and its enabled flag. That single screen resolves the whole question.
2. Send one test email in a throwaway Smartlead campaign and watch whether 8557031 logs a run - a
   one-minute check that separates "Smartlead stopped sending" from "Make stopped receiving". The 4 ACTIVE
   Ai4 email campaigns make this even cheaper: if they are sending today and 8557031 still logs nothing,
   the account-level "email sent" webhook is off.
3. Retire the three enabled-but-dead Smartlead/Pipedrive hooks and the seven orphans (a toggle, not
   done here - read-only pass).
