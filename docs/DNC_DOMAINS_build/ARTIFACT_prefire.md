# Company DNC domains import — §9f.2 pre-post artifact

Дата: 2026-09-09. Read-only так далее — ничего не записано (см. "Blocked" ниже — table-id issue).

## Count

- Source: `Company-DNC-Copy-of-Default-view-export-1788946008479.csv` (Clay export), 1,386 raw rows.
- **1,373 distinct domains** after lowercase + strip-`www.` + dedupe (13 same-day duplicate entries
  in the raw export, earliest `Created At` kept as `added_at`). **Matches expected ~1,373 exactly.**
- **0 free-mail domains found** — checked against a 30-entry list (gmail.com, outlook.com,
  yahoo.com, icloud.com, protonmail.com, yandex.com, qq.com, web.de, etc. — full list in
  `CREATE_DNC_DOMAINS_TABLE.md`). Nothing rejected this batch, but the check runs on every import,
  not just this one.
- 0 blank, 0 malformed (no spaces, no `@`, all contain a dot), 0 `www.`-prefixed or uppercase rows
  in the source itself.

## 5 examples (real, from the prepared payload)

| domain | added_at | source | reason | status |
|---|---|---|---|---|
| 100programmers.com | 2026-06-29T15:03:51Z | clay_company_dnc_import | — | active |
| 10pearls.com | 2026-06-29T10:37:15Z | clay_company_dnc_import | — | active |
| 10xhumans.io | 2026-07-13T13:20:50Z | clay_company_dnc_import | — | active |
| 180dc.org | 2026-06-29T10:35:12Z | clay_company_dnc_import | — | active |
| 20visioneers15.com | 2026-06-29T15:03:28Z | clay_company_dnc_import | — | active |

## Ready, write plan (chunked, matches the tombstone-delete discipline)

- `deploy_domains_import.py` builds a dry_run-default driver identical in shape to the other
  batch drivers this project uses (`dnc_archived_responders_import`, `dnc_tombstone_hard_delete`):
  validates every row (lowercased, no `www.`) before writing, upserts on `domain`.
- Fire plan: dry-run all 1,373 first, then live in chunks (e.g. 500/call, same as every other
  bulk write here), then post-verify: read the table back, confirm count == 1,373 and a handful of
  spot-checked domains match exactly.

## Blocked — table-id issue found, not a wiring bug on my end

The id you gave (`CUkoLQxUxRuS1Lod`) does not resolve — tested in a completely isolated fresh
probe workflow (not the gate, not anything else), both `mode:"id"` with that value AND
`mode:"name"` with `"dnc_domains"` return the identical `"Could not find the data table"` error.
This rules out a mistake in how I wired it into the gate/import driver (both fail the same way in
total isolation).

Likely cause, based on this project's own precedent (`Clay two workspaces` — the same account can
have workspace/project-scoped resources the API key or a given workflow can't see): the table may
be living in a different n8n **project** than the one my API key / the gate workflow operates in.
n8n's public API doesn't expose a project listing or a workflow's own project id for me to check
this directly (`/api/v1/projects` returned 403 with this key).

**Need from you**: confirm which project `dnc_domains` was created in, and if it's not the same
project as `dnc_pre_add_gate`, either move it there or let me know the right project context to
use. Everything else (import payload, driver, gate code) is ready to fire the moment this
resolves — no rework needed, just the id/project fix.

## Дополнение: FIRED, 2026-09-09 (corrected id ai4ZiOGqzuJHRYLB from Nik)

- Первый id (`CUkoLQxUxRuS1Lod`) действительно был неверный — подтверждено live (не резолвился
  даже в полной изоляции). Правильный id пришёл от Ника, подтверждён живым чтением ДО записи.
- **Найден и исправлен реальный баг ДО полного импорта**: пустая (пока ещё не заполненная) таблица
  давала 0 строк БЕЗ ошибки на `Get Domain Blocklist`, и это глушило всю цепочку дальше (тот же
  класс бага, что и раньше с filtered-read-needs-alwaysOutputData, но на этот раз применена только
  к тестовому пробнику, не к самой ноде). Исправлено (`alwaysOutputData: true`), добавлен
  regression-тест, передеплоено через `safe_patch_workflow`.
- **По пути нашёл дыру в самом `patch_utils.py`**: диффинг сравнивал только `parameters`, а
  `alwaysOutputData`/`onError` — это top-level поля ноды, не вложенные в `parameters` — правка
  молча не детектировалась бы. Исправлено сравнивать весь узел (кроме `position`).
- Dry-run 1,373 строк — чисто, 0 отклонений. **Live-запуск**: 1,373 processed, чанками по 500.
- **Post-verify (независимое чтение таблицы)**: `total_count: 1373`, `active_count: 1373`, все 5
  примеров из артефакта найдены с точным совпадением полей.
- **Живой тест гейта**: `pii-2faf1b29@example.invalid` → `BLOCKED, reason: company_dnc /
  100programmers.com` — классификация верна на 100%.
- **Замечена и объяснена аномалия**: сразу после массового импорта (1,373 записей в отдельную
  таблицу) существующая, НЕ МОЯ нода `Get Registry Match (Batch)` (запрос к person-реестру, ~25k+
  строк) резко замедлилась — 78s → 48s → 34s → 32s → 28.5s на последовательных вызовах, чёткий
  тренд восстановления. Мой домен-блок код (`Get Domain Blocklist`, `Classify Batch`) стабильно
  быстрый (32-85ms) на всех вызовах — узкое место НЕ в моих изменениях. Похоже на временную
  нагрузку/контеншн на общем storage n8n data tables после большого burst записи, не постоянная
  регрессия. Рекомендую перепроверить позже сегодня, что вернулось к обычным ~1-2s.
