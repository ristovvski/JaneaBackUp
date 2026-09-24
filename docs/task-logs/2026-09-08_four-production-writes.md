# 2026-09-08 — the four production writes from the auditor's close-out

Files only, no Slack. Pre-posts in
[`WF1_W1.0.1_build/PREPOST_2026-09-08_four_writes.md`](../WF1_W1.0.1_build/PREPOST_2026-09-08_four_writes.md).

| # | item | state |
|---|---|---|
| 1 | digest dead reference | **DONE** — deployed `d17e47b2`, linter exit 0 |
| 2 | auth-notice state → claims row | **DONE** — deployed `2515c295`, 195 nodes |
| 3 | FIRE_PIPEDRIVE | **WINDOW 1 FIRED, verified CLEAN** — exec 48609, 250 records; 330 left |
| 4 | WF-1 early ack | **NOT MOVED, as instructed** — proposal written |

---

## 1. DONE — digest dead reference

`dnc_morning_digest` `qJKfR602wV9yfFrj`, `491f65b8` → **`d17e47b2`**, 40 nodes, still ACTIVE.

```diff
- const prev = $('I04 Status').first().json;
+ const prev = $('Changelog Count').first().json;
```

**The decision was mine and it went against the handoff's preference.** The auditor favoured
option (b), "drop the `...prev` spread and return only the `no_match_*` fields". Measured before
choosing: `Compose` consumes **37** fields off its input item; `No Match Count` produces **3**. The
other 34 exist only because every code node in the chain spreads its predecessor forward, the HTTP
node between them having destroyed `$json`. Option (b) would have posted a digest with every section
reading `n/a` — green, punctual, measuring nothing. The estate's signature failure, arriving as a fix.

The right replacement was already named in the codebase: `Changelog Count`'s own header comment
reads *"Replaces the old `I04 Status`"*. The 3 Sep simplification swapped the node and left the
by-name reader pointing at the corpse.

**Verified:** statics 5/5 including a non-vacuity case (the old code throws
`unresolved node reference: I04 Status` on the same harness); live re-read clean;
`node_reference_resolves.js` **exit 0** over 41 workflows / 979 nodes, self-test 11/11. Real proof
is tomorrow's 06:35 digest — five were lost, the sixth is the evidence.

## 2. DONE — auth-notice state ported to the claims table

WF-2 `5d4a5c97` → **`2515c295`**, 191 → **195** nodes, ACTIVE. Fourth and last of the WF-2
staticData stores.

```
Verify Secret ─▶ IF Authentic                                  (processing path untouched)
              └▶ DT Auth Notice Get ─▶ Auth Notice Decide ─▶ DT Auth Notice Claim
                                     ─▶ Auth Notice Ctx ─▶ IF Auth Warn ─▶ Ops Warn Bad Secret
```

Row `wf2_auth_notice`; state in `evidence` as `{mode, last_posted_date, suppressed_since_last}`.
`unconfigured` → on change plus once a day; `missing`/`mismatch` (a DROP) → every time; exactly one
closing post when the mode leaves a noisy state; row absent or table unreadable → post, because
alert gates fail **open**.

**Two decisions worth flagging.** *Claim before post*, the opposite of the alert registry's
claim-after-delivery: for a lead alert, claiming first can silence an alert nobody received, but for
flood control the failure modes reverse — claim-after means a failed write re-posts on every
subsequent event, which is the flood being fixed. And `Verify Secret` **keeps** its two staticData
writes, write-only, as the rollback copy, matching the 3 Sep ports.

**Statics 16/16**, including both non-uniform dataTable error shapes and two non-vacuity cases: a
burst of three overlapping executions warns **3/3** on the old path, and the same burst against the
row posts once then suppresses.

**Residual, stated:** the row is atomic, the read-then-write is **not** a compare-and-swap. Two
executions in the same instant can both post. 135 → at most a rare 2, not 1.

## 3. HELD at the confirmation gate — FIRE_PIPEDRIVE

As briefed: the ~564 is six days old and unverifiable today, so the pre-post needs a fresh count
from a `MODE="dev"` run.

