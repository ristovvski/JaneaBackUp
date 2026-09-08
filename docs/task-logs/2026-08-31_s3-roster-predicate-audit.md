# 2026-08-31 — S3 roster / predicate audit (person level)

READ-ONLY task from Nik, relaying Melisa's final S3 wording. No deploys, no writes, no config
changes. All output to C0BQM1X9ZUY.
Posted: https://janea.slack.com/archives/C0BQM1X9ZUY/p1788193137818599

## DONE

- Bulk walks, all cached locally: leads 57,867 · persons 57,097 (cursor pagination) · deals 1,069 ·
  activities 38,601 · active registry 25,653.
- Roster diff. Missing from the deployed roster: Sergey, Matt Carothers, Chrissy Winkler,
  Person-f55206df (23094002, `active_flag:false`, still owns 291 persons). In ours but in neither
  role: Araks Grigoryan (24902545).
- Person-level gap for the eight: owned 3,652 / unprotected 2,042, split by owner and by arrival.
- Sergey separately: owned 11,037 / unprotected 10,444 / reply evidence 394 /
  unprotected AND replied 128. The carve-out reduces his contribution 10,444 -> 128.
- Label side (live leads): `3. Responded` 1,690 -> 396 unprotected; DO NOT CONTACT 7 -> 2;
  Disqualified 34 -> 13.
- Item 5 confirmed in code: `S3 Classify` decides on `creator_id in sales_user_ids` OR
  `channel_id === 'Surfe'`. No `label_ids` read, no `lh_campaign_name` read. `owner_id` is used
  only to pick a display name for `source_ref`.
- Five predicate variants W0-W4 measured at person level with captures / new rows / leaky.
  Recommended W3 = item-6 predicate + webform/legacy-Make exclusion: 21,834 / 19,624 / 0 leaky,
  versus W2's 569 leaky.
- Artifact: `AUDIT_S3_ROSTER/person_level_audit.json`.

## PARTIAL

- Label side covers LIVE leads only. `archived_status` on `/v1/leads` is accepted and then
  completely ignored (3,000 rows requested archived -> 0 archived; control lead reads back
  archived on a direct GET). Archived leads are reachable only via term-search, ~14,689 per-person
  searches. Offered as a separate bounded job; not run.
- Person arrival is DERIVED (leads first, then deals) because persons carry no creator field.
  495 of the eight's unprotected and 1,243 of Sergey's have neither, so they are reported as
  `arrival_unknown_no_lead_or_deal` rather than attributed.

## BLOCKED (awaiting Nik's word)

- Which variant to adopt (recommended W3).
- Araks Grigoryan's role — stays as a creator, moves, or comes out.
- Whether the archived label-side sweep runs.
- Whether the ~19.6k backfill runs at all. S3 polls the newest 100 leads every 15 min and never
  re-reads history, so a predicate change alone touches new arrivals only.

## IMPROVABLE / KNOWN GAPS

- S3 is a LEAD poller, so Melisa's "person then deal" case is structurally out of reach: 643/2,042
  (the eight) and 1,260/10,444 (Sergey) unprotected persons have no lead at all. Fixing that needs
  a person/deal watcher, not a predicate edit. Flagged in the post, not built.
- Reply evidence = reply-shaped activity OR a lead carrying `3. Responded`. Only 260 persons have
  a reply-shaped activity across 38,601 activities, so the label carries most of the signal; if
  Smartlead/HeyReach replies are not written as activities, Sergey's 394 is a floor, not a ceiling.
- `/api/v2/persons?start=0` is a hard 400. The first walk returned `[]`, got cached, and silently
  degraded every email/slug match to person-id-only (25,227 of 25,653 registry slugs skipped).
  Caught before reporting, whole pass discarded, switched to cursor pagination, and `cached()` now
  asserts a non-empty walk. Same failure class this audit exists to find.
- `/api/v2/leads/search?limit=500` returns 0 items; must stay at limit <= 100.
