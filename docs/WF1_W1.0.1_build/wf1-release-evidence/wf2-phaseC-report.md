# WF-2 Phase C - E-matrix results, addendum items, and what remains

Suite: **161 static tests, 0 failures**. Discrimination: **31 mutants, all caught**
(`wf2-discrimination-proof.txt`). Build byte-identical on re-run. Artifact: 116 nodes.
Production WF-1 asserted unchanged at every step: `da23d080-a0e0-4126-81c0-0cca60908435`, 95 nodes.
Teardown verified: **0 doubles, 0 mocks remaining**.

The E-matrix was **derived**, not run verbatim - `wf2-architecture.md` §10 does not exist on this
machine (flagged in Phase A). Cases below cover every branch, gate and fail-safe in the built graph.

## Results (all on the live double, WRITE_MODE=live, real Pipedrive + real Slack)

| case | expectation | result |
|---|---|---|
| **E1 SENT** new person + org | enrich → org → person → lead w/ title convention, no activity | PASS - org reused, person 84632, lead titled `9990001 - [Events Visiting] [WF2C1 Expo 2026] - Toby - Valids - E1 Testperson` |
| **E4 REPLIED** Interested, first reply | alert, union preserves a manual label, activity, SL category | PASS - `PATCH OK -> Quarantine, 1.Cold, 2.Connected, 3.Responded` |
| **E5** second reply | NO second alert, CRM still processed | PASS - alert absent, chain continued |
| **E-FWD** forward path | resolve owner, forward the PROSPECT's reply | PASS - `toby@janeasystems.com`, `message_id=<mock-reply-1@example.com>` (the REPLY, not the trailing follow-up the mock plants on purpose) |
| **E6 DNC** | **ZERO** replies-channel posts, SL unsubscribe, DNC label | PASS - no Slack post at all; SL unsubscribe called; DNC label present |
| **E8 Out Of Office** | known category writeback, NOT forwardable | PASS - SL Category only, no forward |
| **E9 nurture** | replies-channel post, **NO** CRM write | PASS - Nurture Alert only, zero writes |
| **E10/E11 no lead** | ops warn, no writes, execution SUCCEEDS | PASS - warn fired, write went to Shadow Log as `/v1/leads/{none}` |
| **E11 BOUNCED** | bounce note, no replies-channel post | PASS |
| **E12 UNSUB event** | SL unsubscribe + DNC label, classifier-independent | PASS |
| **E-UNKNOWN** | ops warn only | PASS |
| **E-AUTH-BAD** wrong secret | silent drop behind 200, ops warn, nothing downstream | PASS - `auth=mismatch`, Normalize never ran, 0 writes |
| **E-AUTH-MISSING** | same as invalid | PASS - `auth=missing`, dropped + warned |

### One result that looked wrong and was not

On E6 and E12 the DNC label PATCH did **not** fire. Both bodies computed the correct 5-label union
including DNC and the correct lead id, but set `__skip: true`. Cause: an earlier batch had already
applied the DNC label, so `changed` was false - the idempotency guard doing its job. Verified
against Pipedrive rather than assumed: the lead ended with exactly
`Quarantine, 1. Cold, 2. Connected, 3. Responded, DO NOT CONTACT`, with the manual label intact.

## Addendum items

- **A** dead `.../person/` link - FIXED. No id now means **no link**, not a broken one. LK1-LK4
  assert the *rendered* link.
- **B** `Lead Labels Union` failure - DIAGNOSED. The v1 payload shape was never wrong; it was
  `/v1/leads/undefined` (B12 + B14). Proven by a real PATCH succeeding.
- **C** WF-ERR header - FIXED and deployed. `🚨 {{ $json.workflow.name }} — execution failed`;
  the duplicate `Workflow:` line dropped. versionId `fc1c0405…` → `b8ec4309…`, still active.
- **D** Smartlead deep link - WIRED, using the payload's own `app_url` first and constructing from
  `sl_email_lead_map_id` only as a fallback; no map id → no link. SLK1-SLK5.
- **E** Slack identity - STAGED. One constant (`SLACK_CRED`) plus `SLACK_CRED_WF2_PENDING`; the
  swap is two lines + rebuild, no graph change.
