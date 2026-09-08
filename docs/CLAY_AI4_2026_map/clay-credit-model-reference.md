# Clay: модель стоимости и семантика исполнения — из корпуса `CLAUDE_GTM_DATABASE`

Собрано 2026-08-20 повторным проходом по `tools/clay` (1167 файлов, 105.7 GiB→MiB: 105.7 MiB; 718 нормализованных документов).
**Этот файл отменяет часть утверждений в `redesign-proposal.md` §0 и §5 — см. раздел «Что я утверждал неверно».**

---

## 1. Две валюты, а не одна

`https://university.clay.com/docs/actions-data-credits`

| | **Actions** | **Data Credits** |
|---|---|---|
| Что измеряет | оркестрацию на платформе Clay | покупку данных/AI у 150+ сторонних провайдеров |
| Цена единицы | «a few tenths of a penny» | «a few pennies» |
| За обогащение | **всегда 1** | 0.5–10+ в зависимости от типа данных |
| Пополнение | только апгрейд тарифа, **разовый топ-ап невозможен** | апгрейд ИЛИ разовый топ-ап (+30% премия) |
| Перенос остатка | **нет**, сгорает в конце цикла | да, до 2× месячного лимита |

Лимиты Actions по тарифам: **Launch 15 000 / Growth 40 000 / Enterprise 100 000+** в месяц.
Data Credits: Launch 2 500–10 000 / Growth 6 000–100 000 / Enterprise 100 000+.
Ориентир Clay: «Each fully enriched record typically costs **6–20 Data Credits**».

### Что тратит Action (по 1 на запись)
Каждое обогащение любого провайдера · **использование своего API-ключа тоже** · любой AI-запуск · сигналы ·
экспорт в CRM/склад · **HTTP API** · 1 на лида, добавленного в кампанию Clay-сиквенсера · **1 на запись, выгруженную во внешний сиквенсер** · экспорт ads-аудиторий.

### Что НЕ тратит Action (документировано явно)
- **Формулы и фильтры Clay**, скоринг и нормализация формулами
- **`Send Table Data`** (перекладывание между таблицами Clay)
- **`Lookup Single Row in Other Table`** ← это закрывает вопрос C3B-04
- поиск списков (`Find People` вернул 100 контактов = 0 Actions), импорты из CRM/склада/вебхуков, ручной ввод, Sculptor, создание аудиторий (платный только экспорт)

### Свой API-ключ
«Connecting your API keys to Clay will **eliminate the Data Credit cost**. Note that **an Action will still be consumed**.»
Токены при этом биллит сам провайдер, и Clay их не показывает — «Clay will only show the Actions used, but not the AI token costs themselves».

---

## 2. Цены AI-моделей в data credits

`https://university.clay.com/docs/ai-pricing`

| Провайдер | Модель | Content Generation | Web Research |
|---|---|---|---|
| Clay | Helium | — | 1 |
| Clay | **Argon** | — | **3** |
| OpenAI | GPT-4o | 1 | variable |
| OpenAI | GPT-4.1 | 1 | variable |
| OpenAI | GPT-5.1 | 2 | variable |
| OpenAI | **GPT-5 Mini** | **0.4** | 1 |
| OpenAI | **GPT-5 Nano** | **0.2** | 0.5 |
| OpenAI | **o3** | **5** | variable |
| Anthropic | Claude 4.5 Haiku | 1 | variable |
| Anthropic | Claude 4.5 Sonnet | 1.5 | variable |
| Anthropic | Claude 4.6 Opus | 7.5 | variable |
| Gemini | 2.5 Pro | 3 | variable |
| Gemini | 2.5 Flash / Flash Lite | 0.5 | 1 |

- **Fixed** прайсинг — 80% моделей, включая все модели Clay: цена известна до запуска.
- **Variable** — 20% (самые сильные reasoning-модели): `Credit Charge = Actual LLM Cost ($) ÷ Workspace Cost Per Credit ($)`,
  **наценка 0%**, точная цена строки видна в таблице после прогона. Перед запуском Clay удерживает оценку по
  **75-му перцентилю прошлых прогонов** этой модели.
- Бюджет на запуск задаётся вручную — это и есть поле `runBudget`, которое я видел в дампе AI4.

