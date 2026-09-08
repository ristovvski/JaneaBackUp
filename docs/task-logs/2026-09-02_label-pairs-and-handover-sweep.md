# 2026-09-02 — truthful label pairs + handover sweep

**Task:** Nik gated the Pipedrive handover automation on labels NOT containing
`DO NOT CONTACT` / `Disqualified`. Four items: (1) write the full label union in ONE PATCH on the
unsubscribe and negative-reply paths, verifying single-PATCH; (2) keep the bounce/OOO locks;
(3) class-level static for the new rule; (4) read-only sweep of open handover activities on
registry-suppressed people. No Slack used.

**Outputs:** `WF_SHARED/` (shared engine + statics + builder),
`WAVE0_2026-09-02/AMENDMENT_label_pairs.md`, `SWEEP_handover_2026-09-02/` (report + 3 CSVs).

---

## DONE

### 1 + 2 — label pairs, one PATCH
- **Verified single-PATCH before changing anything:** exactly two nodes PATCH lead labels
  (`Lead Labels Union`, `U Lead DNC Label`), they hang off different `Switch Event` outputs, and a
  reachability check proves neither is downstream of the other. **The assertion is now enforced in
  the build script**, so a future second PATCH fails the build.
- **One implementation, two nodes.** `WF_SHARED/label_target.js` → `labelTargetV1()`, embedded
  verbatim into both bodies by `build_label_target.py`. The drift between those two nodes is what
  caused the original defect; it is now structurally impossible.
- Mapping deployed: explicit stop / UNSUB → Responded + DO NOT CONTACT; negative reply → Responded
  + Disqualified; interest → Responded; OOO → no Responded; bounce → no Responded, no Connected.
- `Disqualified` added to WF-2 CONFIG (it was absent). Old opt-out lock removed — obsolete now.
- Deployed WF-2 versionId `9c821fcc`, 174 nodes, active, no errors since.

### 3 — class static
- **Behavioural**, not textual: `WF_SHARED/test_label_target.js` executes the engine —
  **22 passed**, including the invariant over **288 combinations**.
- **Estate-wide**: `WF_LINTER/static_responded_class.js` rewritten — a Responded writer must derive
  its target from `labelTargetV1`, or provably not emit the label. **PASS.**
- `R14` in `lint_rules.js` taught to accept the shared engine, and to skip rule engines; linter
  rebuilt from source and redeployed. 185 findings, 39 high, R14 = 0, **0 new findings**.
- Existing `test_lint_rules.js`: **46 passed**.

### 4 — sweep (report only)
Paged all 5,474 open activities, 161 are Handover. Resolved each to a person by email, or by
LinkedIn URL where there was no email, then checked membership through `dnc_pre_add_gate`.

- **71 open handover activities** on people held as `negative_reply` (68) or `explicit_opt_out` (3)
  — 66 distinct people, 64 distinct leads, oldest 2025-02-12, newest 2026-08-14, 70 owned by Melisa.
- 42 of those leads already carry Disqualified/DNC; **29 carry neither** — the projection backlog
  showing up a second time. Labelling should precede closing for those.
- 63 leads archived, 6 live, 2 with no lead.
- 11 more blocked as `employee_connection` — reported separately, outside the specified target set.
- 52 unmatchable, itemised: 46 activities with no person and no lead, 6 whose lead has no person.
- CSVs with Pipedrive URLs per row; nothing closed or modified.

---

## PARTIAL

- **No live execution has exercised the new label code yet.** WF-2 sees ~130 events in 19 days and
  none arrived post-deploy. Proven by 22 behavioural statics + `node --check`, not by production.
  `__label_case` / `__responded_written` / `__implied_label` were added to the node output so the
  first real run is self-describing.
- **The sweep cannot separate `unsubscribe` from `client`.** `dnc_pre_add_gate` returns
  `entry_type / source`, not the registry's `reason` column, so the 3 `explicit_opt_out` rows may
  include a `client` row. The 68 `negative_reply` rows map one-to-one to `reply_dnc` and are exact.
  A reason-level answer needs a registry reader that does not exist; I did not build one because
  the sweep was authorised as read-only and no new workflow was authorised.
- **52 handover activities remain unclassifiable** — no identifier to match on. Not counted, not
  cleared.

## BLOCKED

- Nothing. Two decisions pending: whether to close the 71 (and whether to label the 29 first), and
  whether the 11 `employee_connection` rows count.

## IMPROVABLE

- **WF-1 has no reply classifier**, so a LinkedIn "stop contacting me" writes `3. Responded` alone
  and the handover fires. Consistent with the rule as written, flagged as `NOTE/no-classifier` by
  the static rather than silently passed. Closing it means classifying LinkedIn replies too.
- **A rule engine matches its own documentation.** The class static and `R14` both had to learn to
  skip nodes carrying a rule-registration signature, because the linter's own text quotes
  `label_ids,` and `targetSet.push(...)`. Any future textual scanner over this estate needs the
  same exclusion.
- **The 29 hits with no suppressing label are the Wave 1 projection backlog surfacing in a second
  place.** Worth treating as one problem rather than two.
- `WF_SHARED/` is now the third build-from-source mechanism alongside `build_rules.py` and
  `build_linter.py`. They should converge on one pattern before a fourth appears.
