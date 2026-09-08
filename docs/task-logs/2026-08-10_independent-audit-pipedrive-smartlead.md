# Independent audit — 2026-08-10 (Pipedrive + Smartlead), 00:00Z → 15:45Z

**Auditor session. Read-only. No deploys, no writes, no fixes.** Every number below was re-derived
from Smartlead / Pipedrive / Slack / Make APIs and n8n raw execution data by this session's own
scripts. No other session's grader, reconciler or report was used as evidence — only as a statement
of what was *claimed*.

Evidence files: `scratchpad/a1_census.json`, `a2_pdwrites.json`, `a2b_allleads.json`, `a3_n8n.json`,
`a4_trace.json`, `a5_numbers.json`, `a6_mech.json`, `a7_final_census.json`.

---

## Executive summary

**188 events, 11 accounted, 177 not accounted, 17 anomalies (6 known/expected).**
Three are P0. **Two are actively destroying data right now**: every organic email reply arriving
since 15:10:44Z is destroyed on arrival, and 176 of today's 176 SENT events never reached the CRM at
all. The day's headline claim "zero events lost" is false.

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **P0 — active** | Organic reply `pii-6389984a@example.invalid` destroyed at 15:30:20Z; path still broken | NEW |
| 2 | **P0 — active** | All 176 SENT events invisible; WF-2S reads the *oldest* 500 stats rows; Make's replacement is off | NEW |
| 3 | **P0 — active** | Lead-label wiper: 6 leads today, ≥11 since Aug 5; mechanism identified | known ×2, escalated |
| 4 | High | WF-2 can resolve only 500 of 57,602 leads (0.87%) — 99.13% of replies get no lead writes | NEW |
| 5 | High | Dedupe registers the key *before* the work → a crashed event can never be replayed | NEW |
| 6 | High | 2 reply Slack alerts silently failed (12:37Z, 12:51Z) | known, fix confirmed |
| 7 | High | The new delivery-registry alert gate has never run on a reply — unproven | NEW |
| 8 | Medium | Test fixture live in production incl. an open Handover in Melisa's queue | known |
| 9 | Medium | 4 Pipedrive persons share the fixture email; writes split across two of them | NEW |
| 10 | Medium | WF-2 reply alerts still go to the ops channel; `slack_channel_replies_at_flip` never applied | NEW |
| 11 | Medium | Alarm message bodies pre-render wrong/placeholder text | partly known |
| 12 | Low | Two empty Slack messages posted (13:16:01Z, 14:45:06Z) | NEW |
| 13 | Low | `write_mode` threshold incident was ~45 min on the wire, not ~3 h | claim mismatch |
| 14 | Low | Third-party automation (`pii-0bd328cb@example.invalid`) writes Scan Date fields — the wiper's trigger | NEW |
| 15 | Info | 2 DNC probe subworkflow errors (schema mismatch), inactive workflows | expected |
| 16 | Info | Zero orphan persons; 1 person created today, legitimately | clean |
| 17 | Info | n8n exposes no version-history API — deploy spans reconstructed indirectly | coverage limit |

---

## 1. Event census — Smartlead

**Method.** `/campaigns` → 117 campaigns → `/campaigns/{id}/leads-statistics` for **every** campaign
(not only ACTIVE: a COMPLETED campaign can still receive a reply), paginated `offset`/`limit`.

**Page cap proven, not assumed:** `limit=200` → `HTTP 400 "limit" must be less than or equal to
100`. The walk uses `limit=100` and only marks a campaign complete when the final response carried
`hasMore=false`.

**Walk completeness proof.** Pass 1: 117/117 campaigns terminated on `hasMore=false`, 0 duplicate
`lead_id`s, offsets strictly increasing. Pass 2 (re-walk of all 17 ACTIVE/PAUSED campaigns to close
the window at 15:45Z, because pass 1 took ~11 min and events arrived mid-walk): 17/17 complete.
Pass 2 surfaced **45 events pass 1 could not have seen**, including the lost reply — recorded rather
than hidden.

**Total: 188 events** — 176 SENT · 6 REPLY · 6 FORWARD, in 4 campaigns
(3686187 ×55, 3686184 ×45, 3686181 ×44, 3686193 ×44).

### The 6 replies and 6 forwards

