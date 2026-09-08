# Clay — карта колонок воркбука `[LATEST - USE FOR EVENTS] AI4 2026`

| | |
|---|---|
| Workbook | `wb_0ti6a5icZRyKYfCJm2b`, создан 2026-07-14, owner `355687` |
| Workspace | **332169** — отдельный Clay-аккаунт (**Sergey Cujba**), не тот, где живут остальные наши таблицы ({{OTHER_WORKSPACE}} / Mykyta) |
| Выгружено | 2026-08-20, `clay` CLI v0.5.0 (WSL), OAuth-сессия 332169 |
| Сырьё | `raw/` — `.meta.json` / `.columns.json` (полные settings) / `.rows.json` (сэмплы) |

## Таблицы

| Таблица | id | Строк | Колонок | Роль |
|---|---|---|---|---|
| Speakers & Attendees Enrichment | `t_0ti6a626jog6NWTPTuM` | 13 464 | 89 (55 basic + 34 action) | главный конвейер: список участников AI4 → обогащение → диспатч в кампании |
| [TEMPLATE with Google Sync] Automated Follow-Ups | `t_0ti6a5iMvbufkna2hZA` | 150 | 65 (31 + 34) | ресёрч + генерация follow-up'ов по ответившим, выгрузка в Google Sheet |
| Targeting Rules | `t_0ti6a5ieGgfnj3TohR3` | **0** | 7 | lookup-таблица ICP-вердикта (пустая) |
| Fixed Data | `t_0ti6a5iMR2WbYVvkMux` | **0** | 9 | ручные override'ы LinkedIn-профилей и имён (пустая) |

Внешние lookup-таблицы, на которые ссылается конвейер (живут вне воркбука):
`t_0sw3iz48Kq2qAonaxjU` People DNC (24 181), `t_0sw3izjtgU4MoDF4GNF` Company DNC (1 386),
`t_0t43bjyygEKQKD27iDv` People Email DNC (1 650), `t_0ti6a5ifBrwkAWiYZYX` LinkedIn DNC (через `tables get` не читается, но лукап работает).

---

## 1. Speakers & Attendees Enrichment — 89 колонок по лейнам

### Лейн 0. Вход из списка мероприятия
| # | Колонка | id | Назначение |
|---|---|---|---|
| 3 | First Name | `f_eHgDmZYD9gXP` | сырое имя из выгрузки участников |
| 4 | Last Name | `f_6jQePqtWxv9s` | сырая фамилия |
| 9 | Company Name Input | `f_JrB2xUdjury7` | сырое название компании (может быть пустым) |
| 15 | Website | `f_2NHvHDVXFmuw` | сырой сайт/домен (может быть пустым) |
| 23 | Type | `f_0svta6cboVKN6CSeWsy` | роль на ивенте: `attendee` / `speaker` |
| 24 | Title Input | `f_0t081fhkWcajisaNAcZ` | сырая должность из списка |
| 25 | Batch | `f_0t6su6h5GAxP7R9MNfB` | метка партии импорта (в сэмплах `7.14.2026`) |
| 26 | Personal LinkedIn Profile | `f_6q56yaCkgUs2` | сырой LI-URL, если был в списке |
| 83 | Event User ID | `f_0ti6adyJPGParFb6j7p` | id участника в системе ивента (base64, напр. `VXNlcl8yODQyMDUwMA==`) |
| 1–2 | Created At / Updated At | `f_created_at` / `f_updated_at` | системные |

### Лейн 1. Нормализация имени (под merge-поля письма)
| # | Колонка | Назначение |
|---|---|---|
| 5 | Full Name | формула `First + " " + Last` |
| 6 | Name Normalization | AI (gpt-4o-mini): чистит имя/фамилию для подстановки в «Hi {{first_name}}» |
| 7 | First Name For Using | `NameNormalization.first_name` **\|\|** `Full Name.split(" ")[0]` — то, что реально идёт в кампанию |
| 8 | Last Name For Using | то же для фамилии |

