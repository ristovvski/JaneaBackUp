# Task log — 2026-08-04 — WF-1 full audit (HeyReach → Pipedrive)

**Scope as given:** Melisa's question, applied to our own channel. Coverage reconciliation across all
HeyReach campaigns all-time (sent/accepted/message/reply per lead) vs Pipedrive (lead exists, person
exists, labels match reality, `lh_connected_at` on accepts); per-campaign report with the actual
lists; activities audit (any reply without its text logged); attribute the known lost reply of
30.07 09:46; one-line verdict, Melisa-report format.

**Mode:** read-only. No writes to HeyReach, Pipedrive or n8n. WF-1 untouched on `e28d282b`.

**Verdict shipped:** No — 1,071 of 1,115 production leads correct (96.1%); 41 have no record of the
HeyReach touch, 3 have a missing label. Plus 106 pre-production test-campaign touches never processed.

---

## What was done, and what it proves

- Grounded the truth source before using it: probed the HeyReach API for its actual vocabulary rather
  than assuming one. Per-lead `leadConnectionStatus` / `leadMessageStatus` / `leadCampaignStatus`
  enums, and the inbox message shape (`sender` ∈ {`ME`, `CORRESPONDENT`}).
- Audited **1,611 HeyReach leads across all 6 campaigns**, 253 conversations / 767 messages, against
  **49,406 Pipedrive persons with a LinkedIn identity, 57,152 leads and 20,569 `linkedin_messaging`
  activities**. All Pipedrive list reads sorted + paginated per the banned-class rule.
- Used **WF-1's own matching rule** for lead lookup (Campaign field == `campaign.name`, then title
  prefix) rather than inventing one, so a "missing lead" means missing by the workflow's definition.
- **Separated missing labels from extra labels.** Union labels never remove, and the sprint reply-Zap
  adds `connected`+`responded` ~90s after us. Had I collapsed the two, the report would have shown a
  phantom defect instead of 1 known cohabitant.
- Established the strongest positive results of the audit: **`cold` missing on 0 of 1,115** contacted
  leads, **`lh_connected_at` missing on 0 of 233** accepts, **0 wrong-person attachments**. Where
  WF-1 ran, it wrote correctly.
- Characterised the failure class precisely: production gaps are **lost events** (nothing written),
  not wrong writes. That is the substantive contrast with Make's email channel, and it is why one is
  replayable and the other is CRM corruption.
- Named the one real lost reply: **Person-ef1ea617, 2026-07-31T15:31:57Z**, whose lead was last
  updated 2026-07-29T11:43Z — two days before the reply. Missing `responded` *and* missing reply text,
  two symptoms of a single lost event.
- Found a genuine, previously unknown exposure: **HeyReach sometimes sends the opaque `ACoAA…` URN
  form instead of a vanity slug** (20 leads). WF-1 resolves persons on `lh_linkedin_profile_url`, so
  those miss — risking a duplicate person rather than an enrichment.

## Where my first pass was wrong — three findings verification changed

This is the part worth reading. The first run produced a cleaner-looking report that was wrong in
three places, and all three were caught by deliberately attacking my own results.

1. **"0 replies with no text logged" was a false pass.** The check accepted *any* non-empty
   `linkedin_messaging` note on the person, and there are 20,569 such activities org-wide — an old
   note from another source satisfied it. Re-checked by **content** (≥60% of the reply's own words
   present in a note): 60 of 63 verifiable, **4 not**. Of those 4, exactly one is a genuine miss; two
   are replies too short to verify by text (`"Yes"`, `"Hi"`) and one has an empty body. Reported that
   way rather than as a single number, because "4 missing" would overstate it as badly as "0" understated it.
2. **"23 with nothing in CRM" was inflated by slug matching.** 16 of the 17 production cases are
   people who *do* exist in the CRM under a different LinkedIn slug; only 1 is genuinely absent. The
   real finding was hiding inside my own artefact — the slug mismatch is itself the defect worth
   reporting.
