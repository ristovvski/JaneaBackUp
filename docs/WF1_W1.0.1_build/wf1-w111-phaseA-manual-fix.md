# W1.0.11 — Phase A: manual-fix list (Ai4 2026 touches that landed on OLD leads)

**Read-only scan, 2026-07-19.** Campaigns "Ai4 2026 - Mario - LinkedIn" + "Ai4 2026 - Rune - LinkedIn". Found **7 events across 3 persons** where an Ai4-2026 accepted/reply landed on a lead **created before 2026-07-18** (pre-existing / prior-campaign leads). These predate the W1.0.11 lead-per-campaign fix and are for **Slava to untangle manually** — WF-1 makes NO changes here. (All 7 were the "…Mario…" campaign; no "…Rune…" old-lead landings in the scanned window.)

> Requested output path `/mnt/user-data/outputs/` is not mountable in this Windows environment — file written to the project build dir instead: `WF1_W1.0.1_build/wf1-w111-phaseA-manual-fix.md`.

## 1. Person-1627ef6a — person `51678`  ⟵ the live-case lead
**Old lead:** `54106a70-72e3-11f0-93f6-71cd9a375326` — *"2342850 - [Events Visiting] AI4 **2025** - Catch-alls - Person-1627ef6a"* (created **2025-08-06**). Labels now: `[cold, connected, responded]`.
[Open lead](https://janeasystems.pipedrive.com/leads/inbox/54106a70-72e3-11f0-93f6-71cd9a375326)
| exec | when (UTC) | event | landed |
|---|---|---|---|
| 10234 | 2026-07-18 18:11:44 | reply | stage→**Replied to invite**; reply activity note: `"Hey, Mario\nIt's nice to hear from you"` |
| 10235 | 2026-07-18 18:11:45 | accepted | M5 lead patch (labels/connected) |
| 10244 | 2026-07-18 18:14:52 | reply | stage→**Replied**; reply activity note: `"Will try to meet you during Ai4 conference"` |

## 2. Person-e77d99ff — person `51045`
**Old lead:** `639bbf70-7235-11f0-8741-ffeaa340476d` — *"2342830 - [Events Visiting] AI4 **2026** - Valids - Person-e77d99ff"* (created **2025-08-05**). Labels now: `[cold, connected]`.
[Open lead](https://janeasystems.pipedrive.com/leads/inbox/639bbf70-7235-11f0-8741-ffeaa340476d)
| exec | when (UTC) | event | landed |
|---|---|---|---|
| 10275 | 2026-07-18 23:22:30 | accepted | M5 lead patch (labels/connected) |
| 10276 | 2026-07-18 23:22:30 | reply | stage→**Replied to invite**; reply activity note: `"Yes"` |

## 3. Person-84df1b50 — person `64531`
**Old lead:** `cf8e32b0-fd4c-11f0-9f03-8db5b47de0f4` — *"2876818 - [Trigger-based Campaign] Newly Hired Heads of AI - Person-84df1b50"* (created **2026-01-29**). Labels now: `[cold, connected]`.
[Open lead](https://janeasystems.pipedrive.com/leads/inbox/cf8e32b0-fd4c-11f0-9f03-8db5b47de0f4)
| exec | when (UTC) | event | landed |
|---|---|---|---|
| 10372 | 2026-07-19 17:10:48 | reply | stage→**Replied to invite**; reply activity note: `"Thanks Mario\nPlease could you email my agent? …/posts/…ai4…"` |
| 10374 | 2026-07-19 17:10:49 | accepted | M5 lead patch (labels/connected) |

## Impact / what Slava needs to decide per person
For each: the Ai4-2026 touch (stage advance + labels + reply activity) sits on the **wrong (old-campaign) lead**, so Melisa's "Ai4 2026" report (title/Campaign-field filter) won't count it and the old campaign's numbers are inflated. Options per person (Slava's call — WF-1 won't auto-move): (a) create the correct Ai4-2026 lead and move the reply activity + `responded`/stage onto it, or (b) leave as-is if the person genuinely belongs to that prior campaign. Persons are NOT duplicated; only lead attribution is in question. After W1.0.11 + the Ai4 backfill, **future** events for these persons will attach to the correct campaign lead.
