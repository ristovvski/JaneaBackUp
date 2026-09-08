# S4 RETIREMENT — Melisa's ruling, prep complete, awaiting fire

Дата: 2026-08-26
Запрос: реестр оставляет только replied(S1) + meetings(S2) + sales-created/Surfe(S3) +
employee_connections + explicit opt-outs. Строки с ЕДИНСТВЕННОЙ активной причиной
event_contacted (S4) — убрать. Read-only до слова Ника.

## Done (recon + подготовка, ничего не записано)
- Классификация всех 32976 активных строк: `touched_by_s4 = 7138`, все 7138 — ЧИСТЫЙ S4
  (reason строго == "event_contacted", `overlap_count: 0` на уровне поля reason).
- **Проверка "Lucas pattern" (also_flagged)**: из 7138 только у ОДНОЙ строки вообще есть
  `also_flagged` (Miguel Martín, `manual_sheet` — не защищённая причина), у нуля — реальный
  защищённый сигнал (reply/meeting/creation). **В этой партии demote-кейсов физически нет** —
  весь список безопасен для полного tombstone. Сама defensive-логика (keep+demote при реальном
  overlap) всё равно стоит закладывать в write-path на будущее, просто СЕЙЧАС она не нужна ни
  одной строке.
- Реальное число (7138) заметно выше прикидки Ника (~6424 = "AI4 162 + sprints 6262") —
  сообщаю честно, не подгоняю под оценку. Разбивка по source_ref:
  - 2211 `[Sales Sprint] Sales Sprint 2026 - London - Valids`
  - 1842 `[Sales Sprint] Sales Sprint 2026 - London - Catch-alls`
  - 859 `Ai4 2026` (без sender — старые Smartlead campaign_name без парсинга)
  - 618 `Ai4 2026 - Rune - LinkedIn`
  - 565 `Ai4 2026 - Mario - LinkedIn`
  - 459 `[Sales Sprint] Sales Sprint London`
  - 354 `[Sales Sprint] European Sales Sprint 2025 - Catch-all`
  - 183 `[Sales Sprint] Sales Sprint 2026 - Switzerland`
  - 27 `[Sales Sprint] European Sales Sprint 2026 - Munich and Berlin`
  - 20 `[Sales Sprint] European Sales Sprint 2025 - Valids`
- **Field-686 clearing**: всего ОДИН человек (`pid=70877`, Miguel Martín) из всех 7138 несёт
  `pipedrive_person_id` — остальные 7137 строк были захвачены БЕЗ сматченного Pipedrive-персона
  (`pipedrive_person_id: null`), т.е. 686 для них никогда и не проецировался. Реальная зачистка
  686 — тривиальная, один человек, не массовая операция.
- **Написан + задеплоен (АКТИВЕН, но write-путь заблокирован) `dnc_s4_retirement_removal`**:
  webhook принимает `{row_ids: [...], dry_run}`; `dry_run` по умолчанию `true` — запись требует
  ЯВНОГО `dry_run:false`; tombstone (`status:removed`, `removed_reason:
  rule_change_2026-08-26_melisa`), НИКОГДА `deleteRows`. Живой dry-run тест на 3 реальных id —
  0 записей, подтверждено. 104/104 статических теста (7 новых на этот воркфлоу).
- Артефакт: `fixtures/s4_retirement_manifest.json` (полный список 7138 id + rationale-цитата
  Мелисы + removed_reason tag), `fixtures/s4_retirement_recon.json`,
  `fixtures/s4_686_clear_candidates.json`.

## Blocked — ждёт слова Ника
- **Сам fire** (7138 tombstone-записей, чанками через `dnc_s4_retirement_removal` с
  `dry_run:false`).
- **Field-686 clear** для Miguel Martín (Pipedrive person 70877).
- **Деактивация `dnc_s4_event_populations`** (сейчас `active: True`) — сделаю ОДНОВРЕМЕННО с
  fire, не раньше (чтобы вся операция была одним подтверждённым действием, не растянутой
  частично-сделанной).
- **Отмена запланированного S4 auto-discovery** (был в работе как часть отдельной задачи
  "Event Naming + S4" до этого разворота) — код НЕ был написан на момент разворота, отменять
  нечего технически, просто задача снята.
- Rulebook/G-05 текст под точную формулировку Мелисы — черновик готов набросать, финализирую
  после fire.

## Improvable
- `Ai4 2026` (859 строк, без sender) — источник Smartlead `campaign_name`, который был ПРОСТО
  event-меткой без sender (не путать с реальным campaign-name с брекетами) — после ретиремента
  это уже не важно для DNC, но если Мелиса всё ещё хочет sender-атрибуцию в Pipedrive Event Name
  поле для аналитики (упомянуто в её же формулировке п.4 "keep the event attribution... just not
  as DNC") — это ОТДЕЛЬНАЯ, более мелкая задача, не начата.
