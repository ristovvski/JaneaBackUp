# WF-2 shadow diff - last 2h

Window start (UTC): `2026-07-29T05:59:00.605052+00:00`

WF-2 executions in window: **8**
Leads with intended actions: **4**
LLM Classify invocations: **0** (expected 0 - classify_enabled=false)

## Ops warnings

| warn | count |
|---|---|
| Ops Warn No Lead | 5 |
| Ops Warn Event Alias | 2 |
| Ops Warn Unknown Event | 2 |
| Ops Warn Bad Secret | 1 |

`Ops Warn Unknown Inbox` is the signal for the `from_email` question: a non-zero count means real replies are not carrying our sending inbox, and the campaign-based fallback resolver should be wired.

## Smartlead link form (given vs constructed)

observed: **2** · payload-supplied links: **2** · form mismatches: **1**

- `pii-ef1d7dcd@example.invalid` given `https://app.smartlead.ai/app/master-inbox?leadMap=123` vs constructed leadMap=`1221`

## Make (the incumbent) in the same window

- SENT -> create lead: **UNAVAILABLE** (HTTP 403) - not treated as zero activity
- REPLIED -> responded label: **UNAVAILABLE** (HTTP 403) - not treated as zero activity

## Per-lead comparison

| campaign | lead | WF-2 intended | Pipedrive now | SL category | gating |
|---|---|---|---|---|---|
| 100 | pii-ef1d7dcd@example.invalid | Reply Alert | person=None leads=- | None | compare |
| 101 | pii-ef1d7dcd@example.invalid | Lead Labels Union (shared body: also U Lead DNC Label); Reply Activity; Reply Alert; SL Category; SL Forward Email | person=None leads=- | None | native-gated (Interested) |
| 102 | pii-ef1d7dcd@example.invalid | Lead Labels Union (shared body: also U Lead DNC Label); Reply Activity; Reply Alert; SL Category; SL Forward Email | person=None leads=- | None | native-gated (Interested) |
| 103 | pii-ef1d7dcd@example.invalid | Lead Labels Union (shared body: also U Lead DNC Label); Reply Activity; Reply Alert; SL Category; SL Forward Email | person=None leads=- | None | native-gated (Interested) |

`WF-2 intended` lists Shadow Log entries only: in shadow mode WF-2 writes NOTHING, so `Pipedrive now` reflects Make plus any cohabiting Zap - that is the baseline being compared, not WF-2's output.
