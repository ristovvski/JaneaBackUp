# STEFAN THREAD VERIFICATION

Дата: 2026-08-26
Запрос: Stefan's Clay screenshots показывали 4 BLOCKED строки (Person-49a28ca2, Person-5953822e, Frank
Kartmann, Person-036f16fa) с reason "manual / event_campaign" + own-domain catch (Noah Keimach) +
observability asks.

## Done

### 1. Все 4 против ТЕКУЩЕГО реестра
Все 4 подтверждены `status: removed`, `removed_reason: rule_change_2026-08-26_melisa` — покрыты
вчерашним батчем 7486 (все были чистый S4: `manual/event_contacted`). Никакого survivor-класса не
найдено (широкий sweep по всем активным строкам с `source` содержащим `event_campaign` дал 251
совпадений — но это ЛОЖНЫЙ сигнал: это строки, где reason — реально сильный compliant-класс
(`reply_dnc`, `manual_offboard_eligible`), а `event_campaign` — лишь ОДИН из нескольких union-
объединённых source-сигналов на той же строке. Не S4, корректно compliant, не трогать.)

**Delta-push: подтверждено НЕТ такого механизма вообще** — `dnc_pre_add_gate` это LIVE-QUERY
воркфлоу (Clay HTTP-колонка бьёт вебхук `{{WEBHOOK_DNC_PRE_ADD_GATE}}` синхронно на каждую строку, читает
реестр напрямую в момент запроса). Кэша/снапшота/push-синка нет и никогда не было. Живой вызов
гейта прямо сейчас с реальным email Фрэнка Картманна (`pii-d35dede2@example.invalid`) вернул:
```
gate_result: CLEAN, reason: "was manual until 2026-08-26T16:28:18.775Z, currently clean"
```
Значит скриншоты Стефана — это СТАРЫЙ снимок (снят ДО прогона батча в 16:28 UTC), не баг
рассинхронизации. Fix не требуется — механизм и так корректен по конструкции.

### 2. OWN-DOMAIN GUARD
Добавлен в `gate_classify_batch_js` (общий, byte-identical код между `dnc_pre_add_gate` и
`dnc_gate_queue_drainer` — правка одна, покрывает оба). Любая строка с email на `@janeasystems.com`
получает `gate_result: 'OWN_TEAM'`, `reason: 'own_team — exclude from any campaign list'` — этот
чек СТОИТ ПЕРЕД обычной registry-логикой и побеждает и CLEAN (нет вообще записи в реестре), и
обычный `employee_connection` BLOCKED (личный контакт сейлза). Один узел (изменение внутри
существующего Classify Batch), без нового node — минимальный diff.

- Статический regression-тест добавлен (`dnc_contract_tests.js`): own-domain строка без записи в
  реестре → OWN_TEAM (не CLEAN); own-domain строка С активной employee_connection записью →
  OWN_TEAM (не обычный BLOCKED); внешняя строка с employee_connection остаётся обычным BLOCKED
  (regression guard на chirurgical scope); drainer's копия кода подтверждена byte-identical после
  правки. **105/105 тестов проходят** (было 104, +1 новый).
- Задеплоено хирургическим live-patch (тот же приём, что чинил WF-2R): fetch live → diff каждой
  ноды → подтверждено, что отличаются ТОЛЬКО `Classify Batch` (+`Build Report` в гейте, для
  расширения counts на own_team) → deactivate → PUT → reactivate → verify. Оба воркфлоу (гейт
  `9aP2dP0jgAPFGDvA`, drainer `fZl1vpRsQ6Fko3sB`) подтверждены: остальные ноды byte-identical,
  патч применился, гейт активен как был (True), drainer как был (False — уже был неактивен ДО этой
  правки, не следствие неё).
- **Живая проверка** против настоящего продакшн-вебхука: `@janeasystems.com` строка →
  `OWN_TEAM`/правильный reason; внешняя строка → `CLEAN` как обычно. Подтверждено в трафике, не
  только юнит-тестом.

### 3. OBSERVABILITY SPEC — census done, backfill НЕ запущен
- **owner_tag распределение** (25490 активных строк, пост-удаление): 14 различных значений. Топ:
  Jim 8374, Toby 4129, **Mario 2405**, Noah Keimach 2161, Rune 1807, **Mario Stalder 1567**, Matt
  Carothers 1459, Benedetto 1362, **(empty) 1289**, Mike CEO 672, Sergey Cujba 200, **Jim Ash 59**,
  Melisa Bahonjic 5, Person-f55206df 1.
- **Найдена РЕАЛЬНАЯ неоднозначность, требующая явного слова, НЕ угадана**: "Mario" (2405) и
  "Mario Stalder" (1567) — два РАЗНЫХ строковых значения `owner_tag`. "Jim" (8374) и "Jim Ash" (59)
  — та же картина. Оба варианта в каждой паре встречаются в одних и тех же correlation_id-батчах
  (`seed_2026-08-11:people_dnc_pass1`, `onboarding_import:Matt Carothers`), что НЕ доказывает и НЕ
  опровергает, что это один и тот же человек, записанный двумя формами, против двух разных людей.
  Слепое объединение затронуло бы до ~3972 (Mario-пара) + ~8433 (Jim-пара) строк, если угадать
  неверно — не трогаю без прямого ответа "это один человек" по каждой паре.
- **"Empty owner_tag на manual-строках — by design, не потеряно"**: подтверждено честно — 1289
  пустых строк это ОСТАТОК после снятия S4/manual_sheet (было 8775 пустых ДО вчерашнего удаления,
  правило удаления забрало 7486 из них). Остаток — строки без Pipedrive person_id и без
  привязанного сейлза с самого сид-импорта; дизайн, не потеря данных.
- **Reason self-explaining check**: 24201/24201 (100%) строк `manual_offboard_eligible` УЖЕ несут
  `correlation_id` (batch ref) — опасение Стефана про "reason без источника" не подтвердилось на
  этом bucket-е; данные уже несут batch/date-ref, вопрос скорее в том, показывает ли Clay-facing
  колонка это поле читаемо, а не в том, что оно отсутствует.
- **Backfill (владелец для 1289 пустых + канонизация имён) остаётся ПОДВЕШЕН** — дизайн готов
  (source B: есть pid → живой Pipedrive owner lookup; source C: нет pid → оставить пустым, честно
  посчитано), но канонизация имён ("Mario"/"Mario Stalder", "Jim"/"Jim Ash") не запускается без
  прямого подтверждения по каждой паре.

## Blocked — ждёт слова Ника/Мелисы
- Mario/Mario Stalder — один человек или два? Jim/Jim Ash — один человек или два? Без ответа —
  никакой записи в owner_tag не будет.
- Остальной owner_tag backfill (1289 пустых строк) технически не блокирован этим, но откладываю в
  один заход вместе с канонизацией, раз уже открыт этот вопрос — если нужно отдельно и раньше,
  скажи явно.

## Improvable
- Ничего не тронуто без подтверждения по 4 именам и own-domain guard — оба этих пункта имели явную
  проверку (регистр + live gate call) перед тем как считаться done.