### Лейн 2. Компания и домен (двусторонний доресёрч)
| # | Колонка | Назначение |
|---|---|---|
| 10 | Find Company Name | Claygent: домен → название. **RUN IF** `!Company Name Input` |
| 11 | MASTER COMPANY NAME | waterfall: вход → результат Claygent |
| 12 | Normalize Company Name | встроенная нормализация Clay |
| 13 | Normalized Company Name | AI: бренд-корректное имя для текста письма |
| 14 | Company Name | `AI-нормализованное \|\| встроенное` — итоговое имя |
| 16 | Find Company Domain | Claygent: название → домен. **RUN IF** `!Website` |
| 17 | Result | `FindCompanyDomain.result` |
| 18 | MASTER DOMAIN COLUMN | waterfall: `Website` → Claygent-домен |
| 19 | Normalize a Domain | → `bareDomain` |
| 20 | Domain | `NormalizeDomain.normalizedUrl` — рабочий домен для всех провайдеров |
| 46 | Is Credit Union? | `MASTER COMPANY NAME` содержит «credit union» (отдельный сегмент/исключение) |

### Лейн 3. Дедуп-ключ
| # | Колонка | Назначение |
|---|---|---|
| 21 | Deduplication Column | `lower(first)+" "+lower(last)+" "+lower(company)` — ключ дедупа; им же джойнится **Fixed Data** (кол. 78) |
| 22 | Title | `Title Input ? Title Input : EnrichPerson.title` — итоговая должность |

### Лейн 4. LinkedIn: резолвинг и верификация
| # | Колонка | Назначение |
|---|---|---|
| 37 | Find LinkedIn Profile URL | Claygent (gpt-5.4-mini): ищет профиль по имени+компании. **RUN IF** `!Personal LinkedIn Profile` |
| 38 | MASTER PERSONAL LINKEDIN PROFILE URL | waterfall: ручной override из Fixed Data → сырой LI из списка → результат Claygent |
| 42 | Enrich Person from Profile | скрейп/обогащение профиля (даёт `current_experience`, `country`, `url`) |
| 43 | Enriched LI URL | `EnrichPerson.url` — канонический URL |
| 39 | LinkedIn Match AI Check | AI-верификатор: «это точно тот человек?» (строгий, gpt-4o-mini) |
| 40 | Response | текстовый ответ верификатора |
| 41 | Claygent LI Profile Check | boolean: домен/URL/название компании из `current_experience` совпали с нашей компанией **ИЛИ** верификатор сказал `match` |
| 79 | CORRECT LINKEDIN PROFILE | значение override'а из Fixed Data |
| 87 | LI URL for Smartlead | `Claygent LI Profile Check ? Enriched LI URL : ""` — в кампанию уходит LI только если матч подтверждён |

### Лейн 5. Suppression (кого выкидываем)
| # | Колонка | Назначение |
|---|---|---|
| 27 | **Should Remove?** | итоговый OR: `Title` \|\| `EmailDomain` \|\| `DNC` \|\| `LI DNC` \|\| `Competitor == yes` |
| 28 | Remove Based on Title? | должность содержит одно из ~55 стоп-слов (content creator, retired, student, professor, journalist, recruiter, hr, sales, bdr/sdr, intern, assistant, …) |
| 29 | Remove Based on Email Domain? | домен письма содержит `.edu` / `.gov` / `.org` |
| 30 | Remove Based on DNC Check? | есть запись в **Person DNC** или **Company DNC** |
| 31 | Remove Based on LI DNC Check? | есть запись в **LinkedIn DNC** (см. замечание №7 ниже) |
| 32 | Company DNC | лукап `t_0sw3izjtgU4MoDF4GNF` по `Domain` (EQUAL) |
| 33 | Person DNC | лукап `t_0sw3iz48Kq2qAonaxjU` по `EnrichPerson.url` |
| 34 | LinkedIn DNC | лукап `t_0ti6a5ifBrwkAWiYZYX` по `Enriched LI URL` |
| 67 | Email DNC | лукап `t_0t43bjyygEKQKD27iDv` по `Work Email (SMB)` — **в `Should Remove?` не входит** |
| 35 | Competitor Status | AI (gpt-4o) по скрейпу главной: компания сама оказывает услуги кастомной разработки? |
| 36 | Extracted Competitor Status | вытаскивает `Yes`/`No` из ответа |
| 59 | Connected With? | `PersonDNC.record.Owner` — кто из наших уже связан с этим контактом |

