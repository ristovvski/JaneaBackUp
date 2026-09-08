# AI4-конвейер: редизайн на точность, эффективность и стоимость

Базис: разбор живого воркбука (`clay-ai4-2026-column-map.md`) + Clay-корпус из `CLAUDE_GTM_DATABASE`
(`tools/clay`, 718 документов, статус `PAID_VALIDATION_REQUIRED`) + паттерн `Janea | Event Intelligence v5 | QUALITY`.
Дата: 2026-08-20.

---

> **ПОПРАВКА 2026-08-20 (после полного прохода по корпусу).** Утверждение ниже «цифр по кредитам в корпусе нет»
> **неверно**: оно основано на реестрах, где поля `UNKNOWN`, но в документах модель описана полностью —
> две валюты (Actions / Data Credits), таблица цен по моделям, дашборд трат по колонкам, бюджеты и лимиты воркбука.
> Также неверны: «AI на своём ключе бесплатен» (тратит 1 Action), «стоимость Lookup Rows не доказана»
> (не тратит Action — документировано), «до 8 кредитов на email-цепочку» (валидация в примере Clay бесплатна),
> «нужен платный смоук, чтобы узнать стоимость» (для существующей таблицы — нет).
> Всё исправленное и проверенное: **`clay-credit-model-reference.md`**. Читать его вместо §0 и §5.

## 0. Границы: что корпус подтверждает, а что нет

**Цифр по кредитам в корпусе нет.** В `registries/clay_feature_inventory.jsonl` поле `credit_implications` = `UNKNOWN`,
все 12 записей `clay_decision_rules.jsonl` имеют статус `PARTIAL` с прямым указанием «do not infer undocumented cost or plan behavior».
Поэтому ниже **нет прогноза экономии в деньгах** — есть только механики, которые Clay сам документирует как credit-efficient.

**Проверено исполнением (zero-credit sandbox, 0 кредитов)** — `zero_credit_sandbox/reports/CLAY_C3A_SANDBOX_RESULTS.md`:

| Поведение | Результат |
|---|---|
| Порядок и зависимости формул | Pass |
| Auto-update: правка upstream пересчитывает downstream без ручного запуска | Pass |
| Двухуровневый каскад | Pass |
| Пустой вход → downstream остаётся пустым (не ошибка) | Pass |
| Ошибка в ячейке → downstream отдаёт ошибку расчёта, а не «skipped» | Pass |
| Text-формула с object/array → `[object Object]` + предупреждение | Partial/negative |
| Выбор строк сам по себе не даёт Run (в меню только Delete) | Partial |

**Не доказано, требует платного теста** — `CLAY_C3B_PAID_TEST_QUEUE.md`, ничего из очереди не запускалось:
C3B-01 точная семантика `Only run if` (true/false/null/change), C3B-03 bulk-запуск по фильтру,
C3B-04 стоимость и поведение Lookup Rows, C3B-05 Send Table Data и защита от циклов, C3B-08 HTTP/API,
C3B-09 поведение остановки waterfall'а, C3B-11 подтверждение записи в CRM/сиквенсер.

Это важно, потому что вся экономия ниже опирается на `Only run if` и Lookup Rows — то есть на два пункта из этой очереди.
**Сначала платный смоук на 10–20 строках, потом раскатка.**

Практическое ограничение: **таблицы в Clay нельзя создавать через CLI/API, только через UI**. Моя роль — спека и верификация;
кликает человек. Через CLI я потом проверю результат (`tables columns get`, `rows list`).

---

## 1. Главная структурная ошибка — порядок, а не колонки

У Clay есть каноничный клейбук ровно под наш кейс — «Enrich and score event signups»
(`https://university.clay.com/claybooks/enrich-and-score-event-signups`). Его логика дословно:

> «To ensure event attendees match your ICP criteria **before wasting time (and credits) enriching them**…»
> «No wasted enrichment. No wasted outreach.»
> Шаг 3: «This column only runs if the lead matches your ICP criteria from the previous column.»

**AI4 сделан наоборот.** На всех 13 464 строках сначала тратится всё дорогое, и только потом считается скор:
AI-нормализация имени → Claygent на название компании → Claygent на домен → Claygent на поиск LinkedIn →
обогащение профиля → AI-верификация профиля → скрейп сайта → AI-детект конкурента → 3 поиска email + 3 валидации →
обогащение компании → **и только теперь** `Job Title Score` / `Company Score` / `Final Score`.

Скор при этом считается по `Title` и данным компании, которые в большинстве строк **уже есть на входе** — то есть
квалифицировать можно было до первого платного вызова.

### Целевой порядок: гейт → трата

