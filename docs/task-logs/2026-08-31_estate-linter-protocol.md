# 2026-08-31 — standing protocol: pattern sweeps + the estate linter

New standing rule from Nik: stop fixing instances. Every fix ends with an estate-wide sweep for
the same PATTERN, and the fix is not done until the sweep is reported. All linter output goes to
`C0BQM1X9ZUY` and nowhere else.

## What was built — `WF_LINTER/`

| file | what it is |
|---|---|
| `lint_rules.js` | the rule engine. **One source of truth** — embedded verbatim into the workflow, required directly by the statics. No second implementation. |
| `test_lint_rules.js` | **43 statics**. Every rule has a must-fire fixture AND a must-stay-silent counterpart. |
| `run_lint.js` | ad-hoc / first-run estate scan → `lint_report.json` |
| `class_invariants.js` | class-level assertions run against live definitions |
| `build_linter.py` | builds `dnc_wf_linter` from `lint_rules.js` |

`dnc_wf_linter` (`fziGeigC48aGTLT8`) — ACTIVE, daily 06:40 Asia/Jerusalem, 8 nodes, no fan-in,
errorWorkflow WF-ERR. Posts **only** what is new or newly resolved. A `Lint Send Guard` throws if
the target channel is not in `allowed_channels`, so the single-destination rule is enforced at
runtime rather than trusted.

## Rules, and the incident each one is the general form of

| rule | sev | general form of |
|---|---|---|
| `R01` `$json.__field` read after a replacing node, incl. through IF/switch/noOp | high/med | B12 — 53 of 55 Finovate leads orphaned |
| `R02` two producers into one input treated as a join | high/med | the I-04 five-day outage |
| `R03` IF output-1 wired as if it were TRUE | high/med | ~500 "queue STUCK" alerts on the polls where nothing was stuck |
| `R04` dataTable output consumed with no positive shape check | med | the non-uniform error shape |
| `R05` `.length` count off an unverified read that can never be null | med | queue depth 0; the I-04 686 delta |
| `R06` Slack channel id outside CONFIG | med | the channel-split ruling |
| `R07` scheduled + IF-gated Slack post with no state memory | high | the two alert floods |
| `R08` manual Set without `includeOtherFields` | med | silent loss of carried fields |
| `R09` `/v1/leads` listed without `sort` | high/med | the unsorted page starts in 2023 |
| `R10` `limit >= 500` | high | search silently returns ZERO above 100 |
| `R11` existence guard that forgets the campaign | high | Person-ab3144af |
| `R12` `/executions` read without `status` | med | 4 reported vs 172 real |
| `R13` dataTable referenced by NAME | high | `dnc_gate_queue` |
| `R14` `3. Responded` written with no engagement gate | high | today's bounce defect, **at class level** |

## First full run — the backlog

**192 findings across 30 of 35 workflows · 45 high · 147 medium.** Posted to `C0BQM1X9ZUY` in two
messages plus an addendum. Machine-readable: `WF_LINTER/lint_report.json`.

The 7 ACTIVE `dnc_pre_add_gate` R13 hits are this morning's `dnc_gate_queue` defect — **found from
the definition alone, with no execution history**. That is the tool justifying itself on run one.

### Three rounds of tightening, because a linter that cries wolf gets ignored

* R02 went 76 → 46 by excluding (a) success/error pairs from one node and (b) diamond merges where
  **every pair** of producers is separated by an IF branch. Pairwise, not single-gate: real graphs
  nest gates, and `Person Id Final` is fed by four nodes that no single IF separates.
* R09 stopped firing on `POST /v1/leads` (a create, not a list read) and drops to medium when the
  read is person-scoped.
* R07 stopped firing on unconditional periodic digests. A digest is *supposed* to repeat — that is
  "silence must never be ambiguous". The defect is a **conditional** post re-deciding identically.
* R04 restricted to `get` operations actually consumed by the node.
* R11 now requires an actual verdict assignment, not a mention of `__deal_id`.
* R14 now requires evidence of a WRITE (`label_ids:` / `__body` / `target.push`), so a digest
  counting `l.label_ids` is not flagged.

Each tightening kept its statics: the must-fire fixture was corrected to the real node shape
rather than the rule being weakened to fit a bad fixture. That happened three times (R07, R14)
and in each case the fixture was wrong, not the rule.

## Class-level statics (protocol item 4)

`class_invariants.js` — **5 pass, 2 fail, and both failures are left red because both are true.**

The instance-level static from this morning was "a bounce does not set Responded". The class-level
form is **"no automated event sets `3. Responded` without an engagement gate"** — and it
immediately found a second live instance.

## THE SWEEP RESULT — a live sibling defect, not fixed

`WF-2 / Body U Lead DNC Label`, on the **UNSUB** path:

```
Switch Event [UNSUB] → U Person Search → … → U Mark DNC → Body U Lead DNC Label
const target = [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];
const body   = { label_ids: union };
```

**An unsubscribe writes `3. Responded`.** No reply, no gate. That label is Marci's Handover
trigger, so an opt-out is handed to a human as a warm lead. Its sibling `Body Lead Labels Union`
withholds exactly this label for opted-out leads, quoting the 2026-08-18 ruling — so the two label
writers in one workflow disagree, and the one on the opt-out path is the one that promotes.

**Deliberately not patched.** It is a live CRM write and a semantics ruling, not a bug to fix
quietly. Awaiting Nik's word.

Also dormant, same flood class as this morning, all inactive:
`smartlead_observability_readonly / Slack Anomaly Alert`, `dnc_expiry_job / Slack Weekly Digest`,
`dnc_expiry_job / Dev Summary (verbose)`.

## Known tradeoff

Rule 3 says post ONLY new findings, so the linter is silent on a quiet day. That is the opposite of
the digest's "silence must never be ambiguous" — a missing linter post cannot be distinguished from
a linter that did not run. Honouring the instruction as written; flagged rather than silently
adding a heartbeat.