### Лейн 6. Email-waterfall (3 провайдера + валидация)
| # | Колонка | Назначение |
|---|---|---|
| 47 | Find Work Email | провайдер №1. **RUN IF** должность не в стоп-листе И домен не `.edu/.gov/.org` |
| 48 | Validate LeadMagic | валидация письма №1 |
| 49 | Find Work Email (2) | провайдер №2. **RUN IF** предыдущий не дал валидного |
| 50 | Validate Findymail | валидация №2 |
| 51 | Find Work Email (3) | провайдер №3, тот же каскад |
| 52 | Validate Prospeo | валидация №3 |
| 44 | **Work Email (SMB)** | waterfall: берёт письмо того провайдера, чья валидация вернула `valid_emails` |
| 53 | Work Email (SMB) Data Provider | имя сработавшего провайдера (LeadMagic / Findymail / Prospeo) |
| 54 | Email Status | `reason` от валидатора: `Deliverable` / `Accept All` / … — **гейт диспатча в Smartlead** |
| 45 | Scrape Website | скрейп главной страницы (premium proxy) — вход для Competitor Status и категоризации |

### Лейн 7. Обогащение компании
| # | Колонка | Назначение |
|---|---|---|
| 55 | Enrich Company | **RUN IF** `(есть email ИЛИ есть LI)` И должность не в стоп-листе И домен не `.edu/.gov/.org` |
| 56 | Employee Count | `EnrichCompany.employee_count` |
| 57 | Company Location | `EnrichCompany.country` |
| 58 | Person Location | `EnrichPerson.country` |

### Лейн 8. Скоринг ICP
| # | Колонка | Назначение |
|---|---|---|
| 60 | Job Title Qualification | AI-промпт скоринга должности (формат ответа `N; обоснование`) |
| 61 | Company Qualification Prompt | AI-промпт скоринга компании |
| 62 | Job Title Score | `parseInt(ответ.split(";")[0])` |
| 63 | Company Score | то же |
| 64 | **Final Score** | среднее двух — в сэмплах 6.5–8.5 |

### Лейн 9. Категоризация → Targeting Rules (сейчас **не работает**, см. №1)
| # | Колонка | Назначение |
|---|---|---|
| 68 | Company Category | AI (gpt-5-mini): категория компании |
| 69 | Company categorizer Response | `.response` |
| 70 | Current Job Title & Summary | AI (gpt-5.4): извлекает текущую должность и саммари из скрейпа LI |
| 71 | Category | AI (o3): категория человека |
| 72 | Job title categorizer Response | `.response` |
| 73 | Employee Range | бакеты `1--10 / 11--100 / 101--500 / 501--1000 / 1000+` |
| 74 | Look Up | конкатенация без разделителя: `companyCategory + employeeRange + jobTitleCategory`, lowercase — ключ джойна |
| 75 | Has All Fields? | все три части ключа непустые |
| 76 | Lookup Verdict | лукап в **Targeting Rules** по `Look Up`. **RUN IF** `Has All Fields?` |
| 77 | Verdict | `LookupVerdict.record.Verdict` |
| 78 | Check Fixed URLs | лукап в **Fixed Data** по `Deduplication Column` (ручные исправления профилей) |

### Лейн 10. Диспатч в кампании
| # | Колонка | Назначение |
|---|---|---|
| 65 | [Check Campaign Before Running] **Valids** | Smartlead, `campaign_id 3686187`. **RUN IF** `Email Status` содержит `deliverable` |
| 66 | [Check Campaign Before Running] **Catch-alls** | Smartlead, `campaign_id 3756410`. **RUN IF** `Email Status` содержит `accept all` |
| 80 | TMP | синтетический email `firstlastcompanybatch@test.com` — заглушка для LinkedIn-кампании Smartlead |
| 81 | Add to LinkedIn | Smartlead, `campaign_id 3526869`, письмо = `TMP`, LI = `Enriched LI URL`. **Без run-условия** |
| 82 | Total Leads | `.total_leads` из ответа Smartlead |
| 84 | Are we adding to Linkedin? | ручной текстовый флаг (`Yes`) |
| 85 | **Add Lead to Campaign** | **HeyReach**, `campaignId 512995` — единственный лейн, который в проверенных строках реально отработал (`✅ Lead updated`). **Без run-условия** |
| 86 | Add Lead to Campaign (2) | HeyReach, `campaignId 513000` — в проверенных строках пусто |
| 88 | Lead Assignment for Smartlead | `Math.random()<.5 ? "Mario" : "Rune"` — раздача лидов между двумя владельцами |
| 89 | Picked by Melisa | ручной boolean — отбор Melisa |

