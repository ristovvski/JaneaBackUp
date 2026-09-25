# REPORT — ICP Auto-Scoring & Pipedrive Sync, Phase 1 — final

**For Chrissy. 24 September 2026.** What runs, what it leaves in Pipedrive, what
a rep reads, and the five decisions that are yours. The day-by-day build log —
every defect, measurement and ruling since 9 September — is
[`reports/BUILD_LOG.md`](reports/BUILD_LOG.md).

---

## 1. What runs

A deal is created in Pipedrive — typed in, or converted from a lead — and once
the Clay table has run, its organization carries a grade and one activity
explaining it. Nobody types anything.

```
Pipedrive  create.deal ──▶ n8n WF-ICP-Score, Path A
                              │  read the organization
                              │  fresh grade already?  ──▶ stop
                              │  no Website URL?       ──▶ "n/a - no website" + one activity, stop
                              ▼
                           Clay ICP table
                              │  enrich, classify seven components,
                              │  score (the formula), write the note
                              ▼
                           n8n WF-ICP-Score, Path B
                              │  validate the event
                              │  write Auto-ICP Score + Scored At (one PATCH)
                              ▼
                           one activity on the deal and the organization
```

| piece | where | what it does |
|---|---|---|
| **Trigger** | Pipedrive webhook 3167529, `create.deal` | The only ICP subscription. A lead→deal conversion fires it too, measured: every deal reaches Path A exactly once. |
| **Path A** | n8n | Reads the organization. Skips it when it already holds a grade under 180 days old and scored on or after the rubric's effective date (17 Sep). Sends Clay seven keys: `org_id, deal_id, domain, request_id, callback_url, requested_at, model_version`. |
| **No website** | n8n, Path A | The Website URL is the one identifier (Nik's ruling). Without it there is no Clay call: the organization gets `n/a - no website` and one activity asking a human to fill it in. |
| **The table** | Clay | Enrichment, seven classifiers, the scoring formula, the note. **The table decides the grade**; n8n does no arithmetic. |
| **Path B** | n8n | Validates the table's event (`request_id, org_id, deal_id, requested_at, final, grade, status, note` required), writes the two fields together or not at all, and posts the note verbatim. |
| **Failure** | n8n → `#niks-channel` | A rejected or failed run touches no field. It posts one Slack alert naming what was wrong, leaves one "ICP scoring failed" activity, and turns the execution red so WF-ERR reports it too. |

**The rubric.** The weights are Industry 15, Stage 25, Revenue 25, Company
type 25 and Geography 10, which gives a composite out of 100. Buying signal is
logged and weighted **0**. The composite is multiplied by activation:
Accelerating ×1.00, Transitioning ×0.95, Stable ×0.80, Contracting ×0. The
result is the final score. Grades are **A ≥ 75**, **B ≥ 55**, C below that.

---

## 2. The Pipedrive footprint

Per scoring run: **two field writes and one activity. Nothing else.**

| field | type | written by | holds |
|---|---|---|---|
| **Auto-ICP Score** | text | the workflow | `62 - B` · `n/a - insufficient data` · `n/a - no website` |
| **Auto-ICP Scored At** | date | the workflow | the day it was worked out, always in the same PATCH as the score |
| **Sales Rep ICP Score** | **single-select: A · B · C · D — not a fit** | **humans only** | the rep's own grade |

- **The two automatic fields move together or not at all.** The patch builder
  refuses to write one without the other, and refuses any key outside those two.
  This is an allow-list, not a deny-list. A re-score with an unchanged value
  writes nothing.
- **Sales Rep ICP Score is never written by automation.** Both patch builders
  assert it, and the static suite re-asserts it against the live field key. It is
  never read as scoring input either, so the rep's grade and the system's stand
  side by side.
- **One activity per run**, type `task`, marked done, on the deal and the
  organization. There are three subjects: `ICP scored`, `ICP not scored` (no
  website), and `ICP scoring failed`.
- **Not touched, ever:** notes, labels, owners, the website, LinkedIn, people,
  deals. The five v5 fields (ICP Calculated, ICP Score, ICP Scored At, ICP Model
  Version, ICP Final) were deleted from the account on 17 Sep.
- **Auto-ICP Score has no lock and no self-healing sweep. That is your ruling,
  and nothing was built.** A rep can overwrite it. Nothing puts the system's
  value back until that organization is next scored: a new deal once the grade
  is 180 days old, or a value that isn't grade-shaped (which re-scores on the
  next deal). For the record, the API does
  expose a per-permission-set field restriction (`restriction_settings`). It was
  never tested and is not applied.