### Что это значит для AI4 напрямую
Колонка `Category` в `Speakers & Attendees Enrichment` настроена на **o3** (`runBudget: 5`).
o3 content generation = **5 data credits/строка**. На 13 464 строках это **≈67 000 data credits за одну колонку** —
больше месячного лимита тарифа Growth. В проверенных строках она `empty`, то есть пока не запускалась.
Это самая крупная отложенная трата в таблице, и она ничего не производит.

---

## 3. Экономия: что Clay советует сам

`https://university.clay.com/docs/clay-credit-conservation`

1. **Выключать auto-update, пока строишь таблицу** — иначе случайно добавленные строки обогащаются.
2. **Свои API-ключи** (OpenAI, Anthropic, Apollo, Findymail, Prospeo, Debounce, NeverBounce).
3. **«Qualify leads before enriching»** — дословно: «By adjusting the order of enrichments, you can save credits by
   enriching only the leads that meet specific criteria… filtering them out ensures that only qualified contacts are enriched».
4. **Тест на ~10 строках** перед прогоном всей колонки; для AI — итерации промпта до полного запуска.
5. **Conditional runs** — «enrichments only run when specific conditions are met».

### Важная поправка к «взять модель подешевле»
Урок `lessons/best-practices-to-maximize-your-credits` прямо спорит с этим:

> «You could save credits by choosing the cheaper 1-credit Claygent Helium AI models over the 3-credit Claygent Argon
> model. But if your data quality drops even 10% across 100,000…»

То есть рычаг — **не запускать** на ненужных строках, а не **запускать хуже** на нужных.
Это ровно то, что делает v5 Quality Engine: `clay-argon` (3 кредита/строка) на одну строку ивента, а не Helium на всё.

---

## 4. Формулы: почему мой IIFE не прошёл

`https://university.clay.com/docs/formula-generator`

- Формулы Clay — это **JavaScript-выражения**, не блоки со `const`/`return`. Отсюда «Invalid formula» на моей первой версии.
- Доступно: стандартный JS (`Math`, `String`, `Array`, `Date`, `RegExp`, `Number`, `Object`), **Lodash через `_`**,
  **Moment.js через `moment`**, и **функции Excel/Google Sheets через FormulaJS** (`VLOOKUP`, `IF`, `SUM`, `CONCATENATE`).
- `{{Column}}` подставляет значение колонки.

### Conditional runs — документированный порядок действий
`https://university.clay.com/docs/conditional-runs` + formula-generator:

1. Панель обогащения → **Run Settings** → `Only run if`
2. Нажать **`Use AI`**
3. Описать условие, вставляя колонки через `/`
4. Нажать **`Generate formula`**
5. **Проверить sample outputs справа** — «to ensure your condition behaves as expected»

Ручная запись формулы документирована как возможная («You can also write conditional formulas manually using
JavaScript expressions that evaluate to true or false»), но в живом UI мой ручной ввод с чипом колонки **не сохранился**:
Save оставался неактивным с подсказкой «Regenerate formula to apply your changes». Рабочий путь — п.2–4.
FAQ подтверждает и то, что я использовал: **«Save and don't run enrichments»**.

Структура условий — `docs/conditional-statements`: IF / ELSE IF / ELSE, операторы сравнения, AND/OR/NOT,
и три предупреждения, прямо релевантных нашему стоп-листу: **пустые поля**, **граничные значения**, **неожиданные форматы**.
Наш баг с `hr` внутри `Threat` — это ровно их «unexpected formats».

---

## 5. Как измерять факт, а не гадать

`https://university.clay.com/docs/credit-usage`

**Settings → Usage** — по папкам/воркбукам/таблицам, сортировка, фильтр по времени/владельцу/интеграции, экспорт CSV.

**Дашборд конкретной таблицы** (кнопка `Credit usage` в поповере кредитов или `Table History` внизу справа) — три вида:
- **Time view** — временной ряд, агрегация по часу/дню/неделе/месяцу, **разбивка каждого столбца по типу экшена**
- **Column view** — **сколько кредитов съела каждая колонка** ← прямой ответ на «что дороже всего в AI4»
- **Run view** — по прогонам: ручной клик Run против автоматического (расписание/auto-update)

Все три выгружаются в CSV. **Исторические данные дашборда таблицы — с 5 ноября 2025.**
Overview на уровне воркспейса: Balance и Spend breakdown, кастомный диапазон **до 18 декабря 2024**, drill-in по спайку.

