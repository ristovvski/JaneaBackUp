# Domain 3 — The do-not-contact registry

*Definition, capture sources, the gate, projections — and what is actually switched on.*
*State as read live from n8n on 2026-09-02.*

---

## 1. What the registry is

One n8n data table (`UOgKwlGsL28lX61O`) holding one row per person we must not put into a cold campaign — **and the reason why**. The reason is the point. "Don't email Barry" is a fact; "Barry replied on 12 Aug and Toby now owns that relationship" is a fact you can act on, defend, and eventually retire.

**A row records:**

| Field | Meaning |
|---|---|
| `identity_key`, `linkedin_url_norm`, `email_lc` | who — canonical LinkedIn URL and lower-cased email |
| `full_name`, `pipedrive_person_id` | who, in human and CRM terms |
| `entry_type` | how strong the signal is (see ladder below) |
| `reason`, `source_ref`, `also_flagged` | why, who/what caused it, and any weaker reasons also seen |
| `source` | which capture source(s) filed it — accumulates, never replaced |
| `status`, `added_at`, `removed_at`, `removed_reason` | lifecycle |
| `projections_state` | whether Pipedrive / Smartlead / HeyReach have been told |
| `correlation_id`, `norm_v` | traceability and the normalisation version used |

**Strength ladder** (never downgrades): explicit opt-out **5** → negative reply **4** → replied **3** → employee connection **2** → manual **1**.

**Reason priority** (0 is strongest): client → unsubscribe → meeting → reply-DNC → sales personal outreach → manual offboard-eligible → event contacted → manual sheet → offboard. When two reasons meet, the stronger wins and **the weaker is kept in `also_flagged`** rather than discarded.

## 2. Entries do not expire

Time-based expiry was retired on 2026-08-31. `computeExpiry()` returns `null` for every entry type; the 1,353 rows that carried an expiry were blanked; `dnc_expiry_job` is deactivated and preserved.

The reasoning is in the code: a six-month timer on *replied* and *negative reply* applied a countdown to precisely the rows that represent a response — it said the response stops mattering, which is backwards. **Retention is now reason-based**: the registry keeps replies, meetings, sales-created/Surfe leads, employee connections and explicit opt-outs, and rows whose only reason was "we contacted them once" get retired explicitly, by a human, via `dnc_s4_retirement_removal`.

## 3. One writer, always

**`DNC__UpsertLedger__v1` is the only thing that writes the registry.** It is marked inactive in n8n, which is correct and normal for a sub-workflow — n8n only requires the caller to be active. It has run over 3,000 times in the last 19 days. **Do not switch it on.**

Every write goes through the same decision:

```
normalise identity → look up by LinkedIn → look up by email
    │
    ├─ two different people?              → CONFLICT: alert a human, write nothing
    │     └─ unless it is the narrow split-identity case:
    │        one side a LinkedIn-only bulk-import row with no email and no person id,
    │        the other carrying a person id, AND the names corroborate
    │        → merge them, tombstone the loser
    ├─ nobody matched                     → INSERT
    ├─ matched, something changed         → UPDATE onto the strongest row,
    │                                       soft-remove any duplicates
    └─ matched, nothing changed           → NOOP
```

Consequences worth remembering:
- **Calling it twice with the same signal is safe** — the second call is a no-op.
- **Identity fields fill in but never overwrite.** A blank email gets filled; a wrong one does not get corrected here.
- **A new signal on a removed or expired row reactivates it** and resets `added_at`.
- **A conflict is a human decision, not a bug.** Auto-merging two different real people would be a data-integrity incident; the code refuses to do it except in the one corroborated shape above.

## 4. The capture sources — and which are actually on

Every source has the same skeleton: a `CONFIG` node with a `FIRE_Sn` boolean, a classifier, a Pipedrive person lookup to get a usable identity, and a call to the ledger. **Dry-run is the default. Nothing writes unless the switch is `true`.**

