# AS-IS Infrastructure Map (verified 2026-07-23)

Method: **READ-ONLY** GET/list across Smartlead, Pipedrive, n8n (auth from env; secrets never
persisted). Raw evidence: `discovery_raw.json`. Confidence tags: **VERIFIED (API)** / **REPORTED
(calls only)** / **UNKNOWN**. Zero writes; AI4 untouched.

## Systems inventory (VERIFIED)

### Smartlead  (base `server.smartlead.ai/api/v1`, api_key query auth)
- **114 campaigns** — ACTIVE **6**, PAUSED 11, DRAFTED 3, COMPLETED 94. Active set = the AI4 event
  campaigns (`[Events Visiting] AI4 2026 - {Rune|Mario} - {Valids|Catch-alls}` …), matching WF-1's
  two-bracket naming contract.
- **415 email accounts** connected. Per-campaign assignment varies 0–95 (accounts are reused across
  campaigns; sum-of-assignments 1875 ≫ 415). ⚠️ email-account records expose SMTP/IMAP **passwords** —
  seen during listing, **deliberately not persisted**.
- **Native webhook subscriptions: ZERO** — every one of the 114 campaigns returns `[]` on
  `GET /campaigns/{id}/webhooks` (HTTP 200), and account-level `/webhooks` is 404. **Smartlead is not
  pushing events via its native webhook API.** (How reply/category data leaves Smartlead is therefore
  NOT via Smartlead-native webhooks → see REPORTED flows.)
- **10 lead categories** (global; no campaign-custom found): Interested⁺, Meeting Request⁺,
  Not Interested⁻, **Do Not Contact⁻**, Information Request⁺, Out Of Office(∅), Wrong Person(∅),
  Uncategorizable by Ai(∅), Sender Originated Bounce(∅), No Longer Working There(∅).
  (`sentiment_type` is lowercase `positive|negative|null`.)

### Pipedrive  (base `janeasystems.pipedrive.com/api/v1`, api_token query auth)
- Custom fields: **person 72 / organization 21 / deal 43 / lead 43** (see `FIELD_AUDIT.md`).
- **Webhooks: 1** → **`https://hook.eu2.make.com/d7jasaes12w1joxg256r3qvqndg4cfpw/`**,
  `event_action=*`, `event_object=*` → **Pipedrive streams ALL events to a Make.com scenario.**
- **44 users**, **83 filters**, **22 lead labels** (incl. WF-1's `1. Cold / 2. Connected /
  3. Responded / 4. Positive Reply / 5. Meeting`, plus `DO NOT CONTACT`, `NOT INTERESTED`,
  `Disqualified`, `Move to Nurture Pipeline`, `POST-CONFERENCE MEETING`, `Quarantine`, `Unprocessed`…).
- **Automations: NOT API-exposed** → UNKNOWN (recorded as gap; not guessed).

### n8n  (prod, public API)
- **5 workflows**:
  | id | name | active | trigger | webhook path |
  |---|---|---|---|---|
  | 2jdjKM2NJr473GdA | WF-1 HeyReach Receiver | **ACTIVE** | webhook | `{{WEBHOOK_WF1_HEYREACH_RECEIVER}}` |
  | BbrXPABgOaaTJjD6 | WF-ERR Error Handler | **ACTIVE** | errorTrigger | — |
  | 5TCZwAZ3xeXQr0vI | WF-0 - Discovery | inactive | manual | — |
  | NNOVii5ImjFKDSM0 | WF-1-DO NOT USE | inactive | webhook | `hr-test-hrtest0712r2-…` |
  | rnPaPoVQNe2SShkc | HeyReach Phase 0 Payload Capture | inactive | webhook | `{{WEBHOOK_HEYREACH_CAPTURE}}` |
- **Only ONE active ingest path: WF-1.** No DNC/observability workflows present (unpublished — expected).
- **`GET /datatables` → 404**: the n8n **public API does not expose Data Tables** on this instance.
  Cannot confirm the data-table *module/version* via API (the Amendment-5 `zz_probe_` is moot here —
  the endpoint is absent, so a probe POST would also 404). **Must be verified in the n8n UI.** ⚠️
  Critical for Phase 1 (see `IMPACT_ON_PHASE1.md`).

## De-facto wiring diagram (cross-reference of discovered destinations)

```
HeyReach ──(webhook)──▶ n8n WF-1 (hr-eGVpz…)        VERIFIED (n8n receiver active; HeyReach-side sub REPORTED)
                          └─▶ Pipedrive (person/org/lead/labels/activities)   VERIFIED (WF-1 known)

Pipedrive ──(webhook *:*)──▶ Make.com (hook.eu2.make.com/d7jasa…)             VERIFIED (API)
                                   └─▶ ??? downstream (ClickUp? Slack? enrichment?)  UNKNOWN

Smartlead ──(NO native webhook)──▶ ???                                        VERIFIED-negative
   replies / AI categories ──▶ (Make? Zapier? OpenAI categorizer?) ──▶ Pipedrive?   REPORTED / UNKNOWN
```

### Flow confidence table
| Flow | Confidence | Evidence |
|---|---|---|
| HeyReach → n8n WF-1 → Pipedrive | **VERIFIED** | WF-1 active, webhook path present; WF-1 system reference |
| Pipedrive → Make.com (all events) | **VERIFIED** | `GET /webhooks` → single Make hook, `*:*` |
| Make.com scenario internals / downstream | **UNKNOWN** | Make not API-inventoried; opaque |
| Smartlead → Make/Zapier/OpenAI categorizer | **REPORTED** | no Smartlead-native webhook exists; mechanism is external (poll/native-integration) |
| Smartlead categories → Pipedrive lead creation | **REPORTED** | only forwardable categories reach Pipedrive (per Melisa) — quantify on call |
| The "4 Zaps" | **REPORTED** | not visible in any API (Zapier is external) |
| Slava → ClickUp | **UNKNOWN** | ClickUp not in scope; no API trace here |
| OpenAI reply categorization location | **UNKNOWN** | not in Smartlead API; likely inside Make/Zapier or a script |

## Notes
- The only VERIFIED automation arteries are **HeyReach→n8n(WF-1)** and **Pipedrive→Make**. Everything
  touching Smartlead replies/categorization/forwarding is **REPORTED or UNKNOWN** and must be pinned
  on the Stefan/Melisa call (`GAPS_AND_QUESTIONS.md`).
- WF-1's fingerprints are all over Pipedrive (fields `lh_campaign_name`, `Medium`, `Marketing
  Hypothesis`, `Event name` at ~99% person usage; labels `1.Cold/2.Connected/3.Responded`).
