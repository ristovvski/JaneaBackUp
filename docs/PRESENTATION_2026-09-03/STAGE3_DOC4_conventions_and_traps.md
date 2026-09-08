# Domain 4 — Conventions, and every trap we have paid for

*For whoever changes a workflow here next.*
*Conventions verified against all 40 live definitions on 2026-09-03. Where a rule comes from the
project rulebook rather than from the code, it says so.*

---

# Part A — the conventions

## A1. The CONFIG node

**Every workflow's second node is a `Set` node called `CONFIG`.** Everything environmental lives
there and nowhere else: Slack channels, API bases, Pipedrive field keys, owner ids, label ids,
thresholds, campaign maps, and every switch.

Why it is worth defending: routing a workflow to a different channel, or turning its writes off,
must be **one edit in one visible place** — not a hunt through forty nodes. The linter enforces the
negative case: a literal channel id anywhere outside CONFIG is a finding.

Two styles exist — a raw JSON blob (11 nodes) and an assignment list (47). Both work; **the raw form
is the better one for anything large** and is what the newer workflows use.

## A2. Dry-run by default

Nothing that writes to an outside system does so unless a boolean says it may.

| Switch | Where | Value today |
|---|---|---|
| `WRITE_MODE` | WF-2 | `live` |
| `FIRE_S3` | creation watcher | **true** |
| `FIRE_S1`, `FIRE_S2`, `FIRE_PIPEDRIVE`, `FIRE_SMARTLEAD` | capture sources, projector | **false** *(the projector's are being flipped today)* |
| `dry_run` in the request body | the operator tools | defaults **true**; you must pass `false` |
| `create_assignment_task` | WF-1 | false |

A new workflow ships with the switch off, is fired once, and its dry-run report is read before the
switch is flipped. **The default is always the safe one, and turning it on is a separate deliberate
act.**

## A3. Pre-fire discipline

*(Project convention. Artifacts live in the build folders.)*

Before any bulk write, produce a document that states: **where the input came from and how it was
counted** — parsed properly, never a line count; **every exclusion, with its reason**, and
specifically what was *not* excluded despite looking excludable; **the classification of every row**
and the mechanism that produced it; and **the ambiguous cases listed individually for a human**,
never auto-promoted.

The archived-responders import is the model. A first pass produced 45 "opt-outs" by phrase matching;
review found most matches were *our own* courtesy wording quoted back inside the reply. After
truncating at quote markers in three languages the list fell to 10, and the ruling became: **no
phrase match is ever auto-promoted.** 10 reached the registry, not 45.

## A4. The channel map

| Id | Role | What goes there |
|---|---|---|
| `C07LTD8UT70` | **#lead-processing** | reply announcements. Only campaign members ever reach it |
| `C0B8GCVNR5W` | ops | operational problems, dev summaries, conflict alerts |
| `C0BTUHSSM3K` | **#alerts** | WF-1 / WF-2 alerting |
| `C0BQM1X9ZUY` | **#gtm-telemetry** | dry-run progress, chunk telemetry, and the linter |
| `C0BTP6VHP1B` | digest | the morning digest |
| `C0BFE6KAN8J` | historical default | a fallback inside the shared send guard |

**The split that matters:** routine progress and dry-run chatter → telemetry. Final results and
things needing a decision → ops. Person-level announcements → `#lead-processing`, and only for
campaign members.

**Every Slack post passes a send guard** which, in dev mode, **throws** if the target is not on that
workflow's allow-list — a deliberate hard failure, because a visible crash beats a dry-run summary
landing in the team channel.

One exception is pinned on purpose: WF-1's delivery check compares against the literal team channel
id rather than reading it from CONFIG, because if CONFIG were ever repointed at ops, a config-derived
check would silently re-mute everyone.

**⚠ The guard has already drifted.** It exists in two variants, identical in length, differing only
in the hard-coded fallback channel — one group of 8 workflows and one of 7. Nobody chose that; it is
what fifteen copy-pastes produce.

## A5. Alerts fire once per state change

A scheduled job that posts behind a condition must remember what it said last time, or it re-posts on
every tick. The gate monitor posts once when the gate breaks and once when it recovers. The previous
version produced **96 false alerts a day for five days.**

**The deliberate exception: an unconditional daily digest.** It posts every day, including a wholly
green one, precisely so that **a day with no message means the job did not run.**

## A6. Claim after success, never at decision time

- The reconcilers mark a send or reply seen only after the receiver accepted the replay.
- WF-1 and WF-2 write the alert-suppression key only when Slack confirms the post landed.

Claiming at decision time means a failed post burns that lead's only alert, forever. WF-2's
duplicate claim was moved to the success terminals for the same reason: claiming on arrival made a
crashed run permanently unreplayable, because the 48-hour dedupe memory outlives the reconciler's
48-hour lookback.

## A7. Report "could not read", never "zero"

A count derived from an unverified source must be **null**, not 0. The morning digest suppresses
new-lead counts and names the reason when a page comes back unsorted; reports a saturated page as a
floor; lists unreadable sources in a "not measured" footer; and renders an unmeasurable number as
`n/a`. The linter reports an unreadable workflow list as unreadable, never as a clean estate.

## A8. Everything points at the error handler

34 of the 40 workflows set their error workflow to WF-ERR and restrict callers to the same owner.
Do this on anything new.

## A9. The sandbox protocol

*(Project convention.)* A change to a live workflow is rehearsed on a **`DEV__`-prefixed twin
deployed as a new workflow**, run once end-to-end against real data, then deleted before the live one
is touched.

**There are no `DEV__` workflows in the instance today** — the twins were cleaned up, which is the
intended end state. If you see one, it is either in flight or was forgotten.

The same discipline applies to throwaways: today's sizing measurement was taken with a temporary
read-only workflow that was created, run, and deleted in one script. **A throwaway probe is still
production load** — one of them 502'd the instance (see B4).

## A10. Archiving, not deleting

**Deactivate, rename with an `ARCHIVE__` prefix, record the reason and the date. Never delete.**
Twelve workflows were archived on 2026-09-03. Where a workflow had a reachable webhook path, the path
is neutralised so the old URL cannot be hit even if someone reactivates it.

One-shot tools go in `ONE_SHOT_TOOLS.md` with a proposed delete-after date — a prompt to re-decide,
not an instruction.

**The property this buys:** of the 20 remaining active workflows, every one has run in the last 20
days except the projector, which is active because it is being fired today. *If a workflow is active
and has not run, either it is about to be, or it should be archived.*

## A11. One implementation, embedded — not copied by hand

The linter's rules, the two standing rules inside both receivers, and the shared label-target
function are **generated into the workflow from a single source file** by a build script, and the
same file is what the tests import. Each carries a header saying so.

Where that was not done, the estate is already drifting: the send guard (two variants), the gate's
classification logic (copied into a now-archived drainer), the identity normaliser (three inlined
copies plus the archived original), and a lead-selection block copied within WF-2.

## A12. Rules carry their incident

Every linter rule and every rulebook entry names the incident that bought it. The reason, verbatim
from the code: *"a rule whose reason is forgotten is a rule someone will delete."*

---

# Part B — the traps

Fifteen are enforced daily by the linter, which posts only what is **new** or **newly resolved**.

## The n8n platform

### B1 — `staticData` loses writes when runs overlap
A workflow's own memory is persisted **as one whole object when the run finishes**. Two runs in the
same second each load the same state, and the last to finish wins.

**Cost, precisely:** 2026-09-01 20:50:27, three WF-1 runs in one second. Two alerts delivered, the
registry went 47 → 48 instead of 49, one person's key lost — announced again 27 hours later as a
first reply. **HeyReach fans several events per message into the same second: 28 groups, up to 5
each, 54 true overlaps** in the retained window.

**Fix:** move the memory into a table where each claim is a separate row. Done for WF-1 today.
**⚠ Still outstanding in WF-2** — its alert registry, its duplicate memory and its bounce memory are
all still workflow memory. WF-2's live volume is low, which is the only reason it has not bitten.

### B2 — Fan-in is not a join
n8n runs a node once **per branch arrival**. Two different nodes feeding one input means it fires
twice — and if the target reads either producer by name it throws *"hasn't been executed"*.
**Cost:** five days of I-04 outage. A diamond off a single condition is fine — those branches are
mutually exclusive, and the linter knows the difference.

### B3 — A condition's second output is FALSE
Wiring only output 1 means "when NOT true". **Cost:** ~500 "queue STUCK" alerts fired on exactly the
polls where nothing was stuck.

### B4 — A full-table read is an out-of-memory event
**Cost, twice:** a ~100-item replay burst has taken the instance down and left a workflow
deactivated; and **during this week's work**, a probe that chained four unfiltered reads of the
change-log table (~20 MB) returned **502** — on both the run and the cleanup delete, leaving a stray
active workflow that had to be removed by hand.
**Fix:** filter server-side. The change-log prune reads only rows past its cutoff — one day's worth,
not the 62 MB table.

### B5 — Data-table failures have no uniform shape
Some operations return an error object; others **echo the input item back unchanged**, with no
marker. A negative test cannot work.
**Cost:** a queue table read back as depth 0, producing ~500 false alerts.
**Fix:** check **positively** for the real row shape. WF-1's new alert lookup does exactly this — an
echoed item carries the key, so "did a row come back" would read an outage as *already delivered* and
silence a real first reply.

### B6 — An empty result read as a fact
Zero rows and "we could not look" are the same thing unless you make them different.
**Cost:** the I-04 686-row delta, and the queue depth above.
**New this week:** a *filtered* read whose empty result is the **normal** case emits no items at all,
so every downstream node is skipped and the run produces **no output whatsoever** — success looks
exactly like silence. Set `alwaysOutputData`, and teach the next node to tell the empty placeholder
(one keyless item) apart from a real row.

### B7 — Set-node variants drop your fields
A `Set` node in assignment mode **silently drops every field it does not list** unless
`includeOtherFields` is true. **27 of the 47 assignment-mode Set nodes in this estate do not set it.**
Downstream reads of carried context then see nothing, with no error. The raw-JSON form does not have
this failure mode — another reason to prefer it.

### B8 — A `__field` cannot survive a node that replaces `$json`
Code, HTTP, data-table and Slack nodes emit a **new** object. Conditions and no-ops pass items
through unchanged, which is what makes this invisible — on the canvas the writer and the reader look
adjacent.
**Cost:** 53 of 55 leads created **orphaned**, because a body builder read a person id after an HTTP
call. **Fix:** read the owning node **by name**.

### B9 — Alert once per state change
See A5. **Cost:** 96 identical messages a day, twice over, for five days.

### B10 — n8n deactivates a workflow after repeated crashes
An out-of-memory kill can leave a workflow switched off, and **WF-ERR cannot report a workflow that
is no longer running.** Silence from the error handler is not proof of health. The morning digest's
**missed-schedules** line is the daily proof that everything scheduled actually ran.

### B11 — `settings.timeSavedMode` is rejected by the write API
`PUT /workflows/{id}` answers **"settings must NOT have additional properties"**. It is a UI-only
field, and **omitting it does not clear it** — it comes back on the next read and must be stripped
every time.
**Cost:** one receiver's deploy was rejected while the other's identical deploy succeeded, leaving
the two briefly out of step. **WF-1 still carries it and is the only workflow that does.**

### B12 — A 60-second limit per step
Both reconcilers have hit it, once each, on their scanning steps. Not a logic fault — a reason to
keep per-run batches small.

## Pipedrive

### B13 — List endpoints cannot see archived leads
`/v1/leads` and `/v1/leads?person_id=` **cannot see archived leads at all**, and they ignore the
archived-status parameter everywhere. Only the search routes reach them, and those are term-based —
so **the term is an index, and the match must be confirmed by person id. A name is never what
decides.**
**Cost:** a lead that existed, archived, read as "no lead", producing a wrong Slack message and a
near-duplicate lead.

### B14 — An unsorted list read returns the oldest page
**Cost:** a count taken off an unsorted page reported zero new leads on a day with fifty; the page
started in 2023. Always sort newest-first — and remember a 500-row read is roughly a 7-day window,
not the whole estate.

### B15 — Search returns **zero** items above a limit of 100
It looks like a successful "nothing found". Cap search reads at 100.

### B16 — A suppression key must never derive from mutable state
Keying on a lead id meant archiving a lead silently reset that lead's own suppression, and a genuine
second message was announced as a first. Anything that can be archived, converted to a deal, or fall
past a read horizon is mutable state. When a key format changes, honour the old key on read so a
deploy re-announces nothing, and write only the new one.

### B17 — An existence guard that forgets the campaign
The rule is **one lead per campaign**. A guard asking "does this person have a lead?" suppresses a
legitimate new one. **Cost:** a 2025 lead suppressed the same person's 2026 lead.

### B18 — "3. Responded" is a handover trigger
No automated event may write it without, **in the same write**, the label its category implies —
otherwise the handover fires in the gap. Found on the bounce path, and then on the unsubscribe path,
which set it unconditionally while its own sibling twenty nodes away deliberately withheld it.

## Smartlead

### B19 — Every bounce is delivered twice, and the second copy is shaped like a reply
The second arrives ~20 minutes later carrying **not one** bounce field. It ran the whole reply path
once: posted to `#lead-processing` and computed a label set containing *3. Responded*. Saved only
because that person had no lead yet.
**Fix:** three independent signals, any one wins — the event name, any bounce marker in the body
(including the `bounce_reply_*` fields, which are bounce metadata that merely contain the word
"reply"), and a recent-bounce memory scoped to reply-shaped events only. Smartlead's own category is
**not** a signal: it is empty on 11 of 12 real bounces.
**And on the statistics endpoint a bounce is recorded as history type `REPLY`** — there is no bounce
type there at all — which is why the reply reconciler builds a bounce index before it replays
anything.

### B20 — Smartlead never sends the "sent" webhook
Not a bug we can fix; a fact the architecture is built around. The sent reconciler is the primary
source, not a safety net.

### B21 — `to_email` is whoever replied, not the lead
Two addresses on a reply payload. Reading the wrong one made the receiver adopt a stranger on a
threaded reply. **And the replay envelope is inverted** relative to the live webhook — a replay must
carry the lead's address in the lead-email field or the lead cannot be identified, silently.

### B22 — An unsubscribe cannot be undone through the API
Treat any bulk unsubscribe as a one-way door: confirm the list first, read back afterwards. A
Smartlead call can report success on something that did not happen.

## HeyReach

### B23 — It retries 5×/24h **only on a non-2xx response**
Both receivers answer `200` **before** they process. So a processing failure is never retried by the
provider. For Smartlead the reconcilers cover sent and replied; **for HeyReach nothing covers
anything, so a failed event is LOST.**
The error handler's verdict for WF-1 said the opposite until 2026-09-02. Recovery guidance is code
and should be derived from the graph, not hand-maintained.

### B24 — Several events per message, in the same second
See B1. This is what makes the workflow-memory race routine rather than theoretical.

---

# Part C — the checklist for changing anything here

1. Read the linter's last post for that workflow — the standing backlog is real.
2. Rehearse on a `DEV__` twin, run it once end-to-end, then delete the twin.
3. Put every new constant in `CONFIG`, never in a node.
4. Ship the write switch **off**; fire once; read the dry-run report; then flip it.
5. Point the error workflow at WF-ERR.
6. Reference data tables **by id**, never by name.
7. A scheduled Slack post needs state memory — or make it unconditional and daily.
8. If you inserted a node between a writer and a reader, re-check every carried field (B8).
9. If a read's empty result is the normal case, set `alwaysOutputData` (B6).
10. If your memory could be written by two overlapping runs, use a table, not workflow memory (B1).
11. If you are redeploying WF-1, strip `timeSavedMode` from the payload (B11).
12. **Sweep the estate for the same *pattern*, not just the instance you fixed, and report the
    sweep.** Then write the rule down with the incident that bought it.
