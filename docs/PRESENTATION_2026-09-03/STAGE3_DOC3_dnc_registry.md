# Domain 3 — The do-not-contact registry

*Definition, capture sources, the gate, the projections, and what actually reaches whom.*
*State read live 2026-09-03. Where a number came from a measurement, the measurement is named.*

---

## 1. What the registry is

One table holding **one row per person we must not put into a cold campaign — and the reason why.**

The reason is the point. *"Don't email Barry"* is a fact. *"Barry replied on 12 August and Toby now
owns that relationship"* is a fact you can act on, defend, and eventually retire.

### What belongs on it

| Belongs | Because |
|---|---|
| **they replied** | a response creates a relationship |
| **they booked a meeting** | deeper engagement than a reply |
| **a salesperson owns them** (hand-created or Surfe leads) | a colleague already has the relationship |
| **imported LinkedIn connections** | a departing colleague's network |
| **explicit opt-outs** | they told us to stop |

### What does not

**Contact-only rows.** *"We emailed them once"* is not a relationship and does not protect anyone.
That was the 26 August ruling, and the rows whose only reason was contact were retired by hand.
It is also why `dnc_s4_event_populations` — the bulk campaign loader that files exactly that
signal — is now archived.

### Strength, strongest first
explicit opt-out **5** → negative reply **4** → replied **3** → employee connection **2** →
manual **1**. Strength **never downgrades**: a weaker later signal cannot demote a stronger earlier
one.

### Reason priority, strongest first
client → unsubscribe → meeting → reply-DNC → sales personal outreach → manual offboard-eligible →
event contacted → manual sheet → offboard. When two reasons meet the stronger wins, and **the loser
is kept** in a secondary field so an offboarding scan can still see it.

## 2. Entries do not expire

Time-based expiry was retired on 31 August. The expiry function returns nothing for every entry
type; the rows that carried an expiry date were cleared; the ageing job is archived.

The reasoning is in the code: a six-month timer on *replied* and *negative reply* put a countdown on
exactly the rows that represent a response — it said the response stops mattering, which is
backwards. **Retention is by reason now, not by clock.** Rows are retired explicitly, by a human,
using the retirement tool.

## 3. One writer, always

**`DNC__UpsertLedger__v1` is the only thing that writes the registry.** It is marked inactive, which
is correct for a sub-workflow — n8n only requires the *caller* to be active. It has run **3,500+
times in 20 days**. Do not switch it on.

Every write goes through the same decision:

```
normalise the identity → look up by LinkedIn → look up by email
   │
   ├─ two different people?  → CONFLICT: alert a human, write nothing
   │     └─ unless it is the one corroborated shape: a LinkedIn-only import row
   │        with no email and no person id, against a row that has a person id,
   │        AND the names match → one person split in two, merged
   ├─ nobody matched         → INSERT
   ├─ matched, changed       → UPDATE onto the strongest row, de-duplicating
   └─ matched, unchanged     → NO-OP
```

**Consequences worth remembering.** Calling it twice with the same signal is safe. Identity fields
fill in but never overwrite. A new signal reactivates a retired row. **A conflict is a human
decision, not a bug** — auto-merging two different real people would be a data-integrity incident.

**Two real failures in the window, both worth chasing:**
- **18 Aug — `invalid reason meeting_dnc`.** A caller sent a reason the writer did not recognise, on
  the same day the meeting capture source failed. *Open question: has the meeting source ever
  successfully written a row?*
- **20 Aug — Slack `channel_not_found` on its conflict alert.** A conflict alert that cannot be
  delivered is a human decision nobody was asked to make.

## 4. The capture sources — and which actually run

All share one shape: a switch, a classifier, a Pipedrive lookup for a usable identity, and a call to
the writer. **Dry-run is the default.**

