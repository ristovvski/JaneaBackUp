# §9f.2 pre-posts — the four production writes (2026-09-08)

Files only, no Slack. One section per item, written **before** the corresponding write.

---

## 1. DIGEST FIX — `dnc_morning_digest` `No Match Count`

**Scope:** one workflow, one node, one line. No records, no CRM, no provider calls.
`qJKfR602wV9yfFrj`, live version `491f65b8`, 40 nodes, ACTIVE.

### The decision, and why the auditor's preference was wrong

The handoff offered two candidates and preferred **(b) "drop the `...prev` spread and return only
the `no_match_*` fields, letting `Compose` assemble."**

**(b) would have silently emptied the digest.** Measured, not argued:

* `Compose` consumes **37** fields off its input item — `d.__sl`, `d.pd_by_source`,
  `d.changelog_24h`, `d.missed`, `d.gate_healthy`, `d.dnc_active`, …
* `No Match Count` produces **3** of them: `no_match_24h`, `__nomatch_readable`, `__nomatch_error`.
* The other **34** exist only because every code node in this chain spreads its predecessor's
  object forward: `Changelog Count` spreads `$('Sched Agg')`, `Sched Agg` spreads
  `$('Pick Scheduled')`, back to `Window`.

Drop the spread and the digest still runs, still posts, still looks green — with every section
reading `n/a`. That is the estate's signature failure, not a fix.

### What is actually changing

```diff
- const prev = $('I04 Status').first().json;
+ const prev = $('Changelog Count').first().json;
```

`Changelog Count` is the code node immediately upstream of the `Ops Channel History` HTTP call, and
its own header comment already reads *"Replaces the old `I04 Status`"*. The 3 Sep simplification
swapped the node and left this by-name reader pointing at the corpse. B12 verbatim: `$json` does not
survive an HTTP node, so context is recovered from the node that OWNS it — and when that node is
replaced, every by-name reader has to be re-pointed with it.

### What the line now reports

Unchanged in meaning: **`no_match_24h`** — "no match found" warnings in the ops channel over the
window, counted and never re-posted. The dead reference was never the no-match count; it was the
carrier of everything accumulated before it.

The CRM change-log count is **already reported** and needs no new plumbing — `Changelog Count`
emits `changelog_24h` and `Compose` renders `CRM change log N events`. It reaches the post only once
the spread reads a node that exists. So the README's contract is satisfied by fixing the owner, not
by re-pointing the line at a different measurement.

### Statics — 5/5

```
readable, 2 hits                      -> no_match_24h=2, all 12 carried fields survive
unreadable history                    -> __nomatch_readable=false, context still carried
saturated history (200 msgs)          -> __history_saturated=true
non-vacuity: OLD code on same harness -> throws "unresolved node reference: I04 Status"
no `I04 Status` left in the CODE      -> asserted after comment-stripping
```

The non-vacuity case is the one that matters: without it, green statics prove only that the harness
is lenient.

### Verification after the write

1. `WF_LINTER/node_reference_resolves.js` over the estate — **must exit 0**.
2. Live re-read: new owner present, dead reference gone, node count unchanged, workflow still
   ACTIVE (a rejected PUT deactivates — the 2026-08-10 lesson).
3. Tomorrow 06:35: a digest that posts with real numbers instead of a WF-ERR alert. Five were lost;
   the sixth is the proof.

### Reversible

Full pre-write backup written to `digest_backup_before_dead_ref_<epoch>.json`. Rollback is a PUT of
that file.

---

## 2. AUTH-NOTICE STATE — `__auth_warn_at` → claims row `wf2_auth_notice`

**Scope:** WF-2 `jp7rum9Z0YDJkQWv`, live `5d4a5c97`, 191 nodes → **+4 nodes**, one node edited, one
link rewired. No records, no CRM, no provider calls. Fourth and last of the WF-2 staticData stores.

### What is wrong today

