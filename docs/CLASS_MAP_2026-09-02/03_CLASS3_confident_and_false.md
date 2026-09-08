# CLASS 3 — "the answer is confident and false"

**Read-only.** Nothing changed, nothing posted.

**The class:** we return a response, write a state, or print a count that *looks* like an assertion
about reality and is not. The failure is not that we are wrong — it is that we are wrong in the
shape of an answer, so nobody re-checks.

Three shapes recur. I have sorted the findings by shape, and within each by whether the wrongness
is currently reachable on an ACTIVE workflow.

- **S-A: success reported without the effect** — a write failed or never happened, and the run,
  the response or the downstream state says it worked.
- **S-B: an empty or unreadable result read as a fact** — "we could not look" rendered as "there is
  nothing there".
- **S-C: a queued/pending state with no processor behind it** — an answer that promises a later
  answer that never comes.

Two findings below are the first I would fix, and neither was on the original list.

---

## 1. The two that matter most

### 1.1 ⛔ WF-ERR tells the operator a lost HeyReach event will come back. It will not.

**Shape S-A, on the guidance itself.**

WF-ERR's CONFIG holds the recovery verdict shown to whoever reads the failure:

> `2jdjKM2NJr473GdA` (WF-1 HeyReach receiver) —
> retry: *"HeyReach retries a failed webhook up to 5x over 24h"*
> verdict: **`"DELAYED - the event should come back on its own"`**

The live wiring of WF-1 is:

```
Webhook  →  Respond to Webhook   { "ok": true }, HTTP 200
              ↓
            CONFIG  →  Dedupe  →  Normalize  →  … everything …
```

**WF-1 answers `{"ok": true}` with a 200 before a single line of processing runs.** HeyReach is
told the event was accepted. It will not retry — the retry only covers a *delivery* failure (n8n
unreachable, 5xx at the HTTP layer), never a processing failure after the 200.

WF-2 has byte-identical wiring, and its own WF-ERR entry states this correctly:
*"WF-2 answers 200 before processing, so Smartlead will NOT retry — recovery is ours."* WF-2 then
has two reconcilers. **WF-1 has none.**

So the true verdict for WF-1 is **`LOST`** — the same category WF-2 uses for bounces and
unsubscribes — and the operator is currently told the opposite, at exactly the moment they are
deciding whether to repair by hand.

*This also means the "do nothing first — HeyReach retries" advice in
`SYSTEM_DOCS_2026-09-02/10_DOMAIN_heyreach_to_pipedrive_and_dnc.md` §6 is wrong. I took it from
WF-ERR. Correcting that doc is on the fix list below; I have not edited it yet because the whole
point of this exercise is to fix the class in one wave.*

**Truthful version:** WF-1's verdict becomes `LOST — no reconciler covers HeyReach; repair by hand
from the HeyReach inbox`. And the class-level question this raises: **should WF-1 respond *after*
processing instead?** That would make HeyReach's retry real. It costs webhook latency and risks
duplicate delivery, which the 48-hour dedupe already handles. Worth deciding deliberately rather
than inheriting.

### 1.2 ⛔ An unsubscribe stamps "3. Responded" on the lead — the handover trigger

**Shape S-A. Live, ACTIVE, and the deployed linter flags it high (`R14`).**

Two sibling nodes in WF-2 build the lead's label set. They do not agree.

`Body Lead Labels Union` (the **reply** path) has two locks:

```js
// BOUNCE LOCK (2026-08-31). '3. Responded' on a bounce is the worst outcome in this workflow:
// A bounce proves the opposite of engagement — no human ever saw the message — so it earns
// neither 'responded' NOR 'connected'.
const target = __isBounce ? [cold] : [cold, connected, responded];
…
const __opted_out = existing.includes(CFG.labels.dnc);
if (__opted_out) { remove responded }        // opt-out lock
```

`Body U Lead DNC Label` (the **unsubscribe** path) has **neither lock**:

```js
const target = [CFG.labels.cold, CFG.labels.connected, CFG.labels.responded];
if (__dnc_label === true) target.push(CFG.labels.dnc);
```

So when someone unsubscribes, we write `cold + connected + **responded** + dnc`. "3. Responded" is
the handover trigger — writing it hands a human a lead as warm. **We are currently marking
opt-outs as engaged leads.** The reply path was fixed for exactly this on 31 Aug; the unsubscribe
path was not, and its own sibling twenty nodes away contains the fix.

**Truthful version:** an unsubscribe earns `cold + dnc` and nothing else. Same reasoning as the
bounce lock — an opt-out is the opposite of engagement.

---

## 2. Shape S-C — queued/pending with no processor

### 2.1 The gate's `{"queued": N}` reply

`dnc_pre_add_gate`, ACTIVE, ~3,000 runs.

```
Cap Check      >500 rows        → Respond Over Cap        (honest error ✓)
Decide Sync    ≤50 and no queue → Respond      (real verdicts ✓)
               51–500           → Enqueue Rows → Respond Queued
