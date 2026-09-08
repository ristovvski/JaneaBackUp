# DNC BUILD — HeyReach projection mechanism: reoriented probe results

**Status: items 1-2 done. Item 3 PARKED (2026-08-11 update below) — resolves naturally on the
first live paused-lead reply, no dedicated probe needed. Item 4 (verdict) waits on item 3.**

## 2026-08-11 update: item 3 reframed, no reactivation for a probe

HeyReach campaigns came back live on their own (2 real Ai4 2026 campaigns resumed, sender accounts
Rune Jensen/Mario Stalder now active). Nik's fixture lead sits in a *different*, still-paused
campaign (510448, sender Sergey Cujba still inactive) — checked and confirmed, but the owner
explicitly ruled out reactivating that account just for this probe. Instead: item 3 now resolves
the first time ANY lead in a live campaign gets paused (by this project's own future projection
branch, or by the team for any other reason) and that lead replies — that reply landing (or not)
in `/inbox/GetConversationsV2` IS the verdict, zero-cost, no fixture message needed. The HeyReach
projection branch's go/no-go now explicitly inherits this condition (documented in
`PROJECTIONS_PASS_PLAN_2026-08-11.md`).

## 1. Global blocklist/exclusion — does NOT exist, confirmed

Checked HeyReach's own roadmap page directly (an earlier AI-summarized fetch had wrongly reported
this as shipped — corrected by viewing the live page myself): **"Do not contact" list status =
"🛠 Planned"**, requested 2023-06-11, never built. Confirmed independently via a third-party
comprehensive API audit (`heyreach-cli`'s `HEYREACH_API_AUDIT.md`) — no global blocklist/DNC
endpoint exists in the documented OR undocumented API surface.

The per-campaign "Exclude list" feature that DOES exist only prevents leads from **entering** a
campaign at launch/list-import time — it does not touch anyone already enrolled. So this doesn't
apply to already-contacted people, and **RemoveFromCampaign/pause stays in the design** — moving
to item 2.

## 2. Per-lead PAUSE mechanic — found, verified live, scoped correctly

Found `POST /campaign/StopLeadInCampaign` via validation-error probing (empty body → real 400
"lead id and lead URL are invalid", not a 404 — proved the endpoint exists before ever sending real
data). Mapped the exact shape the same way: `{"campaignId": <id>, "leadUrl": "<linkedin url>"}`.
This is not documented anywhere I could find, in this repo or HeyReach's own docs.

**Executed for real** on Nik's fixture lead (`https://www.linkedin.com/in/pii-0e746683`,
confirmed by the owner) in campaign 510448 ("Final test", PAUSED, 70 leads total, Nik's own status
was "Pending"). Captured a full baseline first, then called Stop, then read the full campaign back:

| Check | Before | After |
|---|---|---|
| Campaign status | PAUSED | PAUSED — unchanged |
| Total leads | 70 | 70 — unchanged |
| Nik's lead status | Pending | **Paused** |
| Other 69 leads' status | Pending | Pending — unchanged, all 69 |

Exactly one lead changed, exactly the one targeted. This is the surgical, scoped behavior the
projection mechanism needs — pausing one lead does not touch the campaign or any other lead.

**Reversibility: UNCONFIRMED via API.** Probed ~10 plausible names (`ResumeLeadInCampaign`,
`UnpauseLeadInCampaign`, `RestartLeadInCampaign`, `ReactivateLeadInCampaign`, etc.) — all 404.
Calling `StopLeadInCampaign` again on the already-paused lead is idempotent (200, no error, safe
to retry). Tried `AddLeadsToCampaignV2` on the already-present lead as a possible resume path — it
returned `{addedLeadsCount:0, updatedLeadsCount:0, failedLeadsCount:0}`, inconclusive (likely needs
a fuller request body with `linkedInSenderId` I didn't have handy, not a confirmed "no"). **Nik's
lead is currently left in "Paused" state in campaign 510448** — if a clean resume is needed, it's
worth checking the HeyReach UI directly for a "Resume" action next to his lead (I couldn't find an
API path for it after reasonable probing, but that doesn't rule out a UI-only mechanism).

## 3. Webhook check — CONFOUNDED, not negative (retest needed)

Nik sent a real LinkedIn message to Sergey Cujba's HeyReach-managed account at 1:10 PM local,
2026-08-11. Checked `/inbox/GetConversationsV2` immediately and again ~5 min later — no trace of
it, and the top-of-inbox item was byte-identical both times (most recent conversation still dated
`2026-08-11T05:03:20Z`, hours stale).

Before treating that absence as a real signal, checked `POST /li_account/GetAll` (found via the
same validation-error-probing discipline as `StopLeadInCampaign` — `/linkedinaccount/GetAll` 404'd,
`/li_account/GetAll` worked): **all 4 HeyReach-managed LinkedIn sender accounts — including Sergey
Cujba's — show `isActive: false` and `activeCampaigns: 0` right now.** This is account-wide and
predates anything done today; it lines up with the earlier finding that every HeyReach campaign is
currently PAUSED or FINISHED, none IN_PROGRESS.

**This means the test is confounded, not negative.** If HeyReach isn't actively syncing new
LinkedIn activity for *any* account right now, a message not showing up proves nothing about
whether pause specifically blocks inbound webhooks — the whole pipe may be quiet for an unrelated
reason. Drawing "pause blocks replies" from this would be exactly the kind of false-negative this
project's own standing discipline warns against (a probe that can't tell "broken" from "not
running" isn't evidence either way).

**Needs the owner**: either reactivate at least one HeyReach sender account first (a decision
outside API-only scope — likely needs LinkedIn-side re-auth in the UI), or confirm there's a
different, already-active account/campaign this test can run against instead. Once *something* in
HeyReach is confirmed actively syncing, re-run the same before/after inbox check.

Ground truth for "did HeyReach register an inbound message" is `/inbox/GetConversationsV2` (proven
pattern already used in this repo's `t1_weekend_reply_audit.py`), not any of our own webhook
consumers — same "check the source system, not our own execution logs" discipline as that file's
own stated design. That discipline is exactly what caught the confound above instead of stopping
at "message not found."

## 4. Verdict — still pending, blocked on account reactivation

**Cannot conclude yet.** The mechanism (per-lead pause via `StopLeadInCampaign`) is confirmed real,
scoped correctly, and live-verified. Whether it actually suppresses inbound webhooks is still
unknown — not because the test failed, but because nothing in HeyReach is currently active enough
to run the test meaningfully. Once at least one sender account is reactivated and the same
before/after inbox check is repeated, the verdict resolves to one of:
- **Confirmed working**: candidate projection mechanism = per-lead pause, with resume unconfirmed
  via API (may need a manual UI step).
- **Confirmed blocking replies too**: neither mechanism works — HeyReach DNC enforcement stays
  intake-guard-only at the WF-1/WF-3 layer, which the owner already flagged as an acceptable v1.