Что уходит в HeyReach (кол. 85/86): `First/Last Name For Using`, `MASTER PERSONAL LINKEDIN PROFILE URL`, локация из `EnrichPerson.experience[0].locality`, `Company Name`, `Title`, `Work Email (SMB)`.
Что уходит в Smartlead (кол. 65/66): те же имена, `Work Email (SMB)`, `Domain`, `LI URL for Smartlead`, локация, `Company Name`, плюс `allow_duplicate_leads_in_another_campaign: true` и `allow_leads_from_community_bounce_list: true`.

---

## 2. [TEMPLATE with Google Sync] Automated Follow-Ups — 65 колонок

Назначение таблицы: по контакту, который **ответил** на холодное письмо, собрать ресёрч, сгенерировать питч-угол и текст follow-up'а, сложить готовые блоки для заметки в Pipedrive и синхронизировать всё в Google Sheet для менеджера.

### Вход и резолвинг
| # | Колонка | Назначение |
|---|---|---|
| 3 | Campaign Name | из какой кампании пришёл ответ |
| 4 | Lead Owner | наш владелец лида |
| 5–7 | Full Name / Company Name / LI Profile | сырой вход |
| 8 | LinkedIn Profile URL | Claygent-поиск профиля. **RUN IF** `!LI Profile` |
| 9 | …Linked In Url | `.LinkedIn_URL` |
| 10 | MASTER LINKEDIN COLUMN | waterfall: сырой → найденный |
| 11 | Enrich Person | обогащение профиля |
| 12 | Title | `current_experience[0].title \|\| headline` |
| 13 | Person Location | `location_name` |
| 14 | Person's Posts | скрейп активности/постов LinkedIn |
| 22 | Current Experience - LI Company Page | URL страницы компании из опыта |
| 23 | Enrich Company | обогащение компании по этой странице |
| 24/26/27/28/29 | Domain / Industry / Employee Count / Company Country / Company Locality | поля из `Enrich Company` |
| 25 | Scrape Company Main Page | скрейп с `js_render` + `anti_bot` |

### Скоринг
| # | Колонка | Назначение |
|---|---|---|
| 15 | Job Title Score | AI-промпт скоринга должности |
| 16 | Company Qualification Prompt | AI-промпт скоринга компании |
| 17 | Prompt 4 (Master Prompt) | третий AI-скоринг |
| 18/19/20 | …Extracted Score | `parseInt(ответ.split(";")[0])` |
| 21 | FINAL SCORE | среднее из 18 и 19 (20 в среднее **не входит**) |

### Ресёрч-сигналы
| # | Колонка | Назначение |
|---|---|---|
| 30 | Find Active Job Openings | вакансии по домену, фильтр по ~списку инженерных должностей |
| 31 | Find Open Jobs | провайдер №2. **RUN IF** у №1 нет `jobCount` |
| 32 | Find Open Jobs (2) | провайдер №3, тот же каскад |
| 33 | Job Openings | waterfall по трём провайдерам |
| 34 | Website Job Posting Finder Agent | Claygent-фолбэк: ищет вакансии на самом сайте. **RUN IF** `!Job Openings` |
| 35 | Website Blog Post Finder Agent | Claygent: свежие посты блога |
| 36 | Website Product Updates Finder Agent | Claygent: продуктовые апдейты |
| 37 | Recent news | Claygent: свежие новости компании |
| 38 | Company focus | AI-саммари фокуса компании |
| 39 | Company focus (2) | дубль колонки 38 |
| 43 | Hiring Analysis | AI-анализ трендов найма по вакансиям |
| 52 | HIRING TRENDS SUMMARY | тот же анализ на claude-haiku-4-5 |
| 53 | RISKS AND OPPORTUNITIES | AI: риски и возможности по ресёрчу |
| 40 | Person-level infomation | AI-справка по человеку. **RUN IF** `Enrich Person` |
| 41 | Gathering Information. | AI-сборка всех сигналов. **RUN IF** колонка 40 |
| 44 | Master research summary | AI (gpt-5): структурированное саммари |
| 45 | Master Research Summary Output | `.response` |

