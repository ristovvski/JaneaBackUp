# Clay CLI — выгрузка таблиц для карты колонок

Дата: 2026-08-20
Запрос: залезть в Clay через CLI и выгрузить таблицы, чтобы понять назначение каждой колонки.
Цель, уточнённая по ходу: воркбук `wb_0ti6a5icZRyKYfCJm2b` = `[LATEST - USE FOR EVENTS] AI4 2026`, workspace **332169**.

## Done
- `clay` v0.5.0 в WSL (`/home/nikita98/.local/bin/clay`). Стартовая сессия: user {{OTHER_WORKSPACE_USER}} (Mykyta), workspace **{{OTHER_WORKSPACE}}** — там инвентарь **{{N}} таблиц / {{N}} воркбуков**.
- Целевой воркбук в **другом** workspace (332169) → был `not_found`. Переавторизация через `clay login --device`
  (код VDVK-HSJK, approve владельцем) → сессия стала **workspace 332169, user 355687 (Sergey Cujba)**.
  `CLAY_PUBLIC_API_KEY` из `.env` тоже скоупнут на {{OTHER_WORKSPACE}} (`GET /public/v0/me`), обойти ключом нельзя.
- Выгружены все 4 таблицы воркбука: `tables get` + `tables columns get` (полные settings) + сэмплы строк.
  Сырьё в репо: `CLAY_AI4_2026_map/raw/`.
- Написана карта колонок по лейнам (170 колонок, 4 таблицы): `CLAY_AI4_2026_map/clay-ai4-2026-column-map.md`.
- Проверено на фактических значениях ячеек (2 срезa: первые 3 строки + 4 строки с фильтром `Are we adding to Linkedin? = Yes`):
  1. ICP-вердикт мёртв: категоризаторы (кол. 68/70/71) `status: empty` → `Look Up` вырожден → `Verdict` = null;
     плюс сама `Targeting Rules` пуста (0 строк).
  2. Smartlead-лейны (кол. 65 `3686187`, кол. 66 `3756410`) `empty` даже на строке с `Email Status = Deliverable`;
     живой лейн — HeyReach `512995` (кол. 85, `✅ Lead updated`).
  3. HeyReach-диспатч (кол. 85/86) **без run-условия и без гейта** на `Should Remove?`/DNC/`Final Score` —
     защита только ручным флагом `Are we adding to Linkedin?` + фильтром вью.
  4. `Email DNC` (кол. 67) считается, но в `Should Remove?` не входит.
  5. `Lead Assignment for Smartlead` (кол. 88) = `Math.random()` → пересчёт переназначает Mario↔Rune; ни к одному action не привязана.
  6. Промпты follow-up'ов про чужие ивенты: в кол. 47 user-промпт «The AI Summit NYC (NOT NVIDIA GTC…)» против
     `systemPrompt` «we were attending NVIDIA GTC»; кол. 51 целиком про NVIDIA GTC. AI4 не упомянут нигде.
  7. Кол. 31 ORит один и тот же LinkedIn DNC дважды (копипаст), хотя prompt описывает Person/Company DNC. Потерь нет (кол. 30 покрывает).
  8. `Missing input` на Person/LinkedIn DNC = пустой LI-URL, не поломка: где URL есть — `❌ No Record Found`.
     Таблица `t_0ti6a5ifBrwkAWiYZYX` (LinkedIn DNC) не читается через `tables get`, но лукап рабочий.
  9. Дубли/заглушки: кол. 39 дублирует 38; кол. 54 = «Add Your Prompt Here.»; кол. 60 начинается с «Add prompt here.».
  10. В follow-up-таблице `FINAL SCORE` = среднее кол. 18/19; третий скоринг (кол. 20) считается, но в среднее не входит.

## Partial
- Fill rate по всем 13 464 строкам главной таблицы **не измерен** — `rows list` идёт в порядке создания,
  проверены только ранние строки партии `7.14.2026`. Выводы 1–2 верны для проверенных строк; по всей таблице нужен полный проход.
- Фильтр по boolean-колонке (`Picked by Melisa = true`) CLI отклонил → срез по отбору Melisa не проверен.

