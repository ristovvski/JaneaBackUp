# 2026-09-09 — Аудитор: INFRA HEALTH CHECK (morning, after yesterday's four production writes)

Read-only. Files only, no Slack. Clock at start: **2026-09-09T08:54:47Z**.
Verdict per item, each with the one number or execution id that proves it.

| # | item | verdict | proof |
|---|---|---|---|
| 1 | digest posted | **AMBER** | exec `49622`, Slack ts `1788926415.313539` — posted, but **5 × n/a** |
| 2 | sweep disarmed | **GREEN** | `dev` / `false` / `false`; **0** executions since 18:21Z |
| 3 | failed executions | **GREEN** | **0** failures, **0** WF-ERR invocations, **0** auto-deactivations |
| 4 | auth-notice port | **AMBER** | **0** NOT ARMED posts today; port ran **once** (exec `48602`) — dedupe branch unexercised |
| 5 | duplicate alerts | **GREEN** | **10** alerts / **10** distinct people, **0** with 2+ |
| 6 | claims + rollback | **AMBER** | prune exec `49667`: **183 deleted / 0 failed**; staticData rollback **still present (28 keys)** |
| 7 | active roster | **GREEN** | 41 workflows; **21** active — same as yesterday, **0** activated/deactivated |
| 8 | 250-person integrity | **GREEN** | **20/20** still field `686`, 0 reverted |
| 9 | Finovate | **AMBER** | row in **62 s** + 1 alert, but **no label / no field** — pending window 2 |

---

## 1. DIGEST — AMBER: it posted, and the n/a failure mode is still there

**It posted.** exec `49622`, started 2026-09-09T04:00:00Z, status `success`, lastNode `Post Digest`,
40 nodes run, no error. `Post Digest` returned `ok: true`, channel `C0BTP6VHP1B`, Slack ts
`1788926415.313539`. **First post since 3 Sep** — the four intervening days were `error` at
`No Match Count`. **The linter now exits 0**: 0 unresolved node references across all 41 workflows,
so the dead `$('I04 Status')` reference is genuinely gone.

*(Timing note: it ran at **04:00:00Z = 07:00 IDT**, not 06:35. The schedule is 04:00Z.)*

**But the section-values guard did not hold — 5 × `n/a`:**

```
:sunrise: *Morning digest* 2026-09-08 04:00Z → 2026-09-09 04:00Z
:large_green_circle: *CAMPAIGNS* SL 4 · HR 4 — BioTechX Boston 2026 - Mario - Catch-alls (0 sent 24h,
  sequence complete) · … | HR: BioTechX … · FinovateFall … · Ai4 2026 - Rune · Ai4 2026 - Mario
:large_green_circle: *VOLUME 24h* email sent 0 · LinkedIn msg 5/inv 81 · replies 0 real / 0 OOO / 0 bounce
  · new leads 80 (API 80)
:large_yellow_circle: *INTEGRITY* sent-without-lead 3917998:n/a 3917997:n/a 3868450:n/a 3868449:n/a
  · leads w/o person 0 · nameless campaign leads 0
:large_green_circle: *DNC* active 25685 (+13 / -0 24h) · gate OK 105ms (0/16 fail today)
:large_green_circle: *HEALTH* failed execs 0 · missed schedules 0 · CRM change log 787 events · no-match n/a
:information_source: _not measured: enrich-queue depth: no such queue exists in the estate (WF-2 enriches
  synchronously) — not 0, absent · no-match count unreadable: missing_scope_
```

Two sections carry no values: **INTEGRITY `sent-without-lead` is `n/a` on all four campaigns**, and
**`no-match n/a`** with the footer naming the cause — `missing_scope`. So the crash is fixed and the
post is back, but the thing the fix was for — real values in every section — is only 5 of 7 sections.
The digest self-flags INTEGRITY yellow, which is honest. Placeholder scan: `n/a` ×5, `null` 0,
`undefined` 0, `unknown` 0.

## 2. SWEEP STATE — GREEN, properly disarmed

Live CONFIG: `MODE = "dev"` · `FIRE_PIPEDRIVE = false` · `FIRE_SMARTLEAD = false` ·
`pd_chunk_size = 250`. versionId `df2ac125`, updatedAt 2026-09-08T15:21:17Z (the disarm).

**Executions since 8 Sep 18:21Z: 0.** Only two executions exist at all, and they split cleanly:

