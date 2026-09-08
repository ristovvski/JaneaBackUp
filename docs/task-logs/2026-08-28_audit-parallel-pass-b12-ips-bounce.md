# 2026-08-28 — Аудитор: parallel read-only pass (B12 grep · WF-2 source IPs · bounce class)

Read-only. Report in #niks-channel; artifact `audit-artifacts/parallel_pass_20260828.json`.

## 1. B12 grep — NO instance #3

32 workflows, connections parsed, transitive walk-back, every candidate verified **by reading the
code**. 85 `$json.__field` reads: **73** writer-is-immediate-upstream, **12** two-or-more hops back,
**0 live instances**.

Candidates and why each died:
* `IF No Lead` ← `Merge Reply Ctx` reads `$('Lead Resolve').item.json` **by name**; its comment
  documents the original fix ("R Deal List now sits between … read the lead result BY NAME").
* `IF Person Found` ← `Carry Person Ctx` returns the verified person object.
* WF-1 `PID Resolved` `$json.org_id` — last term of
  `$json.data?.org_id ?? $json.data?.organization_id ?? $json.org_id`, needed for the
  `IF Rank Allows Invited` branch. Correct as written.
* `Classify Parse` / `Pick Last Message` / `Claim Nurture` read real response fields.

**The finding is the shape, not a bug:** those 12 reads are separated from their writer only by
pass-through nodes, so inserting one HTTP/dataTable node creates instance #3 — exactly how the reply
path broke (`R Deal List` inserted between `Lead Resolve` and `Merge Reply Ctx`). Worst: `Shadow Log`
`__skip` 7 hops · `Gate Person Create` `__skip` 5 · `Body Reply Alert` `__lead_id`/`__person_id` 5 ·
`Body Person Patch` `__person` 4. Structural fix: read carried context by name.

## 2. Source IPs — premise inverted

WF-2 authenticates with a **secret, not an IP allowlist** (no IP literal exists in the workflow), so
IPs came from each execution's captured `x-forwarded-for`, attributed **by payload shape**.

| origin | n | UA | verdict |
|---|---|---|---|
| `4.182.88.118` | 656 | axios/1.18.0 | **OURS** — n8n Cloud egress; bodies carry `__reconciled`/`__reconciled_by` |
| `16.176.213.221` | 67 | axios/0.19.2 | **Smartlead** — EMAIL_REPLY, AWS ap-southeast-2 |
| `3.106.220.241` +4 | 6 | axios/0.19.2 | **Smartlead** — EMAIL_BOUNCE with bounce fields |
| `91.217.61.179` | 37 | browser / curl / Python-urllib / janea-matrix-harness | **OURS** — workstation |

**Risk window CLOSED**: no unattributed third party in the retained history (07-29 → 08-28);
`__auth_ok=false` count **0**. Dedupe-suppressed measured **41, not 55** (stated, not fitted):
26 from our reconciler replays, 15 from the workstation, **0 from Smartlead**.

## 3. Bounce class — detection rule

521 stat rows + live bounce webhooks. Kyle: `pii-febd7426@example.invalid`, campaign 3868449,
`is_bounced:true`, `reply_time:null`, `lead_category:"Sender Originated Bounce"`.

`is_bounced=true` → 12 rows; **0** have `reply_time`; only **1** carries the bounce category,
**11 have an empty category**. Replies (9) always have `reply_time` plus a taxonomy category.

Rule: webhook → `event_type === 'EMAIL_BOUNCE'` (never match `*reply*` field names —
`bounce_reply_email` is bounce metadata); stats → `is_bounced === true`; never key on
`lead_category` (misses 92%); evaluate bounce before reply and treat as mutually exclusive by
construction; actions = never alert / never Responded / never reply activity / deliverability
counter per inbox and domain (rate, not event); **never write a bounce to the DNC registry** — a
dead address is "cannot reach", not "must not contact".

## IMPROVABLE — my own, three

1. First B12 scan looked only **one** hop upstream — would have missed `HTTP → IF → read`.
2. The transitive rerun **over-flagged 12** because the writer-detector could not see spread
   propagation; all 12 died on reading the code.
3. An inline shell regex reported "0 reads" — an escaping artifact, recomputed from the artifact.

## BLOCKED

Nothing. Caveat: IP evidence covers the retained execution window only; older is pruned.
