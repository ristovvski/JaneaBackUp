# S3 (SALES-CREATED → DNC) — build complete, both pieces, real dry-run result in hand

**Status: built, tested (65/65), deployed. Backfill dry-run confirms 27 real Surfe-created leads.
Creation watcher deployed but left INACTIVE (new recurring live automation — separate go-ahead).
One real infra blocker outstanding (source_signal column, UI-only creation).**

## What shipped
1. **Schema**: `sales_personal_outreach` added to `reason_v1.js` (ranks below `reply_dnc`, above
   `manual_offboard_eligible`; maps to `entry_type: manual`, deliberately not `employee_connection`)
   and `dnc_registry_dev.schema.yaml`. `source_signal` (creator|surfe|both) documented in the schema
   but **not yet a real column** — Data Table column creation is UI-only, no public API, the same
   constraint hit earlier this project. `DNC__UpsertLedger__v1` writes it with fill-or-union
   semantics (first signal sets it; a differing second signal upgrades to `both`; never downgrades)
   — ready the moment the column exists, currently a no-op write.
2. **`dnc_s3_creation_watcher`** (new workflow, id `QM21Vd7VId7PBdqh`, deployed INACTIVE): 15-minute
   poll, union of Signal A (creator/owner ∈ {Toby, Jim, Mario, Noah, Araks}) and Signal B
   (`lead.channel_id === 'Surfe'`), `source_signal` set per match. `FIRE_S3` defaults false.
3. **`dnc_s3_surfe_backfill`** (new workflow, id `1fpep0U4XC8KNzta`, deployed and fired dry-run):
   chunked (500 leads/page × 3 pages/chunk, sorted newest-first), resumable via a caller-supplied
   `start_offset`/`next_offset` cursor (no new Data Table needed — the OOM incident's own
   concurrency-guard discipline reused: check nothing running, fire, resolve the specific
   execution). `FIRE_S3_BACKFILL` defaults false.

## Real result (dry-run, zero writes)
**27 Surfe-created leads exist in the whole org**, all found in chunk 1 (`done: true,
next_offset: null` — never even needed a second chunk). Confirmed via execution data that
`S3B Call UpsertLedger` never ran (FIRE flag correctly gated it off) and the Slack post genuinely
fired (`ok:true` from Slack's own API, not just a computed string).

## Signal B recon, corrected before any code shipped
Spec assumed the Surfe marker lived on the **person**. Live recon (fixtures/s3_surfe_recon.json,
lead `f96f4cf0-967f-11f1-9312-db82f8cd0680` vs a WF-1-created negative) found it only on the
**lead** (`channel_id === 'Surfe'`, `origin === 'Marketplace'` as corroborating, not the match key)
— the person object carries neither field. Corrected the design (person-scoped lead lookup, not a
person-field read) before writing any node.

## Two real bugs found and fixed, both same root class: missing outgoing connections
Both new workflows had TWO separate dead-end nodes (`...Build Upsert Input` with no edge to the
FIRE gate at all; `...Combine` with no edge to the MODE gate) — plain missing-connection bugs in my
own build_dnc.py code, nothing to do with n8n itself. The first one triggered a genuinely expensive
debugging detour: a `respondToWebhook`-mode webhook kept failing with n8n's own
`"No Respond to Webhook node found in the workflow"` error despite a byte-for-byte-correct,
fully-reachable connections graph (verified three separate ways: isolated minimal probes of every
node type involved — plain webhook+respond, webhook+executeWorkflow+respond,
webhook+paginated-http+respond, all of which worked standalone — plus a full delete+recreate and a
fresh never-used path/webhookId). Root cause of *that* specific error was never conclusively
identified; pivoted to `responseMode: "lastNode"` instead (no dedicated Respond node needed, and
this workflow never depended on the HTTP response body anyway — results are read via the executions
API, same technique as every projections-sweep chunk fire today). That pivot is what surfaced the
REAL bug: with a working response mode, the execution visibly stopped early at the first missing
edge every time, which the broken Respond-node error had been masking. Fixed both dead ends in both
workflows; added a regression test (`S3: no dead-end nodes on the reporting/write path`) asserting
neither hop point can silently lose its outgoing edge again. 65/65 tests pass.

## Outstanding
- `source_signal` column: needs UI creation before any live (`FIRE_S3`/`FIRE_S3_BACKFILL=true`) run
  writes anything meaningful to it. Flagged to Nik; not blocking the build itself.
- Creation watcher stays inactive pending explicit confirmation to start its recurring poll — a
  genuinely new live automation, treated as its own go/no-go moment, not bundled into "build S3."
- Next in the stated priority order: S4 (AI4 campaign populations), then S1/S2 (Responded/Meeting
  unions).