**Before firing anything I proved a dev run is dark.** Reachability walk from the webhook trigger,
never taking a `FIRE_` gate's true branch: all **7** mutating nodes — both Pipedrive PATCHes, the
Smartlead unsubscribe, and all four `Mark Done` / `Mark Write Error` dataTable updates — are
unreachable. This was the check worth doing: a `Mark Done` reachable on the dev path would stamp
registry rows as projected without projecting them, and the sweep would then skip those people
forever. Only side effect is the workflow's own `Dev Summary` Slack post, into its guarded dev
channel (`C0B8GCVNR5W` / `C0BQM1X9ZUY` — **not** `#infra-issues`).

Fired `POST /webhook/{{WEBHOOK_DNC_PROJECTIONS_SWEEP}}`. The edge returned **HTTP 524 after 125 s** — Cloudflare
giving up on the response, not n8n aborting: execution **48563** is running.

**A trap worth recording:** `GET /executions?workflowId=…` with **no status filter returned 0** while
that same execution was live; only `status=running` showed it. The unfiltered list's
under-reporting, hit again. Absence from the default list is not evidence a run finished, or that it
ever started.

**The count, measured today** — execution 48563 finished **success** in 11 min 2 s, 22 nodes, and
the seven mutators did not execute:

| | |
|---|---|
| registry rows with a Pipedrive person | 2,847 |
| `pipedrive: pending` — **the eligible set** | **580** (the 2 Sep estimate was ~564) |
| one fire writes | **250** (`pd_chunk_size`), 330 left → two more invocations |
| of this chunk: field + lead label union / field only | 224 / 26 |

**Post-verify method changed from the handoff's.** A population delta is not a trustworthy primary
assertion on this surface — four label-wiper Zaps have written to this exact field and label before,
Melisa's automation is live on the same objects, and the 686 population is only confirmed to
27–28 Aug. Primary assertion is now a **per-record read-back of the exact 250 ids**, plus
`projections_state.pipedrive == done` for those rows and no others, plus label-union preservation;
population delta demoted to a secondary sanity check with the caveat stated.

**Blocking finding on the OTHER channel.** The dev run also measured Smartlead: 1,548 pending, **874
would be unsubscribed**, 46 already unsubscribed, 628 not found. And **the sweep has no reason-based
split** — `SL Filter Pending` → `SL Classify` → `SL Filter Resolved Only` never carry `reason`. So
the eligible set includes the HOLD classes: Person-d2a47603 (`manual_offboard_eligible`,
`employee_connection`) resolves to Smartlead lead `1410222726` and would be unsubscribed. Enabling
`FIRE_SMARTLEAD` today would project onto employee connections, on an API-irreversible mechanism.
"Get the exact list FIRST" now has its answer, and the answer is that the list is not yet safe.

**Defect in the dev reporting.** The summary it posted to `#gtm-telemetry` says
`chunk 10/12 done · 250 processed (224 labels, 26 field-only) · 330 remaining · 0 errors` — with no
dry-run marker, for work that did not happen. The signature failure moved into the reporting layer.
One-line fix, worth doing before the next dev run rather than after someone acts on the post.

Nothing fires until Nik confirms on 580/250.

## 4. NOT MOVED — WF-1 early ack

Full write-up: [`PROPOSAL_wf1_retries_and_ack.md`](../WF1_W1.0.1_build/PROPOSAL_wf1_retries_and_ack.md).

Agreed with the hold, but the stated mechanism is not the real one, and the difference changes what
to build:

* **The lead claim is not the only guard.** `Lead Search` (`/v1/leads?person_id=`) plus
  `Lead Create Gate` is a genuine existence check on the campaign field. A duplicate needs *both*
  guards to miss — the Pipedrive read AND the claim row. Narrower than stated, though that
  conjunction is exactly "died immediately after creating the lead".
* **The person half is largely handled** — `Person Create` hangs off a resolver
  (`Person Search Member → IF Member Verified[1]`), which adopts a person created seconds earlier.
* **The real blocker is `Dedupe`.** It drops a repeat of the same `correlation_id` at ingress, from
  **staticData** — so today a HeyReach retry never reaches the create path at all. Which means:
  move the ack, and the retry is thrown away. **Suppression is not resumption.** A late ack buys
  nothing until a retry can resume, and nothing in WF-1 resumes.