## Blocked
- Ничего не заблокировано; чтения только, ни одна колонка не запускалась и ничего не писалось.

## Improvable
- `queryEnabled: false` на всех 4 таблицах → агрегаты (`clay tables query-live`) недоступны без включения query-sync.
  Это единственный дешёвый путь измерить fill rate по 13k строк вместо постраничного обхода.
- Публичный API не отдаёт листинги таблиц/воркбуков (`/public/v0/tables`, `/workbooks` → 404) — инвентарь только через CLI.
- CLI держит один профиль (`profiles.default`): сейчас он на 332169. Возврат к {{OTHER_WORKSPACE}} = повторный `clay login`.
  Два воркспейса одновременно штатно не держатся.
- `/tmp` в этой WSL — tmpfs, и дистрибутив рестартует между вызовами: промежуточные файлы дважды пропали.
  Всё, что нужно сохранить, писать сразу в `/mnt/c/...`, не в `/tmp`.
- Git Bash конвертирует `/mnt/...` в аргументах (`C:/Program Files/Git/mnt/...`): вызовы `wsl -e bash -lc` с такими
  путями запускать с `MSYS_NO_PATHCONV=1`.

---

## Дополнение: редизайн-предложение (тот же день)

- Получен доступ к `CLAUDE_GTM_DATABASE` (путь: `C:\Users\User\Documents\ChatGPT\Data Storage\GTM_TOOL_KNOWLEDGE_MAIN\tasks\2026-08-20_claude_share_bundle\CLAUDE_GTM_DATABASE`).
  Retrieval по правилам бандла: registry → `tools/clay/public/CLAY_MASTER_INDEX.md` → целевые доки.
- **Цифр по кредитам в корпусе нет**: `credit_implications: UNKNOWN` в feature inventory, все 12 decision rules `PARTIAL`
  с «do not infer undocumented cost or plan behavior», статус корпуса `PAID_VALIDATION_REQUIRED`.
  Поэтому прогноз экономии в деньгах не делался — только документированные механики.
- Проверено sandbox-оверлеем (0 кредитов): auto-update каскад, пустой вход → пустой downstream, ошибка → ошибка downstream,
  text-формула коерсит object в `[object Object]`, выбор строк не даёт Run.
- Не доказано (C3B-очередь, ничего не запускалось): `Only run if` семантика, стоимость Lookup Rows, Send Table Data + циклы,
  HTTP/API, остановка waterfall'а. На них опирается вся экономия → нужен платный смоук первым шагом.
- Найдено ключевое: каноничный клейбук Clay под наш кейс (`enrich-and-score-event-signups`) требует
  **квалифицировать до обогащения**; AI4 делает наоборот — тратит всё дорогое на 13 464 строках и скорит в конце.
- Найдено ключевое: `Work Email waterfall` платит **только за провайдера, который нашёл**, + бесплатный `Infer Email`
  (по внутреннему тесту Clay `first.last@domain.com` ≈31%) + `Threshold for duplicate results`. Заменяет 9 наших колонок.
- Инвентарь workspace 332169: 74 воркбука / 242 таблицы; Clay Workflows — НЕТ ни одного (вся логика в колонках таблиц).
- Найден `Janea | Event Intelligence v5 | QUALITY` (`wb_0tjr7s0uc746Ck2pmjw`, 14 авг): `Events | Quality Decision Engine v5`,
  17 колонок, паттерн A (Claygent evidence) → B (независимая перепроверка) → C (примирение без веба, precedence,
  null при конфликте) + человеческий QA-гейт. Уровень ивента, не человека — предложено перенести паттерн на лида.
- Предложение: `CLAY_AI4_2026_map/redesign-proposal.md` (6 разделов, включая границы доказанности и платный смоук-план).

### Ограничение исполнения
Таблицы в Clay **нельзя создавать через CLI/API** — только UI. Моя роль: спека + верификация через
`clay tables columns get` / `rows list`. Клики за человеком.

---

## Дополнение 2: CLI 0.8.1 + сборка в UI (тот же день)

