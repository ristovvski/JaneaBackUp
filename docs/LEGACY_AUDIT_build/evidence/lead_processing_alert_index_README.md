# #lead-processing alert index

**File:** `lead_processing_alert_index.jsonl` — 1,517 rows, one per unique lead.
**Source:** `DISCOVERY/lead_processing_harvest.jsonl` (1,641 raw #lead-processing messages, 2024-12-19 → 2026-08-05, same harvest reused for the Legacy Systems Audit's Section E). 17 harvest rows skipped: no `lead_uuid` or non-alert message (channel-join notices etc.).

## Shape (one JSON object per line)

| field | meaning |
|---|---|
| `lead_uuid` | Pipedrive lead UUID, parsed from the alert's lead link |
| `first_alert_date` | UTC ISO-8601 timestamp of the **earliest** #lead-processing alert found for this lead |
| `delivery_channel` | always `#lead-processing` — the only channel this harvest covers (see scope note) |
| `era` | which legacy alert template fired (see below) |
| `template` | raw template key |
| `lead_name`, `campaign` | as parsed from the alert text, for human cross-reference |

## Era breakdown

| era | count |
|---|---|
| legacy (Make/Zapier — LinkedHelper bridge) | 1,129 |
| legacy (Make/Zapier — Responded-label notice) | 388 |

## Scope caveat — read before treating this as "was this lead ever alerted?"

**Every row in this index is legacy Make/Zapier-era. There are zero n8n-era (WF-1 M7) alerts in it, because there are zero in the source channel.** WF-1's own M7 Critical Slack reply alert posts to **#niks-channel**, not #lead-processing (confirmed: the 2026-08-04 Person-a644a93a M7 alert fired in #niks-channel, per prior investigation). So:

- A lead **present** in this index got a legacy alert at the given date — that's solid.
- A lead **absent** from this index was **not necessarily un-alerted** — it may have been correctly alerted by the current n8n system in #niks-channel, which this index does not cover.

Using this index to answer "was this ever alerted?" for anything after WF-1 went live requires also checking #niks-channel history, which is out of scope here. This index's real value is narrower and still useful: **it is the complete legacy-era alert record**, i.e. exactly the population the Legacy Systems Audit's Section E gap analysis (108 dark windows, 409 days silent) is about.
