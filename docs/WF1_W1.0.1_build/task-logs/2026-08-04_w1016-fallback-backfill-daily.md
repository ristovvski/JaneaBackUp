# Task log — 2026-08-04 — W1.0.16 resolver fallback + gap backfill + daily reconciliation

**Scope as given:** three items from the WF-1 audit. (1) member_id/public_id fallback in the person
resolver, full protocol: statics with real URN fixtures, mutants, quiet-window deploy, live
acceptance, then re-key the audit by member_id. (2) Backfill the 41 production gaps, dry-run → owner's
word → live, priority P1 Rishab / P2 the accepted / P3 invite-only; the 106 test-campaign touches NOT
backfilled. (3) Fold the reconciliation into the daily automated checks with a digest line.

**Naming:** shipped as **W1.0.16**, not W1.0.15. W1.0.15 is already live in WF-1 — it is the M7 alert
gate (duplicate reply alerts), present in the 98-node baseline `e28d282b`.

---

## Item 1 — W1.0.16, LIVE and accepted

**Live: versionId `5525eba3-0cfa-4a64-bc34-d5b2d26a5072`, 110 nodes** (98 → 110, +12: three nodes ×
four resolver branches). Statics **33/33**, mutants **21/21**, live acceptance **8/8**.

Shape, per branch: `IF URL Found ─[false]→ Person Search Member → IF Member Verified ─[true]→ PID
From Member → Person Get`, with the false leg going to the original not-found target (`Person Create`
on the sent path, the Slack warn on M5/M6/M7). No pre-existing node's parameters changed — a static
byte-compares all 98 baseline nodes, and one mutant proves that guard bites.

**The justification got stronger under measurement, not weaker:**
- 660 CRM persons already carry the ACoAA URN as their LinkedIn URL, with confirmed same-human
  duplicates (Person-fff1f4b0 43925 vs 42651, Person-2030b8bb 43951 vs 42725).
- The stored `member_id` equals HeyReach's `linkedin_id` in **16 of 16** checked production cases.
  (The reference described this field as "numeric HeyReach lead id" — that is wrong; the HeyReach
  campaign-lead id matched 0 of 16. Reference corrected.)
- Across **all 1,223 real production keys**: 1,089 resolve to exactly one person via `member_id`,
  **zero** resolve to a single person on any other custom field, and 43 hit two persons — both on
  `member_id`, i.e. genuine duplicate person records (`edkeisling` among them).

That 43 changed the design. Refusing on ambiguity would send the sent-branch to `Person Create` and
mint a *third* duplicate, so the resolver takes the **oldest (lowest) person id** — the same
oldest-wins rule as WF-2's B27, and deterministic regardless of response order.

### The bug I shipped, inert, and how it was caught

The first deploy (`c1292c4b`) verified matches by indexing `custom_fields[member_id]` on the search
result. **That field does not exist**: `persons/search` returns `custom_fields` as a *flat array of
values with no keys* (the full person object returns a keyed dict — I generalised from the wrong
endpoint). Every verification silently returned false, so the fallback was **inert**: every event
took exactly its pre-W1.0.16 path. No regression, no wrong writes — but no benefit either.

The statics passed because **my fixtures mocked the shape I assumed**. This is the B11 class again:
when the harness encodes the same wrong assumption as the code, green means nothing. Only live
acceptance caught it. Fixed by: rebuilding fixtures from the verified live response, a static that
fails if the expressions index `custom_fields` by key at all, and a mutant that reintroduces the
exact bug. Second deploy `5525eba3` passed acceptance 8/8.

### A second finding from acceptance

The first acceptance re-run resolved to person **85101 — the fixture I had deleted minutes earlier**.
Pipedrive `DELETE` is a soft delete and **`persons/search` still returns deleted records**, so
oldest-wins picked the dead one. Test fixed with a unique key per run, but the underlying behaviour
is real and **pre-existing for all three searches** (email, URL, member), not introduced here: WF-1
can resolve to a soft-deleted person. The search response carries no `is_deleted` flag, so it cannot
be filtered where the decision is made. **Open — see below.**

### Re-keying the audit corrected our own number

Keyed by member_id, production gaps go **41 → 25** and "nothing in CRM at all" **17 → 1**. Sixteen of
the 41 were never missing; the audit's slug-keyed matching could not see them, the same blind spot
WF-1 had. The honest production gap is **25 (2.2%)**, and yesterday's 41 over-counted by our own
measurement error. Live campaign drift also moved accepted 269→274 and replied 69→70.

## Item 2 — backfill: dry-run clean, NOT executed

Awaiting the owner's word. `WRITE_MODE=live ONLY=P1` (then P2, P3). Plan in
`wf1-release-evidence/wf1_backfill_plan.csv`.

