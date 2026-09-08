# Domain 4 — n8n conventions and the traps we have paid for

*For whoever has to change a workflow here next.*
*Conventions verified against the live definitions of all 36 workflows on 2026-09-02. Where a rule comes from the project rulebook rather than from n8n, it says so.*

---

## Part A — the conventions

### A1. The CONFIG node

**Every workflow's second node is a `Set` node called `CONFIG`.** 33 of 36 have one; the three that do not are pre-convention scaffolding and one small monitor.

Everything environmental lives there and nowhere else: Slack channel ids, API base URLs, Pipedrive custom-field keys, owner ids, label ids, thresholds, campaign maps, and the `FIRE_*` / `MODE` / `WRITE_MODE` switches.

**Why it is worth defending:** routing a workflow to a different channel, or turning its writes off, must be **one edit in one visible place** — not a hunt through forty nodes. The linter enforces the negative case (`R06`: a literal channel id anywhere outside CONFIG is a finding).

Two styles exist in the estate — `mode: raw` with a JSON blob (the receivers, the digest, the linter) and the assignment list (the DNC family). Both are fine; the raw style is easier to read for large configs.

### A2. Dry-run by default — the `FIRE_*` discipline

Nothing that writes to an outside system does so unless a boolean says it may:

| Switch | Workflow | Live value today |
|---|---|---|
| `WRITE_MODE` | WF-2 | `live` |
| `FIRE_S1` / `FIRE_S2` / `FIRE_S3` / `FIRE_S3_BACKFILL` / `FIRE_S4` | the capture sources | false / false / **true** / false / false |
| `FIRE_PIPEDRIVE`, `FIRE_SMARTLEAD` | `dnc_projections_sweep` | **false / false** |
| `FIRE_REVERSAL` | `dnc_label_reversal` | false |
| `dry_run` (request body, default **true**) | the operator tools | must pass `dry_run: false` explicitly to write |
| `create_assignment_task` | WF-1, WF-2 | false |

A new workflow ships with the switch off, is fired once, and its dry-run report is read before the switch is flipped. **The default is always the safe one, and turning it on is a deliberate, separate act.**

### A3. Pre-fire discipline

*(Project convention — the artifacts live in the build folders, e.g. `ARCHIVED_RESPONDERS_build/ARTIFACT_prefire.md`.)*

Before any bulk write, a pre-fire document is produced that states:
- **where the input came from and how it was counted** — parsed properly, never `wc -l`;
- **every exclusion, with the reason**, and specifically what was *not* excluded despite looking excludable;
- **the classification of every row** and the mechanism that produced it;
- **the ambiguous cases listed individually for a human to decide** — never auto-promoted.

The archived-responders import is the model: a first pass produced 45 "opt-outs" by phrase matching; manual review found most matches were *our own* courtesy wording quoted back inside the reply. After truncating at quote markers in three languages the list fell to 10, and the final ruling was that **no phrase match is ever auto-promoted** — only an explicit label is. The count reached the registry as 10, not 45.

### A4. The channel map

| Id | Used as | What goes there |
|---|---|---|
| `C07LTD8UT70` | `slack_channel_replies` — **#lead-processing** | reply announcements. Only campaign members ever reach it |
| `C0B8GCVNR5W` | `ops_channel` / `alert_channel` | operational problems, dev summaries, conflict alerts |
| `C0BTUHSSM3K` | `slack_channel_alerts` — **#alerts** | WF-1 / WF-2 alerting |
| `C0BQM1X9ZUY` | `telemetry_channel` — **#gtm-telemetry** | dry-run progress, chunk telemetry, and the linter's findings |
| `C0BTP6VHP1B` | `digest_channel` | the morning digest |
| `C0BFE6KAN8J` | historical default | the fallback inside the shared Send Guard when a workflow sets no guard |

**The split that matters:** routine progress and dry-run chatter go to telemetry; final results and things needing a decision go to ops; person-level announcements go to #lead-processing and only for campaign members.

