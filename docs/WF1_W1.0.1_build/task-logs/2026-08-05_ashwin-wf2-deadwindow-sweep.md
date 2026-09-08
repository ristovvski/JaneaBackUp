# Task log — 2026-08-05 — Person-b9e6150b trace / WF-2 dead-window sweep

**What was asked:** priority-insert during the duplicate-forensics run. A real reply
(pii-280f963f@example.invalid) at 2026-08-05T06:08:38Z showed 0 in the digest; suspected cause was WF-2's
documented dead window (OOM crashes, 2026-08-04T14:30Z–2026-08-05T07:00Z). Sweep all Smartlead
replies in the last 48h vs WF-2 executions, list unprocessed ones, confirm Make (still ON) handled
them. Read-only throughout.

## Two bugs caught in my own tooling before reporting anything

1. **First pass reported 0 Smartlead replies in 48h — wrong, a parsing bug.** I built the extractor
   on guessed field names (`email`, `last_reply_time`) at the top level of `leads-statistics` rows.
   The real shape has no such fields: replies live in a `history[]` array per lead, as
   `{type: "REPLY", time, ...}`; the lead's email is the row's `to` field. Verified live before
   rewriting: 90 REPLY events exist across the 4 campaigns all-time, 12 in the 48h window. This is
   the same class of bug as `backfill300-completion`'s unsubscribe check and `c1-daily-reports`'
   `__alert_reason` bug today — a standing pattern now, not a one-off.
2. **Second pass's "10/12 unprocessed by WF-2" used a banned check** — a raw substring search
   (`email in json.dumps(execution))`) across WF-2 execution payloads, exactly the class banned by
   the `no-substring-blob-checks` memory. Caught it before reporting the number as fact. Inspected a
   real execution's actual `runData` structure instead: the execution nearest Ashwin's reply time
   (13549, 06:42:59Z) turned out to be an unrelated test/probe hit (`Python-urllib/3.12`,
   `event=UNKNOWN`), not a real reply-processing run — so "closest execution" was never valid
   evidence either way.

## What's actually true, verified structurally

- **`CONFIG.WRITE_MODE = "shadow"`** on WF-2, confirmed directly from a real execution's `CONFIG`
  node output. WF-2 does not perform live writes/forwards right now — by design, not a bug (matches
  the standing WRITE_MODE gate from `make-forwards-second-copy`). This alone explains why WF-2 shows
  no live action for these replies; it says nothing about whether Make covered them.
- **`slack_channel_replies_at_flip: "C07LTD8UT70"`** is in WF-2's own CONFIG — once WF-2 flips live,
  it will start posting into the SAME channel this whole forensics investigation is about. Worth a
  note for whoever plans that flip: avoid recreating the Zap-274357187 style double-poster problem.
- **The real check has to be at the LEAD level, not the person level** — Make's "3. Responded" label
  lives on the Pipedrive lead, not the person. My first cross-check queried person changelogs and
  would have missed this entirely; caught before drawing a conclusion, corrected to
  `GET /leads?person_id=X` + label_ids.
- **Corrected finding, 9 distinct real replies checked at the lead level: 2 of 9 correctly carry
  "3. Responded"** (pii-6f8f48e5@example.invalid, pii-567b1851@example.invalid — the latter within ~15h of reply).
  **6 of 9 — including Ashwin himself — show only "1. Cold," no responded label, hours after the
  reply**: pii-67425a37@example.invalid, pii-280f963f@example.invalid, pii-135b4c7b@example.invalid,
  pii-90ec4caf@example.invalid, pii-06275333@example.invalid, pii-b02b50cf@example.invalid (2 leads,
  neither labeled). **This does NOT match "business impact zero expected."**
- **One more anomaly, not yet explained:** pii-7b1c0e1a@example.invalid has a real Make "Responded" Slack
  post (found in the duplicate-forensics harvest, 2026-08-04 22:11:35 IDT, linking to lead
  `7acdf900-85e5-11f1-a847-39f34a02ee6f`), but a Pipedrive person-search by his email + a lead lookup
  by that person_id returns **zero leads** — a person-record mismatch (likely two person records for
  the same real contact, or the search didn't resolve to the record Make actually touched), not a
  labeling gap. Not investigated further this pass.

## Not resolved — needs a next step, not closed out as "confirmed zero impact"

The evidence points the opposite direction from the expected "Make caught everything." Possible
explanations not yet distinguished: Make is genuinely lagging/broken for a subset of these specific
campaigns or inboxes; the 6 unlabeled replies are auto-replies/OOO-style content Make's own filter
correctly excludes (worth checking `email_body` content — e.g. `lauren.desalvo`'s reply funnels an
out-of-office assistant, visible in the earlier raw Smartlead capture in this session, which is a
LEGITIMATE reason to skip labeling); or a genuine Make outage/misconfiguration on these leads
specifically. **Reporting as an open, real finding — did not declare this closed or safe.**

## What can be improved

- Two more instances of the substring/wrong-field-name bug class in one investigation, both caught
  before shipping a false number. The standing rule (parse structured fields, verify shapes against
  one real response, never guess a field name or use `x in json.dumps(y)`) needs to be the default
  starting move for any new script touching an unfamiliar payload, not a check applied after
  suspicion — I still wrote the wrong version first both times.
- Did not check reply content (e.g., OOO auto-replies) before flagging the 6 as a gap — that's the
  natural next step before treating this as an incident.
