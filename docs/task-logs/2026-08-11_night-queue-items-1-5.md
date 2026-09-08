# 2026-08-11 NIGHT QUEUE — items 1–5

Read-only / paper except where stated. Hard-stop rule honoured: **nothing touching the live wave
path deployed after the agreed set.** One item (5) was deferred by the "trivial or tomorrow" call.

---

## 1. WF-1 OVERLAP TEST — **EXPOSED, and it is worse than WF-2 was**

### 1a. Structural exposure: confirmed
**424 of 1,434 WF-1 executions (30%) overlap at least one other**, median duration 3.0s, max 63.6s.
Same architecture as WF-2 — webhook per event, HeyReach bursting — and n8n persists
`$getWorkflowStaticData('global')` once at execution end as a whole object. Every overlap is a
chance for the last finisher to clobber the other's writes.

### 1b. A second, independent defect: WF-1 never received P0-1b
`Dedupe` claims at **decision time**:
```js
sd.seen = sd.seen || {};
if (sd.seen[key]) return [];
sd.seen[key] = now;          // <- claimed BEFORE any work happens
```
This is exactly the pre-P0-1b pattern removed from WF-2 today. A WF-1 execution that crashes after
this line has burned its key permanently: `seen` rotates at 48h, so the event is suppressed for two
days and then simply gone. WF-1 has no reconciler of its own, so unlike WF-2 there is no second net.

### 1c. The claim-LOSS RATE is NOT measurable tonight — and the first attempt was contaminated
The initial run reported "alert claim loss: 100% overlapped / 89% non-overlapped". **Both numbers
are meaningless.** I rebuilt `__alerted_v1` from 50 entries to 0 at 11:24Z today, so almost every
historical claim is absent *by my own hand*, not by any race. Only 19 executions have run since the
reset, none of them overlapping.

The dedupe half returned `n=0` because I guessed the key field; WF-1 keys on `correlation_id`, and
its `seen` store (23 entries, untouched today) is the honest signal.

**Re-run after a full day of normal traffic** for a real rate. Structural exposure stands regardless.

### 1d. Recommended treatment (tomorrow, not tonight)
1. Burst spacing / serialisation, as WF-2 got.
2. **Port P0-1b to WF-1**: move the `seen` claim from decision time to after the work succeeds.
3. Then re-measure the loss rate against overlap.

---

## 2. CONCURRENCY CONTROL — verdict

n8n's public API exposes only `{name, nodes, connections, settings}` on PUT, and the accepted
`settings` keys are the execution-behaviour set (`executionOrder`, `errorWorkflow`, `saveData*`,
`executionTimeout`, `timezone`). **No per-workflow concurrency limit is reachable through the API**
on this instance — the UI-only keys we already strip (`availableInMCP`, `callerPolicy`,
`timeSavedMode`) are the only extras the instance sends back, and none of them is a concurrency cap.

n8n's concurrency control (`N8N_CONCURRENCY_PRODUCTION_LIMIT`) is an **instance-level environment
variable**, not a per-workflow setting, and not settable from the API — on n8n Cloud it is a
plan/support-side control.

**Recommendation:** do not pursue API-side serialisation. The spacing fix already closes the window
behaviourally, and it is verifiable from execution timestamps (proven tonight: 0.0–0.5s gaps before,
10.0s after). If instance-level serialisation is still wanted, it is a support ticket, and its
blast radius is every workflow on the instance — which would serialise the reconcilers too.

---

## 3. SMARTLEAD IDEMPOTENCY — verdict + sketch

**Verdict: not established, and I did not test it live** — probing an idempotency parameter on
`/campaigns/{id}/forward-email` means sending real mail to a real rep, which is not a night-time
experiment. What is known from today's payloads: the forward call takes `message_id`, `stats_id`,
`to_emails`, and the response carries a server-generated `messageId`. No client-supplied
idempotency key appears in any request we make. **Confirm against Smartlead's API docs before
building.**

### Sketch: pre-send history read (wire-truth F-check)
If no native key exists, replace the local F-key check with a read of the provider's own record:

```
before sending a forward for <dedupe_key>:
  GET /campaigns/{cid}/leads/{lead_id}/message-history
  scan history[] for type == FORWARD with time > the REPLY's time
  if one exists that corresponds to this reply -> DO NOT SEND
```
**Why it is better than the local F-key**, in one line: today proved local truth evaporates — a
staticData clobber lost 113 claims, and an F-key that is lost re-arms a duplicate send. Smartlead's
history cannot be clobbered by our race. Costs one extra API read per forward, which is nothing
against the cost of a duplicate.