`Verify Secret` rate-limits its own warning with `sd.__auth_warn_at` / `sd.__auth_suppressed`.
staticData is persisted as **one object at execution end**, so overlapping executions each read the
same stale timestamp and each decide to warn — the 09-04 burst of 135 executions produced 135 posts.

### Shape

```
Verify Secret ─▶ IF Authentic                                   (processing path, untouched)
              └▶ DT Auth Notice Get ─▶ Auth Notice Decide ─▶ DT Auth Notice Claim
                                     ─▶ Auth Notice Ctx ─▶ IF Auth Warn ─▶ Ops Warn Bad Secret
```

State lives in the row's `evidence` as `{mode, last_posted_date, suppressed_since_last}`.

| signal | behaviour |
|---|---|
| `unconfigured` — traffic **accepted** | on mode change, then once a day |
| `missing` / `mismatch` — a **DROP** | every time; someone posting without the secret is not noise |
| `valid` after a noisy mode | exactly **one** closing post, so the channel shows resolution |
| `valid`, stable, or valid with no row | silent |
| row absent | post — first notice |
| table unreadable / echoed-input error shape | post — alert gates fail **OPEN** (§9b.0f) |

`suppressed_since_last` is carried into the post and reset on it; a quiet armed endpoint never
inflates it.

### Two decisions I am making, not inheriting

**Claim BEFORE post — the opposite of the alert registry's claim-after-delivery, on purpose.** For a
lead alert, claiming first risks silencing an alert nobody received: a lost lead. For flood control
the failure modes reverse — claim-after means a failed write re-posts on every subsequent event,
which *is* the flood being fixed, while claim-first at worst drops one infra notice that tomorrow's
heartbeat re-raises. Different data, different direction.

**`Verify Secret` keeps its two staticData writes, WRITE-ONLY, as the rollback copy** — matching what
the 3 Sep ports left in place. Nothing reads them. Deleting them is the second half of this port,
after a live burst has proven the row.

### Residual, stated rather than glossed

The row is atomic; the read-then-write is **not** a compare-and-swap (n8n's dataTable has no
conditional update). Two executions in the same instant can both see "not posted today" and both
post. This turns 135 posts into at most a rare 2 — it does not turn it into 1. Calling that "fixed"
would be the third time this estate mistook a narrowed window for a closed one.

### Statics — 16/16

12 decision cases (including both dataTable error shapes and the closing post), the B12 recovery
past the upsert, the rollback-copy assertion, and **two non-vacuity cases**: a burst of three
overlapping executions warns **3/3** on the old staticData path, and the same burst against the row
posts once then suppresses.

### Verification after the write

Live re-read asserts all four nodes present, `Verify Secret` no longer decides the warn, the old
direct link gone, `Ctx → IF Auth Warn` wired, node count exactly +4, workflow still ACTIVE.
Then: the row appears in the claims table on the next non-valid event, and `#alerts` shows one
notice a day instead of one per event.

### Reversible

`wf2_backup_before_auth_notice_<epoch>.json`; the staticData copy is still being written, so a
rollback PUT restores the old behaviour with its counters intact.

---

## 3. FIRE_PIPEDRIVE — §9f.2 PRE-POST, on a count measured today

Dev run: execution **48563**, `MODE="dev"`, both `FIRE_` gates false, **success**, 22 nodes,
13:40:28 → 13:51:31Z (11 min 2 s). Evidence `sweep_dev_counts_48563.json`.

Proved dark before firing: all **7** mutating nodes unreachable without a `FIRE_` gate's true
branch — `PD Write DNC Field`, `PD Patch Lead Labels`, `SL Unsubscribe`, and all four
`Mark Done` / `Mark Write Error` dataTable updates. Confirmed by the run: those nodes did not
execute.

### The number

