# Auditor answer: does `is_unsubscribed` suppress account-wide? — YES, and the sweep already uses
# the right endpoint. Plus a retraction of my own inference about `BLOCKED`.

Read-only. 2026-08-12. Answers the pre-write question assigned before `FIRE_SMARTLEAD` flips.

---

## Q1 — Account-wide or campaign-only? **Account-wide.** Three independent lines agree.

**1. The data model (wire).** `/leads?email=` returns **one lead record per email per account**:

```
TOP-LEVEL keys: company_name, company_url, created_at, custom_fields, email, first_name, id,
                is_unsubscribed, last_name, lead_campaign_data, linkedin_profile, location,
                phone_number, unsubscribed_client_id_map, website
  is_unsubscribed             = True
  unsubscribed_client_id_map  = {"0": "2026-08-11T13:15:59.229917+00:00"}

lead_campaign_data[] entry keys: campaign_id, campaign_lead_map_id, campaign_name, client_email,
                                 client_id, last_activity_at, last_reply_at, last_sent_at,
                                 lead_category_id
  unsubscribe field inside the campaign mapping: NONE
```

`is_unsubscribed` sits on the lead, not on the campaign association. **There is nowhere to store a
per-campaign value**, so it cannot be campaign-scoped. The `unsubscribed_client_id_map` is keyed by
*client* (`"0"`), not by campaign — consistent with account/client scope.

**2. The docs.** `POST /api/v1/leads/{lead_id}/unsubscribe` — *"Globally unsubscribe a lead from all
current and future campaigns."* A distinct campaign-scoped endpoint exists and is documented as the
alternative: `POST /api/v1/campaigns/{campaign_id}/leads/{lead_id}/unsubscribe` — *"unsubscribe a lead
from a specific campaign only (not globally)."*

**3. The sweep uses the global form.** Read off the live workflow:

```
SL Unsubscribe -> POST https://server.smartlead.ai/api/v1/leads/{{ lead_id }}/unsubscribe
   campaign-scoped form (/campaigns/{cid}/leads/{lid}/unsubscribe)?  NO
   global form         (/leads/{lid}/unsubscribe)?                   YES
```

**Conclusion: the 987 writes buy exactly what the registry promises** — suppression across all current
*and future* campaigns. **My pre-write concern is resolved in the sweep's favour and does not block
`FIRE_SMARTLEAD`.**

*Note on the wire test I could not run:* I tried to prove scope by finding a lead present in two
campaigns with divergent flags. Across 7 campaigns and 4,990 unique emails, **zero** emails appear in
more than one campaign — the lead sets are disjoint in this account, so the natural experiment does not
exist here. The structural argument above is what settles it, not an overlap observation.

## Q2 — Global block-list write endpoint? **No such resource.**

The documentation describes no dedicated global block-list / do-not-contact endpoint; **global
unsubscribe is the mechanism**, and it is what sets `is_unsubscribed`. My earlier read probes
(`/leads/global-block-list`, `/leads/blocklist`, `/leads/blocked` → 400; `/global-block-list`,
`/blocklist` → 404) returned 400 not because they are write-only but because they are not a resource.

## RETRACTION — my inference about the 1,650 `BLOCKED` rows was wrong

I wrote: *"actual suppression in this account is overwhelmingly `status=BLOCKED` (1,650), which is what
a global block list looks like reflected per campaign-lead."* **That was wrong**, and since there is no
global block list it could not have been right.

Tested on campaign 1923828 (53 BLOCKED rows vs 258 others), cross-referenced against `/statistics`:

| | BLOCKED rows | non-blocked rows |
|---|---|---|
| flagged `is_bounced` | **22 / 53 (42 %)** | 8 / 258 (3 %) |
| flagged `is_unsubscribed` | 11 / 53 (21 %) | — |

`status: BLOCKED` is a **mixed per-campaign-lead terminal status** — mostly bounces, some unsubscribes,
some other suppression — not a block list.

**Consequences for the reconciliation:**
- The **1,650 is not a suppression population** the sweep should be measured against. Drop it as a
  comparator; I will still report it as context.
- The **55 (`is_unsubscribed`, unique emails) is the correct column** that `SL Unsubscribe` moves. Post-run
  it should grow by the number of successful writes, and I will report both the count and the id set.

## The `623` relay — reframing accepted

Agreed: reconcile **eligible-vs-623** from the dry-run, not Smartlead-state-vs-623. My state baseline
(55 unsubscribed · 1,650 BLOCKED · 5 leads carrying 'DO NOT CONTACT' · 57,847 non-archived leads) stands
as the *before* picture for measuring deltas — it was never a comparator for 623, which is why it
didn't match.

## One thing to confirm before firing, which I could not settle

The documentation I read describes no **resubscribe / undo** operation. If that is right, a global
unsubscribe is a **one-way door for 987 leads** — irreversible via the API, and it covers future
campaigns by design. That raises the cost of a wrong match in the 987 from "noise" to "permanently
unmailable", so it argues for the dry-run count reproducing cleanly first. Worth confirming against the
docs or with Smartlead before `FIRE_SMARTLEAD` flips; I am flagging it rather than asserting it, because
I checked for the mechanism and not exhaustively for its absence.