| time (UTC) | type | campaign | SL lead | address |
|---|---|---|---|---|
| 12:36:29 | REPLY | 3686187 | 4306240392 | pii-c61c7d08@example.invalid *(fixture)* |
| 12:37:32 | FORWARD | 3686187 | 4306240392 | *(Make — pre-kill duplicate)* |
| 12:37:39 | FORWARD | 3686187 | 4306240392 | *(WF-2)* |
| 12:50:55 | REPLY | 3686187 | 4306240392 | fixture |
| 12:51:54 | FORWARD | 3686187 | 4306240392 | WF-2 |
| 14:38:22 | REPLY | 3686187 | 4306240392 | fixture |
| 14:39:19 | FORWARD | 3686187 | 4306240392 | WF-2 |
| 14:52:51 | REPLY | 3686187 | 4306240392 | fixture |
| 14:53:55 | FORWARD | 3686187 | 4306240392 | WF-2 |
| 15:03:18 | REPLY | 3686187 | 4306240392 | fixture |
| 15:04:12 | FORWARD | 3686187 | 4306240392 | WF-2 |
| **15:30:20** | **REPLY** | **3686184** | **4214180591** | **pii-6389984a@example.invalid — ORGANIC, NO FORWARD** |

**Five of the six replies are the same synthetic fixture.** The day's entire reply-path validation
ran against one test address in one campaign. The one organic reply of the day was destroyed.

### Per-event fate

| event | n8n execution | Pipedrive now | SL forward | Slack | verdict |
|---|---|---|---|---|---|
| REPLY 12:36:29 | 14913 success | no lead existed yet → person-side only; `Ops Warn No Lead` posted `ok:true` | ✅ 12:37:39 | ❌ `Reply Alert` returned `{"error":"invalid syntax"}` | **partial** — correct behaviour, lost alert |
| REPLY 12:50:55 | 14922 success | lead `72ec85c0` labels union'd; activity 43973 | ✅ 12:51:54 | ❌ same silent failure | **partial** |
| replay 13:16:01.059 | 14927 success | — | none | — | ✅ deduped |
| replay 13:16:01.212 | 14928 success | — | none | — | ✅ deduped |
| REPLY 14:38:22 | 14954 success | activity 43977 | ✅ 14:39:19 | ⛔ gate said `repeat_reply` → no alert | ✅ by design |
| replay 14:45:06 | 14956 success | — | none | — | ✅ deduped |
| REPLY 14:52:51 | 14958 success | activity 43978 | ✅ 14:53:55 | ⛔ `repeat_reply` | ✅ by design |
| REPLY 15:03:18 | 14961 success | labels union'd; activity 43979 | ✅ 15:04:12 | ✅ `ok:true` ts `1786374243.432809` | ✅ green |
| **REPLY 15:30:20** | **14966 ERROR** | **nothing — person 83623 `update_time` still 2026-07-22T11:39:16Z; lead `da6fce30` still `['1. Cold']`** | **none** | only a WF-ERR crash post to Nik's channel | **🔴 LOST** |
| 176 × SENT | **none** | **none** | n/a | n/a | **🔴 177 unaccounted (176 SENT + 1 reply)** |

**Section verdict: FAIL.** 11 of 188 events fully accounted for.

---

## 🔴 P0-1 — the 15:10:44Z deploy destroys every organic reply

```
exec 14966  2026-08-10T15:30:55.830Z → 15:30:59.160Z  status=error
lastNode: Body Reply Alert
ReferenceError: alert_text is not defined [line 26]
  at VmCodeWrapper (evalmachine.<anonymous>:26:29)
event REPLIED · campaign 3686184 · lead 4214180591 · pii-6389984a@example.invalid
subject "RE: Quick hello before AI4?" · received 2026-08-10T15:30:20Z
stats_id 130d87d7-6a6e-48ef-8a4d-bc62b01596ec
```

The `Body Reply Alert` node's source is mangled — the statement that declared `alert_text` was
removed, leaving an orphaned continuation:

```js
23|   const slLink = slUrl ? (' · <' + slUrl + '|Open in Smartlead>') : '';
24|     + ' · via ' + esc(n.sender_inbox) + ' — ' + link + slLink      // ← dangling expression
25|     + ' · ✉️ ' + esc(n.lead.email);
26|   return [{ json: { ...$json, alert_text, ... } }];                // ← ReferenceError
```

Lines 24–25 are a *valid* expression statement, so the workflow deploys clean and only dies at
runtime. `onError` is unset on this node, so the whole execution aborts.

- Introduced by the last deploy of the day: WF-2 `updatedAt = 2026-08-10T15:10:44.061Z`,
  `versionId 45637e70-6845-40e5-866d-c280120e8cef` (the "gate fix · category line removed").
- The fixture reply at 15:04:00 (exec 14961) passed through the same node fine — the break is
  strictly after 15:04 and before 15:30.
- **Everything downstream never ran**: Slack alert, LLM classify, Smartlead category, **the forward
  to the sales owner**, lead labels, reply activity.
- `Respond to Webhook` is the 2nd node, so Smartlead already had its 200. **Smartlead will not retry.**
- Verified on the Smartlead wire: lead 4214180591's history is 4×SENT + 1×REPLY and **no FORWARD**.
- Verified in Pipedrive: person 83623 untouched since 2026-07-22; lead `da6fce30` still `['1. Cold']`,
  `update_time` still `2026-07-21T18:49:07.475Z`. No activity, no handover, no notification to anyone
  but Nik's error channel.

