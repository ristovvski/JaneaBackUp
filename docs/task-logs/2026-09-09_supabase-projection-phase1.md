# SUPABASE PROJECTION — Phase 1 (files only)

Дата: 2026-09-09. Файлы only, ничего не подключалось к Supabase напрямую (нет credentials в
доступе — secret key живёт только в n8n, как и требовалось).

## Done

1. **Реальная структура таблицы дампнута живьём**, не по памяти: live read-only запрос против
   `dnc_registry_dev` (dataTableId `UOgKwlGsL28lX61O`), 33,138 строк (все — и active, и removed),
   union всех 26 реальных колонок + типы + null-counts. Артефакт:
   `SUPABASE_PROJECTION_build/registry_structure_probe.json`.
2. **`dnc_registry_phase1.sql`** — `CREATE TABLE dnc_registry` (identical field names, включая
   намеренно оставленный camelCase `"createdAt"`/`"updatedAt"` — это буквальные системные колонки
   n8n, не стилистическая правка), `UNIQUE` на `identity_key`, плюс `dnc_registry_meta` (append-
   log по каждому sync-прогону, не одна перезаписываемая строка). RLS: `ENABLE ROW LEVEL SECURITY`
   на обеих, ОДНА read-policy (anon+authenticated), явно НИКАКИХ insert/update/delete policy —
   пояснено, что secret key обходит RLS целиком (платформенное поведение Supabase, не то, что
   настраивает этот скрипт). Весь скрипт идемпотентен (безопасно вставить повторно) — добавил
   `DROP POLICY IF EXISTS` перед каждым `CREATE POLICY`, т.к. у Postgres нет `CREATE POLICY IF NOT
   EXISTS`.
3. **`identity_key` never blank — подтверждено, не предположено**: 0 пустых/null значений на всех
   33,138 строках, живой прямой запрос (НЕ через фильтр `isNotEmpty` на identity_key — это было бы
   самообманом, отфильтровал бы именно те строки, которые нужно проверить; использован `status
   isNotEmpty` как честный "дай всё" фильтр). Пограничный случай (ни email, ни LinkedIn) даёт
   `identity_key: null` в самом нормалайзере, но такая строка НИКОГДА не доходит до записи — это и
   объясняет, почему гарантия держится на живых данных.
4. **`NORMALIZATION_RULES.md`** — алгоритм по шагам + 5 примеров, каждый ПРОГНАН через реальную
   `normalizeIdentityV1` (Node, не ручная трассировка) перед тем как попасть в документ: грязный
   LinkedIn URL с query-string, percent-encoded slug, email с plus-tag (намеренно НЕ схлопывается),
   не-`/in/` LinkedIn URL (компания) → LinkedIn отбрасывается целиком, email становится единственным
   ключом, и граничный случай (оба поля пусты) → `identity_key: null`, никогда не доходит до
   таблицы.
5. **`README_STEFAN.md`** — имя таблицы, key column, как настроить Lookup в Clay, явное
   предупреждение про camelCase-колонки, и что publishable key чисто read-only (structural, не
   convention).

## Blocked / pending
- Phase 2 (initial load + delta pusher + nightly reconcile) — ждёт слова Ника, как и было указано.
  Таблицы после выполнения этого SQL будут существовать, но пустыми.

## Improvable
- `entry_type`/`reason`/`status`/`date_precision` намеренно НЕ CHECK-constrained в Postgres —
  n8n остаётся источником истины по допустимым значениям; жёсткий CHECK здесь рискует молча
  реджектить легитимное будущее значение при Phase 2 sync вместо того чтобы просто спроецировать
  его. Текущие наблюдаемые значения задокументированы в самом .sql как информационный комментарий.
- `expires_at` сейчас `null` на ВСЕХ 33,138 строках (живой факт на 2026-09-09, включая строки,
  где я лично видел непустой `expires_at` в предыдущей сессии 2026-08-28/31 — что-то очистило это
  поле между сессиями за прошедшие ~12 дней). Зафиксировано как наблюдаемый факт без домысливания
  причины (нет контекста за эти 12 дней в этой сессии) — не чинил, не расследовал, просто не дал
  этому факту исказить типизацию колонки (`timestamptz`, nullable, как и должно быть).
