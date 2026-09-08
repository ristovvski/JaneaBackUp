# Golden Example - building an n8n integration workflow the "WF-1" way

*A reusable blueprint distilled from WF-1 "HeyReach Receiver" (webhook -> CRM sync). Use it as the
standard when building the next workflow (WF-2, WF-3, ...). It is NOT "what WF-1 does" (that's the
system-reference doc) - it is HOW WF-1 is built, tested, shipped and operated, so the next one lands
at the same quality bar. Every rule below earned its place by preventing a real incident.*

Class of workflow this fits: **inbound webhook -> normalize -> route by event type -> guarded writes
to an external system (CRM / DB / API) + human notifications**, co-existing with other automations
on the same data.

---

## 0. The one-paragraph philosophy
Treat the workflow as **versioned software, not clickware.** Every change is a deterministic patch
on a JSON export, gated by tests that run the real node code, shipped through a scripted quiet-window
deploy with a saved rollback, and proven on a throwaway production-mode double before you trust it.
Config lives in one node; secrets live in env; bad input is caught on the first offender, not in a
report next week; and you never fight a co-existing automation - you match its values byte-for-byte
or you agree ownership.

---

## 1. Architecture patterns (the node graph)

**Spine:** `Webhook -> (Respond) -> CONFIG -> Dedupe -> Normalize -> Switch(event_type) -> N guarded branches`.

1. **CONFIG is a single Set node, and it runs FIRST.** All field keys/hashes, label ids, channel ids,
   feature flags, enum values, canon maps, base URLs, owner ids - everything - live in `CONFIG.jsonOutput`.
   No hardcoded ids anywhere else in the graph. Because CONFIG is upstream of everything, any node can
   read `$('CONFIG').item.json...`. Changing a channel or a field key is a one-line CONFIG edit, not a
   node hunt. (Ordering matters: `$('NodeX')` only resolves if NodeX already ran in this execution.)

2. **Normalize is the single translation layer.** It turns the raw provider webhook into a clean,
   stable internal shape (`n.lead`, `n.campaign`, `n.event`, plus derived fields). Everything downstream
   reads `$('Normalize')`, never the raw body. When the provider's payload shape shifts, you fix ONE node.
   Derived/parsed values (e.g. an event-marker parse) belong here too, computed once.

3. **Switch on the normalized event type**, one branch per event. Unknown events -> NoOp (explicit,
   not an error).

4. **Code-built request bodies, never inline field templates.** Each write node's body is an IIFE
   (`={{ (() => { ... return JSON.stringify(body); })() }}`) that builds the object in JS: omit-null,
   strip empty-string custom fields, guard every optional. Inline `{{$json.x}}`-in-JSON templates are
   how you get invalid JSON when a field is null (this was incident E1/E2).

5. **Guard every write.** Entity-creating POSTs have `retryOnFail=false`; all errors propagate to a
   dedicated **error workflow** (set `settings.errorWorkflow`) that posts to Slack. No node fails silently.

6. **Alert-before-writes for critical human notifications.** On the reply branch, post the Slack alert
   BEFORE any CRM write (continue-on-fail), so a downstream CRM failure never silences the human ping.

7. **Non-blocking tees for warnings.** A guardrail warn is `Normalize -> IF <bad?> -> Slack Warn`
   hung off the spine as a second connection that dead-ends. The main path (`Normalize -> Switch`) is
   untouched, so a warn can never block or reorder real processing.

8. **Gates mirror their patch builder.** An `IF` node in front of a PATCH returns true only when the
   builder would actually write something (stage advances OR a fillable field differs). Result: no empty
   PATCHes, and the behavior is idempotent - re-running the same event writes nothing.

---

## 2. Semantic invariants (decide these explicitly, per field, and TEST them)

- **Fill-if-empty vs always-overwrite is a per-field decision, written down.** Most enrichment is
  fill-if-empty (never clobber a human/other-source value). A few fields are last-touch always-overwrite
  (only when the incoming value differs = idempotent). Never leave it implicit.
- **Forward-only state.** Stage/status never downgrades (rank-gated in every builder).
- **Union / never-remove for shared multi-writer fields** (e.g. labels also written by another Zap):
  compute `union(existing, target)`, never a replace-set, so you are order-independent and don't wipe a
  peer's write.
- **Idempotency everywhere.** Deterministic dedupe key on the inbound event (no external crypto import);
  duplicate deliveries drop with zero downstream. Same-value writes are skipped.
- **Machine-catchable contracts over tribal knowledge.** If the team must name something a certain way,
  make the workflow PARSE it and post an ops warn on the FIRST bad one - don't discover it in reporting.
  Keep the human rule to one sentence ("event campaigns have two brackets").
- **Co-existence with parallel automations.** If another automation writes the same fields: either write
  values BYTE-IDENTICAL to its canon (so its later pass is a no-op, no flip-flop), or explicitly agree
  ownership. Assert this; a mismatched value churns daily.

---

## 3. The release protocol (this is the crown jewel - copy it wholesale)

Every change, however small, goes through all of it. No editor clicks in production.

1. **Deterministic patcher** (Python). Input = previous release's `patched.json`; output = new
   `patched.json` + `api-payload.json`. Rules: edit via unique-anchor string replaces with an assert that
   each anchor matched exactly once; write LF bytes; a second run must be **byte-identical**; a `validate()`
   pass asserts node count, the new code is present, the OLD code is gone, unrelated surfaces are untouched,
   `active==false`, no `pinData`. If you can't re-run it and get the same bytes, it isn't a release.

2. **Static contract tests** that execute the REAL node code and expressions against fixtures (a small
   JS harness: `runCodeNode`, `evalExpression`, mock `$('...')` outputs) - no calls to n8n/CRM/Slack.
   Tests must be **discriminating**: run them against the PRIOR release and confirm they FAIL there. Green
   on target + fails-on-prior = the tests actually assert the change. Keep prior invariants green.

