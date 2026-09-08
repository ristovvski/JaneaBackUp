# Auditor: block-list contradiction resolved (my error), + global block-list baseline, + spot-check spec

Read-only. 2026-08-12. Evidence: `scratchpad/g4_blocklist.json`.

---

## 1. There is no contradiction to settle. Хранитель is right; my claim is withdrawn.

I said "no block-list resource exists (routes 400)". **Both halves of my evidence were invalid.**

**My probe method was broken.** `/leads/<anything>` matches a wildcard `:leadId` route whose validator
rejects a non-numeric id. Proven with a deliberately bogus control:

```
GET /leads/add-domain-block-list        -> 400  {"message":"\"leadId\" must be a number"}
GET /leads/global-block-list            -> 400  same message
GET /leads/zzz-definitely-not-a-route   -> 400  SAME MESSAGE   <-- control, path does not exist
GET /zzz-definitely-not-a-route         -> 404  HTML           <-- unknown TOP-LEVEL paths do 404
```

Every `/leads/*` 400 was the param validator firing, not a statement about the route. So my earlier
readings — first "route exists but isn't GET-able", then "not a resource" — were both unfounded, in
opposite directions, from the same bad signal. And my doc evidence was a single page (the unsubscribe
reference); its silence on a block list was weak evidence I treated as strong.

**Хранитель's citation is confirmed independently:** `POST /api/v1/leads/add-domain-block-list`,
body `{"domain_block_list": [...], "client_id": null}`, documented as adding an email **or** an entire
domain to the global block list.

**And there is a GET companion I never found: `/leads/get-domain-block-list`.** It works. So the POST
test is still worth running as a write-path confirmation, but it is no longer needed to settle
existence — and the GET gives Хранитель a read-back to verify the fixture domain landed and then
confirm its removal. **The design split does not die.**

## 2. New baseline I had wrongly reported as unavailable: the global block list

`GET /api/v1/leads/get-domain-block-list`, fully paginated: **4,024 entries.**

| | |
|---|---|
| bare domains | **1,372** |
| individual addresses | **2,652** |
| largest creation days | 2026-06-29 (1,571) · 2025-10-13 (1,063) |

Sources are dominated by Smartlead's own bounce detection, plus prior DNC CSV imports —
`Janea Systems Cold Email Outreach Stats - DNC (1)/(2)/(3).csv` (19/27/22),
`Janea DNC from Antonio Master Sheet - 7.16.2025.csv` (10),
`iReformat Report 2 - Janea Email Exclusion by Melisa.csv` (5), `JaneaDNCDomains.csv` (2),
and 3 `manual`.

**This also closes the `BLOCKED` question properly.** Bounce detection writes to the global block list,
which surfaces as `status: BLOCKED` on campaign-lead rows — matching the 42 % bounce correlation I
measured. `BLOCKED` is downstream of this list, not a separate mechanism, and still not the column
`SL Unsubscribe` moves.

## 3. Offer that bears directly on the one-way door

**A DNC-shaped population of 4,024 is already blocked in Smartlead.** When the 623 artifact lands I
will cross-reference every one of the 623 — by address **and** by domain — against these 4,024 and
report **how many of the 623 writes are already no-ops**. Same for the 288 not-founds, which may be
substantially pre-blocked by existing domain entries.

If a meaningful share of the 623 is already suppressed, the real write count and therefore the
one-way-door exposure both shrink before anything is fired. This is cheap and I can have it the moment
the list exists.

## 4. Spot-check spec — what I need in the artifact, and what I will assert

**I am blocked until the artifact exists.** To make the review meaningful rather than decorative, each
row should carry:

| column | why |
|---|---|
| registry reason / source row id | so a match is traceable to real DNC ground truth, not inferred |
| registry `email_lc` (as stored) | the left side of the match |
| matched Smartlead `lead_id` + email | the right side |
| **match method** (exact / normalized / domain) | the single biggest false-match risk |
| campaign(s) the lead belongs to | blast radius if wrong |
| last SENT / last REPLY on that lead | an active conversation being globally suppressed is the worst outcome |

**What I will assert on the sample:**
1. every match is **exact on a normalized address**, with no fuzzy or name-based matching;
2. no **role or shared mailbox** (`info@`, `sales@`, `contact@`, `support@`) is being suppressed
   account-wide on the strength of one registry row;
3. no **Janea-internal or partner address** in the set;
4. no **domain-level** entry that would blanket-block a live customer or an active prospect domain;
5. each registry reason resolves to a real row, and the reason actually implies do-not-contact;
6. no lead with recent two-way activity (a live thread) is in the set.

**On sample design — I would not take 20 at random.** A random 20 of 623 has poor power to find a rare
defect: if 2 % of matches are wrong, random-20 misses the problem about two-thirds of the time. I
propose **20 stratified** across the strata where errors actually live — domain-level matches, role
addresses, leads with recent SENT/REPLY, weakest reason codes, and anything matched by a normalized
rather than exact rule — plus a handful of pure-random rows to keep an unbiased read. Same twenty
minutes, far better detection. If you would rather have random-20 for defensibility, I will do both and
label them separately.

## 5. Arithmetic I can confirm now, and two definitions I still need

Both splits are internally consistent:

```
623 + 6 + 358 = 987     ✓ (the Smartlead resolve total)
1,978 + 286   = 2,264   ✓ (the Pipedrive matched total)
```

But I do not know what the `6`, `358`, `1,978` and `286` buckets *mean*, and after the 623 episode I am
not going to reconcile against a number whose definition I inferred. **One line each, please** — then
the post-run reconciliation is well-posed on the first attempt rather than the second.

My standing Pipedrive baseline for that reconciliation, captured pre-fire: **57,847 non-archived leads,
5 carrying 'DO NOT CONTACT'** (exact id set saved), and the archived-blindness caveat on any list read.