| | |
|---|---|
| registry rows with a Pipedrive person | **2,847** |
| of those, `pipedrive: pending` — **the eligible set** | **580** |
| already `done` / `skipped` | 2,267 (chunk 10 of 12) |
| **one fire writes** | **250** — the `pd_chunk_size` cap |
| remaining after one fire | 330 → two more invocations (250 + 80) |
| within this chunk: person field **+ lead label union** | 224 |
| within this chunk: person field only (no open lead) | 26 |
| write errors in the dev pass | 0 |

The six-day-old estimate was ~564; measured today it is **580**. Close, but it is now a measurement.

**Note the shape of the ask:** confirming this fires **250**, not 580. Three invocations complete the
channel. I would rather run them as three confirmed windows than loop unattended.

### What changes per record

Person field `9c018b7406ebc481b9c108a487f76c4d09f91c9b` (`DNC Status`) → option **686**
(`dnc_active`). For the 224 with an open lead, the lead's label set additionally gains
`52a7c290-fc73-11f0-ad98-81d4703453f3` as a **union** — cumulative, nothing removed. No leads, no
persons, no Smartlead, no HeyReach.

### Post-verify — and I am changing the method

The handoff proposed "re-walk the 686 population and assert `after − before == rows_written`". I do
not trust a population delta as the primary assertion here: four label-wiper Zaps have written to
this exact field-and-label surface before, Melisa's automation is live on the same objects, and the
DNC-686 population is only confirmed to 27–28 Aug because the snapshot job stopped. A concurrent
change by another writer would either mask a failure or manufacture one.

So, primary assertion first:

1. **Per-record read-back of the exact ids written** — for each of the 250 person ids, read field
   `9c018b74…` and assert it equals `686`. Deterministic, immune to other writers. Chunked.
2. **`projections_state.pipedrive` flipped to `done`** for exactly those rows and no others — the
   registry's own claim must match the CRM.
3. **Label union preserved** on the 224 leads: the DNC label present *and* every pre-existing label
   still present (cumulative-label rule).
4. Population delta as a **secondary sanity check only**, reported with the caveat above.
5. Pre-write baseline of the 250 records' current field values, persisted, so rollback is a replay.

### Blocking finding — FIRE_SMARTLEAD must NOT be enabled as it stands

Not part of this confirmation, but the dev run measured it and it changes the plan:

| Smartlead | count |
|---|---|
| rows with an email | 8,582 |
| `smartlead: pending` | 1,548 |
| **resolved, would be unsubscribed** | **874** |
| already unsubscribed | 46 |
| not found in Smartlead | 628 |

**The sweep has no reason-based split.** `SL Filter Pending` → `SL Classify` →
`SL Filter Resolved Only` carry `identity_key`, `email_lc`, `projections_state` — and no `reason`.
The eligible set therefore includes the classes ruled **HOLD**: Person-d2a47603
(`reason: manual_offboard_eligible`, `entry_type: employee_connection`) resolves to Smartlead lead
`1410222726` and would be unsubscribed on a fire. Enabling `FIRE_SMARTLEAD` today would project
onto employee connections, and Smartlead unsubscribe is on the API-irreversible list.

Splitting by reason is a workflow change with its own pre-post. Flagging it here because "get the
exact list FIRST" now has its answer, and the answer is that the list is not yet safe to fire.

HeyReach: 32,425 eligible, parked, no live-write branch exists. Unchanged — doing nothing, as ruled.

### Defect found in the dev reporting

The dev summary posted to `#gtm-telemetry` reads:

> `DNC → Pipedrive: chunk 10/12 done` · `250 processed (224 labels, 26 field-only)` · `330 remaining` · `0 errors`

**Nothing was written.** The text says "done" and "processed" with no dry-run marker, so a reader
sees a completed projection chunk. That is this estate's signature failure moved into the reporting
layer — a message that reports success for work that did not happen. One-line fix (prefix the text
when `MODE !== 'live'`), and worth doing before the next dev run rather than after someone acts on
the post.

### Reversible

Yes, per record: the pre-write baseline holds every prior value, and a rollback is a replay of it.
