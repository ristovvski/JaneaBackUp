# Wave 1 — `dnc_intent_vs_reality`: what the registry actually achieved

**Built and fired 2026-09-02.** Read-only — every provider call is a GET. Nothing was written to
Pipedrive, Smartlead or the registry.

**Workflow:** `dnc_intent_vs_reality`, id `tnW7agCbha7rhNnS`, ACTIVE, webhook-only (no schedule).
**Run it:** `POST /webhook/{{WEBHOOK_DNC_INTENT_VS_REALITY}}` with
`{"mode":"sample","target":1000,"offset":0,"limit":50}` — the driver is
`WAVE1_2026-09-02/build_intent_vs_reality.py` plus `ivr_run.py`.

---

## 0. The number that reframes everything

**The registry holds 25,653 active rows.** The class map estimated ~4,800; that was wrong by 5×.

More important than the size is the shape:

| | sampled (n=1,000) | share | estimated rows |
|---|---:|---:|---:|
| has a Pipedrive person id | 115 | 11.5% | **~2,950** |
| has an email | 65 | 6.5% | **~1,667** |
| **has NEITHER** | **883** | **88.3%** | **~22,652** |

By what put them on the list: **941 of 1,000 sampled rows are `manual_offboard_eligible`** —
the bulk LinkedIn-connections import. Those rows carry a LinkedIn URL and nothing else.

**A row with no person id cannot be projected to Pipedrive. A row with no email cannot be
projected to Smartlead. And there is no HeyReach write path at all.** So roughly **22,650 rows —
88% of the do-not-contact registry — are unenforceable by any mechanism that exists today**, and
flipping the projection switches will not touch them.

That is the finding. The switches are worth turning on, but they are not the problem.

---

## 1. The four buckets you asked for

Systematic sample, **1,000 of 25,653 active rows**, every 25th row so the sample spans the whole
insertion history rather than one end of it. 20 chunks of 50, zero failed chunks. Wilson 95%
intervals.

### Pipedrive — is the person's DNC field actually set?

| bucket | sampled | share | 95% CI | est. of 25,653 |
|---|---:|---:|---|---:|
| claims done + **IS** done | 93 | 9.3% | 7.7 – 11.3% | ~2,386 |
| claims done + **ISN'T** — the liars | **0** | 0.0% | 0.0 – 0.4% | **~0** |
| claims pending + **already done** | 0 | 0.0% | 0.0 – 0.4% | ~0 |
| claims pending + **isn't** — the real backlog | 22 | 2.2% | 1.5 – 3.3% | **~564** |
| uncheckable (no person id on the row) | 885 | 88.5% | 86.4 – 90.3% | ~22,703 |

### Smartlead — is the lead unsubscribed, or absent from Smartlead entirely?

| bucket | sampled | share | 95% CI | est. of 25,653 |
|---|---:|---:|---|---:|
| claims done + **IS** done | 0 | 0.0% | 0.0 – 0.4% | ~0 |
| claims done + **ISN'T** — the liars | **0** | 0.0% | 0.0 – 0.4% | **~0** |
| claims pending + **already done** | 25 | 2.5% | 1.7 – 3.7% | ~641 |
| claims pending + **isn't** — the real backlog | 40 | 4.0% | 3.0 – 5.4% | **~1,026** |
| uncheckable (no email on the row) | 935 | 93.5% | 91.8 – 94.9% | ~23,986 |

### The same numbers, restricted to rows that can actually be checked

The whole-registry percentages are dominated by the unenforceable 88%. These are the rates that
decide the switch:

**Pipedrive — among the ~2,950 rows that have a person id**

| | sampled | rate | estimated rows |
|---|---:|---:|---:|
| DNC field already set | 93 | **81%** | ~2,386 |
| DNC field missing → **the real backlog** | 22 | **19%** (CI 13–27%) | **~564** (CI 383 – 804) |

**Smartlead — among the ~1,667 rows that have an email**

| | sampled | rate | estimated rows |
|---|---:|---:|---:|
| already unsubscribed | 2 | 3% | ~51 |
| not in Smartlead at all | 23 | 35% | ~590 |
| **still CONTACTABLE** | **40** | **62%** (CI 49–72%) | **~1,026** (CI 823 – 1,207) |

---

## 2. Two things worth saying plainly

### 2.1 There are no liars. Zero, in both directions.

Every row that claims `done` for Pipedrive **is** done — 93 for 93. Every row that claims `pending`
and has a person id **is** missing the field — 22 for 22. The Smartlead claim has never been set to
`done` by anything, and indeed nothing has ever projected to Smartlead.

