# §9f.2 pre-fire — WF-2 staticData → claims table

**2026-09-03.** One thing is already deployed (§0). **Everything else is at the gate: your word before
anything is written.**

---

## 0. Done already, as instructed

**WF-2R now has `batchSize 1, batchInterval 10000`** — the same throttle WF-2S already carried.
versionId `7d31f745` → **`f1e4a6b6`**, 25 nodes, still active. Backup in `backups/`.

A worst-case 20-item replay burst now spans **200 s** instead of firing back to back, inside a
900 s cycle. This removes the acute exposure today; it does not replace the port.

---

## 1. The exposure is measured, and the collision has already happened

I found the real overlap window and read what ran inside it. On **2026-08-28 between 11:45:42 and
11:46:16**, four WF-2 executions overlapped:

| exec | started | nodes run | staticData writers it ran |
|---|---|---:|---|
| **35131** | 11:45:42 (ran **34.3 s**) | 50 | `Dedupe`, `Body Lead Labels Union`, `Reply CRM Done`, **`Classify Body`**, `Normalize`, `Verify Secret`, `Event Alias Watch` |
| 35132 | 11:45:43 | 45 | `Dedupe`, `Claim SENT`, `Normalize`, `Verify Secret`, `Event Alias Watch` |
| 35135 | 11:45:53 | 41 | `Dedupe`, `Claim SENT`, `Normalize`, `Verify Secret`, `Event Alias Watch` |
| 35138 | 11:46:03 | 45 | `Dedupe`, `Claim SENT`, `Normalize`, `Verify Secret`, `Event Alias Watch` |

**All four mutated the same state, concurrently.** 35131 started first and finished last, so the
snapshot it loaded — taken *before* the other three wrote anything — is the one that was persisted.
**The `Claim SENT` writes from 35132, 35135 and 35138 were overwritten.**

(35131 is the Person-a9a7d542 bounce-shaped-as-reply execution named in Normalize's own comment. Its
own alert claim survived, because it finished last. That is luck, not design.)

### The framing correction that matters

**`staticData` is ONE object, persisted whole.** It is not seven independent stores that each carry
their own risk — a lost write loses the *entire delta* of whichever execution finished first,
across every key it touched.

So the exposure is not "three stores at low risk". It is: **any two overlapping executions lose one
execution's complete state change, in all seven stores at once.** Measured rate: **3 overlapping
pairs in 130 executions**, peak concurrency 2, and one observed window where four executions
collided.

---

## 2. The immortal entries — who they are

`__alert_delivered` holds 11 entries with two value shapes. The prune is
`nowSec - Number(reg[k]) > maxAge`; `Number("2026-08-11T…")` is `NaN`, and every comparison with
`NaN` is false, so **ISO-valued entries can never be pruned.**

**4 of the 11 are ISO-shaped, and three of them are real people:**

| Who | Key shape | Age |
|---|---|---|
| **Person-67ab0e3f** (person 85307) | legacy lead id | 22.9 d |
| **Person-6cc71013** (person 83681) | legacy lead id | 22.9 d |
| **Person-b70358e4** (person 83769) | legacy lead id | 22.9 d |
| Nik Krivosheia (person 84885) | person id | 23.1 d |

**Nobody has been wrongly suppressed yet.** The bound is 90 days and the oldest entry is 23.1 days,
so all four are *correctly* suppressed today. **The first date on which the bug would start costing
something is ~2026-11-09.** After that, those three people would never become re-alertable — a reply
from any of them would be silently swallowed for ever.

The other seven entries are epoch-valued and prune normally. One is a test lead
(`ZZ FLIP-GATE TEST`), and one email key resolves to no person at all
(`pii-10d2dcec@example.invalid` — the identity case the code comments already name).

### The fix, as you asked — repair, not just migrate

- **Migration normalises every value to one form.** In the table each row carries `claimed_at` as an
  ISO string, which is the column's existing contract from WF-1.