**Every Slack post passes a `Send Guard`** — the same 1,225-character code node copied into eight workflows. In `MODE: dev` it **throws** if the target channel is not on that workflow's allow-list. It is a deliberate hard failure: better a visible crash than a dry-run summary landing in the team channel.

One exception is pinned on purpose: WF-1's alert-delivery check compares against the literal team channel id rather than reading it from CONFIG, because if CONFIG were ever pointed back at ops, a config-derived check would silently re-mute everyone.

### A5. Alerts fire once per state change

A scheduled job that posts behind an `IF` must remember what it said last time, or it re-posts on every tick. The gate monitor posts once when the gate breaks and once when it recovers, and keeps the state in the workflow's static data. The linter's `R07` finds the violation.

**The deliberate exception: an unconditional daily digest.** It posts every day, including a wholly green one, precisely so that **a day with no message means the job did not run**. There is no "only post if interesting" gate in the morning digest, and the code says there must never be one.

### A6. Claim after success, never at decision time

Anything that records "I have handled this" must record it **after** the handling succeeded:
- WF-2S marks a send seen only after WF-2 accepted the replay;
- WF-2R does the same for replies;
- WF-1 and WF-2 write the alert-suppression key only when Slack confirms the post landed.

Claiming at decision time means a failed post burns that lead's only alert, forever.

### A7. Report "could not read", never "zero"

A count derived from a source you did not verify must be **null**, not 0. The morning digest suppresses new-lead counts and names the reason when the Pipedrive page comes back unsorted; it reports a saturated page as a floor rather than a total; the daily CRM summary distinguishes *"no events received"* (the subscription may be dead) from *"zero real changes"*; the linter reports an unreadable workflow list as unreadable rather than as a clean estate. The linter's `R05` finds the violation.

### A8. Every workflow points at WF-ERR

34 of 36 set `errorWorkflow: BbrXPABgOaaTJjD6` and `callerPolicy: workflowsFromSameOwner`. Do this on anything new.

### A9. The sandbox protocol

*(Project convention.)* A change to a live workflow is rehearsed on a **`DEV__`-prefixed twin deployed as a new workflow**, run once end-to-end against real data, before the live one is touched.

**There are no `DEV__` workflows in the instance today** — the twins were cleaned up after use, which is the intended end state. If you see one, it is either in flight or was forgotten.

### A10. One implementation, embedded — not copied by hand

The linter rules, and the two standing rules embedded in WF-1 and WF-2 (`AR Decide`), are **generated into the workflow from a single source file** by a build script, and the same file is what the tests import. The comment at the top of each says so.

Where this discipline was *not* applied, the estate is already drifting: `dnc_pre_add_gate` and `dnc_gate_queue_drainer` contain byte-identical `Classify Batch` code; the identity normaliser exists as a sub-workflow *and* inlined in three places; the `Send Guard` block is copied verbatim into eight workflows.

### A11. Rules carry their incident

Every linter rule and every rulebook entry names the incident that bought it. The reason given, verbatim: *"a rule whose reason is forgotten is a rule someone will delete."* Keep doing this.

---

## Part B — the platform traps

These are the ones that have actually broken something here. The first fifteen are enforced daily by `dnc_wf_linter`, which posts only what is **new** or **newly resolved** to `#gtm-telemetry`.

### B1 — `R01` A `__field` cannot survive a node that replaces `$json`  *(the "B12" class)*
Code nodes, HTTP nodes, data-table nodes and Slack nodes emit a **new** object. A field written upstream is gone. `IF`, `Switch`, `NoOp` and `Filter` pass items through unchanged, which is what makes this invisible — on the canvas the writer and the reader look adjacent with only an `IF` between them.
**Cost:** 53 of 55 Finovate leads created **orphaned**, because a lead-body builder read `$json.__person_id` after a lead-list HTTP call.
**Fix:** read the owning node **by name** — `$('Person Id Final').item.json…` — never `$json` across a replacing node.

