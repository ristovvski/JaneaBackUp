# 2026-08-14 — Clay access: CLI (WSL) + Public API, both live

Question was "есть cli доступ?" → "лучше два, для большего покрытия". Both paths are now working.

## DONE — CLI

`clay 0.3.0+2c838b8f19d0`, running **inside WSL Ubuntu** (`/home/nikita98`), already
authenticated from the 2026-08-13 session:

```
clay whoami → {"user":{"id":"{{OTHER_WORKSPACE_USER}}","name":"Mykyta Kryvosheia"},"workspace":{"id":"{{OTHER_WORKSPACE}}"}}
clay credits → {"balance": 10163.5}
```

| item | value |
|---|---|
| plugin copy | `~/.clay-plugin/clay` (skills + bin shim), cloned from `clay-run/agent-plugins` |
| launcher | `~/.local/bin/clay` — **wrapper script, not a symlink** (see trap below) |
| binary cache | `~/.config/clay/bin/clay-0.3.0-linux-x64` (97 MB; 0.1.22→0.3.0 already cached from 08-13) |
| session | `~/.config/clay/config.json` → `profiles.default.oauth.{accessToken,refreshToken}` |
| invocation from Windows | `wsl.exe -d Ubuntu -- bash <script>` |

Surface: `search · routines · functions · workflows · audiences · tables · folders ·
workbooks · webhooks · users · api-keys · credits · mcp`.

## DONE — Public API

Issued from the CLI (the OAuth session is **not** scoped for the public API — it needs its own key):

```
clay api-keys create --name "gtm-agent-cli"
→ ak_0tjqwjy9ZyH4jFBtbhk · scopes ["public-endpoints:all"] · workspace {{OTHER_WORKSPACE}}
```

Secret written to `Нова папка\.env` as `CLAY_PUBLIC_API_KEY` (59 chars, `clay_sco…`).
Returned **once at creation** — not retrievable later; revoke+reissue if lost.

Verified live **from Windows natively** (no WSL) against `https://api.clay.com/public/v0/me`,
using the existing `win_ca_bundle.pem`:

| auth style | source | result |
|---|---|---|
| `clay-api-key: <key>` header | `public-api/authentication.md` | **200** |
| `Authorization: Bearer <key>` | plugin `public-api/SKILL.md` | **200** |

Both work — the docs contradict each other and *both* are right. Corpus said `clay-api-key`;
the shipped skill said Bearer. Neither is wrong, so no conflict record is needed.

## TRAPS FOUND

1. **`clay-cli` on npm is NOT Clay.com.** It is `3vot/clay`, "Web Tool to publish and manage
   Web Sites", v2.0.14, last touched 2022-06-13, BSD-2. Installing it would have put a
   stranger's `bin/clay.js` on PATH under the exact name we wanted. `@clay/cli`,
   `@clay-run/cli`, `@clayhq/cli` are all 404. **The only sanctioned install is the plugin
   repo**, whose shim downloads `clay-linux-x64` from the `clay-cli-v<version>` GitHub
   release and sha256-verifies it against a pinned `checksums.txt`.
2. **Windows is genuinely unsupported** — not a docs disclaimer. The shim hard-fails
   `uname -s` with `validation_error` / exit 2 on anything that is not Darwin/Linux, and the
   binaries are glibc-linked (it also refuses musl/Alpine). WSL is the only local CLI path.
3. **Do not symlink the launcher.** The shim resolves `cli-version` and `checksums.txt`
   relative to `dirname $0` and does **not** follow symlinks, so `ln -s` into `~/.local/bin`
   produced `internal_error: clay: missing …/cli-version`. A one-line `exec` wrapper is correct.
4. `/tmp` in WSL does not survive between `wsl.exe` invocations — the distro shuts down when
   idle. Any clone-then-use script must be self-contained.

## PARTIAL / NOT DONE

- **MCP not wired.** `clay mcp` exists and speaks stdio, but this Claude Code host is on
  Windows while `clay` lives in WSL, so the server entry would have to be
  `wsl.exe -d Ubuntu -- clay mcp`. Untested. `/plugin marketplace add clay-run/agent-plugins`
  (the sanctioned route) is an interactive terminal-dialog command and is not available in
  this session; the org plugin catalog returns zero hits for "clay".
- **No functional call beyond `/me` and `whoami`.** Searches consume the workspace credit
  balance and the plan's result quota, so nothing was run without an explicit ask.
- Clay MCP pins its workspace at startup — re-running `clay login` alone does not switch it.

## CORRECTION — the tables gate is NOT where the docs put it

The docs say "Tables … Enterprise plans only", and I relayed that. Probing the live workspace
shows the gate is narrower — **only the structured cross-table query is gated**:

| operation | CLI | evidence |
|---|---|---|
| `tables list` / `get` | works | {{N}} tables enumerated |
| `tables columns list` / `get` | works | 34 columns w/ types + full settings |
| `tables rows list` | works | rows returned as `{id, updatedAt, cells{colId: {status,value,fields,isStale}}}` |
| `tables query` | **gated** | `query-usage → {"used":0,"limit":0}` — zero quota on this plan |
| create / write | **absent** | no such subcommand exists; UI is the only path (owner confirmed) |

So row-level **read-back of UI-created tables is available today**. UI creates, CLI verifies.

**Pagination trap, again.** `clay tables list` defaults to `--limit 20` and looks complete —
first read reported "20 tables, newest 2025-05-07". Paginated by cursor: **{{N}} tables**,
range `2024-07-10 → 2026-08-14`, 105 created in 2026. Same class as the Pipedrive/Smartlead
list-ordering traps: an uncapped-looking list read is a page, not a set.

**Live workspace activity.** Newest table is `C3A_ZERO_CREDIT_SANDBOX_TABLE`
(`t_0tjqwe8nPeaS9kJykNa`, workbook `C3A_ZERO_CREDIT_SANDBOX_20260814`) created
**2026-08-14T05:54:08Z** — three minutes before this session issued the API key. A parallel
C3A sandbox effort is in flight; do not assume this session is the only writer.

## IMPROVABLE
- Workflows via CLI are **Alpha**; Clay-managed / custom functions are the stable primitive.
- Search result caps are plan-dependent (free 50/req, paid self-serve 10k/req, 1M/yr) — worth
  pinning down which plan workspace {{OTHER_WORKSPACE}} is on before designing any bulk sweep.