| Source | What it captures | Switch | Runs today |
|---|---|---|---|
| **S1** `dnc_s1_responded_to_dnc` | Pipedrive people who responded | `FIRE_S1` = **false** | hand-fired, last 18 Aug |
| **S2** `dnc_s2_meeting_to_dnc` | people who booked a meeting (label "5. Meeting" ∪ deal stage "Qualified Meeting Set", Memurai/partner pipeline excluded) | `FIRE_S2` = **false** | hand-fired, last 18 Aug |
| **S3** `dnc_s3_creation_watcher` | leads created by a named salesperson, or by Surfe | `FIRE_S3` = **TRUE** | **every 15 minutes** |
| **S3-backfill** `dnc_s3_surfe_backfill` | the same, historically | `FIRE_S3_BACKFILL` = **false** | never |
| **S4** `dnc_s4_event_populations` | everyone in a given Smartlead/HeyReach campaign ("we touched them once") | `FIRE_S4` = **false** | one bulk load, 14 Aug |
| `dnc_archived_responders_import` | a validated CSV of archived responders | `dry_run` default true | 2 runs, 28 Aug |
| `dnc_wf4_sheet_intake` | a Google Sheet a human fills in | inactive | never |
| `heyreach_reply_to_dnc_ledger` | a LinkedIn reply | inactive | never |

**Read that table twice. S3 is the only source writing to the registry.** Everything else needs a human to fire it, and most would produce a dry-run report if fired today.

### What S3 can and cannot see
S3 reads the **newest 100 Pipedrive leads** every 15 minutes, newest-first, and remembers the ids it saw last time. It keeps a lead if the creator is one of eight named sales users or the channel is `Surfe`, and rejects automation writes, web-form leads and Memurai leads.

Two limits that matter:
- **It is forward-only.** If it falls behind, leads can pass out of the 100-lead window unseen. An audit of "new rows" measures the backfill, not a rate.
- **It is lead-shaped.** A person created without a lead — or a person plus a deal — is invisible to it, and Pipedrive persons carry no creator field, so there is no equivalent watch for them.

It posts a heartbeat at 23:55 so a silent failure is visible.

## 5. The gate — the only preventive control

`dnc_pre_add_gate`, webhook `{{WEBHOOK_DNC_PRE_ADD_GATE}}`. POST a list of identities, get a verdict per row:

- **`OWN_TEAM`** — an `@janeasystems.com` address; exclude from any list
- **`UNRESOLVABLE`** — no usable email or LinkedIn URL; nothing can be matched
- **`BLOCKED`** — an active registry row exists; the reason is returned
- **`CLEAN`** — no row, or only retired ones (and it says what it used to be)

It is a pure read — no CRM, no sending tool — so you can ask it as often as you like. `dnc_pre_add_gate_monitor` fires a synthetic two-row check every 15 minutes and alerts **once when the gate breaks and once when it recovers**, plus a daily heartbeat.

### ⚠ The gate has a live trap: batches over 50 rows

The gate answers synchronously for **50 rows or fewer**. Above that it parks the batch in a table called `dnc_gate_queue`, replies `{"queued": N, "eta_minutes": …}`, and expects `dnc_gate_queue_drainer` to process it.

**The drainer has never run and is inactive**, and the monitor's own code states the `dnc_gate_queue` table does not exist. So a caller submitting 51–500 rows gets a confident "queued" and **never receives an answer**. Nothing alerts on it.

**Rule until this is fixed: send the gate at most 50 rows per call.** *(I could not verify table existence from the API — n8n does not expose data tables there — so confirm in the UI before acting on the "table does not exist" claim.)*

## 6. Projections — what is supposed to happen next, and does not

Being on the registry should have consequences in the tools:

