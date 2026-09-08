# WF-2 Phase A - discovery report (READ-ONLY). STOP for Nik's review.

Date 2026-07-28. WF-1 versionId asserted **unchanged**: `da23d080-a0e0-4126-81c0-0cca60908435` (95 nodes, active).
No writes anywhere. Make: read-only GETs only. No Smartlead calls after the A0 gate fired.

## A0 - SECRETS GATE: **STOP** (as the task's own rule requires)

`SMARTLEAD_API_KEY` in env is `9f59ef3d-…` - **the leaked blueprint key**. Confirmed with evidence, and the
leak is worse than "pasted in chat": **the key is hardcoded 15 times inside the Make reply blueprint**, in
`api_key=` URL parameters, plus once as the webhook `secret_key`. Anyone with blueprint/export access has it.

**Required before anything else:** create a NEW named key in the Smartlead UI (name it `WF-2 n8n`), put it in
env, and **revoke `9f59ef3d…`** - noting that revoking it will break the live Make scenario until Make's 15
HTTP modules are updated too, so sequence it with Nik: create new key -> WF-2 uses new key -> Make modules
updated to the new key (or to a second dedicated `Make` key) -> revoke the leaked one.

I stopped Smartlead API usage at this gate. A1 and the A3 test-fire are deferred until the named key exists.

## A1 - lead category map: **DEFERRED** (blocked by A0)
One call post-rotation: `GET /lead-categories` -> name->id map. Expected names per the task: the four
forwardable (Interested / Meeting Request / Not Interested / Information Request) + Do Not Contact /
Out Of Office / Wrong Person / No Longer Working There / Sender Originated Bounce. From the campaign CSV
(`lead_category` column) the following values are **observed in production data**: Out Of Office (71),
Sender Originated Bounce (24), No Longer Working There (15), Not Interested (6), Do Not Contact (3),
Wrong Person (3), Meeting Request (2). "Interested" and "Information Request" were not present in that
campaign's 124 categorized replies - they exist in Smartlead's vocabulary but need the API map to get ids.

## A2 - webhook inventory: **ANSWERED** (no new Smartlead calls needed)
- **Smartlead has no global webhook endpoint.** `/api/v1/webhooks`, `/webhooks/`, `/user/webhooks` -> 404.
  Only `GET /api/v1/campaigns/{id}/webhooks` exists.
- **All 116 campaigns return `[]`** - zero campaign-scoped webhooks (verified against raw bodies).
- The Make blueprint reveals the actual registration: the gateway module stores
  **`webhook_id: 151526`** with `secret_key` = the Smartlead API key -> the webhook is registered at
  **account/user level**, which is exactly why the per-campaign API shows nothing.
- Make's gateways: **hook 3819669** -> scenario 8557031 (SENT), **hook 3819933** -> scenario 8557478
  (REPLIED). Both `enabled=true`, queue 0. Untouched.

