# Two production issues — findings for Stefan / Melisa / Marci

Diagnosis date 2026-08-04. **Everything below is read-only evidence.** No Make scenario, hook,
campaign or account setting was touched; WF-1 stays on `e28d282b`; WF-2 stays in shadow.

---

## Issue 1 — "Make isn't creating leads" (Stefan's required-field diagnosis)

### Verdict: it is NOT a required field. No Pipedrive person field is required.

`GET /v1/personFields` — 115 person fields. 36 carry `mandatory_flag: true` and **every one of
them is a Pipedrive built-in system field** (`id`, `name`, `add_time`, `owner_id`, `campaign_*`,
`marketing_status`, …), each with `edit_flag: false` — i.e. read-only counters Pipedrive maintains
itself, not settings anyone configured.

Every one of the 11 custom fields Make writes is **not** mandatory, including the two suspects:

| field | key | required? |
|---|---|---|
| `lh_linkedin_profile_url` | `66f0af69…` | **false** |
| `LinkedIn Profile` | `b59a7d0a…` | **false** |
| Title / lh_current_position / LinkedIn Title | `0b72db8f…` `ab15ebd7…` `f8edcb01…` | false |
| lh_current_company, Source, lh_campaign_name, Medium, Marketing Hypothesis, Location | — | false |

So nothing needs un-requiring. **The hole is real, but the cause is different — and worse.**

### The actual size of the hole

Reconciliation of the Smartlead sent-list against every person email in Pipedrive
(44,783 distinct addresses, 113 pages, sorted reads only):

| | count |
|---|---|
| unique prospects emailed across the 4 active Ai4 campaigns | **891** |
| have a Pipedrive person | 591 |
| **have NO Pipedrive person** | **300 (34%)** |

Per campaign: Mario-Valids 87, Rune-Catch-alls 79, Rune-Valids 70, Mario-Catch-all 64.

The loss is **uniform, not a burst** — 18–43% in every single hour of every sending day. That rules
out an outage or a rate-limit spike and points at a per-lead code path.

### Three separate defects in scenario 8557031

**D1 — person matching is by NAME, not email.** Module 16 is
`pipedrive:searchPersons { term: "{{1.to_name}}", exact_match: true, limit: 1 }`. When someone with
the same name already exists, the router takes the "name was found" branch and creates the lead
against **that person** — a different human. 58 of the 300 prospects (100 lead rows) landed this way:

| we emailed | lead attached to |
|---|---|
| `pii-9e8228ef@example.invalid` | person 52536 `pii-9f60732e@example.invalid` |
| `pii-7caeaf93@example.invalid` | person 63760 `pii-8426ebb2@example.invalid` |
| `pii-3c416747@example.invalid` | person 37804 `pii-ce7e914f@example.invalid` |
| `pii-82eab592@example.invalid` | person 76020 `pii-f46bad26@example.invalid` |
| `pii-6079f401@example.invalid` | person 37366 `pii-91ecd4ed@example.invalid` |

Full list with a suggested action per row: `mis_attached_leads.csv` — 40 RE-POINT (different human),
30 attached person has no email at all, 20 review, 10 merge (same company, stale address).

This is the exact antipattern we banned in W1.0.11 for our own workflow: *match by the campaign
field, never by title/name.*

**D2 — every Pipedrive module has a `builtin:Ignore` error handler.** Modules 16, 29, 2 and 18 all
swallow their errors. That is why the scenario reports **40/40 runs successful with zero errors**
while 300 people go missing, and why nobody could find a failure message to diagnose. Any diagnosis
that starts from "what does the error say" is starved by design.

**D3 — a latent kill-switch on campaign names.** Module 28 is a regex parser over
`{{1.campaign_name}}` with pattern `\[([^\]]+)\]` and **`continueWhenNoRes: false`**. If a campaign
name contains no square brackets, the parser yields nothing and **the whole flow stops before any
Pipedrive call** — no person, no lead, no error. The 4 Ai4 campaigns are bracketed so they survive;
every older campaign name (`Ag Tech - Catch-alls - USA`, `NVIDIA GTC 2025 - …`) is not. Renaming a
campaign to drop the brackets silently switches lead creation off.

242 of the 300 have neither a person nor a lead, which means the flow died before the router (D3-class
halt or an ignored create failure under D2). Make's incomplete-execution queue would name the exact
module, but `GET /dlqs` rejects every parameter combination our token can send (HTTP 400
`Expected required property / Expected integer`) — so that last hop is unconfirmed and I'm not going
to guess at it.

### Trigger delivery also stopped

Scenario 8557031's last run was **2026-07-31T08:45:51Z**. The Ai4 campaigns kept sending until
**2026-07-31T19:53:26Z** — ~850 send events with no scenario run at all. (Those were follow-up steps
to leads already first-sent, so they add no new names to the 300.) No campaign has sent anything
since; the Ai4 sequences are exhausted, which is why it looks dormant now.

### The example lead, and Slava's manual patches

`74e0d0b0-8ddf-11f1-afef-110b8a9b80b4` = "Person-6b93835c | Trillion.com lead", person 84958,
**created 2026-08-01T19:30:30Z by Slava Kraievskyi** (user 25035678) — a hand-patch a day after
Marc's reply came in (we forwarded it 2026-07-31T17:03:06Z). It confirms the pattern: replies arrive,
no lead exists, a human creates it after the fact.