### B2 — `R02` Two producers into one input is a **race**, not a join
n8n runs the target node once **per branch arrival**. Two different nodes feeding one input means it fires twice, and if the target reads either producer by name it throws *"hasn't been executed"*.
**Cost:** five days of I-04 outage.
**Fix:** chain them, or accept it runs twice. A diamond off a single `IF` is fine — those branches are mutually exclusive and the linter knows the difference.

### B3 — `R03` An `IF`'s output 1 is **FALSE**
Wiring only output 1 means "when NOT true".
**Cost:** ~500 "queue STUCK" alerts, fired on exactly the polls where nothing was stuck.
**Fix:** when only output 1 is wired, say out loud what the false case means.

### B4 — `R04` A failed data-table op does **not** reliably return `{error}`
Some operations return an error object; others — same table, different operation — **echo the original input items with no marker at all**. A negative test (`if (!x.error)`) therefore cannot work.
**Cost:** `dnc_gate_queue` read back as depth 0, producing ~500 false alerts.
**Fix:** check **positively** for the real row shape. The gate does this correctly: it accepts a queue row only if it has a string `row_key` and a string `status`.

### B5 — `R05` A missing read is not zero
See A7.
**Cost:** the I-04 686-row delta, and the queue depth above.

### B6 — `R06` A Slack channel id outside CONFIG
See A4.

### B7 — `R07` A scheduled alert with no state memory
See A5. **Cost:** 96 identical messages a day, twice over, for five days.

### B8 — `R08` A manual-mode `Set` node silently drops everything it does not list
Unless `includeOtherFields` is true. Downstream reads of carried context then see `undefined` with no error.

### B9 — `R09` `/v1/leads` without an explicit sort returns the **oldest** page
**Cost:** a count taken off an unsorted page reported zero new leads on a day with fifty; the page started in 2023.
**Fix:** always `sort=add_time DESC`. And remember the 500-row horizon: a "500-row read" of `/v1/leads` is roughly a 7-day window, not the whole estate.

### B10 — `R10` Pipedrive search returns **zero** items when `limit >= 500`
It looks like a successful "nothing found".
**Fix:** cap search reads at 100.

### B11 — `R11` An existence guard that forgets the campaign
The estate rule is **one lead per campaign**. A guard that asks "does this person have a lead?" suppresses a legitimate new one.
**Cost:** a 2025 lead suppressed the same person's 2026 lead.

### B12 — `R12` `/executions` unfiltered omits crashed runs and under-returns successes
It reported 4 errors against 172 real ones.
**Fix:** use `status=error`, or walk per workflow.

### B13 — `R13` Data tables referenced by **name** are unreliable
`mode: "name"` has failed live on tables that certainly existed — two confirmed-real tables in one day.
**Fix:** `mode: "id"`, with the id taken from the table's UI URL.
**Live state:** both styles are in use in ACTIVE workflows today. The registry (`UOgKwlGsL28lX61O`) and the I-04 event table are referenced by id; `dnc_gate_queue`, `i04_snapshots`, `i04_walk_staging` and `obs_state` are referenced **by name**. Those are the ones to convert.

### B14 — `R14` No automated event may set **"3. Responded"** without an engagement gate
That label is the handover trigger — writing it hands a human a lead as warm. Found on the bounce path, and then on the unsubscribe path, which set it unconditionally while its own sibling node deliberately withheld it.
**Fix:** any node writing that label must also check bounce / out-of-office / opt-out / reply class / stage rank.

### B15 — `R16` `settings.timeSavedMode` is rejected by the public PUT API
`PUT /workflows/{id}` answers **`request/body/settings must NOT have additional properties`**. It is a UI-only field. Strip it from the payload every time — **omitting it does not clear it server-side**, so it comes back on the next read.
**Cost:** WF-1's stable-key deploy was rejected while WF-2's identical deploy succeeded, leaving the two receivers briefly out of step.
**Live state:** **WF-1 still carries `timeSavedMode: "fixed"` and is the only workflow that does.** Anything that redeploys WF-1 must strip it.

