# Пример на одном лиде: что тратится сейчас и что тратилось бы после

Строка `r_0ti6adz2Z84KgiqiNAu` из `Speakers & Attendees Enrichment` (`t_0ti6a626jog6NWTPTuM`), партия `7.14.2026`.
Все значения ниже — фактические из выгрузки, не пример «на пальцах».

```
First Name   : Abhino
Last Name    : Dagar
Title Input  : Senior HRIS Manager
Type         : attendee
```

Итог по строке: `Remove Based on Title? = true` → `Should Remove? = true` → `Final Score = 0` → ни в одну кампанию не ушла.
**Решение о выбросе принято чистой формулой по полю, которое было на входе. Ноль платных вызовов нужно, чтобы это узнать.**

---

## Сейчас: строка выброшена, но 12 action-колонок успели дать результат

| Отработало с результатом | Что это стоит |
|---|---|
| `Name Normalization` | AI, gpt-4o-mini |
| `Normalize Company Name` | встроенный экшен |
| `Normalized Company Name` | AI, gpt-4o-mini |
| `Find Company Domain` | **Claygent**, gpt-4o-mini |
| `Normalize a Domain` | утилита |
| `Company DNC` | lookup |
| `Competitor Status` | **AI, gpt-4o**, runBudget 1 |
| `Find LinkedIn Profile URL` | **Claygent, gpt-5.4-mini** — веб-ресёрч |
| `Scrape Website` | **скрейп с premium proxy** |
| `Job Title Qualification` | AI, gpt-4o-mini |
| `Company Qualification Prompt` | AI, gpt-4o-mini |
| `Check Fixed URLs` | lookup |

Что честно **не** тратилось: весь email-каскад (`Find Work Email` ×3 и три валидации) и `Enrich Company` —
у них в `Only run if` стоит тот же стоп-лист, они вернули `success` с пустым значением. То есть email-лейн защищён.

**Не защищено всё остальное.** Claygent на поиск LinkedIn, скрейп сайта, gpt-4o на детект конкурента и два AI-скоринга
отработали на строке, которую бесплатная формула уже приговорила.

Для сравнения — строка `r_0ti6adz2bHB2KBuVWoY`, которая прошла (`Final Score 7.5`, ушла в HeyReach): 22 колонки с результатом.
Разница между «выбросили» и «отправили в кампанию» — всего 10 колонок. Отсев почти ничего не экономит.

---

## Почему `Should Remove?` нельзя просто поставить гейтом вперёд

```
Should Remove? = Remove Based on Title?          ← формула по Title           (бесплатно)
              || Remove Based on Email Domain?   ← формула по email           (бесплатно)
              || Remove Based on DNC Check?      ← lookup по ОБОГАЩЁННОМУ LI  (нужен резолв)
              || Remove Based on LI DNC Check?   ← lookup по ОБОГАЩЁННОМУ LI  (нужен резолв)
              || Extracted Competitor Status     ← AI gpt-4o по скрейпу       (платно)
```

Три из пяти слагаемых сами зависят от дорогих шагов — поставить эту колонку условием для тех же шагов нельзя, это цикл.
Поэтому гейт надо **расщепить на бесплатный и платный**.

---

## После: одна новая колонка и условие на девяти существующих

### Шаг 1. Новая формульная колонка `Kill — free` (0 кредитов)

```js
(() => {
  const t = " " + ({{Title}} || "").toLowerCase().replace(/[^a-z0-9]+/g, " ") + " ";
  const stop = ["content creator","retired","student","unemployed","professor","journalist","reporter",
    "photographer","recruiter","hr","human resources","business development","sales","host",
    "employee experience","event lead","video editor","junior","intern","events coordinator",
    "account manager","customer success","researcher","recruitment","publisher","correspondent",
    "editor-in-chief","legal","marketing specialist","customer success manager","channel manager",
    "bdr","sdr","bdm","tax lead","legal counsel","content editor","ux designer","public speaking coach",
    "phd candidate","key account manager","customer support","market researcher","assistant",
    "service desk technician","office manager","seo manager","seo specialist","pr manager","qa tester",
    "automation tester","content marketeer","auditor","business developer","user experience expert",
    "senior client manager"];
  const badTitle = stop.some(k => t.includes(" " + k + " "));
  const badDomain = [".edu",".gov",".org"].some(x => ({{Domain}} || "").toLowerCase().includes(x));
  return badTitle || badDomain;
})()
```

Отличие от текущей `Remove Based on Title?` — одно: сопоставление **по словам, а не по подстроке**.
Текущая версия матчит `includes(keyword)` по сырой строке, и `"hr"` попадает внутрь слов. Проверено на реальном списке из 56 слов:

| Должность | Сейчас | Почему | После |
|---|---|---|---|
| Senior HRIS Manager | **KILL** | `hr` внутри `HRIS` | keep |
| Threat Intelligence Manager | **KILL** | `hr` внутри `Threat` | keep |
| Head of Threat Detection | **KILL** | `hr` внутри `Threat` | keep |
| Christopher Lead Architect | **KILL** | `hr` внутри `Christopher` | keep |
| Head of Thriving Communities | **KILL** | `hr` внутри `Thriving` | keep |
| Machine Learning Researcher | **KILL** | `researcher` | KILL (осознанно, слово целое) |
| VP Engineering / Solutions Architect / SRE | keep | — | keep |

То есть текущий гейт **режет security- и engineering-должности из-за подстроки `hr`**. Это не экономия, это потеря ICP.
Если HRIS действительно не нужен — добавить `"hris"` в список словом, а не ловить случайно.

### Шаг 2. На девять дорогих колонок повесить `Only run if`

```
!{{Kill — free}}
```

Колонки: `Name Normalization`, `Normalized Company Name`, `Find Company Name`, `Find Company Domain`,
`Competitor Status`, `Find LinkedIn Profile URL`, `Scrape Website`, `Job Title Qualification`, `Company Qualification Prompt`.

### Результат на этой же строке

| | Сейчас | После |
|---|---|---|
| Формул до решения | 1 | 1 |
| Action-колонок с результатом | **12** | **0** |
| Claygent-вызовов | 2 | 0 |
| Скрейпов | 1 | 0 |
| AI-вызовов (вкл. gpt-4o) | 5 | 0 |
| Итог по лиду | выброшен | выброшен |

Тот же результат, ни одного платного вызова. Провайдеры не меняются, порядок колонок в таблице не меняется —
добавляется одна формула и девять галок `Only run if`.

---

## Что здесь проверяемо, а что нет

- Поведение формул, каскада и пустых значений — подтверждено zero-credit sandbox'ом (`CLAY_C3A_SANDBOX_RESULTS.md`).
- Стоп-лист по словам против подстроки — проверено прогоном реального списка из 56 слов по 16 должностям (таблица выше).
- Что `Only run if = false` действительно **не списывает** кредит — **не доказано**: это пункт `C3B-01` очереди
  платной валидации, ничего из неё не запускалось. Хорошая новость: email-лейн в этой же таблице ведёт себя именно так
  (`success` + пустое значение, провайдер не вызван), то есть механизм на нашей таблице наблюдаем. Но это наблюдение,
  а не измерение — счётчик кредитов я не смотрел.

Первый шаг: включить это на копии таблицы, 20 строк, и сверить счётчик кредитов до/после. Дальше — по фазам из `redesign-proposal.md`.