**Recommendation: keep the early ack and build a WF-1 reconciler instead.** WF-2R already solves
this shape — replay from provider truth, on a schedule, off the hot path. It covers the whole
lost-execution class without adding a resume protocol to a 138-node live receiver, and it fails
soft. The two-phase claim stays worth having, but it buys retry safety for a retry channel we do not
currently need.

---

## Improvable — mine, this pass

1. **A post-deploy assertion false-alarmed on its own comment, for the third time in this project.**
   `"I04 Status" in PATCHED` matched the explanatory comment that necessarily names the dead node.
   I have a comment-stripping verifier from the #26 port and did not reach for it until it bit.
   Both the static and the live check now run through `code_only()`.
2. **One static case asserted the wrong label**, not wrong behaviour: I expected
   `mode_change:unconfigured->missing` where the code correctly reports `drop_every_time` (a DROP
   outranks the change note; same outcome, better reason). Replaced with a case that actually
   exercises the mode-change branch — `valid → unconfigured`, someone clearing the hash.
3. **The dev sweep should have been fired with the response-timeout known.** A 125 s edge timeout on
   a workflow whose `Respond` node is at the very end was predictable from the graph, and a 524 is
   ambiguous between "never started" and "still running". It cost a diagnostic round trip.

---

## 3 (continued) — WINDOW 1 FIRED AND VERIFIED CLEAN

Confirmed by Nik on the measured count. Prerequisite done first, as instructed: the DRY RUN marker
shipped before the fire (sweep `1a111d7e`), together with a label-union shape guard I added and
flagged — statics 11/11, including a non-vacuity case proving the old union code returns
`['DNC-LABEL']` on an unrecognised response, i.e. it would have **wiped every existing label on 224
leads** the first time it ran live.

**Baseline failed on the first attempt and that is why it is asserted.** All 580 reads returned
HTTP 400: `include_fields=custom_fields` is not valid on `/api/v2/persons/{id}` (the plain read
already returns the dict). A baseline of zero rows means firing with no rollback. Second run:
**580/580, 0 errors, 0 already-686** — so the expected delta equals the number of successful writes
with no pre-existing values to muddy it. The script now exits non-zero rather than writing a hollow
file.

**Execution `48609`** — 18:06:54 → 18:21:17 local (14 m 23 s), status success, 30 nodes.

| node | items |
|---|---|
| `PD Filter Pending` | 580 |
| `PD Limit Chunk` | 250 |
| `PD Write DNC Field` | **250**, all responses successful |
| `PD Get Lead For Labels` / `PD Label Union` / `PD Patch Lead Labels` | 224 each |
| `PD Mark Done (with lead)` / `(no lead)` | 224 / 26 |
| `PD Mark Write Error` / `PD Count Write Errors` | did not run |

CONFIG disarmed in the `finally`: `MODE=dev`, `FIRE_PIPEDRIVE=False`, `FIRE_SMARTLEAD=False`,
workflow ACTIVE.

### Post-verify — CLEAN on all four

```
1. per-record read-back      686 confirmed 250 / 250     not-686: 0
2. nothing else moved        330 untargeted pending, unexpectedly 686: 0
3. label union preserved     224 / 224, dnc present, every prior label intact
4. registry vs CRM truth     marked_done 250 == persons reading 686 250
```

Assertion 2 is the one a population delta cannot give you, and assertion 4 is the one that catches
this estate's signature failure — a row claiming `done` for a person that is not actually 686.
Evidence: `window1_verify_48609.json`, `window1_exec_48609.json`.

### New defect found by firing — a LIVE window posts nothing

`Dev Summary` is gated behind `MODE == dev?`, and it is the sweep's **only** Slack node. So in
`MODE=live` the summary is composed (`mode='live'`, `dry_run=false`) and then goes **nowhere**: the
250-record projection announced itself to no one. That is the exact mirror image of the defect fixed
an hour earlier — a dry run that reported success, and now a real write that reports nothing. Worth
fixing before window 2 so the remaining 330 leave a trace in the channel.

### Window 2 readiness

330 remain (250 + 80). The next window's own dev count doubles as the independent "and no others"
check on the registry: **it must read exactly 330.** Awaiting Nik's separate confirmation, as ruled.
