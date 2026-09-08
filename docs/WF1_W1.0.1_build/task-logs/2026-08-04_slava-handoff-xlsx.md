# 2026-08-04 — Slava handoff package: mis_attached_leads.csv -> operator xlsx

Rework the 100-row `mis_attached_leads.csv` (leads Make attached to the wrong person by name-match)
into one WhatsApp-attachable xlsx that a non-technical operator can work top to bottom.
**Read-only against Pipedrive** — the fixes are Slava's manual queue by Melisa's decision.

Deliverable:
`wf1-release-evidence/slava-handoff-2026-08-04/SLAVA_wrong_person_queue.xlsx`
(+ `..._TWIN.csv`, the same 58 rows in readable form — see *blocked* below)

## done

- **Live recheck, read-only** (`GET` only, no write path in any script):
  100 × `/v1/leads/{uuid}`, 60 × `/v1/persons/{id}`, 58 × `/v1/persons/search?fields=email&exact_match=true`.
  - 100/100 leads still exist, and **every title still matches the report exactly** → every link in
    the sheet opens the intended lead.
  - **0 rows hand-fixed** since the report (no lead has moved to another person) → the sheet has no
    DONE section; the code path for it exists and sorts DONE to the bottom if that changes.
  - **0 of 58** contacted addresses has a person in Pipedrive yet.
- Collapsed 100 lead-rows → **58 contacts**, one row each; a contact's 2–4 leads are 2–4 clickable
  columns (`Open the lead`, `Open lead 2..4`). All 100 leads remain reachable from the sheet.
- Taxonomy frozen to `RE-POINT | MERGE | NO-EMAIL-CHECK | REVIEW` (+ `DONE`), recomputed from the
  live snapshot rather than copied from `suggested_action`. Final: **17 / 5 / 22 / 14**.
- Company + job title per prospect pulled from Smartlead (`GET /leads?email=`) — 58/58 hit — so
  `Company` names a real company instead of an email domain. Placeholder `"your company"` (Peter
  Day, Person-55be653b) falls back to the domain.
- Second sheet "Как работать": what happened, what each ACTION means, and the backfill warning.

## findings worth keeping

- **All 58 contacts are inside the 300-row `ai4_missing_persons.jsonl` backfill** (overlap 58/58).
  So the "правильная персона" Slava is told to create is one the backfill (Part A) will create
  itself → **duplicate risk**, and the handoff text's "создай персону" collides with its own
  "300 не создавай руками". Sequencing is Melisa/Nik's call; every note says *search by email
  first*.
- The original CSV's own counts read as contacts but were **lead-rows** (~40/~10/~30/~20).
- **3 rows were mislabelled "different person entirely"** — the attached record sits at the very
  company we emailed, so it is far more likely one human with two addresses. Downgraded to REVIEW:
  Person-0f138f6a (`pii-b3826389@example.invalid` vs `pii-f7897e33@example.invalid`), Person-0638bbae (Guild vs Guild
  Education), Person-11680619 (both Lumenova AI). The mechanical rule alone (domain/local-part)
  cannot see this — it needs the company on both sides.
- A note must describe the attached record that *drives* the action: Person-f7c8fc4a has two wrong
  attachments (one no-email #80560, one different person #68964) and the first one would have
  explained a RE-POINT with "has no email".

## blocked

- **The xlsx cannot be read back on this machine.** Something scans Office files and holds an
  exclusive handle: `openpyxl`, `zipfile`, `os.path.getsize`, `Copy-Item` and `cp` all hang on a
  `.xlsx` (JSON/py reads in the same folder are instant), and overwriting one raises
  `PermissionError` until the handle expires. Verification was therefore done (a) in-process on the
  fully populated sheet before saving, and (b) byte-level in a fresh process on the CSV twin
  emitted from that same sheet — 0 problems both ways. A byte-level check of the xlsx itself is the
  one thing not proven.
- **No literal browser click-check**: the browser is not signed in to Pipedrive and entering
  credentials is out of scope. Link correctness rests on the API check above plus the URL shape
  already used in delivered reports (`/leads/inbox/{uuid}`).

## closed out

- **Handle holder identified: Avast Antivirus**, not OneDrive. `root/SecurityCenter2` lists Avast
  active (`productState 266240`) with Windows Defender passive (`393472` — hence `Get-MpPreference`
  failing with `0x800106ba`). `C:\Users\User\Desktop` is a plain local path, the OneDrive root is a
  separate tree, and the build dirs have no reparse/placeholder attributes → **the "move builds
  outside the synced path" fix does not apply**; the lock is Avast's file-system shield. Could not
  enumerate the handle itself: `fltmc filters` needs elevation (`0x80070005`), `handle.exe` is not
  installed, and `openfiles /query` needs the *maintain objects list* global flag (elevation +
  reboot — not enabled).
- **Runbook rule added** (memory `office-file-handle-lock`): any step touching an Office file gets a
  ~60s hard timeout + kill-on-timeout, never a bare read; write to a fresh path, fall forward on
  `PermissionError`; after a hang, `TaskStop` the shell **and** `Stop-Process` the orphaned children.
- Five leaked background shells stopped (20-80 min old, all wedged on xlsx handles) and their
  surviving children (`cp`, `wc`) killed. 0 processes remain.
- **Package accepted, xlsx byte-check waived by the owner.** Now **ON HOLD**: backfill 300 →
  rebuild the xlsx from a fresh snapshot (notes must flip from "персоны пока нет" to "персона уже
  создана — найди по email") → hand to Nik → Nik sends to Slava. Recorded in memory
  `slava-wrong-person-queue-hold`.

## improvable

- NO-EMAIL-CHECK (22 rows) is the biggest bucket and still needs human eyes; Smartlead also holds
  `linkedin_profile` per prospect, which would let Slava confirm identity without leaving the sheet
  (not added — it is outside the frozen column list).
- If the backfill runs before Slava starts, the notes' "персоны пока нет" becomes stale; the text
  is derived from the snapshot, so a rebuild refreshes it.