### Обновление CLI
- `clay update --check` → 0.8.1 доступен, но «managed by the Clay agent plugin and is pinned».
- Штатный путь (скилл `update`): `claude plugin marketplace update clay-plugins` + `claude plugin update clay@clay-plugins`
  → плагин 2.6.0 → **2.9.1**, CLI-пин 0.5.0 → **0.8.1**.
- Форвардер `~/.local/bin/clay` резолвит НОВЕЙШУЮ по mtime папку `/mnt/c/.../plugins/cache/*/clay/*/bin/clay`;
  2.6.0 и 2.9.1 получили одинаковый mtime, поэтому `clay --version` остался 0.5.0.
  Обошёл, зеркалируя bin из 2.9.1 в `~/.config/clay-plugin-291/bin` (сработало: 0.8.1+e05e171cb82d).
  После рестарта Claude Code форвардер должен взять 2.9.1 сам.
- **Проверено на 0.8.1: у `clay tables` по-прежнему НЕТ create/write** (list/get/columns/rows/query/query-live/query-usage/update).
  Так что «таблицы только через UI» — это свойство API, а не старой версии.

### Собрано в UI (workspace 332169, аккаунт Sergey Cujba)
- Воркбук `SANDBOX — Event Lead Gate v1` = `wb_0tk2fuygVeq4SvhUZYa`, таблица `Free Gate Demo` = `t_0tk2fvePWz3SDa7c9xE`.
- Колонки: `Title` (text), `Domain` (text), `Kill — free` (formula).
- Формула — одно выражение (движок Clay **не принял** IIFE с `const`: «Invalid formula»), стоп-лист из 56 слов,
  сопоставление ПО СЛОВАМ (`" "+k+" "` по нормализованным токенам) вместо продового `includes(keyword)` по подстроке.
- Результат (сверено и в UI, и через `clay tables rows list`):
  Senior HRIS Manager → keep · Threat Intelligence Manager → keep · Head of HR → KILL title ·
  Technical Recruiter → KILL title · VP Engineering @ stanford.edu → KILL domain · пустая строка → keep.
- Ранее собран воркфлоу `Event Lead — Free Gate v1` (`wf_0tk2fl9bThQJRbr5ict`), code-нода `wfn_0tk2fmarKcz62d5WDD3`,
  прогоны через `nodes test` дали те же вердикты. Триггера нет (черновик), таблично его подключить можно только в UI.

### Кредиты: пробел корпуса закрыт UI-панелью Tools
- Бесплатно (нет бейджа): **Use formula**, HTTP API, Create Clay email campaign, Send to external sequencer.
- 1/строка: Enrich Company (By Clay), Enrich person (By Clay), Scrape Website, Perform Search (Google).
- Enrich Person (People Data Labs) — **5/строка**; Snov.io / Mixrank — 2; Apollo / Instantly / NeverBounce — по своему ключу.
- Email-финдеры: LeadMagic 1, Enrow 1, Kitt 1, Icypeas 0.5, Findymail 2, Hunter 2, Prospeo 2, Datagma 2, Wiza 2.
  Валидаторы: 1 каждый (ZeroBounce/Debounce/LeadMagic/Findymail/Enrichley), отдельный «Verify email» 0.4.
- **Work Email waterfall (By Clay, +10 провайдеров) — ~2.9/строка.** Наша ручная цепочка в худшем случае = 8/строка.
- Use AI — «/ model» (зависит от модели), точных цифр по моделям не видно.

### Ошибки, которые я допустил по ходу (для протокола)
1. Выбил лимит `workflows code test` (10/день) и **12 прогонов подряд напечатал как «keep»**, хотя это были ответы
   `rate_limited` — парсер печатал ярлык вместо проверки поля. Тот же класс, что [[no-substring-blob-checks]].
   Перепроверил локально на настоящих ассертах.
2. Сначала посчитал «26 action-колонок отработало» по статусу `success`, тогда как `success` + пустое значение = гейт
   сработал и провайдер не вызывался. Правильная метрика — непустое значение: на выброшенной строке это **12** колонок.
3. Создал воркфлоу до того, как выяснил, что **удалить его через CLI нельзя** (в группе `workflows` нет `delete`).

