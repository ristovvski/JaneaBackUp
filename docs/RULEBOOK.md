# Rulebook — standing rules

Rules are recorded here with the incident that bought them. A rule whose reason is forgotten is a
rule someone will delete.

---

## R-A. ARCHIVED LEAD = IGNORE  *(Nik, 2026-08-31)*

If the person's campaign lead is **archived**, the event passes through **silently**:

* no new lead
* no activity
* no label
* **no post anywhere** — not #lead-processing, not #alerts, not ops

**Detection requires an archived-visible lookup.** `/v1/leads` and `/v1/leads?person_id=` cannot
see archived leads at all — `archived_status` is ignored on both. Only `/v1/leads/search`,
`/api/v2/leads/search` and `/v1/itemSearch` reach them, and all three are term-based. So the term
is an **index**, and the match is confirmed by **person id**. A name is never what decides.

**Bought by:** Person-b093030e, 2026-08-31. His lead `8694ea30` existed with the correct title and
labels, was archived at 10:39:35Z (with a `Disqualified` label, by a human or an external
automation — no WF-1/WF-2 execution ran in that window), and `M7 Lead Get` returned **0 rows**
because the list endpoint is blind to archived leads. WF-1 honestly reported "no lead · Open
person" into #lead-processing, and would have created a duplicate lead on the next invite event —
`Lead Create Gate` filters `!l.is_archived` over a response that can never contain an archived
lead, so it is blind by construction.

**Fail-open exception, narrow and named:** if the archived-visible probe itself cannot be read, do
**not** block — a real reply must never be silenced by an unreadable lookup. Report
`probe_unreadable` instead, so "we could not look" never renders as "nothing archived".

---

## R-B. NON-CAMPAIGN PERSON = NEVER IN #lead-processing  *(Nik, 2026-08-31)*

Only **Smartlead / HeyReach campaign members** reach #lead-processing. A person from outside any
campaign — unknown, unresolvable, or a manual thread — gets **no post of any kind**, not even
#alerts.