- **1 (secret validation)** - BUILT. `Verify Secret` → `IF Authentic` / `IF Auth Warn`, SHA-256
  digest compared in constant time, mismatch/missing → silent drop behind the already-sent 200,
  never a 500. Ships **unarmed** (`webhook_secret_sha256: null` → accept + rate-limited warn) so the
  shadow phase is not blinded. WS1-WS7. Verified live on the double with the hash armed.
- **2 (from_email)** - DESIGN ONLY, per instruction. See below.

## Defects found in Phase C: B7-B19

`wf2-defect-log.md` covers B7-B14. Added since:

- **B15** `sl_lead_id` never read `sl_email_lead_id`, so it was null on every real SENT event; the
  dedupe key is `campaign_id + sl_lead_id`, so **every first-email in a campaign collapsed onto one
  key** and all but the first would have been dropped.
- **B16** `Apply Enrich` published `__enriched` and every body read `$('Normalize')` - enrichment
  was computed and discarded. Fatal, not cosmetic: the real SENT payload carries no `lead_data`, so
  `Org Create` posted `{name: null}` → 400.
- **B17** the person body sent standard `job_title` → **403 on every person create**
  ("contact sync fields are not allowed because contact sync is not enabled"). The three title
  mirrors already carry it.
- **B18** `IF DNC` and `IF Forwardable` decided on the `SL Category` ack instead of the
  classification - `__forwardable` was `true` and the item still took the false branch, so
  **forwarding and classification-derived DNC were both silently dead**. Now locked by a general
  invariant (IFC1) that walks back through IF/Switch pass-throughs, not by two node names.
- **B19 OPEN, needs a decision.** Pipedrive's person *search* returns soft-deleted persons and the
  payload carries **no** `is_deleted` field, so `Person Pick` cannot tell a deleted record from a
  live one and would PATCH the dead one. Confirmed with person 84632 after deletion. The only
  reliable fix is a GET-verify before the patch, which adds one API call per event - a change to the
  call profile, so not made unilaterally. Low frequency (only inside Pipedrive's purge window after
  someone deletes a person), but it is silent data loss when it happens.

## Design-only: forward-owner fallback (item 2)

Not wired, per instruction - observe in shadow first.

If `sender_inbox` fails to resolve an owner (`Ops Warn Unknown Inbox` fires), resolve via the
campaign instead: `campaign_id` → the campaign's assigned sending inbox(es) → `forward_inbox_map`.
`GET /campaigns/{id}` / the campaign's email-account list gives the inboxes; the mapping is stable,
so cache it in workflow static data with a TTL alongside the existing dedupe state. Order of
preference stays: `from_email` → campaign inboxes → `forward_default` (melisa). Wire only if shadow
shows real misses; if `EMAIL_REPLIED` turns out to carry the lead's address in `from_email` (as
Smartlead's doc sample does), this becomes the primary resolver rather than a fallback.

## WF-1 backlog (logged, NOT actioned)

WF-1's HeyReach webhook has the **same exposure**: a public URL performing CRM writes with no
authenticity check. HeyReach's payload/secret mechanism needs checking first (it may differ from
Smartlead's `secret_key`). Separate follow-up release, deliberately not touched here.

## Still to do

1. **Phase D**: deploy to production ACTIVE with `WRITE_MODE=shadow` and `classify_enabled=false`;
   Nik registers the account-level Smartlead webhook; diff harness aligning **by lead** (Make's
   reply hook is `LEAD_CATEGORY_UPDATED`, ours is `EMAIL_REPLIED`), marking classification-dependent
   lines **DEGRADED** rather than discrepancies, plus a per-day classify counter; WF-2H health
   micro-workflow; report after 48-72h.
2. **Flip checklist** (Melisa's call, and it does not happen without these):
   - bind the `Anthropic API` credential + set `classify_enabled: true` + one smoke classify
   - rename the 4 ACTIVE `[Events Visiting]` Smartlead campaigns to the two-bracket convention
   - set `webhook_secret_sha256` to arm authenticity enforcement
   - bind the `Slack WF-2` credential
   - decide B19
   - flip `WRITE_MODE` to `live`