| Ступень | Что делаем | Цена |
|---|---|---|
| 0 | Дедуп по стабильному ключу (auto-dedupe), стоп-лист должностей, `.edu/.gov/.org`, **DNC по сырым данным** | формулы + lookup'ы, платных вызовов нет |
| 1 | Одна дешёвая AI-квалификация по сырым `Title` + `Company` → скор | 1 вызов, малая модель |
| 2 | Только выжившим: резолв LinkedIn → обогащение профиля → верификация «тот ли человек» | дорогое, но на срезе |
| 3 | Только верифицированным: **Work Email waterfall** с Infer Email | pay-on-match |
| 4 | Только контактным: обогащение компании, категоризация, вердикт | на самом узком срезе |
| 5 | Диспатч с жёстким гейтом (не ручным флагом) | — |

Это не только дешевле. Это **точнее**: дорогие шаги работают по уже очищенному срезу, а не по мусору,
и каждая ступень имеет явный вход, а не «посчиталось на всём, дальше разберёмся».

---

## 2. Замены один-в-один

### 2.1 Шесть email-колонок → один Work Email waterfall

Сейчас: `Find Work Email` + `Validate LeadMagic` + `Find Work Email (2)` + `Validate Findymail` +
`Find Work Email (3)` + `Validate Prospeo` + ручной waterfall-сборщик + колонка провайдера + `Email Status` — девять колонок,
связанных вложенными run-условиями (у `Validate Prospeo` условие уже нечитаемое).

Документировано (`https://university.clay.com/docs/work-email-waterfall`):

- «cascades across multiple email finding providers in sequence — stopping as soon as one returns a valid result»;
- «**You only pay credits for the provider that finds a match**, making it one of the most credit-efficient ways to build email coverage at scale»;
- **Infer Email** — бесплатный первый шаг: собирает адрес из имени и домена по шаблону; если прошёл валидацию, платные провайдеры **не вызываются**. «Infer Email is completely free… No credits are charged for the failed Infer Email step.» По внутреннему тесту Clay на software-датасете шаблон `first.last@domain.com` давал валидный email **примерно в 31% случаев**;
- **Validation strategy**: `Conservative` (все верифицированные типы, «best when deliverability matters — cold outreach where bounce rates affect sender reputation»), `Balanced` (включая catch-all), `Aggressive`, `Advanced`;
- **Threshold for duplicate results**: если один и тот же адрес не проходит валидацию у N провайдеров — остановиться, «preventing credits from being spent running additional providers that are likely to return the same result». По умолчанию `0` = выключено; Clay советует `2` в паре с `Conservative`.

Наше текущее деление на кампании (`Deliverable` → Smartlead `3686187`, `Accept All` → `3756410`) ложится на
`Conservative` против `Balanced` штатно, без ручного парсинга строки `reason`.

Действие: заменить девять колонок на один waterfall с `Infer Email` = ON, `Conservative`, `Threshold = 2`,
`Output name of successful provider` = ON. Перед раскаткой — тест шаблона на ~10 наших строках (док прямо это советует:
«Email naming conventions vary by company and industry. Test on a small sample before running at scale»).

### 2.2 Claygent на поиск LinkedIn → waterfall с Claygent в конце

