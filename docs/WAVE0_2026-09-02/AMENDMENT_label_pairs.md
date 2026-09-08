# Amendment to Wave 0 fix #1 — truthful label pairs in one PATCH

**2026-09-02, after Nik changed the Pipedrive handover automation** to fire only when the lead's
labels do NOT contain `DO NOT CONTACT` or `Disqualified`.

This reverses the morning's fix. Withholding `3. Responded` was the right control while the
automation was ungated; now the control is the suppressing label, and withholding Responded would
make the CRM lie about whether a human answered us.

Deployed to WF-2 `jp7rum9Z0YDJkQWv`, versionId **`9c821fcc`**, 174 nodes, still active.

---

## 1. Single-PATCH — verified, not assumed

Nik's constraint: never two sequential PATCHes, because if `Responded` lands alone first the
automation fires in the gap before the suppressing label exists.

**The estate was already correct here.** Checked against the live graph:

- Exactly **two** nodes PATCH `/v1/leads/{id}` with labels: `Lead Labels Union` (reply path) and
  `U Lead DNC Label` (unsubscribe path).
- They descend from **different outputs of `Switch Event`**, so they can never both run in one
  execution.
- A reachability check proves neither is downstream of the other.

That assertion is now **enforced in the build script** (`WF_SHARED/build_label_target.py`), so a
future edit that introduces a second label PATCH, or chains one after the other, fails the build
rather than reaching n8n.

`Person Patch` also exists but writes person custom fields, not lead labels.

## 2. One implementation, two nodes

The two label bodies drifted apart once already — that is what produced the defect. They are now
generated from a single file:

| file | role |
|---|---|
| `WF_SHARED/label_target.js` | `labelTargetV1()` — the only implementation of "which labels does this event earn?" |
| `WF_SHARED/test_label_target.js` | the class static — executes it over every case |
| `WF_SHARED/build_label_target.py` | embeds it verbatim into both nodes, asserts the single-PATCH invariant, deploys |

Both node bodies carry a generated header saying not to edit them in place.

## 3. The mapping, as deployed

| case | labels written, in one PATCH |
|---|---|
| explicit stop — category `Do Not Contact`, or the classifier's own `is_dnc` | `1. Cold` + `2. Connected` + **`3. Responded`** + **`DO NOT CONTACT`** |
| **unsubscribe event** | `1. Cold` + `2. Connected` + **`3. Responded`** + **`DO NOT CONTACT`** |
| negative reply — `Not Interested`, `Wrong Person`, `No Longer Working There` | `1. Cold` + `2. Connected` + **`3. Responded`** + **`Disqualified`** |
| genuine interest — `Interested`, `Meeting Request`, `Information Request` | `1. Cold` + `2. Connected` + `3. Responded` |
| unclassified / low confidence / unknown category | `1. Cold` + `2. Connected` + `3. Responded` |
| out of office | `1. Cold` + `2. Connected` — **no Responded** |
| bounce | `1. Cold` — **no Responded, no Connected** |

Existing labels are never removed; the write is always a union.

**Three category decisions you did not specify, made explicitly:**

- **`Wrong Person` and `No Longer Working There` → Disqualified.** A human replied and the lead
  cannot proceed. That is the negative-reply shape without claiming they opted out.
- **`Uncategorizable by Ai` / classifier failure → Responded only.** A human did reply, and the
  reply is already forwarded to the review address, so handing it to a person is the correct
  outcome — that is what handover is for. Inventing a suppressing label here would be a guess
  written into the CRM.
- **The old opt-out lock is removed.** Previously, a lead already carrying DNC that then replied had
  `Responded` stripped. Under the new condition that is unnecessary: Responded is truthful and the
  existing DNC keeps suppressing handover. Covered by a test.

`Disqualified` (`98008920-e942-11ef-b360-57187fe024ea`) was added to WF-2's CONFIG label map; it was
not previously there.

## 4. Verification

| check | result |
|---|---|
| `WF_SHARED/test_label_target.js` — Nik's five cases, the unsub path, all 10 real categories, precedence, union semantics | **22 passed, 0 failed** |
| the invariant over **288 combinations** of event × category × bounce × OOO × dnc | **PASS** — Responded never appears without its implied label in the same target set; bounce/OOO never produce Responded; bounce never produces Connected |
| both generated node bodies, `node --check` | **syntax OK** |
| single-PATCH reachability assertion | **PASS**, enforced in the build |
| `WF_LINTER/static_responded_class.js` (estate-wide) | **PASS** — both WF-2 writers `OK/shared` |
| `WF_LINTER/test_lint_rules.js` | **46 passed, 0 failed** |
| estate lint after redeploy | 185 findings, 39 high, **R14 = 0, 0 new findings** |
| errors in any touched workflow since deploy | **none** |

**Not yet proven by a live execution.** WF-2 handles ~130 events in 19 days, and none has arrived
since the deploy. The next real reply or unsubscribe will publish `__label_case`,
`__responded_written` and `__implied_label` on the item — added for exactly this reason, so the
first live run says which branch it took without anyone having to reconstruct it.

## 5. The gap this does not close

**WF-1 (HeyReach) has no reply classifier.** `M5 Labels Compute` and `M7 Labels Compute` write
`3. Responded` off the LinkedIn stage rank and can never produce `DO NOT CONTACT` or `Disqualified`.
So a LinkedIn reply saying *"stop contacting me"* gets `Responded` alone, and the handover fires.

That is consistent with your rule as written — the cases are classifier-derived and WF-1 has no
classifier — so the class static reports those two nodes as **`NOTE/no-classifier`** rather than
passing them silently. Closing it means either running the classifier on LinkedIn replies too, or
accepting that LinkedIn handovers get human triage. **Your call; nothing has been changed there.**