**Вывод:** «платный смоук», который я предлагал, для оценки текущего дизайна **не нужен** —
трату существующей таблицы AI4 можно поднять постфактум, по колонкам, с ноября 2025.

---

## 6. Ограничители расхода

- **Workbook credit limits** (Enterprise): в настройках воркбука → `Credit spend limit` → `Manage` → лимит.
  «When the limit is reached, you'll see an error message **preventing further Actions from running**».
  Менять может только админ воркспейса.
- **Credit budgets** (Enterprise, `docs/credit-budgets`): именованные бюджеты с лимитом и сбросом
  (Never / Monthly / Quarterly / Annual), выдаются группам или людям, привязываются к воркбукам при создании.
  **«When a budget's limit is reached, executions stop.»** Трекинг начинается с момента включения, не задним числом;
  существующие воркбуки остаются unbudgeted до ручного назначения.

Для прогона на 13 464 строках это правильный предохранитель — лучше, чем «выключить auto-run и надеяться».

---

## 7. Семантика исполнения формул (sandbox, 0 кредитов)

`zero_credit_sandbox/registries/clay_execution_semantics.jsonl` — 9 тестов, confidence high:

| Тест | Что установлено |
|---|---|
| ZC-01 | формулы считаются от upstream-текста, порядок строк сохраняется |
| ZC-02 | правка upstream пересчитывает формулу **без ручного запуска** |
| ZC-03 | цепочка зависимостей считается в порядке зависимостей и каскадит |
| ZC-04 | null на входе → **обе зависимые ячейки пустые**, без ошибки/pending/retry |
| ZC-05 | ошибка формулы → «This formula could not be calculated» + иконка retry; сводка колонки показывает смешанное состояние |
| ZC-06 | downstream от ошибочной ячейки → **тоже ошибка**, а не отдельное «skipped» |
| ZC-07 | object/array в **text**-формуле → `[object Object]` + предупреждение; структура НЕ сохраняется |
| ZC-08 | выбор строки в formula-only таблице даёт в Actions только `Delete`, кнопки Run нет (не обобщается на enrichment-колонки) |
| ZC-09 | restore конфигурации убирает добавленную колонку, значения остаются, формулы пересчитываются; предыдущая конфигурация сохраняется как новая версия |

---

## Что я утверждал неверно (и что теперь верно)

| Раньше говорил | Как на самом деле |
|---|---|
| «Цифр по кредитам в корпусе нет» | Неверно. `credit_cost`/`credit_implications` в **реестрах** = UNKNOWN (496 и 33 записи), но в **документах** есть полная модель: `actions-data-credits`, `ai-pricing` с таблицей цен по моделям, `credit-usage`, `clay-credit-conservation`, `credit-budgets`. Я смотрел реестры и не открыл доки. |
| «AI на своём ключе ничего не стоит» | Не тратит **Data Credits**, но **тратит 1 Action на строку**. Actions не переносятся и не докупаются — это более жёсткий лимит. |
| «Стоимость Lookup Rows не доказана, нужен платный тест (C3B-04)» | Документировано: `Lookup Single Row in Other Table` и `Send Table Data` **не тратят Action**. Многотабличная архитектура дешёвая. |
| «Ручная цепочка email = до 8 кредитов/строка» | Основание было неверное: я считал по 1 за каждую валидацию. Clay в примере: поиск email ≈0.5, **валидация 0** («select validator providers are free under new pricing»). При этом бейджи в UI показывали 1–2 за поиск и 1 за валидацию — **источники расходятся**, надо сверять по факту через Column view. |
| «Семантика `Only run if` не доказана» | Само поведение документировано (`conditional-runs`, `formula-generator`), включая проверку по sample outputs. Не документировано только одно: **тратит ли Action условие, вернувшее false**. Вот это и остаётся для платной проверки. |
| «Формулы не приняли мой IIFE — надо было выяснять тыком» | Документировано: формулы = **JS-выражения**, плюс Lodash/Moment/FormulaJS. |
| «Взять модель подешевле» (§2.4–2.5 предложения) | Clay сам возражает: падение качества на 10% по 100 000 строк дороже экономии на модели. Рычаг — не запускать лишнее, а не ухудшать нужное. |
| «Нужен платный смоук, чтобы узнать стоимость» | Для **существующей** таблицы не нужен: Column view даёт трату по колонкам с 5 ноября 2025. Платный тест нужен только под новый дизайн и под вопрос про false-условие. |