```

`Build Queue Response` returns:

```js
{ queued: N, eta_minutes: Math.ceil(totalPending / 50) * 2,
  batch_id: $execution.id,
  note: 'retrieve with the same webhook: {"retrieve": true, "rows": [...]}' }
```

An ETA, a batch id, and retrieval instructions. Every one of them is a promise. Behind them:
`dnc_gate_queue_drainer` is **inactive with 0 executions**, and the gate monitor's own code (dated
2026-08-31) states the `dnc_gate_queue` table **does not exist**:

> *"the queue branch entirely. `dnc_gate_queue` does not exist, so `Check Queue` errored on every
> tick … The drainer is inactive and the table is absent; there is no queue to watch."*

The five gate nodes that touch that table all reference it **by name** and all carry
`onError: continueErrorOutput`, so the failures are swallowed and the caller still gets the
confident reply. The `retrieve` path then returns `retrieve_status: "pending"` forever.

*Not independently verified: the n8n public API does not expose data tables (404), so the table's
absence rests on that code comment plus the drainer's zero executions. Confirm in the UI.*

**Truthful version — pick one, do not default:**
- **(a) Remove the queue path.** Lower the hard cap from 500 to 50, and return the same honest
  `Respond Over Cap` error above it. The gate becomes: answer, or say why not. *This is my
  recommendation* — it deletes a subsystem instead of completing one, and no caller has ever
  successfully used the queue.
- **(b) Complete it.** Create the table, switch all five references to `mode:"id"`, activate the
  drainer, and add "a queued row reaches `done` within N minutes" to the gate monitor's
  assertions. Do not do (b) without that last part, or you have rebuilt the same class.

### 2.2 `retrieve_status: "not_found"` cannot distinguish two very different things

Same workflow, `Build Retrieve Report`. A row is `not_found` both when it was never queued and when
the queue read failed — `Lookup Queue By Key` returns nothing usable in either case. The deployed
linter flags this node twice (`R04` and `R05`). **Truthful version:** a failed read must return
`retrieve_status: "unavailable"`, distinct from `not_found`.

---

## 3. Shape S-A — success reported without the effect

### 3.1 The `Mark DNC` chain: we label the lead DNC without knowing the unsubscribe worked

WF-2, ACTIVE. `SL Unsubscribe` and `U SL Unsubscribe` both carry
`onError: continueRegularOutput`. `Mark DNC` sits immediately downstream and does this:

```js
const base = { ...pick('Merge Reply Ctx'), ...pick('Classify Parse') };
return [{ json: { ...base, __dnc_label: true, __forwardable: false } }];
```

It never looks at the unsubscribe response. `__dnc_label: true` is asserted unconditionally, and
the Pipedrive DNC label is then written off it. **Outcome when Smartlead rejects the unsubscribe:
Pipedrive says do-not-contact, Smartlead keeps sending, and the execution is green.**

**Truthful version:** `__dnc_label` must be derived from the unsubscribe response
(`__dnc_label: resp.error === undefined && resp.ok === true`), and a failed unsubscribe must
produce an ops warning naming the lead. The pattern to copy is already in the estate — see §3.4.

### 3.2 Eight more write nodes in WF-2 whose failure is invisible

All ACTIVE, all `onError: continueRegularOutput`, all POST/PATCH:

| Node | What silently not happening looks like |
|---|---|
| `SL Category` | the reply category never reaches Smartlead; our classification exists only in our own logs |
| `SL Forward Email` | **the salesperson is never told about an interested reply** — and the Slack alert already fired, so it reads as handled |
| `Reply Activity` | the conversation is missing from the CRM while the lead shows as Responded |
| `Bounce Note` | no bounce record on the lead |
| `R Person Create` / `R Lead Create` | the recovery path for an unresolvable person quietly does nothing |
| `LLM Classify` | handled correctly — `Classify Parse` has a real guardrail (§4.1) |
| `SL Unsubscribe` / `U SL Unsubscribe` | §3.1 |

For contrast, WF-2's Pipedrive core (`Org Create`, `Person Patch`, `Person Create`, `Lead Create`,
`Lead Labels Union`, `U Lead DNC Label`) has **no** error handling — a failure stops the run and
reaches WF-ERR. That is the loud, correct behaviour. The estate is inconsistent about which writes
are allowed to fail quietly, and the inconsistency does not track how important the write is:
*forwarding an interested reply to a human* is in the silent group.

### 3.3 `dnc_s4_retirement_removal` reports "WRITTEN — rows tombstoned" whether or not they were

ACTIVE. `Update Row` carries `onError: continueErrorOutput`, so failed rows flow onward as error
items. `Build Report`:

```js
const rows = $input.all().map(i => i.json);
return [{ json: { processed: rows.length, dry_run: dryRun,
  note: dryRun ? 'DRY RUN -- nothing written' : 'WRITTEN -- rows tombstoned' } }];
