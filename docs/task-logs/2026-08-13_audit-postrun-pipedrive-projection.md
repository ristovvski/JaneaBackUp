# Auditor POST-RUN — Pipedrive DNC projection. Measured 2026-08-13T05:25Z.

Read-only, independent of the sweep's own reporting. Anchors frozen before any write:
`i1_labelsnap.json` (57,848 leads, full label map, 5 carrying DO NOT CONTACT — captured twice,
agreeing) and `j1_incident_count.json` (the 2,010 person ids written before the crash).
Evidence: `m1_postrun.json`, `m2_orphans.json`.

**VERDICT: coverage PASS, label integrity PASS, one 1-lead gap to explain, and one prediction in the
plan is falsified — the spitz event is orphaned, not pending.**

---

## 1. Coverage — Stage 1 exact, Stage 2 one short

| | measured | claimed / target | verdict |
|---|---|---|---|
| persons carrying `DNC Status = 686` | **2,262** | 2,262 written (+2 skipped) | **exact, shortfall 0** |
| — of those, written pre-crash | 2,010 | | |
| — written after the crash | **252** | | 2,010 + 252 = 2,262 ✓ |
| **pre-crash persons that REGRESSED** | **0** | | idempotency confirmed at outcome level |
| leads carrying `DO NOT CONTACT` | **1,982** | | |
| — **gained vs the 5-anchor** | **1,977** | 1,978 with-lead | **99.9 %, one short** |
| — lost from the anchor | **0** | | |

2,293 persons were touched since 15:00Z; the 31 beyond the 2,262 are unrelated updates.

**The zero regressions matter independently of coverage:** the re-fire re-PATCHed rows that already
carried 686 and not one of them came back changed or cleared. That is the outcome-level proof of the
set semantics — the one the changelog could not give us, since Pipedrive suppresses no-op rows.

## 2. Label-loss watch — CLEAN

```
leads present in both snapshots that LOST >=1 label : 0
leads in the snapshot now ABSENT (archived/deleted) : 0
leads walked: 57,855  (snapshot had 57,848; +7 new)
```

Zero label losses across a 1,977-lead union write. No wiper activity, no collateral damage.

**This also retires the caveat I attached to the snapshot.** It straddled the write boundary, which
could only ever have produced *false positives* — and there were none. The dirty baseline cost nothing.

## 3. The 1-lead gap — three candidates, one request

1,977 gained against a 1,978 target. Candidates, in order of likelihood:

1. **One of the 2 deleted persons sat in the with-lead bucket.** Then 1,977 is correct and expected,
   and the target should read 1,977 + 1 skipped.
2. **The lead is archived.** My walk is a list read, and `archived_status` is silently ignored by
   `/v1/leads` — an archived lead carrying the label is invisible to me by construction.
3. A genuine miss.

**To resolve:** the 2 `skipped:deleted_person` row ids, and ideally the sweep's per-row outcome list.
Two detail reads settle candidate 1; the same ids settle candidate 2. I did not guess between them.

## 4. FALSIFIED: "spitz — unclaimed per P0-1b, WF-2S picks it up on cycle, no manual action"

The P0-1b half is right. The WF-2S half is wrong, and **the event is orphaned**.

```
exec 15949   error   2026-08-12T15:45:45.986Z -> 15:56:57.843Z
  died at:   Person Patch — "The connection timed out"
  event:     SENT · campaign 3686181 · pii-0ddf11ef@example.invalid
  stats_id:  f826809a-8ac1-4ac2-a846-708a73e26f2d
  dedupe:    SENT|3686181|4259023636|1786545158182

  claimed in WF-2 wf2_seen?            NO   <- correct: P0-1b left it replayable
  claimed in WF-2S __sent_seen_v2?     YES  <- claimed 2026-08-12T14:32:38
```

**The two claim ledgers disagree.** WF-2 says "I never finished this, send it again." WF-2S says "I
already delivered this, I will not." The event falls into the gap between them, and 14 hours later no
replay has occurred — I searched every WF-2 execution since and there is exactly one spitz event, the
failed one.

**Root cause is structural, and it is the Marine flaw one layer up.** WF-2S's notion of "the replay
succeeded" is the webhook POST returning 200 — and WF-2's `Respond to Webhook` is node #2, answering
before any work is done. A downstream crash is therefore invisible to the reconciler. The
200-before-processing design defeated Smartlead's retry for Marine; here it defeats *our own*
reconciler.

**Blast radius, measured:** of 28 unclaimed reconciled replays in retention, **1 is orphaned** — this
one. The other 27 are still recoverable because WF-2S has not claimed them either, so it may re-push.
Worth confirming it actually does; if those 27 also fail to reappear, the population is 28, not 1.

**Fix shape (theirs to choose):** WF-2S must claim on WF-2's *completion*, not on the POST's status —
either WF-2 signals completion back, or WF-2S verifies the outcome (lead present / event processed)
before claiming, or both workflows share one claim store written only at WF-2's terminal.

**Manual action IS required for spitz**, contrary to the plan: nothing will re-deliver it.

## 5. Protocol library — the fifth instance, and arguably a sixth

Filed: **n8n `onError: continueErrorOutput` with an UNWIRED error output** — failing items vanish and
the execution reports success. Caught by the DNC session's own read-back.

| # | claimed success | actual outcome |
|---|---|---|
| 1 | n8n execution `success` | `Reply Alert` returned `{"error":"invalid syntax"}` — 11 days of unsent alerts |
| 2 | WF-2S reported `__idle: true` | structurally blind; 176 SENT events unseen |
| 3 | staticData claim written by the node | clobbered by an overlapping execution — 42/55 and 15/15 lost |
| 4 | Smartlead add returns `ok:true` | no lead lands; unsubscribed leads silently un-addable |
| 5 | execution `success` with unwired error output | failing items vanish; "0 errors" digest line was fiction |
| **6** | **WF-2S records a successful replay** | **WF-2 crashed after the 200; event orphaned (this report)** |

Five of the six were found the same way: **never accept a system's self-report as evidence of its own
effect — verify from the other side.** #6 is the sharpest form yet, because here the self-report came
from *our own reconciler*, the component whose entire job is to be the safety net.

## 6. What I am NOT reporting

- The 2 skips are **unverified** — I can confirm them in two calls once I have the ids, and I would
  rather leave the line open than assert a number I did not check.
- Stage-2 coverage is measured against non-archived leads only; if the projection labelled an archived
  lead, I cannot see it.
