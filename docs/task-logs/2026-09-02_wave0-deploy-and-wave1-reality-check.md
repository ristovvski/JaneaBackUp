# 2026-09-02 — Wave 0 deploy + Wave 1 reality check

**Task:** deploy Wave 0's three correctness fixes plus the gate-queue removal, then build
`dnc_intent_vs_reality` and fire it once for a same-day decision on the projection switches.
Authorised by Nik this session. No Slack of any kind was used.

**Outputs:** `WAVE0_2026-09-02/` (pre-fire artifact, backups, patched JSON, post-fire verification)
and `WAVE1_2026-09-02/` (builder, driver, report).

---

## DONE

### Wave 0 — 13 PUTs, all 200, all read back, no activation changed

| Fix | Workflows |
|---|---|
| Unsubscribe no longer writes `3. Responded` | WF-2 (`fb2e2ac3`) |
| Dead flags removed (`dnc_auto`, `forward_enabled`, `create_assignment_task`) | WF-2, same PUT |
| WF-1 verdict `DELAYED` → `LOST` + corrected retry text | WF-ERR (`392238c5`) |
| Gate queue removed: 24 → 14 nodes, `retrieve` → 410, no `dnc_gate_queue` refs | dnc_pre_add_gate (`fe1e4b57`) |
| `IF MODE == dev?` FALSE branch wired to the Send Guard | 9 workflows (5 active, 4 inactive) |
| `R14` widened + strip-aware, rebuilt from `lint_rules.js` | dnc_wf_linter (`e4e774d6`) |

- **Rehearsed first.** A `DEV__dnc_pre_add_gate_wave0` twin was created, activated, exercised on
  four contracts (monitor probe / 60 rows / retrieve / 501 rows), all PASS, then deactivated and
  deleted before the live PUT.
- **Verified after.** Live gate re-probed with the monitor's exact payload → `total 2, clean 1,
  blocked 1`, 182 ms. Retrieve → 410. Estate lint 195 → 185 findings, 45 → 39 high, `R14` → 0,
  `R13 dnc_gate_queue` 7 → 2 (both in the inactive drainer), **0 new findings**. No errored
  execution in any touched workflow after deploy.
- **Class static delivered:** `WF_LINTER/static_responded_class.js` — enumerates every label writer
  in the estate and requires each to be gated or provably incapable. FAIL(1) before, PASS after.
- **`SYSTEM_DOCS_2026-09-02/10_DOMAIN_heyreach…md` §6 corrected** and `FULL_REPORT` regenerated.

### Wave 1 — built, fired, reported

`dnc_intent_vs_reality` (`tnW7agCbha7rhNnS`, ACTIVE, webhook-only, read-only). 1,000-row systematic
sample of 25,653 active registry rows, 20 chunks, zero failures.

**Headline numbers** (full detail in `WAVE1_2026-09-02/REPORT.md`):
- **25,653 active rows** — the class map said ~4,800; wrong by 5×.
- **88.3% have neither a person id nor an email** (`manual_offboard_eligible`, the LinkedIn import).
  ~22,650 rows are unenforceable by any mechanism that exists.
- **Zero liars, both directions.** 93/93 rows claiming Pipedrive `done` are done; 22/22 claiming
  pending are missing the field. `projections_state` is trustworthy.
- **Pipedrive backlog ~564 rows** (of ~2,950 checkable; 19%, CI 13–27%).
- **Smartlead: 62% of checkable rows are still contactable → ~1,026 rows**, and 32 of every 40 are
  people who replied and declined or booked a meeting.

---

## PARTIAL

- **Sample, not census.** ±3% on whole-registry rates, ±11% on the Smartlead conditional rate. Good
  enough to decide the switch, **not** good enough to hand someone a list. Before the Smartlead
  pass fires, run the workflow in sequential mode over the ~1,667 email-bearing rows (~34 calls,
  ~20 min) to name every person instead of estimating the count.
- **`dnc_gate_queue_drainer` untouched.** Already inactive with zero executions; verified by read,
  not written. Its two `dnc_gate_queue` references are the remaining `R13` findings.
- **HeyReach leg not built into the reality check.** Nik's Wave 1 spec asked only for Pipedrive and
  Smartlead. Given that 88% of the registry is LinkedIn-only, a HeyReach assertion is where the
  next real information is.
- **`availableInMCP` is stripped on every PUT** by the sanitizer, alongside `timeSavedMode`. It was
  `false` everywhere and is a UI-only key, but this was not separately confirmed against the UI.

## BLOCKED

- Nothing blocked. Two decisions are pending: whether `FIRE_SMARTLEAD` runs on
  `manual_offboard_eligible` rows as well as `reply_dnc`/`meeting_dnc`, and whether WF-1 should
  respond *after* processing so HeyReach's retry becomes real.

## IMPROVABLE

- **The `R14` blind spot is the lesson of the day.** The rule protecting the Handover trigger could
  not see `M7 Labels Compute` — one of four real writers of that label — because it matched
  `label_ids:` but not the shorthand `label_ids,`. It had been reporting a clean estate it had not
  checked. **Any rule that decides "is this node a writer?" by one spelling of a construction is a
  false PASS waiting to happen.** Worth sweeping the other 14 rules for the same shape.
- **`dnc_intent_vs_reality` should get a schedule and a digest line** once the projections are on —
  it is the standing answer to "did the switch actually do anything?".
- **The registry's 88% unenforceable tail deserves its own decision.** Turning both projection
  switches on is correct and still leaves the bulk of the list as a record rather than a control.
- **`matchType: "allFilters"` is rejected by the dataTable node** ("unexpected match type") and
  `returnAll` defaults to a silent limit of 50. The second one nearly capped the whole registry read
  at 50 rows and would have reported that as the total — worth a linter rule.