| Source | What it captures | Switch | Reality |
|---|---|---|---|
| **S1** responded → DNC | a supplied list of people who replied | `FIRE_S1` **false** | hand-fired, last 18 Aug |
| **S2** meeting → DNC | people who booked a meeting | `FIRE_S2` **false** | hand-fired, last 18 Aug, 1 error |
| **S3** creation watcher | leads a salesperson created by hand, or from Surfe | `FIRE_S3` **TRUE** | **every 15 min, 1,920 runs** |
| S3 backfill | the same, historically | false | archived |
| S4 event populations | everyone in a campaign — *contact-only* | false | archived; no longer part of the definition |
| archived-responders import | a validated CSV of past responders | dry-run default | 2 runs, 28 Aug |
| LinkedIn-reply bridge | a LinkedIn reply | — | **never ran, nothing calls it** |
| sheet intake | a spreadsheet a human fills in | — | never ran |

> **Of the ways a person can get onto the registry, exactly one runs by itself and is allowed to
> write: the creation watcher.**

### What the creation watcher can and cannot see
It reads the **newest 100 Pipedrive leads** every 15 minutes and remembers what it saw last time.
Keeps a lead if the creator is one of eight named sales users or the channel is Surfe; rejects
automation writes, web-form leads and Memurai leads.

Two limits that belong on a slide:
- **forward-only** — if it falls behind, leads can pass out of the 100-lead window unseen. An audit
  of "new rows" measures the backfill, not a rate;
- **lead-shaped** — a person created without a lead is invisible to it, and Pipedrive persons carry
  no creator field, so no equivalent watch is possible.

It posts a nightly heartbeat at 23:55 so a silent failure is visible.

## 5. The gate — the only preventive control

POST a list of people; get a verdict per row, synchronously, up to 500 rows.

| Verdict | Meaning |
|---|---|
| **`OWN_TEAM`** | an `@janeasystems.com` address — exclude from any list |
| **`UNRESOLVABLE`** | no usable email and no usable LinkedIn URL |
| **`BLOCKED`** | an active registry row exists; the reason is returned |
| **`CLEAN`** | no row, or only retired ones — and it says what it used to be |

It is a **pure read** — no CRM, no sending tool — so ask as often as you like. Its monitor sends it
two rows whose answers are known every 15 minutes and alerts **once when it breaks and once when it
recovers**, plus a daily heartbeat.

**Over 500 rows returns an explicit error.** The old queue, which answered *"queued, come back
later"* for batches it could never process, was removed on 2 September; `retrieve` now returns an
explicit error rather than *pending* forever.

**The quiet risk to know about:** a registry read that *succeeds and returns nothing* makes every row
`CLEAN`. Nothing asserts the registry is non-empty. The 15-minute monitor is the only thing standing
between that and a fully open gate — it is carrying more weight than its size suggests.

## 6. Projections — what happens today

Being on the registry should have consequences in the tools. That bridge is
`dnc_projections_sweep`, and **today is the first time it fires.**

| Target | What it does | Status |
|---|---|---|
| **Pipedrive** | set the do-not-contact field on the person; union the label onto any open lead | **approved and firing today — ~564 rows** |
| **Smartlead** | resolve the lead by email and unsubscribe | **approved for negative-reply and meeting rows only — pending the exact list** |
| **HeyReach** | nothing; only a counter of what is pending | **no write path exists at all** |

Both label writes are **unions**, never replacements. Each row is marked done — or marked with its
write error — per target independently.

**The Smartlead leg is a one-way door.** An unsubscribe cannot be undone through the API. Confirm
the list before firing, and read back afterwards: a Smartlead call can report success on something
that did not happen.

## 7. The measurement that sizes all of this

`dnc_intent_vs_reality` asserts the consequence in Pipedrive and Smartlead and compares it against
what each row claims about itself. On **2026-09-02**, a systematic 1,000-row sample of **25,653
active rows**:

