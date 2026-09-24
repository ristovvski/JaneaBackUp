# Phase 2 — nightly reconcile + digest line — §9f.2 pre-post artifact

Дата: 2026-09-14. Files built, logic-tested locally (21 + 11 = 32 new tests, all pass; 57 across
all three Supabase workflows; 105 on the DNC contract suite). **Nothing deployed, nothing live.**

## Nightly reconcile (`dnc_supabase_nightly_reconcile`, new workflow, 24 nodes)

Cron `20 6 * * *` (after I-04's 06:08) + manual webhook (`{{WEBHOOK_DNC_SUPABASE_NIGHTLY_RECONCILE}}`,
`onReceived`, same dual-trigger convention as `dnc_claims_prune`).

**Per table** (dnc_registry, dnc_domains), sequentially:
1. Read n8n's full table (`dataTable get`, `returnAll`) — safe, done many times this session with
   no issue (the earlier 502 was from a webhook response carrying the full registry TWICE, not
   from this kind of internal read).
2. Read Supabase's exact row count (`Prefer: count=exact`).
3. Paginate Supabase's actual rows at 1,000/page — **genuinely required**, not just a style choice:
   PostgREST's own `max-rows` caps any single response at 1,000 regardless of `?limit=` (confirmed
   live 2026-09-14, memory: `supabase-postgrest-max-rows-cap`).
4. Field-by-field diff (timestamp-format-aware, so `Z` vs `+00:00` and trailing-zero truncation
   never register as false drift — the same normalization bug fixed in Tuesday's post-verify).
5. Any drifted/missing row gets healed by **upserting from n8n** (source of truth), chunked at 500.
   A row Supabase has that n8n no longer does is reported as `extra_in_supabase` but **never
   deleted** — only n8n→Supabase healing, never the reverse.
6. One `dnc_registry_meta` row per table, `source: 'nightly_reconcile:dnc_registry'` /
   `'nightly_reconcile:dnc_domains'`.

**One Slack line only if total drift ≠ 0** (both tables combined) — silent on a clean night.

**Also serves as the free-tier keep-alive** you asked for — any real Supabase API traffic (which
this always generates, drift or not) counts against auto-pause.

**Design choice flagged, not yet confirmed**: I did NOT literally chunk the n8n-side read via
`SplitInBatches` — that read has been safe every time this session (proven, not assumed). What IS
genuinely chunked: the Supabase-side read (paginated, required by PostgREST's own cap) and the
write-back (500-row chunks). Say the word if you want the n8n-side read chunked too regardless.

**Still pending your confirmation — I have NOT guessed this**: the `#alerts` channel id. Your own
`RULEBOOK.md` lists `#lead-processing`, `#alerts`, and `ops` as three *separate* destinations, but
this codebase only has one concrete channel constant anywhere
(`OPS_CHANNEL = "C0B8GCVNR5W"`, #niks-channel). I've wired the alert to that id as a placeholder —
**do not treat this as confirmed**; tell me the real `#alerts` channel id (or confirm it really is
the same as ops) before this fires for real.

## Digest line (patch to the existing, live `dnc_morning_digest`, 40→43 nodes)

Folded into the existing **`*DNC*` line**, not a new bullet — same subject (registry health/reach)
and the digest is already capped at 12 lines total:

```
🟢 DNC active 25729 (+3 / -1 24h) · gate OK 145ms (0/96 fail today) · Supabase mirror: 25729 rows · age 4 min · reachable
```

Color folds into the line's existing dot: **red** if Supabase is unreachable/paused (new) OR gate
is FAILING (existing, preserved) — **amber** if reachable but the last sync is >60 min old (new) OR
`dnc_active` is unreadable (existing, preserved) — green otherwise. Two new read-only HTTP checks
(count + latest meta row), both `onError: continueErrorOutput` — a Supabase outage degrades the
digest's own DNC line, it can never crash the whole digest.

Verified against the ACTUAL live Compose function (not a guess at its shape) via
`patch_morning_digest_supabase_mirror.py` — same discipline as the project's own precedent
(`I04_SIMPLIFY_2026-09-03/patch_morning_digest.py`): fetch live, backup, defensive
already-patched-or-original assertion on Compose (refuses to patch blind), full connection/dupe
integrity check, dry-run writes a local file only. 11/11 local tests pass, including that the
existing gate-FAILING→red and dnc-active-unreadable→amber behavior is unchanged when Supabase
itself is healthy.

## Fire plan, pending your word

1. Confirm the real `#alerts` channel id (or that ops is correct).
2. Deploy `dnc_supabase_nightly_reconcile` (new workflow) — dry-run available via the manual
   webhook first if wanted, though unlike the initial load this workflow has no separate
   dry-run/live mode; every fire heals drift for real. First fire, live-verify the two meta rows
   land and (if there's real drift right now) the Slack line looks right.
3. Patch `dnc_morning_digest` via `patch_morning_digest_supabase_mirror.py --apply` — live
   production digest, so flagging this one for explicit confirmation same as UpsertLedger was.
4. Wait for tomorrow's 06:20 cron, or fire both manually tonight to see the real output sooner.

Nothing above fires without your go-ahead.

## Organic 3-write confirmation (still pending, monitored in background)

No new `DNC__UpsertLedger__v1` executions since the patch deployed (2026-09-14 ~11:23) — still
sitting at execution 54342 (2026-09-13T21:23), before the patch. Historical cadence shows gaps of
several hours between real writes, so this hasn't been unusual yet. Will report the moment 3 real
claim→push cycles are confirmed.
