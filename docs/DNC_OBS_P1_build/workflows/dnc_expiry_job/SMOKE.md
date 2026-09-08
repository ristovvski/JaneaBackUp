# Smoke checklist — dnc_expiry_job (Build 4)

Daily 06:00. Import after `dnc_ledger` + `obs_state` exist. Set Error Workflow placeholder.

## Pre
- [ ] Seed from `fixtures/ledger_seeds.json`: `expiring-emma` (`expires_at` = a real past/tomorrow
      date to test both), `opted-out-oscar` (explicit_opt_out, `expires_at` null). Add two active rows
      with the SAME `identity_key` (different `added_at`) to test dedup.
- [ ] CONFIG `MODE=dev`, `alert_channel=C0BFE6KAN8J`, `digest_dow=1` (Mon). Confirm Data Table nodes
      resolve (`dnc_ledger` for get/update, `obs_state` for counter).

## Manual run (Execute Workflow)
- [ ] `Get Active Rows` returns ALL active rows (`returnAll=true`, not capped at 50).
- [ ] `Plan` output: `to_expire` lists emma (if her `expires_at` < now); `to_dedup` lists the extra
      dup row (primary = strongest/earliest kept); `expired_count`/`dedup_count` set.
- [ ] `Update -> expired`: emma's row `status` → `expired`. `opted-out-oscar` untouched.
- [ ] `Update -> removed (dedup)`: the extra dup → `status=removed`, `removed_reason=dedup_self_heal`.
- [ ] `obs_state` gets `counter:expired_week:{week}` with `num_value` = expired count.
- [ ] Digest: on a non-Monday, `Digest day?` false → no Slack. Temporarily set `digest_dow` to today's
      dow → digest posts count to `C0BFE6KAN8J`.
- [ ] Dev summary posts counts to `C0BFE6KAN8J` (MODE=dev). Set MODE=prod → no dev summary.
- [ ] **Rerun same day** → `to_expire`/`to_dedup` empty → no writes (idempotent).

Send-guard: flip CONFIG `alert_channel` to a non-test id → digest/dev runs HARD-FAIL at their Send
Guard (never post elsewhere). Restore `C0BFE6KAN8J`.
