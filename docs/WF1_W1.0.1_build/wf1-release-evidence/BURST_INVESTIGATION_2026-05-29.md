# Investigation — the "LinkedHelper outreach response" burst on old campaigns

**Verdict, up front: it wasn't LinkedHelper, it wasn't Nik, and it wasn't a bug in our workflow. It
was WF-1 doing its normal job on old campaigns, and Zap 274357187 (already killed this morning)
mislabeling WF-1's own writes as "LinkedHelper."**

The burst is not from today or this week — the 7 Slack posts Melisa is asking about all fired
**2026-05-29, 20:15:30–20:19:18 IDT (17:15:30–17:19:18 UTC), a single ~4-minute window, over two
months ago.** Nothing about it needs fixing now; it needs an explanation for Melisa, which this
provides.

## Ground truth per lead

| lead | person | campaign | Slack post (UTC) | changelog write (UTC) | gap |
|---|---|---|---|---|---|
| b2ecfa40-3e8a Person-333362aa | 73743 | eMerge Americas 2026 | 17:08:54.638 | 17:08:29 | 25.6s |
| 13bdaaa0-180b Person-15c42271 | 68269 | Pharma USA 2026 | 17:15:30.374 | 17:15:21 | 9.4s |
| 3fb836e0-1d81 Person-b593f844 | 68412 | Pharma USA 2026 | 17:15:37.548 | 17:15:30 | 7.5s |
| 20473110-34ef Person-91310ef1 | 64786 | ITEXPO 2026 | 17:18:59.071 | 17:18:52 | 7.1s |
| ecd18250-faea Person-a06e7c04 | 62675 | ITEXPO 2026 | 17:19:05.951 | 17:18:57 | 9.0s |
| 47f28490-0130 Person-a9d19c0c | 64763 | ITEXPO 2026 | 17:19:15.774 | 17:19:06 | 9.8s |
| ad38e480-faef Ramanpreet Khinda | 62679 | ITEXPO 2026 | 17:19:18.193 | 17:19:10 | 8.2s |

Every changelog write precedes its Slack post by 7–26 seconds — the identical Pipedrive→Zapier
relay latency proven earlier today for the Jigar duplicate ([[wf1-parallel-automation-clobber]]).
That consistency across 7 independent events, spanning 3 different campaigns, is not coincidence.

## What actually changed, and who did it

Every one of the 7 changes is to Pipedrive field `f016efd8791291c591c1d49440018ab0bd23384d` —
**WF-1's own `stage` custom field** (confirmed unique to WF-1; WF-2 has no such field, and no other
system in this stack writes it). The transitions are exactly reply-processing:

- Person-333362aa: `Accepted` → `Replied`
- Person-15c42271: `Accepted` → `Replied`
- Person-b593f844: `Replied to invite` → `Replied`
- Person-91310ef1, Person-a06e7c04, Person-a9d19c0c, Ramanpreet Khinda: `Follow-up received` → `Replied to 2nd
  follow-up` (an older, more granular stage vocabulary than the current W1.0.13.1 baseline uses —
  consistent with these being touches from an earlier point in WF-1's life, on campaigns that predate
  the current Ai4 focus; not independently version-dated beyond that).

Person-a9d19c0c's and Ramanpreet Khinda's entries also show WF-1's normal enrichment firing in the same
write (position, company, org, LinkedIn URL) — the same fill-if-empty behavior WF-1 does on every
event.

**Every entry: `change_source: "api"`, `change_source_user_agent: "axios/0.27.2"`, `actor_user_id:
16340280` (Melisa Bahonjic's Pipedrive account — the shared service identity our automations write
through, not a human sitting at a keyboard).** `axios` is a Node.js HTTP client; a genuine human edit
through Pipedrive's web app shows `change_source: "app"` with a real browser user-agent string (I
confirmed the contrast directly: person 73743 has a separate, later entry from 2026-06-01, `owner_id`
changed via `change_source: "app"`, Chrome UA — an unrelated human reassignment, not part of this
burst). There is no ambiguity here: these 7 writes came from an API call, not a person.

**Correction to earlier project knowledge:** I had it recorded that Pipedrive exposes no
update-authorship via API for anything except the UI's own changelog view. That was wrong, or at
least incomplete — `/v1/persons/{id}/changelog` and `/v1/persons/{id}/flow` both exist and return
exactly this: field-level history with source, user-agent, and actor. Worth revisiting the earlier
"ghost" clobber diagnosis with this endpoint if it's ever in question again.

## Ruling out the alternatives

- **My own session's work**: trivially clear — I did not exist as a running session on 2026-05-29.
- **Clay, Smartlead, a Pipedrive bulk edit, Slava/Marci manual edits**: none of these would produce
  `axios` + the WF-1-specific `stage` field id. Smartlead and Clay integrations identify themselves
  with their own service user-agents when they write; a bulk edit sets `is_bulk_update_flag: true`
  (false on all 7 entries here); a human edit shows `change_source: "app"` with a browser UA, which
  is exactly what I found instead on the *unrelated* June 1 entry, proving the distinction is real
  and legible in this data.
- **n8n execution logs for WF-1/WF-2/WF-2S**: could not be checked directly — execution retention on
  this instance tops out around ~161 hours (~6.7 days) for WF-2, and nothing close to the 2+ months
  since May 29 survives for any workflow. This is a real, permanent evidentiary gap for events this
  old; the changelog is what closes it instead.

## Was the zap's filter "fire on any person update"?

Not fully characterized, and I want to be precise about what is and isn't shown here. **What's
proven**: this zap fires reliably on WF-1's reply-type `stage` transitions — 7 for 7, on old, long-
dead campaigns where nothing else would plausibly be touching these persons. **What's not proven
here**: whether it would fire identically on WF-1's invite/accept-type stage writes for these same
old campaigns — I don't have a same-day counter-example to check. Earlier today's separate check (on
current Ai4 campaigns) found the sibling zaps' behavior on invite/accept events inconsistent and
partly unexplained ([[wf1-parallel-automation-clobber]]) — so "any person update" is plausible but I
am not asserting it as proven, only that these 7 specific events are conclusively WF-1's own writes,
not LinkedHelper.

## For Nik, to answer Melisa

*The burst of "LinkedHelper outreach response" messages was from 2026-05-29, over two months ago —
not anything from recent work. It's WF-1 (our LinkedIn/HeyReach automation) doing exactly what it's
supposed to do: seven real replies arrived on three old campaigns (eMerge Americas, Pharma USA,
ITEXPO) within a few minutes of each other, and WF-1 correctly updated each person's stage. The
"LinkedHelper" wording is stale — a Zapier automation was listening for Pipedrive person updates and
posting a notification with outdated copy left over from before this pipeline moved to WF-1. Every
one of the 7 posts fired 7–26 seconds after WF-1's own write, on the exact field WF-1 uses and no
other system touches, from an API call under the shared service account, not a person. That specific
Zap was already switched off this morning as part of the same cleanup, for the same reason — it
wasn't reporting LinkedHelper activity, it was echoing our own automation's normal work under a
confusing label. Nothing was wrong then and nothing needs fixing now; it was just a badly-worded
duplicate notification, which is now gone.*
