# GATE: company-domain block + a real incident I caused and fixed same-turn

Дата: 2026-09-09.

## Incident (own mistake — full disclosure)

Deploying the domain-block feature via my usual surgical-patch script, I diffed live vs local and
saw 12 "new" nodes needed — should have been 1 (`Get Domain Blocklist`). **I ran the patch anyway
without stopping to ask why**, which silently RESURRECTED the entire queue-mode apparatus
(`Check Queue Depth`, `Enqueue Rows`, `Is Sync?`, `Log Ingress`, retrieval-by-queue, etc.) that Nik
had deliberately REMOVED on 2026-09-02 — discovered only because a leftover live node
(`Retrieve Removed`) carried Nik's own dated explanation: the queue (`dnc_gate_queue`) never
existed and the drainer never ran once, so every "queued" answer was a promise that could never be
kept. My patch script only knew how to ADD nodes it found in local-but-not-live, never remove
extras, so it silently restored 11 dead nodes instead of failing loudly.

**Fixed same-turn**: reconstructed the correct post-09-02 architecture directly from the live
node's own comment + a node-by-node diff (not guessed), rewired the gate to exactly that graph plus
my one real addition, redeployed with an explicit before/after node-set assertion that aborts on
any mismatch, and live-tested both the submit and retrieve paths end to end. Verified: submit
classifies correctly (own-domain, clean), retrieve returns the honest 410. `dnc_gate_queue_drainer`
(inactive) got the same domain-block addition but is now confirmed fully obsolete per Nik's ruling
— flagged, not deleted (never delete a workflow tied to a live incident without asking first).

**Root cause, generalized**: a second real n8n gotcha found in the same fix. `Get Domain Blocklist`
was wired as a PARALLEL SIBLING of `Get Registry Match (Batch)`, both fed by the same upstream —
`Classify Batch` reads it by name (`$('Get Domain Blocklist')`), the same pattern already proven
safe for `$('Normalize Batch')`. But that pattern only works because `Normalize Batch` is a TRUE
ANCESTOR in `Classify Batch`'s own wired chain — a parallel sibling has NO execution-order
guarantee: n8n fired `Classify Batch` as soon as its own direct input completed, without waiting for
the sibling, throwing "Get Domain Blocklist hasn't been executed" on the very first real submit
call. Fixed by chaining it as a true ancestor (`Normalize Batch → Get Domain Blocklist → Get
Registry Match (Batch) → Classify Batch`) instead of a parallel branch.

Memory saved: `n8n-named-reference-needs-ancestor-not-sibling.md`,
`always-diff-both-directions-before-patch.md`.

## Company-domain block — done, deployed, verified live

- `gate_classify_batch_js`: checked AFTER own-domain, BEFORE person-level registry lookup — a
  banned domain BLOCKS with `reason: 'company_dnc / <domain>'` regardless of the specific person's
  own history. Fail-open (positive shape check, same discipline as the depth-0 fix): a missing/
  misresolving `dnc_domains` table degrades to "nothing is blocked," never a crash, never a false
  block. Same byte-identical code shared with the drainer.
- 8 new/updated static tests (banned domain blocks with zero person history, wins over CLEAN, a
  `removed`-status domain entry does NOT block, ordinary domains unaffected, fail-open on a bad
  read shape, own-domain still wins over company-domain, drainer parity, the ancestor-not-sibling
  ordering guard). 105/105 total pass.
- Live-verified: a banned-domain email correctly classifies (tested against the isolated node);
  the full gate now runs clean end-to-end post-fix.
- `dnc_domains` table itself does not exist yet — needs Nik to create it (spec:
  `DNC_DOMAINS_build/CREATE_DNC_DOMAINS_TABLE.md`). Import payload ready
  (`DNC_DOMAINS_build/domains_import_payload.json`, 1,373 domains, verified dedupe/clean/zero
  free-mail hits) — blocked only on the table id.

## Also cleaned up

5 dnc_contract_tests.js tests that asserted queue-mode-specific behavior (sync/queue split,
fail-open on queue depth, retrieval done/pending split, queue eta, ingress logging) were deleted,
not fixed — the features themselves are gone by Nik's own ruling, not a regression to chase.
Replaced with 2 tests covering what's still true post-removal (row_key stripped from response, the
honest 410 retrieve path).
