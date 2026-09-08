# Gaps & Questions — for the Stefan / Melisa call

Everything below is NOT API-discoverable (or returned negative) and must be answered by humans.
Each is phrased as a concrete question. Grouped by system.

## A. Smartlead → downstream (BIGGEST gap — verified-negative)
The API shows **Smartlead has zero native webhook subscriptions** on all 114 campaigns, and no
account-level webhook endpoint. Yet replies get categorized and (some) reach Pipedrive. So:
1. **How do Smartlead replies leave Smartlead?** A Make.com "Smartlead" module polling the API? A
   Zapier Smartlead trigger? Smartlead's built-in native integration (not exposed under
   `/campaigns/{id}/webhooks`)? Something else?
2. **Where does the OpenAI reply categorization run?** Inside a Make scenario, a Zap, or a standalone
   script? What model/prompt, and does it write the category back into Smartlead or only forward?
3. **Which categories are forwarded to Pipedrive, exactly?** Melisa said interested / not_interested /
   information_request. Does **Meeting Request** (positive) also forward? What about **Do Not Contact**?
   (Smartlead has 10 categories; only a subset should create Pipedrive records.)
4. **What are the exact forwarding rules** (category → Pipedrive object created + fields set + owner
   assigned + labels applied)? This is the contract R2/R4 depend on.
5. **415 email accounts vs "Noah's 50-mailbox routing"** — what is the 50-mailbox subset, and what
   routing logic assigns leads to mailboxes? (We see per-campaign assignments 0–95, accounts reused.)

## B. Pipedrive → Make.com (verified link, opaque internals)
6. The single Pipedrive webhook fires **ALL events** (`*:*`) to `hook.eu2.make.com/d7jasa…`.
   **What does that Make scenario do** — routing, enrichment, Slack notifications, ClickUp task
   creation, dedup? How many modules/branches? (Make internals are not API-visible.)
7. **The "4 Zaps"** — what are they, what triggers each, and what do they write? None are visible in
   any API (Zapier is external). Are any still active, or superseded by WF-1 (per the WF-1 incident
   ledger)?
8. **Pipedrive Automations** (native) are **not API-exposed**. Which automations exist, and do any
   write the low-usage custom fields we flagged for cleanup? (Blocks safe field deletion.)
9. **Slava → ClickUp** — what mechanism moves data to ClickUp (Make branch? Zap? manual?), and what
   triggers it?

## C. n8n / Data Tables (critical for Phase 1)
10. **Does the prod n8n instance support Data Tables?** `GET /datatables` returns **404** — the public
    API does not expose them here, so we can't confirm the module/version via API. **What is the prod
    n8n version, and is `N8N_ENABLED_MODULES=data-table` set (n8n ≥ 1.113)?** Please check the UI
    (Data Tables section present?) or run `n8n --version` on the host. *This gates the entire DNC
    ledger storage design.* (Amendment-5 `zz_probe_` is not usable — the API endpoint is absent.)
11. Are the inactive workflows **WF-1-DO NOT USE** and **HeyReach Phase 0 Payload Capture** safe to
    leave, or should they be archived/deleted to avoid confusion?

## D. HeyReach (not independently re-verified this run)
12. Confirm HeyReach's webhook subscription destination is WF-1's `{{WEBHOOK_WF1_HEYREACH_RECEIVER}}`
    (verified from the n8n receiver side; HeyReach-side config not re-pulled this run — can do,
    read-only, next).

## E. Ownership / process
13. Who owns each Make scenario / Zap (for change control before we touch anything)?
14. Confirm the Smartlead **Do Not Contact** category is the intended Phase-2 trigger for the DNC
    ledger (`smartlead_dnc_category_to_ledger`), and where "unsubscribe" is currently honored today.

## Recorded gaps (no question — just documented absence)
- Make.com scenario definitions: opaque (no API inventory performed / out of scope).
- Zapier Zaps: external, not inventoried.
- ClickUp: out of scope this run.
- Smartlead per-reply message content + per-reply category endpoint: **not documented** (checked
  `llms.txt` + leads reference) — blocks observability R2/R3.