```

`processed` counts *items*, not *successes*, and the note is chosen from the dry-run flag alone.
A run where every write failed returns `processed: 12, note: "WRITTEN -- rows tombstoned"`.

**Same defect, same shape, in `dnc_archived_responders_import`'s `Build Report`** — and there it is
worse, because `Call UpsertLedger` can legitimately return `action: "conflict"` (writes nothing,
alerts a human) and that outcome is still counted in `processed`. Its `conflicts_declined` counter
tests `r.ok === true && r.channel`, which is the shape of a *Slack API response*, not a ledger
decision.

**Truthful version for both:** count outcomes, not items — `{written: n, failed: n, conflicts: n,
skipped: n}` — and derive the note from `failed === 0`.

### 3.4 The pattern that already gets this right — copy it

WF-2S / WF-2R `Summary`:

```js
// Replay Into WF-2 is onError=continueRegularOutput, so a rejected replay arrives as an item
// with .error rather than failing the cycle. Counting them is the only way anyone finds out.
const failed = resp.filter(r => r.error !== undefined).length;
…
if (resp[i] && resp[i].error !== undefined) return;   // rejected — leave it retryable
seen[b.__key] = …
```

Three things at once: the failure is counted, it is reported, and **the claim is not made**. Every
fix in §3 is this pattern applied elsewhere.

### 3.5 WF-1's dedupe claim can fail silently

`DT Claim Seen` (data table upsert, `onError: continueRegularOutput`). The authoritative dedupe is
still the in-memory static data, and this node is explicitly described in `Dedupe` as an
observation-phase dual-write, so today the blast radius is nil. It matters when the dual-write
becomes authoritative: at that point a swallowed upsert means silent re-processing.

---

## 4. Shape S-B — an empty or unreadable result read as a fact

The deployed linter already encodes this as `R04` (data-table failure read as absence) and `R05`
(missing read as zero). I ran the deployed rule code offline against the live definitions:
**195 findings, 45 high, 109 on ACTIVE workflows.** Below are the ones I traced and confirmed as
real; I have separated the false positives rather than pass them on.

### 4.1 Confirmed real, on ACTIVE workflows

| Workflow / node | What goes wrong |
|---|---|
| `dnc_pre_add_gate` / `Classify Batch` | `Get Registry Match (Batch)` has no error handling, so a hard failure is loud — but a read that *succeeds and returns nothing* makes **every row `CLEAN`**. There is no assertion that the registry is non-empty. The gate monitor's 1-clean/1-blocked check is the only thing standing between this and a fully-open gate, and it is doing more work than anyone realises. |
| `dnc_projections_sweep` / `PD Filter Pending`, `SL Filter Pending`, `HR Count Pending` | a failed candidate read yields "nothing pending", which is indistinguishable from a clean sweep |
| `dnc_i04_daily_summary` / `Compute Old Events`, `Summarize` | partially mitigated — `Summarize` deliberately distinguishes `zero_events` from "zero changes", which is the right pattern; `Compute Old Events` does not |
| `dnc_morning_digest` / `DNC Active Agg`, `DNC Removed Agg`, `No Match Count` | the DNC counts in the daily digest can read as 0 on an unreadable table. The digest gets this right elsewhere (it suppresses unsorted lead counts and names the reason) — the DNC block is the gap. |
| `WF-2H` / `Quality Digest`, `SL Stats Summary` | volume comparison silently degrades to zero |
| `dnc_escalation_detector` / `Classify Active Cold Campaigns` | a failed campaign list means "no active cold campaigns", i.e. the safety net reports all-clear |
| `dnc_s4_retirement_removal` / `Build Report` | §3.3 |
| `dnc_pre_add_gate` / `Decide Sync Or Queue`, `Build Queue Response` | §2.1 |

### 4.2 Checked and discarded — do not spend a fix on these

| Finding | Why it is not real |
|---|---|
| `R01` on `dnc_wf_linter / Lint` (`$json.__person_id`) | the string appears inside the linter's own **rule text**, describing the defect |
| `R12` on `WF-ERR / Fetch Execution` | it fetches **one execution by id**, not the list — the rule targets unfiltered list reads |
| `R10` on `dnc_escalation_detector / Get Campaign Leads` (`limit=500`) | the 500-cap rule is about *Pipedrive search*; this is a Smartlead campaign-lead read where 500 is legitimate, and the node already reports `truncated` when it saturates |
| `R10` on `WF-2H / PD Leads` (`limit=500`) | real but different: not a silent-zero, it is the 500-row ≈ 7-day horizon. Belongs in the horizon discussion, not here. |
| 34 findings on `WF-1-DO NOT USE` | inactive duplicate of WF-1 — exclude it from the linter (Class 2 §2b) |

### 4.3 One unreachable alarm

`dnc_i04_daily_summary / Alert Post Failed` has **no inbound edge** — the only orphan node in the
estate. The alarm for "the daily summary failed to post" can never fire. Failure of the daily post
is therefore indistinguishable from the job not running, and the digest's own stated invariant is
"a missing post means the job did not run".

---

## 5. Proposal — make the class impossible, not the instances

Five rules. Each one, applied estate-wide, retires a whole shape.

**R-1. A response may only assert what a response was read to confirm.**
Any node that returns `written`, `queued`, `done`, `ok` or a count must derive it from the
provider's response, never from the fact that we reached the node. Concretely: count outcomes, not
items (§3.3), and derive `__dnc_label` from the unsubscribe ack (§3.1).

**R-2. `onError: continueRegularOutput` obliges you to count the error.**
Swallowing a failure is legitimate — losing it is not. The WF-2S `Summary` pattern (§3.4) is the
house standard: filter `.error`, count it, report it, and do not claim. Candidate as a new linter
rule (`R17`): a node with `continueRegularOutput` whose downstream never tests `.error`.

**R-3. Three states, never two: `true` / `false` / `unavailable`.**
Every read that can fail must be able to say so. `not_found` ≠ `unavailable` (§2.2); `0` ≠
`unknown` (§4.1). The morning digest already does this for lead counts; generalise it.

**R-4. No promise without a processor.**
A response containing a future tense — `queued`, `eta_minutes`, `pending`, `retrieve later` —
requires a monitored consumer whose liveness is asserted, or it must not be returned at all.
Applies to §2.1 and to anything built like it later.

**R-5. Recovery guidance is code and must be tested like code.**
WF-ERR's verdict table (§1.1) is the highest-leverage text in the estate — it is read at the exact
moment someone decides whether to intervene — and it was wrong for WF-1 for as long as WF-1 has
had a respond-first webhook. Every verdict should be derivable from the graph
(*does the workflow respond before processing? does a reconciler cover this event type?*) rather
than hand-maintained. A static check can compute it.

### Fix order within Class 3

1. §1.2 unsubscribe → Responded *(a live CRM correctness defect, one node, no dependencies)*
2. §1.1 WF-ERR's WF-1 verdict *(one CONFIG string; then decide respond-before vs respond-after)*
3. §3.1 `Mark DNC` derived from the ack
4. §2.1 gate queue — remove or complete
5. §3.3 outcome counting in both operator tools
6. §4.1 three-state reads, starting with the gate's registry read and the digest's DNC block
7. §4.3 wire `Alert Post Failed`
8. §3.2 the remaining silent writes, with `SL Forward Email` first