| Target | What the projector would do | Status |
|---|---|---|
| Pipedrive | set the DNC field on the person; add the DNC label to any open lead (union, never replacing) | **not running** |
| Smartlead | resolve the lead by email and unsubscribe it | **not running** |
| HeyReach | nothing — there is only a counter of what is pending | **no write path exists at all** |

`dnc_projections_sweep` has **zero executions in the 19-day retention window** and its CONFIG carries `FIRE_PIPEDRIVE: false` and `FIRE_SMARTLEAD: false`. So even if someone invoked it today, it would report a dry run.

Every row the ledger has inserted since at least 14 August still carries `projections_state` = pending.

### So what actually stops a send today?

1. **The gate** — but only if the person building the list remembers to ask it.
2. **`dnc_escalation_detector`** — hourly, cross-references live Smartlead cold campaigns against the registry's active rows and posts every hit to ops. Nurture campaigns are excluded; it reads up to 500 leads per campaign and says so when a campaign is bigger than that. **This finds people who are already in a campaign. It does not stop them being added.**
3. **WF-2's own reply path** — unsubscribes in Smartlead directly when a reply classifies as do-not-contact. Effective, immediate, and completely independent of the registry.

**Plain statement for the deck: the registry is currently a well-maintained record with no automatic effect on the sending tools.** The enforcement is a manual gate call plus an hourly detector.

## 7. When something looks wrong

| What you see | What it means | What to do |
|---|---|---|
| Escalation alert: "X is on DNC and in campaign Y" | someone was added to a campaign without a gate check, or after being registered | remove them from the campaign; the alert names the entry type and reason |
| Gate says `queued` and nothing comes back | the over-50-row trap above | resend in batches of ≤ 50 |
| Gate monitor: "unhealthy" | the gate's synthetic check no longer returns 1 clean + 1 blocked | usually a registry read failure; the recovery alert will follow when it clears |
| A conflict alert from the ledger | one identity resolves to two different registry rows | a human decides; do not auto-merge |
| Registry count not growing | expected — only S3 writes, and only from new hand-created or Surfe leads | check S3's 23:55 heartbeat and the morning digest's DNC line |
| Someone was contacted who should not have been | check, in order: was the gate asked? is there a registry row? is it `active`? did the escalation detector see the campaign (is it >500 leads, or a nurture campaign)? |

## 8. If you need to change something

- **Retire rows:** `POST /webhook/{{WEBHOOK_DNC_S4_RETIREMENT}}` with `{"row_ids": [...], "dry_run": false}`. Dry-run is the default; you must pass `false` explicitly. There is no undo — re-adding means re-filing through the ledger.
- **Import a list:** `POST /webhook/{{WEBHOOK_DNC_ARCHIVED_IMPORT}}` with validated rows. It refuses the whole call if any row has an unknown reason, a `reply_dnc` without a category, or no email and no LinkedIn URL.
- **Turn a capture source on:** flip its `FIRE_Sn` in that workflow's CONFIG node. Fire it once with a small chunk and read the dry-run report first.
- **Turn projections on:** enable one target at a time, smallest chunk first. **The Smartlead half is irreversible** — an unsubscribe cannot be undone through the API. Confirm the candidate list before firing and read back afterwards.

## 9. Dependencies at a glance

```
S1 ─┐
S2 ─┤   (all dry-run except S3)
S3 ─┼──► DNC__UpsertLedger__v1 ──► registry table UOgKwlGsL28lX61O
S4 ─┤         (single writer,             │
import ─┘      idempotent)                │
                                          ├──► dnc_pre_add_gate ──► "may I contact?"  (preventive, manual)
                                          ├──► dnc_escalation_detector (hourly, detective)
                                          ├──► dnc_morning_digest (counts)
                                          └──✗ dnc_projections_sweep  (dormant: no runs, switches off)
                                                    │
                                                    ├──✗ Pipedrive DNC field + label
                                                    ├──✗ Smartlead unsubscribe
                                                    └──✗ HeyReach (no path exists)
```
