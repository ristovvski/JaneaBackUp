# Access map

Every system the estate touches, what a second operator needs in each, and what that operator can
and cannot diagnose without it. Written for the handover to **Stefan**, who is to get the same
access as Nik **except Pipedrive, by design**.

"Stefan today" records only what is known. Where it says *to confirm*, nobody has checked yet — it
is not an assumption that access exists.

| system | what it is for here | role a second operator needs | Stefan today |
|---|---|---|---|
| **n8n** (cloud) | every workflow, execution, credential, data table | **admin** on the instance (or editor on every project) **plus a personal API key** — every deploy and diagnostic script uses the API | *to confirm* |
| **GitHub** `Nkriv/Janea` (private) | this repository | **write** collaborator. Recommend branch protection on `main` so a second operator works through PRs | being added |
| **Slack** | alerts, digest, telemetry | member of the channels below; **never** posts to `#infra-issues` | *to confirm per channel* |
| **Supabase** | read mirror of the DNC registry (`dnc_registry`, `dnc_domains`) | project **read** access (dashboard / SQL editor) | *to confirm* |
| **HeyReach** | LinkedIn outreach; source of WF-1 events | **UI seat with inbox access** — the blank-reply flow requires opening the conversation itself | *to confirm* |
| **Smartlead** | email outreach; source of WF-2 events | team member with campaign + master-inbox read | *to confirm* |
| **Clay** | enrichment; ICP scoring engine | member of **workspace 332169** (event workbooks) — the usual key is blind to it | *to confirm* |
| **Pipedrive** | the CRM every receiver writes to | read, ideally write | **none — by design** |
| **Make.com** | legacy scenarios, audit only | read | not needed day to day |
| **Zapier** | legacy lead-tagging Zaps (four label-wipers, disabled not deleted) | read | not needed day to day |
| **OpenAI** | WF-2 reply classifier | none — used only through the n8n credential | not needed |

## Slack channels

| channel | id | why | note |
|---|---|---|---|
| morning digest | `C0BTP6VHP1B` | the daily one-screen status | **has exactly one member today (Nik).** Stefan will not see the digest until added. |
| `#alerts` | `C0BTUHSSM3K` | system alarms from WF-1 / WF-2 / WF-ERR | |
| `#lead-processing` | `C07LTD8UT70` | the team's live lead alerts | read; the team is the audience |
| `#niks-channel` | `C0B8GCVNR5W` | ops posts, pre-posts for bulk writes, results | where §9f.2 pre-posts go |
| `#gtm-telemetry` | `C0BQM1X9ZUY` | chunked progress, dry-run summaries | |
| test channel | `C0BFE6KAN8J` | DEV-mode alert target | |
| `#infra-issues` | — | humans only | **read at most; never post** |
| `#agent-inbox` | — | — | **do not read, react or post** |

## What cannot be diagnosed without Pipedrive

Every receiver's output lands in Pipedrive, so without it Stefan sees **what we sent** (request
bodies and responses in n8n execution data) but never **what the CRM now holds** — and several of
this estate's worst incidents lived exactly in that gap, where a write reported success and the
record was wrong.

Specifically, he cannot:

* **verify any write landed** — every post-verify in this repository reads the record back from
  Pipedrive (`3. Responded` set, field 686 = `dnc_active`, activity on the right lead)
* **see other writers** — Melisa's automation, the sprint reply-Zap cohabitant, the four label-wiper
  Zaps. Their changes appear only in Pipedrive; n8n never sees them
* **diagnose ownership** — the "every lead is Melisa's" defect (623 of 722 new leads in 14 days)
* **find duplicates** — the lead-per-campaign rule, the title-prefix fallback, the wrong-person
  bindings, the 73 organizations carrying a LinkedIn URL in a website field
* **tell a deleted lead from a converted one** — a 404 on a lead is usually a lead→deal conversion
* **read activity notes** — the CRM timeline where corrections are annotated
* **run the §9f.2 post-verify** of any batch write, which means he **cannot own a backfill end to end**

What he **can** do without it: every n8n diagnosis (executions, node inputs/outputs, WF-ERR), the
DNC registry via Supabase, the provider side (HeyReach, Smartlead), the digest, statics and deploys
of changes whose verification does not need a CRM read-back.

**Practical consequence:** any change or repair whose acceptance test is a Pipedrive read-back needs
someone with Pipedrive access to run that last step. Plan for that pairing rather than discover it
mid-incident.

## Before access is granted — checklist

- [ ] n8n admin + personal API key issued (keys are per-user; do not share Nik's)
- [ ] added to `C0BTP6VHP1B` (digest) — otherwise the most important morning check is invisible
- [ ] added to `#alerts`, `#lead-processing`, `#niks-channel`, `#gtm-telemetry`
- [ ] HeyReach UI seat with inbox access
- [ ] Supabase project read access
- [ ] Clay workspace 332169
- [ ] GitHub collaborator + `main` protected
- [ ] a local `.env` of his own, built from his own keys — **never a copy of Nik's**
