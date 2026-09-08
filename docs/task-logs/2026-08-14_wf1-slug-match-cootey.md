# 2026-08-14 — WF-1 person match: a single `www.` cost a live meeting request

Live: **WF-1 `c140222b`** (111 nodes) · WF-2 `268cfecf` · WF-2R `dde01df7` · WF-ERR `126624c7`.

## THE CASE

Person-9979a87c (Sr. Director of Data, Babel Street) replied to Noah's LinkedIn InMail at 12:46 UTC:

> Im heading back to Reston Virinia that week, what about the following week?

A scheduling request. WF-1 posted **"not in Pipedrive"** and wrote nothing.

## TWO ANSWERS, AND THE SECOND CONTRADICTS THE ALERT

**1. WF-1 never creates person or lead on a reply — by design.** M7 is resolve-only:
`Person Search Email → Search URL → Search Member → Person Get → Lead Get → Labels Compute →
Lead Patch → Reply Activity`, with `M7 Slack Warn` (no person) and `M7 No Lead Warn` (no lead) as
terminal branches. `Create Lead` / `Lead Create Gate` live on the earlier invite/sent path. A
replier is in the CRM only if the outbound event put them there.

**2. That is not why this failed.** Philip **is** person 85517 — with an existing lead
(`fb215d20`, human-owned) and two hand-written activities. The alert asserted an absence it had no
way to know.

| | value |
|---|---|
| HeyReach sent | `https://www.linkedin.com/in/pii-7a798b9a` |
| Pipedrive stores (`linkedin_lh`) | `https://linkedin.com/in/pii-7a798b9a` |

All four `Person Search URL` nodes sent `term = lead.url` with **`exact_match=true`**. Two strings
differing by `www.` are not an exact match. Proven live:

```
term='https://www.linkedin.com/in/pii-7a798b9a'  -> 0 hits
term='linkedin.com/in/pii-7a798b9a'              -> 1 hit  [85517]
term='philipcootey'                              -> 1 hit  [85517]
```

The member_id/public_id fallback (W1.0.16) also returned 0. And this was an **InMail** —
`email_address`, `enriched_email`, `custom_email` all null — so the email search, which normally
rescues this, never ran. No email meant the brittle route was the *only* route.

## THE FIX — WF-1 `c140222b`

Mirrors W1.0.16's member fallback, which already got the pattern right: **search by a normalised
key, then VERIFY the hit against the person's own field.** Widening a search without tightening the
check would just trade a false negative for a false positive.

* 4 × `Person Search URL` → `term = <slug>`, `exact_match=false`
* 4 × `IF URL Found` → no longer `items.length > 0`, but *"some returned person carries a LinkedIn
  value whose slug equals ours"*, scanning `custom_fields` as a **flat array** (persons/search
  returns no field keys — the W1.0.16 shape).

Normalisation subsumes `www`/no-`www`, `http`/`https`, trailing slash, `/pub/`, percent-encoding.

**Before applying, the script proved every search node has a verifying IF downstream** (via
`connections`, not name pairing) and refuses to deploy otherwise.

Statics 8/8 — the Cootey pair as the fixture, plus the false-positive controls Nik asked for:

| case | verified |
|---|---|
| www-form in, no-www stored (**the live bug**) | ✅ match |
| a different slug (`philcootey`) | ❌ miss |
| same-name different person (`philipcootey2`) | ❌ miss |
| trailing slash + http · `/pub/` · comma-joined field | ✅ match |
| no slug on our side · person with no LinkedIn value | ❌ miss |

**Wire-verified against the live API** with the DEPLOYED expression over Pipedrive's real response
shape: `philipcootey` → 1 item `[85517]`, verification `True`; nonexistent slug → 0 items, `False`;
the old request still returns 0.

## ALERT WORDING (Nik item 4)

`M7 Slack Warn`: **"not in Pipedrive"** → **"no match found (person may exist under a different
URL/email form)"**. Same family as today's WF-ERR `LOST` fix — an alert must not assert an absence
it cannot know. Both were confident statements about a negative that was really a lookup failure.

## PHILIP REPAIRED

Lead `fb215d20` — `responded` + `cold` union-added (**his human label preserved**), reply activity
`44143` with the message text. Deliberately NOT touched: title `'Phil Cootey'`, the empty campaign
field, owner 25733113 — it is a human's lead, and those conventions are for leads we create. Also
skipped the person stage patch M7 would have done: `effectiveRank` is a `max()`, so the next event
self-heals, and minimum footprint wins on someone else's record.

Team alert posted (backfilled-marked), addressed to Noah, naming the follow-up it continues.

## HANDED TO АУДИТОР — the format count

How many stored `linkedin_lh` values are no-`www.` (i.e. would have missed)? **My own sample is not
usable and I said so**: 300 persons returned only 4 with any LinkedIn value, all `www.`-form, which
contradicts Cootey's own record — so I suspect the `custom_fields` query param, not the data. Told
him to verify the read shape before counting. Same family as the leads-statistics trap that produced
a confident fictional "0 replies" earlier today.

If the no-`www.` population is large, past "not in Pipedrive" warns were **match misses, not
absences**, and this normalisation should run as a historical recovery sweep. Nik: that decision
comes after the number.
