# WF-2 - live API shapes and the four defects they exposed

Recorded read-only against the production Smartlead account on **2026-07-28**. Every Phase-C mock
response is derived from these, so the E-matrix tests recorded reality rather than my assumptions.

## Endpoints, verified

| call | verdict |
|---|---|
| `GET /leads/fetch-categories` | 200 - 10 categories (see `category_map` below) |
| `GET /campaigns` | 200 - 116 campaigns |
| `GET /campaigns/{cid}/leads?offset&limit` | 200 - `{total_leads, data:[{campaign_lead_map_id, lead_category_id, status, created_at, lead:{...}}], offset, limit}` |
| `GET /campaigns/{cid}/leads?email=` | **400 Bad Request** - does not exist |
| `GET /leads?email=` | 200 - **FLAT** lead object + `lead_campaign_data[]` |
| `GET /campaigns/{cid}/leads/{lid}/message-history` | 200 - `{history:[{stats_id, from, to, type, message_id, time, email_body}], from, to}` |

`category_map` (name -> id): Interested 1, Meeting Request 2, Not Interested 3, Do Not Contact 4,
Information Request 5, Out Of Office 6, Wrong Person 7, Uncategorizable by Ai 8,
Sender Originated Bounce 9, No Longer Working There 16598.

Notable: the flat lead object has **no `job_title`** at top level - titles only ever arrive via
`custom_fields`. Real data also carries trailing-space dirt (`"last_name": "Nagle "`), which is
what the canonicalization work is for. `message-history` shares one `stats_id` across the thread
and the observed order is `[SENT, REPLY]`.

## Defects this grounding exposed

All four were live in the Phase-B artifact and all are fixed, each with a static test that fails
against the pre-fix build (see `wf2-discrimination-proof.txt`, mutants 9-14).

**B9 - malformed URLs on 23 of 24 HTTP nodes (most severe).** URLs were concatenated as
`PD + "={{ path }}"`. An n8n expression field carries ONE leading `=`; text outside `{{ }}` is
literal, so the second `=` was welded into the URL:
`https://api.pipedrive.com` + `=` + `/api/v2/persons`. Every Pipedrive and Smartlead call would
have 404'd. The raw template looked plausible, which is why it survived a whole phase - so the new
statics evaluate the template the way n8n does (URL1) instead of eye-balling the string (URL2).

**B7 - no authentication anywhere.** All 24 HTTP nodes sent only `Content-Type` and carried no
credential; every call would 401. Pipedrive is now bound to the same credential production WF-1
uses (`pipedriveApi` / `HnyULgvDdYp0lIkB`). Smartlead and Anthropic have **no credential in the
instance** - enumerated read-only across all 5 workflows, only `pipedriveApi` and `slackApi` exist.
That is a deploy gate, printed by the builder on every run. It bites in SHADOW too, because
`SL Fetch Lead`, `SL Message History` and `LLM Classify` are ungated reads.
`anthropic-version: 2023-06-01` was also missing and is now sent.

**B8/1 - wrong lead-lookup endpoint.** `SL Fetch Lead` used the 400-returning per-campaign form;
now uses `GET /leads?email=`.

**B8/2 - enrichment was silently dead.** `Apply Enrich` resolved `data[0] ?? [0] ?? data ?? {}`,
which yields `{}` against the real flat response - so no SENT event was ever enriched. Now handles
flat, `data[0].lead` and `data[0]`, reads titles from `custom_fields`, and falls back to
`company_url` for website.

**B8/3 - the forward could carry our own email.** `Pick Last Message` took the last history entry;
a follow-up landing after the prospect's reply would make us forward our own outbound. Now anchors
on the last `REPLY`, falling back to the last entry.

## Marker coverage over all 116 live campaigns

Run with the shipped parser (`wf2-marker-coverage.json`):

| bucket | count |
|---|---|
| no marker at all | 67 |
| hypothesis only (no event name) | 36 |
| nurture | 8 |
| unknown marker | 5 |

Unknown markers - `[Credit Unions]` x2, `[Exploratory]`, `[EVENT]`, `[SERP]` - are all on
non-ACTIVE campaigns, so **no ops-warn spam today**.

All **25** `[Events Visiting]` campaigns, including all **4 ACTIVE** ones, are single-bracket
(`[Events Visiting] AI4 2026 - Rune - Catch-alls`). The parser accepts the marker but cannot
extract an event name, so those leads would get Hypothesis + Medium and a **null Event name**.

Recommendation: rename the 4 ACTIVE campaigns to the two-bracket convention
(`[Events Visiting] [AI4 2026] - Rune - Catch-alls`), matching what was already done on the
HeyReach side. A single-bracket fallback in WF-2 alone was deliberately NOT added: WF-1 and WF-2
write the **same** person trio, so a divergent parser would make one person's Event name depend on
which channel touched them last.
