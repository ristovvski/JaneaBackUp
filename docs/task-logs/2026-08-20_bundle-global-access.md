# 2026-08-20 — Global access for CLAUDE_GTM_DATABASE bundle

**Ask (Nik):** другой чат не видит бандл → выдать доступ ко всем сессиям глобально.

## Done
- `C:\Users\User\.claude\settings.json` — added `permissions.additionalDirectories` with the bundle path
  (`...\tasks\2026-08-20_claude_share_bundle\CLAUDE_GTM_DATABASE`). JSON re-validated; backup at `settings.json.bak`.
  User-level scope = applies to every project/session.
- `C:\Users\User\.claude\CLAUDE.md` — created (did not exist). Short global pointer: bundle path + 3-step
  retrieval workflow + the don't-bulk-load / untrusted-content guardrails. Loads into every session's context.

Rationale for two changes: `additionalDirectories` only grants *permission*; it does not make another session
*aware* the bundle exists. Access + discovery are separate problems — the global CLAUDE.md is the discovery half.

## Partial / caveats
- **Already-running sessions do not pick this up.** settings.json and user CLAUDE.md are read at session start.
  The other chat must be restarted (or `/clear`) before the bundle becomes visible to it.
- Granted only `CLAUDE_GTM_DATABASE`, not the parent task folder. `work/build_bundle.ps1` +
  `finalize_bundle.ps1` remain out of global scope by design (rebuild is not an every-session need).
- Bundle content itself untouched — still `BUNDLE_VALIDATION.json` status PASS, validated 2026-08-20T10:46Z.

## Improvable
- If the bundle ever moves or is re-snapshotted under a new dated task folder, BOTH files need the new path.
  Consider a stable junction (e.g. `C:\gtm-db`) pointing at the current snapshot so only the junction moves.
