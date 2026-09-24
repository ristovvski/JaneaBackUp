# DELETE the 26-Aug tombstones — §9f.2 pre-post artifact

Дата: 2026-09-09. Read-only до этого момента — ничего не удалено.

## 1. Scope — расхождение найдено, объяснено, не форсировано

**Ожидалось 7,486. Найдено 7,450** (`status='removed' AND removed_reason='rule_change_2026-08-26_melisa'`).
Разница = 36 строк — **полностью объяснена, не игнорирована**: восстановил точный оригинальный
список из 7,486 id (`s4_retirement_manifest.json` 7,138 + `manual_sheet_full_ids.json` 348 =
7,486 ровно) и проверил КАЖДЫЙ id напрямую против текущего реестра:

| Категория | Count |
|---|---:|
| всё ещё removed с правильным тегом | 7,450 |
| **реактивированы (снова active)** | **36** |
| removed с другим тегом | 0 |
| отсутствуют вообще | 0 |
| **Итог** | **7,486** ✓ точное совпадение |

Все 36 реактивированных строк трассируются к **моему собственному** fire archived_responders
(2026-08-28) + 1 к wf1_reply (2026-09-06) — `merge_v1.js`'s `dncMergeDecisionV1` подтверждён живым
кодом: `var reactivate = (primary.status !== 'active')` — новое DNC-событие для той же identity
ПЕРЕАКТИВИРУЕТ существующую tombstoned-строку (тот же `id`, `removed_reason`/`removed_at`
обнуляются), а не создаёт отдельную запись. Это ПРАВИЛЬНОЕ поведение по правилу Мелисы (человек
ответил → его должны защитить снова, уже под reply_dnc/unsubscribe) — эти 36 строк корректно НЕ
входят в scope удаления, они больше не tombstones.

**Остальные removed-строки** (не входят в scope, не трогать):
| removed_reason | Count |
|---|---:|
| `merged_into:23840` | 1 |
| `team ruling 2026-08-18 (Araks/Nik, #ai4-2026): meeting booked but did not happen — protected for post-event follow-ups, not DNC` | 1 |

**Разбивка scope по исходному reason**: manual_sheet 329, event_contacted 7,121 (сумма 7,450 ✓).

## 2. EXPORT — сделан, до любого удаления

- `audit-artifacts/dnc_registry_tombstones_2026-08-26_melisa_EXPORT_2026-09-09.csv` (7,450 строк +
  header, все колонки)
- `audit-artifacts/dnc_registry_tombstones_2026-08-26_melisa_EXPORT_2026-09-09.json` (то же, JSON)
- `TOMBSTONE_DELETE_build/delete_target_ids.json` (точный список 7,450 id для чанкованного удаления)

## 3. 5 примеров

| id | identity_key | исходный reason | source_ref | removed_at |
|---:|---|---|---|---|
| 8856 | nayana-singh-256680 | manual_sheet | — | 2026-08-26T16:34:21Z |
| 8857 | iagoaquino | manual_sheet | — | 2026-08-26T16:34:21Z |
| 8859 | bill-reynolds-385303 | manual_sheet | — | 2026-08-26T16:34:21Z |
| 23852 | akshaychacko | event_contacted | Ai4 2026 | 2026-08-26T16:27:50Z |
| 23853 | pii-eca094c5@example.invalid | event_contacted | Ai4 2026 | 2026-08-26T16:27:50Z |

## 4. Sweep — что читает removed-строки

- **`DNC__UpsertLedger__v1` (Get by LinkedIn / Get by Email)** — подтверждено живым кодом: ЭТИ
  запросы НЕ фильтруют по `status` вообще (`matchType:"anyCondition"` на identity-полях only).
  `merge_v1.js`'s `candidates` включает removed-строки, и если это единственный кандидат,
  `reactivate = true` → строка апдейтится на месте (тот же `id`), НЕ инсертится заново. **После
  удаления**: тот же сценарий (человек отвечает позже) больше не находит НИКАКОГО кандидата →
  INSERT новой строки вместо UPDATE реактивации. Конечный результат ИДЕНТИЧЕН (active reply_dnc/
  meeting_dnc строка) — только новый `id` вместо старого, `added_at`/history не переносится (но
  реактивация и так перезаписывает `added_at` на `now`, так что и здесь разницы по существу нет).
  **Подтверждено: поведение Мелисиного правила не ломается.**
- **Гейта "was X until Y" wording** (`gate_classify_batch_js`): при отсутствии активной строки,
  но наличии removed-строки, гейт отвечает `CLEAN` с `reason: 'was ' + entry_type + ' until ' +
  removed_at + ', currently clean'`. После удаления этих 7,450 строк: для ЭТИХ конкретных людей
  гейт просто вернёт `CLEAN, reason: null` — теряется историческая подпись, но верный BLOCKED/CLEAN
  вердикт не меняется. Мелкий, приемлемый tradeoff, не блокер.
- **Clay delta pusher** — Phase 2 ещё не построен; по дизайну (README_STEFAN.md) проецирует ТОЛЬКО
  active-строки — удаление removed-строк здесь не имеет значения вообще (moot by design).

## Ждёт слова Ника

- Delete scope: **7,450** (не 7,486 — см. §1), чанками (never one bulk op — OOM shape, established
  discipline this project has been burned by once already).
- Post-verify plan: 0 rows match the filter, `total_active` unchanged, спот-чек нескольких id
  подтверждает НИ ОДНА active-строка не тронута.

Nothing fires until you say go.