| priority | count | what |
|---|---|---|
| P1 | 3 | label repairs on existing leads + the reply text that never landed (Person-ef1ea617, Andrew Miller-McKeever, Person-6193c11f) |
| P2 | 1 | accepted with no CRM record (Dr. Fairbanks, NBCUniversal) |
| P3 | 24 | invite-only with no CRM record |

Every write mirrors a WF-1 invariant rather than inventing one: labels are a **union** (W1.0.7),
`connected` is only ever set by a real accept (W1.0.9), titles follow
`{campaign.id} - {campaign.name} - {full_name}` with the Campaign field set (W1.0.11), empty custom
fields and empty notes are omitted (R4 / W1.0.6), persons resolve URL → member_id → slug (W1.0.16).

**A defect in my own backfill, caught by reading the dry-run rather than trusting it:** the first
plan would have posted a reply activity for Person-6193c11f, whose reply text the audit had already
verified as logged — a duplicate. It checked "is this lead in P1?" instead of "is this text already
in the CRM?". Fixed with a content check (≥60% word overlap against existing notes on the person and
lead), the same content-over-presence rule the audit itself had to learn. Re-run with the guard.

## Item 3 — daily reconciliation

`daily_linkedin_reconcile.py` — read-only, emits one line:

```
LinkedIn channel: 41 touches in the last 24h, 40 in CRM, gaps: 1 (Person-fbbb498b / Acme)
```

Excludes the four pre-production test campaigns by id, so the accepted gap cannot resurface as daily
noise. Appends to `linkedin_reconcile_ledger.jsonl` — execution retention is ~13h and a gap trend
needs history that outlives it, the same reason WF-2S keeps its own ledger. Posts to Slack only when
`SLACK_WEBHOOK` is set, so a cron dry-run is silent.

**Scheduling — read this, it is not fully done.** I registered a session job (daily 07:53) that will
produce digest lines while this session lives, but that scheduler is **in-memory, dies with the
session, and expires after 7 days**. It is not production scheduling and I am not presenting it as
such. For durable scheduling I delivered `run_daily_linkedin_reconcile.cmd` plus the exact
`schtasks` line, which needs one thing I deliberately did not do: a persistent `wf1_env.cmd` holding
live credentials next to the script. Writing API keys to a permanent file in the project is the
owner's call, not mine, so **item 3 is complete as code and pending on that one decision.**

The better long-term home is an n8n Schedule Trigger — n8n is always on, and the digest would post
through the same Slack path as every other WF-1/WF-2 alert. That is a build, not a config change, so
it is flagged rather than assumed.

## Open / blocked

| item | state |
|---|---|
| Backfill live execution | waiting on the owner's word (P1 → P2 → P3) |
| Soft-deleted persons are resolvable by every search | real, pre-existing, unfixable at the search step (no `is_deleted` in the response). Options: an `is_deleted` gate after `Person Get`, or prefer non-deleted once Pipedrive exposes it. Not attempted here — it touches the frozen core past the resolver |
| Why ~2% of events never arrive | still undiagnosed; the root cause of every remaining gap. The daily digest makes it visible, not explained |
| Durable scheduling | pending the credentials-file decision above |
| 43 duplicate-person pairs sharing a member_id | surfaced by the collision measurement, incl. known dupes (Person-45bca53f). Resolver now picks oldest deterministically; the duplicates themselves are untouched |
| The 30.07 09:46 lost event | proven not to be a reply; unattributable (HeyReach exposes no event log) |

## What can be improved

- **Verify response shapes against the live API before writing fixtures.** Both defects this task
  came from assuming a shape: the keyed-vs-array search response, and presence-vs-content for reply
  activities. A fixture copied from a *different* endpoint is worse than no fixture, because it makes
  the suite agree with the bug.
- **Live acceptance earned its place.** 33 statics and 21 mutants all passed on a feature that could
  never fire. Cheap unit-level proof cannot detect a wrong contract; only real traffic can.
- The 24 P3 invite-only gaps are low value individually. If the arrival gap gets fixed, they stop
  accruing — worth fixing the cause before spending effort on the tail.
- The audit and the backfill now duplicate their CRM-scanning logic (~15 minutes each). If both are
  going to run regularly, the person/lead index should be cached to disk with an incremental refresh.

## Files

| file | what |
|---|---|
| `patch_wf1_w1016.py` | the patcher, with the measured contract documented in-place |
| `wf1_w1016_static_tests.js` | 33 statics, real-shape fixtures |
| `wf1_w1016_discriminate.py` | 21 mutants, all caught |
| `deploy_wf1_w1016.py` | quiet-window deploy with baseline-version guard + backup |
| `accept_wf1_w1016.py` | live acceptance, fixture created and deleted |
| `backfill_wf1_gaps.py` | dry-run clean, gated on `WRITE_MODE=live` |
| `daily_linkedin_reconcile.py` + `run_daily_linkedin_reconcile.cmd` | item 3 |
| `wf1_backup_before_w1016_*.json` | pre-deploy snapshots (both deploys) |