* exec `48563` @13:40:28Z — the **dev count**. `FIRE_PIPEDRIVE?` gate taken; `PD Write DNC Field`,
  `PD Patch Lead Labels`, `SL Unsubscribe` **did not run**. Dev Summary posted to `C0BQM1X9ZUY`:
  *"chunk 10/12 done · 250 processed (224 labels, 26 field-only) · 330 remaining · 0 errors ·
  Smartlead: 874 pending, 46 already unsub, 628 not found"*.
* exec `48609` @15:04:48Z — **the fire**. `PD Write DNC Field` ran with **250 items**,
  `PD Patch Lead Labels` with **224 items**, `SL Unsubscribe` **did not run** (FIRE_SMARTLEAD false).

So window 1 = 250 field writes + 224 label patches, Smartlead untouched, and **330 rows remain** for
window 2.

## 3. FAILED EXECUTIONS — GREEN

`status=error` walk **per workflow** across all 41 (never the unfiltered list): **0 failed
executions** since 2026-09-08T09:00Z. **0 WF-ERR invocations** in the same window, therefore **0
WF-ERR posts in #alerts** — consistent, not an assumption. **0 auto-deactivations**: nothing
inactive that was not already inactive yesterday.

## 4. AUTH-NOTICE PORT — AMBER: deployed and correct so far, but barely exercised

The port is **wired and running**. The single post-deploy execution, exec `48602` @2026-09-08
T14:46:05Z, ran the new chain: `Verify Secret → IF Authentic → DT Auth Notice Get →
Auth Notice Decide → DT Auth Notice Claim → Auth Notice Ctx → IF Auth Warn → Ops Warn Bad Secret`.
Signals: `__auth_ok: true`, `__auth_mode: "unconfigured"`, `__auth_event: EMAIL_REPLY`,
`__auth_hint: "4.182.88.118 / axios/1.18.0"`.

**NOT ARMED posts in #alerts — 0 today, 1 post-port yesterday** (17:46:05 IDT = 14:46:05Z, which is
exec `48602`). Yesterday's other two (01:03 IDT, 15:58 IDT) are **pre-port**. Expected "at most one"
→ met.

**Two honest qualifications.**
1. **0 WF-2 executions today**, so today's silence is *absence of traffic*, not the dedupe deciding
   to stay quiet. The `already_posted_today` branch has **never been exercised** — same shape as the
   3 Sep port's own PARTIAL. It will only be proven by a burst.
2. **The staticData write does look removed, and here is the proof:** `__auth_warn_at` still reads
   `1788872285595` = **2026-09-08T12:58:05Z**, 40 minutes *before* the 13:38:03Z deploy — and exec
   `48602` ran at 14:46:05Z without updating it. Old code would have stamped 14:46.

## 5. DUPLICATE ALERTS — GREEN

`#lead-processing` since 8 Sep 00:00Z: **10 alerts, 10 distinct people, none with 2+** —
Person-53fb4216 · Person-718696f5 · Person-d86d9627 · Person-a2e29483 · Person-c719f684 · Aoune Barhoumi ·
Person-fcd2e56a · Person-70536e16 · Kevin Shen · Person-68195549.

That holds **despite** four of them having **two** registry upserts each (`pii-9b2ca0d1@example.invalid`,
`pii-8c030cce@example.invalid`, `pii-5b412720@example.invalid`, `linkedin.com/in/pii-12d05b28`). The
alert claim is doing its job; the duplicate upserts stay harmless because upsert is idempotent.
19 UpsertLedger executions since 8 Sep 09:00Z, all `reply_dnc`.

## 6. CLAIMS TABLE — AMBER: prune healthy, rollback NOT dropped

`dnc_claims_prune` (`csGJbrHxEBnJdFfu`, active) **ran today**: exec `49667` @2026-09-09T05:35:00Z,
`success`. Its own report: `dry_run: false`, `read_cutoff 2026-09-02T05:35:01Z`, **rows_read 242**,
`by_family {wf1_seen 89, wf1_alert 48, wf2_seen 94, wf2_alert 11}`, `expired_found 183`,
`attempted 183`, **`deleted 183`, `failed 0`**. Retention config: 90 d for the alert families, 7 d
for seen/bounce/dedupe/lead_create/probe.

*Total* row count is **not API-readable** — n8n still exposes no data-table endpoint — so 242 is
"rows inside the read window", not the table size. Stated rather than guessed.

:warning: **The staticData rollback copy is still present — 28 leaf keys, not dropped as ordered.**
WF-2 `staticData.global` holds: `wf2_seen` **12** keys · `__alert_delivered` **13** · `__event_aliases_seen`
**1** · `wf2_bounce_seen` **0** · plus `__auth_warn_at` and `__auth_suppressed` (= 4). Down from 53,
so something reduced it, but it was not removed. Every embedded timestamp is **≤ 2026-09-08T13:23:14Z**
and nothing has been written since the deploy, so it is inert — a stale copy, not a live dual-write.

