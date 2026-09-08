# 2026-08-20 — Clay CLI pinned into CLAUDE_GTM_DATABASE

**Ask (Nik):** зафиксировать clay cli в нашей database, из `Downloads/agent-plugins-main.zip`.

## Done
New Clay corpus section `tools/clay/agent_plugin/` (58 files), status `MANIFEST_ONLY_NOT_EXECUTED`:

- `source/` — 55 files, verbatim plugin tree (skills, bin, hooks, all three marketplace manifests, repo docs)
- `registries/clay_cli_surface.jsonl` — 29 records: 1 `distribution`, 23 `skill`, 2 `hook`, 3 `marketplace`.
  Every recorded file carries its own sha256, so drift is detectable without a rebuild.
- `INDEX.md` + `reports/CLAY_CLI_ACQUISITION.md`

Wired into navigation:
- `public/CLAY_MASTER_INDEX.md` (the Clay `entry_index`) — appended pointer section
- `metadata/BUNDLE_TOOL_REGISTRY.json` — 3 new Clay `search_hints`, 5 new aliases, `cli_surface` key
- `metadata/BUNDLE_SOURCE_MAP.json` — section `clay_agent_plugin`, placed next to the other clay sections

Re-ran `work/finalize_bundle.ps1`: **PASS**, 17 sections, 149,741 files (+58 exactly), 5.109 GiB,
all 7 checks true, `forbidden_path_hits: []`. clay_documents still 718 — the normalized corpus was not touched.

## What this actually closes
The public corpus already had `developers.clay.com/concepts/cli-basics.md` = the CLI as *documented*.
It had nothing on the CLI as *shipped*. Now pinned: plugin `2.9.1` → CLI `0.8.1` (decoupled via `bin/cli-version`),
the 4 platform assets + sha256, the download-and-checksum-verify shim, and the permission-hook contract
(which command shapes auto-approve; `feedback|login|logout|api-keys|webhooks` never do).

Bonus: the WSL-only access path is now *evidenced*, not just remembered — the shim gates on `uname -s`
(Darwin/Linux only → exit 2) and checks for the glibc loader on Linux. Windows is refused, not untested.

## Blocked / not proven — stated in the report, not hidden
- The 4 platform binaries are NOT in the bundle. Their sha256 are **transcribed from `checksums.txt`,
  not computed locally**. A checksums file cannot attest to itself.
- Shim NOT executed. No `clay login`, no `clay --help`, no workspace call, zero credits.
- Command tree NOT enumerated — 23 skills ≠ the command surface. `clay --help` stays authoritative at runtime.
- Zip is a `main`-branch archive with no commit SHA → exact upstream revision UNKNOWN.

## Fixed along the way
`work/finalize_bundle.ps1` used `[IO.Path]::GetRelativePath`, which is .NET Core only and threw on this
machine (Windows PowerShell 5.1, no pwsh installed). Replaced with a `Get-RelPath` helper. Backup at
`finalize_bundle.ps1.bak`. The script had never been runnable here as written.

## Improvable
- If the binaries matter, download the 4 assets in WSL and verify the sha256 for real; that would move the
  section off `MANIFEST_ONLY_NOT_EXECUTED`.
- `clay --help` capture (in WSL, authenticated) would pin the real command tree — the one thing this
  section deliberately does not claim.