3. **"No inbound message in that hour" needed proving, not asserting.** My first filter simply found
   nothing, which is equally consistent with the inbox not reaching back that far. Verified the inbox
   is **complete** — 767 of 767 messages, zero truncation, back to 14 July — which converts a null
   result into real evidence that the 30.07 09:46 event was *not* a reply.

A fourth error I caught but which did not reach the report: in the follow-up probe I resolved people
by name search with buggy candidate selection, so "0 activities on the person" appeared for people
who did have them. I discarded that pass and kept the indexed one. **Do not report activity counts
from a name-search resolution.**

## Partially solved / unconfirmed

- **The 30.07 09:46 event cannot be attributed.** Proven not to be a reply; most likely a lost
  `accepted` or `message_sent`. HeyReach exposes only *current* per-lead status, no event log, so a
  lost accept cannot be timestamped retrospectively. Andrew Miller-McKeever's and Person-6193c11f's label
  gaps are lost non-reply events, but neither can be tied to that timestamp.
- **Why 3.7% of events never arrive is unknown.** This is the root cause of every production gap and
  it is invisible from our side — a webhook that never arrives leaves no execution to alert on. Not
  diagnosed in this pass.
- **WF-1's go-live date is unprovable** (n8n retains ~13h). The claim that the test campaigns predate
  production is a strongly-supported inference from campaign dates + zero test-campaign leads, and is
  labelled as such in the report, not as fact.
- **Person-e77d99ff / Kamil Jałowiec replies are indeterminate**, not confirmed either way.

## What blocked me

| blocker | consequence |
|---|---|
| HeyReach exposes no per-lead **event history** — only current status | accepts/sends cannot be timestamped, so lost non-reply events cannot be dated or attributed |
| n8n execution retention ~13h | cannot confirm WF-1's deploy date, nor replay-verify which of the 41 events actually arrived |
| Pipedrive activities carry `lead_id` inconsistently (many `None` on older rows) | reply-text matching had to fall back to person-level indexing, which is what made the false pass possible |
| Long runs give no interim progress | `Select-Object -Last N` buffers the whole pipeline; Python buffers stdout when redirected. `python -u` + a log file fixes the second, and I switched to it mid-task |

## What can be improved

- **Add the member-id / public-id fallback to WF-1's person resolver.** WF-1 already stores both
  fields; the resolver just does not fall back to them when `lh_linkedin_profile_url` misses. Cheapest
  real fix available, and it closes 20 known cases.
- **Run this audit on a schedule.** The 3.7% arrival gap is unknowable from execution logs but
  trivially visible from reconciliation. That turns "we lost an event once" into a number we watch —
  the same argument as the WRITE_MODE watchdog: a promise is not a control.
- **Backfill the 41**, prioritising the one accepted-and-replied conversation that is invisible today.
- **Content-matching, not presence-matching, should be the default for any "was it logged" check.**
  The false pass here was not a coding slip; it was the wrong question. Presence proves a record
  exists, not that it holds the right thing.
- The audit script keys leads by `(slug, campaign_id)`. If a person's slug changes mid-campaign they
  would appear twice; not observed, but the key should be the member id once the fallback exists.

## Files produced

| file | what it is |
|---|---|
| `wf1-release-evidence/WF1_AUDIT_REPORT.md` | the deliverable, Melisa-report format |
| `wf1-release-evidence/wf1_audit_missing.csv` | 147 rows, with `classification` (absent vs slug mismatch) |
| `wf1-release-evidence/wf1_audit_label_mismatches.csv` | the 3 label gaps |
| `wf1-release-evidence/wf1_audit_missing_reply_text.csv` | the 4 unverified replies (strict result) |
| `wf1-release-evidence/wf1_audit_extra_labels.csv` | 1 cohabitant label |
| `audit_wf1_coverage.py` | re-runnable, read-only |