## Improvable (дополнение)
- Синтетический ввод в грид Clay ненадёжен: первый символ уходит на вход в режим редактирования, `Escape` отменяет,
  а `ctrl+a` вне режима редактирования выделяет ВСЕ строки (дважды поймал «6/6 rows selected» + меню Actions).
  Надёжный путь — `double_click` по ячейке → `find` textbox → **`form_input`** → `Return`.
- В таблице `Free Gate Demo` осталась пустая строка 2 (демонстрирует «пустой вход → keep»), можно удалить.
- Не проверено: списывается ли кредит при `Only run if = false` (C3B-01) и стоимость `Lookup Rows` (C3B-04).

---

## Дополнение 3: конвейер собран в UI (не только гейт)

Таблица `Free Gate Demo` (`t_0tk2fvePWz3SDa7c9xE`) в `SANDBOX — Event Lead Gate v1` (`wb_0tk2fuygVeq4SvhUZYa`)
доведена с 3 колонок до **39**. Режим таблицы — `Manual` (auto-run ВЫКЛ), выполнено **0 запусков, 0 кредитов**.

### Слои
1. **Вход:** Title, Domain, First Name, Last Name, Company, LinkedIn URL, Event Name (событие — ДАННЫЕ, не текст промпта).
2. **Бесплатный слой (формулы, 0 кредитов):**
   - `Full Name` = First + Last;
   - `Dedup Key` = `first last (company || domain)` lower — не пустеет, когда компании нет (лечит дырку auto-dedupe);
   - `Kill — free` = стоп-лист 56 слов **по словам** + `.edu/.gov/.org`.
3. **Платный слой — оба входа под гейтом:**
   - `ICP Fit Score` — Use AI, use case «Create or modify content» (без веба), модель OpenAI GPT-4o **на своём ключе
     `janea-api-key`** → бейдж кредитов Clay исчезает (на дефолтной модели Clay было 3/row);
   - `Work Email` — управляемый waterfall: `Infer email` (бесплатный шаг) → `Validate Clay` → 12 провайдеров,
     у каждого своя валидация → итоговый `Work Email`. Входы: Full Name, Domain, Company, First/Last, LinkedIn URL.
     **~2.7 кредита/строка** с Infer против ~2.9 без него.
4. **`Dispatch Gate`** (формула): `READY to dispatch` / `blocked: <причина>` / `hold: no email`.
   Диспатч-экшены НЕ подключены осознанно (внешние записи).

### Проверено
- Clay сам рисует по строкам: `keep → Will run`, `KILL title|domain → Will not run` (3 из 6 строк не пойдут в платный шаг).
- Гейты прочитаны обратно через CLI:
  `ICP Fit Score` → `[Kill — free]?.toLowerCase() == "keep"`; `Infer email` → `[Kill — free]?.toLowerCase()==="keep"`.
- Строка 4 (`Threat Intelligence Manager`, синтетическая Ada Testerova @ example.com) прошла весь бесплатный слой:
  Full Name и Dedup Key посчитались, `Kill — free = keep`.
- «Save and run 6 rows in this view» показывал **~16.2 кредита** на 6 строк — цена прогона без гейта.

### ЛОВУШКА UI (стоила двух перезаходов)
`Only run if` **молча не сохраняется**, если вписать формулу с чипом колонки руками: Save остаётся неактивным
с подсказкой «Regenerate formula to apply your changes». Рабочий путь — **описание на естественном языке + кнопка
`Generate`**, которая компилирует его в формулу (`{{Kill — free}}?.toLowerCase()==="keep"`). Первый сохранённый
вариант `ICP Fit Score` уехал БЕЗ гейта, и это поймалось только чтением обратно через `clay tables columns get`.
**Правило: после установки run-условия всегда читать его обратно из CLI.** Ср. [[smartlead-add-readback-rule]].

Прочее: `Escape` в панели колонки закрывает её и **теряет** несохранённую конфигурацию (так пропала первая сборка
waterfall'а). Дропдауны в панели закрывать кликом по нейтральному месту, не Escape.
