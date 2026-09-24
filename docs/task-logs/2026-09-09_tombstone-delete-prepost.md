# DELETE the 26-Aug tombstones — read-only pre-post, waiting for Nik's word

Дата: 2026-09-09. Ничего не удалено — export + investigation only.

## Done
- Scope investigated: expected 7,486, found 7,450 (status=removed AND removed_reason=
  rule_change_2026-08-26_melisa). **36-row gap fully explained, not forced**: reconstructed the
  exact original 7,486-id list from saved fixtures, checked every id directly against the live
  registry — 7,450 still tombstoned + 36 legitimately reactivated (all trace to my own 2026-08-28
  archived-responders fire + 1 wf1_reply event on 2026-09-06) + 0 missing + 0 removed-under-a-
  different-tag. Confirmed via `merge_v1.js`'s live code: a new DNC event for an already-tombstoned
  identity reactivates the SAME row in place (`reactivate = primary.status !== 'active'`), which is
  exactly correct behavior per Melisa's rule, not a bug.
- Other removed rows NOT in scope, counted and reported separately: 2 total (`merged_into:23840`,
  and an 18-Aug team ruling protecting a no-show-meeting person from DNC).
- Full export done BEFORE any deletion: `audit-artifacts/dnc_registry_tombstones_2026-08-26_melisa_EXPORT_2026-09-09.csv`
  + `.json`, 7,450 rows, every column.
- Sweep done: confirmed live that `DNC__UpsertLedger__v1`'s identity lookups don't filter by
  status (removed rows ARE read as merge candidates today); confirmed the gate's "was X until Y"
  wording depends on removed rows existing (loses that historical footnote post-delete, verdict
  itself unaffected); confirmed Clay's future delta pusher is moot here (active-only by design).
- Full artifact: `TOMBSTONE_DELETE_build/ARTIFACT_prefire.md`.

## Дополнение: FIRED, Nik's "if artefact is present — go" 2026-09-09

- Построен `dnc_tombstone_hard_delete` — первый настоящий HARD DELETE в этом проекте (все прежние
  "removal" были tombstone SET, не deleteRows). Каждый id перепроверяется live (status=removed AND
  правильный removed_reason) НЕПОСРЕДСТВЕННО перед удалением — не доверяя только заранее
  посчитанному списку, т.к. между расчётом и выстрелом могло что-то измениться. dry_run по
  умолчанию true.
- Найден и исправлен реальный баг ДО прод-выстрела: `$input.all()` запрещён в
  `runOnceForEachItem`-ноде — поймано на dry-run тесте 5 строк, не на полном батче.
- Тест на 5 реальных строках (dry-run → live delete → прямая проверка отсутствия) прошёл чисто
  ПЕРЕД полным батчем.
- **Выпущено**: 7,445 оставшихся id (7,450 минус 5 из теста), чанками по 500, `TOTAL PROCESSED:
  7445 = ожидаемому`, 0 skipped (ни одна строка не успела реактивироваться между расчётом списка и
  выстрелом).
- **Post-verify (независимый пересчёт)**: `still_matching_target_filter: 0` — ни одна строка
  больше не соответствует фильтру удаления. `total_removed: 2` — ровно те 2 строки, что и должны
  были остаться (merged_into:23840 + 18-Aug team ruling), НИЧЕГО лишнего не тронуто. `total_active`
  25,686→25,687 (+1) — это ОБЫЧНАЯ живая активность в промежутке между scope-проверкой и
  выстрелом (S1/WF1 и т.п. продолжают писать в реестр), НЕ побочный эффект удаления — доказано тем,
  что delete физически трогает только status=removed строки, и total_removed корректно упал ровно
  до 2.

## Improvable
- Ничего не тронуто без подтверждения на каждом шаге — dry-run перед live на каждом уровне
  (5-строчный тест, затем полный батч).