**Every organic reply arriving right now meets the same fate.**

## 🔴 P0-1b — and it cannot be replayed (dedupe registers too early)

`Dedupe` writes the key the moment it decides the event is new, before any work happens:

```js
20| const duplicate = Object.prototype.hasOwnProperty.call(store.wf2_seen, key);
21| if (!duplicate) store.wf2_seen[key] = nowSec;
```

Exec 14966 registered `REPLIED|3686184|4214180591|<epoch-ms>` at 15:30:56 and *then* crashed. When
WF-2R eventually replays that reply it will match → `IF Duplicate` → `NoOp Duplicate` → dropped.
`dedupe_max_age_sec = 172800` (48 h) and WF-2R's `lookback_minutes = 2880` (48 h), so the dedupe
entry outlives the reconciler's reach.

Observed: WF-2R exec 14969 (15:45:00Z) swept campaign **3686181**, not 3686184 —
`max_campaigns_per_cycle: 1`, `__hot_sweep_h: 1.7`. The replay has not happened yet and will be
suppressed when it does.

**This reply is unrecoverable through the automated path.**

## 🔴 P0-2 — 176 SENT events never reached the CRM; the SENT source is structurally blind

WF-2S's `SL Statistics` node calls, with **no `offset` and no `limit` and no pagination**:

```
{{ $('CONFIG').first().json.sl_api }}{{ '/campaigns/' + ($json.campaign_id || 0) + '/statistics' }}
```

Measured on the wire, called exactly as WF-2S calls it:

| campaign | total_stats | rows returned | oldest in page | **newest in page** | rows from today |
|---|---|---|---|---|---|
| 3686181 | 784 | 500 | 2026-07-21T17:20:17 | **2026-07-31T19:09:28** | **0** |
| 3686184 | 633 | 500 | 2026-07-21T17:20:38 | **2026-08-04T19:19:13** | **0** |
| 3686187 | 640 | 500 | 2026-07-21T17:44:07 | **2026-08-06T16:56:56** | **0** |
| 3686193 | 694 | 500 | 2026-07-21T17:43:39 | **2026-08-04T19:21:04** | **0** |
| 3756410 | 16 | 16 | 2026-08-04T21:40:29 | 2026-08-04T21:41:18 | 0 |

The endpoint pages at 500 **ascending by `sent_time`** — an unparameterised read returns the
**oldest** 500 rows. Once a campaign passes 500 sends, its recent sends are permanently outside the
window. `Find New Sends` then discards everything against its 180-minute cutoff:

```
[Find New Sends] {"__idle": true, "considered": 2016, "stale": 2016, "already": 0, "dropped": 0}
```

`stale == considered` on every cycle, and `already: 0` means the success-store `__sent_seen_v2` has
**never recorded a single successful replay**. This is the same class as the recorded Pipedrive
list-ordering trap, on Smartlead this time.

Blind since (per campaign): 3686181 ≈ Jul 31 · 3686184/3686193 ≈ Aug 4 · 3686187 ≈ Aug 6 —
**4 to 10 days**, not just today.

Consequences:
- 0 of today's 176 SENT events reached WF-2 (WF-2 shows 10 executions, all webhook, none SENT).
- WF-2's own alarm text states the stakes: *"SENT reconciliation is the only source of SENT events —
  if it is dead, sends are going unobserved."* It is dead **and reports itself `idle` (healthy)**.
- Make scenario **8557031 "If new email is sent in SmartLead, create Lead in Pipedrive"** was the
  other owner of this path and went OFF at 12:45Z. Since then **nothing creates Pipedrive leads for
  new sends.**
- Corroborated in Pipedrive: **2 leads created today** — `b4badc60` (human, via Leadjet) and the test
  fixture `72ec85c0` — against 176 sends.

## 🔴 P0-3 — the lead-label wiper is live, and the mechanism is now identified

**6 leads lost labels today**, 09:41:42–09:42:45Z, every one landing on exactly `{1. Cold, 2. Connected}`:

| lead | person | lost | title |
|---|---|---|---|
| `29413600` | 61664 | **3. Responded, 4. Positive Reply**, AUTOMATED LEAD NURTURING | AI SUMMIT 2025 \| Person-4354e1e0 \| KAYAK |
| `1574a9a0` | 48704 | **3. Responded, 4. Positive Reply**, AUTOMATED LEAD NURTURING | Ai4 Conference \| Person-4da35a25 \| Cardinal |
| `da28dee0` | 57950 | **3. Responded, 4. Positive Reply**, AUTOMATED LEAD NURTURING | OSFF 2025 \| Person-fb36239a \| Tokenovate |
| `c08d6860` | 61928 | **3. Responded, 4. Positive Reply**, AUTOMATED LEAD NURTURING | AI SUMMIT 2025 \| Person-53052074 \| Hexagon |
| `73f7e160` | 59899 | AUTOMATED LEAD NURTURING | Peter Koerte \| Siemens |
| `fd137710` | 54622 | AUTOMATED LEAD NURTURING | Ornella Alfieri \| Booking.com |