3. **Git audit repo**, one commit per release, tracking the single `wf1.json`. Fixed author + fixed
   timestamps (reproducible), detailed commit body, no noise trailers. Bundle it (`git bundle`) per release.

4. **Quiet-window deploy** (scripted, never manual). For a LIVE workflow, check the execution gap first
   and pick a lull. Then: save rollback (current versionId) -> GET backup -> **refuse to PUT if active**
   -> deactivate -> PUT only `{name,nodes,connections,settings}` (prune settings to the API-writable
   allowlist) -> re-GET and diff intended-vs-actual = **"DIFFS none"** -> reactivate -> final verify. The
   deactivate->PUT->activate window is seconds; on a paused system it's free, on a live one it's a lull.

5. **Fresh-double live suite.** Clone the api-payload to a NEW workflow with its own webhook path, publish
   it, fire synthetic webhooks at it, and assert on **execution-truth** (the n8n run's node outputs) PLUS
   real CRM reads - NOT the final CRM state (a co-existing automation pollutes final state seconds-to-hours
   later; assert what YOUR execution did). Then **cleanup** (soft-delete the synthetic entities) and
   **teardown** (delete the double - which purges its executions) and assert **0 doubles remain** and prod
   versionId unchanged.

6. **Artifact set + report.** patched.json, api-payload.json, audit bundle, a release pack (all patchers +
   tests + runner + reference doc + a RELEASE_MANIFEST.json + CHECKSUMS.sha256), and a short
   `Wx.y_REPORT.md` (parser/diff, static counts, live table, deploy verification with the new versionId).

7. **Keep the two living docs in sync every release:** the system-reference doc and the memory index.

---

## 4. Operational discipline

- **Secrets only in env** (an untracked `*_env.ps1` / env file). Never printed, never committed, never in
  an artifact. Rotations update the credential + env only.
- **Read-only first on shared data.** Before touching data another team owns, do a read-only discovery
  pass and characterize the real shape/volume. Build an **anomaly gate**: if counts or shape differ wildly
  from expectation, STOP and go back to the human - don't apply. (A "~50 records" cleanup that turns out to
  be ~11,000 is a different decision.)
- **Human-in-the-loop for broad/destructive data ops:** dry-run (before->after, anomalies flagged) ->
  explicit approval -> apply CLEAN cases only, hold anomalies -> verify a random sample -> keep an audit
  file with every before/after (so any change is reversible).
- **Irreversible/outward actions confirm first.** Deploys, mass data writes, sends - state exactly what
  will happen and get a yes for the specific action; approval doesn't generalize to the next one.
- **Report faithfully.** DIFFS none means you verified it; if a live test polluted state, say why and how
  you isolated it (execution-truth). Don't over-claim.

---

## 5. Platform gotchas that WILL bite (n8n + this CRM class)

- `={{ ... }}` is an evaluated expression; `{{ ... }}` without the leading `=` posts the literal braces.
  (Real incident: a Slack node posted `{{...}}`.)
- PUT `/workflows/{id}` does not clear `pinData` - benign residual, inert in webhook runs.
- Slack node stores emoji as `:shortcodes:` in output and appends an automation footer; drive `channelId`
  from a CONFIG expression, never a literal id (assert "no literal channel ids").
- `$('NodeName')` throws if that node hasn't executed yet - mind spine ordering when a Code node needs CONFIG.
- CRM specifics (Pipedrive here): leads are v1 (custom fields are TOP-LEVEL hashed keys), persons are v2
  (`custom_fields` object); a combined unarchive+labels PATCH 403s -> split into two; clear a varchar
  custom field with `null`, not `""`; `creator_id` is NOT the update-author (per-update authorship isn't in
  the API - only the UI changelog).
- Provider payload quirks live in ONE place (Normalize). Example: custom fields arrived nested under
  `lead.lists[].custom_fields` (per-list, inconsistently populated), NOT a top-level `lead.custom_fields` -
  discover the real shape from live executions before coding against it.

---

## 6. Build checklist for the NEXT workflow

- [ ] One CONFIG Set node, first in the spine; every id/flag/canon lives there.
- [ ] Normalize as the only payload-translation node; downstream reads `$('Normalize')`.
- [ ] Switch on normalized event; unknown -> NoOp.
- [ ] Code-built bodies (omit-null, strip-empty); no inline field-in-JSON templates.
- [ ] `retryOnFail=false` on creators; `settings.errorWorkflow` set to an error handler that alerts.
- [ ] Critical human alert posted BEFORE writes on its branch.
- [ ] Guardrail warns as non-blocking tees; main spine untouched.
- [ ] Per-field fill-if-empty vs always-overwrite decided, documented, tested; forward-only state; union labels.
- [ ] Deterministic patcher with `validate()` + byte-identical re-run.
- [ ] Discriminating static tests (green on target, fail on prior).
- [ ] Git audit repo (fixed timestamps) + bundle per release.
- [ ] Scripted quiet-window deploy: rollback saved, refuse-if-active, PUT-verify "DIFFS none", reactivate.
- [ ] Fresh-double live suite asserting execution-truth; cleanup + teardown; 0 doubles; prod versionId asserted.
- [ ] Secrets in env only; read-only discovery + anomaly gate before shared-data changes; human approval for broad writes.
- [ ] System-reference doc + memory updated the same release.

---

*Reference implementation: WF-1 "HeyReach Receiver" (n8n `2jdjKM2NJr473GdA`), current release W1.0.13.1.
See `wf1-system-reference.md` for the concrete node-by-node spec and the release ledger (W1.0 -> W1.0.13.1)
for worked examples of each pattern above.*