Сейчас `Find LinkedIn Profile URL` — Claygent (`gpt-5.4-mini`) с условием «нет LI в списке». Веб-ресёрч агентом на каждую
строку — самый дорогой способ получить URL. Кастомный waterfall (`https://university.clay.com/docs/building-a-data-waterfall`:
«utilize multiple data providers in a predetermined sequence, so you don't duplicate tasks or spend extra credits»)
позволяет поставить детерминированных провайдеров первыми, а Claygent — последним фолбэком.

### 2.3 Телефонная цепочка (follow-up-таблица) → готовый Phone waterfall

Пять сцепленных провайдеров (`Find Mobile Number`, `Enrich Person (2)`, `Find Phone Number`, `Find Phone Numbers`,
`Find Mobile Number (2)`) с растущими вложенными условиями — это ручная реализация того, что в Clay есть prebuilt.

### 2.4 Четыре AI-колонки нормализации → формула + AI-фолбэк

`Name Normalization` и `Normalized Company Name` вызываются **на каждой строке безусловно**, хотя результат в большинстве
строк совпадает с детерминированным `split(" ")`, который уже написан рядом как фолбэк. Инвертировать: формула первая,
AI — только по `Only run if` (имя не разбирается однозначно: одно слово, три и больше слов, не-латиница, суффиксы).

### 2.5 Три категоризатора → один структурный вызов (или удалить)

`Company Category` (`gpt-5-mini`), `Current Job Title & Summary` (`gpt-5.4`), `Category` (`o3`, `runBudget: 5`) —
самые дорогие модели в таблице. В проверенных строках они `empty`, то есть **пока не запускались и денег не стоили**.
Риск в другом: если их включат на 13 464 строках ради `Verdict`, который всё равно `null` (матрица `Targeting Rules` пуста) —
это будет самая крупная трата в таблице, дающая нуль. Либо один вызов со структурированным выходом (три поля сразу)
и заполненная матрица, либо лейн удаляется целиком.

---

## 3. Одна таблица на 13k строк → конвейер таблиц

Документировано (`https://university.clay.com/docs/lookup-rows`):

- **Lookup Rows** — «pulls data from another table… non-destructive», прямо назван кейс «reference data from a central table (like a pricing list, messaging library, or **Do Not Contact list**)». Наши четыре DNC-лукапа — ровно этот паттерн, он верный.
- **Send Table Data** — «route or segment your data into different tables based on logic or filters», «multi-stage workflows where each table handles a specific step».

Плюс `https://university.clay.com/docs/table-management-settings`: **passthrough-таблицы** (enterprise) обходят лимит строк —
обогащают, отдают в назначение, удаляют строку; порог 5 000 строк, интервал проверки 60 секунд, только для webhook-источников,
на CSV не действует.

Целевая архитектура — один конвейер вместо копии 89-колоночной таблицы под каждый ивент:

```
Event Ingest (сырьё + Event Name как ДАННЫЕ)
  └─ дедуп, стоп-листы, DNC по сырым данным, дешёвый скор
       └─Send Table Data→ Person Resolve & Verify (LinkedIn + верификация личности)
             └─Send Table Data→ Contactable (Work Email waterfall, обогащение компании)
                   └─ по каналу → Dispatch Email | Dispatch LinkedIn
Reference: Janea DNC (People / Company / Email / LinkedIn) ← Lookup Rows из любой ступени
```

Это лечит корневую проблему всего workspace: **74 воркбука, каждый — мутировавшая копия предыдущего**
(NVIDIA GTC → Build → Databricks → … → AI4). Стандартизация делается штатно: **waterfall-шаблоны**
(«Waterfall templates allow you to save and reuse your waterfall configuration») и column templates,
а не копированием таблицы (док отдельно предупреждает: «Duplicating a table will only copy the sources»).

---

## 4. Точность (приоритетное)

1. **Взять паттерн A→B→C из v5 на уровень человека.** В `Events | Quality Decision Engine v5` уже сделано правильно:
   `A — Evidence Discovery` → `B — Verified Event Dossier` (независимая перепроверка с нуля, только по полям строки, с цитатами URL)
   → `C — Strategic Decision Packet` (без веба, сверка A против B, precedence `actual > expected > claim > historical`,
   `null/Unknown` при неразрешимом конфликте) + человеческий гейт `QA Decision` / `Effective Recommendation`.
   Для лида это заменяет одиночный `LinkedIn Match AI Check` на «две независимые попытки + примирение», что и есть
   основной источник ошибок «не тот человек».
2. **Диспатч сделать гейтом, а не ручным флагом.** Сейчас у HeyReach-колонок нет `Only run if` вообще, а `Should Remove?`
   и DNC на отправку не влияют — защита только ручным `Are we adding to Linkedin?` и фильтром вью.
   Условие должно быть: `!Should Remove? && !EmailDNC && Verdict != "Exclude" && Final Score >= X`.
3. **Починить ключ дедупа.** Auto-dedupe следит за одной колонкой и «Blank cells and cells with more than 200 characters are
   excluded from this process». Наш ключ — формула `имя+фамилия+компания`; у строк без компании он вырождается,
   то есть такие строки **из дедупа выпадают молча**. Ключ должен быть всегда заполнен: LinkedIn URL → email → `имя+домен`.
4. **Перевесить DNC на сырые данные.** `Person DNC` матчится по *обогащённому* LI URL, `LinkedIn DNC` — тоже.
   Значит строка, у которой резолв LinkedIn не удался, **DNC не проверяется вообще** (в сэмпле это ровно те строки с
   `Missing input`). Нужен предварительный DNC-чек по тому, что есть на входе, до траты на резолв.
5. **`Email DNC` завести в `Should Remove?`** — сейчас считается и игнорируется.
6. **Убрать `Math.random()` из распределения владельцев** — заменить детерминированным хэшем от ключа личности,
   чтобы пересчёт не переназначал лида (auto-update подтверждён sandbox'ом как реальный механизм пересчёта downstream).
7. **Событие — это данные, а не текст промпта.** Противоречие «AI Summit NYC против NVIDIA GTC» внутри одной колонки
   возникло именно потому, что название ивента вписано в промпт руками. `Event Name` колонкой + ссылка из промпта —
   одна таблица обслуживает все ивенты, и рассинхрон физически невозможен.
8. **Объекты — только в JSON-колонках.** Sandbox показал: text-формула коерсит object/array в `[object Object]` с
   предупреждением. Все структурные выходы парсить явно, а не тащить как текст.
9. **Мёртвый лейн — удалить или заполнить.** Пустая `Targeting Rules` + незапущенные категоризаторы дают `Verdict = null`,
   который выглядит как «проверено, не подходит». Это опаснее отсутствия колонки.

---

## 5. Что доказать до раскатки (платный смоук)

Одна изолированная таблица, 10–20 синтетических строк, явный потолок кредитов:

| Проверить | Почему это блокер | Очередь |
|---|---|---|
| `Only run if` при false / null / изменении входа | на этом стоит вся экономия | C3B-01 |
| Стоимость Lookup Rows | 4 лукапа на строку × объём | C3B-04 |
| Поведение остановки waterfall'а | от него зависит pay-on-match | C3B-09 |
| Hit-rate `Infer Email` на **наших** данных | 31% — это тест Clay на их датасете, не на нашем | док советует ~10 строк |
| Send Table Data + защита от циклов | если идём в многотабличный конвейер | C3B-05 |

---

## 6. Порядок работ

1. **Фаза 0** — платный смоук из §5. Без него цифры экономии остаются гипотезой.
2. **Фаза 1** — на копии таблицы переставить порядок (§1): гейты и дешёвый скор вперёд. Меняется только порядок и run-условия, провайдеры те же — сравнимо по качеству напрямую.
3. **Фаза 2** — заменить ручные каскады на waterfall'ы (§2), сохранить как шаблоны.
4. **Фаза 3** — разнести на ступени-таблицы (§3), `Event Name` в данные.
5. **Фаза 4** — из результата собрать шаблон под следующий ивент, чтобы 75-й воркбук не был копией 74-го.

Режим сборки — по документированной практике Clay: table-level auto-run **OFF**, 5–10 строк, ручной прогон ячеек,
и только потом auto-run ON с `Keep existing results` (док: «only errored, empty, or new cells can run automatically»).
Для источников с расписанием — `Update Existing: OFF` («Net New… Lower credit usage — more cost-efficient»).

---

# Дополнение (2026-08-20, после доступа к UI): реальные цифры по кредитам

В §0 сказано, что цифр по кредитам в корпусе нет. **Они есть в UI** — панель `Tools` показывает стоимость
каждого экшена на строку. Снято глазами в workspace 332169, 2026-08-20.

## Что бесплатно (нет бейджа кредитов)

| Экшен | Тип |
|---|---|
| **Use formula** | Transformation |
| HTTP API | Enrichment |
| Create Clay email campaign | Transformation |
| Send to external sequencer | Transformation |

То есть весь бесплатный гейт из §1 (стоп-лист, домен, дедуп-ключ, бакеты) действительно стоит **ноль**.

## Стоимость наших шагов

| Экшен | Кредитов / строка |
|---|---|
| Enrich Company (By Clay) | 1 |
| Enrich person (By Clay) | 1 |
| Enrich Person (People Data Labs) | **5** |
| Enrich person from email (Snov.io / Mixrank) | 2 |
| Scrape Website | 1 |
| Perform Search (Google) | 1 |
| Use AI | зависит от модели (`/ model`) |
| Enrich person (Apollo.io), Verify Email (Instantly), Validate Email (NeverBounce) | по своему ключу |

## Email: ручная цепочка против управляемого waterfall

Отдельные провайдеры: LeadMagic **1**, Enrow 1, Kitt 1, Icypeas 0.5, Findymail **2**, Hunter 2, Prospeo **2**, Datagma 2, Wiza 2.
Валидация: LeadMagic / Findymail / ZeroBounce / Debounce / Enrichley — **1 каждая**; отдельный «Verify email» — 0.4.

Наша текущая цепочка в худшем случае (все три провайдера + три валидации):

```
LeadMagic 1 + Validate 1 + Findymail 2 + Validate 1 + Prospeo 2 + Validate 1 = 8 кредитов/строка
```

Управляемый **Work Email waterfall** (By Clay, +10 провайдеров): **~2.9 кредита/строка** в среднем,
с оплатой только за сработавшего провайдера и остановкой на первом валидном. Плюс `Infer Email` — бесплатный шаг перед платными.

То есть замена из §2.1 покрывает 10 провайдеров вместо 3 и при этом дешевле нашей худшей ветки примерно втрое.
Это уже не гипотеза — это цифры из интерфейса.

## Ориентиры по waterfall'ам Clay (для сравнения)

`Website Techstack` ~2.8/row (+3 провайдера), `Company Latest Funding` ~5.8 (+4),
`Company Funding Stage` ~4.9 (+6), `Company Total Funding` ~10.9 (+6).

**Что по-прежнему не измерено:** стоимость `Lookup Rows` (бейджа у него в панели не видно, но и явного «free» тоже),
цена `Use AI` по конкретным моделям, и главное — списывается ли кредит при `Only run if = false` (пункт C3B-01).
Это остаётся первым платным смоуком.
