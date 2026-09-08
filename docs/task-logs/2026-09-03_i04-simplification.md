# 2026-09-03 — I-04 simplification

**Task:** keep the event receiver, retire the daily summary and the weekly reconciliation, add
retention, stop the morning digest reporting a dead component, sweep for other references, record
the decision. Nik's direction. No Slack used.

**Outputs:** `I04_SIMPLIFY_2026-09-03/` (report, builders, backups), `RULEBOOK.md` rule **R-G**,
banners across the affected docs.

---

## DONE

| Item | Result |
|---|---|
| 1. keep the receiver | **untouched — not written to at all.** ACTIVE, 5 nodes, `c0b702c4` |
| 2. retire the daily summary | 22 → 18 nodes (idle watchdog removed), **deactivated**, `d8827dda`. Last run 08:45Z; deactivation landed 08:47Z; nothing since |
| 3. unwire WF-2S | **NOT DONE — premise was wrong.** See below |
| 4. retire the weekly | already inactive → **verified by read, deliberately not written to**, preserved byte-for-byte |
| 5. retention | measured, then `dnc_i04_event_log_prune` built, deployed, armed, live-verified |
| 6. morning digest | `I-04 FAILING` → `CRM change log N events`, verified live at 208 events/24h |
| 7. orphaned tables | banners added to both table docs + the folder README |
| 8. rulebook | **R-G** added |
| sweep | **zero** references to either retired workflow anywhere in 40 workflows |

### Sizing (measured, throwaway read-only workflow, deleted after)
1,563 rows / 9 days · **215 events per complete day** · peak 484 · **~3.4 KB per row** ·
838 lead / 725 person · **projected ~19,400 rows / ~62 MB at 90 days**.
The prune is a **no-op until ~2026-11-24** — oldest row is 26 Aug. Live run confirms
`stale_found: 0`.

### Design decisions worth keeping
- **Prune is a separate workflow, not a step in the receiver.** The receiver is the one component
  with a perfect record (1,562 runs, zero errors) on the hot path of every event; table-sized work
  does not go there.
- **The prune never reads the whole table.** It filters `received_at < cutoff` server-side.
  `lt`/`gte` were verified to work on that column *before* anything was built on them.
- Capped at 500 deletions/run; counts outcomes not items; refuses to report "nothing to prune" off
  a failed read; re-checks the date in code so a broken server-side filter cannot delete live rows.

### Item 3 — not done, with evidence
WF-2S watches `nK3yIOqRcBearV8s` = **WF-2H Health & Digest** (Smartlead volume digest, daily 07:15,
20 runs, staying). Its CONFIG holds exactly two workflow ids and neither is I-04; searching WF-2S
for all three I-04 ids returns nothing; the watch node's own comment explains it guards WF-2H
because WF-2H cannot observe its own failure. Removing it would have deleted a live safety net and
would not have stopped anything reporting on I-04. Flagged to Nik, left intact.

---

## PARTIAL

- **The digest change is verified by component, not by a live digest post.** The exact deployed read
  and count nodes were run against the live table on a throwaway (208 events, 90 leads, 118
  persons) and `Compose` passes a syntax check with no I-04 references — but the digest itself next
  posts at 04:00Z tomorrow. First real proof arrives then.
- **The prune's delete path has never executed** and cannot until ~24 Nov. Only the
  nothing-to-do path is proven live. The delete branch is code-reviewed, not run.
- **One new linter finding accepted:** `R02` fan-in medium on the prune's CONFIG (schedule +
  webhook, matching `dnc_escalation_detector`). Deliberate — it buys an on-demand dry run.

## BLOCKED

- Nothing. One decision outstanding: whether to remove the WF-2S → WF-2H watch anyway.

## IMPROVABLE / THINGS THAT WENT WRONG

- **I 502'd the instance.** A filter-operator probe chained four unfiltered reads of the event
  table (~20 MB) and the instance returned 502 on both the run and the cleanup delete, leaving a
  stray ACTIVE temp workflow. Detected and removed within a minute; no live workflow was
  deactivated and nothing was lost. **Lesson: a throwaway probe is still production load.** The
  retry used one bounded read (`limit: 5`) and was fine. This is the same full-table-read shape the
  prune is designed to avoid — I walked into it while building the thing that avoids it.
- **A re-run of the digest patcher appended duplicate nodes** (40 → 42; two node pairs sharing a
  name *and* an id, with connections resolving by name). Caught on readback, repaired the same
  minute back to 40, and the builder now removes replacement node names before appending plus
  asserts no duplicates. **Lesson: an idempotency guard on the code path is not an idempotency
  guard on the node list.**
- **The prune's first deploy produced no output at all on the healthy path** — a zero-row filtered
  read emits no items, so every downstream node was skipped and the webhook returned
  "No item to return was found". Fixed with `alwaysOutputData` plus explicit placeholder handling.
  Worth a linter rule: *a filtered read whose empty result is the normal case must set
  `alwaysOutputData`, or success is indistinguishable from silence.*
- `changelog_24h` now returns **null** rather than being absent when the read fails, so the digest
  renders `n/a` instead of a number it did not measure. That also cleared an `R05` finding.

## Concurrent session

WF-1 changed underneath this work: **126 → 130 nodes**, `cec8f544` → `7e3e86cf` at 08:32Z, plus two
inactive `zz_*` throwaways and one new `R06` finding on `M7 IF Alert Delivered`. Not mine, not
touched. Recorded in `PRESENTATION_2026-09-03/STAGE1_INVENTORY.md` §E.

## Final state

40 workflows, 22 active, 944 nodes. Lint 185 → 187 findings, 39 high both sides; of the new ones
exactly one is mine and three belong to the other session. No errors in any touched workflow.