## 7. ACTIVE ROSTER — GREEN, and the expectation is the thing that is off

**41 workflows** ✓. **21 active, not 20** — but yesterday's snapshot was *also* 21, and the diff
since yesterday is **0 activated, 0 deactivated**. So there is **no drift**; the "20 expected" is
off by one against the estate as it has stood since at least 8 Sep. Two `zz_*` workflows remain
(`zz_migrate_wf1_alert_registry`, `zz_verify_wf1_alert_registry`) — **both inactive**, left as
throwaways from 3 Sep.

Changed since 8 Sep 09:00Z (all three expected, all still active): `dnc_projections_sweep`
(15:21:17Z, ver `df2ac125`) · `WF-2 Smartlead Receiver` (13:38:03Z, ver `2515c295`, 195 nodes) ·
`dnc_morning_digest` (13:32:03Z, ver `d17e47b2`, 40 nodes).

## 8. INTEGRITY SPOT-CHECK — GREEN, nothing reverted overnight

The 250 person ids were harvested from exec `48609`'s own `PD Split Rows` output (250 distinct).
Random sample of 20, seed fixed: **20/20 still carry `DNC Status = 686`. 0 reverted, 0 errors.**

Every sampled `update_time` is 2026-09-08T15:06–15:08Z — the fire window itself — so **no
cohabitant automation touched them overnight**, which is the specific risk (four label-wiper Zaps
have hit this field before). Sample: p32481, p43370, p43492, p43667, p44112, p53341, p69781, p71395,
p73303, p79835, p80125, p81869, p83660, p83702, p83897, p83906, p84069, p84740, p84966, p85016.

## 9. FINOVATE — AMBER: row and alert land, the projection does not (yet)

**One reply since 8 Sep**: `pii-9b2ca0d1@example.invalid`, campaign 3868449, reply_time
2026-09-08T12:57:20Z, category *Meeting Request*, not bounced.

* **DNC row ✓** — UpsertLedger exec `48530` at 12:58:22Z, **62 seconds** after the reply, reason
  `reply_dnc`.
* **Alert once ✓** — `#lead-processing` 15:58:07 IDT (= 12:58:07Z), single post. (A second upsert
  followed at 13:24:27Z, exec `48555`, and produced **no** second alert.)
* **Label ✗ and field ✗** — lead `98176190` carries `1. Cold, 2. Connected, 3. Responded,
  4. Positive Reply` and **no DO NOT CONTACT**; person `p85878` has `DNC Status = None`.

**That is expected, not a regression:** the projection is done by `dnc_projections_sweep`, which is
disarmed, and window 1 covered chunk 10/12 leaving **330 rows remaining**. Amity was registered
*after* window 1's selection, so she sits in that backlog. Worth stating plainly though, because it
names a standing gap: **a new `reply_dnc` row is not enforced in Pipedrive until the next sweep
window** — registered ≠ enforced, and right now the enforcement leg is switched off.

**WF-2R replays overnight:** 60 executions since 8 Sep 18:00Z, **all success**, no errors.

---

## Needs action, ranked

1. **P2 — digest INTEGRITY + no-match still `n/a`.** `sent-without-lead` is n/a on all four
   campaigns and `no-match` is unreadable (`missing_scope` — a Slack scope, not a code bug). The
   crash is fixed; the values are not. Either grant the scope / fix the integrity query, or make the
   digest say *why* per-campaign instead of a bare `n/a`.
2. **P3 — the auth-notice dedupe is unproven.** One execution, one post, correct. The
   `already_posted_today` path has not run. It will be settled by the next burst, not by more
   reading; worth watching the first busy WF-2 day.
3. **P3 — staticData rollback copy still present (28 keys).** Inert, but it is the fourth store's
   leftovers plus three other families. Drop it when convenient; while it exists, anyone reading
   staticData can mistake it for live state.
4. **P4 — window 2 (330 rows) is the gap between registered and enforced.** Person-d86d9627 is the live
   example. Not a defect, but it is the reason the DNC label/field lags the registry today.
5. **P4 — "20 active" expectation** is off by one against reality (21, unchanged for two days).
   Correct whichever is wrong — the expectation or the roster.

## Artifacts

`audit-artifacts/` — this pass's raw evidence is in the scratchpad JSONs
(`t1_health.json`, `t2_detail.json`, `t3_rest.json`, `t4_auth.json`);
`WF_LINTER/node_reference_resolves.js` run on the live estate → **exit 0**.