---

## 3. The note a rep reads

The note is built in the Clay table and written to Pipedrive **verbatim**; n8n
renders nothing. It is HTML, because that is what Pipedrive renders: a `\n`
collapses into one paragraph, and `\r\n` gets a space inserted. The full rules
and the drop-in block are in
[`engine/clay_note_format.md`](engine/clay_note_format.md).

Abridged. Intellistack, activity 47041, 22 Sep:

> **ICP B (62/100) · confidence high**
>
> **Industry 7/10 · SaaS — Other**
> Sells horizontal workflow, forms, document, eSignature, and contract software across industries — a SaaS vendor.
>
> **Type 10/10** — *why* · **Stage 3/10** — *why* · **Geography 10/10** — *why*
>
> **Revenue 10/10 · $25M–$500M via apollo**
> Apollo's $55.3M estimate was used — about $230k per employee, plausible for a 240-person software company.
>
> **Hiring 0 eng open, 0 ≥60d, leaders: none** — *why*
>
> **Activation Stable ×0.80** — *why*
>
> **Score 78.0 × 0.80 = 62**
>
> Buying signal (not scored): 0 — No job postings or funding rounds are recorded, so no buying signal is detectable.

The note always has the same parts, in this order:
1. The headline: grade, final score and confidence.
2. Seven blocks (Industry, Type, Stage, Geography, Revenue, Hiring, Activation), each a bold header over one sentence.
3. The arithmetic.
4. Tier 2, activation guard and source conflict, each only when there is something to say.
5. **Last and always: the buying signal, marked "not scored".**

**Buying signal: weight 0 is confirmed.** The formula's weights give buying
signal 0. On every live note whose levels parse, the composite equals the
five-component weighted sum with buying signal excluded (4 of 4). The
"(not scored)" line was conditional on the classifier writing a sentence. The two
notes the table wrote on 22 Sep had **no buying line at all**. The spec now
makes the line unconditional, and a static runs the spec's block to prove it.
**The Clay column needs that one line pasted (Nik).**

---

## 4. What changed today, 24 September

### Sales Rep ICP Score → single-select A / B / C / D — done, live

A type change means recreating the field, so it was done in this order:

1. **Read every organization first.** Of 21,871 organizations, **1 carried a
   value**: Akuvo, `80 - A (Toby, by hand)`. It is **not a rep's rating**. This
   project wrote it through the API on 17 Sep as a test fixture, to prove a
   scoring run leaves the field alone. The changelog shows the API as the
   source. It isn't A/B/C, so it was reported, not migrated.
2. **Checked that nothing depends on the field.** None of the account's 89
   filters references it.
3. **Created the single-select.** Options: A, B, C, D — not a fit. The old text
   field was renamed out of the way first.
4. **Migrated 0 values.** There was nothing mappable.
5. **Read every organization back.** 0 of 0 landed, and the new field holds no
   value anywhere that the migration did not put there.
6. **Deleted the old text field only after that readback.** The fixture went
   with it.
7. **Swapped the key and re-ran the checks.** The field registry adopted the new
   field and CONFIG carries its key. The never-write statics pass against it,
   and a new static pins the field's type and its four options.

The new field sits after Auto-ICP Scored At on the organization card. If it
should sit between the two automatic fields, drag it in Pipedrive's field
settings.

### Auto-ICP Score — as is, no sweep

Nothing built, per your ruling.

### Buying signal — see §3

Weight 0 is confirmed live. The "not scored" line is now always in the spec;
the Clay paste is Nik's.

### The dead "Append audit row" node

The `icp_audit` table was dropped on 17 Sep. WF-ERR posted **4** "Append audit
row" failures in total, the last at **17 Sep 15:19 IDT**, and none since. The
week's 17 WF-ICP-Score alerts (15–22 Sep) are mostly the build's own
test-and-fix cycle: Dedupe B, POST Clay, FailLoudly. The node left the build in
the 17 Sep close-out, and a static fails the build if any node reaches a Data
Table. **Pending: live confirmation (see §6).** If the node is still in the live
graph, the deploy below removes it and its dry-run names it.

### DEV → production naming

The workflow runs on real deals, so it is production. The estate's production
workflows carry no suffix (WF-1 HeyReach Receiver, WF-ERR), so the name becomes
**`WF-ICP-Score`**, with no `[DEV]` and no `[PROD]`. The deploy is now the safe
patch. `scripts/n8n_deploy.mjs`:
- saves the live version as a rollback, outside the repo;
- refuses while an execution is running;
- builds in memory and **inherits both webhook paths from the live workflow**;
- **refuses any build that would move a path**, so the Pipedrive subscription
  and the Clay callback keep working;