**Caveat to design around:** correlating a FORWARD to a specific REPLY needs care — today's fixture
had 4 replies and 5 forwards on one thread. Match on `time > reply.time` AND nearest-following, and
treat ambiguity as "already sent" (fail-closed on SENDING, which is the opposite of the alert
gate's fail-open — a duplicate email is worse than a missing duplicate-check).

---

## 4. OPTION 3 SPEC — claims into one atomic store

### Why this is now the highest-value item
Tonight produced three separate failures that are all the same failure:
* claims lost to last-writer-wins (113 re-seeded)
* a claim written when the work did NOT happen (`Reply CRM Done` with `__no_lead`)
* a claim in one store implying retryability governed by ANOTHER store (the stranded 32)

**One atomic table with an upsert kills all three as a class**, rather than requiring every future
repair to remember every half.

### Schema (one table, `wf_claims`)
| column | type | note |
|---|---|---|
| `claim_key` | string, **unique** | the natural key, prefixed by family |
| `family` | string | `dedupe` / `alert` / `forward` / `wf1_seen` |
| `claimed_at` | datetime | for rotation |
| `workflow` | string | WF-1 / WF-2, so one table serves both |
| `evidence` | string | execution id + what proved success (ok:true, messageId) |

Prefixes keep families in one namespace without collision: `D|…` dedupe, `A|…` alert,
`F|…` forward, `S|…` WF-1 seen.

### What migrates
| current store | rows today | family |
|---|---|---|
| WF-2 `wf2_seen` | 213 (incl. 20 F-keys) | `dedupe` + `forward` |
| WF-2 `__alert_delivered` | 1 | `alert` |
| WF-1 `seen` | 23 | `wf1_seen` |
| WF-1 `__alerted_v1` | 0 (rebuilt today) | `alert` |
| WF-2S `__sent_seen_v2` | 163 | **stays** — see below |

### Migration order (each step reversible on its own)
1. Create the table; **dual-write** — keep staticData authoritative, write the table alongside.
2. Run a day; compare. Any divergence is the race, now measurable rather than inferred.
3. Flip reads to the table, keep dual-write.
4. Stop writing staticData; keep it read-only as a fallback for one more day.
5. Delete.

### What dies as a class
* last-writer-wins clobbering (atomic upsert, one row per key — no whole-object persist)
* "claimed in one store, retryable per another" (§9b.0e) **if and only if** WF-2S's producer store
  moves too — otherwise the two-store trap survives in a new form. **Decide this explicitly**: I
  recommend migrating `__sent_seen_v2` in the same programme, second, once the pattern is proven.
* repairs that must remember every half (§9b.0d gets much cheaper — one table to enumerate)

### What does NOT die
Claim-*timing* correctness. Atomicity does not tell you whether the work succeeded; `Reply CRM
Done`'s no-lead guard and the response-inspecting claims stay exactly as they are.

---

## 5. DIGEST OOO-LINE — **DEFERRED to tomorrow (my call, per "trivial or tomorrow")**

It is **not** code-only. WF-2H is a 9-node linear chain with **no n8n-executions reader**, and the
OOO count exists only in WF-2 execution data (`__alert_reason == 'ooo_no_alert'`). Landing it needs
a new HTTP node plus re-pointing two connections in the chain that produces the daily digest — low
risk, but graph surgery, and a mis-wire costs the digest silently.

**Ready to build:** add `WF-2 OOO Count` (httpRequest → `/executions?workflowId=<WF-2>&limit=250`)
between `PD Leads` and `Quality Digest`; count executions in the digest window whose
`First Reply Gate` emitted `__alert_reason == 'ooo_no_alert'`; append
`· N OOO auto-replies suppressed`. This is also §9b.0b's consumer for the OOO signal.

---

## Watcher false alarm, for the record

The drain watcher reported "16 NEW errored executions since the spacing fix". **False.** Those 16
rows have `startedAt: null` (ids 13566…, days old) and my filter did `(ts(x) or START) >= START`, so
a missing timestamp defaulted to *now* and passed. The newest genuinely dated error is 16:15:57Z —
**before** the spacing fix. **Zero real errors since spacing went in**, which is the first positive
signal for it.