*(Numbering note: the rules run R01–R14 and R16 — **R15 does not exist** in either the deployed code or the repository copy. The rulebook's claim of "16 rules" is documentation drift, not a missing rule.)*

### Traps not covered by a linter rule

**B16 — Archived leads are invisible to the list endpoints.** `/v1/leads` and `/v1/leads?person_id=` **cannot see archived leads at all**, and they ignore `archived_status` everywhere — including `person_id`-scoped reads. Only `/v1/leads/search`, `/api/v2/leads/search` and `/v1/itemSearch` reach them, and all three are term-based: **the term is an index, and the match must be confirmed by person id. A name is never what decides.**
*Cost:* a lead that existed, archived, read as "no lead", producing a wrong Slack message and a near-duplicate lead.

**B17 — A suppression key must never derive from mutable state.** Keying on `lead_id` meant that archiving a lead silently reset that lead's own alert suppression, and a genuine second message was announced as a first alert. Anything that can be archived, converted to a deal, or fall past a read horizon is mutable state. When a key format changes, honour the legacy key on lookup so a deploy does not re-announce history, and write only the new key.

**B18 — Never put a large IIFE in an n8n expression.** A 1,154-character inline function in WF-2's reply alert was rejected by the expression parser and **25 of 25 executions failed**. Worse, code in an expression combined with `onError: continueRegularOutput` fails *silently* while the execution still reports success.
**Fix:** build strings in a Code node; keep expressions to one short clause.

**B19 — An inactive sub-workflow still runs.** `DNC__UpsertLedger__v1` is marked inactive and executes thousands of times a week via `executeWorkflow` (`mode: "integrated"`). Never judge whether something is live by the Active toggle alone; check the execution list.

**B20 — Out-of-memory kills, and workflows that come back switched off.** A large replay burst can exhaust the instance and take a workflow down with it; WF-ERR classifies OOM as an instance-level event rather than a workflow defect. Two defences are in place: the reconcilers cap themselves at 20 replays per run, and the morning digest reports **missed schedules** and failed executions daily.
*This is the one item in this list I could not confirm from the live API today — the retention window does not reach the incident. The defences are visible in the live definitions; the incident itself is recorded in the project rulebook and in WF-ERR's own class table.*
**Fix:** never hand-replay in bursts of ~100; check the morning digest's missed-schedule line as the daily proof that everything scheduled actually ran.

**B21 — Execution history is a rolling ~19-day window.** The oldest execution retained anywhere in this instance today is 2026-08-14. "No executions" never means "never ran". For anything older, Smartlead (2024-09 onwards) and Pipedrive (2020 onwards) are the long-memory sources; n8n is not.

**B22 — n8n's Code node sandbox has no `zlib`/`gzip`.** `Module 'zlib' is disallowed`. Anything that needs compression has to be done outside n8n.

---

## Part C — a checklist for changing a workflow here

1. Read the linter's last post for that workflow — the standing backlog is real.
2. Rehearse on a `DEV__` twin, run it once end-to-end, then delete the twin.
3. Put every new constant in `CONFIG`, never in a node.
4. Ship the write switch **off**; fire once; read the dry-run report; then flip it.
5. Point `errorWorkflow` at WF-ERR and set `callerPolicy: workflowsFromSameOwner`.
6. If you added a data-table node, use `mode: "id"`.
7. If you added a Slack post on a schedule, add state memory — or make it unconditional and daily.
8. If you inserted any node between a writer and a reader, re-check every `$json.__field` downstream (B1).
9. If you are redeploying WF-1, strip `settings.timeSavedMode` from the payload (B15).
10. Sweep the whole estate for the same **pattern**, not just the instance you fixed, and report the sweep. Write the rule down with the incident that bought it.