This extends the 2026-08-28 ruling (*"a manual conversation gets the silent CRM activity write and
nothing else"*) from #lead-processing to every channel. **It governs POSTS, not CRM writes:** the
silent activity write on a manual thread still happens, deliberately.

**Scope boundary — rule R-B applies to posts ABOUT A PERSON, not posts about the SYSTEM.**
Silencing `Ops Warn Bad Secret` because an event carried no campaign would hide a webhook-auth
failure. Infrastructure alarms are not person-scoped and are never suppressed by R-A or R-B.

---

## R-C. SUPPRESSION AND DEDUPE KEYS DERIVE FROM STABLE IDENTITY  *(Nik, 2026-08-31)*

Alert-suppression and dedupe keys are built from **person id**, else the **canonical provider
identity** (LinkedIn slug / member id / lowercased email). **Never from lead visibility.**

**Bought by:** the same Person-b093030e incident. The key was `'L' + lead_id` when a lead was visible and
`'P' + person_id` otherwise, so archiving the lead moved his key:

```
08-28 18:23  lead live      key 'L8694ea30-a30b-11f1-8297-bb888c95b31f|572715'  -> first_alert
08-31 10:39  lead ARCHIVED
08-31 14:27  second message key 'P85903|572715'                                 -> first_alert
```

A human archiving a lead silently reset that lead's own alert suppression, and a second genuine
message was announced as a first alert — against the gate's documented intent, *"ONE alert per
lead, suppressed on DELIVERY"*. The general form: **a suppression key must not be derived from
mutable state.** Anything that can be archived, converted to a deal, or fall past a read horizon
is mutable state.

**Migration rule:** when a key format changes, the lookup honours the legacy key as well, so a
deploy never re-announces what was already delivered. Only the new key is written.

---

## R-D. TIME-BASED EXPIRY IS RETIRED; RETENTION IS REASON-BASED  *(Nik, 2026-08-31)*

Alongside Melisa's 2026-08-26 ruling. The registry keeps replies, meetings, sales-created/Surfe,
employee connections and explicit opt-outs, and retires rows whose only reason was contact. A TTL
on the rows that represent a response contradicts that — it says the response stops mattering.
`expires_at` is null on every active row, `dnc_expiry_job` is deactivated and preserved, and
`computeExpiry` returns null for every entry type.

---

## R-E. EVERY FIX ENDS WITH AN ESTATE-WIDE PATTERN SWEEP  *(Nik, 2026-08-31)*

A fix is not done until the same **pattern** has been swept for across all workflows and the sweep
reported. Defects get statics at **class** level, not instance level — "no automated event sets
`3. Responded`", not "a bounce doesn't set Responded". Tooling: `WF_LINTER/`, and
`dnc_wf_linter` posts only new findings, to `C0BQM1X9ZUY` and nowhere else.

---

## R-F. n8n TRAPS — things that have broken a deploy or a read  *(living list)*

The executable form of this list is `WF_LINTER/lint_rules.js` (16 rules, 46 statics). Entries here
are the ones that bite a *human* mid-deploy.

* **`settings.timeSavedMode` is rejected by the public PUT API.** `PUT /workflows/{id}` answers
  `request/body/settings must NOT have additional properties`. It is a UI-only field. Strip it
  from the payload; omitting it does **not** clear it server-side, so it comes back on the next
  read and must be stripped again every time. Cost: WF-1's stable-key deploy was rejected while
  WF-2's identical deploy succeeded, leaving the two receivers briefly out of step. Linter rule
  `R16`.
* **Never put a large IIFE in an n8n expression.** A 1,154-char IIFE in WF-2's reply alert was
  rejected by the expression parser and 25/25 executions failed with "invalid syntax". Build
  strings in a Code node; keep expressions to one short clause.
* **`/v1/leads` and `/v1/leads?person_id=` cannot see archived leads** and ignore
  `archived_status`. Only `/v1/leads/search`, `/api/v2/leads/search` and `/v1/itemSearch` reach
  them. Rule `R-A` exists because of this.
* **`/api/v2/leads/search` returns ZERO items when `limit >= 500`** — it looks like a successful
  "nothing found". Cap at 100. Linter rule `R10`.
* **Two producers into one node input is a race, not a join** — n8n fires the node once per
  branch arrival. Linter rule `R02`.
* **dataTable `mode:"name"` is unreliable**; use `mode:"id"` with the id from the table URL.
  Linter rule `R13`.
* **A failed dataTable op does not reliably return `{error}`** — some ops echo the original input
  with no marker, so only a positive row-shape check works. Linter rule `R04`.
* **A sub-workflow marked inactive still runs** when invoked via `executeWorkflow`
  (`mode: "integrated"`). `DNC__UpsertLedger__v1` is inactive and live.

---

## R-G. I-04 IS A CHANGE LOG, NOT A REPORTING INVARIANT  *(Nik, 2026-09-03)*

`dnc_i04_event_receiver` stays and keeps recording every Pipedrive lead/person change into
`i04_event_log`. **`dnc_i04_daily_summary` and `dnc_i04_weekly_reconciliation` are retired** —
deactivated and preserved, never deleted.

**What we lose:** automatic detection of bulk changes. The daily summary flagged ten or more
distinct leads updated inside the same minute, which is how a label-wiping automation was caught
before. Nothing watches for that now.

**What we keep:** full retrospective traceability. Every change keeps its action, object,
timestamp and raw payload for 90 days, so *"who changed this and when"* stays answerable — for
anyone who asks. Nothing asks on its own any more.

**What never existed and is now explicit:** departures inside a window with no snapshot were never
recoverable. The weekly reconciliation was the only thing that could have caught them, and it never
ran once in its life. That limit used to be implied by a workflow that looked like it covered it.

**Retention.** The summary pruned the table as a side effect of reporting; with it gone,
`dnc_i04_event_log_prune` does the job on its own daily schedule, 90 days.
Measured 2026-09-03: 1,563 rows over 9 days, **215 events/day**, ~3.4 KB per row →
**~19,400 rows / ~62 MB at steady state**. It is a no-op until ~2026-11-24.

**The prune must never read the whole table.** It filters `received_at < cutoff` server-side, so
its read is one day of aged-out rows, not 62 MB. This is not theoretical: while building this
change, a probe that chained four unfiltered reads of this table **returned 502 from the
instance**. Same reason nothing was added to the receiver — 5 nodes, zero errors, on the hot path
of every event.

**Orphaned tables.** `i04_snapshots` and `i04_walk_staging` now have no active reader or writer.
Leave them; do not build on them. Both are referenced **by name**, the form that has failed live on
tables that certainly existed (`R13`) — anything that needs them must convert to `mode: "id"` first.

**Reporting.** The morning digest no longer reports whether an I-04 job ran. It reports
`CRM change log N events` off the event table, and prints `unreadable` rather than `0` when it
cannot measure.

---

# Traps — added 2026-09-11

## T1. The alert is the one surface where omitting a field is the same as lying

Person-8768306e (President @ Circle) accepted a LinkedIn connection request. HeyReach emitted
`connection_request_accepted` and `message_reply_received` in the **same millisecond**, and the
reply carried one correspondent entry with `message: ""`. WF-1 alerted #lead-processing, wrote a
**permanent** `reply_dnc` registry row, set `3. Responded` and opened a handover task — for a man
who had said nothing.

The alert read:

> 💬 Person-8768306e (President @ Circle) · […] - Noah - LinkedIn · via Noah Keimach — Open lead
> **Details:** Name … Company … LinkedIn profile …

Indistinguishable from a real reply. And here is the part that matters: **the workflow knew.**
`M7 Build.render()` has always returned `'[empty message]'` for a blank body, and wrote exactly that
into the CRM activity note — 15 characters, `[empty message]`, sitting on the lead card the whole
time. The CRM told the truth; the channel a human actually reads dropped the one field that carried
it.

**Rule.** An alert that reports THAT something happened without reporting WHAT is not a
notification, it is a rumour. Every alert quotes the payload it is alerting about — the reply text,
the error message, the value that changed — or it does not go out. Truncate it, never omit it.
Fixed in WF-1 by appending `Reply:` (first 120 chars) to the alert body; `[empty message]` now
reaches the channel that can act on it.

## T2. A write path that cannot record WHY is a false audit trail waiting to happen

`dnc_s4_retirement_removal` — the driver behind the 7,450-row tombstoning — read `row_ids` and
`dry_run` from its caller and **hardcoded**:

```js
removed_reason: 'rule_change_2026-08-26_melisa'
```

So the correction of Heath's false suppression would have been filed as Melisa's August rule change.
The row would have been removed correctly and the record of why would have been wrong — which is
worse than no record, because a wrong record is believed.

**Rule.** Any write that stamps a reason, an actor, or a justification takes that value **from the
caller**, with the old constant as the default so existing callers are byte-identical. A constant
frozen at authoring time is a value that will eventually describe a different event than the one
that is happening.

**Sweep, same day (v2, `WF_LINTER/sweep_hardcoded_constants.py`).** Scope matters: v1 searched only
inside mutating nodes, found "5 findings, all benign", and missed *both* known cases — in this
estate the request body is assembled in a preceding **Code** node. v2 scans every node from which a
mutating node is reachable, and carries a self-check that fails loudly if it stops finding the two
we already know about. On ACTIVE workflows it found:

| where | constant | verdict |
|---|---|---|
| WF-1 `M6 Build`, `M7 Build`, `Person Create`, `Create Lead`, `Create Activity`, `M8 Task` | `owner_id = CONFIG.melisa_user_id` | one named human owns everything both receivers create; no per-campaign or per-sender mapping exists |
| WF-2 `Body Lead Create`, `Body Person Create`, `Body Org Create`, `Body Reply Activity`, `Body Bounce Note`, `R Body Lead Create`, `R Body Person Create` | `owner_id = CONFIG.owner_id` (same id) | the third instance — the email side has the identical hardcode |
| **WF-1 `M7 DNC Build Input` and WF-2 `DNC Build Input`** | **`date_precision: 'unknown'`** | **load-bearing.** `reasonExpiryOverride('reply_dnc','unknown')` returns `expires_at: null`, so this literal is why every reply-driven suppression is PERMANENT rather than TTL-bounded. Frozen in both receivers. |
| WF-1 `M7 DNC Build Input` | `reply_category: 'linkedin_reply_uncategorised'` | deliberate placeholder, documented |
| S1/S2/S3 build nodes | `reason: 'reply_dnc' / 'meeting_dnc' / 'sales_personal_outreach'` | legitimate — the workflow *is* that reason |

The first two are decisions to take, not bugs to fix silently. The third is the one to look at
hardest: a single literal, in two places, deciding that everyone who replies is suppressed forever.

## T3. HeyReach webhooks carry no attachment marker — `render()`'s branches are dead

The complete union of every leaf in a `message_reply_received` / `every_message_reply_received`
payload gives exactly three message fields: `creation_time`, `is_reply`, `message`. There is no
`message_type`, no `attachments`, no `media`, no `content_type`.

`M7 Build.render()` reads `m.message_type` and returns `'[attachment]'` / `'[voice note]'` from it.
**Those branches have never fired, in any execution, ever.** An attachment-only reply is
byte-identical to an empty one on this surface.

The inbox API is different: `GetConversationsV2` carries `isVoiceNote`, `transcript`, `postLink`,
and a conversation-level **`lastMessageType`** which does take the value `ATTACHMENT` (5 of 600+
sampled). It is not available to a webhook-driven gate without an extra call.

**CORRECTION, same day.** An earlier version of this entry said `lastMessageType` read `TEXT` while
the UI showed "Attachment(s)", implying the API was unreliable. It is not. Nik opened the
conversation itself: Heath's bubble is **empty** — no rendered attachment, no file, no voice note —
stamped the same minute as Noah's invite. It is an accept surfacing as a reply. The API's `TEXT` was
**right**: it is a textless TEXT message. **"Attachment(s)" is HeyReach's list caption for any
message with no text, not evidence of a file.** The marker is trustworthy; the list label is not.
Two of the five `ATTACHMENT` conversations really do carry files.

**Consequence, ruled:** no gate. A blank body alerts, and the line reads
`Reply: [no text — manually check the inbox; could be an attachment or an empty connection-accept]`
in Slack **and** in the CRM activity note — naming the common cause first, because the accept
artefact is the usual one and the UI's own caption points the reader the wrong way. The ambiguity
goes to the only surface that can resolve it: a human opening the conversation. That loop has now
run once end to end and worked.

## T4. The registry retirement path has no reactivate

`dnc_s4_retirement_removal` sets `status: removed` and nothing sets it back. Reversing a tombstone
needs a one-shot driver against the data table (the registry has no REST API, so it runs inside
n8n). Discovered while reverting a tombstone that should never have been written.