*Proof of shrinkage, not of a coincidental state:* the 2026-08-05 full lead snapshot
(`lead_person_map.json`, 57,240 leads — another session's raw observation, re-verified against my own
current read of all 57,602 leads) has each of these carrying the larger set, and each lead's
`update_time` in that snapshot is from **June** — stable for two months, destroyed today.

**Mechanism, tested across all 11 wipes: 10 of 11 are preceded 23–73 s earlier by a person write to
`fe9e7b17cab6572364afe079680bba8c018617d3` ("Last Scan Date") by `api | axios/1.18.0 | u24599218`
= `pii-0bd328cb@example.invalid`.**

```
2026-08-07T09:38:51  lead 5c898700 p67892  ← -37s  Last Scan Date  axios/1.18.0 u24599218
2026-08-07T09:38:52  lead f80e30a0 p59894  ← -47s  ...
2026-08-07T09:38:54  lead c03c07c0 p60622  ← -70s
2026-08-07T09:39:56  lead 5c9b9980 p60645  ← -59s
2026-08-09T19:54:05  lead 122445c0 p58431  ← no person write within 900s  (different path)
2026-08-10T09:41:42  lead 29413600 p61664  ← -23s
2026-08-10T09:42:42  lead 1574a9a0 p48704  ← -64s
2026-08-10T09:42:43  lead 73f7e160 p59899  ← -62s
2026-08-10T09:42:44  lead fd137710 p54622  ← -73s
2026-08-10T09:42:44  lead da28dee0 p57950  ← -73s
2026-08-10T09:42:44  lead c08d6860 p61928  ← -68s
```

The chain: **any Person update → Zapier "Updated Person" trigger (23–73 s poll lag) → Pipedrive
"Update Lead" → `label_ids` overwritten wholesale.** The 5 active Zaps in the *Outreach
infrastructure* folder are all `Updated Person → Find Lead → Update Lead` and write exactly
Cold/Connected/Responded; the terminal set `{1. Cold, 2. Connected}` matches
`274318213`/`274316027` ("…put connected tag in lead"). Corroborating: lead `330ce930` (Person-82419bfe)
in the same batch **gained** `2. Connected` at 09:42:40 — the writer sets the set, it does not add.

Bounds stated honestly: the middle link (which specific Zap) is inferred — Pipedrive's lead API
carries no actor and lead `changelog`/`flow` both 404, so the write itself is unattributable from
Pipedrive alone. The trigger and the effect are both proven.

**Scale correction: ≥11 wipes since 2026-08-05, 6 of them today — not 2.** This is a lower bound:
leads created after the Aug-5 baseline (which includes the two known cases, Malachi and Lucas) are
outside my comparison. Nothing was repaired by this session.

---

## 2. Pipedrive write census (reverse direction)

**Method.** `/api/v2/persons?sort_by=update_time&sort_direction=desc` and
`/v1/leads?sort=update_time DESC&archived_status=all`, walked until the first record older than
00:00Z. **Ordering proven, not assumed** — both walks assert `update_time` is monotonically
non-increasing across every page (both passed). Actor attribution from
`/api/v1/persons/{id}/changelog` (`change_source`, `change_source_user_agent`, `actor_user_id`).
`/api/v1/recents?since_timestamp` used as an independent cross-check (75 items: 32 person, 23
activity, 13 org, 3 deal, 2 user, 2 file — the person count agrees exactly with the v2 walk).

**32 persons and 24 leads touched. 28 person-field writes, every one attributed:**

| writes | actor | who | assessment |
|---|---|---|---|
| 15 | `api \| axios/1.18.0 \| u24599218` | Andriy Kucherenko `pii-0bd328cb@example.invalid` | Last/Next Scan Date on 8 persons, 09:36–09:41Z — **the wiper's trigger** (P0-3) |
| 5 | `api \| leads-graphql \| u25733113` | Noah Keimach | human, new lead Person-14671955 |
| 4 | `api \| Leadjet \| u25733113` | Noah Keimach | human, LinkedIn extension |
| 2 | `app \| Chrome/150 \| u24902534` | Lule Salihu | human, web app |
| 1 | `api \| janea/1.0 \| u25112064` | this project's token | fixture rename 12:46:23Z |
| **1** | **`api \| Make/production \| u13015123`** | Make | **12:37:32Z** — `org_id` on the fixture person |