### WF-2 is immune — cited, not asserted

- **Static B4** (`wf2_static_contract_tests.js:502`) — *"person create: empty/absent values are
  OMITTED (no empty-string writes)"*, and asserts `job_title` is absent when empty. So a required
  field, if one ever appears, is the only thing that could bite us — and none exists.
- **Statics B27-3 / B27-11** — *"a non-matching email is never a candidate"* and *"B/U resolvers
  verify the email before accepting a person"*. WF-2 resolves people **by verified email**, so D1
  (the name-collision mis-attach) cannot happen to us by construction.
- WF-2 has no `Ignore`-equivalent: every write sits behind the WRITE_MODE gate and lands in the
  Shadow Log, and failures reach WF-ERR.

### Backfill — written, dry-run clean, NOT executed

`backfill_ai4_persons.py`, consuming exactly the reconciliation output
(`ai4_missing_persons.jsonl`, 300 rows) so the number and the backfill can never drift apart.

```
WRITE_MODE = 'shadow'   (dry run, no writes)
  would create : 300
  skipped      : 0 (already present on re-verify)
  enriched from Smartlead: 300
  custom fields omitted as empty (the B4 idiom): 810
DRY RUN COMPLETE - nothing was written.
```

It re-verifies each prospect **by email** immediately before writing, so a record created in the
meantime aborts that row rather than doubling it. Part B (the 58 mis-attached leads) is deliberately
**not** automated: re-pointing a lead moves history between two real people, and ~10 of them are the
same human under a stale address and need merging instead. That is a human call per row.

Nothing runs without `WRITE_MODE=live`, and that waits on Melisa/Marci.

---

## Issue 2 — double forwards

### Verdict: ours + Make's. Confirmed. And the gate held.

Make's **active** scenario 8557478 ("New_If Campaign gets a response, update lead with responded
label") contains **14 `POST /campaigns/{id}/forward-email` calls** in router 82 — one hardcoded per
owner (toby, andreas, mario, mirza, james, rune, chrissy, noah, matt …). It hits the same Smartlead
endpoint WF-2 does, off the same reply webhook. The standalone "Janea Auto-Forward Automation"
scenario is a red herring: inactive since its last edit in Jan 2025, zero log entries ever.

So during our live window every reply produced two forwards — one from Make, one from us.

| reply forwarded | Make (8557478) | WF-2 | recipient | copies |
|---|---|---|---|---|
| pii-b9ee8bb5@example.invalid | 18:39:10.146Z 07-29 | 18:39:10.927Z exec 12037 | rune | **2** |
| pii-d08614f0@example.invalid | 01:42:44.715Z 07-30 | 01:42:45.567Z exec 12077 | mario | **2** |
| pii-4acbb413@example.invalid | 16:37:55.174Z 07-31 | 16:37:55.771Z exec 12632 | mario | **2** |
| pii-cb4872cb@example.invalid | 17:03:05.170Z 07-31 | 17:03:06.171Z exec 12639 | rune | **2** |
| pii-f38c7b54@example.invalid | 15:36:59.890Z 08-02 | 15:36:59.826Z exec 12884 | review addr | **2** |
| pii-cc63be0d@example.invalid | — | 17:22:15.836Z exec 12644 | review addr | 1 |
| pii-b9ee8bb5@example.invalid (2nd) | — | 00:12:23.190Z 08-02 exec 12812 | rune | 1 |
| (reply on 08-03) | 16:54:53.555Z 08-03 | — (we were already shadow) | owner | 1 |

Sub-second alignment on five pairs — same trigger, two consumers. The 08-03 row is the control: after
we reverted, Make forwarded alone and the copy count went back to one.

We sent **12 forwards total** in the window (9 owner, 3 review); 5 of the 7 real-prospect forwards
were doubled. The other 5 were our own test lead.

### P1 gate check: clean

All 267 retained WF-2 executions audited. Window closed 2026-08-03T08:58:51Z.

```
forwards after 2026-08-03T08:58:51Z: 0
any other real write after close:    0
VERDICT: NO write of any kind after the window closed - the WRITE_MODE gate holds.
```

Two of the three review-routed forwards (`pii-cc63be0d@example.invalid`, `pii-f38c7b54@example.invalid`) went to the
personal Gmail that was still configured as the review address — already reported; Nik's relay to
Mario/Melisa is the outstanding item there.

### When WF-2 goes live

Make's forward block and ours must not both run. Either scenario 8557478's router 82 gets switched
off, or WF-2's forward stays gated — Melisa's call, and it belongs on the flip checklist.

---

## What we recommend, in order

1. **Nothing to un-require** — Stefan can drop that line of investigation.
2. **Fix D1 first** (name→email matching in 8557031). It is actively attributing prospects to the
   wrong people; every day it runs adds corruption. Melisa's scenario, our finding.
3. **Remove the `Ignore` handlers** (D2), or the next failure is just as invisible.
4. **Fix D3** or, at minimum, never rename a campaign without brackets.
5. Approve the 300-person backfill; work `mis_attached_leads.csv` by hand.
6. Decide who owns forwarding before the WF-2 flip.
