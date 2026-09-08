# ARCHIVED RESPONDERS — §9f.2 pre-fire artifact

Дата: 2026-08-28. Источник: `leads-16340280-282.csv` (Melisa's Pipedrive export), скопирован в
`ARCHIVED_RESPONDERS_build/leads-16340280-282.csv`. Read-only до этого момента — ничего не
записано в реестр.

## 1. INGEST

- Распарсено (Python `csv.DictReader`, не `wc -l`): **324 строки данных** — точное совпадение с
  ожидаемыми ~324 Мелисы. Не форсировал, не нужно — совпало ровно.

## 2. Исключены: внутренние тест/QA-записи (7)

Найдены по признаку в СОБСТВЕННЫХ полях персоны (имя/компания), не по названию кампании — первая
версия фильтра по кампании ошибочно ловила 3 РЕАЛЬНЫХ человек (см. ниже), исправлено.

| Lead Title | Почему исключён |
|---|---|
| ZZ FLIP-GATE TEST (do not distribute) ×2 | собственное имя персоны = тестовый маркер, email = личный тестовый адрес (WF-2R flip-gate probe) |
| Person-5e07d3f5 — Test Company Name ×2 | классическое имя-плейсхолдер + email @test.com + компания "Test Company Name" |
| Person-7641cf62 — HR Test Company | имя-плейсхолдер, ноль остальных полей |
| Person-7641cf62 2 — HR Test Company | то же |
| Person-7641cf62 3 — HR Test Company | то же |

**Важно — 3 строки НЕ исключены**, хотя название кампании содержит "TEST" (Final TEST / TEST2):
Kamil Jałowiec (sunbay.io, реальный LinkedIn-профиль), Evamarija Batkoska (OutboundLeads, реальный
профиль), Lule Salihu (реальный LinkedIn-профиль). Проверено вручную через живой HeyReach-вызов —
у всех троих реальные ответы в переписке (напр. Kamil ответил "Hi"). Кампания была internal-named
"TEST", но отправлена реальным людям.

## 3. Классификация (317 реальных кандидатов)

| Bucket | Count | Механизм |
|---|---:|---|
| **explicit_opt_out** | **10** | CSV label `DO NOT CONTACT` — единственный АВТОМАТИЧЕСКИЙ путь, без интерпретации |
| **reply_dnc** (чистые) | **265** | ответ прочитан живьём (Smartlead/HeyReach), явного stop-language не найдено |
| reply_dnc + possible_opt_out flag | 10 | ответ содержит фразу из списка stop-language, но НЕ повышен автоматически (см. §4) |
| reply_dnc + unreadable (human_review) | 31 | HeyReach "lead not found" — архивный лид не в активном списке, текст ответа недоступен |
| reply_dnc + no identifier (human_review) | 1 | Lule Salihu, дубликат-строка без email/LinkedIn (см. §5) |

**Итог: opt_out 10 + reply_dnc 307 = 317.** Ничего не додумано молча.

### Найденный и исправленный баг (важно для доверия к цифрам)

Первый прогон живого чтения реплаев дал **45** "opt_out" через фразовый поиск в тексте ответа.
Ручная проверка нашла: большинство матчей были НЕ словами лида, а НАШЕЙ СОБСТВЕННОЙ courtesy-
формулировкой ("if you'd prefer not to be contacted further...") из quoted-цепочки письма,
попавшей в тело ответа при top-posting. Тройная правка (усечение по quote-маркеру: EN "On...wrote:"
→ 45→29, затем DE "Von:"/"Gesendet:" + FR "De :"/"Envoyé :" → 29→19→12→**10**) сузила список до
десяти. Финальное решение: **ни один фразовый матч не повышается автоматически** — только CSV-label
`DO NOT CONTACT` даёт автоматический opt_out. Все 10 оставшихся матчей идут явным списком ниже для
твоего/Мелисиного решения.

## 4. 10 possible_opt_out — мой разбор, финальное решение за вами

**Вероятно ГЕНУИННЫЕ (6)** — фраза в собственных, полных, короткого письма словах человека, без
quote-контаминации:
| Person | Email | Цитата |
|---|---|---|
| Miguel Martín | pii-6606599f@example.invalid | "unsubscribe, please >" |
| Person-ce02caf6 | pii-938681e3@example.invalid | "Sorry, I'm not interested. Please take me off your list." |
| James Ding | pii-a4809ea4@example.invalid | "Please unsubscribe me from your email campaign." |
| Person-92ee42c2 | pii-fcf5853b@example.invalid | "Unsubscribe" |
| Person-26fc20bc | pii-b60c4a6a@example.invalid | "...I would rather like exclude myself from this network." |
| Person-fc62ec56 | pii-90d1f9df@example.invalid | "...please refrain from sending any further inquiries." |

**Вероятно ЛОЖНОЕ СРАБАТЫВАНИЕ (4)** — видимый текст ответа обычный вежливый отказ ("not
interested"/"not relevant"), триггер-фраза не видна в показанных 300 символах → скорее всего
остаточная quote-контаминация в неучтённом формате (не английский/немецкий/французский маркер):
Person-9460fa71, Person-282ef33e, Person-3cbd793b, Person-9b0d4295.

**Рекомендация**: принять 6 генуинных как explicit_opt_out при выстреле, оставить 4 сомнительных
как reply_dnc (безопасный дефолт) — но финальное слово за тобой/Мелисой, ничего не двинется без
подтверждения.

## 5. IDENTITY — единственная нерешённая строка

**Lule Salihu** (Lead created 2026-07-14 12:14:54, label "3. Responded") — пустые все поля кроме
заголовка. **Есть ДРУГАЯ строка "Lule Salihu"** в этом же экспорте (campaign "TEST2", реальный
LinkedIn `lule-salihu-245b7a171`, создана в тот же день на 5 часов раньше) — почти наверняка тот же
человек, более ранняя/неполная Pipedrive-запись. **Не смёржено автоматически** (правило: не
угадывать по имени) — эта пустая строка пойдёт в honest unmatched/enrichment pool; вторая (с
LinkedIn) уже входит в reply_dnc-307 нормально.

## 6. Примеры по 5 на bucket

**explicit_opt_out (label-based, все 10 — список короткий, показан полностью, не только 5):**
Person-6f447c29 (Netflix), Person-54dba3cb (Indurent), Person-2fb7cb16 (Tillo), Robert
Stonehouse (Olix), Person-06015cae (Kovo+), Person-cfc581b3 (Osmind), Person-a884b411 (LinkedIn-only),
Person-9947453a (Bellrock), Person-8e99f848 (Bradley), Oz Katz (Treeverse) — все carry the
literal `DO NOT CONTACT` label.

**reply_dnc, clean (5 examples):**
- Person-10c7a376 (MDPI) — "we do not outsource the development of our solutions" — plain decline.
- Alberto Sánchez Cebrián (Beyond Gravity) — "No need to get me involved" — plain decline.
- Kamil Jałowiec (sunbay.io) — "Hi" — minimal reply, real person (see §2 note).
- Person-b4374f0c (EPFL) — "I don't think that I am the person you are looking for."
- Person-1cf31dd9 (Bühler Group) — "not interested in extending the network at the moment."

**unreadable (5 examples, all HeyReach "lead not found"):**
Person-486d977b, Person-6b8b9479, Person-b0603c34, Person-62e065f7, César Andrade — all archived
LinkedIn leads no longer resolvable via `GetConversationsV3` by profile URL.

## Ждёт твоего слова

- Fire scope: 317 rows (10 auto opt_out + up to 6 more promotable opt_out pending your read of §4
  + remainder reply_dnc), via `DNC__UpsertLedger__v1` (standard merge — some already carry rows
  from other reasons, source/reason UNION per existing rules, no duplicates).
- 7 excluded test/QA rows: confirm these should NOT enter the registry (my read: correct to
  exclude, but flagging explicitly since 3 near-misses turned out to be real people).
- §4's 4 ambiguous rows: opt_out or stay reply_dnc — your call.
- Lule Salihu duplicate: leave as unmatched/enrichment-pool, or manually confirm it's the same
  person as the LinkedIn-bearing row and skip firing it as a separate identity?

Nothing fires until you say go.