### Make after the 12:45Z kill

**No Make write after 12:45Z.** The single Make write is at **12:37:32Z**, 7.5 minutes *before* the
kill, and it is the pre-kill duplicate-forward event itself. **No alarm.**

Independently confirmed via the Make API (`/organizations` → `/teams` → `/scenarios`, org 2262681 /
team 897194): **all 21 scenarios `isActive=false`**, including `8557031`, `8557478` and the two
originals `2925596`, `2925894`.

### Zapier writes today

Zapier does not identify itself in `change_source_user_agent`, and Pipedrive leads carry no actor —
so Zap writes cannot be labelled directly. The evidence that they happened is behavioural: 8 leads
were rewritten 09:41:30–09:42:45Z with no corresponding same-second person write of their own, in a
fixed-label pattern matching the Zaps' documented behaviour (P0-3). One case breaks the strict
chain and is reported rather than smoothed over: lead `4d245410` (person 84544 Person-0128acd7) was
rewritten at 09:41:30Z although that person's last update is **2026-07-27T15:13:17Z** — labels
unchanged, so an idempotent re-write.

### Label shrinkage

Full sweep, all 57,240 baseline leads vs all 57,602 current: **11 leads lost at least one label**
(6 today, 4 on Aug 7, 1 on Aug 9), 5 of them `3. Responded`, and **all 11 end at exactly
`{1. Cold, 2. Connected}`**. See P0-3.

### Orphans and duplicates

- **Persons created today: 1** — `85516` Person-14671955 (13:45:10Z, Leadjet/human), and it has a lead.
  **Zero orphan persons.**
- **Duplicate persons created today: none.**
- Pre-existing duplicates that matter operationally: **4 persons share `pii-c61c7d08@example.invalid`** —
  `84885`, `84886`, `84887` (all `Nik Krivosheia`, created 2026-07-31T09:00:28Z) and `85506`
  (the fixture). WF-2 reported `__person_dupes: true` and
  `__person_candidates: ["84885","84886","84887","85506"]` on every reply. It resolved
  **84885** on the 12:36 reply and **85506** from 12:50 onward (`__person_adopted: true`), so
  person-side and lead-side writes for the same address landed under two different person records.
  Also seen: `karol.kielecki@` (48613/43687) and `mike@` (48601/427) — internal, pre-existing.

**Section verdict: PASS on Make and on orphans; FAIL on label integrity.**

---

## 3. Deploy-window coverage

**Coverage limit, stated up front:** n8n Cloud exposes **no version-history API** —
`/workflows/{id}/versions` and `/workflows/{id}/history` both return `404 {"message":"Version not
found"}`, `/audit` is `405`. Exact spans cannot be read from n8n. Reconstructed from three
independent sources instead: local pre-deploy backup epochs, each workflow's current `updatedAt` +
`versionId`, and — the only wire-level evidence — **scheduler cadence gaps**.

| # | UTC | target | evidence | current versionId |
|---|---|---|---|---|
| 1 | 10:31:33 / 10:32:12 | WF-1 reply channel | `wf1_backup_before_reply_channel_1786357893/932` | WF-1 `updatedAt 10:32:16.029Z` |
| 2 | 10:56:27 | WF-2R two-ring | `wf2r_backup_before_tworing_1786359387` | |
| 3 | 11:00:41 | WF-2 dedupe canonicalisation | `wf2_backup_before_dedupe_canon_1786359641` | |
| 4 | 11:03:46 | WF-2 forward inbox map | `wf2_backup_before_inboxmap_1786359826` | |
| 5 | **11:31:01** | **WF-2 FLIP → live** | `wf2_backup_before_FLIP_1786361461`; WF-2's own stamp on the Slack wire: *"WRITE_MODE=live since 2026-08-10T11:45:14.041Z"* | |
| 6 | 13:21:01 | WF-2 alert fix | `wf2_backup_before_alertfix_1786368061` | |
| 7 | 13:34:18 | alarm conversion, WF-2 + WF-2R + WF-2S | 3 × `*_backup_before_alarmfix_1786368858` | |
| 8 | 14:36:41 | WF-2S mode inversion | `wf2s_backup_before_modeinvert_1786372601` | WF-2S `updatedAt 14:36:44.157Z` |
| 9 | **15:10:40** | **WF-2 gate fix** | `wf2_backup_before_gatefix_1786374640` | WF-2 `updatedAt 15:10:44.061Z`, `45637e70` ← **P0-1** |

WF-2R `updatedAt 14:15:33.801Z` sits inside window 7's family.

**Note on the flip time:** the audit brief says "flip ~12:31Z". The wire says otherwise — WF-2's own
config stamp is `11:45:14.041Z`, the flip backup is `11:31:01Z`, and the readback probe is exec 14853
at `11:31:09.313Z`. Treat 11:45:14Z as the authoritative live-since.

