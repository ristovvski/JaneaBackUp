# PARALLEL BATCH — WF-2 secret coordination / CSV-324 / I-04 monitor fix

Дата: 2026-08-28.

## 1. WF-2 webhook secret re-arm — BLOCKED, real prerequisite found, coordinating

Read `b3_flip_live.py` + `build_wf2s.py` (the flip project) before touching anything:
- `CONFIG.webhook_secret_sha256` is deliberately null. Docstring: *"arming today would silently
  drop every WF-2S / WF-2R replay"* — WF-2's Verify Secret checks a BODY `secret_key`; the
  reconcilers send none (n8n credentials can't inject body fields). The documented fix is a
  header-based `X-Replay-Auth` credential validated against `CONFIG.replay_secret_sha256`, listed
  as a **named, not-yet-confirmed-built follow-up** ("AUTH FOLLOW-UP... needed only when the
  webhook secret is armed").
- This is NOT a safe config-only flip until that header-auth path exists on both WF-2 (verify) and
  WF-2S/WF-2R (inject) — arming blind would break the reconcilers silently, the exact class of
  incident this project has already been burned by once (WF-2 reply loss).
- I also do not have the real secret value anywhere in `.env` — this needs Nik or whoever owns the
  WF-2 chain right now to provide/confirm it, not something I can derive.
- **Reached out to the peer session most likely to be "Дежурный"** (`claude-a3`, running 5h,
  longest-lived of the 3 peer sessions) via SendMessage, asking: is the X-Replay-Auth path built
  yet, does a config-only PUT risk colliding with in-flight node edits, what's a safe window.
  **No reply yet as of this writeup** — not touching WF-2 until one arrives.

## 2. CSV-324 classification → pre-post — already out

Posted earlier this session: `ARCHIVED_RESPONDERS_build/ARTIFACT_prefire.md` +
`task-logs/2026-08-28_archived-responders.md`, message in #niks-channel. 317 real rows classified
(10 auto opt_out + 307 reply_dnc), 7 test/QA rows excluded, a real quote-contamination bug found
and fixed in the reply-text scan. Nothing fired yet — waiting on Nik's word on 4 open questions
listed there.

## 3. I-04 daily_summary 'Load Watermark' — already fixed (see
`task-logs/2026-08-27_i04-consolidation.md`). Drainer-monitor predicate fix — DONE, new bug found
and fixed

Re-examined `dnc_pre_add_gate_monitor`'s stuck-drainer predicate. The literal "depth 0 read as
stuck" framing didn't reproduce from the code as originally written (the `>0` guard already
excluded depth=0) — but tracing it found a REAL, related bug: the `queueOk` check
(`queueRows.length === 1 && queueRows[0].error`) was a NEGATIVE, absence-of-error check — the
exact bug class this project already fixed once in the gate's own ingestion path
(`n8n-datatable-error-shape-nonuniform` — error branches are not uniform; some return
`{error:"..."}`, others echo the original upstream item unchanged). If "Check Queue" ever failed
by echoing a non-row item (no `status`/`row_key`) instead of the `{error}` shape, the old check
would have counted it as "1 ok row" — a phantom, never-draining depth that WOULD have triggered a
false stuck alert after 4 ticks.

Fixed with a positive shape check (`typeof r.status === 'string' && typeof r.row_key === 'string'`
on every returned row — true vacuously for a genuinely empty array too) and made `depth > 0` an
explicit, first-class term in the stuck predicate rather than an incidental side effect. Verified
live that `dnc_gate_queue` still doesn't exist (`"Could not find the data table"`, same as
`i04_snapshots` earlier) and confirmed the new code correctly reads that as `queue_ok=false,
queue_depth=null`, never a false "stuck". 4 new static tests added (idle-queue-never-stuck,
non-row-echo-never-phantom-depth, documented error-shape-never-stuck, drain-to-zero-clears-stuck),
existing stuck-detection test's fixture rows updated to carry real `status`/`row_key` fields so it
still exercises a genuine backlog under the stricter check. **106/106 tests pass.** Deployed via
surgical live patch to `g8MUOKFlUaeVrdBx` (only `Track + Report` changed, verified).

## Blocked / pending
- WF-2 secret arm: needs (a) confirmation the X-Replay-Auth path is built, (b) the real secret
  value, (c) a sync window with whoever owns the WF-2 chain right now.
- CSV-324 fire: needs Nik's word per the artifact's 4 open questions.
