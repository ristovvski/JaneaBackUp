# REGISTRY COMPLIANCE AUDIT vs Melisa's rule

Дата: 2026-08-26
Запрос: полная сверка ВСЕХ активных строк реестра против правила Мелисы (replied + meetings +
sales-created/Surfe + employee_connections + explicit opt-outs, БОЛЬШЕ НИЧЕГО). Read-only.

## Done
- Полное распределение по (entry_type, reason) — 9 комбинаций покрывают ВСЕ 32976 активных
  строк без остатка (проверено суммой):
  - COMPLIANT (25490): employee_connection/manual_offboard_eligible (24201), negative_reply/
    reply_dnc (817), negative_reply/meeting_dnc (179), replied/meeting_dnc (170),
    explicit_opt_out/client (95), employee_connection/sales_personal_outreach (15),
    manual/sales_personal_outreach (13).
  - NON-COMPLIANT (7486): manual/event_contacted (7138 — уже известный S4), manual/manual_sheet
    (348 — новая находка, тот же сид-импорт 2026-08-07, `onboarding_import:people_dnc_csv`/
    `onboarding_import:Pipedrive`, ноль reply-evidence, ноль also_flagged сигналов).
- **Set containment проверен**: множество S4 (manual/event_contacted) из этого прогона — те же
  7138, что и в отдельном S4-recon (совпадение по count, оба посчитаны той же логикой на тех же
  живых данных без записи между прогонами — консистентно by construction).
- **КРУПНАЯ находка, требует явного подтверждения**: `employee_connection/
  manual_offboard_eligible` = **24 201 строка, 73% всего реестра**. Название reason звучит
  тревожно ("eligible for offboarding"), но реальные данные говорят другое: ВСЕ из
  `seed_2026-08-11:people_dnc_pass1` (тот же самый bulk-импорт 2026-08-07), `source =
  onboarding_import:<имя сейлза>` (Jim 8365, Toby 4116, Mario 2404, Noah Keimach 2159, Rune
  1801, Mario Stalder 1546, Matt Carothers 1459, Benedetto 1361, Mike CEO 671, Sergey Cujba
  169, + мельче), **`owner_tag` У КАЖДОЙ строки уже проставлен на то же имя сейлза** — это
  выглядит РОВНО как настоящие personal/employee connections по каждому сейлзу, не мусор.
  Классифицировано COMPLIANT по буквальному правилу (employee_connection — именованная
  защищённая категория), но флагую явно, не молчком — масштаб и название reason требуют
  прямого "да, это ок" от Ника/Мелисы, а не моего единоличного решения.
- Проверены 348 manual_sheet строк на скрытые reply-сигналы — ничего не нашлось, тот же
  бесследный CSV-импорт, честно NON-COMPLIANT.
- Артефакт: `fixtures/compliance_audit_manifest.json`.
- Переиспользуется уже готовый + протестированный `dnc_s4_retirement_removal` (dry_run по
  умолчанию true, tombstone, тот же removed_reason tag) — единый батч теперь 7486 (не 7138),
  воркфлоу не требует изменений (row_ids-агностичен).

## Дополнение: FIRED, Nik's GO 2026-08-26 (тот же день)

- **Комбинированный батч 7486 (7138 S4 + 348 manual_sheet) — выпущен**, чанками по 500 через
  `dnc_s4_retirement_removal` (`dry_run:false`), все 16 чанков подтверждены `WRITTEN`, итог
  `TOTAL PROCESSED: 7486` = ожидаемому.
- **Post-verify, независимый пересчёт**: `total_active` реестра теперь **25490** — ТОЧНО
  совпадает с предсказанным `total_compliant` из аудита. `total_empty_owner_tag` упал с 8775 до
  1289 (разница 7486 — ровно снятые строки, ни одной лишней).
- **Field-686 очищен** на Miguel Martín (Pipedrive person 70877) — единственный человек из всей
  партии с реально спроецированным DNC-флагом; было "686", подтверждено `None` после записи.
  Перед записью отдельно проверено: 0 активных строк осталось на этот `pipedrive_person_id`.
- **`dnc_s4_event_populations` деактивирован**, подтверждено `active: False` — популяция S4
  больше не может писать новые event_contacted-only строки.
- **employee_connection/manual_offboard_eligible (24201) — RULING-CONFIRMED**: "all connections
  are in DNC" (Мелиса, 2026-08-26) — не тронут, финально COMPLIANT. Записано в
  `fixtures/compliance_audit_manifest.json` (`employee_connection_ruling_confirmed`) и в
  `COMMS_AUDIT_build/synthesis/03_RULEBOOK_MAP.md` (раздел P6, датированное дополнение с прямой
  цитатой rationale).
- Финальное определение DNC зафиксировано в rulebook: *replied + meetings + sales-created/Surfe
  + ALL imported connections + explicit opt-outs. Nothing contact-only.*
- Clay delta-push: ожидается подхватит удаления на своём обычном цикле синхронизации — отдельно
  не форсировал (нет известного мне ручного триггера под это), скажи если нужно проверить явно.

## Blocked — ждёт слова Ника
- Комбинированный fire 7486 tombstone-записей (не только 7138 S4).
- **Явное подтверждение по employee_connection/manual_offboard_eligible (24201, 73% реестра)**
  — самое дорогое решение во всём аудите, не тронуто до прямого ответа.
- "116 Amsterdam remnant (72 unresolvable)" — упомянутая когорта НЕ найдена в текущем разрезе
  (entry_type,reason); похоже относится к отдельной, ещё не законченной задаче ARCHIVED
  RESPONDERS (были прерваны на этапе поиска "трёх routes"), не к этому реестровому срезу.
  Продолжу отдельно.

## Improvable
- Ничего не тронуто без прямого слова — весь аудит read-only.