**Did any Smartlead event fall into a paused or dead span?**

- **Scheduler outage: exactly one.** WF-2S has 61 executions today on a 900 s cadence; the only
  anomalous gap is **1762 s, 10:45:55Z → 11:15:17Z** — one missed cycle, consistent with the
  intentional `deploy_with_pollers_paused.py` pause around windows 2–4. WF-2R: 64 executions, max gap
  923 s — no outage. All other gaps ≤ 937 s (normal jitter).
- **No reply fell into a dead webhook span.** All 6 replies produced a WF-2 execution
  (14913, 14922, 14954, 14958, 14961, 14966) within 16–95 s of the Smartlead event time.
- **But window 9 did not drop an event — it destroyed one.** The 15:30:20Z reply arrived 19½ minutes
  after the 15:10:44Z deploy and was killed by it (P0-1). The failure mode the day was guarding
  against (events lost *during* a deploy gap) did not occur; the one that did occur is a deploy that
  poisons every event *after* it.
- **SENT events cannot be assessed this way**: none of the 176 were ever delivered, by a mechanism
  unrelated to deploy windows (P0-2). No reconciler replay recovered any of them —
  `already: 0` proves none ever has.

**Section verdict: PASS on window discipline (one intentional poller pause, no event dropped in a
gap), FAIL on post-deploy verification — the last deploy of the day shipped a runtime-fatal defect
and was never exercised against a reply.**

---

## 4. Test-artifact hygiene

**Live in Pipedrive:**

| artifact | state now | leak risk |
|---|---|---|
| person `85506` "ZZ FLIP-GATE TEST (do not distribute)" | live, org 21719, `pii-c61c7d08@example.invalid`, `update_time 12:51:57Z` | name is self-documenting |
| lead `72ec85c0-94b9-11f1-bf13-f56958004891` | live, **labels `['1. Cold','2. Connected','3. Responded']`**, title `3686187 - [Events Visiting] AI4 2026 - Rune - Valids - ZZ FLIP-GATE TEST (do not distribute)` | **counts toward the 1,713 Responded population and any Responded-driven report** |
| **activity `43974`** | **`type=handover`, `done=false`, `due 2026-08-13`, `user_id 16340280` (Melisa), `reference_type=automation`, subject "Assign this lead to a sales exec!"** | **🔴 sitting in Melisa's queue, due Wednesday** |
| activities `43973`, `43977`, `43978`, `43979` | 4 × `Email reply — [Events Visiting] AI4 2026 - Rune - Valids`, `done=true`, on the fixture lead | timeline noise only |
| persons `84886`, `84887` | duplicate `Nik Krivosheia` records on the fixture email | resolution ambiguity (finding 9) |

The handover is **automation-generated, not ours** — `create_assignment_task: false` in WF-2's CONFIG,
and `reference_type=automation` with `creator_user_id=25112064` means a Pipedrive workflow automation
fired on *our* `3. Responded` write at 12:51:55Z. The identical pattern on a real lead the same day
(activity `43971`, lead `ac5dda00` Person-0ee7dfb2, 10:50:58Z) confirms the trigger. **Consequence:
writing `3. Responded` to any test lead injects a task into Melisa's queue.**

**Live in Smartlead:**

- Lead `4306240392` "Person-6d3f690f" / `pii-c61c7d08@example.invalid`, company "Person-6d3f690f Test", custom field
  `Title: "WF-2R flip-gate probe"`, created 2026-08-06 — **inside the live ACTIVE campaign 3686187**,
  `is_unsubscribed: false`, `lead_category_id: 2`, `last_reply_at 2026-08-10T15:03:18Z`,
  `campaign_lead_map_id 3497903848`. It sits in a production campaign's lead set and is not
  suppressed. `last_sent_at` is 2026-08-06, so no further sequence mail has gone out — but nothing
  prevents it.
- 6 forwards of test content were delivered to `rune@janeasystems.com`.

**Live in n8n:** 7 DNC/observability workflows deployed **inactive** (`DNC__NormalizeIdentity__v1`,
`DNC__UpsertLedger__v1`, `DNC__CheckLedger__v1`, `dnc_check_service`, `dnc_expiry_job`,
`heyreach_reply_to_dnc_ledger`, `smartlead_observability_readonly`) plus 3 legacy inactive
(`WF-0 - Discovery`, `WF-1-DO NOT USE`, `HeyReach — Phase 0 Payload Capture`). Two probe executions
errored today in `mode: integrated` (14869 `unknown column name 'added_at'`; 14897
`Column(s) "linkedin_url_norm" do not exist`) — schema drift in test harnesses, inactive workflows,
no production reach. n8n data-table contents are **not** readable through the public API
(`/data-tables` 404), so residual test rows there could not be inventoried.