**D1 implication (needs Nik's decision):** the task specifies creating our webhooks with
`association_type=1` (user level). There is **no documented user-level webhook endpoint** in the Smartlead
public API - only per-campaign. So D1 is either (a) a UI action, or (b) per-campaign registration on the 4
ACTIVE campaigns + a process for new ones, or (c) an undocumented endpoint we'd have to probe. This needs
resolving before D1; it also affects whether WF-2 can be webhook-registered at all without UI access.

## A3 - payload shapes: **PARTIALLY RECOVERED, still UNVERIFIED**
No test-fire possible (A0). But the blueprints show which fields production actually consumes:

| field | used for |
|---|---|
| `to_name`, `to_email` | person name / person resolve (email) |
| `from_email` | **the sending inbox** - the Sheets lookup key for forwarding |
| `campaign_id`, `campaign_name` | lead title + Campaign field + canon parsing |
| `lead_id` | Smartlead lead id (category writeback, message-history, unsubscribe) |
| `lead_data.company_name` | org resolve / person company |
| `lead_data.website` | org website |
| `lead_data.linkedin_profile` | person LinkedIn fields |
| (message-history response) `message_id`, `stats_id` | required by `forward-email` |

**Verdict:** treat every field as optional in Normalize (defensive build), and verify the true envelope
(esp. reply subject/body field names, sequence number, and the SENT-vs-REPLIED discriminator) with one real
event once the named key exists. **Marking A3 UNVERIFIED per the task's own fallback.**

## A4 - how "Do Not Contact" is represented today: **ANSWERED**
**It is a LEAD LABEL**, not a field:
`DO NOT CONTACT` = **`52a7c290-fc73-11f0-ad98-81d4703453f3`** (color dark-gray).
There is **no** DNC person/org/deal custom field (the only match, `campaign_unsubscribed_date`, is a stock
Pipedrive field, unrelated to Silva's practice). -> **Use the lead label.**

Full lead-label inventory (this is what UNION must preserve - Silva's manual labels):
| label | uuid |
|---|---|
| `1. Cold` | a6d359b0-6a45-11ed-ab46-5b95b19fcb18 |
| `2. Connected` | ca698a50-bdfb-11ef-8172-510383583b0e |
| `3. Responded` | c9d4b550-bcf3-11ef-a843-357f91e826ec |
| `4. Positive Reply` | 3198a520-d19e-11ef-b90a-f3c01a30f7ae |
| `5. Meeting` | 35edf580-d19e-11ef-935e-7d712003f1b4 |
| `DO NOT CONTACT` | 52a7c290-fc73-11f0-ad98-81d4703453f3 |
| `NOT INTERESTED` | dfbabc50-ea13-11ef-82c9-bb70b5d42474 |
| `Disqualified` | 98008920-e942-11ef-b360-57187fe024ea |
| `AUTOMATED LEAD NURTURING` | 5f022d10-0f6f-11f0-99e2-d33e09d9138e |
| `PERSONAL NURTURING` | fe5c0fb0-8747-11f1-8af0-61ed9820aa09 |
| `POST-CONFERENCE MEETING` | bdf05500-af64-11f0-aab4-1ba9765661c3 |
| + legacy: Quarantine, Test, website, newsletter, expert, Support, Review, Unprocessed, Standard, Custom | |

**Hard evidence for the union fix:** Make module 133 does `PATCH v1/leads/{id}` with an **absolute**
`label_ids: [1.Cold, 2.Connected, 3.Responded]` - it overwrites everything else on every reply. That is the
silent bug WF-2's union model fixes, now documented from the blueprint itself.

## A5 - inbox->owner map: **PARTIALLY RECOVERED, mapping still a STOP item**
Sheets is **not readable from this container**: no Google credential in env, and anonymous CSV export fails
TLS certificate validation here (I will not disable certificate verification).

Recovered without Sheets access:
- **Sheet config (from the blueprint):** spreadsheetId `1vrEutNXwQ1_avO7Xq2tAJKqHSqfpK4Ai8ORCDs2yGcE`,
  tab **`Janea All Inboxes (1.15.2025)`**, headers `A1:CZ1`, lookup filter **column A equals
  `{{1.from_email}}`** (text:equal:ci). So column A = the sending inbox address.
- **The 14 forward recipients (the de-facto fallback map), from the blueprint's forward router:**
  toby@, andreas@, mario@, mirza@, **melisa@ (twice - routes 5 and 7)**, can@, bill.sanders@,
  benedetto.proietti@, **sergey@ / james@ / rune@ / chrissy@ (all four with a TRAILING SPACE in the
  blueprint)**, noah@ - all `@janeasystems.com`.
- **The 10 inboxes actually used by sprint campaign 3565502** (from its CSV, `email_account`):
  `pii-661b267e@example.invalid`, `pii-d5596b0e@example.invalid`, `pii-db03c3aa@example.invalid`, `pii-c1d5596e@example.invalid`,
  `pii-d4181568@example.invalid`, `pii-e1200ff3@example.invalid`, `pii-a0babd5e@example.invalid`,
  `pii-78094590@example.invalid`, `pii-0637c702@example.invalid`, `pii-5984be6c@example.invalid` (~220 sends each).
  Note: for that campaign every inbox is Toby's, so its forwards all resolve to one owner.

**What is still missing: the inbox -> owner pairing** for all other campaigns. Cheapest fix for Nik: export
the sheet tab to CSV into `Downloads` (same as the other CSVs) or share it read-only with a service account.
Two data-quality notes to fix at the same time: the trailing spaces on 4 recipient addresses, and the
duplicated melisa@ route.

## A6 - field-hash confirmation: **ANSWERED, 17/17 exist**
| entity | prefix | actual name | key | type |
|---|---|---|---|---|
| person | 0b72db8f | Title | 0b72db8f36929631afc7c449de2914c3580df7ca | varchar |
| person | ab15ebd7 | lh_current_position | ab15ebd797c66ac010e47e543b7ec0226694d12b | text |
| person | f8edcb01 | LinkedIn Title | f8edcb0113a9fe4082b4116a4b3d8e085b971eed | text |
| person | 5a282f55 | lh_current_company | 5a282f55e910cceeb960969460b8409b4c10d623 | text |
| person | 66f0af69 | lh_linkedin_profile_url | 66f0af69bec838dc3f90bb3f16c7d6087d8dbb20 | text |
| person | b59a7d0a | LinkedIn Profile | b59a7d0af178f3149381efd9a8476370b19ca3b5 | varchar |
| person | db219a0b | LinkedIn Location | db219a0b68aa164d0aed1f7791687c5ae788b7ae | varchar |
| person | 86157bb4 | lh_campaign_name | 86157bb49563191c17b4dc62580525f84417524c | text |
| person | 8bdae1a9 | Marketing Hypothesis | 8bdae1a91272e92b335e9e99f668cde659b6daae | varchar |
| person | 961698945 | Medium | 961698945b0329b367da11916a94f10ff7ba71fe | varchar |
| person | ab5540d2 | Event name | ab5540d2ca45905dfb1434c0fe4971cc5790de3f | varchar |
| person | 6070ae31 | Source (enum) | 6070ae31f09228f95048b0f68982b1cd4d3a684a | enum, 446='Cold Outreach' |
| org | 2064369b | Website | 2064369b47d625221e85093240d25b42110d8da4 | text |
| org | 7ef47bd7 | Website URL | 7ef47bd78dae7bbf48da9d837c3fbda079a44de9 | varchar |
| org | c8c70fc5 | lh_website | c8c70fc525238b1c709857ea40f4d60cd2575d37 | text |
| lead | 1cd81dfc | **Campaign** | 1cd81dfcac8a5583935ff4b60e284d0e580db0b6 | varchar |
| lead | c7e30576 | **Opportunity type** | c7e3057693b6f16fbe40bba2c439d38f8ceb1d84 | enum, **480='New opportunity/New PO'** |

`c7e30576=480` now has semantics: Opportunity type = "New opportunity/New PO". Confirmed.

**Open item - which org field is "the LinkedIn-profile field"?** Three candidates exist and the locked
decision does not name a key: `linkedin` (stock, 'LinkedIn profile', varchar), `b4a6ae4b5bdff864a57ebd432f55ec247ff96f0a`
('LinkedIn URL', text), `ed932dfc4870dcd72fa7b4eadb67da38d169299b` ('lh_linkedin_profile_url', text).
Similarly four website-ish org fields exist (`website` stock, plus the three above). **Nik must pick**, or I
mirror Make: the blueprint writes website into **both** `2064369b` and `7ef47bd7`. I will not guess.

## Additional blockers found (not in the task's A-list)
1. **`wf2-architecture.md` does not exist on this machine.** Phases B/C/D are specified as "topology per
   architecture SS1-SS6", "CONFIG per SS6", "E-matrix SS10 E1-E12 verbatim". Without it I would be inventing
   the spec rather than executing it. **This blocks B/C/D.**
2. **`gtm-automation-master-map.md` does not exist** (deliverables ask me to update it).
3. **The Make blueprints were NOT in evidence** as the task assumed - so I recovered them myself via
   read-only `GET /scenarios/{id}/blueprint` and saved them (secret-redacted) as
   `make-blueprint-8557031-sent-create-lead.json` and `make-blueprint-8557478-reply-responded.json`.
   **Caveat: the blueprint export does NOT serialize router filters.** Verified by internal control - the
   SENT router (which must branch person-exists vs not) also exports zero filters, as do all four routers.
   So the recovered parity spec gives modules, endpoints, field mappings, label sets and Slack templates,
   but **not the branch conditions**. Those must come from the architecture doc or a UI walkthrough.

## Recovered parity spec (bonus, now in evidence)
- **SENT scenario (8557031), 8 modules:** CustomWebHook(3819669) -> regexp:Parser -> smartleadai:fetchLeadByEmail
  -> pipedrive:searchPersons -> router{ CreatePersonV2 | createLead | createLead }.
- **REPLIED scenario (8557478), 42 modules:** CustomWebHook(3819933) -> router{ searchLeads -> getLead ->
  MakeAPICall(PATCH labels, absolute) -> slack:CreateMessage | searchPersons -> searchOrganizations ->
  GetPerson -> UpdatePerson | searchOrganizations -> router{ getOrg/updateOrg | searchLeads/getLead/updateLead
  | createOrg | searchLeads/getLead/updateLead } | google-sheets:filterRows -> http GET message-history ->
  ParseJSON -> SetVariable(stats_id) -> SetVariable(message_id) -> router{ 14x http POST forward-email } |
  slack:CreateMessage }.
- **Slack alert format (parity), channel `C07LTD8UT70`, two variants** - with and without the Pipedrive link:
```
New "Responded" Lead Label in Pipedrive!

Details:
Name: {{to_name}}
Company: {{lead_data.company_name}}
Company website: {{lead_data.website}}
LinkedIn profile: {{lead_data.linkedin_profile}} Email: {{to_email}}
Campaign: {{campaign_name}}

The email address we received the response to: {{from_email}}

Feel free to take a look at this lead in Pipedrive: https://janeasystems.pipedrive.com/leads/inbox/{{lead_id}}
```
  (WF-2's locked format is the WF-1 one-liner + `<0x2709> email`, so this is parity reference, not a target.)
- **Smartlead endpoints in use:** `GET /campaigns/{cid}/leads/{lid}/message-history`,
  `POST /campaigns/{cid}/forward-email` (body: message_id, stats_id, to_emails).
  Note: no category-writeback or unsubscribe call exists in the current Make scenarios - those are **new**
  WF-2 behaviour (Melisa's DNC ask), not parity.

## STOP list for Nik (in priority order)
1. **Create the named `WF-2 n8n` Smartlead key** and plan the rotation/revocation of `9f59ef3d…` together
   with updating Make's 15 hardcoded URL params. (A0 - blocks A1, A3, D1.)
2. **Provide `wf2-architecture.md`** (and `gtm-automation-master-map.md`). Without SS1-SS6/SS6/SS10 I cannot
   execute B/C/D as specified.
3. **Decide the user-level webhook path for D1** - Smartlead's public API has no user-level webhook endpoint.
4. **Export the "Janea All Inboxes" tab to CSV** (or share read-only) for the inbox->owner map.
5. **Pick the org LinkedIn-profile field key** (3 candidates) and confirm which website field(s) to write.
6. Confirm whether the four trailing-space recipient addresses and the duplicated melisa@ route should be
   cleaned as part of the WF-2 map.

Everything above is read-only. WF-1 untouched. Awaiting your word before Phase B.