- **The runtime asserts the type rather than coercing it.** Age is
  `const t = Date.parse(row.claimed_at); if (!Number.isFinite(t)) → treat as UNKNOWN` — and unknown
  is reported, never silently retained. A value that cannot be parsed is corrupt state, and the
  current behaviour of keeping it for ever is precisely the bug.

---

## 3. A gap the WF-1 port left behind, which this port must not repeat

**The claims table has no retention, and nothing prunes it.**

Measured: **565 rows, ~180 KB, 27 days** — `wf1_seen` 508, `wf1_alert` 53, plus 4 test rows.
Growth ≈ 21 rows/day. No workflow anywhere performs a delete on this table.

The staticData version of WF-1's alert registry **pruned at 90 days**. The table version does not.
**The port removed a bound and did not replace it.** Adding WF-2 roughly doubles the fill rate.

At ~320 bytes a row this is not an out-of-memory risk any time soon (~4,000 rows / 1.3 MB at 90
days), but an unbounded store is how the change log got into trouble, and it is cheap to fix now.

**Included in this port:** a small `dnc_claims_prune`, the same shape as the change-log prune —
filtered read (`claimed_at < cutoff`) so it never scans the table, capped deletions, outcome
counting, and a family-aware retention (90 days for alert families, 7 days for dedupe families,
which only need to outlive the reconcilers' 48-hour lookback).

---

## 4. What the migration writes

Exact, read from `GET /workflows/{id}` (which does return `staticData`):

| Store | Rows | Family | Notes |
|---|---:|---|---|
| `wf2_seen` | **94** | `wf2_seen` | 47 dedupe keys + 47 first-SENT memos, all aged 1.8 days |
| `__alert_delivered` | **11** | `wf2_alert` | 4 ISO values normalised; 3 key shapes preserved (person id, legacy lead id, email) |
| `wf2_bounce_seen` | **0** | `wf2_bounce` | genuinely empty — the store prunes to ≤24 h |
| **Total** | **105** | | |

**Zero bounce rows is the right answer, not a failed read.** I got that wrong once preparing this —
read the top level instead of `global`, saw zeros everywhere, and would have migrated nothing while
reporting success. The migration script asserts `global` is a non-empty object before believing any
count, and refuses to run otherwise.

---

## 5. The build

**Three stores in WF-2 → ~9 nodes**, family-scoped rows in `euyostwJYfJefItC`, one shared helper
embedded from a single source file:

| | Key node | Read | Decide | Claim |
|---|---|---|---|---|
| alert registry | after `Merge Reply Ctx` | `get`, `anyCondition` on current **and** legacy key | `First Reply Gate` reads the row | after `Reply Alert`, gated on `ok === true` and the team channel |
| duplicate guard | after `Normalize` | `get` on the dedupe key | `Dedupe` reads the row | at the four existing success terminals |
| bounce memory | **before** `Normalize` (the key is derived inside it, so it is lifted out — the same split WF-1 used) | `get` on `{email}\|{campaign}` | `Normalize` reads the row | after the bounce is processed |

**Plus WF-1's duplicate-lead guard — folded in, as you asked.** `Lead Search → Lead Create Gate →
Create Lead` is check-then-act with nothing atomic between the read and the write. The guard is a
claim on `lead|{person_id}|{campaign}` taken before the create; a second concurrent execution finds
the claim and takes the existing-lead path. Same table, same helper, ~3 nodes. Observed instances of
that race: **zero** (the one duplicate in 2,132 campaign leads was not WF-1's create) — it is being
closed because it is the same class, not because it is burning.

**Carried over from WF-1, all deliberate:** positive shape check (an echoed input item carries the
key, so "did a row come back" would read an outage as *already handled*); fail open with an explicit
`dt_unavailable_fail_open` marker; claim after the effect is proven, never at decision time; legacy
keys honoured on read and never written back.

**Nothing is removed.** Every staticData write stays in place as the rollback copy.

## 6. The statics

| # | Assertion | Where it runs |
|---|---|---|
| 1 | concurrent executions with distinct keys **all** persist | offline, against the helper |
| 2 | same key twice → the second reads *already handled* | offline |
| 3 | **redeploy → state survives** | `DEV__` twin, scratch family |
| 4 | table echoes the input → **fail open**, never *already handled* | offline |
| 5 | *(added)* a non-parsable `claimed_at` reads as UNKNOWN and is reported, never retained silently | offline |

**Built and passing already — 37 assertions, `WF_SHARED/claims.js` + `test_claims.js`.** Statics 1,
2, 4, 5 are green offline; the live half of static 3 runs on the twin. Three of them are run against
**two models side by side** — the table, and a read-modify-write model of staticData — so the suite
does not merely show the new code works, it shows the old mechanism **cannot** pass: replaying the
28 Aug commit order, staticData keeps **1 of 4** claims and the table keeps **4 of 4**.

Two things the statics settled that I would otherwise have had to guess:

- **The naive check would have swallowed events.** The suite asserts that `!item.error` reads an
  echoed input item as *already handled*. That is the exact failure the positive shape check exists
  to stop, and it is now a test rather than a comment.
- **A pre-flight check the statics implied.** Under the new arithmetic a *numeric* `claimed_at`
  reads as corrupt and would be pruned. All 565 existing rows are ISO (`2026-08-05T03:33:03.317Z`
  … `2026-09-03T12:10:00.579Z`), so this is safe today — but the prune will not be deployed until a
  read asserts that **every** row's `claimed_at` parses. It refuses to run otherwise.

---

## 7. The other four stores — sweep, with measured exposure

| Store | Written by | Ran in the observed collision? | Cost of a lost write |
|---|---|---|---|
| `__auth_suppressed` / `__auth_warn_at` | `Verify Secret` | **yes, all 4 executions** | one extra, or one missing, bad-secret warning. Cosmetic |
| `__event_aliases_seen` | `Event Alias Watch` | **yes, all 4** | one duplicate ops warning about a new event name. Cosmetic |
| `wf2_bounce_counter` | `Bounce Counter` | no (no bounce in that window) | an undercounted bounce statistic. It is **currently absent entirely**, so it has either never been written or was lost |
| `wf1_*` in WF-1 | already ported this morning | — | — |

**Every one of them is exposed** — they share the one object — but the cost of each is a cosmetic
message or a soft statistic, none is customer-visible, and none gates a write. **Recommendation:
leave them on staticData and record the exposure**, rather than adding nodes to a 174-node workflow
for a duplicate warning. The one worth a second look is `wf2_bounce_counter`, which is missing
altogether when the code says it should exist.

---

## 8. Order of operations, on your word

1. Build the shared helper + statics 1, 2, 4, 5; all must pass offline.
2. `DEV__` twin: static 3 (redeploy survival) against a scratch family. Delete the twin.
3. **Migrate the 105 rows first, then deploy the code — same window.** Migration first, or everyone
   in those stores is re-announced in the gap.
4. Read back: assert 105 rows by family, assert the 4 normalised values parse.
5. Deploy the WF-1 duplicate-lead guard and `dnc_claims_prune`.
6. Post-fire: re-read, re-run every static, report.

**Rollback:** restore each workflow from `backups/`. The staticData stores are untouched and remain
authoritative for the old code; the migrated rows go inert and age out under the new prune.

---

## 9. What changed since the last artifact

- WF-2R throttle **deployed** (§0).
- The overlap is no longer a projection — **the collision is measured** (§1), and it loses whole
  execution deltas rather than single keys.
- The immortal entries are **named**: 3 real people, first harm date ~9 Nov (§2).
- **New finding:** the claims table has no retention and the WF-1 port dropped the 90-day bound —
  a prune is now part of this work (§3).
- WF-1's duplicate-lead guard folded in (§5).
- Statics: 4 → 5 (§6).

**Nothing else is deployed. Say go and I will build, rehearse on a twin, migrate and fire — then
come back with the post-fire numbers.**