**Live in Slack:** deliberately fired test alarms in `#niks-channel` only (`Ops Warn WF-2S Stale`
`ts 1786371329.821239` at 14:15:29Z, write-mode alarms at 13:45/14:00/14:15/14:30Z). **No test
content reached `#lead-processing` (C07LTD8UT70).**

**Section verdict: FAIL — one live handover in Melisa's queue, one test lead labelled `3. Responded`
inside the production Responded population, one test lead sitting unsuppressed in a live campaign.**

---

## 5. Claimed vs actual

| claim | re-derived | verdict |
|---|---|---|
| "5 replies / 6 forwards, single extra = pre-kill duplicate" | 5 replies / 6 forwards up to 15:04Z ✅. The extra is `12:37:32` vs `12:37:39` — 7 s apart, 7½ min before the 12:45Z Make kill ✅. **But all 5 were the same synthetic fixture, and the 6th reply of the day (15:30:20Z, organic) got 0 forwards.** | **CONFIRMED as stated, materially incomplete** |
| "pairing after the Make kill: 4 replies → 4 forwards, exactly 1:1" | 12:50:55→12:51:54, 14:38:22→14:39:19, 14:52:51→14:53:55, 15:03:18→15:04:12 | **CONFIRMED** (fixture traffic only) |
| "P0a dedupe proven 3×" | 3 replay executions (14927, 14928, 14956) each took `IF Duplicate → NoOp Duplicate`; **zero FORWARD events on the Smartlead wire at 13:16 or 14:45** | **CONFIRMED on the wire.** Caveat: the key is `event\|campaign\|lead\|epoch-ms`, so it catches exact replays only — and it is written before the work (P0-1b) |
| "WF-2 reply executions: 8" | 10 WF-2 executions; 5 driven by a real REPLY, 3 reconciler replays, 2 probes (11:01:50 `flip_preflight_probe`, 11:31:09 `flip_b3_readback_probe`). 5+3 = 8 | **CONFIRMED** (reading "reply executions" as replies + replays) |
| "1,713 leads carry `3. Responded`" | **1,713 of 57,602** — exact match. (Aug-5 baseline: 1,686 of 57,240.) 0 archived. | **CONFIRMED exactly** |
| "Make both scenarios OFF" | Make API: all 21 scenarios `isActive=false`, incl. 8557031, 8557478, 2925596, 2925894 | **CONFIRMED independently** |
| "zero events lost" | 1 organic reply destroyed (15:30:20Z) + 176 SENT events never delivered | **🔴 FALSE** |
| "alert now proven on the wire with a permalink" | exec 14961 `Reply Alert` → `ok:true`, `ts 1786374243.432809`, and the message is in `#niks-channel` | **CONFIRMED** — but the very next reply died in `Body Reply Alert` |
| "reply alerts route to `#lead-processing`" (LinkedIn/WF-1) | WF-1 ran **zero** executions today, so unexercised. WF-2's CONFIG: `slack_channel_replies = C0B8GCVNR5W` (ops) with `slack_channel_replies_at_flip = C07LTD8UT70` unused → the 15:04 email reply alert went to the **ops** channel | **UNVERIFIED for WF-1; mismatch for WF-2** (finding 10) |
| "`write_mode_max_hours` stuck at 0 for ~3 h" | Slack wire: 2 h-threshold alarms at 13:45/14:00/14:15Z (correct — live since 11:45 + 2 h), a **0 h**-threshold alarm at 14:30Z, silence after the 14:36:44Z deploy. ~45 min of spam, and the "0" appears only in the last ~15 min | **MISMATCH** (finding 13) |
| "forwards confirmed in the mailbox — Rune confirmed receipt" | not API-verifiable; all 6 forwards carried fixture content | **human-closed, unverifiable** |
| "`Ops Warn WF-2H Stale` converted but unfired AND unexplained" | Partly explained: `WF-2H Watch Eval` returns `__wf2h_hours: 8, __wf2h_stale: false, __wf2h_limit: 48`, while its `alert_text` renders `"has not succeeded for ?h"` — the message body reads a name the eval never sets | **narrowed** (finding 11) |

---

## Remaining findings, with evidence

**4 · WF-2 can resolve only 0.87 % of leads.** `R Lead List` fetches
`/v1/leads?limit=500&archived_status=all&sort=add_time%20DESC` — a **global** page of the 500
most-recently-*created* leads, unfiltered by person; `Lead Resolve` then filters it. Measured
against my full walk of all 57,602 leads: the 500-row window reaches back to
**2026-08-04T09:36:15Z — 6.25 days**, covering **500 of 57,602 leads (0.87 %)**. **57,102 leads
(99.13 %) cannot be resolved**, including **1,695 of the 1,713 `3. Responded` leads**. Every
execution today reported `__leads_page_saturated: true`. Realised live on the one organic reply:
person 83623 has exactly one lead, `da6fce30`, created 2026-07-21 — outside the window →
`__lead_id: null, __lead_how: "none", __no_lead: true`. So even without P0-1 that reply would have
received person-side writes only: no label, no activity, no handover. Today's testing never touched
this because the fixture lead was created at 12:46Z, inside the window.

