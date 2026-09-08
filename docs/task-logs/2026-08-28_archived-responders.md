# ARCHIVED RESPONDERS — Melisa's CSV export

Дата: 2026-08-28. Файл: `leads-16340280-282.csv` → `ARCHIVED_RESPONDERS_build/`.

## Done
- **1. INGEST**: 324 строки данных распарсено (csv.DictReader) — точное совпадение с ожидаемыми
  ~324. Никакого расхождения, форсировать не пришлось.
- **2. Исключены 7 внутренних test/QA-строк** (ZZ FLIP-GATE ×2, Person-5e07d3f5 ×2, Person-7641cf62 ×3) —
  отфильтрованы по фейковым полям САМОЙ персоны (имя/компания), не по названию кампании. Первая
  версия фильтра по кампании ошибочно исключила бы 3 РЕАЛЬНЫХ людей (Kamil Jałowiec, Evamarija
  Batkoska, Lule Salihu — кампания называлась "Final TEST"/"TEST2", но отправлена реальным людям,
  подтверждено живым HeyReach-ответом). Исправлено до финального прогона.
- **3. Классификация 317 реальных строк**: 10 explicit_opt_out (CSV label DO NOT CONTACT,
  единственный автоматический путь) + 307 reply_dnc (265 чистых + 10 possible_opt_out flagged +
  31 unreadable + 1 no-identifier).
- **Найден и исправлен реальный баг**: первый прогон живого чтения реплаев дал 45 "opt_out" через
  фразовый поиск — большинство было НАШЕЙ СОБСТВЕННОЙ courtesy-формулировкой из quoted-цепочки
  письма (top-posting), а не словами лида. Тройная правка (EN/DE/FR quote-маркеры) сузила список с
  45→29→19→12→10. Финальное решение: НИ ОДИН фразовый матч не повышается автоматически — только
  явный CSV-label. Все 10 оставшихся идут в артефакт для ручного решения (6 я оцениваю как
  генуинные, 4 — как вероятный остаточный ложный матч).
- **31 unreadable** — все HeyReach "lead not found" (archived-лид больше не в активном списке,
  текст ответа технически недоступен) — reply_dnc + human_review, не угадано.
- **1 no-identifier** (Lule Salihu, дубликат-строка) — честно в unmatched/enrichment pool, не
  смёржено по имени (London lesson).
- **Артефакт**: `ARCHIVED_RESPONDERS_build/ARTIFACT_prefire.md` + `classification_final.json`
  (полные данные по всем 317 строкам).

## Дополнение: FIRED, Nik's "go" 2026-08-28

- **Схемное расхождение найдено и исправлено ДО выстрела**: `reason_v1.js`'s `REASON_TO_ENTRY_TYPE`
  не содержит ключ `'explicit_opt_out'` вообще — это значение ENTRY_TYPE, не `reason`. Правильный
  `reason` для явного stop-contact сигнала — `'unsubscribe'`. Также подтверждён жёсткий schema-
  assert: `reply_dnc` без `reply_category` — write отклоняется (инцидент 2026-08-14, 116 строк).
  Построен `dnc_archived_responders_import` (новый generic driver, dry_run по умолчанию true,
  mode:each, валидирует reason/reply_category/identity ДО вызова UpsertLedger) — 107/107 тестов.
- **reply_category** для 300 reply_dnc строк выведен из CSV-поля Lead-Labels (не bare
  'unclassified' — есть реальный сигнал): meeting_no_conversion (33) / positive_reply_no_conversion
  (108) / not_interested (97) / disqualified_generic (48) / responded_generic (14).
- **Мои рекомендации из §4 приняты как есть** (Nik сказал "go" без иных уточнений): 6 генуинных
  possible_opt_out (Miguel Martín, Person-ce02caf6, James Ding, Person-92ee42c2, Person-26fc20bc,
  Person-fc62ec56) → `reason=unsubscribe`; 4 сомнительных (Person-9460fa71, Person-282ef33e, Sabrina
  Tomi, Person-9b0d4295) → остались reply_dnc. 7 исключённых test/QA строк и Lule Salihu (no-
  identifier) — не отправлены вообще (316 = 317 - 1).
- **Выпущено 316 строк**: dry-run прошёл чисто (0 отклонений), затем live-запуск (`dry_run:false`).
- **НАЙДЕНА И ИСПРАВЛЕНА реальная ошибка отчёта** (не потеря данных): `DNC__UpsertLedger__v1` имеет
  3 несвязанных терминальных пути (conflict-alert / real-upsert / idempotent-noop) —
  `executeWorkflow(mode:each)` отдаёт их как ОТДЕЛЬНЫЕ output-branches на вызывающей ноде. Мой
  первый Build Report читал только branch 0 (1 item) → отчёт ошибочно показал "processed: 1"
  вместо 316. Прямая проверка execution 35469 подтвердила: branch 0 = 1 item (Slack conflict-alert
  payload), branch 1 = 315 items (реальные upserted registry rows) — **ничего не потеряно, только
  отчёт был неверным**. Исправлено (`Merge Outcomes`, 3 входа, до Build Report), передеплоено,
  тест на регрессию добавлен (107/107).
- **Post-verify (независимый пересчёт по registry напрямую)**: `mine_count: 315` (по
  `correlation_id` префиксу) — точное совпадение. `mine_by_reason: {reply_dnc: 298, meeting_dnc: 1,
  unsubscribe: 16}` — meeting_dnc:1 корректен (не мной отправлен; existing merge правильно
  сохранил более сильную существующую причину вместо downgrade). `total_active` 25490→25653
  (+163 — меньше 315, т.к. многие identity уже существовали в реестре из более ранних источников;
  upsert обновил их на месте, не создал дубли — ожидаемо).
- **1 конфликт (Person-bb2dd1de) корректно НЕ записан**: его email (`pii-0c4fa4c5@example.invalid`)
  уже resolves на СУЩЕСТВУЮЩУЮ активную строку (id 31307, `s1_responded_to_dnc:51996`, reason=
  reply_dnc — уже защищён с более раннего S1-прогона), а его LinkedIn (`thejoshuabentley`) resolves
  на ДРУГУЮ, уже tombstoned строку (id 24746, `event_contacted`, снята в S4-retirement). UpsertLedger
  корректно отказался слить/переписать конфликтующие identity и отправил живой Slack-алерт —
  доброкачественный случай (человек уже защищён через email-строку), действий не требуется.

## Improvable
- HeyReach's `GetConversationsV3` fails for ~1/3 of LinkedIn-only archived leads ("lead not
  found") — no fallback read path found; documented as a real, structural coverage gap for future
  archived-lead work, not fixed here.
- Quote-stripping heuristic (English/German/French markers) is not exhaustive — 4 residual
  ambiguous cases remain, flagged rather than guessed (now live as reply_dnc, not opt_out).
- `dnc_archived_responders_import`'s multi-branch executeWorkflow output is a general lesson for
  ANY future caller of `DNC__UpsertLedger__v1` via a fresh driver — worth a one-line note in the
  subworkflow's own header so the next builder doesn't rediscover this the same way.