### Питч и текст
| # | Колонка | Назначение |
|---|---|---|
| 42 | Janea Angle | AI (claude-haiku-4-5): под каким углом Janea заходит |
| 46 | R. Best pitch angle | AI (claude-sonnet-4-6): лучший угол выхода |
| 47 | MASTER MESSAGING | AI (gpt-4o): текст follow-up'а |
| 48 | Master Messaging Output | `.response` |
| 51 | Prompt 4 | альтернативный генератор текста (temperature Medium) |
| 54 | New Prompt 3 | заглушка, промпт = «Add Your Prompt Here.» |
| 55 | Total OpenAI Cost | сумма `totalCostToAIProvider` по всем AI-колонкам |

### Телефон (waterfall из 5 провайдеров)
| # | Колонка | Назначение |
|---|---|---|
| 56 | Find Mobile Number | провайдер №1 по LI-профилю |
| 57 | Enrich Person (2) | №2, `requirePhone: true`. **RUN IF** №1 пусто |
| 58 | Find Phone Number | №3, каскад |
| 59 | Find Phone Numbers | №4, каскад |
| 60 | Find Mobile Number (2) | №5, каскад |
| 61 | Mobile Phone | waterfall по всем пяти |

### Выход
| # | Колонка | Назначение |
|---|---|---|
| 49 | Pipedrive 1 (number, research, hiring) | склейка текста заметки: телефон + research summary + hiring trends |
| 50 | Pipedrive 2 (risks and opportunities, messaging) | вторая заметка: риски/возможности + messaging |
| 62 | Response status | ручной статус ответа |
| 63 | Priority level | ручной select приоритета |
| 64 | Links to Audio Notes | ссылка на аудио-заметки |
| 65 | Lookup, Add, or Update Row | upsert в Google Sheet `1mhZD_HSkmVvtXsYg1XLRZNp12MCkmus5zq028T4TlWo`, ключ — `Full Name`; создаёт и обновляет (`updateDuplicateRows: true`) |

---

## 3. Targeting Rules (`t_0ti6a5ieGgfnj3TohR3`) — 0 строк
Lookup-матрица ICP-вердикта: `Company type`, `Headcount group`, `Person type`, `Look Up` (ключ джойна), `Verdict`.
Заполняется вручную; сейчас пустая → любой лукап из конвейера возвращает `null`.

## 4. Fixed Data (`t_0ti6a5iMR2WbYVvkMux`) — 0 строк
Ручные override'ы: `Deduplication Column` (ключ), `Enriched LI URL`, `CORRECT LINKEDIN PROFILE`, `First/Last Name For Using`, `Full Name`, `Company Name Input`.
Сейчас пустая → override-ветка waterfall'а (кол. 38) всегда проваливается дальше, что безвредно.

---

## Что нашлось по ходу разбора (проверено на данных, не догадки)