`projections_state` is a trustworthy ledger. It has simply never been *acted on* by a live sweep in
the retention window. That is a much better starting position than the alternative — you are not
repairing corrupted state, you are running a backlog.

*(The 93 Pipedrive rows that claim and are `done` predate the 19-day execution window, so the sweep
did run at some point before 14 August and did it correctly.)*

### 2.2 The 40 still-contactable people are not edge cases

| what put them on the registry | count |
|---|---:|
| `negative_reply` / `reply_dnc` — **they replied and said no** | **25** |
| `employee_connection` / `manual_offboard_eligible` | 8 |
| `negative_reply` / `meeting_dnc` | 4 |
| `replied` / `meeting_dnc` | 3 |

**32 of the 40 are people who engaged with us and declined, or who booked a meeting.** They are
sitting in Smartlead in a contactable state right now. Extrapolated, that is roughly **820 people
who told us no and can still be emailed.**

Sample of the actual rows (full list in `ivr_result.json`):

```
pii-0b601cba@example.invalid                negative_reply / reply_dnc     2026-08-07
pii-f153f311@example.invalid                 negative_reply / reply_dnc     2026-08-07
pii-b8732314@example.invalid         negative_reply / reply_dnc     2026-08-07
pii-72db5a8f@example.invalid              replied        / meeting_dnc   2026-08-07
pii-bcf33a8f@example.invalid   negative_reply / reply_dnc     2025-07-01
pii-d90dcdf9@example.invalid                negative_reply / reply_dnc     2026-08-28
```

---

## 3. The decision, with the numbers attached

### `FIRE_PIPEDRIVE` → **turn it on.** Recommended.

- **Blast radius:** ~564 person records get a custom field set. CI 383–804.
- **Reversible:** yes — a custom field can be cleared.
- **Evidence quality:** the ledger's claim is 100% accurate on this population, so the sweep will
  target exactly the right rows.
- **Caveat:** the sweep also unions the DNC label onto any open lead. That is additive and matches
  the estate's "labels only accumulate" rule.

### `FIRE_SMARTLEAD` → **turn it on, but not on the whole population at once.**

- **Blast radius:** ~1,026 unsubscribes. CI 823–1,207.
- **Irreversible:** a Smartlead unsubscribe cannot be undone via the API. This is a one-way door.
- **But:** 62% of the checkable population is still contactable, and 80% of those are people who
  explicitly declined. Leaving it is the larger risk.
- **Recommendation:** run it in two passes.
  1. **`reply_dnc` + `meeting_dnc` first** — ~32 of every 40, people who engaged and declined. These
     are unambiguous and should already have been unsubscribed.
  2. **`manual_offboard_eligible` second, and only if you want it** — 8 of 40. That reason means
     "a departing employee's LinkedIn connection", which is a much weaker claim on a cold-email
     suppression. Worth Melisa's word before it fires.
- Whichever pass runs, **read back afterwards**: a Smartlead add can report success on an add that
  did not happen for an unsubscribed lead, so the reverse deserves the same distrust. Re-running
  this workflow after the sweep is the read-back.

### The thing neither switch fixes

~22,650 rows have no email and no person id. They came from the LinkedIn connections import and can
only ever be enforced inside HeyReach, where **no write path exists in either direction**. Until
that is built, 88% of the registry is a record, not a control. That is a separate decision and it
is bigger than Wave 1.

---

## 4. How the number was obtained, and what would make it better

- **Sample, not census.** 1,000 of 25,653, systematic with stride 25. A full walk is ~51,000
  provider GETs, ~3 hours, and re-reads all 25,653 rows per chunk — the burst shape that has OOM'd
  this instance before. The sample gives ±3% on the whole-registry rates and ±11% on the Smartlead
  conditional rate, which is enough to decide but not enough to hand someone a list.
- **Before you fire the Smartlead pass, get the exact list**, not an estimate: run the same workflow
  in sequential mode (`{"offset":0,"limit":50}` with no `mode`) across the ~1,667 rows that have an
  email. That is ~34 calls, about 20 minutes, and it names every person instead of estimating how
  many there are.
- **The check is honest about not knowing.** Both HTTP nodes use `fullResponse`, so a 5xx, an auth
  failure or a rate limit reads as `uncheckable`, never as "not there". Zero chunks failed in this
  run, and the `uncheckable` counts are entirely `no_person_id_on_row` / `no_email_on_row` — not one
  provider error. The numbers above are not hiding a failed read.