- keeps the Dedupe ledger;
- PUTs with the build's name, re-reads, and diffs to "DIFFS none";
- restores the active state.

Eight statics run it against a mock n8n, and all eight fail against the previous
script. **Pending: the live rename (see §6).** WF-ERR's alerts identify this
workflow by name, so its CONFIG may still say `[DEV]`. That gets checked in the
same step.

---

## 5. The five decisions that are yours

### 5.1 Activation — where hiring data comes from

**Every live scored run so far reads "Hiring 0 eng open, 0 ≥60d, leaders:
none — no job postings were provided", and "Activation Stable ×0.80".**
That covers all four parseable notes: Intellistack twice and Jovia twice. The
table isn't receiving job postings. With no evidence, activation defaults to
Stable, so **every account takes a 0.80 multiplier**, and an A needs a composite
of about 93.

The decision is either:
- a hiring source for the table, which is what can move an account to
  Accelerating ×1.00 or Transitioning ×0.95; or
- accepting Stable as the honest default and reading the grades with that in
  mind.

A related point on the other end: Contracting (×0, off the board) applies only
on a measured headcount fall or a dated layoff/freeze citation. The sheet says
Contracting for Microsoft, and the enrichment doesn't show it.

### 5.2 Stage maturity for enterprises

| account | sheet | engine |
|---|---|---|
| Microsoft | **7** | 0 |
| Merck | **7** | 0 |

The rubric's stage 0 is "mature steady-state, no acute pressure". The engine
reads a 70,000-person company as exactly that, and the sheet's reviewers read the
same companies as 7. Stage carries 25 of 100, so every enterprise account
inherits whichever reading you pick. **Nothing has been changed pending your
call.**

### 5.3 Workato — "Horizontal B2B Software"

That vertical isn't one of the 17 in the rubric. The sheet scores its industry
10, and the engine scores it 0 with an `unknown_vertical` flag, so the composite
is 100 on the sheet and 85 in the engine. It is an A either way, because
industry is only 15 of 100. The decision: the vertical joins the rubric with a
tier, or the sheet row is wrong.

### 5.4 Organization duplicates

Scoring is per organization, so duplicates mean several grades and several
activities for one company. A rep on the wrong record sees no grade at all.

| name (exact search, 17 Sep) | records |
|---|---:|
| Sumersports | **6** |
| Merck | 2 exact (+1 "Merck Life Science") |
| jovia.org | 2 organizations on one domain |

The workflow can't fix this: it scores what exists and never merges. **Dedupe,
or name the canonical record per company.**

### 5.5 Legacy URL fallback — coverage

Measured today across all 21,871 organizations:

| website the gate can read | orgs | share |
|---|---:|---:|
| today: native `website`, then the "Website URL" field | 1,997 | **9.1%** |
| adding the legacy **"Website"** text field | 4,991 | **22.8%** |
| reachable **only** through that legacy field | 2,994 | 13.7% |
| `lh_website` adds | 1 | — |

**Reading one more field is a 2.5× lift in how many organizations can be scored
at all.** Every organization outside it gets "n/a - no website". The code change
is small. The decision is which field is canonical when two disagree, which is a
data-ownership question. Related, measured 17 Sep: 64.7% of open leads have no
organization, so a conversion gives a deal with nothing to score.

---

## 6. What is left

| item | owner | state |
|---|---|---|
| Live rename to `WF-ICP-Score`; confirm "Append audit row" is gone; WF-ERR's name reference | ICP session | **Needs n8n API access for this session.** The deploy is built and tested; dry-run first, then one PUT. |
| Paste the unconditional buying-signal line into the Clay `note:` column | Nik | One line: [`engine/clay_note_format.md`](engine/clay_note_format.md). |
| §5.1–5.5 | Chrissy | Above. None blocks the system running. |

---

## 7. Proof

- `npm test`: all green (unit, contract, static, golden), and the secret scan is
  clean.
- New statics today, each shown to fail on the version before it:
  - the note block executed from the doc, reproducing the live note byte for
    byte and always ending in the buying line;
  - the Sales Rep field is single-select A/B/C/D and never written;
  - the deploy against a mock n8n: rename, paths kept, ledger kept, rollback,
    and refusing on a path change, a running execution, or a backup path inside
    the repo;
  - the production name.
- Runbook: [`RUNBOOK.md`](RUNBOOK.md). Deploy, rollback and turning it off are
  all there.