| Finding | Number |
|---|---|
| **No false claims, either direction** | 93 of 93 rows claiming "done" in Pipedrive were done; 22 of 22 claiming pending were genuinely missing |
| Pipedrive backlog | **~564 rows** (19% of the ~2,950 that have a person id) |
| **Still contactable in Smartlead** | **62%** of the ~1,667 rows that have an email → **~1,026 people** |
| Of the still-contactable found | **32 of every 40 had replied and declined, or booked a meeting** |
| **Rows with neither an email nor a person id** | **88.3% — about 22,650 rows** |

**Read that last line twice.** Most of the registry is the bulk LinkedIn-connections import: a
LinkedIn URL and nothing else. A row with no person id cannot be projected to Pipedrive; a row with
no email cannot be projected to Smartlead; and there is no HeyReach write path. **Turning both
switches on is right, and it touches roughly 6% of the list.** The other 88% is a record, not a
control — and that is a separate, larger decision.

**The good news in that table:** the registry's own bookkeeping never lied. You are not repairing
corrupted state; you are running a backlog.

## 8. What actually stops a send today

1. **The gate** — preventive, but only if the person building the list asks it.
2. **The hourly escalation detector** — cross-references live cold campaigns against the registry and
   shouts if a protected person is in one. **Detective, not preventive**, capped at 500 leads per
   campaign, and it says so when a campaign is bigger.
3. **WF-2's own reply path** — unsubscribes directly when a reply says stop. Immediate, and entirely
   independent of the registry.
4. **From today, the projector** — Pipedrive leg live, Smartlead leg pending the list.

## 9. Operating it

- **Ask before you send:** POST your list to the gate, ≤500 rows per call.
- **Retire someone:** the retirement tool, `dry_run: false` required explicitly. No undo — re-adding
  means re-filing through the writer.
- **Import a list:** the archived-responders importer refuses the whole batch if any row has an
  unknown reason, a reply-DNC with no category, or no identifier at all.
- **Turn a capture source on:** flip its switch, fire once, read the dry-run report first.
- **Check whether protection is real:** run `dnc_intent_vs_reality`. Sample mode for rates, sequential
  mode to name every affected person.

## 10. The map

```
S1 ─┐  (dry-run)
S2 ─┤  (dry-run)
S3 ─┼──► DNC__UpsertLedger__v1 ──► the registry (25,653 active rows)
import ─┘   single writer,              │
            idempotent                  ├──► dnc_pre_add_gate ......... "may I contact?"  PREVENTIVE
                                        ├──► dnc_escalation_detector .. hourly            DETECTIVE
                                        ├──► dnc_morning_digest ....... counts
                                        ├──► dnc_intent_vs_reality .... does it actually hold?
                                        └──► dnc_projections_sweep
                                                  ├──► Pipedrive  FIRING TODAY (~564)
                                                  ├──► Smartlead  approved, list pending
                                                  └──✗ HeyReach   no path exists

WF-2 ──✗──► the registry     (it labels and unsubscribes directly, writes no row)
WF-1 ──✗──► the registry     (LinkedIn replies never reach it)
```

## 11. And alongside it — the CRM change log

Not part of the registry, but the other thing people mean by "how do we know what happened".

**I-04 is a change log now, not a reporting system.** The event receiver still records every
Pipedrive lead and person change — silently, no summaries, no alerts. The daily summary and the
weekly reconciliation were retired today.

- **215 events a day**, ~3.4 KB each → **~62 MB at 90-day retention**
- a prune keeps 90 days; it is a **no-op until ~24 November**, because nothing is that old yet
- **what we lose:** automatic detection of bulk changes — the summary used to flag ten or more
  distinct leads updated in the same minute, which is how a label-wiping automation was caught before
- **what we keep:** *who changed this, and when* — answerable for 90 days, by anyone who asks
- **what was never true:** departures inside a window with no snapshot were never recoverable. The
  weekly sweep was the only thing that could have caught them, and it never ran once. That limit is
  now explicit instead of implied by a workflow that looked like it covered it.
