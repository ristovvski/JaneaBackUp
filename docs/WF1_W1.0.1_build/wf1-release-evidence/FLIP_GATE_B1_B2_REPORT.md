# Flip gate — B1 + B2 verdict

2026-08-05. All checks read-only against real state; no writes beyond Phase A1 (already reported,
separately). **Stopping here — B3 (the actual flip) requires Nik's explicit word per the gate rule.**

## B1 — pre-checks: 5/5 GREEN

| check | result |
|---|---|
| WF-2 active | GREEN — `active=true`, versionId `e9242d0a` |
| WF-2 webhook probe | GREEN — 200 |
| WF-2S clean cycle at cap=20 | GREEN, **with a caveat**: the observed cycle was idle (no sends to replay). Cap=20 has not yet been exercised under an actual batch — verified clean, not load-tested. |
| WF-ERR alive | GREEN — active, 5 executions retained |
| mario@janeasystems.com in forward map | GREEN — present as `forward_owner_map.Mario` in live CONFIG, not just a stray string match |

## B2 — campaign correctness gate: label-chain proof fully GREEN; per-campaign coverage partial

**Label-chain proof — all three points confirmed against real ground truth, not assumed:**

| point | result |
|---|---|
| (a) our label ID == Pipedrive's real "3. Responded" ID | GREEN — both `c9d4b550-bcf3-11ef-a843-357f91e826ec`, exact match |
| (b) lead creation sets owner=Melisa | GREEN — CONFIG.owner_id `16340280` == Melisa Bahonjic's real Pipedrive user ID |
| (c) a real shadow-processed reply's lead carries that label ID | GREEN — confirmed directly on both real reply executions this window (13143, 13236): `Lead Labels Union` body = `[..., "c9d4b550-bcf3-11ef-a843-357f91e826ec", ...]` in both. `Reply Activity` independently shows `owner_id: 16340280` on both too. |

(My first pass on (c) reported a false RED — my check matched the exact string `"Lead Labels Union"`,
but the real node label is `"Lead Labels Union (shared body: also U Lead DNC Label)"`. Fixed by
reading the two real executions directly rather than trusting the string match.)

**Per-campaign completeness — honest gap, not a defect:**

Pulled all 48h of real WF-2 executions (retention actually spans ~161h — much better than the ~13h
assumed earlier). Only **2 reply-type executions occurred in the whole 48h window, both on
`[Events Visiting] AI4 2026 - Mario - Valids`**:

| campaign | reply execs | categorized | forward attempts | lead writes |
|---|---|---|---|---|
| Mario - Valids | 2 | 2 | 2 | 2 |
| Mario - Catch-alls | 0 | — | — | — |
| Rune - Valids | 0 | — | — | — |
| Rune - Catch-alls | 0 | — | — | — |

Every reply in-window was fully categorized, had a forward target resolved (one to `mario@`, one to
`melisa@`), and produced a matched lead. **3 of the 4 live campaigns had zero reply traffic in this
window** — that's genuinely unproven, not failing: there was nothing to observe, so the gate can't
certify or refute those three from real data. This mirrors the "a gated path is unproven until it
runs" rule from earlier work — here it's "a per-campaign correctness claim is unproven where zero
events occurred."

**One observation, not a red flag:** both proven replies show `Lead Labels Union` with
`would_write=False` — the union write was a no-op skip, consistent with cumulative-union idiom
(skip an empty PATCH when the target label set already matches). Not independently verified whether
skip was warranted in both specific cases; noted for awareness, not blocking.

## Verdict

**B1: 5/5 GREEN. B2 label-chain: 3/3 GREEN (with real evidence, not just code inspection). B2
per-campaign: 1/4 campaigns proven, 3/4 unproven (no data, not a failure).**

**Separate from the named B1/B2 checks, but material to the flip decision:** the OOM finding from I0
— WF-2S and WF-2 crash together, same few seconds, both times observed, pointing to a shared
instance-wide memory ceiling that also exposes WF-1 (live production). That memory calls it a flip
blocker in its own words. Phase A1 (cap=20) reduces exposure but doesn't prove the ceiling is fixed.

**Stopping here.** Nothing beyond A1 (already deployed and verified) has been written. B3 (pause
WF-2S → arm webhook secret → WRITE_MODE=live → deploy → read-back → unpause) has not been started and
will not start without your explicit word.