**5 · Dedupe registers before the work.** See P0-1b.

**6 · Two reply alerts silently failed.** `Reply Alert` returned `{"error": "invalid syntax"}` as its
*output* (not an execution failure) in execs 14913 and 14922 — real JavaScript in an n8n expression
on a node that swallows errors, with the execution still `success`. `Ops Warn No Lead` in the same
execution posted `ok:true`, so the failure is node-local. Fixed by window 6 (13:21Z) and proven at
15:04Z. Note the two failure modes sit side by side: `Reply Alert` swallows and continues,
`Body Reply Alert` has `onError` unset and kills the execution.

**7 · The new alert gate is unproven.** WF-2's current `First Reply Gate` is the delivery-registry
version (`$getWorkflowStaticData('global').__alert_delivered`, set only on Slack `ok:true`). It was
deployed at 15:10:44Z; the last reply to reach the gate was at 15:03:18Z, under the **old**
label-based rule. Evidence the old rule was still live then: exec 14954/14958 read
`__lead_labels` containing `3. Responded` → `__should_alert: false, __alert_reason: "repeat_reply"`,
while exec 14961 read `['1. Cold','2. Connected']` → `"first_reply"` → alerted. That label was
removed from the fixture lead between 14:53:40Z and 15:04:00Z (a
`strip_fixture_responded.py` exists in the build directory), i.e. the "alert proven" run was
enabled by stripping the gate's input. The new gate has **never run on a reply**, and the deploy
that introduced it is the one that breaks the path.

**9 · Split person resolution on duplicates.** See §2. Writes for one address landed under person
84885 (12:36 reply) and person 85506's lead (12:50 onward).

**10 · Reply alerts still land in the ops channel.** `slack_channel_replies = C0B8GCVNR5W` equals
`slack_channel_ops`; `slack_channel_replies_at_flip = C07LTD8UT70` is carried in CONFIG but unused.
The one successful reply alert (15:04Z) went to `#niks-channel`. Either the flip-time switch was
never applied or the key is vestigial — the owning session should say which.

**11 · Alarm bodies pre-render wrong text.** `WF-2H Watch Eval` renders `"…not succeeded for ?h"`
while `__wf2h_hours = 8`. `WF-2 Mode Eval` renders *"WRITE_MODE is 'live' but the declared steady
state is 'live'. Someone rolled back — replies are being LOGGED, not written to the CRM."* while
`__mode_actual == __mode_expected == "live"` and `__mode_overdue: false`. The texts are built
unconditionally; if either ever fires it will say something false.

**12 · Two empty Slack messages** in `#niks-channel` at 13:16:01Z and 14:45:06Z — the timestamps of
the dedupe-replay executions, which took a NoOp path with no Slack node. Cosmetic, but it means
something posts an empty body.

**14 · Third-party automation on the outreach data.** `pii-0bd328cb@example.invalid` (Pipedrive user
24599218, active) runs an axios client that wrote `Last Scan Date`/`Next Scan Date` on 8 persons at
09:36–09:41Z. Harmless in itself; it is the trigger for P0-3 and it is outside the outreach stack's
ownership.

---

## Coverage limits of this audit

1. n8n has no version-history API — deploy spans are reconstructed (§3), not read.
2. Pipedrive leads expose no `changelog` and no `flow` (both 404) — lead writes cannot be attributed
   to an actor directly; label shrinkage is proven by snapshot diff instead.
3. Shrinkage detection is bounded by the 2026-08-05 baseline: leads created after it (including the
   two previously-known wipes) are outside the comparison. **≥11 is a floor, not a total.**
4. Zapier task history was not read (no enabled read action was available without changing MCP
   configuration, which a read-only session should not do) — so the specific Zap in P0-3 remains
   inferred from behaviour.
5. n8n data-table contents are not API-readable — residual DNC test rows are uninventoried.
6. Mailbox delivery of the 6 forwards is not API-verifiable.
7. The census window closes at **2026-08-10T15:45:07Z**. Pass 1 already proved that events arriving
   during a walk are missed; anything after 15:45Z is outside this audit.

---

## What is NOT in this report

No fixes, no deploys, no writes. The repair list implied by P0-3 (6 leads today, 11 since Aug 5,
`a5_numbers.json` / `a6_mech.json` carry the exact prior label sets) and the disable/patch decisions
for P0-1 and P0-2 belong to the owning sessions.