1. **ICP-вердикт мёртв в обе стороны.** Категоризаторы (кол. 68 Company Category, 70 Current Job Title & Summary, 71 Category) в проверенных строках **никогда не запускались** (`status: empty`), поэтому `Look Up` вырождается в один `Employee Range` (`"1000+"`, `"101--500"`), `Has All Fields?` = `false`, и `Verdict` = `null` во всех проверенных строках. Плюс сама **Targeting Rules пуста (0 строк)** — даже полный ключ ничего бы не нашёл.
2. **Smartlead-лейны не отрабатывали.** Кол. 65 (`3686187`, valids) и 66 (`3756410`, catch-alls) — `empty` во всех проверенных строках, включая строку с `Email Status = Deliverable`, которая проходит их run-условие. Живой лейн — **HeyReach `512995`** (кол. 85, `✅ Lead updated`).
3. **HeyReach-диспатч ничем не защищён на уровне таблицы.** У кол. 85/86 **нет** run-условия и **нет** гейта на `Should Remove?`, DNC или `Final Score`. Единственная защита — ручной флаг `Are we adding to Linkedin?` и запуск колонки на отфильтрованном вью. Ошибка фильтра = отправка в suppression-список.
4. **`Email DNC` (кол. 67) не участвует в `Should Remove?`** — email-DNC считается, но на исключение лида не влияет.
5. **`Lead Assignment for Smartlead` (кол. 88) — `Math.random()`.** Любой пересчёт колонки переназначит владельца (Mario↔Rune). При этом ни к одному action-входу она не привязана — значение читается только глазами/снаружи.
6. **Промпты follow-up'ов ссылаются на чужие мероприятия.** В кол. 47 (`MASTER MESSAGING`) пользовательский промпт говорит «ahead of the The AI Summit NYC (NOT NVIDIA GTC or BUILD…)», а `systemPrompt` той же колонки — «we were attending **NVIDIA GTC**». Кол. 51 (`Prompt 4`) целиком про NVIDIA GTC. AI4 2026 не упомянут нигде, хотя воркбук — AI4.
7. **`Remove Based on LI DNC Check?` (кол. 31) ORит один и тот же LinkedIn DNC дважды** (копипаст: обе половины формулы — `f_0t3j0r9Cz3K8reDucdy`), а её `prompt` описывает Person/Company DNC. Функционально не теряем ничего — Person/Company DNC покрыты кол. 30 — но формула не делает то, что описано.
8. **Ошибки `Missing input` на Person/LinkedIn DNC — это пустой вход, а не поломка.** В строках без разрезолвленного LI-URL лукапы падают; там, где URL есть, лукап отвечает `❌ No Record Found`. Таблица `t_0ti6a5ifBrwkAWiYZYX` не читается через `clay tables get`, но её лукап рабочий.
9. **Дубли-заглушки:** кол. 39 `Company focus (2)` дублирует 38; кол. 54 `New Prompt 3` — незаполненный шаблон («Add Your Prompt Here.»); в кол. 60 `Job Title Qualification` промпт начинается с артефакта «Add prompt here.».
10. **Скоринг в follow-up-таблице:** `FINAL SCORE` (кол. 21) = среднее только колонок 18 и 19; третий скоринг (кол. 20, `Prompt 4 Extracted Score`) считается, но в среднее не входит.

## Границы проверки

- `clay tables rows list` отдаёт строки в порядке создания. Проверены два срезa (первые 3 строки и 4 строки с фильтром `Are we adding to Linkedin? = Yes`) — все из партии `7.14.2026`. **Fill rate по всем 13 464 строкам не измерен**; выводы №1 и №2 верны для проверенных строк, но по всей таблице требуют полного прохода.
- `queryEnabled: false` на всех таблицах воркбука → агрегаты через `clay tables query-live` недоступны без включения query-sync.
- Фильтр по boolean-колонке (`Picked by Melisa = true`) CLI отклонил; срез по отбору Melisa не проверен.

## Как повторить выгрузку

```bash
wsl -e bash -lc 'clay whoami && clay tables list --limit 100 --filter workbook.id=wb_0ti6a5icZRyKYfCJm2b'
```

Для каждой таблицы: `clay tables get <id>`, `clay tables columns get <id>` (полные settings: formulaText / formulaPrompt / inputsBinding / conditionalRunFormulaText / formulaWaterfall / authAccountId), `clay tables rows list <id> --limit N`.

**Важно:** CLI держит один профиль (`profiles.default`). Сейчас он на workspace **332169** (Sergey Cujba); чтобы вернуться к **{{OTHER_WORKSPACE}}** (Mykyta, {{N}} таблиц), нужен повторный `clay login` с выбором того воркспейса на consent-экране.
